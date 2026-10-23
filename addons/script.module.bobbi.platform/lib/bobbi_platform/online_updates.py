"""Fetch a complete release; installation stays with the existing CE transaction."""
import hashlib
from contextvars import ContextVar
from http.client import HTTPException
import os
from pathlib import Path
import re
import shutil
import ssl
import tempfile
import time
import zipfile
import zlib
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .offline_updates import MAX_BUNDLE, SignedBundle
from .online_transport import CancellableHTTPSHandler
from .updates import MAX_REDIRECTS, UpdateError, _json, _safe_path, allowed_release_redirect

OFFER_URL = 'https://raw.githubusercontent.com/2223M1/bobbi-tv/main/repository/current.json'
TRANSFER_SECONDS = 600
# Preserve the single-argument opener seam while keeping concurrent/nested
# requests isolated. The callback runs only on the caller's thread.
_ACTIVE = ContextVar('bobbi_online_active', default=lambda: None)


class Cancelled(UpdateError):
    pass


class _Redirects(HTTPRedirectHandler):
    def __init__(self):
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > MAX_REDIRECTS or not allowed_release_redirect(newurl):
            raise UpdateError('ONLINE_REDIRECT_REJECTED')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        # We never reuse the connection. Do not drain an unbounded redirect
        # body before following a permitted URL.
        if fp is not None:
            fp.close()
        return redirected

    def http_error_302(self, req, fp, code, msg, headers):
        try:
            return super().http_error_302(req, fp, code, msg, headers)
        finally:
            fp.close()  # Includes rejected/malformed URLs and failed next hops.

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _open(url):
    # No account cookies, private proxy or GitHub token belongs in this request.
    opener = build_opener(ProxyHandler({}),
                          CancellableHTTPSHandler(_ACTIVE.get(), ssl.create_default_context()), _Redirects())
    try:
        return opener.open(Request(url, headers={'User-Agent': 'BobbiTV-CE',
                                                'Accept-Encoding': 'identity'}), timeout=5)
    except HTTPError as error:
        error.close()  # HTTPError owns a response even though open() raised.
        raise


def _transfer(url, maximum, consume, cancelled, progress, expected=None):
    started = time.monotonic()
    def active():
        if cancelled():
            raise Cancelled('ONLINE_CANCELLED')
        if time.monotonic() - started >= TRANSFER_SECONDS:
            raise UpdateError('ONLINE_TIMEOUT')
    active()
    token = _ACTIVE.set(active)
    try:
        _receive(url, maximum, consume, progress, expected, active)
    except HTTPException:
        active()
        raise UpdateError('ONLINE_RESPONSE_INVALID') from None
    except Exception:
        active()
        raise
    finally:
        _ACTIVE.reset(token)


def _receive(url, maximum, consume, progress, expected, active):
    received = 0
    with _open(url) as response:
        active()
        if response.status != 200 or response.headers.get('Content-Encoding', 'identity') not in ('', 'identity'):
            raise UpdateError('ONLINE_RESPONSE_INVALID')
        length = response.headers.get('Content-Length')
        if length is not None:
            if not length.isdigit() or int(length) > maximum or (expected is not None and int(length) != expected):
                raise UpdateError('ONLINE_LENGTH_INVALID')
            length = int(length)
        while True:
            active()
            # read1 returns available bytes without waiting to fill a large
            # block. The production transport additionally polls during idle,
            # headers, chunk framing and TLS, not only between these blocks.
            read = getattr(response, 'read1', response.read)
            block = read(min(128 * 1024, maximum - received + 1))
            active()
            if not block:
                break
            received += len(block)
            if received > maximum:
                raise UpdateError('ONLINE_LENGTH_INVALID')
            consume(block)
            progress(int(100 * received / expected) if expected else 0)
        if (length is not None and received != length) or (expected is not None and received != expected):
            raise UpdateError('ONLINE_SHORT_READ')


def parse_offer(raw):
    value = _json(raw)
    if (not isinstance(value, dict) or set(value) != {'schema', 'tag', 'sequence', 'url', 'size', 'sha256'}
            or type(value['schema']) is not int or value['schema'] != 1
            or not isinstance(value['tag'], str) or not re.fullmatch(r'ce[1-9][0-9]{3,7}', value['tag'])
            or type(value['sequence']) is not int or value['sequence'] < 1
            or type(value['size']) is not int or not 0 < value['size'] <= MAX_BUNDLE
            or not isinstance(value['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['sha256'])):
        raise UpdateError('ONLINE_OFFER_INVALID')
    expected_url = ('https://github.com/2223M1/bobbi-tv/releases/download/' + value['tag']
                    + '/BobbiTV-' + value['tag'].upper() + '.bobbi-update.zip')
    if value['url'] != expected_url:
        raise UpdateError('ONLINE_OFFER_INVALID')
    return value


def latest(cancelled=lambda: False):
    chunks = []
    _transfer(OFFER_URL, 32768, chunks.append, cancelled, lambda _: None)
    return parse_offer(b''.join(chunks))


def download(offer, work, trust, cancelled=lambda: False, progress=lambda _: None):
    work = _safe_path(work)
    work.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(work).free < offer['size'] + 16 * 1024 * 1024:
        raise UpdateError('INSTALLATION_SPACE_REQUIRED')
    descriptor, name = tempfile.mkstemp(prefix='online-', suffix='.zip', dir=str(work))
    path, digest = Path(name), hashlib.sha256()
    try:
        with os.fdopen(descriptor, 'wb') as output:
            def consume(block):
                output.write(block)
                digest.update(block)
            _transfer(offer['url'], offer['size'], consume, cancelled, progress, offer['size'])
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest() != offer['sha256']:
            raise UpdateError('ONLINE_CONTENT_INVALID')
        if cancelled():
            raise Cancelled('ONLINE_CANCELLED')
        # The online index is only discovery, never a replacement trust anchor.
        try:
            with SignedBundle(path, trust, 'coreelec') as signed:
                if signed.check_all()['sequence'] != offer['sequence']:
                    raise UpdateError('ONLINE_GENERATION_MISMATCH')
        except (zipfile.BadZipFile, EOFError, zlib.error):
            raise UpdateError('ONLINE_PACKAGE_INVALID') from None
        if cancelled():
            raise Cancelled('ONLINE_CANCELLED')
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise

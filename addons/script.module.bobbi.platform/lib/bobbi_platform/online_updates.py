"""Fetch a complete release; installation stays with the existing CE transaction."""
import json
from contextvars import ContextVar
from http.client import HTTPException, IncompleteRead
import re
import shutil
import ssl
import time
import zipfile
import zlib
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .offline_updates import MAX_BUNDLE, SignedBundle
from .online_transport import CancellableHTTPSHandler
from .online_partial import PartialDownload
from .updates import MAX_REDIRECTS, UpdateError, _json, _safe_path, allowed_release_redirect

MIRROR_ROOT = 'https://gitee.com/M12223/bobbi-tv-updates'
MIRROR_FEED = MIRROR_ROOT + '/raw/master/repository/'
OFFER_URL = MIRROR_FEED + 'current.json'
FALLBACK_OFFER_URL = 'https://raw.githubusercontent.com/2223M1/bobbi-tv/main/repository/current.json'
TRANSFER_SECONDS = 600
DISCOVERY_SECONDS = 20
TRACKS = ('stable', 'preview')
# Explicit migration exception: this exact already-published stable artifact
# predates signed stable channels. No other schema-1 identity is adopted.
LEGACY_STABLE = ('ce2080', 2026102080, 95934438,
    '39e2435a50bcb8e1832e7b03929a5efbeaa6d1d9f17ce5b3704287629620331c')


def feed_url(track, source):
    if track not in TRACKS or source not in ('gitee', 'github'):
        raise UpdateError('ONLINE_TRACK_MISMATCH')
    root = MIRROR_FEED if source == 'gitee' else FALLBACK_OFFER_URL.rsplit('/', 1)[0] + '/'
    return root + track + '/current.json'


def selected_track(work, value=None):
    """Independent preference; never mutate the installation high watermark."""
    from .updates import _atomic
    path = _safe_path(work) / 'update-track.json'
    if value is not None:
        if value not in TRACKS:
            raise UpdateError('ONLINE_TRACK_MISMATCH')
        _atomic(path, dict(schema=1, track=value))
    if not path.exists():
        return 'stable'
    if path.stat().st_size > 1024:
        raise UpdateError('ONLINE_TRACK_MISMATCH')
    data = _json(path.read_bytes())
    if (not isinstance(data, dict) or set(data) != {'schema', 'track'}
            or type(data['schema']) is not int or data['schema'] != 1 or data['track'] not in TRACKS):
        raise UpdateError('ONLINE_TRACK_MISMATCH')
    return data['track']
# Preserve the single-argument opener seam while keeping concurrent/nested
# requests isolated. The callback runs only on the caller's thread.
_ACTIVE = ContextVar('bobbi_online_active', default=lambda: None)
_REQUEST_HEADERS = ContextVar('bobbi_online_headers', default=None)


class Cancelled(UpdateError):
    pass


def release_url(tag, source='gitee'):
    if not isinstance(tag, str) or not re.fullmatch(r'ce[1-9][0-9]{3,7}', tag):
        raise UpdateError('ONLINE_OFFER_INVALID')
    roots = {'gitee': MIRROR_ROOT, 'github': 'https://github.com/2223M1/bobbi-tv'}
    if source not in roots:
        raise UpdateError('ONLINE_OFFER_INVALID')
    return roots[source] + '/releases/download/' + tag + '/BobbiTV-' + tag.upper() + '.bobbi-update.zip'


def _allowed_redirect(value):
    if allowed_release_redirect(value):
        return True
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 33 for c in value):
        return False
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or url.fragment:
            return False
        if url.netloc == 'raw.giteeusercontent.com':
            # Gitee signs anonymous raw redirects. These short-lived delivery
            # parameters are not account credentials and never enter the feed.
            query = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
            member = (r'(?:current\.json|addons\.xml(?:\.md5|\.sha256)?|index\.html|'
                r'script\.bobbi\.start/script\.bobbi\.start-[0-9.]+\.zip(?:\.sha256)?|'
                r'repository\.bobbi/repository\.bobbi-[0-9.]+\.zip(?:\.sha256)?)')
            return (re.fullmatch(r'/M12223/bobbi-tv-updates/raw/master/repository/(?:(?:stable|preview)/)?' + member, url.path) is not None and
                    (not url.query or (len(query) == 2 and
                     {key for key, _ in query} == {'metadata', 'signature'} and
                     all(value for _, value in query))))
        filename = r'(?:BobbiTV-CE[1-9][0-9]{3,7}\.(?:bobbi-update|components-v1)|bobbi-component-[a-f0-9]{64})\.zip'
        if url.netloc == 'gitee.com':
            return not url.query and re.fullmatch(
                r'/M12223/bobbi-tv-updates/attach_files/[1-9][0-9]*/download/' + filename, url.path) is not None
        return (url.netloc == 'foruda.gitee.com' and
                re.fullmatch(r'/attach_file/[1-9][0-9]*/' + filename, url.path, re.IGNORECASE) is not None)
    except ValueError:
        return False


def _network_failure(error):
    if isinstance(error, HTTPError):
        return error.code in (403, 404, 408, 429, 500, 502, 503, 504)
    if isinstance(getattr(error, 'reason', error), ssl.SSLError):
        return False
    return isinstance(error, (URLError, TimeoutError, ConnectionError))


class _Redirects(HTTPRedirectHandler):
    def __init__(self):
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > MAX_REDIRECTS or not _allowed_redirect(newurl):
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
        headers = {'User-Agent': 'BobbiTV-CE', 'Accept-Encoding': 'identity'}
        headers.update(_REQUEST_HEADERS.get() or {})
        return opener.open(Request(url, headers=headers), timeout=5)
    except HTTPError as error:
        error.close()  # HTTPError owns a response even though open() raised.
        raise


def _transfer(url, maximum, consume, cancelled, progress, expected=None, deadline=None, partial=None):
    started = time.monotonic()
    deadline = min(started + TRANSFER_SECONDS, deadline) if deadline is not None else started + TRANSFER_SECONDS
    def active():
        if cancelled():
            raise Cancelled('ONLINE_CANCELLED')
        if time.monotonic() >= deadline:
            raise UpdateError('ONLINE_TIMEOUT')
    active()
    token = _ACTIVE.set(active)
    headers_token = _REQUEST_HEADERS.set(partial.request(url) if partial else {})
    try:
        _receive(url, maximum, consume, progress, expected, active, partial)
    except IncompleteRead:
        active()
        raise UpdateError('ONLINE_SHORT_READ' if partial else 'ONLINE_RESPONSE_INVALID') from None
    except HTTPException:
        active()
        raise UpdateError('ONLINE_RESPONSE_INVALID') from None
    except Exception:
        active()
        raise
    finally:
        _REQUEST_HEADERS.reset(headers_token)
        _ACTIVE.reset(token)


def _receive(url, maximum, consume, progress, expected, active, partial=None):
    received = 0
    with _open(url) as response:
        active()
        if response.headers.get('Content-Encoding', 'identity') not in ('', 'identity'):
            raise UpdateError('ONLINE_RESPONSE_INVALID')
        if partial is None and response.status != 200:
            raise UpdateError('ONLINE_RESPONSE_INVALID')
        base = partial.response(response) if partial else 0
        maximum -= base
        remaining = expected-base if expected is not None else None
        length = response.headers.get('Content-Length')
        if length is not None:
            if not length.isdigit() or int(length) > maximum or (remaining is not None and int(length) != remaining):
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
            progress(int(100 * (base+received) / expected) if expected else 0)
        if (length is not None and received != length) or (remaining is not None and received != remaining):
            raise UpdateError('ONLINE_SHORT_READ')


def parse_offer(raw, track=None):
    value = _json(raw)
    fields = {'schema', 'tag', 'sequence', 'url', 'size', 'sha256'}
    if isinstance(value, dict) and value.get('schema') == 2:
        fields |= {'track', 'manifest_channel', 'prerelease', 'versions'}
    if (not isinstance(value, dict) or set(value) != fields
            or type(value['schema']) is not int or value['schema'] not in (1, 2)
            or not isinstance(value['tag'], str) or not re.fullmatch(r'ce[1-9][0-9]{3,7}', value['tag'])
            or type(value['sequence']) is not int or value['sequence'] < 1
            or type(value['size']) is not int or not 0 < value['size'] <= MAX_BUNDLE
            or not isinstance(value['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['sha256'])):
        raise UpdateError('ONLINE_OFFER_INVALID')
    if value['url'] not in (release_url(value['tag']), release_url(value['tag'], 'github')):
        raise UpdateError('ONLINE_OFFER_INVALID')
    legacy = tuple(value[key] for key in ('tag', 'sequence', 'size', 'sha256')) == LEGACY_STABLE
    if value['schema'] == 2:
        if (value['track'] not in TRACKS or type(value['prerelease']) is not bool
                or value['prerelease'] != (value['track'] == 'preview')
                or value['manifest_channel'] != ('private-candidate' if value['track'] == 'preview' else 'private-stable')
                   and not (legacy and value['track'] == 'stable' and value['manifest_channel'] == 'private-candidate')
                or not isinstance(value['versions'], dict) or not value['versions']
                or len(value['versions']) > 128
                or any(not isinstance(name, str) or not re.fullmatch(r'[a-z0-9_.-]{1,128}', name)
                       or not isinstance(version, str) or not re.fullmatch(r'[0-9][a-zA-Z0-9.+_-]{0,63}', version)
                       for name, version in value['versions'].items())):
            raise UpdateError('ONLINE_TRACK_MISMATCH')
    if track is not None and (track not in TRACKS or
            (value['schema'] == 1 and not (legacy and track == 'stable')) or
            (value['schema'] == 2 and value['track'] != track)):
        raise UpdateError('ONLINE_TRACK_MISMATCH')
    return value


def check_offer_manifest(offer, manifest):
    if manifest['sequence'] != offer['sequence']:
        raise UpdateError('ONLINE_GENERATION_MISMATCH')
    if offer['schema'] == 2 and (manifest['channel'] != offer['manifest_channel']
            or {r['id']: r['version'] for r in manifest['components']} != offer['versions']):
        raise UpdateError('ONLINE_TRACK_MISMATCH')


def latest(cancelled=lambda: False, *, track='stable', report=None):
    deadline = time.monotonic() + min(TRANSFER_SECONDS, DISCOVERY_SECONDS)
    urls = tuple(feed_url(track, source) for source in ('gitee', 'github'))
    candidates, unavailable = [], []
    last_error = None
    for index, url in enumerate(urls):
        chunks = []
        legacy = False
        try:
            # Reserve a share for each mirror; one timeout cannot starve the other.
            until = deadline if index else min(deadline, time.monotonic() + DISCOVERY_SECONDS / 2)
            try:
                _transfer(url, 32768, chunks.append, cancelled, lambda _: None, deadline=until)
            except HTTPError as error:
                if error.code != 404 or track != 'stable':
                    raise
                chunks.clear()
                legacy = True
                _transfer((OFFER_URL, FALLBACK_OFFER_URL)[index], 32768, chunks.append,
                          cancelled, lambda _: None, deadline=until)
            try:
                candidates.append(parse_offer(b''.join(chunks), track))
            except UpdateError:
                if not legacy:
                    raise
                # Compatibility is an allowlist, not a reinterpretation of old
                # channel-less offers. Still try the other official mirror.
                raise UpdateError('ONLINE_LEGACY_UNVERIFIED') from None
        except (URLError, TimeoutError, ConnectionError, UpdateError) as error:
            if isinstance(error, Cancelled) or not (_network_failure(error) or
                    str(error) in ('ONLINE_TIMEOUT', 'ONLINE_LEGACY_UNVERIFIED')):
                raise
            unavailable.append(index)
            last_error = error
    if not candidates:
        raise last_error or UpdateError('ONLINE_OFFER_INVALID')
    candidates.sort(key=lambda value: value['sequence'], reverse=True)
    if len(candidates) == 2 and candidates[0]['sequence'] == candidates[1]['sequence']:
        if {k: v for k, v in candidates[0].items() if k != 'url'} != {k: v for k, v in candidates[1].items() if k != 'url'}:
            raise UpdateError('ONLINE_MIRROR_CONFLICT')
    if report is not None:
        report.update(track=track, mirrors=('unavailable' if unavailable else 'out-of-sync'
            if len({o['sequence'] for o in candidates}) > 1 else 'synchronized'),
            compatibility='pinned-schema1' if candidates[0]['schema'] == 1 else 'versioned')
    return candidates[0]


def download(offer, work, trust, cancelled=lambda: False, progress=lambda _: None, *, deadline=None, report=None):
    offer = parse_offer(json.dumps(offer))
    work = _safe_path(work)
    work.mkdir(parents=True, exist_ok=True)
    deadline = min(deadline, time.monotonic()+TRANSFER_SECONDS) if deadline is not None else time.monotonic()+TRANSFER_SECONDS
    if report is not None:
        report['downloaded_bytes'] = 0
    urls = tuple(dict.fromkeys((offer['url'], release_url(offer['tag']), release_url(offer['tag'], 'github'))))

    def active():
        if cancelled():
            raise Cancelled('ONLINE_CANCELLED')
        if time.monotonic() >= deadline:
            raise UpdateError('ONLINE_TIMEOUT')

    def recoverable(error):
        return (_network_failure(error) or type(error) is UpdateError
                and str(error) in ('ONLINE_SHORT_READ', 'ONLINE_TIMEOUT'))

    active()
    with PartialDownload(work, offer, urls, active) as partial:
        def consume(block):
            if report is not None:
                report['downloaded_bytes'] += len(block)
            partial.write(block)
        try:
            if partial.source in urls:
                urls = (partial.source,) + tuple(url for url in urls if url != partial.source)
            if partial.count != offer['size']:
                for index, url in enumerate(urls):
                    active()
                    # A mirror change starts a full response; never stitch origins.
                    # The same file is reused, even for a full restart: truncation
                    # releases the old prefix before replacing it.
                    remaining = offer['size'] - partial.count
                    if shutil.disk_usage(work).free < remaining + 16 * 1024 * 1024:
                        raise UpdateError('INSTALLATION_SPACE_REQUIRED')
                    try:
                        try:
                            _transfer(url, offer['size'], consume, cancelled, progress,
                                      offer['size'], deadline, partial)
                        except HTTPError as error:
                            if error.code != 416 or not partial.request_offset:
                                raise
                            partial.reset()  # One bounded full restart of this origin.
                            _transfer(url, offer['size'], consume, cancelled, progress,
                                      offer['size'], deadline, partial)
                        break
                    except Exception as error:
                        if index == len(urls)-1 or not recoverable(error):
                            raise
                        active()
                        progress(0)
            partial.flush()
            if partial.digest.hexdigest() != offer['sha256']:
                raise UpdateError('ONLINE_CONTENT_INVALID')
            progress(100)
            active()
            # Discovery and checkpoints never replace the existing trust anchor.
            try:
                with SignedBundle(partial.path, trust, 'coreelec') as signed:
                    check_offer_manifest(offer, signed.check_all())
            except (zipfile.BadZipFile, EOFError, zlib.error):
                raise UpdateError('ONLINE_PACKAGE_INVALID') from None
            active()
            return partial.deliver()
        except BaseException as error:
            if recoverable(error) and not cancelled():
                try:
                    kept = partial.checkpoint()
                except OSError:
                    kept = False
                if not kept:
                    partial.discard()
            else:
                partial.discard()
            raise

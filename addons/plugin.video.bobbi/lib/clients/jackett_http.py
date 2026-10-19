"""Disposable, OS-supervised HTTP batch; no Kodi network worker survives return."""
import base64
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Lock
import time

import requests

from bobbi_core.child_lifetime import ParentLifetime
from bobbi_core.subtitle_io import _interpreter


_UNREAPED = set()
_REAP_LOCK = Lock()
_LIFETIME_LOCK = Lock()
MAX_BATCH_BYTES = 16 * 1024 * 1024
CLEANUP_SECONDS = .2


class HTTPBatchError(RuntimeError):
    """Only the error class crosses the diagnostics boundary, never URLs."""


class _Lifetime:
    """Serialize Job bookkeeping, not independent providers' network work."""
    def __enter__(self):
        with _LIFETIME_LOCK:
            self.owner = ParentLifetime()
        return self

    def contract(self, expires):
        return self.owner.contract(expires)

    def attach(self, process):
        with _LIFETIME_LOCK:
            self.owner.attach(process)

    def close(self):
        with _LIFETIME_LOCK:
            self.owner.close()

    def __exit__(self, *args):
        self.close()


def _reap(process):
    # Independent Jackett/AnimeGarden batches cannot clear each other's latch.
    with _REAP_LOCK:
        _UNREAPED.add(process)
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=.05)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=.1)
        _UNREAPED.remove(process)


def iter_events(session, urls, deadline, cancelled, mode, limit, request_timeout=2.0):
    try:
        from lib.clients.portable_http import iter_events as stock_events
        yield from stock_events(session, urls, deadline, cancelled, mode, limit, request_timeout)
    except Exception as error:
        raise HTTPBatchError(type(error).__name__) from error


def _verification_path(verification):
    if verification is False:
        raise ValueError('Verified HTTP transport required')
    # requests' True means its configured bundle, NOT the system interpreter's
    # OpenSSL defaults. The isolated child has neither certifi nor Kodi imports.
    if verification is True or verification is None:
        verification = requests.adapters.DEFAULT_CA_BUNDLE_PATH
    return os.fspath(verification)


def _iter_events(session, urls, deadline, cancelled, mode, limit, request_timeout):
    """Yield (ordinal, state, reason, response). All secrets use private stdin.

    The single disposable child has at most four HTTP workers. Its stdout is a
    private regular file, not PIPE reader threads. Complete sibling results are
    harvested while other requests run; cancellation kills/reaps the whole child.
    """
    with _REAP_LOCK:
        pending = list(_UNREAPED)
    for process in pending:
        _reap(process)
    if not urls:
        return
    if len(urls) > 256 or mode not in ('rss', 'json', 'inventory'):
        raise ValueError('Bounded HTTP batch required')
    if type(limit) is not int or not 0 < limit <= 4 * 1024 * 1024:
        raise ValueError('Bounded HTTP response required')
    if request_timeout is not None and (type(request_timeout) not in (int, float)
            or not math.isfinite(request_timeout) or not 0 < request_timeout <= 8):
        raise ValueError('Bounded HTTP request timeout required')
    transfer_end = deadline - CLEANUP_SECONDS
    if cancelled() or time.monotonic() >= transfer_end:
        return
    entries = []
    for url in urls:
        if cancelled() or time.monotonic() >= transfer_end:
            return
        prepared = session.prepare_request(requests.Request('GET', url))
        settings = session.merge_environment_settings(prepared.url, {}, False, None, None)
        entries.append(dict(url=prepared.url, headers=dict(prepared.headers),
                            proxies=settings.get('proxies') or {},
                            verify=_verification_path(settings.get('verify'))))
    worker = Path(__file__).with_name('jackett_http_worker.py')
    import bobbi_core.child_lifetime as child_lifetime
    with _Lifetime() as lifetime, tempfile.TemporaryDirectory(prefix='am6b-http-') as directory, \
            tempfile.TemporaryFile() as source, open(Path(directory) / 'reply', 'w+b') as sink, \
            open(Path(directory) / 'reply', 'rb') as output:
        command = dict(entries=entries, limit=limit, mode=mode, total_limit=MAX_BATCH_BYTES,
            request_timeout=request_timeout,
            lifetime=lifetime.contract(transfer_end), lifetime_module=child_lifetime.__file__,
            parser=str(Path(__file__).parents[1] / 'utils' / 'parsers' / 'xmltodict.py'))
        payload = json.dumps(command).encode('utf-8')
        if len(payload) > 1024 * 1024:
            raise ValueError('HTTP request batch too large')
        source.write(payload)
        source.seek(0)
        # Windows venv python.exe can be a launcher: wait() may only reap the
        # launcher while its real interpreter still owns stdout. Use the actual
        # stdlib interpreter; the child intentionally has no site dependencies.
        executable = (getattr(sys, '_base_executable', None) if sys.platform == 'win32' else None) or _interpreter()
        process = subprocess.Popen([executable, '-I', '-S', '-B', str(worker)],
            stdin=source, stdout=sink, stderr=subprocess.DEVNULL, close_fds=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            lifetime.attach(process)
            offset, received = 0, 0
            while True:
                if cancelled() or time.monotonic() >= transfer_end:
                    break
                output.seek(offset)
                line = output.readline(6 * 1024 * 1024 + 1)
                if line.endswith(b'\n'):
                    offset += len(line)
                    received += len(line)
                    if len(line) > 6 * 1024 * 1024 or received > 24 * 1024 * 1024:
                        raise ValueError('HTTP IPC size exceeded')
                    event = json.loads(line)
                    ordinal = event['ordinal']
                    if type(ordinal) is not int or not 0 <= ordinal < len(urls):
                        raise ValueError('HTTP IPC ordinal invalid')
                    response = None
                    if type(event.get('status')) is int:
                        response = requests.Response()
                        response.status_code = event['status']
                    if event['state'] == 'succeeded':
                        response._content = base64.b64decode(event.get('body', ''), validate=True)
                        if 'items' in event:
                            response._am6b_items = event['items']
                        response._am6b_parse_failed = bool(event.get('parse_failed'))
                    yield ordinal, event['state'], event['reason'], response
                    continue
                if len(line) > 6 * 1024 * 1024:
                    raise ValueError('HTTP IPC size exceeded')
                if process.poll() is not None:
                    process.wait()
                    if line or process.returncode:
                        if time.monotonic() < transfer_end and not cancelled():
                            raise RuntimeError('HTTP worker failed')
                    break
                if cancelled() or time.monotonic() >= transfer_end:
                    break
                time.sleep(.01)
        finally:
            _reap(process)
            lifetime.close()

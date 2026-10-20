"""Exec-isolated subtitle HTTP, bounded by the caller's absolute deadline.

Where a CLI interpreter exists, DNS, TLS and body reads live in one disposable
interpreter. Embedded-only hosts use a single cooperative, deadline-observed
worker; an OS DNS stall may outlive the caller but cannot spawn more workers.
No credentials occur in argv/environment. Anonymous private temporary files
avoid PIPE reader threads (notably subprocess.communicate on Windows).
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Lock, Event, Thread
import time

from bobbi_core.child_lifetime import LifetimeError, ParentLifetime


_LOCK = Lock()
_UNREAPED = None
_EMBEDDED = None
POLL_SECONDS = .01
CLEANUP_SECONDS = .15


class SubtitleIOStopped(RuntimeError):
    pass


def _interpreter():
    # Embedded Kodi's sys.executable is kodi.bin, not a Python CLI. CoreELEC
    # also runs the preparation service with its independent system Python.
    executable = Path(sys.executable)
    if executable.name.lower().startswith('python') and executable.is_file():
        return str(executable)
    for candidate in ('/usr/bin/python3', '/usr/bin/python'):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise SubtitleIOStopped('SUBTITLE_IO_PYTHON_UNAVAILABLE')


def _embedded_read(command, deadline, cancelled, clock):
    """One cooperative fallback for embedded Kodi without an executable Python.

    Never spawn an unbounded population when OS DNS is stuck. The caller stops
    observing at its deadline; the single outstanding worker prevents further
    work until it has exited. No late bytes can be applied to another playback.
    """
    global _EMBEDDED
    if _EMBEDDED is not None and _EMBEDDED.is_alive():
        raise SubtitleIOStopped('SUBTITLE_IO_BUSY')
    completed, stopped, result = Event(), Event(), {}
    command = dict(command, _cancelled=lambda: stopped.is_set() or cancelled(),
                   _deadline=time.monotonic() + max(0, deadline-clock()))
    def worker():
        try:
            from bobbi_core.subtitle_io_worker import fetch
            result['raw'] = fetch(command)
        except Exception as error:
            result['error'] = (str(error) if isinstance(error, ValueError)
                               else 'SUBTITLE_IO_' + type(error).__name__)
        finally:
            completed.set()
    _EMBEDDED = Thread(target=worker, name='bobbi-subtitle-io', daemon=True)
    _EMBEDDED.start()
    try:
        while not completed.wait(.02):
            if cancelled() or clock() >= deadline:
                raise SubtitleIOStopped('SUBTITLE_IO_DEADLINE')
        if cancelled() or clock() >= deadline:
            raise SubtitleIOStopped('CANCELLED_OR_DEADLINE')
        if 'error' in result:
            reason = result['error']
            if (not reason.startswith(('SUBTITLE_IO_', 'ASSRT_HTTP_', 'TORRENT_SUBTITLE_', 'OPENSUBTITLES_'))
                    or not reason.replace('_', '').isalnum() or len(reason) > 80):
                reason = 'SUBTITLE_IO_FAILED'
            raise SubtitleIOStopped(reason)
        return result['raw']
    finally:
        stopped.set()


def _reap(process):
    """Terminate then kill/join; a pathological OS failure forbids new children."""
    global _UNREAPED
    # Latch BEFORE any OS action: terminate/kill/wait can themselves fail or
    # be interrupted. Only a confirmed wait is permission to create a child.
    _UNREAPED = process
    try:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=.05)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=.05)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SubtitleIOStopped('SUBTITLE_IO_REAP_FAILED') from error
    # BaseException deliberately propagates while retaining the latch.
    _UNREAPED = None


def read_http(url, deadline, cancelled, limit, headers=None, mode='assrt',
              method='GET', json_body=None, auth=None, clock=time.monotonic,
              trusted_proxy=None):
    """Return bounded bytes; only the explicitly configured torrent may be local.

    Startup, transfer and cleanup share one budget. Cleanup starts early, not
    after the result deadline. A failed optional I/O is safe to ignore only
    while the caller's original guard still permits publishing a candidate.
    """
    global _UNREAPED

    def guard():
        if cancelled() or clock() >= deadline:
            raise SubtitleIOStopped('CANCELLED_OR_DEADLINE')

    guard()
    if type(limit) is not int or not 0 < limit <= 8 * 1024 * 1024:
        raise ValueError('Bounded subtitle IO required')
    if trusted_proxy is not None and (trusted_proxy != 'am6b-tmdb-fallback-v1'
            or mode not in ('opensubtitles_api', 'opensubtitles_download')):
        raise ValueError('SUBTITLE_IO_ORIGIN')
    # No wait on a second I/O owner; there is never a queued child population.
    if not _LOCK.acquire(False):
        raise SubtitleIOStopped('SUBTITLE_IO_BUSY')
    process = None
    try:
        if _UNREAPED is not None:
            try:
                if _UNREAPED.poll() is None:
                    raise SubtitleIOStopped('SUBTITLE_IO_REAP_FAILED')
                _UNREAPED.wait(timeout=0)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise SubtitleIOStopped('SUBTITLE_IO_REAP_FAILED') from error
            _UNREAPED = None
        try:
            executable = _interpreter()
        except SubtitleIOStopped as error:
            if str(error) != 'SUBTITLE_IO_PYTHON_UNAVAILABLE':
                raise
            return _embedded_read(dict(url=url, limit=limit, headers=headers or {},
                mode=mode, method=method, json_body=json_body, auth=auth,
                trusted_proxy=trusted_proxy), deadline, cancelled, clock)
        guard()
        remaining = deadline - clock()
        transfer_end = deadline - min(CLEANUP_SECONDS, remaining / 4)
        # Map injected policy clocks onto the actual OS monotonic clock. The
        # absolute child expiry is fixed before spawn, so startup consumes it.
        expires = time.monotonic() + max(0, transfer_end - clock())
        with ParentLifetime() as lifetime, tempfile.TemporaryFile() as request, tempfile.TemporaryFile() as response:
            payload = json.dumps(dict(url=url, limit=limit, headers=headers or {},
                mode=mode, method=method, json_body=json_body, auth=auth,
                trusted_proxy=trusted_proxy,
                lifetime=lifetime.contract(expires))).encode('utf-8')
            if len(payload) > 16384:
                raise ValueError('Subtitle IO request too large')
            request.write(payload)
            request.seek(0)
            guard()
            process = subprocess.Popen([executable, '-I', '-S', '-B',
                str(Path(__file__).with_name('subtitle_io_worker.py'))],
                stdin=request, stdout=response, stderr=subprocess.DEVNULL,
                close_fds=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                lifetime.attach(process)
                while process.poll() is None:
                    guard()
                    if clock() >= transfer_end:
                        raise SubtitleIOStopped('SUBTITLE_IO_DEADLINE')
                    time.sleep(min(POLL_SECONDS, max(0, transfer_end - clock())))
                process.wait()
                guard()
                response.seek(0)
                envelope = response.readline(1025)
                if len(envelope) > 1024 or not envelope.endswith(b'\n'):
                    if time.monotonic() >= expires:
                        raise SubtitleIOStopped('SUBTITLE_IO_DEADLINE')
                    raise SubtitleIOStopped('SUBTITLE_IO_RESPONSE_INVALID')
                status = json.loads(envelope)
                if status.get('error'):
                    raise SubtitleIOStopped(status['error'])
                raw = response.read(limit + 1)
                if len(raw) > limit or len(raw) != status.get('bytes') or process.returncode:
                    raise SubtitleIOStopped('SUBTITLE_IO_RESPONSE_INVALID')
                guard()
                return raw
            finally:
                _reap(process)
    except LifetimeError as error:
        raise SubtitleIOStopped('SUBTITLE_IO_LIFETIME_FAILED') from error
    finally:
        _LOCK.release()

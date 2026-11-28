"""Prepare the exact byte ranges Kodi needs from the selected BT video."""
import time
from threading import Event, Lock, Thread

from .backend import BackendError
from .http_io import RequestIO

MIB = 1024 * 1024
SMALL_FILE = 2 * MIB
PREFIX = 12 * MIB


def ranges(length, chunk):
    # Kodi FileCache::Seek clamps a near-EOF seek to fileSize - chunkSize.
    tail = max(MIB, chunk) if type(chunk) is int and 0 < chunk <= 4 * MIB else 2 * MIB
    if length <= PREFIX + tail:
        return ((0, length - 1),)
    return ((length - tail, length - 1), (0, PREFIX - 1))


def duration_hint(prefix):
    """Optional Matroska Segment/Info from bytes already received; no extra IO."""
    from bobbi_core.matroska_qualification import (
        EBML, SEGMENT, INFO, UnsupportedLayout, vint, floating, uint)
    if not prefix.startswith(b'\x1a\x45\xdf\xa3'):
        return None

    def header(at):
        ident, iw, _ = vint(prefix, at, 4, True)
        size, sw, unknown = vint(prefix, at + iw, 8)
        start = at + iw + sw
        return ident, start, start + size, unknown

    try:
        ident, _, pos, unknown = header(0)
        if ident != EBML or unknown:
            return None
        ident, pos, segment_end, unknown = header(pos)
        if ident != SEGMENT:
            return None
        bound = len(prefix) if unknown else min(len(prefix), segment_end)
        for _ in range(32):
            if pos >= bound:
                break
            ident, start, pos, unknown = header(pos)
            if unknown or pos > bound:
                break
            if ident != INFO:
                continue
            scale, duration, seen = 1_000_000, None, set()
            for _ in range(48):
                if start == pos:
                    seconds = duration * scale / 1e9 if duration else 0
                    return seconds if 1 <= seconds <= 7 * 86400 else None
                field, value, end, unknown = header(start)
                if unknown or end > pos:
                    break
                if field in (0x2ad7b1, 0x4489):
                    if field in seen:
                        return None
                    seen.add(field)
                    if field == 0x4489:
                        duration = floating(prefix[value:end])
                    else:
                        scale = uint(prefix[value:end])
                        if not 0 < scale <= 1_000_000_000:
                            return None
                start = end
            return None
    except (UnsupportedLayout, OverflowError):
        pass
    return None


def extra_prefix(length, duration, rate, remaining, tail_start):
    """Cover an observed shortfall within the existing bounded buffer stages.

    Limit the optional read by measured selected-file delivery and the time
    left. No swarm count, filename, container extension or unknown duration
    can authorize an open or make a fast file wait.
    """
    if not duration or rate <= 0 or remaining <= 20:
        return 0
    bitrate = length / duration
    if rate >= bitrate:
        return 0
    desired = min(64 * MIB, (bitrate - rate) * 90 + bitrate * 4, tail_start)
    affordable = rate * (remaining - 15) * .75
    return max(0, int(min(desired - PREFIX, affordable)) // MIB * MIB)


class SelectedOpening:
    """One media request per disjoint span, with independent control IO."""
    def __init__(self, url, length, chunk, timeout, session_factory, clock=time.monotonic):
        self.url, self.length, self.spans = url, length, ranges(length, chunk)
        self.target = sum(end - start + 1 for start, end in self.spans)
        self.timeout, self.session_factory, self.clock = timeout, session_factory, clock
        self.stop, self.done, self.lock = Event(), Event(), Lock()
        self.received, self.error = 0, None
        # Planning horizon only: the resolver still owns the first deadline,
        # offers Keep Waiting once, and interrupts this reader on Back/timeout.
        self.planning_deadline = clock() + max(0, timeout - 30)
        self.extended_deadline, self.base_ready = None, False
        self.thread = Thread(target=self._run, name='bobbi-selected-file-opening')

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()

    def continued(self, deadline):
        with self.lock:
            self.extended_deadline = deadline

    def _active(self):
        if self.stop.is_set():
            raise BackendError('TORRENT_CANCELLED', 'cancelled')

    def _read(self, session, start, end, capture=False):
        self._active()
        span = '{}-{}'.format(start, end)
        with session.get(self.url, headers={'Range': 'bytes=' + span, 'Accept-Encoding': 'identity'},
                         timeout=(3.05, self.timeout), allow_redirects=False, stream=True) as response:
            if (response.status_code != 206 or response.headers.get('Content-Range') !=
                    'bytes {}/{}'.format(span, self.length) or
                    response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
                raise BackendError('TORRENT_OPENING_RANGE_INVALID', 'preload_error')
            count, prefix = 0, bytearray()
            for block in response.iter_content(65536):
                self._active()
                count += len(block)
                if count > end - start + 1:
                    raise BackendError('TORRENT_OPENING_RANGE_INVALID', 'preload_error')
                if capture and len(prefix) < 65536:
                    prefix.extend(block[:65536-len(prefix)])
                with self.lock:
                    self.received += len(block)
            if count != end - start + 1:
                raise BackendError('TORRENT_OPENING_INCOMPLETE', 'preload_error')
            return bytes(prefix)

    def _run(self):
        try:
            session = self.session_factory()
            try:
                session.trust_env = False
                with RequestIO(session, self._active):
                    for start, end in self.spans:
                        began = self.clock()
                        prefix = self._read(session, start, end, capture=start == 0)
                    # The last base span starts at zero and has completed. The
                    # optional extension is adjacent; it never re-reads a byte.
                    with self.lock:
                        deadline = self.extended_deadline or self.planning_deadline
                    extra = 0
                    if len(self.spans) == 2:
                        now = self.clock()
                        extra = extra_prefix(self.length, duration_hint(prefix),
                                             PREFIX / max(.001, now - began),
                                             deadline - now, self.spans[0][0])
                    with self.lock:
                        self.base_ready = True
                        self.target += extra
                    if extra:
                        import requests
                        from urllib3.exceptions import HTTPError
                        try:
                            self._read(session, PREFIX, PREFIX + extra - 1)
                        except (requests.RequestException, HTTPError, OSError):
                            self._active()  # Back wins over an optional network failure.
                            # Both required ranges were already received in full.
                            # Identity and range-contract errors remain terminal.
            finally:
                session.close()
        except BackendError as error:
            self.error = error
        except Exception:
            self.error = BackendError('TORRENT_OPENING_UNAVAILABLE', 'preload_error')
        finally:
            self.done.set()

    def snapshot(self):
        finished = self.done.is_set()
        if finished and self.error:
            raise self.error
        with self.lock:
            return finished, self.received, self.target, self.base_ready

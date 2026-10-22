"""Loopback, bounded Range transport for identity-checked renewable share URLs.

Public port is owned by the long-lived stock Kodi service. The private AM6B
build used a standalone preparation service; transport identity is unchanged.
No cloud writes, full-file cache, alternate edition, cookies to CDN or player calls.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from threading import BoundedSemaphore, Condition, Event, Lock, Thread, local
from collections import deque
import hashlib
import json
import re
import select
import socket
import time
from urllib.parse import parse_qs
from uuid import uuid4
from dataclasses import dataclass
import math

STARTUP_SEGMENT_BYTES = 8 * 1024**2
DIAGNOSTIC_STARTUP_SEGMENT_BYTES = 1024**2
MAX_SEGMENT_BYTES = 64 * 1024**2
DELIVERY_CHUNK_BYTES = 128 * 1024
DIAGNOSTIC_BATCH_SECONDS = .002
DELIVERY_POLL_SECONDS = 1
FETCH_CHUNK_BYTES = 32 * 1024
PROGRESSIVE_QUEUE_BYTES = 8 * 1024**2
BINDING_IDENTITY = ('locator', 'guid', 'title', 'size')
NEGATIVE_GRANT_SECONDS = 30
OBSERVATION_LIMIT = 48
OBSERVATION_WAIT_MS = 25
OBSERVATION_REASONS = frozenset((
    'SHARE_STOPPED', 'SHARE_RANGE_IDENTITY', 'SHARE_RANGE_OVERFLOW',
    'SHARE_READ_UNAVAILABLE', 'SHARE_READ_TRUNCATED', 'SHARE_READ_REJECTED',
    'SHARE_REFRESH_BUDGET', 'SHARE_TRANSPORT_INVALID',
    'share_login_required', 'share_unavailable', 'share_network', 'share_invalid_response',
    'share_cancelled', 'share_deadline', 'share_identity_changed', 'share_invalid_locator',
    'share_refresh_required', 'share_revoked', 'share_http_rejected', 'share_network_timeout'))
OBSERVATION_NUMBERS = frozenset((
    'http', 'gate', 'start', 'end', 'monotonic_us', 'offset', 'delivered',
    'status', 'first_block_bytes', 'block_end', 'wait_ms', 'wait_begin_us',
    'wait_end_us', 'upstream_start', 'bytes', 'remaining', 'retry', 'fetch_ms',
    'write_ms', 'wall_ms', 'suppressed', 'len', 'requested', 'queue_peak', 'queue_limit', 'api_code',
    'queue_puts', 'queue_gets', 'send_calls', 'grant_us', 'connect_us', 'read_wait_us',
    'queue_room_us', 'queue_put_us', 'queue_get_us', 'socket_send_us', 'retry_window', 'upstream_accepted',
    'batch_budget_us', 'producer_cpu_us', 'consumer_cpu_us',
    'producer_cancel_calls', 'consumer_cancel_calls', 'producer_cancel_us', 'consumer_cancel_us',
    'read_zero', 'read_eof', 'read_le4k', 'read_le32k', 'read_le128k', 'read_gt128k',
    'get_zero', 'get_eof', 'get_le4k', 'get_le32k', 'get_le128k', 'get_gt128k'))
OBSERVATION_HASHES = {'run': 16, 'request': 16, 'transport': 64, 'file': 64}
OBSERVATION_ENUMS = {
    'exception': frozenset(('ShareError','AccountError','ValueError','TypeError','KeyError',
                            'OSError','TimeoutError','HTTPError','other')),
    'phase': frozenset(('begin', 'response', 'gate_wait', 'upstream_status',
                       'yield', 'retry', 'fetch_end', 'write_end', 'end', 'window')),
    'stage': frozenset(('range', 'gate', 'fetch', 'grant', 'connect',
                       'response_check', 'body', 'headers', 'write')),
    'cancel': frozenset(('none', 'account_revoked', 'service_stop',
                        'socket_error', 'socket_probe_error', 'diagnostic_expired')),
    'timing_scope': frozenset(('diagnostic_cumulative',)),
    'diagnostic_mode': frozenset(('open_range', 'open_range_microbatch', 'open_range_bound_guard',
                                 'block_startup_1m')),
    'method': frozenset(('GET', 'HEAD')),
    'role': frozenset(('unknown',)),
    'outcome': frozenset(('incomplete', 'rejected', 'head_complete',
                         'complete', 'cancelled', 'failed')),
    'reason': OBSERVATION_REASONS | frozenset((
        'none', 'invalid_range', 'gate_cancelled', 'after_fetch',
        'delivery_incomplete', 'range_complete', 'before_fetch',
        'unexpected_exception', 'contention', 'address_renewed', 'read_resumed')),
}


def observation_error(error):
    """Closed error taxonomy, retaining file/request correlation but no body."""
    code = error.args[0] if len(error.args) == 1 and type(error.args[0]) is str else None
    category = code if code in OBSERVATION_REASONS else 'unexpected_exception'
    fields = {'exception': type(error).__name__ if type(error).__name__ in
              OBSERVATION_ENUMS['exception'] else 'other'}
    # Base transport also runs without the optional catalog module. Diagnostics
    # must never replace the original range failure with an import exception.
    try:
        from bobbi_catalog.api import ShareError
    except ImportError:
        ShareError = ()
    if isinstance(error, ShareError):
        candidate = 'share_' + error.code
        category = candidate if candidate in OBSERVATION_REASONS else error.code
        if category not in OBSERVATION_REASONS:
            category = 'unexpected_exception'
        if error.http_status is not None:
            fields['status'] = error.http_status
        if error.api_code is not None:
            fields['api_code'] = error.api_code
    return category, fields


def observation_fields(row):
    """A closed, bounded schema; a future caller cannot log URLs/paths by accident."""
    if type(row) is not dict:
        return {}
    safe = {}
    for key in OBSERVATION_NUMBERS:
        value = row.get(key)
        if type(value) is int and 0 <= value <= 2**63 - 1:
            safe[key] = value
    for key, length in OBSERVATION_HASHES.items():
        value = row.get(key)
        if type(value) is str and len(value) == length and re.fullmatch('[0-9a-f]+', value):
            safe[key] = value
    for key, allowed in OBSERVATION_ENUMS.items():
        value = row.get(key)
        if type(value) is str and value in allowed:
            safe[key] = value
    for key in ('started', 'initial', 'complete', 'producer_complete', 'thread_cpu_supported'):
        if type(row.get(key)) is bool:
            safe[key] = row[key]
    return safe


def observation_line(row):
    """One bounded JSON record for the portable host's existing report sink."""
    return json.dumps(dict(event='share_read', **observation_fields(row)),
                      sort_keys=True, separators=(',', ':'))


def observation_json(row):
    # This module runs in the standalone preparation service. Its stdout is
    # journalled; keep this separate from the existing report callback contract.
    print(json.dumps(dict(event='share_read', at=time.time(), **observation_fields(row)),
                     sort_keys=True), flush=True)


class ReadGate:
    """FIFO same-file upstream ownership, with cooperative prefix yielding."""
    def __init__(self):
        self.condition = Condition()
        self.queue = deque()
        self.active = False
        self.last_yield = None
        self.diagnostic_id = 0

    def acquire(self, cancelled=lambda: False, initial=True):
        ticket = object()
        queued = (ticket, initial)
        with self.condition:
            if initial:
                position = next((i for i, (_, urgent) in enumerate(self.queue) if not urgent), len(self.queue))
                self.queue.insert(position, queued)
            else:
                self.queue.append(queued)
            while self.active or self.queue[0][0] is not ticket:
                if cancelled():
                    self.queue.remove(queued)
                    self.condition.notify_all()
                    return False
                self.condition.wait(.05)
            if cancelled():
                self.queue.popleft()
                self.condition.notify_all()
                return False
            self.queue.popleft()
            self.active = True
            return True

    def release(self):
        with self.condition:
            self.active = False
            self.condition.notify_all()

    def contended(self):
        with self.condition:
            # Only a new HTTP read/seek needs low initial latency. Two ongoing
            # sequential readers must not ping-pong every 32 KiB and sacrifice
            # CDN throughput to repeated TLS handshakes and admission races.
            return any(urgent for _, urgent in self.queue)

    def note_yield(self):
        with self.condition:
            self.last_yield = time.monotonic()

    def recently_yielded(self):
        with self.condition:
            return self.last_yield is not None and time.monotonic() - self.last_yield < 1

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class ByteQueue:
    """One HTTP read's bounded prefix; never a whole-file or cross-read cache."""
    def __init__(self, limit=PROGRESSIVE_QUEUE_BYTES, microbatch=False):
        if type(limit) is not int or not FETCH_CHUNK_BYTES <= limit <= PROGRESSIVE_QUEUE_BYTES:
            raise ValueError('SHARE_QUEUE_BUDGET')
        if type(microbatch) is not bool:
            raise ValueError('SHARE_DIAGNOSTIC_INVALID')
        self.microbatch = microbatch
        self.limit, self.peak, self.bytes = limit, 0, 0
        self.chunks, self.condition = deque(), Condition()
        self.stopped, self.finished, self.error = False, False, None
        self.puts = self.gets = 0  # Successful queued fragments / returned batches, not delivered bytes.

    def put(self, chunk):
        with self.condition:
            if self.stopped or self.bytes + len(chunk) > self.limit:
                return False  # Caller closes upstream BEFORE waiting for room.
            self.chunks.append(chunk)
            self.puts += 1
            self.bytes += len(chunk)
            self.peak = max(self.peak, self.bytes)
            self.condition.notify_all()
            return True

    def room(self, cancelled):
        with self.condition:
            # Reopen only after half the buffer drains; avoid one TLS/Range per
            # tiny socket write when the player is paused or throttled.
            while self.bytes > self.limit // 2 and not self.stopped:
                if cancelled():
                    return False
                self.condition.wait(.05)
            return not self.stopped and not cancelled()

    def get(self, cancelled):
        with self.condition:
            while not self.chunks and not self.finished and not self.stopped:
                if cancelled():
                    return None
                self.condition.wait(.05)
            if self.stopped or cancelled():
                return None
            if self.microbatch:
                # Only an explicit diagnostic may collect later fragments.
                # Start once from the first available fragment of this batch;
                # arrivals/spurious wakes never move the deadline. First output,
                # full batches and producer EOF/error never wait for collection.
                until = time.monotonic() + DIAGNOSTIC_BATCH_SECONDS
                while (self.gets and self.chunks and self.chunks[0]
                       and self.bytes < DELIVERY_CHUNK_BYTES and not self.finished):
                    remaining = until - time.monotonic()
                    if remaining <= 0:
                        break
                    self.condition.wait(remaining)
                    if self.stopped or cancelled():
                        return None
                if self.error is not None:
                    raise self.error
            if self.chunks:
                # Coalesce ONLY the prefix already queued under this lock.
                # Ordinary/control mode never waits to fill a batch; the
                # diagnostic's bounded wait above is over. A chunk retains its exact
                # suffix; accepted and delivered accounting stay separate.
                parts, length = [], 0
                while self.chunks and length < DELIVERY_CHUNK_BYTES:
                    chunk = self.chunks[0]
                    if not chunk:
                        if not parts:
                            parts.append(self.chunks.popleft())
                        break  # Preserve an empty injected prefix without an unbounded zero-byte scan.
                    take = min(len(chunk), DELIVERY_CHUNK_BYTES - length)
                    if take == len(chunk):
                        parts.append(self.chunks.popleft())
                    else:
                        parts.append(chunk[:take])
                        self.chunks[0] = chunk[take:]
                    length += take
                chunk = parts[0] if len(parts) == 1 else b''.join(parts)
                self.bytes -= length
                self.gets += 1
                self.condition.notify_all()
                return chunk
            if self.error is not None:
                raise self.error
            return None

    def finish(self, error=None):
        with self.condition:
            self.finished, self.error = True, error
            self.condition.notify_all()

    def stop(self):
        with self.condition:
            self.stopped = True
            self.chunks.clear()
            self.bytes = 0
            self.condition.notify_all()


def byte_range(value, size):
    if value is None:
        return 0, size - 1, 200
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()):
        raise ValueError('INVALID_RANGE')
    first, last = match.groups()
    if not first:
        length = int(last)
        if length <= 0:
            raise ValueError('INVALID_RANGE')
        return max(0, size - length), size - 1, 206
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError('INVALID_RANGE')
    return start, end, 206


def checked(body):
    keys = {'request_id', 'locator', 'guid', 'title', 'size', 'media'}
    if not isinstance(body, dict) or set(body) != keys:
        raise ValueError('SHARE_FIELDS')
    if (not isinstance(body['request_id'], str) or not re.fullmatch('[0-9a-f]{32}', body['request_id'])
            or not isinstance(body['locator'], str) or not re.fullmatch(r'(?:am6bqqdocs://(?:[A-Z]{1,2}[1-9]\d*|supp-[0-9a-f]{24})/\d{1,32}|am6bjuku://[0-9a-f]{64})', body['locator'])
            or not isinstance(body['guid'], str) or len(body['guid']) > 90
            or not isinstance(body['title'], str) or not 1 <= len(body['title']) <= 1024
            or re.search(r'[\x00-\x1f\x7f/\\]', body['title'])
            or type(body['size']) is not int or not 1 <= body['size'] <= 512 * 1024**3
            or not isinstance(body['media'], str) or not re.fullmatch(r'(?:movies|movie|tv|anime|episode):[1-9]\d{0,11}:\d{1,4}:\d{1,4}', body['media'])):
        raise ValueError('SHARE_IDENTITY')
    return dict(body)


def checked_diagnostic(value):
    """Explicit maintainer registration only; never a saved/user preference."""
    if (type(value) is not dict or set(value) != {'mode', 'seconds'}
            or value['mode'] not in ('open_range', 'open_range_microbatch', 'open_range_bound_guard',
                                    'block_startup_1m') or type(value['seconds']) is not int
            or not 1 <= value['seconds'] <= 60):
        raise ValueError('SHARE_DIAGNOSTIC_INVALID')
    return dict(value)


class RetryWindow:
    """64 MiB accepted-byte budgets, independent of connections and gate yields."""
    def __init__(self, start):
        self.start, self.index = start, 0
        self.failures = self.contention = 0

    def advance(self, offset):
        index = (offset - self.start) // MAX_SEGMENT_BYTES
        if index > self.index:
            self.index = index
            self.failures = self.contention = 0
            return True
        return False


class DiagnosticMetrics:
    """Per-thread diagnostic counters, emitted only at the existing final events.

    CPU is each worker's own thread time, including instrumentation overhead.
    Cancel wall time overlaps queue/read/socket wall time; those totals must not
    be added. Buckets count returned prefixes, not HTTP requests or delivered bytes.
    """
    BUCKETS = ('zero', 'eof', 'le4k', 'le32k', 'le128k', 'gt128k')

    def __init__(self):
        self.thread = local()
        self.cpu_clock = getattr(time, 'thread_time_ns', None)
        self.rows = {role: dict(cancel_calls=0, cancel_us=0, cpu_start=None, cpu_us=None,
                               complete=False, **{kind + '_' + bucket: 0 for bucket in self.BUCKETS})
                     for role, kind in (('producer', 'read'), ('consumer', 'get'))}

    def cpu(self):
        try:
            return self.cpu_clock() if callable(self.cpu_clock) else None
        except (OSError, RuntimeError):
            return None  # An optional CPU clock cannot change transport policy.

    def begin(self, role):
        self.thread.row = self.rows[role]
        self.thread.row['cpu_start'] = self.cpu()

    def end(self):
        row, now = self.thread.row, self.cpu()
        if now is not None and row['cpu_start'] is not None:
            row['cpu_us'] = max(0, (now - row['cpu_start']) // 1000)
        row['complete'] = True

    def cancel(self, check):
        row, began = self.thread.row, time.monotonic()
        try:
            return check()
        finally:
            row['cancel_calls'] += 1
            row['cancel_us'] += max(0, int((time.monotonic() - began) * 1000000))

    def size(self, kind, value):
        if not isinstance(value, (bytes, bytearray, memoryview)):
            bucket = 'eof'
        else:
            length = len(value)
            bucket = ('zero' if length == 0 else 'le4k' if length <= 4096 else
                      'le32k' if length <= 32768 else 'le128k' if length <= 131072 else 'gt128k')
        self.thread.row[kind + '_' + bucket] += 1

    def snapshot(self):
        result = dict(producer_complete=self.rows['producer']['complete'],
                      thread_cpu_supported=all(row['cpu_start'] is not None for row in self.rows.values()))
        for role, row in self.rows.items():
            result.update({key: value for key, value in row.items() if key.startswith(('read_', 'get_'))})
            for key in ('cancel_calls', 'cancel_us', 'cpu_us'):
                if row[key] is not None:
                    result[role + '_' + key] = row[key]
        return result


@dataclass(frozen=True)
class ResolvedResource:
    """Optional resolver-owned expiry; never guessed from signed URL parameters."""
    url: str
    expires_at: float = None


def upstream_chunks(response):
    # urllib3's public read1 returns available bytes without waiting to fill
    # 32 KiB. iter_content/read can be kept inside a single call indefinitely
    # by a peer trickling bytes below the per-socket timeout. Our pinned 2.2.3
    # supplies read1. The fallback supports older injected transports.
    read = getattr(getattr(response, 'raw', None), 'read1', None)
    if callable(read):
        while True:
            chunk = read(FETCH_CHUNK_BYTES, decode_content=False)
            if not chunk:
                return
            yield chunk
    else:
        yield from response.iter_content(FETCH_CHUNK_BYTES)


class Binding:
    def __init__(self, body, resolve, validate_url, account=None, scope=None, diagnostic=None):
        self.body, self.resolve, self.validate_url = body, resolve, validate_url
        self.account, self.scope = account, dict(scope) if scope else None
        self.diagnostic = checked_diagnostic(diagnostic) if diagnostic is not None else None
        self.diagnostic_deadline = time.monotonic() + diagnostic['seconds'] if diagnostic is not None else None
        self._account_current_guard = None
        if self.diagnostic is not None and self.diagnostic['mode'] == 'open_range_bound_guard':
            factory = getattr(account, 'current_guard', None)
            if not callable(factory):
                raise ValueError('SHARE_DIAGNOSTIC_INVALID')
            self._account_current_guard = factory(self.scope)
        self.revoked = Event()
        self.connections, self.connection_lock = set(), Lock()
        self.token = uuid4().hex
        self.request_hash = hashlib.sha256(body['request_id'].encode('ascii')).hexdigest()[:16]
        self.transport_hash = ''
        canonical = json.dumps([body[key] for key in BINDING_IDENTITY],
                               ensure_ascii=True, separators=(',', ':')).encode('ascii')
        self.physical_file_hash = hashlib.sha256(canonical).hexdigest()
        self.lock = Lock()
        # Read-only diagnostics must not wait for the grant's network lock.
        self.outcome_lock, self.outcome = Lock(), None
        self.io_lock = ReadGate()
        self.address = None
        self.expires_at = None
        self.renewals = []
        self.touched = time.monotonic()
        self.active = 0

    def cancelled(self):
        return (self.diagnostic_expired() or self.revoked.is_set()
                or (self.account is not None and not (
                    self._account_current_guard() if getattr(self, '_account_current_guard', None) is not None
                    else self.account.is_current(self.scope))))

    def diagnostic_expired(self):
        return self.diagnostic_deadline is not None and time.monotonic() >= self.diagnostic_deadline

    def revoke(self):
        self.revoked.set()
        self.address = None
        with self.connection_lock:
            connections = tuple(self.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def grant(self, rejected=None):
        with self.lock:
            if self.cancelled():
                raise OSError('SHARE_STOPPED')
            if (self.address is not None and (rejected is None or rejected != self.address)
                    and (self.expires_at is None or time.time() + 15 < self.expires_at)):
                return self.address
            now = time.monotonic()
            from bobbi_core.share_failure import PERMANENT, failure_error, failure_value, resolution_state
            previous = self.grant_outcome()
            if (previous and previous['state'] == 'failed'
                    and previous['failure']['code'] in PERMANENT and now < previous['retry_after']):
                raise failure_error(previous['failure'])
            self.renewals = [t for t in self.renewals if now - t < 300]
            if len(self.renewals) >= 4:
                raise ValueError('SHARE_REFRESH_BUDGET')
            self.renewals.append(now)
            attempt = dict(started_at=time.time(), started=now, state='pending')
            observed = time.perf_counter_ns()
            self._publish_outcome(attempt)
            try:
                address = (self.resolve(self.body, self.scope) if self.account is not None
                           else self.resolve(self.body))
            except Exception as error:
                try:
                    failure = failure_value(error)
                    if failure is not None and failure['code'] in PERMANENT:
                        state = resolution_state(self.body, self.scope, failure['code'], observed)
                        if state:
                            error.share_state = state
                            failure['share_state'] = state
                except ImportError:
                    failure = None  # The base transport has no catalog dependency.
                if failure is not None and not self.cancelled():
                    self._publish_outcome(dict(attempt, state='failed', failure=failure,
                        retry_after=time.monotonic() + NEGATIVE_GRANT_SECONDS))
                raise
            expiry = None
            if isinstance(address, ResolvedResource):
                expiry, address = address.expires_at, address.url
                if expiry is not None and (type(expiry) not in (int, float)
                        or not math.isfinite(expiry) or expiry <= time.time()):
                    raise ValueError('SHARE_TRANSPORT_INVALID')
            if not isinstance(address, str):
                raise ValueError('SHARE_TRANSPORT_INVALID')
            if self.cancelled():
                raise OSError('SHARE_STOPPED')
            base, separator, options = address.partition('|')
            headers = parse_qs(options, strict_parsing=True)
            ua = headers.get('User-Agent', [])
            if (not separator or set(headers) != {'User-Agent'} or len(ua) != 1
                    or not ua[0] or len(ua[0]) > 1024 or re.search(r'[\x00-\x1f\x7f]', ua[0])
                    or not self.validate_url(base)):
                raise ValueError('SHARE_TRANSPORT_INVALID')
            if self.account is not None:
                self.account.run_if_current(self.scope, lambda: setattr(self, 'address', address))
            else:
                self.address = address
            self.expires_at = expiry
            self._publish_outcome(dict(attempt, state='ready'))
            return address

    def _publish_outcome(self, value):
        from bobbi_core.share_failure import PERMANENT
        def publish():
            with self.outcome_lock:
                if not self.revoked.is_set() and not self.diagnostic_expired():
                    if value['state'] == 'failed' and value['failure']['code'] in PERMANENT:
                        # A rejected/expired earlier address must not bypass
                        # this binding's negative window on the next GET.
                        self.address = self.expires_at = None
                    self.outcome = value
        if self.account is not None:
            self.account.run_if_current(self.scope, publish)
        else:
            publish()

    def grant_outcome(self):
        with self.outcome_lock:
            return self.outcome  # Replaced as a whole, never mutated after publication.


class LimitedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False

    def process_request(self, request, client_address):
        if not self.owner.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.owner.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.owner.slots.release()

    def handle_error(self, request, client_address):
        self.owner.report('REQUEST_FAILED')  # Never print signed URLs or tokens.


class ShareStream:
    def __init__(self, validate, resolve, validate_url, report=lambda phase: None,
                 session_factory=None, segment_bytes=MAX_SEGMENT_BYTES, observer=observation_json,
                 account=None, progressive=False, queue_bytes=PROGRESSIVE_QUEUE_BYTES):
        if type(segment_bytes) is not int or not 0 < segment_bytes <= MAX_SEGMENT_BYTES:
            raise ValueError('SHARE_SEGMENT_BUDGET')
        self.validate, self.resolve, self.validate_url = validate, resolve, validate_url
        self._report, self.observer = report, observer
        self.observation_run = uuid4().hex[:16]
        self.http_sequence = self.gate_sequence = 0
        self.session_factory = session_factory
        self.segment_bytes = segment_bytes
        if type(progressive) is not bool:
            raise ValueError('SHARE_MODE_INVALID')
        ByteQueue(queue_bytes)  # Validate before starting any listener.
        self.progressive, self.queue_bytes = progressive, queue_bytes
        self.account = account
        self.records, self.lock = {}, Lock()
        self.stopping, self.slots = Event(), BoundedSemaphore(6)
        self.producer_slots = BoundedSemaphore(6)
        self.producers = set()
        self.server = LimitedHTTPServer(('127.0.0.1', 0), Handler)
        self.server.owner = self
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1}, daemon=True,
                             name='share-stream-listener')
        self.thread.start()
        self.unsubscribe = account.subscribe(self.revoke) if account is not None else lambda: None

    def report(self, phase):
        try:
            self._report(phase)
        except Exception:
            pass  # A logging failure must not change the media byte stream.

    def observation(self, entry):
        with self.lock:
            self.http_sequence += 1
            return dict(run=self.observation_run, http=self.http_sequence, transport=entry.transport_hash,
                        request=entry.request_hash, file=entry.physical_file_hash,
                        gate=entry.io_lock.diagnostic_id)

    def register(self, body, account=None):
        body = checked(body)
        if self.account is not None:
            return self.account.run_if_current(account, lambda: self._register(body, account))
        return self._register(body, None)

    def failure_record(self, scope, selected, transport_hash):
        """Exact current Binding only; no resolution, registration, or IO gate."""
        from bobbi_core.share_failure import TUPLE_FIELDS
        with self.lock:
            entries = tuple(self.records.values())
        matches = [entry for entry in entries if entry.scope == scope
            and entry.transport_hash == transport_hash
            and all(entry.body[key] == selected[key] for key in TUPLE_FIELDS)]
        if len(matches) != 1 or matches[0].cancelled():
            return None
        entry = matches[0]
        outcome = entry.grant_outcome()
        if not outcome or outcome['state'] != 'failed':
            return None
        return entry, outcome

    def denied_proofs(self, scope, submitted):
        """Known exact failures only. Missing/evicted bindings are not failures."""
        from bobbi_core.share_failure import PERMANENT, tuple_hash
        account_hash = hashlib.sha256(json.dumps([scope['account_id'], scope['epoch']],
            ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with self.lock:
            entries = tuple(self.records.values())
        latest = {}
        for entry in entries:
            if entry.scope != scope or entry.cancelled():
                continue
            key, outcome = tuple_hash(entry.body), entry.grant_outcome()
            if key not in submitted or not outcome:
                continue
            if key not in latest or outcome['started'] > latest[key][0][1]['started']:
                latest[key] = [(entry, outcome)]
            elif outcome['started'] == latest[key][0][1]['started']:
                latest[key].append((entry, outcome))
        denied = []
        for key, matches in latest.items():
            if len(matches) != 1:
                continue  # Clock ties cannot establish which attempt won.
            entry, outcome = matches[0]
            if (outcome['state'] == 'failed' and outcome['failure']['code'] in PERMANENT
                    and outcome['failure'].get('checked_proof') ==
                        dict(checked_at=submitted[key], checked_account=account_hash)
                    and entry.grant_outcome() is outcome and not entry.cancelled()):
                denied.append(key)
        return sorted(denied)

    def register_diagnostic(self, body, account, diagnostic):
        body, diagnostic = checked(body), checked_diagnostic(diagnostic)
        if self.account is not None:
            return self.account.run_if_current(account, lambda: self._register(body, account, diagnostic))
        return self._register(body, None, diagnostic)

    def _register(self, body, account, diagnostic=None):
        with self.lock:
            if self.stopping.is_set():
                raise ValueError('SHARE_STOPPED')
            now = time.monotonic()
            for key, entry in list(self.records.items()):
                if not entry.active and now - entry.touched > 6 * 3600:
                    del self.records[key]
            entry = self.records.get(body['request_id'])
            if entry is not None:
                if (entry.body != body or entry.scope != account or entry.diagnostic != diagnostic
                        or entry.cancelled()):
                    raise ValueError('SHARE_REQUEST_RETARGETED')
            else:
                if len(self.records) >= 32:
                    # Retain active and newly reserved streams. Repeated movie
                    # browsing must not exhaust every slot for six hours.
                    idle = [(e.touched, key) for key, e in self.records.items()
                            if not e.active and now - e.touched > 60]
                    if not idle:
                        raise ValueError('SHARE_BINDINGS_FULL')
                    del self.records[min(idle)[1]]
                self.validate(body)  # Exact local catalogue binding, no network IO here.
                entry = Binding(body, self.resolve, self.validate_url, self.account, account, diagnostic)
                # A new playback reservation of the same physical file shares
                # the upstream gate, even while an old reservation winds down.
                identity = BINDING_IDENTITY
                peer = next((e for e in self.records.values()
                             if e.scope == account and all(e.body[k] == body[k] for k in identity)), None)
                if peer is not None:
                    entry.io_lock = peer.io_lock
                else:
                    self.gate_sequence += 1
                    entry.io_lock.diagnostic_id = self.gate_sequence
                self.records[body['request_id']] = entry
            entry.touched = now
            extension = body['title'].rsplit('.', 1)[-1].lower()
            if extension not in ('mkv', 'mp4', 'm4v', 'avi', 'ts', 'm2ts', 'webm'):
                extension = 'bin'
            url = 'http://127.0.0.1:{}/stream/{}/video.{}'.format(self.server.server_port, entry.token, extension)
            # The reservation request is not necessarily the playback request.
            # Join to native URL SHA explicitly; never equate those two IDs.
            entry.transport_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
            return dict(state='ready', request_id=body['request_id'], guid=body['guid'], media=body['media'],
                        bytes=body['size'], url=url)

    def revoke(self, previous, current=None):
        with self.lock:
            entries = [entry for entry in self.records.values() if entry.scope == previous]
            self.records = {key: entry for key, entry in self.records.items() if entry.scope != previous}
        for entry in entries:
            entry.revoke()

    def acquire(self, path, connection=None):
        match = re.fullmatch(r'/stream/([0-9a-f]{32})/video\.[a-z0-9]+', path)
        if match is None or self.stopping.is_set():
            return None
        with self.lock:
            entry = next((e for e in self.records.values() if e.token == match[1]), None)
            if entry is not None:
                # No manager lock while holding records: register/revoke acquire
                # account -> records. The revoked flag is the local fast gate.
                if entry.revoked.is_set() or entry.diagnostic_expired():
                    return None
                entry.active += 1
                entry.touched = time.monotonic()
                if connection is not None:
                    with entry.connection_lock:
                        entry.connections.add(connection)
            return entry

    def release(self, entry, connection=None):
        with self.lock:
            entry.active -= 1
            entry.touched = time.monotonic()
            if connection is not None:
                with entry.connection_lock:
                    entry.connections.discard(connection)

    def session(self):
        if self.session_factory:
            return self.session_factory()
        import requests
        session = requests.Session()
        session.trust_env = False
        return session

    def close(self):
        if getattr(self, '_closed', False):
            return
        with self.lock:
            self.stopping.set()  # Same admission lock as producer registration.
        self.unsubscribe()
        with self.lock:
            entries = tuple(self.records.values())
            self.records.clear()
        for entry in entries:
            entry.revoke()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        # Handler joins are bounded; they are not the service ownership barrier.
        # A slow response header may outlive its handler. Never release the host
        # lease until every admitted producer has finished its upstream IO.
        while True:
            with self.lock:
                workers = tuple(self.producers)
            if not workers:
                break
            for worker in workers:
                worker.join()
        self._closed = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(15)
        self.disconnected = False

    def cancelled(self):
        entry = getattr(self, 'entry', None)
        if entry is not None and entry.diagnostic_expired():
            self.cancel_reason = 'diagnostic_expired'
            return True
        if entry is not None and entry.cancelled():
            self.cancel_reason = 'account_revoked'
            return True
        if self.server.owner.stopping.is_set():
            self.cancel_reason = 'service_stop'
            return True
        if getattr(self, 'disconnected', False):
            return True
        try:
            if self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                self.disconnected = True
                self.cancel_reason = 'socket_error'
            elif select.select([self.connection], [], [], 0)[0]:
                # A FIN alone can be a valid HTTP half-close: the peer may
                # still receive this response. Never call it Stop or Pause.
                self.connection.recv(1, socket.MSG_PEEK)
        except (OSError, ValueError):
            self.disconnected = True
            self.cancel_reason = 'socket_probe_error'
        return self.disconnected

    def observe(self, event, terminal=False, **detail):
        """Sparse numbers/enums only; never paths, tokens, headers or exception text."""
        try:
            if not hasattr(self, 'observation_state'):
                return
            # Reserve the last record for end, including when retries exhaust
            # the ordinary event budget. Total per HTTP read never exceeds 48.
            if self.observation_count >= OBSERVATION_LIMIT - (0 if terminal else 1):
                self.observation_suppressed += 1
                return
            self.observation_count += 1
            row = observation_fields(dict(self.observation_state, phase=event,
                       monotonic_us=int(time.monotonic() * 1000000),
                       stage=self.observation_stage,
                       offset=self.observation_offset,
                       delivered=self.observation_delivered,
                       cancel=getattr(self, 'cancel_reason', 'none'), **detail))
            if self.observation_holds_gate:
                self.observation_pending.append(row)
            else:
                self.server.owner.observer(row)
        except Exception:
            pass  # Observation is not an input to cancellation or retry policy.

    def flush_observations(self):
        pending, self.observation_pending = self.observation_pending, []
        for row in pending:
            try:
                self.server.owner.observer(row)
            except Exception:
                pass

    def do_HEAD(self):
        self.serve(head=True)

    def do_GET(self):
        self.serve(head=False)

    def response_headers(self, status, start, end, size):
        self.send_response(status)
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        if status == 206:
            self.send_header('Content-Range', 'bytes {}-{}/{}'.format(start, end, size))
        self.end_headers()
        self.close_connection = True

    def serve(self, head=False):
        owner = self.server.owner
        entry = owner.acquire(self.path, self.connection)
        if entry is None:
            self.send_error(404)
            return
        self.entry = entry
        self.observation_state = owner.observation(entry)
        diagnostic = getattr(entry, 'diagnostic', None)
        if diagnostic is not None:
            self.observation_state.update(diagnostic_mode=diagnostic['mode'],
                batch_budget_us=2000 if diagnostic['mode'] == 'open_range_microbatch' else 0)
        self.observation_count = self.observation_suppressed = 0
        self.observation_offset = self.observation_delivered = 0
        self.observation_stage = 'range'
        self.observation_holds_gate = False
        self.observation_pending = []
        observation_began = time.monotonic()
        observation_wait_ms = observation_fetch_ms = observation_write_ms = 0
        outcome, reason = 'incomplete', 'none'
        started = False
        try:
            if self.cancelled():
                raise OSError('SHARE_STOPPED')
            size = entry.body['size']
            try:
                start, end, status = byte_range(self.headers.get('Range'), size)
            except ValueError:
                outcome, reason = 'rejected', 'invalid_range'
                self.send_error(416)
                return
            self.observation_state.update(start=start, end=end, method='HEAD' if head else 'GET', role='unknown')
            self.observation_offset = start
            self.observe('begin')
            if head:
                self.response_headers(status, start, end, size)
                outcome = 'head_complete'
                return
            small_block = diagnostic is not None and diagnostic['mode'] == 'block_startup_1m'
            if not small_block and (getattr(owner, 'progressive', False) or diagnostic is not None):
                complete = self.serve_progressive(entry, start, end, status)
                started = getattr(self, 'progressive_started', False)
                outcome = 'complete' if complete else 'cancelled'
                reason = 'range_complete' if complete else 'delivery_incomplete'
                if not complete:
                    # No response_headers() ran when cancellation won before
                    # the first prefix. Do not wait for another HTTP request
                    # on this unanswered connection after the producer drains.
                    self.close_connection = True
                return
            offset = start
            # This explicit, short-lived diagnostic changes only the block
            # startup floor. It never selects progressive/open Range, changes
            # the owner's default, or shares a warm-up across HTTP reads.
            startup_bytes = DIAGNOSTIC_STARTUP_SEGMENT_BYTES if small_block else STARTUP_SEGMENT_BYTES
            window = time.monotonic()
            fetched = wait_ms = fetch_ms = write_ms = recovered = 0
            with owner.session() as session:
                while offset <= end and not self.cancelled():
                    # Grow only with bytes already delivered on this HTTP read.
                    # Jumping from an 8 MiB prefix straight to a store-and-forward
                    # 64 MiB fetch can drain a cold player/seek buffer even when
                    # sustained CDN throughput exceeds the media bitrate. Reach
                    # the unchanged cap after warm-up; no prefetch or new worker.
                    length = min(owner.segment_bytes, max(startup_bytes, offset - start))
                    upper = min(end, offset + length - 1)
                    self.observation_offset = offset
                    self.observation_stage = 'gate'
                    # Some share CDNs reject a second concurrent read with 403,
                    # including Kodi's separate active-area scanner. Fully read
                    # one bounded block and close its upstream connection BEFORE
                    # delivering it. A paused client cannot hold this file's gate.
                    waiting = time.monotonic()
                    if not entry.io_lock.acquire(self.cancelled, initial=not started):
                        observation_wait_ms += int((time.monotonic() - waiting) * 1000)
                        outcome, reason = 'cancelled', 'gate_cancelled'
                        return
                    self.observation_holds_gate = True
                    # Cover growth through the first maximum-size block, not
                    # the whole movie. This also applies to a new HTTP seek.
                    observe_block = offset - start <= MAX_SEGMENT_BYTES
                    block_bytes, fetch_complete = 0, False
                    try:
                        reading = time.monotonic()
                        waited = int((reading - waiting) * 1000)
                        wait_ms += waited
                        observation_wait_ms += waited
                        self.observation_stage = 'fetch'
                        # The retry bound applies to THIS incomplete block, not
                        # the lifetime of a two-hour movie. A fully checked and
                        # delivered block is successful recovery; failures from
                        # it must not poison an unrelated future range.
                        block, failures = self.read_block(session, entry, offset, upper, 0)
                        block_bytes, fetch_complete = len(block), True
                        recovered += failures
                    finally:
                        block_fetch_ms = int((time.monotonic() - reading) * 1000)
                        fetch_ms += block_fetch_ms
                        observation_fetch_ms += block_fetch_ms
                        entry.io_lock.release()
                        self.observation_holds_gate = False
                        self.flush_observations()
                        if observe_block:
                            self.observe('fetch_end', len=block_bytes, requested=upper-offset+1,
                                         fetch_ms=block_fetch_ms, write_ms=0,
                                         complete=fetch_complete, block_end=upper)
                        if waited >= OBSERVATION_WAIT_MS:
                            self.observe('gate_wait', block_end=upper, wait_ms=waited,
                                         wait_begin_us=int(waiting * 1000000),
                                         wait_end_us=int(reading * 1000000), initial=not started)
                    if self.cancelled():
                        outcome, reason = 'cancelled', 'after_fetch'
                        return
                    if not started:
                        self.observation_stage = 'headers'
                        self.response_headers(status, start, end, size)
                        started = True
                        self.observe('response', status=status, first_block_bytes=len(block))
                    self.observation_stage = 'write'
                    writing = time.monotonic()
                    delivered_before = self.observation_delivered
                    write_complete = False
                    try:
                        write_complete = self.write_block(block)
                    finally:
                        block_write_ms = int((time.monotonic() - writing) * 1000)
                        observation_write_ms += block_write_ms
                        if observe_block:
                            self.observe('write_end', len=self.observation_delivered-delivered_before,
                                         requested=block_bytes, fetch_ms=block_fetch_ms,
                                         write_ms=block_write_ms, complete=write_complete)
                    if not write_complete:
                        outcome, reason = 'cancelled', 'delivery_incomplete'
                        owner.report('CLIENT_DISCONNECTED')
                        return  # Known Stop/seek/disconnect never fetches another block.
                    write_ms += block_write_ms
                    fetched += len(block)
                    offset += len(block)
                    self.observation_offset = offset
                    # Do not retain the prior 64 MiB while allocating the next
                    # segment. At most one bounded block per HTTP worker lives.
                    del block
                    now = time.monotonic()
                    if now - window >= 20:
                        # Numbers only: no request tokens, filenames, URLs or
                        # provider exceptions. Includes downstream backpressure
                        # separately from upstream and lock contention.
                        owner.report('READ_WINDOW bytes={} wall_ms={} fetch_ms={} wait_ms={} write_ms={} recovered={}'.format(
                            fetched, int((now - window) * 1000), fetch_ms, wait_ms, write_ms, recovered))
                        window = now
                        fetched = wait_ms = fetch_ms = write_ms = recovered = 0
                outcome = 'complete' if offset > end else 'cancelled'
                reason = 'range_complete' if offset > end else 'before_fetch'
        except Exception as exc:
            reason, fault = observation_error(exc)
            self.observe('response', outcome='failed', reason=reason, **fault)
            outcome = 'cancelled' if reason == 'SHARE_STOPPED' else 'failed'
            owner.report('STREAM_UNAVAILABLE')
            if not started and not getattr(self, 'progressive_started', False):
                self.send_error(503)
            # After partial output close the socket; do not append an error
            # body or claim the remaining Content-Length reached a real EOF.
            self.close_connection = True
        finally:
            owner.release(entry, self.connection)
            started = started or getattr(self, 'progressive_started', False)
            self.observe('end', terminal=True, outcome=outcome, reason=reason, started=started,
                         wait_ms=observation_wait_ms, fetch_ms=observation_fetch_ms,
                         write_ms=observation_write_ms,
                         wall_ms=int((time.monotonic() - observation_began) * 1000),
                         suppressed=self.observation_suppressed, **getattr(self, 'progressive_counts', {}))

    def serve_progressive(self, entry, start, end, status):
        """Read and deliver concurrently, retaining the SAME grant/gate/retry path.

        Accepted, queued and delivered offsets are separate. A discarded chunk
        on backpressure is fetched again; an accepted chunk never is. The gate
        belongs only to the producer, and only while an upstream response lives.
        New HTTP ranges do not revoke earlier reads or masquerade as player seek.
        """
        owner = self.server.owner
        if not owner.producer_slots.acquire(blocking=False):
            raise OSError('SHARE_READ_UNAVAILABLE')
        pipe = ByteQueue(owner.queue_bytes, microbatch=entry.diagnostic is not None
                         and entry.diagnostic['mode'] == 'open_range_microbatch')
        self.progressive_started = False
        self.progressive_send_calls = 0
        diagnostic = entry.diagnostic is not None
        self.diagnostic_timings = ({key: 0 for key in ('grant_us','connect_us','read_wait_us',
            'queue_room_us','queue_put_us','queue_get_us','socket_send_us')} if diagnostic else None)
        self.diagnostic_metrics = DiagnosticMetrics() if diagnostic else None
        if diagnostic:
            self.diagnostic_metrics.begin('consumer')
        retry_window = RetryWindow(start) if diagnostic else None
        original_cancelled = self.cancelled
        queued_cancelled = lambda: pipe.stopped or original_cancelled()
        self.cancelled = ((lambda: self.diagnostic_metrics.cancel(queued_cancelled))
                          if diagnostic else queued_cancelled)

        def produce():
            if diagnostic:
                self.diagnostic_metrics.begin('producer')
            received = start
            try:
                with owner.session() as session:
                    while received <= end and not self.cancelled():
                        if not self.diagnostic_call('queue_room_us', pipe.room, self.cancelled):
                            break
                        waiting = time.monotonic()
                        if not entry.io_lock.acquire(self.cancelled, initial=received == start):
                            break
                        self.observation_holds_gate = True
                        self.observation_offset = received
                        reading = time.monotonic()
                        # Prefix delivery does not wait for this whole range.
                        # Use the existing cap from the first request, avoiding
                        # the block path's forced early reconnects. Queue/gate
                        # pressure still closes and resumes the exact suffix.
                        upper = end if diagnostic else min(end, received + owner.segment_bytes - 1)
                        count = 0
                        try:
                            count, _ = self.read_block(session, entry, received, upper, 0,
                                consume=lambda chunk: self.diagnostic_call('queue_put_us', pipe.put, chunk),
                                retry_window=retry_window)
                        finally:
                            entry.io_lock.release()
                            self.observation_holds_gate = False
                            self.flush_observations()
                            if received - start <= MAX_SEGMENT_BYTES:
                                self.observe('fetch_end', len=count, requested=upper-received+1,
                                    fetch_ms=int((time.monotonic()-reading)*1000), write_ms=0,
                                    wait_ms=int((reading-waiting)*1000), complete=count == upper-received+1,
                                    queue_peak=pipe.peak, queue_limit=pipe.limit, block_end=upper)
                        received += count
                if received <= end:
                    raise OSError('SHARE_STOPPED')
                pipe.finish()
            except Exception as error:
                pipe.finish(error)
            finally:
                if diagnostic:
                    self.diagnostic_metrics.end()
                owner.producer_slots.release()
                with owner.lock:
                    owner.producers.discard(worker)

        worker = Thread(target=produce, name='share-stream-prefix', daemon=True)
        try:
            with owner.lock:
                if owner.stopping.is_set():
                    raise OSError('SHARE_STOPPED')
                owner.producers.add(worker)
                worker.start()
        except BaseException:
            with owner.lock:
                owner.producers.discard(worker)
            owner.producer_slots.release()
            raise
        try:
            while not self.cancelled():
                block = self.diagnostic_call('queue_get_us', pipe.get, self.cancelled)
                if block is None:
                    break
                if not self.progressive_started:
                    self.response_headers(status, start, end, entry.body['size'])
                    self.progressive_started = True
                    self.observe('response', status=status, first_block_bytes=len(block))
                if not self.write_block(block):
                    return False
            # Even exactly Content-Length bytes are not a successful transfer
            # if the producer subsequently rejected excess bytes/invalid EOF.
            if pipe.error is not None:
                raise pipe.error
            return pipe.finished and self.observation_delivered == end-start+1
        finally:
            pipe.stop()
            # read1 cooperates between available prefixes. A stuck external
            # transport retains its independent producer slot even if joining
            # times out: new requests cannot create unbounded orphan workers.
            worker.join(15)
            self.progressive_counts = dict(queue_puts=pipe.puts, queue_gets=pipe.gets,
                                           send_calls=self.progressive_send_calls)
            if self.diagnostic_timings is not None:
                self.diagnostic_metrics.end()
                self.progressive_counts.update(self.diagnostic_timings, timing_scope='diagnostic_cumulative')
                self.progressive_counts.update(self.diagnostic_metrics.snapshot())
            self.observe('write_end', len=self.observation_delivered, requested=end-start+1,
                         queue_peak=pipe.peak, queue_limit=pipe.limit,
                         complete=self.observation_delivered == end-start+1, **self.progressive_counts)

    def write_block(self, block):
        # sendall's timeout is for the WHOLE block, not a no-progress timeout.
        # A full player cache (or Pause) must not turn a healthy socket into a
        # truncated movie. send() gives an exact acknowledged-byte count, so a
        # polling timeout never replays bytes already accepted by the socket.
        # No upstream connection or same-file IO gate is held here.
        self.connection.settimeout(DELIVERY_POLL_SECONDS)
        view = memoryview(block)
        position = 0
        try:
            while position < len(view) and not self.cancelled():
                try:
                    if hasattr(self, 'progressive_send_calls'):
                        self.progressive_send_calls += 1  # Attempts, including timeout/partial send.
                    sent = self.diagnostic_call('socket_send_us', self.connection.send,
                                                view[position:position + DELIVERY_CHUNK_BYTES])
                except TimeoutError:
                    continue  # Backpressure, not evidence that the player stopped.
                except OSError:
                    return False
                if sent <= 0:
                    return False
                position += sent
                if hasattr(self, 'observation_delivered'):
                    self.observation_delivered += sent
            return position == len(view)
        finally:
            view.release()

    def diagnostic_call(self, key, function, *args, **kwargs):
        timings = getattr(self, 'diagnostic_timings', None)
        if timings is None:
            return function(*args, **kwargs)
        began = time.monotonic()
        try:
            result = function(*args, **kwargs)
            metrics = getattr(self, 'diagnostic_metrics', None)
            if metrics is not None and key in ('read_wait_us', 'queue_get_us'):
                metrics.size('read' if key == 'read_wait_us' else 'get', result)
            return result
        finally:
            timings[key] += max(0, int((time.monotonic() - began) * 1000000))

    def read_block(self, session, entry, start, end, failures, consume=None, retry_window=None):
        owner, data = self.server.owner, bytearray()
        if retry_window is not None and consume is None:
            raise ValueError('SHARE_DIAGNOSTIC_INVALID')  # Never accumulate an extended range in memory.
        accepted = 0
        contention_retries = 0
        while start + accepted <= end and not self.cancelled():
            offset = start + accepted
            if retry_window is not None:
                retry_window.advance(offset)
                failures, contention_retries = retry_window.failures, retry_window.contention
            self.observation_stage = 'grant'
            address = self.diagnostic_call('grant_us', entry.grant)
            base, _, options = address.partition('|')
            ua = parse_qs(options)['User-Agent'][0]
            rejected = False
            yielded = False
            possible_close_race = False
            try:
                self.observation_stage = 'connect'
                range_end = '' if retry_window is not None and end == entry.body['size'] - 1 else str(end)
                with self.diagnostic_call('connect_us', session.get, base, headers={'User-Agent': ua,
                    'Range': 'bytes={}-{}'.format(offset, range_end), 'Accept-Encoding': 'identity',
                    'Connection': 'close'}, stream=True, allow_redirects=False, timeout=(3.05, 10)) as response:
                    self.observation_stage = 'response_check'
                    if response.status_code != 206:
                        self.observe('upstream_status', status=response.status_code,
                                     upstream_start=offset, block_end=end)
                    if response.status_code in (401, 403, 410):
                        rejected = True
                        possible_close_race = response.status_code == 403 and entry.io_lock.recently_yielded()
                    else:
                        expected = 'bytes {}-{}/{}'.format(offset, end, entry.body['size'])
                        if (response.status_code != 206 or response.headers.get('Content-Range') != expected
                                or response.headers.get('Content-Length', str(end-offset+1)) != str(end-offset+1)
                                or response.headers.get('Content-Encoding', 'identity') != 'identity'):
                            raise ValueError('SHARE_RANGE_IDENTITY')
                        self.observation_stage = 'body'
                        chunks = iter(upstream_chunks(response))
                        exhausted = object()
                        while True:
                            chunk = self.diagnostic_call('read_wait_us', next, chunks, exhausted)
                            if chunk is exhausted:
                                break
                            if self.cancelled():
                                raise OSError('SHARE_STOPPED')
                            if not chunk:
                                continue
                            if len(chunk) > end-start+1-accepted:
                                raise ValueError('SHARE_RANGE_OVERFLOW')
                            if consume is not None and len(chunk) == end-start+1-accepted:
                                # Retain the last prefix until the declared body
                                # actually ends; an oversized chunked response
                                # cannot look complete to the downstream player.
                                if self.diagnostic_call('read_wait_us', next, chunks, b''):
                                    raise ValueError('SHARE_RANGE_OVERFLOW')
                            if consume is not None:
                                if not consume(chunk):
                                    yielded = True
                                    break
                            else:
                                data.extend(chunk)
                            accepted += len(chunk)
                            if retry_window is not None and retry_window.advance(start + accepted):
                                failures, contention_retries = retry_window.failures, retry_window.contention
                                self.observe('window', retry_window=retry_window.index, upstream_accepted=start+accepted,
                                    timing_scope='diagnostic_cumulative', **(self.diagnostic_timings or {}))
                            if accepted and accepted < end-start+1 and entry.io_lock.contended():
                                # Keep the sequential 64 MiB request when it is
                                # alone. A queued seek/scanner gets the next
                                # closed-upstream turn after this exact prefix.
                                yielded = True
                                break
                        if not yielded and accepted != end-start+1:
                            raise OSError('SHARE_READ_TRUNCATED')
                if yielded:
                    entry.io_lock.note_yield()
                    owner.report('READ_YIELDED bytes={} remaining={}'.format(accepted, end-start+1-accepted))
                    self.observe('yield', bytes=accepted, remaining=end-start+1-accepted, block_end=end)
                    return (accepted if consume is not None else data), failures
                # Exit response context before resolving/retrying a signature;
                # the rejected socket must not compete with its own replacement.
                if rejected:
                    # close() releases our socket, not the remote server's
                    # connection admission slot instantly. A recent deliberate
                    # yield can therefore produce a transient same-file 403.
                    # Retry only the same identity/address, with a small bound;
                    # do not spend renewable-signature budget on this race.
                    if possible_close_race and contention_retries < 3:
                        delay = .05 * (2 ** contention_retries)
                        contention_retries += 1
                        if retry_window is not None:
                            retry_window.contention = contention_retries
                        if owner.stopping.wait(delay) or self.cancelled():
                            raise OSError('SHARE_STOPPED')
                        owner.report('READ_CONTENTION_RETRY')
                        self.observe('retry', reason='contention', retry=contention_retries,
                                     upstream_start=offset, block_end=end)
                        continue
                    failures += 1
                    if retry_window is not None:
                        retry_window.failures = failures
                    if failures > 3:
                        raise ValueError('SHARE_READ_REJECTED')
                    if owner.stopping.wait(.25):
                        raise OSError('SHARE_STOPPED')
                    self.diagnostic_call('grant_us', entry.grant, rejected=address)
                    owner.report('ADDRESS_RENEWED')
                    self.observe('retry', reason='address_renewed', retry=failures,
                                 upstream_start=offset, block_end=end)
            except ValueError:
                raise  # Wrong file/range never becomes video bytes.
            except Exception:
                if self.cancelled():
                    raise OSError('SHARE_STOPPED') from None
                failures += 1
                if retry_window is not None:
                    retry_window.failures = failures
                if failures > 3 or owner.stopping.wait(.25):
                    raise OSError('SHARE_READ_UNAVAILABLE') from None
                owner.report('READ_RESUMED')
                self.observe('retry', reason='read_resumed', retry=failures,
                             upstream_start=offset, block_end=end)
                # Retain exactly the bytes already read into this bounded block;
                # fetch only its missing suffix, then deliver it once to Kodi.
        if accepted != end-start+1:
            raise OSError('SHARE_STOPPED')
        return (accepted if consume is not None else data), failures

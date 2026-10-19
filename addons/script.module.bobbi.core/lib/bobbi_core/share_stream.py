"""Loopback, bounded Range transport for identity-checked renewable share URLs.

Public port is owned by the long-lived stock Kodi service. The private AM6B
build used a standalone preparation service; transport identity is unchanged.
No cloud writes, full-file cache, alternate edition, cookies to CDN or player calls.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from threading import BoundedSemaphore, Condition, Event, Lock, Thread
from collections import deque
import hashlib
import json
import re
import select
import socket
import time
from urllib.parse import parse_qs
from uuid import uuid4

STARTUP_SEGMENT_BYTES = 8 * 1024**2
MAX_SEGMENT_BYTES = 64 * 1024**2
DELIVERY_CHUNK_BYTES = 128 * 1024
DELIVERY_POLL_SECONDS = 1
FETCH_CHUNK_BYTES = 32 * 1024
BINDING_IDENTITY = ('locator', 'guid', 'title', 'size')
OBSERVATION_LIMIT = 48
OBSERVATION_WAIT_MS = 25
OBSERVATION_REASONS = frozenset((
    'SHARE_STOPPED', 'SHARE_RANGE_IDENTITY', 'SHARE_RANGE_OVERFLOW',
    'SHARE_READ_UNAVAILABLE', 'SHARE_READ_TRUNCATED', 'SHARE_READ_REJECTED',
    'SHARE_REFRESH_BUDGET', 'SHARE_TRANSPORT_INVALID'))


def observation_json(row):
    # This module runs in the standalone preparation service. Its stdout is
    # journalled; keep this separate from the existing report callback contract.
    print(json.dumps(dict(event='share_read', at=time.time(), **row), sort_keys=True), flush=True)


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
            or not isinstance(body['locator'], str) or not re.fullmatch(r'am6bqqdocs://(?:[A-Z]{1,2}[1-9]\d*|supp-[0-9a-f]{24})/\d{1,32}', body['locator'])
            or not isinstance(body['guid'], str) or len(body['guid']) > 90
            or not isinstance(body['title'], str) or not 1 <= len(body['title']) <= 1024
            or re.search(r'[\x00-\x1f\x7f/\\]', body['title'])
            or type(body['size']) is not int or not 1 <= body['size'] <= 512 * 1024**3
            or not isinstance(body['media'], str) or not re.fullmatch(r'(?:movies|movie|tv|anime|episode):[1-9]\d{0,11}:\d{1,4}:\d{1,4}', body['media'])):
        raise ValueError('SHARE_IDENTITY')
    return dict(body)


class Binding:
    def __init__(self, body, resolve, validate_url):
        self.body, self.resolve, self.validate_url = body, resolve, validate_url
        self.token = uuid4().hex
        self.request_hash = hashlib.sha256(body['request_id'].encode('ascii')).hexdigest()[:16]
        self.transport_hash = ''
        canonical = json.dumps([body[key] for key in BINDING_IDENTITY],
                               ensure_ascii=True, separators=(',', ':')).encode('ascii')
        self.physical_file_hash = hashlib.sha256(canonical).hexdigest()
        self.lock = Lock()
        self.io_lock = ReadGate()
        self.address = None
        self.renewals = []
        self.touched = time.monotonic()
        self.active = 0

    def grant(self, rejected=None):
        with self.lock:
            if self.address is not None and (rejected is None or rejected != self.address):
                return self.address
            now = time.monotonic()
            self.renewals = [t for t in self.renewals if now - t < 300]
            if len(self.renewals) >= 4:
                raise ValueError('SHARE_REFRESH_BUDGET')
            self.renewals.append(now)
            address = self.resolve(self.body)
            base, separator, options = address.partition('|')
            headers = parse_qs(options, strict_parsing=True)
            ua = headers.get('User-Agent', [])
            if (not separator or set(headers) != {'User-Agent'} or len(ua) != 1
                    or not ua[0] or len(ua[0]) > 1024 or re.search(r'[\x00-\x1f\x7f]', ua[0])
                    or not self.validate_url(base)):
                raise ValueError('SHARE_TRANSPORT_INVALID')
            self.address = address
            return address


class LimitedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False
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
                 session_factory=None, segment_bytes=MAX_SEGMENT_BYTES, observer=observation_json):
        if type(segment_bytes) is not int or not 0 < segment_bytes <= MAX_SEGMENT_BYTES:
            raise ValueError('SHARE_SEGMENT_BUDGET')
        self.validate, self.resolve, self.validate_url = validate, resolve, validate_url
        self._report, self.observer = report, observer
        self.observation_run = uuid4().hex[:16]
        self.http_sequence = self.gate_sequence = 0
        self.session_factory = session_factory
        self.segment_bytes = segment_bytes
        self.records, self.lock = {}, Lock()
        self.stopping, self.slots = Event(), BoundedSemaphore(6)
        self.server = LimitedHTTPServer(('127.0.0.1', 0), Handler)
        self.server.owner = self
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1}, daemon=True,
                             name='share-stream-listener')
        self.thread.start()

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

    def register(self, body):
        body = checked(body)
        with self.lock:
            now = time.monotonic()
            for key, entry in list(self.records.items()):
                if not entry.active and now - entry.touched > 6 * 3600:
                    del self.records[key]
            entry = self.records.get(body['request_id'])
            if entry is not None:
                if entry.body != body:
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
                entry = Binding(body, self.resolve, self.validate_url)
                # A new playback reservation of the same physical file shares
                # the upstream gate, even while an old reservation winds down.
                identity = BINDING_IDENTITY
                peer = next((e for e in self.records.values()
                             if all(e.body[k] == body[k] for k in identity)), None)
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

    def acquire(self, path):
        match = re.fullmatch(r'/stream/([0-9a-f]{32})/video\.[a-z0-9]+', path)
        if match is None or self.stopping.is_set():
            return None
        with self.lock:
            entry = next((e for e in self.records.values() if e.token == match[1]), None)
            if entry is not None:
                entry.active += 1
                entry.touched = time.monotonic()
            return entry

    def release(self, entry):
        with self.lock:
            entry.active -= 1
            entry.touched = time.monotonic()

    def session(self):
        if self.session_factory:
            return self.session_factory()
        import requests
        session = requests.Session()
        session.trust_env = False
        return session

    def close(self):
        self.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(15)
        self.disconnected = False

    def cancelled(self):
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
            if not terminal and self.observation_count >= OBSERVATION_LIMIT:
                self.observation_suppressed += 1
                return
            self.observation_count += 1
            row = dict(self.observation_state, phase=event,
                       monotonic_us=int(time.monotonic() * 1000000),
                       stage=self.observation_stage,
                       offset=self.observation_offset,
                       delivered=self.observation_delivered,
                       cancel=getattr(self, 'cancel_reason', 'none'), **detail)
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
        entry = owner.acquire(self.path)
        if entry is None:
            self.send_error(404)
            return
        self.observation_state = owner.observation(entry)
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
            offset = start
            window = time.monotonic()
            fetched = wait_ms = fetch_ms = write_ms = recovered = 0
            with owner.session() as session:
                while offset <= end and not self.cancelled():
                    # Grow only with bytes already delivered on this HTTP read.
                    # Jumping from an 8 MiB prefix straight to a store-and-forward
                    # 64 MiB fetch can drain a cold player/seek buffer even when
                    # sustained CDN throughput exceeds the media bitrate. Reach
                    # the unchanged cap after warm-up; no prefetch or new worker.
                    length = min(owner.segment_bytes, max(STARTUP_SEGMENT_BYTES, offset - start))
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
                        fetch_ms += int((time.monotonic() - reading) * 1000)
                        recovered += failures
                    finally:
                        entry.io_lock.release()
                        self.observation_holds_gate = False
                        observation_fetch_ms += int((time.monotonic() - reading) * 1000)
                        self.flush_observations()
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
                    if not self.write_block(block):
                        observation_write_ms += int((time.monotonic() - writing) * 1000)
                        outcome, reason = 'cancelled', 'delivery_incomplete'
                        owner.report('CLIENT_DISCONNECTED')
                        return  # Known Stop/seek/disconnect never fetches another block.
                    write_ms += int((time.monotonic() - writing) * 1000)
                    observation_write_ms += int((time.monotonic() - writing) * 1000)
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
            # Only exact literals from this module may become error details.
            code = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str else None
            reason = code if code in OBSERVATION_REASONS else 'unexpected_exception'
            outcome = 'cancelled' if reason == 'SHARE_STOPPED' else 'failed'
            owner.report('STREAM_UNAVAILABLE')
            if not started:
                self.send_error(503)
            # After partial output close the socket; do not append an error
            # body or claim the remaining Content-Length reached a real EOF.
            self.close_connection = True
        finally:
            owner.release(entry)
            self.observe('end', terminal=True, outcome=outcome, reason=reason, started=started,
                         wait_ms=observation_wait_ms, fetch_ms=observation_fetch_ms,
                         write_ms=observation_write_ms,
                         wall_ms=int((time.monotonic() - observation_began) * 1000),
                         suppressed=self.observation_suppressed)

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
            while position < len(view) and not self.server.owner.stopping.is_set():
                try:
                    sent = self.connection.send(view[position:position + DELIVERY_CHUNK_BYTES])
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

    def read_block(self, session, entry, start, end, failures):
        owner, data = self.server.owner, bytearray()
        contention_retries = 0
        while start + len(data) <= end and not self.cancelled():
            offset = start + len(data)
            self.observation_stage = 'grant'
            address = entry.grant()
            base, _, options = address.partition('|')
            ua = parse_qs(options)['User-Agent'][0]
            rejected = False
            yielded = False
            possible_close_race = False
            try:
                self.observation_stage = 'connect'
                with session.get(base, headers={'User-Agent': ua,
                    'Range': 'bytes={}-{}'.format(offset, end), 'Accept-Encoding': 'identity',
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
                        for chunk in response.iter_content(FETCH_CHUNK_BYTES):
                            if self.cancelled():
                                raise OSError('SHARE_STOPPED')
                            if len(chunk) > end-start+1-len(data):
                                raise ValueError('SHARE_RANGE_OVERFLOW')
                            data.extend(chunk)
                            if data and len(data) < end-start+1 and entry.io_lock.contended():
                                # Keep the sequential 64 MiB request when it is
                                # alone. A queued seek/scanner gets the next
                                # closed-upstream turn after this exact prefix.
                                yielded = True
                                break
                        if not yielded and len(data) != end-start+1:
                            raise OSError('SHARE_READ_TRUNCATED')
                if yielded:
                    entry.io_lock.note_yield()
                    owner.report('READ_YIELDED bytes={} remaining={}'.format(len(data), end-start+1-len(data)))
                    self.observe('yield', bytes=len(data), remaining=end-start+1-len(data), block_end=end)
                    return data, failures
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
                        if owner.stopping.wait(delay) or self.cancelled():
                            raise OSError('SHARE_STOPPED')
                        owner.report('READ_CONTENTION_RETRY')
                        self.observe('retry', reason='contention', retry=contention_retries,
                                     upstream_start=offset, block_end=end)
                        continue
                    failures += 1
                    if failures > 3:
                        raise ValueError('SHARE_READ_REJECTED')
                    if owner.stopping.wait(.25):
                        raise OSError('SHARE_STOPPED')
                    entry.grant(rejected=address)
                    owner.report('ADDRESS_RENEWED')
                    self.observe('retry', reason='address_renewed', retry=failures,
                                 upstream_start=offset, block_end=end)
            except ValueError:
                raise  # Wrong file/range never becomes video bytes.
            except Exception:
                if self.cancelled():
                    raise OSError('SHARE_STOPPED') from None
                failures += 1
                if failures > 3 or owner.stopping.wait(.25):
                    raise OSError('SHARE_READ_UNAVAILABLE') from None
                owner.report('READ_RESUMED')
                self.observe('retry', reason='read_resumed', retry=failures,
                             upstream_start=offset, block_end=end)
                # Retain exactly the bytes already read into this bounded block;
                # fetch only its missing suffix, then deliver it once to Kodi.
        if len(data) != end-start+1:
            raise OSError('SHARE_STOPPED')
        return data, failures

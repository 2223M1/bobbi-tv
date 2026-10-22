"""Real upstream + downstream loopback HTTP, no virtual IO/clock throughput claims."""
from contextlib import contextmanager
from http.client import HTTPConnection, IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import sys
from threading import Event, Lock, Thread
import time
from urllib.parse import urlsplit

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import share_stream as stream

PAYLOAD = bytes(range(256)) * (4 * 1024 * 1024 // 256)


@contextmanager
def pipeline(progressive=True, mode='normal', delay=0, queue_bytes=128*1024,
             payload=PAYLOAD, segment_bytes=stream.MAX_SEGMENT_BYTES,
             body_pause=None, diagnostic=None, range_headers=None, header_pause=None):
    calls, events, resolves = [], [], []
    lock = Lock()
    active, peak = [0], [0]

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            first_text, last_text = self.headers['Range'][6:].split('-')
            start, end = int(first_text), int(last_text) if last_text else len(payload)-1
            if range_headers is not None:
                range_headers.append(self.headers['Range'])
            with lock:
                first = not calls
                calls.append((start, end))
            if mode == 'expired' and first:
                self.send_error(403)
                return
            if first and header_pause is not None:
                header_pause[0].set()
                if not header_pause[1].wait(8):
                    return
            self.send_response(206)
            self.send_header('Content-Range', 'bytes {}-{}/{}'.format(
                start + (1 if mode == 'wrong_range' else 0), end, len(payload)))
            if mode in ('chunked', 'overflow'):
                self.send_header('Transfer-Encoding', 'chunked')
            else:
                self.send_header('Content-Length', str(end-start+1 + (mode == 'wrong_length')))
            if mode == 'encoding':
                self.send_header('Content-Encoding', 'gzip')
            self.send_header('Connection', 'close')
            self.end_headers()
            try:
                step = 1 if mode == 'trickle' else 16384
                for offset in range(start, end+1, step):
                    if first and body_pause is not None and offset-start >= body_pause[0]:
                        body_pause[1].set()
                        if not body_pause[2].wait(8):
                            return
                    if mode == 'short_once' and first and offset-start >= 128*1024:
                        return  # Header promised more; connection actually closes.
                    if delay:
                        time.sleep(delay)
                    chunk = payload[offset:min(end+1, offset+step)]
                    if mode in ('chunked', 'overflow'):
                        self.wfile.write(('%x\r\n' % len(chunk)).encode() + chunk + b'\r\n')
                    else:
                        self.wfile.write(chunk)
                    self.wfile.flush()
                if mode == 'overflow':
                    self.wfile.write(b'5\r\nEXTRA\r\n')
                if mode in ('chunked', 'overflow'):
                    self.wfile.write(b'0\r\n\r\n')
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()

    class Session(requests.Session):
        def get(self, *args, **kwargs):
            response = super().get(*args, **kwargs)
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            close, closed = response.close, [False]
            def tracked_close():
                close()
                with lock:
                    if not closed[0]:
                        closed[0] = True
                        active[0] -= 1
            response.close = tracked_close
            return response

    def resolve(body):
        resolves.append(True)
        return 'http://127.0.0.1:{}/file|User-Agent=test'.format(server.server_port)

    service = stream.ShareStream(lambda _: None, resolve, lambda _: True,
        session_factory=Session, progressive=progressive, queue_bytes=queue_bytes,
        segment_bytes=segment_bytes, observer=events.append)
    body = dict(request_id='a'*32, locator='am6bqqdocs://A1/123',
        guid='qqdocs:fixture', title='Fixture.mkv', size=len(payload), media='movie:1:0:0')
    ready = (service.register_diagnostic(body, None, diagnostic) if diagnostic is not None
             else service.register(body))
    url = urlsplit(ready['url'])
    def connect(value=None):
        connection = HTTPConnection(url.hostname, url.port, timeout=8)
        connection.request('GET', url.path, headers={'Range':value} if value else {})
        return connection, connection.getresponse()
    try:
        yield service, connect, calls, events, resolves, peak
    finally:
        if body_pause is not None:
            body_pause[2].set()
        if header_pause is not None:
            header_pause[1].set()
        service.close()
        server.shutdown()
        server.server_close()
        thread.join(2)


def wait_end(events, count=1):
    deadline = time.monotonic()+3
    while time.monotonic() < deadline:
        if len([r for r in events if r['phase'] == 'end']) >= count:
            return
        time.sleep(.01)
    raise AssertionError('HTTP worker did not terminate')


@pytest.mark.parametrize('progressive', [False, True])
@pytest.mark.parametrize('mode', ['normal', 'short_once', 'expired'])
def test_real_http_exact_range_short_read_and_renewal(progressive, mode):
    with pipeline(progressive, mode) as (_, connect, calls, events, resolves, peak):
        connection, response = connect('bytes=117-524404')
        assert response.status == 206
        assert response.read() == PAYLOAD[117:524405]
        connection.close()
        wait_end(events)
        assert peak[0] == 1
        assert events[-1]['outcome'] == 'complete'
        if mode == 'short_once':
            assert calls[1][0] == 117+128*1024  # Accepted bytes never replayed.
        if mode == 'expired':
            assert len(resolves) == 2
        assert all(r.get('queue_peak', 0) <= 128*1024 for r in events)


@pytest.mark.parametrize('progressive', [False, True])
def test_wrong_range_never_becomes_video(progressive):
    with pipeline(progressive, 'wrong_range') as (_, connect, _, events, _, _):
        connection, response = connect('bytes=0-99999')
        assert response.status == 503
        connection.close()
        wait_end(events)
        assert events[-1]['delivered'] == 0


def test_progressive_first_byte_precedes_whole_block(record_property):
    timings = {}
    for mode in (False, True):
        with pipeline(mode, delay=.003) as (_, connect, _, events, _, _):
            began = time.monotonic()
            connection, response = connect('bytes=0-2097151')
            first = response.read(1)
            timings[mode] = time.monotonic()-began
            assert first + response.read() == PAYLOAD[:2097152]
            connection.close()
            wait_end(events)
    record_property('block_first_byte_ms', round(timings[False]*1000))
    record_property('progressive_first_byte_ms', round(timings[True]*1000))
    assert timings[True] < timings[False] / 2


def test_pause_releases_gate_for_auxiliary_range_without_killing_first(monkeypatch):
    original = stream.Handler.response_headers
    def small_socket(self, *args):
        self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        original(self, *args)
    monkeypatch.setattr(stream.Handler, 'response_headers', small_socket)
    with pipeline(queue_bytes=64*1024) as (_, connect, calls, events, _, peak):
        first, first_response = connect()
        time.sleep(.15)  # Real downstream stops reading, producer fills its queue.
        second, second_response = connect('bytes=3000000-3032767')
        assert second_response.read() == PAYLOAD[3000000:3032768]
        second.close()
        assert first_response.read() == PAYLOAD
        first.close()
        wait_end(events, 2)
        assert peak[0] == 1
        assert all(r.get('queue_peak', 0) <= 64*1024 for r in events)
        assert len([r for r in events if r['phase'] == 'end' and r['outcome'] == 'complete']) == 2


def test_revoked_request_closes_partial_response_without_fake_eof():
    with pipeline(delay=.006) as (service, connect, _, events, _, _):
        connection, response = connect()
        assert response.read(32768) == PAYLOAD[:32768]
        next(iter(service.records.values())).revoke()
        with pytest.raises((IncompleteRead, ConnectionError, OSError)):
            response.read()
        connection.close()
        wait_end(events)
        assert events[-1]['outcome'] != 'complete'


def test_trickle_does_not_hold_full_chunk_or_delay_revocation():
    with pipeline(mode='trickle', delay=.02) as (service, connect, _, events, _, _):
        began = time.monotonic()
        connection, response = connect('bytes=0-999')
        assert response.read(1) == PAYLOAD[:1]
        assert time.monotonic() - began < 2
        next(iter(service.records.values())).revoke()
        with pytest.raises((IncompleteRead, ConnectionError, OSError)):
            response.read()
        connection.close()
        wait_end(events)
        assert events[-1]['outcome'] != 'complete'
        # All six producer slots have been returned; no orphan trickle reader.
        for _ in range(6):
            assert service.producer_slots.acquire(blocking=False)
        for _ in range(6):
            service.producer_slots.release()


def test_unknown_length_chunked_has_exact_body():
    with pipeline(mode='chunked') as (_, connect, _, events, _, _):
        connection, response = connect('bytes=17-99999')
        assert response.read() == PAYLOAD[17:100000]
        connection.close()
        wait_end(events)
        assert events[-1]['outcome'] == 'complete'


def test_excess_chunked_body_cannot_deliver_successful_final_prefix():
    with pipeline(mode='overflow') as (_, connect, _, events, _, _):
        connection, response = connect('bytes=0-99999')
        with pytest.raises(IncompleteRead) as failure:
            response.read()
        assert failure.value.partial == PAYLOAD[:len(failure.value.partial)]
        assert len(failure.value.partial) < 100000
        assert b'EXTRA' not in failure.value.partial
        connection.close()
        wait_end(events)
        assert events[-1]['outcome'] == 'failed'


def test_trusted_expiry_is_optional_not_parsed_from_url(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(stream.time, 'time', lambda:clock[0])
    urls = ['http://example.test/a?exp=1|User-Agent=test',
            'http://example.test/b|User-Agent=test']
    resolutions = []
    def resolve(body):
        index = len(resolutions)
        resolutions.append(True)
        return stream.ResolvedResource(urls[index], clock[0]+40)
    binding = stream.Binding(dict(request_id='a'*32, locator='x', guid='g',title='f',size=1),
                             resolve, lambda _:True)
    assert binding.grant() == urls[0]
    clock[0] += 20
    assert binding.grant() == urls[0]
    clock[0] += 10
    assert binding.grant() == urls[1]
    assert len(resolutions) == 2
    unknown = stream.Binding(binding.body, lambda _:urls[0], lambda _:True)
    assert unknown.grant() == urls[0]
    clock[0] += 100000
    assert unknown.grant() == urls[0] and len(unknown.renewals) == 1

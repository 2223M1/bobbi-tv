"""Independent CE2024 shutdown repro: real HTTP headers, no patched clocks/joins.

Only the media origin is a local test server; Host, ShareStream, requests,
urllib3, HTTP handler threads and InstanceLock are the actual implementations.
The slow header emits a byte every 50 ms, so the 10 s socket-read timeout does
not impose a 10 s total response-header deadline.
"""
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from threading import Event, Lock, Thread, enumerate as threads
import time
from urllib.parse import urlsplit

import pytest
import requests
import urllib3

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
sys.path.insert(0, str(SOURCE / 'addons/script.module.bobbi.platform/lib'))
sys.path.insert(0, str(SOURCE / 'addons/script.module.bobbi.core/lib'))
from bobbi_platform.host import Host
from bobbi_platform.instance_lock import InstanceLock
from bobbi_core.share_stream import ShareStream


@pytest.mark.parametrize('mode', ['progressive_fast_header',
                                 'progressive_slow_header', 'block_slow_header'])
def test_lease_remains_owned_until_actual_upstream_reader_finishes(tmp_path, mode):
    OUTPUT = Path(os.environ.get('BOBBI_REVIEW_OUTPUT', str(tmp_path)))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entered, release, host_closed = Event(), Event(), Event()
    errors, client_errors = [], []
    timeline, timeline_lock = [], Lock()
    began = time.monotonic()
    def record(event):
        with timeline_lock:
            timeline.append({'event': event, 'seconds': round(time.monotonic() - began, 6)})

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                self.connection.sendall(
                    b'HTTP/1.1 206 Partial Content\r\n'
                    b'Content-Length: 1\r\n'
                    b'Content-Range: bytes 0-0/1\r\n'
                    b'Connection: close\r\nX-Slow: ')
                record('upstream_response_header_started')
                entered.set()
                while not release.wait(.05):
                    self.connection.sendall(b'a')
                record('upstream_response_header_released')
                self.connection.sendall(b'\r\n\r\nx')
            except (BrokenPipeError, ConnectionResetError):
                pass

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    upstream.daemon_threads = True
    listener = Thread(target=upstream.serve_forever,
                      kwargs={'poll_interval': .02}, daemon=True)
    listener.start()
    host = Host(tmp_path / 'host')
    host.start()
    host.streams = ShareStream(lambda _: None,
        lambda body: 'http://127.0.0.1:%d/file|User-Agent=review' % upstream.server_port,
        lambda _: True, progressive=mode.startswith('progressive'), observer=lambda _: None)
    link = host.streams.register(dict(request_id='a' * 32,
        locator='am6bqqdocs://A1/123', guid='qqdocs:review', title='Fixture.mkv',
        size=1, media='movie:1:0:0'))['url']
    target = urlsplit(link)

    def consume():
        connection = HTTPConnection(target.hostname, target.port, timeout=25)
        try:
            connection.request('GET', target.path)
            connection.getresponse().read()
        except Exception as error:
            client_errors.append(type(error).__name__)
        finally:
            connection.close()

    def close():
        try:
            record('host_close_called')
            host.close()
            record('host_close_returned')
        except BaseException as error:
            errors.append(type(error).__name__)
        finally:
            host_closed.set()

    client = Thread(target=consume, daemon=True)
    closer = Thread(target=close, daemon=True)
    contender = InstanceLock(str(host.root / 'runtime.json') + '.lock')
    row = {'mode': mode, 'requests': requests.__version__, 'urllib3': urllib3.__version__,
           'requests_file': requests.__file__, 'urllib3_file': urllib3.__file__,
           'actual_product_join_seconds': 15, 'header_byte_interval_seconds': .05}
    producers = []
    try:
        client.start()
        assert entered.wait(3), 'origin did not receive actual HTTP request'
        producers = [t for t in threads() if t.name == 'share-stream-prefix']
        if mode.startswith('progressive'):
            assert len(producers) == 1
        else:
            assert not producers
        started = time.monotonic()
        closer.start()
        # Close admission and revoke downstream, but the upstream response
        # header is still trickling. Check the actual process lease initially.
        assert not host_closed.wait(.3)
        with pytest.raises(OSError):
            contender.acquire()
        record('initial_replacement_lease_refused')
        row['initial_lease_retained'] = True
        if mode == 'progressive_fast_header':
            release.set()
            assert host_closed.wait(3)
        else:
            host_closed.wait(16.5)
        row.update(seconds_to_probe=round(time.monotonic() - started, 3),
                   host_close_returned=host_closed.is_set(),
                   host_shutdown_complete=getattr(host, '_shutdown_complete', False),
                   old_producer_alive=any(t.is_alive() for t in producers),
                   upstream_header_released=release.is_set())
        try:
            contender.acquire()
        except OSError:
            row['replacement_lease_acquired'] = False
            record('final_replacement_lease_refused')
        else:
            row['replacement_lease_acquired'] = True
            record('final_replacement_lease_acquired')
            contender.close()
        row['unsafe_ownership_overlap'] = (row['replacement_lease_acquired']
                                           and row['old_producer_alive'])
    finally:
        record('cleanup_releases_response_header')
        release.set()
        contender.close()
        closer.join(4)
        client.join(3)
        for producer in producers:
            producer.join(3)
        record('upstream_producers_drained')
        host.close()
        upstream.shutdown()
        upstream.server_close()
        listener.join(2)
        row.update(close_errors=errors, client_errors=client_errors,
                   timeline=timeline,
                   all_probe_threads_drained=not closer.is_alive()
                       and not client.is_alive() and not any(t.is_alive() for t in producers))
        (OUTPUT / (mode + '.json')).write_text(json.dumps(row, indent=2) + '\n')
    assert not errors and row['all_probe_threads_drained']
    # This is the lifecycle invariant. CE2024 fails only the slow progressive
    # case; the positive/negative controls verify the surrounding test path.
    assert not row['unsafe_ownership_overlap'], row


@pytest.mark.parametrize('failure',['admission_closed','thread_start'])
def test_producer_admission_or_start_failure_leaks_neither_worker_nor_slot(monkeypatch,failure):
    from test_ce_progressive_http import pipeline,stream,wait_end
    with pipeline() as (service,connect,calls,events,resolves,peak):
        if failure=='admission_closed':
            acquire=service.producer_slots.acquire
            def stop_then_acquire(*args,**kwargs):
                acquired=acquire(*args,**kwargs)
                service.stopping.set()
                return acquired
            monkeypatch.setattr(service.producer_slots,'acquire',stop_then_acquire)
        else:
            start=stream.Thread.start
            def fail_start(thread):
                if thread.name=='share-stream-prefix':raise RuntimeError('injected thread start failure')
                return start(thread)
            monkeypatch.setattr(stream.Thread,'start',fail_start)
        connection,response=connect('bytes=0-0')
        assert response.status==503
        connection.close();wait_end(events)
        assert not service.producers and not calls
        monkeypatch.undo()
        assert all(service.producer_slots.acquire(blocking=False) for _ in range(6))
        assert not service.producer_slots.acquire(blocking=False)
        for _ in range(6):service.producer_slots.release()


def test_close_exception_keeps_retryable_service_state(monkeypatch):
    from test_ce_progressive_http import pipeline
    with pipeline() as (service,*_):
        close=service.server.server_close
        def fail():raise OSError('injected close failure')
        monkeypatch.setattr(service.server,'server_close',fail)
        with pytest.raises(OSError):service.close()
        assert not getattr(service,'_closed',False) and service.stopping.is_set()
        monkeypatch.setattr(service.server,'server_close',close)
        service.close();service.close()
        assert service._closed and not service.producers

"""Bounded transport observations must not influence fetching or delivery."""
from contextlib import nullcontext
from http.client import HTTPConnection
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from threading import Event
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.catalog/lib'))
from bobbi_core import share_stream as stream
from bobbi_platform.host import Host


class Clock:
    value = 100.0

    def monotonic(self):
        return self.value


class Gate:
    active = False

    def acquire(self, cancelled, initial):
        assert not self.active
        self.active = True
        return True

    def release(self):
        assert self.active
        self.active = False


def run_http(monkeypatch, size=256, segment=64, fetch_failure=0,
             write_failure=0, raise_write=False, broken_observer=False, head=False):
    """Exercise the real serve loop with bounded bytes and no network/threads."""
    monkeypatch.setattr(stream, 'STARTUP_SEGMENT_BYTES', 8)
    monkeypatch.setattr(stream, 'MAX_SEGMENT_BYTES', 64)
    clock, gate = Clock(), Gate()
    monkeypatch.setattr(stream, 'time', SimpleNamespace(monotonic=clock.monotonic, time=lambda: 1000))
    rows, reads, writes, reports, headers, released, errors = [], [], [], [], [], [], []
    entry = SimpleNamespace(body={'size': size}, io_lock=gate)

    def observer(row):
        assert not gate.active, 'Logging must not extend same-file gate ownership'
        if broken_observer:
            raise RuntimeError('logging unavailable')
        rows.append(row)

    owner = SimpleNamespace(
        segment_bytes=segment, acquire=lambda *args: entry,
        release=lambda *args: released.append(True), session=lambda: nullcontext(None),
        observation=lambda entry: dict(run='1'*16, http=3, transport='2'*64,
                                       request='3'*16, file='4'*64, gate=5),
        observer=observer, report=reports.append)
    handler = stream.Handler.__new__(stream.Handler)
    handler.server, handler.path, handler.connection = SimpleNamespace(owner=owner), '/secret-token', object()
    handler.headers = {}
    handler.cancelled = lambda: False
    handler.send_error = errors.append
    handler.response_headers = lambda *args: headers.append(args)

    def fetch(session, selected, offset, upper, failures):
        assert gate.active and failures == 0
        reads.append((offset, upper))
        clock.value += len(reads) * .125
        if len(reads) == fetch_failure:
            raise RuntimeError('https://secret.invalid/path?token=private')
        return bytearray(b'x'*(upper-offset+1)), 0

    def write(block):
        assert not gate.active
        writes.append(len(block))
        clock.value += .0625
        failed = len(writes) == write_failure
        handler.observation_delivered += len(block)//2 if failed else len(block)
        if failed and raise_write:
            raise RuntimeError('/private/userdata/cookie')
        return not failed

    handler.read_block, handler.write_block = fetch, write
    handler.serve(head=head)
    return SimpleNamespace(rows=rows, reads=reads, writes=writes, reports=reports,
                           headers=headers, errors=errors, released=released)


def test_growth_reports_each_fetch_and_write_through_first_maximum_block(monkeypatch):
    result = run_http(monkeypatch)
    assert result.reads == [(0,7), (8,15), (16,31), (32,63), (64,127), (128,191), (192,255)]
    assert result.writes == [8,8,16,32,64,64,64]
    fetched = [r for r in result.rows if r['phase'] == 'fetch_end']
    written = [r for r in result.rows if r['phase'] == 'write_end']
    assert [r['offset'] for r in fetched] == [0,8,16,32,64]
    assert [r['len'] for r in fetched] == [8,8,16,32,64]
    assert [r['len'] for r in written] == [8,8,16,32,64]
    assert [r['fetch_ms'] for r in fetched] == [125,250,375,500,625]
    assert all(r['write_ms'] == 0 and r['complete'] for r in fetched)
    assert all(r['write_ms'] == 62 and r['complete'] for r in written)
    assert [r['fetch_ms'] for r in written] == [125,250,375,500,625]
    assert [r['monotonic_us'] for r in result.rows] == sorted(r['monotonic_us'] for r in result.rows)
    assert result.rows[-1]['phase'] == 'end'
    assert result.rows[-1]['outcome'] == 'complete'
    assert result.rows[-1]['delivered'] == 256
    assert result.released == [True] and not result.errors


def test_total_budget_includes_terminal_record_and_transport_is_unchanged(monkeypatch):
    result = run_http(monkeypatch, segment=1)
    assert len(result.reads) == 256 and sum(result.writes) == 256
    assert len(result.rows) == stream.OBSERVATION_LIMIT == 48
    assert result.rows[-1]['phase'] == 'end'
    assert result.rows[-1]['outcome'] == 'complete'
    assert result.rows[-1]['suppressed'] > 0


def test_failed_fetch_has_bounded_timing_and_no_exception_text(monkeypatch):
    result = run_http(monkeypatch, fetch_failure=2)
    fetched = [r for r in result.rows if r['phase'] == 'fetch_end']
    assert len(result.reads) == 2 and result.writes == [8]
    assert fetched[-1]['offset'] == 8 and fetched[-1]['len'] == 0
    assert fetched[-1]['requested'] == 8 and fetched[-1]['fetch_ms'] == 250
    assert fetched[-1]['complete'] is False
    assert result.rows[-1]['outcome'] == 'failed'
    assert result.rows[-1]['reason'] == 'unexpected_exception'
    assert 'secret' not in json.dumps(result.rows+result.reports)
    assert not result.errors  # A partial response never appends an HTTP error body.


@pytest.mark.parametrize('raise_write', [False, True])
def test_partial_write_is_measured_without_fetching_another_block(monkeypatch, raise_write):
    result = run_http(monkeypatch, write_failure=2, raise_write=raise_write)
    written = [r for r in result.rows if r['phase'] == 'write_end']
    assert len(result.reads) == 2 and result.writes == [8,8]
    assert written[-1]['offset'] == 8 and written[-1]['len'] == 4
    assert written[-1]['requested'] == 8 and written[-1]['write_ms'] == 62
    assert written[-1]['complete'] is False
    assert result.rows[-1]['delivered'] == 12
    assert result.rows[-1]['outcome'] == ('failed' if raise_write else 'cancelled')
    assert '/private' not in json.dumps(result.rows+result.reports)


def test_observer_failure_cannot_change_byte_ranges_or_delivery(monkeypatch):
    result = run_http(monkeypatch, broken_observer=True)
    assert len(result.reads) == 7 and sum(result.writes) == 256
    assert result.released == [True] and not result.errors


def test_head_does_not_fetch_or_add_block_events(monkeypatch):
    result = run_http(monkeypatch, head=True)
    assert not result.reads and not result.writes
    assert [r['phase'] for r in result.rows] == ['begin','end']
    assert result.rows[-1]['outcome'] == 'head_complete'


def test_schema_drops_unknown_fields_and_rejects_sensitive_or_unbounded_values():
    malicious = dict(url='https://secret.invalid', token='private', path='/home/user',
        phase='fetch_end', stage='https://secret.invalid', reason='/private/path',
        run='1'*16, request='bad'*99, transport='2'*64, file='not-a-hash',
        len=64, requested=2**100, fetch_ms=float('inf'), write_ms=True,
        monotonic_us=1234, offset=-1, complete=True, initial='false', custom=['secret'])
    result = json.loads(stream.observation_line(malicious))
    assert result == dict(event='share_read', phase='fetch_end', run='1'*16,
                          transport='2'*64, len=64, monotonic_us=1234, complete=True)
    assert len(stream.observation_line(malicious)) < 1024
    assert json.loads(stream.observation_line(None)) == {'event':'share_read'}


def test_observe_boundary_filters_before_custom_sink(monkeypatch):
    rows = []
    handler = stream.Handler.__new__(stream.Handler)
    handler.observation_state = dict(run='1'*16, path='/secret', token='private')
    handler.observation_count = handler.observation_suppressed = 0
    handler.observation_stage, handler.observation_offset, handler.observation_delivered = 'body', 0, 0
    handler.observation_holds_gate, handler.observation_pending = False, []
    handler.server = SimpleNamespace(owner=SimpleNamespace(observer=rows.append))
    handler.observe('fetch_end', len=8, url='https://secret.invalid')
    assert rows[0]['len'] == 8
    assert not {'path','token','url'} & rows[0].keys()


def test_host_sends_structured_observation_to_existing_report_not_stdout(tmp_path, monkeypatch, capsys):
    reports, kwargs = [], {}
    def factory(*args, **values):
        kwargs.update(values)
        return SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(stream, 'ShareStream', factory)
    host = Host(tmp_path, report=reports.append)
    try:
        assert host._shares() is host._shares()
        kwargs['observer'](dict(phase='fetch_end', offset=8, len=16, fetch_ms=125,
                                write_ms=0, monotonic_us=999, token='private'))
        assert json.loads(reports[-1]) == dict(event='share_read', phase='fetch_end',
            offset=8, len=16, fetch_ms=125, write_ms=0, monotonic_us=999)
        assert not capsys.readouterr().out
    finally:
        host.close()


def test_pending_observations_remain_outside_the_read_gate():
    rows = []
    handler = stream.Handler.__new__(stream.Handler)
    handler.observation_state = {'run':'1'*16}
    handler.observation_count = handler.observation_suppressed = 0
    handler.observation_stage, handler.observation_offset, handler.observation_delivered = 'body', 0, 0
    handler.observation_holds_gate, handler.observation_pending = True, []
    handler.server = SimpleNamespace(owner=SimpleNamespace(observer=rows.append))
    handler.observe('retry', reason='read_resumed', retry=1, token='private')
    assert not rows and len(handler.observation_pending) == 1
    handler.observation_holds_gate = False
    handler.flush_observations()
    assert len(rows) == 1 and rows[0]['reason'] == 'read_resumed'
    assert 'token' not in rows[0] and not handler.observation_pending


def test_loopback_http_preserves_exact_range_and_uses_only_existing_fetches(monkeypatch):
    monkeypatch.setattr(stream, 'STARTUP_SEGMENT_BYTES', 1024)
    payload = bytes(range(256))*64
    requests, rows, done = [], [], Event()

    class Response:
        status_code = 206
        def __init__(self, start, end):
            self.data = payload[start:end+1]
            self.headers = {'Content-Range':'bytes {}-{}/{}'.format(start,end,len(payload)),
                            'Content-Length':str(len(self.data))}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_content(self, chunk_size):
            for offset in range(0,len(self.data),chunk_size):
                yield self.data[offset:offset+chunk_size]

    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, headers, **kwargs):
            start,end = map(int,headers['Range'][6:].split('-'))
            requests.append((start,end))
            return Response(start,end)

    def observer(row):
        rows.append(row)
        if row['phase'] == 'end':
            done.set()

    service = stream.ShareStream(lambda _:None,
        lambda _: 'https://fixture.115cdn.com/private?token=secret|User-Agent=fixture',
        lambda _:True, session_factory=Session, segment_bytes=4096, observer=observer)
    connection = None
    try:
        selected = dict(request_id='a'*32, locator='am6bqqdocs://A1/123', guid='qqdocs:fixture',
                        title='Fixture.mkv', size=len(payload), media='movie:1:0:0')
        ready = service.register(selected)
        url = urlsplit(ready['url'])
        connection = HTTPConnection(url.hostname,url.port,timeout=2)
        connection.request('GET',url.path,headers={'Range':'bytes=100-8291'})
        response = connection.getresponse()
        assert response.status == 206 and response.read() == payload[100:8292]
        assert done.wait(1)
        assert requests == [(100,1123),(1124,2147),(2148,4195),(4196,8291)]
        fetched = [r for r in rows if r['phase'] == 'fetch_end']
        written = [r for r in rows if r['phase'] == 'write_end']
        assert [r['len'] for r in fetched] == [1024,1024,2048,4096]
        assert [r['len'] for r in written] == [1024,1024,2048,4096]
        assert rows[-1]['delivered'] == 8192 and rows[-1]['outcome'] == 'complete'
        assert not any(value in json.dumps(rows) for value in ('secret','Fixture','115cdn','/stream/'))
    finally:
        if connection is not None:
            connection.close()
        service.close()

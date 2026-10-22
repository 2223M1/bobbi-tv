"""Explicit 1 MiB block startup diagnostic; actual local HTTP, no CDN claim."""
from http.client import HTTPConnection, IncompleteRead
from threading import Event, Thread
import time
from urllib.parse import urlsplit

import pytest

from test_ce_progressive_http import pipeline, stream, wait_end, PAYLOAD
from test_ce2035_progressive_initial_range import large_payload, wait_for


MIB = 1024**2
DIAGNOSTIC = dict(mode='block_startup_1m', seconds=60)


def fetch(connect, value=None):
    connection, response = connect(value)
    try:
        return response.status, response.read()
    finally:
        response.close()
        connection.close()


def background_fetch(connect, value=None):
    result, errors, done = [], [], Event()
    def run():
        try:
            result.append(fetch(connect, value))
        except Exception as error:
            errors.append(error)
        finally:
            done.set()
    worker = Thread(target=run, daemon=True)
    worker.start()
    return worker, result, errors, done


@pytest.mark.parametrize('progressive', [False, True])
def test_explicit_block_overrides_only_this_binding_and_keeps_full_growth_cap(progressive, large_payload):
    headers = []
    with pipeline(progressive, payload=large_payload, diagnostic=DIAGNOSTIC,
                  range_headers=headers) as (service, connect, calls, events, resolves, peak):
        assert fetch(connect) == (200, large_payload)
        wait_end(events)
        expected = [(0, MIB-1), (MIB, 2*MIB-1), (2*MIB, 4*MIB-1),
                    (4*MIB, 8*MIB-1), (8*MIB, 16*MIB-1), (16*MIB, 32*MIB-1),
                    (32*MIB, 64*MIB-1), (64*MIB, len(large_payload)-1)]
        assert calls == expected
        assert headers == ['bytes={}-{}'.format(start, end) for start, end in expected]
        assert service.progressive is progressive and service.segment_bytes == 64*MIB
        assert stream.STARTUP_SEGMENT_BYTES == 8*MIB and stream.MAX_SEGMENT_BYTES == 64*MIB
        assert len(resolves) == 1 and peak[0] == 1 and not service.producers
        assert events[-1]['outcome'] == 'complete'
        assert events[-1]['delivered'] == len(large_payload)
        assert all(row['diagnostic_mode'] == 'block_startup_1m' for row in events)
        assert all('queue_puts' not in row and 'timing_scope' not in row for row in events)
        assert next(row for row in events if row['phase'] == 'response')['first_block_bytes'] == MIB
        assert len(events) <= stream.OBSERVATION_LIMIT


def test_candidate_respects_a_smaller_existing_segment_cap():
    with pipeline(False, diagnostic=DIAGNOSTIC, segment_bytes=256*1024) as (
            _, connect, calls, events, _, _):
        assert fetch(connect, 'bytes=117-2097268') == (206, PAYLOAD[117:2097269])
        wait_end(events)
        assert len(calls) == 8 and all(end-start+1 == 256*1024 for start, end in calls)


def test_registration_never_rearms_or_retargets_and_ordinary_peer_keeps_eight_mib(large_payload):
    with pipeline(False, payload=large_payload, diagnostic=DIAGNOSTIC) as (
            service, connect, calls, events, resolves, _):
        entry = next(iter(service.records.values()))
        deadline = entry.diagnostic_deadline
        assert not resolves
        service.register_diagnostic(entry.body, None, DIAGNOSTIC)
        assert entry.diagnostic_deadline == deadline
        for diagnostic in (dict(DIAGNOSTIC, seconds=59), dict(mode='open_range', seconds=60)):
            with pytest.raises(ValueError, match='SHARE_REQUEST_RETARGETED'):
                service.register_diagnostic(entry.body, None, diagnostic)
        with pytest.raises(ValueError, match='SHARE_REQUEST_RETARGETED'):
            service.register(entry.body)
        ready = service.register(dict(entry.body, request_id='b'*32))
        peer = service.records['b'*32]
        assert peer.diagnostic is None and peer.io_lock is entry.io_lock and not resolves
        url = urlsplit(ready['url'])
        connection = HTTPConnection(url.hostname, url.port, timeout=8)
        try:
            connection.request('GET', url.path, headers={'Range': 'bytes=0-9437183'})
            response = connection.getresponse()
            assert response.read() == large_payload[:9*MIB]
            response.close()
        finally:
            connection.close()
        wait_end(events)
        assert calls == [(0, 8*MIB-1), (8*MIB, 9*MIB-1)]


@pytest.mark.parametrize('invalid', [dict(DIAGNOSTIC, seconds=True), dict(DIAGNOSTIC, seconds=0),
    dict(DIAGNOSTIC, seconds=61), dict(DIAGNOSTIC, startup_bytes=MIB)])
def test_fixed_candidate_cannot_inject_a_budget_or_general_preference(invalid):
    with pytest.raises(ValueError, match='SHARE_DIAGNOSTIC_INVALID'):
        stream.checked_diagnostic(invalid)


def test_first_response_still_waits_for_whole_small_block_not_a_progressive_prefix():
    paused, resume = Event(), Event()
    with pipeline(False, diagnostic=DIAGNOSTIC, body_pause=(128*1024, paused, resume)) as (
            _, connect, calls, events, _, _):
        worker, result, errors, done = background_fetch(connect, 'bytes=0-2097151')
        try:
            assert paused.wait(2)
            assert not any(row['phase'] == 'response' for row in events)
            assert not done.is_set() and calls == [(0, MIB-1)]
            resume.set()
            assert done.wait(4)
            assert not errors and result == [(206, PAYLOAD[:2*MIB])]
            wait_end(events)
            assert next(row for row in events if row['phase'] == 'response')['first_block_bytes'] == MIB
        finally:
            resume.set()
            worker.join(5)
        assert not worker.is_alive()


@pytest.mark.parametrize('mode', ['short_once', 'expired', 'chunked'])
def test_first_block_short_read_and_renewal_keep_exact_bounded_suffix(mode):
    start, end, headers = 117, 117+3*MIB-1, []
    with pipeline(False, mode=mode, diagnostic=DIAGNOSTIC, range_headers=headers) as (
            _, connect, calls, events, resolves, peak):
        assert fetch(connect, 'bytes={}-{}'.format(start, end)) == (206, PAYLOAD[start:end+1])
        wait_end(events)
        first_end = start+MIB-1
        prefix = [(start, first_end)]
        if mode == 'short_once':
            prefix.append((start+128*1024, first_end))
            assert any(row.get('reason') == 'read_resumed' for row in events)
        if mode == 'expired':
            prefix.append((start, first_end))
            assert len(resolves) == 2
            assert any(row.get('reason') == 'address_renewed' for row in events)
        assert calls == prefix + [(start+MIB, start+2*MIB-1), (start+2*MIB, end)]
        assert headers == ['bytes={}-{}'.format(lo, hi) for lo, hi in calls]
        assert events[-1]['outcome'] == 'complete' and events[-1]['delivered'] == 3*MIB
        assert peak[0] == 1


@pytest.mark.parametrize('value', [None, 'bytes=117-', 'bytes=117-1001', 'bytes=-1025'])
def test_exact_http_range_forms_and_eof_are_preserved(value):
    with pipeline(False, diagnostic=DIAGNOSTIC) as (_, connect, calls, events, _, _):
        start, end, status = stream.byte_range(value, len(PAYLOAD))
        assert fetch(connect, value) == (status, PAYLOAD[start:end+1])
        wait_end(events)
        assert calls[0] == (start, min(end, start+MIB-1))
        assert calls[-1][1] == end and events[-1]['outcome'] == 'complete'


@pytest.mark.parametrize('value', ['bytes=0-1,4-5', 'bytes=4194304-', 'bytes=-0', 'bytes=2-1'])
def test_invalid_ranges_never_fetch(value):
    with pipeline(False, diagnostic=DIAGNOSTIC) as (_, connect, calls, events, resolves, _):
        assert fetch(connect, value)[0] == 416
        wait_end(events)
        assert not calls and not resolves and events[-1]['delivered'] == 0


@pytest.mark.parametrize('mode', ['wrong_range', 'wrong_length', 'encoding', 'overflow'])
def test_wrong_upstream_response_delivers_zero_media_before_headers(mode):
    with pipeline(False, mode=mode, diagnostic=DIAGNOSTIC) as (_, connect, calls, events, _, _):
        assert fetch(connect, 'bytes=17-99999')[0] == 503
        wait_end(events)
        assert calls == [(17, 99999)]
        assert events[-1]['outcome'] == 'failed' and events[-1]['delivered'] == 0


def test_later_seek_restarts_its_own_small_floor_and_does_not_reuse_media(large_payload):
    with pipeline(False, payload=large_payload, diagnostic=DIAGNOSTIC) as (
            _, connect, calls, events, resolves, peak):
        for start in (0, 10*MIB+117, 0):
            end = start+3*MIB-1
            before = len(calls)
            assert fetch(connect, 'bytes={}-{}'.format(start, end)) == (206, large_payload[start:end+1])
            assert calls[before:] == [(start, start+MIB-1), (start+MIB, start+2*MIB-1),
                                      (start+2*MIB, end)]
        wait_end(events, 3)
        assert len(resolves) == 1 and peak[0] == 1


def test_later_block_injected_read_failure_retains_exact_accepted_suffix(monkeypatch):
    original, accepted = stream.upstream_chunks, []
    def fail_later_once(response):
        start = int(response.headers['Content-Range'].split()[1].split('-')[0])
        if start != MIB or accepted:
            yield from original(response)
            return
        count = 0
        for chunk in original(response):
            yield chunk
            count += len(chunk)
            if count >= 128*1024:
                accepted.append(count)
                raise OSError('injected read interruption')
    monkeypatch.setattr(stream, 'upstream_chunks', fail_later_once)
    with pipeline(False, diagnostic=DIAGNOSTIC) as (_, connect, calls, events, _, _):
        assert fetch(connect, 'bytes=0-3145727') == (206, PAYLOAD[:3*MIB])
        wait_end(events)
        assert calls == [(0, MIB-1), (MIB, 2*MIB-1),
                         (MIB+accepted[0], 2*MIB-1), (2*MIB, 3*MIB-1)]
        assert events[-1]['delivered'] == 3*MIB and events[-1]['outcome'] == 'complete'


def test_four_failed_reads_in_same_first_block_do_not_replay_or_reset_budget(monkeypatch):
    original, accepted = stream.upstream_chunks, []
    def fail_after_one_prefix(response):
        for chunk in original(response):
            yield chunk
            accepted.append(len(chunk))
            raise OSError('injected repeated read interruption')
    monkeypatch.setattr(stream, 'upstream_chunks', fail_after_one_prefix)
    with pipeline(False, diagnostic=DIAGNOSTIC) as (_, connect, calls, events, resolves, _):
        assert fetch(connect)[0] == 503
        wait_end(events)
        assert len(accepted) == len(calls) == 4 and len(resolves) == 1
        assert calls == [(sum(accepted[:index]), MIB-1) for index in range(4)]
        assert events[-1]['outcome'] == 'failed' and events[-1]['delivered'] == 0


def test_new_seek_waiting_during_fetch_gets_gate_after_exact_accepted_prefix():
    paused, resume = Event(), Event()
    with pipeline(False, diagnostic=DIAGNOSTIC, body_pause=(128*1024, paused, resume)) as (
            service, connect, calls, events, _, peak):
        first, result, errors, done = background_fetch(connect, 'bytes=0-2097151')
        tail = None
        try:
            assert paused.wait(2)
            tail, tail_result, tail_errors, tail_done = background_fetch(connect, 'bytes=3000000-3032767')
            wait_for(next(iter(service.records.values())).io_lock.contended)
            resume.set()
            assert tail_done.wait(4) and done.wait(4)
            assert not errors and result == [(206, PAYLOAD[:2*MIB])]
            assert not tail_errors and tail_result == [(206, PAYLOAD[3000000:3032768])]
            wait_end(events, 2)
            yielded = next(row for row in events if row['phase'] == 'yield' and row['start'] == 0)
            assert 0 < yielded['bytes'] < MIB
            assert calls[:2] == [(0, MIB-1), (3000000, 3032767)]
            assert calls[2] == (yielded['bytes'], yielded['bytes']+MIB-1)
            assert peak[0] == 1
        finally:
            resume.set()
            first.join(5)
            if tail is not None:
                tail.join(5)


@pytest.mark.parametrize('cancel', ['revoke', 'expire'])
def test_cancel_during_first_fetch_delivers_no_late_prefix(cancel):
    paused, resume = Event(), Event()
    with pipeline(False, diagnostic=DIAGNOSTIC, body_pause=(128*1024, paused, resume)) as (
            service, connect, calls, events, _, _):
        worker, result, errors, done = background_fetch(connect)
        try:
            assert paused.wait(2)
            entry = next(iter(service.records.values()))
            if cancel == 'revoke':
                entry.revoke()
            else:
                entry.diagnostic_deadline = time.monotonic()-1
            resume.set()
            assert done.wait(4)
            wait_end(events)
            assert all(status >= 400 for status, _ in result)
            assert all(isinstance(error, (ConnectionError, OSError)) for error in errors)
            assert events[-1]['delivered'] == 0 and events[-1]['outcome'] != 'complete'
            assert calls == [(0, MIB-1)] and not service.producers
            assert fetch(connect, 'bytes=0-1')[0] == 404
        finally:
            resume.set()
            worker.join(5)


def test_revocation_after_first_block_never_fetches_next_or_fakes_eof(monkeypatch):
    original = stream.Handler.write_block
    def stop_after_write(self, block):
        completed = original(self, block)
        self.entry.revoke()
        return completed
    monkeypatch.setattr(stream.Handler, 'write_block', stop_after_write)
    with pipeline(False, diagnostic=DIAGNOSTIC) as (_, connect, calls, events, _, _):
        connection, response = connect()
        try:
            with pytest.raises(IncompleteRead) as failure:
                response.read()
            assert failure.value.partial == PAYLOAD[:MIB]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert calls == [(0, MIB-1)]
        assert events[-1]['delivered'] == MIB and events[-1]['outcome'] != 'complete'


def test_slow_downstream_releases_gate_for_other_range_and_resumes_exactly(monkeypatch):
    entered, resume = Event(), Event()
    original = stream.Handler.write_block
    def paused_write(self, block):
        if self.observation_state['start'] == 0 and self.observation_delivered == 0:
            entered.set()
            assert resume.wait(5)
        return original(self, block)
    monkeypatch.setattr(stream.Handler, 'write_block', paused_write)
    with pipeline(False, diagnostic=DIAGNOSTIC) as (_, connect, calls, events, _, peak):
        worker, result, errors, done = background_fetch(connect, 'bytes=0-2097151')
        try:
            assert entered.wait(2)
            assert fetch(connect, 'bytes=3000000-3032767') == (206, PAYLOAD[3000000:3032768])
            assert not done.is_set()
            resume.set()
            assert done.wait(4) and not errors and result == [(206, PAYLOAD[:2*MIB])]
            wait_end(events, 2)
            assert calls == [(0, MIB-1), (3000000, 3032767), (MIB, 2*MIB-1)]
            assert peak[0] == 1
        finally:
            resume.set()
            worker.join(5)


def test_head_does_not_grant_or_fetch():
    with pipeline(False, diagnostic=DIAGNOSTIC) as (service, _, calls, events, resolves, _):
        entry = next(iter(service.records.values()))
        connection = HTTPConnection('127.0.0.1', service.server.server_port, timeout=8)
        try:
            connection.request('HEAD', '/stream/{}/video.mkv'.format(entry.token),
                               headers={'Range': 'bytes=-99'})
            response = connection.getresponse()
            assert response.status == 206 and response.read() == b''
            assert response.getheader('Content-Length') == '99'
            response.close()
        finally:
            connection.close()
        wait_end(events)
        assert not calls and not resolves and events[-1]['outcome'] == 'head_complete'


def test_small_block_keeps_live_account_checks_without_bound_guard(tmp_path, monkeypatch):
    from test_accounts import logged_in
    from test_account_streams import body
    manager, scope = logged_in(tmp_path)
    checks, original = [], manager.is_current
    monkeypatch.setattr(manager, 'is_current', lambda value: (checks.append(value), original(value))[1])
    monkeypatch.setattr(manager, 'current_guard', lambda _: pytest.fail('Not the bound-guard candidate'))
    entry = stream.Binding(body(), lambda *args: '', lambda _: True,
                           account=manager, scope=scope, diagnostic=DIAGNOSTIC)
    assert not entry.cancelled() and len(checks) == 1
    manager.logout(scope)
    assert entry.cancelled() and len(checks) == 2


def test_v8_small_block_receipt_requires_exact_mode_duration_and_revision(tmp_path):
    from test_ce2039_diagnostic_log_probe import receipt, scope_for
    value = receipt()
    value.update(tool_revision=8, route='sharestream-block-startup-1m', transport_diagnostic=dict(DIAGNOSTIC))
    assert scope_for(tmp_path, value)['route'] == 'sharestream-block-startup-1m'
    for change in ({'tool_revision': 7}, {'transport_diagnostic': dict(mode='open_range', seconds=60)},
                   {'transport_diagnostic': dict(DIAGNOSTIC, seconds=59)}):
        with pytest.raises(ValueError, match='DIAGNOSTIC_RECEIPT_INVALID'):
            scope_for(tmp_path, dict(value, **change))

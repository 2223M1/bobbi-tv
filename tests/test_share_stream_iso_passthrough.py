"""Disc ranges use the existing bounded stream, not full-block staging."""
from contextlib import contextmanager
from http.client import HTTPConnection, IncompleteRead
import socket
from threading import Event
from urllib.parse import urlsplit

import pytest

from test_ce_progressive_http import PAYLOAD, pipeline, stream, wait_end
from test_ce2035_progressive_initial_range import large_payload, wait_for


MIB = 1024**2


@contextmanager
def disc_pipeline(*args, title='Fixture.iso', diagnostic=None, **kwargs):
    with pipeline(*args, diagnostic=diagnostic, **kwargs) as values:
        service, _, calls, events, resolves, peak = values
        original = next(iter(service.records.values()))
        body = dict(original.body, request_id='b'*32, title=title)
        ready = (service.register(body, account=original.scope) if diagnostic is None else
                 service.register_diagnostic(body, original.scope, diagnostic))
        url = urlsplit(ready['url'])

        def connect(value=None):
            connection = HTTPConnection(url.hostname, url.port, timeout=8)
            connection.request('GET', url.path, headers={'Range': value} if value else {})
            return connection, connection.getresponse()

        yield service, connect, calls, events, resolves, peak


@pytest.mark.parametrize('title', ['Fixture.iso', 'Fixture.ISO', 'Fixture.iSo'])
@pytest.mark.parametrize('progressive', [False, True])
def test_disc_first_prefix_does_not_wait_for_eight_mib_or_change_global_mode(title, progressive):
    paused, resume = Event(), Event()
    payload = PAYLOAD * 3
    with disc_pipeline(progressive, title=title, payload=payload,
                       body_pause=(64*1024, paused, resume), queue_bytes=64*1024,
                       range_headers=(headers := [])) as (
            service, connect, calls, events, resolves, peak):
        entry = service.records['b'*32]
        assert entry.iso_passthrough and entry.diagnostic is None
        assert entry.diagnostic_deadline is None and not entry.diagnostic_expired()
        assert service.progressive is progressive
        assert not resolves  # Registering still performs no upstream IO.
        connection, response = connect('bytes=117-')
        try:
            assert paused.wait(2)
            assert response.read(16384) == payload[117:117+16384]
            assert not resume.is_set()  # Upstream cannot yet finish even 1 MiB.
            assert headers[0] == 'bytes=117-'
            assert calls[0] == (117, len(payload)-1)
            resume.set()
            assert response.read() == payload[117+16384:]
        finally:
            resume.set()
            response.close()
            connection.close()
        wait_end(events)
        assert events[-1]['outcome'] == 'complete' and peak[0] == 1
        assert next(row for row in events if row['phase'] == 'response')['first_block_bytes'] < MIB
        assert all(row.get('queue_peak', 0) <= 64*1024 for row in events)
        assert not any('diagnostic_mode' in row or 'timing_scope' in row
                       or 'producer_cpu_us' in row or 'batch_budget_us' in row for row in events)


@pytest.mark.parametrize('requested', [None, 'bytes=117-', 'bytes=117-524404', 'bytes=-1025'])
@pytest.mark.parametrize('mode', ['normal', 'short_once', 'expired'])
def test_disc_range_bytes_and_retry_identity_are_preserved(requested, mode):
    with disc_pipeline(False, mode, range_headers=(headers := [])) as (
            _, connect, calls, events, resolves, peak):
        start, end, status = stream.byte_range(requested, len(PAYLOAD))
        connection, response = connect(requested)
        try:
            assert response.status == status
            assert response.read() == PAYLOAD[start:end+1]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert headers[0] == 'bytes={}-{}'.format(start, '' if end == len(PAYLOAD)-1 else end)
        assert calls[0] == (start, end) and calls[-1][1] == end
        assert events[-1]['outcome'] == 'complete' and peak[0] == 1
        if mode == 'expired':
            assert len(resolves) == 2
        if mode == 'short_once' and end-start+1 > 128*1024:
            assert calls[1][0] == start+128*1024


def test_disc_range_does_not_inherit_ordinary_segment_boundary_or_diagnostic_window():
    # A small ordinary cap makes the wire-policy distinction deterministic.
    with disc_pipeline(False, segment_bytes=256*1024, queue_bytes=8*MIB,
                       range_headers=(headers := [])) as (_, connect, calls, events, _, _):
        connection, response = connect('bytes=117-1048692')
        try:
            assert response.read() == PAYLOAD[117:1048693]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert calls == [(117, 1048692)]
        assert headers == ['bytes=117-1048692']
        assert not any('diagnostic_mode' in row or 'timing_scope' in row for row in events)


def test_disc_crosses_sixty_four_mib_without_a_cap_or_diagnostic_metrics(large_payload):
    with disc_pipeline(False, payload=large_payload, queue_bytes=8*MIB,
                       range_headers=(headers := [])) as (_, connect, calls, events, _, peak):
        connection, response = connect()
        try:
            assert response.read() == large_payload
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert calls[0] == (0, len(large_payload)-1) and headers[0] == 'bytes=0-'
        assert all(end == len(large_payload)-1 for _, end in calls)
        assert all(row.get('queue_peak', 0) <= 8*MIB for row in events)
        assert not any('diagnostic_mode' in row or 'timing_scope' in row
                       or 'producer_cpu_us' in row or 'batch_budget_us' in row for row in events)
        assert events[-1]['outcome'] == 'complete' and peak[0] == 1


@pytest.mark.parametrize('title', ['Fixture.mkv', 'Fixture.iso.mkv', 'Fixture.iso?redirect=1'])
def test_non_disc_keeps_existing_block_startup(title):
    payload = PAYLOAD * 3
    with disc_pipeline(False, title=title, payload=payload) as (
            service, connect, calls, events, _, _):
        assert service.records['b'*32].iso_passthrough is False
        connection, response = connect('bytes=0-9437183')
        try:
            assert response.read() == payload[:9*MIB]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert calls == [(0, 8*MIB-1), (8*MIB, 9*MIB-1)]
        assert next(row for row in events if row['phase'] == 'response')['first_block_bytes'] == 8*MIB


def test_explicit_disc_block_diagnostic_keeps_its_own_policy_and_deadline():
    diagnostic = dict(mode='block_startup_1m', seconds=60)
    with disc_pipeline(False, diagnostic=diagnostic) as (service, connect, calls, events, _, _):
        entry = service.records['b'*32]
        assert entry.iso_passthrough is False and entry.diagnostic_deadline is not None
        connection, response = connect('bytes=0-2097151')
        try:
            assert response.read() == PAYLOAD[:2*MIB]
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert calls == [(0, MIB-1), (MIB, 2*MIB-1)]
        assert next(row for row in events if row['phase'] == 'response')['first_block_bytes'] == MIB
        assert all(row['diagnostic_mode'] == diagnostic['mode'] for row in events)


def test_paused_disc_releases_gate_for_seek_and_resumes_exact_bytes(monkeypatch):
    original = stream.Handler.response_headers

    def small_socket(self, *args):
        self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        original(self, *args)

    monkeypatch.setattr(stream.Handler, 'response_headers', small_socket)
    with disc_pipeline(False, queue_bytes=64*1024) as (
            _, connect, calls, events, _, peak):
        first, first_response = connect()
        second = second_response = None
        try:
            wait_for(lambda: any(row['phase'] == 'yield' for row in events))
            second, second_response = connect('bytes=3000000-3032767')
            assert second_response.read() == PAYLOAD[3000000:3032768]
            assert first_response.read() == PAYLOAD
        finally:
            if second_response is not None:
                second_response.close()
            if second is not None:
                second.close()
            first_response.close()
            first.close()
        wait_end(events, 2)
        assert peak[0] == 1 and (3000000, 3032767) in calls
        assert all(row.get('queue_peak', 0) <= 64*1024 for row in events)
        assert len([row for row in events if row['phase'] == 'end'
                    and row['outcome'] == 'complete']) == 2


@pytest.mark.parametrize('stop', ['revoke', 'shutdown'])
def test_disc_revoke_and_shutdown_close_partial_response_without_fake_eof(stop):
    with disc_pipeline(False, delay=.006) as (service, connect, _, events, _, _):
        connection, response = connect()
        try:
            assert response.read(32768) == PAYLOAD[:32768]
            if stop == 'revoke':
                service.records['b'*32].revoke()
            else:
                service.close()
            with pytest.raises((IncompleteRead, ConnectionError, OSError)):
                response.read()
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert events[-1]['outcome'] != 'complete'


@pytest.mark.parametrize('mode', ['wrong_range', 'wrong_length', 'encoding', 'overflow'])
def test_disc_rejects_corrupt_upstream_without_complete_eof(mode):
    with disc_pipeline(False, mode) as (_, connect, _, events, _, _):
        connection, response = connect('bytes=17-99999')
        try:
            if mode == 'overflow':
                with pytest.raises(IncompleteRead):
                    response.read()
            else:
                assert response.status == 503
                response.read()
        finally:
            response.close()
            connection.close()
        wait_end(events)
        assert events[-1]['outcome'] == 'failed'
        assert events[-1]['delivered'] < 99983


@pytest.mark.parametrize('transition', ['logout', 'switch'])
def test_disc_real_account_epoch_revokes_live_bytes_and_old_url(tmp_path, transition):
    from test_accounts import logged_in, credential
    from bobbi_platform.account_manager import AccountError
    manager, scope = logged_in(tmp_path)
    with disc_pipeline(False, delay=.006, account=manager, scope=scope) as (
            service, connect, _, events, _, _):
        entry = service.records['b'*32]
        assert entry.iso_passthrough and entry.scope == scope
        connection, response = connect()
        try:
            assert response.read(32768) == PAYLOAD[:32768]
            if transition == 'logout':
                manager.logout(scope)
            else:
                manager.install(credential('456'), scope)
            with pytest.raises((IncompleteRead, ConnectionError, OSError)):
                response.read()
        finally:
            response.close()
            connection.close()
        wait_end(events)
        wait_for(lambda: not service.producers)
        assert events[-1]['outcome'] != 'complete' and entry.cancelled()
        late, missing = connect('bytes=0-1')
        try:
            assert missing.status == 404
        finally:
            missing.close()
            late.close()
        with pytest.raises(AccountError):
            service.register(dict(entry.body, request_id='c'*32), account=scope)

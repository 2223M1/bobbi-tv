"""115 confirmation timeouts are bounded pending polls, never login success."""
from functools import partial
from http.client import RemoteDisconnected
import io
import json
from threading import Event
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

import pytest

from bobbi_platform import cloud115, runtime
from bobbi_platform.cloud115 import CloudError, CloudTimeout, Login, request
from bobbi_platform.cloud_ui import _LoginAdapter
from bobbi_platform.login_flow import LoginFlowError, LoginRunner
from test_ce2100_login_integration import COOKIES115, login_host, provider_wire


class Reply(io.BytesIO):
    def __init__(self, value):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        super().__init__(raw)
        self.headers = {'Content-Length': str(len(raw))}


class Protocol:
    def __init__(self, polls, begin_error=None, exchange_error=None):
        self.polls, self.calls, self.poll_count = list(polls), [], 0
        self.begin_error, self.exchange_error = begin_error, exchange_error
        self.on_status = lambda: None

    def open(self, value, timeout):
        assert timeout == 8  # No broad HTTP or runner deadline extension.
        route = urlsplit(value.full_url).path
        self.calls.append(route)
        if route == '/api/1.0/web/1.0/token/':
            if self.begin_error is not None:
                raise self.begin_error
            return Reply(dict(state=1, data=dict(uid='fixture', sign='fixture-sign', time=123,
                                                qrcode='https://115.com/scan/fixture')))
        if route == '/get/status/':
            self.poll_count += 1
            result = self.polls.pop(0)
            self.on_status()
            if isinstance(result, Exception):
                raise result
            return Reply(dict(state=1, data={'status': result}))
        assert route == '/app/1.0/os_linux/1.0/login/qrcode'
        if self.exchange_error is not None:
            raise self.exchange_error
        return Reply(dict(state=1, data={'cookie': COOKIES115}))


def setup_runner(fixture, protocol, clock=None):
    options = {'clock': clock} if clock is not None else {}
    flow = Login(partial(request, opener=protocol), **options)
    adapter = _LoginAdapter(flow, runtime.call('account_status', {}))
    window = SimpleNamespace(cancelled=False, statuses=[])
    window.set_status = window.statuses.append
    monitor = SimpleNamespace(abortRequested=lambda: False, waitForAbort=lambda seconds: False)
    return LoginRunner(window, monitor, **options), adapter, window


@pytest.mark.parametrize('failure,timeout', [
    (TimeoutError('synthetic timeout'), True), (URLError(TimeoutError('synthetic timeout')), True),
    (RemoteDisconnected('synthetic disconnect'), False), (URLError(OSError('synthetic offline')), False),
    (HTTPError('https://qrcodeapi.115.com/test', 503, 'synthetic rejection', {}, None), False),
])
def test_timeout_classification_is_narrow_and_keeps_public_code(failure, timeout):
    def reject(*args, **kwargs):
        raise failure
    with pytest.raises(CloudError, match='^NETWORK_ERROR$') as caught:
        request('https://qrcodeapi.115.com/get/status/', opener=SimpleNamespace(open=reject))
    assert isinstance(caught.value, CloudTimeout) is timeout


@pytest.mark.parametrize('deadline_at', ['before-read', 'after-read'])
def test_request_total_deadline_has_internal_timeout_type(monkeypatch, deadline_at):
    now = [0.]
    monkeypatch.setattr(cloud115.time, 'monotonic', lambda: now[0])

    class SlowReply(Reply):
        def read1(self, size):
            now[0] = 9.
            return super().read1(size)

    def opened(*args, **kwargs):
        if deadline_at == 'before-read':
            now[0] = 9.
        return SlowReply({})

    with pytest.raises(CloudTimeout, match='^NETWORK_ERROR$'):
        request('https://qrcodeapi.115.com/get/status/', opener=SimpleNamespace(open=opened))


def test_bad_json_is_not_pending_timeout():
    with pytest.raises(CloudError, match='^INVALID_REPLY$') as caught:
        request('https://qrcodeapi.115.com/get/status/',
                opener=SimpleNamespace(open=lambda *args, **kwargs: Reply(b'not-json')))
    assert not isinstance(caught.value, CloudTimeout)


def test_more_than_three_empty_polls_can_confirm_and_commit_once(login_host):
    protocol = Protocol([TimeoutError(), URLError(TimeoutError()), TimeoutError(),
                         URLError(TimeoutError()), 1, 2])
    runner, adapter, window = setup_runner(login_host, protocol)
    try:
        assert runner.run(adapter, lambda state: None)
        assert protocol.poll_count == 6
        assert protocol.calls.count('/app/1.0/os_linux/1.0/login/qrcode') == 1
        assert login_host.actions.count('account_install') == 1
        assert len(login_host.writes) == 1
        assert runner.commit_acknowledged and login_host.host.accounts.snapshot()['authenticated']
    finally:
        adapter.cancel()


@pytest.mark.parametrize('error_factory', [lambda: RemoteDisconnected('synthetic close'),
                                         lambda: URLError(OSError('synthetic network failure'))])
def test_real_connection_failures_still_stop_after_three_without_saving(login_host, error_factory):
    protocol = Protocol([error_factory() for _ in range(3)])
    runner, adapter, window = setup_runner(login_host, protocol)
    try:
        with pytest.raises(CloudError, match='^NETWORK_ERROR$') as caught:
            runner.run(adapter, lambda state: None)
        assert not isinstance(caught.value, CloudTimeout)
        assert protocol.poll_count == 3
        assert login_host.writes == [] and not runner.commit_sent
        assert '/app/1.0/os_linux/1.0/login/qrcode' not in protocol.calls
    finally:
        adapter.cancel()


def test_cancel_after_pending_polls_never_exchanges_or_saves(login_host):
    protocol = Protocol([TimeoutError() for _ in range(4)])
    runner, adapter, window = setup_runner(login_host, protocol)
    def cancel_late_poll():
        if protocol.poll_count == 4:
            window.cancelled = True
            adapter.cancel()
    protocol.on_status = cancel_late_poll
    try:
        assert not runner.run(adapter, lambda state: None)
        assert adapter.flow.terminal and adapter.flow.token is None
        assert login_host.writes == [] and not runner.commit_sent
        assert '/app/1.0/os_linux/1.0/login/qrcode' not in protocol.calls
    finally:
        adapter.cancel()


@pytest.mark.parametrize('result', [TimeoutError(), 2])
def test_late_poll_after_cancellation_cannot_revive_or_exchange(result):
    protocol = Protocol([result])
    flow = Login(partial(request, opener=protocol))
    flow.begin()
    protocol.on_status = flow.cancel
    with pytest.raises(CloudError, match='^QR_FINISHED$'):
        flow.poll()
    assert flow.terminal and flow.token is None
    assert '/app/1.0/os_linux/1.0/login/qrcode' not in protocol.calls


@pytest.mark.parametrize('result', [TimeoutError(), 2])
def test_poll_reaching_180_seconds_never_exchanges_or_saves(login_host, result):
    now = [0.]
    protocol = Protocol([result])
    runner, adapter, window = setup_runner(login_host, protocol, clock=lambda: now[0])
    protocol.on_status = lambda: now.__setitem__(0, 180.)
    done, actual_poll = Event(), adapter.flow.poll
    def poll_and_finish():
        try:
            return actual_poll()
        finally:
            done.set()
    adapter.flow.poll = poll_and_finish
    try:
        # Either independent deadline may win the worker/UI race.
        with pytest.raises((CloudError, LoginFlowError), match='^(QR_EXPIRED|EXPIRED)$'):
            runner.run(adapter, lambda state: None)
        assert done.wait(1)
        assert adapter.flow.terminal and adapter.flow.token is None
        assert login_host.writes == [] and not runner.commit_sent
        count = len(protocol.calls)
        with pytest.raises(CloudError, match='^QR_FINISHED$'):
            adapter.flow.poll()
        assert len(protocol.calls) == count
    finally:
        adapter.cancel()


@pytest.mark.parametrize('result', [TimeoutError(), 2])
def test_protocol_itself_expires_a_reply_arriving_at_180_seconds(result):
    now = [0.]
    protocol = Protocol([result])
    flow = Login(partial(request, opener=protocol), clock=lambda: now[0])
    flow.begin()
    protocol.on_status = lambda: now.__setitem__(0, 180.)
    with pytest.raises(CloudError, match='^QR_EXPIRED$'):
        flow.poll()
    assert flow.terminal and flow.token is None
    assert '/app/1.0/os_linux/1.0/login/qrcode' not in protocol.calls


def test_exact_180_second_boundary_stops_before_network():
    now = [0.]
    protocol = Protocol([])
    flow = Login(partial(request, opener=protocol), clock=lambda: now[0])
    flow.begin()
    now[0] = 180.
    with pytest.raises(CloudError, match='^QR_EXPIRED$'):
        flow.poll()
    assert protocol.poll_count == 0 and flow.terminal


@pytest.mark.parametrize('stage', ['prepare', 'exchange'])
def test_prepare_or_one_use_exchange_timeout_is_never_pending_or_replayed(login_host, stage):
    protocol = Protocol([2], begin_error=TimeoutError() if stage == 'prepare' else None,
                        exchange_error=URLError(TimeoutError()) if stage == 'exchange' else None)
    runner, adapter, window = setup_runner(login_host, protocol)
    try:
        with pytest.raises(CloudTimeout, match='^NETWORK_ERROR$'):
            runner.run(adapter, lambda state: None)
        assert protocol.calls.count('/api/1.0/web/1.0/token/') == 1
        assert protocol.calls.count('/app/1.0/os_linux/1.0/login/qrcode') == (stage == 'exchange')
        assert protocol.poll_count == (stage == 'exchange')
        assert login_host.writes == [] and not runner.commit_sent
        if stage == 'exchange':
            with pytest.raises(CloudError, match='^QR_FINISHED$'):
                adapter.flow.poll()
            assert protocol.calls.count('/app/1.0/os_linux/1.0/login/qrcode') == 1
    finally:
        adapter.cancel()

"""Provider HTTP -> real login/IPC/owners/storage, entirely on loopback.

Only the GUI and network socket destination are substituted. All credentials
below are synthetic; no device profile or external provider is accessed.
"""
from functools import partial
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler, HTTPCookieProcessor, ProxyHandler, build_opener

import pytest

from bobbi_platform import account_manager, pan_accounts, runtime
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.cloud115 import CloudError, Login as Login115, NoRedirect as Redirect115, request
from bobbi_platform.cloud_ui import _LoginAdapter
from bobbi_platform.host import Host
from bobbi_platform.login_flow import LoginFlowError, LoginRunner
from bobbi_platform.pan_accounts import PanAccounts, PanError
from bobbi_platform.pan_baidu import Login as BaiduLogin, QR_CALLBACK
from bobbi_platform.pan_http import NoRedirect, Session, credentials
from bobbi_platform.pan_service import PanService
from bobbi_platform.pan_ui import _NativeLogin
from test_ce2096_pan_adapters import png, baidu_exchange


BAIDU_COOKIE = 'fixture-bduss-' + 'x'*64
COOKIES115 = dict(UID='12345_fixture', CID='fixture-cid', SEID='fixture-seid')


@pytest.fixture
def provider_wire():
    state = SimpleNamespace(mode='success', requests=[], identity_cookie_sent=False,
                            exchange_form_valid=False, baidu_polls=0, polls115=0, identities=0)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def send(self, value, cookie=False):
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Connection', 'close')
            if cookie:
                scope = {
                    'host-only-cookie': '; Path=/',
                    'passport-cookie': '; Domain=passport.baidu.com; Path=/',
                    'narrow-path-cookie': '; Domain=.baidu.com; Path=/v3',
                    'omitted-path-cookie': '; Domain=.baidu.com',
                    'foreign-cookie': '; Domain=example.test; Path=/',
                    'expired-cookie': '; Domain=.baidu.com; Path=/; Max-Age=0',
                }.get(state.mode, '; Domain=.baidu.com; Path=/')
                self.send_header('Set-Cookie', 'BDUSS=' + BAIDU_COOKIE +
                                 scope + '; Secure; HttpOnly')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.close_connection = True
            parts = urlsplit(self.path)
            path = parts.path
            state.requests.append(('GET', path))  # Never record query tickets or headers.
            if path == '/v2/api/getqrcode':
                self.send(dict(errno=0, sign='fixture-sign',
                               imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture-sign'))
            elif path == '/v2/api/qrcode':
                self.send(png())
            elif path == '/channel/unicast':
                state.baidu_polls += 1
                self.send(dict(errno=1) if state.baidu_polls == 1 else
                          dict(channel_v=json.dumps(dict(status=0, v='fixture-temporary-ticket'))))
            elif path == '/v3/login/main/qrbdusslogin':
                # Exercise real Set-Cookie ingestion; do not populate jar directly.
                assert parse_qs(parts.query)['callback'] == [QR_CALLBACK]
                subject = None if state.mode.startswith('identity-') else '12345'
                self.send(baidu_exchange(subject), cookie=state.mode != 'missing-cookie')
            elif path == '/userx/v1/info/get':
                state.identities += 1
                state.identity_cookie_sent = ('BDUSS=' + BAIDU_COOKIE) in self.headers.get('Cookie', '')
                if state.mode == 'identity-retry' and state.identities == 1:
                    return  # Real RemoteDisconnected; retry identity, never exchange again.
                if state.mode == 'identity-rejected':
                    self.send(dict(errno=1))
                else:
                    self.send(dict(errno=0, data={'fields': {} if state.mode == 'identity-invalid' else {'uid': 12345}}))
            elif path == '/api/1.0/web/1.0/token/':
                self.send(dict(state=1, data=dict(uid='fixture-qr-user', sign='fixture-sign',
                                                 time=123, qrcode='https://115.com/scan/fixture')))
            elif path == '/get/status/':
                state.polls115 += 1
                self.send(dict(state=1, data={'status': min(state.polls115 - 1, 2)}))
            else:
                self.send_error(404)

        def do_POST(self):
            self.close_connection = True
            path = urlsplit(self.path).path
            state.requests.append(('POST', path))
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            state.exchange_form_valid = (parse_qs(body.decode()) == {'account': ['fixture-qr-user'], 'app': ['os_linux']}
                and self.headers.get_content_type() == 'application/x-www-form-urlencoded')
            if path != '/app/1.0/os_linux/1.0/login/qrcode':
                self.send_error(404)
            elif state.mode == 'exchange-disconnected':
                return
            elif state.mode == 'exchange-rejected':
                self.send(dict(state=0))
            else:
                self.send(dict(state=1, data={'cookie': COOKIES115}))

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()

    class LoopbackHTTPS(HTTPSHandler):
        def https_open(self, original):
            # Retain original HTTPS URL/host for real CookieJar origin checks,
            # while every actual socket goes exclusively to this local server.
            def connection(host, timeout, **kwargs):
                return HTTPConnection('127.0.0.1', server.server_address[1], timeout=timeout)
            return self.do_open(connection, original)

    def opener(jar=None):
        handlers = [ProxyHandler({}), LoopbackHTTPS(), NoRedirect() if jar is not None else Redirect115()]
        if jar is not None:
            handlers.append(HTTPCookieProcessor(jar))
        return build_opener(*handlers)

    state.opener = opener
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def login_host(tmp_path, monkeypatch, provider_wire):
    host = Host(tmp_path)
    host.accounts = AccountManager(tmp_path/'115-os_linux.json')
    native = PanAccounts(tmp_path/'pan-accounts-v1.json', {'baidu': partial(credentials, 'baidu')})
    session = Session('baidu')
    session.opener = provider_wire.opener(session.jar)
    host.pans = PanService(tmp_path, host.accounts, accounts=native,
                          login_factory={'baidu': lambda: BaiduLogin(session)})
    monkeypatch.setattr(runtime, 'profile', lambda **kwargs: tmp_path/'runtime.json')
    writes, actions, replies = [], [], []
    original_write = account_manager._write

    def write(path, value):
        original_write(path, value)  # Real atomic persistent owner write.
        writes.append(path.name)

    monkeypatch.setattr(account_manager, '_write', write)
    monkeypatch.setattr(pan_accounts, '_write', write)

    def dispatch(action, body):
        actions.append(action)
        result = host.dispatch(action, body)
        replies.append(result)
        return result

    host.runtime.server.dispatch = dispatch
    host.runtime.start()
    result = SimpleNamespace(host=host, writes=writes, actions=actions, replies=replies, session=session)
    try:
        yield result
    finally:
        host.pans.close()
        host.runtime.close()


def runner_for(provider, fixture, wire):
    window = SimpleNamespace(cancelled=False, messages=[])
    window.set_status = window.messages.append
    monitor = SimpleNamespace(abortRequested=lambda: False, waitForAbort=lambda seconds: False)
    runner = LoginRunner(window, monitor)
    if provider == 'baidu':
        body = dict(provider='baidu', attempt='a'*32)
        adapter = _NativeLogin(body, fixture.host.pans.accounts.snapshot('baidu'))
    else:
        flow = Login115(transport=partial(request, opener=wire.opener()))
        adapter = _LoginAdapter(flow, runtime.call('account_status', {}))
    return runner, adapter, window


@pytest.mark.parametrize('provider', ['baidu', '115'])
def test_real_login_runner_protocol_ipc_and_account_owner_commit_once(login_host, provider_wire, provider):
    runner, adapter, window = runner_for(provider, login_host, provider_wire)
    rendered = []

    def render(value):
        assert login_host.writes == []
        rendered.append(value)

    try:
        assert runner.run(adapter, render)
        assert len(rendered) == 1
        assert runner.diagnostic()['commit_acknowledged']
        assert len(login_host.writes) == 1
        if provider == 'baidu':
            owner = login_host.host.pans.accounts
            current = owner.snapshot('baidu')
            assert provider_wire.identities == 0  # Exchange receipt already identifies this account.
            assert not any(path == '/api/gettemplatevariable' for _, path in provider_wire.requests)
            assert PanAccounts(owner.path, owner.validators).snapshot('baidu') == current
            before = owner.path.read_bytes(), owner.path.stat().st_mtime_ns
            assert runtime.call('pan_login_commit', adapter.body)['state'] == 'committed'
            assert (owner.path.read_bytes(), owner.path.stat().st_mtime_ns) == before
            assert len(login_host.writes) == 1
            assert provider_wire.requests.count(('GET', '/v3/login/main/qrbdusslogin')) == 1
        else:
            owner = login_host.host.accounts
            current = owner.snapshot()
            assert AccountManager(owner.path).snapshot() == current
            assert provider_wire.exchange_form_valid
            assert login_host.actions.count('account_install') == 1
            assert provider_wire.requests.count(('POST', '/app/1.0/os_linux/1.0/login/qrcode')) == 1
            with pytest.raises(CloudError, match='QR_FINISHED'):
                adapter.flow.poll()
        assert current['authenticated']
        with pytest.raises(LoginFlowError, match='INVALID_STATE'):
            runner.run(adapter, render)
        assert len(login_host.writes) == 1
        serialized = json.dumps(login_host.replies)
        assert BAIDU_COOKIE not in serialized and 'fixture-seid' not in serialized
        assert 'fixture-temporary-ticket' not in serialized
    finally:
        if provider == '115':
            adapter.cancel()


def test_baidu_real_identity_disconnect_recovers_without_reexchange(login_host, provider_wire):
    provider_wire.mode = 'identity-retry'
    runner, adapter, window = runner_for('baidu', login_host, provider_wire)
    assert runner.run(adapter, lambda state: None)
    assert provider_wire.identities == 2
    assert provider_wire.identity_cookie_sent
    assert not any(path == '/api/gettemplatevariable' for _, path in provider_wire.requests)
    assert provider_wire.requests.count(('GET', '/v3/login/main/qrbdusslogin')) == 1
    assert len(login_host.writes) == 1
    assert any('核对账号' in message for message in window.messages)


@pytest.mark.parametrize('mode,code,phase', [
    ('identity-rejected', 'PAN_API_REJECTED', 'identity'),
    ('identity-invalid', 'PAN_ACCOUNT_ID_INVALID', 'identity'),
] + [(mode, 'PAN_QR_EXCHANGE_FAILED', 'exchange') for mode in [
    'missing-cookie', 'host-only-cookie', 'passport-cookie', 'narrow-path-cookie',
    'omitted-path-cookie', 'foreign-cookie', 'expired-cookie',
]])
def test_baidu_real_identity_and_cookie_gates_prevent_persistence(login_host, provider_wire, mode, code, phase):
    provider_wire.mode = mode
    runner, adapter, window = runner_for('baidu', login_host, provider_wire)
    with pytest.raises(PanError, match='^' + code + '$') as caught:
        runner.run(adapter, lambda state: None)
    assert login_host.writes == []
    assert not login_host.host.pans.accounts.path.exists()
    assert not login_host.host.pans.accounts.snapshot('baidu')['authenticated']
    assert not runner.commit_sent and not runner.commit_acknowledged
    assert runner.diagnostic(caught.value)['phase'] == phase
    assert runner.diagnostic(caught.value)['code'] == code
    assert provider_wire.identities == (1 if phase == 'identity' else 0)
    assert provider_wire.requests.count(('GET', '/v3/login/main/qrbdusslogin')) == 1


@pytest.mark.parametrize('mode,code', [('exchange-rejected', 'LOGIN_FAILED'),
                                      ('exchange-disconnected', 'NETWORK_ERROR')])
def test_115_real_exchange_failure_preserves_old_login_without_replay(login_host, provider_wire, mode, code):
    owner = login_host.host.accounts
    owner.install(dict(app='os_linux', cookies=dict(COOKIES115, UID='67890_old')), owner.snapshot())
    before = owner.path.read_bytes(), owner.path.stat().st_mtime_ns, owner.snapshot()
    login_host.writes.clear()
    provider_wire.mode = mode
    runner, adapter, window = runner_for('115', login_host, provider_wire)
    try:
        with pytest.raises(CloudError, match='^' + code + '$'):
            runner.run(adapter, lambda state: None)
        assert (owner.path.read_bytes(), owner.path.stat().st_mtime_ns, owner.snapshot()) == before
        assert login_host.writes == [] and 'account_install' not in login_host.actions
        assert provider_wire.requests.count(('POST', '/app/1.0/os_linux/1.0/login/qrcode')) == 1
        assert runner.diagnostic()['phase'] == 'exchange'
        assert not runner.commit_sent
    finally:
        adapter.cancel()


def test_baidu_cancel_after_qr_does_not_poll_exchange_or_save(login_host, provider_wire):
    runner, adapter, window = runner_for('baidu', login_host, provider_wire)
    assert not runner.run(adapter, lambda state: setattr(window, 'cancelled', True))
    assert runtime.call('pan_login_cancel', adapter.body)['state'] == 'cancelled'
    assert provider_wire.requests == [('GET', '/v2/api/getqrcode'), ('GET', '/v2/api/qrcode')]
    assert login_host.writes == []

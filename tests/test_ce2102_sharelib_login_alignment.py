"""Public protocol alignment on loopback only; no live-provider success claim."""
import base64
from functools import partial
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler, HTTPCookieProcessor, ProxyHandler, build_opener

import pytest

from bobbi_platform import cloud115, pan_aliyun
from bobbi_platform.cloud115 import CloudError
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import Session, NoRedirect, QUARK_USER_AGENT, UC_USER_AGENT
from bobbi_platform.pan_quark_uc import QuarkLogin, UCLogin, Client
from test_ce2096_pan_tokens import aliyun_token, ali_content, token_saved, ali_row


COOKIES = dict(UID='12345_fixture', CID='fixture-cid', SEID='fixture-seid')


@pytest.fixture
def wire():
    state = SimpleNamespace(replies=[], calls=[])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_call(self):
            self.close_connection = True
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            parts = urlsplit(self.path)
            # These are exclusively test-generated, synthetic requests.
            state.calls.append(dict(method=self.command, host=self.headers['Host'],
                path=parts.path, query=parse_qs(parts.query, keep_blank_values=True),
                headers=dict(self.headers), body=body))
            value, cookies = state.replies.pop(0)
            if value is None:
                return  # Actual connection failure before HTTP status line.
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Connection', 'close')
            for cookie in cookies:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = handle_call

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()

    class LoopbackHTTPS(HTTPSHandler):
        def https_open(self, original):
            def connection(host, timeout, **kwargs):
                return HTTPConnection('127.0.0.1', server.server_address[1], timeout=timeout)
            return self.do_open(connection, original)

    def opener(jar=None):
        handlers = [ProxyHandler({}), LoopbackHTTPS(), NoRedirect()]
        if jar is not None:
            handlers.append(HTTPCookieProcessor(jar))
        return build_opener(*handlers)

    def session(provider):
        value = Session(provider)
        value.opener = opener(value.jar)
        return value

    state.opener, state.session = opener, session
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def start115(wire, value, cookies=(), status=2):
    wire.replies = [(dict(state=1, data=dict(uid='fixture-qr', sign='fixture-sign', time=123,
        qrcode='https://115.com/scan/fixture')), []), (dict(state=1, data={'status': status}), []),
        (value, cookies)]
    login = cloud115.Login(partial(cloud115.request, opener=wire.opener()))
    login.begin()
    return login


@pytest.mark.parametrize('source', ['nested', 'direct', 'headers', 'mixed'])
def test_115_official_route_headers_and_complete_credential_sources(wire, source):
    data = {'cookie': COOKIES} if source == 'nested' else dict(COOKIES) if source == 'direct' else {}
    cookies = ['%s=%s; Domain=.115.com; Path=/; Secure' % row for row in COOKIES.items()]
    if source == 'mixed':
        data = {'cookie': {'SEID': COOKIES['SEID']}}
        cookies = cookies[:2]
    login = start115(wire, dict(state=1, data=data), cookies if source in ('headers', 'mixed') else [])
    status, result = login.poll()
    assert status == 'confirmed' and result['cookies'] == COOKIES
    begin, poll, exchange = wire.calls
    assert (begin['host'], begin['path']) == ('qrcodeapi.115.com', '/api/1.0/web/1.0/token/')
    assert poll['headers']['User-Agent'] == 'okhttp/5.3.2'
    assert poll['query'] == dict(uid=['fixture-qr'], sign=['fixture-sign'], time=['123'])
    assert (exchange['host'], exchange['path'], exchange['method']) == (
        'passportapi.115.com', '/app/1.0/os_linux/1.0/login/qrcode', 'POST')
    assert parse_qs(exchange['body'].decode()) == dict(account=['fixture-qr'], app=['os_linux'])
    for request in (begin, exchange):
        assert request['headers']['Origin'] == 'https://115cdn.com'
        assert request['headers']['Referer'] == 'https://115cdn.com/'
        assert request['headers']['User-Agent'] == cloud115.QR_USER_AGENT
    with pytest.raises(CloudError, match='QR_FINISHED'):
        login.poll()


@pytest.mark.parametrize('case', ['foreign', 'expired', 'partial', 'conflicting', 'duplicate',
                                  'spoofed-json-attribute', 'missing-success'])
def test_115_header_and_json_credentials_cannot_bypass_validation(wire, case):
    cookies = ['%s=%s; Domain=.115.com; Path=/' % row for row in COOKIES.items()]
    value = dict(state=1, data={})
    if case == 'foreign':
        cookies = [row.replace('.115.com', '.evil.test') for row in cookies]
    elif case == 'expired':
        cookies = [row + '; Max-Age=0' for row in cookies]
    elif case == 'partial':
        cookies = cookies[:1]
    elif case == 'conflicting':
        value['data']['cookie'] = dict(COOKIES, UID='67890_other')
    elif case == 'duplicate':
        cookies.append('UID=67890_other; Domain=.115.com; Path=/')
    elif case == 'spoofed-json-attribute':
        cookies = []
        value['cookies'] = COOKIES
    else:
        value['state'] = 0
    login = start115(wire, value, cookies)
    with pytest.raises(CloudError, match='^(INVALID_CREDENTIALS|LOGIN_FAILED)$'):
        login.poll()
    assert login.terminal


@pytest.mark.parametrize('status', [True, False, 2.0, '2', None])
def test_115_malformed_status_does_not_consume_ticket(wire, status):
    login = start115(wire, dict(state=1, data={'cookie': COOKIES}), status=status)
    with pytest.raises(CloudError, match='INVALID_REPLY'):
        login.poll()
    assert len(wire.calls) == 2


@pytest.mark.parametrize('missing', [True, False])
def test_115_token_without_qrcode_cannot_start_or_exchange(wire, missing):
    # Anonymous device probe of the unsupported os_linux token family returned
    # uid/sign/time but qrcode=null. Never synthesize a scan link from this shape.
    value = dict(uid='fixture-qr', sign='fixture-sign', time=123)
    if not missing:
        value['qrcode'] = None
    wire.replies = [(dict(state=1, code=0, data=value), [])]
    login = cloud115.Login(partial(cloud115.request, opener=wire.opener()))
    with pytest.raises(CloudError, match='INVALID_REPLY'):
        login.begin()
    assert login.phase == 'prepare' and login.token is None
    assert len(wire.calls) == 1
    assert wire.calls[0]['path'] == '/api/1.0/web/1.0/token/'
    with pytest.raises(CloudError, match='QR_FINISHED'):
        login.poll()
    assert len(wire.calls) == 1


def cookie_login(wire, provider, fail=None):
    domain = provider + '.cn'
    cookies = ['__uid=fixture-user; Domain=.%s; Path=/; Secure' % domain,
               '__pus=fixture-session; Domain=.%s; Path=/; Secure' % domain]
    wire.replies = [(dict(status=2000000, data={'members': {'token': 'fixture-qr'}}), []),
        (dict(status=2000000, data={'members': {'service_ticket': 'fixture-ticket'}}), []),
        (None if fail == 'exchange' else dict(success=True), cookies),
        (None if fail == 'identity' else dict(code=0, status=200, data={}), []),
        (dict(code=0, status=200, data={}), [])]
    session = wire.session(provider)
    login = (QuarkLogin if provider == 'quark' else UCLogin)(session)
    return login, login.begin()


@pytest.mark.parametrize('provider', ['quark', 'uc'])
def test_quark_uc_complete_exchange_does_not_require_member_access(wire, provider):
    login, qr = cookie_login(wire, provider, 'identity')
    status, saved = login.poll()
    assert status == 'ready' and saved['provider'] == provider
    assert {row['name'] for row in saved['cookies']} == {'__uid', '__pus'}
    begin, poll, exchange = wire.calls
    values = parse_qs(begin['body'].decode()) if provider == 'uc' else begin['query']
    assert values['client_id'] == ['386' if provider == 'quark' else '529']
    assert poll['query']['client_id'] == ['532' if provider == 'quark' else '529']
    assert values['request_id'] == poll['query']['request_id']
    assert parse_qs(urlsplit(qr).query)['client_id'] == poll['query']['client_id']
    assert begin['method'] == ('POST' if provider == 'uc' else 'GET')
    if provider == 'uc':
        assert 10000 <= int(begin['query']['__dt'][0]) <= 99999
        assert int(begin['query']['__t'][0]) > 0
    assert exchange['query'] == (dict(st=['fixture-ticket'], lw=['scan']) if provider == 'quark'
                                 else dict(st=['fixture-ticket']))
    assert all(row['headers']['User-Agent'] == (QUARK_USER_AGENT if provider == 'quark' else UC_USER_AGENT)
               for row in wire.calls)
    assert sum(row['path'] == '/account/info' for row in wire.calls) == 1
    assert not any('/member' in row['path'] for row in wire.calls)
    with pytest.raises(PanError, match='FINISHED'):
        login.poll()


@pytest.mark.parametrize('provider', ['quark', 'uc'])
def test_quark_uc_ambiguous_exchange_is_terminal(wire, provider):
    login, _ = cookie_login(wire, provider, 'exchange')
    with pytest.raises(PanError, match='PAN_NETWORK_ERROR'):
        login.poll()
    with pytest.raises(PanError, match='FINISHED'):
        login.poll()
    assert login.phase == 'exchange' and len(wire.calls) == 3


def ali_login(wire, failure=None, identity=None):
    ext = base64.b64encode(json.dumps({'pds_login_result': {'refreshToken': 'fixture-initial'}}).encode()).decode()
    identity = identity if identity is not None else dict(default_drive_id='100', resource_drive_id='100')
    wire.replies = [(ali_content(codeContent='https://signin.aliyundrive.com/qr', ck='fixture-ck', t=123), []),
        (ali_content(qrCodeStatus='CONFIRMED', bizExt=ext), []),
        (None if failure == 'exchange' else aliyun_token(), []),
        (None if failure == 'identity' else identity, []), (identity, [])]
    login = pan_aliyun.Login(wire.session('aliyun'), wall_clock=lambda: 1000)
    login.begin()
    return login


def test_aliyun_real_session_saves_token_identity_without_drive_probe(wire):
    login = ali_login(wire, 'identity')
    state, value = login.poll()
    assert state == 'ready' and value['subject'] == '12345'
    begin, poll, exchange = wire.calls
    assert exchange['host'] == 'auth.aliyundrive.com'
    assert exchange['path'] == '/v2/account/token' and exchange['method'] == 'POST'
    assert json.loads(exchange['body']) == dict(grant_type='refresh_token', refresh_token='fixture-initial')
    assert all(row['headers']['Origin'] == 'https://www.alipan.com' for row in wire.calls)
    assert all(row['headers']['Referer'] == 'https://www.alipan.com/' for row in wire.calls)
    assert 'Authorization' not in exchange['headers']
    assert len(wire.calls) == 3 and login.pending is None and login.refresh is None


@pytest.mark.parametrize('identity', [{}, {'default_drive_id': 'foreign'},
    {'default_drive_id': '100', 'user_id': 'another'}, {'resource_drive_id': True}])
def test_aliyun_unrequested_drive_metadata_cannot_replace_token_identity(wire, identity):
    login = ali_login(wire, identity=identity)
    state, value = login.poll()
    assert state == 'ready' and value['subject'] == '12345'
    assert len(wire.calls) == 3


def test_aliyun_ambiguous_rotation_not_replayed(wire):
    login = ali_login(wire, 'exchange')
    with pytest.raises(PanError, match='PAN_NETWORK_ERROR'):
        login.poll()
    with pytest.raises(PanError, match='FINISHED'):
        login.poll()
    assert login.phase == 'exchange' and len(wire.calls) == 3


def test_aliyun_new_api_routes_preserve_exact_file_and_renewal(wire):
    wire.replies = [(aliyun_token(), []), (dict(items=[ali_row()], next_marker=''), []),
        (ali_row(), []), (dict(url='https://cn-beijing-data.aliyundrive.com/file', size=1234), [])]
    client = pan_aliyun.Client(token_saved(expires=1001), session=wire.session('aliyun'), clock=lambda: 1000)
    publications = []
    client.renew_if_needed(lambda new, old: publications.append((new, old)))
    assert len(publications) == 1
    selected = client.list_files('100:root')['items'][0]
    assert client.resolve_original(selected)['original']
    assert [call['host'] for call in wire.calls] == ['auth.aliyundrive.com'] + ['api.aliyundrive.com'] * 3
    assert all(call['headers']['Authorization'] == 'Bearer fixture-access-new' for call in wire.calls[1:])

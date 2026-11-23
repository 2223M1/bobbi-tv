"""Official exchange receipt is login authority; all HTTP stays in memory."""
from email.message import Message
from http.cookiejar import Cookie
import io
import json
import logging
import sys
from types import SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPCookieProcessor, ProxyHandler, build_opener
from urllib.response import addinfourl

import pytest

from bobbi_platform import pan_baidu
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import NoRedirect, Session
from test_ce2096_pan_adapters import png


BDUSS = 'synthetic-cookie-' + 'x' * 192
TICKET = 'synthetic-channel-' + 't' * 192
IDENTITY_PATH = '/userx/v1/info/get'
EXCHANGE_PATH = '/v3/login/main/qrbdusslogin'


def receipt(subject='123', code='0', session=None, encoding='utf-8'):
    value = dict(errInfo={'no': code, 'msg': '扫码结果'}, code=code, data=dict(
        user={} if subject is None else {'userId': subject}, session=session or {}))
    payload = json.dumps(value, ensure_ascii=False).replace('"data":', "'data':", 1)
    return (pan_baidu.QR_CALLBACK + '(' + payload + ');').encode(encoding)


def cookie(name='BDUSS', value=BDUSS, domain='.baidu.com', path='/'):
    return Cookie(0, name, value, None, False, domain, domain.startswith('.'), domain.startswith('.'),
                  path, True, True, None, True, None, None, {})


def memory_login(exchange, identity=None, issue_cookie=True):
    """Real Session/HTTPCookieProcessor, replacing only the HTTPS socket handler."""
    session = Session('baidu')
    calls = []

    class MemoryHTTPS(HTTPSHandler):
        def https_open(self, request):
            path = urlsplit(request.full_url).path
            calls.append(dict(path=path, cookie=request.get_header('Cookie', ''),
                              agent=request.get_header('User-agent'), referer=request.get_header('Referer')))
            headers = Message()
            if path == '/v2/api/getqrcode':
                raw = json.dumps(dict(errno=0, sign='fixture-sign',
                    imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture-sign')).encode()
            elif path == '/v2/api/qrcode':
                raw = png()
            elif path == '/channel/unicast':
                raw = json.dumps(dict(channel_v=json.dumps(dict(status=0, v=TICKET)))).encode()
            elif path == EXCHANGE_PATH:
                raw = exchange
                if issue_cookie:
                    headers.add_header('Set-Cookie', 'BDUSS=' + BDUSS + '; Domain=.baidu.com; Path=/; Secure; HttpOnly')
            elif path == IDENTITY_PATH:
                raw = json.dumps(identity if identity is not None else dict(data={'fields': {'uid': '456'}})).encode()
            else:
                raise AssertionError('Unexpected network route: ' + path)
            headers.add_header('Content-Length', str(len(raw)))
            reply = addinfourl(io.BytesIO(raw), headers, request.full_url, 200)
            reply.msg = 'OK'
            return reply

    session.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(session.jar), MemoryHTTPS())
    flow = pan_baidu.Login(session)
    flow.begin()
    return flow, session, calls


@pytest.mark.parametrize('identity', ['123', 123])
@pytest.mark.parametrize('code', ['0', 0])
def test_single_quoted_data_callback_requires_success_and_extracts_stable_user_id(identity, code):
    raw = receipt(identity, code)
    assert b"'data':" in raw
    assert pan_baidu._exchange_subject(raw) == '123'


@pytest.mark.parametrize('code', ['310005', 310005, '400021', -6])
def test_explicit_exchange_failure_cannot_be_repaired_by_cookie_or_identity(code):
    flow, session, calls = memory_login(receipt(code=code))
    with pytest.raises(PanError, match='^PAN_QR_EXCHANGE_FAILED$'):
        flow.poll()
    assert pan_baidu._has_bduss(session)
    assert flow.terminal and flow.subject is None and flow.phase == 'exchange'
    assert [call['path'] for call in calls][-1] == EXCHANGE_PATH
    assert len(calls) == 4


@pytest.mark.parametrize('value', [None, {}, [], True, {'no': None}, {'no': True}, {'no': False}, {'no': []}])
def test_missing_or_malformed_success_code_is_not_an_exchange_receipt(value):
    raw = json.dumps(dict(errInfo=value, data={'user': {'userId': '123'}})).encode()
    with pytest.raises(PanError, match='^PAN_REPLY_INVALID$'):
        pan_baidu._exchange_subject(raw)


@pytest.mark.parametrize('identity', [True, False, 0, -1, 1.5, '0', '-1', ' 123', '123 ', '1e3', '9'*33, [], {}])
def test_nonstable_or_nonnumeric_exchange_identity_cannot_publish(identity):
    with pytest.raises(PanError, match='^PAN_ACCOUNT_ID_INVALID$'):
        pan_baidu._exchange_subject(receipt(identity))


@pytest.mark.parametrize('raw', [
    b'evil({"errInfo":{"no":0},"data":{}});',
    b'bd__cbs__cupstt({"errInfo":{"no":0},"data":{}}); evil()',
    b'bd__cbs__cupstt((function(){return {"errInfo":{"no":0},"data":{}}})())',
    b'bd__cbs__cupstt({"errInfo":{"no":0},"data":{}})//comment',
    b'<script>bd__cbs__cupstt({"errInfo":{"no":0},"data":{}})</script>',
    b'bd__cbs__cupstt({"errInfo":{"no":0},"data":{}});bd__cbs__cupstt({})',
    b'{"errInfo":{"no":0},"data":{},"extra":undefined}',
    b'{"errInfo":{"no":0},"data":{},}',
    b'{"errInfo":{"no":0},"data":/*comment*/{}}',
    b'{"errInfo":{"no":0},"data":{"user":{userId:"123"}}}',
    b'{"errInfo":{"no":0},"data":{"user":{"userId":\'123\'}}}',
    b'{"errInfo":{"no":0},"data":{"user":{"userId":"123"}}',
    b'[]', b'null', b'false', b'"string"', b'', b'\xff',
    b'[' * 8000 + b']' * 8000,
    b'{"errInfo":{"no":0},"data":{},"extra":' + b'[' * 8000 + b']' * 8000 + b'}',
    b'x' * 65537,
], ids=['foreign-callback', 'trailing-script', 'function-expression', 'comment-trailer',
        'html', 'two-callbacks', 'undefined', 'trailing-comma', 'inline-comment',
        'unquoted-key', 'single-quoted-value', 'truncated-object', 'array', 'null',
        'bool', 'string', 'empty', 'bad-encoding', 'deep-array', 'deep-object', 'oversize'])
def test_callback_parser_rejects_scripts_malformed_and_unbounded_nesting(raw):
    with pytest.raises(PanError, match='^PAN_REPLY_INVALID$'):
        pan_baidu._exchange_object(raw)


@pytest.mark.parametrize('shape', ['dict', 'list', 'mixed'])
@pytest.mark.parametrize('depth', [3, 64, 65], ids=['shallow', 'limit', 'over-limit'])
def test_callback_parser_enforces_container_depth_independently_of_python(shape, depth):
    nested = 'leaf'
    # The exchange object itself is depth one; strings do not add depth.
    for level in range(depth - 1):
        nested = ({'child': nested} if shape == 'dict' or
                  (shape == 'mixed' and level % 2 == 0) else [nested])
    value = dict(errInfo={'no': 0}, data={'user': {'userId': '123'}}, extra=nested)
    raw = json.dumps(value).encode()
    if depth > 64:
        with pytest.raises(PanError, match='^PAN_REPLY_INVALID$'):
            pan_baidu._exchange_object(raw)
    else:
        assert pan_baidu._exchange_object(raw) == value
        assert pan_baidu._exchange_subject(raw) == '123'


def test_callback_parser_does_not_count_brackets_inside_strings_as_depth():
    value = dict(errInfo={'no': 0}, data={'user': {'userId': '123'}},
                 note='[{' * 8000 + '}]' * 8000 + ' "quoted" \\ text')
    assert pan_baidu._exchange_object(json.dumps(value).encode()) == value


@pytest.mark.parametrize('raw', [
    b'{"errInfo":{"no":1,"no":0},"data":{}}',
    b'{"errInfo":{"no":0},"data":{},\'data\':{}}',
    b'{"errInfo":{"no":0},"data":{"user":{"userId":"123","userId":"456"}}}',
    b'{"errInfo":{"no":0},"data":{},"extra":{"key":1,"key":2}}',
] + [b'{"errInfo":{"no":0},"data":{},"extra":' + number + b'}'
     for number in [b'NaN', b'Infinity', b'-Infinity']])
def test_parser_rejects_duplicate_keys_and_nonjson_numeric_constants(raw):
    with pytest.raises(PanError, match='^PAN_REPLY_INVALID$'):
        pan_baidu._exchange_object(raw)


def test_parser_preserves_single_quoted_data_text_inside_json_strings():
    value = dict(errInfo={'no': 0}, data={'user': {'userId': '123'}},
                 note='literal \'data\': "quoted" and escaped \\" text')
    payload = json.dumps(value).replace('"data":', "'data':", 1)
    raw = (pan_baidu.QR_CALLBACK + '(' + payload + ')').encode()
    assert pan_baidu._exchange_object(raw) == value


def test_gbk_response_is_data_only_and_retains_success_identity():
    raw = receipt(encoding='gb18030')
    with pytest.raises(UnicodeDecodeError):
        raw.decode('utf-8')
    assert pan_baidu._exchange_subject(raw) == '123'


def test_exchange_identity_is_primary_without_template_directory_or_secondary_identity_request():
    flow, session, calls = memory_login(receipt('789'))
    state, saved = flow.poll()
    assert state == 'ready' and saved['subject'] == '789'
    assert saved['cookies'] == [dict(name='BDUSS', value=BDUSS, domain='.baidu.com', path='/')]
    assert [call['path'] for call in calls] == [
        '/v2/api/getqrcode', '/v2/api/qrcode', '/channel/unicast', EXCHANGE_PATH]
    assert flow.terminal and flow.subject is None


@pytest.mark.parametrize('user', [None, {}, {'userId': ''}, {'userId': None}])
def test_missing_exchange_identity_only_uses_mbd_fallback(user):
    raw = (pan_baidu.QR_CALLBACK + '(' + json.dumps(dict(errInfo={'no': '0'}, data={'user': user})) + ');').encode()
    flow, session, calls = memory_login(raw)
    state, saved = flow.poll()
    assert state == 'ready' and saved['subject'] == '456'
    assert len(calls) == 5 and calls[-1]['path'] == IDENTITY_PATH
    assert calls[-1]['cookie'] == 'BDUSS=' + BDUSS
    assert calls[-1]['agent'] == 'Mozilla/5.0 (Linux; Android 12; SM-X800) AppleWebKit/537.36'
    assert calls[-1]['referer'] is None


@pytest.mark.parametrize('raw', [b'', b'{}', receipt(session={'bduss': BDUSS}), receipt(None, session={'bduss': BDUSS})])
def test_channel_ticket_and_body_session_never_manufacture_a_login_cookie(raw):
    flow, session, calls = memory_login(raw, issue_cookie=False)
    with pytest.raises(PanError):
        flow.poll()
    assert not list(session.jar)
    assert flow.terminal and flow.subject is None
    assert len(calls) == 4
    assert calls[-1]['path'] == EXCHANGE_PATH


@pytest.mark.parametrize('field', ['errno', 'error_code'])
@pytest.mark.parametrize('code', [-6, 1, '0', False, None])
def test_mbd_explicit_error_rejects_even_when_it_contains_a_plausible_uid(field, code):
    flow, session, calls = memory_login(receipt(None), identity={field: code, 'data': {'fields': {'uid': '456'}}})
    with pytest.raises(PanError, match='^PAN_API_REJECTED$'):
        flow.poll()
    assert flow.subject is None and calls[-1]['path'] == IDENTITY_PATH


@pytest.mark.parametrize('domain,path', [('.pan.baidu.com', '/'), ('passport.baidu.com', '/'),
                                      ('.baidu.com', '/api'), ('.example.test', '/')])
def test_mbd_fallback_cannot_expand_an_unrelated_cookie_scope(domain, path):
    session = Session('baidu', opener=SimpleNamespace(open=lambda *args, **kwargs: pytest.fail('Must not request identity')))
    session.jar.set_cookie(cookie(domain=domain, path=path))
    assert not pan_baidu._has_bduss(session, pan_baidu.IDENTITY_URL)
    with pytest.raises(PanError, match='^PAN_CREDENTIALS_INVALID$'):
        pan_baidu.Client(session=session).subject()


def test_bfess_only_does_not_impersonate_the_required_bduss_cookie():
    session = Session('baidu')
    session.jar.set_cookie(cookie(name='BDUSS_BFESS'))
    assert not pan_baidu._has_bduss(session)
    assert not pan_baidu._has_bduss(session, pan_baidu.IDENTITY_URL)


@pytest.mark.parametrize('domain', ['mbd.baidu.com', '.mbd.baidu.com'])
def test_exact_mbd_cookie_survives_export_without_becoming_a_pan_or_passport_cookie(domain):
    session = Session('baidu')
    session.jar.set_cookie(cookie())
    session.jar.set_cookie(cookie(name='STOKEN', value='synthetic-mbd-token', domain=domain, path='/userx'))
    saved = session.export(subject='123')
    restored = Session('baidu', saved)
    assert 'STOKEN=synthetic-mbd-token' in restored.cookie_header(pan_baidu.IDENTITY_URL)
    for url in ['https://pan.baidu.com/api/list', 'https://passport.baidu.com/channel/unicast',
                'https://mbd.baidu.com/other', 'https://mbd.baidu.com.evil.test/userx/v1/info/get']:
        assert 'STOKEN=' not in restored.cookie_header(url)


@pytest.mark.parametrize('domain', ['mbd.baidu.com.evil.test', 'fake-mbd.baidu.com', 'other.baidu.com'])
def test_mbd_export_exception_does_not_allow_arbitrary_domains(domain):
    session = Session('baidu')
    session.jar.set_cookie(cookie())
    session.jar.set_cookie(cookie(name='STOKEN', value='synthetic-token', domain=domain))
    with pytest.raises(PanError, match='^PAN_CREDENTIALS_INVALID$'):
        session.export(subject='123')


@pytest.mark.parametrize('url', ['https://mbd.baidu.com/userx/v1/info/other',
    'https://mbd.baidu.com.evil.test/userx/v1/info/get', 'http://mbd.baidu.com/userx/v1/info/get',
    'https://pan.baidu.com/api/gettemplatevariable'])
def test_mbd_identity_route_allowlist_is_exact_and_template_api_is_removed(url):
    session = Session('baidu', opener=SimpleNamespace(open=lambda *args, **kwargs: pytest.fail('Must not send request')))
    with pytest.raises(PanError, match='^PAN_ORIGIN_REJECTED$'):
        session.request(url)


def test_protocol_facts_go_to_kodi_info_without_credentials_or_upstream_text(monkeypatch, caplog):
    logs = []
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(LOGINFO=17, log=lambda message, level: logs.append((message, level))))
    session = Session('baidu')
    session.jar.set_cookie(cookie())
    pan_baidu._login_probe('exchange', session, receipt('987654321', session={'bduss': BDUSS}))
    assert len(logs) == 1 and logs[0][1] == 17
    assert '"exchange_code": 0' in logs[0][0]
    for private in [BDUSS, '987654321', '扫码结果', 'userId', 'session']:
        assert private not in logs[0][0]
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


def test_protocol_fallback_logging_is_info_not_stderr_warning(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, 'xbmc', None)
    caplog.set_level(logging.INFO, logger=pan_baidu.__name__)
    pan_baidu._login_probe('exchange', Session('baidu'), receipt())
    records = [record for record in caplog.records if record.name == pan_baidu.__name__]
    assert len(records) == 1 and records[0].levelno == logging.INFO
    assert '"exchange_code": 0' in records[0].message

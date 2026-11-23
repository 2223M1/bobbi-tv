"""Unknown exchange bodies recover only through first-party cookie identity.

Every response and credential in this module is synthetic and in memory.
"""
import json
from urllib.parse import urlsplit

import pytest

from bobbi_platform import pan_baidu
from bobbi_platform.pan_accounts import PanError
from test_ce2105_baidu_contract import (
    BDUSS, EXCHANGE_PATH, IDENTITY_PATH, cookie, memory_login, receipt,
)


UNKNOWN_BODIES = [
    b'<html><script>parent.callback({"userId":"999"})</script></html>',
    b'other_callback({"errInfo":{"no":0},"data":{"user":{"userId":"999"}}});',
    b'bd__cbs__cupstt((function(){throw new Error("never execute");})());',
    b'{"errInfo":{"no":0},"data":',
    b'',
    b'\xff',
]


def paths(calls):
    return [call['path'] for call in calls]


def assert_single_exchange(calls):
    assert paths(calls).count('/channel/unicast') == 1
    assert paths(calls).count(EXCHANGE_PATH) == 1


@pytest.mark.parametrize('body', UNKNOWN_BODIES)
def test_unknown_exchange_body_uses_mbd_identity_not_embedded_script(body, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Exchange bodies are data, not executable code')

    monkeypatch.setattr(pan_baidu, 'eval', forbidden, raising=False)
    monkeypatch.setattr(pan_baidu, 'exec', forbidden, raising=False)
    flow, session, calls = memory_login(body, identity={'data': {'fields': {'uid': '456'}}})

    state, saved = flow.poll()

    assert state == 'ready' and saved['subject'] == '456'
    assert saved['cookies'] == [dict(name='BDUSS', value=BDUSS, domain='.baidu.com', path='/')]
    assert paths(calls) == ['/v2/api/getqrcode', '/v2/api/qrcode',
                            '/channel/unicast', EXCHANGE_PATH, IDENTITY_PATH]
    assert calls[-1]['cookie'] == 'BDUSS=' + BDUSS
    assert flow.terminal and flow.subject is None
    with pytest.raises(PanError, match='^PAN_QR_FINISHED$'):
        flow.poll()
    assert_single_exchange(calls)


@pytest.mark.parametrize('body', UNKNOWN_BODIES)
def test_unknown_exchange_without_real_cookie_never_requests_identity(body):
    flow, session, calls = memory_login(body, issue_cookie=False)

    with pytest.raises(PanError):
        flow.poll()

    assert not list(session.jar)
    assert flow.terminal and flow.subject is None
    assert IDENTITY_PATH not in paths(calls)
    with pytest.raises(PanError, match='^PAN_QR_FINISHED$'):
        flow.poll()
    assert_single_exchange(calls)


@pytest.mark.parametrize('field', ['errno', 'error_code'])
@pytest.mark.parametrize('code', [-6, 1, '0', False, None])
def test_unknown_exchange_with_cookie_cannot_override_mbd_error(field, code):
    flow, session, calls = memory_login(UNKNOWN_BODIES[0],
        identity={field: code, 'data': {'fields': {'uid': '456'}}})

    with pytest.raises(PanError, match='^PAN_API_REJECTED$'):
        flow.poll()

    assert flow.subject is None and paths(calls)[-1] == IDENTITY_PATH
    assert pan_baidu._has_bduss(session)
    assert_single_exchange(calls)


@pytest.mark.parametrize('uid', [None, '', True, False, 0, -1, 1.5,
                                '0', '-1', ' 456', '456 ', '1e3', '9' * 33, [], {}])
def test_unknown_exchange_requires_stable_mbd_account_identity(uid):
    flow, session, calls = memory_login(UNKNOWN_BODIES[0],
        identity={'errno': 0, 'data': {'fields': {'uid': uid}}})

    with pytest.raises(PanError, match='^PAN_ACCOUNT_ID_INVALID$'):
        flow.poll()

    assert flow.subject is None and paths(calls)[-1] == IDENTITY_PATH
    assert_single_exchange(calls)


@pytest.mark.parametrize('domain,path', [
    ('passport.baidu.com', '/'), ('.example.test', '/'),
    ('.pan.baidu.com', '/'), ('.baidu.com', '/api'),
    ('.baidu.com', '/v3'), ('.baidu.com', '/userx'),
])
def test_unknown_exchange_cannot_expand_cookie_domain_or_path(domain, path, monkeypatch):
    flow, session, calls = memory_login(UNKNOWN_BODIES[0], issue_cookie=False)
    original = session.request_raw

    def request_raw(url, *args, **kwargs):
        raw = original(url, *args, **kwargs)
        if urlsplit(url).path == EXCHANGE_PATH:
            session.jar.set_cookie(cookie(domain=domain, path=path))
        return raw

    monkeypatch.setattr(session, 'request_raw', request_raw)
    with pytest.raises(PanError):
        flow.poll()

    assert flow.subject is None
    assert IDENTITY_PATH not in paths(calls)
    assert_single_exchange(calls)


@pytest.mark.parametrize('code', ['310005', 310005, '400021', -6])
def test_parseable_explicit_exchange_rejection_never_uses_identity_recovery(code):
    flow, session, calls = memory_login(receipt(code=code))

    with pytest.raises(PanError, match='^PAN_QR_EXCHANGE_FAILED$'):
        flow.poll()

    assert pan_baidu._has_bduss(session)
    assert flow.terminal and flow.subject is None
    assert IDENTITY_PATH not in paths(calls)
    with pytest.raises(PanError, match='^PAN_QR_FINISHED$'):
        flow.poll()
    assert_single_exchange(calls)


@pytest.mark.parametrize('value', [
    {}, {'errInfo': None}, {'errInfo': []}, {'errInfo': True},
    {'errInfo': {'no': None}}, {'errInfo': {'no': True}},
    {'errInfo': {'no': 0}}, {'errInfo': {'no': 0}, 'data': []},
    {'errInfo': {'no': 0}, 'data': {'user': []}},
    {'errInfo': {'no': 0}, 'data': {'user': {'userId': False}}},
    {'errInfo': {'no': 0}, 'data': {'user': {'userId': 'not-an-id'}}},
])
def test_parseable_but_invalid_exchange_contract_is_not_an_unknown_body(value):
    flow, session, calls = memory_login(json.dumps(value).encode())

    with pytest.raises(PanError):
        flow.poll()

    assert pan_baidu._has_bduss(session)
    assert flow.terminal and flow.subject is None
    assert IDENTITY_PATH not in paths(calls)
    assert_single_exchange(calls)


def test_unknown_exchange_identity_timeout_retries_only_identity(monkeypatch):
    flow, session, calls = memory_login(UNKNOWN_BODIES[0])
    original, attempts = session.request, []

    def request(url, *args, **kwargs):
        if urlsplit(url).path == IDENTITY_PATH:
            attempts.append(url)
            if len(attempts) == 1:
                raise PanError('PAN_NETWORK_ERROR')
        return original(url, *args, **kwargs)

    monkeypatch.setattr(session, 'request', request)
    with pytest.raises(PanError, match='^PAN_NETWORK_ERROR$'):
        flow.poll()
    assert flow.exchanged and not flow.terminal and flow.phase == 'identity'
    assert flow.subject is None
    state, saved = flow.poll()

    assert state == 'ready' and saved['subject'] == '456'
    assert len(attempts) == 2 and paths(calls).count(IDENTITY_PATH) == 1
    assert_single_exchange(calls)


@pytest.mark.parametrize('expire', [False, True])
@pytest.mark.parametrize('during', ['exchange', 'identity'])
def test_cancel_or_expiry_wins_over_unknown_body_recovery(expire, during, monkeypatch):
    flow, session, calls = memory_login(UNKNOWN_BODIES[0])
    now, probes = [0], []
    flow.clock, flow.started = lambda: now[0], 0
    original = session.request_raw if during == 'exchange' else session.request
    target = EXCHANGE_PATH if during == 'exchange' else IDENTITY_PATH

    def request(url, *args, **kwargs):
        raw = original(url, *args, **kwargs)
        if urlsplit(url).path == target:
            if expire:
                now[0] = 180
            else:
                flow.cancel()
        return raw

    monkeypatch.setattr(session, 'request_raw' if during == 'exchange' else 'request', request)
    monkeypatch.setattr(pan_baidu, '_login_probe', lambda *args: probes.append(args))
    with pytest.raises(PanError, match='^PAN_QR_EXPIRED$' if expire else '^PAN_QR_FINISHED$'):
        flow.poll()

    assert flow.terminal and flow.subject is None and flow.phase == 'closed'
    assert_single_exchange(calls)
    if during == 'exchange':
        assert IDENTITY_PATH not in paths(calls) and not probes


def test_unknown_exchange_still_validates_entire_cookie_export(monkeypatch):
    flow, session, calls = memory_login(UNKNOWN_BODIES[0])
    original = session.request

    def request(url, *args, **kwargs):
        value = original(url, *args, **kwargs)
        if urlsplit(url).path == IDENTITY_PATH:
            session.jar.set_cookie(cookie(name='EXTRA', value='invalid cookie value'))
        return value

    monkeypatch.setattr(session, 'request', request)
    with pytest.raises(PanError, match='^PAN_CREDENTIALS_INVALID$'):
        flow.poll()
    assert paths(calls)[-1] == IDENTITY_PATH
    assert_single_exchange(calls)

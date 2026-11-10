"""Regressions from CE QR acceptance; no account or live provider required."""
import io
import json
import sys
from http.cookiejar import Cookie
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from bobbi_platform import account_dialog, pan_baidu
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_baidu import Login, QR_CALLBACK
from bobbi_platform.pan_http import Session
from test_ce2096_pan_accounts import accounts, service, begin
from test_ce2096_pan_adapters import Transport, png, baidu_saved, baidu_exchange


@pytest.mark.parametrize('early_controls', [True, False])
def test_delayed_oninit_keeps_latest_qr_and_status(monkeypatch, early_controls):
    class Control:
        def setImage(self, value): self.image = value
        def setLabel(self, value, **kwargs): self.label = value
    class Window:
        def __init__(self, *args):
            self.ready = early_controls
            self.controls = {key: Control() for key in (100, 101, 102, 103, 9001)}
        def getControl(self, key):
            if not self.ready: raise RuntimeError('not initialized')
            return self.controls[key]
        def setFocusId(self, value): assert value == 9001
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(getSkinDir=lambda: 'skin.bobbi.cinema'))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(WindowXMLDialog=Window))
    monkeypatch.setitem(sys.modules, 'xbmcaddon', SimpleNamespace(
        Addon=lambda _: SimpleNamespace(getAddonInfo=lambda _: '/fixture')))
    window = account_dialog.create('', '登录 百度网盘', '用百度网盘 App 扫码')
    window.set_image('/fixture/fresh-qr.png')
    window.set_status('请确认')
    window.ready = True
    window.onInit()
    assert window.controls[101].image == '/fixture/fresh-qr.png'
    assert window.controls[103].label == '请确认'
    window.set_image('/fixture/newer-qr.png')
    window.onInit()
    assert window.controls[101].image == '/fixture/newer-qr.png'


@pytest.mark.parametrize('route,ceiling', [('/channel/unicast', 15), ('/v2/api/getqrcode', 8)])
@pytest.mark.parametrize('budget', [None, 3, 24])
def test_baidu_long_poll_ceiling_is_route_scoped_and_budget_bounded(route, ceiling, budget):
    observed = []
    class Reply(io.BytesIO):
        status = 200
        headers = {'Content-Length': '2'}
    def opened(request, timeout):
        observed.append(timeout)
        return Reply(b'{}')
    session = Session('baidu', opener=SimpleNamespace(open=opened), clock=lambda: 100)
    if budget is None:
        session.request('https://passport.baidu.com'+route)
    else:
        with session.budget(budget):
            session.request('https://passport.baidu.com'+route)
    assert observed == [min(ceiling, budget) if budget else ceiling]


@pytest.mark.parametrize('phase', ['confirm', 'exchange', 'identity', 'secret-ticket'])
def test_retry_exposes_only_allowlisted_login_stage(service, phase):
    begin(service)
    service.fixture_flow.phase = phase
    def timeout(): raise PanError('PAN_NETWORK_ERROR')
    service.fixture_flow.poll = timeout
    result = service.dispatch('pan_login_poll', dict(provider='quark', attempt='a'*32))
    assert result.get('phase') == (phase if phase != 'secret-ticket' else None)
    assert 'secret-ticket' not in json.dumps(result)
    assert not service.accounts.snapshot('quark')['authenticated']


def test_baidu_stages_identify_identity_retry_without_replaying_exchange():
    transport = Transport(dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture'),
        png(), PanError('PAN_NETWORK_ERROR'),
        dict(errno=0, channel_v=json.dumps(dict(status=0, v='temporary-ticket'))),
        baidu_exchange(None), PanError('PAN_NETWORK_ERROR'), dict(errno=0, data={'fields': {'uid': 123}}))
    transport.saved = baidu_saved()
    flow = Login(transport)
    flow.begin()
    assert set(transport.calls[0][1]) == {'lp', '_'}
    with pytest.raises(PanError): flow.poll()
    assert flow.phase == 'confirm'
    with pytest.raises(PanError): flow.poll()
    assert flow.phase == 'identity'
    assert flow.poll() == ('ready', baidu_saved())
    assert sum(url.endswith('/qrbdusslogin') for url, _, _ in transport.calls) == 1


@pytest.mark.parametrize('status', [0, 1])
def test_baidu_channel_delivery_without_errno_requires_valid_channel(status):
    transport = Transport(dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture'),
        png(), dict(channel_v=json.dumps(dict(status=status, v='temporary-ticket'))),
        baidu_exchange())
    transport.saved = baidu_saved()
    flow = Login(transport)
    flow.begin()
    assert flow.poll() == (('ready', baidu_saved()) if status == 0 else ('waiting', None))
    assert sum(url.endswith('/qrbdusslogin') for url, _, _ in transport.calls) == (1 if status == 0 else 0)


@pytest.mark.parametrize('reply', [
    {}, dict(errno=None), dict(errno=True), dict(errno='0'), dict(errno=2),
    dict(channel_v='{}'), dict(channel_v='[]'), dict(channel_v='not-json'),
    dict(channel_v=json.dumps(dict(status=True, v='temporary-ticket'))),
    dict(channel_v=json.dumps(dict(status=0))),
    dict(channel_v=json.dumps(dict(status=0, v=''))),
    dict(channel_v=json.dumps(dict(status=2, v='temporary-ticket'))),
])
def test_baidu_missing_errno_does_not_accept_malformed_confirmation(reply):
    transport = Transport(dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture'),
        png(), reply)
    flow = Login(transport)
    flow.begin()
    with pytest.raises(PanError):
        flow.poll()
    assert not any(url.endswith('/qrbdusslogin') for url, _, _ in transport.calls)


def test_baidu_no_errno_confirmation_still_requires_account_identity():
    transport = Transport(dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture'),
        png(), dict(channel_v=json.dumps(dict(status=0, v='temporary-ticket'))),
        baidu_exchange(None), dict(errno=0, data={'fields': {}}))
    transport.saved = baidu_saved()
    flow = Login(transport)
    flow.begin()
    with pytest.raises(PanError, match='PAN_ACCOUNT_ID_INVALID'):
        flow.poll()


def test_baidu_exchange_refreshes_timestamp_after_channel_long_poll():
    transport = Transport(dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture'),
        png(), dict(channel_v=json.dumps(dict(status=0, v='temporary-ticket'))),
        baidu_exchange())
    transport.saved = baidu_saved()
    times = iter([100, 101, 116])
    flow = Login(transport, wallclock=lambda: next(times))
    flow.begin()
    assert flow.poll() == ('ready', baidu_saved())
    assert transport.calls[2][1]['tt'] == '101000'
    exchange = transport.calls[3][1]
    assert exchange['tt'] == exchange['v'] == '116000'
    assert exchange['callback'] == QR_CALLBACK


def test_baidu_completed_exchange_without_cookie_stops_before_identity(caplog):
    caplog.set_level('INFO', logger='bobbi_platform.pan_baidu')
    transport = Transport(dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture'),
        png(), dict(channel_v=json.dumps(dict(status=0, v='temporary-ticket'))),
        baidu_exchange())
    flow = Login(transport)
    flow.begin()
    with pytest.raises(PanError, match='^PAN_QR_EXCHANGE_FAILED$'):
        flow.poll()
    assert flow.terminal and not flow.exchanged and flow.phase == 'exchange'
    assert len(transport.calls) == 4
    assert '"exchange_code": 0' in caplog.text
    assert '"bduss_present": false' in caplog.text
    assert 'temporary-ticket' not in caplog.text
    with pytest.raises(PanError, match='^PAN_QR_FINISHED$'):
        flow.poll()
    assert len(transport.calls) == 4


@pytest.mark.parametrize('expire', [False, True])
@pytest.mark.parametrize('reply', [baidu_exchange(), PanError('PAN_NETWORK_ERROR')])
def test_baidu_late_exchange_stops_before_probe_or_cookie_gate(monkeypatch, expire, reply):
    now, probes = [0], []
    transport = Transport(dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture'),
        png(), dict(channel_v=json.dumps(dict(status=0, v='temporary-ticket'))), reply)
    flow = Login(transport, clock=lambda: now[0])
    original = transport.request

    def request(url, *args, **kwargs):
        try:
            return original(url, *args, **kwargs)
        finally:
            if url.endswith('/qrbdusslogin'):
                if expire:
                    now[0] = 180
                else:
                    flow.cancel()

    transport.request = request
    monkeypatch.setattr(pan_baidu, '_login_probe', lambda *args: probes.append(args))
    flow.begin()
    with pytest.raises(PanError, match='^PAN_QR_EXPIRED$' if expire else '^PAN_QR_FINISHED$'):
        flow.poll()
    assert flow.terminal and not flow.exchanged and flow.phase == 'closed'
    assert not probes and len(transport.calls) == 4


def exchange_body_failure(cookie=None, failure=None, identity=None, repeat_ticket=False):
    """Real Session cookie/export gates; no network or user credentials."""
    calls = []
    session = Session('baidu')

    class Reply(io.BytesIO):
        status = 200

        def __init__(self, raw):
            super().__init__(raw)
            self.headers = {'Content-Length': str(len(raw))}

    class LostBody(Reply):
        def read1(self, size=-1):
            raise failure if failure is not None else OSError('fixture timeout')

    def opened(request, timeout):
        route = urlsplit(request.full_url).path
        calls.append(route)
        if route == '/v2/api/getqrcode':
            result = dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture')
        elif route == '/v2/api/qrcode':
            return Reply(png())
        elif route == '/channel/unicast':
            result = (dict(errno=1) if calls.count(route) > 1 and not repeat_ticket else
                      dict(channel_v=json.dumps(dict(status=0, v='temporary-ticket'))))
        elif route == '/v3/login/main/qrbdusslogin':
            if cookie is not None:
                # HTTPCookieProcessor inserts response cookies before Session
                # reads the body. Reproduce that ordering at the opener seam.
                session.jar.set_cookie(cookie)
            return LostBody(b'body unavailable')
        elif route == '/userx/v1/info/get':
            result = identity if identity is not None else dict(errno=0, data={'fields': {'uid': 123}})
        else:
            raise AssertionError(route)
        return Reply(json.dumps(result).encode('utf-8'))

    session.opener = SimpleNamespace(open=opened)
    flow = Login(session)
    flow.begin()
    return flow, session, calls


def fixture_cookie(value='fixture-' + 'x'*64, domain='.baidu.com', expires=None, name='BDUSS', path='/'):
    return Cookie(0, name, value, None, False, domain, domain.startswith('.'), domain.startswith('.'),
                  path, True, True, expires, expires is None, None, None, {})


def test_baidu_exchange_body_timeout_retries_identity_with_received_cookie():
    flow, session, calls = exchange_body_failure(fixture_cookie())
    with pytest.raises(PanError, match='PAN_NETWORK_ERROR'):
        flow.poll()
    assert flow.exchanged and flow.phase == 'exchange'
    assert flow.poll() == ('ready', baidu_saved())
    assert calls.count('/channel/unicast') == 1
    assert calls.count('/v3/login/main/qrbdusslogin') == 1
    assert calls[-1] == '/userx/v1/info/get'


@pytest.mark.parametrize('cookie', [None, fixture_cookie(value='short'),
    fixture_cookie(domain='passport.baidu.com'), fixture_cookie(domain='.example.test'),
    fixture_cookie(expires=1), fixture_cookie(name='BAIDUID'), fixture_cookie(value='x'*64 + ' bad'),
    fixture_cookie(path='/v3'), fixture_cookie(path='/userx')])
def test_baidu_exchange_timeout_without_usable_identity_cookie_terminates(cookie):
    flow, session, calls = exchange_body_failure(cookie)
    with pytest.raises(PanError, match='PAN_NETWORK_ERROR'):
        flow.poll()
    assert not flow.exchanged and flow.terminal and flow.phase == 'exchange'
    with pytest.raises(PanError, match='PAN_QR_FINISHED'):
        flow.poll()
    assert calls.count('/channel/unicast') == 1
    assert calls.count('/v3/login/main/qrbdusslogin') == 1
    assert '/userx/v1/info/get' not in calls


def test_baidu_exchange_timeout_cannot_consume_a_redelivered_ticket_twice():
    flow, session, calls = exchange_body_failure(repeat_ticket=True)
    with pytest.raises(PanError, match='^PAN_NETWORK_ERROR$'):
        flow.poll()
    with pytest.raises(PanError, match='^PAN_QR_FINISHED$'):
        flow.poll()
    assert calls.count('/channel/unicast') == 1
    assert calls.count('/v3/login/main/qrbdusslogin') == 1
    assert '/userx/v1/info/get' not in calls


def test_baidu_exchange_cookie_scope_uses_actual_drive_route_not_root():
    flow, session, calls = exchange_body_failure(fixture_cookie(path='/api'))
    with pytest.raises(PanError, match='^PAN_NETWORK_ERROR$'):
        flow.poll()
    assert flow.exchanged and not flow.terminal
    # A drive-scoped cookie passes the exchange gate but cannot be widened
    # into a passport-identity credential when the response body was lost.
    assert session.cookie_header('https://mbd.baidu.com/userx/v1/info/get') == ''
    assert calls.count('/v3/login/main/qrbdusslogin') == 1
    assert '/userx/v1/info/get' not in calls


def test_baidu_exchange_nonnetwork_failure_does_not_enter_identity():
    flow, session, calls = exchange_body_failure(fixture_cookie(), failure=PanError('PAN_REPLY_INVALID'))
    with pytest.raises(PanError, match='PAN_REPLY_INVALID'):
        flow.poll()
    assert not flow.exchanged and flow.terminal and flow.phase == 'exchange'
    assert '/userx/v1/info/get' not in calls


@pytest.mark.parametrize('bad_identity', [True, False])
def test_baidu_exchange_timeout_never_bypasses_identity_or_export(bad_identity):
    flow, session, calls = exchange_body_failure(fixture_cookie(),
        identity=dict(errno=0, data={'fields': {}}) if bad_identity else None)
    with pytest.raises(PanError, match='PAN_NETWORK_ERROR'):
        flow.poll()
    if not bad_identity:
        session.jar.set_cookie(fixture_cookie(value='invalid cookie value', name='EXTRA'))
    with pytest.raises(PanError, match='PAN_ACCOUNT_ID_INVALID' if bad_identity else 'PAN_CREDENTIALS_INVALID'):
        flow.poll()
    assert not flow.terminal
    assert calls.count('/channel/unicast') == 1
    assert calls[-1] == '/userx/v1/info/get'

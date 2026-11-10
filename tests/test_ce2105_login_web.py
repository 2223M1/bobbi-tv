"""Authorization is not a membership/drive probe. Synthetic loopback only.

Juku evidence: Quark 00a44620, UC 00a69580, Aliyun 0096c180,
123 009d8940. Bobbi keeps stable subjects, scoped cookies and host CAS.
"""
import base64
import json

import pytest

from bobbi_platform import pan_123, pan_aliyun
from bobbi_platform.pan_accounts import PanAccounts, PanError
from bobbi_platform.pan_http import credentials as cookie_credentials
from bobbi_platform.pan_quark_uc import QuarkLogin, UCLogin
from test_ce2096_pan_tokens import Wire, ali_content, aliyun_token, token_saved
from test_ce2102_juku_login_alignment import wire


def cookies(provider, names=('__uid', '__pus'), domain=None, path='/'):
    values = dict(__uid='fixture-user', __pus='fixture-session')
    return ['%s=%s; Domain=%s; Path=%s; Secure' %
            (name, values[name], domain or '.' + provider + '.cn', path) for name in names]


def cookie_start(wire, provider, issued, extra=(), success=True):
    wire.replies = [(dict(status=2000000, data={'members': {'token': 'fixture-qr'}}), []),
        (dict(status=2000000, data={'members': {'service_ticket': 'fixture-ticket'}}), []),
        (dict(success=success), issued)] + list(extra)
    flow = (QuarkLogin if provider == 'quark' else UCLogin)(wire.session(provider))
    flow.begin()
    return flow


@pytest.mark.parametrize('provider', ['quark', 'uc'])
def test_complete_authorization_does_not_probe_membership_or_directory(wire, provider, caplog):
    flow = cookie_start(wire, provider, cookies(provider))
    state, saved = flow.poll()
    assert state == 'ready' and cookie_credentials(provider, saved)[0] == 'fixture-user'
    assert [call['path'] for call in wire.calls][-1] == '/account/info'
    assert len(wire.calls) == 3 and flow.terminal and flow.token is None
    assert 'fixture-' not in caplog.text


@pytest.mark.parametrize('provider', ['quark', 'uc'])
@pytest.mark.parametrize('member', [dict(code=0, status=200, data={}),
                                  dict(code=403, status=403, data=None)])
def test_member_only_completes_missing_cookies_not_a_membership_gate(wire, provider, member):
    flow = cookie_start(wire, provider, cookies(provider, ('__uid',)),
        [(member, cookies(provider, ('__pus',)))])
    state, saved = flow.poll()
    assert state == 'ready' and len(saved['cookies']) == 2
    assert len(wire.calls) == 4 and wire.calls[-1]['path'] == '/1/clouddrive/member'


@pytest.mark.parametrize('provider', ['quark', 'uc'])
def test_cookie_bootstrap_network_retry_never_reconsumes_service_ticket(wire, provider):
    flow = cookie_start(wire, provider, cookies(provider, ('__uid',)),
        [(None, []), (dict(code=403), cookies(provider, ('__pus',)))])
    with pytest.raises(PanError, match='^PAN_NETWORK_ERROR$'):
        flow.poll()
    assert flow.exchanged and not flow.terminal and flow.phase == 'identity'
    assert flow.poll()[0] == 'ready'
    assert sum(call['path'] == '/account/info' for call in wire.calls) == 1
    assert sum(call['path'].endswith('getServiceTicketByQrcodeToken') for call in wire.calls) == 1


@pytest.mark.parametrize('provider', ['quark', 'uc'])
@pytest.mark.parametrize('action', ['cancel', 'expire'])
def test_late_cookie_bootstrap_does_not_revive_a_closed_attempt(wire, provider, action):
    flow = cookie_start(wire, provider, cookies(provider, ('__uid',)),
        [(dict(code=0, status=200), cookies(provider, ('__pus',)))])
    request = flow.session.request
    def after(url, *args, **kwargs):
        value = request(url, *args, **kwargs)
        if url.endswith('/member'):
            if action == 'cancel':
                flow.cancel()
            else:
                flow.started = flow.clock() - 180
        return value
    flow.session.request = after
    with pytest.raises(PanError, match='PAN_QR_(FINISHED|EXPIRED)'):
        flow.poll()
    assert flow.terminal and len(wire.calls) == 4


@pytest.mark.parametrize('provider', ['quark', 'uc'])
@pytest.mark.parametrize('issue', ['missing-uid', 'missing-session', 'wrong-path', 'web-only-domain'])
def test_member_success_never_substitutes_for_complete_scoped_credentials(wire, provider, issue):
    issued = cookies(provider)
    if issue == 'missing-uid':
        issued = cookies(provider, ('__pus',))
    elif issue == 'missing-session':
        issued = cookies(provider, ('__uid',))
    elif issue == 'wrong-path':
        issued = cookies(provider, path='/account')
    else:
        issued = cookies(provider, domain='pan.quark.cn' if provider == 'quark' else 'drive.uc.cn')
    flow = cookie_start(wire, provider, issued, [(dict(code=0, status=200), [])])
    with pytest.raises(PanError, match='^PAN_CREDENTIALS_INVALID$'):
        flow.poll()
    assert len(wire.calls) == 4


@pytest.mark.parametrize('provider', ['quark', 'uc'])
@pytest.mark.parametrize('success', [False, 1, 'true', None])
def test_official_exchange_success_still_required_even_with_cookies(wire, provider, success):
    flow = cookie_start(wire, provider, cookies(provider), success=success)
    with pytest.raises(PanError, match='^PAN_QR_EXCHANGE_FAILED$'):
        flow.poll()
    assert flow.terminal and len(wire.calls) == 3


def ali_wire(reply):
    ext = base64.b64encode(json.dumps({'pds_login_result': {'refreshToken': 'fixture-initial'}}).encode()).decode()
    return Wire(ali_content(codeContent='https://signin.aliyundrive.com/qr', ck='fixture-ck', t=123),
                ali_content(qrCodeStatus='CONFIRMED', bizExt=ext), reply)


def no_drives():
    return {key: value for key, value in aliyun_token().items() if not key.endswith('_drive_id')}


def test_aliyun_complete_identity_and_tokens_are_saved_without_drive_metadata(tmp_path, caplog):
    transport = ali_wire(no_drives())
    flow = pan_aliyun.Login(transport, wall_clock=lambda: 1000)
    flow.begin()
    state, saved = flow.poll()
    assert state == 'ready' and saved['subject'] == '12345' and saved['drives'] == {}
    assert len(transport.calls) == 3 and flow.pending is None and flow.refresh is None
    accounts = PanAccounts(tmp_path / 'accounts.json', {'aliyun': pan_aliyun.credentials})
    original = accounts.snapshot('aliyun')
    active = accounts.install(saved, original)
    assert accounts.credentials(active) == saved
    with pytest.raises(PanError, match='CHANGED'):
        accounts.install(saved, original)
    assert 'fixture-' not in caplog.text


@pytest.mark.parametrize('field,value', [('user_id', None), ('user_id', True), ('user_id', ''),
    ('access_token', ''), ('refresh_token', ''), ('expires_in', 0), ('expires_in', True)])
def test_aliyun_authorization_still_requires_real_subject_and_complete_tokens(field, value):
    reply = no_drives()
    reply[field] = value
    transport = ali_wire(reply)
    flow = pan_aliyun.Login(transport)
    flow.begin()
    with pytest.raises(PanError):
        flow.poll()
    assert flow.terminal and flow.pending is None and len(transport.calls) == 3


def test_aliyun_drive_discovery_is_lazy_and_does_not_mutate_credential_cas(tmp_path):
    initial = token_saved(drives={})
    accounts = PanAccounts(tmp_path / 'accounts.json', {'aliyun': pan_aliyun.credentials})
    active = accounts.install(initial, accounts.snapshot('aliyun'))
    transport = Wire(dict(user_id='12345', resource_drive_id='100', backup_drive_id='200'), aliyun_token())
    now = [1000]
    client = pan_aliyun.Client(initial, transport, clock=lambda: now[0])
    assert not transport.calls
    assert [row['file_id'] for row in client.list_files()['items']] == ['100:root', '200:root']
    assert client.saved == initial and initial['drives'] == {}
    client.list_files()
    assert len(transport.calls) == 1 and transport.calls[0]['url'] == pan_aliyun.USER_URL
    now[0] = 1990
    client.renew_if_needed(lambda current, previous: accounts.renew(current, active, previous))
    assert accounts.is_current(active) and accounts.credentials(active)['access_token'] == 'fixture-access-new'


@pytest.mark.parametrize('reply', [{'code': 'AccessTokenInvalid'}, {'user_id': 'another', 'default_drive_id': '100'}, {}])
def test_aliyun_browsing_failure_does_not_erase_or_rebind_saved_authorization(reply):
    initial = token_saved(drives={})
    client = pan_aliyun.Client(initial, Wire(reply))
    with pytest.raises(PanError):
        client.list_files()
    assert client.saved == initial and client.drives == {}


@pytest.mark.parametrize('provider', ['quark', 'uc', 'aliyun'])
@pytest.mark.parametrize('action', ['cancel', 'expire'])
def test_completed_exchange_cannot_revive_cancelled_or_expired_login(provider, action):
    now = [0]
    if provider == 'aliyun':
        transport = ali_wire(no_drives())
        flow = pan_aliyun.Login(transport, clock=lambda: now[0])
    else:
        from test_ce2096_pan_adapters import Transport
        from test_ce2096_pan_accounts import saved
        transport = Transport(dict(status=2000000, data={'members': {'token': 'fixture-qr'}}),
            dict(status=2000000, data={'members': {'service_ticket': 'fixture-ticket'}}), dict(success=True))
        transport.saved = saved(provider)
        flow = (QuarkLogin if provider == 'quark' else UCLogin)(transport, clock=lambda: now[0])
    request = transport.request
    def after(url, *args, **kwargs):
        result = request(url, *args, **kwargs)
        if url.endswith('/account/info') or url == pan_aliyun.TOKEN_URL:
            flow.cancel() if action == 'cancel' else now.__setitem__(0, 180)
        return result
    transport.request = after
    flow.begin()
    with pytest.raises(PanError, match='PAN_QR_(FINISHED|EXPIRED)'):
        flow.poll()
    assert flow.terminal and len(transport.calls) == 3
    if provider == 'aliyun':
        assert flow.pending is None and flow.refresh is None


def test_123_token_only_authorization_reads_identity_but_no_drive_or_member():
    # Juku's QR/sign-in response schemas expose token, not a proven UID.
    # Keep the genuine identity read instead of guessing an owner from a JWT.
    transport = Wire(dict(code=0, data=dict(uniID='fixture-qr', url='https://yun.123pan.cn/wx-app-login.html')),
        dict(code=0, data=dict(loginStatus=3, scanPlatform=7, token='fixture-token')),
        PanError('PAN_NETWORK_ERROR'), dict(code=0, data=dict(UID=12345)))
    flow = pan_123.Login(transport)
    flow.begin()
    with pytest.raises(PanError, match='PAN_NETWORK_ERROR'):
        flow.poll()
    state, saved = flow.poll()
    assert state == 'ready' and saved['subject'] == '12345'
    assert len(transport.calls) == 4
    assert [call['url'] for call in transport.calls[2:]] == ['https://api.123pan.cn/b/api/user/info'] * 2

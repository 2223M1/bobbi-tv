"""Authorization is independent of drive capability; synthetic fixtures only."""
from copy import deepcopy

import pytest

from bobbi_platform import pan_device as device, pan_mobile as mobile, pan_tianyi as tianyi
from bobbi_platform.pan_accounts import PanAccounts, PanError
from test_ce2096_pan_tokens import Wire, token_saved
from test_ce2096_pan_mobile import reply, saved as mobile_saved
from test_ce2096_pan_tianyi import login_wire, conf, saved as tianyi_saved
from test_ce2102_juku_baidu_device import device_start, device_token


def login_mobile(**fields):
    wire = Wire(reply(authToken='fixture-token', account='13800000000', **fields))
    flow = mobile.Login(wire, clock=lambda: 0)
    flow.started, flow.key, flow.secret = 0, b'abcdefghijklmnop', 'fixture-secret'
    return flow, wire


def test_mobile_authorization_finishes_before_route_discovery(tmp_path):
    flow, wire = login_mobile(cutoverStatus=1, userDomainId='domain1')
    state, value = flow.poll()
    assert state == 'ready' and value['route'] == '' and value['pds']
    assert value['user_domain_id'] == 'domain1' and len(wire.calls) == 1
    accounts = PanAccounts(tmp_path / 'accounts.json', {'139': mobile.credentials})
    expected = accounts.install(value, accounts.snapshot('139'))
    before = accounts.credentials(expected)
    access = Wire(PanError('PAN_NETWORK_ERROR'))
    with pytest.raises(PanError, match='NETWORK'):
        mobile.Client(before, access).list_files()
    assert access.calls[0]['url'] == mobile.ROUTES
    assert accounts.snapshot('139') == expected and accounts.credentials(expected) == before


@pytest.mark.parametrize('extra', [dict(cutoverStatus=1), dict(cutoverStatus='unexpected'),
    dict(cutoverStatus=1, userDomainId='bad\r\nheader'),
    dict(cutoverStatus=1, routerInfo=[dict(modName='personal', httpsUrl='https://evil.test/hcy')]),
    dict(cutoverStatus=True, routerInfo='malformed')])
def test_mobile_unavailable_drive_hints_do_not_reject_valid_authorization(extra):
    flow, wire = login_mobile(**extra)
    state, value = flow.poll()
    assert state == 'ready' and value['subject'] == '13800000000'
    assert value['route'] == '' and 'user_domain_id' not in value and len(wire.calls) == 1


def test_mobile_discovered_route_in_login_needs_no_extra_request():
    route = mobile_saved()['route']
    flow, wire = login_mobile(routerInfo=[dict(modName='personal', httpsUrl=route)])
    state, value = flow.poll()
    assert state == 'ready' and value['pds'] and value['route'] == route
    assert len(wire.calls) == 1


def test_mobile_lazy_route_is_client_local_and_cached_for_directory_reads():
    flow, _ = login_mobile(cutoverStatus=1, userDomainId='domain1')
    value = flow.poll()[1]
    original = deepcopy(value)
    wire = Wire(reply(routePolicyList=[dict(modName='personal', httpsUrl=mobile_saved()['route'])]),
                reply(items=[], nextPageCursor=''), reply(items=[], nextPageCursor=''))
    client = mobile.Client(value, wire)
    assert client.list_files()['items'] == client.list_files()['items'] == []
    assert [call['url'] for call in wire.calls] == [mobile.ROUTES] + [mobile_saved()['route'] + '/file/list'] * 2
    assert value == original and value['route'] == ''
    assert wire.calls[0]['body'] == dict(userInfo=dict(userDomainId='domain1'), modAddrType=1)


def test_mobile_unknown_personal_route_uses_catalog_on_demand_with_correct_auth():
    flow, wire = login_mobile(cutoverStatus=1)
    account = flow.poll()[1]
    assert len(wire.calls) == 1
    access = Wire(dict(code=0, data=dict(catalogList=[], contentList=[])))
    assert mobile.Client(account, access).list_files()['items'] == []
    assert access.calls[0]['url'].endswith('/getDirectoryCatalog')
    assert access.calls[0]['headers']['Authorization'] == 'fixture-token'
    assert access.calls[0]['headers']['x-account'] == '13800000000'


@pytest.mark.parametrize('pds', [False, True])
def test_mobile_old_saved_schema_still_valid_without_migration(pds):
    old = mobile_saved(pds)
    assert mobile.credentials(old)[1] == old


def test_mobile_route_hint_survives_token_refresh_owner_cas(tmp_path):
    old = dict(mobile_saved(), route='', user_domain_id='domain1', auth_token='a|b|c|1699999990000')
    accounts = PanAccounts(tmp_path / 'accounts.json', {'139': mobile.credentials})
    expected = accounts.install(old, accounts.snapshot('139'))
    client = mobile.Client(old, Wire(b'<root><return>0</return><token>a|b|c|1900000000000</token></root>'),
                           clock=lambda: 1700000000)
    client.renew_if_needed(lambda current, previous: accounts.renew(current, expected, previous=previous))
    assert accounts.credentials(expected)['user_domain_id'] == 'domain1'
    assert accounts.snapshot('139') == expected


def login_device(provider, response, *extra):
    now = [0]
    wire = Wire(device_start(provider), response, *extra)
    flow = device.Login(provider, wire, clock=lambda: now[0], wall_clock=lambda: 1000)
    flow.begin()
    now[0] = 2
    return flow, wire, now


def test_xunlei_token_user_id_finishes_without_any_identity_or_drive_probe():
    flow, wire, _ = login_device('xunlei', device_token(user_id='12345'))
    state, value = flow.poll()
    assert state == 'ready' and value['subject'] == '12345'
    assert len(wire.calls) == 2 and wire.calls[-1]['url'].endswith('/v1/auth/token')
    assert flow.pending is None and flow.terminal


@pytest.mark.parametrize('provider', ['guangya', 'xunlei'])
def test_token_without_stable_subject_only_reads_real_identity(provider):
    flow, wire, now = login_device(provider, device_token(), PanError('PAN_NETWORK_ERROR'), dict(sub='12345'))
    with pytest.raises(PanError, match='NETWORK'):
        flow.poll()
    now[0] = 4
    state, value = flow.poll()
    assert state == 'ready' and value['subject'] == '12345'
    assert [call['url'].rsplit('/', 1)[-1] for call in wire.calls] == ['code', 'token', 'me', 'me']


def test_guangya_unproven_token_field_does_not_replace_authoritative_identity():
    flow, wire, _ = login_device('guangya', device_token(user_id='unproven'), dict(sub='real-subject'))
    assert flow.poll()[1]['subject'] == 'real-subject'
    assert len(wire.calls) == 3


@pytest.mark.parametrize('uid', [True, 123, {}, [], 'bad id', 'bad\r\nheader'])
def test_xunlei_explicit_invalid_token_identity_is_not_saved(uid):
    flow, wire, _ = login_device('xunlei', device_token(user_id=uid))
    with pytest.raises(PanError):
        flow.poll()
    assert len(wire.calls) == 2


@pytest.mark.parametrize('uid', ['', None])
def test_xunlei_missing_token_identity_falls_back_to_real_identity(uid):
    flow, wire, _ = login_device('xunlei', device_token(user_id=uid), dict(sub='12345'))
    assert flow.poll()[1]['subject'] == '12345' and len(wire.calls) == 3


@pytest.mark.parametrize('expire', [False, True])
def test_xunlei_direct_identity_cannot_publish_after_cancel_or_deadline(expire):
    flow, wire, now = login_device('xunlei', device_token(user_id='12345'))
    request = wire.request
    def late(*args, **kwargs):
        result = request(*args, **kwargs)
        now.__setitem__(0, 181) if expire else flow.cancel()
        return result
    wire.request = late
    with pytest.raises(PanError, match='EXPIRED' if expire else 'FINISHED'):
        flow.poll()
    assert flow.pending is None and len(wire.calls) == 2


def test_xunlei_token_refresh_attested_subject_still_uses_owner_cas(tmp_path):
    old = token_saved('xunlei', expires=1001)
    accounts = PanAccounts(tmp_path / 'accounts.json', {'xunlei': lambda value: device.credentials('xunlei', value)})
    expected = accounts.install(old, accounts.snapshot('xunlei'))
    wire = Wire(device_token(user_id='12345'))
    client = device.RenewableClient('xunlei', old, wire, clock=lambda: 1000)
    client.renew_if_needed(lambda current, previous: accounts.renew(current, expected, previous=previous))
    assert len(wire.calls) == 1 and accounts.snapshot('xunlei') == expected
    assert accounts.credentials(expected) == client.saved


def test_xunlei_token_refresh_changed_subject_never_calls_owner():
    old = token_saved('xunlei', expires=1001)
    wire = Wire(device_token(user_id='another-user'))
    client = device.RenewableClient('xunlei', old, wire, clock=lambda: 1000)
    with pytest.raises(PanError, match='IDENTITY_CHANGED'):
        client.renew_if_needed(lambda *a: pytest.fail('Foreign account published'))
    assert len(wire.calls) == 1 and client.saved == old


def test_tianyi_session_key_without_subject_keeps_only_necessary_identity_read():
    wire = login_wire(dict(status=0, redirectUrl=conf()['returnUrl']), (b'', 200, None),
        dict(res_code=0, sessionKey='fixture-session'), PanError('PAN_NETWORK_ERROR'),
        dict(res_code=0, loginName='13800000000'))
    wire.export = lambda **kw: tianyi_saved()
    flow = tianyi.Login(wire)
    flow.begin()
    with pytest.raises(PanError, match='NETWORK'):
        flow.poll()
    assert flow.poll() == ('ready', tianyi_saved())
    urls = [call['url'] for call in wire.calls]
    assert sum(url.endswith('/qrcodeLoginState.do') for url in urls) == 1
    assert sum(url.endswith('/callbackUnify.action') for url in urls) == 1
    assert sum(url.endswith('/getUserBriefInfo.action') for url in urls) == 1
    assert sum(url.endswith('/getUserInfoForPortal.action') for url in urls) == 2
    assert not any('/file/' in url or '/member' in url for url in urls)

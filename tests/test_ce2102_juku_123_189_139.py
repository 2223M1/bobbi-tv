"""Juku 0.81 protocol comparisons, synthetic fixtures only; no live accounts."""
import base64
from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_platform import pan_123 as c123, pan_mobile as mobile, pan_tianyi as tianyi
from bobbi_platform.pan_accounts import PanError
from test_ce2096_pan_tokens import Wire, c123_row, token_saved
from test_ce2096_pan_mobile import saved as mobile_saved, reply
from test_ce2096_pan_tianyi import saved as tianyi_saved, conf, login_wire


def qr123():
    return dict(code=0, data=dict(uniID='fixture-qr', url='https://yun.123pan.cn/wx-app-login.html'))


def test_123_qr_has_complete_web_parameters_and_no_preflight():
    wire = Wire(qr123())
    flow = c123.Login(wire)
    assert parse_qs(urlsplit(flow.begin()).query) == dict(env=['production'], uniID=['fixture-qr'],
                                                        source=['123pan'], type=['login'])
    assert len(wire.calls) == 1 and wire.calls[0]['query'] is None
    assert wire.calls[0]['headers']['app-version'] == '3'


@pytest.mark.parametrize('outer,status,platform', [(0, 3, 4), (200, None, 4), (200, None, 0)])
def test_123_confirmation_exchanges_only_at_login_origin(outer, status, platform):
    value = dict(loginStatus=status, **({'scanPlatform': platform} if outer == 0 else {'login_type': platform}))
    wire = Wire(qr123(), dict(code=outer, data=value), dict(code=0, data=dict(wxCode='fixture-wx')),
                dict(code=0, data=dict(token='fixture-token')), dict(code=0, data=dict(UID=12345)))
    flow = c123.Login(wire)
    flow.begin()
    assert flow.poll()[0] == 'ready'
    assert wire.calls[1]['query'] == {'uniID': 'fixture-qr'}
    exchange = wire.calls[3]
    assert exchange['url'] == c123.SIGN_IN + '/api/user/sign_in'
    assert exchange['body'] == {'from': 'web', 'wechat_code': 'fixture-wx', 'type': 4}
    assert exchange['headers']['app-version'] == '43'
    assert exchange['headers']['Origin'] == c123.SIGN_IN


@pytest.mark.parametrize('outer', [0, 200])
def test_123_platform_seven_uses_token_but_still_checks_identity(outer):
    value = dict(loginStatus=3, scanPlatform=7, login_type=7, token='fixture-token')
    wire = Wire(qr123(), dict(code=outer, data=value), dict(code=0, data=dict(UID=12345)))
    flow = c123.Login(wire)
    flow.begin()
    assert flow.poll()[1]['subject'] == '12345'
    assert len(wire.calls) == 3 and wire.calls[-1]['url'].endswith('/b/api/user/info')


@pytest.mark.parametrize('value', [dict(loginStatus=2), dict(loginStatus=4),
    dict(loginStatus=3, scanPlatform=999), dict(loginStatus=True), dict(loginStatus=3, scanPlatform=7, token='')])
def test_123_rejected_qr_never_becomes_an_account(value):
    wire = Wire(qr123(), dict(code=0, data=value))
    flow = c123.Login(wire)
    flow.begin()
    with pytest.raises(PanError):
        flow.poll()
    assert len(wire.calls) == 2


def test_123_exchange_failure_does_not_replay_one_use_code():
    wire = Wire(qr123(), dict(code=0, data=dict(loginStatus=3, scanPlatform=4)),
                dict(code=0, data=dict(wxCode='fixture-code')), PanError('PAN_NETWORK_ERROR'))
    flow = c123.Login(wire)
    flow.begin()
    with pytest.raises(PanError, match='NETWORK'):
        flow.poll()
    with pytest.raises(PanError, match='FINISHED'):
        flow.poll()
    assert len(wire.calls) == 4


class AfterWire(Wire):
    after = None

    def request(self, *args, **kwargs):
        value = super().request(*args, **kwargs)
        if self.after:
            self.after(len(self.calls))
        return value

    request_raw = request


@pytest.mark.parametrize('step', [1, 2, 3, 4, 5])
@pytest.mark.parametrize('cancel', [False, True])
def test_123_late_response_cannot_cross_deadline_or_revive_cancelled_attempt(step, cancel):
    now = [0]
    wire = AfterWire(qr123(), dict(code=0, data=dict(loginStatus=3, scanPlatform=4)),
                    dict(code=0, data=dict(wxCode='fixture-code')),
                    dict(code=0, data=dict(token='fixture-token')), dict(code=0, data=dict(UID=12345)))
    flow = c123.Login(wire, clock=lambda: now[0])
    def after(n):
        if n == step:
            flow.cancel() if cancel else now.__setitem__(0, 120)
    wire.after = after
    with pytest.raises(PanError, match='FINISHED' if cancel else 'EXPIRED'):
        flow.begin()
        flow.poll()
    assert len(wire.calls) == step and flow.terminal and flow.access is None


def test_123_listing_uses_current_web_domain_and_keeps_exact_file_guard():
    wire = Wire(dict(code=0, data=dict(InfoList=[c123_row()], Total=1)))
    c123.Client(token_saved('123'), wire).list_files()
    assert wire.calls[0]['url'] == 'https://yun.123pan.com/b/api/file/list/new'
    assert wire.calls[0]['query']['orderBy'] == 'update_time'


def test_123_optional_count_storage_and_category_directory():
    row = c123_row()
    del row['S3KeyFlag']
    wire = Wire(dict(code=200, data=dict(InfoList=[row])),
                dict(code=0, data=dict(InfoList=[dict(FileId=8, FileName='Folder', Category=1)])))
    client = c123.Client(token_saved('123'), wire)
    result = client.list_files(size=1)
    assert result['has_more'] and result['items'][0]['storage_key'] == ''
    assert client.list_files(page=2, size=1)['items'][0]['directory'] is True


@pytest.mark.parametrize('bad', [None, False, -1, '1'])
def test_123_explicit_invalid_count_not_treated_as_missing(bad):
    client = c123.Client(token_saved('123'), Wire(dict(code=0, data=dict(InfoList=[], Total=bad))))
    with pytest.raises(PanError):
        client.list_files()


def mobile_login(*responses):
    wire = Wire(*responses)
    flow = mobile.Login(wire, clock=lambda: 0)
    flow.started, flow.key, flow.secret = 0, b'abcdefghijklmnop', 'fixture-secret'
    return flow, wire


@pytest.mark.parametrize('identity', [dict(account='13800000000'), dict(userPhone='+8613800000000'),
    dict(msisdn='8613800000000'), dict(encryptAccount=base64.b64encode(b'+8613800000000').decode())])
def test_mobile_minimal_qr_response_does_not_require_unrelated_route_fields(identity):
    flow, wire = mobile_login(reply(authToken='one|two|three|1900000000000', **identity))
    state, account = flow.poll()
    assert state == 'ready' and account['subject'] == '13800000000'
    assert account['pds'] is False and account['route'] == '' and len(wire.calls) == 1


@pytest.mark.parametrize('identity', [dict(account='13800000000', msisdn='13900000000'),
    dict(account='masked'), dict(account='13800000000', encryptAccount=base64.b64encode(b'13900000000').decode()),
    dict(account='13800000000', encryptAccount='invalid@@')])
def test_mobile_ambiguous_identity_is_not_saved(identity):
    flow, wire = mobile_login(reply(authToken='fixture-token', **identity))
    with pytest.raises(PanError):
        flow.poll()
    assert len(wire.calls) == 1


def test_mobile_encrypted_poll_string_fields_and_public_device_profile():
    AES = pytest.importorskip('Crypto.Cipher.AES')
    padding = pytest.importorskip('Crypto.Util.Padding')
    flow, wire = mobile_login(reply('200059548'))
    assert flow.poll() == ('waiting', None) and flow.phase == 'confirm'
    call = wire.calls[0]
    plaintext = padding.unpad(AES.new(flow.key, AES.MODE_ECB).decrypt(base64.b64decode(call['body']['encryptMsg'])), 16)
    assert json.loads(plaintext) == dict(dycPwd=flow.sid, loginStyle='QRCode', clientEnv='3', setCookie='0')
    assert call['headers']['X-Deviceinfo'] == '||3|12.27.0|chrome|131.0.0.0|' + flow.device + '||windows 10|1920X919|zh-CN|||'


@pytest.mark.parametrize('cancel', [False, True])
def test_mobile_late_login_does_not_publish_or_lookup_routes(cancel):
    now = [0]
    wire = AfterWire(reply(account='13800000000', authToken='fixture-token', cutoverStatus=1, userDomainId='uid1'))
    flow = mobile.Login(wire, clock=lambda: now[0])
    flow.started, flow.key, flow.secret = 0, b'abcdefghijklmnop', 'fixture-secret'
    wire.after = lambda _: flow.cancel() if cancel else now.__setitem__(0, 180)
    with pytest.raises(PanError, match='FINISHED' if cancel else 'EXPIRED'):
        flow.poll()
    assert len(wire.calls) == 1 and flow.accepted is None and flow.key is None


def test_mobile_signature_query_escape_vector(monkeypatch):
    monkeypatch.setattr(mobile, 'random_text', lambda n: 'A' * n)
    h = mobile.headers({'name': "a b!*~'()"}, 'test-device', wall_clock=lambda: 0)
    assert h['mcloud-sign'] == '19700101080000000,' + 'A' * 16 + ',A3C7B934836076234F96CD7D7B5D7B2E'


@pytest.mark.parametrize('value', [dict(code='1010010005'), dict(code='1010010005', data=None), dict(code=401)])
def test_mobile_expired_top_level_without_data_is_login_required(value):
    with pytest.raises(PanError, match='LOGIN_REQUIRED'):
        mobile.checked(value)


def test_mobile_catalog_uses_raw_auth_and_precise_route_with_bounded_pagination():
    item = dict(contentId='file1', contentName='film.mkv', contentSize=100)
    wire = Wire(dict(code=0, data=dict(catalogList=[], contentList=[item])),
                dict(code=0, data=dict(catalogList=[], contentList=[])))
    client = mobile.Client(mobile_saved(False), wire)
    page = client.list_files(size=1)
    assert page['has_more'] and page['items'][0]['modified'] == ''
    assert client.list_files(page=2, size=1)['has_more'] is False
    assert wire.calls[0]['url'].endswith('/getDirectoryCatalog')
    assert wire.calls[0]['body']['catalogId'] == mobile.CATALOG_ROOT
    assert wire.calls[0]['body']['sortDirection'] == 0 and wire.calls[0]['body']['catalogSortType'] == 1
    assert wire.calls[0]['headers']['Authorization'] == 'fixture-auth'
    assert wire.calls[0]['headers']['x-account'] == '13800000000'


def refreshing(wire):
    old = dict(mobile_saved(), auth_token='a|b|c|1699999990000')
    return mobile.Client(old, wire, clock=lambda: 1700000000), old


def test_mobile_timestamp_token_refresh_uses_existing_owner_before_publish():
    wire = Wire(b'<root><return>0</return><desc>ok</desc><token>a|b|c|1900000000000</token><account>13800000000</account></root>')
    client, old = refreshing(wire)
    published = []
    client.renew_if_needed(lambda current, previous: published.append((deepcopy(current), deepcopy(previous))))
    assert published[0][1] == old and client.saved == published[0][0]
    call = wire.calls[0]
    assert call['url'] == mobile.REFRESH and call['body'] is None
    assert b'<account>13800000000</account>' in call['xml_body']
    assert b'<clienttype>656</clienttype>' in call['xml_body']
    assert client.saved['auth_token'] == 'a|b|c|1900000000000'
    client.renew_if_needed(lambda *a: pytest.fail('Unnecessary renewal'))
    assert len(wire.calls) == 1


@pytest.mark.parametrize('raw', [
    b'<!DOCTYPE root [<!ENTITY e "secret">]><root><return>0</return><token>&e;</token></root>',
    b'<root><return>0</return><return>0</return><token>fresh</token></root>',
    b'<root><return>0</return><token><nested>fresh</nested></token></root>',
    b'<root><return>0</return><token>fresh</token><account>13900000000</account></root>',
    b'<root><return>0</return><token>a|b|c|1600000000000</token></root>',
    b'<root><return>0</return><token>bad token</token></root>',
    b'<root><return>5</return><token>fresh</token></root>', b'not xml',
])
def test_mobile_invalid_refresh_never_publishes(raw):
    client, old = refreshing(Wire(raw))
    with pytest.raises(PanError):
        client.renew_if_needed(lambda *a: pytest.fail('Invalid refresh published'))
    assert client.saved == old


def test_mobile_refresh_cas_failure_and_network_failure_never_replay():
    for response in (PanError('PAN_NETWORK_ERROR'), b'<root><return>0</return><token>fresh</token></root>'):
        client, old = refreshing(Wire(response))
        def publish(*args):
            raise PanError('PAN_ACCOUNT_CHANGED')
        with pytest.raises(PanError):
            client.renew_if_needed(publish)
        with pytest.raises(PanError):
            client.renew_if_needed(publish)
        assert client.saved == old and len(client.session.calls) == 1


def tianyi_page():
    return dict(res_code=0, fileListAO=dict(count=1, folderList=[], fileList=[
        dict(id=1, name='movie.mkv', size=100, lastOpTime='2026-11-09 10:00:00')]))


def test_tianyi_date_and_confirmation_context_preserve_authoritative_config(monkeypatch):
    monkeypatch.setattr(tianyi.secrets, 'randbelow', lambda _: 17)
    wire = login_wire(dict(status=-11002), dict(status=-106))
    flow = tianyi.Login(wire, clock=lambda: 0, wall_clock=lambda: 0)
    flow.begin()
    assert flow.poll() == ('waiting', None) and flow.phase == 'confirm'
    assert flow.poll() == ('waiting', None) and flow.phase == 'confirm'
    call = wire.calls[5]
    assert call['form']['date'] == '1970-01-0108:00:0017'
    assert call['form']['timeStamp'] == 1000 and call['form']['cb_SaveName'] == '0'
    assert call['form']['isOauth2'] == 'true' and call['form']['state'] == 'fixture-state'
    assert call['headers']['Referer'] == 'https://open.e.189.cn/api/logbox/separate/web/index.html'


def test_tianyi_original_info_fallback_and_native_root_header():
    wire = Wire(tianyi_page(), tianyi_page(), dict(res_code=0),
                dict(res_code=0, downloadUrl='https://download.cloud.189.cn/file'))
    client = tianyi.Client(tianyi_saved(), wire)
    assert client.resolve_original(client.list_files()['items'][0])['original']
    assert wire.calls[0]['query']['folderId'] == '-11' and wire.calls[0]['query']['iconOption'] == 5
    assert 'sessionKey' not in wire.calls[0]['query'] and wire.calls[0]['headers']['sessionKey'] == 'fixture-session'
    assert wire.calls[2]['url'].endswith('/getFileInfo.action')
    assert wire.calls[3]['query']['dt'] == '1'


def test_tianyi_optional_count_mtime_and_string_zero_code():
    page = dict(res_code='0', fileListAO=dict(folderList=[dict(id=1, name='Folder')], fileList=[]))
    client = tianyi.Client(tianyi_saved(), Wire(page))
    result = client.list_files(size=1)
    assert result['has_more'] and result['items'][0]['modified'] == ''


@pytest.mark.parametrize('bad', [None, False, -1, '1'])
def test_tianyi_explicit_invalid_count_not_treated_as_missing(bad):
    page = dict(res_code=0, fileListAO=dict(folderList=[], fileList=[], count=bad))
    with pytest.raises(PanError):
        tianyi.Client(tianyi_saved(), Wire(page)).list_files()


def test_tianyi_foreign_download_info_never_falls_back():
    wire = Wire(tianyi_page(), tianyi_page(), dict(res_code=0, fileDownloadUrl='https://evil.test/file'))
    client = tianyi.Client(tianyi_saved(), wire)
    with pytest.raises(PanError, match='DOWNLOAD_ORIGIN'):
        client.resolve_original(client.list_files()['items'][0])
    assert len(wire.calls) == 3


def test_tianyi_ambiguous_callback_failure_never_replays_one_use_ticket():
    wire = login_wire(dict(status=0, redirectUrl=conf()['returnUrl']), PanError('PAN_NETWORK_ERROR'))
    flow = tianyi.Login(wire)
    flow.begin()
    with pytest.raises(PanError, match='NETWORK'):
        flow.poll()
    with pytest.raises(PanError, match='FINISHED'):
        flow.poll()
    assert sum(c['url'].endswith('/callbackUnify.action') for c in wire.calls) == 1


@pytest.mark.parametrize('step', range(1, 10))
@pytest.mark.parametrize('cancel', [False, True])
def test_tianyi_late_response_cannot_continue_after_cancel_or_deadline(step, cancel):
    now = [0]
    wire = AfterWire(*login_wire(dict(status=0, redirectUrl=conf()['returnUrl']), (b'', 200, None),
        dict(res_code=0, sessionKey='fixture-session'), dict(res_code=0, loginName='13800000000')).responses)
    wire.export = lambda **kw: pytest.fail('Cancelled account must not be exported')
    flow = tianyi.Login(wire, clock=lambda: now[0])
    def after(n):
        if n == step:
            flow.cancel() if cancel else now.__setitem__(0, 180)
    wire.after = after
    with pytest.raises(PanError, match='FINISHED' if cancel else 'EXPIRED'):
        flow.begin()
        flow.poll()
    assert len(wire.calls) == step and flow.terminal and flow.config is None

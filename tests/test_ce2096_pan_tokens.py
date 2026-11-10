"""Offline contracts only. Do not present fixtures as account/device validation."""
import base64
from copy import deepcopy
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_platform.pan_accounts import PanAccounts, PanError
from bobbi_platform.pan_http import Session
from bobbi_platform import pan_123, pan_aliyun, pan_device, pan_guangya
from bobbi_platform.pan_service import PanService
from test_ce2096_pan_accounts import saved as cookie_saved


class Wire:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def request(self, url, query=None, body=None, **options):
        self.calls.append(dict(url=url, query=query, body=body, **options))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)

    request_raw = request


def token_saved(provider='aliyun', expires=2000, **kw):
    value = dict(provider=provider, subject='12345', access_token='fixture-access',
                 device_id='fixture-device')
    if provider != '123':
        value.update(refresh_token='fixture-refresh', expires_at=expires)
    if provider == 'aliyun':
        value['drives'] = {'default': '100', 'resource': '100', 'backup': '200'}
    value.update(kw)
    return value


def aliyun_token(**kw):
    return dict(user_id='12345', access_token='fixture-access-new', refresh_token='fixture-refresh-new',
                expires_in=3600, default_drive_id='100', resource_drive_id='100', backup_drive_id='200', **kw)


def ali_row(**kw):
    value = dict(file_id='file1', drive_id='100', name='Episode.mkv', type='file', size=1234, content_hash='a'*40)
    value.update(kw)
    return value


def ali_content(**kw):
    return {'content': {'success': True, 'data': kw}}


@pytest.mark.parametrize('provider,validator', [('aliyun', pan_aliyun.credentials), ('123', pan_123.credentials),
    ('guangya', lambda c: pan_device.credentials('guangya', c)),
    ('xunlei', lambda c: pan_device.credentials('xunlei', c))])
def test_token_credentials_persistent_independent_and_redacted(tmp_path, provider, validator):
    accounts = PanAccounts(tmp_path/'accounts.json', {provider: validator})
    expected = accounts.install(token_saved(provider), accounts.snapshot(provider))
    loaded = PanAccounts(accounts.path, accounts.validators)
    assert loaded.snapshot(provider) == expected
    assert loaded.credentials(expected) == token_saved(provider)
    assert 'fixture-access' not in json.dumps(expected)
    with pytest.raises(PanError):
        validator(dict(token_saved(provider), access_token='secret\r\nX: secret'))
    with pytest.raises(PanError):
        validator(dict(token_saved(provider), subject=''))
    with pytest.raises(PanError):
        validator(dict(token_saved(provider), provider='quark'))


def test_aliyun_qr_form_isolation_exchange_and_identity():
    ext = base64.b64encode(json.dumps({'pds_login_result': {'refreshToken': 'fixture-initial'},
        'unrelated': '名字'}, ensure_ascii=False).encode('gb18030')).decode()
    wire = Wire(ali_content(codeContent='https://signin.aliyundrive.com/qr?fixture=1', ck='fixture-ck', t=123),
        ali_content(qrCodeStatus='NEW'), ali_content(qrCodeStatus='CONFIRMED', bizExt=ext), aliyun_token(),
        dict(default_drive_id='100', resource_drive_id='100', backup_drive_id='200'))
    login = pan_aliyun.Login(wire, clock=lambda: 1, wall_clock=lambda: 1000)
    assert login.begin().startswith('https://signin.aliyundrive.com/')
    assert login.poll() == ('waiting', None)
    state, value = login.poll()
    assert state == 'ready' and value['subject'] == '12345' and value['expires_at'] == 4600
    assert wire.calls[1]['form']['ck'] == 'fixture-ck'
    assert wire.calls[-1]['body']['refresh_token'] == 'fixture-initial'
    assert wire.calls[-1]['url'] == 'https://auth.aliyundrive.com/v2/account/token'
    assert len(wire.calls) == 4
    assert 'fixture' not in repr(login)
    with pytest.raises(PanError, match='FINISHED'):
        login.poll()


@pytest.mark.parametrize('status', ['EXPIRED', 'CANCELED', 'UNKNOWN', True, None])
def test_aliyun_qr_errors_are_not_pending(status):
    wire = Wire(ali_content(codeContent='https://signin.aliyundrive.com/qr', ck='fixture-ck', t=123),
                ali_content(qrCodeStatus=status))
    login = pan_aliyun.Login(wire)
    login.begin()
    with pytest.raises(PanError):
        login.poll()


def test_aliyun_root_cursors_and_exact_original_not_preview():
    wire = Wire(dict(items=[ali_row()], next_marker='marker1'), dict(items=[], next_marker=''),
        ali_row(), dict(url='https://cn-beijing-data.aliyundrive.com/original', size=1234))
    client = pan_aliyun.Client(token_saved(), session=wire)
    assert [r['file_id'] for r in client.list_files()['items']] == ['100:root', '200:root']
    selected = client.list_files('100:root')['items'][0]
    assert client.list_files('100:root', page=2, cursor='marker1')['has_more'] is False
    assert wire.calls[1]['body']['marker'] == 'marker1'
    assert client.resolve_original(selected)['original'] is True
    assert all('preview' not in r['url'] for r in wire.calls)
    with pytest.raises(PanError):
        client.list_files('100:root', page=2)
    with pytest.raises(PanError):
        client.list_files('foreign:root')


@pytest.mark.parametrize('change', [{'size': 55}, {'name': 'Other.mkv'}, {'content_hash': 'b'*40},
    {'file_id': 'other'}, {'drive_id': '200'}, {'size': True}])
def test_aliyun_original_rejects_changed_file(change):
    client = pan_aliyun.Client(token_saved(), session=Wire(dict(items=[ali_row()], next_marker=''), ali_row(**change)))
    with pytest.raises(PanError):
        client.resolve_original(client.list_files('100:root')['items'][0])


def test_refresh_compare_and_swap_and_account_switch(tmp_path):
    accounts = PanAccounts(tmp_path/'accounts.json', {'aliyun': pan_aliyun.credentials})
    expected = accounts.install(token_saved(expires=1010), accounts.snapshot('aliyun'))
    old = accounts.credentials(expected)
    client = pan_aliyun.Client(old, session=Wire(aliyun_token()), clock=lambda: 1000)
    client.renew_if_needed(lambda current, previous: accounts.renew(current, expected, previous=previous))
    assert accounts.snapshot('aliyun') == expected
    assert accounts.credentials(expected)['refresh_token'] == 'fixture-refresh-new'
    with pytest.raises(PanError, match='CREDENTIALS_CHANGED'):
        accounts.renew(token_saved(expires=7000), expected, previous=old)
    accounts.logout(expected)
    with pytest.raises(PanError, match='ACCOUNT_CHANGED'):
        accounts.renew(token_saved(), expected, previous=client.saved)


def test_aliyun_refresh_user_change_never_published():
    response = aliyun_token()
    response['user_id'] = 'other-user'
    client = pan_aliyun.Client(token_saved(expires=1001), session=Wire(response), clock=lambda: 1000)
    with pytest.raises(PanError, match='IDENTITY_CHANGED'):
        client.renew_if_needed(lambda *a: pytest.fail('Must not publish'))


def c123_row(**kw):
    result = dict(FileId=7, FileName='Episode.mkv', Size=1234, Type=0, Etag='a'*32, S3KeyFlag='fixture-node')
    result.update(kw)
    return result


def test_123_qr_and_identity_read_retry_does_not_reconsume_login_code():
    wire = Wire(dict(code=0, data=dict(uniID='fixture-qr', url='https://yun.123pan.cn/wx-app-login.html')),
        dict(code=0, data=dict(loginStatus=1)), dict(code=0, data=dict(loginStatus=3, scanPlatform=4)),
        dict(code=0, data=dict(wxCode='fixture-wx')), dict(code=0, data=dict(token='fixture-access')),
        PanError('PAN_NETWORK_ERROR'), dict(code=0, data=dict(UID=12345)))
    login = pan_123.Login(wire)
    assert parse_qs(urlsplit(login.begin()).query)['env'] == ['production']
    assert login.poll() == ('waiting', None)
    with pytest.raises(PanError, match='NETWORK'):
        login.poll()
    state, value = login.poll()
    assert state == 'ready' and value['subject'] == '12345'
    assert sum(r['url'].endswith('/sign_in') for r in wire.calls) == 1


@pytest.mark.parametrize('url', ['https://evil.test/qr', 'http://yun.123pan.cn/wx-app-login.html',
    'https://yun.123pan.cn/wx-app-login.html?redirect=evil'])
def test_123_untrusted_qr_rejected(url):
    login = pan_123.Login(Wire(dict(code=0, data=dict(uniID='fixture-qr', url=url))))
    with pytest.raises(PanError):
        login.begin()


def test_123_original_rechecks_same_page_and_version():
    listing = dict(code=0, data=dict(InfoList=[c123_row()], Total=1))
    wire = Wire(listing, listing, dict(code=0, data=dict(DownloadUrl='https://download.123pan.cn/file')))
    client = pan_123.Client(token_saved('123'), session=wire)
    selected = client.list_files()['items'][0]
    result = client.resolve_original(selected)
    assert result['original'] and 'Authorization' not in result['headers']
    assert wire.calls[-1]['body']['etag'] == 'a'*32
    assert wire.calls[-1]['headers']['platform'] == 'web'


@pytest.mark.parametrize('change', [{'Etag': 'b'*32}, {'Size': 55}, {'FileId': 8}, {'Type': 1}])
def test_123_changed_file_rejected(change):
    wire = Wire(dict(code=0, data=dict(InfoList=[c123_row()], Total=1)),
                dict(code=0, data=dict(InfoList=[c123_row(**change)], Total=1)))
    client = pan_123.Client(token_saved('123'), session=wire)
    with pytest.raises(PanError):
        client.resolve_original(client.list_files()['items'][0])


@pytest.mark.parametrize('provider,qr', [('guangya', 'https://account.guangyapan.com/qr?code=fixture'),
    ('xunlei', 'https://i.xunlei.com/center/account/personal/qrcode-login/?user_code=fixture')])
def test_device_oauth_pending_slowdown_rotation_identity(provider, qr):
    now = [1]
    wire = Wire(dict(device_code='fixture-code', expires_in=120, interval=5, verification_uri_complete=qr),
        dict(error='authorization_pending'), dict(error='slow_down'),
        dict(access_token='fixture-access', refresh_token='fixture-refresh', expires_in=3600, token_type='Bearer'),
        dict(sub='12345'))
    flow = pan_device.Login(provider, wire, clock=lambda: now[0], wall_clock=lambda: 1000)
    assert flow.begin() == qr
    assert flow.poll() == ('waiting', None) and len(wire.calls) == 1
    now[0] += 5
    assert flow.poll() == ('waiting', None)
    now[0] += 5
    assert flow.poll() == ('waiting', None)
    now[0] += 9
    assert flow.poll() == ('waiting', None) and len(wire.calls) == 3
    now[0] += 1
    state, value = flow.poll()
    assert state == 'ready' and value['provider'] == provider and value['subject'] == '12345'
    assert flow.pending is None and flow.code is None
    assert 'fixture-access' not in repr(flow)


@pytest.mark.parametrize('response', [PanError('PAN_NETWORK_ERROR'), dict(error='invalid_client'),
    dict(device_code='fixture', expires_in=180, verification_uri_complete='https://evil.test/qr')])
def test_device_auth_never_falls_back_to_juku_mock(response):
    flow = pan_device.Login('guangya', Wire(response))
    with pytest.raises(PanError):
        flow.begin()
    assert flow.code is None


def test_guangya_root_pagination_and_original_metadata():
    row = dict(fileId='file1', fileName='Episode.mkv', fileSize=1234, resType=1, utime=100)
    listing = dict(code=0, data=dict(list=[row], total=1))
    wire = Wire(listing, listing, dict(code=0, data=dict(signedURL='https://cdn.guangyapan.com/file')))
    client = pan_guangya.Client(token_saved('guangya'), session=wire)
    selection = client.list_files()['items'][0]
    assert wire.calls[0]['body']['parentId'] == '' and wire.calls[0]['body']['page'] == 0
    assert client.resolve_original(selection)['original']
    assert all('delete' not in r['url'] and 'transfer' not in r['url'] for r in wire.calls)


def test_bounded_directory_cache_refresh_and_account_guard(tmp_path):
    calls = []
    now = [1]
    service = PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}), clock=lambda: now[0])
    expected = service.accounts.install(cookie_saved(), service.accounts.snapshot('quark'))
    def listing(*a, **kw):
        calls.append(1)
        return dict(items=[], has_more=False, page=1)
    service.client_factory = lambda *a: SimpleNamespace(list_files=listing)
    first = service.list_files(expected, '0', 1)
    first['items'].append('tampered')
    assert service.list_files(expected, '0', 1)['items'] == [] and len(calls) == 1
    service.list_files(expected, '0', 1, refresh=True)
    assert len(calls) == 2
    now[0] += 21
    service.list_files(expected, '0', 1)
    assert len(calls) == 3
    for n in range(80):
        service.list_files(expected, str(n), 1)
    assert len(service.directory_cache) == 64
    service.accounts.logout(expected)
    with pytest.raises(PanError, match='ACCOUNT_CHANGED'):
        service.list_files(expected, '79', 1)
    service.close()
    assert not service.directory_cache


def test_token_http_rejects_foreign_origin_and_header_injection():
    session = Session('aliyun', opener=SimpleNamespace(open=lambda *a, **kw: pytest.fail('No IO')))
    with pytest.raises(PanError, match='ORIGIN'):
        session.request('https://api.alipan.com.evil.test/v2/user/get', body={}, headers={'Authorization': 'Bearer fixture'})
    with pytest.raises(PanError, match='ORIGIN'):
        session.request('https://auth.alipan.com/v2/account/token', body={}, headers={'Authorization': 'Bearer fixture'})
    with pytest.raises(PanError, match='HEADERS'):
        session.request('https://api.alipan.com/v2/user/get', body={}, headers={'Authorization': 'Bearer fixture\r\nCookie:secret'})


def test_oauth_http_400_is_bounded_json_only_on_token_route():
    def failed(request, **kw):
        raise HTTPError(request.full_url, 400, 'private text', {}, io.BytesIO(b'{"error":"authorization_pending"}'))
    session = Session('guangya', opener=SimpleNamespace(open=failed))
    assert session.request('https://account.guangyapan.com/v1/auth/token', body={}) == {'error': 'authorization_pending'}
    with pytest.raises(PanError, match='HTTP_REJECTED'):
        session.request('https://account.guangyapan.com/v1/auth/device/code', body={})


def test_cookie_rotation_is_saved_by_host_without_changing_scope(tmp_path):
    initial = cookie_saved()
    rotated = cookie_saved(session='fixture-rotated')
    service = PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}))
    expected = service.accounts.install(initial, service.accounts.snapshot('quark'))
    service.client_factory = lambda *a: SimpleNamespace(
        session=SimpleNamespace(export=lambda **kw: rotated),
        list_files=lambda *a, **kw: dict(items=[], has_more=False, page=1))
    service.list_files(expected, '0', 1)
    assert service.accounts.credentials(expected) == rotated
    assert service.accounts.snapshot('quark') == expected
    service.close()

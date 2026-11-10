"""Offline contracts, separate from anonymous first-party QR smoke checks."""
import base64
import json

import pytest

from bobbi_platform import pan_mobile as mobile
from bobbi_platform.pan_accounts import PanAccounts, PanError
from bobbi_platform.pan_http import Session
from test_ce2096_pan_tokens import Wire


def saved(pds=True):
    return dict(provider='139', subject='13800000000', auth_token='fixture-auth',
                device_id='fixture-device', pds=pds,
                route='https://personal-kd-njs.yun.139.com/hcy' if pds else '')


def reply(status='0', **data):
    return dict(success=True, code='0', data=dict(result=dict(resultCode=status), **data))


def row(**kw):
    return dict(fileId='file1', name='movie.mkv', type='file', size=100, updatedAt='2026-11-09T10:00:00', **kw)


def test_mobile_uses_ce_single_namespace_loader_and_fixed_failure(monkeypatch):
    from bobbi_core import juku_api
    calls, module = [], object()
    def load(name):
        calls.append(name)
        return module
    monkeypatch.setattr(juku_api, 'crypto_module', load)
    assert mobile.crypto('PublicKey.RSA') is module
    assert mobile.crypto('Cipher.AES') is module
    assert calls == ['Crypto.PublicKey.RSA', 'Crypto.Cipher.AES']
    def failed(name):
        raise juku_api.JukuError('private-loader-detail')
    monkeypatch.setattr(juku_api, 'crypto_module', failed)
    with pytest.raises(PanError, match='^PAN_CRYPTO_UNAVAILABLE$'):
        mobile.Login(Wire()).begin()


def test_mobile_credential_scope_does_not_use_rotating_auth_token(tmp_path):
    a = PanAccounts(tmp_path/'accounts.json', {'139': mobile.credentials})
    current = a.install(saved(), a.snapshot('139'))
    a.renew(dict(saved(), auth_token='rotated'), current)
    assert a.snapshot('139') == current
    with pytest.raises(PanError, match='IDENTITY_CHANGED'):
        a.renew(dict(saved(), subject='13900000000'), current)
    assert 'fixture-auth' not in json.dumps(current)


@pytest.mark.parametrize('value', ['https://evil.test/hcy', 'https://personal-kd-njs.yun.139.com.evil.test/hcy',
    'http://personal-kd-njs.yun.139.com/hcy', 'https://personal-kd-njs.yun.139.com/hcy/../user',
    'https://personal-kd-njs.yun.139.com:444/hcy', 'https://139.com/hcy'])
def test_mobile_rejects_foreign_route_before_credentials_leave(value):
    with pytest.raises(PanError):
        mobile.credentials(dict(saved(), route=value))


def test_mobile_qr_uses_fresh_keys_nested_pending_and_unknown_is_not_waiting():
    RSA = pytest.importorskip('Crypto.PublicKey.RSA')
    AES = pytest.importorskip('Crypto.Cipher.AES')
    PKCS = pytest.importorskip('Crypto.Cipher.PKCS1_v1_5')
    padding = pytest.importorskip('Crypto.Util.Padding')
    private = RSA.generate(1024)
    wire = Wire(reply(publicKey=base64.b64encode(private.public_key().export_key(format='DER')).decode()),
                reply('200059541'), reply('200059548'), reply('999999999'))
    now = [0]
    login = mobile.Login(wire, clock=lambda: now[0])
    qr = login.begin()
    assert qr.startswith('https://yun.139.com/w/#/qrcLogin?')
    assert login.poll() == ('waiting', None)
    encrypted_key = base64.b64decode(wire.calls[1]['headers']['mcloud-skey'])
    key = PKCS.new(private).decrypt(encrypted_key, None)
    plaintext = padding.unpad(AES.new(key, AES.MODE_ECB).decrypt(
        base64.b64decode(wire.calls[1]['body']['encryptMsg'])), 16)
    assert json.loads(plaintext)['dycPwd'] == login.sid
    assert login.poll() == ('waiting', None) and len(wire.calls) == 2
    now[0] = 2
    assert login.poll() == ('waiting', None)
    now[0] = 4
    with pytest.raises(PanError, match='API_REJECTED'):
        login.poll()
    login.cancel()
    assert login.key is None and login.secret is None
    with pytest.raises(PanError, match='FINISHED'):
        login.poll()


def test_mobile_new_account_defers_route_retry_until_directory_access():
    wire = Wire(reply(encryptAccount=base64.b64encode(b'13800000000').decode(), authToken='fixture-auth',
        cutoverStatus='1', userDomainId='uid1', routerInfo=[]))
    pytest.importorskip('Crypto')
    now = [0]
    flow = mobile.Login(wire, clock=lambda: now[0])
    flow.started, flow.key, flow.secret = 0, b'abcdefghijklmnop', 'fixture-secret'
    state, value = flow.poll()
    assert state == 'ready' and value['subject'] == saved()['subject']
    assert sum(c['url'].endswith('/login') for c in wire.calls) == 1
    assert value['route'] == '' and value['user_domain_id'] == 'uid1'
    access = Wire(PanError('PAN_NETWORK_ERROR'),
        reply(routePolicyList=[dict(modName='personal', httpsUrl=saved()['route'])]),
        reply(items=[], nextPageCursor=''))
    client = mobile.Client(value, access)
    with pytest.raises(PanError, match='NETWORK'):
        client.list_files()
    assert client.list_files()['items'] == []
    assert client.saved['route'] == saved()['route']


@pytest.mark.parametrize('pds', [True, False])
def test_mobile_both_personal_drive_formats_exact_original(pds):
    data = (dict(items=[row()], nextPageCursor='') if pds else
        dict(catalogList=[], contentList=[dict(contentId='file1', contentName='movie.mkv',
            contentSize=100, updateTime='2026-11-09T10:00:00')]))
    download = dict(url='https://download.yun.139.com/original')
    wire = Wire(reply(**data), reply(**data), reply(**download))
    client = mobile.Client(saved(pds), wire)
    selected = client.list_files()['items'][0]
    grant = client.resolve_original(selected)
    assert grant['original'] is True and grant['size'] == 100
    assert 'auth' not in json.dumps(grant)
    assert wire.calls[0]['body']['parentFileId' if pds else 'catalogId'] == ('/' if pds else mobile.CATALOG_ROOT)


def test_mobile_marker_pages_and_changed_file_not_opened():
    wire = Wire(reply(items=[row()], nextPageCursor='cursor1'), reply(items=[dict(row(), size=101)], nextPageCursor='cursor1'))
    client = mobile.Client(saved(), wire)
    page = client.list_files()
    assert page['has_more'] and page['next_cursor'] == 'cursor1'
    with pytest.raises(PanError, match='FILE_CHANGED'):
        client.resolve_original(page['items'][0])
    assert len(wire.calls) == 2
    with pytest.raises(PanError, match='PAGE_INVALID'):
        client.list_files(page=2)


def test_mobile_authorization_cannot_be_sent_to_key_or_login_endpoints():
    session = Session('139', opener=object())
    for url in (mobile.AUTH + 'key/v1.0/getRsaPublicKey', mobile.AUTH + 'permission/v1.0/login'):
        with pytest.raises(PanError, match='ORIGIN_REJECTED'):
            session.request(url, body={}, headers={'Authorization': 'Basic fixture'})

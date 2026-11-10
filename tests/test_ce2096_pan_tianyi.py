"""Tianyi web handoff contracts; no authenticated account fixtures are used."""
import base64
from copy import deepcopy

import pytest

from bobbi_platform import pan_tianyi as tianyi
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import Session, credentials
from test_ce2096_pan_tokens import Wire


def saved():
    return dict(provider='189', subject='13800000000', session_key='fixture-session',
        cookies=[dict(name='COOKIE_LOGIN_USER', value='fixture-cookie', domain='.189.cn', path='/')])


def conf():
    return dict(isOauth2=True, clientType=1, returnUrl=tianyi.API + '/api/portal/callbackUnify.action',
                appKey='cloud', reqId='fixture-request', paramId='fixture-param', state='fixture-state')


def png():
    return b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' + (180).to_bytes(4, 'big') * 2 + bytes(9)


def login_wire(*extra):
    return Wire((b'', 302, 'https://open.e.189.cn/api/logbox/separate/web/index.html?lt=t&reqId=r&appId=cloud'),
        (b'', 200, None), dict(result='0', data=conf()),
        dict(result=0, uuid='fixture-uuid', encryuuid='fixture-encrypted', encodeuuid='fixture-encoded'), png(), *extra)


def test_tianyi_handoff_qr_and_observed_pending_states():
    wire = login_wire(dict(status=-106), dict(status=-11002), dict(status=123456))
    flow = tianyi.Login(wire, clock=lambda: 1)
    assert base64.b64decode(flow.begin()['png']) == png()
    assert flow.poll() == ('waiting', None)
    assert flow.poll() == ('waiting', None)
    assert wire.calls[5]['form']['returnUrl'].startswith('https%3A%2F%2Fcloud.189.cn')
    with pytest.raises(PanError, match='STATE_INVALID'):
        flow.poll()


@pytest.mark.parametrize('url', ['http://cloud.189.cn/api/portal/loginUrl.action',
    'https://cloud.189.cn.evil.test/api/portal/callbackUnify.action',
    'https://cloud.189.cn/web/main#foreign', 'https://cloud.189.cn/web/main?a=1&a=2',
    'https://cloud.189.cn/api/open/file/deleteFile.action'])
def test_tianyi_redirects_never_follow_foreign_or_mutating_targets(url):
    wire = Wire((b'', 302, url))
    with pytest.raises(PanError):
        tianyi.follow(wire, tianyi.API + '/api/portal/loginUrl.action')
    assert len(wire.calls) == 1


@pytest.mark.parametrize('state,code', [(dict(status=-11001), 'EXPIRED'),
    (dict(result=-20099), 'EXPIRED'), (dict(status=-134), 'CHALLENGE_REQUIRED')])
def test_tianyi_terminal_or_challenge_is_not_pending(state, code):
    flow = tianyi.Login(login_wire(state))
    flow.begin()
    with pytest.raises(PanError, match=code):
        flow.poll()


def test_tianyi_success_retries_identity_not_consumed_qr():
    wire = login_wire(dict(status=0, redirectUrl=conf()['returnUrl']), (b'', 200, None),
        dict(res_code=0, sessionKey='fixture-session'), PanError('PAN_NETWORK_ERROR'),
        dict(res_code=0, loginName='13800000000'))
    wire.export = lambda **kw: saved()
    flow = tianyi.Login(wire)
    flow.begin()
    with pytest.raises(PanError, match='NETWORK'):
        flow.poll()
    assert flow.poll() == ('ready', saved())
    assert sum(c['url'].endswith('qrcodeLoginState.do') for c in wire.calls) == 1
    assert sum(c['url'].endswith('callbackUnify.action') for c in wire.calls) == 1
    assert 'fixture' not in repr(flow)


def test_tianyi_directory_original_identity_and_credentials():
    page = dict(res_code=0, fileListAO=dict(count=1, folderList=[], fileList=[
        dict(id=1, name='movie.mkv', size=100, lastOpTime='2026-11-09 10:00:00')]))
    wire = Wire(page, page, dict(res_code=0, fileDownloadUrl='https://download.cloud.189.cn/file'))
    client = tianyi.Client(saved(), wire)
    item = client.list_files()['items'][0]
    assert client.resolve_original(item)['original'] is True
    changed = deepcopy(page)
    changed['fileListAO']['fileList'][0]['size'] = 101
    client.session = Wire(changed)
    with pytest.raises(PanError, match='FILE_CHANGED'):
        client.resolve_original(item)
    assert credentials('189', saved())[0] == '13800000000'
    with pytest.raises(PanError):
        credentials('189', dict(saved(), cookies=[]))


def test_tianyi_handoff_metadata_not_available_to_other_providers():
    with pytest.raises(PanError, match='REQUEST_INVALID'):
        Session('baidu', opener=object()).request_raw('https://pan.baidu.com/api/list', metadata=True)

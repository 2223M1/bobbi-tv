"""Route changes exercise the real HTTP guard; synthetic replies, no accounts."""
import io
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import Session, MOBILE_REFRESH, MOBILE_CATALOG_ROUTES, TIANYI_FILE_ROUTES
from bobbi_platform.pan_request_policy import safe_read


LOGIN_123 = 'https://login.123pan.com/api/user/sign_in'
CONTEXT_123 = {
    'Origin': 'https://login.123pan.com',
    'Referer': 'https://login.123pan.com/centerlogin?redirect_url=https%3A%2F%2Fwww.123684.com&source_page=website',
    'app-version': '43',
}
DOWNLOAD_GUANGYA = 'https://api.guangyapan.com/userres/v1/get_res_download_url'


def wire(provider):
    calls = []

    def open_request(request, timeout):
        calls.append((request, timeout))
        reply = io.BytesIO(b'{"ok":true}')
        reply.status, reply.headers = 200, {}
        return reply

    return Session(provider, opener=SimpleNamespace(open=open_request)), calls


def test_123_exchange_uses_login_origin_and_bounded_transport():
    session, calls = wire('123')
    assert session.request(LOGIN_123, body={'code': 'fixture'}, headers=CONTEXT_123) == {'ok': True}
    request, timeout = calls[0]
    assert request.full_url == LOGIN_123 and request.get_method() == 'POST'
    assert request.get_header('App-version') == '43'
    assert request.get_header('User-agent').endswith('(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36')
    assert request.get_header('Accept') == 'application/json, text/plain, */*'
    assert request.get_header('Accept-language') == 'zh-CN,zh;q=0.9'
    assert request.get_header('Authorization') is None
    assert 0 < timeout <= 8


@pytest.mark.parametrize('url', [
    'https://user.123pan.cn/api/user/sign_in',
    'https://login.123pan.com/api/user/sign_in?redirect=1',
    'https://login.123pan.com/api/user/sign_in#fragment',
    'https://login.123pan.com.evil.test/api/user/sign_in',
    'http://login.123pan.com/api/user/sign_in',
    'https://login.123pan.com/api/user/info',
])
def test_123_rejects_old_and_unrelated_exchange_routes(url):
    session, calls = wire('123')
    with pytest.raises(PanError, match='PAN_ORIGIN_REJECTED'):
        session.request(url, body={}, headers=CONTEXT_123)
    assert not calls


@pytest.mark.parametrize('change', [
    {'Origin': 'https://user.123pan.cn'}, {'Referer': 'https://evil.test/'},
    {'Origin': None}, {'Referer': None}, {'Authorization': 'Bearer fixture'},
])
def test_123_ticket_exchange_rejects_incorrect_context_or_bearer(change):
    session, calls = wire('123')
    headers = dict(CONTEXT_123)
    for key, value in change.items():
        if value is None:
            headers.pop(key)
        else:
            headers[key] = value
    with pytest.raises(PanError, match='PAN_ORIGIN_REJECTED'):
        session.request(LOGIN_123, body={}, headers=headers)
    assert not calls


def test_guangya_original_route_and_authorization_stay_on_personal_api():
    session, calls = wire('guangya')
    assert session.request(DOWNLOAD_GUANGYA, body={'fileId': 'fixture'},
                           headers={'Authorization': 'Bearer fixture'}) == {'ok': True}
    assert urlsplit(calls[0][0].full_url).path == '/userres/v1/get_res_download_url'


@pytest.mark.parametrize('provider,url,body', [
    ('guangya', 'https://api.guangyapan.com/nd.bizuserres.s/v1/get_res_download_url', {}),
    ('guangya', DOWNLOAD_GUANGYA, None),
    ('xunlei', DOWNLOAD_GUANGYA, {}),
    ('123', DOWNLOAD_GUANGYA, {}),
])
def test_new_guangya_route_does_not_widen_cross_provider_or_method_access(provider, url, body):
    session, calls = wire(provider)
    with pytest.raises(PanError, match='PAN_ORIGIN_REJECTED'):
        session.request(url, body=body)
    assert not calls


def test_123_directory_bearer_moves_with_exact_official_route():
    session, calls = wire('123')
    url = 'https://yun.123pan.com/b/api/file/list/new'
    assert session.request(url, headers={'Authorization': 'Bearer fixture'}) == {'ok': True}
    assert safe_read('123', 'GET', url)
    assert not safe_read('123', 'POST', LOGIN_123)
    with pytest.raises(PanError, match='PAN_ORIGIN_REJECTED'):
        session.request('https://www.123pan.cn/b/api/file/list/new', headers={'Authorization': 'Bearer fixture'})
    assert len(calls) == 1


@pytest.mark.parametrize('url', sorted(TIANYI_FILE_ROUTES))
def test_tianyi_session_header_only_on_known_file_get_routes(url):
    session, calls = wire('189')
    assert session.request(url, query={'fileId': 'fixture'}, headers={'sessionKey': 'fixture'}) == {'ok': True}
    assert calls[0][0].get_header('Sessionkey') == 'fixture'
    assert calls[0][0].get_header('Accept') == 'application/json;charset=UTF-8'
    assert 'sessionKey' not in calls[0][0].full_url
    with pytest.raises(PanError, match='PAN_ORIGIN_REJECTED'):
        session.request('https://open.e.189.cn/api/logbox/oauth2/appConf.do', form={}, headers={'sessionKey': 'fixture'})


@pytest.mark.parametrize('url', sorted(MOBILE_CATALOG_ROUTES))
def test_mobile_catalog_account_and_auth_stay_in_known_routes(url):
    session, calls = wire('139')
    headers = {'Authorization': 'fixture|auth', 'x-account': '13900000000'}
    assert session.request(url, body={}, headers=headers) == {'ok': True}
    assert calls[0][0].get_header('X-account') == '13900000000'
    assert calls[0][0].get_header('Content-type') == 'application/json;charset=UTF-8'
    with pytest.raises(PanError, match='PAN_ORIGIN_REJECTED'):
        session.request('https://yun.139.com/orchestration/auth-rebuild/permission/v1.0/login',
                        body={}, headers=headers)


def test_mobile_xml_refresh_is_single_bounded_raw_request():
    session, calls = wire('139')
    payload = b'<root><token>fixture|auth</token><account>13900000000</account><clienttype>656</clienttype></root>'
    assert session.request_raw(MOBILE_REFRESH, xml_body=payload) == b'{"ok":true}'
    request, timeout = calls[0]
    assert request.get_method() == 'POST' and request.data == payload
    assert request.get_header('Content-type') == 'application/xml'
    assert request.get_header('Authorization') is None and timeout <= 8
    assert not safe_read('139', 'POST', MOBILE_REFRESH)


@pytest.mark.parametrize('options', [
    {'xml_body': '<root/>'}, {'xml_body': b''}, {'xml_body': b'x' * 16385},
    {'xml_body': b'<root/>', 'body': {}}, {'xml_body': b'<root/>', 'form': {}},
    {'xml_body': b'<root/>', 'query': {'account': 'fixture'}}, {'body': {}}, {'form': {}},
])
def test_mobile_xml_body_does_not_become_generic_raw_request(options):
    session, calls = wire('139')
    with pytest.raises(PanError, match='PAN_REQUEST_INVALID'):
        session.request_raw(MOBILE_REFRESH, **options)
    assert not calls


@pytest.mark.parametrize('provider,url', [
    ('baidu', MOBILE_REFRESH), ('139', 'https://yun.139.com/orchestration/auth-rebuild/permission/v1.0/login'),
])
def test_xml_is_not_available_for_other_providers_or_routes(provider, url):
    session, calls = wire(provider)
    with pytest.raises(PanError, match='PAN_REQUEST_INVALID'):
        session.request_raw(url, xml_body=b'<root/>')
    assert not calls


@pytest.mark.parametrize('headers', [{'Authorization': 'fixture'}, {'x-account': '13900000000'},
                                    {'sessionKey': 'fixture'}])
def test_mobile_refresh_cannot_leak_other_header_credentials(headers):
    session, calls = wire('139')
    with pytest.raises(PanError, match='PAN_ORIGIN_REJECTED'):
        session.request_raw(MOBILE_REFRESH, xml_body=b'<root/>', headers=headers)
    assert not calls


@pytest.mark.parametrize('provider,method', [('quark', 'GET'), ('uc', 'POST')])
def test_desktop_provider_user_agent_is_fixed_not_caller_controlled(provider, method):
    session, calls = wire(provider)
    host = 'uop.quark.cn' if provider == 'quark' else 'api.open.uc.cn'
    url = 'https://' + host + '/cas/ajax/getTokenForQrcodeLogin'
    options = {'form': {'client_id': '529'}} if method == 'POST' else {}
    assert session.request(url, **options) == {'ok': True}
    assert calls[0][0].get_method() == method
    assert provider + '-cloud-drive/2.5.20' in calls[0][0].get_header('User-agent')
    with pytest.raises(PanError, match='PAN_HEADERS_INVALID'):
        session.request(url, headers={'User-Agent': 'arbitrary'}, **options)
    assert len(calls) == 1


@pytest.mark.parametrize('url', [
    'https://user.aliyundrive.com/v2/user/get',
    'https://api.aliyundrive.com/adrive/v3/file/list',
    'https://api.aliyundrive.com/v2/file/get',
    'https://api.aliyundrive.com/v2/file/get_download_url',
])
def test_aliyun_aligned_origins_accept_bearer_only_on_known_api_routes(url):
    session, calls = wire('aliyun')
    assert session.request(url, body={}, headers={'Authorization': 'Bearer fixture'}) == {'ok': True}
    assert calls[0][0].get_header('Authorization') == 'Bearer fixture'
    assert calls[0][0].get_header('User-agent') == 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    assert not safe_read('aliyun', 'POST', 'https://auth.aliyundrive.com/v2/account/token')
    assert safe_read('aliyun', 'POST', 'https://api.aliyundrive.com/adrive/v3/file/list')


@pytest.mark.parametrize('url', [
    'https://auth.aliyundrive.com/v2/account/token',
    'https://user.aliyundrive.com/v2/file/get',
    'https://api.aliyundrive.com/v2/file/delete',
    'https://api.aliyundrive.com.evil.test/v2/file/get',
])
def test_aliyun_token_and_unknown_origins_never_receive_bearer(url):
    session, calls = wire('aliyun')
    with pytest.raises(PanError, match='PAN_ORIGIN_REJECTED'):
        session.request(url, body={}, headers={'Authorization': 'Bearer fixture'})
    assert not calls


def test_aliyun_refresh_user_agent_matches_public_client_and_carries_no_bearer():
    session, calls = wire('aliyun')
    assert session.request('https://auth.aliyundrive.com/v2/account/token',
                           body={'refresh_token': 'fixture'}) == {'ok': True}
    assert calls[0][0].get_header('User-agent').endswith('(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36')
    assert calls[0][0].get_header('Authorization') is None

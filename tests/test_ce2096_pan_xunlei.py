"""Offline Xunlei contracts. Fixtures do not attest real account playback."""
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from bobbi_platform import pan_xunlei
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import Session
from bobbi_platform.pan_service import PanService, _client
from test_ce2096_pan_tokens import Wire, token_saved


def admission(**kw):
    return dict(captcha_token='fixture-admission', expires_in=300, **kw)


def row(**kw):
    value = dict(kind='drive#file', id='f1', parent_id='', name='Episode.mkv', size='1234',
                 modified_time='2026-11-09T00:00:00Z', hash='a'*40, trashed=False)
    value.update(kw)
    return value


def page(**kw):
    return dict(files=[row(**kw)], next_page_token='')


def test_directory_cursor_original_identity_and_private_headers():
    wire = Wire(admission(), dict(page(), next_page_token='page2'), dict(files=[], next_page_token=''),
                admission(), row(web_content_link='https://vod0001.xunlei.com/original?fixture=secret',
                                 medias=[dict(link=dict(url='https://evil.test/transcode'))]))
    client = pan_xunlei.Client(token_saved('xunlei'), session=wire)
    selected = client.list_files()['items'][0]
    assert client.list_files(page=2, cursor='page2')['has_more'] is False
    result = client.resolve_original(selected)
    assert result['original'] is True and result['size'] == 1234
    assert set(result['headers']) == {'User-Agent'}
    assert wire.calls[0]['body'] == dict(client_id='Xqp0kJBXWhwaTpB6', action='GET:/drive/v1/files',
                                       device_id='fixture-device', meta={})
    assert wire.calls[3]['body']['action'] == 'GET:/drive/v1/files/f1'
    assert wire.calls[1]['headers']['Authorization'] == 'Bearer fixture-access'
    assert wire.calls[1]['headers']['X-Captcha-Token'] == 'fixture-admission'
    assert wire.calls[2]['query']['page_token'] == 'page2'
    assert 'secret' not in json.dumps(selected) and 'fixture' not in repr(client)


@pytest.mark.parametrize('change', [dict(name='other.mkv'), dict(size='2'), dict(hash='b'*40),
    dict(modified_time='2026-11-08'), dict(id='f2'), dict(parent_id='other'), dict(trashed=True),
    dict(kind='drive#folder'), dict(phase='PHASE_TYPE_RUNNING')])
def test_original_rejects_changed_file(change):
    wire = Wire(admission(), page(), admission(), row(**change))
    client = pan_xunlei.Client(token_saved('xunlei'), session=wire)
    with pytest.raises(PanError):
        client.resolve_original(client.list_files()['items'][0])


@pytest.mark.parametrize('url', ['https://evil.test/file', 'http://vod0001.xunlei.com/file',
    'https://xunlei.com.evil.test/file', 'https://vod0001.xunlei.com:8443/file'])
def test_original_cdn_is_restricted(url):
    client = pan_xunlei.Client(token_saved('xunlei'), session=Wire(admission(), page(), admission(), row(web_content_link=url)))
    with pytest.raises(PanError, match='ORIGIN_REJECTED'):
        client.resolve_original(client.list_files()['items'][0])


def test_expired_admission_retry_is_bounded_and_does_not_retry_account_error():
    expired = dict(error_code=9, error='captcha_invalid')
    wire = Wire(admission(), expired, admission(), expired)
    client = pan_xunlei.Client(token_saved('xunlei'), session=wire)
    with pytest.raises(PanError, match='CHALLENGE_REQUIRED'):
        client.list_files()
    assert len(wire.calls) == 4
    client.session = Wire(admission(), dict(error_code=4122, error='unauthenticated'))
    client.admissions.clear()
    with pytest.raises(PanError, match='LOGIN_REQUIRED'):
        client.list_files()
    assert len(client.session.calls) == 2


def test_human_challenge_never_followed_even_if_token_present():
    wire = Wire(admission(url='https://example.test/challenge'))
    client = pan_xunlei.Client(token_saved('xunlei'), session=wire)
    with pytest.raises(PanError, match='CHALLENGE_REQUIRED'):
        client.list_files()
    assert len(wire.calls) == 1


def test_admission_expiry_and_cache_are_bounded():
    now = [1]
    wire = Wire(admission(), page(), page(), admission(), page())
    client = pan_xunlei.Client(token_saved('xunlei'), session=wire, monotonic=lambda: now[0])
    client.list_files()
    now[0] = 295
    client.list_files()
    now[0] = 296
    client.list_files()
    assert sum(c['url'] == pan_xunlei.SHIELD for c in wire.calls) == 2


@pytest.mark.parametrize('reply', [dict(files=[], next_page_token='p2'), dict(files=[row(), row()]),
    page(parent_id='foreign'), page(size=True), dict(files=[row()], next_page_token=True)])
def test_invalid_directory_rejected(reply):
    client = pan_xunlei.Client(token_saved('xunlei'), session=Wire(admission(), reply))
    with pytest.raises(PanError):
        client.list_files()


@pytest.mark.parametrize('kwargs', [dict(page=2), dict(cursor='unexpected'), dict(parent='../escape'), dict(size=100)])
def test_invalid_request_never_reaches_network(kwargs):
    wire = Wire()
    client = pan_xunlei.Client(token_saved('xunlei'), session=wire)
    with pytest.raises(PanError):
        client.list_files(**kwargs)
    assert not wire.calls


@pytest.mark.parametrize('path,headers', [
    (pan_xunlei.SHIELD, {'X-Captcha-Token': 'secret'}),
    (pan_xunlei.SHIELD, {'Authorization': 'Bearer secret'}),
    ('https://xluser-ssl.xunlei.com/v1/user/me', {'X-Captcha-Token': 'secret'}),
    ('https://api-pan.xunlei.com/drive/v1/files/../user/me', {}),
    ('https://api-pan.xunlei.com/drive/v1/files/f1?retarget=1', {})])
def test_secret_headers_and_routes_are_restricted(path, headers):
    session = Session('xunlei', opener=SimpleNamespace(open=lambda *a, **kw: pytest.fail('No IO')))
    with pytest.raises(PanError, match='ORIGIN_REJECTED'):
        session.request(path, body={} if path == pan_xunlei.SHIELD else None, headers=headers)


def test_structured_http_error_cannot_be_mistaken_for_success():
    payload = [b'{"error_code":9,"error":"captcha_invalid"}']
    def failed(request, **kw):
        raise HTTPError(request.full_url, 403, 'private', {}, io.BytesIO(payload[0]))
    session = Session('xunlei', opener=SimpleNamespace(open=failed))
    assert session.request(pan_xunlei.API + pan_xunlei.FILES)['error_code'] == 9
    payload[0] = b'{"files":[],"next_page_token":""}'
    with pytest.raises(PanError, match='REPLY_INVALID'):
        session.request(pan_xunlei.API + pan_xunlei.FILES)


def test_service_wires_cursor_adapter_and_reports_unverified_capability(tmp_path):
    service = PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}))
    expected = service.accounts.install(token_saved('xunlei'), service.accounts.snapshot('xunlei'))
    client = _client('xunlei', token_saved('xunlei', expires=9999999999))
    client.session = Wire(admission(), dict(page(), next_page_token='p2'), admission(), dict(files=[], next_page_token=''))
    service.client_factory = lambda *a: client
    try:
        assert service.list_files(expected, '0', 1)['next_cursor'] == 'p2'
        # _using_client keeps the same test client; its admission is cached.
        client.session.responses = [dict(files=[], next_page_token='')]
        assert not service.list_files(expected, '0', 2, cursor='p2')['has_more']
        status = next(r for r in service.status()['providers'] if r['provider'] == 'xunlei')
        assert status['capabilities'] == ['qr_login', 'list_files', 'personal_play']
        assert status['verification'] == 'not_device_verified'
    finally:
        service.close()

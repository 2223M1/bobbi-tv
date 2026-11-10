"""Offline protocol/negative fixtures, not a claim of live provider success."""
from copy import deepcopy
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import API, Session, NoRedirect, credentials
from bobbi_platform.pan_quark_uc import Client, QuarkLogin, UCLogin
from bobbi_platform.pan_baidu import Client as BaiduClient, Login as BaiduLogin
from test_ce2096_pan_accounts import saved


class Transport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.saved = saved()
    def request(self, url, query=None, body=None):
        self.calls.append((url, query, body))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)
    def request_raw(self, url, query=None, body=None, **kwargs):
        return self.request(url, query, body)
    def export(self, **kwargs):
        return deepcopy(self.saved)
    def cookie_header(self, url):
        return 'fixture-cookie'


def file(fid='file-1', name='episode.mkv', size=1024, **values):
    return dict(fid=fid, file_name=name, size=size, file=True, **values)


def response(rows=None, total=1):
    return dict(code=0, status=200, data={'list': rows if rows is not None else [file()]},
                metadata={'_total': total})


@pytest.mark.parametrize('provider', ['quark', 'uc'])
def test_directory_uses_provider_specific_origin_pagination_and_no_mutation(provider):
    transport = Transport(response())
    result = Client(provider, session=transport).list_files()
    url, query, body = transport.calls[0]
    assert url == API[provider] + '/1/clouddrive/file/sort'
    assert query['_size'] == 10 and query['_page'] == 1 and body is None
    assert query['pr'] == ('ucpro' if provider == 'quark' else 'UCBrowser')
    assert result['items'] == [dict(file_id='file-1', name='episode.mkv', size=1024, directory=False)]
    assert result['has_more'] is False


@pytest.mark.parametrize('change', [lambda r: r.update(code=True), lambda r: r.update(status=403),
    lambda r: r['data']['list'][0].update(file=1), lambda r: r['data']['list'][0].update(size=True),
    lambda r: r['data']['list'][0].update(fid='../bad'), lambda r: r['metadata'].update(_total=-1),
    lambda r: r['data']['list'].append(deepcopy(r['data']['list'][0])),
    lambda r: r['data']['list'][0].update(file_name='name\r\nsecret')])
def test_malformed_cloud_listing_fails_closed(change):
    value = response()
    change(value)
    with pytest.raises(PanError):
        Client('quark', session=Transport(value)).list_files()


@pytest.mark.parametrize('page,size', [(True, 10), (0, 10), (10001, 10), (1, 21), (1, 0), (1, True)])
def test_pagination_rejected_before_network(page, size):
    transport = Transport()
    with pytest.raises(PanError):
        Client('uc', session=transport).list_files(page=page, size=size)
    assert not transport.calls


def test_share_access_does_not_transfer_delete_or_resolve_candidate():
    transport = Transport(dict(code=0, status=200, data={'stoken': 'fixture-share-token'}), response())
    client = Client('quark', session=transport)
    token = client.share_token('share-1', '1234')
    client.list_share('share-1', token)
    assert [r[0].rsplit('/', 1)[1] for r in transport.calls] == ['token', 'detail']
    assert transport.calls[0][2] == {'pwd_id': 'share-1', 'passcode': '1234'}


@pytest.mark.parametrize('provider', ['quark', 'uc'])
def test_download_keeps_exact_file_and_never_requests_transcoding(provider):
    domain = 'quark.cn' if provider == 'quark' else 'uc.cn'
    row = file(download_url='https://download.' + domain + '/fixture')
    transport = Transport(response(), dict(code=0, status=200, data=[row]))
    client = Client(provider, session=transport)
    selected = client.list_files()['items'][0]
    link = client.resolve_original(selected)
    assert link['original'] and link['size'] == selected['size']
    assert transport.calls[-1][0].endswith('/file/download')
    assert all('/play' not in r[0] and '/save' not in r[0] for r in transport.calls)


@pytest.mark.parametrize('change', [lambda r: r.update(fid='other'), lambda r: r.update(size=2048),
    lambda r: r.update(file_name='other.mkv'), lambda r: r.update(file=False),
    lambda r: r.update(download_url='https://quark.cn.evil.test/secret'),
    lambda r: r.update(download_url='http://download.quark.cn/secret'),
    lambda r: r.update(download_url='https://user:secret@download.quark.cn/secret')])
def test_changed_or_untrusted_download_rejected(change):
    row = file(download_url='https://download.quark.cn/fixture')
    change(row)
    transport = Transport(response(), dict(code=0, status=200, data=[row]))
    client = Client('quark', session=transport)
    with pytest.raises(PanError):
        client.resolve_original(client.list_files()['items'][0])


def test_quark_qr_wait_then_exchange_without_credentials_in_ready_state():
    transport = Transport(dict(status=2000000, data={'members': {'token': 'qr-token'}}),
        dict(status=50004001), dict(status=2000000, data={'members': {'service_ticket': 'ticket'}}),
        dict(success=True), dict(code=0, status=200, data={}))
    flow = QuarkLogin(transport)
    assert parse_qs(urlsplit(flow.begin()).query)['client_id'] == ['532']
    assert flow.poll() == ('waiting', None)
    state, account = flow.poll()
    assert state == 'ready' and account == saved()
    assert transport.calls[-2][0] == 'https://pan.quark.cn/account/info'
    assert 'qr-token' not in repr(flow)
    with pytest.raises(PanError, match='FINISHED'):
        flow.poll()


def test_uc_browser_login_does_not_reuse_quark_origin_client_or_cookies():
    transport = Transport(dict(status=2000000, data={'members': {'token': 'qr-token'}}),
        dict(status=2000000, data={'members': {'service_ticket': 'ticket'}}),
        dict(success=True), dict(code=0, status=200, data={}))
    transport.saved = saved('uc')
    flow = UCLogin(transport)
    qr = flow.begin()
    assert urlsplit(qr).hostname == 'su.uc.cn'
    assert parse_qs(urlsplit(qr).query)['client_id'] == ['381']
    assert flow.poll() == ('ready', saved('uc'))
    assert all('quark.cn' not in r[0] for r in transport.calls)
    assert transport.calls[0][0].startswith('https://api.open.uc.cn/')
    assert transport.calls[-2][0] == 'https://drive.uc.cn/account/info'


@pytest.mark.parametrize('status', [50004002, 50004003, 50004004, 999])
def test_qr_nonwaiting_errors_not_silently_pending(status):
    flow = QuarkLogin(Transport(dict(status=2000000, data={'members': {'token': 'qr-token'}}), dict(status=status)))
    flow.begin()
    with pytest.raises(PanError):
        flow.poll()


class Reply(io.BytesIO):
    status = 200
    def __init__(self, raw, length=None):
        super().__init__(raw)
        self.headers = {} if length is None else {'Content-Length': str(length)}


def test_http_no_cookies_cross_provider_and_redacted_repr():
    session = Session('quark', saved())
    assert 'fixture-session' in session.cookie_header('https://drive-pc.quark.cn/')
    assert not session.cookie_header('https://pc-api.uc.cn/')
    assert not session.cookie_header('https://evil.test/')
    assert 'fixture-session' not in repr(session)
    with pytest.raises(PanError):
        Session('uc', saved())


@pytest.mark.parametrize('url', ['http://drive-pc.quark.cn/1/clouddrive/file/sort',
    'https://drive-pc.quark.cn.evil.test/1/clouddrive/file/sort',
    'https://drive-pc.quark.cn/1/clouddrive/file/delete',
    'https://drive-pc.quark.cn/1/clouddrive/file/sort?secret=yes',
    'https://user@drive-pc.quark.cn/1/clouddrive/file/sort',
    'https://pc-api.uc.cn/1/clouddrive/file/sort'])
def test_http_endpoint_allowlist_before_network(url):
    def forbidden(*args, **kwargs):
        pytest.fail('Untrusted URL reached network')
    with pytest.raises(PanError, match='ORIGIN'):
        Session('quark', opener=SimpleNamespace(open=forbidden)).request(url)


@pytest.mark.parametrize('raw,length', [(b'{}', 3), (b'[]', 2), (b'{}', 2097153),
                                      (b'not-json', None), (b'{}', '-1')])
def test_bounded_complete_dictionary_response_required(raw, length):
    session = Session('quark', opener=SimpleNamespace(open=lambda *a, **kw: Reply(raw, length)))
    with pytest.raises(PanError, match='REPLY'):
        session.request(API['quark'] + '/1/clouddrive/file/sort')


def test_http_redirect_and_exception_text_never_forwarded():
    with pytest.raises(PanError, match='REDIRECT'):
        NoRedirect().redirect_request(None)
    def reject(*args, **kwargs):
        raise HTTPError('https://secret.invalid', 403, 'sensitive body', {}, io.BytesIO(b'secret'))
    with pytest.raises(PanError) as error:
        Session('quark', opener=SimpleNamespace(open=reject)).request(API['quark'] + '/1/clouddrive/file/sort')
    assert str(error.value) == 'PAN_LOGIN_REQUIRED'


def baidu_saved():
    return dict(provider='baidu', subject='123', cookies=[dict(name='BDUSS', value='fixture-' + 'x'*64,
                                                            domain='.baidu.com', path='/')])


def png():
    # A bounded PNG header fixture; no actual GUI or decoding assertion.
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + (100).to_bytes(4, 'big')*2 + b'\x08\x02\x00\x00\x00crc!'


def test_baidu_qr_uses_official_image_and_temporary_ticket_not_saved_as_cookie():
    transport = Transport(dict(errno=0, sign='fixture-sign',
        imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture-sign'), png(),
        dict(errno=1), dict(errno=0, channel_v=json.dumps(dict(status=0, v='temporary-ticket'))),
        b'<script>never evaluated</script>', dict(errno=0, result={'uk': 123}))
    transport.saved = baidu_saved()
    flow = BaiduLogin(transport)
    assert set(flow.begin()) == {'png'}
    assert flow.poll() == ('waiting', None)
    state, account = flow.poll()
    assert state == 'ready' and account == baidu_saved()
    assert 'temporary-ticket' not in json.dumps(account)
    assert transport.calls[-2][1]['bduss'] == 'temporary-ticket'
    assert 'client_secret' not in json.dumps(transport.calls)


def test_baidu_identity_network_retry_does_not_consume_qr_ticket_twice():
    transport = Transport(dict(errno=0, sign='fixture-sign',
        imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture-sign'), png(),
        dict(errno=0, channel_v=json.dumps(dict(status=0, v='temporary-ticket'))),
        b'exchanged', PanError('PAN_NETWORK_ERROR'), dict(errno=0, result={'uk': 123}))
    transport.saved = baidu_saved()
    flow = BaiduLogin(transport)
    flow.begin()
    with pytest.raises(PanError, match='NETWORK_ERROR'):
        flow.poll()
    assert flow.poll() == ('ready', baidu_saved())
    assert sum(url.endswith('/qrbdusslogin') for url, _, _ in transport.calls) == 1
    assert sum(url.endswith('/channel/unicast') for url, _, _ in transport.calls) == 1


@pytest.mark.parametrize('image_url', ['https://evil.test/qr',
    'https://passport.baidu.com.evil.test/v2/api/qrcode?sign=x',
    'https://passport.baidu.com/v2/api/qrcode?sign=other',
    'https://passport.baidu.com/v2/api/qrcode?sign=x&sign=x',
    'http://passport.baidu.com/v2/api/qrcode?sign=x'])
def test_baidu_untrusted_qr_image_is_not_fetched(image_url):
    transport = Transport(dict(errno=0, sign='x', imgurl=image_url))
    with pytest.raises(PanError):
        BaiduLogin(transport).begin()
    assert len(transport.calls) == 1


def test_baidu_uses_stable_subject_not_bduss_to_identify_user():
    first = baidu_saved()
    changed = deepcopy(first)
    changed['cookies'][0]['value'] = 'renewed-' + 'z'*64
    assert credentials('baidu', first)[0] == credentials('baidu', changed)[0]
    first['subject'] = ''
    with pytest.raises(PanError):
        credentials('baidu', first)


def test_baidu_directory_identity_and_original_filemetas_no_mediainfo():
    row = dict(fs_id=1234, server_filename='片.mkv', path='/目录/片.mkv', size=4096, isdir=0)
    transport = Transport(dict(errno=0, list=[row]),
        dict(errno=0, info=[dict(row, dlink='https://d.pcs.baidu.com/file/fixture')]))
    client = BaiduClient(session=transport)
    selected = client.list_files('/目录')['items'][0]
    result = client.resolve_original(selected)
    assert result['original'] is True and result['size'] == 4096
    assert transport.calls[-1][0].endswith('/api/filemetas')
    assert json.loads(transport.calls[-1][1]['target']) == ['/目录/片.mkv']
    assert all('mediainfo' not in row[0] for row in transport.calls)


@pytest.mark.parametrize('change', [lambda r: r.update(fs_id=4321), lambda r: r.update(size=8192),
    lambda r: r.update(path='/elsewhere/片.mkv'), lambda r: r.update(isdir=1),
    lambda r: r.update(dlink='https://evil.test/file')])
def test_baidu_rejects_changed_file_or_unknown_download_host(change):
    row = dict(fs_id=1234, server_filename='片.mkv', path='/片.mkv', size=4096, isdir=0)
    changed = dict(row, dlink='https://d.pcs.baidu.com/fixture')
    change(changed)
    client = BaiduClient(session=Transport(dict(errno=0, list=[row]), dict(errno=0, info=[changed])))
    with pytest.raises(PanError):
        client.resolve_original(client.list_files()['items'][0])

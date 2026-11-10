"""Offline Juku 0.81 contract alignment, never real-account acceptance.

Evidence: x64 00a7cd60 (Xunlei QR), 009eb5e0 (Guangya scope),
009fc060 (personal download), 00a858e0 (original file links),
009ed260/00a87020 (refresh), 00988300/00985b40 (Baidu file API).
"""
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_platform import pan_baidu, pan_device, pan_guangya, pan_xunlei
from bobbi_platform.pan_accounts import PanError
from test_ce2096_pan_adapters import Transport, baidu_saved, baidu_exchange, png
from test_ce2096_pan_tokens import Wire, token_saved
from test_ce2096_pan_xunlei import admission, row


def device_start(provider, **values):
    result = dict(device_code='fixture-device-code', expires_in=120, interval=2,
                  verification_uri_complete=pan_device.PROFILES[provider][0] + '/qr')
    result.update(values)
    return result


def device_token(**values):
    result = dict(access_token='fixture-access-new', refresh_token='fixture-refresh-new',
                  expires_in=3600, token_type='Bearer')
    result.update(values)
    return result


@pytest.mark.parametrize('provider,scope', [('guangya', 'user'), ('xunlei', 'user pan profile offline')])
def test_device_scope_is_provider_specific_and_identity_is_local(provider, scope):
    wire = Wire(device_start(provider))
    flow = pan_device.Login(provider, wire, clock=lambda: 0)
    flow.begin()
    assert wire.calls[0]['body']['scope'] == scope
    assert wire.calls[0]['headers']['X-Device-Id'] == flow.device
    assert len(flow.device) == 32 and int(flow.device, 16) > 0
    if provider == 'guangya':
        assert wire.calls[0]['headers']['X-Device-Sign'] == 'wdi10.' + flow.device + 'x' * 32


def test_xunlei_missing_server_qr_uses_nested_first_party_handoff():
    wire = Wire(device_start('xunlei', verification_uri_complete=None, user_code='fixture/code+='))
    flow = pan_device.Login('xunlei', wire, clock=lambda: 0)
    qr = urlsplit(flow.begin())
    assert qr.scheme == 'https' and qr.netloc == 'xluser-ssl.xunlei.com'
    assert qr.path == '/xluser.core.login/v3/qrlogin'
    redirect = urlsplit(parse_qs(qr.query)['redirect_uri'][0])
    assert redirect.netloc == 'i.xunlei.com'
    assert redirect.path == '/center/account/personal/qrcode-login/'
    assert parse_qs(redirect.query) == dict(client_id=[pan_device.PROFILES['xunlei'][1]],
        scope=['user pan profile offline'], user_code=['fixture/code+='])


def test_guangya_legacy_response_url_and_missing_lifetime_remain_bounded():
    wire = Wire(dict(device_code='fixture-code', verification_url='https://account.guangyapan.com/qr'))
    now = [0]
    flow = pan_device.Login('guangya', wire, clock=lambda: now[0])
    assert flow.begin() == 'https://account.guangyapan.com/qr'
    now[0] = 180
    with pytest.raises(PanError, match='EXPIRED'):
        flow.poll()
    assert len(wire.calls) == 1


@pytest.mark.parametrize('provider', ['guangya', 'xunlei'])
def test_identity_retry_never_reexchanges_consumed_device_code(provider):
    now = [0]
    wire = Wire(device_start(provider), device_token(), PanError('PAN_NETWORK_ERROR'), dict(sub='12345'))
    flow = pan_device.Login(provider, wire, clock=lambda: now[0], wall_clock=lambda: 1000)
    flow.begin()
    now[0] = 2
    with pytest.raises(PanError, match='NETWORK'):
        flow.poll()
    assert flow.phase == 'identity' and flow.pending is not None
    now[0] = 4
    assert flow.poll()[0] == 'ready'
    assert sum(call['url'].endswith('/auth/token') for call in wire.calls) == 1
    assert flow.phase == 'closed' and flow.pending is None


@pytest.mark.parametrize('provider', ['guangya', 'xunlei'])
@pytest.mark.parametrize('rotate', [False, True])
def test_refresh_optional_rotation_keeps_stable_identity(provider, rotate):
    response = device_token()
    if not rotate:
        response.pop('refresh_token')
    wire = Wire(response, dict(sub='12345'))
    old = token_saved(provider, expires=1001)
    client = pan_device.RenewableClient(provider, old, session=wire, clock=lambda: 1000)
    published = []
    client.renew_if_needed(lambda current, previous: published.append((current, previous)))
    assert len(published) == 1 and published[0][1] == old
    assert client.saved['refresh_token'] == ('fixture-refresh-new' if rotate else 'fixture-refresh')
    assert client.saved['subject'] == old['subject']
    assert wire.calls[0]['body']['grant_type'] == 'refresh_token'
    assert 'client_secret' not in wire.calls[0]['body']
    assert wire.calls[-1]['url'].endswith('/v1/user/me')


@pytest.mark.parametrize('provider', ['guangya', 'xunlei'])
@pytest.mark.parametrize('bad', ['', None, True, 'bad\r\nvalue'])
def test_explicit_invalid_refresh_is_never_silently_preserved(provider, bad):
    client = pan_device.RenewableClient(provider, token_saved(provider, expires=1001),
        session=Wire(device_token(refresh_token=bad)), clock=lambda: 1000)
    with pytest.raises(PanError):
        client.renew_if_needed(lambda *args: pytest.fail('invalid credentials must not publish'))


@pytest.mark.parametrize('provider', ['guangya', 'xunlei'])
def test_refresh_new_subject_is_never_published(provider):
    client = pan_device.RenewableClient(provider, token_saved(provider, expires=1001),
        session=Wire(device_token(), dict(sub='different-user')), clock=lambda: 1000)
    with pytest.raises(PanError, match='IDENTITY_CHANGED'):
        client.renew_if_needed(lambda *args: pytest.fail('changed identity must not publish'))


@pytest.mark.parametrize('provider', ['guangya', 'xunlei'])
def test_missing_token_lifetime_uses_short_local_renewal_deadline(provider):
    response = device_token()
    response.pop('expires_in')
    now = [0]
    wire = Wire(device_start(provider), response, dict(sub='12345'))
    flow = pan_device.Login(provider, wire, clock=lambda: now[0], wall_clock=lambda: 1000)
    flow.begin()
    now[0] = 2
    state, saved = flow.poll()
    assert state == 'ready' and saved['expires_at'] == 1300
    assert wire.calls[-1]['url'].endswith('/v1/user/me')


@pytest.mark.parametrize('provider', ['guangya', 'xunlei'])
@pytest.mark.parametrize('invalid', [None, 0, -1, True, '300', 32 * 86400])
def test_explicit_invalid_token_lifetime_is_not_defaulted(provider, invalid):
    with pytest.raises(PanError):
        pan_device.exchanged(provider, device_token(expires_in=invalid), 'fixture-device', lambda: 1000)


@pytest.mark.parametrize('provider', ['guangya', 'xunlei'])
@pytest.mark.parametrize('stage', ['begin', 'token', 'identity'])
@pytest.mark.parametrize('expire', [False, True])
def test_device_late_response_cannot_revive_cancelled_or_expired_login(provider, stage, expire):
    now = [0]
    wire = Wire(device_start(provider), device_token(), dict(sub='12345'))
    flow = pan_device.Login(provider, wire, clock=lambda: now[0])
    original = wire.request
    target = {'begin': '/device/code', 'token': '/auth/token', 'identity': '/user/me'}[stage]
    def request(url, *args, **kwargs):
        value = original(url, *args, **kwargs)
        if url.endswith(target):
            if expire:
                now[0] = 181
            else:
                flow.cancel()
        return value
    wire.request = request
    with pytest.raises(PanError, match='EXPIRED' if expire else 'FINISHED'):
        flow.begin()
        now[0] = 2
        flow.poll()
    assert flow.pending is None and flow.code is None and flow.terminal
    assert len(wire.calls) == {'begin': 1, 'token': 2, 'identity': 3}[stage]


def baidu_start():
    return dict(errno=0, sign='fixture', imgurl='passport.baidu.com/v2/api/qrcode?sign=fixture')


@pytest.mark.parametrize('stage,requests', [('begin', 1), ('image', 2), ('confirm', 3), ('exchange', 4), ('identity', 5)])
@pytest.mark.parametrize('expire', [False, True])
def test_baidu_late_response_cannot_start_next_phase_or_publish(stage, requests, expire):
    now = [0]
    wire = Transport(baidu_start(), png(), dict(channel_v=json.dumps(dict(status=0, v='temporary-ticket'))),
                     baidu_exchange(None), dict(errno=0, data={'fields': {'uid': 123}}))
    wire.saved = baidu_saved()
    flow = pan_baidu.Login(wire, clock=lambda: now[0])
    original = wire.request
    def request(url, *args, **kwargs):
        value = original(url, *args, **kwargs)
        if len(wire.calls) == requests:
            if expire:
                now[0] = 180
            else:
                flow.cancel()
        return value
    wire.request = request
    with pytest.raises(PanError, match='EXPIRED' if expire else 'FINISHED'):
        flow.begin()
        flow.poll()
    assert flow.terminal and flow.sign is None and not flow.exchanged
    assert len(wire.calls) == requests


def test_baidu_file_api_includes_public_web_application_id_without_order_regression():
    file = dict(fs_id=7, path='/Episode.mkv', server_filename='Episode.mkv', size=1234, isdir=0)
    wire = Transport(dict(errno=0, list=[file]),
        dict(errno=0, info=[dict(file, dlink='https://d.pcs.baidu.com/original')]))
    client = pan_baidu.Client(session=wire)
    assert client.resolve_original(client.list_files()['items'][0])['original']
    assert [call[1]['app_id'] for call in wire.calls] == [250528, 250528]
    assert wire.calls[0][1]['order'] == 'name' and wire.calls[0][1]['desc'] == 0


@pytest.mark.parametrize('field', ['downloadUrl', 'signedURL', 'url', 'signedUrl'])
def test_guangya_personal_download_route_and_evidenced_url_aliases(field):
    file = dict(fileId='f1', fileName='Episode.mkv', fileSize=1234, resType=1, utime=1)
    listing = dict(code=0, data=dict(list=[file], total=1))
    wire = Wire(listing, listing, dict(code=0, data={field: 'https://cdn.guangyapan.com/original'}))
    client = pan_guangya.Client(token_saved('guangya'), session=wire)
    result = client.resolve_original(client.list_files()['items'][0])
    assert result['original'] and result['size'] == 1234
    assert wire.calls[-1]['url'] == 'https://api.guangyapan.com/userres/v1/get_res_download_url'
    assert wire.calls[-1]['body'] == dict(fileId='f1')


def test_guangya_directory_without_total_or_mtime_stays_page_local():
    file = dict(fileId='f1', fileName='Episode.mkv', fileSize=1234, resType=1)
    page = dict(code=0, data=dict(list=[file]))
    wire = Wire(page, dict(code=0, data=dict(list=[])), page,
        dict(code=0, data=dict(downloadUrl='https://cdn.guangyapan.com/original')))
    client = pan_guangya.Client(token_saved('guangya'), session=wire)
    first = client.list_files(size=1)
    assert first['has_more'] and first['items'][0]['modified'] == 0
    assert not client.list_files(page=2, size=1)['has_more']
    assert client.resolve_original(first['items'][0])['original']
    assert len(wire.calls) == 4


@pytest.mark.parametrize('field', ['total', 'utime'])
@pytest.mark.parametrize('bad', [None, True, -1, '1'])
def test_guangya_explicit_bad_optional_metadata_still_rejected(field, bad):
    file = dict(fileId='f1', fileName='Episode.mkv', fileSize=1234, resType=1)
    data = dict(list=[file])
    (file if field == 'utime' else data)[field] = bad
    client = pan_guangya.Client(token_saved('guangya'), session=Wire(dict(code=0, data=data)))
    with pytest.raises(PanError):
        client.list_files()


@pytest.mark.parametrize('code', [401, 1001])
def test_guangya_expired_account_is_actionable_login_required(code):
    client = pan_guangya.Client(token_saved('guangya'), session=Wire(dict(code=code)))
    with pytest.raises(PanError, match='LOGIN_REQUIRED'):
        client.list_files()


@pytest.mark.parametrize('fields', [
    dict(medias=[dict(is_origin=True, link=dict(url='https://vod.xunlei.com/original'))]),
    dict(links={'application/octet-stream': dict(url='https://vod.xunlei.com/original')}),
])
def test_xunlei_original_fallbacks_are_explicit_and_do_not_forward_account_tokens(fields):
    wire = Wire(admission(), row(**fields))
    client = pan_xunlei.Client(token_saved('xunlei'), session=wire)
    result = client.resolve_original(pan_xunlei.entry(row()))
    assert result['url'] == 'https://vod.xunlei.com/original' and result['original']
    assert set(result['headers']) == {'User-Agent'}
    assert len(wire.calls) == 2


@pytest.mark.parametrize('fields', [
    dict(medias=[dict(link=dict(url='https://vod.xunlei.com/preview'))]),
    dict(medias=[dict(is_origin=False, link=dict(url='https://vod.xunlei.com/preview'))]),
    dict(medias=[dict(is_origin=1, link=dict(url='https://vod.xunlei.com/preview'))]),
    dict(medias=[dict(is_origin=True, link=dict(url='https://evil.test/original'))]),
    dict(medias=[dict(is_origin=True, link=dict(url='http://vod.xunlei.com/original'))]),
    dict(links={'video/mp4': dict(url='https://vod.xunlei.com/preview')}),
    dict(links={'application/octet-stream': dict(url='https://evil.test/original')}),
])
def test_xunlei_no_transcode_or_untrusted_origin_fallback(fields):
    client = pan_xunlei.Client(token_saved('xunlei'), session=Wire(admission(), row(**fields)))
    with pytest.raises(PanError):
        client.resolve_original(pan_xunlei.entry(row()))

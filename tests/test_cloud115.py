import json
from urllib.parse import parse_qs, urlsplit
import pytest
from bobbi_platform.cloud115 import Login, CloudError, load, save, credentials, request

TOKEN = {'state': 1, 'data': {'uid': 'example', 'sign': 'synthetic-sign', 'time': 1234,
                             'qrcode': 'https://115.com/scan/synthetic-test'}}
ACCOUNT = {'app': 'os_linux', 'cookies': {'UID': 'example-uid', 'CID': 'example-cid', 'SEID': 'example-seid'}}


def test_complete_login_only_exchanges_once_and_does_not_persist_until_requested(tmp_path):
    replies = iter([TOKEN, {'state': 1, 'data': {'status': 0}},
                    {'state': 1, 'data': {'status': 1}}, {'state': 1, 'data': {'status': 2}},
                    {'state': 1, 'data': {'cookie': ACCOUNT['cookies']}}])
    calls = []
    def transport(url, **kwargs):
        calls.append((url, kwargs))
        return next(replies)
    flow = Login(transport)
    assert flow.begin() == TOKEN['data']['qrcode']
    assert flow.poll() == ('waiting', None)
    assert flow.poll() == ('scanned', None)
    state, value = flow.poll()
    assert state == 'confirmed' and value['cookies'] == ACCOUNT['cookies']
    assert calls[-1] == ('https://qrcodeapi.115.com/app/1.0/os_linux/1.0/login/qrcode/', {'values': {'account': 'example'}})
    assert not list(tmp_path.iterdir())
    with pytest.raises(CloudError, match='QR_FINISHED'):
        flow.poll()
    save(tmp_path / 'account.json', value)
    assert load(tmp_path / 'account.json') == value
    assert 'synthetic' not in repr(flow)


@pytest.mark.parametrize('status,code', [(-1, 'QR_EXPIRED'), (-2, 'QR_CANCELLED')])
def test_expired_or_rejected_never_exchanges(status, code):
    replies = iter([TOKEN, {'state': 1, 'data': {'status': status}}])
    flow = Login(lambda *a, **kw: next(replies))
    flow.begin()
    with pytest.raises(CloudError, match=code):
        flow.poll()
    assert flow.terminal and flow.token is None


def test_cancel_and_elapsed_deadline_stop_network():
    now = [1]
    calls = []
    def transport(*args):
        calls.append(args)
        return TOKEN
    flow = Login(transport, lambda: now[0])
    flow.begin()
    now[0] = 182
    with pytest.raises(CloudError, match='QR_EXPIRED'):
        flow.poll()
    assert len(calls) == 1
    flow.begin()
    flow.cancel()
    with pytest.raises(CloudError, match='QR_FINISHED'):
        flow.poll()
    assert len(calls) == 2


def test_failed_exchange_is_not_retried(tmp_path):
    replies = iter([TOKEN, {'state': 1, 'data': {'status': 2}}, {'state': 0}])
    flow = Login(lambda *a, **kw: next(replies))
    flow.begin()
    with pytest.raises(CloudError, match='LOGIN_FAILED'):
        flow.poll()
    assert flow.terminal
    assert not list(tmp_path.iterdir())


def test_bad_credentials_cannot_replace_old_session(tmp_path):
    path = tmp_path / 'account.json'
    save(path, ACCOUNT)
    before = path.read_bytes()
    for cookies in ({'UID': 'bad'}, dict(ACCOUNT['cookies'], SEID='invalid;header'),
                    dict(ACCOUNT['cookies'], KID='bad\r\nheader')):
        with pytest.raises(CloudError):
            save(path, {'app': 'os_linux', 'cookies': cookies})
        assert path.read_bytes() == before


def test_login_protocol_rejects_unexpected_qr_host():
    flow = Login(lambda *a: {'state': 1, 'data': dict(TOKEN['data'], qrcode='https://evil.example/qr')})
    with pytest.raises(CloudError, match='INVALID_REPLY'):
        flow.begin()


def test_cookie_never_sent_to_foreign_origin():
    with pytest.raises(CloudError, match='INVALID_ORIGIN'):
        request('https://example.com/', cookie='synthetic-secret')


def test_qr_renderer_is_local_and_generates_actual_png(tmp_path):
    from bobbi_platform._vendor import segno
    image = tmp_path / 'qr.png'
    segno.make(TOKEN['data']['qrcode'], micro=False).save(str(image), scale=4)
    assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')

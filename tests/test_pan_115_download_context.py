"""A route-scoped download UA must survive into the existing Range transport."""
from io import BytesIO
import json
from types import SimpleNamespace

import pytest

from bobbi_platform import cloud115, pan_115, pan_115_cipher
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import NoRedirect, Session
from test_accounts import credential
from test_ce2096_pan_stream import Upstream, read
from test_pan_115_personal import RAW, SELECTED, drive


DOWNLOAD_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36')


class Reply(BytesIO):
    status = 200

    def __init__(self, value):
        raw = json.dumps(value).encode()
        super().__init__(raw)
        self.headers = {'Content-Length': str(len(raw))}


def test_only_original_download_uses_browser_agent_and_returns_the_same_agent(monkeypatch):
    requests = []
    def open_request(request, timeout):
        requests.append(request)
        if request.full_url.startswith(pan_115.WEB + '/files/get_info?'):
            return Reply(dict(state=True, data=[RAW]))
        if request.full_url.startswith(pan_115.WEB + '/files?'):
            return Reply(dict(state=True, path=[dict(cid='42')], offset=0, count=1, data=[RAW]))
        assert request.full_url == pan_115.DOWNLOAD and request.get_method() == 'POST'
        assert request.get_header('Content-type') == 'application/x-www-form-urlencoded'
        return Reply(dict(state=True, data='fixture-wire'))
    decoded = {'101': dict(file_name='Movie.mkv', file_size='8', sha1='A' * 40,
        pick_code='fixture-pick', url={'url': 'https://download.115cdn.net/original?fixture=private'})}
    monkeypatch.setattr(pan_115_cipher, 'decrypt', lambda value: json.dumps(decoded).encode())
    session = Session('115', credential(), opener=SimpleNamespace(open=open_request))
    client = pan_115.Client(credential(), session)
    assert client.list_files('42')['items'] == [SELECTED]
    resolved = client.resolve_original(SELECTED)
    agents = [request.get_header('User-agent') for request in requests]
    assert cloud115.USER_AGENT == 'Mozilla/5.0 115Browser/36.2.28'  # Existing login/share contract.
    assert agents == [cloud115.USER_AGENT, cloud115.USER_AGENT, DOWNLOAD_AGENT]
    assert resolved['headers'] == {'User-Agent': agents[-1]}
    assert all(request.get_header('Referer') == 'https://115.com/' for request in requests)
    assert len(requests) == 3  # No alternate route, retry or CDN request.


def test_registered_original_range_uses_download_agent_without_api_cookies(drive):
    pans, expected = drive.pans, drive.expected
    assert pans.list_files(expected, '42', 1)['items'] == [SELECTED]
    ticket = pans.prepare_play(expected, SELECTED)['ticket']
    selected = pans.claim_play(ticket)['selected']
    ready = pans.open_stream(expected, selected, ticket)
    calls = []
    pans.streams.session_factory = lambda: Upstream(calls)
    assert read(ready['url'])[0::2] == (206, b'cdef')
    assert calls[0][1]['User-Agent'] == DOWNLOAD_AGENT
    assert calls[0][1]['Range'] == 'bytes=2-5'
    assert 'Cookie' not in calls[0][1]


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_download_redirect_remains_terminal_and_never_follows(status):
    requests = []
    def open_request(request, timeout):
        requests.append(request)
        return NoRedirect().redirect_request(request, None, status, 'redirect',
            {'Location': 'https://unknown.test/?secret=fixture'}, 'https://unknown.test/?secret=fixture')
    session = Session('115', credential(), opener=SimpleNamespace(open=open_request))
    with pytest.raises(PanError, match='^PAN_REDIRECT_REJECTED$'):
        session.request(pan_115.DOWNLOAD, form={'data': 'fixture-wire'})
    assert len(requests) == 1 and requests[0].full_url == pan_115.DOWNLOAD

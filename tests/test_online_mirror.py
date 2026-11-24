"""Domestic discovery and same-generation fallback never require user secrets."""
import hashlib
import json
from pathlib import Path
import ssl
from urllib.error import URLError
from urllib.request import Request

import pytest

from bobbi_platform import online_updates as online
from bobbi_platform.updates import UpdateError
from test_online_updates import Response, offer_for, tracked_offer
from test_ce_general_installer import package, signing

MIRROR = 'https://gitcode.com/BobbiZerri/bobbi-tv-updates'


def mirror_offer(raw):
    offer = offer_for(raw)
    offer['url'] = MIRROR + '/releases/download/ce2054/BobbiTV-CE2054.bobbi-update.zip'
    return offer


def test_default_discovery_is_domestic_and_offer_schema_remains_one():
    assert online.OFFER_URL == 'https://raw.gitcode.com/BobbiZerri/bobbi-tv-updates/raw/main/repository/current.json'
    value = mirror_offer(b'blob')
    assert online.parse_offer(json.dumps(value)) == value
    assert online.parse_offer(json.dumps(offer_for(b'blob')))['schema'] == 1


@pytest.mark.parametrize('url', [
    MIRROR.replace('BobbiZerri', 'another') + '/releases/download/ce2054/BobbiTV-CE2054.bobbi-update.zip',
    MIRROR + '/releases/download/ce2053/BobbiTV-CE2054.bobbi-update.zip',
    MIRROR + '/releases/download/ce2054/BobbiTV-CE2054.bobbi-update.zip?token=anything',
    'https://foruda.gitee.com/attach_file/123/BobbiTV-CE2054.bobbi-update.zip',
])
def test_discovery_cannot_nominate_other_projects_or_cdn_urls(url):
    with pytest.raises(UpdateError, match='ONLINE_OFFER_INVALID'):
        online.parse_offer(json.dumps(dict(mirror_offer(b'blob'), url=url)))


CDN = 'https://file-cdn.gitcode.com/11470074/releases/untagger_' + 'a'*32 + '/'
NAME = 'BobbiTV-CE2054.bobbi-update.zip'


def test_real_gitcode_redirect_stays_bound_to_origin_and_exact_asset():
    url = CDN + NAME + '?auth_key=1700000000-0-0-deadbeef'
    req = Request(mirror_offer(b'x')['url'])
    assert online._Redirects().redirect_request(req, None, 302, '', {}, url).full_url == url
    for bad in (url.replace('11470074','99'), url.replace('2054','2055'),
                url.replace('file-cdn.gitcode.com','file-cdn.gitcode.com.other.invalid'),
                url.replace('https:','http:'), url.replace('untagger_', 'private_'),
                url.replace('?auth_key=', '?target='), url+'#x',url+'&auth_key=x',
                url.replace('1700000000-0-0-deadbeef',''), url.replace(NAME,'other.zip')):
        with pytest.raises(UpdateError, match='ONLINE_REDIRECT_REJECTED'):
            online._Redirects().redirect_request(req, None, 302, '', {}, bad)
    for bad in (online.feed_url('stable','gitcode'), req.full_url.replace('BobbiZerri','other'),
                req.full_url.replace('gitcode.com','github.com')):
        with pytest.raises(UpdateError, match='ONLINE_REDIRECT_REJECTED'):
            online._Redirects().redirect_request(Request(bad), None, 302, '', {}, url)


def test_discovery_falls_back_once_only_on_transport_failure(monkeypatch):
    calls = []
    def open_response(url):
        calls.append(url)
        if len(calls) == 1:
            raise URLError(TimeoutError())
        return Response(json.dumps(tracked_offer(b'blob')).encode())
    monkeypatch.setattr(online, '_open', open_response)
    assert online.latest() == tracked_offer(b'blob')
    assert calls == [online.feed_url('stable', mirror) for mirror in ('gitcode', 'github')]


@pytest.mark.parametrize('failure', ['cancel', 'json', 'length', 'redirect'])
def test_discovery_does_not_mask_cancel_or_invalid_content(monkeypatch, failure):
    calls = []
    def open_response(url):
        calls.append(url)
        if failure == 'cancel':
            raise online.Cancelled('ONLINE_CANCELLED')
        if failure == 'redirect':
            raise UpdateError('ONLINE_REDIRECT_REJECTED')
        return Response(b'invalid' if failure == 'json' else b'x'*32769)
    monkeypatch.setattr(online, '_open', open_response)
    with pytest.raises(UpdateError):
        online.latest()
    assert len(calls) == 1


def test_partial_download_fallback_restarts_same_file_without_mixing_bytes(tmp_path, signing, monkeypatch):
    raw = package(tmp_path/'signed.zip', signing).read_bytes()
    calls, progress = [], []
    class Broken(Response):
        def read(self, size):
            if self.tell():
                raise URLError(TimeoutError())
            return super().read(17)
    first = Broken(raw)
    def open_response(url):
        calls.append(url)
        return first if len(calls) == 1 else Response(raw)
    monkeypatch.setattr(online, '_open', open_response)
    path = online.download(mirror_offer(raw), tmp_path/'work', signing[1], progress=progress.append)
    assert path.read_bytes() == raw and first.closed
    assert calls == [mirror_offer(raw)['url'], offer_for(raw)['url']]
    assert progress[-1] == 100 and 0 in progress
    assert hashlib.sha256(path.read_bytes()).hexdigest() == mirror_offer(raw)['sha256']


def test_cancel_between_sources_prevents_any_fallback(tmp_path, signing, monkeypatch):
    calls, state = [], {'cancel': False}
    def open_response(url):
        calls.append(url)
        state['cancel'] = True
        raise URLError(TimeoutError())
    monkeypatch.setattr(online, '_open', open_response)
    with pytest.raises(online.Cancelled):
        online.download(mirror_offer(b'x'), tmp_path/'work', signing[1], cancelled=lambda: state['cancel'])
    assert len(calls) == 1 and not list((tmp_path/'work').iterdir())


def test_integrity_failure_is_not_hidden_by_another_provider(tmp_path, signing, monkeypatch):
    calls = []
    def open_response(url):
        calls.append(url)
        return Response(b'bad!')
    monkeypatch.setattr(online, '_open', open_response)
    with pytest.raises(UpdateError, match='ONLINE_CONTENT_INVALID'):
        online.download(mirror_offer(b'good'), tmp_path/'work', signing[1])
    assert len(calls) == 1 and not list((tmp_path/'work').iterdir())


def test_fallback_keeps_one_total_budget(monkeypatch):
    clock, calls = [0], []
    monkeypatch.setattr(online.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(online, 'TRANSFER_SECONDS', .2)
    class Slow(Response):
        def read(self, size):
            clock[0] = .21
            return super().read(size)
    def open_response(url):
        calls.append(url)
        if len(calls) == 1:
            clock[0] = .15
            raise URLError(TimeoutError())
        return Slow(json.dumps(offer_for(b'blob')).encode())
    monkeypatch.setattr(online, '_open', open_response)
    with pytest.raises(UpdateError, match='ONLINE_TIMEOUT'):
        online.latest()
    assert len(calls) == 2


def test_certificate_failure_does_not_silently_switch_host(monkeypatch):
    calls = []
    def open_response(url):
        calls.append(url)
        raise URLError(ssl.SSLCertVerificationError('fixture'))
    monkeypatch.setattr(online, '_open', open_response)
    with pytest.raises(URLError):
        online.latest()
    assert len(calls) == 1


def test_retired_gitee_never_enters_discovery_or_artifact_fallback():
    with pytest.raises(UpdateError):
        online.feed_url('stable', 'gitee')
    with pytest.raises(UpdateError):
        online.release_url('ce2183', 'gitee')
    assert not online._allowed_redirect('https://foruda.gitee.com/attach_file/1/' + NAME)

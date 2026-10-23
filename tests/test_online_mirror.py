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
from test_online_updates import Response, offer_for
from test_ce_general_installer import package, signing

MIRROR = 'https://gitee.com/M12223/bobbi-tv-updates'


def mirror_offer(raw):
    offer = offer_for(raw)
    offer['url'] = MIRROR + '/releases/download/ce2054/BobbiTV-CE2054.bobbi-update.zip'
    return offer


def test_default_discovery_is_domestic_and_offer_schema_remains_one():
    assert online.OFFER_URL == MIRROR + '/raw/master/repository/current.json'
    value = mirror_offer(b'blob')
    assert online.parse_offer(json.dumps(value)) == value
    assert online.parse_offer(json.dumps(offer_for(b'blob')))['schema'] == 1


@pytest.mark.parametrize('url', [
    MIRROR.replace('M12223', 'another') + '/releases/download/ce2054/BobbiTV-CE2054.bobbi-update.zip',
    MIRROR + '/releases/download/ce2053/BobbiTV-CE2054.bobbi-update.zip',
    MIRROR + '/releases/download/ce2054/BobbiTV-CE2054.bobbi-update.zip?token=anything',
    'https://foruda.gitee.com/attach_file/123/BobbiTV-CE2054.bobbi-update.zip',
])
def test_discovery_cannot_nominate_other_projects_or_cdn_urls(url):
    with pytest.raises(UpdateError, match='ONLINE_OFFER_INVALID'):
        online.parse_offer(json.dumps(dict(mirror_offer(b'blob'), url=url)))


@pytest.mark.parametrize('url', [
    'https://raw.giteeusercontent.com/M12223/bobbi-tv-updates/raw/master/repository/current.json',
    'https://raw.giteeusercontent.com/M12223/bobbi-tv-updates/raw/master/repository/current.json?metadata=fixture&signature=fixture',
    MIRROR + '/attach_files/123/download/BobbiTV-CE2054.bobbi-update.zip',
    'https://foruda.gitee.com/attach_file/123/BobbiTV-CE2054.bobbi-update.zip?signature=fixture',
    'https://foruda.gitee.com/attach_file/123/bobbitv-ce2055.bobbi-update.zip?token=fixture&ts=123&attname=fixture',
])
def test_domestic_redirects_only_admit_known_delivery_routes(url):
    redirected = online._Redirects().redirect_request(Request(mirror_offer(b'x')['url']), None, 302, '', {}, url)
    assert redirected.full_url == url


@pytest.mark.parametrize('url', [
    'http://foruda.gitee.com/attach_file/123/BobbiTV-CE2054.bobbi-update.zip',
    'https://foruda.gitee.com.evil.invalid/attach_file/123/BobbiTV-CE2054.bobbi-update.zip',
    'https://user@foruda.gitee.com/attach_file/123/BobbiTV-CE2054.bobbi-update.zip',
    'https://foruda.gitee.com:8443/attach_file/123/BobbiTV-CE2054.bobbi-update.zip',
    'https://foruda.gitee.com/attach_file/123/BobbiTV-CE2054.bobbi-update.zip#fragment',
    'https://gitee.com/login',
    'https://raw.giteeusercontent.com/elsewhere/repository/current.json',
    'https://raw.giteeusercontent.com/M12223/bobbi-tv-updates/raw/master/repository/current.json?url=https%3A%2F%2Fexample.org',
    'https://raw.giteeusercontent.com/M12223/bobbi-tv-updates/raw/master/repository/current.json?metadata=fixture',
    'https://raw.giteeusercontent.com/M12223/bobbi-tv-updates/raw/master/repository/current.json?metadata=fixture&signature=',
    'https://raw.giteeusercontent.com/M12223/bobbi-tv-updates/raw/master/repository/current.json?metadata=fixture&signature=a&signature=b',
])
def test_domestic_redirect_policy_has_no_wildcard_hosts_or_login_hops(url):
    with pytest.raises(UpdateError, match='ONLINE_REDIRECT_REJECTED'):
        online._Redirects().redirect_request(Request(mirror_offer(b'x')['url']), None, 302, '', {}, url)


def test_discovery_falls_back_once_only_on_transport_failure(monkeypatch):
    calls = []
    def open_response(url):
        calls.append(url)
        if len(calls) == 1:
            raise URLError(TimeoutError())
        return Response(json.dumps(offer_for(b'blob')).encode())
    monkeypatch.setattr(online, '_open', open_response)
    assert online.latest() == offer_for(b'blob')
    assert calls == [online.OFFER_URL, online.FALLBACK_OFFER_URL]


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


def test_mirror_builder_rejects_free_attachment_limit_before_publishing(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'tools'))
    from build_online_repository import publish
    large = tmp_path/'large.zip'
    with large.open('wb') as stream:
        stream.truncate(100_000_001)
    output = tmp_path/'feed'
    with pytest.raises(ValueError, match='100M'):
        publish(large, output, 'ce2055')
    assert not output.exists()

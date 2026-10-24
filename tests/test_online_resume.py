"""Resume keeps one exact release, never grants installation or mixes mirrors."""
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from bobbi_platform import online_updates as online
from bobbi_platform.updates import UpdateError
from test_online_updates import Response, offer_for, package, signing, entry, environment
from test_online_transport import endpoint


def headers():
    context = getattr(online, '_REQUEST_HEADERS', None)
    return dict(context.get()) if context is not None else {}


class Dropped(Response):
    def __init__(self, raw, count, etag='"fixed-release"'):
        super().__init__(raw, {'Content-Length': str(len(raw)), 'ETag': etag})
        self.count = count

    def read1(self, size):
        if self.tell() >= self.count:
            raise URLError('fixture disconnected')
        return super().read1(min(size, self.count-self.tell()))


def interrupt(monkeypatch, raw, offer, work, trust, etag='"fixed-release"'):
    responses = []
    def open_response(url):
        if responses:
            raise URLError('fixture mirror unavailable')
        result = Dropped(raw, len(raw)//2, etag)
        responses.append(result)
        return result
    monkeypatch.setattr(online, '_open', open_response)
    with pytest.raises(URLError):
        online.download(offer, work, trust)
    assert responses[0].closed


@pytest.fixture
def payload(tmp_path, signing):
    raw = package(tmp_path/'input.zip', signing).read_bytes()
    return raw, offer_for(raw), tmp_path/'downloads', signing[1]


def ranged(raw, offset, etag='"fixed-release"', **replace):
    values = {'Content-Length': str(len(raw)-offset),
              'Content-Range': 'bytes {}-{}/{}'.format(offset,len(raw)-1,len(raw)), 'ETag': etag}
    values.update(replace)
    return Response(raw[offset:], values, 206)


@pytest.mark.parametrize('known_length', [True, False])
def test_interrupted_download_resumes_exact_remaining_bytes(payload, monkeypatch, known_length):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    requests, progress = [], []
    def open_response(url):
        requests.append((url, headers()))
        assert headers() == {'Range': 'bytes={}-'.format(len(raw)//2), 'If-Range': '"fixed-release"'}
        response = ranged(raw, len(raw)//2)
        if not known_length: response.headers.pop('Content-Length')
        return response
    monkeypatch.setattr(online, '_open', open_response)
    result = online.download(offer, work, trust, progress=progress.append)
    assert result.read_bytes() == raw and len(requests) == 1 and progress[-1] == 100
    assert list(work.iterdir()) == [result]


@pytest.mark.parametrize('etag', ['', 'W/"weak"', 'bad', '"newline\n"'])
def test_no_strong_validator_restarts_without_retaining_partial(payload, monkeypatch, etag):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload, etag=etag)
    assert not list(work.iterdir())
    def open_response(url):
        assert not headers()
        return Response(raw)
    monkeypatch.setattr(online, '_open', open_response)
    assert online.download(offer, work, trust).read_bytes() == raw


def test_ignored_range_200_replaces_prefix_instead_of_appending(payload, monkeypatch):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    requests = []
    def open_response(url):
        requests.append(headers())
        return Response(raw, {'Content-Length': str(len(raw)), 'ETag': '"changed"'})
    monkeypatch.setattr(online, '_open', open_response)
    assert online.download(offer, work, trust).read_bytes() == raw
    assert requests[0]['Range'] == 'bytes={}-'.format(len(raw)//2)


@pytest.mark.parametrize('replacement', [
    {'Content-Range': 'bytes 0-9/10'}, {'Content-Range': 'bytes */9'},
    {'ETag': '"changed"'}, {'ETag': ''}, {'Content-Length': '1'},
])
def test_invalid_resume_response_is_never_published(payload, monkeypatch, replacement):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    monkeypatch.setattr(online, '_open', lambda _: ranged(raw, len(raw)//2, **replacement))
    with pytest.raises(UpdateError):
        online.download(offer, work, trust)
    assert not list(work.iterdir())


def test_416_restarts_once_without_range(payload, monkeypatch):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    seen = []
    def open_response(url):
        seen.append(headers())
        if len(seen) == 1:
            raise HTTPError(url,416,'fixture',{},None)
        assert not headers()
        return Response(raw)
    monkeypatch.setattr(online, '_open', open_response)
    assert online.download(offer, work, trust).read_bytes() == raw
    assert len(seen) == 2 and seen[0]['Range']


def test_mirror_switch_never_appends_other_origin_bytes(payload, monkeypatch):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    seen = []
    def open_response(url):
        seen.append((url, headers()))
        if len(seen) == 1:
            assert headers()['Range']
            raise URLError('fixture first origin unavailable')
        assert not headers()
        return Response(raw)
    monkeypatch.setattr(online, '_open', open_response)
    assert online.download(offer, work, trust).read_bytes() == raw
    assert len(seen) == 2 and seen[0][0] != seen[1][0]


@pytest.mark.parametrize('changed', ['sequence', 'digest', 'prefix', 'journal'])
def test_changed_identity_or_local_prefix_cannot_resume(payload, monkeypatch, changed):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    if changed == 'sequence':
        offer = dict(offer, sequence=2)
    elif changed == 'digest':
        offer = dict(offer, sha256='0'*64)
    elif changed == 'prefix':
        part = work/'online.partial'
        assert part.is_file()
        part.write_bytes(b'x'*part.stat().st_size)
    else:
        (work/'online-resume.json').write_text('{broken', encoding='utf-8')
    seen = []
    def open_response(url):
        seen.append(headers())
        assert not headers()
        return Response(raw)
    monkeypatch.setattr(online, '_open', open_response)
    if changed in ('sequence','digest'):
        with pytest.raises(UpdateError): online.download(offer, work, trust)
    else:
        assert online.download(offer, work, trust).read_bytes() == raw
    assert seen == [{}]


def test_cancel_resume_discards_only_current_partial(payload, monkeypatch):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    (work/'previous-backup.zip').write_bytes(b'keep')
    cancelled = [False]
    monkeypatch.setattr(online, '_open', lambda _: ranged(raw,len(raw)//2))
    with pytest.raises(online.Cancelled):
        online.download(offer, work, trust, lambda: cancelled[0],
                        lambda _: cancelled.__setitem__(0,True))
    assert [p.name for p in work.iterdir()] == ['previous-backup.zip']


def test_checkpoint_tail_from_process_exit_is_not_trusted(payload, monkeypatch):
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    part = work/'online.partial'
    assert part.is_file()
    with part.open('ab') as stream: stream.write(b'uncheckpointed-tail')
    def open_response(url):
        assert headers()['Range'] == 'bytes={}-'.format(len(raw)//2)
        return ranged(raw,len(raw)//2)
    monkeypatch.setattr(online, '_open', open_response)
    assert online.download(offer, work, trust).read_bytes() == raw


def test_resume_uses_real_tls_socket_range_and_sni(payload, endpoint, monkeypatch):
    raw, offer, work, trust = payload
    endpoint.blob = raw
    native_open = online._open
    first = [True]
    def open_response(url):
        if not first[0]:
            raise URLError('fixture fallback offline')
        first[0] = False
        return native_open(endpoint.url+'/resume')
    monkeypatch.setattr(online, '_open', open_response)
    with pytest.raises(URLError): online.download(offer, work, trust)
    monkeypatch.setattr(online, '_open', lambda _: native_open(endpoint.url+'/resume'))
    assert online.download(offer, work, trust).read_bytes() == raw
    assert len(endpoint.requests) == 2
    assert 'Range' not in endpoint.requests[0][1]
    assert endpoint.requests[1][1]['Range'] == 'bytes={}-'.format(len(raw)//2)
    assert endpoint.requests[1][1]['If-Range'] == '"fixed-release"'
    assert endpoint.sni == ['localhost','localhost']
    assert online._REQUEST_HEADERS.get() is None


def test_second_downloader_cannot_change_the_owned_checkpoint(payload, monkeypatch):
    from bobbi_platform.online_partial import PartialDownload
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    before = {path.name:path.read_bytes() for path in work.iterdir()}
    with PartialDownload(work, offer, (offer['url'],), lambda: None):
        monkeypatch.setattr(online, '_open', lambda _: pytest.fail('Concurrent network request'))
        with pytest.raises(UpdateError, match='ONLINE_DOWNLOAD_BUSY'):
            online.download(offer, work, trust)
    assert {path.name:path.read_bytes() for path in work.iterdir()} == before


def test_full_checkpoint_revalidated_without_redownload(payload, monkeypatch):
    raw, offer, work, trust = payload
    from bobbi_platform.online_partial import PartialDownload
    work.mkdir()
    with PartialDownload(work, offer, (offer['url'],), lambda: None) as partial:
        partial.request(offer['url'])
        partial.response(Response(raw, {'ETag':'"fixed-release"'}))
        partial.write(raw)
        assert partial.checkpoint()
    monkeypatch.setattr(online, '_open', lambda _: pytest.fail('Already downloaded complete content'))
    assert online.download(offer, work, trust).read_bytes() == raw


def test_resume_requires_only_remaining_disk_space(payload, monkeypatch):
    from types import SimpleNamespace
    raw, offer, work, trust = payload
    interrupt(monkeypatch, *payload)
    monkeypatch.setattr(online.shutil, 'disk_usage', lambda _: SimpleNamespace(
        free=len(raw)-len(raw)//2+16*1024*1024))
    monkeypatch.setattr(online, '_open', lambda _: ranged(raw,len(raw)//2))
    assert online.download(offer, work, trust).read_bytes() == raw


def test_special_cache_target_is_not_overwritten(payload, monkeypatch):
    raw, offer, work, trust = payload
    work.mkdir()
    target = work/'online.partial'
    target.mkdir()
    (target/'keep.txt').write_text('keep')
    monkeypatch.setattr(online, '_open', lambda _: pytest.fail('Unsafe cache starts network'))
    with pytest.raises(UpdateError, match='ONLINE_CACHE_PATH_INVALID'):
        online.download(offer, work, trust)
    assert (target/'keep.txt').read_text() == 'keep'


def test_resume_through_actual_install_menu_preserves_data_until_complete(entry, monkeypatch):
    from bobbi_platform import ce_install_ui as ui
    raw = (entry.env.root/'online.zip').read_bytes()
    attempts = []
    def fail(url):
        attempts.append(url)
        if len(attempts) == 1: return Dropped(raw,len(raw)//2)
        raise URLError('fixture mirror unavailable')
    monkeypatch.setattr(online, '_open', fail)
    ui.main(online=True)
    assert entry.env.installer._read() is None
    assert not entry.commands and not entry.env.calls
    assert (entry.env.user/'watching').read_text() == 'user-history'
    assert (entry.env.work/'downloads/online.partial').is_file()
    def resumed(url):
        assert headers()['Range'] == 'bytes={}-'.format(len(raw)//2)
        return ranged(raw,len(raw)//2)
    monkeypatch.setattr(online, '_open', resumed)
    ui.main(online=True)
    assert entry.env.installer._read()['phase'] == 'complete'
    assert entry.commands == ['RunScript(script.bobbi.setup)']
    assert (entry.env.user/'watching').read_text() == 'user-history'
    assert not list((entry.env.work/'downloads').iterdir())


def test_resume_headers_do_not_leak_into_nested_discovery(payload, monkeypatch):
    raw, offer, work, trust = payload
    interrupt(monkeypatch,*payload)
    def response(url):
        if url == online.OFFER_URL:
            assert headers() == {}
            return Response(json.dumps(offer).encode())
        before = headers()
        assert before['Range']
        assert online.latest() == offer
        assert headers() == before
        return ranged(raw,len(raw)//2)
    monkeypatch.setattr(online,'_open',response)
    assert online.download(offer,work,trust).read_bytes() == raw
    assert online._REQUEST_HEADERS.get() is None


def test_allowed_cdn_redirect_keeps_range_but_not_a_new_trust_anchor():
    from urllib.request import Request
    request = Request(offer_for(b'x')['url'],headers={'Range':'bytes=17-','If-Range':'"fixed-release"'})
    target = online._Redirects().redirect_request(request,None,302,'',{},
        'https://release-assets.githubusercontent.com/fixture?signature=fixture')
    assert target.get_header('Range') == 'bytes=17-'
    assert target.get_header('If-range') == '"fixed-release"'


def test_repeated_416_is_not_an_unbounded_retry(payload, monkeypatch):
    raw, offer, work, trust = payload
    interrupt(monkeypatch,*payload)
    seen = []
    def response(url):
        seen.append(headers())
        raise HTTPError(url,416,'fixture',{},None)
    monkeypatch.setattr(online,'_open',response)
    with pytest.raises(HTTPError): online.download(offer,work,trust)
    assert len(seen) == 2 and seen[0]['Range'] and seen[1] == {}
    assert not list(work.iterdir())


def test_certificate_failure_during_resume_is_not_hidden_by_fallback(payload, monkeypatch):
    import ssl
    raw, offer, work, trust = payload
    interrupt(monkeypatch,*payload)
    seen = []
    def response(url):
        seen.append(url)
        raise URLError(ssl.SSLCertVerificationError('fixture'))
    monkeypatch.setattr(online,'_open',response)
    with pytest.raises(URLError): online.download(offer,work,trust)
    assert len(seen) == 1 and not list(work.iterdir())

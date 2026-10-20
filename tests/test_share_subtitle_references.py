"""Official same-share reference schema + bounded offline candidate pipeline."""
import io
import json
from pathlib import Path
import sys
from threading import Event
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, build_opener

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.catalog', 'script.module.bobbi.platform'):
    sys.path.insert(0, str(ROOT / 'addons' / addon / 'lib'))
from bobbi_catalog.api import Client, ShareError
from bobbi_core import share_subtitles as sidecar

CHINESE = '1\n00:30:00,000 --> 00:30:02,000\n中文字幕，允许用户自行调轴\n'.encode()
BILINGUAL = CHINESE + b'English dialogue.\n'
VIDEO = 'Example.2025.S01E02.1080p.Group.mkv'
SHARE = dict(code='sfixture', password='abcd')


class Opener:
    def __init__(self, **changes):
        self.data = dict(fid='7', fn='Example.2025.S01E02.chs.srt', fs=len(CHINESE),
                         url={'url': 'https://cdn.115cdn.com/fixture.srt'})
        self.data.update(changes)
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return io.BytesIO(json.dumps(dict(state=True, data=self.data)).encode())


def client(**changes):
    opener = Opener(**changes)
    session = dict(app='os_linux', cookies=dict(UID='fixture', CID='fixture', SEID='fixture'),
                   user_agent='Fixture Agent')
    return Client(session=session, opener=opener), opener


def test_real_reference_method_uses_only_existing_same_share_endpoint():
    api, opener = client()
    result = api.resolve_reference(SHARE, '7', time.monotonic()+1)
    assert result == dict(fid='7', name='Example.2025.S01E02.chs.srt', size=len(CHINESE),
                         resolved='https://cdn.115cdn.com/fixture.srt|User-Agent=Fixture%20Agent')
    request, timeout = opener.calls[0]
    parsed = urlsplit(request.full_url)
    assert (parsed.hostname, parsed.path) == ('proapi.115.com', '/os_linux/2.0/share/downurl')
    assert parse_qs(parsed.query) == dict(share_code=['sfixture'], receive_code=['abcd'],
                                        file_id=['7'], dl=['1'], app_ver=['36.2.28'])
    assert len(opener.calls) == 1 and 0 < timeout <= 1
    assert 'Cookie' not in result['resolved']


@pytest.mark.parametrize('fid', ['', None, 7, '7/8', '7'*33, '７'])
def test_reference_input_is_exact_numeric_and_bounded(fid):
    api, opener = client()
    with pytest.raises(ShareError, match='invalid_locator'):
        api.resolve_reference(SHARE, fid, time.monotonic()+1)
    assert not opener.calls


@pytest.mark.parametrize('changes,error', [
    ({'fid': '8'}, 'identity_changed'),
    ({'fn': '../foreign.srt'}, 'invalid_response'),
    ({'fn': 'foreign\\sub.srt'}, 'invalid_response'),
    ({'fn': 'sub\x7f.srt'}, 'invalid_response'),
    ({'fn': 'video.mkv'}, 'invalid_response'),
    ({'fn': 'image.sup'}, 'invalid_response'),
    ({'fn': 'subs.zip'}, 'invalid_response'),
    ({'fn': 'srt'}, 'invalid_response'),
    ({'fn': 'x'*1025+'.srt'}, 'invalid_response'),
    ({'fs': 0}, 'invalid_response'),
    ({'fs': -1}, 'invalid_response'),
    ({'fs': True}, 'invalid_response'),
    ({'fs': 2*1024*1024+1}, 'invalid_response'),
    ({'fs': '1.5'}, 'invalid_response'),
    ({'url': 'https://foreign.invalid/sub.srt'}, 'invalid_locator'),
    ({'url': 'https://cdn.115cdn.com/sub|Cookie=secret'}, 'invalid_locator'),
    ({'url': 'https://cdn.115cdn.com/sub#fragment'}, 'invalid_locator'),
    ({'url': 'https://user@cdn.115cdn.com/sub'}, 'invalid_locator'),
])
def test_reference_response_rejects_changed_identity_nontext_or_unbounded_metadata(changes, error):
    api, opener = client(**changes)
    with pytest.raises(ShareError, match=error):
        api.resolve_reference(SHARE, '7', time.monotonic()+1)
    assert len(opener.calls) == 1


def test_reference_supports_decimal_size_and_plain_cdn_url():
    api, _ = client(fs=str(len(CHINESE)), url='https://fixture.115.com/sub.srt')
    assert api.resolve_reference(SHARE, '7', time.monotonic()+1)['size'] == len(CHINESE)


def test_cancelled_reference_does_not_request_cloud():
    api, opener = client()
    stop = Event()
    stop.set()
    with pytest.raises(ShareError, match='cancelled'):
        api.resolve_reference(SHARE, '7', time.monotonic()+1, stop)
    assert not opener.calls


@pytest.mark.parametrize('cancel', [False, True])
def test_real_http_drip_body_observes_absolute_deadline_and_cancellation(cancel):
    stopped, cancellation = Event(), Event()
    raw = json.dumps(dict(state=True, data=dict(list=[]))).encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            for index, byte in enumerate(raw):
                if stopped.wait(.03):
                    break
                try:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                except OSError:
                    break
                if cancel and index == 2:
                    cancellation.set()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    class LocalOpener:
        def open(self, request, timeout):
            # Dummy API request never leaves loopback; no credentials forwarded.
            return build_opener(ProxyHandler({})).open('http://127.0.0.1:%d/' % server.server_port, timeout=timeout)
    api, _ = client()
    api.opener = LocalOpener()
    start = time.monotonic()
    try:
        with pytest.raises(ShareError, match='cancelled' if cancel else 'deadline'):
            api.get('/share/snap', SHARE, {}, start+.25, cancellation)
        assert time.monotonic() - start < 1.5
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        worker.join(2)


class API:
    def __init__(self, refs=None, directory=None):
        self.refs, self.directory = refs or {}, directory or []
        self.reference_calls, self.directory_calls, self.resolve_calls = [], [], []
    def resolve_reference(self, share, fid, deadline, cancelled):
        assert share == SHARE and not cancelled.is_set()
        assert 0 < deadline - time.monotonic() <= 10
        self.reference_calls.append(fid)
        value = self.refs.get(fid, ShareError('share_unavailable'))
        if isinstance(value, Exception):
            raise value
        return dict(value)
    def list_directory(self, share, parent, offset, limit, deadline, cancelled):
        self.directory_calls.append((parent, offset))
        return dict(rows=self.directory[offset:offset+limit], total=len(self.directory))
    def resolve(self, share, entry, deadline):
        self.resolve_calls.append(entry['fid'])
        return 'https://cdn.115cdn.com/' + entry['fid'] + '|User-Agent=Fixture%20Agent'


def entry(fid='7', name='中文字幕.srt', raw=CHINESE):
    return dict(fid=fid, name=name, size=len(raw), resolved='https://cdn.115cdn.com/'+fid+'|User-Agent=Fixture%20Agent')


def fetch(tmp_path, api, parent='', refs=('7',), transport=None, account=lambda: True, cancelled=lambda:False,
          scope=None):
    row = dict(name=VIDEO, size=999, parent=parent, share=SHARE, subtitle_fids=list(refs))
    def download(url, deadline, stopped, limit, **kwargs):
        assert kwargs == dict(headers={'User-Agent':'Fixture Agent'}, mode='share_cdn')
        assert limit == 2*1024*1024 and not stopped()
        return CHINESE
    return sidecar.fetch_candidate(dict(title=VIDEO, size=999),
        dict(mode='series', title='Example', season=1, episode=2, duration=60), time.monotonic()+30,
        cancelled, api, account, selected=lambda _:row, transport=transport or download, root=tmp_path/'subs',
        account_scope=scope)


@pytest.mark.parametrize('parent', ['', '999'])
def test_explicit_reference_works_without_parent_or_outside_current_parent(tmp_path, parent):
    api = API(refs={'7':entry()})
    result = fetch(tmp_path, api, parent=parent)
    assert Path(result['file']['path']).read_bytes() == CHINESE
    assert result['state'] == 'candidate'  # Never synchronized/proven playback.
    assert api.reference_calls == ['7'] and not api.directory_calls and not api.resolve_calls


def test_rejected_reference_falls_back_to_directory_without_cloud_tasks(tmp_path):
    api = API(directory=[entry('8', VIDEO[:-4]+'.chs.srt')])
    result = fetch(tmp_path, api, parent='9')
    assert Path(result['file']['path']).read_bytes() == CHINESE
    assert api.reference_calls == ['7'] and api.directory_calls == [('9',0)]


def test_three_reference_and_three_download_budget_with_deduplication(tmp_path):
    api = API(refs={str(i):entry(str(i)) for i in range(1,30)})
    downloaded = []
    def download(url, *args, **kwargs):
        downloaded.append(url)
        return CHINESE
    fetch(tmp_path, api, refs=('1','1',*[str(i) for i in range(2,30)]), transport=download)
    assert api.reference_calls == ['1','2','3'] and len(downloaded) == 3
    assert not api.directory_calls


def test_actual_bilingual_text_outranks_a_bilingual_filename(tmp_path):
    api = API(refs={'7':entry(name='虚标双语.srt'), '8':entry('8','中文字幕.srt',BILINGUAL)})
    result = fetch(tmp_path, api, refs=('7','8'),
                   transport=lambda url,*a,**k: BILINGUAL if url.endswith('/8') else CHINESE)
    assert result['bilingual'] is True
    assert Path(result['file']['path']).read_bytes() == BILINGUAL


@pytest.mark.parametrize('name', ['Example.S01E03.chs.srt', 'Example.S02.chs.srt',
    'Example.Season.2.chs.srt', 'Example - 03.chs.srt', 'Example.extended.chs.srt',
    'Example.forced.srt', 'Example.commentary.srt', 'Example.chs.sup'])
def test_explicit_does_not_authorize_conflicting_episode_edition_or_nontext(tmp_path, name):
    api = API(refs={'7':entry(name=name)})
    with pytest.raises(sidecar.Stopped, match='NOT_FOUND'):
        fetch(tmp_path, api, transport=lambda *a,**k: pytest.fail('must not download mismatched metadata'))


def test_weak_anime_release_can_match_explicit_episode_when_context_supplies_season():
    context = dict(mode='series', title='Example', season=1, episode=2)
    assert sidecar.matches('[Group] Example - 02.mkv', 'Example.S01E02.chs.srt', True, context)
    assert not sidecar.matches('[Group] Example - 02.mkv', 'Example - 03.chs.srt', True, context)


def test_explicit_movie_year_contradiction_is_rejected_but_generic_filename_is_allowed():
    context = dict(mode='movie', title='Example', year=2025, tmdb=1)
    assert not sidecar.matches('Example.2025.mkv', 'Example.1999.chs.srt', True, context)
    assert sidecar.matches('Example.2025.mkv', '中文字幕.srt', True, context)


def test_short_read_cannot_publish(tmp_path):
    api = API(refs={'7':entry()})
    with pytest.raises(sidecar.Stopped, match='NOT_FOUND'):
        fetch(tmp_path, api, transport=lambda *a,**k: CHINESE[:-1])
    assert not (tmp_path/'subs').exists()


@pytest.mark.parametrize('stage', ['reference', 'download'])
def test_late_account_switch_never_publishes(tmp_path, stage):
    current = [True]
    api = API(refs={'7':entry()})
    if stage == 'reference':
        original = api.resolve_reference
        def resolve(*args):
            result = original(*args)
            current[0] = False
            return result
        api.resolve_reference = resolve
    def download(*args, **kwargs):
        current[0] = False
        return CHINESE
    with pytest.raises(sidecar.Stopped, match='ACCOUNT_CHANGED'):
        fetch(tmp_path, api, account=lambda:current[0], transport=download)
    assert not (tmp_path/'subs').exists()


def test_expired_deadline_never_resolves_or_downloads(tmp_path, monkeypatch):
    api = API(refs={'7':entry()})
    clock = [100.0]
    monkeypatch.setattr(sidecar.time, 'monotonic', lambda:clock[0])
    original = api.resolve_reference
    def resolve(*args):
        result = original(*args)
        clock[0] += 11
        return result
    api.resolve_reference = resolve
    with pytest.raises(sidecar.Stopped, match='TIMEOUT'):
        fetch(tmp_path, api, transport=lambda *a,**k:pytest.fail('deadline expired'))
    assert not (tmp_path/'subs').exists()


def test_same_share_candidate_retains_a_copied_authenticated_account_scope(tmp_path):
    scope = dict(account_id='115:'+'a'*64, epoch=1, authenticated=True)
    result = fetch(tmp_path, API(refs={'7':entry()}), scope=scope)
    assert result['account_scope'] == scope and result['account_scope'] is not scope
    scope['epoch'] = 2
    assert result['account_scope']['epoch'] == 1


@pytest.mark.parametrize('stage', ['account', 'cancel'])
def test_switch_during_local_publication_cannot_return_a_candidate(tmp_path, monkeypatch, stage):
    from bobbi_core import subtitle_candidates
    current, cancelled = [True], [False]
    original = subtitle_candidates.publish
    def publish(*args):
        result = original(*args)
        if stage == 'account':
            current[0] = False
        else:
            cancelled[0] = True
        return result
    monkeypatch.setattr(subtitle_candidates, 'publish', publish)
    with pytest.raises(sidecar.Stopped, match='ACCOUNT_CHANGED' if stage == 'account' else 'CANCELLED'):
        fetch(tmp_path, API(refs={'7':entry()}), account=lambda:current[0], cancelled=lambda:cancelled[0],
              scope=dict(account_id='115:'+'a'*64, epoch=1, authenticated=True))


@pytest.mark.parametrize('scope', [{}, {'account_id':'', 'epoch':1, 'authenticated':False}])
def test_supplied_invalid_account_scope_cannot_start_subtitle_io(tmp_path, scope):
    from bobbi_platform.account_manager import AccountError
    api = API(refs={'7':entry()})
    with pytest.raises(AccountError, match='ACCOUNT_SCOPE_INVALID'):
        fetch(tmp_path, api, scope=scope)
    assert not api.reference_calls and not api.directory_calls

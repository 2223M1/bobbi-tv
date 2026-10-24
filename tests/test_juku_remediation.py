"""J-02/03/04 controls: real SQLite/provider/coordinator and local HTTP only."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from types import SimpleNamespace, ModuleType
import time
from urllib.request import Request, build_opener, ProxyHandler

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT / 'addons' / addon / 'lib'))
from bobbi_core import juku_api as api, juku_catalog as cat, juku_refresh as refresh
from bobbi_core.juku_snapshot import SnapshotReader
from bobbi_core.progressive_search import ProgressiveSearch
from bobbi_core.search_completion import SearchCompletion, SearchResults
from bobbi_core.source_list_session import SourceListSession
from bobbi_core.provider_cache import ProviderResultCache


@pytest.fixture(autouse=True)
def offline_protocol_endpoint(monkeypatch):
    monkeypatch.setattr(api, 'BASE', 'https://catalog.example.invalid')


def movie(index=1):
    return dict(tmdbId=101, typeId=1, year=2024, title='Audit Movie', id=1, vodId=1,
        links=[dict(url='https://115.com/s/sabcdef', fileId=str(index),
                    fileName='Audit.Movie.2024.Version%d.1080p.mkv' % index,
                    fileSize=123456+index, parentFolderId='8')])


SPEC = dict(tmdb_id=101, mode='movies', year=2024, aliases=['Audit Movie'])


def envelope(movies=None, code='audit', version=1, **library):
    movies = [movie()] if movies is None else movies
    return dict(success=True, data=dict(library=dict(shareCode=code, version=version,
        itemCount=len(movies), isPublic=True, **library), movies=movies))


class Catalogue:
    def __init__(self, body=None, pages=None):
        self.body = envelope() if body is None else body
        self.pages = pages or {1: dict(items=[dict(shareCode='audit', version=1)])}
        self.requests = []
        self.fail = {}

    def get(self, path, params, deadline, **options):
        self.requests.append((path, params))
        if path in self.fail:
            raise api.JukuError(self.fail[path])
        if path == '/shared-libraries/public':
            return self.pages[params['page']]
        raw = json.dumps(self.body, ensure_ascii=False).encode()
        Path(options['destination']).write_bytes(raw)
        return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def step(tmp_path, client, cancelled=lambda: False):
    return cat.refresh_one(state=tmp_path, deadline=time.monotonic()+10,
                           cancelled=cancelled, client=client)


def seed(tmp_path, code='audit'):
    value = movie()
    row = cat._row(value, value['links'][0], 'shared:' + code)
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        cache.replace_library(code, 0, [row])
    return row


def local(tmp_path):
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        return cache.local(cat._spec(SPEC))


@pytest.mark.parametrize('route,expected', [('complete', None), ('short', 'NETWORK_SHORT_READ'),
                                         ('unknown', None), ('bad', 'RESPONSE_SCHEMA')])
def test_http_message_completeness(route, expected):
    body = json.dumps(dict(success=True, data=dict(items=[]))).encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            raw = b'{bad' if route == 'bad' else body
            self.send_response(200)
            if route != 'unknown':
                self.send_header('Content-Length', str(len(raw) + (19 if route == 'short' else 0)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    receiver = api.Client.__new__(api.Client)
    receiver.cancelled = lambda: False
    try:
        request = Request('http://127.0.0.1:%d/' % server.server_port)
        if expected:
            with pytest.raises(api.JukuError, match=expected):
                receiver._receive(build_opener(ProxyHandler({})), request, time.monotonic()+2, 1024)
        else:
            assert receiver._receive(build_opener(ProxyHandler({})), request, time.monotonic()+2, 1024) == dict(items=[])
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def test_body_not_cut_in_half_for_unused_edge(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(api.time, 'monotonic', lambda: clock[0])
    client = api.Client.__new__(api.Client)
    client.cancelled, client.requests, client.openers = lambda: False, 0, ['first', 'second']
    seen = []
    def receive(opener, request, deadline, max_bytes):
        seen.append((opener, deadline-clock[0]))
        clock[0] += 8.311
        api.guard(deadline)
        return {'complete': True}
    client._receive = receive
    assert client._request('GET', '/shared-libraries/detail/audit', {}, b'', None, None,
                           112.0, api.MAX_SNAPSHOT_JSON) == {'complete': True}
    assert seen == [('first', 12.0)]


def test_actual_client_twelve_second_refresh_phases_complete(tmp_path, monkeypatch):
    """Real get/_request/refresh/SQLite with a controlled 8.311s body delay."""
    clock = [1000.0]
    monkeypatch.setattr(api.time, 'monotonic', lambda: clock[0])
    attempts = []
    class Transport(api.Client):
        def __init__(self):
            self.cancelled, self.requests, self.openers = lambda: False, 0, ['first', 'second']
        def _session(self, *args, **kwargs):
            return None, None
        def _receive(self, opener, request, deadline, max_bytes, destination=None):
            delay = 8.311 if destination else .1
            attempts.append((opener, deadline-clock[0], bool(destination)))
            clock[0] += delay
            api.guard(deadline)
            if destination:
                raw = json.dumps(envelope()).encode()
                Path(destination).write_bytes(raw)
                return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            return dict(items=[dict(shareCode='audit', version=1)])
    client = Transport()
    states = []
    for _ in range(4):
        states.append(cat.refresh_one(state=tmp_path, deadline=clock[0]+12, client=client)['state'])
    assert states == ['DIRECTORY_READY', 'FETCHED', 'VALIDATED', 'UPDATED']
    assert attempts == [('first', 12, False), ('first', 12, True)]
    assert len(local(tmp_path)) == 1


@pytest.mark.parametrize('short', [False, True])
def test_download_stage_requires_complete_length_and_cleans_partial(tmp_path, short):
    raw = json.dumps(envelope()).encode()
    class Response(io.BytesIO):
        headers = {'Content-Length': str(len(raw)+(1 if short else 0))}
    receiver = api.Client.__new__(api.Client)
    receiver.cancelled = lambda: False
    opener = SimpleNamespace(open=lambda *args, **kwargs: Response(raw))
    target = tmp_path / 'incoming-snapshot.json'
    if short:
        with pytest.raises(api.JukuError, match='NETWORK_SHORT_READ'):
            receiver._receive(opener, Request(api.BASE), time.monotonic()+2, 1024, target)
        assert not target.exists()
    else:
        receipt = receiver._receive(opener, Request(api.BASE), time.monotonic()+2, 1024, target)
        assert receipt == dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        assert target.read_bytes() == raw
    assert not target.with_name(target.name+'.part').exists()


def test_second_edge_only_after_failure_with_original_deadline(monkeypatch):
    client = api.Client.__new__(api.Client)
    client.cancelled, client.requests, client.openers = lambda: False, 0, ['first', 'second']
    deadline = time.monotonic()+12
    seen = []
    def receive(opener, request, end, limit):
        seen.append(end)
        if opener == 'first':
            raise api.JukuError('NETWORK_SHORT_READ')
        return dict(items=[])
    client._receive = receive
    assert client._request('GET', '/videos/search', {}, b'', None, None, deadline) == dict(items=[])
    assert seen == [deadline, deadline]


def test_completed_snapshot_checkpoints_not_partial_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, 'IMPORT_BATCH', 2)
    seed(tmp_path)
    client = Catalogue(envelope([movie(i) for i in range(2, 7)]))
    assert step(tmp_path, client)['state'] == 'DIRECTORY_READY'
    assert step(tmp_path, client)['state'] == 'FETCHED'
    assert step(tmp_path, client)['state'] == 'IMPORTING'
    assert [row['fid'] for row in local(tmp_path)] == ['1']
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        checkpoint = refresh._read(cache, 'snapshot-job')['cursor']
        assert checkpoint['count'] == 2
    assert step(tmp_path, client)['state'] == 'IMPORTING'
    assert step(tmp_path, client)['state'] == 'VALIDATED'
    assert [row['fid'] for row in local(tmp_path)] == ['1']
    assert step(tmp_path, client)['state'] == 'UPDATED'
    assert {row['fid'] for row in local(tmp_path)} == {'2', '3', '4', '5', '6'}
    assert len([path for path, _ in client.requests if '/detail/' in path]) == 1
    assert not (tmp_path / 'incoming-snapshot.json').exists()


def test_cancel_preserves_last_committed_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, 'IMPORT_BATCH', 1)
    seed(tmp_path)
    client = Catalogue(envelope([movie(2), movie(3)]))
    for _ in range(3):
        step(tmp_path, client)
    with pytest.raises(api.JukuError, match='CANCELLED'):
        step(tmp_path, client, cancelled=lambda: True)
    assert [row['fid'] for row in local(tmp_path)] == ['1']
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        assert refresh._read(cache, 'snapshot-job')['cursor']['count'] == 1
    for _ in range(3):
        result = step(tmp_path, client)
    assert result['state'] == 'UPDATED'
    assert {row['fid'] for row in local(tmp_path)} == {'2', '3'}


def test_cancel_inside_batch_rolls_back_rows_and_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, 'IMPORT_BATCH', 2)
    client = Catalogue(envelope([movie(i) for i in range(1, 5)]))
    step(tmp_path, client)
    step(tmp_path, client)
    step(tmp_path, client)
    original = cat._row
    def cancel_on_four(work, link, origin, main=False):
        if link['fileId'] == '4':
            raise api.JukuError('CANCELLED')
        return original(work, link, origin, main)
    monkeypatch.setattr(cat, '_row', cancel_on_four)
    with pytest.raises(api.JukuError, match='CANCELLED'):
        step(tmp_path, client)
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        assert refresh._read(cache, 'snapshot-job')['cursor']['count'] == 2
        assert cache.db.execute('SELECT COUNT(*) FROM snapshot_rows').fetchone()[0] == 2
    monkeypatch.setattr(cat, '_row', original)
    assert step(tmp_path, client)['state'] == 'IMPORTING'
    assert step(tmp_path, client)['state'] == 'VALIDATED'
    assert step(tmp_path, client)['state'] == 'UPDATED'


def test_upstream_removal_invalidates_old_selection(tmp_path, monkeypatch):
    row = seed(tmp_path)
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        spec = cat._spec(SPEC)
        cache.remember([row], spec)
    step(tmp_path, Catalogue(pages={1:dict(items=[])}))
    with pytest.raises(ValueError, match='withdrawn'):
        cat.selected('am6bjuku://'+row['key'], 'juku:'+row['key'], row['name'], row['size'],
                     spec['media_key'], state=tmp_path)


def test_oversized_stage_is_dropped_so_siblings_can_progress(tmp_path, monkeypatch):
    seed(tmp_path)
    monkeypatch.setattr(refresh, 'MAX_STAGED_ROWS', 1)
    client = Catalogue(envelope([movie(2)]))
    step(tmp_path, client)
    step(tmp_path, client)
    with pytest.raises(ValueError, match='quota'):
        step(tmp_path, client)
    assert [row['fid'] for row in local(tmp_path)] == ['1']
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        assert refresh._read(cache, 'snapshot-job') is None


def test_bad_final_envelope_never_replaces_success(tmp_path):
    seed(tmp_path)
    body = envelope([movie(2)])
    body['success'] = False
    client = Catalogue(body)
    step(tmp_path, client)
    step(tmp_path, client)
    with pytest.raises(ValueError, match='snapshot envelope'):
        step(tmp_path, client)
    assert [row['fid'] for row in local(tmp_path)] == ['1']
    assert not (tmp_path / 'incoming-snapshot.json').exists()


@pytest.mark.parametrize('broken', [b'{"success":true,"success":true,"data":{}}',
    b'{"success":true,"data":{"library":{},"movies":[],}}',
    b'{"success":true,"data":{"library":{},"movies":[{},]}}'])
def test_snapshot_rejects_ambiguous_json(broken):
    reader = SnapshotReader(io.BytesIO(broken), None, lambda: None)
    with pytest.raises(ValueError):
        while reader.next_movie() is not None:
            pass


def test_snapshot_arbitrary_field_order_unicode_resume():
    raw = json.dumps(dict(data=dict(movies=[dict(title='猫汤'), dict(title='企鹅')], library={'shareCode':'a'}),
                          success=True), ensure_ascii=False).encode()
    reader = SnapshotReader(io.BytesIO(raw), None, lambda: None)
    assert reader.next_movie()['title'] == '猫汤'
    reader = SnapshotReader(io.BytesIO(raw), reader.state, lambda: None)
    assert reader.next_movie()['title'] == '企鹅'
    assert reader.next_movie() is None
    assert reader.state['count'] == 2


def test_stale_snapshot_retained_and_explicitly_marked(tmp_path, monkeypatch):
    seed(tmp_path)
    with contextlib.closing(cat.Cache(tmp_path)) as cache, cache.db:
        cache.db.execute('UPDATE libraries SET at=?', (time.time()-8*cat.DAY,))
    monkeypatch.setattr(cat, '_account', lambda client=None: '')
    class Empty:
        def get(self, *args):
            return dict(items=[], pagination=dict(total=0))
    rows = cat.search(SPEC, time.monotonic()+3, lambda: False, state=tmp_path, client=Empty())
    assert len(rows) == 1 and rows.completion.state == 'PARTIAL'
    assert rows.completion.stale == 1 and rows.completion.snapshot_age >= 8*cat.DAY
    assert not rows[0]['_verified']


@pytest.mark.parametrize('code,remaining', [('HTTP_503', 1), ('HTTP_403', 0), ('HTTP_404', 0)])
def test_failure_vs_authoritative_withdrawal(tmp_path, code, remaining):
    seed(tmp_path)
    client = Catalogue()
    step(tmp_path, client)
    client.fail['/shared-libraries/detail/audit'] = code
    with pytest.raises(api.JukuError, match=code):
        step(tmp_path, client)
    assert len(local(tmp_path)) == remaining


def test_complete_directory_withdrawal_hides_but_keeps_prior_bytes(tmp_path):
    seed(tmp_path)
    assert step(tmp_path, Catalogue(pages={1:dict(items=[])}))['state'] == 'DIRECTORY_READY'
    assert not local(tmp_path)
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        assert cache.db.execute('SELECT COUNT(*) FROM shared_rows').fetchone()[0] == 1


def test_pagination_limit_reports_truncation_never_revokes_unseen(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, 'PAGE_SIZE', 2)
    monkeypatch.setattr(refresh, 'MAX_PAGES', 2)
    seed(tmp_path, 'unseen')
    client = Catalogue(pages={page:dict(items=[dict(shareCode=str(i), version=1)
        for i in range(page*2, page*2+2)], pagination=dict(total=5)) for page in (1, 2)})
    assert step(tmp_path, client)['state'] == 'DIRECTORY_PROGRESS'
    result = step(tmp_path, client)
    assert result['state'] == 'DIRECTORY_READY' and result['truncated'] is True
    assert len(local(tmp_path)) == 1


def test_failed_library_does_not_starve_sibling(tmp_path):
    client = Catalogue(pages={1:dict(items=[dict(shareCode='a',version=1),dict(shareCode='b',version=1)])})
    client.fail['/shared-libraries/detail/a'] = 'HTTP_503'
    step(tmp_path, client)
    with pytest.raises(api.JukuError, match='HTTP_503'):
        step(tmp_path, client)
    client.body = envelope(code='b')
    assert step(tmp_path, client)['code'] == 'b'


@pytest.mark.parametrize('failed,expected', [(True, 'PARTIAL'), (False, 'COMPLETE')])
def test_local_first_and_final_search_receipt(tmp_path, monkeypatch, failed, expected):
    seed(tmp_path)
    monkeypatch.setattr(cat, '_account', lambda client=None: '')
    received = []
    class Remote:
        def get(self, *args):
            assert received and len(received[0]) == 1  # Published before any remote call.
            if failed:
                raise api.JukuError('HTTP_503')
            return dict(items=[], pagination=dict(total=0))
    result = cat.search(SPEC, time.monotonic()+3, lambda: False, state=tmp_path,
                        client=Remote(), publish=received.append)
    assert len(result) == 1 and result.completion.state == expected
    assert result[0]['key'] == received[0][0]['key']
    assert result.completion.failed == int(failed)


def test_real_provider_and_coordinator_keep_receipt_and_focus(tmp_path, monkeypatch):
    seed(tmp_path)
    monkeypatch.setattr(cat, '_account', lambda client=None: '')
    module_path = ROOT / 'addons/plugin.video.bobbi/lib/clients/juku_provider.py'
    spec = importlib.util.spec_from_file_location('juku_provider_under_test', module_path)
    provider = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provider)
    monkeypatch.setattr(provider, 'enabled', lambda: True)
    modules = {
        'lib.domain.torrent': dict(TorrentStream=lambda **kw: SimpleNamespace(**kw)),
        'lib.utils.kodi.utils': dict(kodilog=lambda value: None),
    }
    class Builder:
        def __init__(self, rows): pass
        def extract_codec_hdr(self): return self
        def filter_by_quality(self): return self
    modules['lib.utils.general.processors'] = dict(PreProcessBuilder=Builder)
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    session = SourceListSession(dict(tmdb=101), lambda rows: rows)
    class Remote:
        def get(self, *args):
            assert len(session.entries) == 1
            key = next(iter(session.entries))
            session.focus(key, 4)
            raise api.JukuError('HTTP_503')
    original = cat.search
    def routed(*args, **kwargs):
        return original(*args, state=tmp_path, client=Remote(), **kwargs)
    monkeypatch.setattr(cat, 'search', routed)
    manager = ProgressiveSearch(session, None, lambda rows: rows)
    manager.deadline = time.monotonic()+3
    manager.lease = SimpleNamespace(retain=lambda: None, release=lambda *args: None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        manager.pool = pool
        future = manager.submit_task('Juku', 'juku', provider.find_sources,
            dict(tmdb_id=101), 'movies', None, None, 2024, ['Audit Movie'], None,
            manager.deadline, Event(), _progressive=True)
        future.result(3)
    state = session.status()['providers']['juku:1']
    assert state['state'] == 'PARTIAL'
    assert state['completion']['failed'] == 1
    assert len(session.entries) == 1 and session.focus_position == 4
    assert session.focus_key == next(iter(session.entries))


def test_account_verification_epoch_not_cookie():
    a = SimpleNamespace(account_scope=dict(account_id='115:a', epoch=3, authenticated=True), cookie='old')
    b = SimpleNamespace(account_scope=dict(a.account_scope), cookie='renewed')
    assert cat._account(a) == cat._account(b)
    b.account_scope['epoch'] = 4
    assert cat._account(a) != cat._account(b)
    assert cat._account(SimpleNamespace(cookie='legacy-no-scope')) == ''


def test_progressive_partial_never_overwrites_provider_success():
    values = {}
    backend = SimpleNamespace(get=lambda key: values.get(key),
        set=lambda key, value, ttl: values.__setitem__(key, value))
    normal = ProviderResultCache(backend, 'scope', hours=1)
    old = SimpleNamespace(title='old', infoHash='1'*40)
    new = SimpleNamespace(title='new', infoHash='2'*40)
    normal.put('provider', 'name', [old])
    session = SourceListSession(dict(tmdb=101), lambda rows: rows)
    manager = ProgressiveSearch(session, None, lambda rows: rows,
        result_cache=ProviderResultCache(backend, 'scope', hours=1, refresh=True))
    manager.deadline = time.monotonic()+3
    manager.lease = SimpleNamespace(retain=lambda: None, release=lambda *args: None)
    partial = SearchResults([new], SearchCompletion(planned=2, succeeded=1, failed=1))
    def produce(publish):
        publish(SearchResults([new], SearchCompletion(planned=2, succeeded=1, skipped=1)))
        return partial
    with ThreadPoolExecutor(max_workers=1) as pool:
        manager.pool = pool
        manager.submit_task('name', 'provider', produce, _progressive=True).result(3)
    assert normal.get('provider', 'name') == [old]
    assert session.status()['providers']['provider:1']['state'] == 'PARTIAL'


def test_selection_and_forced_timeout_keep_snapshot_receipt():
    source = SimpleNamespace(title='selected', infoHash='1'*40)
    session = SourceListSession(dict(tmdb=101), lambda rows: rows)
    receipt = SearchCompletion(planned=2, succeeded=1, skipped=1, stale=1, snapshot_age=700000)
    assert session.publish(session.epoch, 'juku', [source], state='RUNNING', completion=receipt)
    assert session.publish(session.epoch, 'juku', state='TIMEOUT', error='SEARCH_DEADLINE')
    assert session.status()['providers']['juku']['completion']['snapshot_age'] == 700000
    assert session.capture(session.epoch, session.key(source)) == source
    assert not session.publish(session.epoch, 'later', [SimpleNamespace(title='new', infoHash='2'*40)])


def test_explicit_withdrawal_cannot_use_cached_main_detail(tmp_path):
    path = '/videos/1'
    original = dict(id=1, tmdbId=101, typeId=1)
    class Withdrawn:
        def get(self, *args):
            raise api.JukuError('HTTP_404')
    with contextlib.closing(cat.Cache(tmp_path)) as cache:
        key = hashlib.sha256(cat._encode([path, {}]).encode()).hexdigest()
        cache.put_raw(key, original)
        with cache.db:
            cache.db.execute('UPDATE raw_cache SET at=?', (time.time()-2*cat.DAY,))
        with pytest.raises(api.JukuError, match='HTTP_404'):
            cat._fetch(cache, Withdrawn(), path, {}, time.monotonic()+2, lambda: False, lambda event: None)
        assert cache.get_raw(key, cat.STALE) is None


def test_snapshot_utf8_read_boundary_and_record_budget(monkeypatch):
    body = envelope([dict(links=[], title='x'*65450 + '猫汤'*100)])
    raw = json.dumps(body, ensure_ascii=False).encode()
    reader = SnapshotReader(io.BytesIO(raw), None, lambda: None)
    assert reader.next_movie()['title'].endswith('猫汤')
    assert reader.next_movie() is None
    import bobbi_core.juku_snapshot as parser
    monkeypatch.setattr(parser, 'MAX_VALUE', 100)
    reader = SnapshotReader(io.BytesIO(raw), None, lambda: None)
    with pytest.raises(ValueError, match='budget|oversized'):
        reader.next_movie()


def test_python38_pool_shutdown_keeps_nonblocking_cancellation():
    session = SourceListSession(dict(tmdb=101), lambda rows: rows)
    manager = ProgressiveSearch(session, None, lambda rows: rows)
    calls = []
    class Pool38:
        def shutdown(self, wait):
            calls.append(wait)
    manager.pool = Pool38()
    manager.cancel()
    assert calls == [False] and manager.cancelled.is_set()

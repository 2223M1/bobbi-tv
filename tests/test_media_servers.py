"""Offline protocol fixtures through the production Registry/index/Range/history.

No running server/device or real token is used. Experimental, not device QA.
"""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.error import HTTPError

_PRIVATE_BASELINE = str(Path(__file__).resolve().parent / 'private_baseline')
_PLUGIN_ROOT = str(Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi')
for _extra_path in (_PRIVATE_BASELINE, _PLUGIN_ROOT):
    if _extra_path not in sys.path:
        sys.path.append(_extra_path)

import pytest

from bobbi_core.file_ref import from_selected, validate, identity
from bobbi_core.library_contract import Source, LibraryError, validate_source
from bobbi_core.server_ref import parts, resumable, file_id
from bobbi_platform import server_plex, server_emby, server_http, pan_ui, server_ui
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import scope, scope_key, PanError, PanAccounts
from bobbi_platform.pan_history import prepare_history_play
from bobbi_platform.pan_service import PanService
from bobbi_platform.server_accounts import Accounts, PlexBinding
from test_ce2096_pan_stream import Upstream, read
from test_ce2097_file_history import database, history, playback
from test_ce2096_pan_playback import entry
from test_media_library_index import command

BASE = 'https://server.example/pms'
SETTINGS = dict(location=BASE, token='fixture-server-secret', user_token='fixture-user-secret')


class PlexWire:
    base = BASE
    operation = None

    def __init__(self):
        self.calls, self.before = [], lambda: None
        self.server, self.user = 'machine1', '77'
        self.media = [dict(id='12', Part=[dict(id='123', key='/library/parts/123/456/file.mkv',
            size=8, file='/movies/Movie.2020.mkv')])]

    def budget(self, seconds):
        return nullcontext()

    def headers(self):
        return {'User-Agent': server_http.USER_AGENT, 'X-Plex-Token': SETTINGS['token']}

    def request(self, path, **kwargs):
        self.calls.append((path, deepcopy(kwargs)))
        if self.operation:
            self.operation.consume_request()
        self.before()
        if self.operation:
            self.operation.check()
        if path == '/api/v2/user':
            return dict(id=int(self.user))
        if path == '/api/v2/resources':
            return [dict(clientIdentifier=self.server, accessToken=SETTINGS['token'], provides='server')]
        if path == '/identity':
            return dict(MediaContainer=dict(machineIdentifier=self.server))
        if path == '/library/sections':
            return dict(MediaContainer=dict(Directory=[dict(key='1', title='Movies', type='movie')]))
        if path == '/library/sections/1/all':
            return dict(MediaContainer=dict(librarySectionID=1, totalSize=1, offset=0,
                Metadata=[dict(ratingKey='9', title='Movie')]))
        assert path == '/library/metadata/9'
        return dict(MediaContainer=dict(Metadata=[dict(ratingKey='9', Media=deepcopy(self.media))]))


@pytest.fixture
def server(tmp_path):
    values = deepcopy(SETTINGS)
    binding = PlexBinding(lambda: deepcopy(values), lambda: True)
    accounts = Accounts(tmp_path, binding)
    wire = PlexWire()
    class Client(server_plex.Client):
        def __init__(self, saved):
            super().__init__(saved, wire)
        def verify(self):
            return super().verify(wire)
    expected = accounts.register('plex', 'Plex', client_factory=lambda key, saved: Client(saved))
    pans = PanService(tmp_path, AccountManager(tmp_path / '115.json'), servers=accounts,
                      client_factory=lambda key, saved: Client(saved))
    yield SimpleNamespace(accounts=accounts, pans=pans, expected=expected, wire=wire,
                          binding=binding, values=values, Client=Client)
    pans.close()


def source(tmp_path, expected):
    store = Registry(tmp_path / 'libraries.sqlite3')
    try:
        return store.source_snapshot(expected['source_id'])
    finally:
        store.close()


def test_server_source_optional_metadata_old_records_and_no_secret_projection(tmp_path, server):
    saved, generation = source(tmp_path, server.expected)
    assert saved.password == '' and generation == server.expected['generation']
    assert saved.metadata == dict(schema=1, provider='plex', server_id='machine1', user_id='77')
    assert 'secret' not in repr(saved)
    old = dict(id='a'*32, name='Old', kind='vfs', location='D:/Movies/', username='', password='', items=[])
    assert Registry._read(json.dumps(old)).metadata == {}
    for data in (dict(saved.metadata, token='no'), dict(saved.metadata, schema=True)):
        with pytest.raises(LibraryError):
            validate_source(replace(saved, metadata=data))
    with pytest.raises(LibraryError):
        validate_source(replace(saved, password='forbidden-copy'))
    assert 'secret' not in json.dumps(server.pans.status())
    assert not (tmp_path / 'pan-accounts-v1.json').exists()
    with pytest.raises(PanError):
        PanAccounts(tmp_path / 'wrong.json', {'plex': lambda v: ('id', v)})


@pytest.mark.parametrize('change', [dict(epoch=1), dict(source_id='x'), dict(generation=''),
                                    dict(extra='x'), dict(account_id='quark:'+'a'*64)])
def test_strict_server_scope_unknown_fields_rejected(server, change):
    with pytest.raises(PanError):
        scope(dict(server.expected, **change))
    with pytest.raises(PanError):
        scope({k:v for k,v in server.expected.items() if k not in ('source_id', 'generation')})


def test_server_scope_not_cloud_contract(server):
    cloud = dict(provider='quark', account_id='quark:'+'a'*64, epoch=1, authenticated=True)
    assert scope(cloud) == cloud
    with pytest.raises(PanError):
        scope(dict(cloud, source_id='b'*32, generation='c'*64))


def test_registry_configuration_a_b_a_and_remove_readd_never_revive(tmp_path, server):
    original, revision = source(tmp_path, server.expected)
    store = Registry(tmp_path / 'libraries.sqlite3')
    try:
        store.save(original)
        assert store.source_snapshot(original.id)[1] == revision
        store.save(replace(original, name='B'))
        middle = server.accounts.snapshot('plex')
        store.save(original)
        current = server.accounts.snapshot('plex')
        assert len({revision, middle['generation'], current['generation']}) == 3
        assert not server.accounts.is_current(server.expected)
        store.remove(original.id)
        assert not server.accounts.snapshot('plex')['authenticated']
        store.save(original)
        assert server.accounts.snapshot('plex')['generation'] != current['generation']
    finally:
        store.close()


def test_plex_settings_rotation_latches_and_same_server_user_change_is_not_silent(tmp_path, server):
    server.values['token'] = 'other-secret'
    assert not server.accounts.is_current(server.expected)
    server.values.update(SETTINGS)
    assert not server.binding.current() and not server.accounts.snapshot('plex')['authenticated']
    fresh = Accounts(tmp_path, PlexBinding(lambda: deepcopy(SETTINGS), lambda: True))
    server.wire.user = '88'
    with pytest.raises(PanError, match='ACCOUNT_ID_INVALID'):
        fresh.register('plex', 'Change', expected_source=server.expected['source_id'],
                       client_factory=lambda key,saved: server.Client(saved))
    assert source(tmp_path, server.expected)[0].metadata['user_id'] == '77'
    fresh.logout(fresh.snapshot('plex'))
    current = fresh.register('plex', 'New user', client_factory=lambda key,saved: server.Client(saved))
    assert current['account_id'] != server.expected['account_id']


def test_plex_all_media_all_parts_and_full_reversible_identity(server):
    server.wire.media[0]['Part'].append(dict(id='124', key='/library/parts/124/456/file.mkv', size=8, file='/x/Second.mkv'))
    server.wire.media.append(dict(id='13', Part=[dict(id='125', key='/library/parts/125/456/file.mkv', size=8, file='/x/Alt.mkv')]))
    rows = server.pans.list_files(server.expected, 'item:9', 1)['items']
    refs = [from_selected(server.expected, row, 'item:9') for row in rows]
    assert len(refs) == len({ref['id'] for ref in refs}) == 3
    assert [parts(ref['file_id'])[:3] for ref in refs] == [('9','12','123'), ('9','12','124'), ('9','13','125')]
    assert [resumable(ref) for ref in refs] == [False, False, False]
    assert all('分卷' in row['name'] for row in rows[:2])
    for ref in refs:
        with pytest.raises(PanError, match='SERVER_RESUME'):
            prepare_history_play(server.pans, dict(file_ref=ref), 'a'*32)
    with pytest.raises(ValueError):
        validate(dict(refs[0], file_id='hash-only', id=identity('plex', refs[0]['account_id'], 'machine1', refs[0]['file_id'])))


def test_full_registry_scan_review_ticket_range_history_and_removal(tmp_path, server, database):
    pans, expected = server.pans, server.expected
    registry = Registry(tmp_path / 'libraries.sqlite3')
    directory = registry.save_directory('Plex Movies', expected, 'root')
    registry.close()
    catalog = CatalogService(tmp_path, pans)
    try:
        task = catalog.start_scan(expected, directory['id'])['task_id']
        catalog.worker.join(3)
        assert not catalog.worker.is_alive()
        job = catalog.index.jobs(expected, task=task)['items'][0]
        assert job['state'] == 'completed' and job['counts']['discovered'] == 1
        selected = pans.list_files(expected, 'item:9', 1)['items'][0]
        ref = from_selected(expected, selected, 'item:9')
        assert catalog.index.trusted_file(expected, ref['id']) == ref
        assert catalog.source_observation(expected, directory['id'])['coverage'] == 'complete'
        result = catalog.dispatch('catalog_apply', dict(expected=expected, request_id='1'*32,
                                  commands=[command(ref, title='Plex film')]))
        assert result['items'][0]['status'] == 'applied'
        ticket = catalog.prepare_play(expected, ref['id'], '2'*32, 'play')['ticket']
        claimed = pans.claim_play(ticket)
        assert claimed['file_ref'] == ref and claimed['account'] == expected
        ready = pans.open_stream(expected, claimed['selected'], ticket)
        seen = []
        pans.streams.session_factory = lambda: Upstream(seen)
        assert read(ready['url'])[0::2] == (206, b'cdef')
        assert seen[0][1]['X-Plex-Token'] == SETTINGS['token']
        assert 'secret' not in seen[0][0] and seen[0][2]['allow_redirects'] is False
        assert 'secret' not in json.dumps(ready)
        storage, _ = database
        files = history.FileHistory(storage.PickleDatabase())
        context = files.begin(ref)
        assert files.save(playback(context, position=40))
        record = files.get(ref['id'])
        with pytest.raises(PanError, match='SERVER_RESUME'):
            prepare_history_play(pans, record, '3'*32)
        replay = prepare_history_play(pans, record, '3'*32, start_only=True)
        assert pans.claim_play(replay['ticket'])['file_ref'] == ref
        pending = catalog.prepare_play(expected, ref['id'], '4'*32, 'play')['ticket']
        registry = Registry(tmp_path / 'libraries.sqlite3')
        registry.remove(expected['source_id'])
        registry.close()
        pans.servers.poll()
        assert read(ready['url'])[0] == 404
        with pytest.raises(PanError):
            pans.claim_play(pending)
        with pytest.raises(PanError):
            prepare_history_play(pans, record, '5'*32, start_only=True)
    finally:
        catalog.close()


def test_cache_receipt_cursor_and_cooldown_bind_full_generation(tmp_path, server):
    from bobbi_core.catalog_query import scope_key as query_scope
    from bobbi_platform.pan_request_policy import Cooldowns
    rows = server.pans.list_files(server.expected, 'item:9', 1)['items']
    current_source, _ = source(tmp_path, server.expected)
    store = Registry(tmp_path / 'libraries.sqlite3')
    store.save(replace(current_source, name='Changed'))
    store.close()
    fresh = server.accounts.snapshot('plex')
    assert query_scope(fresh) != query_scope(server.expected)
    assert Cooldowns.key(fresh) != Cooldowns.key(server.expected)
    with pytest.raises(PanError, match='PLAY_EXPIRED'):
        server.pans.prepare_play(fresh, rows[0])
    with pytest.raises(PanError, match='ACCOUNT_CHANGED'):
        server.pans.list_files(server.expected, 'item:9', 1)


def test_service_restart_does_not_revive_old_ticket(tmp_path, server):
    rows = server.pans.list_files(server.expected, 'item:9', 1)['items']
    ticket = server.pans.prepare_play(server.expected, rows[0])['ticket']
    other = PanService(tmp_path, AccountManager(tmp_path / 'other115.json'), servers=Accounts(
        tmp_path, PlexBinding(lambda: deepcopy(SETTINGS), lambda: True)))
    try:
        assert other.accounts.snapshot('plex') == server.expected
        with pytest.raises(PanError, match='PLAY_EXPIRED'):
            other.claim_play(ticket)
    finally:
        other.close()


def test_ui_registration_entry_calls_host_and_existing_source_browse(server, tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ALPHANUM_HIDE_INPUT=1))
    store = Registry(tmp_path / 'libraries.sqlite3')
    dialog = SimpleNamespace(select=lambda *a,**k:0, input=lambda *a,**k:'Plex',
                             yesno=lambda *a,**k:True, ok=lambda *a,**k:None)
    calls = []
    monkeypatch.setattr(server_ui, 'call', lambda action,body,**kw: calls.append((action,body,kw)))
    assert server_ui.add(dialog, store)
    assert calls[0][0] == 'pan_server_register'
    assert calls[0][1] == dict(provider='plex', name='Plex', expected_source=server.expected['source_id'])
    monkeypatch.setattr(pan_ui, 'call', lambda *a,**k:server.pans.status())
    assert len(pan_ui._status()) == 10 and len(pan_ui._status(servers=True)) == 3
    seen = []
    monkeypatch.setattr(pan_ui, 'browse', lambda row,dialog:seen.append(row) or True)
    assert server_ui.browse(dialog, store.get(server.expected['source_id']))
    assert seen[0]['account'] == server.expected
    store.close()


class Response(io.BytesIO):
    status = 200
    def __init__(self, raw=b'{"ok":true}', url=BASE+'/identity'):
        super().__init__(raw)
        self.url = url
    def geturl(self):
        return self.url


def test_server_http_exact_origin_headers_only_and_redirect_rejected():
    seen = []
    def open_(request, timeout):
        seen.append(request)
        return Response()
    session = server_http.Session('plex', BASE, SETTINGS['token'], opener=SimpleNamespace(open=open_))
    assert session.request('/identity') == {'ok':True}
    assert SETTINGS['token'] not in seen[0].full_url
    assert seen[0].get_header('X-plex-token') == SETTINGS['token']
    for path in ('//evil.test/x', '/a/../x', '/a/%2e%2e/x', '/x?token=secret', '/x|Cookie=y'):
        with pytest.raises(PanError):
            session.request(path)
    for url in ('https://evil.test/pms/x', 'http://server.example/pms/x',
                BASE+'/x?api_key=secret', BASE+'/x?X-Plex-Token=secret', 'https://server.example/other/x'):
        assert not server_http.at_origin(BASE, url)
    with pytest.raises(PanError):
        server_http.NoRedirect().redirect_request(None, None, None, None, None, None)
    session.opener.open = lambda *a,**k:Response(url='https://evil.test/x')
    with pytest.raises(PanError):
        session.request('/identity')
    session.opener.open = lambda *a,**k:Response(b'x'*(server_http.MAX_REPLY+1))
    with pytest.raises(PanError):
        session.request('/identity')


class EmbyWire:
    base = BASE
    operation = None
    def __init__(self, provider):
        self.provider = provider
        self.calls = []
        self.media = [dict(Id='version1', Protocol='File', Path='/movies/Jelly.mkv', Size=8, SupportsDirectPlay=True)]
    def budget(self, seconds):
        return nullcontext()
    def headers(self):
        if self.provider == 'jellyfin':
            return {'User-Agent':server_http.USER_AGENT, 'Authorization':'MediaBrowser Token="fixture-secret"'}
        return {'User-Agent':server_http.USER_AGENT, 'X-Emby-Token':'fixture-secret'}
    def request(self, path, **kw):
        self.calls.append((path,kw))
        if self.operation:
            self.operation.consume_request()
        if path == ('/System/Info/Public' if self.provider == 'emby' else '/System/Info'): return {'Id':'server1'}
        if path == '/Users/Me' or self.provider == 'emby' and path == '/Users/user1': return {'Id':'user1'}
        if path == '/Users/user1/Views': return dict(Items=[dict(Id='library1',Name='Movies',IsFolder=True)],TotalRecordCount=1)
        if path == '/Users/user1/Items': return dict(Items=[dict(Id='item1',Name='Film',IsFolder=False)],TotalRecordCount=1)
        if path == '/Users/user1/Items/item1': return dict(Id='item1',PartCount=1,MediaSources=deepcopy(self.media))
        assert path == '/Items/item1/PlaybackInfo'
        assert kw['data']['MediaSourceId'] == 'version1'
        assert kw['data']['AutoOpenLiveStream'] is False and kw['data']['EnableTranscoding'] is False
        return dict(MediaSources=deepcopy(self.media))


@pytest.mark.parametrize('provider', ['jellyfin', 'emby'])
def test_shared_server_protocol_exact_media_source_and_static_response(provider):
    wire = EmbyWire(provider)
    client = server_emby.Client(provider, dict(location=BASE,token='fixture-secret',server_id='server1',user_id='user1'), wire)
    assert client.verify() == ('server1','user1')
    assert client.list_files()['items'][0]['file_id'] == 'folder:library1'
    assert client.list_files('folder:library1')['items'][0]['file_id'] == 'item:item1'
    row = client.list_files('item:item1')['items'][0]
    assert parts(row['file_id'])[:3] == ('item1','version1','version1')
    result = client.resolve_original(row)
    assert result['url'] == BASE+'/Videos/item1/stream?Static=true&MediaSourceId=version1'
    assert 'secret' not in result['url'] and result['original'] is True
    wire.media[0]['SupportsDirectPlay'] = False
    with pytest.raises(PanError, match='MEDIA_UNSUPPORTED'):
        client.resolve_original(row)


@pytest.mark.parametrize('provider', ['jellyfin', 'emby'])
def test_jellyfin_emby_registry_index_range_and_history_vertical(provider, tmp_path, database):
    wire = EmbyWire(provider)
    factory = lambda key,saved:server_emby.Client(key,saved,wire)
    accounts = Accounts(tmp_path)
    expected = accounts.register(provider, provider, BASE, 'fixture-secret', client_factory=factory)
    saved, revision = source(tmp_path, expected)
    assert saved.password == 'fixture-secret' and saved.metadata['user_id'] == 'user1'
    pans = PanService(tmp_path, AccountManager(tmp_path/'115.json'), servers=accounts, client_factory=factory)
    registry = Registry(tmp_path/'libraries.sqlite3')
    registered = registry.save_directory('Movies', expected, 'root')
    registry.close()
    catalog = CatalogService(tmp_path,pans)
    try:
        task = catalog.start_scan(expected,registered['id'])['task_id']
        catalog.worker.join(3)
        assert catalog.index.jobs(expected,task=task)['items'][0]['state'] == 'completed'
        row = pans.list_files(expected,'item:item1',1)['items'][0]
        ref = from_selected(expected,row,'item:item1')
        ticket = catalog.prepare_play(expected,ref['id'],'1'*32,'play')['ticket']
        assert pans.claim_play(ticket)['file_ref'] == ref
        ready = pans.open_stream(expected,row,ticket)
        seen = []
        pans.streams.session_factory = lambda:Upstream(seen)
        assert read(ready['url'])[0::2] == (206,b'cdef')
        assert seen[0][1] == {**wire.headers(), 'Range': 'bytes=2-5',
                              'Accept-Encoding': 'identity', 'Connection': 'close'}
        storage, _ = database
        files = history.FileHistory(storage.PickleDatabase())
        context = files.begin(ref)
        files.save(playback(context,position=40))
        with pytest.raises(PanError, match='SERVER_RESUME'):
            prepare_history_play(pans,files.get(ref['id']),'2'*32)
        assert prepare_history_play(pans,files.get(ref['id']),'2'*32, start_only=True)['ticket'] == '2'*32
        registry = Registry(tmp_path/'libraries.sqlite3')
        registry.save(replace(saved,password='rotated-secret'))
        registry.close()
        assert not accounts.is_current(expected)
        assert read(ready['url'])[0] == 404
    finally:
        catalog.close()
        pans.close()


def test_phone_full_server_scope_is_revoked_before_business_after_revision(tmp_path, server):
    from test_ce2097_phone_management import load, pair, invoke
    phone_module = load('server_phone_fixture','lib/services/phone_management.py')
    calls = []
    def rpc(action,body,**kw):
        calls.append((action,deepcopy(body)))
        return server.pans.status() if action == 'pan_status' else dict(items=[],next_offset=None)
    manager = phone_module.PhoneManagement(server.expected,'http://127.0.0.1:8081',rpc=rpc)
    state = SimpleNamespace(manager=manager,module=phone_module,
        headers={'Host':'127.0.0.1:8081','Origin':'http://127.0.0.1:8081'})
    pair(state)
    invoke(state)
    assert next(body['expected'] for action,body in calls if action == 'catalog_items') == server.expected
    original,_ = source(tmp_path,server.expected)
    store = Registry(tmp_path/'libraries.sqlite3')
    store.save(replace(original,name='B'))
    store.save(original)
    store.close()
    calls.clear()
    with pytest.raises(phone_module.PhoneError,match='ACCOUNT_OR_SERVICE_CHANGED'):
        invoke(state)
    assert manager.closed and all(action == 'pan_status' for action,_ in calls)


def test_native_scope_and_existing_osd_authority_revoke_source_removal(tmp_path, server, monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parent/'private_baseline'))
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi'))
    from test_playback_authority import Native, row
    from bobbi_core.playback_authority import PlaybackAuthority
    from bobbi_platform.playback_accounts import PlaybackAccounts
    native = Native()
    owner = PlaybackAuthority(native)
    owner.configure_accounts(PlaybackAccounts(server.pans.legacy,lambda:server.pans))
    snapshot = owner.dispatch(dict(operation='snapshot'))
    state = owner.dispatch(dict(operation='select',boot_id=snapshot['boot_id'],epoch=snapshot['epoch'],
        request_id='a'*32,selection_identity='server-file',account_scope=server.expected))
    args = dict(boot_id=state['boot_id'],epoch=state['epoch'],request_id='a'*32)
    assert owner.selection_account == server.expected
    assert owner.dispatch(dict(args,operation='bind_file',selection_identity='server-file',
        file_identity='server-file|part',url_sha256='b'*64,file_evidence='USER_CONFIRMED_FILE')) == {'bound':True}
    assert owner.dispatch(dict(args,operation='claim_start',route='player_play'))['status'] == 'CLAIMED'
    native.current = row('a'*32,'server-file|part',url_sha256='b'*64)
    owner.refresh()
    store = Registry(tmp_path/'libraries.sqlite3')
    store.remove(server.expected['source_id'])
    store.close()
    assert owner.account_changed()
    assert owner.owner.desired['cancelled']
    assert native.commands[-1]['action'] == 'stop'
    assert native.commands[-1]['native_instance'] == native.current['native_instance']


def test_late_registration_cannot_overwrite_new_registry_revision(tmp_path, server):
    original,_ = source(tmp_path,server.expected)
    def change():
        store = Registry(tmp_path/'libraries.sqlite3')
        store.save(replace(original,name='Other edit'))
        store.close()
    server.wire.before = change
    with pytest.raises(LibraryError,match='AUTHORITY_CHANGED'):
        server.accounts.register('plex','Late result',expected_source=original.id,
            client_factory=lambda key,saved:server.Client(saved))
    assert source(tmp_path,server.expected)[0].name == 'Other edit'


def test_real_cursor_and_play_receipt_reject_same_account_new_generation(tmp_path, server):
    server.wire.media.append(dict(id='13',Part=[dict(id='124',key='/library/parts/124/456/file.mkv',
        size=8,file='/movies/Alternate.mkv')]))
    store = Registry(tmp_path/'libraries.sqlite3')
    directory = store.save_directory('Movies',server.expected,'item:9')
    store.close()
    catalog = CatalogService(tmp_path,server.pans)
    try:
        catalog.start_scan(server.expected,directory['id'])
        catalog.worker.join(3)
        result = catalog.query(server.expected,query={'view':'files'},limit=1)
        assert result['next_cursor']
        row = server.pans.list_files(server.expected,'item:9',1)['items'][0]
        ref = from_selected(server.expected,row,'item:9')
        catalog.prepare_play(server.expected,ref['id'],'a'*32,'play')
        original,_ = source(tmp_path,server.expected)
        store = Registry(tmp_path/'libraries.sqlite3')
        store.save(replace(original,name='Changed'))
        store.close()
        fresh = server.accounts.snapshot('plex')
        with pytest.raises(ValueError,match='CURSOR_STALE'):
            catalog.query(fresh,query={'view':'files'},limit=1,cursor=result['next_cursor'])
        with pytest.raises(ValueError,match='REQUEST_REUSED'):
            catalog.prepare_play(fresh,ref['id'],'a'*32,'play')
    finally:
        catalog.close()


@pytest.mark.parametrize('mutation',['foreign_origin','token_query','wrong_headers','size'])
def test_server_range_resolution_never_sends_credentials_to_unregistered_address(server,mutation,monkeypatch):
    row = server.pans.list_files(server.expected,'item:9',1)['items'][0]
    original = server.Client.resolve_original
    def resolve(client,selected):
        reply = original(client,selected)
        if mutation == 'foreign_origin': reply['url'] = 'https://foreign.example/video.mkv'
        elif mutation == 'token_query': reply['url'] += '?X-Plex-Token=secret'
        elif mutation == 'wrong_headers': reply['headers']['X-Plex-Token'] = 'other'
        else: reply['size'] = 9
        return reply
    monkeypatch.setattr(server.Client,'resolve_original',resolve)
    with pytest.raises(PanError):
        server.pans.open_stream(server.expected,row,'a'*32)


def test_optional_plex_binding_is_profile_bound_and_never_recovers_after_a_b_a():
    profile = ['A']
    binding = PlexBinding(lambda:deepcopy(SETTINGS),lambda:profile[0]=='A')
    profile[0] = 'B'
    assert not binding.current()
    profile[0] = 'A'
    assert not binding.current()


@pytest.mark.parametrize('raw', [b'{"id":1,"id":2}', b'{"id":NaN}', b'{"id":Infinity}',
    b'['*34+b'0'+b']'*34, b'['*2000+b'0'+b']'*2000,
    b'['+b'0,'*100000+b'0]'], ids=['duplicate','nan','infinity','depth','recursive','nodes'])
def test_bounded_server_json_rejects_duplicate_nonfinite_deep_and_huge_node_trees(raw):
    session = server_http.Session('plex',BASE,'fixture-secret',
        opener=SimpleNamespace(open=lambda *a,**kw:Response(raw)))
    with pytest.raises(PanError,match='PAN_REPLY_INVALID'):
        session.request('/identity')


@pytest.mark.parametrize('provider', ['plex', 'jellyfin', 'emby'])
def test_same_id_same_size_replacement_keeps_display_history_but_cannot_resume(
        provider, tmp_path, database, server):
    from bobbi_platform.host import Host
    from bobbi_platform.pan_history import history_summary
    from bobbi_platform.pan_providers import descriptor
    if provider == 'plex':
        pans, expected, wire, parent = server.pans, server.expected, server.wire, 'item:9'
    else:
        wire = EmbyWire(provider)
        factory = lambda key, saved: server_emby.Client(key, saved, wire)
        accounts = Accounts(tmp_path)
        expected = accounts.register(provider, provider, BASE, 'fixture-secret', client_factory=factory)
        pans = PanService(tmp_path, AccountManager(tmp_path/'115.json'), servers=accounts, client_factory=factory)
        parent = 'item:item1'
    try:
        row = pans.list_files(expected, parent, 1)['items'][0]
        ref = from_selected(expected, row, parent)
        storage, _ = database
        files = history.FileHistory(storage.PickleDatabase())
        files.save(playback(files.begin(ref), position=42))
        old = files.get(ref['id'])
        # The server replaces content without changing IDs, basename or size.
        # These remote hints are not a retained, validated observation contract.
        if provider == 'plex':
            wire.media[0]['Part'][0].update(key='/library/parts/123/999/file.mkv', updatedAt=999)
        else:
            wire.media[0].update(ETag='replacement-content', DateModified='2026-11-13T00:00:00Z')
        fresh = from_selected(expected, pans.list_files(expected, parent, 1, refresh=True)['items'][0], parent)
        assert fresh == ref and not resumable(fresh)
        host = Host(tmp_path/'platform', file_history=files)
        host.accounts, host.pans = pans.accounts, pans
        body = dict(history_id=ref['id'], request_id='e'*32)
        with pytest.raises(PanError, match='SERVER_RESUME'):
            host.dispatch('pan_prepare_history_play', body)
        for invalid in (1, 'true', None):
            with pytest.raises(PanError, match='SELECTION_INVALID'):
                host.dispatch('pan_prepare_history_play', dict(body, start_only=invalid))
        assert not pans.play_tickets
        assert host.dispatch('pan_prepare_history_play', dict(body, start_only=True)) == {'ticket':'e'*32}
        claimed = host.dispatch('pan_claim_play', {'ticket':'e'*32})
        assert claimed['file_ref'] == fresh
        assert files.get(ref['id'])['position'] == old['position'] == 42
        summary = history_summary(pans, expected, history=files)['items'][0]
        assert summary['start_only'] is True and summary['position'] == 42
        assert descriptor(provider).capabilities == ('list_files', 'personal_play')
    finally:
        if provider != 'plex':
            pans.close()


def configure_server_entry(entry, provider):
    from bobbi_platform.pan_stream import body
    entry.expected = dict(provider=provider, account_id=provider+':'+'f'*64, epoch=0,
                          authenticated=True, source_id='b'*32, generation='c'*64)
    entry.file = dict(file_id=file_id('entry1', 'media1', 'part1'), server_id='server1',
                      name='movie.mkv', size=8, directory=False)
    entry.body = body(provider, entry.file, entry.ticket)
    ref = from_selected(entry.expected, entry.file, 'item:entry1')
    entry.claim_extra = dict(file_ref=ref, history=dict(generation=2, session_id='d'*32))
    return ref


@pytest.mark.parametrize('provider', ['plex', 'jellyfin', 'emby'])
@pytest.mark.parametrize('native', [True, False])
def test_server_handoff_discards_old_position_for_native_and_standard(entry, provider, native):
    ref = configure_server_entry(entry, provider)
    entry.native = native
    entry.module.play({'ticket':entry.ticket}, reservation=dict(account=entry.expected,
        owner={'request_id':entry.ticket}, file_ref=ref, position=42))
    assert len(entry.played) == 1 and not entry.errors
    assert entry.played[0]['_file_resume_position'] == 0
    assert entry.played[0]['_bobbi_start_over'] is True


@pytest.mark.parametrize('provider', ['plex', 'jellyfin', 'emby'])
@pytest.mark.parametrize('native', [True, False])
@pytest.mark.parametrize('route', ['implicit_history', 'start_history', 'indexed'])
def test_server_ui_never_reserves_implicit_resume_or_offers_old_position(
        entry, provider, native, route, monkeypatch):
    import sys
    ref = configure_server_entry(entry, provider)
    entry.native = native
    record = dict(file_ref=ref, position=42, completion_reason='STOP')
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(
        FileHistory=lambda *args: SimpleNamespace(get=lambda identifier: record)))
    monkeypatch.setitem(sys.modules, 'lib.utils.views.personal_catalog', SimpleNamespace(
        account_for=lambda params, accounts: entry.expected))
    original = entry.module.call
    def call(action, body, **kwargs):
        if action == 'pan_status':
            entry.calls.append((action, body))
            return dict(providers=[dict(provider=provider, account=entry.expected)])
        if action in ('pan_prepare_history_play', 'catalog_prepare_play'):
            entry.calls.append((action, body))
            entry.ticket = body['request_id']
            return dict(ticket=entry.ticket)
        return original(action, body, **kwargs)
    monkeypatch.setattr(entry.module, 'call', call)
    if route == 'indexed':
        # The test Dialog has no select() method: advertising resume fails.
        entry.module.indexed(dict(object_id=ref['id'], provider=provider))
    else:
        entry.module.resume(dict(history_id=ref['id'],
            **({'start_over':'true'} if route == 'start_history' else {})))
    if route == 'implicit_history':
        assert entry.calls == [('status', {})] and not entry.played
        assert '不继承旧进度' in entry.errors[0][1]
    else:
        assert len(entry.played) == 1 and not entry.errors
        assert entry.played[0]['_file_resume_position'] == 0
        assert entry.played[0]['_bobbi_start_over'] is True
        if route == 'start_history':
            prepared = next(body for action, body in entry.calls if action == 'pan_prepare_history_play')
            assert prepared['start_only'] is True


def test_standard_start_only_handoff_explicitly_zeros_kodi_offset(monkeypatch):
    import sys
    from bobbi_platform.kodi import make_item
    properties = {}
    item = SimpleNamespace(setProperty=lambda key, value: properties.update({key:value}),
                           getVideoInfoTag=lambda: SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=lambda **kwargs: item))
    make_item('http://127.0.0.1/stream/video.mkv', dict(_pan_file=True,
        _file_resume_position=42, _bobbi_start_over=True))
    assert properties['StartOffset'] == '0'

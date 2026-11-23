"""Real SQLite + existing adapter publication, not server/device QA.

Server claims never establish mappings, playback identities or resume evidence.
The legacy test executes frozen baseline reader/writer source, not a facsimile.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import json
import sqlite3
import subprocess

import pytest

from bobbi_core import catalog_query, catalog_transfer, server_description
from bobbi_core.file_ref import from_selected
from bobbi_core.media_library_index import MediaIndex
from bobbi_core.server_ref import resumable
from bobbi_platform import server_emby, server_plex, server_http
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_service import PanService
from bobbi_platform.scan_sources import NativePort
from bobbi_platform.server_accounts import Accounts, PlexBinding
from test_media_library_index import command, ref as cloud_ref, scope as cloud_scope
from test_media_servers import BASE, SETTINGS, PlexWire, EmbyWire, source
from test_ce2096_pan_stream import Upstream, read
from test_personal_catalog import catalog
from test_library_plugin import plugin

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '51317effaef2f84953eeb48eea486f0239da693f'


@pytest.fixture(params=['plex', 'jellyfin', 'emby'])
def scene(tmp_path, request):
    provider = request.param
    wire = PlexWire() if provider == 'plex' else EmbyWire(provider)
    wire.claims = dict(type='movie', title='Server film', summary='<b>Server overview</b>', year=2024,
        Guid=[dict(id='tmdb://42'), dict(id='imdb://tt1234567')]) if provider == 'plex' else dict(
        Type='Movie', Name='Server film', Overview='<b>Server overview</b>', ProductionYear=2024,
        ProviderIds=dict(Tmdb='42', Imdb='tt1234567'))
    original = wire.request
    def request_value(path, **kwargs):
        value = original(path, **kwargs)
        if provider == 'plex' and path == '/library/metadata/9':
            value['MediaContainer']['Metadata'][0].update(deepcopy(wire.claims))
        elif path == '/Users/user1/Items/item1':
            value.update(deepcopy(wire.claims))
        return value
    wire.request = request_value
    if provider == 'plex':
        class Client(server_plex.Client):
            def __init__(self, saved): super().__init__(saved, wire)
            def verify(self): return super().verify(wire)
        factory = lambda key, saved: Client(saved)
        accounts = Accounts(tmp_path, PlexBinding(lambda: deepcopy(SETTINGS), lambda: True))
        expected = accounts.register(provider, provider, client_factory=factory)
        parent, item_id = 'item:9', '9'
    else:
        factory = lambda key, saved: server_emby.Client(key, saved, wire)
        accounts = Accounts(tmp_path)
        expected = accounts.register(provider, provider, BASE, 'fixture-secret', client_factory=factory)
        parent, item_id = 'item:item1', 'item1'
    pans = PanService(tmp_path, AccountManager(tmp_path / '115.json'), servers=accounts, client_factory=factory)
    registry = Registry(tmp_path / 'libraries.sqlite3')
    directory = registry.save_directory('Movies', expected, parent)
    registry.close()
    active = [True]
    service = CatalogService(tmp_path, pans, profile_current=lambda: active[0])
    value = SimpleNamespace(provider=provider, wire=wire, accounts=accounts, pans=pans,
        expected=expected, parent=parent, item_id=item_id, service=service, index=service.index,
        directory=directory, active=active, root=tmp_path)
    yield value
    service.close()
    pans.close()


def scan(scene):
    task = scene.service.start_scan(scene.expected, scene.directory['id'])['task_id']
    scene.service.worker.join(5)
    assert not scene.service.worker.is_alive()
    assert scene.index._scan(task)['state'] == 'completed', scene.index._scan(task)
    return task


def files(scene):
    return [from_selected(scene.expected, row, scene.parent)
            for row in scene.pans.list_files(scene.expected, scene.parent, 1)['items']]


def claims(scene, title='Changed source', year=2025):
    scene.wire.claims = dict(type='movie', title=title, summary='Updated overview', year=year,
        Guid=[dict(id='tmdb://999')]) if scene.provider == 'plex' else dict(Type='Movie',
        Name=title, Overview='Updated overview', ProductionYear=year, ProviderIds=dict(Tmdb='999'))


def description(scene, title='Direct description'):
    return server_description.observed(scene.provider, scene.item_id, title=title, year=2026,
                                       ids=dict(tmdb='987'))


def batch(index, expected, refs, descriptions):
    task = index.start('a' * 32, expected)
    index.begin(task)
    index.batch(task, refs, dict(page=1), len(refs), descriptions=descriptions)
    index.finish(task, 'completed')
    return task


def authority(index):
    return {table: [tuple(row) for row in index.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
        for table in ('objects', 'typed_objects', 'memberships', 'reviews', 'review_changes',
                      'catalog_rows', 'object_times')}


def test_scan_descriptions_are_nested_read_only_and_selected_stream_identity_is_unchanged(scene):
    selected = scene.pans.list_files(scene.expected, scene.parent, 1)
    assert set(selected) == {'items', 'has_more'}
    file = from_selected(scene.expected, selected['items'][0], scene.parent)
    before_calls = len(scene.wire.calls)
    scan(scene)
    # Exactly the existing identity checks + item detail; no metadata request added.
    paths = [path for path, _ in scene.wire.calls[before_calls:]]
    assert paths == (['/identity', '/library/metadata/9'] if scene.provider == 'plex'
        else ['/System/Info', '/Users/Me', '/Users/user1/Items/item1'])
    assert scene.index.trusted_file(scene.expected, file['id']) == file
    review = scene.index.item(scene.expected, file['id'])
    assert review['revision'] == 0 and review['provenance'] == 'filename' and review['mapping'] is None
    candidate = review['candidates'][-1]
    assert set(candidate) == {'origin', 'description'} and candidate['origin'] == 'server'
    assert review['candidates'][0]['origin'] == 'filename'
    assert candidate['description']['ids'] == dict(tmdb='42', imdb='tt1234567')
    for view in ('works', 'files'):
        card = scene.index.query(scene.expected, query=dict(view=view))['items'][0]
        assert card['display_title'] == ('Server film' if view == 'works' else file['name'])
        assert card['year'] == 2024
        assert card['metadata_key'] is None and card['media_kind'] == 'unknown'
        assert card['server_description']['overview'] == 'Server overview'
    claims(scene)
    assert scene.pans.list_files(scene.expected, scene.parent, 1) == selected
    ticket = scene.service.prepare_play(scene.expected, file['id'], uuid4().hex, 'play')['ticket']
    assert scene.pans.claim_play(ticket)['file_ref'] == file
    ready = scene.pans.open_stream(scene.expected, selected['items'][0], ticket)
    seen = []
    scene.pans.streams.session_factory = lambda: Upstream(seen)
    assert read(ready['url'])[0::2] == (206, b'cdef')
    assert 'secret' not in json.dumps(ready) and not resumable(file)


def test_refresh_removal_cursor_invalidation_and_noop_keeps_filename_evidence(scene):
    if scene.provider == 'plex':
        scene.wire.media.append(dict(id='13', Part=[dict(id='124', key='/library/parts/124/456/file.mkv',
            size=8, file='/movies/Other.mkv')]))
    else:
        scene.wire.media.append(dict(Id='version2', Protocol='File', Path='/movies/Other.mkv', Size=8))
    scan(scene)
    refs = files(scene)
    assert len({file['id'] for file in refs}) == 2
    initial = {file['id']: deepcopy(scene.index.item(scene.expected, file['id'])['candidates'][0]) for file in refs}
    cursor = scene.index.query(scene.expected, limit=1)['next_cursor']
    claims(scene)
    scan(scene)
    with pytest.raises(ValueError, match='CURSOR_STALE'):
        scene.index.query(scene.expected, limit=1, cursor=cursor)
    assert {card['display_title'] for card in scene.index.query(scene.expected)['items']} == {'Changed source'}
    assert all(card['variant_count'] == 1 for card in scene.index.query(scene.expected)['items'])
    before = scene.index.scope_revision(scene.expected)
    scan(scene)
    assert scene.index.scope_revision(scene.expected) == before
    scene.wire.claims = {}
    scan(scene)
    for file in refs:
        row = scene.index.item(scene.expected, file['id'])
        assert row['candidates'] == [initial[file['id']]] and row['revision'] == 0
    assert all('server_description' not in card for card in scene.index.query(scene.expected)['items'])


@pytest.mark.parametrize('action', ['confirm', 'confirm_movie', 'unbind', 'ignore'])
def test_manual_edit_refresh_undo_and_transfer_keep_authority_and_filename_candidate(scene, action):
    scan(scene)
    file = files(scene)[0]
    initial = scene.index.item(scene.expected, file['id'])['candidates'][0]
    cmd = command(file, action='confirm' if action == 'confirm_movie' else action, title='User title')
    if cmd['mapping']:
        cmd['mapping']['version'] = 'User cut'
        if action == 'confirm_movie':
            cmd['mapping'].update(kind='movie', tmdb_id=123)
    assert scene.index.apply(scene.expected, uuid4().hex, [cmd])['items'][0]['status'] == 'applied'
    before = scene.index.item(scene.expected, file['id'])
    changes = [tuple(row) for row in scene.index.db.execute('SELECT * FROM review_changes')]
    claims(scene, 'Conflicting server', 2022)
    scan(scene)
    after = scene.index.item(scene.expected, file['id'])
    for key in ('mapping', 'state', 'reason', 'revision', 'provenance'):
        assert after[key] == before[key]
    assert after['candidates'][0] == initial and after['candidates'][-1]['description']['title'] == 'Conflicting server'
    assert [tuple(row) for row in scene.index.db.execute('SELECT * FROM review_changes')] == changes
    assert all('server_description' not in card for card in scene.index.query(scene.expected)['items'])
    exported = catalog_transfer.export_records(scene.expected, scene.index.manual_records(scene.expected)['items'])
    assert 'Conflicting server' not in json.dumps(exported) and 'candidates' not in json.dumps(exported)
    assert catalog_transfer.loads(catalog_transfer.dumps(exported)) == exported
    result = scene.index.apply(scene.expected, uuid4().hex, [command(file, 1, 'undo')])
    assert result['items'][0]['revision'] == 2
    after_undo = scene.index.item(scene.expected, file['id'])
    assert after_undo['mapping'] is None and after_undo['provenance'] == 'manual'
    scan(scene)
    assert scene.index.item(scene.expected, file['id']) == after_undo
    assert all('server_description' not in card for card in scene.index.query(scene.expected)['items'])


def test_manual_transfer_import_does_not_copy_server_claims_or_infer_content_match(scene):
    from test_catalog_manual_transfer import record
    scan(scene)
    file = files(scene)[0]
    scene.index.apply(scene.expected, uuid4().hex, [command(file, title='Portable manual title')])
    payload = catalog_transfer.export_records(scene.expected, scene.index.manual_records(scene.expected)['items'])
    target = MediaIndex(scene.root / 'target.sqlite3')
    try:
        batch(target, scene.expected, [file], {file['id']: description(scene, 'Target source description')})
        candidate = target.item(scene.expected, file['id'])['candidates']
        result = catalog_transfer.preview(payload, scene.expected, [record(target, scene.expected, file)])
        row = result['items'][0]
        assert row['status'] == 'review_required' and row['reason'] == 'CONTENT_EVIDENCE_WEAK'
        target.apply(scene.expected, uuid4().hex, [row['command']])
        assert target.item(scene.expected, file['id'])['candidates'] == candidate
        assert target.item(scene.expected, file['id'])['mapping']['title'] == 'Portable manual title'
        assert 'server_description' not in target.query(scene.expected)['items'][0]
    finally:
        target.close()


def test_episode_claims_never_make_series_mapping_or_season_group(scene):
    scene.wire.claims = (dict(type='episode', title='Episode title', grandparentTitle='Series title',
        parentIndex=2, index=3, Guid=[dict(id='tmdb://987')]) if scene.provider == 'plex' else
        dict(Type='Episode', Name='Episode title', SeriesName='Series title', ParentIndexNumber=2,
             IndexNumber=3, ProviderIds=dict(Tmdb='987')))
    scan(scene)
    row = scene.index.query(scene.expected)['items'][0]
    assert row['metadata_key'] is None and row['media_kind'] == 'unknown' and row['season'] is None
    assert row['server_description']['ids'] == dict(tmdb='987')
    assert row['server_description']['item_type'] == 'episode'
    assert row['server_description']['series_title'] == 'Series title'


def test_sqlite_batch_replay_rollback_and_reference_binding(scene):
    file = files(scene)[0]
    task = scene.index.start(scene.directory['id'], scene.expected)
    scene.index.begin(task)
    desc = {file['id']: description(scene)}
    scene.index.db.execute("CREATE TRIGGER fail_batch BEFORE UPDATE ON scans BEGIN SELECT RAISE(ABORT,'fixture crash'); END")
    before = authority(scene.index)
    with pytest.raises(sqlite3.IntegrityError):
        scene.index.batch(task, [file], dict(page=1), 1, descriptions=desc)
    assert authority(scene.index) == before and scene.index._scan(task)['checkpoint'] == {}
    scene.index.db.execute('DROP TRIGGER fail_batch')
    scene.index.batch(task, [file], dict(page=1), 1, descriptions=desc)
    before = authority(scene.index)
    scene.index.batch(task, [file], dict(page=1), 1, descriptions={file['id']: description(scene, 'Replay')})
    assert authority(scene.index) == before
    assert scene.index._scan(task)['pages'] == 1
    for invalid in ({'unknown': description(scene)}, {file['id']: dict(description(scene), item_id='wrong')}):
        with pytest.raises(ValueError, match='SERVER_DESCRIPTION_INVALID'):
            scene.index.batch(task, [file], dict(page=2), 1, descriptions=invalid)
    assert authority(scene.index) == before
    scene.index.finish(task, 'completed')


def test_unrelated_provider_rejects_server_sidecar_and_legacy_batch_stays_unchanged(tmp_path):
    index = MediaIndex(tmp_path / 'index.db')
    try:
        file, expected = cloud_ref(), cloud_scope()
        task = index.start('a' * 32, expected)
        index.begin(task)
        with pytest.raises(ValueError, match='SERVER_DESCRIPTION_INVALID'):
            index.batch(task, [file], dict(page=1), 1, descriptions={file['id']: None})
        index.batch(task, [file], dict(page=1), 1)
        assert index.item(expected, file['id'])['candidates'][0]['origin'] == 'filename'
        assert 'server_description' not in index.query(expected)['items'][0]
    finally:
        index.close()


def test_optional_malformed_metadata_does_not_change_valid_file_or_break_scan(scene):
    selected = scene.pans.list_files(scene.expected, scene.parent, 1)
    scene.wire.claims = (dict(type=[], title=['bad'], summary='https://secret.example/token', year=True,
        grandparentTitle='\x00bad', parentIndex=-1, index=0, Guid=[dict(id='tmdb://bad')]) if scene.provider == 'plex' else
        dict(Type=[], Name=['bad'], Overview='https://secret.example/token', ProductionYear=True,
             SeriesName='\x00bad', ParentIndexNumber=-1, IndexNumber=0, ProviderIds=['bad']))
    scan(scene)
    assert scene.pans.list_files(scene.expected, scene.parent, 1) == selected
    assert all('server_description' not in row for row in scene.index.query(scene.expected)['items'])
    value = server_description.observed(scene.provider, scene.item_id, title='T'*300,
        overview='<p>' + '中'*2000 + '</p>', ids=dict(tmdb='0', imdb='tt1234567', private='secret'))
    assert len(value['title']) == 240 and len(value['overview']) == 1200 and value['ids'] == dict(imdb='tt1234567')
    assert server_description.observed(scene.provider, scene.item_id, title='T'*20001) is None


def test_source_only_frontend_description_never_enqueues_tmdb(catalog, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'lib.clients.tmdb.frontend_metadata', SimpleNamespace(
        apply=lambda *a, **k: pytest.fail('source claim called TMDB')))
    item = MagicMock()
    value = server_description.observed('plex', '9', title='Server title', overview='Summary', year=2024,
                                        ids=dict(tmdb='42'))
    catalog.catalog.decorate(item, dict(server_description=value, metadata_key=None))
    item.getVideoInfoTag().setYear.assert_called_once_with(2024)
    plot = item.getVideoInfoTag().setPlot.call_args.args[0]
    assert '服务器声明 tmdb=42' in plot and '未确认作品匹配' in plot


@pytest.fixture(scope='module')
def legacy():
    result = {}
    for name in ('catalog_review', 'catalog_query', 'catalog_transfer', 'media_library_index'):
        source = subprocess.check_output(['git', 'show', BASELINE + ':' +
            'addons/script.module.bobbi.core/lib/bobbi_core/' + name + '.py'], cwd=ROOT)
        module = ModuleType('legacy_server_description_' + name)
        module.__package__ = 'bobbi_core'
        exec(compile(source, '<frozen-' + BASELINE[:7] + '-' + name + '>', 'exec'), module.__dict__)
        result[name] = module
    result['media_library_index'].catalog_query = result['catalog_query']
    result['media_library_index'].review = result['catalog_review']
    return SimpleNamespace(**result)


def sql_shape(index):
    return {row[0]: [tuple(column) for column in index.db.execute('PRAGMA table_info(' + row[0] + ')')]
            for row in index.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}


def test_actual_baseline_reader_writer_scan_undo_transfer_and_upgrade_roundtrip(scene, legacy):
    selected = scene.pans.list_files(scene.expected, scene.parent, 1)['items'][0]
    first = from_selected(scene.expected, selected, scene.parent)
    from bobbi_core.server_ref import file_id
    second = from_selected(scene.expected, dict(selected, name='Other.2019.mkv',
        file_id=file_id(scene.item_id, 'alternate', 'alternate')), scene.parent)
    path = scene.root / 'compatibility.sqlite3'
    current = MediaIndex(path)
    try:
        batch(current, scene.expected, [first, second], {
            file['id']: description(scene, 'New description') for file in (first, second)})
        assert {row['display_title'] for row in current.query(scene.expected)['items']} == {'New description'}
        original = {file['id']: current.item(scene.expected, file['id'])['candidates'] for file in (first, second)}
        current_shape = sql_shape(current)
        assert current.db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert current.db.execute('SELECT schema FROM catalog_meta').fetchone()[0] == 7
    finally:
        current.close()
    old = legacy.media_library_index.MediaIndex(path)
    try:
        assert sql_shape(old) == current_shape
        assert old.db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert old.db.execute('SELECT schema FROM catalog_meta').fetchone()[0] == 6
        rows = old.query(scene.expected)['items']
        assert all('server_description' not in row for row in rows)
        assert all(row['display_title'] != 'New description' and row['year'] != 2026 for row in rows)
        assert [row['year'] for row in rows if row['entity_id'] == second['id']] == [2019]
        for file in (first, second):
            assert old.item(scene.expected, file['id'])['candidates'] == original[file['id']]
            assert legacy.catalog_review.suggestion(file['name'])[2] == [original[file['id']][0]]
        cmd = command(first, title='Old writer manual title')
        cmd['mapping']['version'] = 'Old writer version note'
        assert old.apply(scene.expected, uuid4().hex, [cmd])['items'][0]['revision'] == 1
        task = old.start('a' * 32, scene.expected)
        old.begin(task)
        old.batch(task, [first, second], dict(page=1), 2)
        old.finish(task, 'completed')
        exported = legacy.catalog_transfer.export_records(scene.expected, old.manual_records(scene.expected)['items'])
        assert exported['entries'][0]['mapping']['title'] == 'Old writer manual title'
        assert 'description' not in json.dumps(exported) and 'candidates' not in json.dumps(exported)
        assert legacy.catalog_transfer.loads(legacy.catalog_transfer.dumps(exported)) == exported
        assert old.apply(scene.expected, uuid4().hex, [command(first, 1, 'undo')])['items'][0]['revision'] == 2
        for file in (first, second):
            assert old.item(scene.expected, file['id'])['candidates'] == original[file['id']]
        legacy_authority = {key: value for key, value in authority(old).items() if key != 'catalog_rows'}
    finally:
        old.close()
    upgraded = MediaIndex(path)
    try:
        assert sql_shape(upgraded) == current_shape
        assert upgraded.db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert upgraded.db.execute('SELECT schema FROM catalog_meta').fetchone()[0] == 7
        assert {key: value for key, value in authority(upgraded).items() if key != 'catalog_rows'} == legacy_authority
        cards = {row['entity_id']: row for row in upgraded.query(scene.expected)['items']}
        assert 'server_description' not in cards[first['id']]
        assert cards[second['id']]['server_description']['title'] == 'New description'
        assert upgraded.item(scene.expected, first['id'])['provenance'] == 'manual'
        assert upgraded.item(scene.expected, first['id'])['revision'] == 2
    finally:
        upgraded.close()


def test_actual_legacy_reader_negative_control_detects_top_level_year_pollution(scene, legacy):
    file = files(scene)[0]
    # Use a filename without a year so the old scalar promotion is unambiguous.
    file = dict(file, name='Opaque.mkv')
    batch(scene.index, scene.expected, [file], {file['id']: description(scene)})
    legacy.catalog_query.project(scene.index.db, file['id'])
    assert scene.index.db.execute('SELECT year FROM catalog_rows WHERE id=?', (file['id'],)).fetchone()[0] is None
    candidate = scene.index.item(scene.expected, file['id'])['candidates']
    candidate[-1]['year'] = 2026  # Intentional incompatible shape, never production output.
    scene.index.db.execute('UPDATE reviews SET candidates=? WHERE file=?', (json.dumps(candidate), file['id']))
    legacy.catalog_query.project(scene.index.db, file['id'])
    assert scene.index.db.execute('SELECT year FROM catalog_rows WHERE id=?', (file['id'],)).fetchone()[0] == 2026
    assert server_description.effective(candidate, 'filename', scene.provider) is None


def test_large_unicode_descriptions_obey_existing_reply_budget_and_paginate_without_loss(scene):
    from bobbi_core.server_ref import file_id
    selected = scene.pans.list_files(scene.expected, scene.parent, 1)['items'][0]
    refs = [from_selected(scene.expected, dict(selected, name='File-%02d.mkv' % number,
        file_id=file_id(scene.item_id, 'v%d' % number, 'p%d' % number)), scene.parent) for number in range(20)]
    value = server_description.observed(scene.provider, scene.item_id, title='中文'*120,
        overview='中'*1200, year=2024, ids=dict(tmdb='123'))
    batch(scene.index, scene.expected, refs, {file['id']: value for file in refs})
    for view in ('works', 'files'):
        cursor, seen = None, []
        while True:
            result = scene.index.query(scene.expected, query=dict(view=view), cursor=cursor, limit=32)
            assert len(catalog_query.wire(result)) <= 15000
            seen.extend(row['entity_id'] for row in result['items'])
            cursor = result['next_cursor']
            if not cursor:
                break
        assert len(seen) == len(set(seen)) == 20
    assert len(catalog_query.wire(scene.index.items(scene.expected))) <= 15000


def test_partial_current_description_does_not_reuse_old_year_or_ids(scene):
    scan(scene)
    claims(scene, year=None)
    scene.wire.claims['Guid' if scene.provider == 'plex' else 'ProviderIds'] = None
    scan(scene)
    card = scene.index.query(scene.expected)['items'][0]
    assert card['display_title'] == 'Changed source' and card['year'] is None
    assert card['server_description']['ids'] == {}


@pytest.mark.parametrize('event', ['cancel', 'logout', 'remove', 'registry_aba', 'profile_aba', 'manual'])
def test_delayed_description_page_cannot_publish_after_revocation_or_overwrite_manual(scene, monkeypatch, event):
    scan(scene)
    file = files(scene)[0]
    before = authority(scene.index)
    claims(scene, 'Delayed source title')
    entered, release = Event(), Event()
    original = NativePort.page
    def delayed(port, *args, **kwargs):
        reply = original(port, *args, **kwargs)
        assert any('description' in row for row in reply['items'])
        entered.set()
        assert release.wait(5), 'test did not release fetched page'
        return reply
    monkeypatch.setattr(NativePort, 'page', delayed)
    task = scene.service.start_scan(scene.expected, scene.directory['id'])['task_id']
    try:
        assert entered.wait(3)
        if event == 'cancel':
            scene.service.dispatch('catalog_cancel', dict(expected=scene.expected, task_id=task))
        elif event == 'logout':
            scene.accounts.logout(scene.expected)
        elif event in ('remove', 'registry_aba'):
            saved, generation = source(scene.root, scene.expected)
            registry = Registry(scene.root / 'libraries.sqlite3')
            try:
                if event == 'remove':
                    registry.remove(saved.id)
                else:
                    registry.save(replace(saved, name='Temporary B'))
                    registry.save(saved)
                    assert registry.source_snapshot(saved.id)[1] != generation
            finally:
                registry.close()
        elif event == 'profile_aba':
            scene.active[0] = False
            with pytest.raises(ValueError, match='PROFILE_CHANGED'):
                scene.service._profile()
            scene.active[0] = True
        else:
            scene.index.apply(scene.expected, uuid4().hex, [command(file, title='Manual during I/O')])
        release.set()
        scene.service.worker.join(5)
        assert not scene.service.worker.is_alive()
        job = scene.index._scan(task)
        if event == 'manual':
            assert job['state'] == 'completed'
            row = scene.index.item(scene.expected, file['id'])
            assert row['mapping']['title'] == 'Manual during I/O' and row['revision'] == 1
            assert row['provenance'] == 'manual' and row['candidates'][-1]['description']['title'] == 'Delayed source title'
            assert 'server_description' not in scene.index.query(scene.expected)['items'][0]
        else:
            assert job['state'] in ('canceled', 'failed', 'interrupted')
            assert authority(scene.index) == before
            assert 'Delayed source title' not in repr(authority(scene.index))
            if event == 'profile_aba':
                with pytest.raises(ValueError, match='PROFILE_CHANGED'):
                    scene.service.start_scan(scene.expected, scene.directory['id'])
    finally:
        release.set()


def test_real_local_http_scan_contract_uses_existing_get_routes_and_secret_headers_only(scene):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlsplit
    import time
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            requests.append((self.command, self.path, dict(self.headers)))
            path = urlsplit(self.path).path
            value = scene.wire.request(path)
            raw = json.dumps(value).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        base = 'http://127.0.0.1:%d' % http.server_port
        session = server_http.Session(scene.provider, base, 'fixture-http-secret')
        session.operation = SimpleNamespace(kind='scan', deadline=time.monotonic()+10,
            clock=time.monotonic, consume_request=lambda: None, check=lambda: None)
        saved = dict(location=base, token='fixture-http-secret',
            server_id='machine1' if scene.provider == 'plex' else 'server1',
            user_id='77' if scene.provider == 'plex' else 'user1')
        client = server_plex.Client(saved, session) if scene.provider == 'plex' else server_emby.Client(scene.provider, saved, session)
        result = client.list_files(scene.parent)
        desc = next(iter(result['catalog_descriptions'].values()))
        assert desc['title'] == 'Server film' and desc['ids']['tmdb'] == '42'
        assert set(result['items'][0]) == {'file_id', 'server_id', 'name', 'size', 'directory'}
        assert [(method, path) for method, path, _ in requests] == [('GET', path) for path in
            (['/identity', '/library/metadata/9'] if scene.provider == 'plex' else
             ['/System/Info', '/Users/Me', '/Users/user1/Items/item1'])]
        key, credential = {'plex': ('X-Plex-Token', 'fixture-http-secret'),
            'emby': ('X-Emby-Token', 'fixture-http-secret'),
            'jellyfin': ('Authorization', 'MediaBrowser Token="fixture-http-secret"')}[scene.provider]
        assert all({k.lower(): v for k, v in headers.items()}[key.lower()] == credential
                   and 'secret' not in path for _, path, headers in requests)
    finally:
        http.shutdown()
        http.server_close()
        thread.join(2)

"""Real atomic store and descriptive navigation; no credentials or device IO."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_ce2097_file_history import database, history, playback
from test_media_library_index import index, ref, insert, scope
from test_catalog_file_projection_contract import describe
from bobbi_core.catalog_query import opaque, wire, parameters
from bobbi_platform.catalog_navigation import history_links

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('saved_views_test_subject',
    ROOT/'addons/plugin.video.bobbi/lib/db/catalog_views.py')
views = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(views)


def create(store, title='我的收藏', query=None, expected=None, descriptor=None):
    return store.change(store.snapshot(), 'create', title=title, expected=expected or scope(),
                        query=query or {}, descriptor=descriptor)


def test_same_atomic_profile_store_survives_restart_without_old_scope(database):
    storage, path = database
    store = views.CatalogViews(storage.PickleDatabase())
    identifier = create(store, query=dict(view='files', text='中文'*80, sort='recent_added'))
    store.change(store.snapshot(), 'home', identifier=identifier)
    raw, saved = views.CatalogViews(storage.PickleDatabase()).snapshot()
    assert saved['active'] == identifier and len(saved['items']) == 1
    assert saved['items'][0]['owner'] == dict(provider='quark', account_id=scope()['account_id'])
    assert not {'epoch', 'scope', 'cursor', 'ticket', 'url', 'file_ref'} & set(saved['items'][0])
    assert b'authenticated' not in (path/'database.pickle').read_bytes()


def test_edit_cas_preserves_concurrent_history_and_rejects_other_editor(database):
    storage, _ = database
    one, two = views.CatalogViews(storage.PickleDatabase()), views.CatalogViews(storage.PickleDatabase())
    identifier = create(one)
    snapshot = one.snapshot()
    files = history.FileHistory(storage.PickleDatabase())
    session = files.begin(ref())
    assert files.save(playback(session, position=18))
    two.change(two.snapshot(), 'rename', identifier=identifier, title='已确认修改')
    with pytest.raises(ValueError, match='VIEW_CONFLICT'):
        one.change(snapshot, 'delete', identifier=identifier)
    assert one.snapshot()[1]['items'][0]['title'] == '已确认修改'
    assert files.get(ref()['id'])['position'] == 18
    one.change(one.snapshot(), 'rename', identifier=identifier, title='第二次修改')
    assert files.get(ref()['id'])['position'] == 18


def test_pending_operations_not_lost_on_cas_conflict(database):
    storage, _ = database
    first, second = storage.PickleDatabase(), storage.PickleDatabase()
    second.set_key('views', {'new': True})
    first.set_item('jt:lfh', 'pending', {'position': 42}, commit=False)
    assert not first.compare_and_set_key('views', None, {})
    assert first.has_pending() and first.commit()
    assert second.get_key('jt:lfh')['pending']['position'] == 42


def test_limit_reorder_delete_home_default_are_one_record_set(database):
    storage, _ = database
    store = views.CatalogViews(storage.PickleDatabase())
    ids = [create(store, title='收藏%d' % n) for n in range(32)]
    with pytest.raises(ValueError, match='VIEW_LIMIT'):
        create(store)
    store.change(store.snapshot(), 'up', identifier=ids[-1])
    assert store.snapshot()[1]['items'][-2]['id'] == ids[-1]
    store.change(store.snapshot(), 'home', identifier=ids[0])
    store.change(store.snapshot(), 'delete', identifier=ids[0])
    assert store.snapshot()[1]['active'] is None and len(store.snapshot()[1]['items']) == 31
    store.change(store.snapshot(), 'home', identifier=ids[1])
    store.change(store.snapshot(), 'default')
    assert store.snapshot()[1]['active'] is None


@pytest.mark.parametrize('query', [dict(cursor='a'*32), dict(epoch=1), dict(url='http://example.test'),
    dict(text='字'*161), dict(parent_entity_id='a'*64), dict(view='episodes')])
def test_invalid_or_unbound_saved_queries_are_rejected(database, query):
    storage, _ = database
    store = views.CatalogViews(storage.PickleDatabase())
    with pytest.raises(ValueError):
        create(store, query=query)
    assert not store.snapshot()[1]['items']


@pytest.mark.parametrize('title', ['', '字'*81, 'line\nbreak', 'plugin://bad'])
def test_title_is_bounded_and_not_executable(database, title):
    storage, _ = database
    with pytest.raises(ValueError):
        create(views.CatalogViews(storage.PickleDatabase()), title=title)


def test_explicit_profile_root_never_follows_new_kodi_translation(database, monkeypatch):
    storage, root = database
    monkeypatch.setattr(sys.modules['xbmcvfs'], 'translatePath', lambda _: str(root/'other'))
    explicit = storage.PickleDatabase(profile_root=root/'captured')
    explicit.set_key('views', {})
    assert (root/'captured/database.pickle').is_file() and not (root/'other/database.pickle').exists()
    with pytest.raises(ValueError, match='PROFILE_ROOT_INVALID'):
        storage.PickleDatabase(profile_root='relative')


def test_parent_semantics_are_confirmed_and_movie_tv_same_number_are_isolated(index):
    movie, tv = ref(1), ref(2)
    insert(index, [movie, tv])
    describe(index, movie, '版一', tmdb=20)
    describe(index, tv, '版二', kind='tv', tmdb=20)
    cards = index.describe_files(scope(), [movie['id'], tv['id']])['items']
    by_id = {card['entity_id']: card for card in cards}
    assert index.parent_descriptor(scope(), by_id[movie['id']]['parent_entity_id'])['metadata_key'] == 'tmdb:movie:20'
    assert index.parent_descriptor(scope(), by_id[tv['id']]['parent_entity_id'])['metadata_key'] == 'tmdb:tv:20'
    assert index.parent_descriptor(scope(), by_id[tv['id']]['parent_entity_id'])['entity_kind'] == 'episode'
    with pytest.raises(ValueError, match='PARENT_CHANGED'):
        index.parent_descriptor(scope('b'), by_id[movie['id']]['parent_entity_id'])
    assert not index.describe_files(scope('b'), [movie['id']])['items']


def test_holdings_one_batch_distinct_files_not_memberships_and_unknown(index):
    identities = ['tmdb:movie:20', 'tmdb:tv:20', 'tmdb:movie:21']
    assert all(row['state'] == 'unknown' and row['file_count'] is None for row in index.holdings(scope(), identities)['items'])
    movie, tv, unconfirmed = ref(1), ref(2), ref(3)
    insert(index, [movie, tv, unconfirmed])
    insert(index, [movie], source='b'*32)
    describe(index, movie, None, tmdb=20)
    describe(index, tv, None, kind='tv', tmdb=20)
    rows = index.holdings(scope(), identities)['items']
    assert [row['file_count'] for row in rows] == [1, 1, 0]
    assert rows[0]['entity_id'] != rows[1]['entity_id']
    assert rows[2]['state'] == 'not_indexed'
    with pytest.raises(ValueError):
        index.holdings(scope(), identities*7)


def accounts(expected):
    def require(value):
        if value != expected:
            raise ValueError('PAN_ACCOUNT_CHANGED')
        return value
    return SimpleNamespace(snapshot=lambda provider: dict(expected) if provider == expected['provider'] else {},
        require_current=require, is_current=lambda value: value == expected,
        run_if_current=lambda value, operation: operation() if require(value) else None)


def test_history_links_preserve_original_file_and_reject_replacement(index, database):
    storage, _ = database
    file = ref()
    insert(index, [file])
    describe(index, file, '导演剪辑')
    saved = history.FileHistory(storage.PickleDatabase())
    assert saved.save(playback(saved.begin(file), position=18))
    pans = SimpleNamespace(accounts=accounts(scope()))
    catalogue = SimpleNamespace(index=index)
    result = history_links(catalogue, pans, [file['id']], saved)
    card = result['items'][0]
    assert card['version_label'] == '导演剪辑' and card['parent_entity_id']
    assert 'file_ref' not in card and not {'ticket', 'url'} & set(card)
    before = saved.get(file['id'])
    insert(index, [dict(file, size=file['size'] + 1)])
    assert not history_links(catalogue, pans, [file['id']], saved)['items']
    assert saved.get(file['id']) == before


def test_manual_export_is_bounded_revision_guarded_and_omits_other_account(index):
    files = [ref(n) for n in range(7)]
    insert(index, files)
    for file in files:
        describe(index, file, '备注')
    result = index.manual_records(scope())
    assert len(result['items']) == 5 and result['next_offset'] == 5
    assert set(result['items'][0]) == {'file_ref', 'state', 'mapping', 'revision', 'provenance', 'available'}
    assert not index.manual_records(scope('b'), file_ids=[files[0]['id']])['items']
    describe(index, files[0], '新备注')
    with pytest.raises(ValueError, match='CURSOR_STALE'):
        index.manual_records(scope(), offset=5, projection_revision=result['projection_revision'])


def test_descriptive_batch_remains_within_wire_budget(index):
    files = [ref(n, name='中文'*400 + str(n) + '.mkv') for n in range(20)]
    insert(index, files)
    for file in files:
        describe(index, file, '备注'*40, title='标题'*80)
    result = index.describe_files(scope(), [file['id'] for file in files])
    assert len(wire(result)) <= 15000 and result['truncated']


@pytest.fixture
def saved_ui(database, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'addons/plugin.video.bobbi'))
    from lib.utils.views import catalog_saved_views as ui
    return ui


def test_clear_filters_then_save_does_not_restore_original_url_filters(database, saved_ui, monkeypatch):
    from lib.utils.views import personal_catalog
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace())
    storage, _ = database
    store = views.CatalogViews(storage.PickleDatabase())
    choices = iter((7, 8, 0, -1))  # Clear, save, new view, close filters.
    dialog = SimpleNamespace(select=lambda *a: next(choices), input=lambda *a, **kw: '已清除筛选',
                             notification=lambda *a: None)
    original_save = saved_ui.save
    monkeypatch.setattr(saved_ui, 'save', lambda *a: original_save(*a, store=store))
    monkeypatch.setattr(saved_ui, 'changed', lambda: None)
    monkeypatch.setattr(personal_catalog, 'origin_is_current', lambda *a: True)
    personal_catalog.filters(dialog, dict(view='files', source_id='b'*32, text='旧关键词',
        media_kind='movie', review_state='confirmed', availability='observed_present', sort='recent_edited'),
        scope(), None, lambda *a: None)
    query = store.snapshot()[1]['items'][0]['query']
    assert query == parameters(dict(view='files', source_id='b'*32, sort='name'))


def test_reopen_native_same_account_gets_new_epoch_but_never_new_account(database, saved_ui):
    storage, _ = database
    store = views.CatalogViews(storage.PickleDatabase())
    create(store)
    record = store.snapshot()[1]['items'][0]
    current = scope(epoch=9)
    def rpc(action, body):
        assert action == 'pan_status'
        return dict(providers=[dict(provider='quark', account=current)])
    expected, query = saved_ui.resolve(record, rpc)
    assert expected['epoch'] == 9 and query['view'] == 'works'
    current = scope('b', epoch=10)
    with pytest.raises(ValueError, match='VIEW_SCOPE_CHANGED'):
        saved_ui.resolve(record, rpc)


@pytest.mark.parametrize('kind,prefix', [('mounted_path', 'catalog_mount_'), ('local_path', 'catalog_local_')])
def test_saved_path_scope_cannot_silently_follow_replaced_root(database, saved_ui, kind, prefix):
    storage, _ = database
    store = views.CatalogViews(storage.PickleDatabase())
    original = dict(reference_kind=kind, source_id='a'*32, namespace='b'*64, generation='c'*64)
    create(store, expected=original)
    record = store.snapshot()[1]['items'][0]
    calls = []
    def rpc(action, body):
        calls.append(action)
        return dict(original, generation='d'*64)
    assert saved_ui.resolve(record, rpc)[0]['generation'] == 'd'*64
    assert calls == [prefix + 'scope']
    with pytest.raises(ValueError, match='VIEW_SCOPE_CHANGED'):
        saved_ui.resolve(record, lambda *args: dict(original, namespace='e'*64))


def test_saved_parent_semantics_are_rechecked_on_every_open(index, database, saved_ui):
    storage, _ = database
    store = views.CatalogViews(storage.PickleDatabase())
    file = ref()
    insert(index, [file])
    describe(index, file, None)
    parent_id = index.describe_files(scope(), [file['id']])['items'][0]['parent_entity_id']
    descriptor = index.parent_descriptor(scope(), parent_id)
    create(store, query=dict(view='files', parent_entity_id=parent_id), descriptor=descriptor)
    record = store.snapshot()[1]['items'][0]
    def rpc(action, body):
        if action == 'pan_status':
            return dict(providers=[dict(provider='quark', account=scope(epoch=2))])
        assert action == 'catalog_parent'
        return index.parent_descriptor(body['expected'], body['parent_id'])
    assert saved_ui.resolve(record, rpc)[1]['parent_entity_id'] == parent_id
    describe(index, file, None, tmdb=99)
    with pytest.raises(ValueError, match='PARENT_CHANGED'):
        saved_ui.resolve(record, rpc)


def test_named_view_ui_order_home_and_delete_keep_stable_record_id(database, saved_ui, monkeypatch):
    storage, _ = database
    store = views.CatalogViews(storage.PickleDatabase())
    identifier = create(store)
    changes = []
    monkeypatch.setattr(saved_ui, 'changed', lambda: changes.append('home'))
    dialog = SimpleNamespace(select=lambda *args: 1, input=lambda *args, **kw: '新名称', yesno=lambda *args: True)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: dialog))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(executebuiltin=lambda value: changes.append(value)))
    saved_ui.manage(dict(mode='view_edit', view_id=identifier), lambda *args: None, store)
    assert store.snapshot()[1]['items'][0]['id'] == identifier
    assert store.snapshot()[1]['items'][0]['title'] == '新名称'
    dialog.select = lambda *args: 4
    saved_ui.manage(dict(mode='view_edit', view_id=identifier), lambda *args: None, store)
    assert not store.snapshot()[1]['items'] and changes.count('home') == 2


def test_public_holdings_overlay_keeps_discovery_target_and_uses_one_batch(database, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'addons/plugin.video.bobbi'))
    from lib.utils.views.catalog_owned import annotate
    props, menu, calls = {}, [], []
    item = SimpleNamespace(setProperty=lambda key, value: props.update({key: value}), addContextMenuItems=menu.extend)
    def rpc(action, body):
        calls.append((action, body))
        return dict(state='ready', expected=scope(), items=[dict(metadata_key='tmdb:movie:10',
            entity_id='a'*64, entity_kind='work', media_kind='movie', state='observed', file_count=2)])
    annotate([(item, 'tmdb:movie:10')], rpc)
    assert len(calls) == 1 and props['Bobi.Catalog.OwnedCount'] == '2'
    assert 'parent_entity_id=' + 'a'*64 in props['Bobi.Catalog.Owned']
    assert menu[0][0] == '我的片库 · 2 个文件'
    assert 'play' not in props['Bobi.Catalog.Owned']

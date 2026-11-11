"""Real directory orchestration against fake Kodi; summaries never play media."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest

from test_library_plugin import plugin
from test_ce2096_pan_playback import entry
from bobbi_core.file_ref import from_selected

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def catalog(monkeypatch, plugin):
    monkeypatch.syspath_prepend(str(ROOT/'addons/plugin.video.bobbi'))
    spec = importlib.util.spec_from_file_location('personal_catalog_test',
        ROOT/'addons/plugin.video.bobbi/lib/utils/views/personal_catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plugin.catalog = module
    plugin.account = dict(provider='quark', account_id='quark:'+'f'*64, epoch=1, authenticated=True)
    plugin.query_calls, plugin.notices = [], []
    plugin.page = dict(items=[], next_cursor=None, projection_revision=1)
    plugin.on_query = None
    gui = sys.modules['xbmcgui']
    gui.Dialog = lambda: SimpleNamespace(ok=lambda *a: plugin.notices.append(a),
        notification=lambda *a: plugin.notices.append(a), input=lambda *a, **kw: '测试')

    def rpc(action, body):
        plugin.query_calls.append((action, deepcopy(body)))
        if action == 'pan_status':
            return dict(providers=[dict(provider='quark', account=deepcopy(plugin.account))])
        if action == 'catalog_query':
            if plugin.on_query:
                plugin.on_query(body)
            return deepcopy(plugin.page)
        pytest.fail('Unexpected authority/network operation: ' + action)
    plugin.rpc = rpc
    plugin.params = dict(provider='quark', scope=module.scope_key(plugin.account), view='works')
    return plugin


def card(kind='work', identifier='a'*64, **kw):
    return dict(entity_id=identifier, entity_kind=kind, display_title='作品', media_kind='tv',
                availability='observed_present', review_state='confirmed', variant_count=2, **kw)


@pytest.mark.parametrize('kind,view', [('work', 'seasons'), ('season', 'episodes'), ('episode', 'files')])
def test_relationship_directory_routes_opaque_identity_not_title(catalog, kind, view):
    catalog.page['items'] = [card(kind, season=0)]
    catalog.catalog.execute(catalog.params, 17, catalog.rpc)
    target, item, folder = catalog.rows[0]
    params = dict(parse_qsl(urlsplit(target).query))
    assert folder and params['view'] == view and params['parent_entity_id'] == 'a'*64
    assert item.info['season'] == 0 and item.properties['IsPlayable'] == 'false'
    assert item.properties['Bobi.CardKey'].endswith('a'*64)
    assert item.label2.endswith('2 个文件版本')
    assert [a for a, _ in catalog.query_calls] == ['pan_status', 'catalog_query', 'pan_status']
    assert not catalog.resolved


def test_file_variants_keep_exact_file_history_and_are_not_direct_urls(catalog, monkeypatch):
    ref = from_selected(catalog.account, dict(file_id='f1', name='one.mkv', size=100, directory=False), '0')
    other = from_selected(catalog.account, dict(file_id='f2', name='two.mkv', size=200, directory=False), '0')
    record_spec = importlib.util.spec_from_file_location('file_history_test',
        ROOT/'addons/plugin.video.bobbi/lib/db/file_history.py')
    history_module = importlib.util.module_from_spec(record_spec)
    record_spec.loader.exec_module(history_module)
    row = dict(version=1, id=ref['id'], file_ref=ref, position=25, duration=100,
        completion_reason='STOP', updated_at=1, generation=1, session_id='a'*32, sequence=1)
    history_module.FileHistory = lambda: SimpleNamespace(database=SimpleNamespace(
        get_key_checked=lambda key: {ref['id']: row}))
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', history_module)
    catalog.page['items'] = [card('file', ref['id']), card('file', other['id'])]
    catalog.catalog.execute(dict(catalog.params, view='files'), 17, catalog.rpc)
    for target, item, folder in catalog.rows:
        assert not folder and item.properties['IsPlayable'] == 'false'
        params = dict(parse_qsl(urlsplit(target).query))
        assert params['action'] == 'personal_catalog_play'
        assert set(params) == {'action', 'object_id', 'provider', 'scope'}
        assert 'url' not in params and 'file_ref' not in params
    assert catalog.rows[0][1].properties['PercentPlayed'] == '25'
    assert 'PercentPlayed' not in catalog.rows[1][1].properties
    assert not catalog.resolved


def test_account_epoch_change_during_query_cannot_publish_private_cards(catalog):
    catalog.page['items'] = [card()]
    catalog.on_query = lambda body: catalog.account.update(epoch=2)
    catalog.catalog.execute(catalog.params, 17, catalog.rpc)
    assert not catalog.rows and catalog.notices
    assert catalog.ended[-1][1]['succeeded'] is False


def test_cursor_stale_restarts_once_and_keeps_query(catalog):
    catalog.page['items'], catalog.page['next_cursor'] = [card()], 'b'*32
    def stale(body):
        if body['cursor']:
            raise ValueError('CATALOG_CURSOR_STALE')
    catalog.on_query = stale
    catalog.catalog.execute(dict(catalog.params, cursor='c'*32, text='作品'), 17, catalog.rpc)
    reads = [body for action, body in catalog.query_calls if action == 'catalog_query']
    assert [body['cursor'] for body in reads] == ['c'*32, None]
    assert reads[0]['query'] == reads[1]['query'] and len(catalog.notices) == 1
    target = dict(parse_qsl(urlsplit(catalog.rows[-1][0]).query))
    assert target['cursor'] == 'b'*32 and target['text'] == '作品'


def test_rail_does_not_offer_pagination_or_refresh_other_windows(catalog):
    catalog.page.update(items=[card()], next_cursor='a'*32)
    catalog.catalog.execute(dict(catalog.params, mode='rail'), 17, catalog.rpc)
    assert len(catalog.rows) == 1 and not catalog.calls
    assert catalog.ended[-1][1]['cacheToDisc'] is False
    assert [b['limit'] for a, b in catalog.query_calls if a == 'catalog_query'] == [20]
    assert catalog.rows[0][1].properties['Bobi.Rail.State'] == 'ready'
    assert catalog.rows[0][1].properties['Bobi.Rail.Revision'] == '1'
    assert catalog.params['scope'] in catalog.rows[0][1].properties['node.visible']


class RailCache:
    def __init__(self): self.rows = {}
    def get(self, key): return deepcopy(self.rows.get(key))
    def set(self, key, page, ttl): self.rows[key] = deepcopy(page)


def test_rail_same_scope_query_failure_keeps_stale_cards(catalog):
    cache = RailCache()
    catalog.page['items'] = [card()]
    params = dict(catalog.params, mode='rail')
    catalog.catalog.execute(params, 17, catalog.rpc, cache)
    old_path = catalog.rows[0][0]
    catalog.rows.clear()
    def fail(_): raise OSError('unavailable')
    catalog.on_query = fail
    catalog.catalog.execute(params, 17, catalog.rpc, cache)
    assert catalog.rows[0][0] == old_path
    assert catalog.rows[0][1].properties['Bobi.Rail.State'] == 'stale'
    assert not catalog.notices


def test_rail_old_scope_cache_and_late_response_cannot_publish_after_account_switch(catalog):
    cache = RailCache()
    catalog.page['items'] = [card()]
    params = dict(catalog.params, mode='rail')
    catalog.catalog.execute(params, 17, catalog.rpc, cache)
    catalog.rows.clear()
    catalog.on_query = lambda _: catalog.account.update(epoch=2)
    catalog.catalog.execute(params, 17, catalog.rpc, cache)
    assert len(catalog.rows) == 1
    assert catalog.rows[0][1].properties['Bobi.Rail.State'] == 'auth_required'
    assert 'Bobi.CardKey' not in catalog.rows[0][1].properties
    assert not catalog.notices


def test_empty_and_failed_rail_have_distinct_real_recovery_routes(catalog):
    params = dict(catalog.params, mode='rail')
    catalog.catalog.execute(params, 17, catalog.rpc, RailCache())
    assert catalog.rows[0][1].properties['Bobi.Rail.State'] == 'empty'
    assert 'personal_catalog_manage' in catalog.rows[0][0]
    catalog.rows.clear()
    def fail(_): raise OSError('unavailable')
    catalog.on_query = fail
    catalog.catalog.execute(params, 17, catalog.rpc, RailCache())
    assert catalog.rows[0][1].properties['Bobi.Rail.State'] == 'error'
    assert 'bobi_retry_rail' in catalog.rows[0][0] and not catalog.rows[0][2]
    assert not catalog.notices


def test_authenticated_115_does_not_break_other_personal_provider_scope(catalog):
    catalog.page['items'] = [card()]
    original = catalog.rpc
    def rpc(action, body):
        value = original(action, body)
        if action == 'pan_status':
            value['providers'].insert(0, dict(provider='115', account=dict(
                account_id='115:'+'a'*64, epoch=1, authenticated=True)))
        return value
    catalog.catalog.execute(catalog.params, 17, rpc)
    assert len(catalog.rows) == 1 and not catalog.notices


def test_late_private_result_after_real_thread_account_switch_is_rejected(catalog):
    from threading import Event, Thread
    started, release = Event(), Event()
    catalog.page['items'] = [card()]
    def pause(_):
        started.set()
        assert release.wait(3)
    catalog.on_query = pause
    worker = Thread(target=catalog.catalog.execute,
        args=(dict(catalog.params, mode='rail'), 17, catalog.rpc, RailCache()))
    worker.start()
    assert started.wait(3)
    catalog.account.update(epoch=2, account_id='quark:'+'c'*64)
    release.set()
    worker.join(3)
    assert not worker.is_alive()
    assert len(catalog.rows) == 1 and catalog.rows[0][1].properties['Bobi.Rail.State'] == 'auth_required'
    assert not any('Bobi.CardKey' in item.properties for _, item, _ in catalog.rows)


@pytest.mark.parametrize('native', [True, False])
@pytest.mark.parametrize('cancel', [True, False])
@pytest.mark.parametrize('logged_in_115', [False, True])
def test_index_selection_reserves_existing_owner_before_verification(entry, monkeypatch, native, cancel, logged_in_115):
    spec = importlib.util.spec_from_file_location('lib.utils.views.personal_catalog',
        ROOT/'addons/plugin.video.bobbi/lib/utils/views/personal_catalog.py')
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    monkeypatch.setitem(sys.modules, 'lib.utils.views.personal_catalog', catalog)
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(
        FileHistory=lambda: SimpleNamespace(get=lambda identifier: None)))
    entry.native = native
    ref = from_selected(entry.expected, entry.file, '0')
    entry.claim_extra = dict(file_ref=ref)
    original = entry.module.call
    def call(action, body, **kw):
        if action == 'pan_status':
            entry.calls.append((action, body))
            providers = [dict(provider='quark', account=entry.expected)]
            if logged_in_115:
                # 115 retains its pre-existing scope without a provider field.
                # Its authentication must not block another indexed provider.
                providers.insert(0, dict(provider='115', account=dict(
                    account_id='115:'+'a'*64, epoch=1, authenticated=True)))
            return dict(providers=providers)
        if action == 'catalog_prepare_play':
            entry.calls.append((action, body))
            entry.ticket, entry.cancel = body['request_id'], cancel
            return dict(ticket=entry.ticket)
        return original(action, body, **kw)
    monkeypatch.setattr(entry.module, 'call', call)
    entry.module.indexed(dict(object_id=ref['id'], provider='quark', scope=catalog.scope_key(entry.expected)))
    actions = [a for a, _ in entry.calls]
    assert actions.index('native_select' if native else 'standard_playback') < actions.index('catalog_prepare_play')
    assert actions.count('native_select' if native else 'standard_playback') == (2 if cancel and not native else 1)
    if cancel:
        assert not entry.played and 'pan_claim_play' not in actions
        assert 'pan_cancel_operation' in actions and 'pan_close_stream' in actions
    else:
        assert len(entry.played) == 1 and not entry.errors
        assert entry.played[0]['file_evidence'] == 'USER_CONFIRMED_FILE'
        assert entry.played[0]['_file_resume_position'] == 0


def test_mismatched_index_claim_cannot_play_another_file(entry):
    ref = from_selected(entry.expected, entry.file, '0')
    entry.claim_extra = dict(file_ref=ref)
    entry.module.play(dict(ticket=entry.ticket), reservation=dict(account=entry.expected,
        owner={'request_id': entry.ticket}, object_id='0'*64, file_ref=None, position=0))
    assert not entry.played and entry.errors
    assert 'pan_open_stream' not in [a for a, _ in entry.calls]

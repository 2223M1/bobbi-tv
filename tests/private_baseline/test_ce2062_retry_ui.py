"""Real picker callbacks + session/pump + native-list FIFO model; no playback."""
from pathlib import Path
from threading import Event

import pytest

from test_source_incremental_ui import window, source
from test_ce2015_list_binding import QueuedControl
from bobbi_core.source_list_session import SourceListSession
from bobbi_core.progressive_search import ProgressiveSearch
from bobbi_core.search_admission import try_acquire
from bobbi_core.search_completion import SearchCompletion, SearchResults


@pytest.mark.parametrize('filtered', [False, True])
def test_retry_button_preserves_native_cards_filter_and_focus(window, monkeypatch, tmp_path, filtered):
    from lib.gui import source_select as ui
    monkeypatch.setattr(ui, 'kodilog', lambda *a, **kw: None)
    control = window.display_list = QueuedControl()
    props = {}
    window.setProperty = lambda key, value: props.__setitem__(key, value)
    window._refresh_frontend_metadata = lambda **kw: None
    window._source_revision = -1
    window.last_error = ''
    window._auto_select_pending = False
    window._source_interacted = False
    window._selection_locked = False
    window.list_sources = []
    window._filter_spec = ('quality_tab', '1080p') if filtered else None
    window.filter_applied = filtered
    session = window.source_session = SourceListSession({}, lambda rows: rows)
    a, b, c = source('a'), source('b'), source('c', '2160p')
    count = [0]
    release, entered = Event(), Event()
    def flaky():
        count[0] += 1
        if count[0] == 1:
            return SearchResults([], SearchCompletion(1, failed=1))
        entered.set()
        release.wait(3)
        return [c]
    def setup(manager):
        manager.submit_task('Good', 'qqdocs', lambda: [a, b])
        manager.submit_task('Flaky', 'sharelib', flaky)
    pump = window.source_pump = ProgressiveSearch(session, setup, lambda rows: rows,
        admission=lambda: try_acquire(tmp_path/'lease'))
    try:
        pump.start(); pump.thread.join(3)
        window._refresh_progressive_sources(force=True)
        control.dispatch()
        control.selectItem(1); control.dispatch()
        survivor = control.getSelectedItem()
        resets = control.resets
        assert props['source_retry_visible'] == 'true'
        window.handle_action(7, 1500)
        assert entered.wait(2)
        control.dispatch()
        assert control.getSelectedItem() is survivor and control.resets == resets
        assert window.filter_applied is filtered
        assert window._source_interacted and not window._auto_select_pending
        release.set(); pump.thread.join(3)
        window._refresh_progressive_sources(); control.dispatch()
        assert control.getSelectedItem() is survivor and control.resets == resets
        assert len(window.list_sources) == (2 if filtered else 3)
        assert props['source_retry_visible'] == 'true'  # Focused button does not disappear.
        assert props['source_retry_label'] == '查询已完成'
        assert not props['playback_error']
        assert session.confirmed is None
    finally:
        release.set(); pump.cancel(); pump.thread.join(3)


def test_partial_empty_is_not_claimed_to_be_no_resources():
    from lib.cinema.source_presentation import search_status
    from dataclasses import asdict
    row = dict(state='PARTIAL', error='', completion=asdict(
        SearchCompletion(2, succeeded=1, failed=1)))
    summary, error, _ = search_status({'sharelib': row}, False)
    assert summary == '部分来源未完成' and error == '1 个来源查询失败或超时'
    row['completion'] = asdict(SearchCompletion(2, succeeded=1, skipped=1))
    assert search_status({'sharelib': row}, False)[1] == ''


def test_provider_status_does_not_republish_unchanged_window_metadata(window, monkeypatch):
    from lib.gui import source_select as ui
    monkeypatch.setattr(ui, 'kodilog', lambda *a, **kw: None)
    window._refresh_frontend_metadata = lambda **kw: None
    window._source_revision = -1
    window.last_error = ''
    window._auto_select_pending = False
    window.list_sources = []
    window.source_pump = None
    window._filter_spec = None
    applied = []
    window.add_item_information_to_window = lambda info: applied.append(info.copy())
    session = window.source_session = SourceListSession({}, lambda rows: rows)
    session.set_metadata({'title': 'Example', 'year': 2026})
    window._refresh_progressive_sources(force=True)
    session.publish(session.epoch, 'first', state='RUNNING')
    window._refresh_progressive_sources()
    session.publish(session.epoch, 'first', state='FAILED', error='timeout')
    window._refresh_progressive_sources()
    assert len(applied) == 1  # Status-only updates do not rewrite all header fields.
    session.set_metadata({'title': 'Example localized', 'year': 2026})
    window._refresh_progressive_sources()
    assert len(applied) == 2 and applied[-1]['title'] == 'Example localized'
    window._refresh_progressive_sources(force=True)
    assert len(applied) == 3  # A reopened native window receives its full state.


def test_retry_has_native_theme_button_and_remote_navigation():
    import xml.etree.ElementTree as ET
    root = Path(__file__).resolve().parents[2]
    xml = ET.parse(root/'addons/plugin.video.bobbi/resources/skins/Default/1080i/source_select.xml')
    button = xml.find('.//control[@id="1500"]')
    assert button.findtext('font') == 'Button24'
    assert button.findtext('texturefocus') == 'bobbi/pill.png'
    assert button.findtext('focusedcolor') == 'FF0A0B0E'
    assert button.findtext('onright') == '1300'
    assert xml.findtext('.//control[@id="1000"]/onleft') == '1500'
    assert xml.findtext('.//control[@id="1300"]/onleft') == '1500'


def test_actual_source_entry_reuses_metadata_and_only_resubmits_failed_provider(monkeypatch, tmp_path):
    from lib import search
    from lib.clients import bobbi_library, catalog_providers, mdsub_provider
    from lib.clients.tmdb.utils import utils
    from lib.utils.general import cinema_source_rank
    metadata, requests = [], []
    monkeypatch.setattr(search, 'get_setting', lambda key, default=None: default)
    monkeypatch.setattr(search, 'reconcile_source_selection', lambda **kw: None)
    monkeypatch.setattr(search, '_build_search_cache_scope', lambda *a: 'fixture')
    monkeypatch.setattr(search, '_movie_catalog_context', lambda *a: None)
    monkeypatch.setattr(search, '_tv_completed_context', lambda *a: None)
    monkeypatch.setattr(search, 'build_media_metadata', lambda *a, **kw: {})
    monkeypatch.setattr(search, '_cinema_catalog_aliases', lambda *a, **kw: [])
    monkeypatch.setattr(search, '_build_title_fallback_queries', lambda *a, **kw: ['Fixture'])
    monkeypatch.setattr(search, '_search_worker_count', lambda *a: 2)
    monkeypatch.setattr(utils, 'get_tmdb_media_details', lambda *a: metadata.append(1) or {})
    monkeypatch.setattr(bobbi_library, 'load_index', lambda **kw: {})
    monkeypatch.setattr(bobbi_library, 'find_sources', lambda *a: [])
    monkeypatch.setattr(mdsub_provider, 'find_sources', lambda *a, **kw: [])
    monkeypatch.setattr(catalog_providers, 'submit_catalogs', lambda *a, **kw: None)
    monkeypatch.setattr(cinema_source_rank, 'rank_sources', lambda rows, context: rows)
    from bobbi_platform import paths
    # Exercise the actual entry capture, cache and OS admission in this profile.
    monkeypatch.setattr(paths, '_translated_profile_root', lambda addon: tmp_path / addon)
    def healthy():
        requests.append('good')
        return []
    def failed():
        requests.append('bad')
        return SearchResults([], SearchCompletion(1, failed=1))
    def submit(manager, *a, **kw):
        manager.submit_task('Good', 'jackett', healthy)
        manager.submit_task('Bad', 'sharelib', failed)
    monkeypatch.setattr(search, '_submit_search_tasks_managed', submit)
    def choose(*a, source_pump, **kw):
        assert source_pump.current.__self__.root('plugin.video.bobbi') == tmp_path / 'plugin.video.bobbi'
        assert source_pump.scope_current()
        source_pump.thread.join(3)
        assert source_pump.retry_failed()
        source_pump.thread.join(3)
        assert requests == ['good', 'bad', 'bad']
        return False
    monkeypatch.setattr(search, 'show_source_select', choose)
    search._run_progressive_source_entry({'force_select': True}, 'Fixture', {'tmdb_id': 1},
        'movies', 'movie', {}, False, '', 'default', 'localized_first', 2024, False, {}, [])
    assert metadata == [1]


@pytest.mark.parametrize('enabled', [False, True])
def test_legacy_and_managed_submit_use_the_same_plan(monkeypatch, enabled):
    from lib import search
    calls = []
    class Submission:
        def submit_task(self, name, key, function, *args, **kwargs):
            calls.append((function, args, kwargs))
        def submit(self, function, *args, **kwargs):
            calls.append((function, args, kwargs))
            return object()
    settings = {key: enabled for key in search.BUILTIN_INDEXER_SETTINGS.values()}
    settings['easynews_enabled'] = enabled
    monkeypatch.setattr(search, 'get_setting', lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(search, '_is_source_enabled', lambda *a, **kw: True)
    monkeypatch.setattr(search, 'get_selected_stream_addons', lambda: [])
    args = (None, 'Fixture', 'tv', 'tv', 1, 2, {'tmdb_id': 1}, '', 1, 'tt123')
    submission = Submission()
    search._submit_search_tasks_managed(submission, *args)
    managed = list(calls)
    calls.clear()
    tasks = []
    search._submit_search_tasks(submission, tasks, *args, show_dialog=True)
    assert len(calls) == len(managed) == len(tasks)
    for old, new in zip(calls, managed):
        assert old[:2] == new[:2]
        assert old[2] == dict(new[2], show_dialog=True)
    assert any(row[1][0] == search.Indexer.EXTERNAL_SCRAPER for row in calls) is enabled

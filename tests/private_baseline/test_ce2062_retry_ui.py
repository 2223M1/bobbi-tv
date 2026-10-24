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
        manager.submit_task('Flaky', 'juku', flaky)
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
    summary, error, _ = search_status({'juku': row}, False)
    assert summary == '部分来源未完成' and error == '1 个来源查询失败或超时'
    row['completion'] = asdict(SearchCompletion(2, succeeded=1, skipped=1))
    assert search_status({'juku': row}, False)[1] == ''


def test_retry_has_native_theme_button_and_remote_navigation():
    import xml.etree.ElementTree as ET
    root = Path(__file__).resolve().parents[2]
    xml = ET.parse(root/'addons/plugin.video.bobbi/resources/skins/Default/1080i/source_select.xml')
    button = xml.find('.//control[@id="1500"]')
    assert button.findtext('font') == 'Button24'
    assert button.findtext('texturefocus') == 'bobi/pill.png'
    assert button.findtext('focusedcolor') == 'FF0A0B0E'
    assert button.findtext('onright') == '1300'
    assert xml.findtext('.//control[@id="1000"]/onleft') == '1500'
    assert xml.findtext('.//control[@id="1300"]/onleft') == '1500'


def test_actual_source_entry_reuses_metadata_and_only_resubmits_failed_provider(monkeypatch, tmp_path):
    from lib import search
    from lib.clients import bobi_library, catalog_providers, mdsub_provider
    from lib.clients.tmdb.utils import utils
    from lib.utils.general import cinema_source_rank
    import bobbi_core.progressive_search as progressive
    metadata, requests = [], []
    monkeypatch.setattr(search, 'get_setting', lambda key, default=None: default)
    monkeypatch.setattr(search, 'reconcile_source_selection', lambda **kw: None)
    monkeypatch.setattr(search, '_build_search_cache_scope', lambda *a: 'fixture')
    monkeypatch.setattr(search, '_movie_catalog_context', lambda *a: None)
    monkeypatch.setattr(search, '_tv_completed_context', lambda *a: None)
    monkeypatch.setattr(search, 'build_media_metadata', lambda *a, **kw: {})
    monkeypatch.setattr(search, '_cinema_catalog_aliases', lambda *a, **kw: [])
    monkeypatch.setattr(search, '_build_title_fallback_queries', lambda *a, **kw: ['Fixture'])
    monkeypatch.setattr(search, '_search_worker_count', lambda: 2)
    monkeypatch.setattr(utils, 'get_tmdb_media_details', lambda *a: metadata.append(1) or {})
    monkeypatch.setattr(bobi_library, 'load_index', lambda: {})
    monkeypatch.setattr(bobi_library, 'find_sources', lambda *a: [])
    monkeypatch.setattr(mdsub_provider, 'find_sources', lambda *a: [])
    monkeypatch.setattr(catalog_providers, 'submit_catalogs', lambda *a, **kw: None)
    monkeypatch.setattr(cinema_source_rank, 'rank_sources', lambda rows, context: rows)
    from bobbi_platform import paths
    monkeypatch.setattr(paths, 'profile', lambda *a: tmp_path/'trace')
    # Keep the coordinator implementation and OS lease; avoid sharing a test lease.
    original = progressive.ProgressiveSearch
    monkeypatch.setattr(progressive, 'ProgressiveSearch', lambda *a, **kw: original(
        *a, **kw, admission=lambda: try_acquire(tmp_path/'lease')))
    def healthy():
        requests.append('good')
        return []
    def failed():
        requests.append('bad')
        return SearchResults([], SearchCompletion(1, failed=1))
    def submit(manager, *a, **kw):
        manager.submit_task('Good', 'jackett', healthy)
        manager.submit_task('Bad', 'juku', failed)
    monkeypatch.setattr(search, '_submit_search_tasks_managed', submit)
    def choose(*a, source_pump, **kw):
        source_pump.thread.join(3)
        assert source_pump.retry_failed()
        source_pump.thread.join(3)
        assert requests == ['good', 'bad', 'bad']
        return False
    monkeypatch.setattr(search, 'show_source_select', choose)
    search._run_progressive_source_entry({'force_select': True}, 'Fixture', {'tmdb_id': 1},
        'movies', 'movie', {}, False, '', 'default', 'localized_first', 2024, False, {}, [])
    assert metadata == [1]

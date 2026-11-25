"""Contract regressions for U12 (CT-SEARCH-FAILURE) and U13 (CT-TRAKT-UNKNOWN).

Covers:
- F-ROOT-SEARCH-FAILURE-1..4
- F-ROOT-TRAKT-UNKNOWN-EMPTY-1..4
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import runpy
import sqlite3
import sys
from threading import Event
import time
from types import SimpleNamespace

import pytest
import requests
from requests.exceptions import ReadTimeout

ROOT = Path(__file__).resolve().parents[2]
for rel in (
    'addons/script.module.bobbi.core/lib',
    'addons/script.module.bobbi.platform/lib',
    'addons/plugin.video.bobbi',
):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)


from bobbi_core.progressive_search import ProgressiveSearch
from bobbi_core.search_completion import (
    SearchCompletion,
    SearchResults,
    provider_diagnostics,
    provider_failed,
)
from bobbi_core.source_list_session import SourceListSession


class _DummyLease:
    def retain(self):
        pass

    def release(self, *_args):
        pass


def _create_trakt_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        'CREATE TABLE IF NOT EXISTS trakt_data (id TEXT UNIQUE, data TEXT)'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS watched ('
        'db_type TEXT, media_id TEXT, season INTEGER, episode INTEGER, '
        'last_played TEXT, title TEXT, '
        'UNIQUE(db_type, media_id, season, episode))'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS progress ('
        'db_type TEXT, media_id TEXT, season INTEGER, episode INTEGER, '
        'resume_point TEXT, curr_time TEXT, last_played TEXT, '
        'paused_id INTEGER, title TEXT, '
        'UNIQUE(db_type, media_id, season, episode))'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS watched_status ('
        'db_type TEXT, media_id TEXT, status TEXT)'
    )


# ==============================================================================
# U12: CT-SEARCH-FAILURE (F-ROOT-SEARCH-FAILURE-1..4)
# ==============================================================================

@pytest.mark.parametrize(
    'scenario,expect_state,expect_retryable',
    [
        ('http_503', 'FAILED', True),
        ('timeout', 'TIMEOUT', True),
        ('bad_json', 'FAILED', True),
        ('schema_dict', 'FAILED', True),
        ('http_200_empty', 'COMPLETE', False),
    ],
)
def test_u12_f1_prowlarr_503_timeout_bad_json_retryable_vs_200_empty_complete(
    monkeypatch, scenario, expect_state, expect_retryable
):
    """F-ROOT-SEARCH-FAILURE-1: 503/timeout/bad JSON are retryable failures; 200 [] is COMPLETE empty."""
    import xbmc
    from lib import search
    from lib.clients.prowlarr import Prowlarr

    monkeypatch.setattr(xbmc, 'getSkinDir', lambda: 'skin.bobbi.cinema')
    client = Prowlarr(
        'http://127.0.0.1',
        'test-key',
        '9696',
        lambda *_: None,
        settings_getter=lambda key, default=None: default,
    )
    client.session.close()

    def _fake_get(*_a, **_kw):
        if scenario == 'http_503':
            return SimpleNamespace(status_code=503, json=lambda: [])
        if scenario == 'timeout':
            raise ReadTimeout('simulated prowlarr read timeout')
        if scenario == 'bad_json':
            return SimpleNamespace(
                status_code=200,
                json=lambda: (_ for _ in ()).throw(ValueError('truncated json')),
            )
        if scenario == 'schema_dict':
            return SimpleNamespace(status_code=200, json=lambda: {'message': 'upstream error'})
        return SimpleNamespace(status_code=200, json=lambda: [])

    client.session = SimpleNamespace(get=_fake_get)
    monkeypatch.setattr(search, 'get_client', lambda *_a, **_kw: client)

    session = SourceListSession({'query': 'Dune'}, lambda rows: rows)

    def _setup(pump):
        pump.submit_task(
            'Prowlarr',
            search.Indexer.PROWLARR,
            search._perform_search,
            search.Indexer.PROWLARR,
            None,
            'Dune',
            'movies',
            show_dialog=False,
            cancelled=pump.scope_cancelled,
            deadline=pump.deadline,
        )

    pump = ProgressiveSearch(session, _setup, lambda rows: rows, budget=2.0, admission=_DummyLease)
    pump.start()
    pump.thread.join(3.0)
    try:
        status = session.status()
        prov_key = next(k for k in status['providers'] if k != 'setup')
        prov_row = status['providers'][prov_key]
        assert prov_row['state'] == expect_state
        assert bool(pump.retry_candidates()) is expect_retryable
        assert provider_failed(prov_row) is expect_retryable
        diag = provider_diagnostics({prov_key: prov_row})
        assert diag[0]['provider'] == 'prowlarr'
        assert diag[0]['state'] == expect_state
    finally:
        pump.cancel()

    # Unified non-Jackett None adapter contract across non-Cinema skins too
    monkeypatch.setattr(xbmc, 'getSkinDir', lambda: 'skin.estuary')
    monkeypatch.setattr(search, 'get_client', lambda *_a, **_kw: SimpleNamespace(search=lambda *_x, **_y: None))
    none_res = search._perform_search(search.Indexer.EASYNEWS, None, 'Dune', 'movies', show_dialog=False)
    assert isinstance(none_res, SearchResults) and list(none_res) == []
    assert none_res.completion == SearchCompletion(1, failed=1)


def test_u12_f2_partial_shard_success_shows_results_and_retries_failed_shard(monkeypatch):
    """F-ROOT-SEARCH-FAILURE-2: TV episode shard 200 + season-pack shard 503 shows partial results and retries failed shard."""
    from lib import search
    from lib.clients.prowlarr import Prowlarr

    settings = {'include_season_packs': True, 'prowlarr_timeout': 5}
    client = Prowlarr(
        'http://127.0.0.1',
        'test-key',
        '9696',
        lambda *_: None,
        settings_getter=lambda k, default=None: settings.get(k, default),
    )
    client.session.close()
    pack_healthy = [False]

    def _shard_get(_url, *, params=None, **_kw):
        q = (params or {}).get('query', '')
        if 'S01E02' in q:
            return SimpleNamespace(
                status_code=200,
                json=lambda: [{
                    'title': 'Andor.S01E02.1080p.WEB-DL',
                    'indexer': 'IndexerA',
                    'guid': 'magnet:?xt=urn:btih:' + 'a' * 40,
                    'downloadUrl': 'magnet:?xt=urn:btih:' + 'a' * 40,
                    'magnetUrl': 'magnet:?xt=urn:btih:' + 'a' * 40,
                    'infoHash': 'a' * 40,
                    'seeders': 25,
                    'peers': 30,
                    'size': 2_000_000_000,
                }],
            )
        # Season pack shard S01 fails on first attempt, succeeds on retry
        if not pack_healthy[0]:
            return SimpleNamespace(status_code=503, json=lambda: [])
        return SimpleNamespace(
            status_code=200,
            json=lambda: [{
                'title': 'Andor.S01.COMPLETE.1080p.WEB-DL',
                'indexer': 'IndexerB',
                'guid': 'magnet:?xt=urn:btih:' + 'b' * 40,
                'downloadUrl': 'magnet:?xt=urn:btih:' + 'b' * 40,
                'magnetUrl': 'magnet:?xt=urn:btih:' + 'b' * 40,
                'infoHash': 'b' * 40,
                'seeders': 40,
                'peers': 50,
                'size': 18_000_000_000,
            }],
        )

    client.session = SimpleNamespace(get=_shard_get)
    monkeypatch.setattr(search, 'get_client', lambda *_a, **_kw: client)

    session = SourceListSession({'query': 'Andor'}, lambda rows: rows)

    def _setup(pump):
        pump.submit_task(
            'Prowlarr',
            search.Indexer.PROWLARR,
            search._perform_search,
            search.Indexer.PROWLARR,
            None,
            'Andor',
            'tv',
            1,
            2,
            None,
            show_dialog=False,
            cancelled=pump.scope_cancelled,
            deadline=pump.deadline,
        )

    pump = ProgressiveSearch(session, _setup, lambda rows: rows, budget=3.0, admission=_DummyLease)
    try:
        pump.start()
        pump.thread.join(3.0)
        status1 = session.status()
        prov_key = next(k for k in status1['providers'] if k != 'setup')
        assert len(session.entries) == 1
        assert status1['providers'][prov_key]['state'] == 'PARTIAL'
        assert status1['providers'][prov_key]['completion']['planned'] == 2
        assert status1['providers'][prov_key]['completion']['succeeded'] == 1
        assert status1['providers'][prov_key]['completion']['failed'] == 1
        assert pump.retry_candidates() == (prov_key,)

        # Explicit user retry recovers the failed S01 pack shard into the same session
        pack_healthy[0] = True
        assert pump.retry_failed() is True
        pump.thread.join(3.0)
        status2 = session.status()
        assert len(session.entries) == 2
        assert status2['providers'][prov_key]['state'] == 'COMPLETE'
        assert pump.retry_candidates() == ()
    finally:
        pump.cancel()


@pytest.mark.parametrize('revocation', ['back_cancel', 'new_search_session', 'profile_switch'])
def test_u12_f3_back_new_search_or_profile_switch_blocks_late_result_backfill(monkeypatch, revocation):
    """F-ROOT-SEARCH-FAILURE-3: Late responses after back/cancel, new search, or profile switch never backfill."""
    from lib import search
    from lib.clients.prowlarr import Prowlarr

    entered, release = Event(), Event()
    profile_active = [True]
    shard_calls = []

    client = Prowlarr(
        'http://127.0.0.1',
        'test-key',
        '9696',
        lambda *_: None,
        settings_getter=lambda k, default=None: True if k == 'include_season_packs' else default,
    )
    client.session.close()

    def _slow_get(_url, *, params=None, **_kw):
        shard_calls.append((params or {}).get('query', ''))
        entered.set()
        release.wait(2.0)
        return SimpleNamespace(
            status_code=200,
            json=lambda: [{
                'title': 'Late.Stale.Result.S01E01.1080p',
                'indexer': 'StaleIdx',
                'guid': 'magnet:?xt=urn:btih:' + 'c' * 40,
                'downloadUrl': 'magnet:?xt=urn:btih:' + 'c' * 40,
                'magnetUrl': 'magnet:?xt=urn:btih:' + 'c' * 40,
                'infoHash': 'c' * 40,
                'seeders': 10,
                'peers': 10,
                'size': 1_000_000_000,
            }],
        )

    client.session = SimpleNamespace(get=_slow_get)
    monkeypatch.setattr(search, 'get_client', lambda *_a, **_kw: client)

    session_old = SourceListSession({'query': 'OldSearch'}, lambda rows: rows)
    session_new = SourceListSession({'query': 'NewSearch'}, lambda rows: rows)

    def _setup(pump):
        pump.submit_task(
            'Prowlarr',
            search.Indexer.PROWLARR,
            search._perform_search,
            search.Indexer.PROWLARR,
            None,
            'OldSearch',
            'tv',
            1,
            1,
            None,
            show_dialog=False,
            cancelled=pump.scope_cancelled,
            deadline=pump.deadline,
        )

    pump = ProgressiveSearch(
        session_old,
        _setup,
        lambda rows: rows,
        budget=3.0,
        admission=_DummyLease,
        current=lambda: profile_active[0],
    )
    pump.start()
    assert entered.wait(1.5)

    if revocation == 'back_cancel':
        pump.cancel()
    elif revocation == 'new_search_session':
        # User navigated away and opened a new search session
        pump.cancel()
    elif revocation == 'profile_switch':
        profile_active[0] = False
        assert pump.scope_cancelled() is True

    release.set()
    pump.thread.join(2.0)
    for fut in getattr(pump, '_futures', ()):
        fut.result(2.0)

    assert len(session_old.entries) == 0
    assert len(session_new.entries) == 0
    # Second shard (S01 season pack) was skipped immediately once cancelled!
    assert len(shard_calls) == 1


def test_u12_f4_cancel_returns_promptly_without_freezing_ui_on_slow_network(monkeypatch):
    """F-ROOT-SEARCH-FAILURE-4: Cancelling source picker while network is slow returns in <150ms without blocking UI."""
    from lib import search
    from lib.clients.prowlarr import Prowlarr

    entered, release = Event(), Event()
    observed_timeouts = []

    client = Prowlarr(
        'http://127.0.0.1',
        'test-key',
        '9696',
        lambda *_: None,
        settings_getter=lambda k, default=None: 25 if k == 'prowlarr_timeout' else default,
    )
    client.session.close()

    def _blocking_get(_url, *, timeout=None, **_kw):
        observed_timeouts.append(timeout)
        entered.set()
        release.wait(2.0)
        raise ReadTimeout('slow network closed')

    client.session = SimpleNamespace(get=_blocking_get)
    monkeypatch.setattr(search, 'get_client', lambda *_a, **_kw: client)

    session = SourceListSession({'query': 'SlowMovie'}, lambda rows: rows)

    def _setup(pump):
        pump.submit_task(
            'Prowlarr',
            search.Indexer.PROWLARR,
            search._perform_search,
            search.Indexer.PROWLARR,
            None,
            'SlowMovie',
            'movies',
            show_dialog=False,
            cancelled=pump.scope_cancelled,
            deadline=pump.deadline,
        )

    pump = ProgressiveSearch(session, _setup, lambda rows: rows, budget=1.5, admission=_DummyLease)
    try:
        pump.start()
        assert entered.wait(1.5)
        t0 = time.monotonic()
        pump.cancel()
        cancel_elapsed = time.monotonic() - t0
        assert cancel_elapsed < 0.15, f'UI cancel blocked for {cancel_elapsed:.3f}s'
        assert observed_timeouts and observed_timeouts[0] <= 1.55
    finally:
        release.set()
        pump.thread.join(2.0)


# ==============================================================================
# U13: CT-TRAKT-UNKNOWN (F-ROOT-TRAKT-UNKNOWN-EMPTY-1..4)
# ==============================================================================

@pytest.fixture
def isolated_trakt_env(tmp_path, monkeypatch):
    from lib.api.trakt import trakt as trakt_mod
    from lib.api.trakt import trakt_cache as tc_mod
    from lib.services import trakt_sync as ts_mod
    from lib.utils.kodi import utils as kodi_utils

    db_path = tmp_path / 'trakt.db'
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    conn.execute('PRAGMA journal_mode = OFF')  # Exact production base_cache pragma!
    _create_trakt_schema(conn)

    settings_store = {
        'trakt_user': 'alice',
        'is_trakt_auth': 'true',
        'trakt_enabled': 'true',
        'trakt_client': 'client-id-123',
        'trakt_secret': 'client-secret-456',
    }
    props_store = {
        'trakt_token': 'tok-alice',
        'trakt_refresh': 'ref-alice',
        'trakt_expires': str(int(time.time()) + 7200),
    }

    def _get_setting(key, default=''):
        return settings_store.get(key, default)

    def _set_setting(key, val):
        settings_store[key] = val

    def _get_prop(key):
        return props_store.get(key, '')

    def _set_prop(key, val):
        props_store[key] = str(val)

    for target_mod in (kodi_utils, trakt_mod, tc_mod, ts_mod):
        if hasattr(target_mod, 'get_setting'):
            monkeypatch.setattr(target_mod, 'get_setting', _get_setting)
        if hasattr(target_mod, 'set_setting'):
            monkeypatch.setattr(target_mod, 'set_setting', _set_setting)
        if hasattr(target_mod, 'get_property'):
            monkeypatch.setattr(target_mod, 'get_property', _get_prop)
        if hasattr(target_mod, 'set_property'):
            monkeypatch.setattr(target_mod, 'set_property', _set_prop)

    monkeypatch.setattr(trakt_mod, 'trakt_client', lambda: settings_store['trakt_client'])
    monkeypatch.setattr(trakt_mod, 'trakt_secret', lambda: settings_store['trakt_secret'])
    monkeypatch.setattr(trakt_mod, 'notification', lambda *_a, **_kw: None)
    monkeypatch.setattr(tc_mod, 'connect_database', lambda _name: conn)
    monkeypatch.setattr(trakt_mod, 'connect_database', lambda _name: conn)

    fresh_watched = tc_mod.TraktWatched()
    monkeypatch.setattr(tc_mod, 'trakt_watched_cache', fresh_watched)
    monkeypatch.setattr(ts_mod, 'trakt_watched_cache', fresh_watched)

    try:
        yield SimpleNamespace(
            conn=conn,
            settings=settings_store,
            props=props_store,
            trakt_mod=trakt_mod,
            tc_mod=tc_mod,
            ts_mod=ts_mod,
            watched_cache=fresh_watched,
        )
    finally:
        conn.close()


@pytest.mark.parametrize(
    'fault_mode',
    ['bad_json', 'http_401', 'http_503', 'timeout', 'missing_token', 'non_list_json'],
)
def test_u13_f1_unknown_errors_preserve_snapshots_while_200_empty_clears_only_target_bucket(
    isolated_trakt_env, monkeypatch, fault_mode
):
    """F-ROOT-TRAKT-UNKNOWN-EMPTY-1: Bad JSON/401/5xx/timeout/no-token preserve all buckets; 200 [] clears ONLY target bucket."""
    env = isolated_trakt_env
    wc = env.watched_cache
    wc.set_bulk_movie_watched([('movie', '101', None, None, '2026-01-01T00:00:00.000Z', 'Inception')])
    wc.set_bulk_tvshow_watched([('episode', '202', 1, 1, '2026-01-02T00:00:00.000Z', 'Severance')])
    wc.set_bulk_movie_progress([('movie', '303', None, None, '45.5', '0', '2026-01-03T00:00:00.000Z', 11, 'Heat')])
    wc.set_bulk_tvshow_progress([('episode', '404', 2, 3, '62.0', '0', '2026-01-04T00:00:00.000Z', 22, 'Dark - S2E3')])

    def _fake_send(_self, path, *_a, **_kw):
        if fault_mode == 'timeout':
            raise requests.Timeout(f'timeout on {path}')
        resp = requests.Response()
        resp.headers['Content-Type'] = 'application/json'
        if fault_mode == 'bad_json':
            resp.status_code = 200
            resp._content = b'{corrupt-json'
        elif fault_mode == 'non_list_json':
            resp.status_code = 200
            resp._content = b'{"unexpected":"object"}'
        elif fault_mode == 'http_401':
            resp.status_code = 401
            resp._content = b'{"error":"invalid_token"}'
        elif fault_mode == 'http_503':
            resp.status_code = 503
            resp._content = b'Service Unavailable'
        return resp

    monkeypatch.setattr(env.trakt_mod.TraktBase, '_send_request', _fake_send)
    monkeypatch.setattr(env.trakt_mod.TraktBase, '_wait_for_retry', staticmethod(lambda _d: False))
    if fault_mode == 'missing_token':
        monkeypatch.setattr(env.trakt_mod.TraktBase, 'ensure_token_valid', lambda _self: False)
    else:
        monkeypatch.setattr(env.trakt_mod.TraktBase, 'ensure_token_valid', lambda _self: True)

    api = env.trakt_mod.TraktAPI()
    svc = env.ts_mod.TraktSyncService(api=api, monitor=SimpleNamespace())

    for sync_fn in (
        svc.sync_watched_movies,
        svc.sync_watched_shows,
        svc.sync_movie_progress,
        svc.sync_episode_progress,
    ):
        if fault_mode in ('http_503', 'timeout'):
            with pytest.raises(env.trakt_mod.ProviderException):
                sync_fn()
        else:
            assert sync_fn() is False

    # Every single cached row across all 4 buckets MUST remain intact!
    assert wc.get_watched_status('movie', '101') is True
    assert wc.get_watched_status('episode', '202', 1, 1) is True
    assert wc.get_progress('movie', '303') == pytest.approx(45.5)
    assert wc.get_progress('episode', '404', 2, 3) == pytest.approx(62.0)

    # Now verify genuine HTTP 200 [] clears ONLY its own bucket while leaving the other 3 untouched
    env.settings['trakt_user'] = 'alice'
    env.settings['is_trakt_auth'] = 'true'
    env.props['trakt_token'] = 'tok-alice'
    monkeypatch.setattr(env.trakt_mod.TraktBase, 'ensure_token_valid', lambda _self: True)

    def _empty_200(_self, _path, *_a, **_kw):
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'[]'
        return resp

    monkeypatch.setattr(env.trakt_mod.TraktBase, '_send_request', _empty_200)
    assert svc.sync_watched_movies() is True
    assert wc.get_watched_status('movie', '101') is False
    assert wc.get_watched_status('episode', '202', 1, 1) is True
    assert wc.get_progress('movie', '303') == pytest.approx(45.5)
    assert wc.get_progress('episode', '404', 2, 3) == pytest.approx(62.0)


def test_u13_f2_mid_replacement_failure_rolls_back_without_exposing_half_snapshot(isolated_trakt_env):
    """F-ROOT-TRAKT-UNKNOWN-EMPTY-2: Mid-replacement SQLite or payload error rolls back completely (zero half-snapshot)."""
    env = isolated_trakt_env
    wc = env.watched_cache
    wc.set_bulk_movie_watched([
        ('movie', '101', None, None, '2026-01-01T00:00:00.000Z', 'Original Movie 1'),
        ('movie', '102', None, None, '2026-01-02T00:00:00.000Z', 'Original Movie 2'),
    ])
    wc.set_bulk_tvshow_watched([
        ('episode', '999', 1, 1, '2026-01-03T00:00:00.000Z', 'Untouched Show'),
    ])

    # 1. SQLite failure AFTER DELETE and AFTER 1st row insert (2nd row has wrong column arity -> ProgrammingError!)
    with pytest.raises(sqlite3.ProgrammingError):
        wc.set_bulk_movie_watched([
            ('movie', '555', None, None, '2026-02-01T00:00:00.000Z', 'Partial Row That Must Roll Back'),
            ('movie', '556'),  # Invalid tuple arity triggers error mid-executemany!
        ])

    rows = env.conn.execute(
        "SELECT media_id, title FROM watched WHERE db_type='movie' ORDER BY media_id"
    ).fetchall()
    assert rows == [
        ('101', 'Original Movie 1'),
        ('102', 'Original Movie 2'),
    ]
    assert wc.get_watched_status('movie', '555') is False
    assert wc.get_watched_status('episode', '999', 1, 1) is True

    # 2. Malformed API item halfway through TraktSyncService.sync_watched_movies
    svc = env.ts_mod.TraktSyncService(
        api=SimpleNamespace(
            movies=SimpleNamespace(
                get_watched_movies=lambda: [
                    {'last_watched_at': '2026-03-01T00:00:00.000Z', 'movie': {'title': 'Valid', 'ids': {'tmdb': 777}}},
                    {'broken_item': True},
                ]
            )
        ),
        monitor=SimpleNamespace(),
    )
    with pytest.raises(ValueError):
        svc.sync_watched_movies()
    assert env.conn.execute(
        "SELECT media_id FROM watched WHERE db_type='movie' ORDER BY media_id"
    ).fetchall() == [('101',), ('102',)]


def test_u13_f3_account_a_b_a_isolation_and_watermark_never_advances_past_failed_bucket(isolated_trakt_env):
    """F-ROOT-TRAKT-UNKNOWN-EMPTY-3: Account A->B->A isolation and per-bucket watermark retention on partial failure."""
    env = isolated_trakt_env
    wc = env.watched_cache

    # --- Part 1: Account A -> B -> A strict isolation ---
    env.settings['trakt_user'] = 'alice'
    act_alice = deepcopy(env.tc_mod.default_activities())
    act_alice['all'] = '2026-05-01T10:00:00.000Z'
    act_alice['movies']['watched_at'] = '2026-05-01T10:00:00.000Z'
    wc.set_bulk_movie_watched([('movie', '101', None, None, '2026-05-01T10:00:00.000Z', 'Alice Movie')])
    wc.set_bulk_movie_progress([('movie', '101', None, None, '33.0', '0', '2026-05-01T10:00:00.000Z', 1, 'Alice Movie')])
    env.tc_mod.set_activity(act_alice)
    assert wc.get_watched_status('movie', '101') is True
    assert wc.get_progress('movie', '101') == pytest.approx(33.0)

    # Switch to Account B ('bob'): even BEFORE bob syncs, alice's watched/progress/activity are invisible!
    env.settings['trakt_user'] = 'bob'
    assert wc.get_watched_status('movie', '101') is False
    assert wc.get_progress('movie', '101') == 0.0
    assert env.tc_mod.get_activity()['movies']['watched_at'] == env.tc_mod.default_activities()['movies']['watched_at']

    # Bob syncs movie 202
    wc.set_bulk_movie_watched([('movie', '202', None, None, '2026-05-02T10:00:00.000Z', 'Bob Movie')])
    assert wc.get_watched_status('movie', '202') is True
    assert wc.get_watched_status('movie', '101') is False

    # Switch back to Account A ('alice'): Bob's movie 202 is immediately invisible, and Alice re-syncs cleanly
    env.settings['trakt_user'] = 'alice'
    assert wc.get_watched_status('movie', '202') is False
    wc.set_bulk_movie_watched([('movie', '101', None, None, '2026-05-03T10:00:00.000Z', 'Alice Movie')])
    assert wc.get_watched_status('movie', '101') is True
    assert wc.get_watched_status('movie', '202') is False

    # --- Part 2: Activity watermark never advances past an unsynced/failed bucket ---
    base_act = deepcopy(env.tc_mod.default_activities())
    env.tc_mod.set_activity(base_act)

    next_act = deepcopy(base_act)
    next_act['all'] = '2026-06-10T12:00:00.000Z'
    next_act['movies']['watched_at'] = '2026-06-10T12:00:00.000Z'
    next_act['episodes']['watched_at'] = '2026-06-10T12:00:00.000Z'

    shows_ok = [False]
    calls = {'movies': 0, 'shows': 0}

    def _movies_api():
        calls['movies'] += 1
        return [{'last_watched_at': '2026-06-10T12:00:00.000Z', 'movie': {'title': 'M1', 'ids': {'tmdb': 901}}}]

    def _shows_api():
        calls['shows'] += 1
        if not shows_ok[0]:
            return None  # Unknown response (e.g. bad JSON / 401) on Cycle 1
        return [{
            'show': {'title': 'S1', 'ids': {'tmdb': 902}},
            'seasons': [{'number': 1, 'episodes': [{'number': 1, 'last_watched_at': '2026-06-10T12:00:00.000Z'}]}],
        }]

    svc = env.ts_mod.TraktSyncService(
        api=SimpleNamespace(
            sync=SimpleNamespace(get_last_activities=lambda: deepcopy(next_act)),
            movies=SimpleNamespace(get_watched_movies=_movies_api),
            tv=SimpleNamespace(get_watched_shows=_shows_api),
            scrobble=SimpleNamespace(trakt_get_playback_progress=lambda _t: []),
        ),
        monitor=SimpleNamespace(),
    )

    applied1 = svc.sync_activities(force=False)
    assert applied1 == {'watched_movies'}
    saved_after_1 = env.tc_mod.get_activity()
    assert saved_after_1['movies']['watched_at'] == '2026-06-10T12:00:00.000Z'
    # Failed bucket watermark AND top-level 'all' MUST stay at base_act!
    assert saved_after_1['episodes']['watched_at'] == base_act['episodes']['watched_at']
    assert saved_after_1['all'] == base_act['all']

    # Cycle 2 with identical server activities retries ONLY the failed watched_shows bucket!
    shows_ok[0] = True
    applied2 = svc.sync_activities(force=False)
    assert applied2 == {'watched_shows'}
    assert calls == {'movies': 1, 'shows': 2}
    saved_after_2 = env.tc_mod.get_activity()
    assert saved_after_2['episodes']['watched_at'] == '2026-06-10T12:00:00.000Z'
    assert saved_after_2['all'] == '2026-06-10T12:00:00.000Z'
    assert wc.get_watched_status('episode', '902', 1, 1) is True


def test_u13_f4_trakt_emby_and_local_bobbi_history_keep_separate_storage_owners(
    isolated_trakt_env, tmp_path
):
    """F-ROOT-TRAKT-UNKNOWN-EMPTY-4: Trakt cache, Emby writeback, and Bobbi local FileHistory keep separate storage owners."""
    from bobbi_core.file_ref import from_selected
    from bobbi_platform.emby_session import EmbyInvalidationHub, EmbySessionReporter
    from bobbi_platform.server_progress import item_progress
    from lib.db.file_history import FileHistory
    from lib.db.pickle_db import PickleDatabase

    env = isolated_trakt_env
    wc = env.watched_cache

    # 1. Real Bobbi local FileHistory owner backed by isolated PickleDatabase
    local_db = PickleDatabase(profile_root=tmp_path)
    file_hist = FileHistory(database=local_db, clock=lambda: 1700000000.0)
    fref = from_selected(
        {'provider': '115', 'account_id': '115:' + '1' * 64, 'authenticated': True},
        {'file_id': 'fid-101', 'name': 'Movie.101.mkv', 'directory': False, 'size': 4_000_000_000},
        'dir-1',
    )
    sess = file_hist.begin(fref)
    assert sess is not None

    # 2. Real Emby server_progress + EmbySessionReporter owner
    emby_prog = item_progress(
        'emby',
        'emby-101',
        {'RunTimeTicks': 36_000_000_000, 'UserData': {'PlaybackPositionTicks': 7_770_000_000, 'Played': False}},
    )
    assert emby_prog['position'] == pytest.approx(777.0)

    emby_calls = []

    class _EmbyClient:
        session = SimpleNamespace(
            budget=lambda *_: __import__('contextlib').nullcontext(),
            request=lambda path, **kw: emby_calls.append((path, kw.get('data', {}).get('ItemId'))),
        )

        def set_played(self, iid, played=True):
            emby_calls.append(('set_played', iid))

        def _item(self, _iid):
            return {'UserData': {'Played': False, 'PlaybackPositionTicks': 3_000_000_000}}

    hub = EmbyInvalidationHub(tmp_path)
    reporter = EmbySessionReporter(tmp_path, hub, client_loader=lambda *_: (_EmbyClient(), {}), start_worker=False)

    # 3. Seed Trakt, then run Trakt 200 [] clear and Trakt clear_all
    wc.set_bulk_movie_watched([('movie', '101', None, None, '2026-01-01T00:00:00.000Z', 'M101')])
    assert wc.get_watched_status('movie', '101') is True
    wc.set_bulk_movie_watched([])
    wc.clear_all()
    assert wc.get_watched_status('movie', '101') is False

    # Local Bobbi FileHistory and Emby state are 100% untouched by Trakt mutations
    assert file_hist.get(fref['id'])['session_id'] == sess['session_id']
    assert emby_calls == []

    # Conversely, Emby writeback events never write into trakt_db or local FileHistory
    wc.set_bulk_movie_watched([('movie', '505', None, None, '2026-02-01T00:00:00.000Z', 'M505')])
    emby_meta = {
        'provider': 'emby',
        'source_id': 'a' * 32,
        'source_generation': 'b' * 64,
        'server_id': 's1',
        'user_id': 'u1',
        'item_id': 'emby-101',
        'media_source_id': 'ms1',
        'play_session_id': 'ps1',
    }
    reporter.on_playback_event({
        'event': 'AV_START',
        'request_id': 'f' * 32,
        'position': 5.0,
        'duration': 600.0,
        'observed_clock': True,
        'data': {'_owned_source': emby_meta},
    })
    reporter.on_playback_event({
        'event': 'TERMINAL',
        'request_id': 'f' * 32,
        'position': 600.0,
        'duration': 600.0,
        'reason': 'NATURAL_EOF',
        'observed_clock': True,
        'data': {'_owned_source': emby_meta},
    })
    reporter.drain_once()
    reporter.drain_once()
    assert '/Sessions/Playing/Stopped' in [p for p, _ in emby_calls]
    assert wc.get_watched_status('movie', '505') is True
    assert wc.get_watched_status('movie', 'emby-101') is False
    assert file_hist.get(fref['id'])['session_id'] == sess['session_id']

    reporter.close()
    hub.close()


@pytest.mark.parametrize('bucket', ['watched_movies', 'watched_shows', 'movie_progress', 'episode_progress'])
@pytest.mark.parametrize('switch', ['other_account', 'same_account_new_session'])
def test_round2_trakt_inflight_snapshot_cannot_replace_new_account_or_session(isolated_trakt_env, bucket, switch):
    env = isolated_trakt_env
    wc = env.watched_cache

    def late_response():
        env.settings['trakt_user'] = 'bob' if switch == 'other_account' else 'alice'
        env.props['trakt_token'] = 'new-login-token'
        wc.set_bulk_movie_watched([('movie', '202', None, None, '2026-11-25', 'New login')])
        wc.set_bulk_tvshow_watched([('episode', '202', 1, 1, '2026-11-25', 'New login')])
        wc.set_bulk_movie_progress([('movie', '202', None, None, '50', '0', '2026-11-25', 2, 'New login')])
        wc.set_bulk_tvshow_progress([('episode', '202', 1, 1, '50', '0', '2026-11-25', 2, 'New login')])
        return []  # A real empty A snapshot is still not a snapshot of this new login.

    service = env.ts_mod.TraktSyncService(api=SimpleNamespace(
        movies=SimpleNamespace(get_watched_movies=late_response),
        tv=SimpleNamespace(get_watched_shows=late_response),
        scrobble=SimpleNamespace(trakt_get_playback_progress=lambda _kind: late_response()),
    ), monitor=SimpleNamespace())
    assert getattr(service, 'sync_' + bucket)() is False
    assert wc.get_watched_status('movie', '202') is True
    assert wc.get_watched_status('episode', '202', 1, 1) is True
    assert wc.get_progress('movie', '202') == 50.0
    assert wc.get_progress('episode', '202', 1, 1) == 50.0


def test_round2_trakt_late_activity_watermark_cannot_skip_new_account_sync(isolated_trakt_env):
    env = isolated_trakt_env
    prior = deepcopy(env.tc_mod.default_activities())
    env.tc_mod.set_activity(prior)
    calls = []

    def late_activities():
        env.settings['trakt_user'] = 'bob'
        env.props['trakt_token'] = 'bob-login'
        env.watched_cache.bind_account('bob')
        changed = deepcopy(prior)
        changed['all'] = '2026-11-25T20:00:00.000Z'
        changed['movies']['watched_at'] = changed['all']
        return changed

    service = env.ts_mod.TraktSyncService(api=SimpleNamespace(
        sync=SimpleNamespace(get_last_activities=late_activities),
        movies=SimpleNamespace(get_watched_movies=lambda: calls.append('movies') or []),
    ), monitor=SimpleNamespace())
    assert service.sync_activities() == set()
    assert calls == []
    assert env.tc_mod.get_activity() == prior


@pytest.mark.parametrize('status', [200, 401])
def test_round2_trakt_late_auth_response_cannot_return_a_data_or_revoke_b(isolated_trakt_env, monkeypatch, status):
    env = isolated_trakt_env

    def send(_self, _path, *_args, **_kwargs):
        env.settings['trakt_user'] = 'bob'
        env.props.update(trakt_token='bob-token', trakt_refresh='bob-refresh')
        response = requests.Response()
        response.status_code = status
        response._content = b'[{"alice":"private"}]'
        response._content_consumed = True
        return response

    monkeypatch.setattr(env.trakt_mod.TraktBase, '_send_request', send)
    assert env.trakt_mod.TraktBase().call_trakt('sync/watched/movies') is None
    assert env.settings['trakt_user'] == 'bob'
    assert env.props['trakt_token'] == 'bob-token'
    assert env.props['trakt_refresh'] == 'bob-refresh'


@pytest.mark.parametrize('status', [200, 401])
def test_round2_trakt_late_refresh_cannot_overwrite_or_revoke_b(isolated_trakt_env, monkeypatch, status):
    env = isolated_trakt_env

    def send(_self, _path, *_args, **_kwargs):
        env.settings['trakt_user'] = 'bob'
        env.props.update(trakt_token='bob-token', trakt_refresh='bob-refresh')
        response = requests.Response()
        response.status_code = status
        response._content = b'{"access_token":"alice-late","refresh_token":"alice-late-refresh","expires_in":3600}'
        response._content_consumed = True
        return response

    monkeypatch.setattr(env.trakt_mod.TraktBase, '_send_request', send)
    api = env.trakt_mod.TraktBase()
    api.trakt_refresh = 'ref-alice'
    assert api.trakt_refresh_token() is False
    assert env.settings['trakt_user'] == 'bob'
    assert env.props['trakt_token'] == 'bob-token'
    assert env.props['trakt_refresh'] == 'bob-refresh'


def test_round2_trakt_device_login_result_cannot_replace_login_changed_during_poll(isolated_trakt_env, monkeypatch):
    env = isolated_trakt_env
    auth = env.trakt_mod.TraktAuthentication()
    monkeypatch.setattr(auth, 'trakt_get_device_code', lambda: {'device_code': 'synthetic'})

    def finish_poll(_code):
        env.settings['trakt_user'] = 'bob'
        env.props.update(trakt_token='bob-token', trakt_refresh='bob-refresh')
        return {'access_token': 'alice-late', 'refresh_token': 'alice-late-refresh', 'expires_in': 3600}

    monkeypatch.setattr(auth, 'trakt_get_device_token', finish_poll)
    monkeypatch.setattr(auth, 'call_trakt', lambda *_a, **_kw: {'username': 'alice'})
    assert auth.trakt_authenticate() is False
    assert env.settings['trakt_user'] == 'bob'
    assert env.props['trakt_token'] == 'bob-token'


@pytest.mark.parametrize('cycle', [False, True])
def test_round2_trakt_normal_token_refresh_still_syncs_in_same_cycle(isolated_trakt_env, monkeypatch, cycle):
    env = isolated_trakt_env
    env.props['trakt_expires'] = str(time.time() - 1)
    calls = []

    def send(_self, path, *_args, **_kwargs):
        calls.append(path)
        if path == 'oauth/token':
            body = {'access_token': 'new-alice', 'refresh_token': 'new-refresh', 'expires_in': 7200}
        elif path == 'sync/last_activities':
            body = deepcopy(env.tc_mod.default_activities())
            body['movies']['watched_at'] = '2026-11-25T20:00:00.000Z'
            body['all'] = body['movies']['watched_at']
        elif path == 'sync/watched/movies':
            body = [{'last_watched_at': '2026-11-25', 'movie': {'title': 'Alice', 'ids': {'tmdb': 101}}}]
        else:
            raise AssertionError(path)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode()
        response._content_consumed = True
        return response

    monkeypatch.setattr(env.trakt_mod.TraktBase, '_send_request', send)
    service = env.ts_mod.TraktSyncService(api=env.trakt_mod.TraktAPI(), monitor=SimpleNamespace())
    result = service.sync_activities() if cycle else service.sync_watched_movies()
    assert result == {'watched_movies'} if cycle else result is True
    assert calls[0] == 'oauth/token'
    assert calls.count('oauth/token') == 1
    assert env.watched_cache.get_watched_status('movie', '101') is True


def test_round2_trakt_current_401_still_revokes_only_current_login(isolated_trakt_env, monkeypatch):
    env = isolated_trakt_env
    response = requests.Response()
    response.status_code = 401
    response._content = b'{}'
    response._content_consumed = True
    monkeypatch.setattr(env.trakt_mod.TraktBase, '_send_request', lambda *_a, **_kw: response)
    assert env.trakt_mod.TraktBase().call_trakt('sync/watched/movies') is None
    assert env.props['trakt_token'] == ''
    assert env.props['trakt_refresh'] == ''
    assert env.settings['is_trakt_auth'] == 'false'


def test_round2_trakt_account_change_at_sql_commit_rolls_back_snapshot(isolated_trakt_env):
    env = isolated_trakt_env
    wc = env.watched_cache
    wc.set_bulk_movie_watched([('movie', '101', None, None, '2026-11-25', 'Original')])
    scope = env.tc_mod.trakt_account_scope()

    def rows():
        yield ('movie', '202', None, None, '2026-11-25', 'Discarded')
        env.settings['trakt_user'] = 'bob'
        env.props['trakt_token'] = 'bob-login'

    assert wc.set_bulk_movie_watched(rows(), expected_scope=scope) is False
    assert env.conn.execute('SELECT media_id FROM watched').fetchall() == [('101',)]


def test_round2_trakt_device_login_positive_binds_new_owner(isolated_trakt_env, monkeypatch):
    env = isolated_trakt_env
    auth = env.trakt_mod.TraktAuthentication()
    monkeypatch.setattr(auth, 'trakt_get_device_code', lambda: {'device_code': 'synthetic'})
    monkeypatch.setattr(auth, 'trakt_get_device_token', lambda _: {
        'access_token': 'bob-token', 'refresh_token': 'bob-refresh', 'expires_in': 7200,
    })
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"username":"bob"}'
    response._content_consumed = True
    monkeypatch.setattr(auth, '_send_request', lambda *_a, **_kw: response)
    assert auth.trakt_authenticate() is True
    assert env.settings['trakt_user'] == 'bob'
    assert env.props['trakt_token'] == 'bob-token'
    assert env.props['trakt_refresh'] == 'bob-refresh'
    assert env.tc_mod._stored_cache_owner(env.conn) == 'bob'

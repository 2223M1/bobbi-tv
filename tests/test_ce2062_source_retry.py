"""In-place recovery uses the real coordinator, subscription and OS admission."""
from pathlib import Path
import sys
from threading import Event
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core.progressive_search import ProgressiveSearch
from bobbi_core.search_admission import try_acquire
from bobbi_core.search_completion import SearchCompletion, SearchResults
from bobbi_core.source_list_session import SourceListSession


def source(key):
    return SimpleNamespace(title=key, infoHash=key*40)


def finish(pump):
    pump.thread.join(3)
    assert not pump.thread.is_alive()


def test_retry_only_failed_task_keeps_cards_focus_and_fresh_request_context(tmp_path):
    session = SourceListSession({'tmdb': 1}, lambda rows: rows)
    calls, contexts = [], []
    a, b = source('a'), source('b')

    def healthy():
        calls.append('healthy')
        return [a]

    def flaky(deadline, cancelled):
        calls.append('flaky')
        contexts.append((deadline, cancelled))
        if calls.count('flaky') == 1:
            raise TimeoutError()
        assert deadline > time.monotonic() and not cancelled.is_set()
        return [b]

    def setup(manager):
        manager.submit_task('Good', 'juku', healthy)
        manager.submit_task('Flaky', 'jackett', flaky, manager.deadline, manager.cancelled)

    pump = ProgressiveSearch(session, setup, lambda rows: rows,
        admission=lambda: try_acquire(tmp_path/'lease'), budget=2)
    pump.start()
    finish(pump)
    session.focus(session.key(a), 0)
    old_epoch = session.epoch
    assert pump.retry_failed()
    assert not pump.retry_failed()  # Never stack retries.
    finish(pump)
    assert calls == ['healthy', 'flaky', 'flaky']
    assert contexts[0][1].is_set() and contexts[0][1] is not contexts[1][1]
    assert contexts[1][0] > contexts[0][0]
    snapshot = session.snapshot()
    assert snapshot['epoch'] == old_epoch
    assert [row.title for _, row in snapshot['entries']] == ['a', 'b']
    assert session.focus_key == session.key(a)
    assert all(row['state'] == 'COMPLETE' for row in snapshot['providers'].values())
    assert not pump.retry_failed()
    pump.cancel()


@pytest.mark.parametrize('receipt,eligible', [
    (SearchCompletion(2, succeeded=1, failed=1), True),
    (SearchCompletion(2, succeeded=1, timed_out=1), True),
    (SearchCompletion(2, succeeded=1, skipped=1), False),
    (SearchCompletion(1, succeeded=1, truncated=1), False),
    (SearchCompletion(1, succeeded=1, stale=1, snapshot_age=100), False),
    (SearchCompletion(1, succeeded=1), False),
])
def test_partial_failure_is_retryable_but_deliberate_limits_are_not(tmp_path, receipt, eligible):
    session = SourceListSession({}, lambda rows: rows)
    def setup(manager):
        manager.submit_task('Fixture', 'juku', lambda: SearchResults([source('a')], receipt))
    pump = ProgressiveSearch(session, setup, lambda rows: rows,
        admission=lambda: try_acquire(tmp_path/'lease'))
    pump.start()
    finish(pump)
    assert bool(pump.retry_candidates()) is eligible
    pump.cancel()


def test_timeout_does_not_overlap_old_io_or_accept_late_cards(tmp_path):
    session = SourceListSession({}, lambda rows: rows)
    entered, release = Event(), Event()
    calls = []
    def slow():
        calls.append(1)
        entered.set()
        release.wait(3)
        return [source('a')]
    def setup(manager):
        manager.submit_task('Slow', 'juku', slow)
    pump = ProgressiveSearch(session, setup, lambda rows: rows, budget=.15,
        admission=lambda: try_acquire(tmp_path/'lease'))
    try:
        pump.start()
        assert entered.wait(2)
        finish(pump)
        assert pump.retry_candidates()
        assert not pump.retry_failed()
        assert calls == [1] and not session.entries
    finally:
        release.set()
        for future in getattr(pump, '_futures', []):
            future.result(3)
    assert not session.entries  # Late initial request cannot revive its provider.
    assert pump.retry_failed()
    finish(pump)
    assert len(calls) == 2 and len(session.entries) == 1
    pump.cancel()


@pytest.mark.parametrize('action', ['cancel', 'select', 'close_session'])
def test_explicit_stop_or_selection_prevents_retry(tmp_path, action):
    session = SourceListSession({}, lambda rows: rows)
    session.publish(session.epoch, 'local', [source('a')])
    def setup(manager):
        manager.submit_task('Fail', 'juku', lambda: SearchResults([], SearchCompletion(1, failed=1)))
    pump = ProgressiveSearch(session, setup, lambda rows: rows,
        admission=lambda: try_acquire(tmp_path/'lease'))
    pump.start()
    finish(pump)
    if action == 'cancel':
        pump.cancel()
    elif action == 'select':
        session.capture(session.epoch, session.key(source('a')))
    else:
        session.cancel()
    assert not pump.retry_failed()
    pump.cancel()


def test_retry_skips_success_cache_and_does_not_reuse_failed_tasks_cache(tmp_path):
    session = SourceListSession({}, lambda rows: rows)
    calls = []
    class Cache:
        def get(self, key, name):
            calls.append(('get', key))
            return None
        def put(self, key, name, rows):
            calls.append(('put', key))
    count = [0]
    def flaky():
        count[0] += 1
        if count[0] == 1:
            raise ValueError()
        return [source('a')]
    def setup(manager):
        manager.submit_task('Flaky', 'juku', flaky)
    pump = ProgressiveSearch(session, setup, lambda rows: rows, result_cache=Cache(),
        admission=lambda: try_acquire(tmp_path/'lease'))
    pump.start()
    finish(pump)
    assert pump.retry_failed()
    finish(pump)
    assert calls == [('get', 'juku'), ('put', 'juku')]
    pump.cancel()


def test_busy_admission_keeps_failed_provider_retryable(tmp_path):
    session = SourceListSession({}, lambda rows: rows)
    def setup(manager):
        manager.submit_task('Fail', 'juku', lambda: SearchResults([], SearchCompletion(1, failed=1)))
    busy = [False]
    pump = ProgressiveSearch(session, setup, lambda rows: rows, budget=.12,
        admission=lambda: None if busy[0] else try_acquire(tmp_path/'lease'))
    pump.start(); finish(pump)
    busy[0] = True
    assert pump.retry_failed()
    finish(pump)
    assert pump.retry_candidates() == ('juku:1',)
    assert session.status()['providers']['juku:1']['error'] == 'PREVIOUS_SEARCH_IO_BUSY'
    pump.cancel()


def test_changed_provider_configuration_never_replaces_failure_with_a_new_sibling(tmp_path):
    session = SourceListSession({}, lambda rows: rows)
    calls = []
    def setup(manager):
        if manager.retrying:
            manager.submit_task('Other', 'juku', lambda: calls.append('wrong'))
        else:
            manager.submit_task('Original', 'juku', lambda: SearchResults([], SearchCompletion(1, failed=1)))
    pump = ProgressiveSearch(session, setup, lambda rows: rows,
        admission=lambda: try_acquire(tmp_path/'lease'))
    pump.start(); finish(pump)
    assert pump.retry_failed()
    finish(pump)
    assert calls == []
    assert session.status()['providers']['juku:1']['error'] == 'RETRY_PROVIDER_UNAVAILABLE'
    pump.cancel()

"""Real legacy controls and deterministic scoped row/lifetime regressions.

This slice deliberately retains legacy authentication, not account isolation.
"""
import ast
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import sqlite3
import subprocess
from threading import Event, Lock, Thread, current_thread
from time import monotonic
from types import SimpleNamespace

import pytest
import requests

from lib.domain.torrent import TorrentStream
from lib.utils.debrid import debrid_utils as du
from lib.utils.debrid import search_check as scoped
from lib.search import _process_search_results as actual_processing
from test_ce2089_shared_search import shared

ROOT = Path(__file__).resolve().parents[2]
BASE = '629597c7c6655a992438f1903e3066dfa72cf61a'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(requests.Session, 'request', lambda *a, **kw: pytest.fail('Unexpected remote request'))


def row(token='a', title='Fixture S01E01 1080p'):
    return TorrentStream(title=title, infoHash=token*40, indexer='Jackett', type='Torrent')


def context(factory, *, providers=('AllDebrid',), current=lambda: True, cancelled=None,
            deadline=None, show=False, include_all=False, workers=6):
    return scoped.SearchDebridContext(providers, show_uncached=show,
        include_all_uncached=include_all, workers=workers, current=current,
        cancelled=cancelled if cancelled is not None else Event(),
        deadline=deadline if deadline is not None else monotonic()+20, helper_factory=factory)


def call(rows, scope=None, fn=None):
    return (fn or du.check_debrid_cached)('Fixture', rows, 'tv', 'tv',
        SimpleNamespace(create=lambda *a: None, update=lambda *a: None), False, 1,
        **({'search_context': scope} if scope is not None else {}))


@lru_cache(None)
def old_check_code():
    source = subprocess.check_output(['git', '-C', str(ROOT), 'show',
        BASE+':addons/plugin.video.bobbi/lib/utils/debrid/debrid_utils.py']).decode('utf-8')
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'check_debrid_cached')
    return compile(ast.Module(body=[function], type_ignores=[]), '<629597c-original-debrid>', 'exec')


def original():
    namespace = dict(vars(du))
    exec(old_check_code(), namespace)
    return namespace['check_debrid_cached']


@pytest.fixture
def aggregate(monkeypatch, tmp_path):
    from lib.db.cached import HybridCache
    backend = HybridCache(str(tmp_path/'legacy.sqlite'))
    reads, writes = [], []
    def get(key, params=None):
        reads.append((key, params))
        return backend.get(str((key, params)))
    def put(value, key, params=None):
        writes.append((key, params))
        backend.set(str((key, params)), value)
    monkeypatch.setattr(du, 'get_cached', get)
    monkeypatch.setattr(du, 'set_cached', put)
    monkeypatch.setattr(du, '_build_debrid_cache_scope', lambda: 'unchanged-window-scope')
    monkeypatch.setattr(du, 'get_setting', lambda key, default=None: 2 if key == 'thread_number' else default)
    monkeypatch.setattr(du, 'should_include_uncached', lambda: False)
    try:
        yield SimpleNamespace(backend=backend, reads=reads, writes=writes, path=tmp_path/'legacy.sqlite')
    finally:
        backend.close()


def cached_check(rows, cached, uncached, total, dialog, lock):
    for item in rows:
        item.isCached = True
        cached.append(item)


@pytest.mark.parametrize('old', [False, True], ids=['fixed', 'original-control'])
@pytest.mark.parametrize('disabled', [False, True])
def test_same_query_new_hash_and_season_or_disabled_never_reuses_old_rows(aggregate, monkeypatch, old, disabled):
    monkeypatch.setattr(du, 'get_debrid_check_functions', lambda: [cached_check])
    run = original() if old else du.check_debrid_cached
    first = call([row('a', 'First S01E01')], None if old else context(
        lambda _: scoped.CheckHandle(cached_check)), run)
    assert first[0].title == 'First S01E01'
    if disabled:
        monkeypatch.setattr(du, 'get_debrid_check_functions', lambda: [])
    second = call([row('b', 'Second S02E01')], None if old else context(
        lambda _: scoped.CheckHandle(cached_check), providers=() if disabled else ('AllDebrid',)), run)
    assert [item.title for item in second] == (['First S01E01'] if old else
                                              [] if disabled else ['Second S02E01'])
    assert len(aggregate.reads) == (2 if old else 0)
    assert len(aggregate.writes) == (1 if old else 0)
    with sqlite3.connect(aggregate.path) as observer:
        assert observer.execute('SELECT COUNT(*) FROM cached').fetchone()[0] == (1 if old else 0)


@pytest.mark.parametrize('old', [False, True], ids=['fixed', 'original-control'])
def test_actual_ad_db_helpers_do_not_share_mutable_output(aggregate, monkeypatch, old):
    from lib.clients.debrid import alldebrid, debrider
    monkeypatch.setattr(alldebrid, 'get_setting', lambda *a: False)
    ad = alldebrid.AllDebridHelper.__new__(alldebrid.AllDebridHelper)
    db = debrider.DebriderHelper.__new__(debrider.DebriderHelper)
    ad.client = SimpleNamespace(get_user_torrent_list=lambda: {'magnets': [{'hash': 'a'*40}]})
    db.client = SimpleNamespace(get_torrent_instant_availability=lambda _: {'result': [{'cached': False}]})
    ad_done, db_done = Event(), Event()
    helpers = {'AllDebrid': ad, 'Debrider': db}
    def check(provider):
        def run(*args):
            if provider == 'Debrider':
                assert ad_done.wait(2)
            helpers[provider].check_cached(*args)
            (ad_done if provider == 'AllDebrid' else db_done).set()
        return run
    monkeypatch.setattr(du, 'get_debrid_check_functions', lambda: [check('AllDebrid'), check('Debrider')])
    inputs = [row()]
    untouched = deepcopy(inputs)
    original_item = inputs[0]
    result = call(inputs, None if old else context(lambda provider: scoped.CheckHandle(check(provider)),
        providers=('AllDebrid', 'Debrider')), original() if old else None)
    assert db_done.is_set()
    assert len(result) == 1
    assert (result[0].debridType, result[0].isCached) == (
        ('Debrider', False) if old else ('AllDebrid', True))
    assert (inputs[0] is original_item) is (not old)
    if not old:
        assert inputs == untouched and result[0] is not inputs[0]


@pytest.mark.parametrize('ambient_show,captured_show', [(False, True), (True, False), (True, True)])
def test_captured_show_preference_normalizes_real_rd_aliases(monkeypatch, ambient_show, captured_show):
    from lib.clients.debrid import realdebrid
    monkeypatch.setattr(realdebrid, 'get_setting', lambda *a: ambient_show)
    helper = realdebrid.RealDebridHelper.__new__(realdebrid.RealDebridHelper)
    helper.client = SimpleNamespace(get_user_torrent_list=lambda: [])
    scope = context(lambda _: scoped.CheckHandle(helper.check_cached), providers=('RealDebrid',), show=captured_show)
    result = call([row()], scope)
    assert len(result) == int(captured_show)  # No duplicate cached/uncached alias.
    assert not result or result[0].isCached is False


def test_capture_disabled_flags_does_not_touch_legacy_cache_or_factory(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Disabled scoped search must not enter ambient cache/helper selection')
    for name in ('get_cached_results', 'update_cache', 'get_debrid_check_functions', 'get_debrid_helper'):
        monkeypatch.setattr(du, name, forbidden)
    settings = {'thread_number': 4, 'easydebrid_enabled': True}
    scope = du.capture_search_debrid(lambda key, default=None: settings.get(key, default),
        current=lambda: True, cancelled=Event(), deadline=monotonic()+10)
    settings.update(alldebrid_enabled=True, show_uncached=True)
    assert scope.providers == ()  # EasyDebrid remains absent from search checks.
    source = TorrentStream(title='Direct', type='Direct', url='https://fixture.invalid/media')
    results = call([row(), source], scope)
    assert len(results) == 1 and results[0] == source and results[0] is not source


@pytest.mark.parametrize('old', [False, True], ids=['fixed', 'original-control'])
def test_revoke_retains_outer_lease_until_real_child_drain_without_late_sqlite_write(
        aggregate, monkeypatch, tmp_path, old):
    from bobbi_core.progressive_search import ProgressiveSearch
    from bobbi_core.source_list_session import SourceListSession
    from bobbi_core.search_admission import try_acquire
    entered, release, drained = Event(), Event(), Event()
    active, closed, threads = [True], [], []
    def held(*args):
        threads.append(current_thread().name)
        entered.set()
        assert release.wait(3)
        cached_check(*args)
    monkeypatch.setattr(du, 'get_debrid_check_functions', lambda: [held])
    fn = original() if old else du.check_debrid_cached
    session = SourceListSession({'query': 'Fixture'}, lambda rows: rows, 20)
    def transform(rows):
        scope = None if old else context(lambda _: scoped.CheckHandle(held, lambda: closed.append('helper')),
            current=lambda: active[0], cancelled=pump.cancelled, deadline=pump.deadline)
        return call(rows, scope, fn)
    def close():
        closed.append('outer')
        drained.set()
    pump = ProgressiveSearch(session, lambda manager: manager.submit_task('fixture', 'fixture', lambda: [row()]),
        transform, admission=lambda: try_acquire(tmp_path/'admission'),
        current=lambda: active[0], on_close=close)
    try:
        pump.start()
        assert entered.wait(2)
        assert threads[0] != current_thread().name
        if not old:
            assert threads[0].startswith('BobbiDebrid')
        active[0] = False
        pump.cancel()
        pump.thread.join(2)
        assert not pump.thread.is_alive() and pump._pending == 1 and not drained.is_set()
        assert try_acquire(tmp_path/'admission') is None  # Real file lease is still retained.
        release.set()
        assert drained.wait(2)
        assert closed == (['outer'] if old else ['helper', 'outer'])
        assert session.snapshot()['entries'] == [] and pump._pending == 0
        assert len(aggregate.writes) == int(old)
        with sqlite3.connect(aggregate.path) as observer:
            assert observer.execute('SELECT COUNT(*) FROM cached').fetchone()[0] == int(old)
        lease = try_acquire(tmp_path/'admission')
        assert lease is not None
        lease.release()
    finally:
        release.set()
        pump.cancel()


@pytest.mark.parametrize('failure_phase', ['factory', 'check', 'close'])
def test_failures_preserve_original_exception_healthy_sibling_and_owned_cleanup(failure_phase):
    error, closed = RuntimeError('fixture-error'), []
    def factory(provider):
        if provider == 'bad' and failure_phase == 'factory':
            raise error
        def check(*args):
            if provider == 'bad' and failure_phase == 'check':
                raise error
            cached_check(*args)
        def close():
            closed.append(provider)
            if provider == 'bad' and failure_phase == 'close':
                raise error
        return scoped.CheckHandle(check, close)
    scope = context(factory, providers=('bad', 'healthy'))
    result = call([row()], scope)
    assert len(result) == (2 if failure_phase == 'close' else 1)
    assert result.completion.state == 'PARTIAL' and result.completion.failed == 1
    assert scope.failures == [('bad', failure_phase, error)]
    assert sorted(closed) == (['healthy'] if failure_phase == 'factory' else ['bad', 'healthy'])


def test_borrowed_handle_has_no_implicit_cleanup():
    helper = SimpleNamespace(check_cached=cached_check,
                             client=SimpleNamespace(session=SimpleNamespace(close=lambda: pytest.fail('Borrowed'))))
    assert len(call([row()], context(lambda _: scoped.CheckHandle(helper.check_cached)))) == 1


def test_partial_submit_failure_drains_submitted_work_and_preserves_error(monkeypatch):
    entered, release, finished = Event(), Event(), Event()
    error, closed = RuntimeError('submit-fixture'), []
    class FailingSubmit(ThreadPoolExecutor):
        def submit(self, *args, **kwargs):
            if hasattr(self, 'submitted'):
                assert entered.wait(2)
                raise error
            self.submitted = True
            return super().submit(*args, **kwargs)
    monkeypatch.setattr(scoped, 'ThreadPoolExecutor', FailingSubmit)
    def check(*args):
        entered.set()
        assert release.wait(3)
        cached_check(*args)
    scope = context(lambda _: scoped.CheckHandle(check, lambda: closed.append(True)), providers=('first', 'second'))
    result = []
    def run():
        result.extend(call([row()], scope))
        finished.set()
    worker = Thread(target=run)
    try:
        worker.start()
        assert entered.wait(2) and worker.is_alive() and not finished.is_set() and not closed
        release.set()
        worker.join(2)
        assert finished.is_set() and len(result) == 1 and closed == [True]
        assert scope.failures == [('second', 'submit', error)]
    finally:
        release.set()
        worker.join(3)


@pytest.mark.parametrize('stage', ['cancel', 'deadline', 'profile'])
def test_revoked_context_is_sticky_and_never_calls_factory(stage):
    active, cancel = [True], Event()
    scope = context(lambda _: pytest.fail('Revoked context'), current=lambda: active[0], cancelled=cancel)
    if stage == 'cancel':
        cancel.set()
    elif stage == 'deadline':
        scope.deadline = 0
    else:
        active[0] = False
    assert call([row()], scope) == []
    active[0] = True
    cancel.clear()
    scope.deadline = monotonic()+10
    assert call([row()], scope) == []


def test_default_rd_factory_retains_original_oauth_then_query_and_closes_own_session(monkeypatch):
    from lib.clients.debrid import realdebrid
    operations, closed = [], []
    token = base64.b64encode(b'fixture-client:fixture-secret:fixture-code').decode()
    monkeypatch.setattr(realdebrid, 'get_setting', lambda key, default=None: token if key == 'real_debrid_token' else False)
    def request(self, method, url, **kwargs):
        operations.append((method, url))
        payload = {'access_token': 'fixture-access'} if url.endswith('/token') else [{'hash': 'a'*40}]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(requests.Session, 'request', request)
    monkeypatch.setattr(requests.Session, 'close', lambda self: closed.append(id(self)))
    scope = du.capture_search_debrid(lambda key, default=None: {'real_debrid_enabled': True}.get(key, default),
        current=lambda: True, cancelled=Event(), deadline=monotonic()+10)
    assert len(call([row()], scope)) == 1 and not scope.failures
    assert operations == [('POST', 'https://api.real-debrid.com/oauth/v2/token'),
                          ('GET', 'https://api.real-debrid.com/rest/1.0/torrents')]
    assert len(closed) == 1


@pytest.mark.parametrize('borrowed', [False, True])
@pytest.mark.parametrize('close_fails', [False, True])
def test_failed_client_constructor_closes_only_internal_session_and_keeps_auth_error(monkeypatch, borrowed, close_fails):
    from lib.api.debrid.base import DebridClient
    auth_error, calls = RuntimeError('auth-fixture'), []
    def close():
        calls.append('close')
        if close_fails:
            raise RuntimeError('cleanup-fixture')
    session = SimpleNamespace(close=close)
    monkeypatch.setattr(requests, 'Session', lambda: session)
    class Client(DebridClient):
        def initialize_headers(self):
            calls.append('authenticate')
            raise auth_error
        def disable_access_token(self):
            pass
        def _handle_service_specific_errors(self, *args):
            pass
    with pytest.raises(RuntimeError) as caught:
        Client('fixture', session=session if borrowed else None)
    assert caught.value is auth_error
    assert calls == (['authenticate'] if borrowed else ['authenticate', 'close'])


def test_real_processing_pipeline_passes_context_without_legacy_cache(monkeypatch):
    from lib import search
    monkeypatch.setattr(du, 'get_cached_results', lambda *a: pytest.fail('Legacy aggregate read'))
    monkeypatch.setattr(du, 'update_cache', lambda *a: pytest.fail('Legacy aggregate write'))
    monkeypatch.setattr(search, 'close_busy_dialog', lambda *a: pytest.fail('UI mutation'))
    settings = lambda key, default=None: {'torrent_enable': False, 'stremio_bypass_addons': False}.get(key, default)
    scope = context(lambda _: scoped.CheckHandle(cached_check))
    results = search._process_search_results([row()], 'tv', '', 1, 1, '', 'Fixture', 'tv', False,
        suppress_debrid_dialog=True, suppress_busy_dialog=True, settings_getter=settings, debrid_context=scope)
    assert len(results) == 1 and results[0].isCached


def test_real_entry_transforms_in_provider_worker_and_retains_child_until_close(shared, monkeypatch, tmp_path):
    from bobbi_core.search_admission import try_acquire
    search = shared.search
    getter = search.get_setting
    monkeypatch.setattr(search, 'get_setting', lambda key, default=None:
        True if key == 'alldebrid_enabled' else getter(key, default))
    entered, release, drained = Event(), Event(), Event()
    threads, scopes, closed = [], [], []
    backend_close = search.HybridCache.close

    def close_backend(backend):
        backend_close(backend)
        closed.append('backend')
        drained.set()

    def check(*args):
        threads.append(('helper', current_thread().name))
        entered.set()
        assert release.wait(3)
        cached_check(*args)

    def factory(provider):
        assert provider == 'AllDebrid'
        threads.append(('factory', current_thread().name))
        return SimpleNamespace(check_cached=check, client=SimpleNamespace(
            session=SimpleNamespace(close=lambda: closed.append('helper'))))

    def process(rows, *args, **kwargs):
        threads.append(('transform', current_thread().name))
        scopes.append(kwargs['debrid_context'])
        return call(rows, scopes[-1])

    monkeypatch.setattr(search.HybridCache, 'close', close_backend)
    monkeypatch.setattr(search, '_process_search_results', process)
    monkeypatch.setattr(du, 'get_debrid_helper', factory)
    session, pump = search._create_source_search({}, 'Fixture', {'tmdb_id': 123}, 'tv', 'tv',
        {'season': 1, 'episode': 1}, False, '', search.SearchVariant.DEFAULT,
        search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    admission = tmp_path/'plugin.video.bobbi'/'search-admission'
    try:
        pump.start()
        assert entered.wait(2), session.status()
        assert scopes[0].providers == ('AllDebrid',)
        assert scopes[0].cancelled is pump.cancelled and scopes[0].deadline == pump.deadline
        assert [(phase, name.split('_')[0]) for phase, name in threads] == [
            ('transform', 'BobbiSource'), ('factory', 'BobbiDebrid'), ('helper', 'BobbiDebrid')]
        assert all(name != current_thread().name for _, name in threads)
        pump.cancel()
        pump.thread.join(2)
        assert not pump.thread.is_alive() and pump._pending == 1 and not closed
        assert try_acquire(admission) is None
        release.set()
        assert drained.wait(2)
        assert closed == ['helper', 'backend'] and pump._pending == 0
        assert session.snapshot()['entries'] == []
        lease = try_acquire(admission)
        assert lease is not None
        lease.release()
    finally:
        release.set()
        pump.cancel()


def test_executor_constructor_failure_retains_original_exception(monkeypatch):
    error = RuntimeError('executor-fixture')
    def fail(**kwargs):
        raise error
    monkeypatch.setattr(scoped, 'ThreadPoolExecutor', fail)
    scope = context(lambda _: pytest.fail('No executor'))
    result = call([row()], scope)
    assert result == [] and not result.completion.complete and result.completion.failed == 1
    assert scope.failures == [('', 'executor', error)]


def test_check_and_close_failures_preserve_both_original_exceptions():
    check_error, close_error = RuntimeError('check-fixture'), RuntimeError('close-fixture')
    def check(*args):
        raise check_error
    def close():
        raise close_error
    scope = context(lambda _: scoped.CheckHandle(check, close))
    result = call([row()], scope)
    assert result == [] and result.completion.failed == 1
    assert scope.failures == [('AllDebrid', 'check', check_error), ('AllDebrid', 'close', close_error)]


def test_cancellation_after_factory_skips_query_but_closes_owned_session():
    cancelled, closed = Event(), []
    def factory(provider):
        cancelled.set()
        return scoped.CheckHandle(lambda *a: pytest.fail('Cancelled query'), lambda: closed.append(True))
    scope = context(factory, cancelled=cancelled)
    assert call([row()], scope) == []
    assert closed == [True] and not scope.failures


def test_cancellation_while_copying_rows_skips_query_and_closes_handle(monkeypatch):
    cancelled, closed = Event(), []
    copy_rows = scoped.copy.deepcopy
    def copy_and_revoke(rows):
        copied = copy_rows(rows)
        cancelled.set()
        return copied
    monkeypatch.setattr(scoped.copy, 'deepcopy', copy_and_revoke)
    scope = context(lambda _: scoped.CheckHandle(lambda *a: pytest.fail('Cancelled query'),
        lambda: closed.append(True)), cancelled=cancelled)
    assert scope.check([row()], []) == []
    assert closed == [True] and not scope.failures


def test_default_debrider_factory_retains_public_ip_lookup_and_only_checks_availability(monkeypatch):
    from lib.clients.debrid import debrider
    operations, closed = [], []
    monkeypatch.setattr(debrider, 'get_setting', lambda *a: 'fixture-token')
    def public_ip():
        operations.append('public-ip')
        return '192.0.2.1'
    monkeypatch.setattr(debrider, 'get_public_ip', public_ip)
    def request(self, method, url, **kwargs):
        operations.append((method, url))
        assert kwargs['headers']['X-Forwarded-For'] == '192.0.2.1'
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'result': [{'cached': True}]})
    monkeypatch.setattr(requests.Session, 'request', request)
    monkeypatch.setattr(requests.Session, 'close', lambda self: closed.append(id(self)))
    scope = du.capture_search_debrid(lambda key, default=None: {'debrider_enabled': True}.get(key, default),
        current=lambda: True, cancelled=Event(), deadline=monotonic()+10)
    assert len(call([row()], scope)) == 1 and not scope.failures
    assert operations == ['public-ip', ('POST', 'https://debrider.app/api/v1/link/lookup')]
    assert len(closed) == 1


@pytest.mark.parametrize('providers', [('AllDebrid', 'Debrider'), ('Debrider', 'AllDebrid')])
def test_each_provider_owns_its_rows_in_both_execution_orders(monkeypatch, providers):
    from lib.clients.debrid import alldebrid, debrider
    monkeypatch.setattr(alldebrid, 'get_setting', lambda *a: True)
    ad = alldebrid.AllDebridHelper.__new__(alldebrid.AllDebridHelper)
    db = debrider.DebriderHelper.__new__(debrider.DebriderHelper)
    ad.client = SimpleNamespace(get_user_torrent_list=lambda: {'magnets': [{'hash': 'a'*40}]})
    db.client = SimpleNamespace(get_torrent_instant_availability=lambda _: {'result': [{'cached': False}]})
    helpers = {'AllDebrid': ad, 'Debrider': db}
    source = row()
    scope = context(lambda provider: scoped.CheckHandle(helpers[provider].check_cached),
        providers=providers, show=True, include_all=True, workers=1)
    results = call([source], scope)
    assert len(results) == 2 and results[0] is not results[1]
    assert all(result is not source for result in results)
    assert {(item.debridType, item.isCached) for item in results} == {('AllDebrid', True), ('Debrider', False)}


@pytest.mark.parametrize('phase', ['factory', 'check', 'close'])
@pytest.mark.parametrize('upstream_receipt', [False, True])
@pytest.mark.parametrize('siblings', [False, True])
def test_actual_entry_failure_is_retryable_and_keeps_healthy_rows_without_polluting_raw_cache(
        shared, monkeypatch, phase, upstream_receipt, siblings):
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    from bobbi_core.provider_cache import ProviderResultCache
    search, failed, completed, cached = shared.search, [True], [], []
    getter = search.get_setting
    settings = {'torrent_enable': False, 'stremio_bypass_addons': False,
                'alldebrid_enabled': True, 'premiumize_enabled': siblings}
    monkeypatch.setattr(search, 'get_setting', lambda key, default=None: settings.get(key, getter(key, default)))
    monkeypatch.setattr(search, '_process_search_results', actual_processing)
    receipt = SearchCompletion(1, succeeded=1)
    def provider(*args, **kwargs):
        rows = [row()]
        if siblings:
            rows.append(TorrentStream(title='Fixture S01E01 direct', type='Direct',
                url='https://fixture.invalid/media'))
        return SearchResults(rows, receipt) if upstream_receipt else rows
    monkeypatch.setattr(search, '_perform_search', provider)
    put = ProviderResultCache.put
    def cache_put(cache, key, query, rows):
        cached.append(getattr(rows, 'completion', None))
        return put(cache, key, query, rows)
    monkeypatch.setattr(ProviderResultCache, 'put', cache_put)
    def factory(provider):
        bad = provider == 'AllDebrid' and failed[0]
        if bad and phase == 'factory':
            raise RuntimeError('factory-fixture')
        def check(*args):
            if bad and phase == 'check':
                raise RuntimeError('check-fixture')
            cached_check(*args)
        def close():
            if bad and phase == 'close':
                raise RuntimeError('close-fixture')
        return SimpleNamespace(check_cached=check, client=SimpleNamespace(session=SimpleNamespace(close=close)))
    monkeypatch.setattr(du, 'get_debrid_helper', factory)
    session, pump = search._create_source_search({}, 'Fixture', {'tmdb_id': 123}, 'tv', 'tv',
        {'season': 1, 'episode': 1}, False, '', search.SearchVariant.DEFAULT,
        search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    pump.on_complete = lambda: completed.append(True)
    try:
        pump.start()
        pump.thread.join(3)
        assert not pump.thread.is_alive() and not completed
        targets = pump.retry_candidates()
        assert len(targets) == 1, session.status()
        status = session.status()['providers'][targets[0]]
        assert status['state'] == ('PARTIAL' if upstream_receipt or siblings else 'FAILED')
        assert status['completion']['failed'] == 1
        assert status['completion']['planned'] == 1 + int(siblings) + int(upstream_receipt)
        visible = [item for _, item in session.snapshot()['entries']]
        assert bool(visible) == (siblings or phase == 'close')
        if siblings:
            assert any(item.type == 'Direct' for item in visible)
            assert any(item.isCached for item in visible)
        assert len(cached) == 1
        assert cached[0] is None if not upstream_receipt else (
            cached[0].planned == 1 and cached[0].succeeded == 1 and cached[0].failed == 0)
        failed[0] = False
        assert pump.retry_failed()
        pump.thread.join(3)
        assert not pump.thread.is_alive() and completed == [True] and pump.retry_candidates() == ()
        success = session.status()['providers'][targets[0]]
        assert success['state'] == 'COMPLETE' and success['completion']['failed'] == 0
        assert success['completion']['planned'] == 1 + int(siblings) + int(upstream_receipt)
    finally:
        pump.cancel()


@pytest.mark.parametrize('empty_upstream', [False, True])
def test_actual_entry_streaming_and_empty_receipts_are_not_lost_or_double_counted(shared, monkeypatch, empty_upstream):
    from bobbi_core.search_completion import SearchCompletion, SearchResults
    search = shared.search
    getter = search.get_setting
    settings = {'torrent_enable': False, 'stremio_bypass_addons': False, 'alldebrid_enabled': True}
    monkeypatch.setattr(search, 'get_setting', lambda key, default=None: settings.get(key, getter(key, default)))
    monkeypatch.setattr(search, '_process_search_results', actual_processing)
    emitted, release = Event(), Event()
    completed = []
    upstream = SearchResults([], SearchCompletion(1, failed=1)) if empty_upstream else SearchResults(
        [row()], SearchCompletion(1, succeeded=1))
    def factory(provider):
        assert not empty_upstream
        raise RuntimeError('factory-fixture')
    monkeypatch.setattr(du, 'get_debrid_helper', factory)
    def produce(publish):
        assert publish(upstream)
        emitted.set()
        assert release.wait(3)
        return upstream
    def submit(manager, *args, **kwargs):
        manager.submit_task('fixture', 'Jackett', produce, _progressive=True)
    monkeypatch.setattr(search, '_submit_search_tasks_managed', submit)
    session, pump = search._create_source_search({}, 'Fixture', {'tmdb_id': 123}, 'tv', 'tv',
        {'season': 1, 'episode': 1}, False, '', search.SearchVariant.DEFAULT,
        search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    pump.on_complete = lambda: completed.append(True)
    try:
        pump.start()
        assert emitted.wait(2)
        record = session.status()['providers']['Jackett:1']
        assert record['state'] == 'RUNNING'
        assert record['completion']['failed'] == 1
        assert record['completion']['planned'] == (1 if empty_upstream else 2)
        release.set()
        pump.thread.join(2)
        assert not pump.thread.is_alive() and not completed
        final = session.status()['providers']['Jackett:1']
        assert final['completion'] == record['completion']
        assert final['state'] == ('FAILED' if empty_upstream else 'PARTIAL')
        assert pump.retry_candidates() == ('Jackett:1',)
    finally:
        release.set()
        pump.cancel()


def test_disabled_checks_do_not_read_unused_worker_configuration():
    calls = []
    def setting(key, default=None):
        calls.append(key)
        if key == 'thread_number':
            pytest.fail('Disabled checks must not read invalid unused thread_number')
        return default
    scope = du.capture_search_debrid(setting, current=lambda: True, cancelled=Event(), deadline=monotonic()+10)
    assert scope.providers == () and 'thread_number' not in calls


def test_actual_entry_disabled_debrid_and_invalid_workers_keep_direct_and_torrent_routes(shared, monkeypatch):
    search = shared.search
    getter = search.get_setting
    settings = {'torrent_enable': True, 'stremio_bypass_addons': False, 'thread_number': 'invalid'}
    monkeypatch.setattr(search, 'get_setting', lambda key, default=None: settings.get(key, getter(key, default)))
    monkeypatch.setattr(search, '_process_search_results', actual_processing)
    direct = TorrentStream(title='Fixture S01E01 direct', type='Direct', url='https://fixture.invalid/media')
    monkeypatch.setattr(search, '_perform_search', lambda *a, **kw: [row(), direct])
    monkeypatch.setattr(du, 'get_debrid_helper', lambda *a: pytest.fail('Disabled helper'))
    session, pump = search._create_source_search({}, 'Fixture', {'tmdb_id': 123}, 'tv', 'tv',
        {'season': 1, 'episode': 1}, False, '', search.SearchVariant.DEFAULT,
        search.TITLE_LANGUAGE_LOCALIZED_FIRST, 2020, False, {}, [])
    completed = []
    pump.on_complete = lambda: completed.append(True)
    try:
        pump.start()
        pump.thread.join(2)
        assert not pump.thread.is_alive() and completed == [True] and not pump.retry_candidates()
        assert {item.type for _, item in session.snapshot()['entries']} == {'Direct', 'Torrent'}
    finally:
        pump.cancel()


def test_unexpected_future_failure_is_reported_in_existing_receipt(monkeypatch):
    error = RuntimeError('future-fixture')
    scope = context(lambda _: pytest.fail('Replaced worker'))
    def broken(*args):
        raise error
    monkeypatch.setattr(scope, '_check', broken)
    result = call([row()], scope)
    assert result == [] and result.completion.state == 'FAILED' and result.completion.failed == 1
    assert scope.failures == [('AllDebrid', 'future', error)]


def test_actual_629597c_factory_error_was_not_an_empty_success(monkeypatch):
    from lib.utils.general import utils
    error = RuntimeError('original-factory-fixture')
    monkeypatch.setattr(du, 'get_cached_results', lambda *args: None)
    monkeypatch.setattr(utils, 'get_setting_fresh', lambda key: key == 'alldebrid_enabled')
    def factory(provider):
        assert provider == 'AllDebrid'
        raise error
    monkeypatch.setattr(du, 'get_debrid_helper', factory)
    with pytest.raises(RuntimeError) as caught:
        call([row()], fn=original())
    assert caught.value is error

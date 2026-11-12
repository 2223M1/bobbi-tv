"""Actual portable main, scopes and dependency worker across both adapters.

Host/Kodi IO are doubles. StandardPlayback and shared presentation remain real.
The native composition uses a controlled loop; the actual native callback is
also exercised by private_baseline/test_ce2020_native_stop.py.
"""
from copy import deepcopy
import sqlite3
import sys
from threading import Event, RLock, Thread
import time
from types import SimpleNamespace

import pytest

from test_focus_anchor import Accounts
from test_standard_product import product


def until(predicate):
    deadline = time.monotonic()+2
    while not predicate():
        assert time.monotonic() < deadline, 'controlled worker did not reach boundary'
        time.sleep(.001)


@pytest.fixture
def resident(product, monkeypatch, tmp_path):
    from lib import portable_runtime
    from lib.services import widget_refresh
    host = product.actor.host
    account = dict(provider='quark', account_id='quark:'+'b'*64, epoch=1, authenticated=True)
    legacy = Accounts({'115': dict(account_id='', epoch=0, authenticated=False)}, legacy=True)
    pans = Accounts({'quark': account})
    host.accounts, host.pans = legacy, SimpleNamespace(accounts=pans)
    trace = SimpleNamespace(ticks=0, limit=4, closed=False, snapshots=[],
        native=False, host_hook=lambda: None, read_hook=lambda: None,
        history={'jt:lfh': {}, 'files': {}}, sampler=None, history_read=Event(),
        close_entered=Event(), worker_alive_at_host_close=None)
    trace.path = tmp_path/'history.pkl'
    trace.path.write_bytes(b'initial')
    class Database:
        _database_path = str(trace.path)
        def get_keys_checked(self, keys):
            trace.history_read.set()
            trace.read_hook()
            return deepcopy(trace.history)
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', SimpleNamespace(PickleDatabase=Database))
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(KEY='files'))
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', SimpleNamespace(
        get_property=lambda key: product.state.props.get(key, ''), get_setting=lambda *a: 60,
        kodilog=lambda *a, **kw: None))
    db = sqlite3.connect(':memory:', check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE catalog_meta(singleton,generation,revision)')
    db.execute("INSERT INTO catalog_meta VALUES(1,'boot',1)")
    host.catalog = SimpleNamespace(index=SimpleNamespace(db=db, lock=RLock()))
    service_type = widget_refresh.WidgetRefreshService
    class WorkerMonitor:
        def abortRequested(self): return False
        def waitForAbort(self, seconds): time.sleep(seconds); return False
    def sampler(**kw):
        value = service_type(monitor=WorkerMonitor(), interval=.005, **kw)
        close = value.close
        def close_and_record():
            trace.close_entered.set()
            close()
        value.close = close_and_record
        trace.sampler = value
        return value
    monkeypatch.setattr(widget_refresh, 'WidgetRefreshService', sampler)
    def host_tick():
        trace.ticks += 1
        trace.host_hook()
    def host_close():
        trace.worker_alive_at_host_close = trace.sampler.worker.is_alive()
        trace.closed = True
    host.start = lambda: None
    host.configure_preparation = lambda *a: None
    host.tick, host.close = host_tick, host_close
    monkeypatch.setitem(sys.modules, 'bobbi_platform.host', SimpleNamespace(Host=lambda *a, **kw: host))
    monkeypatch.setitem(sys.modules, 'bobbi_platform.paths', SimpleNamespace(profile=lambda *a: '/test-profile'))
    monkeypatch.setitem(sys.modules, 'bobbi_core.runtime_paths', SimpleNamespace(
        configure=lambda *a, **kw: None, native_subtitle_abi=lambda *a: None))
    xbmc = sys.modules['xbmc']
    monkeypatch.setattr(widget_refresh, 'xbmc', xbmc)
    monkeypatch.setattr(xbmc, 'getSkinDir', lambda: 'skin.bobbi.cinema', raising=False)
    monkeypatch.setattr(xbmc, 'getCondVisibility', lambda key: True, raising=False)
    monkeypatch.setattr(xbmc, 'LOGERROR', 4, raising=False)
    monkeypatch.setattr(xbmc, 'Monitor', lambda: SimpleNamespace(
        waitForAbort=lambda seconds: trace.ticks >= trace.limit), raising=False)
    real_standard_tick = product.actor.tick
    def standard_tick():
        real_standard_tick()
        trace.snapshots.append(dict(product.state.props))
    monkeypatch.setattr(product.actor, 'tick', standard_tick)
    monkeypatch.setitem(sys.modules, 'lib.services.standard_playback', SimpleNamespace(
        StandardPlayback=lambda h: product.actor))
    class NativeLoop:
        def run_owner_loop(self, host, presentation_tick):
            while trace.ticks < trace.limit:
                host.tick()
                presentation_tick()
                trace.snapshots.append(dict(product.state.props))
    monkeypatch.setitem(sys.modules, 'lib.services.background_service', SimpleNamespace(JacktookMOnitor=NativeLoop))
    trace.invoke = lambda: portable_runtime.main({'native_contract_available': trace.native})
    trace.account, trace.pans, trace.legacy = account, pans, legacy
    trace.host, trace.product, trace.db = host, product, db
    yield trace
    if trace.sampler is not None:
        trace.sampler.close()
    db.close()


@pytest.mark.parametrize('native', [False, True], ids=['standard', 'native'])
def test_real_main_publishes_scopes_local_revisions_and_drains_on_close(resident, native):
    from lib.utils.views.personal_catalog import scope_key
    state = resident
    state.native = native
    state.product.state.props['Bobi.Rail.Revision.popular_tv'] = '77'
    revoked = []
    def on_tick():
        if state.ticks == 1:
            until(lambda: state.sampler.observed.get('personal_library') == ('boot', 1))
        if state.ticks == 2:
            old = state.sampler.observed['continue_watching']
            state.history['jt:lfh']['record'] = {'progress': 50}
            state.path.write_bytes(b'changed history')
            with state.host.catalog.index.lock:
                state.db.execute('UPDATE catalog_meta SET revision=2')
            until(lambda: state.sampler.observed.get('personal_library') == ('boot', 2)
                  and state.sampler.observed.get('continue_watching') != old)
        if state.ticks == 3:
            state.pans.change('quark', epoch=2)
            revoked.append(state.product.state.props['Bobi.Rail.Scope.quark'] == ''
                and state.product.state.props['Bobi.Rail.Account.quark'] == '')
    state.host_hook = on_tick
    state.invoke()
    assert state.closed and state.ticks == 4 and revoked == [True]
    first, changed, revoked_row, unchanged = state.snapshots
    assert first['Bobi.Rail.Scope.quark'] == scope_key(state.account)
    assert revoked_row['Bobi.Rail.Scope.quark'] == scope_key(dict(state.account, epoch=2))
    for key in ('personal_library', 'continue_watching'):
        prop = 'Bobi.Rail.Revision.'+key
        assert int(changed[prop]) > int(first[prop])
        assert unchanged[prop] == revoked_row[prop]
    assert all(row['Bobi.Rail.Revision.popular_tv'] == '77' for row in state.snapshots)
    assert not state.legacy.listeners and not state.pans.listeners
    assert all(not value for key, value in state.product.state.props.items()
               if '.Scope.' in key or '.Account.' in key)
    assert state.worker_alive_at_host_close is False
    assert not state.product.state.opened and not state.product.state.subtitles


@pytest.mark.parametrize('native', [False, True], ids=['standard', 'native'])
def test_slow_history_does_not_block_owner_and_shutdown_waits_for_reader(resident, native):
    state = resident
    state.native = native
    release, errors = Event(), []
    def read():
        assert release.wait(2), 'test must release controlled slow history'
    state.read_hook = read
    state.host_hook = lambda: state.history_read.wait(1) if state.ticks == 1 else None
    def run():
        try: state.invoke()
        except BaseException as error: errors.append(error)
    owner = Thread(target=run)
    owner.start()
    try:
        assert state.close_entered.wait(1)
        assert state.ticks == 4 and len(state.snapshots) == 4
        assert all(row['Bobi.Rail.Scope.quark'] for row in state.snapshots)
        assert owner.is_alive() and not state.closed
        release.set()
        owner.join(2)
        assert not owner.is_alive() and not errors and state.closed
        assert state.worker_alive_at_host_close is False
    finally:
        release.set()
        owner.join(3)


@pytest.mark.parametrize('native', [False, True], ids=['standard', 'native'])
def test_held_catalog_lock_does_not_block_owner_or_worker_drain(resident, native):
    state = resident
    state.native = native
    state.host_hook = lambda: until(lambda: 'continue_watching' in state.sampler.observed) if state.ticks == 1 else None
    with state.host.catalog.index.lock:
        state.invoke()
        assert state.closed and state.ticks == 4
        assert 'personal_library' not in state.sampler.observed
        assert state.worker_alive_at_host_close is False
    assert all(row['Bobi.Rail.Scope.quark'] for row in state.snapshots)

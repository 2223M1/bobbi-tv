"""Retries through real installer transactions, and diagnostic-failure drains."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import sys

import pytest
from bobbi_platform import ce_install_ui as ui, runtime
from bobbi_platform.ce_installer import Installer
from bobbi_platform.instance_lock import InstanceLock
from test_ce_general_installer import signing, package


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    marker = tmp_path/'runtime.json'
    marker.write_text('{}')
    lease = InstanceLock(str(marker)+'.lock'); lease.acquire()
    enabled, events, clock = [True], [], [0.0]
    monkeypatch.setattr(ui, 'profile', lambda **kw: marker)
    monkeypatch.setattr(ui.time, 'monotonic', lambda: clock[0])
    def make():
        host = ui.KodiHost.__new__(ui.KodiHost)
        host.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: False))
        host.monitor = SimpleNamespace(waitForAbort=lambda dt: clock.__setitem__(0, clock[0]+dt) or False)
        host.skin = lambda: 'skin.estuary'
        return host
    def rpc(method, params):
        if method == 'Addons.GetAddonDetails':
            return {'addon': dict(version='1', enabled=enabled[0] if params['addonid']=='plugin.video.bobbi' else False)}
        assert method == 'Addons.SetAddonEnabled'
        events.append('disable'); enabled[0] = False
    monkeypatch.setattr(ui, 'rpc', rpc)
    def call(action, body, **kw):
        if action == 'status': return {'quiesce_protocol': 1}
        assert action == 'quiesce'
        marker.unlink(); return {'accepted': True}
    monkeypatch.setattr(runtime, 'call', call)
    yield SimpleNamespace(make=make, marker=marker, lease=lease, enabled=enabled, events=events)
    lease.close()


def test_retry_same_and_new_objects_never_disable_live_modern_owner(boundary):
    first, second = boundary.make(), boundary.make()
    try:
        for actor in (first, first, second):
            with pytest.raises(ui.UpdateError, match='CINEMA_SERVICE_NOT_STOPPED'): actor.quiesce()
            assert boundary.enabled[0] and not boundary.events
        boundary.lease.close()
        second.quiesce()
        assert boundary.events == ['disable']
    finally:
        first.close(); second.close()


@pytest.mark.parametrize('reply', [None, {}, {'ready': True}, {'quiesce_protocol': 2}, OSError(), RuntimeError()])
def test_unknown_state_is_not_legacy(boundary, monkeypatch, reply):
    def call(*a, **kw):
        if isinstance(reply, Exception): raise reply
        return reply
    monkeypatch.setattr(runtime, 'call', call)
    actor = boundary.make()
    with pytest.raises(ui.UpdateError, match='CINEMA_SERVICE_NOT_STOPPED'): actor.quiesce()
    assert not boundary.events


def test_explicit_legacy_reply_keeps_old_stop_path(boundary, monkeypatch):
    # Exact pre-protocol Host.status fields, not an empty or failed reply.
    monkeypatch.setattr(runtime, 'call', lambda *a, **kw: dict(ready=True, version='0.1.0',
        native_owner=False, preparation=False, shares=False, account={}, playback_adapter='standard'))
    original = ui.rpc
    def rpc(method, body):
        if method == 'Addons.SetAddonEnabled': boundary.lease.close()
        return original(method, body)
    monkeypatch.setattr(ui, 'rpc', rpc)
    actor=boundary.make()
    try:
        actor.quiesce(); assert boundary.events == ['disable']
    finally: actor.close()


def test_actual_apply_exception_then_recover_still_retains_owner(boundary, tmp_path, signing):
    host = boundary.make(); host.dependencies = lambda stage: None
    actor = Installer(tmp_path/'addons', tmp_path/'work', host, signing[1])
    bundle = package(tmp_path/'candidate.zip', signing, 1)
    with pytest.raises(ui.UpdateError, match='CINEMA_SERVICE_NOT_STOPPED'): actor.apply(bundle)
    assert actor._read()['phase'] == 'restoring' and not boundary.events
    replacement = boundary.make()
    resumed = Installer(tmp_path/'addons', tmp_path/'work', replacement, signing[1])
    with pytest.raises(ui.UpdateError, match='CINEMA_SERVICE_NOT_STOPPED'): resumed.recover()
    assert not boundary.events and not list((tmp_path/'addons').glob('*/addon.xml'))


def history_module():
    path = Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi/lib/services/standard_playback.py'
    spec=importlib.util.spec_from_file_location('ce2025_history',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_history_diagnostic_failure_does_not_lose_accepted_records(monkeypatch):
    attempted=[]
    def write(data):
        attempted.append(data)
        if data == 1: raise OSError('write failed')
    monkeypatch.setitem(sys.modules,'lib.utils.general.utils',SimpleNamespace(set_watched_file=write))
    def report(code): raise RuntimeError('report failed')
    writer=history_module().HistoryWriter(report)
    writer.save(1);writer.save(2);writer.close();writer.close();writer.save(3)
    assert attempted == [1,2]
    assert (writer.accepted,writer.completed,writer.failed,writer.diagnostic_failures)==(2,2,1,1)
    assert not writer.worker.is_alive()


def test_history_unexpected_worker_exit_is_not_successful_drain(monkeypatch):
    module=history_module()
    monkeypatch.setattr(module.HistoryWriter,'run',lambda self: None)
    writer=module.HistoryWriter(lambda code: None)
    writer.save(1)
    with pytest.raises(RuntimeError,match='HISTORY_DRAIN_INCOMPLETE'):writer.close()


def test_history_fatal_storage_exit_is_not_counted_as_success(monkeypatch):
    def write(data):raise SystemExit()
    monkeypatch.setitem(sys.modules,'lib.utils.general.utils',SimpleNamespace(set_watched_file=write))
    writer=history_module().HistoryWriter(lambda code:None)
    writer.save(1)
    with pytest.raises(RuntimeError,match='HISTORY_DRAIN_INCOMPLETE'):writer.close()
    assert writer.worker_failed and writer.failed==1

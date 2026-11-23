"""Actual IPC/owner/installer/lease, including a Kodi-manager lock analogue."""
from threading import Event, Thread
from types import SimpleNamespace
import time

import pytest
from bobbi_platform import ce_install_ui as ui, runtime
from bobbi_platform.host import Host
from bobbi_platform.stop_monitor import StopMonitor


def test_installer_drains_before_addon_manager_disable(tmp_path, monkeypatch):
    server = Host(tmp_path)
    server.start()
    server.can_quiesce = lambda: True
    server.bind_owner(lambda body: {'adapter': 'standard'})
    monkeypatch.setattr(runtime, 'profile', lambda **kw: tmp_path/'runtime.json')
    monkeypatch.setattr(ui, 'profile', lambda **kw: tmp_path/'runtime.json')
    release, entered, drained = Event(), Event(), Event()
    def slow_close():
        entered.set()
        assert release.wait(3)
        drained.set()
    server.playback = SimpleNamespace(close=slow_close)
    enabled, events, errors = [True], [], []
    def rpc(method, params):
        if method == 'Addons.GetAddonDetails':
            return {'addon': dict(enabled=enabled[0] if params['addonid']=='plugin.video.bobbi' else False, version='1')}
        assert method == 'Addons.SetAddonEnabled' and params['enabled'] is False
        # A real Kodi disable may hold a manager lock needed by auxiliary IO.
        # It must not start while any admitted worker can still need that lock.
        assert drained.is_set() and server._shutdown_complete
        assert actor._runtime_lease.fd is not None
        enabled[0] = False
        events.append('disable')
    monkeypatch.setattr(ui, 'rpc', rpc)
    actor = ui.KodiHost.__new__(ui.KodiHost)
    actor.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: False))
    actor.monitor = SimpleNamespace(waitForAbort=lambda seconds: time.sleep(seconds) or False)
    actor.skin = lambda: 'skin.estuary'
    def owner():
        while not server.stopping.wait(.005): server.tick()
        server.close()
    service = Thread(target=owner); service.start()
    def install():
        try: actor.quiesce()
        except BaseException as error: errors.append(error)
    installer = Thread(target=install); installer.start()
    try:
        assert entered.wait(1)
        assert enabled[0] and not events
        release.set()
        installer.join(3); service.join(3)
        assert not installer.is_alive() and not service.is_alive()
        assert not errors and events == ['disable']
    finally:
        release.set(); server.stopping.set()
        installer.join(4); service.join(4)
        actor.close(); server.close()


@pytest.mark.parametrize('idle', [False, None, 'unknown'])
def test_quiesce_requires_explicit_idle_on_owner(tmp_path, monkeypatch, idle):
    server = Host(tmp_path); server.start()
    server.can_quiesce = lambda: idle
    server.bind_owner(lambda body: {})
    monkeypatch.setattr(runtime, 'profile', lambda **kw: tmp_path/'runtime.json')
    errors = []
    def request():
        try: runtime.call('quiesce', {'protocol': 1})
        except ValueError as error: errors.append(error)
    worker = Thread(target=request); worker.start()
    try:
        deadline=time.monotonic()+1
        while server.calls.empty() and time.monotonic()<deadline: time.sleep(.005)
        server.tick(); worker.join(1)
        assert errors and not server.stopping.is_set()
    finally: server.close()


def test_local_cancellation_wakes_long_kodi_monitor_wait():
    stop = Event()
    calls=[]
    monitor = StopMonitor(stop, SimpleNamespace(abortRequested=lambda: False,
        waitForAbort=lambda value: calls.append(value) or stop.wait(value)))
    results=[]
    worker=Thread(target=lambda: results.append(monitor.waitForAbort(600)))
    worker.start(); stop.set(); worker.join(1)
    assert results == [True] and all(0 < value <= .1 for value in calls)
    assert monitor.waitForAbort(0) is True

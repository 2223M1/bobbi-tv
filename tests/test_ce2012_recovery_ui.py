"""Actual user entry, transaction and Kodi host adapter; only Kodi IO is fake."""
import sys
from types import SimpleNamespace
from threading import Thread, Event
import time

import pytest
from bobbi_platform import ce_install_ui as ui, runtime
from bobbi_platform.host import Host
from bobbi_platform.instance_lock import InstanceLock
from bobbi_platform.ce_installer import MANAGED
from test_ce_install_recovery import installed
from test_ce_general_installer import signing


@pytest.mark.parametrize('choice', ['exit', 'retry_exit', 'rollback'])
def test_real_main_keeps_recovery_choices_reachable(installed, monkeypatch, choice):
    actor = installed
    before = actor.host.read()
    def fail(*args):
        raise RuntimeError('persistent activation error')
    actor.host.activate = fail
    with pytest.raises(RuntimeError):
        actor.apply(actor.addons.parent / 'two.zip')
    choices = iter([0, -1] if choice == 'retry_exit' else [1, -1] if choice == 'rollback' else [-1])
    menus = []
    def select(title, actions, **kw):
        menus.append((title, actions))
        return next(choices)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: SimpleNamespace(select=select)))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(actor.addons)))
    monkeypatch.setattr(ui, 'profile', lambda *a, **kw: actor.work)
    monkeypatch.setattr(ui, 'KodiHost', lambda: actor.host)
    monkeypatch.setattr(ui, 'Installer', lambda *a: actor)
    ui.main()
    assert menus[0][0] == '安装恢复尚未完成'
    assert len(menus[0][1]) == 3
    assert (actor.addons.parent / 'user-history').read_text() == 'new user data'
    if choice == 'rollback':
        assert actor._read()['phase'] == 'restored'
        assert actor.host.read() == before
        assert all('1.0.0' in (actor.addons/n/'addon.xml').read_text() for n in MANAGED)
    else:
        assert actor._read()['phase'] == 'activation_pending'
        assert len(menus) == (2 if choice == 'retry_exit' else 1)


@pytest.mark.parametrize('fallback', ['enabled', 'disabled', 'absent', 'unknown', 'malformed'])
def test_strict_snapshot_does_not_invent_disabled(monkeypatch, fallback):
    def rpc(method, params):
        if method == 'Addons.GetAddonDetails' or fallback == 'unknown':
            raise RuntimeError('unavailable')
        if fallback == 'malformed':
            return {'addons': [{'broken': True}]}
        return {'addons': [] if fallback == 'absent' else [
            {'addonid': 'plugin.video.bobbi', 'enabled': fallback == 'enabled', 'version': '1'}]}
    monkeypatch.setattr(ui, 'rpc', rpc)
    host = ui.KodiHost.__new__(ui.KodiHost)
    if fallback in ('unknown', 'malformed'):
        with pytest.raises(RuntimeError): host.details('plugin.video.bobbi')
    else:
        value = host.details('plugin.video.bobbi')
        assert value == (None if fallback == 'absent' else
            dict(addonid='plugin.video.bobbi', enabled=fallback == 'enabled', version='1'))


def test_readiness_requires_actual_owner_queue_not_registration(tmp_path, monkeypatch):
    path = tmp_path/'runtime.json'
    monkeypatch.setattr(runtime, 'profile', lambda **_: path)
    monkeypatch.setattr(ui, 'profile', lambda **_: path)
    server = Host(tmp_path)
    server.start()
    server.bind_owner(lambda body: {'adapter': 'standard', 'desired': None})
    host = ui.KodiHost.__new__(ui.KodiHost)
    commands = []
    host.xbmc = SimpleNamespace(executebuiltin=commands.append)
    host.monitor = SimpleNamespace(waitForAbort=lambda _: False)
    finished = []
    worker = Thread(target=lambda: (host.ensure_running(), finished.append(True)))
    try:
        worker.start()
        end = time.monotonic()+1
        while server.calls.empty() and time.monotonic()<end: time.sleep(.005)
        assert not finished  # runtime file and enabled flags cannot complete it.
        server.tick()
        worker.join(1)
        assert finished == [True] and not commands
    finally:
        server.close()


def test_enabled_without_host_restarts_actual_service_once(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, 'profile', lambda **_: tmp_path/'runtime.json')
    replies, commands, enabled = [False], [], [True]
    def call(*args, **kwargs):
        if not replies[0]: raise OSError('not running')
        return {'adapter': 'standard', 'desired': None}
    monkeypatch.setattr(runtime, 'call', call)
    host = ui.KodiHost.__new__(ui.KodiHost)
    host.xbmc = SimpleNamespace(executebuiltin=lambda command: pytest.fail('Unmanaged RunScript'))
    def rpc(method, params):
        assert params['addonid'] == 'plugin.video.bobbi'
        if method == 'Addons.GetAddonDetails':
            return {'addon': {'enabled': enabled[0], 'version': '1'}}
        assert method == 'Addons.SetAddonEnabled'
        commands.append(params['enabled'])
        enabled[0] = params['enabled']
        replies[0] = enabled[0]
        return 'OK'
    monkeypatch.setattr(ui, 'rpc', rpc)
    host.monitor = SimpleNamespace(waitForAbort=lambda _: False)
    host.ensure_running()
    assert commands == [False, True] and enabled[0]


def test_host_shutdown_keeps_os_lease_through_dependency_close(tmp_path):
    host = Host(tmp_path)
    host.start()
    verified = []
    def close_stream():
        contender = InstanceLock(str(tmp_path/'runtime.json')+'.lock')
        with pytest.raises(OSError): contender.acquire()
        verified.append(True)
    host.streams = SimpleNamespace(close=close_stream)
    host.close()
    assert verified == [True]
    contender = InstanceLock(str(tmp_path/'runtime.json')+'.lock')
    contender.acquire()
    contender.close()


@pytest.mark.parametrize('worker_kind', ['http', 'engine', 'catalog'])
def test_runtime_lease_outlives_admitted_slow_work(tmp_path, monkeypatch, worker_kind):
    entered, release = Event(), Event()
    server = Host(tmp_path)
    server.start()
    monkeypatch.setattr(runtime, 'profile', lambda **_: tmp_path/'runtime.json')
    def slow(*args):
        entered.set()
        if not release.wait(4): raise RuntimeError('fixture was not released')
        return {}
    if worker_kind == 'http':
        server.runtime.server.dispatch = slow
        worker = Thread(target=lambda: runtime.call('status', {}, timeout=5))
    else:
        worker = Thread(target=slow)
        setattr(server, 'engine_worker' if worker_kind == 'engine' else 'refresh_worker', worker)
    worker.start()
    assert entered.wait(1)
    closed = Event()
    closer = Thread(target=lambda: (server.close(), closed.set()))
    closer.start()
    contender = InstanceLock(str(tmp_path/'runtime.json')+'.lock')
    try:
        assert not closed.wait(.5), 'unfinished work is not quiescence'
        with pytest.raises(OSError): contender.acquire()
    finally:
        release.set()
        worker.join(3)
        closer.join(3)
    assert closed.is_set()
    contender.acquire()
    contender.close()


def test_persistent_restore_failure_keeps_retry_and_exit_reachable(installed, monkeypatch):
    actor = installed
    actor.apply(actor.addons.parent/'two.zip')
    actor.host.restore = lambda *args: (_ for _ in ()).throw(RuntimeError('persistent restore'))
    with pytest.raises(RuntimeError): actor.rollback()
    menus, choices = [], iter([0, -1])
    def select(title, actions, **kw):
        menus.append(actions)
        return next(choices)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: SimpleNamespace(select=select)))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(actor.addons)))
    monkeypatch.setattr(ui, 'profile', lambda *a, **kw: actor.work)
    monkeypatch.setattr(ui, 'KodiHost', lambda: actor.host)
    monkeypatch.setattr(ui, 'Installer', lambda *a: actor)
    ui.main()
    assert len(menus) == 2 and all(len(menu) == 2 for menu in menus)
    assert actor._read()['host_pending'] == 'restore'
    assert (actor.addons.parent/'user-history').read_text() == 'new user data'

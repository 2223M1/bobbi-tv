"""Full native owner-loop module cooperates with real Host/Runtime shutdown."""
import importlib.util
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
import sys
import time


def test_native_owner_and_auxiliary_monitor_exit_without_kodi_disable(tmp_path, monkeypatch):
    from bobbi_platform.host import Host
    from bobbi_platform import runtime
    class Monitor:
        def abortRequested(self): return False  # Kodi addon remains enabled.
        def waitForAbort(self, seconds): time.sleep(seconds); return False
    monkeypatch.setattr(sys.modules['xbmc'], 'Monitor', Monitor)
    path=Path(__file__).resolve().parents[2]/'addons/plugin.video.bobbi/lib/services/background_service.py'
    spec=importlib.util.spec_from_file_location('ce2020_native_service', path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    calls, account_bindings = [], []
    account_changed = lambda: None
    control=SimpleNamespace(authority=SimpleNamespace(dispatch=lambda body: {'boot_id': 'native'},
        configure_accounts=lambda accounts:account_bindings.append(accounts), account_changed=account_changed),
        native=SimpleNamespace(subtitle_fallback=SimpleNamespace()), tick=lambda:None, close=lambda:calls.append('control_drained'))
    monkeypatch.setitem(sys.modules,'lib.services.playback_control',SimpleNamespace(PlaybackControlServer=lambda **kw:control))
    server=Host(tmp_path); server.start(); server.can_quiesce=lambda:True
    monkeypatch.setattr(runtime,'profile',lambda **kw:tmp_path/'runtime.json')
    actor=module.JacktookMOnitor()
    entered, done=Event(), Event()
    def auxiliary():
        monitor=actor._worker_monitor()
        def work():
            entered.set()
            assert monitor.waitForAbort(600)  # owner stop, not Kodi abort
            done.set()
        actor._auxiliary_workers.append(actor._start_worker(work))
    monkeypatch.setattr(actor,'_start_auxiliary_services',auxiliary)
    errors=[]
    def service():
        try: actor.run_owner_loop(host=server)
        except BaseException as error: errors.append(error)
        finally: server.close()
    worker=Thread(target=service); worker.start()
    try:
        assert entered.wait(1)
        assert account_bindings == [server.accounts]
        assert server.owner_account_changed is account_changed
        assert runtime.call('quiesce',{'protocol':1}) == {'accepted':True}
        worker.join(3)
        assert not worker.is_alive() and not errors and done.is_set()
        assert calls == ['control_drained'] and server._shutdown_complete
    finally:
        server.stopping.set(); actor._owner_stopped.set()
        worker.join(4); server.close()

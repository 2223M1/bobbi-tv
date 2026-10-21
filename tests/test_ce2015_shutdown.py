"""Actual portable entry -> standard workers -> Host/Runtime -> OS lease."""
from threading import Thread, Event
from types import SimpleNamespace
import importlib.util
from pathlib import Path
import sys

import pytest
from test_standard_product import product, selected, handoff
from bobbi_platform.host import Host
from bobbi_platform.instance_lock import InstanceLock


@pytest.mark.parametrize('kind', ['next', 'subtitle', 'history', 'all', 'close_error'])
def test_real_entry_drains_consumers_before_replacement(product, monkeypatch, tmp_path, kind):
    from lib import portable_runtime
    host = Host(tmp_path)
    actor = product.actor
    # Preserve actual HistoryWriter despite the older product fixture's DB stub.
    path = Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi/lib/services/standard_playback.py'
    spec = importlib.util.spec_from_file_location('ce2015_history', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    release = Event()
    entered = {name: Event() for name in ('next', 'subtitle', 'history', 'catalog')}
    finished, errors, written = Event(), [], []
    def slow(name):
        entered[name].set()
        assert release.wait(5), 'test IO must be released'
        if name == 'history': written.append(name)
    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(set_watched_file=lambda data: slow('history')))
    actor.history = module.HistoryWriter(host.report)
    actor.session.history = actor.history.save
    def factory(actual):
        assert actual is host
        actor.host, actor.session.accounts, host.playback = host, host.accounts, actor
        host.bind_owner(actor.dispatch)
        actor.session.next_loader = (lambda *args: slow('next')) if kind in ('next', 'all') else None
        data = selected(product)
        if kind in ('subtitle', 'all'):
            monkeypatch.setattr(product.module, 'discover', lambda *args: slow('subtitle'))
            actor.dispatch(dict(operation='subtitle_start', request_id=data['request_id'], data=data))
        handoff(product, data)
        if kind == 'close_error':
            host.images.close()
            def fail(): raise OSError('image close injected')
            host.images = SimpleNamespace(close=fail)
            host.refresh_worker = Thread(target=lambda: slow('catalog'))
            host.refresh_worker.start()
        return actor
    monkeypatch.setitem(sys.modules, 'lib.services.standard_playback', SimpleNamespace(StandardPlayback=factory))
    monkeypatch.setitem(sys.modules, 'bobbi_platform.host', SimpleNamespace(Host=lambda *a, **kw: host))
    monkeypatch.setitem(sys.modules, 'bobbi_platform.paths', SimpleNamespace(profile=lambda *a, **kw: tmp_path))
    monkeypatch.setitem(sys.modules, 'bobbi_core.runtime_paths', SimpleNamespace(configure=lambda *a, **kw: None, native_subtitle_abi=lambda *a: None))
    monkeypatch.setattr(sys.modules['xbmc'], 'Monitor', lambda: SimpleNamespace(waitForAbort=lambda _: True), raising=False)
    def run():
        try: portable_runtime.main({'native_contract_available': False})
        except BaseException as error: errors.append(error)
        finally: finished.set()
    worker = Thread(target=run); worker.start()
    claimant = InstanceLock(str(tmp_path/'runtime.json')+'.lock')
    try:
        required = ['history'] + (['next', 'subtitle'] if kind == 'all' else
                    [kind] if kind in ('next', 'subtitle') else ['catalog'] if kind == 'close_error' else [])
        assert all(entered[name].wait(1) for name in required)
        assert not finished.wait(.4)
        with pytest.raises(OSError): claimant.acquire()
        # Closing admission while a late result is blocked cannot queue more work.
        release.set(); worker.join(3)
        assert finished.is_set() and not actor.history.worker.is_alive()
        assert written  # accepted STARTED/SERVICE_STOPPED records were not dropped
        assert len(product.state.opened) == 1 and not product.state.subtitles
        if kind == 'close_error':
            assert len(errors) == 1 and isinstance(errors[0], OSError)
            with pytest.raises(OSError): claimant.acquire()
            host.images = None
            host.close()  # retry drains and releases; never silently successful
        else:
            assert not errors
        claimant.acquire(); claimant.close()
        host.close()
    finally:
        release.set(); worker.join(6); claimant.close()
        host.images = None
        host.close()


def test_failed_close_does_not_skip_later_consumers(tmp_path):
    host = Host(tmp_path); host.start()
    called = []
    host.images.close()
    def fail(): called.append('image'); raise OSError('injected')
    host.images = SimpleNamespace(close=fail)
    host.streams = SimpleNamespace(close=lambda: called.append('stream'))
    with pytest.raises(OSError): host.close()
    assert called == ['image', 'stream']
    claimant = InstanceLock(str(tmp_path/'runtime.json')+'.lock')
    with pytest.raises(OSError): claimant.acquire()
    host.images = None; host.close()
    claimant.acquire(); claimant.close()


def test_close_reporting_failure_cannot_skip_drain(tmp_path):
    def broken_report(code):
        raise RuntimeError('diagnostic sink unavailable')
    host = Host(tmp_path, report=broken_report)
    host.start()
    host.close()
    assert host._shutdown_complete
    claimant = InstanceLock(str(tmp_path/'runtime.json')+'.lock')
    claimant.acquire(); claimant.close()

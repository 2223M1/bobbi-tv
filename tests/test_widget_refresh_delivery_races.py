"""The owner must acknowledge only the revision it actually dispatched."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def test_new_invalidation_arriving_during_builtin_survives_previous_ack(monkeypatch):
    sid, generation = 'a' * 32, 'b' * 64
    folder = ('plugin://plugin.video.bobbi.library/?action=emby_page&source='
              + sid + '&revision=' + generation + '&parent=root')
    calls = []
    def builtin(command):
        calls.append(command)
        if len(calls) == 1:
            # Represents the dependency worker publishing a newer snapshot
            # while Kodi handles the previous owner's refresh request.
            service._schedule_container_refresh(sid, generation, 3, folder)
    xbmc = SimpleNamespace(getInfoLabel=lambda _: folder,
        getCondVisibility=lambda _: False, executebuiltin=builtin)
    monkeypatch.setitem(sys.modules, 'xbmc', xbmc)
    spec = importlib.util.spec_from_file_location('widget_delivery_race',
        ROOT / 'addons/plugin.video.bobbi/lib/services/widget_refresh.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    service = module.WidgetRefreshService(host=SimpleNamespace(
        check_profile=lambda: True, root=Path('/profile'), plugin_root=Path('/profile')))
    service._schedule_container_refresh(sid, generation, 2, folder)
    service.tick()
    assert service._pending_container is not None
    assert service._pending_container['revision'] == 3
    service.tick()
    assert service._pending_container is None
    assert calls == ['Container.Refresh', 'Container.Refresh']
    service.tick()
    assert len(calls) == 2


def test_directory_readback_cannot_confirm_invalidation_arriving_during_fetch(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from bobbi_platform import emby_artwork, emby_dynamic, optimization, runtime
    from bobbi_platform.emby_session import EmbyInvalidationHub
    sid, generation = 'a' * 32, 'b' * 64
    hub = EmbyInvalidationHub(tmp_path)
    source = SimpleNamespace(id=sid, kind='media_server', password='synthetic-token',
        location='https://emby.example.invalid', name='Synthetic Emby',
        metadata={'provider': 'emby', 'server_id': 'srv1', 'user_id': 'usr1'})
    store = SimpleNamespace(source_snapshot=lambda _: (source, generation))
    monkeypatch.setattr(emby_dynamic, 'ProfileBinding', lambda: SimpleNamespace(
        root=lambda: tmp_path, is_current=lambda: True))
    monkeypatch.setattr(optimization, 'observe', lambda *_: None)
    monkeypatch.setattr(emby_artwork, 'poster_factory', lambda *_: lambda *_: '')
    calls = []
    def call(action, body, timeout):
        assert action == 'emby_invalidation_status'
        calls.append(dict(body))
        if body.get('confirm'):
            return hub.mark_confirmed(sid, generation, expected_revision=body['expected_revision'])
        return hub.snapshot(sid, generation)
    monkeypatch.setattr(runtime, 'bind_call', lambda _: call)
    class Client:
        def __init__(self, *_):
            self.session = SimpleNamespace(budget=lambda _: nullcontext())
        def _identity(self, **_):
            pass
        def page_rows(self, *_, **__):
            hub.notify_event(sid, generation, item_ids=['later-update'])
            return [], 0
    monkeypatch.setattr(emby_dynamic, 'Client', Client)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: False)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: SimpleNamespace(ok=lambda *_: None)))
    finished = []
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(
        setPluginCategory=lambda *_: None, setContent=lambda *_: None,
        addDirectoryItems=lambda *_: None, endOfDirectory=lambda *a, **kw: finished.append(kw)))
    before = hub.snapshot(sid, generation)['revision']
    emby_dynamic.execute(7, {'action': 'emby_page', 'source': sid, 'revision': generation,
        'parent': 'recent'}, store, lambda *_: None)
    assert finished == [{'succeeded': True, 'cacheToDisc': False}]
    assert len(calls) == 2 and calls[-1]['expected_revision'] == before
    snapshot = hub.snapshot(sid, generation)
    assert snapshot['revision'] == before + 1
    assert snapshot['sync_state'] == 'dirty'
    assert hub.mark_confirmed(sid, generation, expected_revision=before + 1)['sync_state'] == 'synced'
    hub.close()

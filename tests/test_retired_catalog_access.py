"""Retired upstream access cannot be revived by an old setting or cached source."""
import importlib.util
from pathlib import Path
import socket
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import juku_api, share_catalog


def plugin_module(relative):
    path = ROOT / 'addons/plugin.video.bobbi/lib' / relative
    spec = importlib.util.spec_from_file_location('retired_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unexpected(*args, **kwargs):
    pytest.fail('Retired catalogue attempted configuration or network IO')


@pytest.mark.parametrize('configured', [False, True])
def test_default_client_cannot_resolve_connect_authenticate_or_create_state(tmp_path, monkeypatch, configured):
    root = tmp_path / 'catalogue'
    if configured:
        root.mkdir()
        (root / 'config.json').write_text('{"proxy":"http://127.0.0.1:9999"}')
        (root / 'session.json').write_text('{"accessToken":"synthetic-old-token"}')
    before = {p.name: p.read_bytes() for p in root.glob('*')}
    monkeypatch.setattr(socket, 'getaddrinfo', unexpected)
    monkeypatch.setattr(socket, 'create_connection', unexpected)
    monkeypatch.setattr(juku_api, 'load_json', unexpected)
    monkeypatch.setattr(juku_api, 'build_opener', unexpected)
    monkeypatch.setattr(juku_api.Client, '_session', unexpected)
    assert juku_api.BASE == ''
    with pytest.raises(juku_api.JukuError, match='CATALOGUE_DISABLED'):
        juku_api.Client(state=root)
    assert {p.name: p.read_bytes() for p in root.glob('*')} == before
    assert root.exists() is configured


@pytest.mark.parametrize('xml', [None, '<settings/>',
    '<settings><setting id="juku_enabled">true</setting></settings>'])
def test_legacy_setting_and_old_cached_source_cannot_reactivate_provider(tmp_path, monkeypatch, xml):
    path = tmp_path / 'settings.xml'
    if xml is not None:
        path.write_text(xml)
    provider = plugin_module('clients/juku_provider.py')
    monkeypatch.setitem(sys.modules, 'xbmcaddon', SimpleNamespace(
        Addon=lambda _: SimpleNamespace(getSetting=lambda key: 'true')))
    monkeypatch.setattr(juku_api, 'Client', unexpected)
    assert not share_catalog.juku_enabled(path) and not provider.enabled()
    result = provider.find_sources({'tmdb_id': 101}, 'movies', None, None, 2024,
        ['Fixture'], None, time.monotonic() + 1, lambda: False)
    assert not result and result.completion.skipped == 1
    assert provider.next_source({}, {}, lambda: False, time.monotonic() + 1) == (
        None, 'PROVIDER_DISABLED')
    with pytest.raises(RuntimeError, match='共享目录已关闭'):
        provider.resolve_source(SimpleNamespace(), {})
    with pytest.raises(ValueError, match='SHARE_CATALOG_UNAVAILABLE'):
        share_catalog.catalog(dict(locator='am6bjuku://' + 'a' * 64, guid='juku:' + 'a' * 64))


def test_registry_keeps_other_catalogue_and_never_loads_retired_adapter(monkeypatch):
    registry = plugin_module('clients/catalog_providers.py')
    qqdocs = SimpleNamespace(SITE='115 资源目录', find_sources=object())
    imported, calls = [], []
    def adapter(name):
        imported.append(name)
        assert name == 'lib.clients.qqdocs_provider'
        return qqdocs
    monkeypatch.setattr(registry, 'import_module', adapter)
    manager = SimpleNamespace(deadline=time.monotonic() + 1, cancelled=lambda: False,
        submit_task=lambda *args, **kwargs: calls.append(args[1]))
    registry.submit_catalogs(manager, {'tmdb_id': 101}, 'movies', None, None, 2024,
        ['Fixture'], None)
    assert calls == ['qqdocs'] and imported == ['lib.clients.qqdocs_provider']
    assert registry.provider_for(SimpleNamespace(type='Direct', guid='juku:old')) is None


def test_startup_does_not_schedule_removed_background_refresh(tmp_path, monkeypatch):
    runtime = plugin_module('portable_runtime.py')
    closed = []
    playback = [False]
    host = SimpleNamespace(start=lambda: None, configure_preparation=lambda *a: None,
        configure_catalog_refresh=unexpected, close=lambda: closed.append(True),
        stopping=SimpleNamespace(is_set=lambda: False))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Player=lambda: SimpleNamespace(isPlaying=lambda: playback[0]),
        Monitor=lambda: SimpleNamespace(waitForAbort=lambda _: True),
        getGlobalIdleTime=lambda: 60, log=lambda *args: None, LOGINFO=1))
    monkeypatch.setitem(sys.modules, 'bobbi_platform.host', SimpleNamespace(Host=lambda *a, **k: host))
    monkeypatch.setitem(sys.modules, 'bobbi_platform.paths', SimpleNamespace(profile=lambda *a: tmp_path))
    monkeypatch.setitem(sys.modules, 'bobbi_platform.kodi', SimpleNamespace(rpc=lambda *a: None))
    monkeypatch.setitem(sys.modules, 'bobbi_core.runtime_paths', SimpleNamespace(
        configure=lambda *a, **k: None, native_subtitle_abi=lambda *a: None))
    monkeypatch.setitem(sys.modules, 'lib.services.standard_playback', SimpleNamespace(
        StandardPlayback=lambda host: None))
    runtime.main({'native_contract_available': False})
    assert closed == [True]
    assert host.idle_probe() is True and host.playing is False
    playback[0] = True
    assert host.idle_probe() is False and host.playing is True


def test_host_keeps_polling_local_idle_state_without_catalogue_worker():
    from bobbi_platform.host import Host
    host = SimpleNamespace(refresh=None, refresh_worker=None, idle_check=0, idle=False,
        idle_probe=lambda: True)
    Host._tick_catalog(host)
    assert host.idle is True and host.refresh_worker is None
    host.idle_probe = lambda: False
    host.idle_check = 0
    Host._tick_catalog(host)
    assert host.idle is False and host.refresh_worker is None


def test_no_shipped_upstream_host_or_migration():
    for path in (ROOT / 'addons').rglob('*.py'):
        source = path.read_text(encoding='utf-8')
        assert 'api.jukuku.xyz' not in source and 'api.juku.xyz' not in source, str(path)
    migration = (ROOT / 'tools/deploy_ce_remote.py').read_text(encoding='utf-8')
    assert 'old_juku' not in migration

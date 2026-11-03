"""Unused optional account integrations must not delay a cached source picker."""
import builtins
import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def test_debrid_utility_import_does_not_load_any_optional_provider(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith('lib.clients.debrid.'), name
        assert name != 'lib.utils.torrent.torrserver_utils', name
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    path = Path(__file__).resolve().parents[2] / 'addons/plugin.video.bobbi/lib/utils/debrid/debrid_utils.py'
    spec = importlib.util.spec_from_file_location('lazy_debrid_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.is_supported_debrid_type(module.DebridType.RD)
    assert not module.is_supported_debrid_type(None)
    calls = []
    for kind, (provider, name) in module.DEBRID_HELPERS.items():
        sentinel = object()
        def factory(target, expected='lib.clients.debrid.' + provider, cls=name, result=sentinel):
            assert target == expected
            calls.append(target)
            return SimpleNamespace(**{cls: lambda: result})
        monkeypatch.setattr(importlib, 'import_module', factory)
        assert module.get_debrid_helper(kind) is sentinel
    assert len(calls) == len(module.DEBRID_HELPERS)


def test_search_import_keeps_network_clients_lazy_in_fresh_interpreter():
    root = Path(__file__).resolve().parents[2]
    script = '''
import builtins, runpy, sys
fixture = runpy.run_path('tests/private_baseline/conftest.py')
original = builtins.__import__
def guarded(name, *args, **kwargs):
    assert name != 'requests' and not name.startswith('requests.'), name
    assert not name.startswith('lib.clients.debrid.'), name
    assert name != 'lib.utils.torrent.torrserver_utils', name
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
try:
    import lib.search
    assert 'requests' not in sys.modules
finally:
    fixture['pytest_sessionfinish'](None, 0)
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', script], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_real_search_route_does_not_import_navigation(monkeypatch):
    from lib import router, search
    calls = []
    params = {'action': 'search', 'ids': '{"tmdb_id":65329}', 'force_select': True}
    monkeypatch.setattr(search, 'run_search_entry', lambda value: calls.append(value))
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert name != 'lib.navigation', 'Picker must not import unrelated navigation providers'
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    router._route_core('search', params)
    assert calls == [params]
    assert calls[0] is params

"""The real continuation function retains the host's six-second search budget."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT / 'addons' / addon / 'lib'))
from bobbi_core.catalog_release import release_envelope
from bobbi_catalog.identity import media_key
from bobbi_platform import runtime, paths
from bobbi_platform.host import Host
from test_accounts import credential


@pytest.mark.parametrize('late', ['none', 'cancel', 'wrong_account'])
def test_exact_same_share_next_episode_survives_full_host_budget(tmp_path, monkeypatch, late):
    from bobbi_catalog import api
    monkeypatch.setattr(paths, 'profile', lambda addon, name='': tmp_path/addon/name)
    # Isolated catalogue instance avoids changing another test's Kodi profile.
    spec = importlib.util.spec_from_file_location('bobbi_catalog.catalog',
        ROOT/'addons/script.module.bobbi.catalog/lib/bobbi_catalog/catalog.py')
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    monkeypatch.setitem(sys.modules, 'bobbi_catalog.catalog', catalog)
    source = ROOT / 'addons/plugin.video.bobbi/lib/utils/player/direct_continuity.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_qqdocs')
    namespace = dict(release_envelope=release_envelope)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    for name in ('lib', 'lib.clients'):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, ModuleType(name))
    provider = ModuleType('lib.clients.qqdocs_provider')
    provider.enabled = lambda: True
    monkeypatch.setitem(sys.modules, provider.__name__, provider)
    cache_class, cache_path = catalog.Cache, tmp_path/'cache.sqlite'
    anchor = dict(fid='1', cell='A1', origin='fixture', name='Fixture.S01E02.1080p.Group.mkv', size=1000)
    following = dict(fid='2', name='Fixture.S01E03.1080p.Group.mkv', size=2000)
    fields = catalog.fields(anchor)
    cache = cache_class(cache_path)
    cache.remember(fields['guid'], media_key(1, 'tv', 1, 2), anchor)
    cache.close()
    monkeypatch.setattr(catalog, 'Cache', lambda: cache_class(cache_path))
    monkeypatch.setattr(catalog, 'share_for', lambda cell: dict(code='fixture123', password='pass', cell=cell))
    h, calls = Host(tmp_path/'host'), []
    h.start()
    scope = h.accounts.install(credential(), h.accounts.snapshot())
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['account_scope'] == scope
        def search(self, share, query, deadline, cancelled):
            assert query == 'S01E03' and share == dict(code='fixture123', password='pass')
            assert 5.5 < deadline-time.monotonic() <= 6
            return [following]
    monkeypatch.setattr(api, 'Client', Client)
    def call(action, body, timeout=3):
        calls.append((action, timeout))
        assert timeout == 6.5  # Former default of 3 would abandon a valid 3-6s reply.
        result = h.dispatch(action, body)
        return dict(result, account=dict(scope, epoch=scope['epoch']+1)) if late == 'wrong_account' else result
    monkeypatch.setattr(runtime, 'call', call)
    current = dict(_account=scope, source_title=anchor['name'],
        direct_source=dict(provider='qqdocs', guid=fields['guid'], locator=fields['url'], size=anchor['size']))
    try:
        value, reason = namespace['_qqdocs'](current, (1,1,2), lambda:late == 'cancel')
        assert calls == [('share_search', 6.5)]
        cache = cache_class(cache_path)
        try:
            stored = cache.selected('qqdocs:A1:2', media_key(1,'tv',1,3))
            if late == 'none':
                assert reason == 'INDEXED_DIRECT_SAME_RELEASE' and value['title'] == following['name']
                assert stored == dict(following, cell=anchor['cell'], origin=anchor['origin'])
            else:
                assert value is None and stored is None
                assert reason == ('CANCELLED' if late == 'cancel' else 'ACCOUNT_SCOPE_CHANGED')
        finally:
            cache.close()
    finally:
        h.close()

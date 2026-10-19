import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'plugin.video.bobbi'):
    path = ROOT / 'addons' / addon
    sys.path.insert(0, str(path / 'lib' if addon.startswith('script') else path))
from bobbi_core.subtitle_lookup_portable import SubtitleLookup


def eventually(test, timeout=1):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if test():
            return
        time.sleep(.005)
    assert test()


def test_portable_subtitle_lookup_never_waits_on_actor_or_uses_unix_socket():
    began, release = Event(), Event()
    calls = []
    def call(method, body, timeout):
        calls.append(body['request_id'])
        began.set()
        assert release.wait(1)
        return {'state': 'candidate', 'request_id': body['request_id']}
    lookup = SubtitleLookup(call=call)
    try:
        start = time.monotonic()
        assert lookup.request({'request_id': 'A'}) == {'state': 'pending'}
        assert time.monotonic() - start < .1
        assert began.wait(1)
        for value in ('B', 'C', 'D'):
            assert lookup.request({'request_id': value}) == {'state': 'pending'}
        assert calls == ['A']
        release.set()
        eventually(lambda: not lookup.worker.is_alive())
        lookup.tick()
        eventually(lambda: not lookup.worker.is_alive())
        lookup.tick()
        assert calls == ['A', 'D']
        assert lookup.request({'request_id': 'D'}) == {'state': 'candidate', 'request_id': 'D'}
    finally:
        release.set()
        lookup.close()


def test_portable_subtitle_close_discards_late_success():
    release, begun = Event(), Event()
    def call(*args, **kwargs):
        begun.set()
        release.wait(1)
        return {'state': 'ready'}
    lookup = SubtitleLookup(call=call)
    lookup.request({'request_id': 'A'})
    assert begun.wait(1)
    lookup.close()
    release.set()
    lookup.worker.join(1)
    lookup.tick()
    assert lookup.result is None
    assert lookup.request({'request_id': 'A'})['state'] == 'unavailable'


def test_actual_portable_service_entrypoint_with_empty_profile(tmp_path):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([
        str(ROOT / 'addons/script.module.bobbi.platform/lib'),
        str(ROOT / 'addons/script.module.bobbi.core/lib'), str(ROOT / 'addons/plugin.video.bobbi')]))
    script = '''import sys, types
from pathlib import Path
class Monitor:
 def __init__(self): self.n=0
 def waitForAbort(self, seconds): self.n+=1; return self.n>1
class Player:
 def isPlaying(self): return False
xbmc=types.SimpleNamespace(Monitor=Monitor,Player=Player,getGlobalIdleTime=lambda:0,
 log=lambda *a:None,LOGINFO=1)
sys.modules['xbmc']=xbmc
sys.modules['xbmcvfs']=types.SimpleNamespace(translatePath=lambda p:str(Path(sys.argv[1])/p.split('/')[-1]))
from lib.portable_runtime import main
main({'native_contract_available':False})
assert 'lib.native_player' not in sys.modules
assert 'bobbi_core.preparation_host' not in sys.modules
assert 'bobbi_platform.native_engine' not in sys.modules
assert not list(Path(sys.argv[1]).rglob('runtime.json'))
'''
    subprocess.run([sys.executable, '-B', '-c', script, str(tmp_path)], env=env, check=True, timeout=10)


def module(name):
    path = ROOT / 'addons/plugin.video.bobbi/lib/clients/tmdb' / (name + '.py')
    spec = importlib.util.spec_from_file_location('portable_test_' + name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize('name', ['frontend_metadata', 'season_cards'])
def test_card_queue_lock_uses_real_portable_exclusion(tmp_path, monkeypatch, name):
    target = module(name)
    monkeypatch.setattr(target, '_root', lambda: tmp_path)
    with target._lock('queue') as first:
        assert first
        with target._lock('queue') as second:
            assert second is False
    with target._lock('queue') as available:
        assert available


class Cache:
    def __init__(self):
        self.data = {}
    def get(self, key):
        return self.data.get(key)
    def set(self, key, data, expires):
        self.data[key] = data


def test_detail_refresh_with_cross_interpreter_lease_works_on_windows(tmp_path):
    target = module('detail_cache')
    expected = dict(id=1, name='Fixture', seasons=[{'season_number': 1}])
    assert target.get('tv_details', {'id': 1}, 'zh', Cache(), lambda _: expected,
                      lock_root=tmp_path) == expected


def test_search_admission_uses_configured_profile_not_global_storage(tmp_path):
    from bobbi_core import runtime_paths
    from bobbi_core.search_admission import try_acquire
    previous = runtime_paths._profile
    runtime_paths.configure(tmp_path)
    first = None
    try:
        first = try_acquire()
        assert first is not None
        assert (tmp_path / 'search-admission/active.lock').is_file()
        assert try_acquire() is None
    finally:
        if first:
            first.release()
        runtime_paths._profile = previous

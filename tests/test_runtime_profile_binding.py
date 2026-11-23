"""Captured runtime paths: real I/O, old-source controls, no Kodi/device needed."""
from functools import partial
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread, get_ident
import time
from types import SimpleNamespace

import pytest

from bobbi_core import runtime_paths, subtitle_candidates, subtitle_export
from bobbi_core.preparation_host import Lease
from bobbi_core.progressive_search import ProgressiveSearch
from bobbi_core.search_admission import try_acquire
from bobbi_core.source_list_session import SourceListSession
from bobbi_platform.paths import ProfileBinding
from bobbi_platform.host import Host
from test_provider_streaming import chain

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'addons/script.module.bobbi.core/lib'
BASE = '1eb2e58b668916b950d332337486109184c48a18'


@pytest.fixture
def profiles(tmp_path):
    active = ['A']
    binding = ProfileBinding(lambda addon: tmp_path / active[0] / addon)
    def revoke():
        active[0] = 'B'
        assert binding.is_current() is False
        active[0] = 'A'
        assert binding.is_current() is False
    return SimpleNamespace(binding=binding, active=active, revoke=revoke,
        root=binding.root('plugin.video.bobbi'), other=tmp_path / 'B')


def original(path):
    result = subprocess.run(['git', 'show', BASE + ':' + path], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', check=True)
    return result.stdout


def isolated(script, *args):
    wrapper = 'import json, sys; script, args = json.load(sys.stdin); sys.argv = ["-c", *args]; exec(compile(script, "<isolated-profile-probe>", "exec"))'
    result = subprocess.run([sys.executable, '-I', '-B', '-c', wrapper],
                            input=json.dumps([script, [str(CORE), *map(str, args)]]),
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_core_paths_and_leaves_have_no_kodi_platform_or_home_fallback_in_isolated_python(tmp_path):
    isolated(r'''
import importlib.abc, sys
from pathlib import Path
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        assert fullname.split('.')[0] not in {'xbmc','xbmcvfs','xbmcaddon','xbmcgui','bobbi_platform','lib'}, fullname
sys.meta_path.insert(0, Deny())
sys.path.insert(0, sys.argv[1])
from bobbi_core import runtime_paths as p, direct_cloud_client as direct, subtitle_candidates as candidates
from bobbi_core import subtitle_export, search_admission, share_subtitles, torrent_subtitles
assert not hasattr(p, '_profile')
Path.home = classmethod(lambda cls: (_ for _ in ()).throw(AssertionError('home fallback')))
root = Path(sys.argv[2])
assert p.configure(root) == str(root/'subtitle-browser')
assert str(p.ProfilePath('assrt-token', profile=root)) == str(root/'assrt-token')
assert direct.snapshot() == {}
for call in (lambda: p.ProfilePath('assrt-token'), lambda: search_admission.try_acquire(),
             lambda: candidates.publish(b'text', '.srt'), lambda: subtitle_export.export(None, {})):
    try: call()
    except (TypeError, ValueError): pass
    else: raise AssertionError('uncaptured path accepted')
assert sorted(item.name for item in root.iterdir()) == ['runtime-paths.json', 'subtitle-browser']
''', tmp_path / 'profile')


@pytest.mark.parametrize('legacy', [False, True])
def test_independent_interpreters_read_same_descriptor_and_upgrade_resets_only_new_captures(tmp_path, legacy):
    script = r'''
import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from bobbi_core import runtime_paths as p
root, legacy, mode = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
p.CE_F9_ROOT = str(legacy)
p._coreelec = lambda: True
if mode == 'legacy':
    p.configure(root, subtitle_root=str(legacy), native_sha256=p.CE_F9_SHA256)
elif mode == 'profile': p.configure(root)
print(str(p.ProfilePath('subtitle-browser', profile=root)))
'''
    profile, native = tmp_path / 'profile', tmp_path / 'native-abi'
    expected = str(native if legacy else profile / 'subtitle-browser')
    assert isolated(script, profile, native, 'legacy' if legacy else 'profile').strip() == expected
    assert isolated(script, profile, native, 'read').strip() == expected
    marker = json.loads((profile / runtime_paths.CONFIG).read_text())
    assert marker == (dict(schema=1, subtitle_abi='ce-f9', native_sha256=runtime_paths.CE_F9_SHA256)
                      if legacy else dict(schema=1, subtitle_abi='profile'))
    assert isolated(script, profile, native, 'profile').strip() == str(profile / 'subtitle-browser')
    assert isolated(script, profile, native, 'read').strip() == str(profile / 'subtitle-browser')


def test_frozen_original_control_proves_implicit_drift_and_unrevoked_configured_binding(tmp_path):
    source = original('addons/script.module.bobbi.core/lib/bobbi_core/runtime_paths.py')
    isolated(r'''
import sys, types
from pathlib import Path
space = {}; exec(compile(sys.argv[3], '<frozen-runtime-paths>', 'exec'), space)
base = Path(sys.argv[2]); active = [base/'A']
sys.modules['xbmcvfs'] = types.SimpleNamespace(translatePath=lambda _: str(active[0]))
path = space['ProfilePath']('search-admission')
assert str(path) == str(base/'A/search-admission')
active[0] = base/'B'
assert str(path) == str(base/'B/search-admission')
space['configure'](base/'A')
assert str(path) == str(base/'A/search-admission')  # still usable while B is current
''', tmp_path, source)


def test_frozen_original_publisher_control_commits_after_observed_switch(tmp_path):
    old_paths = original('addons/script.module.bobbi.core/lib/bobbi_core/runtime_paths.py')
    old_candidates = original('addons/script.module.bobbi.core/lib/bobbi_core/subtitle_candidates.py')
    isolated(r'''
import sys, types, os
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import bobbi_core
p = types.ModuleType('bobbi_core.runtime_paths')
exec(compile(sys.argv[3], '<frozen-runtime-paths>', 'exec'), p.__dict__)
sys.modules[p.__name__] = p
space = {}; exec(compile(sys.argv[4], '<frozen-subtitle-candidates>', 'exec'), space)
revoked = []; original_sync = os.fsync
def switch(fd):
    original_sync(fd); revoked.append(True)
os.fsync = switch
result = space['publish'](b'late original publication', '.srt', Path(sys.argv[2])/'A')
assert revoked and Path(result['path']).is_file()
assert not (Path(sys.argv[2])/'B').exists()
''', tmp_path, old_paths, old_candidates)


@pytest.mark.parametrize('prefixed', [False, True], ids=['fixed', 'pre-fix-control'])
def test_search_delayed_positive_cannot_restore_observed_revocation(prefixed):
    entered, release = Event(), Event()
    main = get_ident()
    def current():
        if get_ident() == main:
            return False
        entered.set()
        assert release.wait(2)
        return True
    pump = ProgressiveSearch(SourceListSession({}, lambda rows: rows),
                             lambda _: None, lambda rows: rows, current=current)
    if prefixed:
        # Exact assignment from the first migration, before independent review.
        def old_current():
            if not pump._profile_revoked:
                pump._profile_revoked = pump.current() is not True
            return not pump._profile_revoked
        pump.scope_current = old_current
    results = []
    worker = Thread(target=lambda: results.append(pump.scope_current()))
    worker.start()
    try:
        assert entered.wait(2)
        assert pump.scope_current() is False
        release.set()
        worker.join(2)
        assert not worker.is_alive()
        assert results == [prefixed]
        assert pump._profile_revoked is not prefixed
    finally:
        release.set()
        worker.join(2)


@pytest.mark.parametrize('prefixed', [False, True], ids=['fixed', 'pre-fix-control'])
def test_preparation_rechecks_profile_inside_real_account_cas(tmp_path, prefixed):
    from test_accounts import logged_in
    accounts, scope = logged_in(tmp_path)
    observed, active = Event(), [True]
    def current():
        result = active[0]
        observed.set()
        return result
    lease = Lease(accounts, scope, current=current)
    if prefixed:
        def old_commit(operation):
            lease.check()
            return accounts.run_if_current(scope, operation)
        lease.commit = old_commit
    committed, errors = [], []
    def commit():
        try:
            lease.commit(lambda: committed.append('publication'))
        except RuntimeError as error:
            errors.append(str(error))
    with accounts.lock:
        worker = Thread(target=commit)
        worker.start()
        assert observed.wait(2)
        active[0] = False
    worker.join(2)
    assert not worker.is_alive()
    assert committed == (['publication'] if prefixed else [])
    assert bool(errors) is not prefixed


@pytest.mark.parametrize('failure', ['construct', 'start'])
def test_coordinator_start_failure_closes_owned_resources_once(monkeypatch, failure):
    import bobbi_core.progressive_search as module
    closed = []
    def broken(*args, **kwargs):
        if failure == 'construct':
            raise RuntimeError('construct')
        return SimpleNamespace(start=lambda: (_ for _ in ()).throw(RuntimeError('start')))
    monkeypatch.setattr(module, 'Thread', broken)
    pump = module.ProgressiveSearch(SourceListSession({}, lambda rows: rows),
        lambda _: None, lambda rows: rows, on_close=lambda: closed.append(True))
    with pytest.raises(RuntimeError):
        pump.start()
    pump.cancel(); pump.cancel()
    assert closed == [True] and pump._pending == 0


def test_coordinator_closes_only_after_cancel_and_actual_provider_drain(tmp_path):
    entered, release, closed = Event(), Event(), []
    def provider():
        entered.set()
        assert release.wait(3)
        return []
    pump = ProgressiveSearch(SourceListSession({}, lambda rows: rows),
        lambda manager: manager.submit_task('Held', 'held', provider), lambda rows: rows,
        admission=lambda: try_acquire(tmp_path / 'admission'), on_close=lambda: closed.append(True))
    pump.start()
    try:
        assert entered.wait(2)
        pump.cancel(); pump.thread.join(2)
        assert not pump.thread.is_alive() and closed == []
    finally:
        release.set()
    for future in pump._futures:
        future.result(timeout=2)
    deadline = time.monotonic() + 2
    while not closed and time.monotonic() < deadline:
        time.sleep(.01)
    pump.cancel()
    assert closed == [True] and pump._pending == 0


@pytest.mark.parametrize('prefixed', [False, True], ids=['fixed', 'pre-fix-control'])
def test_concurrent_deadline_and_cancel_have_no_executor_lifecycle_lock_cycle(tmp_path, prefixed):
    result = isolated(r'''
import json, os, sys
from pathlib import Path
from threading import Event, Thread, current_thread
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, sys.argv[1])
from bobbi_core import progressive_search as product
from bobbi_core.source_list_session import SourceListSession
from bobbi_core.search_admission import try_acquire
callback, cancel_shutdown, entered, release, drained = Event(), Event(), Event(), Event(), Event()
closed = []
def on_close():
    closed.append(True)
    drained.set()
def admission():
    lease = try_acquire(Path(sys.argv[2]) / 'admission')
    original_release = lease.release
    def release_lease(future=None):
        if future is not None and future.cancelled() and current_thread().name == 'BobbiSourceCoordinator':
            callback.set()
            assert cancel_shutdown.wait(3)
        original_release(future)
    lease.release = release_lease
    return lease
class ObservedPool(ThreadPoolExecutor):
    def shutdown(self, *args, **options):
        if current_thread().name == 'ReviewCancel':
            cancel_shutdown.set()
        return super().shutdown(*args, **options)
product.ThreadPoolExecutor = ObservedPool
def active():
    entered.set()
    assert release.wait(4)
    return []
def setup(manager):
    manager.submit_task('active', 'fixture', active)
    assert entered.wait(2)
    manager.submit_task('queued', 'fixture', lambda: [])
manager = product.ProgressiveSearch(SourceListSession({}, lambda rows: rows), setup, lambda rows: rows,
    workers=1, budget=1, admission=admission, on_close=on_close)
if sys.argv[3] == 'True':
    def old_cancel():
        with manager._lifecycle:
            manager._closed = True
            manager.cancelled.set()
            manager.session.stop_queries()
            manager._stop_pool()
            manager._close_if_drained()
    manager.cancel = old_cancel
manager.start()
assert callback.wait(3)
closer = Thread(target=manager.cancel, name='ReviewCancel', daemon=True)
closer.start()
assert cancel_shutdown.wait(2)
release.set()
closer.join(.5); manager.thread.join(.5)
if sys.argv[3] != 'True':
    assert drained.wait(2), (closed, manager._pending)
print(json.dumps(dict(deadlocked=closer.is_alive() and manager.thread.is_alive(),
                      closed=closed, pending=manager._pending)), flush=True)
# The negative control intentionally deadlocks; don't block executor atexit.
os._exit(0)
''', tmp_path, prefixed)
    observation = json.loads(result)
    assert observation['deadlocked'] is prefixed, observation
    if not prefixed:
        assert observation['closed'] == [True] and observation['pending'] == 0


def test_configuring_second_profile_never_rebinds_existing_concrete_path(profiles):
    runtime_paths.configure(profiles.root)
    path = runtime_paths.ProfilePath('subtitle-browser', profile=profiles.root)
    runtime_paths.configure(profiles.other / 'plugin.video.bobbi')
    assert str(path) == str(profiles.root / 'subtitle-browser')
    profiles.revoke()
    assert str(path) == str(profiles.root / 'subtitle-browser')  # paths are not authorization


@pytest.mark.parametrize('kind', ['candidate', 'prepared', 'assrt-cache', 'descriptor'])
def test_switch_during_fsync_cannot_publish_or_move_old_async_write(profiles, monkeypatch, kind):
    import os
    root = profiles.root
    runtime_paths.configure(root)
    original_descriptor = (root / runtime_paths.CONFIG).read_bytes()
    provider = subtitle_candidates.AssrtCandidates(None, root / 'subtitle-cache283',
        current=profiles.binding.is_current)
    raw = b'bounded immutable subtitle'
    record = dict(state='READY_NOT_VISUAL_PROOF', extension='.srt', subtitle_sha256=hashlib.sha256(raw).hexdigest())
    real_sync = os.fsync
    def switch(fd):
        real_sync(fd)
        profiles.revoke()
    monkeypatch.setattr(os, 'fsync', switch)
    with pytest.raises((ValueError, subtitle_candidates.LookupStopped), match='PROFILE_CHANGED'):
        if kind == 'candidate':
            subtitle_candidates.publish(raw, '.srt', root / 'subtitle-browser', current=profiles.binding.is_current)
        elif kind == 'prepared':
            subtitle_export.export(SimpleNamespace(_read=lambda _: raw), record,
                root / 'subtitle-browser', current=profiles.binding.is_current)
        elif kind == 'assrt-cache':
            provider.save('candidates.json', ['late'])
        else:
            runtime_paths.configure(root, current=profiles.binding.is_current)
    assert not profiles.other.exists()
    assert list((root / 'subtitle-browser').iterdir()) == []
    assert list((root / 'subtitle-cache283').iterdir()) == []
    assert (root / runtime_paths.CONFIG).read_bytes() == original_descriptor
    assert not list(root.glob('.runtime-paths-*'))


def test_captured_paths_still_reject_symlink_replacement_before_io(profiles, monkeypatch):
    root = profiles.root
    runtime_paths.configure(root)
    path = runtime_paths.ProfilePath('subtitle-browser', profile=root)
    real = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda item: item == root or real(item))
    for operation in (lambda: str(path), lambda: try_acquire(root / 'search-admission'),
                      lambda: subtitle_candidates.publish(b'text', '.srt', root / 'subtitle-browser')):
        with pytest.raises(ValueError):
            operation()
    assert not (root / 'search-admission').exists()


def test_host_binding_does_not_reanimate_subtitle_factory_export_or_lease(profiles):
    host = Host(profiles.binding.root(), plugin_root=profiles.root,
        subtitle_root=profiles.root / 'subtitle-browser', profile_current=profiles.binding.is_current)
    provider = host.subtitle_candidates()
    assert provider.directory == profiles.root / 'subtitle-cache283'
    assert provider.token_file == profiles.root / 'assrt-token'
    assert provider.preparation_root == profiles.root / 'preparation'
    lease = Lease(SimpleNamespace(is_current=lambda _: True, run_if_current=lambda _, fn: fn()),
                  {}, current=host.check_profile)
    assert lease.valid()
    profiles.revoke()
    assert not lease.valid() and lease.revoked.is_set()
    for operation in (host.subtitle_candidates, lambda: provider.save('quota.json', []),
                      lambda: lease.commit(lambda: pytest.fail('revoked commit'))):
        with pytest.raises((ValueError, RuntimeError)):
            operation()
    assert host.stopping.is_set() and not profiles.other.exists()


def row(key='a'):
    return SimpleNamespace(title=key, infoHash=key * 40)


@pytest.mark.parametrize('phase', ['before-admission', 'final', 'partial', 'transform', 'callback-error'])
def test_search_revocation_suppresses_late_rows_cache_retry_but_drains_original_lock(profiles, phase):
    entered, release = Event(), Event()
    writes, errors = [], []
    session = SourceListSession({}, lambda rows: rows)
    class Cache:
        def get(self, *args): return None
        def put(self, *args): writes.append(args)
    def current():
        if errors:
            raise OSError('private-context-not-for-output')
        return profiles.binding.is_current()
    def provider(publish):
        if phase == 'partial':
            assert publish([row()])
        entered.set()
        assert release.wait(3)
        return [row('b')]
    def transform(rows):
        if phase == 'transform':
            profiles.revoke()
        return rows
    def setup(manager):
        manager.submit_task('fixture', 'jackett', provider, _progressive=True)
    pump = ProgressiveSearch(session, setup, transform, budget=2, current=current,
        admission=lambda: try_acquire(profiles.root / 'search-admission'), result_cache=Cache())
    if phase == 'before-admission':
        profiles.revoke()
    try:
        pump.start()
        if phase != 'before-admission':
            assert entered.wait(1)
            if phase != 'transform':
                if phase == 'callback-error': errors.append(True)
                else: profiles.revoke()
                assert pump.scope_cancelled()
                pump.thread.join(1)
                assert not pump.thread.is_alive()
                assert try_acquire(profiles.root / 'search-admission') is None
            release.set()
        pump.thread.join(2)
        assert not pump.thread.is_alive()
        for future in pump._futures:
            future.result(2)
        assert not writes
        assert [value.title for _, value in session.snapshot()['entries']] == (['a'] if phase == 'partial' else [])
        assert not pump.retry_failed()
        assert not profiles.other.exists()
        if phase == 'before-admission':
            assert not profiles.root.exists() and not entered.is_set()
        else:
            lease = try_acquire(profiles.root / 'search-admission')
            assert lease is not None
            lease.release()
    finally:
        release.set()
        pump.cancel()


def test_http_refill_reuses_captured_slots_and_never_opens_profile_b(profiles, monkeypatch):
    spec = importlib.util.spec_from_file_location('profile_http',
        ROOT / 'addons/plugin.video.bobbi/lib/clients/portable_http.py')
    http = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(http)
    monkeypatch.setattr(http, 'WORKERS', 1)
    requests = []
    class Response:
        status_code, headers = 200, {}
        def __enter__(self): return self
        def __exit__(self, *args): profiles.revoke()
        def iter_content(self, size): yield b'{}'
    session = SimpleNamespace(get=lambda url, **kw: requests.append(url) or Response())
    events = list(http.iter_events(session, ['https://fixture.invalid/first', 'https://fixture.invalid/late'],
        time.monotonic() + 2, lambda: not profiles.binding.is_current(), 'json', 1024,
        slot_factory=partial(http._slot, directory=profiles.root / 'http-admission',
                             current=profiles.binding.is_current)))
    assert requests == ['https://fixture.invalid/first']
    assert not any(event[1] == 'succeeded' for event in events)
    assert not profiles.other.exists()
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        http._slot('later', directory=profiles.root / 'http-admission', current=profiles.binding.is_current)
    lease = try_acquire(profiles.root / 'http-admission/0')
    assert lease is not None
    lease.release()


def test_jackett_internal_query_cache_rechecks_profile_after_parse(chain, profiles):
    from test_provider_streaming import client, rss, Response
    writes, published = [], []
    class Cache:
        def get(self, *args): return None
        def put(self, *args): writes.append(args)
    value = client(chain, {'https://fixture.invalid/one': Response(rss())})
    def parse(response):
        profiles.revoke()
        return [row()]
    value.parse_response = parse
    value._search_cinema('Fixture', 'movies', 1, 1, None, None, 2020, '',
        deadline=time.monotonic() + 2, cancelled=lambda: not profiles.binding.is_current(),
        publish=published.append, query_cache=Cache(),
        slot_factory=partial(chain.http._slot.func, directory=profiles.root / 'http-admission',
                             current=profiles.binding.is_current))
    assert not writes and not published and not profiles.other.exists()


def test_animegarden_internal_query_cache_rechecks_profile_after_parse(chain, profiles, monkeypatch):
    chain.package('lib.cinema', ROOT / 'addons/plugin.video.bobbi/lib/cinema')
    chain.stub('lib.cinema._shared')
    module = chain.load('lib.clients.animegarden_provider',
        ROOT / 'addons/plugin.video.bobbi/lib/clients/animegarden_provider.py')
    from bobbi_core.search_completion import SearchResults, SearchCompletion
    writes, published = [], []
    class Cache:
        def get(self, *args): return None
        def put(self, *args): writes.append(args)
    def parse(raw):
        profiles.revoke()
        return [row()], True, 0
    monkeypatch.setattr(module, 'parse_page', parse)
    def fetch(session, urls, **options):
        response = SimpleNamespace(content=b'{}', status_code=200, _bobbi_query_url=urls[0])
        options['on_response'](response)
        return SearchResults([response], SearchCompletion(1, succeeded=1))
    monkeypatch.setattr(chain.fanout, 'fetch_independent', fetch)
    result = module.find_sources({'tmdb_id': 1}, 'tv', [('en', 'Fixture')], time.monotonic() + 2,
        Event(), query_cache=Cache(), publish=published.append, current=profiles.binding.is_current,
        proxy_path=profiles.root / 'search-network.json', slot_factory=lambda _: None)
    assert not result and not writes and not published and not profiles.other.exists()


@pytest.mark.parametrize('stage', ['search', 'select', 'download', 'confirm'])
def test_manual_ui_keeps_original_profile_and_never_opens_browser_after_switch(profiles, stage):
    from test_manual_subtitle_ui import ui, RPC, Dialogs, Provider, Progress, NoLock
    root = profiles.root / 'subtitle-browser'
    root.mkdir(parents=True)
    dialogs, provider, calls = Dialogs(), Provider(None), []
    if stage == 'search': provider.onsearch = profiles.revoke
    elif stage == 'select': dialogs.onselect = profiles.revoke
    elif stage == 'download': provider.ondownload = profiles.revoke
    else: dialogs.onyes = profiles.revoke
    result = ui.run(RPC(), dialogs, Progress, SimpleNamespace(abortRequested=lambda: False),
        calls.append, lambda _: provider, profiles.root / 'manual-state', root=root,
        lock_factory=NoLock, current=profiles.binding.is_current)
    assert result in ('cancelled', 'downloaded') and not calls
    assert not profiles.other.exists()
    if stage in ('search', 'select'):
        assert provider.downloads == 0 and list(root.iterdir()) == []


def test_manual_entry_captures_own_state_and_export_root_before_ui(profiles, monkeypatch):
    from bobbi_platform import paths
    from bobbi_platform import runtime
    import types
    monkeypatch.setattr(paths, '_translated_profile_root',
        lambda addon: profiles.root.parent.parent / profiles.active[0] / addon)
    runtime_paths.configure(profiles.root)
    seen, captures = [], []
    def absent_runtime(path):
        captures.append(path)
        raise OSError('initial runtime unavailable')
    monkeypatch.setattr(runtime, 'bind_call', absent_runtime)
    def run(*args, **kwargs):
        seen.append((args[6], str(kwargs['root'])))
        assert kwargs['current']()
        monkeypatch.setattr(runtime, 'bind_call', lambda path: pytest.fail('late runtime capture'))
        with pytest.raises(OSError, match='RUNTIME_NOT_CAPTURED'):
            kwargs['account_reader']()
        profiles.active[0] = 'B'
        assert not kwargs['current']()
        profiles.active[0] = 'A'
        assert not kwargs['current']()
        return 'cancelled'
    fixtures = {
        'xbmc': dict(Player=lambda: None, Monitor=lambda: None, executebuiltin=lambda _: None),
        'xbmcaddon': dict(Addon=lambda: SimpleNamespace(getSetting=lambda _: '')),
        'xbmcgui': dict(Dialog=lambda: None, DialogProgress=lambda: None),
        'resources.lib.provider': dict(Provider=lambda *a, **kw: None),
        'resources.lib.ui': dict(run=run),
        'bobbi_platform.standard_subtitle_ui': dict(offer=lambda *a: False),
    }
    for name, values in fixtures.items():
        module = types.ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location('manual_entry_profile',
        ROOT / 'addons/script.bobbi.opensubtitles/script.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 'cancelled'
    assert seen == [(profiles.root.parent / 'script.bobbi.opensubtitles', str(profiles.root / 'subtitle-browser'))]
    assert captures == [profiles.binding.root() / 'runtime.json']
    assert not profiles.other.exists()

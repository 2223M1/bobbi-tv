#!/usr/bin/env python3
"""Exercise CE recovery against Kodi's documented invocation ownership semantics.

Product Python modules are loaded from --repo. Kodi C++ IO is represented by a
small explicit model: path-based RunScript carries no addon identity and is not
registered in ServiceAddonManager; disabling an addon stops its tracked service.
Those semantics are sourced in PRIMARY-SOURCES.json, rather than invented as a
product fix. Native import probes run in isolated subprocesses. Standard owner
readiness and exclusion use actual Host/Runtime modules, loopback IO and OS locks.
No device, account, repository write, or external network operation is performed.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from types import ModuleType, SimpleNamespace


PROVIDER = 'plugin.video.bobbi'
REFERENCE = 'c8de17ae9dabbe0f37753e1751b1d88107311316'


def bootstrap_paths(repo):
    paths = [repo / 'addons' / PROVIDER]
    paths.extend(sorted((repo / 'addons').glob('*/lib')))
    for path in reversed(paths):
        sys.path.insert(0, str(path))


class Dummy:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return lambda *args, **kwargs: ''


def kodi_import_io(repo, root, addon_id):
    """Only Kodi extension modules are doubled for the native import probe."""
    calls = []
    xbmc = ModuleType('xbmc')
    xbmc.LOGINFO, xbmc.LOGERROR, xbmc.LOGDEBUG = 1, 2, 0
    xbmc.PLAYLIST_VIDEO = 1
    xbmc.Monitor = xbmc.Player = xbmc.PlayList = Dummy
    xbmc.log = lambda *args: None
    xbmc.getCondVisibility = lambda *_: False
    xbmc.getInfoLabel = lambda *_: ''
    xbmc.executebuiltin = lambda *args: None
    xbmcgui = ModuleType('xbmcgui')
    xbmcgui.__getattr__ = lambda name: Dummy
    xbmcplugin = ModuleType('xbmcplugin')
    xbmcplugin.__getattr__ = lambda name: lambda *args, **kwargs: None
    xbmcvfs = ModuleType('xbmcvfs')
    xbmcvfs.translatePath = lambda path: str(root / 'profile') if path.startswith('special:') else path
    xbmcvfs.File = Dummy
    xbmcvfs.delete = lambda *_: True
    xbmcvfs.listdir = lambda *_: ([], [])
    xbmcvfs.__getattr__ = lambda name: lambda *args, **kwargs: False
    xbmcaddon = ModuleType('xbmcaddon')

    class Addon:
        def __init__(self, explicit=None):
            self.id = explicit or addon_id
            calls.append({'explicit': explicit, 'resolved': self.id})
            if not self.id:
                raise RuntimeError("No valid addon id could be obtained. None was passed and the script wasn't executed in a normal Kodi manner.")

        def getAddonInfo(self, key):
            return {'id': self.id, 'profile': str(root / 'profile'),
                    'path': str(repo / 'addons' / self.id), 'version': '0.1.10',
                    'name': 'Bobbi', 'icon': '', 'fanart': ''}.get(key, '')

        def getSetting(self, key):
            return ''

        def getLocalizedString(self, key):
            return str(key)

    xbmcaddon.Addon = Addon
    for module in (xbmc, xbmcgui, xbmcplugin, xbmcvfs, xbmcaddon):
        sys.modules[module.__name__] = module
    return calls


def native_import(repo, addon_id):
    bootstrap_paths(repo)
    with tempfile.TemporaryDirectory(prefix='bobbi-pr3-native-context-', ignore_cleanup_errors=True) as temporary:
        calls = kodi_import_io(repo, Path(temporary), addon_id)
        try:
            # This is the real import performed by portable_runtime.main when
            # the native contract is present; do not replace its dependencies.
            module = importlib.import_module('lib.services.background_service')
            return {'imported': True, 'module': str(Path(module.__file__).relative_to(repo)),
                    'addon_calls': calls}
        except BaseException as error:
            frames = [dict(file=str(Path(frame.filename).relative_to(repo)), line=frame.lineno,
                           function=frame.name)
                      for frame in traceback.extract_tb(error.__traceback__)
                      if str(frame.filename).startswith(str(repo) + '/')]
            return {'imported': False, 'exception': type(error).__name__,
                    'error': str(error), 'addon_calls': calls, 'product_frames': frames}


def native_subprocess(repo, addon_id):
    command = [sys.executable, str(Path(__file__).resolve()), '--repo', str(repo),
               '--native-import', addon_id or '']
    proc = subprocess.run(command, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        raise RuntimeError('Native import probe harness failed: ' + proc.stderr)
    return json.loads(proc.stdout)


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def wait(self, seconds):
        self.now += max(1.0, seconds)
        time.sleep(.005)
        return False


def probe_native_recovery(repo, ui, runtime, directory):
    original_call, original_profile, original_time, original_rpc = runtime.call, ui.profile, ui.time, ui.rpc
    state, commands, events = {'ready': False, 'enabled': True}, [], []
    clock = Clock()
    ui.profile = lambda **_: directory / 'runtime.json'
    ui.time = SimpleNamespace(monotonic=clock.monotonic)

    def call(*args, **kwargs):
        if not state['ready']:
            raise OSError('not running')
        return {'boot_id': 'review-native-owner', 'desired': None}

    def builtin(command, *args):
        commands.append(command)
        parameter = command[len('RunScript('):-1] if command.startswith('RunScript(') else ''
        # AddonBuiltins.cpp resolves only an addon id into an AddonPtr. A path
        # is passed to ExecuteAsync with a null AddonPtr, even inside addons/.
        # RunScript(PROVIDER) chooses the addon's main entrypoint, not its
        # service extension. Do not make that naive edit pass this oracle.
        if parameter == PROVIDER:
            events.append('runs_primary_plugin_entrypoint_not_service')
            return
        state['native_import'] = native_subprocess(repo, None)
        state['ready'] = state['native_import']['imported']

    def rpc(method, params):
        name = params.get('addonid')
        if method == 'Settings.GetSettingValue':
            return {'value': 'skin.estuary'}
        if method == 'Addons.GetAddonDetails':
            return {'addon': {'enabled': state['enabled'] if name == PROVIDER else False,
                              'version': '1.0.0'}}
        if method == 'Addons.GetAddons':
            return {'addons': [{'addonid': PROVIDER, 'enabled': state['enabled'],
                                'version': '1.0.0'}]}
        if method == 'Addons.SetAddonEnabled':
            if name == PROVIDER and params['enabled'] != state['enabled']:
                state['enabled'] = params['enabled']
                if not state['enabled']:
                    state['ready'] = False
                    events.append('managed_disable')
                else:
                    # The supported IO seam also permits a real managed
                    # disable/enable restart to satisfy the intended contract.
                    events.append('managed_enable_service_context')
                    state['native_import'] = native_subprocess(repo, PROVIDER)
                    state['ready'] = state['native_import']['imported']
            return 'OK'
        raise AssertionError(method)

    runtime.call = call
    ui.rpc = rpc
    host = ui.KodiHost.__new__(ui.KodiHost)
    host.xbmc = SimpleNamespace(executebuiltin=builtin,
                               Player=lambda: SimpleNamespace(isPlaying=lambda: False))
    host.monitor = SimpleNamespace(waitForAbort=clock.wait)
    try:
        try:
            host.ensure_running()
            error = None
        except (OSError, ValueError, RuntimeError) as exception:
            error = str(exception)
        return dict(id='RECOVERY-NATIVE-ADDON-CONTEXT', passed=state['ready'] and error is None,
                    expected='enabled-but-not-running recovery starts the real native import chain with addon identity',
                    actual=dict(commands=commands, events=events, error=error, **state))
    finally:
        runtime.call, ui.profile, ui.time, ui.rpc = original_call, original_profile, original_time, original_rpc
        host.close()


def probe_standard_stop(repo, ui, runtime, directory, recovered):
    from bobbi_platform.host import Host
    original_profile, original_runtime_profile, original_time, original_rpc = ui.profile, runtime.profile, ui.time, ui.rpc
    path = directory / 'runtime.json'
    ui.profile = runtime.profile = lambda **_: path
    clock = Clock()
    ui.time = SimpleNamespace(monotonic=clock.monotonic)
    state = {'enabled': True, 'tracked': False, 'started': False}
    commands, events = [], []
    servers, workers, releases = [], [], []

    def start(tracked):
        server = Host(directory)
        server.start()
        server.bind_owner(lambda body: {'adapter': 'standard', 'desired': None})
        release = threading.Event()

        def pump():
            while not release.wait(.003):
                server.tick()

        worker = threading.Thread(target=pump)
        worker.start()
        servers.append(server)
        workers.append(worker)
        releases.append(release)
        state.update(tracked=tracked, started=True)
        events.append('started_tracked' if tracked else 'started_untracked_path')

    def stop_tracked():
        if state['tracked'] and state['started']:
            releases[-1].set()
            workers[-1].join(2)
            servers[-1].close()
            state['started'] = False
            events.append('tracked_service_stopped')
        elif state['started']:
            events.append('disable_cannot_find_manual_handle')

    def rpc(method, params):
        name = params.get('addonid')
        if method == 'Settings.GetSettingValue':
            return {'value': 'skin.estuary'}
        if method == 'Addons.GetAddonDetails':
            return {'addon': {'enabled': state['enabled'] if name == PROVIDER else False, 'version': '1.0.0'}}
        if method == 'Addons.SetAddonEnabled':
            if name == PROVIDER:
                state['enabled'] = params['enabled']
                if not params['enabled']:
                    stop_tracked()
                elif not state['started']:
                    start(True)
            return 'OK'
        raise AssertionError(method)

    def builtin(command, *args):
        commands.append(command)
        if command.startswith('RunScript('):
            # CServiceAddonManager::Start owns registration; arbitrary RunScript
            # handles are absent from its m_services map.
            start(False)
        elif command.startswith('StopScript('):
            releases[-1].set()
            workers[-1].join(2)
            servers[-1].close()
            state['started'] = False
        else:
            raise AssertionError(command)

    ui.rpc = rpc
    host = ui.KodiHost.__new__(ui.KodiHost)
    host.xbmc = SimpleNamespace(executebuiltin=builtin, Player=lambda: SimpleNamespace(isPlaying=lambda: False))
    host.monitor = SimpleNamespace(waitForAbort=clock.wait)
    try:
        if not recovered:
            start(True)
        host.ensure_running()
        ready_before_disable = state['started']
        try:
            host.quiesce()
            error = None
        except (OSError, ValueError, RuntimeError) as exception:
            error = str(exception)
        return dict(id='RECOVERY-STANDARD-MANAGED-STOP' if recovered else 'CONTROL-STANDARD-MANAGED-STOP',
                    passed=error is None and not state['started'],
                    expected='a ready recovered host can be stopped through the actual installer path before another generation',
                    actual=dict(commands=commands, events=events, error=error,
                                ready_before_disable=ready_before_disable,
                                marker_after_disable=path.exists(), **state))
    finally:
        host.close()
        for release in releases:
            release.set()
        for worker in workers:
            worker.join(2)
        for server in servers:
            server.close()
        ui.profile, runtime.profile, ui.time, ui.rpc = original_profile, original_runtime_profile, original_time, original_rpc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--native-import', default=None)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.native_import is not None:
        print(json.dumps(native_import(repo, args.native_import or None)))
        return 0
    bootstrap_paths(repo)
    from bobbi_platform import ce_install_ui as ui, runtime
    with tempfile.TemporaryDirectory(prefix='bobbi-pr3-installer-') as temporary:
        root = Path(temporary)
        tests = [probe_native_recovery(repo, ui, runtime, root / 'native')]
        control = native_subprocess(repo, PROVIDER)
        tests.append(dict(id='CONTROL-NATIVE-REGISTERED-CONTEXT', passed=control['imported'],
                          expected='the same real native import chain succeeds with normal Kodi addon context', actual=control))
        for recovered in (True, False):
            directory = root / ('manual-standard' if recovered else 'managed-standard')
            directory.mkdir()
            tests.append(probe_standard_stop(repo, ui, runtime, directory, recovered))
    sources = [
        'addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py',
        'addons/script.module.bobbi.platform/lib/bobbi_platform/host.py',
        'addons/script.module.bobbi.platform/lib/bobbi_platform/runtime.py',
        'addons/script.module.bobbi.platform/lib/bobbi_platform/instance_lock.py',
        'addons/plugin.video.bobbi/service.py',
        'addons/plugin.video.bobbi/lib/portable_runtime.py',
        'addons/plugin.video.bobbi/lib/services/background_service.py',
        'addons/plugin.video.bobbi/lib/jacktook/utils.py',
        'addons/plugin.video.bobbi/lib/utils/kodi/utils.py',
        'tests/test_ce2012_recovery_ui.py',
    ]
    result = dict(reference_head=REFERENCE,
                  scope='Actual candidate Python imports and Host/Runtime with primary-source-grounded Kodi invocation IO model; no device certification',
                  count=len(tests), passed=sum(row['passed'] for row in tests),
                  failed=sum(not row['passed'] for row in tests), tests=tests,
                  sources=[dict(path=path, sha256=hashlib.sha256((repo/path).read_bytes()).hexdigest()) for path in sources])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())

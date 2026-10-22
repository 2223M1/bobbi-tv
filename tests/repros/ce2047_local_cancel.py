"""One CE2047 local-Back/IPC-recovery interleaving, without Kodi/media IO.

Run with --repo /path/to/bobbi-tv, or set BOBBI_REPO.
Actual product methods are AST-extracted unchanged. Only IO/optional features
and the post-dispatch monitor are doubles. This proves attempted successful
plugin dispatch after local cancellation, not media playback or BT submission.
"""
import argparse
import ast
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Event
from time import monotonic
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from uuid import uuid4

parser = argparse.ArgumentParser()
parser.add_argument('--repo', type=Path, default=Path(os.environ.get('BOBBI_REPO', '.')))
parser.add_argument('--expect-dispatches', type=int, choices=(0, 1), default=1,
                    help='1 reproduces CE2047 defect; 0 asserts cancellation blocked dispatch')
args = parser.parse_args()
root = args.repo.resolve()
audit_commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                       text=True).strip()
sys.path.insert(0, str(root / 'addons/script.module.bobbi.core/lib'))
sys.path.insert(0, str(root / 'addons/script.module.bobbi.platform/lib'))
from bobbi_core.playback_owner import PlaybackOwner
from bobbi_core import playback_request


def extracted_class(path, original, name, methods, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    source = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == original)
    nodes = [deepcopy(n) for n in source.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    assert {n.name for n in nodes} == set(methods)
    cls = ast.ClassDef(name=name, bases=[], keywords=[], body=nodes, decorator_list=[])
    tree = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace[name]


def module(name):
    value = ModuleType(name)
    value.__path__ = []
    sys.modules[name] = value
    return value


rid, info_hash = 'a' * 32, 'b' * 40
owner = PlaybackOwner(boot_id='c' * 32)
owner.select(owner.boot_id, owner.epoch, rid, 'bt:' + info_hash)
initial = owner.snapshot()
calls, events, logs, players, props, dispatches = [], [], [], [], {}, []
reads = 0
inside_back = False
injected = False


def rpc(message, **kwargs):
    global reads, inside_back, injected
    operation = message['operation']
    calls.append(operation)
    if operation == 'snapshot':
        reads += 1
        if inside_back:
            events.append('back_ownership_snapshot_unavailable')
            raise ConnectionResetError('fixture IPC unavailable during Back ownership check')
        if reads == 4 and not injected:
            # doModal initial read, pre-provider guard, post-provider guard,
            # then _activate_playback_session's first read is now outstanding.
            injected = True
            events.append('Back_during_player_activation_snapshot')
            inside_back = True
            try:
                window.onAction(SimpleNamespace(getId=lambda: 10))
            finally:
                inside_back = False
            events.append('activation_snapshot_transient_failure')
            raise ConnectionResetError('fixture original activation read also lost')
        return owner.snapshot()
    if operation == 'register_window':
        return dict(registered=owner.register_window(message['boot_id'], message['epoch'],
            message['request_id'], message['token'], message['role']))
    raise AssertionError('Unexpected mutating control operation: ' + operation)


playback_request.call = rpc
module('lib')
module('lib.cinema')
ipc = module('lib.cinema.playback_ipc')
ipc.call = rpc
sys.modules['lib.cinema.playback_request'] = playback_request
account = module('lib.cinema.preparation_client')
account.capture_account = lambda *a, **k: None
frontend_path = root / 'addons/plugin.video.bobbi/lib/cinema/frontend_contract.py'
spec = importlib.util.spec_from_file_location('lib.cinema.frontend_contract', frontend_path)
frontend = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = frontend
spec.loader.exec_module(frontend)


class ListItem:
    def __init__(self):
        self.path = ''
        self.properties = {}
    def setPath(self, value):
        self.path = value
    def setProperty(self, key, value):
        self.properties[key] = value


def dispatch(handle, success, item):
    dispatches.append(dict(success=success, local_cancel=window.cancel_event.is_set(),
        user_cancelled=window.user_cancelled,
        cancellation_property=props.get('bobbi_cinema_cancel'),
        active_session_property=props.get('bobbi_active_player_session'),
        target_is_bt_plugin=item.path.startswith('plugin://plugin.video.bobbi.torrent/')))
    events.append('setResolvedUrl_success_IO_double')


namespace = dict(re=re, uuid4=uuid4, Any=Any, Dict=Dict, Optional=Optional,
    xbmc=SimpleNamespace(LOGWARNING=2, LOGINFO=1), json=json, json_dumps=json.dumps,
    monotonic=monotonic, kodilog=lambda message, **kwargs: logs.append(message),
    set_property=lambda key, value: props.__setitem__(key, value),
    clear_property=lambda key: props.pop(key, None), close_busy_dialog=lambda: None,
    ACTIVE_PLAYER_SESSION_PROPERTY='bobbi_active_player_session',
    PLAYNEXT_ACTION_PROPERTY='bobbi_playnext_action', ADDON_HANDLE=1,
    make_listing=lambda data: ListItem(), setResolvedUrl=dispatch,
    notification=lambda *a, **k: events.append('notification'))
player_path = root / 'addons/plugin.video.bobbi/lib/native_player.py'
player_class = extracted_class(player_path, 'JacktookPLayer', 'ReviewPlayer',
    ['run', '_activate_playback_session', '_cinema_phase', 'play_video', 'clear_playback_properties'], namespace)


def factory(**callbacks):
    player = player_class()
    players.append(player)
    player._was_superseded = False
    player._resolution_answered = False
    player._cinema_cancel = callbacks['cancel_event']
    player.set_constants = lambda data: (setattr(player, 'data', data), setattr(player, 'url', data['url']))
    player._is_trakt_tracking_excluded = lambda: True
    player._check_volume = lambda: True
    player._handle_trakt_scrobble = lambda item: None
    player._handle_simkl_scrobble = lambda: None
    player.handle_subtitles = lambda item: None
    player.monitor = lambda: events.append('post_dispatch_monitor_double')
    player.run_error = lambda error: events.append('run_error:' + type(error).__name__)
    player._drain_nextep_queue = lambda: False
    return player


namespace['JacktookPLayer'] = factory
window_path = root / 'addons/plugin.video.bobbi/lib/gui/resolver_window.py'
window_class = extracted_class(window_path, 'ResolverWindow', 'ReviewWindow',
    ['doModal', 'resolve_source', 'onAction', '_owns_selection', '_handoff_rejected'], namespace)
window = window_class()
window.source = SimpleNamespace(isPack=False, debridType='')
window.item_information = dict(selection_policy='exact', request_id=rid,
    _selection_context=playback_request.context(initial, rid))
window._update_window_properties = lambda source: None
window.is_subtitle_download = False
window.local_subtitle_path = None
window._window_token = 'd' * 32
window.cancel_event = Event()
window.action_exitkeys_id = (10,)
window.user_cancelled = False
window.resolved = False
window.error_message = ''
window.resolution_answered = False
window.startup_failure_category = None
window.preparation_intent = None
window.player = None
window.show = lambda: events.append('show_loading_window')
window.close = lambda: events.append('close_loading_window')
data = dict(selection_policy='exact', request_id=rid, mode='movies',
    is_torrent=True, info_hash=info_hash,
    url='plugin://plugin.video.bobbi.torrent/play_magnet/?' + urlencode(dict(
        request_id=rid, selection_policy='exact', magnet='magnet:?xt=urn:btih:' + info_hash)))
window.resolve_single_source = lambda: setattr(window, 'playback_info', dict(data))
for name in ('handle_playback_started', 'handle_playback_error', 'update_progress',
             'handle_handoff_confirmed', 'handle_presentation_deferred'):
    setattr(window, name, lambda n=name: events.append(n))
window.doModal(False)
report = dict(audit_commit=audit_commit,
    method='Actual doModal/resolve_source/onAction/run/activation/play_video; IO doubles only',
    stage='Back during first player activation snapshot; Back ownership reads all fail; activation retry recovers',
    real_kodi_media_backend_io=False, dispatches=dispatches, operations=calls,
    events=events, logs=logs, owner_cancelled=owner.snapshot()['desired']['cancelled'],
    owner_current_request=owner.snapshot()['desired']['request_id'])
print(json.dumps(report, ensure_ascii=False, indent=2))
assert injected, report
assert len(dispatches) == args.expect_dispatches, report
if dispatches:
    assert dispatches[0]['success'] is True, report
    assert dispatches[0]['local_cancel'] is True and dispatches[0]['user_cancelled'] is True, report
    assert dispatches[0]['cancellation_property'] is None, report
    assert dispatches[0]['target_is_bt_plugin'] is True, report
assert not owner.snapshot()['desired']['cancelled'], report

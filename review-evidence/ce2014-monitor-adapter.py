#!/usr/bin/env python3
"""Load actual native monitor + owned_state and inject only transient IPC IO.

The selected/observed request comes from the actual PlaybackOwner policy.
Kodi, optional monitor work, clock and the IPC transport are explicit doubles.
No television connection, player command, source edit or service deployment.
"""
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from threading import Event
from types import MethodType, SimpleNamespace


def source_hash(path, root):
    value = path.read_bytes()
    return dict(path=path.relative_to(root).as_posix(), bytes=len(value),
                git_blob_sha1=hashlib.sha1(
                    ('blob ' + str(len(value)) + '\0').encode() + value).hexdigest(),
                sha256=hashlib.sha256(value).hexdigest())


def run_case(root, name):
    core = root / 'addons/script.module.bobbi.core/lib'
    sys.path.insert(0, str(core))
    for key in tuple(sys.modules):
        if key == 'bobbi_core' or key.startswith('bobbi_core.'):
            del sys.modules[key]
    request = importlib.import_module('bobbi_core.playback_request')
    owner_module = importlib.import_module('bobbi_core.playback_owner')
    sys.modules['lib.cinema.playback_request'] = request

    rid = 'a' * 32
    selection = 'transport:' + '1' * 64
    identity = selection + '|' + '2' * 64
    owner = owner_module.PlaybackOwner(boot_id='c' * 32)
    owner.select(owner.boot_id, owner.epoch, rid, selection)
    owner.bind_file(owner.boot_id, owner.epoch, rid, selection, identity)
    owner.claim_start(owner.boot_id, owner.epoch, rid, 'player_play')
    owner.observe_started(owner.boot_id, owner.epoch, rid, 'native-A', identity)
    if name == 'explicit_replacement':
        owner.select(owner.boot_id, owner.epoch, 'b' * 32, 'transport:' + '3' * 64)
    if name == 'explicit_cancel':
        owner.cancel(owner.boot_id, owner.epoch, rid)
    snapshot_before = owner.snapshot()

    clock, events, logs, calls = [100.0], [], [], []
    state = SimpleNamespace(playing=True)
    def transport(body, **kwargs):
        assert body == {'operation': 'snapshot'}, body
        calls.append(deepcopy(body))
        if name == 'transient_ipc_recovers' and len(calls) <= 3:
            clock[0] += .2
            raise OSError('LOCAL_IPC_TEMPORARILY_BUSY')
        if name == 'eof_after_player_check' and len(calls) == 1:
            # The while condition already observed a playing video. The real
            # same-instance EOF arrives before the now single authority read.
            state.playing = False
            assert owner.observe_terminal('native-A', 'NATURAL_EOF')
        return owner.snapshot()
    request.call = transport
    request.time = SimpleNamespace(monotonic=lambda: clock[0],
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    source = root / 'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    names = {'_owns_playback_session', '_matches_requested_playback', 'monitor',
             'wait_cinema_terminal'}
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names), 'Actual monitor interface changed: review adaptation required'
    env = dict(xbmc=SimpleNamespace(LOGWARNING=2, LOGINFO=1, LOGERROR=3),
               kodilog=lambda value, **kwargs: logs.append(str(value)),
               get_setting=lambda *args: False, TERMINAL_RECONCILIATION_SECONDS=3,
               monotonic=lambda: clock[0], loads=json.loads, get_property=lambda key: '',
               sleep=lambda ms: clock.__setitem__(0, clock[0] + ms / 1000))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), env)
    player = SimpleNamespace(data=dict(selection_policy='exact', mode='tv', cinema_continuity=True),
        playback_session_id=rid, _native_instance='native-A', _cinema_cancel=Event(),
        _was_superseded=False, _cinema_end=False, skip_intro_enabled=False,
        _terminal_reason='UNKNOWN',
        _owner_context=dict(boot_id=owner.boot_id, epoch=1, request_id=rid))
    for method in names:
        setattr(player, method, MethodType(env[method], player))
    player.isPlayingVideo = lambda: state.playing
    player._wait_for_video_start = lambda: True  # Trial starts after verified AV.
    player.handle_playback_start = lambda: True
    player._cinema_phase = lambda value: events.append('phase:' + value)
    player._record_started_history = lambda: events.append('started_history')
    player.update_playback_progress = lambda: events.append('progress_observed')
    player.check_cinema_stall = lambda: False
    player._consume_next_dialog_action = lambda: False
    for method in ('start_cinema_preparation', 'select_audio_stream', 'handle_subtitle_selection',
        '_apply_simkl_resume', '_apply_trakt_resume', '_apply_nuvio_resume',
        'check_cinema_subtitles', 'handle_trakt_pause_resume', 'check_cinema_continuity',
        'check_autoscrape_threshold', 'playback_close_dialogs', 'check_next_dialog',
        'check_skip_intro', 'check_stinger_notification', '_handle_next_dialog_action'):
        setattr(player, method, lambda: None)
    def finish_tick():
        events.append('monitor_tick')
        state.playing = False
        assert owner.observe_terminal('native-A', 'NATURAL_EOF')
    player._wait_monitor_tick = finish_tick
    player.queue_cinema_natural_end = lambda: events.append('continuation_boundary')
    player.handle_playback_stop = lambda: events.append('stop_bookkeeping')
    player.offer_terminal_actions = lambda: events.append('terminal_ui')
    player.kill_dialog = lambda: events.append('monitor_exception')
    player.clear_playback_properties = lambda: events.append('clear_playback_properties')
    player._release_playback_session = lambda: events.append('release_playback_session')

    player.monitor()
    snapshot_after = owner.snapshot()
    # This is an actual fresh owned_state read after the injected transport gap.
    try:
        request.owned_state(rid)
        authority_still_current = True
    except (OSError, RuntimeError, ValueError):
        authority_still_current = False
    actual = dict(transport_calls=len(calls), clock_elapsed=round(clock[0] - 100, 6),
        selected_request_before=snapshot_before['desired']['request_id'],
        selected_request_after=snapshot_after['desired']['request_id'],
        observed_request_after=(snapshot_after['observed'] or {}).get('request_id'),
        observed_instance_after=(snapshot_after['observed'] or {}).get('native_instance'),
        authority_terminal=(snapshot_after['terminal'] or {}).get('reason'),
        local_terminal=player._terminal_reason,
        authority_still_current=authority_still_current,
        playback_still_active=state.playing, was_superseded=player._was_superseded,
        local_cancelled=player._cinema_cancel.is_set(), events=events, logs=logs)
    if name == 'explicit_replacement':
        passed = (player._was_superseded and not authority_still_current
                  and 'progress_observed' not in events
                  and 'continuation_boundary' not in events
                  and 'clear_playback_properties' not in events)
        expected = 'Explicit new selection retires the old monitor without touching new owner UI'
    elif name == 'explicit_cancel':
        passed = (player._cinema_cancel.is_set() and not authority_still_current
                  and 'progress_observed' not in events
                  and 'continuation_boundary' not in events
                  and 'clear_playback_properties' not in events)
        expected = 'Explicit cancellation retires old monitoring without reviving continuation'
    elif name == 'eof_after_player_check':
        passed = (not player._was_superseded and authority_still_current
                  and player._terminal_reason == 'NATURAL_EOF'
                  and 'stop_bookkeeping' in events and 'continuation_boundary' in events
                  and 'monitor_exception' not in events)
        expected = 'A same-instance EOF between playing check and receipt reaches terminal reconciliation'
    else:
        passed = (not player._was_superseded and authority_still_current
                  and 'progress_observed' in events and 'stop_bookkeeping' in events
                  and 'continuation_boundary' in events and 'monitor_exception' not in events
                  and player._terminal_reason == 'NATURAL_EOF')
        expected = ('A recovered transient read gap preserves monitoring of the unchanged AV instance'
                    if name == 'transient_ipc_recovers' else
                    'A continuously current AV instance reaches normal terminal bookkeeping')
    return dict(id=name, passed=passed, expected=expected, actual=actual)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    output = Path(args.output).resolve()
    rows = []
    for name in ('transient_ipc_recovers', 'eof_after_player_check', 'continuously_current',
                 'explicit_replacement', 'explicit_cancel'):
        try:
            rows.append(run_case(root, name))
        except Exception as error:
            rows.append(dict(id=name, passed=False, harness_error=type(error).__name__,
                             message=str(error)))
    paths = ['addons/plugin.video.bobbi/lib/native_player.py',
             'addons/script.module.bobbi.core/lib/bobbi_core/playback_request.py',
             'addons/script.module.bobbi.core/lib/bobbi_core/playback_owner.py']
    result = dict(schema=1, scope='Actual production policies with explicit IPC/Kodi IO doubles; no device trial',
                  source=[source_hash(root / path, root) for path in paths],
                  count=len(rows), passed=sum(row['passed'] for row in rows),
                  failed=sum(not row['passed'] and 'harness_error' not in row for row in rows),
                  errors=sum('harness_error' in row for row in rows), tests=rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['errors'] else 1 if result['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

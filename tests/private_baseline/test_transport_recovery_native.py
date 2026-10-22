"""The real add-on run/activate/resolve/bind path for a same-file child."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import re
from threading import Event
from types import MethodType, SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest

from bobbi_core import preparation_client, playback_request as core_request
from lib.cinema import playback_request, playback_ipc
from lib.utils.player.transport_recovery import child_data, exact_context
from test_transport_recovery import recovery_case, proved, CAPSULE, prime


def methods(names, env):
    path = Path(__file__).resolve().parents[2] / 'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(row for row in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(row, ast.ClassDef) and row.name == 'JacktookPLayer')
    rows = [row for row in cls.body if isinstance(row, ast.FunctionDef) and row.name in names]
    assert len(rows) == len(names)
    exec(compile(ast.Module(body=rows, type_ignores=[]), str(path), 'exec'), env)
    return {name: env[name] for name in names}


@pytest.mark.parametrize('wrapped', [False, True])
def test_actual_run_preserves_parent_selection_and_canonical_file_identity_without_capsule_leaks(recovery_case, monkeypatch, wrapped):
    case = recovery_case
    context = deepcopy(case.context)
    if wrapped:
        snapshot = deepcopy(case.snapshot)
        snapshot['desired']['selection_identity'] = 'transport:' + '7' * 64
        snapshot['desired']['file_identity'] = snapshot['desired']['selection_identity'] + '|' + context['file_identity']
        snapshot['observed']['file_identity'] = snapshot['desired']['file_identity']
        context = exact_context(case.data, case.target, snapshot, 'native-A')
        assert context is not None
    child = child_data(context, case.result, '8' * 32, CAPSULE, 123450)
    child['_queue_drained_by_parent'] = True
    desired = dict(request_id=child['request_id'], selection_identity=context['selection_identity'], cancelled=False)
    reserved = dict(boot_id='boot', epoch=2, desired=desired, observed=None)
    commands, opened, histories, synchronized, properties = [], [], [], [], {}
    bound = {}
    def call(body, **kwargs):
        commands.append(deepcopy(body))
        operation = body['operation']
        if operation == 'snapshot': return deepcopy(reserved)
        if operation == 'bind_file':
            assert body['selection_identity'] == context['selection_identity']
            assert body['file_identity'] == context['file_identity']
            bound.update(body)
            return {'bound': True}
        assert operation == 'claim_start'
        assert body['route'] == 'player_play'
        receipt = {key: body[key] for key in ('boot_id', 'epoch', 'request_id', 'claim_id', 'route')}
        receipt.update(file_identity=bound['file_identity'], url_sha256=bound['url_sha256'])
        return {'status': 'CLAIMED', 'receipt': receipt}
    for module in (core_request, playback_request, playback_ipc):
        monkeypatch.setattr(module, 'call', call)
    def preparation(method, body, **kwargs):
        assert method == 'resolve'
        assert kwargs['expected_account'] == case.data['_account']
        assert CAPSULE not in json.dumps(body)
        return dict(state='ready', **body, file_id=case.entry['prepared_file_id'], path=case.entry['path'],
            bytes=case.entry['bytes'], version_key=case.entry['prepared_version_key'], video_context=case.entry['video_context'])
    monkeypatch.setattr(preparation_client, 'call', preparation)
    class Item:
        def __init__(self): self.props, self.resume, self.path = {}, None, None
        def setProperty(self, key, value): self.props[key] = value
        def setPath(self, value): self.path = value
        def getVideoInfoTag(self): return self
        def setResumePoint(self, position, total): self.resume = (position, total)
    item = Item()
    def make_listing(data):
        assert '_transport_handoff' not in data
        return item
    class ProgressThread:
        def __init__(self, target, args): synchronized.append(deepcopy(args[0]))
        def start(self): pass
    env = dict(deepcopy=deepcopy, re=re, uuid4=uuid4, Event=Event, Thread=ProgressThread,
        urlsplit=urlsplit, urlunsplit=urlunsplit, parse_qsl=parse_qsl, urlencode=urlencode,
        get_setting=lambda key, default=None: default, clear_property=lambda key: properties.pop(key, None),
        set_property=lambda key, value: properties.update({key: value}), kodilog=lambda *a, **kw: None,
        xbmc=SimpleNamespace(LOGINFO=1, LOGWARNING=2, LOGDEBUG=0), json_dumps=json.dumps,
        close_busy_dialog=lambda: None, make_listing=make_listing,
        ACTIVE_PLAYER_SESSION_PROPERTY='active', PLAYNEXT_ACTION_PROPERTY='next',
        setResolvedUrl=lambda *args: pytest.fail('internal child must use one outer play'),
        is_nuvio_progress_sync_enabled=lambda: True)
    names = {'run', 'set_constants', '_activate_playback_session', 'play_video',
             '_record_started_history', '_queue_nuvio_progress_sync'}
    actor = SimpleNamespace(on_started=None, _provided_cancel_event=None, playback_session_id='',
        _cinema_phase=lambda *args: None, clear_playback_properties=lambda: None,
        _is_trakt_tracking_excluded=lambda: False, add_external_trakt_scrolling=lambda: None,
        _check_volume=lambda: pytest.fail('same-file recovery must not reset manual volume'),
        _handle_trakt_scrobble=lambda *a: pytest.fail('no pre-AV tracking/resume'),
        _handle_simkl_scrobble=lambda: pytest.fail('no pre-AV tracking'),
        handle_subtitles=lambda *a: pytest.fail('native owns restored presentation'),
        play=lambda url, value: opened.append((url, value)),
        run_error=lambda error: pytest.fail('unexpected child error: ' + str(error)),
        _owns_playback_session=lambda: True, _matches_requested_playback=lambda: True,
        mark_watched=lambda data: histories.append(deepcopy(data)), _send_nuvio_progress=lambda *a: None)
    for name, method in methods(names, env).items(): setattr(actor, name, MethodType(method, actor))
    actor.monitor = lambda: actor._record_started_history()
    actor.run(child)
    actor._queue_nuvio_progress_sync()
    assert len(opened) == 1 and opened[0][0] == case.result['url']
    assert item.props['bobitv.handoff_token'] == CAPSULE
    assert item.props['bobitv.file_identity'] == context['file_identity']
    assert item.props['bobitv.request_id'] == '8' * 32
    assert item.props['StartPercent'] == '0' and item.resume == (0, 0)
    assert desired['selection_identity'] == context['selection_identity']
    assert actor._transport_handoff['capsule'] == CAPSULE
    assert not any(row['operation'] == 'select' for row in commands)
    assert histories and synchronized
    assert CAPSULE not in json.dumps(actor.data)
    assert CAPSULE not in json.dumps(histories + synchronized)


@pytest.mark.parametrize('name', ['_apply_trakt_resume', '_apply_simkl_resume', '_apply_nuvio_resume',
                                  'select_audio_stream', 'handle_subtitle_selection', 'check_cinema_subtitles'])
def test_recovered_child_never_overrides_native_presentation_or_initial_position(name):
    method = methods({name}, {})[name]
    actor = SimpleNamespace(_transport_recovery_child=True,
        seekTime=lambda *a: pytest.fail('no global seek'), showSubtitles=lambda *a: pytest.fail('no subtitle reset'),
        setAudioStream=lambda *a: pytest.fail('no audio reset'))
    method(actor)


def test_real_monitor_reserves_same_file_before_stop_cancellation_or_bookkeeping(recovery_case, monkeypatch):
    case = recovery_case
    recovery = prime(case)
    recovery.tick(6.4, 123.45, True, False, case.context, case.command)
    case.phases[0] = 'STOPPED'
    queue, events, clock, owns = [], [], [7.], [True]
    def call(body):
        result = case.command(body)
        if body['operation'] == 'reserve_child': owns[0] = False
        return result
    monkeypatch.setattr(playback_request, 'call', call)
    env = dict(deepcopy=deepcopy, monotonic=lambda: clock[0],
        sleep=lambda ms: clock.__setitem__(0, clock[0] + ms / 1000),
        TERMINAL_RECONCILIATION_SECONDS=3., get_setting=lambda *a: False,
        kodilog=lambda *a, **kw: None, xbmc=SimpleNamespace(LOGINFO=1, LOGERROR=2),
        JacktookPLayer=SimpleNamespace(_nextep_queue=queue))
    actor = SimpleNamespace(data=deepcopy(case.data), _transport_recovery=recovery,
        _native_instance='native-A', playback_session_id=case.data['request_id'], _cinema_cancel=Event(),
        _cinema_natural_queued=False, _cinema_end=False, _terminal_reason='UNKNOWN', skip_intro_enabled=False,
        _cinema_next_data={'wrong_episode': True},
        _wait_for_video_start=lambda: True, handle_playback_start=lambda: True,
        _cinema_phase=lambda value: events.append(value), _record_started_history=lambda: None,
        start_cinema_preparation=lambda: None, select_audio_stream=lambda: None,
        handle_subtitle_selection=lambda: None, isPlayingVideo=lambda: False,
        _owns_playback_session=lambda: owns[0],
        wait_cinema_terminal=lambda **kw: pytest.fail('STOP must be reserved before normal cancellation'),
        queue_cinema_natural_end=lambda: pytest.fail('same-file STOP is not next-episode EOF'),
        handle_playback_stop=lambda: events.append(('bookkeeping', len(queue))),
        offer_terminal_actions=lambda: None, kill_dialog=lambda: pytest.fail('unexpected monitor failure'),
        clear_playback_properties=lambda: pytest.fail('cannot clear child properties'),
        _release_playback_session=lambda: pytest.fail('cannot release newly reserved child'))
    for name, method in methods({'monitor', 'queue_cinema_transport_end'}, env).items():
        setattr(actor, name, MethodType(method, actor))
    actor.monitor()
    assert len(queue) == 1
    assert ('bookkeeping', 1) in events
    assert actor._terminal_reason == 'STOP' and actor.data['completed'] is False
    assert actor._transport_parent_queued and not actor._cinema_natural_queued
    assert not actor._cinema_end


def test_parent_transport_stop_saves_progress_without_remote_completion_or_late_pause(recovery_case, monkeypatch):
    from lib.db import deferred_history
    saved = []
    monkeypatch.setattr(deferred_history, 'defer_watched_file', lambda data: saved.append(deepcopy(data)) or True)
    method = methods({'handle_playback_stop'}, dict(deepcopy=deepcopy))[ 'handle_playback_stop']
    actor = SimpleNamespace(_transport_parent_queued=True, data=deepcopy(recovery_case.data),
        _is_trakt_tracking_excluded=lambda: False,
        _sync_yamtrack_watched=lambda: pytest.fail('transport change is not completion'),
        _queue_nuvio_progress_sync=lambda: pytest.fail('child owns new progress tracking'))
    method(actor)
    assert len(saved) == 1 and saved[0]['terminal_reason'] == 'STOP' and saved[0]['completed'] is False
    assert CAPSULE not in json.dumps(saved)

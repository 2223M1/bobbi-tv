"""Actual JS/HTTP/service/authority chain, synthetic native only."""
from copy import deepcopy
from pathlib import Path
from queue import Queue
import shutil
import subprocess
import sys
from threading import Event, Thread
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from test_ce2097_phone_management import phone, http_server
from test_playback_authority import playing


def test_real_browser_http_reload_preserves_instance_command_and_observed_position(http_server):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js required for actual browser transport regression')
    _, phone = http_server
    phone.manager.scopes |= phone.module.PLAYBACK_SCOPES
    inbox, started = Queue(), Event()
    captured = {}

    def run():
        owner, native, args = playing()
        native.current.update(audio_intent=0, open_epoch=native.epoch, control_protocol=1)
        owner.selection_account = dict(phone.expected)
        def scoped(expected, action):
            assert expected == phone.expected
            return action()
        owner.configure_accounts(SimpleNamespace(run_if_current=scoped))
        position = [2000]
        control = native.control
        def accept(command):
            result = control(command)
            position[0] = command['position_ms']
            return result
        native.control = accept
        native.subtitles = lambda: dict(status='READY', control_protocol=1, receipt=deepcopy(native.current),
            selection_epoch=native.epoch, position_ms=position[0], duration_ms=100000, can_seek=True,
            visible=False, audio_index=-1, current_index=-1, audio_streams=[], streams=[], chapters=[],
            commands=[dict(command, status='applied') for command in native.commands])
        captured.update(owner=owner, native=native)
        started.set()
        while True:
            request = inbox.get()
            if request is None:
                return
            body, done, response = request
            try:
                response['result'] = owner.dispatch(body)
            except BaseException as error:
                response['error'] = error
            finally:
                done.set()

    worker = Thread(target=run, daemon=True)
    worker.start()
    assert started.wait(5)
    original = phone.manager.rpc
    def dispatch(action, body, **kwargs):
        if action == 'catalog_query':
            return dict(items=[], next_cursor=None)
        if action != 'playback':
            return original(action, body, **kwargs)
        done, response = Event(), {}
        inbox.put((body, done, response))
        assert done.wait(5)
        if 'error' in response:
            raise response['error']
        return response['result']
    phone.manager.rpc = dispatch
    try:
        trial = subprocess.run([node, str(ROOT / 'tests/frontend/phone_http_recovery_trial.cjs'),
            phone.manager.origin, phone.manager.pairing_url.split('#')[1]],
            capture_output=True, text=True, encoding='utf-8', timeout=20)
        assert trial.returncode == 0, trial.stdout + trial.stderr
        assert 'HTTP_RELOAD_RECOVERED_ORIGINAL_COMMAND' in trial.stdout
        assert len(captured['native'].commands) == 1
        assert captured['native'].commands[0]['position_ms'] == 42000
        assert captured['native'].gui_commands == []
        assert len(captured['owner'].playback_commands) == 1
    finally:
        inbox.put(None)
        worker.join(5)
        assert not worker.is_alive()


def test_real_browser_user_transport_recovers_stop_after_native_instance_is_gone(http_server):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js required for actual browser transport regression')
    _, phone = http_server
    phone.manager.scopes |= phone.module.PLAYBACK_SCOPES
    inbox, started = Queue(), Event()
    captured = {}

    def run():
        owner, native, _ = playing()
        native.current.update(audio_intent=0, open_epoch=native.epoch, control_protocol=1)
        owner.selection_account = dict(phone.expected)
        def scoped(expected, action):
            assert expected == phone.expected
            return action()
        owner.configure_accounts(SimpleNamespace(run_if_current=scoped))
        recent, terminal = [], []
        control, state = native.control, native.state
        native.state = lambda: dict(state(), control_protocol=1, terminal_commands=deepcopy(terminal))
        def accept(command):
            result = control(command)
            original = deepcopy(native.current)
            if command['action'] == 'user_stop':
                terminal.append(dict(command, status='applied', terminal_reason='STOP',
                    terminal_sequence=original['sequence'] + 1, terminal_open_epoch=original['open_epoch'],
                    terminal_user_intent=original['user_intent'] + 1))
                native.current = None
            else:
                assert command['action'] in ('user_pause', 'user_resume')
                native.current.update(paused=command['action'] == 'user_pause',
                    user_intent=original['user_intent'] + 1, sequence=original['sequence'] + 1)
                recent.append(dict(command, status='applied'))
            return result
        native.control = accept
        def subtitles():
            if native.current is None:
                return dict(status='UNAVAILABLE')
            paused = native.current['paused']
            return dict(status='READY', control_protocol=1, receipt=deepcopy(native.current),
                selection_epoch=native.epoch, position_ms=2000, duration_ms=100000, can_seek=False,
                visible=False, audio_index=-1, current_index=-1, audio_streams=[], streams=[], chapters=[],
                commands=deepcopy(recent), transport_protocol=1, transport_state='paused' if paused else 'playing',
                can_pause=not paused, can_resume=paused, can_stop=True)
        native.subtitles = subtitles
        captured.update(owner=owner, native=native)
        started.set()
        while True:
            request = inbox.get()
            if request is None:
                return
            body, done, response = request
            try:
                response['result'] = owner.dispatch(body)
            except BaseException as error:
                response['error'] = error
            finally:
                done.set()

    worker = Thread(target=run, daemon=True)
    worker.start()
    assert started.wait(5)
    original = phone.manager.rpc
    def dispatch(action, body, **kwargs):
        if action == 'catalog_query':
            return dict(items=[], next_cursor=None)
        if action != 'playback':
            return original(action, body, **kwargs)
        done, response = Event(), {}
        inbox.put((body, done, response))
        assert done.wait(5)
        if 'error' in response:
            raise response['error']
        return response['result']
    phone.manager.rpc = dispatch
    try:
        trial = subprocess.run([node, str(ROOT / 'tests/frontend/phone_http_user_transport_trial.cjs'),
            phone.manager.origin, phone.manager.pairing_url.split('#')[1]],
            capture_output=True, text=True, encoding='utf-8', timeout=25)
        assert trial.returncode == 0, trial.stdout + trial.stderr
        assert 'HTTP_USER_TRANSPORT_ORIGINAL_STOP_RECOVERED' in trial.stdout
        native, owner = captured['native'], captured['owner']
        assert [command['action'] for command in native.commands] == ['user_pause', 'user_resume', 'user_stop']
        assert native.current is None and native.gui_commands == []
        assert len(owner.playback_commands) == 3
        assert all(record['status'] == 'applied' for record in owner.playback_commands.values())
    finally:
        inbox.put(None)
        worker.join(5)
        assert not worker.is_alive()

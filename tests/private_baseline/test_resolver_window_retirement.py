"""Run the actual resolver lifecycle methods without Kodi/import side effects."""
import ast
from pathlib import Path
from threading import Event
from types import ModuleType, SimpleNamespace
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[2] / 'addons/plugin.video.bobbi/lib/gui/resolver_window.py'


@pytest.fixture
def resolver(monkeypatch):
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'ResolverWindow')
    methods = [node for node in original.body if isinstance(node, ast.FunctionDef)
               and node.name in ('_capture_loading_dialog', '_handoff_rejected', 'handle_playback_started')]
    isolated = ast.ClassDef(name='ResolverWindow', bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[isolated], type_ignores=[]))
    state = SimpleNamespace(top=10138, tokens={}, visible=set(), calls=[], sleeps=[], closes=[], tracked=True,
                            hide_after=1, sleep_count=0, read_ids=[], scanned_ids=[])

    def window(value):
        raise AssertionError('Do not construct a Window wrapper for potentially empty slots')

    def label(value):
        dialog_id = int(value.split('(')[1].split(')')[0])
        state.read_ids.append(dialog_id)
        return state.tokens.get(dialog_id, '')

    def visible(condition):
        assert condition.startswith('Window.IsVisible(')
        dialog_id = int(condition.split('(')[1].split(')')[0])
        state.scanned_ids.append(dialog_id)
        return dialog_id in state.visible

    def pause(milliseconds):
        state.sleeps.append(milliseconds)
        state.sleep_count += 1
        if state.hide_after is not None and state.sleep_count >= state.hide_after:
            state.visible.discard(13001)

    def call(message):
        state.calls.append(message)
        if message['operation'] == 'begin_window_close':
            assert message['dialog_id'] == 13001
            assert state.tokens[13001] == message['token']
            assert 13001 in state.visible
            return {'tracked': state.tracked}
        assert message['operation'] == 'close_window'
        assert 13001 not in state.visible
        return {'closed': True}

    adapter = ModuleType('lib.cinema.playback_request')
    adapter.call = call
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', adapter)
    namespace = dict(xbmc=SimpleNamespace(getCondVisibility=visible, getInfoLabel=label, sleep=pause, LOGWARNING=2),
                     xbmcgui=SimpleNamespace(getCurrentWindowDialogId=lambda: state.top,
                         Window=window),
                     kodilog=lambda *_args, **_kwargs: None)
    exec(compile(module, str(SOURCE), 'exec'), namespace)
    obj = namespace['ResolverWindow']()
    obj._dialog_id = 0
    obj._window_token = 'owned-loading-token'
    obj._window_context = {'boot_id': 'boot', 'epoch': 1, 'request_id': 'request'}
    obj.item_information = {'request_id': 'request'}
    obj._modeless = True
    obj.cancel_event = Event()
    obj.resolved = False
    obj._owns_selection = lambda: True
    obj.close_windows = lambda: state.closes.append('owned-only')
    state.tokens[13001] = obj._window_token
    state.visible.add(13001)
    return obj, state


def test_busy_overlay_at_init_is_not_the_owned_loading_dialog(resolver):
    obj, state = resolver
    state.visible.add(10138)
    assert obj._capture_loading_dialog() is True
    assert obj._dialog_id == 13001
    assert state.scanned_ids == list(range(13000, 13100))
    assert state.read_ids == [13001]


def test_start_rebinds_busy_id_and_waits_for_exact_owned_window_retirement(resolver):
    obj, state = resolver
    obj._dialog_id = 10138  # Reproduce the Windows onInit timing before this fix.
    state.top = 13001
    state.hide_after = 3
    assert obj.handle_playback_started() is True
    assert obj._dialog_id == 13001
    assert [message['operation'] for message in state.calls] == ['begin_window_close', 'close_window']
    assert state.sleeps == [25, 25, 25]
    assert state.closes == ['owned-only']


@pytest.mark.parametrize('failure', ['wrong-token', 'hidden', 'no-context', 'cancelled', 'not-owned', 'untracked'])
def test_no_handoff_or_lease_release_without_current_owned_window_receipt(resolver, failure):
    obj, state = resolver
    state.top = 13001
    if failure == 'wrong-token':
        state.tokens[13001] = 'another-request'
    elif failure == 'hidden':
        state.visible.clear()
    elif failure == 'no-context':
        obj._window_context = None
    elif failure == 'cancelled':
        obj.cancel_event.set()
    elif failure == 'not-owned':
        obj._owns_selection = lambda: False
    elif failure == 'untracked':
        state.tracked = False
    assert obj.handle_playback_started() is False
    assert not state.closes
    assert not any(message['operation'] == 'close_window' for message in state.calls)


def test_never_closing_owned_dialog_fails_bounded_without_releasing_lease(resolver):
    obj, state = resolver
    state.top = 13001
    state.hide_after = None
    assert obj.handle_playback_started() is False
    assert state.sleeps == [25] * 20
    assert [message['operation'] for message in state.calls] == ['begin_window_close']


def test_new_user_modal_is_never_misidentified_or_closed(resolver):
    obj, state = resolver
    state.top = 10126
    state.tokens[10126] = 'new-user-modal'
    state.visible.add(10126)
    assert obj._capture_loading_dialog() is True
    assert obj._dialog_id == 13001
    assert obj.handle_playback_started() is True
    assert 10126 in state.visible
    assert state.tokens[10126] == 'new-user-modal'
    assert state.closes == ['owned-only']
    # This callback only retires our loading dialog. Native fullscreen still
    # rejects the user's modal; it is never closed or treated as our window.
    assert state.calls[0]['dialog_id'] == 13001


def test_duplicate_visible_token_is_rejected_without_picking_first_match(resolver):
    obj, state = resolver
    state.tokens[13002] = obj._window_token
    state.visible.add(13002)
    assert obj._capture_loading_dialog() is False
    assert obj._capture_reason == 'LOADING_WINDOW_AMBIGUOUS'
    assert obj.handle_playback_started() is False
    assert not state.calls
    assert not state.closes


def test_token_outside_python_window_namespace_is_never_bound(resolver):
    obj, state = resolver
    state.tokens.pop(13001)
    state.tokens[10138] = obj._window_token
    state.visible.add(10138)
    assert obj._capture_loading_dialog() is False
    assert obj._capture_reason == 'LOADING_WINDOW_NOT_IDENTIFIED'


def test_hidden_duplicate_does_not_replace_the_one_visible_owned_window(resolver):
    obj, state = resolver
    state.tokens[13002] = obj._window_token
    assert obj._capture_loading_dialog() is True
    assert obj._dialog_id == 13001

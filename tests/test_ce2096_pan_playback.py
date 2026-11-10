"""Manual entry handoff to existing owners; fake Kodi, no playback claims."""
from copy import deepcopy
import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import playback_request, playback_ipc
from bobbi_platform import pan_stream
from bobbi_platform.pan_accounts import PanError


@pytest.fixture
def entry(monkeypatch):
    state = SimpleNamespace(calls=[], played=[], errors=[], native=True, cancel=False, fail=None)
    state.expected = dict(provider='quark', account_id='quark:'+'f'*64, epoch=1, authenticated=True)
    state.file = dict(file_id='f1', name='movie.mkv', size=8, directory=False)
    state.ticket = 'a'*32
    state.body = pan_stream.body('quark', state.file, state.ticket)
    progress = SimpleNamespace(create=lambda *a: None, close=lambda: None, iscanceled=lambda: state.cancel)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: SimpleNamespace(
        abortRequested=lambda: False, waitForAbort=lambda seconds: False)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(DialogProgress=lambda: progress,
        Dialog=lambda: SimpleNamespace(ok=lambda *a: state.errors.append(a))))
    monkeypatch.setitem(sys.modules, 'lib.native_support', SimpleNamespace(available=lambda: state.native))
    class Player:
        def __init__(self, cancel_event): self._resolution_answered = False
        def run(self, data):
            state.played.append(deepcopy(data))
            self._resolution_answered = True
    monkeypatch.setitem(sys.modules, 'lib.player', SimpleNamespace(JacktookPLayer=Player))
    monkeypatch.setattr(playback_request, 'read_snapshot', lambda: dict(boot_id='fixture-boot', epoch=1))
    def select(snapshot, request, identity, account_scope):
        state.calls.append(('native_select', dict(request_id=request, identity=identity, account=account_scope)))
        return dict(boot_id='fixture-boot', epoch=2, desired=dict(request_id=request, cancelled=False))
    monkeypatch.setattr(playback_request, 'select', select)
    monkeypatch.setattr(playback_ipc, 'call', lambda body: state.calls.append(('native_control', body)))
    spec = importlib.util.spec_from_file_location('pan_play_entry', ROOT/'addons/plugin.video.bobbi/lib/pan_playback.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def call(action, body, **kw):
        state.calls.append((action, deepcopy(body)))
        if action == 'pan_claim_play':
            return dict(request_id=state.ticket, account=state.expected, selected=state.file,
                        **getattr(state, 'claim_extra', {}))
        if action == 'pan_open_stream':
            if state.fail: raise state.fail
            return dict(state='ready', request_id=state.ticket, account=state.expected, bytes=8,
                guid=state.body['guid'], media=state.body['media'],
                url='http://127.0.0.1:12345/stream/'+'b'*32+'/video.mkv')
        return {}
    monkeypatch.setattr(module, 'call', call)
    state.module = module
    return state


@pytest.mark.parametrize('native', [True, False])
def test_manual_file_keeps_owner_reservation_and_never_invents_tmdb(entry, native):
    entry.native = native
    entry.module.play({'ticket': entry.ticket})
    assert len(entry.played) == 1 and not entry.errors
    data = entry.played[0]
    assert data['file_evidence'] == 'USER_CONFIRMED_FILE' and data['ids'] == {} and data['mode'] == 'file'
    assert data['_account'] == entry.expected and data['_ui_reserved_request'] == entry.ticket
    assert data['url'].startswith('http://127.0.0.1:') and 'selected' not in data
    assert playback_request.data_identity(data) == 'transport:' + playback_request.digest(data['_pan_locator'])
    actions = [a for a, b in entry.calls]
    assert actions.index('native_select' if native else 'standard_playback') < actions.index('pan_open_stream')
    assert 'pan_close_stream' not in actions


def test_back_after_resolution_wins_before_any_player_submission(entry):
    entry.cancel = True
    entry.module.play({'ticket': entry.ticket})
    assert not entry.played and not entry.errors
    assert [a for a, b in entry.calls][-2:] == ['pan_close_stream', 'native_control']
    assert entry.calls[-1][1]['operation'] == 'cancel'


def test_resolution_failure_never_reselects_or_replays_entry(entry):
    entry.fail = PanError('PAN_ACCOUNT_CHANGED')
    entry.module.play({'ticket': entry.ticket})
    assert not entry.played and len(entry.errors) == 1
    assert sum(a == 'native_select' for a, b in entry.calls) == 1
    assert sum(a == 'pan_open_stream' for a, b in entry.calls) == 1
    assert '账号已变更' in entry.errors[0][1]


def test_route_accepts_only_an_opaque_ticket(entry):
    entry.module.play({'ticket': 'https://evil.test/'})
    assert not entry.calls and not entry.played


@pytest.mark.parametrize('native', [True, False])
def test_history_reuses_pre_reserved_owner_and_real_position_without_reselection(entry, native):
    from bobbi_core.file_ref import from_selected, locator
    entry.native = native
    ref = from_selected(entry.expected, entry.file, '0')
    history = dict(file_ref=ref, generation=2, session_id='c' * 32)
    entry.claim_extra = dict(file_ref=ref, history={k: history[k] for k in ('generation', 'session_id')})
    reservation = dict(account=entry.expected, owner={'request_id': entry.ticket},
                       file_ref=ref, position=42)
    entry.module.play({'ticket': entry.ticket}, reservation=reservation)
    assert len(entry.played) == 1 and not entry.errors
    assert not [a for a, b in entry.calls if a in ('native_select', 'standard_playback')]
    data = entry.played[0]
    assert data['_file_history'] == history and data['_file_resume_position'] == 42
    assert data['_pan_locator'] == locator(ref)
    assert 'selected' not in data and 'file_ref' not in data


@pytest.mark.parametrize('native', [True, False])
def test_resume_reserves_before_host_verification_and_cancel_retires_only_that_request(entry, native, monkeypatch):
    from bobbi_core.file_ref import from_selected
    entry.native = native
    ref = from_selected(entry.expected, entry.file, '0')
    row = dict(file_ref=ref, position=42)
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(
        FileHistory=lambda: SimpleNamespace(get=lambda identifier: row)))
    original = entry.module.call
    def call(action, body, **kwargs):
        if action == 'pan_status':
            entry.calls.append((action, body))
            return {'providers': [dict(provider='quark', account=entry.expected)]}
        if action == 'pan_prepare_history_play':
            entry.calls.append((action, body))
            entry.cancel = True  # Back wins while remote metadata is finishing.
            return dict(ticket=body['request_id'])
        return original(action, body, **kwargs)
    monkeypatch.setattr(entry.module, 'call', call)
    entry.module.resume({'history_id': ref['id']})
    assert not entry.played and not entry.errors
    actions = [a for a, b in entry.calls]
    assert actions.index('native_select' if native else 'standard_playback') < actions.index('pan_prepare_history_play')
    assert 'pan_cancel_operation' in actions and 'pan_close_stream' in actions
    assert 'pan_claim_play' not in actions and actions.count('native_select') == int(native)
    assert entry.calls[-1][1]['operation'] == 'cancel'


def test_personal_native_listitem_does_not_invent_movie_metadata():
    path = ROOT/'addons/plugin.video.bobbi/lib/utils/general/utils.py'
    node = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
                if isinstance(n, ast.FunctionDef) and n.name == 'make_listing')
    calls = []
    tag = SimpleNamespace(setTitle=lambda value: calls.append(('title', value)),
                          setMediaType=lambda value: calls.append(('type', value)))
    item = SimpleNamespace(setContentLookup=lambda value: calls.append(('lookup', value)),
        setProperty=lambda *a: calls.append(a), getVideoInfoTag=lambda: tag)
    env = dict(make_list_item=lambda **kw: item,
               set_media_infoTag=lambda *a, **kw: pytest.fail('No movie identity/metadata path'))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), env)
    data = dict(_pan_file=True, title='My personal video.mkv', mode='file', ids={})
    before = deepcopy(data)
    assert env['make_listing'](data) is item
    assert ('type', 'video') in calls and ('lookup', False) in calls and data == before

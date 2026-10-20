"""Candidate production modules/methods, not a simplified Web model."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace, MethodType
from threading import Thread
import time
import pytest

ROOT = Path(__file__).resolve().parents[1]
for name in ('script.module.bobbi.core', 'plugin.video.bobbi.torrent'):
    sys.path.insert(0, str(ROOT / 'addons' / name / 'lib'))
from bobbi_core.playback_owner import PlaybackOwner
from bobbi_torrent.resolver import Resolver, metadata_files, manual_candidates
from bobbi_torrent.backend import Backend, BackendError
from test_bobbi_torrent_adapter import (Clock, FakeOwner, Session, Response,
    request, config, status, HASH, RID)


def test_unknown_file_choice_is_rechecked_and_not_published_for_preparation():
    file = dict(id=4, path='video.mkv', length=1000000)
    info = status(file)
    clock, prompts = Clock(), []
    owner = FakeOwner(clock)
    owner.choose_file = lambda files: prompts.append(files) or files[0]
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(info),
                       Response(info), Response(b''), Response(info)])
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert result['file_evidence'] == 'USER_CONFIRMED_FILE'
    assert result['file'] == file and prompts == [[file]]
    assert owner.targets == []  # No early preparation target for a manual choice.
    assert sum(c[2].get('json', {}).get('action') == 'add' for c in session.calls) == 1


def test_changed_file_after_manual_dialog_cannot_open():
    file = dict(id=4, path='video.mkv', length=1000000)
    clock = Clock()
    owner = FakeOwner(clock)
    owner.choose_file = lambda files: files[0]
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(status(file)),
                       Response(status(dict(file, length=2000000)))])
    with pytest.raises(BackendError, match='SELECTED_FILE_CHANGED'):
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert not owner.bindings and not owner.targets


@pytest.mark.parametrize('path', ['/a.mkv', '../a.mkv', 'dir/../a.mkv', 'C:/a.mkv',
                                  'dir//a.mkv', 'dir\\..\\a.mkv', 'a\r.mkv'])
def test_metadata_paths_rejected_before_any_file_dialog(path):
    with pytest.raises(BackendError):
        metadata_files(status(dict(id=1, path=path, length=100)))


def test_manual_does_not_offer_explicit_other_episode_or_season():
    rows = [dict(id=i+1, path=name, length=1000) for i, name in enumerate(
        ['video.mkv', 'Series.S01E02.mkv', 'Series.S02E01.mkv', 'Series - 03.mkv'])]
    protocol = SimpleNamespace(validate_torrent_resolution=lambda *a: 'bt:' + HASH)
    assert manual_candidates(dict(file_stats=rows), request(), HASH, {}, protocol) == rows[:1]


def test_manual_cannot_bypass_validated_wrong_work_binding():
    from bobbi_core.episode_identity import bind_transport_episode
    from bobbi_core.playback_request import digest
    locator = 'https://example.test/pack.torrent'
    identity = 'transport:' + digest(locator)
    proof = bind_transport_episode({'tmdb_id': '68272'}, {'season': 1, 'episode': 1},
        RID, identity, locator, catalog={'tmdb_id': 68272, 'aliases': ['Flip Flappers'], 'year': 2016})
    protocol = SimpleNamespace(validate_torrent_resolution=lambda *a: identity)
    assert manual_candidates(status(), request(episode_binding=json.dumps(proof)), HASH, {}, protocol) == []


def test_manual_binding_has_no_continuation_and_cannot_be_upgraded_by_rebinding():
    owner = PlaybackOwner('boot')
    owner.select('boot', 0, RID, 'bt:' + HASH)
    args = ('boot', 1, RID)
    assert owner.bind_file(*args, 'bt:' + HASH, 'file', 'USER_CONFIRMED_FILE')
    assert not owner.bind_file(*args, 'bt:' + HASH, 'file', 'AUTO_VERIFIED_FILE')
    assert owner.claim_start(*args, 'resolved_url')
    assert owner.observe_started(*args, 'native', 'file')
    assert owner.observe_terminal('native', 'NATURAL_EOF')
    assert not owner.consume_next(*args, 'native')
    assert owner.snapshot()['terminal']['reason'] == 'NATURAL_EOF'


def test_high_progress_error_keeps_real_resume_and_order():
    path = ROOT / 'addons/plugin.video.bobbi/lib/cinema/frontend_contract.py'
    spec = importlib.util.spec_from_file_location('ce_frontend', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [(str(i), dict(ids={'tmdb_id':i}, mode='movies', progress=p, **extra))
            for i, p, extra in [(1,97,{'completed':False}), (2,100,{'completed':True}),
                                 (3,50,{}), (4,99,{}), (5,2,{'completed':False})]]
    result = module.history_rows(rows, lambda item: int(item[0]))
    assert [r[0] for r in result] == ['5', '3', '1']
    assert result[-1][1]['progress'] == 97


@pytest.mark.parametrize('reason,completed', [('ERROR',False), ('UNKNOWN',False),
    ('STOP',False), ('SUPERSEDED',False), ('CANCEL',False), ('NATURAL_EOF',True)])
def test_actual_stop_method_cannot_report_error_as_watched(reason, completed):
    path = ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'handle_playback_stop')
    events = []
    scrobble = SimpleNamespace(trakt_pause_scrobble=lambda d: events.append('pause'),
                               trakt_stop_scrobble=lambda d: events.append('stop'))
    env = dict(kodilog=lambda *a, **kw:None, xbmc=SimpleNamespace(LOGINFO=1),
        TraktAPI=lambda:SimpleNamespace(scrobble=scrobble),
        set_watched_file=lambda d:events.append(dict(d)))
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), env)
    player = SimpleNamespace(data={'selection_policy':'exact','progress':97}, _terminal_reason=reason,
        _cinema_phase=lambda *a:None, _sync_yamtrack_watched=lambda:None,
        _queue_nuvio_progress_sync=lambda:None, _is_trakt_scrobble_enabled=lambda:True,
        _is_trakt_tracking_excluded=lambda:False, _delete_completed_simkl_playback=lambda:None,
        _delete_completed_trakt_playback=lambda:None)
    env['handle_playback_stop'](player)
    assert player.data['completed'] is completed and player.data['progress'] == 97
    assert events[0] == ('stop' if completed else 'pause')


@pytest.mark.parametrize('evidence,request_id,cancelled,allowed', [
    ('AUTO_VERIFIED_FILE', RID, False, True),
    ('USER_CONFIRMED_FILE', RID, False, False),
    ('AUTO_VERIFIED_FILE', 'e' * 32, False, False),
    ('AUTO_VERIFIED_FILE', RID, True, False),
])
def test_preparation_checks_real_actor_snapshot(tmp_path, evidence, request_id, cancelled, allowed):
    from bobbi_platform.host import Host
    from bobbi_core.capabilities import IPC_PROTOCOL
    from test_accounts import credential
    host, calls, replies = Host(tmp_path), [], []
    host.start()
    scope = host.accounts.install(credential('42'), host.accounts.snapshot())
    host.bind_owner(lambda body: dict(desired=dict(request_id=RID, cancelled=cancelled,
                                                  file_evidence=evidence)))
    host.bind_preparation(SimpleNamespace(
        request=lambda *args: calls.append(args) or {'accepted': True}, close=lambda: None))
    def invoke():
        try:
            replies.append(host.dispatch('preparation', dict(method='prepare', protocol=IPC_PROTOCOL,
                account=scope, body=dict(request_id=request_id))))
        except ValueError as error:
            replies.append(str(error))
    try:
        worker = Thread(target=invoke)
        worker.start()
        end = time.monotonic() + 1
        while host.calls.empty() and time.monotonic() < end:
            time.sleep(.005)
        host.tick()
        worker.join(1)
        assert not worker.is_alive()
        assert bool(calls) is allowed
        assert replies == ([{'accepted': True}] if allowed else
                           ['PREPARATION_CURRENT_VERIFIED_SELECTION_REQUIRED'])
    finally:
        host.close()


def test_terminal_menu_is_available_when_next_reservation_was_rejected(monkeypatch):
    path = ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'offer_terminal_actions')
    shown, actions = [], []
    monkeypatch.setitem(sys.modules, 'lib.gui.terminal_actions', SimpleNamespace(
        choose=lambda current, episode, ended: shown.append((current(), episode, ended))))
    env = dict(xbmc=SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: False)),
               execute_builtin=actions.append)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), env)
    player = SimpleNamespace(data=dict(selection_policy='exact', mode='tv', cinema_continuity=True),
        _terminal_reason='NATURAL_EOF', _cinema_natural_queued=False,
        _cinema_next_data={'not_authorized': True}, playback_session_id=RID,
        kodi_monitor=SimpleNamespace(abortRequested=lambda: False), _owns_playback_session=lambda: True)
    env['offer_terminal_actions'](player)
    assert shown == [(True, True, True)] and not actions
    player._cinema_natural_queued = True
    env['offer_terminal_actions'](player)
    assert len(shown) == 1  # A queued successor must not be covered by this prompt.

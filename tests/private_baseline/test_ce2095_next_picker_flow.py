"""Production EOF queue -> shared discovery -> manual picker, with real authority."""
import ast
from copy import deepcopy
from pathlib import Path
import re
from threading import Event
from time import monotonic
from types import MethodType, SimpleNamespace as NS
from uuid import uuid4

import pytest

from lib.utils.player import next_source_picker as picker
from lib.cinema import playback_request
from test_playback_authority import playing, select
from test_ce2089_shared_search import shared


def current(**extra):
    return dict(mode='tv', ids={'tmdb_id': 123}, tv_data={'season': 1, 'episode': 1},
        title='Fixture', selection_policy='exact', cinema_continuity=True, **extra)


def episode(number, air='2020-01-01'):
    return NS(episode_number=number, name='Episode ' + str(number), air_date=air)


@pytest.fixture
def metadata(monkeypatch):
    from lib.clients.tmdb.utils import utils
    rows = {1: [episode(1), episode(2)], 2: [episode(1)]}
    calls = []
    def get(kind, value):
        calls.append((kind, value))
        return (NS(episodes=rows.get(value['season'], [])) if kind == 'season_details'
                else NS(seasons=[NS(season_number=s) for s in rows]))
    monkeypatch.setattr(utils, 'tmdb_get', get)
    return NS(rows=rows, calls=calls)


@pytest.mark.parametrize('boundary', [False, True])
def test_target_is_exact_adjacent_episode_without_previous_file_state(metadata, boundary):
    data = current(url='previous', source_title='previous', _share={'secret': 'no'},
        subtitles_path=['old'], resume_time=77, _selection_context={'epoch': 7},
        _account={'account_id': 'fixture', 'epoch': 1})
    if boundary:
        data['tv_data']['episode'] = 2
    result = picker.target_episode(data, lambda: False)
    assert result['ids'] == {'tmdb_id': 123}
    assert (result['tv_data']['season'], result['tv_data']['episode']) == ((2, 1) if boundary else (1, 2))
    assert not result['autoplay'] and result['_account'] == data['_account']
    assert not set(result).intersection({'url', 'source_title', '_share', 'subtitles_path',
        'resume_time', '_selection_context', '_ui_reserved_request'})


@pytest.mark.parametrize('change', ['future', 'no-date', 'bad-date', 'duplicate', 'gap',
    'past-end', 'series-end', 'missing-next-season', 'cancel', 'wrong-mode'])
def test_uncertain_or_nonadjacent_target_never_searches(metadata, change):
    data = current()
    if change == 'future': metadata.rows[1][1].air_date = '2999-01-01'
    elif change == 'no-date': metadata.rows[1][1].air_date = None
    elif change == 'bad-date': metadata.rows[1][1].air_date = 'bad'
    elif change == 'duplicate': metadata.rows[1].append(episode(2))
    elif change == 'gap': metadata.rows[1] = [episode(1), episode(3)]
    elif change == 'past-end': data['tv_data']['episode'] = 99
    elif change == 'series-end': data['tv_data'] = {'season': 2, 'episode': 1}
    elif change == 'missing-next-season':
        data['tv_data']['episode'] = 2
        metadata.rows[3] = metadata.rows.pop(2)
    elif change == 'wrong-mode': data['mode'] = 'movies'
    assert picker.target_episode(data, lambda: change == 'cancel') is None


@pytest.fixture
def flow(shared, metadata, monkeypatch, tmp_path):
    authority, native, parent = playing()
    from bobbi_platform import runtime
    from bobbi_platform.account_manager import AccountManager
    from test_native_continuation_account_guard import credentials
    manager = AccountManager(tmp_path / 'account.json')
    manager.install(credentials(), manager.snapshot())
    authority.configure_accounts(manager)
    original = runtime.call
    monkeypatch.setattr(runtime, 'call', lambda action, *a, **kw:
        manager.snapshot() if action == 'account_status' else original(action, *a, **kw))
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    monkeypatch.setattr(playback_request, 'call', authority.dispatch)
    path = Path(__file__).resolve().parents[2] / 'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(node for node in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(node, ast.ClassDef) and node.name == 'JacktookPLayer')
    names = {'queue_cinema_natural_end', '_drain_nextep_queue'}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    entries, notices, shown = [], [], []
    def forbidden(*a, **kw): pytest.fail('Fallback must not play, stop, or globally close dialogs')
    env = dict(re=re, uuid4=uuid4, xbmc=NS(LOGINFO=1, LOGWARNING=2),
        kodilog=lambda *a, **kw: None, notification=lambda *a, **kw: notices.append(a),
        JacktookPLayer=NS(_nextep_queue=entries), close_busy_dialog=forbidden, close_all_dialog=forbidden,
        clear_property=forbidden)
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), 'exec'), env)
    actor = NS(data=current(), _cinema_cancel=Event(), _cinema_end=True,
        _cinema_next_data=None, _cinema_fresh_next=lambda: None, _cinema_natural_queued=False,
        _owns_playback_session=lambda: True,
        _owner_context=parent, _native_instance=native.current['native_instance'],
        _check_still_watching_threshold=forbidden, kodi_monitor=NS(abortRequested=lambda: False))
    for name in names:
        setattr(actor, name, MethodType(env[name], actor))
    monkeypatch.setattr(shared.search.xbmc, 'Monitor', lambda: NS(abortRequested=lambda: False,
        waitForAbort=lambda seconds: Event().wait(seconds)))
    monkeypatch.setattr(shared.search, 'show_source_select', lambda *a, **kw: shown.append((a, kw)) or False)
    monkeypatch.setattr(shared.search, 'notification', lambda *a, **kw: notices.append(a))
    result = NS(authority=authority, native=native, parent=parent, actor=actor, entries=entries,
        notices=notices, shown=shown, shared=shared)
    yield result
    job = getattr(actor, '_cinema_picker_search', None)
    if job:
        job.cancel()


def prefetch_done(flow):
    job = picker.prefetch(flow.actor)
    assert job.finished.wait(3)
    assert job.snapshot() is not None
    job.snapshot()[2].thread.join(3)
    assert not job.snapshot()[2].thread.is_alive()
    return job


def test_eof_to_existing_search_session_is_manual_once_with_exact_target(flow):
    job = prefetch_done(flow)
    before = list(flow.shared.calls)
    flow.actor.queue_cinema_natural_end()
    flow.actor.queue_cinema_natural_end()
    assert len(flow.entries) == 1
    assert flow.authority.owner.desired['selection_identity'].startswith('next-picker:')
    assert not flow.authority.owner.desired['file_bound']
    assert flow.actor._drain_nextep_queue()
    assert len(flow.shown) == 1 and flow.entries == []
    args, kw = flow.shown[0]
    assert args[2] == {'tmdb_id': 123} and args[3]['episode'] == 2
    assert kw['auto_select_sources'] is False
    assert kw['source_session'] is job.snapshot()[1]
    assert flow.shared.calls == before  # No second broad search at EOF.
    assert flow.authority.owner.desired['cancelled'] and job.closed.is_set()
    assert flow.native.commands == flow.native.gui_commands == []


def test_eof_reservation_precedes_even_metadata_lookup(flow, monkeypatch):
    from lib.clients.tmdb.utils import utils
    observed = []
    def check(*args):
        observed.append(flow.authority.owner.desired['selection_identity'])
        return None
    monkeypatch.setattr(utils, 'tmdb_get', check)
    flow.actor.queue_cinema_natural_end()
    assert flow.actor._cinema_picker_search.finished.wait(3)
    assert observed == ['next-picker:' + flow.parent['request_id']]
    flow.actor._drain_nextep_queue()
    assert flow.shown == [] and flow.notices


@pytest.mark.parametrize('change', ['gui', 'selection', 'stop'])
def test_late_results_cannot_reopen_after_user_intent(flow, change):
    prefetch_done(flow)
    flow.actor.queue_cinema_natural_end()
    if change == 'gui': flow.native.gui['gui_user_intent'] += 1
    elif change == 'selection': select(flow.authority, 'new-manual-source')
    else: flow.actor._cinema_cancel.set()
    flow.actor._drain_nextep_queue()
    assert flow.shown == flow.notices == [] and flow.entries == []
    assert flow.native.commands == flow.native.gui_commands == []


def test_empty_results_never_open_picker_or_start_video(flow, monkeypatch):
    monkeypatch.setattr(flow.shared.search, '_perform_search', lambda *a, **kw: [])
    prefetch_done(flow)
    flow.actor.queue_cinema_natural_end()
    flow.actor._drain_nextep_queue()
    assert flow.shown == [] and len(flow.notices) == 1
    assert not flow.authority.owner.desired['start_claimed']


def test_manual_choice_becomes_new_owner_and_old_picker_cleanup_cannot_cancel_it(flow, monkeypatch):
    prefetch_done(flow)
    flow.actor.queue_cinema_natural_end()
    def choose(*args, **kw):
        snapshot = picker.picker_status(kw['playback_context'])
        accepted = playback_request.select(snapshot, 'e' * 32, playback_request.source_identity(args[0][0]))
        assert accepted['desired']['request_id'] == 'e' * 32
        return True
    monkeypatch.setattr(flow.shared.search, 'show_source_select', choose)
    flow.actor._drain_nextep_queue()
    desired = flow.authority.owner.desired
    assert desired['request_id'] == 'e' * 32 and not desired['cancelled']
    assert desired['selection_identity'].startswith('bt:') and not desired['start_claimed']


def test_cancel_during_metadata_does_not_start_provider_work(shared, metadata, monkeypatch):
    entered, unblock = Event(), Event()
    from lib.clients.tmdb.utils import utils
    from bobbi_platform import runtime
    monkeypatch.setattr(runtime, 'call', lambda *a, **kw:
        {'account_id': '115:' + 'a' * 64, 'epoch': 1, 'authenticated': True})
    def wait(*args):
        entered.set()
        assert unblock.wait(3)
        return NS(episodes=[episode(1), episode(2)])
    monkeypatch.setattr(utils, 'tmdb_get', wait)
    job = picker.NextSourceSearch(current(), Event()).start()
    assert entered.wait(3)
    job.cancel()
    unblock.set()
    assert job.finished.wait(3)
    assert job.snapshot() is None and shared.calls == []


def test_oninit_rechecks_queued_window_before_render(monkeypatch):
    from lib.gui.source_select import SourceSelect
    closed = []
    actor = NS(_next_picker_guard={'_next_picker_context': {'request_id': 'old'}}, close=lambda: closed.append(True))
    monkeypatch.setattr(picker, 'picker_status', lambda data: None)
    SourceSelect.onInit(actor)
    assert closed == [True] and actor._next_picker_guard is None


def test_automatic_picker_cannot_downgrade_when_native_owner_disappears(monkeypatch):
    from lib.gui.source_select import SourceSelect
    from lib import native_support, portable
    monkeypatch.setattr(native_support, 'available', lambda: False)
    monkeypatch.setattr(portable, 'manual_modal', lambda *a: pytest.fail('No unguarded automatic UI'))
    actor = NS(item_information={'_next_picker_context': {'request_id': 'old'}})
    assert SourceSelect.doModal(actor) is False

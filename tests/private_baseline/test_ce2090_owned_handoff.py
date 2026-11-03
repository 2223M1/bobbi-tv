"""Real owner, run, monitor, natural/transport reservation and child bind with IO doubles."""
import ast
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import socket
from threading import Event
import time
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'addons/plugin.video.bobbi/lib/native_player.py').read_text(encoding='utf-8')
SOURCE_HASH = sha256(SOURCE.encode()).hexdigest()
METHODS = {
    'run', 'set_constants', '_activate_playback_session', '_owns_playback_session',
    '_release_playback_session', 'play_video', 'monitor', 'wait_cinema_terminal',
    'queue_cinema_natural_end', 'queue_cinema_transport_end', '_drain_nextep_queue', '_cinema_phase', 'run_error',
    'cancel_playback', '_cleanup_playback_session',
}


def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('This evidence probe must not access any network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def player_type(env, selected=METHODS, baseline=False):
    original = next(node for node in ast.parse(SOURCE).body
                    if isinstance(node, ast.ClassDef) and node.name == 'JacktookPLayer')
    body = [deepcopy(node) for node in original.body
            if isinstance(node, ast.FunctionDef) and node.name in selected]
    assert {node.name for node in body} == selected
    if baseline:
        monitor = next(node for node in body if node.name == 'monitor')
        outer = next(node for node in monitor.body if isinstance(node, ast.Try))
        final_set = next(node for node in outer.finalbody if isinstance(node, ast.If)
            and any(isinstance(child, ast.Expr) and isinstance(child.value, ast.Call)
                    and isinstance(child.value.func, ast.Attribute) and child.value.func.attr == 'set'
                    and isinstance(child.value.func.value, ast.Attribute)
                    and child.value.func.value.attr == '_cinema_cancel'
                    for child in node.body))
        final_set.test = ast.parse(
            "hasattr(self, '_cinema_cancel') and "
            "getattr(self, '_startup_failure_category', None) != 'prepared_ready'",
            mode='eval').body
    node = ast.ClassDef(name='ReviewPlayer', bases=[], keywords=[], body=body, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, str(ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'), 'exec'), env)
    result = env['ReviewPlayer']
    env['JacktookPLayer'] = result
    result._nextep_queue = []
    return result


def boundary_case(monkeypatch, tmp_path, variant, change, kind='natural'):
    no_network(monkeypatch)
    from test_playback_authority import playing, select
    from test_native_continuation_account_guard import credentials
    from bobbi_platform.account_manager import AccountManager
    from bobbi_core import playback_request as protocol
    from lib.cinema import playback_request, playback_ipc, preparation_client
    from lib.clients.tmdb import original_audio

    recovery = None
    entry = None
    if kind == 'transport':
        from test_transport_handoff_authority import setup, command, HASH, IDENTITY, SELECTED
        from bobbi_core.video_context import video_identity
        from lib.utils.player.transport_recovery import Recovery
        from lib.clients import bobi_library
        authority, native, args, accounts, account, capture = setup(tmp_path)
        grant = authority.dispatch(capture)
        assert grant['authorized']
        native.captured()
        assert authority.dispatch(command(args, account, grant, 'transport_status'))['state'] == 'CAPTURED'
        assert authority.dispatch(command(args, account, grant, 'transport_stop'))['queued']
        video = video_identity('tmdb:tv:1:s1:e1', 'c' * 64, SELECTED)
        entry = dict(title=SELECTED['torrent_path'], key='resource',
            prepared_version_key='c' * 64, prepared_source_info_hash=HASH,
            video_context=video, path='/115open/' + SELECTED['torrent_path'], bytes=1000,
            _playback_url='http://127.0.0.1:9999/fixture-never-fetched')
        parent_data = dict(selection_policy='exact', request_id=args['request_id'],
            url='plugin://plugin.video.bobbi.torrent/?action=play', mode='tv',
            info_hash=HASH, is_torrent=True, _account=account,
            ids={'tmdb_id': 1}, tv_data={'season': 1, 'episode': 1}, title='Show')
        recovery = Recovery()
        recovery.state, recovery.stop_sent = 'STOPPING', True
        recovery.token, recovery.child = grant['token'], capture['child_request_id']
        recovery.deadline = time.monotonic() + 30
        recovery.context = dict(owner=args, request_id=args['request_id'],
            account_scope=account, selection_identity='bt:' + HASH, file_identity=IDENTITY,
            data=deepcopy(parent_data), selected=deepcopy(SELECTED))
        recovery.result = dict(entry=entry, url=entry['_playback_url'])
        monkeypatch.setattr(bobi_library, 'load_prepared_index', lambda: dict(
            mount_root='/storage/videos/Clouddrive/CloudDrive', titles=[dict(sources=[entry])]))
        monkeypatch.setattr(preparation_client, 'resolve_entry', lambda *a, **kw: deepcopy(entry))
    else:
        authority, native, args = playing()
        accounts = AccountManager(tmp_path / 'fixture-accounts.json')
        account = accounts.install(credentials(), accounts.snapshot())
        authority.configure_accounts(accounts)
        parent_data = dict(selection_policy='exact', request_id=args['request_id'],
            url='plugin://plugin.video.bobbi.torrent/?action=play', mode='tv')
    parent_id = args['request_id']
    explicit = Event()
    events, opened, actors, commands = [], [], [], []
    props, aborted = {}, [False]

    def call(body, **kwargs):
        commands.append(body['operation'])
        return authority.dispatch(body)

    for module in {protocol, playback_request, playback_ipc}:
        monkeypatch.setattr(module, 'call', call)
    monkeypatch.setattr(preparation_client, 'capture_account', lambda *a, **kw: None)
    monkeypatch.setattr(preparation_client, 'prepare_fonts', lambda *a, **kw: {'state': 'none'})
    monkeypatch.setattr(original_audio, 'cached_hint', lambda *a, **kw: None)

    def settings(key, default=None):
        return True if key == 'cinema_continuity_enabled' else default

    class Item:
        def __init__(self, *args, **kwargs):
            self.properties = {}

        def setPath(self, path):
            self.path = path

        def setProperty(self, key, value):
            self.properties[key] = value

        def getVideoInfoTag(self):
            return self

        def setResumePoint(self, position, total):
            self.resume = (position, total)

    def resolved(*args):
        events.append('parent_resolution_io_double')
        if kind == 'transport':
            native.stopped()
            actors[0]._transport_recovery = recovery
            if change == 'native_error':
                native.current['reason'] = 'ERROR'
            elif change == 'native_stop':
                native.current['user_intent'] += 1
        else:
            reason = {'native_error': 'ERROR', 'native_stop': 'STOP'}.get(change, 'NATURAL_EOF')
            native.current.update(phase='TERMINAL', reason=reason, sequence=2)

    env = dict(
        deepcopy=deepcopy, re=re, json_dumps=json.dumps, uuid4=uuid4, Event=Event,
        urlsplit=urlsplit, urlunsplit=urlunsplit, parse_qsl=parse_qsl, urlencode=urlencode,
        monotonic=time.monotonic, sleep=lambda ms: None, TERMINAL_RECONCILIATION_SECONDS=3.,
        xbmc=SimpleNamespace(LOGINFO=1, LOGWARNING=2, LOGERROR=3,
            Monitor=lambda: SimpleNamespace(abortRequested=lambda: aborted[0])),
        get_setting=settings, get_property=lambda key: props.get(key, ''),
        set_property=lambda key, value: props.__setitem__(key, value),
        clear_property=lambda key: props.pop(key, None),
        kodilog=lambda message, **kw: events.append(message), notification=lambda *a, **kw: None,
        close_busy_dialog=lambda: None, close_all_dialog=lambda: None,
        make_listing=lambda data: Item(), setResolvedUrl=resolved, ADDON_HANDLE=1,
        ListItem=Item, ACTIVE_PLAYER_SESSION_PROPERTY='active', PLAYNEXT_ACTION_PROPERTY='next',
    )
    Player = player_type(env, baseline=variant == 'baseline')

    def initialize(self, on_started=None, **kwargs):
        actors.append(self)
        self.on_started, self.on_error = on_started, None
        self._provided_cancel_event = explicit if on_started else None
        self._native_instance = native.current['native_instance'] if native.current else 'original'
        self.kodi_monitor = SimpleNamespace(abortRequested=lambda: aborted[0])
        self._is_trakt_tracking_excluded = lambda: True
        self.clear_playback_properties = lambda: None
        self._check_volume = lambda: True
        self._handle_trakt_scrobble = lambda *a: None
        self._handle_simkl_scrobble = lambda: None
        self.handle_subtitles = lambda *a: None
        self._record_started_history = lambda: None
        self.handle_playback_start = lambda: True
        self.start_cinema_preparation = lambda: None
        self.select_audio_stream = lambda: None
        self.handle_subtitle_selection = lambda: None
        # Only the parent is observed. The child is checked through actual bind,
        # claim and fake media dispatch, then returns before any fabricated AV.
        self._wait_for_video_start = lambda: bool(on_started)
        self.isPlayingVideo = lambda: False
        if kind != 'transport' or not on_started:
            self.queue_cinema_transport_end = lambda budget: False
        self._check_still_watching_threshold = lambda: False
        self._cinema_fresh_next = lambda: dict(
            selection_policy='exact', url='https://fixture.invalid/next.mkv',
            mode='tv', tv_data={'season': 1, 'episode': 2}, ids={'tmdb_id': 123},
            playnext_context=True, _account=account, _next_recheck=True,
        )
        self.offer_terminal_actions = lambda: None

        def stopped():
            if not on_started:
                return
            events.append('bookkeeping')
            if change == 'ui_cancel':
                explicit.set()
            elif change == 'replacement':
                select(authority, 'new-human-choice')
            elif change == 'external_audio':
                native.epoch += 1
                native.current = None
            elif change == 'abort':
                aborted[0] = True
            elif change == 'account_logout':
                accounts.logout(account)
            elif change == 'child_cancelled':
                current = authority.owner.snapshot()
                authority.dispatch(dict(operation='cancel', boot_id=current['boot_id'],
                    epoch=current['epoch'], request_id=current['desired']['request_id']))

        self.handle_playback_stop = stopped
        self.play = lambda url, item: opened.append((url, dict(item.properties)))
        self.kill_dialog = lambda: pytest.fail('Unexpected monitor exception: ' + str(events[-3:]))

    Player.__init__ = initialize
    actor = Player(on_started=lambda: None)
    actor.run(parent_data)
    state = authority.owner.snapshot()
    outcome = dict(
        source_sha256=SOURCE_HASH, variant=variant, change=change, kind=kind,
        queued=len(Player._nextep_queue), parent_cancel=actor._cinema_cancel.is_set(),
        desired_child=state['desired']['request_id'] != parent_id,
        child_bound=state['desired']['file_bound'], child_claimed=state['desired']['start_claimed'],
        desired_cancelled=state['desired']['cancelled'], child_player_io=len(opened), actors=len(actors),
        reservations=commands.count('reserve_child'), binds=commands.count('bind_file'),
    )
    print('REVIEW HANDOFF_BOUNDARY ' + json.dumps(outcome, sort_keys=True))
    if variant == 'baseline':
        assert actor._cinema_cancel.is_set() and len(Player._nextep_queue) == 1 and len(actors) == 1
        assert state['desired']['request_id'] != parent_id and not state['desired']['file_bound']
        assert not state['desired']['start_claimed'] and not opened
        assert commands.count('reserve_child') == 1
    elif change == 'none':
        assert not actor._cinema_cancel.is_set() and not explicit.is_set()
        assert len(opened) == 1 and len(actors) == 2 and not Player._nextep_queue
        assert state['desired']['file_bound'] and state['desired']['start_claimed']
        assert commands.count('reserve_child') == 1 and commands.count('bind_file') == 1
        if kind == 'transport':
            assert actor._transport_parent_queued and not actor._cinema_natural_queued
            assert actor._terminal_reason == 'STOP' and actor.data['completed'] is False
            assert opened[0][1]['bobitv.handoff_token'] == native.handoff['token']
            assert opened[0][1]['bobitv.file_identity'] == IDENTITY
    else:
        assert not opened, 'Cancellation, replacement or abort must never dispatch a child'
        if change == 'ui_cancel':
            assert explicit.is_set(), 'Never clear the resolver/user cancellation Event'
        if change in ('native_stop', 'native_error'):
            assert commands.count('reserve_child') == 0
        if change in ('replacement', 'external_audio', 'child_cancelled'):
            assert commands.count('bind_file') == 0
        if change == 'account_logout':
            assert not state['desired']['file_bound'] and not state['desired']['start_claimed']


def multi_case(monkeypatch, change):
    """Exercise per-entry cancellation with different parent and child Events."""
    no_network(monkeypatch)
    from lib import search
    calls = []
    parent_cancel = Event()
    env = dict(kodilog=lambda *a, **kw: None, close_busy_dialog=lambda: None,
        close_all_dialog=lambda: None, clear_property=lambda *a: None,
        xbmc=SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: False)))
    Player = player_type(env, selected={'_drain_nextep_queue'})

    def initialize(self):
        self._cinema_cancel = Event()
        self._was_superseded = False
        self.kodi_monitor = SimpleNamespace(abortRequested=lambda: False)

    def run(self, data):
        calls.append(data['name'])
        if data['name'] == 'child-1':
            if change == 'child_cancel':
                self._cinema_cancel.set()
            elif change == 'child_superseded':
                self._was_superseded = True

    Player.__init__, Player.run = initialize, run
    parent = Player()
    parent._cinema_cancel = parent_cancel
    parent._cinema_phase = lambda *a: None
    parent.PLAYLIST = SimpleNamespace(clear=lambda: None)
    monkeypatch.setattr(search, 'show_next_sources', lambda data: False)
    if change == 'manual_picker_cancel':
        Player._nextep_queue = [
            {'data': {'name': 'picker'}, 'results': [object()]},
            {'data': {'name': 'should-not-run'}},
        ]
    else:
        Player._nextep_queue = [
            {'data': {'name': 'child-1'}}, {'data': {'name': 'should-not-run'}},
        ]
    parent._drain_nextep_queue()
    print('REVIEW MULTI_ENTRY ' + json.dumps(dict(source_sha256=SOURCE_HASH,
        change=change, calls=calls, parent_cancel=parent_cancel.is_set()), sort_keys=True))
    assert 'should-not-run' not in calls, 'Current child/picker cancellation must end the drain'


@pytest.mark.parametrize('variant,change', [('baseline', 'none')] + [
    ('current', value) for value in (
        'none', 'ui_cancel', 'abort', 'replacement', 'external_audio',
        'native_error', 'native_stop', 'child_cancelled', 'account_logout')])
@pytest.mark.parametrize('kind', ['natural', 'transport'])
def test_owned_handoff_boundary(monkeypatch, tmp_path, variant, change, kind):
    boundary_case(monkeypatch, tmp_path, variant, change, kind)


@pytest.mark.parametrize('change', ['manual_picker_cancel', 'child_cancel', 'child_superseded'])
def test_owned_handoff_queue_cancellation(monkeypatch, change):
    multi_case(monkeypatch, change)

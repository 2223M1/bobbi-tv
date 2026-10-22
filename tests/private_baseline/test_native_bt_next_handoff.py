"""Actual native add-on EOF consumer, with only service/owner IO substituted."""
import ast
from copy import deepcopy
from pathlib import Path
import re
from threading import Event
from types import MethodType, SimpleNamespace
from uuid import uuid4

import pytest

from bobbi_core import preparation_client
from lib.clients import bobi_library
from lib.cinema import playback_request
from test_bt_next_continuity import proved


@pytest.fixture
def native(proved, monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(row for row in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(row, ast.ClassDef) and row.name == 'JacktookPLayer')
    names = {'_cinema_fresh_next', 'queue_cinema_natural_end'}
    nodes = [row for row in cls.body if isinstance(row, ast.FunctionDef) and row.name in names]
    queued, messages, commands = [], [], []
    env = dict(deepcopy=deepcopy, re=re, uuid4=uuid4,
        xbmc=SimpleNamespace(LOGINFO=1, LOGWARNING=2), kodilog=lambda *a, **kw: None,
        notification=lambda *a, **kw: messages.append(a), JacktookPLayer=SimpleNamespace(_nextep_queue=queued))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
    owner = [True]
    actor = SimpleNamespace(data=deepcopy(proved.current), playback_session_id=proved.current['request_id'],
        _cinema_cancel=Event(), _cinema_end=True, _cinema_natural_queued=False, _native_instance='native',
        _owner_context=dict(boot_id='boot', epoch=1, request_id=proved.current['request_id']),
        _cinema_next_data={'url': 'magnet:?cached-before-ready'}, _owns_playback_session=lambda: owner[0],
        _check_still_watching_threshold=lambda: False)
    for name in names:
        setattr(actor, name, MethodType(env[name], actor))
    granted = [False]
    def call(body):
        commands.append(deepcopy(body))
        assert body['account_scope'] == proved.current['_account']
        if body['operation'] == 'authorize_next':
            if granted[0]: return {'authorized': False}
            granted[0] = True
            return {'authorized': True, 'token': 'one-use'}
        assert body['operation'] == 'reserve_child'
        assert body['token'] == 'one-use'
        return dict(boot_id='boot', epoch=2, desired={'request_id': body['child_request_id'], 'cancelled': False})
    monkeypatch.setattr(playback_request, 'call', call)
    monkeypatch.setattr(bobi_library, 'load_prepared_index', lambda: deepcopy(proved.index))
    monkeypatch.setattr(preparation_client, 'resolve_entry', lambda data, index, entry, *a, **kw: entry)
    return SimpleNamespace(actor=actor, queued=queued, commands=commands, owner=owner,
                           messages=messages, call=call)


def test_eof_upgrades_cached_bt_to_fresh_ready_115_before_one_use_reservation(native, proved):
    native.actor.queue_cinema_natural_end()
    native.actor.queue_cinema_natural_end()
    assert [row['operation'] for row in native.commands] == ['authorize_next', 'reserve_child']
    assert len(native.queued) == 1
    result = native.queued[0]['data']
    assert result['_next_transport'] == '115'
    assert result['prepared_resource_id'] == proved.entry['key']
    assert result['_ui_reserved_request'] == result['request_id']
    assert native.actor._cinema_natural_queued


def test_explicit_cloud_unavailability_can_reserve_only_the_proved_bt_tuple(native, proved, monkeypatch):
    monkeypatch.setattr(preparation_client, 'resolve_entry', lambda *a, **kw: None)
    native.actor.queue_cinema_natural_end()
    result = native.queued[0]['data']
    assert result['_next_transport'] == 'bt'
    assert result['_bt_next_selected'] == proved.proof['next']['video_context']['selected']
    assert native.commands[-1]['selection_identity'] == 'bt:' + result['info_hash']


@pytest.mark.parametrize('failure', [FileNotFoundError, ValueError])
def test_missing_or_corrupt_cloud_index_still_allows_service_proved_bt(native, monkeypatch, failure):
    def load(): raise failure('fixture unavailable projection')
    monkeypatch.setattr(bobi_library, 'load_prepared_index', load)
    native.actor.queue_cinema_natural_end()
    assert native.queued[0]['data']['_next_transport'] == 'bt'


def test_no_service_proof_cannot_reserve_cached_bt(native, proved, monkeypatch):
    monkeypatch.setattr(bobi_library, 'load_prepared_index', lambda: {'titles': []})
    proved.status['result'] = {}
    native.actor.queue_cinema_natural_end()
    assert native.commands == native.queued == []


@pytest.mark.parametrize('change', ['selection', 'cancel', 'account'])
def test_final_fresh_io_cannot_override_new_selection_cancel_or_account(native, proved, monkeypatch, change):
    original_call = preparation_client.call
    changed = [False]
    def call(method, body, **kwargs):
        if method == 'ping' and changed[0]: raise RuntimeError('ACCOUNT_CHANGED')
        return original_call(method, body, **kwargs)
    def resolve(*args, **kwargs):
        if change == 'selection': native.owner[0] = False
        elif change == 'cancel': native.actor._cinema_cancel.set()
        else: changed[0] = True
        return proved.entry
    monkeypatch.setattr(preparation_client, 'call', call)
    monkeypatch.setattr(preparation_client, 'resolve_entry', resolve)
    native.actor.queue_cinema_natural_end()
    assert native.commands == native.queued == []


def test_lost_child_reservation_reply_is_not_replayed_or_enqueued(native, monkeypatch):
    def call(body):
        result = native.call(body)
        if body['operation'] == 'reserve_child': raise OSError('lost acknowledgement')
        return result
    monkeypatch.setattr(playback_request, 'call', call)
    native.actor.queue_cinema_natural_end()
    native.actor.queue_cinema_natural_end()
    assert len([row for row in native.commands if row['operation'] == 'reserve_child']) == 1
    assert native.queued == []


def test_smooth_current_does_not_trigger_continuation_without_actual_eof(native):
    native.actor._cinema_end = False
    native.actor.queue_cinema_natural_end()
    assert native.commands == native.queued == []

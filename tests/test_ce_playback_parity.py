"""Execute production player methods against real local admission, without Kodi or network.

AST extraction avoids importing the whole UI/debrid stack; the method bodies
are compiled unchanged from native_player.py, not reimplemented by fixtures.
This is local contract coverage, not an AV or device acceptance claim.
"""
import ast
import json
from pathlib import Path
import re
import sys
from threading import Event
from types import MethodType, ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import preparation_client, direct_cloud_client
from bobbi_core.account_readiness import AccountReadiness
from bobbi_core.ledger import Ledger
from bobbi_core.preparation_intake import Intake
from bobbi_core.preparation_host import Session, Lease
from test_accounts import logged_in


@pytest.fixture
def parity(tmp_path, monkeypatch):
    clock, logs, notices = [1000.0], [], []
    accounts, scope = logged_in(tmp_path)
    ledger = Ledger(tmp_path / 'resources.sqlite')
    session = object.__new__(Session)
    session.lease = Lease(accounts, scope)
    session.readiness = AccountReadiness('fixture', clock=lambda: clock[0])
    session.intake = Intake(ledger)
    intent = dict(request_id='a' * 32, purpose='current',
        media=dict(tmdb_id=1, kind='movie', season=0, episode=0, anime=False,
                   title='Fixture', release_title='Fixture.2025'),
        selected=dict(source_info_hash='b' * 40, torrent_file_id=1,
                      torrent_path='Fixture.2025.mkv', torrent_file_bytes=1000))
    source = ast.parse((ROOT / 'addons/plugin.video.bobbi/lib/native_player.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    names = {'start_cinema_preparation', 'start_direct_preparation', '_preparation_diagnostic'}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    env = dict(monotonic=lambda: clock[0], loads=json.loads, re=re, Thread=InlineThread,
        get_property=lambda key: '', kodilog=lambda value, **kw: logs.append(value),
        notification=lambda value, **kw: notices.append(value),
        xbmc=SimpleNamespace(LOGWARNING=2, LOGINFO=1))
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'), 'exec'), env)
    player = SimpleNamespace(data={'selection_policy': 'exact'}, _cinema_cancel=Event(),
        playback_session_id=intent['request_id'], current=True)
    player._owns_playback_session = lambda: player.current
    for name in names:
        setattr(player, name, MethodType(env[name], player))
    for name in ('lib', 'lib.cinema'):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, ModuleType(name))
    monkeypatch.setitem(sys.modules, 'lib.cinema.preparation_client', preparation_client)
    monkeypatch.setattr(preparation_client, 'source_intent', lambda *args: intent)
    monkeypatch.setattr(preparation_client, 'advance_intent', lambda *args: None)
    calls = []
    def call(method, body):
        calls.append((method, dict(body)))
        return session.dispatch(method, body)
    monkeypatch.setattr(preparation_client, 'call', call)
    result = SimpleNamespace(player=player, session=session, accounts=accounts, scope=scope,
        ledger=ledger, clock=clock, logs=logs, notices=notices, calls=calls, call=call, intent=intent)
    try:
        yield result
    finally:
        ledger.close()


def retry(value, direct=False):
    value.clock[0] = getattr(value.player, '_direct_prepare_due' if direct else '_cinema_prepare_due')
    (value.player.start_direct_preparation if direct else value.player.start_cinema_preparation)()


def test_cd2_unverified_still_accepts_exact_local_intent_and_does_not_submit_cloud(parity):
    p = parity
    p.player.start_cinema_preparation()
    assert p.player._cinema_prepare_sent and p.player._cinema_prepare_ticket == p.intent['request_id']
    assert p.session.intake.status(p.intent['request_id'])['state'] == 'queued'
    assert [c[0] for c in p.calls] == ['prepare']
    assert p.ledger.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 0
    assert not p.session.readiness.ready


def test_lost_acceptance_receipt_is_recovered_by_status_without_second_intake(parity, monkeypatch):
    p = parity
    def transport(method, body):
        result = p.call(method, body)
        if method == 'prepare':
            raise OSError('fixture reply lost after local commit')
        return result
    monkeypatch.setattr(preparation_client, 'call', transport)
    p.player.start_cinema_preparation()
    assert not getattr(p.player, '_cinema_prepare_sent', False)
    retry(p)
    assert p.player._cinema_prepare_sent
    assert [c[0] for c in p.calls] == ['prepare', 'status']
    assert p.ledger.db.execute('SELECT COUNT(*) FROM preparation_intents').fetchone()[0] == 1


def test_explicit_absent_allows_same_idempotent_intent_after_lost_request(parity, monkeypatch):
    p, first = parity, [True]
    def transport(method, body):
        if first[0]:
            first[0] = False
            p.calls.append((method, dict(body)))
            raise OSError('fixture request never arrived')
        return p.call(method, body)
    monkeypatch.setattr(preparation_client, 'call', transport)
    p.player.start_cinema_preparation()
    retry(p)
    assert p.player._cinema_prepare_sent
    assert [c[0] for c in p.calls] == ['prepare', 'status', 'prepare']
    assert p.calls[0][1] == p.calls[2][1] == p.intent


@pytest.mark.parametrize('invalid', [{}, {'state': 'unavailable'},
    {'request_id': 'b' * 32, 'state': 'queued'}, {'request_id': 'a' * 32, 'state': 'absent'}])
def test_invalid_acceptance_never_latches_sent_or_ticket(parity, monkeypatch, invalid):
    monkeypatch.setattr(preparation_client, 'call', lambda *args: invalid)
    parity.player.start_cinema_preparation()
    assert not getattr(parity.player, '_cinema_prepare_sent', False)
    assert not getattr(parity.player, '_cinema_prepare_ticket', None)


@pytest.mark.parametrize('status', ['timeout', 'empty', 'none', 'unavailable', 'wrong_id'])
def test_unknown_status_never_blindly_replays_and_exhaustion_is_visible(parity, monkeypatch, status):
    p, called = parity, []
    def transport(method, body):
        called.append(method)
        if method == 'prepare' or status == 'timeout':
            raise OSError('fixture uncertain IPC')
        return {'empty': {}, 'none': None, 'unavailable': {'state': 'unavailable'},
                'wrong_id': {'request_id': 'b' * 32, 'state': 'absent'}}[status]
    monkeypatch.setattr(preparation_client, 'call', transport)
    p.player.start_cinema_preparation()
    for _ in range(7):
        retry(p)
    assert called == ['prepare'] + ['status'] * 5
    assert not getattr(p.player, '_cinema_prepare_sent', False)
    assert len(p.notices) == 1 and '重新选择同片源可重试' in p.notices[0]


@pytest.mark.parametrize('operation', ['subtitle', 'font_preflight'])
def test_cached_subtitle_and_font_local_lane_survive_cd2_outage(parity, operation):
    p, calls = parity, []
    p.session.subtitles = SimpleNamespace(for_playback=lambda body: calls.append(body) or {'state': 'ready'})
    p.session.font_cache = True
    p.session.font_preflight = SimpleNamespace(request=lambda body: calls.append(body) or {'state': 'pending'})
    result = p.session.dispatch(operation, {'fixture': True})
    assert result['state'] in ('ready', 'pending')
    if operation == 'subtitle':
        assert result['account_scope'] == p.scope and result['account_scope'] is not p.scope
    assert calls == [{'fixture': True}]
    p.accounts.logout(p.scope)
    with pytest.raises(RuntimeError, match='REVOKED'):
        p.session.dispatch(operation, {'fixture': True})
    assert len(calls) == 1


def test_cloud_resolution_remains_blocked_while_dependency_unverified(parity):
    for operation in ('resolve', 'catalog_resolve'):
        assert parity.session.dispatch(operation, {})['reason'] == 'cloud_dependency_not_ready'


@pytest.mark.parametrize('playing', [False, True])
def test_local_font_warming_remains_idle_only_and_independent_of_cd2(parity, playing):
    session, calls = parity.session, []
    session.playing_probe = lambda:playing
    session.protection_lane = SimpleNamespace(tick=lambda:None)
    session.font_preflight = SimpleNamespace(tick=lambda:None)
    def resolve_tick(**kwargs):
        assert kwargs == dict(allow_submit=False)
    session.resolve_lane = session.direct_resolve = SimpleNamespace(tick=resolve_tick)
    session.future = None
    session.readiness = SimpleNamespace(begin=lambda:False, ready=False)
    session.next_fonts = 0
    session.font_cache = SimpleNamespace(next_byte_action=lambda:'local-font', warm_bytes=lambda *a:None)
    session._submit = lambda *args:calls.append(args)
    session.tick()
    assert len(calls) == (0 if playing else 1)
    if not playing:
        assert calls[0][0:2] == ('font_bytes', 'local-font')
        assert calls[0][-1]() is True
        parity.accounts.logout(parity.scope)
        assert calls[0][-1]() is False


def direct_setup(p, monkeypatch):
    from bobbi_core.direct_cloud import DirectQueue, source_key
    body = dict(request_id='a' * 32,
        source=dict(provider='mdsub', guid='mdsub:' + 'b' * 64,
            locator='https://pan.mdsub.top/api/raw?fixture', title='Fixture.mkv', size=16384),
        media=dict(tmdb_id=1, kind='movie', season=0, episode=0))
    root = p.ledger.path.parent
    queue = DirectQueue(root / 'direct.sqlite', root / 'direct.json', 'account', '/115open/fixture',
                       SimpleNamespace(perform=lambda *args: pytest.fail('No cloud IO')))
    p.session.direct_queue = queue
    monkeypatch.setattr(direct_cloud_client, 'intent', lambda data: body)
    return queue, source_key(body)


def test_direct_intake_is_idempotent_and_available_before_cd2_health(parity, monkeypatch):
    p = parity
    queue, key = direct_setup(p, monkeypatch)
    try:
        p.player.start_direct_preparation()
        assert p.player._direct_prepare_sent
        assert queue.status(key)['state'] == 'queued'
        assert queue.db.execute('SELECT COUNT(*) FROM direct_jobs').fetchone()[0] == 1
        assert [c[0] for c in p.calls] == ['catalog_prepare']
    finally:
        queue.close()


@pytest.mark.parametrize('status', ['unavailable', 'none', 'empty', 'wrong_key', 'timeout'])
def test_direct_unknown_receipt_only_queries_status_then_reports_retry(parity, monkeypatch, status):
    p = parity
    queue, key = direct_setup(p, monkeypatch)
    calls = []
    def unavailable(method, body):
        calls.append(method)
        if status == 'timeout':
            raise OSError('fixture uncertain IPC')
        return {'unavailable': {'state': 'unavailable'}, 'none': None,
                'empty': {}, 'wrong_key': {'key':'wrong', 'state':'absent'}}[status]
    monkeypatch.setattr(preparation_client, 'call', unavailable)
    try:
        p.player.start_direct_preparation()
        for _ in range(7):
            retry(p, direct=True)
        assert not getattr(p.player, '_direct_prepare_sent', False)
        assert calls == ['catalog_prepare'] + ['catalog_status'] * 5
        assert len(p.notices) == 1 and '重新选择同片源可重试' in p.notices[0]
        assert queue.status(key)['state'] == 'absent'
    finally:
        queue.close()


def test_non_catalog_playback_does_not_consume_direct_retry_budget_or_notify(parity, monkeypatch):
    monkeypatch.setattr(direct_cloud_client, 'intent', lambda data: None)
    parity.player.start_direct_preparation()
    for _ in range(7):
        retry(parity, direct=True)
    assert getattr(parity.player, '_direct_prepare_attempts', 0) == 0
    assert not parity.notices and not parity.calls


@pytest.mark.parametrize('accepted', [True, False])
def test_direct_lost_receipt_recovers_or_reaccepts_only_explicit_absence(parity, monkeypatch, accepted):
    p, first = parity, [True]
    queue, key = direct_setup(p, monkeypatch)
    def transport(method, body):
        if first[0]:
            first[0] = False
            if accepted:
                p.call(method, body)
            else:
                p.calls.append((method, dict(body)))
            raise OSError('fixture lost receipt or request')
        return p.call(method, body)
    monkeypatch.setattr(preparation_client, 'call', transport)
    try:
        p.player.start_direct_preparation()
        assert not getattr(p.player, '_direct_prepare_sent', False)
        retry(p, direct=True)
        assert p.player._direct_prepare_sent and queue.status(key)['state'] == 'queued'
        assert queue.db.execute('SELECT COUNT(*) FROM direct_jobs').fetchone()[0] == 1
        assert [c[0] for c in p.calls] == ['catalog_prepare', 'catalog_status'] + ([] if accepted else ['catalog_prepare'])
        if not accepted:
            assert p.calls[0][1] == p.calls[2][1]
    finally:
        queue.close()

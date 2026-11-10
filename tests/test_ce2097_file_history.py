"""Real atomic persistence and fake provider/Kodi history, not device playback."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.file_ref import from_selected, validate, same_file
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_history import prepare_history_play, history_summary
from bobbi_platform.pan_service import PanService
from bobbi_platform.standard_session import StandardSession
from test_ce2096_pan_accounts import saved


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


history = module('file_history_subject', 'addons/plugin.video.bobbi/lib/db/file_history.py')
submission = module('history_submission_subject', 'addons/plugin.video.bobbi/lib/services/playback_history.py')
ACCOUNT = dict(provider='quark', account_id='quark:' + 'a' * 64, epoch=1, authenticated=True)
FILE = dict(file_id='f1', name='My video.mkv', size=100, directory=False)


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(tmp_path), mkdirs=lambda _: None))
    monkeypatch.setitem(sys.modules, 'lib.jacktook.utils', SimpleNamespace(kodilog=lambda *a: None))
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', SimpleNamespace(ADDON_ID='plugin.video.bobbi'))
    storage = module('file_history_database_subject', 'addons/plugin.video.bobbi/lib/db/pickle_db.py')
    return storage, tmp_path


def playback(context, sequence=1, reason='STOP', position=97):
    return dict(_pan_file=True, _file_history=context, _file_history_sequence=sequence,
        current_time=position, total_time=100, terminal_reason=reason,
        url='http://127.0.0.1/stream/SECRET/video.mkv', selected={'Cookie': 'SECRET'},
        nested={'Authorization': 'SECRET', 'token': 'SECRET'}, ticket='SECRET')


def test_identity_separates_accounts_drives_and_files_but_not_membership_or_epoch():
    ref = from_selected(ACCOUNT, FILE, '0')
    assert from_selected(dict(ACCOUNT, epoch=7), dict(FILE, source_id='other'), 'other')['id'] == ref['id']
    assert from_selected(dict(ACCOUNT, account_id='quark:' + 'b' * 64), FILE, '0')['id'] != ref['id']
    assert from_selected(ACCOUNT, dict(FILE, file_id='f2'), '0')['id'] != ref['id']
    aliyun = dict(ACCOUNT, provider='aliyun', account_id='aliyun:' + 'a' * 64)
    a = from_selected(aliyun, dict(FILE, file_id='drive1:f', content_hash='hash'), 'drive1:root')
    b = from_selected(aliyun, dict(FILE, file_id='drive2:f', content_hash='hash'), 'drive2:root')
    assert a['id'] != b['id'] and a['namespace'] == 'drive1'
    assert same_file(ref, from_selected(ACCOUNT, dict(FILE, name='renamed.mkv'), '0'))
    assert not same_file(ref, from_selected(ACCOUNT, dict(FILE, size=101), '0'))
    with pytest.raises(ValueError): validate(dict(ref, token='SECRET'))


def test_real_bytes_restart_and_whitelist_do_not_store_streams_or_secrets(database):
    storage, path = database
    db = storage.PickleDatabase()
    db.set_item('jt:lfh', 'legacy', {'title': 'Legacy'})
    files = history.FileHistory(db, clock=lambda: 100)
    context = files.begin(from_selected(ACCOUNT, FILE, '0'))
    assert files.save(playback(context)) is True
    raw = (path / 'database.pickle').read_bytes()
    assert b'SECRET' not in raw and b'127.0.0.1' not in raw and b'Cookie' not in raw
    restarted = history.FileHistory(storage.PickleDatabase())
    row = restarted.get(context['file_ref']['id'])
    assert row['position'] == 97 and row['completion_reason'] == 'STOP'
    assert row['file_ref']['fingerprint'] is None
    assert len(restarted.rows()) == 1
    assert db.get_key_checked('jt:lfh') == {'legacy': {'title': 'Legacy'}}
    assert set(pickle.loads(raw)[history.KEY][row['id']]) == history.FIELDS


def test_atomic_generation_and_sequence_reject_delayed_old_writer(database):
    storage, _ = database
    old = history.FileHistory(storage.PickleDatabase())
    new = history.FileHistory(storage.PickleDatabase())
    ref = from_selected(ACCOUNT, FILE, '0')
    one = old.begin(ref)
    assert old.save(playback(one, sequence=1, position=30))
    two = new.begin(ref)
    assert two['generation'] == one['generation'] + 1
    assert new.save(playback(two, sequence=2, position=40))
    assert old.save(playback(one, sequence=99, reason='NATURAL_EOF', position=100))
    assert new.save(playback(two, sequence=1, position=5))
    assert history.FileHistory(storage.PickleDatabase()).get(ref['id'])['position'] == 40
    # A legitimate terminal snapshot after owner handoff still persists when
    # no newer session of THIS exact file has superseded its generation.
    assert new.save(playback(two, sequence=3, reason='NATURAL_EOF', position=100))
    assert new.rows() == []


def test_network_error_at_97_is_not_completed_and_failed_disk_keeps_old_bytes(database, monkeypatch):
    storage, path = database
    files = history.FileHistory(storage.PickleDatabase())
    context = files.begin(from_selected(ACCOUNT, FILE, '0'))
    assert files.save(playback(context, reason='ERROR'))
    assert files.rows()[0]['position'] == 97
    before = (path / 'database.pickle').read_bytes()
    monkeypatch.setattr(storage, '_atomic_save', lambda *a: (_ for _ in ()).throw(OSError('fixture')))
    assert files.save(playback(context, sequence=2, position=99)) is False
    assert (path / 'database.pickle').read_bytes() == before
    assert history.FileHistory(storage.PickleDatabase()).rows()[0]['position'] == 97


def test_unknown_schema_not_rewritten_and_invalid_context_does_not_serialize(database):
    storage, path = database
    ref = from_selected(ACCOUNT, FILE, '0')
    db = storage.PickleDatabase()
    db.set_item(history.KEY, ref['id'], {'version': 99})
    before = (path / 'database.pickle').read_bytes()
    files = history.FileHistory(db)
    assert files.begin(ref) is None
    assert not files.save(playback({'file_ref': ref, 'token': 'SECRET'}))
    assert (path / 'database.pickle').read_bytes() == before


@pytest.fixture
def service(tmp_path):
    service = PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}))
    expected = service.accounts.install(saved(), service.accounts.snapshot('quark'))
    state = SimpleNamespace(items=[deepcopy(FILE)], calls=0)
    def listing(parent, page, size):
        state.calls += 1
        return dict(items=deepcopy(state.items), page=page, has_more=False)
    service.client_factory = lambda *a: SimpleNamespace(list_files=listing)
    yield service, expected, state
    service.close()


def test_history_rechecks_remote_after_restart_and_mints_one_use_ticket(service):
    owner, expected, state = service
    ref = from_selected(expected, FILE, '0')
    owner.directory_cache.clear()
    result = prepare_history_play(owner, {'file_ref': ref}, 'a' * 32)
    assert result == {'ticket': 'a' * 32} and state.calls == 1
    claimed = owner.claim_play(result['ticket'])
    assert claimed['selected'] == FILE and claimed['file_ref'] == ref
    with pytest.raises(PanError, match='PLAY_EXPIRED'): owner.claim_play(result['ticket'])


@pytest.mark.parametrize('change', ['deleted', 'size', 'account', 'cancelled'])
def test_history_never_substitutes_same_name_or_old_account(service, change):
    owner, expected, state = service
    ref = from_selected(expected, FILE, '0')
    if change == 'deleted': state.items = [dict(FILE, file_id='other')]
    if change == 'size': state.items = [dict(FILE, size=101)]
    if change == 'account': owner.accounts.install(saved(uid='other-user'), expected)
    if change == 'cancelled': owner.close_stream(expected, 'b' * 32)
    with pytest.raises(PanError): prepare_history_play(owner, {'file_ref': ref}, 'b' * 32)
    assert not owner.play_tickets


def test_same_account_new_epoch_keeps_identity_and_checks_new_scope(service):
    owner, expected, state = service
    ref = from_selected(expected, FILE, '0')
    latest = owner.accounts.install(saved(session='new-login'), expected)
    assert latest['epoch'] != expected['epoch']
    prepare_history_play(owner, {'file_ref': ref}, 'c' * 32)
    assert owner.claim_play('c' * 32)['account'] == latest


def test_logged_out_history_has_explicit_reauthorize_error(service):
    owner, expected, state = service
    ref = from_selected(expected, FILE, '0')
    owner.accounts.logout(expected)
    with pytest.raises(PanError, match='PAN_LOGIN_REQUIRED'):
        prepare_history_play(owner, {'file_ref': ref}, '6' * 32)
    assert not owner.play_tickets and state.calls == 0


def test_standard_and_native_snapshot_sequence_retains_real_terminal_reason():
    data = dict(_pan_file=True, request_id='d' * 32, url='https://example.test/video.mkv',
                _account=ACCOUNT, selection_policy='exact', ids={}, mode='file', title='Video')
    snapshots = []
    accounts = SimpleNamespace(require_current=lambda *a, **k: None, is_current=lambda *a: True)
    session = StandardSession(accounts, history=snapshots.append)
    session.select(data['request_id'], ACCOUNT)
    session.register(data['request_id'], data)
    session.observe(data['request_id'], data['url'], 97, 100)
    session.terminal(data['request_id'], 'ERROR')
    assert [s['_file_history_sequence'] for s in snapshots] == [1, 2]
    assert snapshots[-1]['terminal_reason'] == 'ERROR' and snapshots[-1]['completed'] is False
    native = dict(data)
    first = submission.snapshot(native, 'STARTED')
    last = submission.snapshot(native, 'NATURAL_EOF')
    assert first['_file_history_sequence'] == 1 and last['_file_history_sequence'] == 2
    assert last['completed'] is True and first['completed'] is False


def test_native_full_existing_lane_never_blocks_on_synchronous_file_write(monkeypatch):
    calls, logs = [], []
    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(
        set_watched_file=lambda data: calls.append(data)))
    monkeypatch.setitem(sys.modules, 'lib.db.deferred_history', SimpleNamespace(defer_watched_file=lambda data: False))
    monkeypatch.setitem(sys.modules, 'lib.jacktook.utils', SimpleNamespace(kodilog=logs.append))
    assert submission.submit_native(dict(_pan_file=True), reason='STOP') is False
    assert calls == [] and logs == ['[FILE-HISTORY] HISTORY_QUEUE_FULL']


def test_history_revalidation_budget_and_cancel_during_listing_publish_no_ticket(service):
    owner, expected, state = service
    ref = from_selected(expected, FILE, '0')
    calls = []
    def cancelled_listing(parent, page, size):
        owner.cancel_operation(expected, 'e' * 32)
        return dict(items=[FILE], page=page, has_more=False)
    owner.client_factory = lambda *a: SimpleNamespace(list_files=cancelled_listing)
    with pytest.raises(PanError, match='CANCELLED'):
        prepare_history_play(owner, {'file_ref': ref}, 'e' * 32)
    assert not owner.play_tickets
    def endless(parent, page, size):
        calls.append(page)
        return dict(items=[dict(FILE, file_id='other')], page=page, has_more=True)
    owner.client_factory = lambda *a: SimpleNamespace(list_files=endless)
    with pytest.raises(PanError, match='BUDGET_EXHAUSTED'):
        prepare_history_play(owner, {'file_ref': ref}, 'f' * 32)
    assert len(calls) == 8 and not owner.play_tickets


def test_unmatched_file_restart_reissues_stream_and_restores_only_stable_progress(database):
    storage, root = database
    owners, urls = [], []
    def create_owner():
        owner = PanService(root, SimpleNamespace(snapshot=lambda: {}))
        owners.append(owner)
        def resolve(selected):
            urls.append('https://download.quark.cn/file?secret=rotating-%d' % len(urls))
            return dict(url=urls[-1], original=True, size=100, headers={'User-Agent': 'fixture'})
        owner.client_factory = lambda *a: SimpleNamespace(resolve_original=resolve,
            list_files=lambda *a, **k: dict(items=[deepcopy(FILE)], page=1, has_more=False))
        return owner
    try:
        first = create_owner()
        expected = first.accounts.install(saved(), first.accounts.snapshot('quark'))
        first.list_files(expected, '0', 1)
        ticket = first.prepare_play(expected, FILE)['ticket']
        selected = first.claim_play(ticket)
        files = history.FileHistory(storage.PickleDatabase())
        context = files.begin(selected['file_ref'])
        old_stream = first.open_stream(expected, selected['selected'], ticket)
        assert files.save(dict(playback(context, position=42), ids={}, mode='file', url=old_stream['url']))
        first.close()

        second = create_owner()  # No directory, ticket, URL or owner state survived.
        restarted = history.FileHistory(storage.PickleDatabase())
        row = restarted.get(selected['file_ref']['id'])
        assert row['position'] == 42 and not second.directory_cache and not second.play_tickets
        reply = prepare_history_play(second, row, '7' * 32)
        fresh = second.claim_play(reply['ticket'])
        fresh_context = restarted.begin(fresh['file_ref'])
        new_stream = second.open_stream(fresh['account'], fresh['selected'], reply['ticket'])
        assert new_stream['url'] != old_stream['url'] and urls[0] != urls[1]
        assert fresh_context['file_ref']['id'] == context['file_ref']['id']
        assert fresh_context['generation'] == context['generation'] + 1
        assert restarted.get(row['id'])['position'] == 42
        raw = (root / 'database.pickle').read_bytes()
        assert b'secret=' not in raw and b'127.0.0.1' not in raw and b'/stream/' not in raw
    finally:
        for owner in owners:
            owner.close()


def test_phone_history_summary_current_account_only_paginated_readonly_and_no_locators(database, service):
    storage, path = database
    owner, expected, state = service
    files = history.FileHistory(storage.PickleDatabase())
    for number in range(7):
        selected = dict(FILE, file_id='private-%d' % number, name='🎬' * 300 + '.mkv')
        context = files.begin(from_selected(expected, selected, 'private-parent'))
        assert files.save(playback(context, position=number + 1))
    other = files.begin(from_selected(dict(expected, account_id='quark:' + 'f' * 64), FILE, 'private-other'))
    assert files.save(playback(other))
    legacy = storage.PickleDatabase()
    legacy.set_item('jt:lfh', 'Private legacy', {'url': 'SECRET', '_account': expected})
    before = (path / 'database.pickle').read_bytes()
    first = history_summary(owner, expected, history=files)
    second = history_summary(owner, expected, offset=first['next_offset'], history=files)
    assert len(first['items']) == 5 and len(second['items']) == 2 and second['next_offset'] is None
    assert len({row['id'] for row in first['items'] + second['items']}) == 7
    assert all(set(row) == {'id', 'name', 'position', 'duration', 'updated_at', 'completion_reason'}
               and len(row['name']) == 240 for row in first['items'])
    encoded = json.dumps(first, ensure_ascii=False)
    assert not any(secret in encoded for secret in ('SECRET', 'private-parent', 'private-', 'account_id', 'file_ref', 'selected'))
    assert (path / 'database.pickle').read_bytes() == before and state.calls == 0
    owner.accounts.logout(expected)
    with pytest.raises(PanError): history_summary(owner, expected, history=files)


def test_phone_history_summary_late_account_change_cannot_publish(service):
    owner, expected, state = service
    def changed():
        owner.accounts.logout(expected)
        return []
    with pytest.raises(PanError, match='ACCOUNT_CHANGED'):
        history_summary(owner, expected, history=SimpleNamespace(rows=changed))


@pytest.mark.parametrize('offset,limit', [(-1, 5), (0, 6), (True, 1), (501, 1), (0, False)])
def test_phone_history_summary_rejects_unbounded_query_before_storage(service, offset, limit):
    owner, expected, state = service
    with pytest.raises(ValueError, match='CATALOG_PAGE_INVALID'):
        history_summary(owner, expected, offset, limit,
                        history=SimpleNamespace(rows=lambda: pytest.fail('Invalid query must not read storage')))

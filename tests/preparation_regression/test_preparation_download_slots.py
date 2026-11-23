"""Real SQLite contracts for cloud-download slots vs retained verification."""
import json
import sqlite3

import pytest

from bobbi_core.ledger import Ledger
from bobbi_core.preparation import PreparationQueue


@pytest.fixture(autouse=True)
def real_sqlite(monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', sqlite3.dbapi2.connect)


@pytest.fixture
def state(tmp_path):
    clock = [1000.0]
    with Ledger(tmp_path / 'local.sqlite', now=lambda: clock[0]) as ledger:
        yield PreparationQueue(ledger), clock


def request(letter='a', episode=1, account='test-account'):
    return dict(provider='115', account=account, destination='/115open/test',
        source_info_hash=letter * 40, media_id='tmdb:tv:123:s1:e' + str(episode),
        version_key='release-' + letter, bytes_required=1000, purpose='current')


def create(q, letter='a', episode=1, account='test-account'):
    return q.request(request(letter, episode, account))['task_id']


def observation(q, task, state='finished'):
    row = q.status(task)
    return dict(account=row['account'], destination=row['destination'],
        source_info_hash=row['source_hash'], state=state, file_id='root', parent_id='parent')


def setup(q, letter='a', state='mapping'):
    task = create(q, letter)
    assert q.begin_submission(task, 100000, 90000)
    if state == 'submitting':
        return task
    q.submitted(task, state != 'uncertain')
    if state not in ('submitted', 'uncertain'):
        q.observe(task, observation(q, task, 'finished' if state in ('mapping', 'checking') else state))
        if state == 'checking':
            q.db.execute("UPDATE tasks SET state='checking' WHERE id=?", (task,))
    return task


@pytest.mark.parametrize('state_name', ['mapping', 'checking'])
def test_completed_download_does_not_occupy_network_slot(state, state_name):
    q, _ = state
    mapped = setup(q, 'a', state_name)
    setup(q, 'b', 'downloading')
    third = create(q, 'c')
    assert q.begin_submission(third, 100000, 90000)
    assert q.status(mapped)['state'] == state_name
    assert q.status(mapped)['attempts'] == 1
    assert q.status(mapped)['reserved_bytes'] == 1000
    assert q.generation() == 0


@pytest.mark.parametrize('state_name', ['submitting', 'submitted', 'uncertain', 'downloading'])
def test_noncompleted_download_keeps_its_slot(state, state_name):
    q, _ = state
    setup(q, 'a', state_name)
    setup(q, 'b', 'downloading')
    third = create(q, 'c')
    assert not q.begin_submission(third, 100000, 90000)
    assert q.status(third)['attempts'] == 0


@pytest.mark.parametrize('changes', [
    {'state': 'downloading'}, {'state': 'missing'}, {'state': 'unknown'}, {'state': 'failed'},
    {'account': 'other'}, {'destination': '/115open/other'}, {'source_info_hash': 'f' * 40},
    {'file_id': ''}, {'file_id': None}, {'file_id': 1}, {'file_id': '   '},
    {'parent_id': ''}, {'parent_id': None}, {'parent_id': 1}, {'parent_id': '   '},
    {'extra': True},
])
@pytest.mark.parametrize('state_name', ['mapping', 'checking'])
def test_unproved_mapping_keeps_slot(state, changes, state_name):
    q, _ = state
    task = setup(q, 'a', state_name)
    payload = q.status(task)['payload']
    payload['provider_observation'].update(changes)
    q.db.execute('UPDATE tasks SET payload=? WHERE id=?', (json.dumps(payload), task))
    setup(q, 'b', 'downloading')
    third = create(q, 'c')
    assert not q.begin_submission(third, 100000, 90000)


@pytest.mark.parametrize('payload', ['{', 'null', '[]', '{}',
    '{"provider_observation":[]}', '{"provider_observation":null}'])
def test_malformed_mapping_payload_keeps_slot(state, payload):
    q, _ = state
    task = setup(q)
    q.db.execute('UPDATE tasks SET payload=? WHERE id=?', (payload, task))
    setup(q, 'b', 'downloading')
    third = create(q, 'c')
    assert not q.begin_submission(third, 100000, 90000)


@pytest.mark.parametrize('column,value', [('provider', 'legacy'), ('account', ''),
    ('destination', '/outside'), ('destination', '/115open/../other'), ('source_hash', 'bad')])
def test_legacy_or_invalid_scope_never_releases_slot(state, column, value):
    q, _ = state
    task = setup(q)
    payload = q.status(task)['payload']
    if column != 'provider':
        payload['provider_observation']['source_info_hash' if column == 'source_hash' else column] = value
    q.db.execute('UPDATE tasks SET ' + column + '=?,payload=? WHERE id=?', (value, json.dumps(payload), task))
    setup(q, 'b', 'downloading')
    third = create(q, 'c')
    assert not q.begin_submission(third, 100000, 90000)


@pytest.mark.parametrize('state_name', ['mapping', 'checking'])
def test_completed_download_keeps_entire_capacity_reservation(state, state_name):
    q, _ = state
    setup(q, 'a', state_name)
    setup(q, 'b', 'downloading')
    third = create(q, 'c')
    # 2% + two existing 1,000-byte reservations + 1,000-byte proposal.
    assert not q.begin_submission(third, 100000, 4999)
    assert q.status(third)['state'] == 'space_blocked'
    assert q.begin_submission(third, 100000, 5000)


def test_two_completed_downloads_allow_only_two_new_downloads(state):
    q, _ = state
    setup(q, 'a')
    setup(q, 'b')
    third = create(q, 'c')
    fourth = create(q, 'd')
    fifth = create(q, 'e')
    assert q.begin_submission(third, 100000, 90000)
    assert q.begin_submission(fourth, 100000, 90000)
    assert not q.begin_submission(fifth, 100000, 90000)


def test_slots_still_global_but_capacity_reservations_still_account_scoped(state):
    q, _ = state
    setup(q, 'a')
    setup(q, 'b', 'downloading')
    third = create(q, 'c', account='another-account')
    # Existing reservations belong to another account, exactly as before.
    assert q.begin_submission(third, 100000, 3000)
    fourth = create(q, 'd', account='another-account')
    assert not q.begin_submission(fourth, 100000, 90000)


def test_ready_pack_new_episode_is_verification_not_new_download(state):
    q, _ = state
    task = setup(q)
    file = dict(provider='115', account='test-account', file_id='file-1',
        cloud_path='/115open/test/pack/ep1.mkv', bytes=1000, kind='video',
        media_id='tmdb:tv:123:s1:e1', version_key='release-a')
    rid = q.ledger.register(file, managed=True, identity_verified=True)
    q.ledger.mark_ready(rid, dict(file_id='file-1', bytes=1000, version_key='release-a',
        source_binding=True, read_bytes=500, probe_sha256='b' * 64, duration=1400, video_codec='hevc'))
    q.publish(task, rid, dict(source_info_hash='a' * 40, cloud_root_id='root', cloud_file_id='file-1',
        cloud_path=file['cloud_path'], torrent_path='ep1.mkv', torrent_file_id=1, bytes=1000))
    assert q.status(task)['state'] == 'ready'
    assert create(q, 'a', 2) == task
    assert q.status(task)['state'] == 'mapping'
    setup(q, 'b', 'downloading')
    third = create(q, 'c')
    assert q.begin_submission(third, 100000, 90000)
    assert q.resolve('test-account', 'tmdb:tv:123:s1:e2', 'release-a') is None
    assert q.generation() == 1


def test_reopen_database_preserves_completion_and_uncertainty_without_resubmit(tmp_path):
    path = tmp_path / 'persistent.sqlite'
    with Ledger(path) as ledger:
        q = PreparationQueue(ledger)
        mapped = setup(q)
        uncertain = setup(q, 'b', 'submitting')
        waiting = create(q, 'c')
    with Ledger(path) as ledger:
        q = PreparationQueue(ledger)
        q.recover()
        assert q.status(mapped)['state'] == 'mapping'
        assert q.status(uncertain)['state'] == 'uncertain'
        assert q.begin_submission(waiting, 100000, 90000)
        assert q.status(uncertain)['attempts'] == 1
        with pytest.raises(ValueError):
            q.begin_submission(uncertain, 100000, 90000)


def test_recovered_legacy_checking_stays_a_slot_even_after_state_becomes_mapping(state):
    q, _ = state
    task = setup(q, 'a', 'checking')
    q.db.execute("UPDATE tasks SET provider='legacy' WHERE id=?", (task,))
    q.recover()
    setup(q, 'b', 'downloading')
    third = create(q, 'c')
    assert not q.begin_submission(third, 100000, 90000)


def test_mapping_cannot_be_resubmitted_or_resolved_without_media_qualification(state):
    q, _ = state
    task = setup(q)
    with pytest.raises(ValueError):
        q.begin_submission(task, 100000, 90000)
    assert q.resolve('test-account', 'tmdb:tv:123:s1:e1', 'release-a') is None
    assert q.generation() == 0



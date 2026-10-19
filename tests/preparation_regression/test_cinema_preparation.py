import json
import sqlite3

import pytest

from bobbi_core.ledger import Ledger
from bobbi_core.preparation import PreparationQueue, checked_request


@pytest.fixture(autouse=True)
def real_sqlite(monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', sqlite3.dbapi2.connect)


@pytest.fixture
def queue(tmp_path):
    clock = [1000.0]
    with Ledger(tmp_path / 'ledger.sqlite', now=lambda: clock[0]) as ledger:
        yield PreparationQueue(ledger), clock


def request(**changes):
    return dict(provider='115', account='account-a', destination='/115open/波比TV',
                source_info_hash='a' * 40, media_id='tmdb:tv:123:s1:e1',
                version_key='release-a', bytes_required=1000, purpose='current', **{}) | changes


def observation(**changes):
    return dict(account='account-a', destination='/115open/波比TV', source_info_hash='a' * 40,
                state='finished', file_id='root-id', parent_id='destination-id') | changes


def mapped(queue):
    task = queue.request(request())['task_id']
    assert queue.begin_submission(task, 100000, 90000)
    queue.submitted(task, True)
    assert queue.observe(task, observation()) == 'mapping'
    return task


def qualified(queue, media='tmdb:tv:123:s1:e1', n='file-1'):
    file = dict(provider='115', account='account-a', file_id=n, cloud_path='/115open/波比TV/pack/' + n + '.mkv',
                bytes=1000, kind='video', media_id=media, version_key='release-a')
    rid = queue.ledger.register(file, managed=True, identity_verified=True)
    queue.ledger.mark_ready(rid, dict(file_id=n, bytes=1000, version_key='release-a', source_binding=True,
                                    read_bytes=500, probe_sha256='b' * 64, duration=1400, video_codec='hevc'))
    evidence = dict(source_info_hash='a' * 40, cloud_root_id='root-id', cloud_file_id=n,
                    cloud_path=file['cloud_path'], torrent_path=n + '.mkv', torrent_file_id=1, bytes=1000)
    return rid, evidence


def test_idempotent_scope_and_pack_targets(queue):
    q, _ = queue
    first = q.request(request())
    assert q.request(request())['existing']
    assert q.request(request(media_id='tmdb:tv:123:s1:e2'))['task_id'] == first['task_id']
    assert q.request(request(account='account-b'))['task_id'] != first['task_id']
    assert q.request(request(destination='/115open/other'))['task_id'] != first['task_id']
    assert q.db.execute('SELECT COUNT(*) FROM preparation_targets WHERE task=?', (first['task_id'],)).fetchone()[0] == 2
    with pytest.raises(ValueError):
        q.request(request(bytes_required=2000))


@pytest.mark.parametrize('changes', [dict(token='not-allowed'), dict(bytes_required=True), dict(bytes_required=0),
    dict(source_info_hash='invalid'), dict(account=''), dict(destination='/115open/../x'),
    dict(destination='/115open//x'), dict(destination='/other'), dict(media_id='tmdb:tv:123:s1'),
    dict(media_id='nearby-name'), dict(purpose='test-skip-verification'), dict(provider='other')])
def test_request_rejects_unknown_or_ambiguous_fields(changes):
    with pytest.raises(ValueError):
        checked_request(request(**changes))


def test_submit_is_persisted_before_provider_call_and_never_replayed(queue):
    q, _ = queue
    task = q.request(request())['task_id']
    assert q.begin_submission(task, 100000, 90000)
    assert q.status(task)['state'] == 'submitting'
    q.recover()
    assert q.status(task)['state'] == 'uncertain'
    with pytest.raises(ValueError):
        q.begin_submission(task, 100000, 90000)
    assert q.observe(task, observation(state='missing', file_id='', parent_id='')) == 'uncertain'
    assert q.request(request())['existing']
    assert q.status(task)['attempts'] == 1


def test_concurrency_and_capacity_and_priority(queue):
    q, clock = queue
    first = q.request(request(purpose='recommendation'))['task_id']
    clock[0] += 1
    second = q.request(request(source_info_hash='b' * 40))['task_id']
    clock[0] += 1
    third = q.request(request(source_info_hash='c' * 40))['task_id']
    assert q.due(playing=True)[0]['id'] == second
    assert first not in [r['id'] for r in q.due(playing=True)]
    assert q.begin_submission(first, 100000, 90000)
    assert q.begin_submission(second, 100000, 90000)
    assert not q.begin_submission(third, 100000, 90000)
    q.submitted(first, True)
    q.observe(first, observation(state='failed'))
    assert not q.begin_submission(third, 100000, 3500)  # 2% + in-flight + new
    assert q.status(third)['state'] == 'space_blocked'
    assert q.begin_submission(third, 100000, 90000)


@pytest.mark.parametrize('changes', [dict(account='wrong'), dict(source_info_hash='c' * 40), dict(destination='/115open/other')])
def test_observation_is_account_source_scoped(queue, changes):
    q, _ = queue
    task = q.request(request())['task_id']
    q.begin_submission(task, 100000, 90000)
    q.submitted(task, False)
    with pytest.raises(ValueError):
        q.observe(task, observation(**changes))
    assert q.status(task)['state'] == 'uncertain'


def test_finished_without_cloud_identity_cannot_map(queue):
    q, _ = queue
    task = q.request(request())['task_id']
    q.begin_submission(task, 100000, 90000)
    q.submitted(task, True)
    assert q.observe(task, observation(file_id='')) == 'uncertain'
    assert q.generation() == 0


def test_publish_exact_binding_and_generation_and_next_episode(queue):
    q, _ = queue
    task = mapped(q)
    rid, proof = qualified(q)
    assert q.publish(task, rid, proof) == 1
    assert q.publish(task, rid, proof) == 1
    assert q.status(task)['state'] == 'ready'
    assert q.resolve('account-a', 'tmdb:tv:123:s1:e1', 'release-a')['resource_id'] == rid
    assert q.resolve('wrong', 'tmdb:tv:123:s1:e1', 'release-a') is None
    assert q.resolve('account-a', 'tmdb:tv:123:s1:e1', 'another-release') is None
    assert q.request(request(media_id='tmdb:tv:123:s1:e2'))['task_id'] == task
    assert q.status(task)['state'] == 'mapping'
    assert q.status(task)['attempts'] == 1
    second, second_proof = qualified(q, media='tmdb:tv:123:s1:e2', n='file-2')
    assert q.publish(task, second, second_proof) == 2
    assert q.status(task)['state'] == 'ready'


@pytest.mark.parametrize('changes', [dict(source_info_hash='c' * 40), dict(cloud_root_id='wrong'),
    dict(cloud_file_id='wrong'), dict(bytes=999), dict(cloud_path='/115open/other.mkv'),
    dict(torrent_path='../other.mkv'), dict(torrent_file_id=True)])
def test_mismatched_publish_is_atomic(queue, changes):
    q, _ = queue
    task = mapped(q)
    rid, proof = qualified(q)
    with pytest.raises(ValueError):
        q.publish(task, rid, proof | changes)
    assert q.generation() == 0
    assert q.db.execute('SELECT COUNT(*) FROM prepared_bindings').fetchone()[0] == 0
    assert q.status(task)['state'] == 'mapping'


def test_persisted_queue_survives_restart_without_resubmit(tmp_path):
    path = tmp_path / 'state.sqlite'
    with Ledger(path) as ledger:
        q = PreparationQueue(ledger)
        task = q.request(request())['task_id']
        q.begin_submission(task, 100000, 90000)
    with Ledger(path) as ledger:
        q = PreparationQueue(ledger)
        q.recover()
        assert q.status(task)['state'] == 'uncertain'
        assert q.request(request())['task_id'] == task


def test_v1_migration_preserves_tasks_and_a_verified_backup(tmp_path):
    path = tmp_path / 'v1.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE tasks(id TEXT PRIMARY KEY,source_hash TEXT UNIQUE,payload TEXT,state TEXT,reserved_bytes INTEGER,updated REAL);
            PRAGMA user_version=1;''')
        db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?)', ('old-task', 'a' * 40, '{}', 'uncertain', 1000, 10))
    with Ledger(path) as ledger:
        assert ledger.db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert ledger.db.execute("SELECT state FROM tasks WHERE id='old-task'").fetchone()[0] == 'uncertain'
        with sqlite3.connect(ledger.migration_backup) as original:
            assert original.execute('PRAGMA user_version').fetchone()[0] == 1
            assert original.execute('SELECT id FROM tasks').fetchone()[0] == 'old-task'
        q = PreparationQueue(ledger)
        assert q.request(request())['task_id'] != 'old-task'



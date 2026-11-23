"""Service-only adjacent-file evidence, independent of cloud readiness."""
from copy import deepcopy
import json

import pytest

from bobbi_core.preparation_intake import Intake
from test_rolling_preparation import queue, source, prove, service, perform


def accepted(queue, value):
    intake = Intake(queue.ledger)
    intake.accept(value[0])
    assert intake.take() == value[0]
    targets = prove(value)
    tasks = [dict(queue.request(r, s), media_id=r['media_id'], version_key=r['version_key']) for r, s in targets]
    intake.finish(value[0]['request_id'], {'tasks': tasks}, True)
    return intake, targets, tasks


def test_accepted_pack_projects_exact_next_before_any_cloud_submission(queue):
    value = source((1, 2, 3))
    intake, targets, tasks = accepted(queue, value)
    proof = intake.status(value[0]['request_id'])['result'].get('source_proof')
    assert proof is not None
    assert proof['anchor']['selected'] == value[0]['selected']
    assert proof['next']['video_context']['media_id'] == 'tmdb:tv:1:s1:e2'
    assert proof['next']['video_context']['selected']['torrent_file_id'] == 14
    assert proof['next']['video_context']['selected']['torrent_file_bytes'] == 1000
    assert queue.status(tasks[0]['task_id'])['state'] == 'queued'
    assert queue.status(tasks[0]['task_id'])['attempts'] == 0


def test_discovered_next_requires_its_actual_current_anchor_and_prepared_receipt(queue):
    value = source()
    intake, targets, tasks = accepted(queue, value)
    discovery = service(queue)
    discovery.jobs.schedule(tasks[0]['task_id'], targets[0][0]['media_id'], targets[0][0]['version_key'])
    job = discovery.claim()
    assert job['media_id'] == 'tmdb:tv:1:s1:e2'
    proposal = perform(job, source((2,), current=2, source_hash='b' * 40)[1], [])
    assert intake.status(value[0]['request_id'])['result']['source_proof']['next'] is None
    discovery.complete(job, proposal)
    proof = intake.status(value[0]['request_id'])['result']['source_proof']
    assert proof['next']['video_context']['selected']['source_info_hash'] == 'b' * 40
    payload = deepcopy(job['payload'])
    payload['anchor']['selected']['torrent_file_bytes'] += 1
    queue.db.execute('UPDATE next_discovery_jobs SET payload=? WHERE id=?', (json.dumps(payload), job['id']))
    assert intake.status(value[0]['request_id'])['result']['source_proof']['next'] is None


@pytest.mark.parametrize('change', ['next_purpose', 'manual_purpose', 'current_tuple', 'unaccepted', 'unrelated_work', 'suppressed'])
def test_status_never_projects_unaccepted_or_other_current_source(queue, change):
    value = source((1, 2))
    if change.endswith('_purpose'):
        value[0]['purpose'] = change.split('_')[0]
    intake, targets, tasks = accepted(queue, value)
    if change == 'current_tuple':
        payload = deepcopy(value[0])
        payload['selected']['torrent_file_id'] = 999
        queue.db.execute('UPDATE preparation_intents SET payload=?', (json.dumps(payload),))
    elif change == 'unaccepted': queue.db.execute("UPDATE preparation_intents SET state='failed'")
    elif change == 'suppressed': queue.db.execute("UPDATE tasks SET state='suppressed'")
    elif change == 'unrelated_work':
        row = queue.db.execute('SELECT payload FROM preparation_targets WHERE media_id=?', ('tmdb:tv:1:s1:e1',)).fetchone()
        payload = json.loads(row[0])
        payload['_selection']['work_identity']['id'] = 2
        queue.db.execute('UPDATE preparation_targets SET payload=? WHERE media_id=?',
                         (json.dumps(payload), 'tmdb:tv:1:s1:e1'))
    assert intake.status(value[0]['request_id'])['result'].get('source_proof') is None


def test_gap_never_projects_e3_as_next(queue):
    value = source((1, 3))
    intake, _, _ = accepted(queue, value)
    assert intake.status(value[0]['request_id'])['result']['source_proof']['next'] is None


def test_cloud_failure_keeps_exact_bt_evidence_without_restarting_submission(queue):
    value = source((1, 2))
    intake, _, tasks = accepted(queue, value)
    queue.db.execute("UPDATE tasks SET state='failed' WHERE id=?", (tasks[0]['task_id'],))
    assert intake.status(value[0]['request_id'])['result']['source_proof']['next'] is not None
    assert queue.status(tasks[0]['task_id'])['state'] == 'failed'


def test_prepared_offset_two_becomes_adjacent_after_independently_proved_current_advance(queue):
    first = source()
    _, targets, tasks = accepted(queue, first)
    discovery = service(queue)
    key = discovery.jobs.schedule(tasks[0]['task_id'], targets[0][0]['media_id'], targets[0][0]['version_key'], 2)
    job = discovery.claim()
    proposal = perform(job, source((3,), current=3, source_hash='b' * 40)[1], [])
    receipt = discovery.complete(job, proposal)
    second = source((2,), current=2, source_hash='c' * 40)
    second[0]['request_id'] = 'e' * 32
    intake, _, _ = accepted(queue, second)
    before = queue.status(receipt['task_id'])
    proof = intake.status(second[0]['request_id'])['result']['source_proof']
    assert proof['anchor']['selected'] == second[0]['selected']
    assert proof['next']['video_context']['selected']['source_info_hash'] == 'b' * 40
    assert proof['next']['video_context']['media_id'] == 'tmdb:tv:1:s1:e3'
    assert discovery.jobs.get(key)['payload']['target_offset'] == 2
    assert discovery.jobs.get(key)['state'] == 'prepared'
    assert queue.status(receipt['task_id']) == before


def test_unicode_file_proof_cannot_overflow_status_ipc_budget(queue):
    value = source((1, 2))
    for item in value[1]['file_stats']:
        item['path'] = item['path'].replace(' [Group]', ' ' + '字' * 1800 + ' [Group]')
    value[0]['selected']['torrent_path'] = value[1]['file_stats'][0]['path']
    intake, _, _ = accepted(queue, value)
    status = intake.status(value[0]['request_id'])
    assert status['state'] == 'accepted'
    assert 'source_proof' not in status['result']
    assert len(json.dumps(status).encode()) < 16384

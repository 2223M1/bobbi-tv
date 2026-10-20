import sqlite3

import pytest

from bobbi_core.ledger import Ledger
from bobbi_core.preparation import PreparationQueue
from bobbi_core.preparation_worker import PreparationWorker


class Provider:
    def __init__(self):
        self.account = 'a'
        self.rows, self.submissions = [], []
        self.failure = None

    def account_scope(self):
        return self.account

    def space(self, path):
        return dict(total=100000, free=90000, used=10000)

    def add_offline(self, magnet, destination):
        self.submissions.append((magnet, destination))
        if self.failure:
            raise self.failure
        return {'status': 'ACCEPTED_NOT_VERIFIED'}

    def offline_tasks(self, path):
        return self.rows


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', sqlite3.dbapi2.connect)
    clock = [1000.0]
    with Ledger(tmp_path / 'ledger.db', now=lambda: clock[0]) as ledger:
        q = PreparationQueue(ledger)
        task = q.request(dict(provider='115', account='a', destination='/115open/波比TV',
                              source_info_hash='a' * 40, media_id='tmdb:tv:123:s1:e1',
                              version_key='version1', bytes_required=1000, purpose='current'),
                         selection=dict(file=dict(id=7, path='video.mkv', length=1000), title='Series',
                                        release_title='video.mkv', anime=False, request_id='f' * 32,
                                        metadata_sha256='b' * 64, work_identity={'provider': 'tmdb'}))['task_id']
        provider = Provider()
        worker = PreparationWorker(q, provider, lambda *_: None)
        yield worker, q, provider, clock, task


def execute(worker, kind):
    action = worker.next_action()
    assert action.kind == kind
    assert worker.next_action() is None
    result = worker.perform(action)
    assert worker.complete(action, result)
    assert worker.complete(action, result) is False
    return result


def test_submission_intent_and_network_are_separate_transactions(state):
    w, q, p, clock, task = state
    execute(w, 'capacity')
    assert q.status(task)['state'] == 'submitting'
    assert not p.submissions and not q.db.in_transaction
    execute(w, 'submit')
    assert q.status(task)['state'] == 'submitted'
    assert p.submissions == [('magnet:?xt=urn:btih:' + 'a' * 40, '/115open/波比TV')]
    assert q.generation() == 0


def test_provider_timeout_cannot_create_second_submission(state):
    w, q, p, clock, task = state
    p.failure = TimeoutError('SECRET-SIGNED-URL')
    execute(w, 'capacity')
    result = execute(w, 'submit')
    assert result == {'ok': False, 'error': 'TimeoutError'}
    assert q.status(task)['state'] == 'uncertain'
    w = PreparationWorker(q, p, lambda *_: None)
    clock[0] += 60
    execute(w, 'poll')
    assert q.status(task)['state'] == 'uncertain'
    assert len(p.submissions) == 1


def test_account_change_between_capacity_and_submission_fails_closed(state):
    w, q, p, _, task = state
    execute(w, 'capacity')
    p.account = 'other'
    assert execute(w, 'submit')['error'] == 'ACCOUNT_CHANGED'
    assert not p.submissions
    assert q.status(task)['state'] == 'uncertain'


@pytest.mark.parametrize('status,state_name', [(0, 'downloading'), (1, 'downloading'),
    (2, 'mapping'), (3, 'failed'), (4, 'uncertain'), (99, 'uncertain')])
def test_provider_states_are_not_playable(state, status, state_name):
    w, q, p, clock, task = state
    execute(w, 'capacity')
    execute(w, 'submit')
    p.rows = [dict(info_hash='a' * 40, status=status, file_id='root', parent_id='parent')]
    clock[0] += 5
    execute(w, 'poll')
    assert q.status(task)['state'] == state_name
    assert q.generation() == 0


@pytest.mark.parametrize('rows', [[], [dict(info_hash='b' * 40, status=2)],
    [dict(info_hash='a' * 40, status=2)] * 2])
def test_absent_wrong_or_duplicate_torrent_never_qualifies(state, rows):
    w, q, p, clock, task = state
    execute(w, 'capacity')
    execute(w, 'submit')
    p.rows = rows
    clock[0] += 5
    execute(w, 'poll')
    assert q.status(task)['state'] == 'uncertain'


def test_current_next_light_probe_can_finish_during_video_without_fake_publication(state):
    w, q, p, clock, task = state
    execute(w, 'capacity')
    execute(w, 'submit')
    p.rows = [dict(info_hash='a' * 40, status=2, file_id='root', parent_id='parent')]
    clock[0] += 5
    execute(w, 'poll')
    clock[0] += 15
    action = w.next_action(playing=True)
    assert action.kind == 'qualify'
    assert w.next_action(playing=True) is None
    assert w.complete(action, w.perform(action))
    assert q.status(task)['state'] == 'mapping'
    assert q.generation() == 0
    assert w.next_action() is None


def test_recommendation_probe_stays_paused_during_video(state):
    w, q, p, clock, task = state
    execute(w, 'capacity')
    execute(w, 'submit')
    p.rows = [dict(info_hash='a' * 40, status=2, file_id='root', parent_id='parent')]
    clock[0] += 5
    execute(w, 'poll')
    clock[0] += 15
    q.db.execute('UPDATE tasks SET priority=3 WHERE id=?', (task,))
    assert w.next_action(playing=True) is None
    assert w.next_action(playing=False).kind == 'qualify'


def test_startup_without_qualifier_cannot_mutate_provider(state):
    _, q, p, _, _ = state
    with pytest.raises(ValueError):
        PreparationWorker(q, p, None)
    assert not p.submissions


def test_probe_failure_records_typed_cause_without_provider_secrets(state):
    import json
    from bobbi_core.media_probe import ProbeError
    w, q, p, clock, task = state
    execute(w, 'capacity')
    execute(w, 'submit')
    p.rows = [dict(info_hash='a' * 40, status=2, file_id='root', parent_id='parent')]
    clock[0] += 5
    execute(w, 'poll')
    clock[0] += 15
    def failed(*_):
        raise ProbeError('BYTE_BUDGET')
    w.qualifier = failed
    assert execute(w, 'qualify') == dict(ok=False, error='ProbeError', code='BYTE_BUDGET')
    detail = json.loads(q.db.execute("SELECT detail FROM audit WHERE action='preparation_io_failed' ORDER BY seq DESC LIMIT 1").fetchone()[0])
    assert detail == dict(task=task, kind='qualify', error='ProbeError', code='BYTE_BUDGET')
    assert q.generation() == 0


def test_defer_does_not_echo_arbitrary_error_strings(state):
    import json
    w, q, _, _, _ = state
    action = w.next_action()
    w.complete(action, dict(ok=False, error='https://example/SECRET', code='SECRET token'))
    detail = json.loads(q.db.execute("SELECT detail FROM audit WHERE action='preparation_io_failed' ORDER BY seq DESC LIMIT 1").fetchone()[0])
    assert set(detail) == {'task', 'kind'}


def test_bare_queue_record_without_fresh_selection_cannot_submit(state):
    w, q, p, _, task = state
    q.db.execute("UPDATE preparation_targets SET payload=json_remove(payload,'$._selection')")
    assert w.next_action() is None
    assert q.status(task)['state'] == 'queued'
    assert not p.submissions



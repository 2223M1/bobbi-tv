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


def test_probe_failure_keeps_only_bounded_numeric_metrics(state):
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
        error = ProbeError('BYTE_BUDGET')
        error.metrics = dict(read_bytes=16777216, requests=2, seconds=2.123456,
                             url='https://private/SECRET', raw='SECRET', probe_sha256='f' * 64)
        raise error
    w.qualifier = failed
    metrics = dict(read_bytes=16777216, requests=2, seconds=2.123)
    assert execute(w, 'qualify')['probe'] == metrics
    detail = json.loads(q.db.execute("SELECT detail FROM audit WHERE action='preparation_io_failed' ORDER BY seq DESC LIMIT 1").fetchone()[0])
    assert detail == dict(task=task, kind='qualify', error='ProbeError', code='BYTE_BUDGET', probe=metrics)
    assert q.generation() == 0


@pytest.mark.parametrize('metrics', [None, 'SECRET',
    dict(read_bytes=True, requests=False, seconds=float('nan')),
    dict(read_bytes=-1, requests=34, seconds=float('inf')),
    dict(read_bytes=16777217, requests='2', seconds=-1),
    dict(seconds=10**1000), dict(seconds=-(10**1000))])
def test_probe_metrics_reject_malformed_observations(metrics):
    from bobbi_core.preparation_worker import _probe_metrics
    assert _probe_metrics(metrics) == {}


@pytest.mark.parametrize('unavailable', ['error', 'none'])
def test_unreadable_first_target_does_not_starve_other_pack_episodes_after_restart(state, unavailable):
    import json
    from bobbi_core.media_probe import ProbeError
    w, q, p, clock, task = state
    original = json.loads(q.db.execute('SELECT payload FROM preparation_targets WHERE task=?', (task,)).fetchone()[0])
    for episode in (2, 3):
        selected = dict(original, media_id='tmdb:tv:123:s1:e%d' % episode)
        q.request({k: v for k, v in selected.items() if k != '_selection'},
                  selection=selected['_selection'])
    execute(w, 'capacity')
    execute(w, 'submit')
    p.rows = [dict(info_hash='a' * 40, status=2, file_id='root', parent_id='parent')]
    clock[0] += 5
    execute(w, 'poll')
    clock[0] += 15
    attempts = []
    def failed(provider, request):
        attempts.append(request['targets'][0]['media_id'])
        if unavailable == 'error':
            raise ProbeError('BYTE_BUDGET')
        return None
    for _ in range(4):
        # Each owner restart must preserve fairness, not revive a permanently
        # failing first item ahead of every remaining episode.
        w = PreparationWorker(q, p, failed)
        execute(w, 'qualify')
        assert w.next_action() is None
        clock[0] += 60
    assert attempts == ['tmdb:tv:123:s1:e%d' % n for n in (1, 2, 3, 1)]
    assert q.generation() == 0
    assert len(p.submissions) == 1


@pytest.mark.parametrize('cursor', [None, [], {}, ['x'], ['x', 'y', 'z'],
                                  ['', 'v'], ['x' * 257, 'v'], [True, 'v']])
def test_invalid_qualification_cursor_is_not_authority(state, cursor):
    import json
    from bobbi_core.preparation_worker import next_qualification_target
    _, q, _, _, task = state
    original = json.loads(q.db.execute('SELECT payload FROM preparation_targets WHERE task=?', (task,)).fetchone()[0])
    assert next_qualification_target(q.db, task, {'_qualification_cursor': cursor}) == original


def test_round_robin_wrap_and_insert_use_canonical_unbound_order_only(state):
    import json
    from bobbi_core.preparation_worker import next_qualification_target
    _, q, _, _, task = state
    original = json.loads(q.db.execute('SELECT payload FROM preparation_targets WHERE task=?', (task,)).fetchone()[0])
    def add(n):
        item = dict(original, media_id='tmdb:tv:123:s1:e%d' % n)
        q.request({k: v for k, v in item.items() if k != '_selection'}, selection=item['_selection'])
    def next_id(media):
        return next_qualification_target(q.db, task,
            {'_qualification_cursor': [media, original['version_key']]})['media_id']
    add(3)
    assert next_id(original['media_id']).endswith(':e3')
    add(2)
    assert next_id(original['media_id']).endswith(':e2')
    q.db.execute('DELETE FROM preparation_targets WHERE task=? AND media_id=?', (task, original['media_id']))
    assert next_id(original['media_id']).endswith(':e2')
    assert next_id('tmdb:tv:123:s1:e9').endswith(':e2')
    assert next_id('tmdb:tv:123:s1:e2').endswith(':e3')


def test_bad_first_episode_does_not_prevent_real_ledger_publication_of_second(state):
    import json
    from bobbi_core.media_probe import ProbeError
    w, q, p, clock, task = state
    first = json.loads(q.db.execute('SELECT payload FROM preparation_targets WHERE task=?', (task,)).fetchone()[0])
    second = dict(first, media_id='tmdb:tv:123:s1:e2')
    selection = dict(first['_selection'], file=dict(id=8, path='e2.mkv', length=1000))
    q.request({k: v for k, v in second.items() if k != '_selection'}, selection=selection)
    execute(w, 'capacity')
    execute(w, 'submit')
    p.rows = [dict(info_hash='a' * 40, status=2, file_id='root', parent_id='parent')]
    clock[0] += 5
    execute(w, 'poll')
    clock[0] += 15
    def qualify(provider, request):
        target = request['targets'][0]
        if target['media_id'] == first['media_id']:
            raise ProbeError('BYTE_BUDGET')
        assert target['_selection']['file'] == selection['file']
        file = dict(provider='115', account='a', file_id='cloud-e2',
                    cloud_path='/115open/波比TV/e2.mkv', bytes=1000, kind='video',
                    media_id=target['media_id'], version_key=target['version_key'])
        return dict(file=file,
            qualification=dict(file_id='cloud-e2', bytes=1000, version_key=target['version_key'],
                source_binding=True, duration=1400, video_codec='hevc',
                read_bytes=500, probe_sha256='f' * 64),
            mapping=dict(source_info_hash='a' * 40, cloud_root_id='root', cloud_file_id='cloud-e2',
                cloud_path=file['cloud_path'], torrent_path='e2.mkv', torrent_file_id=8, bytes=1000))
    w.qualifier = qualify
    assert execute(w, 'qualify')['ok'] is False
    assert q.generation() == 0
    clock[0] += 60
    assert execute(w, 'qualify')['ok'] is True
    assert q.generation() == 1
    assert q.resolve('a', second['media_id'], second['version_key'])['file_id'] == 'cloud-e2'
    assert q.resolve('a', first['media_id'], first['version_key']) is None
    action = w.next_action()
    assert action.request['targets'][0]['media_id'] == first['media_id']
    assert len(p.submissions) == 1
    assert q.status(task)['payload']['provider_observation']['state'] == 'finished'

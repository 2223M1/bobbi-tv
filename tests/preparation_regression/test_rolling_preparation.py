"""Real service proofs and durable queues for the fixed current + 2 window."""
from copy import deepcopy
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from bobbi_core.discovery_queue import DiscoveryQueue
from bobbi_core.discovery_service import NextDiscovery
from bobbi_core.ledger import Ledger
from bobbi_core.next_discovery import discover
from bobbi_core.preparation import PreparationQueue
from bobbi_core.source_intent import verified_intents


CATALOG = dict(provider='tmdb', id=1, kind='tv', aliases=['Series'], year=2026,
               response_sha256='c' * 64, ambiguous=False)


def file(number, group='Group'):
    return dict(id=number * 7, path='Series/Series S01E{:02} [{}].mkv'.format(number, group), length=1000)


def source(numbers=(1,), current=1, source_hash='a' * 40, purpose='current'):
    selected = file(current)
    body = dict(request_id='f' * 32, purpose=purpose,
        media=dict(tmdb_id=1, kind='tv', season=1, episode=current, anime=False,
                   title='Series', release_title='Series [Group]'),
        selected=dict(source_info_hash=source_hash, torrent_file_id=selected['id'],
                      torrent_path=selected['path'], torrent_file_bytes=selected['length']))
    return body, dict(hash=source_hash, title='Series', file_stats=[file(n) for n in numbers])


def selector(files, season, episode, *_):
    choices = [row for row in files if 'S{:02}E{:02} '.format(season, episode) in row['path']]
    if len(choices) != 1:
        raise ValueError('Exact unique episode required')
    return choices[0]


def prove(value, account='account'):
    return verified_intents(*value, account, '/115open/inbox', selector, CATALOG)


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', sqlite3.dbapi2.connect)
    with Ledger(tmp_path / 'rolling.db') as ledger:
        yield PreparationQueue(ledger)


def admission(queue, value):
    targets = prove(value)
    admitted = [dict(queue.request(request, selection), media_id=request['media_id'],
                     version_key=request['version_key']) for request, selection in targets]
    return targets, admitted


def service(queue):
    return NextDiscovery(queue, None, None, None, selector, None)


def jobs(queue):
    return [dict(row) for row in queue.db.execute('SELECT * FROM next_discovery_jobs ORDER BY media_id')]


def test_pack_window_is_current_and_two_future_episodes_only(queue):
    targets, accepted = admission(queue, source((1, 2, 3, 4, 5)))
    assert [r['media_id'] for r, _ in targets] == ['tmdb:tv:1:s1:e1', 'tmdb:tv:1:s1:e2', 'tmdb:tv:1:s1:e3']
    assert [r['purpose'] for r, _ in targets] == ['current', 'next', 'next']
    assert len({r['task_id'] for r in accepted}) == 1
    assert queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 1
    assert targets[0][0]['bytes_required'] == 5000


def test_missing_e1_does_not_prevent_independent_e2_preparation():
    targets = prove(source((1, 3, 4)))
    assert [r['media_id'] for r, _ in targets] == ['tmdb:tv:1:s1:e1', 'tmdb:tv:1:s1:e3']


@pytest.mark.parametrize('case', ['foreign_group', 'foreign_work', 'duplicate', 'foreign_season'])
def test_e2_conflicts_do_not_cancel_current_or_e1(case):
    body, metadata = source((1, 2, 3, 4))
    if case == 'foreign_group': metadata['file_stats'][2] = file(3, 'OtherGroup')
    elif case == 'foreign_work': metadata['file_stats'][2]['path'] = 'Other Series S01E03 [Group].mkv'
    elif case == 'foreign_season': metadata['file_stats'][2]['path'] = 'Series S02E03 [Group].mkv'
    else: metadata['file_stats'].append(dict(file(3), id=999, path='Alternate/' + file(3)['path']))
    assert [r['media_id'] for r, _ in prove((body, metadata))] == ['tmdb:tv:1:s1:e1', 'tmdb:tv:1:s1:e2']


def ordered_catalog(last):
    from bobbi_core.episode_order import validate_group
    group_id = 'a' * 24
    def episode(number, order):
        return dict(id=number, show_id=1, season_number=1, episode_number=number, order=order)
    listing = dict(id=1, results=[dict(id=group_id, type=6)])
    document = dict(id=group_id, type=6, groups=[
        dict(order=1, name='Season 1', episodes=[episode(1, 0), episode(2, 1)]),
        dict(order=2, name='Season 2', episodes=[episode(last, 0)])])
    return dict(CATALOG, episode_order=validate_group(1, listing, document))


@pytest.mark.parametrize('last, reason', [(3, 'RELEASE_SEASON_END'), (4, 'NO_NEXT_CATALOG_EPISODE')])
def test_e2_service_catalog_boundary_preserves_current_e1_and_does_not_search(queue, last, reason):
    catalog = ordered_catalog(last)
    targets = verified_intents(*source((1, 2, 3, 4)), 'account', '/115open/inbox', selector, catalog)
    assert [r['media_id'] for r, _ in targets] == ['tmdb:tv:1:s1:e1', 'tmdb:tv:1:s1:e2']
    _, job, _ = anchored_job(queue)
    def unexpected(*args, **kwargs):
        pytest.fail('Catalog boundary must be checked before IO')
    result = discover(job, catalog, SimpleNamespace(search_tv=unexpected), unexpected, selector, mappings={})
    assert result['state'] == 'UNAVAILABLE'
    assert result['reason'] == reason


def test_next_purpose_is_not_a_new_window_anchor():
    assert [r['media_id'] for r, _ in prove(source((1, 2, 3, 4), purpose='next'))] == ['tmdb:tv:1:s1:e1']


@pytest.mark.parametrize('numbers, expected', [((1,), [2, 3]), ((1, 2), [3]), ((1, 3), [2]), ((1, 2, 3, 4), [])])
def test_service_schedules_only_missing_positions_from_current(queue, numbers, expected):
    discovery = service(queue)
    targets, admitted = admission(queue, source(numbers))
    discovery.after_intent(targets, admitted)
    discovery.after_intent(targets, admitted)
    assert [row['media_id'] for row in jobs(queue)] == ['tmdb:tv:1:s1:e{}'.format(n) for n in expected]
    for row in jobs(queue):
        payload = json.loads(row['payload'])
        assert payload['anchor']['media']['episode'] == 1
        assert payload['target_offset'] == int(row['media_id'].rsplit('e', 1)[1]) - 1


def test_current_advance_moves_window_without_resubmitting_uncertain_pack(queue):
    discovery = service(queue)
    targets, admitted = admission(queue, source((1, 2, 3, 4, 5)))
    task = admitted[0]['task_id']
    assert queue.begin_submission(task, 10**12, 10**12)
    queue.submitted(task, None)
    future, accepted = admission(queue, source((1, 2, 3, 4, 5), current=2))
    discovery.after_intent(future, accepted)
    assert [r['media_id'] for r, _ in future] == ['tmdb:tv:1:s1:e2', 'tmdb:tv:1:s1:e3', 'tmdb:tv:1:s1:e4']
    assert {row['task_id'] for row in accepted} == {task}
    assert queue.status(task)['state'] == 'uncertain'
    assert queue.status(task)['attempts'] == 1
    with pytest.raises(ValueError, match='resubmit'):
        queue.begin_submission(task, 10**12, 10**12)
    assert jobs(queue) == []


def anchored_job(queue, offset=2):
    targets, accepted = admission(queue, source())
    discovery = DiscoveryQueue(queue)
    discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'],
                       targets[0][0]['version_key'], target_offset=offset)
    return discovery, discovery.claim(), targets


@pytest.mark.parametrize('offset', [0, 3, -1, True, '2', None])
def test_durable_jobs_reject_offsets_outside_explicit_window(queue, offset):
    targets, accepted = admission(queue, source())
    discovery = DiscoveryQueue(queue)
    with pytest.raises(ValueError):
        discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'],
                           targets[0][0]['version_key'], target_offset=offset)
    assert jobs(queue) == []


def perform(job, metadata, calls):
    candidate = SimpleNamespace(info_hash=metadata['hash'], title=metadata['file_stats'][0]['path'], key='candidate')
    def search(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(candidates=[candidate], complete=True, state='CANDIDATES_ONLY_NOT_READY', errors=[])
    return discover(job, CATALOG, SimpleNamespace(search_tv=search), lambda *a, **kw: metadata,
                    selector, mappings={})


def test_separate_e2_is_proved_from_current_metadata_and_does_not_recurse(queue):
    discovery, job, _ = anchored_job(queue)
    calls = []
    result = perform(job, source((3,), current=3, source_hash='b' * 40)[1], calls)
    assert [args[2:4] for args in calls] == [(1, 3)]
    assert result['state'] == 'SOURCE_PROVED_NOT_CLOUD_READY'
    assert result['request']['media_id'] == 'tmdb:tv:1:s1:e3'
    accepted = discovery.accept(job['id'], job['nonce'], result['request'], result['selection'])
    assert accepted['state'] == 'queued'
    assert discovery.accept(job['id'], job['nonce'], result['request'], result['selection']) is None
    assert len(jobs(queue)) == 1
    with pytest.raises(ValueError, match='not recursive'):
        discovery.schedule(accepted['task_id'], result['request']['media_id'], result['request']['version_key'])


@pytest.mark.parametrize('change', ['other_group', 'wrong_episode', 'wrong_season'])
def test_e2_discovery_does_not_substitute_a_different_release(queue, change):
    _, job, _ = anchored_job(queue)
    metadata = source((3,), current=3, source_hash='b' * 40)[1]
    if change == 'other_group': metadata['file_stats'][0] = file(3, 'OtherGroup')
    elif change == 'wrong_episode': metadata['file_stats'][0] = file(4)
    else: metadata['file_stats'][0]['path'] = 'Series S02E03 [Group].mkv'
    result = perform(job, metadata, [])
    assert result['state'] == 'UNAVAILABLE'
    assert queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 1


def test_legacy_job_missing_offset_still_proves_only_e1(queue):
    _, job, _ = anchored_job(queue, 1)
    job['payload'].pop('target_offset', None)
    result = perform(job, source((2,), current=2, source_hash='b' * 40)[1], [])
    assert result['request']['media_id'] == 'tmdb:tv:1:s1:e2'


def test_tampered_job_target_cannot_override_offset(queue):
    _, job, _ = anchored_job(queue)
    job['media_id'] = 'tmdb:tv:1:s1:e4'
    with pytest.raises(ValueError, match='anchor'):
        perform(job, source((4,), current=4, source_hash='b' * 40)[1], [])


def test_existing_future_job_reanchors_on_real_current_advance(queue):
    discovery, old, _ = anchored_job(queue)
    proposal = perform(old, source((3,), current=3, source_hash='b' * 40)[1], [])
    targets, accepted = admission(queue, source((2,), current=2, source_hash='c' * 40))
    key = discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'], targets[0][0]['version_key'])
    assert key == old['id']
    current = discovery.get(key)
    assert current['payload']['anchor']['media']['episode'] == 2
    assert current['payload']['target_offset'] == 1
    assert current['state'] == 'waiting'
    assert discovery.accept(old['id'], old['nonce'], proposal['request'], proposal['selection']) is None
    assert discovery.defer(old['id'], old['nonce'], 'CANCELLED') is False
    assert len(jobs(queue)) == 1


def test_repeated_same_current_intent_keeps_running_nonce_and_retry_budget(queue):
    discovery, old, _ = anchored_job(queue)
    value = source()
    value[0]['request_id'] = 'b' * 32
    targets, accepted = admission(queue, value)
    key = discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'],
                             targets[0][0]['version_key'], target_offset=2)
    assert discovery.get(key) == old


@pytest.mark.parametrize('state', ['prepared', 'superseded', 'cancelled'])
def test_new_anchor_does_not_reactivate_completed_discovery_history(queue, state):
    discovery, old, _ = anchored_job(queue)
    queue.db.execute('UPDATE next_discovery_jobs SET state=? WHERE id=?', (state, old['id']))
    frozen = discovery.get(old['id'])
    targets, accepted = admission(queue, source((2,), current=2, source_hash='c' * 40))
    key = discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'], targets[0][0]['version_key'])
    assert discovery.get(key) == frozen


def cancelled_for_old_anchor(queue):
    discovery, old, _ = anchored_job(queue)
    queue.db.execute("UPDATE tasks SET state='failed' WHERE id=?", (old['payload']['task'],))
    assert discovery.defer(old['id'], old['nonce'], 'CANCELLED')
    queue.db.execute('UPDATE next_discovery_jobs SET next_poll=0 WHERE id=?', (old['id'],))
    assert discovery.claim() is None
    assert discovery.get(old['id'])['state'] == 'cancelled'
    return discovery, old


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('existing_state', [None, 'failed', 'suppressed'])
def test_cancelled_old_anchor_allows_real_current_advance_without_live_target(queue, legacy, existing_state):
    discovery, old = cancelled_for_old_anchor(queue)
    if legacy:
        # Old builds kept the previous defer result; cancellation cause remains
        # in their durable CURRENT_SOURCE_INELIGIBLE audit event.
        queue.db.execute('UPDATE next_discovery_jobs SET result=? WHERE id=?',
                         (json.dumps({'reason': 'CANCELLED'}), old['id']))
    proposal = perform(old, source((3,), current=3, source_hash='b' * 40)[1], [])
    if existing_state is not None:
        previous = queue.request(proposal['request'], proposal['selection'])
        queue.db.execute('UPDATE tasks SET state=? WHERE id=?', (existing_state, previous['task_id']))
    targets, accepted = admission(queue, source((2,), current=2, source_hash='c' * 40))
    count = queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    key = discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'], targets[0][0]['version_key'])
    revived = discovery.get(key)
    assert key == old['id']
    assert revived['state'] == 'waiting'
    assert revived['payload']['anchor']['media']['episode'] == 2
    assert revived['payload']['target_offset'] == 1
    assert revived['nonce'] == ''
    assert discovery.accept(key, old['nonce'], proposal['request'], proposal['selection']) is None
    assert discovery.defer(key, old['nonce'], 'CANCELLED') is False
    assert queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == count
    assert discovery.claim()['id'] == key


@pytest.mark.parametrize('existing_state', ['queued', 'uncertain', 'ready'])
def test_cancelled_old_anchor_does_not_compete_with_existing_live_target(queue, existing_state):
    discovery, old = cancelled_for_old_anchor(queue)
    proposal = perform(old, source((3,), current=3, source_hash='b' * 40)[1], [])
    previous = queue.request(proposal['request'], proposal['selection'])
    if existing_state == 'uncertain':
        assert queue.begin_submission(previous['task_id'], 10**12, 10**12)
        queue.submitted(previous['task_id'], None)
    else:
        queue.db.execute('UPDATE tasks SET state=? WHERE id=?', (existing_state, previous['task_id']))
    frozen = discovery.get(old['id'])
    targets, accepted = admission(queue, source((2,), current=2, source_hash='c' * 40))
    key = discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'], targets[0][0]['version_key'])
    assert discovery.get(key) == frozen
    assert queue.status(previous['task_id'])['state'] == existing_state
    assert queue.status(previous['task_id'])['attempts'] == (1 if existing_state == 'uncertain' else 0)
    assert discovery.claim() is None


def test_same_actual_anchor_never_revives_cancelled_job(queue):
    discovery, old = cancelled_for_old_anchor(queue)
    queue.db.execute("UPDATE tasks SET state='queued' WHERE id=?", (old['payload']['task'],))
    value = source()
    value[0]['request_id'] = 'b' * 32
    targets, accepted = admission(queue, value)
    frozen = discovery.get(old['id'])
    key = discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'],
                             targets[0][0]['version_key'], target_offset=2)
    assert discovery.get(key) == frozen


def test_legacy_cancellation_cannot_borrow_an_older_anchor_failure_audit(queue):
    discovery, old = cancelled_for_old_anchor(queue)
    last_audit = queue.db.execute('SELECT MAX(at) FROM audit').fetchone()[0]
    queue.db.execute('UPDATE next_discovery_jobs SET result=?,updated=? WHERE id=?',
                     (json.dumps({'reason': 'CANCELLED'}), last_audit + 1, old['id']))
    frozen = discovery.get(old['id'])
    targets, accepted = admission(queue, source((2,), current=2, source_hash='c' * 40))
    key = discovery.schedule(accepted[0]['task_id'], targets[0][0]['media_id'], targets[0][0]['version_key'])
    assert discovery.get(key) == frozen


def test_existing_uncertain_future_target_supersedes_discovery(queue):
    discovery, job, _ = anchored_job(queue)
    proposal = perform(job, source((3,), current=3, source_hash='b' * 40)[1], [])
    accepted = queue.request(proposal['request'], proposal['selection'])
    assert queue.begin_submission(accepted['task_id'], 10**12, 10**12)
    queue.submitted(accepted['task_id'], None)
    # Simulate discovery process restart; only read-only discovery is retried.
    restarted = DiscoveryQueue(queue)
    assert restarted.claim() is None
    assert restarted.get(job['id'])['state'] == 'superseded'
    assert queue.status(accepted['task_id'])['state'] == 'uncertain'
    assert queue.status(accepted['task_id'])['attempts'] == 1


def test_window_jobs_and_transfers_remain_account_scoped(queue):
    discovery = service(queue)
    for account in ('account-a', 'account-b'):
        targets = prove(source(), account)
        accepted = [dict(queue.request(r, s), media_id=r['media_id'], version_key=r['version_key']) for r, s in targets]
        discovery.after_intent(targets, accepted)
    assert len(jobs(queue)) == 4
    assert queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 2


def playback_replies(job):
    from bobbi_core.discovery_playback import STARTED, SELECTED, OWNER
    anchor = job['payload']['anchor']
    media = anchor['media']
    url = 'http://127.0.0.1:8090/fixture'
    proof = dict(request_id='a' * 32, url_sha256=hashlib.sha256(url.encode()).hexdigest(),
                 ids={'tmdb_id': media['tmdb_id']}, tv_data={'season': media['season'], 'episode': media['episode']},
                 source_info_hash=anchor['selected']['source_info_hash'])
    players = [dict(playerid=1, type='video', playertype='internal')]
    return {1: players, 2: {STARTED: json.dumps(proof), SELECTED: 'a' * 32, OWNER: 'a' * 32},
            3: {'item': {'file': url}}, 4: {'Player.Caching': False, 'Player.Paused': False}, 5: players}


def test_e2_discovery_admitted_during_smooth_exact_current_playback(queue):
    from bobbi_core.discovery_playback import admitted
    _, job, _ = anchored_job(queue)
    replies = playback_replies(job)
    assert admitted(job, replies)
    for flag in ('Player.Caching', 'Player.Paused'):
        changed = deepcopy(replies)
        changed[4][flag] = True
        assert not admitted(job, changed)
    job['payload']['target_offset'] = 3
    assert not admitted(job, replies)

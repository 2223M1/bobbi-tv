from copy import deepcopy
import sqlite3

import pytest

from bobbi_core.ledger import Ledger
from bobbi_core.preparation_intake import Intake


@pytest.fixture
def intake(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', sqlite3.dbapi2.connect)
    with Ledger(tmp_path / 'ledger.db') as ledger:
        yield Intake(ledger)


def body(identifier='a' * 32):
    return dict(request_id=identifier,
                media=dict(tmdb_id=1, kind='movie', season=0, episode=0, anime=False, title='Film', release_title='Film 2026'),
                selected=dict(source_info_hash='b' * 40, torrent_file_id=7, torrent_path='film.mkv', torrent_file_bytes=1000),
                purpose='current')


def test_durable_intent_is_idempotent_but_not_playable(intake):
    assert intake.accept(body())['state'] == 'queued'
    assert intake.accept(body())['state'] == 'queued'
    assert intake.take() == body()
    assert intake.take() is None
    assert intake.finish('a' * 32, {'task_id': 'test'}, True)
    assert not intake.finish('a' * 32, {}, True)
    assert intake.status('a' * 32)['state'] == 'accepted'  # not ready


def test_restart_repeats_only_readonly_validation(intake):
    intake.accept(body())
    intake.take()
    recovered = Intake(intake.ledger)
    assert recovered.take() == body()


def test_same_request_cannot_be_retargeted(intake):
    intake.accept(body())
    other = body()
    other['selected']['hash'] = 'different'
    with pytest.raises(ValueError):
        intake.accept(other)


@pytest.mark.parametrize('extra', ['verified', 'qualification', 'token', 'url', 'publish'])
def test_ipc_cannot_manufacture_qualification(intake, extra):
    value = body() | {extra: True}
    with pytest.raises(ValueError):
        intake.accept(value)


def test_intake_backpressure_preserves_existing_work(intake):
    for n in range(64):
        intake.accept(body(format(n, '032x')))
    with pytest.raises(ValueError, match='full'):
        intake.accept(body('f' * 32))
    assert intake.status(format(0, '032x'))['state'] == 'queued'


def prepared_context(intake):
    import json
    from bobbi_core.preparation import PreparationQueue
    source = dict(provider='115', account='account', file_id='file-2', cloud_path='/115open/inbox/Series S01E02.mkv',
                  bytes=1000, kind='video', media_id='tmdb:tv:1:s1:e2', version_key='family')
    rid = intake.ledger.register(source, managed=True, identity_verified=True)
    intake.ledger.mark_ready(rid, dict(file_id='file-2', bytes=1000, version_key='family', duration=1400,
                            video_codec='hevc', source_binding=True, read_bytes=512, probe_sha256='c' * 64))
    q = PreparationQueue(intake.ledger)
    request = dict(provider='115', account='account', destination='/115open/inbox', source_info_hash='b' * 40,
                   media_id=source['media_id'], version_key='family', bytes_required=1000, purpose='next')
    selection = dict(file=dict(id=19, path='Series S01E02.mkv', length=1000), title='Series',
                     release_title='Series S01E02.mkv', anime=True, request_id='d' * 32,
                     metadata_sha256='c' * 64, work_identity={'provider': 'tmdb', 'id': 1})
    task = q.request(request, selection)['task_id']
    # A fixture binding; not a production shortcut or provider qualification.
    q.db.execute('INSERT INTO prepared_bindings VALUES(?,?,?,?,?)', (task, rid, source['media_id'], 'family', '{}'))
    return dict(request_id='e' * 32, resource_id=rid, media_id=source['media_id'],
                version_key='family', source_info_hash='b' * 40)


def test_prepared_second_episode_reenters_intake_from_real_binding(intake):
    message = prepared_context(intake)
    assert intake.accept_advance(message)['state'] == 'queued'
    assert intake.accept_advance(message)['state'] == 'queued'
    actual = intake.take()
    assert actual['request_id'] == 'e' * 32
    assert actual['media']['episode'] == 2
    assert actual['selected'] == dict(source_info_hash='b' * 40, torrent_file_id=19,
                                      torrent_path='Series S01E02.mkv', torrent_file_bytes=1000)
    assert actual['purpose'] == 'current'


@pytest.mark.parametrize('change', ['media', 'version', 'hash', 'url', 'not_ready'])
def test_advance_cannot_self_certify_other_current_file(intake, change):
    message = prepared_context(intake)
    if change == 'media': message['media_id'] = 'tmdb:tv:2:s1:e2'
    if change == 'version': message['version_key'] = 'other'
    if change == 'hash': message['source_info_hash'] = 'a' * 40
    if change == 'url': message['url'] = 'https://example/secret'
    if change == 'not_ready':
        item = intake.ledger._get(message['resource_id'])
        item['state'] = 'unavailable'
        intake.ledger._save(item)
    with pytest.raises(ValueError):
        intake.accept_advance(message)
    assert intake.take() is None


def naked_episode_context(intake, monkeypatch):
    import json
    from bobbi_core import source_intent
    from bobbi_core.preparation import PreparationQueue
    from test_cinema_source_intent import native_selector
    monkeypatch.setattr(source_intent, 'bind_selected_episode', lambda *args: None)
    files = [dict(id=n * 7, path='Series/Series [{:02}] [Group].mkv'.format(n), length=1000)
             for n in (1, 2, 3, 4)]
    original = dict(request_id='a' * 32, purpose='current',
        media=dict(tmdb_id=1, kind='tv', season=1, episode=1, anime=True,
                   title='Series', release_title='Series [S1 Fin]'),
        selected=dict(source_info_hash='b' * 40, torrent_file_id=7,
                      torrent_path=files[0]['path'], torrent_file_bytes=1000))
    metadata = dict(hash='b' * 40, title='Series', file_stats=files)
    catalog = dict(provider='tmdb', id=1, kind='tv', aliases=['Series'], year=2026,
                   response_sha256='c' * 64, ambiguous=False)
    selector = native_selector()
    queue = PreparationQueue(intake.ledger)
    def admit(value):
        targets = source_intent.verified_intents(value, metadata, 'account', '/115open/inbox', selector, catalog)
        intake.accept(value)
        assert intake.take() == value
        accepted = [dict(queue.request(r, s), media_id=r['media_id'], version_key=r['version_key'])
                    for r, s in targets]
        assert intake.finish(value['request_id'], {'tasks': accepted}, True)
        return targets, accepted
    def ready(target, accepted, request_id):
        request, selection = target
        source = dict(provider='115', account='account', file_id=str(selection['file']['id']),
                      cloud_path='/115open/inbox/' + selection['file']['path'], bytes=1000,
                      kind='video', media_id=request['media_id'], version_key=request['version_key'])
        rid = intake.ledger.register(source, managed=True, identity_verified=True)
        intake.ledger.mark_ready(rid, dict(file_id=source['file_id'], bytes=1000, version_key=source['version_key'],
            duration=1400, video_codec='hevc', source_binding=True, read_bytes=512, probe_sha256='c' * 64))
        # Fixture publication only. No provider qualification is claimed here.
        queue.db.execute('INSERT INTO prepared_bindings VALUES(?,?,?,?,?)',
                         (accepted['task_id'], rid, source['media_id'], source['version_key'], '{}'))
        return dict(request_id=request_id, resource_id=rid, media_id=source['media_id'],
                    version_key=source['version_key'], source_info_hash='b' * 40)
    targets, accepted = admit(original)
    message = ready(targets[1], accepted[1], 'e' * 32)
    return message, original, metadata, catalog, selector, admit, ready


def test_prepared_pack_keeps_season_context_across_multiple_advances(intake, monkeypatch):
    message, original, metadata, catalog, selector, admit, ready = naked_episode_context(intake, monkeypatch)
    assert intake.accept_advance(message)['state'] == 'queued'
    value = intake.take()
    assert value['media']['release_title'] == original['media']['release_title']
    assert value['media']['episode'] == 2
    # Complete this real validation path, without forging a successful result.
    from bobbi_core.source_intent import verified_intents
    from bobbi_core.preparation import PreparationQueue
    targets = verified_intents(value, metadata, 'account', '/115open/inbox', selector, catalog)
    queue = PreparationQueue(intake.ledger)
    accepted = [dict(queue.request(r, s), media_id=r['media_id'], version_key=r['version_key']) for r, s in targets]
    assert intake.finish(value['request_id'], {'tasks': accepted}, True)
    assert [r['media_id'] for r, _ in targets] == ['tmdb:tv:1:s1:e2', 'tmdb:tv:1:s1:e3']
    next_message = ready(targets[1], accepted[1], 'f' * 32)
    intake.accept_advance(next_message)
    next_value = intake.take()
    following = verified_intents(next_value, metadata, 'account', '/115open/inbox', selector, catalog)
    assert [r['media_id'] for r, _ in following] == ['tmdb:tv:1:s1:e3', 'tmdb:tv:1:s1:e4']
    assert intake.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 1


@pytest.mark.parametrize('change', ['unaccepted', 'foreign_hash', 'foreign_work', 'foreign_season',
                                  'foreign_task', 'foreign_version', 'foreign_episode'])
def test_season_context_cannot_be_borrowed_from_unrelated_intent(intake, monkeypatch, change):
    import json
    from bobbi_core.source_intent import verified_intents
    message, original, metadata, catalog, selector, _, _ = naked_episode_context(intake, monkeypatch)
    row = intake.db.execute('SELECT payload,result FROM preparation_intents WHERE id=?', (original['request_id'],)).fetchone()
    payload, result = json.loads(row[0]), json.loads(row[1])
    if change == 'unaccepted':
        intake.db.execute("UPDATE preparation_intents SET state='failed' WHERE id=?", (original['request_id'],))
    elif change == 'foreign_hash': payload['selected']['source_info_hash'] = 'c' * 40
    elif change == 'foreign_work': payload['media']['tmdb_id'] = 2
    elif change == 'foreign_season': payload['media']['season'] = 2
    elif change == 'foreign_task':
        for task in result['tasks']: task['task_id'] = '0' * 32
    elif change == 'foreign_version':
        for task in result['tasks']: task['version_key'] = 'other'
    else:
        for task in result['tasks']: task['media_id'] = 'tmdb:tv:1:s1:e99'
    intake.db.execute('UPDATE preparation_intents SET payload=?,result=? WHERE id=?',
                     (json.dumps(payload), json.dumps(result), original['request_id']))
    intake.accept_advance(message)
    value = intake.take()
    assert value['media']['release_title'] != original['media']['release_title']
    with pytest.raises(ValueError):
        verified_intents(value, metadata, 'account', '/115open/inbox', selector, catalog)


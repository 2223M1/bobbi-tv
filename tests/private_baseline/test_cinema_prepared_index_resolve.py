import json
import sqlite3

import pytest

from lib.cinema.ledger import Ledger
from lib.cinema.preparation import PreparationQueue
from lib.cinema.prepared_index import document, load, publish, selected_cloud
from lib.cinema.prepared_resolver import PreparedResolver


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', sqlite3.dbapi2.connect)
    with Ledger(tmp_path / 'ledger.db') as ledger:
        q = PreparationQueue(ledger)
        request = dict(provider='115', account='account', destination='/115open/inbox', source_info_hash='a' * 40,
                       media_id='tmdb:tv:1:s1:e1', version_key='b' * 64, bytes_required=1000, purpose='current')
        selection = dict(file=dict(id=7, path='Series S01E01.mkv', length=1000), title='Series',
                         release_title='Series S01E01.mkv', anime=False, request_id='f' * 32,
                         metadata_sha256='c' * 64, work_identity={'provider': 'tmdb'})
        task = q.request(request, selection)['task_id']
        q.begin_submission(task, 100000, 90000)
        q.submitted(task, True)
        q.observe(task, dict(account='account', destination='/115open/inbox', source_info_hash='a' * 40,
                             state='finished', file_id='root', parent_id='dest'))
        file = dict(provider='115', account='account', file_id='cloud-file', cloud_path='/115open/inbox/Series S01E01.mkv',
                    bytes=1000, kind='video', media_id=request['media_id'], version_key=request['version_key'])
        resource = ledger.register(file, managed=True, identity_verified=True)
        ledger.mark_ready(resource, dict(file_id='cloud-file', bytes=1000, version_key='b' * 64,
            source_binding=True, read_bytes=500, probe_sha256='d' * 64, duration=1400, video_codec='hevc'))
        q.publish(task, resource, dict(source_info_hash='a' * 40, cloud_root_id='root', cloud_file_id='cloud-file',
            cloud_path=file['cloud_path'], torrent_path=selection['file']['path'], torrent_file_id=7, bytes=1000))
        yield q, resource, tmp_path


class Provider:
    def __init__(self):
        self.accounts = ['account', 'account']
        self.rows = [dict(file_id='cloud-file', path='/115open/inbox/Series S01E01.mkv', bytes=1000,
                          directory=False, forbidden=False)]
    def account_scope(self):
        return self.accounts.pop(0)
    def identified_files(self, path):
        return self.rows


def body(resource, **changes):
    return dict(request_id='f' * 32, verification_id='e' * 32, resource_id=resource, generation=1, account='account',
                source_info_hash='a' * 40, media_id='tmdb:tv:1:s1:e1') | changes


def test_projection_roundtrip_and_account_filter(prepared):
    q, resource, folder = prepared
    path = folder / 'prepared.json'
    assert publish(q, path, 'account') == 1
    value = load(path)
    assert value == document(q, 'account')
    assert document(q, 'different-account')['titles'] == []
    data = dict(info_hash='a' * 40, ids={'tmdb_id': 1}, mode='tv', tv_data={'season': 1, 'episode': 1})
    assert selected_cloud(data, value)['key'] == resource
    assert selected_cloud(dict(data, tv_data={'season': 1, 'episode': 2}), value) is None


def test_projection_subtitle_identity_comes_from_qualified_source_tuple(prepared):
    from lib.cinema.subtitle_binding import prepared_video
    q, resource, folder = prepared
    value = document(q, 'account')
    assert value['titles'][0]['sources'][0]['video_context'] == prepared_video(q, resource, 'a' * 40)


@pytest.mark.parametrize('field,value', [('prepared_account', 'old-account'), ('state', 'pending'),
    ('prepared_source_info_hash', 'wrong'), ('path', '/115open/../wrong')])
def test_invalid_projection_is_not_ready(prepared, field, value):
    q, _, folder = prepared
    data = document(q, 'account')
    data['titles'][0]['sources'][0][field] = value
    path = folder / 'invalid.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        load(path)


def test_fresh_resolve_checks_file_then_account_again(prepared):
    q, resource, _ = prepared
    provider = Provider()
    resolver = PreparedResolver(q, 'account', provider)
    plan = resolver.plan(body(resource))
    assert q.ledger.get(resource)['active_lease']
    result = resolver.finish(plan, resolver.perform(plan))
    assert result['state'] == 'ready'
    assert result['resource_id'] == resource
    assert not provider.accounts


def test_resolve_observer_records_only_request_phase_duration(prepared):
    q, resource, _ = prepared
    events = []
    resolver = PreparedResolver(q, 'account', Provider(), observer=events.append)
    plan = resolver.plan(body(resource))
    assert resolver.finish(plan, resolver.perform(plan))['state'] == 'ready'
    assert [r['phase'] for r in events] == ['resolve_owner_plan', 'resolve_identity_io', 'resolve_owner_finish']
    assert all(set(r) == {'request_id', 'phase', 'seconds'} and r['request_id'] == 'f'*32
               and r['seconds'] >= 0 for r in events)


@pytest.mark.parametrize('accounts', [['other'], ['account', 'other']])
def test_account_change_before_or_during_resolve_rejects(prepared, accounts):
    q, resource, _ = prepared
    provider = Provider()
    provider.accounts = accounts
    resolver = PreparedResolver(q, 'account', provider)
    plan = resolver.plan(body(resource))
    assert resolver.finish(plan, resolver.perform(plan))['state'] == 'unavailable'
    assert not q.ledger.get(resource)['active_lease']


@pytest.mark.parametrize('field,value', [('file_id', 'new-file'), ('bytes', 999), ('path', '/115open/other.mkv'),
    ('forbidden', True), ('directory', True)])
def test_cloud_file_drift_rejects_static_snapshot(prepared, field, value):
    q, resource, _ = prepared
    provider = Provider()
    provider.rows[0][field] = value
    resolver = PreparedResolver(q, 'account', provider)
    plan = resolver.plan(body(resource))
    assert resolver.finish(plan, resolver.perform(plan))['state'] == 'unavailable'


@pytest.mark.parametrize('changes', [dict(account='other'), dict(generation=0), dict(media_id='tmdb:tv:1:s1:e2'),
    dict(source_info_hash='c' * 40)])
def test_resolve_input_must_match_ledger(prepared, changes):
    q, resource, _ = prepared
    with pytest.raises(ValueError):
        PreparedResolver(q, 'account', Provider()).plan(body(resource, **changes))


def test_generation_change_during_network_read_rejects_late_result(prepared):
    q, resource, _ = prepared
    resolver = PreparedResolver(q, 'account', Provider())
    plan = resolver.plan(body(resource))
    result = resolver.perform(plan)
    q.db.execute("UPDATE settings SET value='2' WHERE key='prepared_generation'")
    assert resolver.finish(plan, result)['state'] == 'unavailable'


def scoped_body(q, resource):
    item = document(q, 'account')['titles'][0]['sources'][0]
    return body(resource, qualification=item['prepared_qualification'])


def test_unrelated_publication_before_and_during_resolve_does_not_starve_current_file(prepared):
    q, resource, _ = prepared
    request = scoped_body(q, resource)
    q.db.execute("UPDATE settings SET value='2' WHERE key='prepared_generation'")
    resolver = PreparedResolver(q, 'account', Provider())
    plan = resolver.plan(request)
    proof = resolver.perform(plan)
    for generation in range(3, 20):
        q.db.execute("UPDATE settings SET value=? WHERE key='prepared_generation'", (str(generation),))
        assert resolver.finish(plan, proof)['state'] == 'ready'
    assert resolver.finish(plan, proof)['qualification'] == request['qualification']


def test_watch_favorite_and_lease_changes_do_not_change_file_qualification(prepared):
    q, resource, _ = prepared
    request = scoped_body(q, resource)
    q.ledger.user_action(resource, 'favorite')
    q.ledger.user_action(resource, 'details')
    q.ledger.acquire(resource, 'other-reader', 'next')
    assert scoped_body(q, resource)['qualification'] == request['qualification']
    resolver = PreparedResolver(q, 'account', Provider())
    plan = resolver.plan(request)
    assert resolver.finish(plan, resolver.perform(plan))['state'] == 'ready'


@pytest.mark.parametrize('change', ['request', 'purpose', 'both'])
def test_same_exact_source_repreparation_does_not_invalidate_its_published_qualification(prepared, change):
    q, resource, _ = prepared
    request = scoped_body(q, resource)
    row = q.db.execute('SELECT payload FROM preparation_targets').fetchone()
    target = json.loads(row[0])
    selection = target.pop('_selection')
    if change in ('request', 'both'):
        selection['request_id'] = '1' * 32
    if change in ('purpose', 'both'):
        target['purpose'] = 'next'
    outcome = q.request(target, selection)
    assert outcome['existing']
    assert q.generation() == request['generation']
    assert scoped_body(q, resource)['qualification'] == request['qualification']
    resolver = PreparedResolver(q, 'account', Provider())
    plan = resolver.plan(request)
    assert resolver.finish(plan, resolver.perform(plan))['state'] == 'ready'


@pytest.mark.parametrize('field,value', [('title', 'Alternate display title'), ('anime', True),
                                       ('work_identity', {'provider': 'tmdb', 'verified_mapping': 'updated'})])
def test_reaccepted_target_evidence_invalidates_projection_generation(prepared, field, value):
    q, resource, folder = prepared
    path = folder / 'projection.json'
    generation = publish(q, path, 'account')
    previous = scoped_body(q, resource)
    target = json.loads(q.db.execute('SELECT payload FROM preparation_targets').fetchone()[0])
    selection = target.pop('_selection')
    selection[field] = value
    assert q.request(target, selection)['existing']
    # Existing service publication is generation-driven. Accepted changes to
    # signed target evidence must not leave the UI's old token indefinitely.
    assert q.generation() == generation + 1
    with pytest.raises(ValueError, match='qualification changed'):
        PreparedResolver(q, 'account', Provider()).plan(previous)
    publish(q, path, 'account')
    current = scoped_body(q, resource)
    current['generation'] = q.generation()
    resolver = PreparedResolver(q, 'account', Provider())
    plan = resolver.plan(current)
    assert resolver.finish(plan, resolver.perform(plan))['state'] == 'ready'
    assert load(path) == document(q, 'account')
    # Repeating precisely the same intake does not churn the UI generation.
    q.request(target, selection)
    assert q.generation() == generation + 1


def test_target_publication_failure_rolls_back_evidence_and_audit(prepared):
    q, resource, _ = prepared
    before = q.db.execute('SELECT payload FROM preparation_targets').fetchone()[0]
    previous = scoped_body(q, resource)
    audits = q.db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
    target = json.loads(before)
    selection = target.pop('_selection')
    selection['title'] = 'Revised display title'
    q.db.execute("CREATE TRIGGER reject_generation BEFORE UPDATE ON settings "
                 "WHEN OLD.key='prepared_generation' BEGIN SELECT RAISE(ABORT,'test publication failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='test publication failure'):
        q.request(target, selection)
    assert q.db.execute('SELECT payload FROM preparation_targets').fetchone()[0] == before
    assert q.db.execute('SELECT COUNT(*) FROM audit').fetchone()[0] == audits
    assert q.generation() == previous['generation']
    assert scoped_body(q, resource)['qualification'] == previous['qualification']
    assert not q.db.in_transaction


def test_unpublished_target_update_does_not_invent_a_ready_generation(prepared):
    q, _, _ = prepared
    target = json.loads(q.db.execute('SELECT payload FROM preparation_targets').fetchone()[0])
    selection = target.pop('_selection')
    target['media_id'] = 'tmdb:tv:1:s1:e2'
    selection['file'] = dict(id=8, path='Series S01E02.mkv', length=1000)
    selection['release_title'] = 'Series S01E02.mkv'
    q.request(target, selection)
    before = q.generation()
    selection['title'] = 'Updated but still unprepared'
    q.request(target, selection)
    assert q.generation() == before
    assert len(document(q, 'account')['titles'][0]['sources']) == 1


@pytest.mark.parametrize('field', ['file', 'metadata_sha256', 'release_title', 'work_identity'])
def test_exact_preparation_evidence_remains_part_of_qualification(prepared, field):
    q, resource, _ = prepared
    request = scoped_body(q, resource)
    payload = json.loads(q.db.execute('SELECT payload FROM preparation_targets').fetchone()[0])
    selected = payload['_selection']
    if field == 'file': selected[field]['path'] = 'Other.mkv'
    elif field == 'work_identity': selected[field] = {'provider': 'other'}
    else: selected[field] = 'changed'
    q.db.execute('UPDATE preparation_targets SET payload=?', (json.dumps(payload),))
    with pytest.raises(ValueError):
        PreparedResolver(q, 'account', Provider()).plan(request)


@pytest.mark.parametrize('mutation', ['path', 'bytes', 'qualification', 'suppressed', 'binding', 'target', 'deleted'])
def test_same_resource_or_binding_drift_rejects_scoped_late_result_and_releases_probe(prepared, mutation):
    q, resource, _ = prepared
    resolver = PreparedResolver(q, 'account', Provider())
    plan = resolver.plan(scoped_body(q, resource))
    proof = resolver.perform(plan)
    item = q.ledger._get(resource)
    if mutation == 'path': item['cloud_path'] += '.renamed'
    elif mutation == 'bytes': item['bytes'] += 1
    elif mutation == 'qualification': item['qualification']['probe_sha256'] = '9' * 64
    elif mutation == 'suppressed': item['suppressed'] = True
    elif mutation == 'binding': q.db.execute("UPDATE prepared_bindings SET evidence='{}'")
    elif mutation == 'target': q.db.execute("UPDATE preparation_targets SET payload='{}'")
    elif mutation == 'deleted': q.db.execute('DELETE FROM prepared_bindings WHERE resource=?', (resource,))
    if mutation in ('path', 'bytes', 'qualification', 'suppressed'):
        q.ledger._save(item)
    assert resolver.finish(plan, proof)['state'] == 'unavailable'
    assert not q.db.execute('SELECT 1 FROM leases WHERE resource=? AND owner=?', (resource, plan['body']['verification_id'])).fetchone()


def test_old_snapshot_of_requalified_resource_is_rejected_before_cloud_io(prepared):
    q, resource, _ = prepared
    request = scoped_body(q, resource)
    item = q.ledger._get(resource)
    item['qualification']['probe_sha256'] = '9' * 64
    q.ledger._save(item)
    with pytest.raises(ValueError, match='qualification changed'):
        PreparedResolver(q, 'account', Provider()).plan(request)

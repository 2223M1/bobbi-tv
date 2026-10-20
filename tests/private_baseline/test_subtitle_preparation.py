from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest

from lib.cinema.ledger import Ledger
from lib.cinema.preparation import PreparationQueue
from lib.cinema.subtitle_preparation import SubtitlePreparation
from lib.cinema.subtitle_store import SubtitleStore
from lib.cinema.metadata_cache import MetadataCache
from lib.cinema.prepared_protection import PreparedProtection
from lib.cinema.prepared_resolver import PreparedResolver
from test_cinema_prepared_index_resolve import body
from test_subtitle_pack import data, metadata, matcher
from test_playback_authority import row


@pytest.fixture
def subject(tmp_path, monkeypatch, matcher):
    monkeypatch.setattr(sqlite3, 'connect', sqlite3.dbapi2.connect)
    raw = data()
    with Ledger(tmp_path / 'ledger.db') as ledger:
        queue = PreparationQueue(ledger)
        request = dict(provider='115', account='account', destination='/115open/inbox', source_info_hash='a' * 40,
                       media_id='tmdb:tv:1:s1:e1', version_key='b' * 64, bytes_required=1000, purpose='current')
        selection = dict(file=dict(id=7, path='Series S01E01.mkv', length=1000), title='Series',
                         release_title='Series', anime=False, request_id='f' * 32,
                         metadata_sha256='c' * 64, work_identity={'provider': 'tmdb'})
        task = queue.request(request, selection)['task_id']
        queue.begin_submission(task, 100000, 90000)
        queue.submitted(task, True)
        queue.observe(task, dict(account='account', destination=request['destination'], source_info_hash='a' * 40,
                                state='finished', file_id='root', parent_id='dest'))
        file = dict(provider='115', account='account', file_id='cloud-file',
                    cloud_path='/115open/inbox/Series/Series S01E01.mkv', bytes=1000, kind='video',
                    media_id=request['media_id'], version_key=request['version_key'])
        rid = ledger.register(file, managed=True, identity_verified=True)
        ledger.mark_ready(rid, dict(file_id='cloud-file', bytes=1000, version_key='b' * 64,
            source_binding=True, read_bytes=500, probe_sha256='d' * 64, duration=1200, video_codec='hevc'))
        queue.publish(task, rid, dict(source_info_hash='a' * 40, cloud_root_id='root', cloud_file_id='cloud-file',
            cloud_path=file['cloud_path'], torrent_path=selection['file']['path'], torrent_file_id=7, bytes=1000))
        cache = MetadataCache(tmp_path / 'metadata')
        cache.store(metadata(raw))
        store = SubtitleStore(ledger, tmp_path / 'subs', metadata_cache=cache, release_matcher=matcher)
        provider = SimpleNamespace(account_scope=lambda: 'account', session=object(),
            offline_tasks=lambda _: [dict(info_hash='a' * 40, status=2, file_id='root', parent_id='dest')])
        listing = {
            '/115open': [dict(name='inbox', path='/115open/inbox', file_id='dest', directory=True)],
            '/115open/inbox': [dict(name='Series', path='/115open/inbox/Series', file_id='root', directory=True)],
            '/115open/inbox/Series': [dict(name='Series S01E01.mkv', path=file['cloud_path'], file_id='cloud-file',
                                         directory=False, bytes=1000),
                dict(name='Series S01E01.chs.srt', path='/115open/inbox/Series/Series S01E01.chs.srt',
                     file_id='cloud-sub', directory=False, bytes=len(raw))]}
        provider.identified_files = lambda path: deepcopy(listing[path])
        qualifier = SimpleNamespace(download_url=lambda p, item: 'http://127.0.0.1/subtitle-only')
        reads = []
        def reader(session, url, size):
            def chunks(start, end):
                reads.append((url, start, end))
                yield raw
            return chunks
        monkeypatch.setattr('lib.cinema.subtitle_preparation.http_range_reader', reader)
        exports = []
        def export(s, r):
            exports.append(r['key'])
            return dict(path='/storage/.kodi/userdata/addon_data/plugin.video.bobbi/subtitle-browser/'
                        + r['subtitle_sha256'][:32] + '.srt', sha256=r['subtitle_sha256'], bytes=r['bytes'])
        monkeypatch.setattr('lib.cinema.subtitle_export.export', export)
        worker = SubtitlePreparation(queue, store, cache, matcher, provider, qualifier)
        yield SimpleNamespace(queue=queue, rid=rid, worker=worker, provider=provider,
                              listing=listing, reads=reads, raw=raw, exports=exports, file=file)


def finish(subject):
    plan = subject.worker.next_action()
    result = subject.worker.perform(plan)
    assert result['state'] == 'CANDIDATE'
    assert subject.worker.complete(plan, result)
    return plan, result


def test_pipeline_reuses_real_matcher_mapping_store_and_only_reads_subtitle(subject):
    plan, result = finish(subject)
    assert subject.reads == [('http://127.0.0.1/subtitle-only', 0, len(subject.raw) - 1)]
    assert subject.worker.next_action() is None
    assert not subject.worker.complete(plan, result)
    assert len(subject.exports) == 1
    state = subject.queue.db.execute('SELECT state FROM subtitle_preparation').fetchone()[0]
    assert state == 'READY_NOT_VISUAL_PROOF'
    assert subject.queue.generation() == 1  # No republishing/video qualification or cloud submission.


def test_legacy_negative_rechecked_once_after_matcher_policy_change(subject):
    worker, db = subject.worker, subject.queue.db
    actual_matcher = worker.matcher
    worker.matcher = lambda *args: []
    assert worker.next_action() is None
    first = db.execute('SELECT attempts,detail FROM subtitle_preparation').fetchone()
    assert json.loads(first['detail'])['matcher_policy']
    assert worker.next_action() is None  # Same-policy negative must not spin.
    assert db.execute('SELECT attempts FROM subtitle_preparation').fetchone()[0] == first['attempts']
    db.execute('UPDATE subtitle_preparation SET detail=?', (json.dumps(dict(reason='NO_UNIQUE_RELEASE_CHINESE_FILE')),))
    worker.matcher = actual_matcher
    plan, result = finish(subject)
    assert plan['attempts'] == 1
    assert worker.next_action() is None
    assert len(subject.reads) == 1 and subject.queue.generation() == 1


def test_legacy_negative_does_not_replace_manual_subtitle_revision(subject):
    finish(subject)
    db = subject.queue.db
    row = db.execute('SELECT seq,payload FROM subtitle_revisions').fetchone()
    payload = json.loads(row['payload'])
    payload['manual_intent'] = 1
    db.execute('UPDATE subtitle_revisions SET payload=? WHERE seq=?', (json.dumps(payload), row['seq']))
    db.execute("UPDATE subtitle_preparation SET state='NO_EXACT_SIDECAR',detail='{}'")
    assert subject.worker.next_action() is None
    assert len(subject.reads) == 1


def test_legacy_content_failure_rechecks_once_and_records_failure_stage(subject):
    worker, db = subject.worker, subject.queue.db
    worker._record(subject.rid, '', 'READ_UNAVAILABLE', 3, dict(reason='ValueError'))
    subject.listing['/115open/inbox/Series'][1]['bytes'] += 1
    for attempt in range(1, 4):
        plan = worker.next_action()
        assert plan['attempts'] == attempt
        result = worker.perform(plan)
        assert result['stage'] == 'subtitle_mapping'
        assert worker.complete(plan, result)
        db.execute('UPDATE subtitle_preparation SET next_attempt=0')
    assert worker.next_action() is None
    assert len(subject.reads) == 0
    detail = json.loads(db.execute('SELECT detail FROM subtitle_preparation').fetchone()[0])
    assert detail['content_policy'] and detail['stage'] == 'subtitle_mapping'


@pytest.mark.parametrize('reason', ['TimeoutError', 'ACCOUNT_OR_CANCELLED'])
def test_content_policy_does_not_reset_exhausted_transport_or_account_work(subject, reason):
    subject.worker._record(subject.rid, '', 'READ_UNAVAILABLE', 3, dict(reason=reason))
    assert subject.worker.next_action() is None


def test_content_policy_does_not_replace_manual_subtitle(subject):
    finish(subject)
    db = subject.queue.db
    row = db.execute('SELECT seq,payload FROM subtitle_revisions').fetchone()
    payload = json.loads(row['payload']); payload['manual_intent'] = 1
    db.execute('UPDATE subtitle_revisions SET payload=? WHERE seq=?', (json.dumps(payload), row['seq']))
    db.execute("UPDATE subtitle_preparation SET state='READ_UNAVAILABLE',detail=?", (json.dumps(dict(reason='ValueError')),))
    assert subject.worker.next_action() is None


def test_rar_asset_policy_revisits_only_prior_no_assets_once(subject):
    from bobbi_core.subtitle_font_preparation import SubtitleFontPreparation, KEY, ASSET_POLICY
    worker = SubtitleFontPreparation(subject.worker, None, None, lambda: False)
    db = subject.queue.db
    entries = [('a', 'FONT_INPUTS_UNAVAILABLE', 'NO_RELEASE_FONT_ASSETS'),
               ('b', 'FONT_INPUTS_UNAVAILABLE', 'ValueError'),
               ('c', 'FONT_INPUTS_BOUND', 'READY')]
    for binding, state, reason in entries:
        db.execute('INSERT INTO subtitle_font_preparation VALUES(?,?,?,?,?,?)',
                   (binding, subject.rid, state, 3, 0, json.dumps(dict(reason=reason))))
    db.execute('UPDATE settings SET value=? WHERE key=?', ('legacy', KEY + ':asset-policy'))
    worker._recheck_asset_policy()
    assert [tuple(r) for r in db.execute('SELECT binding,state,attempts FROM subtitle_font_preparation ORDER BY binding')] == [
        ('a', 'RETRY', 0), ('b', 'FONT_INPUTS_UNAVAILABLE', 3), ('c', 'FONT_INPUTS_BOUND', 3)]
    db.execute("UPDATE subtitle_font_preparation SET state='FONT_INPUTS_UNAVAILABLE',attempts=3 WHERE binding='a'")
    worker._recheck_asset_policy()
    assert db.execute("SELECT attempts FROM subtitle_font_preparation WHERE binding='a'").fetchone()[0] == 3
    assert db.execute('SELECT value FROM settings WHERE key=?', (KEY + ':asset-policy',)).fetchone()[0] == ASSET_POLICY


@pytest.mark.parametrize('change', ['video_id', 'video_size', 'subtitle_size', 'account', 'task_root'])
def test_cloud_drift_never_applies_wrong_caption(subject, change):
    plan = subject.worker.next_action()
    if change == 'video_id': subject.listing['/115open/inbox/Series'][0]['file_id'] = 'new-file'
    elif change == 'video_size': subject.listing['/115open/inbox/Series'][0]['bytes'] += 1
    elif change == 'subtitle_size': subject.listing['/115open/inbox/Series'][1]['bytes'] += 1
    elif change == 'account': subject.provider.account_scope = lambda: 'another-account'
    else: subject.provider.offline_tasks = lambda _: [dict(info_hash='a'*40, status=2, file_id='different', parent_id='dest')]
    result = subject.worker.perform(plan)
    assert subject.worker.complete(plan, result)
    assert subject.queue.db.execute('SELECT state FROM subtitle_preparation').fetchone()[0] != 'READY_NOT_VISUAL_PROOF'
    assert subject.exports == []


def test_first_failure_retained_and_retry_is_bounded(subject):
    subject.provider.account_scope = lambda: 'wrong'
    for attempt in range(3):
        plan = subject.worker.next_action()
        assert subject.worker.complete(plan, subject.worker.perform(plan))
        subject.queue.db.execute('UPDATE subtitle_preparation SET next_attempt=0')
    assert subject.worker.next_action() is None
    assert subject.queue.db.execute('SELECT attempts FROM subtitle_preparation').fetchone()[0] == 3
    assert len(subject.reads) == 0


def receipt_for(subject):
    protection = PreparedProtection(subject.queue.ledger)
    resolver = PreparedResolver(subject.queue, 'account', subject.provider, protection)
    plan = resolver.plan(body(subject.rid))
    assert resolver.finish(plan, True)['state'] == 'ready'
    protected = json.loads(subject.queue.db.execute('SELECT payload FROM prepared_playback_protection').fetchone()[0])
    current = row('f'*32, protected['identities'][0], subtitle_intent=0, subtitle_auto_intent=0)
    current['url_sha256'] = protected['url_sha256']
    return current


def test_playback_lookup_is_small_local_and_exactly_bound(subject):
    finish(subject)
    current = receipt_for(subject)
    before = (len(subject.reads), len(subject.exports))
    result = subject.worker.for_playback(current)
    assert result['state'] == 'ready'
    assert result['native_instance'] == current['native_instance']
    assert (len(subject.reads), len(subject.exports)) == before


@pytest.mark.parametrize('change', ['request', 'url', 'identity', 'manual', 'instance', 'version'])
def test_late_caption_has_no_authority_for_other_playback(subject, change):
    finish(subject)
    current = receipt_for(subject)
    if change == 'request': current['request_id'] = 'e'*32
    elif change == 'url': current['url_sha256'] = 'c'*64
    elif change == 'identity': current['file_identity'] = 'wrong'
    elif change == 'manual': current['subtitle_intent'] = 1
    elif change == 'version': subject.queue.db.execute("UPDATE subtitle_preparation SET video_key=?", ('c'*64,))
    else:
        row = subject.queue.db.execute('SELECT payload FROM prepared_playback_protection').fetchone()
        payload = json.loads(row[0]); payload['native_instance'] = str(uuid4())
        subject.queue.db.execute('UPDATE prepared_playback_protection SET payload=?', (json.dumps(payload),))
    assert subject.worker.for_playback(current)['state'] == 'unavailable'

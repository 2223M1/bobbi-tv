"""Same-release subtitle work on the existing preparation lane and ledger.

Only a read-only provider operation is performed. No subtitle search, cloud
submission, video reading, Kodi control or guessed filename mapping occurs.
"""
from copy import deepcopy
import json
from pathlib import PurePosixPath
import time

from bobbi_core.cloud_mapping import map_torrent_file
from bobbi_core.ledger import encode
from bobbi_core.ledger_extension import install_extension
from bobbi_core.media_probe import http_range_reader
from bobbi_core.native_receipt import receipt
from bobbi_core.subtitle_binding import prepared_video
from bobbi_core.subtitle_pack import select, timing

SCHEMA_KEY = 'extension:subtitle-preparation:schema'
DDL = {'subtitle_preparation': '''CREATE TABLE subtitle_preparation(
    resource TEXT PRIMARY KEY REFERENCES resources(id), video_key TEXT NOT NULL,
    state TEXT NOT NULL, attempts INTEGER NOT NULL, next_attempt REAL NOT NULL,
    detail TEXT NOT NULL)'''}


class SubtitlePreparation:
    def __init__(self, queue, store, metadata_cache, matcher, provider, qualifier, cancelled=lambda: False):
        self.queue, self.store, self.cache, self.matcher = queue, store, metadata_cache, matcher
        self.provider, self.qualifier, self.cancelled = provider, qualifier, cancelled
        self.pending = None
        install_extension(queue.ledger, SCHEMA_KEY, 1, DDL)

    def _record(self, rid, key, state, attempts, detail, delay=0):
        with self.queue.ledger.transaction():
            self._record_in_transaction(rid, key, state, attempts, detail, delay)

    def _record_in_transaction(self, rid, key, state, attempts, detail, delay=0):
        """Join the owner's font transaction; never silently autocommit readiness."""
        if not self.queue.db.in_transaction:
            raise RuntimeError('Subtitle readiness requires an owned transaction')
        self.queue.db.execute('INSERT INTO subtitle_preparation VALUES(?,?,?,?,?,?) '
            'ON CONFLICT(resource) DO UPDATE SET video_key=excluded.video_key,state=excluded.state,'
            'attempts=excluded.attempts,next_attempt=excluded.next_attempt,detail=excluded.detail',
            (rid, key, state, attempts, self.queue.now() + delay, encode(detail)))
        self.queue.ledger._audit('subtitle_preparation', rid, dict(state=state, attempts=attempts, **detail))

    def next_action(self):
        if self.pending is not None or self.cancelled():
            return None
        rows = self.queue.db.execute('''SELECT b.resource,b.task FROM prepared_bindings b
            LEFT JOIN subtitle_preparation s ON b.resource=s.resource
            WHERE s.resource IS NULL OR (s.state='RETRY' AND s.next_attempt<=?)
            ORDER BY b.rowid LIMIT 1''', (self.queue.now(),)).fetchall()
        if not rows:
            return None
        rid, task = rows[0]
        if self.queue.db.execute('SELECT COUNT(*) FROM subtitle_preparation').fetchone()[0] >= 8192:
            return None
        row = self.queue.status(task)
        old = self.queue.db.execute('SELECT attempts FROM subtitle_preparation WHERE resource=?', (rid,)).fetchone()
        attempts = (old[0] if old else 0) + 1
        try:
            video = prepared_video(self.queue, rid, row['source_hash'])
            meta = self.cache.load(row['source_hash'])
            selection = select(video, meta, self.matcher) if meta is not None else None
            if selection is None:
                self._record(rid, video['key'], 'NO_EXACT_SIDECAR', attempts,
                             dict(reason='NO_UNIQUE_RELEASE_CHINESE_FILE'))
                return None
            item = self.queue.ledger.get(rid)
            self.pending = deepcopy(dict(resource=rid, task=task, video=video, selection=selection,
                account=row['account'], destination=row['destination'],
                observation=row['payload']['provider_observation'], duration=item['qualification']['duration'],
                attempts=attempts))
            return self.pending
        except (ValueError, KeyError, TypeError):
            self._record(rid, '', 'REJECTED_IDENTITY', attempts, dict(reason='SOURCE_CONTEXT_UNAVAILABLE'))
            return None

    def perform(self, plan):
        """Shared IO lane; original video bytes are never fetched here."""
        try:
            if self.cancelled() or self.provider.account_scope() != plan['account']:
                return dict(state='RETRY', reason='ACCOUNT_OR_CANCELLED')
            rows = [r for r in self.provider.offline_tasks(plan['destination'])
                    if r['info_hash'] == plan['video']['selected']['source_info_hash']]
            old = plan['observation']
            if (len(rows) != 1 or rows[0]['status'] != 2 or old['state'] != 'finished'
                    or any(rows[0][key] != old[key] for key in ('file_id', 'parent_id'))):
                return dict(state='RETRY', reason='CLOUD_TASK_CHANGED')
            video = map_torrent_file(self.provider, plan['destination'], rows[0], plan['selection']['video_file'])
            item = map_torrent_file(self.provider, plan['destination'], rows[0], plan['selection']['subtitle_file'])
            if self.cancelled():
                return dict(state='RETRY', reason='CANCELLED')
            url = self.qualifier.download_url(self.provider, item)
            reader = http_range_reader(self.provider.session, url, item['bytes'])(0, item['bytes'] - 1)
            raw, started = bytearray(), time.monotonic()
            try:
                for chunk in reader:
                    if self.cancelled() or time.monotonic() - started >= 5 or len(raw) + len(chunk) > item['bytes']:
                        return dict(state='RETRY', reason='SUBTITLE_READ_BUDGET')
                    raw.extend(chunk)
            finally:
                reader.close()
            if len(raw) != item['bytes'] or self.provider.account_scope() != plan['account']:
                return dict(state='RETRY', reason='INCOMPLETE_OR_ACCOUNT_CHANGED')
            raw = bytes(raw)
            proof = timing(plan['video'], raw, plan['selection'], plan['duration'])
            return dict(state='CANDIDATE', raw=raw, timing=proof,
                        cloud=dict(file_id=item['file_id'], path=item['path'], bytes=item['bytes'],
                                   video_file_id=video['file_id'], video_path=video['path'], video_bytes=video['bytes']))
        except Exception as error:
            return dict(state='RETRY', reason=type(error).__name__)

    def complete(self, plan, result):
        if self.pending != plan:
            return False
        self.pending = None
        rid, key, attempts = plan['resource'], plan['video']['key'], plan['attempts']
        if result.get('state') != 'CANDIDATE':
            self._record(rid, key, 'RETRY' if attempts < 3 else 'READ_UNAVAILABLE', attempts,
                         dict(reason=result.get('reason', 'WORKER_REJECTED')), delay=60)
            return True
        current = prepared_video(self.queue, rid, plan['video']['selected']['source_info_hash'])
        item = self.queue.ledger.get(rid)
        if (current != plan['video'] or any(item[a] != result['cloud'][b] for a, b in
                [('file_id', 'video_file_id'), ('cloud_path', 'video_path'), ('bytes', 'video_bytes')])):
            self._record(rid, key, 'REJECTED_IDENTITY', attempts, dict(reason='VIDEO_CHANGED_DURING_READ'))
            return True
        extension = PurePosixPath(plan['selection']['subtitle_file']['path']).suffix.casefold()
        record = self.store.put(current, result['raw'], extension, 'zh', True, False,
            dict(kind='same_release_pack', id='torrent:' + str(plan['selection']['subtitle_file']['id'])),
            timing=result['timing'])
        detail = dict(binding_key=record['key'], subtitle_sha256=record['subtitle_sha256'], cloud=result['cloud'])
        if record['state'] == 'READY_NOT_VISUAL_PROOF':
            from bobbi_core.subtitle_export import export
            detail['native_file'] = export(self.store, record)
        self._record(rid, key, record['state'], attempts,
                     detail)
        return True

    def for_playback(self, raw_receipt):
        """Small local reply, bound through existing prepared-playback protection.

The playback owner rechecks native identity/intent after this call and the
native actor checks again when applying. A bare media ID is never sufficient.
"""
        current = receipt(raw_receipt)
        if (current is None or current['phase'] != 'AV_STARTED'
                or type(current.get('subtitle_intent')) is not int
                or current['subtitle_intent'] != current.get('subtitle_auto_intent')):
            return dict(state='unavailable', reason='PLAYBACK_OR_MANUAL_INTENT')
        row = self.queue.db.execute('SELECT resource,payload FROM prepared_playback_protection WHERE request=?',
                                    (current['request_id'],)).fetchone()
        if row is None:
            return dict(state='unavailable', reason='NO_PREPARED_PLAYBACK_BINDING')
        protected = json.loads(row['payload'])
        if (current['url_sha256'] != protected['url_sha256'] or current['file_identity'] not in protected['identities']
                or protected.get('native_instance', current['native_instance']) != current['native_instance']):
            return dict(state='unavailable', reason='ACTUAL_VIDEO_CHANGED')
        jobs = self.queue.db.execute('SELECT detail,state,video_key FROM subtitle_preparation WHERE resource=?', (row['resource'],)).fetchone()
        if jobs is None or jobs['state'] not in {'READY_NOT_VISUAL_PROOF', 'STYLE_REVIEW_REQUIRED'}:
            return dict(state='pending' if jobs is None or jobs['state'] == 'RETRY' else 'unavailable',
                        reason=jobs['state'] if jobs else 'SUBTITLE_NOT_PREPARED')
        sources = self.queue.db.execute('SELECT DISTINCT t.source_hash FROM prepared_bindings b JOIN tasks t ON t.id=b.task '
                                        'WHERE b.resource=?', (row['resource'],)).fetchall()
        if len(sources) != 1:
            return dict(state='unavailable', reason='AMBIGUOUS_SOURCE_BINDING')
        video = prepared_video(self.queue, row['resource'], sources[0][0])
        if video['key'] != jobs['video_key']:
            return dict(state='unavailable', reason='PREPARED_VIDEO_VERSION_CHANGED')
        # Export was verified on completion, not in this latency-sensitive IPC.
        # The native actor independently validates immutable bytes at apply.
        detail = json.loads(jobs['detail'])
        file = detail.get('native_file')
        if not file or file['sha256'] != detail['subtitle_sha256']:
            return dict(state='unavailable', reason='SUBTITLE_NOT_EXPORTED')
        if PurePosixPath(file['path']).suffix.casefold() in {'.ass', '.ssa'}:
            activation = detail.get('font_activation', {})
            fonts = self.store.font_cache
            if (activation.get('request_id') != current['request_id']
                    or activation.get('release_key') != video['release_key'] or fonts is None
                    or not fonts.owns_activation(video['release_key'], detail['subtitle_sha256'],
                        current['request_id'], activation.get('font_hashes'))):
                return dict(state='unavailable', reason='FONT_ACTIVATION_NOT_OWNED')
        return dict(state='ready', font_acceptance=jobs['state'], file=file, video_key=video['key'],
                    native_instance=current['native_instance'], request_id=current['request_id'],
                    subtitle_intent=current['subtitle_intent'])

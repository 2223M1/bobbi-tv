"""Owner-thread font handoff for an already verified prepared-file request.

No font download or provider lookup here. The caller supplies the live playback
owner guard; local candidate coverage alone does not enable this IPC operation.
"""
import json
import re
from copy import deepcopy

from bobbi_core.subtitle_binding import prepared_video, style_reviewable
from bobbi_core.subtitle_export import export
from bobbi_core.subtitle_store import binding
from bobbi_core.runtime_measurement import measured


class FontPlaybackPreflight:
    def __init__(self, subtitles, fonts, allowed, exporter=export, observer=None):
        self.subtitles, self.fonts = subtitles, fonts
        self.queue, self.store = subtitles.queue, subtitles.store
        self.allowed, self.exporter = allowed, exporter
        self.observer = observer

    @measured('owner_plan')
    def plan(self, body):
        required = {'request_id', 'resource_id', 'source_info_hash', 'file_identity', 'boot_id', 'epoch'}
        if (not isinstance(body, dict) or set(body) != required
                or not all(isinstance(body[k], str) and re.fullmatch(pattern, body[k])
                    for k, pattern in (('request_id', '[0-9a-f]{32}'), ('resource_id', '[0-9a-f]{64}'),
                                       ('source_info_hash', '[0-9a-f]{40}'), ('boot_id', '[0-9a-f]{32}')))
                or type(body['epoch']) is not int or body['epoch'] < 1
                or not isinstance(body['file_identity'], str) or not 1 <= len(body['file_identity']) <= 1024):
            raise ValueError('Exact prepared font request required')
        if self.allowed(body) is not True:
            return dict(state='stale')
        row = self.queue.db.execute('SELECT resource,payload,startup_until FROM prepared_playback_protection WHERE request=?',
                                    (body['request_id'],)).fetchone()
        if (row is None or row['resource'] != body['resource_id'] or row['startup_until'] <= self.queue.now()
                or body['file_identity'] not in json.loads(row['payload'])['identities']):
            raise ValueError('Font request does not own this prepared file')
        video = prepared_video(self.queue, body['resource_id'], body['source_info_hash'])
        job = self.queue.db.execute('SELECT * FROM subtitle_preparation WHERE resource=?',
                                    (body['resource_id'],)).fetchone()
        if job is None or job['video_key'] != video['key']:
            return dict(state='unavailable', reason='SUBTITLE_NOT_PREPARED')
        detail = json.loads(job['detail'])
        current = self.queue.db.execute('SELECT r.payload,r.seq FROM subtitle_current c '
            'JOIN subtitle_revisions r ON r.seq=c.revision WHERE c.video_key=? AND c.binding_key=?',
            (video['key'], detail.get('binding_key'))).fetchone()
        record = json.loads(current['payload']) if current else None
        if (record is None or (record['state'] != 'READY_NOT_VISUAL_PROOF' and not style_reviewable(record))
                or record['manual_intent'] != 0 or record['video'] != video):
            return dict(state='unavailable', reason='SUBTITLE_FONT_INPUTS_NOT_READY')
        if record['extension'] not in {'.ass', '.ssa'}:
            return dict(state='not_applicable')
        if self.fonts is None:
            return dict(state='unavailable', reason='FONT_CACHE_DISABLED')
        if (not isinstance(record.get('font_result'), dict)
                or self.fonts.binding(video['release_key'], record['subtitle_sha256']) != record['font_result']):
            return dict(state='unavailable', reason='SUBTITLE_FONT_INPUTS_NOT_READY')
        return deepcopy(dict(state='planned', body=body, video=video, record=record,
            revision=current['seq'], attempts=job['attempts'], detail=detail,
            fonts=self.fonts.activation_plan(video['release_key'], record['subtitle_sha256'])))

    @measured('immutable_io')
    def perform(self, plan):
        """Only immutable cache IO on a worker, never SQLite or font activation."""
        self._verify_subtitle(plan)
        proof = self._verify_fonts(plan)
        native = self._export_subtitle(plan)
        return dict(proof=proof, native=native)

    @measured('subtitle_binding_io')
    def _verify_subtitle(self, plan):
        record, video = plan['record'], plan['video']
        raw = self.store._read(record)
        self.store._release_proof(video, record['timing'])
        actual = binding(video, raw, record['extension'], record['language'], record['full_dialogue'],
            record['forced'], record['origin'], record['timing'], record['font_result'], record['manual_intent'])
        old = {key: value for key, value in record.items() if key != 'font_result'}
        if record.get('schema') == 1:
            # Existing exact cached fonts must not become unavailable merely
            # because idle content-policy migration has not reached this row.
            derived = {'schema', 'content', 'chinese_ready', 'state'}
            matches = all(actual.get(key) == value for key, value in old.items() if key not in derived)
        else:
            matches = actual == old
        if not matches:
            raise ValueError('Subtitle record differs from its immutable inputs')
    @measured('font_bytes_io')
    def _verify_fonts(self, plan):
        return self.fonts.verify_plan(plan['fonts'])

    @measured('subtitle_export_io')
    def _export_subtitle(self, plan):
        # Export is immutable, not permission to attach the subtitle. The owner
        # must still revalidate the request, revision and font working set.
        return self.exporter(self.store, plan['record'])

    @measured('owner_commit')
    def complete(self, plan, result):
        current = self.plan(plan['body'])
        if current.get('state') == 'stale':
            return current
        if current != plan:
            return dict(state='unavailable', reason='FONT_PLAN_CHANGED')
        body, video, record = plan['body'], plan['video'], plan['record']
        if self.fonts.ledger is not self.queue.ledger:
            raise RuntimeError('Font and subtitle readiness must share their ledger')
        state = 'STYLE_REVIEW_REQUIRED' if style_reviewable(record) else 'READY_NOT_VISUAL_PROOF'
        def record_ready(hashes):
            detail = deepcopy(plan['detail'])
            detail.update(native_file=result['native'], subtitle_sha256=record['subtitle_sha256'],
                          font_activation=dict(request_id=body['request_id'], release_key=video['release_key'],
                                               font_hashes=hashes,
                                               inputs_complete=not record['font_result']['missing'],
                                               missing_count=len(record['font_result']['missing'])))
            self.subtitles._record_in_transaction(body['resource_id'], video['key'], state, plan['attempts'], detail)
        # Guard is refreshed inside the cache's existing rollback transaction,
        # before and after link changes. It must prove both idle and ownership.
        activation = self.fonts.activate(video['release_key'], record['subtitle_sha256'],
            body['request_id'], lambda: self.allowed(body), verified=result['proof'], record_ready=record_ready)
        if self.allowed(body) is not True:
            return dict(state='stale')
        return dict(state='ready', font_acceptance=state, request_id=body['request_id'], font_hashes=activation['hashes'],
                    subtitle_sha256=record['subtitle_sha256'], scope='PRE_AV_INPUTS_NOT_RENDER_PROOF',
                    font_inputs_complete=activation['inputs_complete'], missing_font_count=activation['missing_count'])

    def prepare(self, body):
        """Synchronous adapter for isolated tests; production uses plan/perform/complete."""
        plan = self.plan(body)
        return self.complete(plan, self.perform(plan)) if plan['state'] == 'planned' else plan

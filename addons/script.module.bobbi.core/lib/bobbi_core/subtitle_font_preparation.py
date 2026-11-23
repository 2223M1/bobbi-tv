"""Font preparation revisions on the existing subtitle/resource ledger.

It cannot activate Kodi fonts or qualify a subtitle without rendering inputs.
All SQLite work stays on the owner; the loader uses the existing single IO lane.
"""
from copy import deepcopy
import json

from bobbi_core.ledger import encode
from bobbi_core.ledger_extension import install_extension
from bobbi_core.subtitle_binding import prepared_video, style_reviewable
from bobbi_core.subtitle_export import export

KEY = 'extension:subtitle-font-preparation:schema'
ASSET_POLICY = 'nearest-release-directory-128m-rar-v2'
DDL = {'subtitle_font_preparation': '''CREATE TABLE subtitle_font_preparation(
    binding TEXT PRIMARY KEY, resource TEXT NOT NULL, state TEXT NOT NULL,
    attempts INTEGER NOT NULL, next_attempt REAL NOT NULL, detail TEXT NOT NULL)'''}


class SubtitleFontPreparation:
    def __init__(self, subtitles, cache, loader, allowed, exporter=export):
        self.subtitles, self.cache, self.loader, self.allowed = subtitles, cache, loader, allowed
        self.queue, self.store = subtitles.queue, subtitles.store
        self.exporter = exporter
        self.pending = None
        install_extension(self.queue.ledger, KEY, 1, DDL)
        self._recheck_asset_policy()

    def _recheck_asset_policy(self):
        key = KEY + ':asset-policy'
        with self.queue.ledger.transaction():
            prior = self.queue.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            if prior and prior[0] == ASSET_POLICY:
                return
            rows = self.queue.db.execute("SELECT binding,resource,attempts,detail FROM subtitle_font_preparation "
                "WHERE state='FONT_INPUTS_UNAVAILABLE' ORDER BY binding LIMIT 8193").fetchall()
            if len(rows) > 8192:
                raise ValueError('Font policy recheck budget')
            for binding_key, resource, attempts, detail in rows:
                if json.loads(detail).get('reason') != 'NO_RELEASE_FONT_ASSETS':
                    continue
                self.queue.ledger._audit('font_asset_policy_changed', resource,
                    dict(binding=binding_key, previous_policy=prior[0] if prior else None,
                         policy=ASSET_POLICY, previous_attempts=attempts,
                         previous_state='FONT_INPUTS_UNAVAILABLE'))
                self.queue.db.execute("UPDATE subtitle_font_preparation SET state='RETRY',attempts=0,next_attempt=? "
                    'WHERE binding=?', (self.queue.now(), binding_key))
            self.queue.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, ASSET_POLICY))

    def _record(self, plan, state, detail, delay=0):
        with self.queue.ledger.transaction():
            self.queue.db.execute('INSERT INTO subtitle_font_preparation VALUES(?,?,?,?,?,?) '
                'ON CONFLICT(binding) DO UPDATE SET state=excluded.state,attempts=excluded.attempts,'
                'next_attempt=excluded.next_attempt,detail=excluded.detail',
                (plan['binding']['key'], plan['resource'], state, plan['attempts'], self.queue.now()+delay, encode(detail)))
            self.queue.ledger._audit('subtitle_font_preparation', plan['resource'],
                dict(binding=plan['binding']['key'], state=state, attempts=plan['attempts'],
                     reason=detail.get('reason')))

    def next_action(self):
        if self.pending is not None or self.allowed() is not True:
            return None
        publication = self._publication_action()
        if publication is not None:
            self.pending = deepcopy(publication)
            return publication
        if self.queue.db.execute('SELECT COUNT(*) FROM subtitle_font_preparation').fetchone()[0] >= 8192:
            return None
        rows = self.queue.db.execute('''SELECT s.resource,c.binding_key,r.payload,r.seq AS revision,f.state,f.attempts,f.detail,b.task
            FROM subtitle_preparation s JOIN subtitle_current c ON c.video_key=s.video_key
            JOIN subtitle_revisions r ON r.seq=c.revision
            JOIN prepared_bindings b ON b.resource=s.resource
            LEFT JOIN subtitle_font_preparation f ON f.binding=c.binding_key
            WHERE s.state IN ('CANDIDATE_NOT_READY','READY_NOT_VISUAL_PROOF','STYLE_REVIEW_REQUIRED')
              AND (f.binding IS NULL OR
                (f.state IN ('RETRY','DEFERRED_IMPORT') AND f.next_attempt<=?))
            ORDER BY c.rowid LIMIT 32''', (self.queue.now(),)).fetchall()
        for row in rows:
            plan = dict(resource=row['resource'],binding={'key':row['binding_key']},attempts=(row['attempts'] or 0)+1)
            try:
                binding = json.loads(row['payload'])
                if binding['extension'] not in {'.ass','.ssa'} or not binding['chinese_ready']:
                    self._record(plan,'NOT_APPLICABLE',dict(reason='NO_QUALIFIED_ASS'))
                    continue
                task = self.queue.status(row['task'])
                current = prepared_video(self.queue,row['resource'],task['source_hash'])
                if current != binding['video'] or binding['key'] != row['binding_key']:
                    raise ValueError('Font binding identity changed')
                metadata = self.subtitles.cache.load(task['source_hash'])
                if metadata is None:
                    raise ValueError('Immutable font release metadata missing')
                plan.update(binding=binding, revision=row['revision'], video=current, metadata=metadata,
                    account=task['account'], destination=task['destination'],
                    observation=task['payload']['provider_observation'],
                    requirements=dict(subtitle_sha256=binding['subtitle_sha256'], fonts=binding['content']['fonts']))
                if row['state']=='DEFERRED_IMPORT':
                    plan['cached_result']=json.loads(row['detail'])['result']
                    plan['attempts']=row['attempts']
                else:
                    hashes=[r[0] for r in self.queue.db.execute(
                        'SELECT DISTINCT sha256 FROM font_sources WHERE version=? OR origin=?',
                        (current['release_key'],'local_exact')).fetchmany(129)]
                    if len(hashes)<=128:
                        known=self.cache.bind(current['release_key'],self.store._read(binding),hashes)
                        if not known['missing']:
                            plan['cached_result']=dict(state='EXISTING_FONT_INPUTS',fonts=[],cached_hashes=hashes)
            except (OSError,ValueError,KeyError,TypeError) as error:
                self._record(plan,'REJECTED_IDENTITY',dict(reason=type(error).__name__))
                continue
            self.pending=deepcopy(plan)
            return plan
        return None

    def perform(self, plan):
        if plan.get('kind') == 'immutable_export':
            try:
                if self.allowed() is not True:
                    return dict(state='PAUSED')
                self.store._release_proof(plan['video'], plan['binding']['timing'])
                return dict(state='IMMUTABLE_ONLY', file=self.exporter(self.store, plan['binding']))
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
                return dict(state='FAILED', reason=type(error).__name__)
        if 'cached_result' in plan:
            return deepcopy(plan['cached_result'])
        try:
            return self.loader.perform(plan)
        except InterruptedError:
            return dict(state='PAUSED',reason='PLAYBACK_OR_SHUTDOWN')
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as error:
            return dict(state='FAILED',reason=type(error).__name__)

    def complete(self, plan, result):
        if self.pending != plan:
            return False
        self.pending=None
        if plan.get('kind') == 'immutable_export':
            return self._complete_publication(plan, result)
        if result.get('state') not in {'EXISTING_FONT_INPUTS','FONT_INPUTS_NOT_NATIVE_OR_VISUAL_PROOF'}:
            state='RETRY' if plan['attempts']<3 or result.get('state')=='PAUSED' else 'FONT_INPUTS_UNAVAILABLE'
            self._record(plan,state,dict(reason=result.get('reason',result.get('state'))),delay=60)
            return True
        if self.allowed() is not True:
            self._record(plan,'DEFERRED_IMPORT',dict(result=result,reason='PLAYBACK_STARTED'),delay=5)
            return True
        # IO runs outside the ledger owner. A user/manual revision or retirement
        # can arrive while the font download is in flight. Never publish the old
        # snapshot over it, even though the video and subtitle hashes still fit.
        revision=self.queue.db.execute('SELECT revision FROM subtitle_current WHERE binding_key=?',
            (plan['binding']['key'],)).fetchone()
        if revision is None:
            self._record(plan,'REJECTED_IDENTITY',dict(reason='BINDING_RETIRED'))
            return True
        if revision['revision'] != plan['revision']:
            # The next owner pass snapshots the current revision. Immutable
            # downloaded font inputs can be rechecked there without new IO.
            self._record(plan,'DEFERRED_IMPORT',dict(result=result,reason='BINDING_REVISION_CHANGED'),delay=5)
            return True
        current=prepared_video(self.queue,plan['resource'],plan['video']['selected']['source_info_hash'])
        if current != plan['video']:
            self._record(plan,'REJECTED_IDENTITY',dict(reason='VIDEO_CHANGED'))
            return True
        old=plan['binding']
        self.store._release_proof(current,old['timing'])
        raw=self.store._read(old)
        hashes=list(result.get('cached_hashes',[]))
        for item in result['fonts']:
            if self.allowed() is not True:
                self._record(plan,'DEFERRED_IMPORT',dict(result=result,reason='PLAYBACK_STARTED'),delay=5)
                return True
            record=self.cache.import_file(item['path'],'same_release_pack',current['release_key'],item['sha256'])
            hashes.append(record['sha256'])
        fonts=self.cache.bind(current['release_key'],raw,hashes)
        bound=self.store.put(current,raw,old['extension'],old['language'],old['full_dialogue'],old['forced'],
            old['origin'],timing=old['timing'],font_result=fonts,manual_intent=old['manual_intent'])
        # Do not change video/subtitle admission or activate Kodi fonts.
        # Content-only v2 subtitles may already be READY with missing fonts;
        # the font inputs remain an independent rendering-quality result.
        # A subsequent idle IO pass may publish immutable subtitle bytes;
        # playback preflight still owns activation and readiness independently.
        self._record(plan,'FONT_INPUTS_BOUND' if bound['fonts_ready'] else 'FONT_INPUTS_INCOMPLETE',
            dict(reason=fonts['status'],font_hashes=bound['font_hashes'],subtitle_sha256=bound['subtitle_sha256'],
                 binding_key=bound['key'],evidence=result.get('evidence',[]),native_activated=False))
        return True

    def _publication_record(self, plan, result, retry=False):
        detail = deepcopy(plan['font_detail'])
        detail['publication'] = result
        detail['publication_attempts'] = plan['publication_attempts']
        if result.get('state') == 'IMMUTABLE_ONLY':
            detail['immutable_file'] = result['file']
        # -1 is a terminal publication marker, not permission to play. No new
        # schema or second writer is needed. Font qualification stays intact.
        due = self.queue.now() + 60 if retry else -1
        with self.queue.ledger.transaction():
            self.queue.db.execute('UPDATE subtitle_font_preparation SET detail=?,next_attempt=? WHERE binding=?',
                (encode(detail), due, plan['binding']['key']))
            self.queue.ledger._audit('subtitle_immutable_publication', plan['resource'],
                dict(state=result['state'], reason=result.get('reason')))

    def _publication_action(self):
        rows = self.queue.db.execute('''SELECT f.resource,f.state,f.detail,c.binding_key,r.seq,r.payload
            FROM subtitle_font_preparation f JOIN subtitle_current c ON c.binding_key=f.binding
            JOIN subtitle_revisions r ON r.seq=c.revision
            JOIN subtitle_preparation s ON s.resource=f.resource AND s.video_key=c.video_key
            WHERE f.state IN ('FONT_INPUTS_BOUND','FONT_INPUTS_INCOMPLETE')
              AND f.next_attempt>=0 AND f.next_attempt<=? AND s.state='CANDIDATE_NOT_READY'
            ORDER BY f.next_attempt,f.binding LIMIT 32''', (self.queue.now(),)).fetchall()
        for row in rows:
            record, detail = json.loads(row['payload']), json.loads(row['detail'])
            plan = dict(kind='immutable_export', resource=row['resource'], binding=record,
                revision=row['seq'], video=record['video'], font_detail=detail,
                publication_attempts=detail.get('publication_attempts', 0) + 1)
            if (record['key'] != row['binding_key'] or record['manual_intent'] != 0
                    or (record['state'] != 'READY_NOT_VISUAL_PROOF' and not style_reviewable(record))):
                self._publication_record(plan, dict(state='NOT_QUALIFIED'))
                continue
            try:
                current = prepared_video(self.queue, row['resource'], record['video']['selected']['source_info_hash'])
                if current != record['video']:
                    raise ValueError('Subtitle publication video changed')
            except (OSError, ValueError, KeyError, TypeError):
                self._publication_record(plan, dict(state='REJECTED_IDENTITY'))
                continue
            return plan
        return None

    def _complete_publication(self, plan, result):
        # The worker only wrote content-addressed immutable bytes. Never grant
        # automatic subtitle/font authority, even if the user changed intent.
        if self.allowed() is not True:
            self._publication_record(plan, dict(state='DEFERRED', reason='PLAYBACK_STARTED'), retry=True)
            return True
        revision = self.queue.db.execute('SELECT revision FROM subtitle_current WHERE binding_key=?',
            (plan['binding']['key'],)).fetchone()
        if revision is None or revision['revision'] != plan['revision']:
            self._publication_record(plan, dict(state='REJECTED_IDENTITY', reason='REVISION_CHANGED'))
            return True
        try:
            current = prepared_video(self.queue, plan['resource'], plan['video']['selected']['source_info_hash'])
            if current != plan['video']:
                raise ValueError('Publication identity changed')
        except (OSError, ValueError, KeyError, TypeError):
            self._publication_record(plan, dict(state='REJECTED_IDENTITY', reason='VIDEO_CHANGED'))
            return True
        self._publication_record(plan, result,
            retry=result.get('state') != 'IMMUTABLE_ONLY' and plan['publication_attempts'] < 3)
        return True

"""Immutable subtitle bytes plus append-only evidence in the resource ledger.

Called by the preparation owner, never by GUI callbacks. A downloaded file is
a candidate until its identity and text checks pass. Fonts are optional. Legacy
IMDb folders are not recursively scanned or silently adopted by this store.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from bobbi_core.font_cache import safe_directory
from bobbi_core.ledger import encode
from bobbi_core.ledger_extension import install_extension
from bobbi_core.subtitle_binding import binding, checked_video, digest, MAX_SUBTITLE_BYTES

SCHEMA_KEY = 'extension:subtitle-bindings:schema'
DEFINITIONS = {
    'subtitle_objects': 'CREATE TABLE subtitle_objects(sha256 TEXT PRIMARY KEY, bytes INTEGER NOT NULL, extension TEXT NOT NULL)',
    'subtitle_revisions': '''CREATE TABLE subtitle_revisions(
        seq INTEGER PRIMARY KEY AUTOINCREMENT, binding_key TEXT NOT NULL,
        video_key TEXT NOT NULL, subtitle_sha256 TEXT REFERENCES subtitle_objects(sha256),
        payload TEXT NOT NULL, at REAL NOT NULL)''',
    'subtitle_current': '''CREATE TABLE subtitle_current(
        binding_key TEXT PRIMARY KEY, video_key TEXT NOT NULL,
        revision INTEGER NOT NULL REFERENCES subtitle_revisions(seq))''',
}


class SubtitleStore:
    def __init__(self, ledger, root, font_cache=None, metadata_cache=None, release_matcher=None):
        self.ledger = ledger
        self.font_cache = font_cache
        self.metadata_cache = metadata_cache
        self.release_matcher = release_matcher
        self.root = safe_directory(root)
        self.objects = safe_directory(self.root / 'objects')
        self.migration_backup = install_extension(ledger, SCHEMA_KEY, 1, DEFINITIONS)

    def _path(self, record):
        if record['extension'] not in {'.srt', '.ass', '.ssa', '.sup', '.sub', '.vtt'}:
            raise ValueError('Unexpected subtitle representation')
        return self.objects / (digest(record['subtitle_sha256']) + record['extension'])

    def _read(self, record):
        path = self._path(record)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != record['bytes'] or not 1 <= info.st_size <= MAX_SUBTITLE_BYTES:
            raise ValueError('Subtitle object type/size drift; do not use or delete')
        with path.open('rb') as stream:
            raw = stream.read(MAX_SUBTITLE_BYTES + 1)
        if hashlib.sha256(raw).hexdigest() != record['subtitle_sha256']:
            raise ValueError('Subtitle bytes changed; old readiness is invalid')
        return raw

    def _release_proof(self, video, timing):
        if not isinstance(timing, dict) or timing.get('kind') != 'same_release':
            return
        from bobbi_core.subtitle_pack import select
        if self.metadata_cache is None or self.release_matcher is None:
            raise ValueError('Same-release membership requires the immutable metadata cache')
        metadata = self.metadata_cache.load(video['selected']['source_info_hash'])
        if metadata is None or select(video, metadata, self.release_matcher) != timing['selection']:
            raise ValueError('Release membership or unique sidecar selection changed')

    def put(self, video, raw, extension, language, full_dialogue, forced, origin,
            timing=None, font_result=None, manual_intent=0):
        self._release_proof(video, timing)
        result = binding(video, raw, extension, language, full_dialogue, forced, origin,
                         timing, font_result, manual_intent)
        known = self.ledger.db.execute('SELECT 1 FROM subtitle_current WHERE binding_key=?', (result['key'],)).fetchone()
        if not known and self.ledger.db.execute('SELECT COUNT(*) FROM subtitle_current WHERE video_key=?',
                                               (video['key'],)).fetchone()[0] >= 32:
            raise ValueError('Subtitle candidate count budget')
        stored_format = self.ledger.db.execute('SELECT extension FROM subtitle_objects WHERE sha256=?',
                                               (result['subtitle_sha256'],)).fetchone()
        if stored_format and stored_format[0] != extension:
            raise ValueError('Existing subtitle bytes cannot change their verified format')
        # An immutable hash object is not a second authoritative ready state.
        path = self._path(result)
        if path.exists() or path.is_symlink():
            self._read(result)
        else:
            count, total = self.ledger.db.execute('SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM subtitle_objects').fetchone()
            if count >= 8192 or total + len(raw) > 256 * 1024 * 1024:
                raise ValueError('Subtitle cache capacity; retain previous candidates')
            fd, name = tempfile.mkstemp(prefix='.pending-', dir=self.objects)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(name, path)
            except FileExistsError:
                self._read(result)
            Path(name).unlink()
        db = self.ledger.db
        with self.ledger.transaction():
            old = db.execute('''SELECT r.payload FROM subtitle_current c JOIN subtitle_revisions r
                ON r.seq=c.revision WHERE c.binding_key=?''', (result['key'],)).fetchone()
            # Exact repeated results need no new audit record or DB growth.
            raw_record = encode(dict(result, font_result=font_result))
            if old and old[0] == raw_record:
                return result
            db.execute('INSERT OR IGNORE INTO subtitle_objects VALUES(?,?,?)', (result['subtitle_sha256'], len(raw), extension))
            cursor = db.execute('INSERT INTO subtitle_revisions(binding_key,video_key,subtitle_sha256,payload,at) VALUES(?,?,?,?,?)',
                (result['key'], video['key'], result['subtitle_sha256'], raw_record, self.ledger.now()))
            db.execute('INSERT INTO subtitle_current VALUES(?,?,?) ON CONFLICT(binding_key) DO UPDATE SET revision=excluded.revision',
                       (result['key'], video['key'], cursor.lastrowid))
            self.ledger._audit('subtitle_binding_recorded', None, dict(key=result['key'], video_key=video['key'],
                               revision=cursor.lastrowid, state=result['state']))
            # Publish changed card metadata atomically with its binding revision.
            # Do not requalify video or submit/recreate a cloud task.
            db.execute("INSERT INTO settings VALUES('subtitle_generation','1') ON CONFLICT(key) "
                       "DO UPDATE SET value=CAST(value AS INTEGER)+1")
        return result

    def records(self, video, current_manual_intent=None, ready_only=False):
        checked_video(video)
        rows = self.ledger.db.execute('''SELECT r.payload FROM subtitle_current c
            JOIN subtitle_revisions r ON r.seq=c.revision WHERE c.video_key=? ORDER BY c.binding_key''',
            (video['key'],)).fetchmany(33)
        if len(rows) > 32:
            raise ValueError('Subtitle candidate count budget')
        result, read_bytes = [], 0
        for row in rows:
            record = json.loads(row['payload'])
            read_bytes += record['bytes']
            if read_bytes > 16 * 1024 * 1024:
                raise ValueError('Subtitle verification byte budget')
            raw = self._read(record)
            self._release_proof(video, record['timing'])
            current = binding(video, raw, record['extension'], record['language'], record['full_dialogue'],
                              record['forced'], record['origin'], record['timing'], record['font_result'], record['manual_intent'])
            # v1 records retain source/file identity and original bytes, but
            # their derived timing/font gate is deliberately not inherited.
            old = {k: v for k, v in record.items() if k != 'font_result'}
            if record.get('schema') == 1:
                derived = {'schema', 'content', 'chinese_ready', 'state'}
                matches = all(current.get(k) == v for k, v in old.items() if k not in derived)
            else:
                matches = current == old
            if not matches:
                raise ValueError('Subtitle record differs from its inputs')
            if ready_only and (current['state'] != 'READY_NOT_VISUAL_PROOF'
                    or current_manual_intent is None or current['manual_intent'] != current_manual_intent):
                continue
            result.append(dict(current, local_object=str(self._path(record))))
        return result

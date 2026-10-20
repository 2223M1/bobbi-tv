"""One-time, stopped-owner CE state migration. Never included in installers.

The caller verifies the live CD2 UID against the local 115 session and keeps
both old owners stopped. Old files remain untouched; only a new account epoch
directory is published. No cloud writes occur in this module.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from uuid import uuid4

TABLES = set('audit dependencies font_bindings font_leases font_native_links '
    'font_objects font_sources leases media_profile_refresh next_discovery_jobs '
    'preparation_intents preparation_targets prepared_bindings '
    'prepared_playback_protection resources sessions settings sqlite_sequence '
    'subtitle_current subtitle_font_preparation subtitle_objects '
    'subtitle_preparation subtitle_revisions tasks'.split())
REQUIRED = {'resources', 'tasks', 'prepared_bindings', 'preparation_targets',
            'preparation_intents', 'settings', 'sessions', 'leases', 'audit'}
MAX_DB = 128 * 1024 * 1024


def plain(path, file=False):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('MIGRATION_SYMLINK')
    if file and not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('MIGRATION_REGULAR_FILE')
    return path


def digest(path):
    value = hashlib.sha256()
    with plain(path, file=True).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def sqlite_backup(source, target, stopped):
    source, target = plain(source, file=True), plain(target)
    if target.exists() or source.stat().st_size > MAX_DB:
        raise ValueError('MIGRATION_DB_DESTINATION_OR_SIZE')
    deadline = time.monotonic() + 30
    def progress(status, remaining, total):
        stopped()
        if time.monotonic() >= deadline or total * 65536 > MAX_DB * 16:
            raise TimeoutError('MIGRATION_BACKUP_BUDGET')
    old = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=1)
    new = sqlite3.connect(str(target))
    try:
        if old.execute('PRAGMA page_count').fetchone()[0] * old.execute('PRAGMA page_size').fetchone()[0] > MAX_DB:
            raise ValueError('MIGRATION_DB_SIZE')
        old.backup(new, pages=64, progress=progress, sleep=.01)
        if (new.execute('PRAGMA integrity_check').fetchone()[0] != 'ok'
                or new.execute('PRAGMA foreign_key_check').fetchone()):
            raise ValueError('MIGRATION_DB_INTEGRITY')
    finally:
        new.close()
        old.close()


def _objects(db, source, stage, stopped):
    count, total = 0, 0
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    def copy(kind, key, size, extension, allowed):
        nonlocal count, total
        stopped()
        if (not re.fullmatch('[0-9a-f]{64}', key) or extension not in allowed
                or type(size) is not int or not 0 < size <= 64 * 1024 * 1024):
            raise ValueError('MIGRATION_OBJECT_RECORD')
        count, total = count + 1, total + size
        if count > 8192 or total > 768 * 1024 * 1024:
            raise ValueError('MIGRATION_OBJECT_BUDGET')
        src = plain(source / kind / 'objects' / (key + extension), file=True)
        dst = stage / kind / 'objects' / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        before = src.stat()
        if before.st_size != size:
            raise ValueError('MIGRATION_OBJECT_SIZE')
        value, copied = hashlib.sha256(), 0
        with src.open('rb') as reader, dst.open('xb') as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b''):
                stopped()
                copied += len(chunk)
                if copied > size:
                    raise ValueError('MIGRATION_OBJECT_CHANGED')
                value.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        after = src.stat()
        stamp = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if copied != size or value.hexdigest() != key or stamp(after) != stamp(before):
            raise ValueError('MIGRATION_OBJECT_CHANGED')
        os.chmod(dst, 0o444)
    if 'font_objects' in tables:
        for key, payload in db.execute('SELECT sha256,payload FROM font_objects'):
            record = json.loads(payload)
            if record['sha256'] != key:
                raise ValueError('MIGRATION_FONT_IDENTITY')
            copy('fonts', key, record['bytes'], record['extension'], {'.ttf', '.ttc', '.otf'})
    if 'subtitle_objects' in tables:
        for key, size, extension in db.execute('SELECT sha256,bytes,extension FROM subtitle_objects'):
            copy('subtitles', key, size, extension, {'.srt', '.ssa', '.ass', '.vtt', '.sub', '.sup'})
    return dict(count=count, bytes=total)


def _ledger(db, account, destination, now):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if (tables - TABLES or REQUIRED - tables or db.execute('PRAGMA user_version').fetchone()[0] != 2
            or db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()):
        raise ValueError('MIGRATION_UNKNOWN_SCHEMA')
    for payload, in db.execute('SELECT payload FROM resources'):
        if json.loads(payload).get('account') != account:
            raise ValueError('MIGRATION_RESOURCE_ACCOUNT')
    if db.execute("SELECT 1 FROM tasks WHERE provider IS NOT '115' OR account IS NOT ? OR destination IS NOT ?", (account, destination)).fetchone():
        raise ValueError('MIGRATION_TASK_ACCOUNT')
    before = {t: db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
              for t in ('resources', 'prepared_bindings', 'tasks', 'sessions')}
    states = dict(db.execute('SELECT state,COUNT(*) FROM tasks GROUP BY state'))
    allowed = {'ready', 'failed', 'suppressed', 'queued', 'space_blocked',
               'submitting', 'submitted', 'uncertain', 'downloading', 'mapping', 'checking'}
    if set(states) - allowed:
        raise ValueError('MIGRATION_UNKNOWN_TASK_STATE')
    # Retain already-submitted work only for read-only poll/qualification.
    # Unsent old intents/discovery must not cause a new cloud mutation.
    db.execute("UPDATE tasks SET state='suppressed',updated=? WHERE state IN ('queued','space_blocked')", (now,))
    db.execute("UPDATE tasks SET state='uncertain',updated=? WHERE state='submitting'", (now,))
    db.execute("UPDATE tasks SET state='mapping',updated=? WHERE state='checking'", (now,))
    db.execute("UPDATE preparation_intents SET state='failed',result=?,updated=? WHERE state IN ('queued','validating')",
               ('{"error":"MIGRATION_UNSENT_INTENT_NOT_REPLAYED"}', now))
    if 'next_discovery_jobs' in tables:
        db.execute("UPDATE next_discovery_jobs SET state='cancelled',nonce='',updated=?,result=? WHERE state IN ('waiting','running')",
                   (now, '{"reason":"MIGRATION_UNSENT_DISCOVERY_NOT_REPLAYED"}'))
    for table in ('leases', 'font_leases', 'prepared_playback_protection'):
        if table in tables:
            db.execute('DELETE FROM ' + table)  # Only transient leases in NEW copy.
    db.execute('UPDATE sessions SET ended=?,natural=0 WHERE ended IS NULL', (now,))
    db.execute('INSERT INTO audit(at,action,resource,detail) VALUES(?,?,NULL,?)',
               (now, 'private_host_migration', json.dumps({'prior_task_states': states})))
    return dict(counts=before, prior_task_states=states,
                active_policy='already-submitted read-only reconciliation; no unsent replay')


def migrate_preparation(source, target, identity, scope, legacy_account, destination, stopped):
    from bobbi_platform.account_manager import validate_snapshot
    from bobbi_core.preparation import scope_path
    scope = validate_snapshot(scope, authenticated=True)
    scope_path(destination)
    if (identity.get('account_id') != scope['account_id']
            or identity.get('legacy_scope') != legacy_account
            or not re.fullmatch('[0-9a-f]{64}', legacy_account)):
        raise ValueError('MIGRATION_LIVE_UID_MISMATCH')
    stopped()
    source, target = plain(source), plain(target)
    if (target.exists() or source == target or source in target.parents or target in source.parents
            or target.name != scope['account_id'][4:] + '-' + str(scope['epoch'])):
        raise ValueError('MIGRATION_NEW_EPOCH_REQUIRED')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / ('.migration-' + uuid4().hex)
    stage.mkdir(mode=0o700)
    sqlite_backup(source / 'resources.sqlite', stage / 'resources.sqlite', stopped)
    receipt = dict(schema=1, account=scope, source_db_sha256=digest(stage / 'resources.sqlite'))
    db = sqlite3.connect(str(stage / 'resources.sqlite'))
    try:
        receipt['ledger'] = _ledger(db, legacy_account, destination, time.time())
        receipt['objects'] = _objects(db, source, stage, stopped)
        db.commit()
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('MIGRATION_FINAL_FOREIGN_KEYS')
    finally:
        db.close()
    direct = source / 'direct.sqlite3'
    if direct.exists():
        sqlite_backup(direct, stage / direct.name, stopped)
        db = sqlite3.connect(str(stage / direct.name))
        try:
            if ({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} != {'direct_jobs'}
                    or db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()
                    or db.execute('SELECT 1 FROM direct_jobs WHERE account IS NOT ? OR destination IS NOT ?', (legacy_account, destination)).fetchone()):
                raise ValueError('MIGRATION_DIRECT_SCOPE')
            receipt['direct_states'] = dict(db.execute('SELECT state,COUNT(*) FROM direct_jobs GROUP BY state'))
            from bobbi_core.direct_cloud import ACTIVE
            if set(receipt['direct_states']) - set(ACTIVE) - {'ready', 'failed', 'rejected', 'retryable'}:
                raise ValueError('MIGRATION_DIRECT_STATE')
            db.execute("UPDATE direct_jobs SET state='failed',error='MIGRATION_UNSENT_NOT_REPLAYED' WHERE state IN ('queued','inspect','submit_ready')")
            db.execute("UPDATE direct_jobs SET state='uncertain' WHERE state='submitting'")
            db.commit()
        finally:
            db.close()
    from bobbi_core.metadata_cache import MetadataCache
    cache = source / 'torrent-file-metadata'
    receipt['metadata_entries'] = 0
    if cache.is_dir():
        old, new = MetadataCache(cache), MetadataCache(stage / cache.name)
        paths = sorted(cache.glob('*.json'))
        if len(paths) > 64:
            raise ValueError('MIGRATION_METADATA_BUDGET')
        for path in paths:
            stopped()
            new.store(old.load(path.stem))
            receipt['metadata_entries'] += 1
    # Same-release subtitles need their pack metadata, not just the ASS bytes.
    # Refuse a nominally successful migration that would discard this proof.
    from bobbi_core.subtitle_pack import select
    from bobbi_core.torrent_subtitles import matching_chinese_sidecars
    db = sqlite3.connect(str(stage / 'resources.sqlite'))
    try:
        has_current = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='subtitle_current'").fetchone()
        if has_current:
            for payload, in db.execute('SELECT r.payload FROM subtitle_current c JOIN subtitle_revisions r ON r.seq=c.revision'):
                record = json.loads(payload)
                timing = record.get('timing') or {}
                if timing.get('kind') == 'same_release':
                    video = record['video']
                    metadata = MetadataCache(stage / cache.name).load(video['selected']['source_info_hash'])
                    if metadata is None or select(video, metadata, matching_chinese_sidecars) != timing['selection']:
                        raise ValueError('MIGRATION_SUBTITLE_PACK_PROOF')
    finally:
        db.close()
    receipt['target_db_sha256'] = digest(stage / 'resources.sqlite')
    with (stage / 'migration-receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    stopped()
    os.rename(stage, target)  # No existing target; old state is never renamed.
    return receipt

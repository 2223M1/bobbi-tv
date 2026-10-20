"""Content-addressed subtitle fonts in the shared ledger, activated before AV.

Only this cache's recorded objects/links can be removed. User-installed fonts,
embedded subtitle data and the UI typeface are never rewritten or replaced.
No network operations, archive extraction or full system-font scan occurs here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
from collections import deque
from contextlib import contextmanager
from threading import Lock
from time import monotonic
from uuid import uuid4

from bobbi_core.fonts import (
    FONT_CACHE_SOFT_BYTES, ass_font_requirements, cache_eviction_candidates,
    inspect_font, inspect_font_file, select_fonts,
)
from bobbi_core.ledger import encode

FONT_SCHEMA_KEY = 'extension:subtitle-fonts:schema'
# Windows st_ctime is creation time, not a reliable content-change marker.
# The CoreELEC target is POSIX; other platforms retain full-byte verification.
BYTE_PROOF_REUSE = os.name == 'posix'
FONT_DDL = (
    'CREATE TABLE font_objects(sha256 TEXT PRIMARY KEY, payload TEXT NOT NULL, last_used REAL)',
    'CREATE TABLE font_sources(sha256 TEXT REFERENCES font_objects(sha256), version TEXT, '
    'origin TEXT, PRIMARY KEY(sha256,version,origin))',
    'CREATE TABLE font_bindings(version TEXT, subtitle TEXT, payload TEXT, PRIMARY KEY(version,subtitle))',
    'CREATE TABLE font_leases(owner TEXT PRIMARY KEY, version TEXT, subtitle TEXT, purpose TEXT, expires REAL)',
    'CREATE TABLE font_native_links(sha256 TEXT PRIMARY KEY REFERENCES font_objects(sha256))',
)


def install_schema(ledger):
    """One verified backup before this optional, additive ledger extension."""
    db = ledger.db
    version = db.execute('SELECT value FROM settings WHERE key=?', (FONT_SCHEMA_KEY,)).fetchone()
    definitions = {statement.split('(', 1)[0].split()[-1]: statement for statement in FONT_DDL}
    present = {name: db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
               for name in definitions}
    if version:
        if version[0] != '1' or any(not present[name] or ' '.join(present[name][0].split()) != ' '.join(sql.split())
                                    for name, sql in definitions.items()):
            raise ValueError('Unknown/incomplete font schema; preserve existing ledger')
        return None
    if any(present.values()):
        raise ValueError('Unversioned font tables require explicit migration, no guessing')
    size = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
    if size > 128 * 1024 * 1024 or shutil.disk_usage(ledger.path.parent).free < size * 2 + 128 * 1024 * 1024:
        raise ValueError('Font migration backup capacity gate')
    backup = ledger.path.with_name(ledger.path.name + '.pre-subtitle-fonts-v1-' + uuid4().hex)
    saved = sqlite3.connect(str(backup))
    try:
        db.backup(saved)
        if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Font migration backup integrity failed')
    finally:
        saved.close()
    digest = file_hash(backup)
    with ledger.transaction():
        for statement in FONT_DDL: db.execute(statement)
        db.execute('INSERT INTO settings VALUES(?,?)', (FONT_SCHEMA_KEY, '1'))
        ledger._audit('font_schema_installed', None, {'version': 1, 'backup_name': backup.name, 'sha256': digest})
    return backup


def checked_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_:.\-]{1,256}", value):
        raise ValueError("Stable local identity required, not a URL or path")
    return value


def safe_directory(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise ValueError("Font directories cannot traverse symbolic links")
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_hash(path, allowed=None):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            if allowed is not None and allowed() is not True:
                raise InterruptedError('Idle font verification paused')
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def file_stamp(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Font proof requires a regular file')
    return tuple(getattr(info, key) for key in
                 ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def verify_font_plan(plan, reusable=None, allowed=None):
    """Verify current paths against complete byte proofs from this process.

    Unchanged proofs may come from an earlier idle verification. They grant no
    activation authority: every path is restatted here and again by the owner.
    A new/replaced/changed object is always hashed completely.
    """
    proof, hashed = {}, {}
    reusable = (reusable or {}) if BYTE_PROOF_REUSE else {}
    for path, record in plan.items():
        if allowed is not None and allowed() is not True:
            raise InterruptedError('Idle font verification paused')
        before = file_stamp(path)
        if before[3] != record['bytes']:
            raise ValueError('Font bytes differ from the frozen activation plan')
        # Object and native paths normally are hard links. Hash each physical
        # inode once within THIS verification, not twice through its two names.
        digest = hashed.get(before) if before[1] else None
        if digest is None:
            if before[1] and reusable.get(path) == (record['sha256'], before):
                digest = record['sha256']
            else:
                digest = file_hash(Path(path)) if allowed is None else file_hash(Path(path), allowed=allowed)
        if digest != record['sha256']:
            raise ValueError('Font bytes differ from the frozen activation plan')
        if before[1]:
            hashed[before] = digest
        proof[path] = (record['sha256'], before)
    # Include aliases and paths proved before another object was read.
    for path, (_, before) in proof.items():
        if file_stamp(path) != before:
            raise ValueError('Font changed during worker verification')
    return proof


class FontCache:
    def __init__(self, ledger, root, native_directory):
        self.ledger = ledger
        self.root = safe_directory(root)
        self.objects = safe_directory(self.root / "objects")
        self.native = safe_directory(native_directory)
        if self.native == self.root or self.native in self.root.parents or self.root in self.native.parents:
            raise ValueError("Native font links and private cache must be disjoint")
        self.migration_backup = install_schema(ledger)
        # Volatile byte evidence only, never serialized into the ledger. The
        # lock coordinates the existing idle and preflight IO lanes, not SQLite.
        self._proofs, self._proof_lock = {}, Lock()
        self._byte_queue, self._byte_queued = deque(), set()
        self._seed_byte_warmup()

    def _queue_bytes(self, digest, priority=False):
        if digest in self._byte_queued:
            if priority:
                self._byte_queue.remove(digest)
                self._byte_queue.appendleft(digest)
            return
        if len(self._byte_queued) >= 256:
            if not priority:
                return
            self._byte_queued.remove(self._byte_queue.pop())
        self._byte_queued.add(digest)
        (self._byte_queue.appendleft if priority else self._byte_queue.append)(digest)

    def _seed_byte_warmup(self):
        """One bounded ledger-only pass per service start; never a font scan."""
        for row in self.ledger.db.execute('SELECT sha256 FROM font_native_links LIMIT 128'):
            self._queue_bytes(row[0])
        for version, subtitle in self.ledger.db.execute(
                "SELECT version,subtitle FROM font_leases WHERE expires>? "
                "ORDER BY CASE purpose WHEN 'current' THEN 0 ELSE 1 END LIMIT 32", (self.ledger.now(),)):
            result = self.binding(version, subtitle)
            for item in (result or {}).get('selected', []):
                self._queue_bytes(item['sha256'])
        for row in self.ledger.db.execute('SELECT payload FROM font_bindings ORDER BY rowid DESC LIMIT 64'):
            for item in json.loads(row[0]).get('selected', []):
                self._queue_bytes(item['sha256'])

    def verify_plan(self, plan, allowed=None):
        """IO-lane entry point; no ledger reads or activation writes here."""
        with self._proof_lock:
            reusable = {path: self._proofs[path] for path in plan if path in self._proofs}
        try:
            proof = verify_font_plan(plan, reusable, allowed)
        except (OSError, ValueError):
            with self._proof_lock:
                for path in plan:
                    self._proofs.pop(path, None)
            raise
        with self._proof_lock:
            for path, value in proof.items():
                self._proofs.pop(path, None)
                self._proofs[path] = value
            while len(self._proofs) > 512:
                self._proofs.pop(next(iter(self._proofs)))
        return proof

    def _invalidate_bytes(self, record, requeue=True):
        # link/unlink changes ctime even when bytes are unchanged. Do NOT turn
        # its post-operation stamp into fresh byte evidence without rehashing.
        with self._proof_lock:
            for native in (False, True):
                self._proofs.pop(str(self._path(record, native)), None)
        if requeue:
            self._queue_bytes(record['sha256'], priority=True)

    def next_byte_action(self):
        """Owner pops one event-enqueued object; an empty queue does no IO."""
        while self._byte_queue:
            digest = self._byte_queue.popleft()
            self._byte_queued.remove(digest)
            try:
                record = self._record(digest)
            except KeyError:  # Evicted after it was queued.
                continue
            plan = {str(self._path(record)): record}
            if self.ledger.db.execute('SELECT 1 FROM font_native_links WHERE sha256=?', (digest,)).fetchone():
                plan[str(self._path(record, True))] = record
            return plan
        return None

    def warm_bytes(self, plan, allowed):
        """One local object on the existing idle lane, never a renderer action."""
        next_check, idle = 0.0, False
        def still_idle():
            nonlocal next_check, idle
            now = monotonic()
            if now >= next_check:
                idle = allowed() is True
                next_check = now + 0.1
            return idle
        if not still_idle():
            return {'state': 'PAUSED'}
        try:
            proof = self.verify_plan(plan, allowed=still_idle)
        except InterruptedError:
            return {'state': 'PAUSED'}
        return {'state': 'BYTE_PROOF_ONLY', 'paths': len(proof)}

    def finish_byte_action(self, plan, result):
        if result.get('state') == 'PAUSED':
            for record in plan.values():
                self._queue_bytes(record['sha256'], priority=True)

    def _record(self, digest):
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Exact font hash required")
        row = self.ledger.db.execute("SELECT payload FROM font_objects WHERE sha256=?", (digest,)).fetchone()
        if row is None:
            raise KeyError(digest)
        return json.loads(row[0])

    def _path(self, record, native=False):
        digest = record["sha256"]
        if not re.fullmatch("[0-9a-f]{64}", digest) or record["extension"] not in {".ttf", ".ttc", ".otf"}:
            raise ValueError("Invalid font object name")
        return (self.native if native else self.objects) / (("bobi-" if native else "") + digest + record["extension"])

    def _verify(self, record, native=False):
        path = self._path(record, native)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != record["bytes"]:
            raise ValueError("Font object size/type drift; preserve it")
        if file_hash(path) != record["sha256"]:
            raise ValueError("Font object hash drift; preserve it")
        return path

    def import_font(self, data, origin, source_version):
        """Caller has already verified attachment/release provenance."""
        return self._import(inspect_font(data), origin, source_version, lambda stream: stream.write(data))

    def import_file(self, path, origin, source_version, expected_sha256):
        """Admit actual extracted bytes, not trusted JSON from a decoder child.

        The isolated child can use its own bounded heap. The ledger owner
        independently inspects/copies in chunks and never retains a whole font.
        """
        path = Path(path)
        record = inspect_font_file(path)
        if record['sha256'] != expected_sha256:
            raise ValueError('Extracted font differs from verified input')
        def copy(stream):
            if path.is_symlink():
                raise ValueError('Font file changed to link')
            with path.open('rb') as source:
                count = 0
                for block in iter(lambda: source.read(1024*1024), b''):
                    count += len(block)
                    if count > record['bytes']:
                        raise ValueError('Font copy byte budget')
                    stream.write(block)
                if count != record['bytes']:
                    raise ValueError('Font truncated during publication')
        return self._import(record, origin, source_version, copy)

    def _import(self, record, origin, source_version, write):
        checked_key(source_version)
        if origin not in {"media_attachment", "same_release_pack", "local_exact"}:
            raise ValueError("Unverified font origin")
        target = self._path(record)
        total = sum(json.loads(row[0])["bytes"] for row in self.ledger.db.execute("SELECT payload FROM font_objects"))
        known = self.ledger.db.execute("SELECT 1 FROM font_objects WHERE sha256=?", (record["sha256"],)).fetchone()
        if not known and total + record['bytes'] > FONT_CACHE_SOFT_BYTES:
            raise RuntimeError("Font cache requires an idle bounded prune before importing more fonts")
        if target.exists() or target.is_symlink():
            self._verify(record)
        else:
            descriptor, temporary = tempfile.mkstemp(prefix=".font-", suffix=".pending", dir=self.objects)
            temporary = Path(temporary)
            with os.fdopen(descriptor, "wb") as stream:
                write(stream)
                stream.flush()
                os.fsync(stream.fileno())
            if temporary.stat().st_size != record['bytes'] or file_hash(temporary) != record['sha256']:
                raise ValueError('Font changed before immutable publication')
            # Immutable publication, never replace an unknown file. A failed
            # temporary stays available for diagnostics; it is not loadable.
            try:
                os.link(temporary, target)
            except FileExistsError:
                self._verify(record)
            temporary.unlink()
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT INTO font_objects VALUES(?,?,?) ON CONFLICT(sha256) DO UPDATE SET last_used=excluded.last_used",
                                   (record["sha256"], encode(record), self.ledger.now()))
            added = self.ledger.db.execute("INSERT OR IGNORE INTO font_sources VALUES(?,?,?)", (record["sha256"], source_version, origin)).rowcount
            self.ledger._audit("font_import", record["sha256"], {"origin": origin, "version": source_version, "bytes": record['bytes']})
            if added:
                self._wake_preparation(record, origin, source_version)
        self._queue_bytes(record['sha256'])
        return record

    def _wake_preparation(self, record, origin, source_version):
        """New exact input invalidates only a matching exhausted font result.

        Runs in the import owner's transaction, not a timer or GUI scan. It
        grants no subtitle/native readiness and preserves every prior failure.
        """
        db = self.ledger.db
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='subtitle_font_preparation'").fetchone():
            return
        rows = db.execute('''SELECT f.binding,f.resource,f.state,f.attempts,r.payload
            FROM subtitle_font_preparation f JOIN subtitle_current c ON c.binding_key=f.binding
            JOIN subtitle_revisions r ON r.seq=c.revision
            WHERE f.state IN ('FONT_INPUTS_UNAVAILABLE','FONT_INPUTS_INCOMPLETE')
            ORDER BY f.binding LIMIT 8193''').fetchall()
        if len(rows) > 8192:
            raise ValueError('Font arrival wake budget')
        for key, resource, state, attempts, payload in rows:
            binding = json.loads(payload)
            if (binding['key'] != key or binding['manual_intent'] != 0
                    or not binding['chinese_ready']
                    or (origin != 'local_exact' and binding['video']['release_key'] != source_version)):
                continue
            selection = select_fonts(dict(subtitle_sha256=binding['subtitle_sha256'],
                fonts=binding['content']['fonts']), [dict(record, origin=origin)])
            if not selection['selected']:
                continue
            self.ledger._audit('font_input_arrived', resource, dict(binding=key,
                sha256=record['sha256'], origin=origin, previous_state=state,
                previous_attempts=attempts, native_activated=False))
            db.execute("UPDATE subtitle_font_preparation SET state='RETRY',attempts=0,next_attempt=? WHERE binding=?",
                       (self.ledger.now(), key))

    def bind(self, version, subtitle_data, candidates):
        checked_key(version)
        if len(candidates) > 128:
            raise ValueError("Font candidate budget")
        records = []
        for digest in set(candidates):
            record = self._record(digest)
            self._verify(record)
            sources = self.ledger.db.execute("SELECT origin,version FROM font_sources WHERE sha256=?", (digest,)).fetchall()
            for origin, source in sources:
                if origin == "local_exact" or source == version:
                    records.append(dict(record, origin=origin))
        result = select_fonts(ass_font_requirements(subtitle_data), records)
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT OR REPLACE INTO font_bindings VALUES(?,?,?)",
                                   (version, result["subtitle_sha256"], encode(result)))
            self.ledger._audit("font_bind", version, {"subtitle": result["subtitle_sha256"], "missing": result["missing"]})
        return result

    def binding(self, version, subtitle):
        checked_key(version)
        if not re.fullmatch("[0-9a-f]{64}", subtitle):
            raise ValueError("Exact subtitle hash required")
        row = self.ledger.db.execute("SELECT payload FROM font_bindings WHERE version=? AND subtitle=?", (version, subtitle)).fetchone()
        if not row:
            return None
        result = json.loads(row[0])
        # Eviction leaves the exact release/subtitle identity in the ledger,
        # but readiness must not survive eviction of an input font object.
        selected = []
        for item in result["selected"]:
            if self.ledger.db.execute("SELECT 1 FROM font_objects WHERE sha256=?", (item["sha256"],)).fetchone():
                selected.append(item)
            else:
                result["missing"].append(item["request"])
                result["status"] = "FONT_CACHE_MISS"
        result["selected"] = selected
        return result

    def reserve(self, version, subtitle, owner, purpose="next", seconds=600):
        checked_key(owner)
        result = self.binding(version, subtitle)
        if result is None or not result['selected']:
            raise ValueError("No matched subtitle font inputs are ready")
        if purpose not in {"current", "next"} or type(seconds) is not int or not 1 <= seconds <= 21600:
            raise ValueError("Bounded current/next font reservation required")
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT OR REPLACE INTO font_leases VALUES(?,?,?,?,?)",
                                   (owner, version, subtitle, purpose, self.ledger.now() + seconds))
        for item in result['selected']:
            self._queue_bytes(item['sha256'], priority=True)
        return result

    def owns_activation(self, version, subtitle, owner, hashes):
        """Ownership of matched inputs, not complete style coverage; no IO."""
        result = self.binding(version, subtitle)
        if result is None or not result['selected'] or not isinstance(hashes, list):
            return False
        expected = sorted({item['sha256'] for item in result['selected']})
        if hashes != expected:
            return False
        lease = self.ledger.db.execute(
            "SELECT 1 FROM font_leases WHERE owner=? AND version=? AND subtitle=? "
            "AND purpose='current' AND expires>?",
            (owner, version, subtitle, self.ledger.now())).fetchone()
        links = sorted(row[0] for row in self.ledger.db.execute('SELECT sha256 FROM font_native_links'))
        return lease is not None and links == expected

    @contextmanager
    def _link_rollback(self, added, old_records):
        try:
            yield
        except BaseException:
            for native in added:
                if native.exists():
                    native.unlink()
            for record in old_records.values():
                native = self._path(record, native=True)
                if not native.exists():
                    os.link(self._path(record), native)
            raise

    def activation_plan(self, version, subtitle):
        result = self.binding(version, subtitle)
        if result is None or not result['selected']:
            raise ValueError('No matched fonts are ready')
        selected = {item['sha256'] for item in result['selected']}
        previous = {row[0] for row in self.ledger.db.execute('SELECT sha256 FROM font_native_links')}
        plan = {}
        for digest in selected | previous:
            record = self._record(digest)
            # Old object bytes are also needed if rollback must restore links.
            plan[str(self._path(record))] = record
            native = self._path(record, native=True)
            if digest in previous or native.exists() or native.is_symlink():
                plan[str(native)] = record
        return plan

    def activate(self, version, subtitle, owner, can_activate, verified=None, record_ready=None):
        """Call before opening AV, with a live idle + request-ownership guard.

        The existing ASS renderer holds its own fonts. We do not hot-reload it
        or touch user fonts. Only the next renderer sees this exact working set.
        """
        result = self.binding(version, subtitle)
        # A missing family must not discard other exact matched faces. Libass
        # retains normal fallback for missing families; never claim full style
        # coverage or synthesize a replacement font file here.
        if result is None or not result['selected']:
            raise ValueError("No matched font inputs to activate")
        checked_key(owner)
        def verify(record, native=False):
            if verified is None:
                return self._verify(record, native)
            path = self._path(record, native)
            if verified.get(str(path)) != (record['sha256'], file_stamp(path)):
                raise ValueError('Font worker proof expired before activation')
            return path
        records = {row["sha256"]: self._record(row["sha256"]) for row in result["selected"]}
        for record in records.values():
            verify(record)
        if can_activate() is not True:
            raise RuntimeError("Font activation requires idle player and current request")
        added, old_records = [], {}
        with self._link_rollback(added, old_records), self.ledger.transaction():
            previous = {row[0] for row in self.ledger.db.execute("SELECT sha256 FROM font_native_links")}
            # Verify all removable links before changing any of them. Never
            # unlink a user-replaced or unknown file, even with our prefix.
            old_records.update({digest: self._record(digest) for digest in previous - set(records)})
            for record in old_records.values():
                verify(record, native=True)
                if verified is not None:
                    verify(record)
            try:
                for digest, record in records.items():
                    native = self._path(record, native=True)
                    if native.exists() or native.is_symlink():
                        if digest not in previous:
                            raise ValueError("Unrecorded native font collision; preserve it")
                        verify(record, native=True)
                    else:
                        self._invalidate_bytes(record)
                        os.link(self._path(record), native)
                        added.append(native)
                    self.ledger.db.execute("INSERT OR IGNORE INTO font_native_links VALUES(?)", (digest,))
                if can_activate() is not True:
                    raise RuntimeError("Playback/request changed during font activation")
                for digest, record in old_records.items():
                    self._invalidate_bytes(record)
                    self._path(record, native=True).unlink()
                    self.ledger.db.execute("DELETE FROM font_native_links WHERE sha256=?", (digest,))
                self.ledger.db.execute("DELETE FROM font_leases WHERE purpose='current'")
                self.ledger.db.execute("INSERT OR REPLACE INTO font_leases VALUES(?,?,?,?,?)",
                                       (owner, version, subtitle, "current", self.ledger.now() + 600))
                for digest in records:
                    self.ledger.db.execute("UPDATE font_objects SET last_used=? WHERE sha256=?", (self.ledger.now(), digest))
                self.ledger._audit("font_activate", version, {"owner": owner, "subtitle": subtitle, "hashes": sorted(records)})
                # The optional owner-thread readiness write is part of this
                # same durable transaction and filesystem rollback scope.
                if record_ready is not None:
                    record_ready(sorted(records))
                    if can_activate() is not True:
                        raise RuntimeError("Playback/request changed during readiness write")
            except BaseException:
                for native in added:
                    if native.exists():
                        native.unlink()
                # Restore only the prior recorded links from immutable objects.
                for record in old_records.values():
                    native = self._path(record, native=True)
                    if not native.exists():
                        os.link(self._path(record), native)
                raise
        return {"status": "FONTS_ACTIVATED_NOT_RENDER_PROOF", "font_count": len(records),
                "bytes": sum(record["bytes"] for record in records.values()), "hashes": sorted(records),
                "inputs_complete": not result['missing'], "missing_count": len(result['missing'])}

    def release(self, owner):
        checked_key(owner)
        with self.ledger.transaction():
            self.ledger.db.execute("DELETE FROM font_leases WHERE owner=?", (owner,))

    def prune(self, idle, limit=FONT_CACHE_SOFT_BYTES):
        if idle() is not True:
            return {"status": "PAUSED_DURING_PLAYBACK", "removed": []}
        with self.ledger.transaction():
            pinned = {row[0] for row in self.ledger.db.execute("SELECT sha256 FROM font_native_links")}
            leases = self.ledger.db.execute("SELECT version,subtitle FROM font_leases WHERE expires>?", (self.ledger.now(),)).fetchall()
            for version, subtitle in leases:
                result = self.binding(version, subtitle)
                pinned.update(row["sha256"] for row in result["selected"])
            records = [dict(json.loads(row[0]), last_used=row[1], managed=True)
                       for row in self.ledger.db.execute("SELECT payload,last_used FROM font_objects")]
            decision = cache_eviction_candidates(records, pinned, limit=limit)
            removed = []
            for digest in decision["hashes"]:
                if idle() is not True:
                    break
                record = self._record(digest)
                self._verify(record).unlink()
                self._invalidate_bytes(record, requeue=False)
                self.ledger.db.execute("DELETE FROM font_sources WHERE sha256=?", (digest,))
                self.ledger.db.execute("DELETE FROM font_objects WHERE sha256=?", (digest,))
                self.ledger._audit("font_cache_evict", digest, {"bytes": record["bytes"]})
                removed.append(digest)
            return {"status": "BOUNDED_CACHE_PRUNED", "removed": removed,
                    "soft_limit_exceeded_by_protected_items": decision["soft_limit_exceeded_by_protected_items"]}

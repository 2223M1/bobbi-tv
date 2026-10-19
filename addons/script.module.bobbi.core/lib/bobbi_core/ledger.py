"""Small durable resource ledger shared by preparation, playback and retention.

No network/file deletion here. Cloud credentials and temporary download URLs
are deliberately not part of the schema. All mutating decisions use short
SQLite transactions; no network calls may be made while a transaction is held.
"""
import hashlib
import json
import math
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import sqlite3
import time
from uuid import uuid4

from bobbi_core.retention import PlaybackCoverage, cleanup_candidate

SCHEMA = 2
STATES = {"observed", "queued", "pending", "checking", "ready", "unavailable", "deleting", "recycled", "uncertain"}
KINDS = {"video", "subtitle", "font", "attachment"}


def encode(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode("utf-8")) > 128 * 1024:
        raise ValueError("Ledger record budget exceeded")
    return raw


def checked_cloud_file(file):
    allowed = {"provider", "account", "file_id", "cloud_path", "bytes", "kind", "media_id", "version_key", "sha1", "sha256"}
    if set(file) - allowed:
        raise ValueError("Unknown/secret fields cannot enter the file ledger")
    if file.get("provider") != "115" or not all(isinstance(file.get(key), str) and 0 < len(file[key]) <= 256
                                               for key in ("account", "file_id", "media_id", "version_key")):
        raise ValueError("Stable cloud/account/file/media/version identities required")
    path = file.get("cloud_path", "")
    if (not isinstance(path, str) or not path.startswith("/115open/") or "\\" in path or "\x00" in path
            or any(part in {".", ".."} for part in path.split("/")) or str(PurePosixPath(path)) != path):
        raise ValueError("Exact normalized 115 file path required")
    if type(file.get("bytes")) is not int or file["bytes"] <= 0 or file.get("kind") not in KINDS:
        raise ValueError("Exact positive size and file kind required")
    for key, length in (("sha1", 40), ("sha256", 64)):
        digest = file.get(key)
        if digest is not None and (len(digest) != length or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("Invalid content digest")
    return dict(file)


def resource_id(file):
    return hashlib.sha256(encode([file["provider"], file["account"], file["file_id"]]).encode()).hexdigest()


class Ledger:
    def __init__(self, path, now=time.time):
        self.path, self.now = Path(path), now
        # A live observation is authority only on this owner connection. It is
        # not durable permission for a reopened ledger or another process.
        self._playback_observation = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=2, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=2000")
        self.db.execute("PRAGMA cache_size=-512")
        self.db.execute("PRAGMA mmap_size=0")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, SCHEMA):
            self.db.close()
            raise ValueError("Unknown ledger version; preserve without migrating")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.migration_backup = None
        if version == 1:
            # SQLite backup includes committed WAL pages, unlike copying the
            # database file while another connection may still have a WAL.
            self.migration_backup = self.path.with_name(self.path.name + '.pre-v2-' + uuid4().hex)
            destination = sqlite3.connect(str(self.migration_backup))
            try:
                self.db.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Pre-migration database integrity failed')
            finally:
                destination.close()
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS dependencies(owner TEXT REFERENCES resources(id), asset TEXT REFERENCES resources(id),
                role TEXT NOT NULL, PRIMARY KEY(owner,asset));
            CREATE TABLE IF NOT EXISTS leases(resource TEXT REFERENCES resources(id), owner TEXT, purpose TEXT, expires REAL,
                PRIMARY KEY(resource,owner));
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, resource TEXT REFERENCES resources(id), purpose TEXT,
                duration REAL, intervals TEXT, started REAL, ended REAL, natural INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, source_hash TEXT UNIQUE, payload TEXT, state TEXT,
                reserved_bytes INTEGER NOT NULL, updated REAL);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, action TEXT,
                resource TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS preparation_intents(id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                state TEXT NOT NULL, updated REAL NOT NULL, result TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS dependency_asset ON dependencies(asset);
            CREATE INDEX IF NOT EXISTS active_tasks ON tasks(state);
        """)
        if version < SCHEMA:
            with self.transaction():
                self.db.execute('ALTER TABLE tasks RENAME TO tasks_v1')
                self.db.execute('''CREATE TABLE tasks(
                    id TEXT PRIMARY KEY, source_hash TEXT NOT NULL, payload TEXT NOT NULL,
                    state TEXT NOT NULL, reserved_bytes INTEGER NOT NULL, updated REAL NOT NULL,
                    provider TEXT NOT NULL, account TEXT NOT NULL, destination TEXT NOT NULL,
                    dedup_key TEXT NOT NULL UNIQUE, priority INTEGER NOT NULL DEFAULT 3,
                    next_poll REAL NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0)''')
                self.db.execute('''INSERT INTO tasks(id,source_hash,payload,state,reserved_bytes,updated,
                    provider,account,destination,dedup_key)
                    SELECT id,source_hash,payload,state,reserved_bytes,updated,
                    'legacy','','','legacy:' || source_hash FROM tasks_v1''')
                self.db.execute('DROP TABLE tasks_v1')
                self.db.execute('CREATE INDEX active_tasks ON tasks(state)')
                self.db.execute('''CREATE TABLE preparation_targets(
                    task TEXT REFERENCES tasks(id), media_id TEXT, version_key TEXT,
                    payload TEXT NOT NULL, PRIMARY KEY(task,media_id,version_key))''')
                self.db.execute('''CREATE TABLE prepared_bindings(
                    task TEXT REFERENCES tasks(id), resource TEXT REFERENCES resources(id),
                    media_id TEXT NOT NULL, version_key TEXT NOT NULL, evidence TEXT NOT NULL,
                    PRIMARY KEY(task,resource))''')
                self.db.execute('PRAGMA user_version=2')

    def close(self):
        self._playback_observation = None
        self.db.close()

    def playback_observation(self):
        return dict(self._playback_observation) if self._playback_observation is not None else None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _audit(self, action, rid, detail=None):
        self.db.execute("INSERT INTO audit(at,action,resource,detail) VALUES(?,?,?,?)",
                        (self.now(), action, rid, encode(detail or {})))

    def _get(self, rid):
        row = self.db.execute("SELECT payload,revision FROM resources WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise KeyError(rid)
        result = json.loads(row["payload"])
        result["revision"] = row["revision"]
        return result

    def _save(self, record):
        result = dict(record)
        revision = result.pop("revision", 0) + 1
        self.db.execute("INSERT INTO resources(id,payload,revision) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision",
                        (result["resource_id"], encode(result), revision))

    def register(self, file, managed=False, identity_verified=False):
        record = checked_cloud_file(file)
        rid = resource_id(record)
        with self.transaction():
            try:
                old = self._get(rid)
            except KeyError:
                old = None
            if old is not None:
                # A rename/size/version drift requires explicit requalification;
                # it must never silently retarget a pending delete or playback.
                if any(old.get(key) != record.get(key) for key in record):
                    raise ValueError("Existing file identity changed; do not overwrite")
                return rid
            record.update(resource_id=rid, managed=bool(managed), identity_verified=bool(identity_verified),
                          state="observed", observation_at=self.now() if managed else None,
                          recommended=False, user_started=False, incomplete=False,
                          completed_at=None, last_access_at=None, left_recommendation_at=None,
                          favorite=False, keep=False, suppressed=False)
            self._save(record)
            self._audit("register", rid, {"managed": bool(managed), "identity_verified": bool(identity_verified)})
        return rid

    def get(self, rid):
        record = self._get(rid)
        record["active_lease"] = bool(self.db.execute("SELECT 1 FROM leases WHERE resource=? AND expires>? LIMIT 1", (rid, self.now())).fetchone())
        owners = self.db.execute("SELECT owner FROM dependencies WHERE asset=?", (rid,)).fetchall()
        record["retained_dependency"] = any(self._get(row[0])["state"] != "recycled" for row in owners)
        return record

    def records(self):
        # Paged iteration, not a whole-cloud scan or unbounded materialization.
        after = ""
        while True:
            rows = self.db.execute("SELECT id FROM resources WHERE id>? ORDER BY id LIMIT 64", (after,)).fetchall()
            if not rows:
                break
            for row in rows:
                yield self.get(row[0])
            after = rows[-1][0]

    def mark_ready(self, rid, evidence):
        with self.transaction():
            self._mark_ready_in_transaction(rid, evidence)

    def _mark_ready_in_transaction(self, rid, evidence):
        if not self.db.in_transaction:
            raise RuntimeError('Qualification requires an owner transaction')
        required = {"file_id", "bytes", "version_key", "source_binding", "read_bytes", "probe_sha256", "duration", "video_codec"}
        if set(evidence) not in (required, required | {'media_profile'}):
            raise ValueError("Complete bounded media qualification required")
        if 'media_profile' in evidence:
            from bobbi_core.release_media_profile import checked_profile
            profile = checked_profile(evidence['media_profile'])
            if profile['video']['codec'] != evidence['video_codec']:
                raise ValueError('Media profile differs from qualified video codec')
        record = self._get(rid)
        if record["kind"] != "video" or record["state"] in {"deleting", "recycled", "uncertain"} or record["suppressed"]:
            raise ValueError("Resource cannot become ready")
        if any(evidence[key] != record[key] for key in ("file_id", "bytes", "version_key")):
            raise ValueError("Probe belongs to a different file/version")
        if (evidence["source_binding"] is not True or not record["identity_verified"]
                or type(evidence["read_bytes"]) is not int or not 0 < evidence["read_bytes"] <= min(record["bytes"], 16 * 1024 * 1024)
                or not isinstance(evidence["duration"], (int, float)) or not math.isfinite(evidence["duration"])
                or evidence["duration"] < 300 or not evidence["video_codec"]
                or len(evidence["probe_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in evidence["probe_sha256"])):
            raise ValueError("Unverified/trailer/invalid media evidence")
        record.update(state="ready", qualification=dict(evidence, at=self.now()))
        self._save(record)
        self._audit("ready", rid, evidence)

    def user_action(self, rid, action):
        if action not in {"details", "play", "prepare", "favorite", "unfavorite", "keep", "unkeep", "mark_completed"}:
            raise ValueError("Unknown explicit user action")
        with self.transaction():
            record = self._get(rid)
            if record["state"] == "deleting":
                raise ValueError("Deletion is in flight; wait for reconciliation")
            record["last_access_at"] = self.now()
            if action in {"favorite", "unfavorite"}:
                record["favorite"] = action == "favorite"
            if action in {"keep", "unkeep"}:
                record["keep"] = action == "keep"
            if action in {"play", "prepare", "favorite"}:
                record["suppressed"] = False
            if action == "mark_completed":
                record.update(user_started=True, incomplete=False, completed_at=self.now())
            self._save(record)
            self._audit("user_" + action, rid)

    def recommend(self, rids, cycle):
        if not isinstance(cycle, str) or not 1 <= len(cycle) <= 40 or len(rids) > 40 or len(set(rids)) != len(rids):
            raise ValueError("A dated, bounded recommendation set is required")
        with self.transaction():
            wanted = set(rids)
            for rid in wanted:
                candidate = self._get(rid)
                if candidate["state"] != "ready" or candidate["suppressed"]:
                    raise ValueError("Recommendations may only publish ready unsuppressed files")
            for item in self.records():
                rid = item["resource_id"]
                record = self._get(rid)
                if rid in wanted:
                    record.update(recommended=True, recommendation_cycle=cycle,
                                  left_recommendation_at=None, observation_at=record["observation_at"] or self.now())
                elif record["recommended"]:
                    record.update(recommended=False, left_recommendation_at=self.now())
                else:
                    continue
                self._save(record)
            self._audit("recommendation_snapshot", None, {"cycle": cycle, "resources": rids})

    def add_dependency(self, owner, asset, role):
        if owner == asset or role not in {"font", "subtitle", "attachment"}:
            raise ValueError("Invalid dependency")
        with self.transaction():
            self._get(owner)
            target = self._get(asset)
            if target["kind"] != role or target["state"] in {"deleting", "recycled", "uncertain"}:
                raise ValueError("Unavailable or incompatible dependency")
            self.db.execute("INSERT OR IGNORE INTO dependencies(owner,asset,role) VALUES(?,?,?)", (owner, asset, role))
            self._audit("dependency", owner, {"asset": asset, "role": role})

    def acquire(self, rid, owner, purpose, ttl=60):
        if purpose not in {"playback", "next", "font", "probe"} or not owner or not 1 <= ttl <= 3600:
            raise ValueError("Invalid bounded lease")
        with self.transaction():
            if self._get(rid)["state"] in {"deleting", "recycled", "uncertain"}:
                raise ValueError("Resource unavailable for a lease")
            self.db.execute("INSERT INTO leases(resource,owner,purpose,expires) VALUES(?,?,?,?) ON CONFLICT(resource,owner) DO UPDATE SET purpose=excluded.purpose,expires=excluded.expires",
                            (rid, owner, purpose, self.now() + ttl))

    def release(self, rid, owner):
        self.db.execute("DELETE FROM leases WHERE resource=? AND owner=?", (rid, owner))

    def start_watch(self, rid, session, duration, purpose):
        evidence = PlaybackCoverage(duration, purpose)
        with self.transaction():
            record = self._get(rid)
            if record["state"] != "ready":
                raise ValueError("Only a verified ready file can begin watched evidence")
            self.db.execute("INSERT INTO sessions(id,resource,purpose,duration,intervals,started) VALUES(?,?,?,?,?,?)",
                            (session, rid, purpose, duration, "[]", self.now()))
            if purpose == "user":
                record.update(user_started=True, incomplete=True, last_access_at=self.now())
                self._save(record)
            self._audit("play_start", rid, {"session": session, "purpose": purpose})
        return evidence

    def save_watch(self, session, evidence, natural_end=None):
        with self.transaction():
            row = self.db.execute("SELECT * FROM sessions WHERE id=?", (session,)).fetchone()
            if row is None or row["ended"] is not None or evidence.purpose != row["purpose"] or evidence.duration != row["duration"]:
                raise ValueError("Stale/mismatched playback evidence")
            ended = self.now() if type(natural_end) is bool else None
            self.db.execute("UPDATE sessions SET intervals=?,ended=?,natural=? WHERE id=?",
                            (encode(evidence.intervals), ended, natural_end is True, session))
            if evidence.completed(natural_end):
                record = self._get(row["resource"])
                record.update(completed_at=self.now(), incomplete=False)
                self._save(record)
                self._audit("user_completed_coverage_eof", row["resource"], {"session": session, "coverage": evidence.fraction})

    def reserve_task(self, source_hash, spec, bytes_required, total, free):
        from bobbi_core.retention import required_free_bytes
        if len(source_hash) != 40 or any(c not in "0123456789abcdef" for c in source_hash):
            raise ValueError("A real torrent identity is required")
        if set(spec) - {"media_id", "version_key", "destination", "title", "season", "episode"}:
            raise ValueError("Unknown/private task fields")
        with self.transaction():
            old = self.db.execute("SELECT id,state FROM tasks WHERE dedup_key=?", ('legacy:' + source_hash,)).fetchone()
            if old:
                return {"id": old["id"], "state": old["state"], "existing": True}
            active = self.db.execute("SELECT COUNT(*),COALESCE(SUM(reserved_bytes),0) FROM tasks WHERE state IN ('reserved','submitted','uncertain','checking')").fetchone()
            if active[0] >= 2:
                raise ValueError("Two cloud preparation tasks already in flight")
            required = required_free_bytes(total, active[1], bytes_required)
            if type(free) is not int or not 0 <= free <= total or free < required:
                raise ValueError("Insufficient verified capacity; evaluate cleanup first")
            task = uuid4().hex
            self.db.execute("INSERT INTO tasks(id,source_hash,payload,state,reserved_bytes,updated,provider,account,destination,dedup_key) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (task, source_hash, encode(spec), "reserved", bytes_required, self.now(), 'legacy', '', '', 'legacy:' + source_hash))
            self._audit("task_reserved", None, {"task": task, "source_hash": source_hash, "reserved_bytes": bytes_required})
            return {"id": task, "state": "reserved", "existing": False}

    def task_state(self, task, state, resources=None):
        allowed = {"reserved": {"submitted", "uncertain", "failed"}, "submitted": {"checking", "uncertain", "failed"},
                   "uncertain": {"submitted", "checking", "failed"}, "checking": {"ready", "uncertain", "failed"}}
        with self.transaction():
            row = self.db.execute("SELECT state,payload FROM tasks WHERE id=?", (task,)).fetchone()
            if not row or state not in allowed.get(row[0], set()):
                raise ValueError("Invalid task state transition")
            if state == "ready":
                spec = json.loads(row[1])
                if not resources or len(resources) > 128:
                    raise ValueError("Accepted task is not verified playable media")
                items = [self._get(rid) for rid in resources]
                if (any(item["state"] != "ready" for item in items)
                        or not any(item["media_id"] == spec.get("media_id") and item["version_key"] == spec.get("version_key") for item in items)):
                    raise ValueError("No qualified target file belongs to this task")
            self.db.execute("UPDATE tasks SET state=?,updated=? WHERE id=?", (state, self.now(), task))
            self._audit("task_" + state, None, {"task": task})

    def set_recycle_gate(self, proof):
        # A typed outcome is required; provider/membership expiry is reported
        # separately. Never infer recoverability from a successful Delete RPC.
        required = {"account", "canary_file_id", "before_sha256", "restored_sha256", "visible_in_recycle", "restored",
                    "capacity_before", "capacity_after_delete", "capacity_after_restore", "at"}
        if (set(proof) != required or proof["visible_in_recycle"] is not True or proof["restored"] is not True
                or len(proof["before_sha256"]) != 64 or proof["before_sha256"] != proof["restored_sha256"]
                or proof["capacity_after_delete"] <= proof["capacity_before"]
                or proof["capacity_after_restore"] >= proof["capacity_after_delete"]):
            raise ValueError("Recycle/restore/hash/capacity canary not proven")
        with self.transaction():
            self.db.execute("INSERT INTO settings VALUES('recycle_gate',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (encode(proof),))
            self._audit("recycle_gate_proven", None, proof)

    def begin_recycle(self, rid, fresh, emergency=False):
        fresh = checked_cloud_file(fresh)
        with self.transaction():
            record = self.get(rid)
            protection = self.db.execute("SELECT value FROM settings WHERE key='playback_protection'").fetchone()
            if protection:
                observation = self.playback_observation() or {}
                if (observation.get('known') is not True
                        or not 0 <= self.now() - observation.get('at', 0) <= 10):
                    raise ValueError('Current native playback protection unavailable; recycling paused')
            gate = self.db.execute("SELECT value FROM settings WHERE key='recycle_gate'").fetchone()
            gate = json.loads(gate[0]) if gate else {}
            if (gate.get("account") != record["account"] or not gate.get("at")
                    or not 0 <= self.now() - gate["at"] <= 30 * 86400):
                raise ValueError("Fresh account-specific recycle canary required")
            if any(record.get(key) != value for key, value in fresh.items()) or resource_id(fresh) != rid:
                raise ValueError("Fresh ID/path/size/version drift; do not delete")
            decision = cleanup_candidate(record, self.now(), emergency)
            if not decision["eligible"]:
                raise ValueError("Resource became protected: " + decision["reason"])
            token = uuid4().hex
            original = self._get(rid)
            original.update(state="deleting", deletion_token=token, suppression_reason=decision["reason"])
            self._save(original)
            self._audit("recycle_intent", rid, {"token": token, "decision": decision})
            return token

    def finish_recycle(self, rid, token, *, visible_in_recycle=False, absent_from_original=False):
        with self.transaction():
            record = self._get(rid)
            if record["state"] != "deleting" or record.get("deletion_token") != token:
                raise ValueError("Stale deletion result")
            proven = visible_in_recycle is True and absent_from_original is True
            record.update(state="recycled" if proven else "uncertain", suppressed=True,
                          recycled_at=self.now() if proven else None)
            self._save(record)
            self._audit("recycled" if proven else "recycle_uncertain_do_not_repeat", rid, {"token": token})

    def audit_since(self, sequence=0, limit=1000):
        if not 1 <= limit <= 1000:
            raise ValueError("Bounded audit page required")
        return [{**dict(row), "detail": json.loads(row["detail"])} for row in self.db.execute(
            "SELECT * FROM audit WHERE seq>? ORDER BY seq LIMIT ?", (sequence, limit))]

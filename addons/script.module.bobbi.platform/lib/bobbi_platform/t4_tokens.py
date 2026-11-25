"""Persistent bounded SQLite store for opaque T4 selection tokens and approved media origins.

Implements R13-01, R13-02, R13-05, R14-02, REV-11, and U07 (SRC-02):
- Keeps URL-shaped/arbitrary vod_id, category type_id, filter maps, and line/episode play
  references out of Kodi plugin URLs, Host IPC, and logs.
- Play records are self-contained on disk (storing vod_id, line/episode hashes & raw summary
  bound to source_id, generation, and site_hash) so parent item eviction never invalidates
  an existing play token, while external URLs remain 100% opaque 32-hex HMAC tokens.
- True read-LRU ordering with strictly monotonic timestamps and single-transaction page batches
  that pin the active page's parent/sibling tokens against self-eviction.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from bobbi_core.library_contract import LibraryError
from bobbi_core.source_endpoint import endpoint

MAX_TOKENS = 4096
MAX_BATCH_TOKENS = 512
MAX_APPROVED_ORIGINS_PER_SOURCE = 64
SCHEMA_VERSION = 2


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class T4TokenStore:
    def __init__(self, path: Path | str, *, read_only: bool = False, timeout: float = 1.0):
        self.path = Path(path)
        self.read_only = read_only
        self._last_clock = 0
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise LibraryError('STORAGE_UNSAFE')
        self.db: sqlite3.Connection | None = None
        try:
            if read_only:
                if not self.path.is_file():
                    return
                self.db = sqlite3.connect(self.path.absolute().as_uri() + '?mode=ro', uri=True, timeout=timeout)
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if not self.path.exists():
                    fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(fd)
                self.db = sqlite3.connect(str(self.path), timeout=timeout)
                self.db.execute('PRAGMA journal_mode=WAL')
                self.db.execute('PRAGMA synchronous=NORMAL')
                self.db.execute('PRAGMA secure_delete=ON')
                self._ensure_schema()
        except LibraryError:
            self.close()
            raise
        except (OSError, sqlite3.Error):
            self.close()
            if not read_only:
                raise LibraryError('STORAGE_UNAVAILABLE') from None

    def _next_stamp(self) -> int:
        assert self.db is not None
        if self._last_clock == 0:
            row = self.db.execute('SELECT COALESCE(MAX(updated_at), 0) FROM t4_tokens').fetchone()
            if row and isinstance(row[0], int):
                self._last_clock = row[0]
        candidate = time.time_ns()
        self._last_clock = candidate if candidate > self._last_clock else self._last_clock + 1
        return self._last_clock

    def _ensure_schema(self) -> None:
        assert self.db is not None
        with self.db:
            self.db.execute(
                'CREATE TABLE IF NOT EXISTS t4_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)'
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS t4_tokens (
                    token TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    generation TEXT NOT NULL,
                    site_hash TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            self.db.execute(
                'CREATE INDEX IF NOT EXISTS idx_t4_tokens_lru ON t4_tokens (updated_at ASC)'
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS t4_approved_origins (
                    source_id TEXT NOT NULL,
                    generation TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (source_id, generation, origin)
                )
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS t4_pending_origin_prompts (
                    request_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    generation TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            self.db.execute(
                'INSERT OR IGNORE INTO t4_meta(key, value) VALUES (?, ?)',
                ('hmac_salt', secrets.token_hex(32)),
            )
            ver = self.db.execute('PRAGMA user_version').fetchone()[0]
            if ver < SCHEMA_VERSION:
                self._migrate_play_rows_v1_to_v2()
                self.db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

    def _migrate_play_rows_v1_to_v2(self) -> None:
        """Upgrade existing v1 play rows in-place when their parent item_token is still present."""
        assert self.db is not None
        rows = self.db.execute(
            "SELECT token, source_id, generation, site_hash, payload_json FROM t4_tokens WHERE kind='play'"
        ).fetchall()
        for tok, sid, gen, shash, pjson in rows:
            try:
                val = json.loads(pjson)
            except ValueError:
                continue
            if not isinstance(val, dict) or 'vod_id' in val:
                continue
            itok = val.get('item_token', '')
            prow = self.db.execute(
                "SELECT payload_json FROM t4_tokens WHERE token=? AND source_id=? AND generation=? AND site_hash=? AND kind='item'",
                (itok, sid, gen, shash),
            ).fetchone()
            if not prow:
                continue
            try:
                vid = json.loads(prow[0])
            except ValueError:
                continue
            if isinstance(vid, str) and vid:
                upgraded = {
                    'schema': SCHEMA_VERSION,
                    'item_token': itok,
                    'vod_id': vid,
                    'line': val.get('line', ''),
                    'line_name': '',
                    'episode': val.get('episode', ''),
                    'episode_id': '',
                    'title': str(val.get('title') or '')[:512],
                }
                self.db.execute(
                    'UPDATE t4_tokens SET payload_json=? WHERE token=?',
                    (json.dumps(upgraded, ensure_ascii=False, sort_keys=True, separators=(',', ':')), tok),
                )

    def close(self) -> None:
        if self.db is not None:
            try:
                self.db.close()
            except sqlite3.Error:
                pass
            self.db = None

    def __enter__(self) -> T4TokenStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _salt(self) -> bytes:
        assert self.db is not None
        row = self.db.execute("SELECT value FROM t4_meta WHERE key='hmac_salt'").fetchone()
        if not row or not isinstance(row[0], str):
            raise LibraryError('STORAGE_UNAVAILABLE')
        return row[0].encode('ascii')

    @staticmethod
    def _check_scope(source_id: str, generation: str, site_hash: str) -> None:
        if (
            not isinstance(source_id, str)
            or not re.fullmatch(r'[0-9a-f]{32}', source_id)
            or not isinstance(generation, str)
            or not re.fullmatch(r'[0-9a-f]{64}', generation)
            or not isinstance(site_hash, str)
            or not re.fullmatch(r'[0-9a-f]{64}', site_hash)
        ):
            raise LibraryError('T4_CHANGED')

    def _mint(self, salt: bytes, source_id: str, generation: str, site_hash: str, kind: str, raw: str) -> str:
        msg = f'{source_id}:{generation}:{site_hash}:{kind}:{raw}'.encode('utf-8')
        return hmac.new(salt, msg, hashlib.sha256).hexdigest()[:32]

    def _evict_in_tx(self, protected: set[str]) -> None:
        assert self.db is not None
        count = self.db.execute('SELECT COUNT(*) FROM t4_tokens').fetchone()[0]
        if count <= MAX_TOKENS:
            return
        excess = count - MAX_TOKENS
        keep = [t for t in protected if isinstance(t, str) and re.fullmatch(r'[0-9a-f]{32}', t)]
        if keep and len(keep) < MAX_TOKENS:
            placeholders = ','.join('?' for _ in keep)
            self.db.execute(
                f"""
                DELETE FROM t4_tokens WHERE token IN (
                    SELECT token FROM t4_tokens
                    WHERE token NOT IN ({placeholders})
                    ORDER BY updated_at ASC LIMIT ?
                )
                """,
                (*keep, excess),
            )
        else:
            self.db.execute(
                """
                DELETE FROM t4_tokens WHERE token IN (
                    SELECT token FROM t4_tokens ORDER BY updated_at ASC LIMIT ?
                )
                """,
                (excess,),
            )

    def _touch_in_tx(self, source_id: str, generation: str, site_hash: str, tokens) -> None:
        assert self.db is not None
        for tok in tokens:
            if isinstance(tok, str) and re.fullmatch(r'[0-9a-f]{32}', tok):
                self.db.execute(
                    'UPDATE t4_tokens SET updated_at=? WHERE token=? AND source_id=? AND generation=? AND site_hash=?',
                    (self._next_stamp(), tok, source_id, generation, site_hash),
                )

    def _put(
        self,
        source_id: str,
        generation: str,
        site_hash: str,
        kind: str,
        payload: object,
        *,
        token_identity: str | None = None,
        pinned_tokens=(),
    ) -> str:
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
        self._check_scope(source_id, generation, site_hash)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        ident_raw = token_identity if token_identity is not None else raw
        tok = self._mint(self._salt(), source_id, generation, site_hash, kind, ident_raw)
        with self.db:
            self._touch_in_tx(source_id, generation, site_hash, pinned_tokens)
            stamp = self._next_stamp()
            self.db.execute(
                """
                INSERT INTO t4_tokens(token, source_id, generation, site_hash, kind, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (tok, source_id, generation, site_hash, kind, raw, stamp),
            )
            self._evict_in_tx({tok, *pinned_tokens})
        return tok

    def _get(self, source_id: str, generation: str, site_hash: str, kind: str, tok: str):
        if (
            not isinstance(tok, str)
            or not re.fullmatch(r'[0-9a-f]{32}', tok)
            or not isinstance(source_id, str)
            or not re.fullmatch(r'[0-9a-f]{32}', source_id)
            or not isinstance(generation, str)
            or not re.fullmatch(r'[0-9a-f]{64}', generation)
            or not isinstance(site_hash, str)
            or not re.fullmatch(r'[0-9a-f]{64}', site_hash)
        ):
            raise LibraryError('T4_TOKEN_EXPIRED')
        if self.db is None:
            raise LibraryError('T4_TOKEN_EXPIRED')
        try:
            row = self.db.execute(
                """
                SELECT payload_json FROM t4_tokens
                WHERE token=? AND source_id=? AND generation=? AND site_hash=? AND kind=?
                """,
                (tok, source_id, generation, site_hash, kind),
            ).fetchone()
            if not row:
                raise LibraryError('T4_TOKEN_EXPIRED')
            if not self.read_only:
                with self.db:
                    self.db.execute(
                        'UPDATE t4_tokens SET updated_at=? WHERE token=?',
                        (self._next_stamp(), tok),
                    )
        except LibraryError:
            raise
        except sqlite3.Error:
            raise LibraryError('T4_TOKEN_EXPIRED') from None
        return json.loads(row[0])

    @staticmethod
    def _validate_vod_id(vod_id: str) -> str:
        if not isinstance(vod_id, str) or not (1 <= len(vod_id) <= 4096) or any(ord(c) < 32 for c in vod_id):
            raise LibraryError('T4_PLAY_UNSUPPORTED')
        return vod_id

    def put_item(self, source_id: str, generation: str, site_hash: str, vod_id: str, *, pinned_tokens=()) -> str:
        self._validate_vod_id(vod_id)
        return self._put(source_id, generation, site_hash, 'item', vod_id, pinned_tokens=pinned_tokens)

    def put_item_batch(
        self,
        source_id: str,
        generation: str,
        site_hash: str,
        vod_ids: list[str],
        *,
        pinned_tokens=(),
    ) -> list[str]:
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
        self._check_scope(source_id, generation, site_hash)
        if not isinstance(vod_ids, list) or len(vod_ids) > MAX_BATCH_TOKENS:
            raise LibraryError('T4_LIMIT')
        for vid in vod_ids:
            self._validate_vod_id(vid)
        if not vod_ids:
            return []
        salt = self._salt()
        out_tokens: list[str] = []
        rows_to_insert = []
        with self.db:
            self._touch_in_tx(source_id, generation, site_hash, pinned_tokens)
            for vid in vod_ids:
                raw = json.dumps(vid, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                tok = self._mint(salt, source_id, generation, site_hash, 'item', raw)
                out_tokens.append(tok)
                rows_to_insert.append((tok, source_id, generation, site_hash, 'item', raw, self._next_stamp()))
            self.db.executemany(
                """
                INSERT INTO t4_tokens(token, source_id, generation, site_hash, kind, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET updated_at=excluded.updated_at
                """,
                rows_to_insert,
            )
            self._evict_in_tx({*out_tokens, *pinned_tokens})
        return out_tokens

    def get_item(self, source_id: str, generation: str, site_hash: str, tok: str) -> str:
        val = self._get(source_id, generation, site_hash, 'item', tok)
        if not isinstance(val, str) or not val:
            raise LibraryError('T4_TOKEN_EXPIRED')
        return val

    def put_category(
        self,
        source_id: str,
        generation: str,
        site_hash: str,
        type_id: str,
        *,
        facets: list | None = None,
        name: str = '',
    ) -> str:
        if not isinstance(type_id, str) or not (1 <= len(type_id) <= 512) or any(ord(c) < 32 for c in type_id):
            raise LibraryError('INVALID_DOCUMENT')
        ident = json.dumps(type_id, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if facets is None and not name:
            payload: object = type_id
        else:
            payload = {
                'type_id': type_id,
                'name': str(name or '')[:120],
                'facets': list(facets) if facets is not None else None,
            }
        return self._put(source_id, generation, site_hash, 'cat', payload, token_identity=ident)

    def get_category_meta(self, source_id: str, generation: str, site_hash: str, tok: str) -> dict:
        val = self._get(source_id, generation, site_hash, 'cat', tok)
        if isinstance(val, str) and val:
            return {'type_id': val, 'name': '', 'facets': None}
        if isinstance(val, dict) and isinstance(val.get('type_id'), str) and val['type_id']:
            return {
                'type_id': val['type_id'],
                'name': str(val.get('name') or ''),
                'facets': val.get('facets') if isinstance(val.get('facets'), list) else None,
            }
        raise LibraryError('T4_TOKEN_EXPIRED')

    def get_category(self, source_id: str, generation: str, site_hash: str, tok: str) -> str:
        return self.get_category_meta(source_id, generation, site_hash, tok)['type_id']

    def put_filter(
        self,
        source_id: str,
        generation: str,
        site_hash: str,
        type_id: str,
        filters: dict[str, str],
        *,
        pinned_tokens=(),
    ) -> str:
        if not isinstance(type_id, str) or not (1 <= len(type_id) <= 512):
            raise LibraryError('INVALID_DOCUMENT')
        if not isinstance(filters, dict) or len(filters) > 16:
            raise LibraryError('INVALID_DOCUMENT')
        cleaned: dict[str, str] = {}
        for k, v in filters.items():
            if (
                not isinstance(k, str)
                or not (1 <= len(k) <= 64)
                or any(ord(c) < 32 for c in k)
                or not isinstance(v, str)
                or len(v) > 256
                or any(ord(c) < 32 for c in v)
            ):
                raise LibraryError('INVALID_DOCUMENT')
            if v:
                cleaned[k] = v
        payload = {'type_id': type_id, 'filters': cleaned}
        return self._put(source_id, generation, site_hash, 'flt', payload, pinned_tokens=pinned_tokens)

    def get_filter(self, source_id: str, generation: str, site_hash: str, type_id: str, tok: str) -> dict[str, str]:
        val = self._get(source_id, generation, site_hash, 'flt', tok)
        if (
            not isinstance(val, dict)
            or val.get('type_id') != type_id
            or not isinstance(val.get('filters'), dict)
        ):
            raise LibraryError('T4_TOKEN_EXPIRED')
        return dict(val['filters'])

    def _build_play_record(
        self,
        source_id: str,
        generation: str,
        site_hash: str,
        item_token: str,
        line: str,
        episode: str,
        title: str,
        vod_id: str | None,
        line_name: str | None,
        episode_id: str | None,
    ) -> tuple[dict, str]:
        if not isinstance(item_token, str) or not re.fullmatch(r'[0-9a-f]{32}', item_token):
            raise LibraryError('T4_TOKEN_EXPIRED')
        if not isinstance(line, str) or not line or not isinstance(episode, str) or not episode:
            raise LibraryError('T4_PLAY_UNSUPPORTED')
        resolved_vid = vod_id
        if resolved_vid is None and self.db is not None:
            prow = self.db.execute(
                "SELECT payload_json FROM t4_tokens WHERE token=? AND source_id=? AND generation=? AND site_hash=? AND kind='item'",
                (item_token, source_id, generation, site_hash),
            ).fetchone()
            if prow:
                loaded = json.loads(prow[0])
                if isinstance(loaded, str) and loaded:
                    resolved_vid = loaded
        if resolved_vid is not None:
            self._validate_vod_id(resolved_vid)
        else:
            resolved_vid = ''
        is_lhash = bool(re.fullmatch(r'[0-9a-f]{64}', line))
        is_ehash = bool(re.fullmatch(r'[0-9a-f]{64}', episode))
        lhash = line if is_lhash else _sha256_hex(line)
        ehash = episode if is_ehash else _sha256_hex(episode)
        raw_lname = str(line_name if line_name is not None else ('' if is_lhash else line))[:120]
        raw_eid = str(episode_id if episode_id is not None else ('' if is_ehash else episode))[:8192]
        payload = {
            'schema': SCHEMA_VERSION,
            'item_token': item_token,
            'vod_id': resolved_vid,
            'line': lhash,
            'line_name': raw_lname,
            'episode': ehash,
            'episode_id': raw_eid,
            'title': str(title or '')[:512],
        }
        ident_key = json.dumps(
            {'vod_id': resolved_vid or item_token, 'line': lhash, 'episode': ehash},
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        )
        return payload, ident_key

    def put_play(
        self,
        source_id: str,
        generation: str,
        site_hash: str,
        item_token: str,
        line: str,
        episode: str,
        title: str,
        *,
        vod_id: str | None = None,
        line_name: str | None = None,
        episode_id: str | None = None,
    ) -> str:
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
        self._check_scope(source_id, generation, site_hash)
        payload, ident_key = self._build_play_record(
            source_id, generation, site_hash, item_token, line, episode, title, vod_id, line_name, episode_id
        )
        return self._put(
            source_id,
            generation,
            site_hash,
            'play',
            payload,
            token_identity=ident_key,
            pinned_tokens=(item_token,),
        )

    def put_play_batch(
        self,
        source_id: str,
        generation: str,
        site_hash: str,
        item_token: str,
        vod_id: str,
        entries: list[tuple[str, str, str]],
        *,
        pinned_tokens=(),
    ) -> list[str]:
        """Batch-insert up to MAX_BATCH_TOKENS self-contained play records in ONE SQLite transaction."""
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
        self._check_scope(source_id, generation, site_hash)
        self._validate_vod_id(vod_id)
        if not isinstance(entries, list) or len(entries) > MAX_BATCH_TOKENS:
            raise LibraryError('T4_LIMIT')
        if not entries:
            return []
        salt = self._salt()
        out_tokens: list[str] = []
        rows_to_insert = []
        all_pinned = (item_token, *pinned_tokens)
        with self.db:
            self._touch_in_tx(source_id, generation, site_hash, all_pinned)
            for raw_line, raw_ep, ep_title in entries:
                payload, ident_key = self._build_play_record(
                    source_id,
                    generation,
                    site_hash,
                    item_token,
                    raw_line,
                    raw_ep,
                    ep_title,
                    vod_id,
                    raw_line,
                    raw_ep,
                )
                raw_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                tok = self._mint(salt, source_id, generation, site_hash, 'play', ident_key)
                out_tokens.append(tok)
                rows_to_insert.append((tok, source_id, generation, site_hash, 'play', raw_json, self._next_stamp()))
            self.db.executemany(
                """
                INSERT INTO t4_tokens(token, source_id, generation, site_hash, kind, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                rows_to_insert,
            )
            self._evict_in_tx({*out_tokens, *all_pinned})
        return out_tokens

    def get_play(self, source_id: str, generation: str, site_hash: str, tok: str) -> dict:
        val = self._get(source_id, generation, site_hash, 'play', tok)
        if not isinstance(val, dict):
            raise LibraryError('T4_TOKEN_EXPIRED')
        if set(val) == {'item_token', 'line', 'episode', 'title'}:
            # Legacy v1 row fallback ONLY via valid resident item_token; NEVER raw token!
            vid = self.get_item(source_id, generation, site_hash, val['item_token'])
            return {
                'schema': 1,
                'item_token': val['item_token'],
                'vod_id': vid,
                'line': val['line'],
                'line_name': '',
                'episode': val['episode'],
                'episode_id': '',
                'title': val['title'],
            }
        expected_keys = {'schema', 'item_token', 'vod_id', 'line', 'line_name', 'episode', 'episode_id', 'title'}
        if not expected_keys <= set(val):
            raise LibraryError('T4_TOKEN_EXPIRED')
        if (
            not isinstance(val['line'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', val['line'])
            or not isinstance(val['episode'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', val['episode'])
            or not isinstance(val['vod_id'], str)
        ):
            raise LibraryError('T4_TOKEN_EXPIRED')
        return val

    def approve_origin(self, source_id: str, generation: str, raw_origin: str) -> str:
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
        self._check_scope(source_id, generation, '0' * 64)
        from urllib.parse import urlsplit
        checked = endpoint(raw_origin, 'SOURCE_HTTP_URL')
        parts = urlsplit(checked)
        canonical = f'{parts.scheme}://{parts.netloc.lower()}'
        with self.db:
            cnt = self.db.execute(
                'SELECT COUNT(*) FROM t4_approved_origins WHERE source_id=? AND generation=?',
                (source_id, generation),
            ).fetchone()[0]
            if cnt >= MAX_APPROVED_ORIGINS_PER_SOURCE:
                raise LibraryError('T4_LIMIT')
            self.db.execute(
                """
                INSERT OR IGNORE INTO t4_approved_origins(source_id, generation, origin, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (source_id, generation, canonical, time.time_ns()),
            )
        return canonical

    def approved_origins(self, source_id: str, generation: str) -> set[str]:
        if self.db is None:
            return set()
        try:
            rows = self.db.execute(
                'SELECT origin FROM t4_approved_origins WHERE source_id=? AND generation=?',
                (source_id, generation),
            ).fetchall()
        except sqlite3.Error:
            return set()
        return {r[0] for r in rows if isinstance(r[0], str)}

    def revoke_origin(self, source_id: str, generation: str | None = None, raw_origin: str | None = None) -> int:
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
        if not isinstance(source_id, str) or not re.fullmatch(r'[0-9a-f]{32}', source_id):
            raise LibraryError('T4_TOKEN_EXPIRED')
        canonical = None
        if raw_origin is not None:
            from urllib.parse import urlsplit
            checked = endpoint(raw_origin, 'SOURCE_HTTP_URL')
            parts = urlsplit(checked)
            canonical = f'{parts.scheme}://{parts.netloc.lower()}'
        with self.db:
            if generation is not None and canonical is not None:
                cur = self.db.execute(
                    'DELETE FROM t4_approved_origins WHERE source_id=? AND generation=? AND origin=?',
                    (source_id, generation, canonical),
                )
            elif generation is not None:
                cur = self.db.execute(
                    'DELETE FROM t4_approved_origins WHERE source_id=? AND generation=?',
                    (source_id, generation),
                )
            else:
                cur = self.db.execute(
                    'DELETE FROM t4_approved_origins WHERE source_id=?',
                    (source_id,),
                )
            return int(cur.rowcount or 0)

    def record_blocked_origin(self, source_id: str, generation: str, request_id: str, raw_origin: str) -> str:
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
        self._check_scope(source_id, generation, '0' * 64)
        if not isinstance(request_id, str) or not re.fullmatch(r'[0-9a-f]{32}', request_id):
            raise LibraryError('SOURCE_STREAM_INVALID')
        from urllib.parse import urlsplit
        checked = endpoint(raw_origin, 'SOURCE_HTTP_URL')
        parts = urlsplit(checked)
        canonical = f'{parts.scheme}://{parts.netloc.lower()}'
        with self.db:
            self.db.execute(
                """
                INSERT INTO t4_pending_origin_prompts(request_id, source_id, generation, origin, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    source_id=excluded.source_id,
                    generation=excluded.generation,
                    origin=excluded.origin,
                    created_at=excluded.created_at
                """,
                (request_id, source_id, generation, canonical, time.time_ns()),
            )
            self.db.execute(
                """
                DELETE FROM t4_pending_origin_prompts
                WHERE request_id IN (
                    SELECT request_id FROM t4_pending_origin_prompts
                    ORDER BY created_at DESC LIMIT -1 OFFSET 32
                )
                """
            )
        return canonical

    def pop_blocked_origin(self, source_id: str, generation: str, request_id: str) -> str | None:
        if self.read_only or self.db is None:
            return None
        if not isinstance(request_id, str) or not re.fullmatch(r'[0-9a-f]{32}', request_id):
            return None
        with self.db:
            row = self.db.execute(
                'SELECT origin FROM t4_pending_origin_prompts WHERE request_id=? AND source_id=? AND generation=?',
                (request_id, source_id, generation),
            ).fetchone()
            self.db.execute('DELETE FROM t4_pending_origin_prompts WHERE request_id=?', (request_id,))
        return row[0] if row and isinstance(row[0], str) else None

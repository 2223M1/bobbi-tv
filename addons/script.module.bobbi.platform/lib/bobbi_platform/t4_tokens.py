"""Persistent bounded SQLite store for opaque T4 selection tokens and approved media origins.

Implements R13-01, R13-02, R13-05, R14-02, and REV-11:
- Keeps URL-shaped/arbitrary vod_id, category type_id, and line/episode play references out of
  Kodi plugin URLs, Host IPC, and logs.
- Strictly separated from short-lived playback grants so directory pages remain navigable across
  pauses and Host restarts, while invalidating immediately on (source_id, generation) change.
- Bounded at MAX_TOKENS (4096) with LRU eviction; missing/evicted tokens raise T4_TOKEN_EXPIRED
  and are NEVER forwarded as raw vod_id strings.
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
MAX_APPROVED_ORIGINS_PER_SOURCE = 64
SCHEMA_VERSION = 1


class T4TokenStore:
    def __init__(self, path: Path | str, *, read_only: bool = False, timeout: float = 1.0):
        self.path = Path(path)
        self.read_only = read_only
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
                'INSERT OR IGNORE INTO t4_meta(key, value) VALUES (?, ?)',
                ('hmac_salt', secrets.token_hex(32)),
            )
            self.db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

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

    def _put(self, source_id: str, generation: str, site_hash: str, kind: str, payload: object) -> str:
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
        if (
            not re.fullmatch(r'[0-9a-f]{32}', source_id)
            or not re.fullmatch(r'[0-9a-f]{64}', generation)
            or not re.fullmatch(r'[0-9a-f]{64}', site_hash)
        ):
            raise LibraryError('T4_CHANGED')
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        msg = f'{source_id}:{generation}:{site_hash}:{kind}:{raw}'.encode('utf-8')
        tok = hmac.new(self._salt(), msg, hashlib.sha256).hexdigest()[:32]
        now_ns = time.time_ns()
        with self.db:
            self.db.execute(
                """
                INSERT INTO t4_tokens(token, source_id, generation, site_hash, kind, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (tok, source_id, generation, site_hash, kind, raw, now_ns),
            )
            count = self.db.execute('SELECT COUNT(*) FROM t4_tokens').fetchone()[0]
            if count > MAX_TOKENS:
                excess = count - MAX_TOKENS
                self.db.execute(
                    """
                    DELETE FROM t4_tokens WHERE token IN (
                        SELECT token FROM t4_tokens ORDER BY updated_at ASC LIMIT ?
                    )
                    """,
                    (excess,),
                )
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
        except sqlite3.Error:
            raise LibraryError('T4_TOKEN_EXPIRED') from None
        if not row:
            raise LibraryError('T4_TOKEN_EXPIRED')
        return json.loads(row[0])

    def put_item(self, source_id: str, generation: str, site_hash: str, vod_id: str) -> str:
        if not isinstance(vod_id, str) or not (1 <= len(vod_id) <= 4096) or any(ord(c) < 32 for c in vod_id):
            raise LibraryError('T4_PLAY_UNSUPPORTED')
        return self._put(source_id, generation, site_hash, 'item', vod_id)

    def get_item(self, source_id: str, generation: str, site_hash: str, tok: str) -> str:
        val = self._get(source_id, generation, site_hash, 'item', tok)
        if not isinstance(val, str) or not val:
            raise LibraryError('T4_TOKEN_EXPIRED')
        return val

    def put_category(self, source_id: str, generation: str, site_hash: str, type_id: str) -> str:
        if not isinstance(type_id, str) or not (1 <= len(type_id) <= 512) or any(ord(c) < 32 for c in type_id):
            raise LibraryError('INVALID_DOCUMENT')
        return self._put(source_id, generation, site_hash, 'cat', type_id)

    def get_category(self, source_id: str, generation: str, site_hash: str, tok: str) -> str:
        val = self._get(source_id, generation, site_hash, 'cat', tok)
        if not isinstance(val, str) or not val:
            raise LibraryError('T4_TOKEN_EXPIRED')
        return val

    def put_play(
        self,
        source_id: str,
        generation: str,
        site_hash: str,
        item_token: str,
        line_hash: str,
        episode_hash: str,
        title: str,
    ) -> str:
        payload = {
            'item_token': item_token,
            'line': line_hash,
            'episode': episode_hash,
            'title': str(title or '')[:512],
        }
        return self._put(source_id, generation, site_hash, 'play', payload)

    def get_play(self, source_id: str, generation: str, site_hash: str, tok: str) -> dict:
        val = self._get(source_id, generation, site_hash, 'play', tok)
        if not isinstance(val, dict) or set(val) != {'item_token', 'line', 'episode', 'title'}:
            raise LibraryError('T4_TOKEN_EXPIRED')
        return val

    def approve_origin(self, source_id: str, generation: str, raw_origin: str) -> str:
        if self.read_only or self.db is None:
            raise LibraryError('STORAGE_UNAVAILABLE')
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

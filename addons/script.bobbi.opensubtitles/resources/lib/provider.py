# Modified for bobbi portability and explicit credentials, 2026-10-19.
"""Manual Chinese subtitle candidates; never grants playback mutation rights.

REST contract researched against the GPLv2 official OpenSubtitles Kodi provider
1.0.91, commit 7acfa8f2932a0155ba921212882baa0fade05890. Its public application
configuration is NOT shipped. Supply the user's own application API key.
No credentials, signed URLs, Kodi player calls or automatic downloads.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from urllib.parse import urlencode

API = 'https://api.opensubtitles.com/api/v1/'
USER_AGENT = 'bobbi TV OpenSubtitles integration v0.1.0'
MAX_BYTES = 2 * 1024 * 1024
LANGUAGES = {'zh-cn': '简中', 'zh-tw': '繁中', 'ze': '中文双语声明'}
EXCLUDE = re.compile(r'(?i)commentary|\bforced\b|signs.?and.?songs|导演评论|導演評論|仅标识|僅標識')
EDITION = re.compile(r'(?i)extended|unrated|director.?s.?cut|theatrical|imax')


class ProviderError(RuntimeError):
    def __init__(self, reason, retry_after=None):
        self.reason = reason
        self.retry_after = retry_after
        super().__init__(reason)


def _positive(value):
    if type(value) is int and 0 < value < 2 ** 63:
        return value
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,17}', value):
        return int(value)
    return None


def _imdb(value):
    if isinstance(value, str) and value.startswith('tt'):
        value = value[2:]
        if re.fullmatch(r'[0-9]{5,12}', value):
            value = value.lstrip('0')
    return _positive(value)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode('ascii')).hexdigest()


def _identity(context):
    if not isinstance(context, dict):
        raise ProviderError('CONTEXT_INVALID')
    kind = {'movie': 'movie', 'tv': 'episode', 'series': 'episode'}.get(context.get('mode'))
    tmdb, imdb = _positive(context.get('tmdb')), _imdb(context.get('imdb'))
    duration = context.get('duration')
    if (not kind or not (tmdb or imdb) or type(duration) not in (int, float)
            or not math.isfinite(duration) or not 60 <= duration <= 21600):
        raise ProviderError('CONTEXT_INVALID')
    identity = dict(kind=kind, tmdb=tmdb, imdb=imdb)
    if kind == 'movie':
        year = context.get('year')
        if type(year) is not int or not 1888 <= year <= 2100:
            raise ProviderError('CONTEXT_INVALID')
        identity['year'] = year
    else:
        season, episode = context.get('season'), context.get('episode')
        if (type(season) is not int or not 0 <= season <= 999
                or type(episode) is not int or not 1 <= episode <= 10000):
            raise ProviderError('CONTEXT_INVALID')
        identity.update(season=season, episode=episode)
    return identity


def _matches(feature, identity):
    if not isinstance(feature, dict) or str(feature.get('feature_type', '')).lower() != identity['kind']:
        return False
    prefix = 'parent_' if identity['kind'] == 'episode' else ''
    matched = False
    for field in ('tmdb', 'imdb'):
        expected = identity[field]
        actual = (_imdb if field == 'imdb' else _positive)(feature.get(prefix + field + '_id'))
        if expected and actual:
            if expected != actual:
                return False  # One agreeing ID never overrides a conflicting ID.
            matched = True
    if not matched:
        return False
    if identity['kind'] == 'movie':
        return type(feature.get('year')) is int and feature['year'] == identity['year']
    return (type(feature.get('season_number')) is int and type(feature.get('episode_number')) is int
            and feature['season_number'] == identity['season'] and feature['episode_number'] == identity['episode'])


def _editions(value):
    return {re.sub(r'[^a-z]', '', match.group().lower()) for match in EDITION.finditer(value)}


def _candidate(row, identity, context):
    if not isinstance(row, dict) or not isinstance(row.get('attributes'), dict):
        return None
    data = row['attributes']
    language = str(data.get('language', '')).lower()
    feature = data.get('feature_details')
    if (language not in LANGUAGES or not _matches(feature, identity)
            or any(data.get(flag) is not False for flag in ('foreign_parts_only', 'machine_translated', 'ai_translated'))):
        return None
    files = data.get('files')
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        return None  # Do not guess which segment of a split subtitle applies.
    file_data = files[0]
    file_id = _positive(file_data.get('file_id'))
    if not file_id or file_data.get('cd_number', 1) != 1:
        return None
    release, filename = data.get('release'), file_data.get('file_name')
    if not all(isinstance(value, str) and 0 < len(value) <= 1024 and '://' not in value
               and not any(ord(char) < 32 or ord(char) == 127 for char in value)
               for value in (release, filename)):
        return None
    evidence = release + ' ' + filename
    if EXCLUDE.search(evidence) or _editions(evidence) != _editions(str(context.get('release') or '')[:1024]):
        return None
    if identity['kind'] == 'movie':
        from bobbi_core.movie_identity import declared_years
        aliases = [feature.get('title'), context.get('title')]
        if any(not declared_years(value, aliases) <= {identity['year']} for value in (release, filename)):
            return None
    else:
        from bobbi_core.subtitle_candidates import episode_tags
        if any(not episode_tags(value) <= {(identity['season'], identity['episode'])}
               for value in (release, filename)):
            return None
    fps = data.get('fps')
    if type(fps) not in (int, float) or not math.isfinite(fps) or not 0 <= fps <= 240:
        fps = None
    item = dict(provider='opensubtitles', file_id=file_id, identity=identity, language=language,
                title=release, filename=filename, fps=fps, sync_verified=False,
                label=LANGUAGES[language] + ' · ' + release + ' · 待校准')
    item['key'] = _digest(item)
    return item


class Provider:
    def __init__(self, state_directory, transport=None, clock=time.monotonic, wall=time.time,
                 api_key=''):
        self.directory = Path(state_directory)
        self.transport, self.clock, self.wall = transport, clock, wall
        self.api_key = api_key

    def _guard(self, deadline, cancelled):
        if cancelled():
            raise ProviderError('CANCELLED')
        if self.clock() >= deadline:
            raise ProviderError('TIMEOUT')

    def _deadline(self, deadline):
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ProviderError('CONTEXT_INVALID')
        return min(deadline, self.clock() + 20)

    def _api_key(self):
        key = self.api_key
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9]{16,128}', key):
            raise ProviderError('PROVIDER_NOT_CONFIGURED')
        return key

    @contextmanager
    def _operation(self, deadline, cancelled):
        self._guard(deadline, cancelled)
        if any(path.is_symlink() for path in (self.directory, *self.directory.parents)):
            raise ProviderError('CACHE_INVALID')
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.stat()
        if (os.name == 'posix' and stat.S_IMODE(info.st_mode) & 0o022
                or hasattr(os, 'getuid') and info.st_uid != os.getuid()):
            raise ProviderError('CACHE_INVALID')
        db_path = self.directory / 'provider.sqlite3'
        if db_path.is_symlink() or (db_path.exists() and (not db_path.is_file() or db_path.stat().st_size > 4 * 1024 * 1024)):
            raise ProviderError('CACHE_INVALID')
        connection = None
        try:
            connection = sqlite3.connect(str(db_path), timeout=0)
            connection.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, key TEXT, body TEXT, updated REAL, PRIMARY KEY(kind,key))')
            connection.execute('BEGIN IMMEDIATE')  # No cross-process double spend or queued workers.
            self._guard(deadline, cancelled)
            yield connection
        except sqlite3.OperationalError as error:
            raise ProviderError('BUSY') from error
        except sqlite3.DatabaseError as error:
            raise ProviderError('CACHE_INVALID') from error
        finally:
            if connection is not None:
                # A successful quota-consuming POST is remembered even when its
                # body fetch is later cancelled. No signed URL is ever saved.
                connection.commit()
                connection.close()

    def _get(self, db, kind, key, age):
        row = db.execute('SELECT body,updated FROM records WHERE kind=? AND key=?', (kind, key)).fetchone()
        if not row or not self.wall() - age <= row[1] <= self.wall() + 5 or len(row[0]) > 16384:
            return None
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return None

    def _put(self, db, kind, key, value):
        body = _json(value)
        if len(body) > 16384:
            raise ProviderError('CACHE_INVALID')
        db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (kind, key, body, self.wall()))
        db.execute('DELETE FROM records WHERE rowid IN (SELECT rowid FROM records WHERE kind=? ORDER BY updated DESC,rowid DESC LIMIT -1 OFFSET 128)', (kind,))

    def _quota(self, db, download=False):
        state = self._get(db, 'quota', 'shared', 172800) or {}
        until = state.get('cooldown_until', 0)
        if type(until) in (int, float) and until > self.wall():
            raise ProviderError('RATE_LIMIT', min(86400, int(math.ceil(until - self.wall()))))
        if download and state.get('remaining') == 0 and state.get('reset_at', 0) > self.wall():
            raise ProviderError('QUOTA_EXHAUSTED')
        return state

    def _read(self, db, url, deadline, cancelled, mode, method='GET', body=None):
        from bobbi_core.subtitle_io import read_http, SubtitleIOStopped
        self._guard(deadline, cancelled)
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json' if mode == 'opensubtitles_api' else 'text/plain'}
        if mode == 'opensubtitles_api':
            headers['Api-Key'] = self._api_key()
        try:
            raw = (self.transport or read_http)(url, deadline, cancelled, MAX_BYTES,
                mode=mode, headers=headers, method=method, json_body=body, clock=self.clock,
                trusted_proxy=None)
        except SubtitleIOStopped as error:
            self._guard(deadline, cancelled)
            reason = str(error)
            retry = re.fullmatch(r'OPENSUBTITLES_RATE_LIMIT_RETRY_([0-9]{1,5})', reason)
            if retry and 1 <= int(retry[1]) <= 86400:
                state = self._get(db, 'quota', 'shared', 172800) or {}
                state['cooldown_until'] = self.wall() + int(retry[1])
                self._put(db, 'quota', 'shared', state)
                raise ProviderError('RATE_LIMIT', int(retry[1])) from error
            if reason in ('OPENSUBTITLES_HTTP_401', 'OPENSUBTITLES_HTTP_403'):
                raise ProviderError('AUTH_UNAVAILABLE') from error
            if reason == 'OPENSUBTITLES_HTTP_406':
                self._put(db, 'quota', 'shared', dict(remaining=0, reset_at=self.wall() + 86400))
                raise ProviderError('QUOTA_EXHAUSTED') from error
            mapping = {'SUBTITLE_IO_DEADLINE': 'TIMEOUT', 'SUBTITLE_IO_TimeoutError': 'TIMEOUT',
                       'SUBTITLE_IO_BUSY': 'BUSY', 'SUBTITLE_IO_ORIGIN': 'ORIGIN_REJECTED',
                       'SUBTITLE_IO_SIZE': 'SIZE_REJECTED', 'SUBTITLE_IO_LENGTH': 'RESPONSE_INVALID',
                       'SUBTITLE_IO_ENCODING': 'RESPONSE_INVALID'}
            raise ProviderError(mapping.get(reason, 'PROVIDER_UNAVAILABLE')) from error
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
            raise ProviderError('RESPONSE_INVALID')
        if method != 'POST':
            self._guard(deadline, cancelled)
        return raw

    def search(self, context, deadline, cancelled):
        identity = _identity(context)
        deadline = self._deadline(deadline)
        with self._operation(deadline, cancelled) as db:
            self._quota(db)
            # The upstream request model omits its machine_translated=exclude
            # default; the API canonicalizes explicit defaults with a 301.
            # Independently reject every returned machine/AI/forced candidate.
            params = dict(languages='zh-cn,zh-tw,ze', type=identity['kind'],
                          foreign_parts_only='exclude', ai_translated='exclude')
            prefix = 'parent_' if identity['kind'] == 'episode' else ''
            for field in ('tmdb', 'imdb'):
                if identity[field]:
                    params[prefix + field + '_id'] = identity[field]
            if identity['kind'] == 'movie':
                params['year'] = identity['year']
            else:
                params.update(season_number=identity['season'], episode_number=identity['episode'])
            raw = self._read(db, API + 'subtitles?' + urlencode(sorted(params.items())), deadline, cancelled, 'opensubtitles_api')
            try:
                response = json.loads(raw)
            except (ValueError, UnicodeError) as error:
                raise ProviderError('RESPONSE_INVALID') from error
            if not isinstance(response, dict) or not isinstance(response.get('data'), list):
                raise ProviderError('RESPONSE_INVALID')
            items, seen = [], set()
            for row in response['data'][:60]:
                item = _candidate(row, identity, context)
                if item and item['file_id'] not in seen:
                    seen.add(item['file_id'])
                    items.append(item)
            release = str(context.get('release') or '').casefold()
            items.sort(key=lambda item: (item['title'].casefold() != release,
                {'ze': 0, 'zh-cn': 1, 'zh-tw': 2}[item['language']], item['file_id']))
            items = items[:20]
            self._guard(deadline, cancelled)
            for item in items:
                self._put(db, 'candidate', item['key'], item)
            return items

    def _cached(self, db, cache_key, context, root):
        record = self._get(db, 'download', cache_key, 86400)
        if not isinstance(record, dict):
            return None
        try:
            path = Path(record['path'])
            if not path.exists() and not path.is_symlink():
                return None
            if (path.parent.resolve() != Path(root).resolve() or path.is_symlink()
                    or not re.fullmatch(r'[0-9a-f]{32}\.srt', path.name)
                    or not path.is_file() or path.stat().st_size != record['bytes']
                    or not 0 < record['bytes'] <= MAX_BYTES):
                raise ProviderError('CACHE_INVALID')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != record['sha256']:
                raise ProviderError('CACHE_INVALID')
            return raw
        except (OSError, KeyError, TypeError, ValueError):
            return None

    def download(self, candidate, context, deadline, cancelled, root):
        from bobbi_core.subtitle_candidates import inspect_text, publish
        identity = _identity(context)
        deadline = self._deadline(deadline)
        if not isinstance(candidate, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(candidate.get('key', ''))):
            raise ProviderError('IDENTITY_REJECTED')
        with self._operation(deadline, cancelled) as db:
            stored = self._get(db, 'candidate', candidate['key'], 3600)
            if (stored != candidate or candidate.get('identity') != identity
                    or _editions(candidate.get('title', '') + ' ' + candidate.get('filename', ''))
                    != _editions(str(context.get('release') or '')[:1024])):
                raise ProviderError('IDENTITY_REJECTED')
            cache_key = _digest(dict(file_id=stored['file_id'], identity=identity))
            raw = self._cached(db, cache_key, context, root)
            cached = raw is not None
            remaining = (self._get(db, 'quota', 'shared', 172800) or {}).get('remaining')
            if not cached:
                self._quota(db, download=True)
                response = self._read(db, API + 'download', deadline, cancelled, 'opensubtitles_api',
                                      method='POST', body=dict(file_id=stored['file_id'], sub_format='srt'))
                try:
                    response = json.loads(response)
                except (ValueError, UnicodeError) as error:
                    raise ProviderError('RESPONSE_INVALID') from error
                if not isinstance(response, dict):
                    raise ProviderError('RESPONSE_INVALID')
                remaining = response.get('remaining')
                if type(remaining) is int and 0 <= remaining <= 100000:
                    reset_at = self.wall() + 86400
                    try:
                        reset = datetime.fromisoformat(str(response.get('reset_time_utc', '')).replace('Z', '+00:00'))
                        if reset.tzinfo is None:
                            reset = reset.replace(tzinfo=timezone.utc)
                        reset_at = max(self.wall(), min(self.wall() + 172800, reset.timestamp()))
                    except (ValueError, OverflowError):
                        pass
                    self._put(db, 'quota', 'shared', dict(remaining=remaining, reset_at=reset_at))
                else:
                    remaining = None
                link = response.get('link')
                if not isinstance(link, str) or len(link) > 8192:
                    raise ProviderError('RESPONSE_INVALID')
                raw = self._read(db, link, deadline, cancelled, 'opensubtitles_download')
            self._guard(deadline, cancelled)
            try:
                raw, bilingual = inspect_text(raw, '.srt', context['duration'])
            except ValueError as error:
                raise ProviderError('TEXT_REJECTED') from error
            self._guard(deadline, cancelled)
            try:
                result = publish(raw, '.srt', root=root)
            except (OSError, ValueError, RuntimeError) as error:
                raise ProviderError('CACHE_INVALID') from error
            self._put(db, 'download', cache_key, result)
            self._guard(deadline, cancelled)
            result.update(title=stored['title'], language=stored['language'], remaining=remaining,
                          sync_verified=False, bilingual=bilingual, cached=cached)
            return result

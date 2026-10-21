"""Bounded subtitle candidates, deliberately separate from proven readiness.

No cloud submissions, video downloads, Kodi calls or video-quality changes.
Only the native playback owner may apply the exported immutable text file.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
from urllib.parse import urlencode

MAX_BYTES = 8 * 1024 * 1024
TEXT_EXTENSIONS = {'.srt', '.ass', '.ssa', '.vtt'}
from bobbi_core.runtime_paths import ProfilePath
TOKEN_FILE = ProfilePath('assrt-token')
ROOT = ProfilePath('subtitle-browser')
PREPARATION_ROOT = ProfilePath('preparation')
EDITION = re.compile(r'(?i)extended|unrated|director.?s.?cut|theatrical|imax')
EXCLUDE = re.compile(r'(?i)commentary|\bforced\b|signs.?and.?songs|导演评论|導演評論|仅标识|僅標識')
_VALUE_REASONS = {
    'Subtitle cue outside exact video timeline': 'SUBTITLE_TIMELINE_MISMATCH',
    'HTML is not a subtitle': 'SUBTITLE_NOT_TEXT',
    'Not a subtitle': 'SUBTITLE_NOT_TEXT',
    'Insufficient full Chinese dialogue': 'SUBTITLE_CHINESE_INSUFFICIENT',
    'Only partial Chinese dialogue': 'SUBTITLE_CHINESE_PARTIAL',
    'Unknown subtitle encoding': 'SUBTITLE_ENCODING_UNSUPPORTED',
    'SUBTITLE_IO_TimeoutError': 'SUBTITLE_DOWNLOAD_TIMEOUT',
    'SUBTITLE_IO_ORIGIN': 'SUBTITLE_DOWNLOAD_ORIGIN_REJECTED',
    'SUBTITLE_IO_SIZE': 'SUBTITLE_DOWNLOAD_SIZE_REJECTED',
    'SUBTITLE_IO_LENGTH': 'SUBTITLE_DOWNLOAD_LENGTH_INVALID',
    'SUBTITLE_IO_ENCODING': 'SUBTITLE_DOWNLOAD_ENCODING_INVALID',
    'SUBTITLE_IO_RESPONSE_INVALID': 'SUBTITLE_DOWNLOAD_RESPONSE_INVALID',
    'Torrent metadata identity changed': 'TORRENT_METADATA_IDENTITY_CHANGED',
    'Playing torrent file identity changed': 'TORRENT_PLAYING_FILE_CHANGED',
    'Subtitle torrent does not belong to playing file': 'TORRENT_SUBTITLE_IDENTITY_MISMATCH',
    'Bounded torrent file metadata required': 'TORRENT_METADATA_INVALID',
    'Incomplete torrent subtitle': 'TORRENT_SUBTITLE_INCOMPLETE',
}
_STOP_REASONS = frozenset({
    'TORRENT_SUBTITLE_CANCELLED_OR_TIMEOUT', 'NO_EXACT_TORRENT_CHINESE_SIDECAR',
    'CANCELLED_OR_DEADLINE', 'SUBTITLE_IO_DEADLINE', 'SUBTITLE_IO_REAP_FAILED',
    'SUBTITLE_IO_BUSY', 'SUBTITLE_IO_PYTHON_UNAVAILABLE', 'SUBTITLE_IO_LIFETIME_FAILED',
    'SUBTITLE_IO_FAILED', 'TORRENT_SUBTITLE_HTTP', 'SUBTITLE_CACHE_CAPACITY',
    'SUBTITLE_ACCOUNT_CHANGED',
    'ASSRT_QUOTA_STATE_INVALID', 'ASSRT_RATE_LIMIT', 'ASSRT_TOKEN_NOT_CONFIGURED',
    'ASSRT_RESPONSE_INVALID', 'MATCHED_SUBTITLE_UNAVAILABLE', 'NO_MATCHED_CHINESE_TEXT',
# Preserve any bounded HTTP error status, including nonstandard provider/CDN
# responses. This records evidence only; it does not widen candidate retries.
} | {'ASSRT_HTTP_' + str(code) for code in range(400, 600)})


class LookupStopped(RuntimeError):
    pass


def public_failure_reason(error):
    """Finite local reason vocabulary, shared by remote and same-torrent probes."""
    if isinstance(error, (ValueError, LookupStopped)):
        message = str(error)
        if message in _VALUE_REASONS:
            return _VALUE_REASONS[message]
        if isinstance(error, LookupStopped) and message in _STOP_REASONS:
            return message
    return type(error).__name__


def normalized(text):
    return ' '.join(re.findall(r'[^\W_]+', str(text).casefold(), re.UNICODE))


def identity(context):
    if not isinstance(context, dict):
        raise ValueError('Subtitle context required')
    title = context.get('title')
    if not isinstance(title, str) or not 2 <= len(title) <= 256 or '://' in title:
        raise ValueError('Bounded title required')
    mode = context.get('mode')
    if mode == 'movie':
        if type(context.get('year')) is not int or not 1888 <= context['year'] <= 2100:
            raise ValueError('Movie year required')
    elif mode == 'series':
        if (type(context.get('season')) is not int or not 0 <= context['season'] <= 999
                or type(context.get('episode')) is not int or not 1 <= context['episode'] <= 10000):
            raise ValueError('Exact episode required')
    else:
        raise ValueError('Explicit media type required')
    media = {k: context.get(k) for k in ('mode', 'title', 'year', 'season', 'episode', 'imdb', 'tmdb')}
    return hashlib.sha256(json.dumps(media, sort_keys=True).encode()).hexdigest()


def episode_tags(text):
    from bobbi_core.filename_semantics import parse_filename
    return parse_filename(text).episode_pairs()


def rank(row, context, allow_season_pack=False, allow_incomplete=False):
    """Identity/edition first, bilingual second; labels are not sync evidence."""
    parts = [str(row.get(k) or '') for k in ('native_name', 'title', 'videoname', 'filename')]
    text = ' '.join(parts)
    if any(len(part) > 4096 for part in parts) or len(text) > 8192 or EXCLUDE.search(text):
        return None
    words = normalized(text)
    wanted = normalized(context['title'])
    if not re.search(r'(?:^| )' + re.escape(wanted) + r'(?: |$)', words):
        return None
    if context['mode'] == 'movie':
        from bobbi_core.movie_identity import declared_years
        from bobbi_core.movie_years import accepted_years
        # The same bounded title-aware parser guards movie files and subtitles.
        # Inspect each metadata field separately: title digits are not release
        # years, while an additional explicit conflicting year still rejects.
        years = set().union(*(declared_years(part, [context['title']]) for part in parts))
        allowed = set(accepted_years(context.get('_movie_years'), context.get('tmdb'), context['year']))
        if (not years or not years <= allowed) and not (allow_incomplete and not years):
            return None
    else:
        from bobbi_core.subtitle_episode import matches as subtitle_episode_matches, declarations
        episodes = episode_tags(text)
        seasons = set().union(*(declarations(part, context['title']) for part in parts))
        if seasons and seasons != {context['season']}:
            return None
        if episodes and episodes != {(context['season'], context['episode'])}:
            return None
        filename = row.get('filename')
        file_matches = bool(filename and subtitle_episode_matches(str(filename), context, seasons))
        if not episodes and not (file_matches or (allow_season_pack and seasons == {context['season']})
                                 or (allow_incomplete and not seasons)):
            return None
        # Every downloaded file must name this episode itself. A package title
        # may authorize inspection, never a differently numbered file.
        if filename and not file_matches:
            return None
    release = str(context.get('release') or '')[:1024]
    edition = {normalized(m.group()) for m in EDITION.finditer(text)}
    target_edition = {normalized(m.group()) for m in EDITION.finditer(release)}
    if edition != target_edition:
        return None
    language = row.get('lang') or {}
    flags = language.get('langlist', {}) if isinstance(language, dict) else {}
    if not isinstance(flags, dict):
        return None
    desc = str(language.get('desc', '')) if isinstance(language, dict) else str(language)
    bilingual = bool(flags.get('langdou') or re.search(r'(?i)双语|雙語|中英|bilingual|chs.?eng|eng.?chs', text + desc))
    chinese = bilingual or flags.get('langchs') or flags.get('langcht') or re.search(r'(?i)中文|简|繁|\bchs\b|\bcht\b', desc + text)
    # Missing search metadata authorizes a bounded DETAIL lookup, not loading.
    # The final file still goes through the original full identity/language gate.
    if not chinese and not (allow_incomplete and not flags and not desc):
        return None
    simplified = bool(flags.get('langchs') or re.search(r'简|\bchs\b', desc + text, re.I))
    exact = bool(release and normalized(release) == normalized(row.get('videoname', '')))
    # Release type is supporting evidence, never sufficient identity.
    medium = re.search(r'(?i)bluray|blu.ray|web.?dl|web.?rip|dvd', release)
    same_medium = bool(medium and normalized(medium.group()) in words)
    return (int(exact), int(bilingual), int(simplified), int(same_medium))


def inspect_text(raw, extension, duration=None):
    from bobbi_core.fonts import subtitle_text
    from bobbi_core.subtitle_cues import parse
    if extension not in TEXT_EXTENSIONS or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('Bounded text subtitle required')
    text = subtitle_text(raw)
    if text.lstrip().startswith('<'):
        raise ValueError('HTML is not a subtitle')
    cues = parse(raw, extension)
    chinese = [c for c in cues if re.search(r'[\u3400-\u9fff]', c['text'])]
    if not chinese:
        raise ValueError('Insufficient full Chinese dialogue')
    # Sparse dialogue, opening credits or a shifted subtitle are not evidence
    # of a wrong work. Explicit forced/signs/commentary labels are excluded by
    # identity ranking; no elapsed-time/coverage threshold decides admission.
    # ASS may put Chinese and English in separate simultaneous Dialogue rows.
    english = sorted((c for c in cues if re.search(r'[A-Za-z]{3,}', c['text'])), key=lambda c: c['start'])
    paired, cursor = 0, 0
    for cue in sorted(chinese, key=lambda c: c['start']):
        while cursor < len(english) and english[cursor]['end'] < cue['start'] - .25:
            cursor += 1
        paired += any(c['start'] <= cue['end'] + .25 and c['end'] >= cue['start'] - .25
                      for c in english[cursor:cursor + 8])
    bilingual = paired >= len(chinese) * .4
    return raw, bilingual  # Preserve ASS/SSA source bytes, styles and encoding.


def candidate_rank(record, context):
    """Rank inspected bytes consistently across cache, local and remote files.

    Preserve actual bilingual dialogue ahead of release preference. A provider's
    bilingual label may guide inspection, but cannot outrank the inspected text.
    """
    score = rank(record['source'], context)
    return (int(record['bilingual']), score[0], score[2], score[3])


def publish(raw, extension, root=ROOT, volume=None):
    """Publish candidate bytes without forging the qualified SubtitleStore."""
    directory = Path(root)
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError('Symlink candidate directory')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.stat()
    volume = volume or directory
    if (info.st_dev != Path(volume).stat().st_dev or (os.name == 'posix' and stat.S_IMODE(info.st_mode) & 0o022)
            or (hasattr(os, 'getuid') and info.st_uid != os.getuid())
            or extension not in TEXT_EXTENSIONS or not 0 < len(raw) <= MAX_BYTES):
        raise ValueError('Private same-volume bounded text cache required')
    digest = hashlib.sha256(raw).hexdigest()
    target = directory / (digest[:32] + extension)
    if not target.exists() and not target.is_symlink():
        # No automatic eviction of subtitles or user files. Stop cache growth.
        total, count = 0, 0
        for item in directory.iterdir():
            if re.fullmatch(r'[a-f0-9]{32}\.(?:srt|ass|ssa|vtt)', item.name):
                total += item.lstat().st_size
                count += 1
                if count >= 2048 or total + len(raw) > 256 * 1024 * 1024:
                    raise LookupStopped('SUBTITLE_CACHE_CAPACITY')
        fd, temporary = tempfile.mkstemp(prefix='.candidate283-', dir=str(directory))
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o444)
            try:
                if os.name == 'nt':
                    # Windows cannot unlink a read-only hardlink. rename does
                    # not replace an existing target on Windows and preserves
                    # the immutable attribute without a writable target gap.
                    os.rename(temporary, target)
                else:
                    os.link(temporary, target)
            except FileExistsError:
                pass
        finally:
            if os.path.exists(temporary):
                if os.name == 'nt':
                    os.chmod(temporary, 0o600)
                os.unlink(temporary)
    info = target.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size != len(raw) or info.st_mode & 0o222
            or info.st_dev != directory.stat().st_dev
            or (hasattr(os, 'getuid') and info.st_uid != os.getuid())):
        raise ValueError('Immutable candidate file required')
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError('Candidate bytes changed')
    return dict(path=str(target), sha256=digest, bytes=len(raw))


class AssrtCandidates:
    def __init__(self, session, state, token_file=TOKEN_FILE, clock=time.monotonic, wall=time.time, transport=None,
                 accounts=None, preparation_root=PREPARATION_ROOT):
        self.session, self.directory = session, Path(state)
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.token_file, self.clock, self.wall = Path(token_file), clock, wall
        self.events = []
        self.transport = transport
        self.accounts, self.preparation_root, self.local_scope = accounts, preparation_root, None
        if accounts is not None:
            try:
                from bobbi_platform.account_manager import validate_snapshot
                self.local_scope = validate_snapshot(accounts.snapshot(), authenticated=True)
            except (ImportError, ValueError, RuntimeError, OSError):
                pass  # Optional prepared cache; public Assrt does not need 115.

    def local_current(self):
        try:
            return (self.local_scope is not None and self.accounts is not None
                    and self.accounts.is_current(self.local_scope) is True)
        except (ValueError, RuntimeError, OSError):
            return False

    def candidate_current(self, record):
        # Old unscoped local-cache receipts cannot prove which account/epoch
        # authorized their ledger. Public Assrt text is independent of 115.
        if str(record.get('origin', '')).startswith('local:'):
            return self.local_current() and record.get('account_scope') == self.local_scope
        return True

    def selected_candidate(self, record):
        if not self.candidate_current(record):
            raise LookupStopped('SUBTITLE_ACCOUNT_CHANGED')
        return record

    def note(self, stage, reason, ident=None):
        """Small public diagnostic vocabulary; never retain provider URLs/text."""
        if stage not in ('search', 'detail', 'download', 'inspect'):
            return
        if not re.fullmatch(r'[A-Za-z0-9_]{1,80}', str(reason)):
            reason = 'INVALID_CANDIDATE'
        self.events.append(dict(stage=stage, reason=reason,
                                candidate=str(ident) if re.fullmatch(r'\d{1,12}', str(ident)) else None))
        self.events = self.events[-12:]

    def candidate_failure(self, stage, error, ident, deadline, cancelled):
        """One missing/broken candidate must not hide the following candidates."""
        self.guard(deadline, cancelled)
        reason = str(error) if isinstance(error, LookupStopped) else type(error).__name__
        self.note(stage, public_failure_reason(error), ident)
        retryable = {'ASSRT_HTTP_404', 'ASSRT_HTTP_410', 'ASSRT_HTTP_500',
                     'ASSRT_HTTP_502', 'ASSRT_HTTP_503', 'ASSRT_HTTP_504'}
        if stage == 'download':
            retryable.add('ASSRT_HTTP_403')  # Expired individual file, not API auth.
        if stage == 'detail':
            retryable.add('ASSRT_RESPONSE_INVALID')
        if isinstance(error, LookupStopped) and reason not in retryable:
            raise error  # Auth, quota, cancellation/deadline are never retried.

    def guard(self, deadline, cancelled):
        if cancelled() or self.clock() >= deadline:
            raise LookupStopped('CANCELLED_OR_DEADLINE')

    def load(self, name, default):
        p = self.directory / name
        try:
            if p.is_symlink() or p.stat().st_size > 1024 * 1024:
                return default
            return json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return default

    def save(self, name, value):
        fd, temporary = tempfile.mkstemp(prefix='.subtitle283-', dir=str(self.directory))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(value, stream, ensure_ascii=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def quota(self):
        now = self.wall()
        old = self.load('quota.json', [])
        if not isinstance(old, list):
            raise LookupStopped('ASSRT_QUOTA_STATE_INVALID')
        recent = [v for v in old if type(v) in (int, float) and now - 60 < v <= now]
        if len(recent) >= 20:
            raise LookupStopped('ASSRT_RATE_LIMIT')
        self.save('quota.json', recent + [now])

    def read(self, url, deadline, cancelled, headers=None, limit=MAX_BYTES):
        from bobbi_core.subtitle_io import read_http, SubtitleIOStopped
        self.guard(deadline, cancelled)
        try:
            raw = (self.transport or read_http)(url, deadline, cancelled, limit,
                headers=headers, mode='assrt', clock=self.clock)
        except SubtitleIOStopped as error:
            reason = str(error)
            # A damaged/oversized/unreachable individual file is a failed
            # candidate, not cancellation of the complete search. Keep auth,
            # quota and supervisor lifetime failures on the stop path.
            terminal = {'CANCELLED_OR_DEADLINE', 'SUBTITLE_IO_DEADLINE',
                        'SUBTITLE_IO_REAP_FAILED', 'SUBTITLE_IO_BUSY',
                        'SUBTITLE_IO_PYTHON_UNAVAILABLE', 'SUBTITLE_IO_LIFETIME_FAILED'}
            if reason in terminal or reason.startswith('ASSRT_HTTP_'):
                raise LookupStopped(reason) from error
            raise ValueError(reason) from error
        self.guard(deadline, cancelled)
        return raw

    def improvement_deadline(self, deadline):
        """Leave commit/cleanup room without ever extending the result budget."""
        return deadline - min(1.0, max(.15, (deadline - self.clock()) * .1))

    def api(self, operation, params, deadline, cancelled):
        self.guard(deadline, cancelled)
        token = self.token_file.read_text().strip()
        if not re.fullmatch(r'[A-Za-z0-9]{32}', token):
            raise LookupStopped('ASSRT_TOKEN_NOT_CONFIGURED')
        self.quota()
        data = json.loads(self.read('https://api.assrt.net/v1/sub/' + operation + '?' + urlencode(params),
                                   deadline, cancelled, {'Authorization': 'Bearer ' + token}, 1024 * 1024))
        if not isinstance(data, dict):
            raise ValueError('Invalid subtitle response')
        if data.get('status') != 0:
            code = data.get('status')
            raise LookupStopped('ASSRT_API_' + (str(code) if type(code) is int else 'INVALID_STATUS'))
        sub = data.get('sub')
        if not isinstance(sub, dict):
            raise LookupStopped('ASSRT_RESPONSE_INVALID')
        rows = sub.get('subs', [])
        # ASSRT's successful empty-search response uses {}, not []. Keep other
        # malformed response shapes as errors; an empty result is not a failure.
        if operation == 'search' and rows == {}:
            return []
        if not isinstance(rows, list) or len(rows) > 100:
            raise LookupStopped('ASSRT_RESPONSE_INVALID')
        return rows

    def local_candidates(self, context, deadline, cancelled, root):
        """Read already stored same-work subtitles, not videos or cloud tasks.

        Other releases remain uncalibrated candidates, irrespective of their
        old release's timing/readiness. Never instantiate the ledger writer.
        """
        from bobbi_core.subtitle_language import CHINESE_CODES
        ident = context.get('tmdb')
        if type(ident) is not int or ident <= 0:
            return []
        media = 'tmdb:movie:' + str(ident) if context['mode'] == 'movie' else 'tmdb:tv:{}:s{}:e{}'.format(
            ident, context['season'], context['episode'])
        if not self.local_current():
            return []
        directory = Path(self.preparation_root) / (self.local_scope['account_id'][4:] + '-' + str(self.local_scope['epoch']))
        # No recursive search, previous-epoch fallback or implicit legacy root.
        database = directory / 'resources.sqlite'
        if not database.is_file() or any(p.is_symlink() for p in (database, *database.parents)):
            return []
        choices, consumed = [], 0
        try:
            connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=.1)
        except sqlite3.Error:
            return []
        try:
            connection.execute('PRAGMA query_only=ON')
            connection.set_progress_handler(lambda: int(cancelled() or self.clock() >= deadline), 1000)
            rows = connection.execute("SELECT r.payload FROM subtitle_current c JOIN subtitle_revisions r "
                "ON r.seq=c.revision WHERE json_extract(r.payload,'$.video.media_id')=? ORDER BY r.seq DESC LIMIT 32", (media,))
            for (payload,) in rows:
                self.guard(deadline, cancelled)
                if not self.local_current():
                    return []
                try:
                    record = json.loads(payload)
                    video = record['video']
                    if (record.get('forced') is not False or record.get('full_dialogue') is not True
                            or record.get('language') not in CHINESE_CODES or video.get('media_id') != media):
                        continue
                    source = dict(native_name=video['selected']['torrent_path'],
                                  videoname=video['selected']['torrent_path'], lang={'desc': '中文'})
                    if rank(source, context) is None:
                        continue
                    digest, extension = record['subtitle_sha256'], record['extension']
                    if not re.fullmatch('[a-f0-9]{64}', digest) or extension not in TEXT_EXTENSIONS:
                        continue
                    path = directory / 'subtitles/objects' / (digest + extension)
                    size = path.lstat().st_size
                    consumed += size
                    if consumed > 16 * 1024 * 1024:
                        break
                    if not 0 < size <= MAX_BYTES or any(p.is_symlink() for p in (path, *path.parents)):
                        continue
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != digest:
                        continue
                    raw, bilingual = inspect_text(raw, extension, context['duration'])
                    self.guard(deadline, cancelled)
                    if not self.local_current():
                        return []
                    choices.append(dict(media=identity(context), source=source, state='candidate',
                        file=publish(raw, extension, root), bilingual=bilingual, origin='local:' + digest[:16],
                        account_scope=dict(self.local_scope)))
                except (OSError, KeyError, TypeError, ValueError):
                    continue
        except sqlite3.Error:
            pass  # Optional old cache schema cannot affect video or API search.
        finally:
            connection.close()
        return choices if self.local_current() else []

    def candidates(self, context, deadline, cancelled, root=ROOT):
        self.guard(deadline, cancelled)
        key = identity(context)
        # Reuse subtitles from previous readable releases of this exact work.
        catalog = self.load('candidates.json', [])
        if not isinstance(catalog, list):
            catalog = []
        catalog = catalog[-128:]
        cached = []
        for record in catalog:
            self.guard(deadline, cancelled)
            if not isinstance(record, dict):
                continue
            if not self.candidate_current(record):
                continue
            if record.get('media') != key or rank(record.get('source', {}), context) is None:
                continue
            try:
                p = Path(record['file']['path'])
                if p.parent != Path(root) or p.is_symlink() or p.stat().st_size > MAX_BYTES:
                    continue
                raw, bilingual = inspect_text(p.read_bytes(), p.suffix, context['duration'])
                if hashlib.sha256(raw).hexdigest() != record['file']['sha256']:
                    continue
                cached.append(dict(record, bilingual=bilingual, state='candidate'))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        try:
            local = self.local_candidates(context, self.improvement_deadline(deadline) if cached else deadline,
                                          cancelled, root)
        except (OSError, ValueError, sqlite3.Error, LookupStopped):
            self.guard(deadline, cancelled)
            local = []  # Optional local state never prevents public API search.
        additions = [record for record in local if record not in catalog]
        if additions:
            catalog = (catalog + additions)[-128:]
            self.save('candidates.json', catalog)
        choices = cached + local
        self.guard(deadline, cancelled)
        if choices:
            best = max(choices, key=lambda record: candidate_rank(record, context))
            # Exact, actually bilingual text needs no forced network refresh.
            # Other releases remain usable while an optional improvement fits.
            if candidate_rank(best, context)[:2] == (1, 1) or deadline - self.clock() < 7:
                return self.selected_candidate(best)
        try:
            candidate = self.remote_candidates(context, self.improvement_deadline(deadline) if choices else deadline,
                                               cancelled, root, key, catalog, choices)
            self.guard(deadline, cancelled)
            return self.selected_candidate(candidate)
        except (OSError, ValueError, LookupStopped):
            self.guard(deadline, cancelled)
            if choices:
                return self.selected_candidate(max(choices, key=lambda record: candidate_rank(record, context)))
            raise

    def search(self, query, deadline, cancelled):
        self.guard(deadline, cancelled)
        search_key = hashlib.sha256(query.encode()).hexdigest()
        search_file = 'search-' + search_key + '.json'
        saved = self.load(search_file, {})
        if (isinstance(saved, dict) and type(saved.get('time')) in (int, float)
                and 0 <= self.wall() - saved['time'] < 86400 and isinstance(saved.get('rows'), list)):
            rows = saved.get('rows', [])
        else:
            rows = self.api('search', {'q': query, 'cnt': 15, 'filelist': 1}, deadline, cancelled)
            # Search metadata contains no authentication token or download URL.
            clean = [{k: row.get(k) for k in ('id', 'native_name', 'videoname', 'lang', 'subtype')} for row in rows if isinstance(row, dict)]
            if len(list(self.directory.glob('search-*.json'))) < 128 or (self.directory / search_file).exists():
                self.save(search_file, dict(time=self.wall(), rows=clean))
        return rows

    def remote_candidates(self, context, deadline, cancelled, root, key, catalog, local):
        if context['mode'] == 'movie':
            from bobbi_core.movie_years import accepted_years
            years = accepted_years(context.get('_movie_years'), context.get('tmdb'), context['year'])
            queries = [context['title'] + ' ' + str(year) for year in
                       dict.fromkeys((context['year'],) + tuple(years))]
        else:
            queries = [context['title'] + ' S{:02}E{:02}'.format(context['season'], context['episode']),
                       context['title'] + ' S{:02}'.format(context['season']), context['title']]
        rows = []
        seen = set()
        for query in queries:
            try:
                found = self.search(query, deadline, cancelled)
            except (OSError, ValueError, LookupStopped) as error:
                self.note('search', str(error) if isinstance(error, LookupStopped) else type(error).__name__)
                raise
            for row in found:
                if isinstance(row, dict) and str(row.get('id')).isdigit() and str(row['id']) not in seen:
                    rows.append(row)
                    seen.add(str(row['id']))
            # Broaden only when the more precise query has no qualified entry.
            if any(rank(row, context, allow_season_pack=True) is not None for row in rows):
                break
        ranked = [(rank(row, context, allow_season_pack=True, allow_incomplete=True), row) for row in rows
                  if str(row.get('subtype', '')).casefold() not in ('vobsub', 'pgs', 'sup')]
        ranked = sorted((item for item in ranked if item[0] is not None), key=lambda item: item[0], reverse=True)
        # Share inspected additions with the caller: a later optional timeout
        # must not discard the first valid cold-cache download either.
        choices, additions = local, []
        for _, row in ranked[:6]:
            self.guard(deadline, cancelled)
            # Keep a validated fallback instead of spending its last seconds on
            # an optional improvement. IO remains within the worker's 30s cap.
            if choices and deadline - self.clock() < 7:
                break
            ident = row.get('id')
            if not str(ident).isdigit():
                continue
            try:
                details = self.api('detail', {'id': ident}, deadline, cancelled)
            except (OSError, ValueError, LookupStopped) as error:
                self.candidate_failure('detail', error, ident, deadline, cancelled)
                continue
            for detail in details[:1]:
                if not isinstance(detail, dict):
                    continue
                source = dict(row, **{k: v for k, v in detail.items() if k in ('native_name', 'title', 'videoname', 'lang')})
                if rank(source, context, allow_season_pack=True, allow_incomplete=True) is None:
                    continue
                files = detail.get('filelist')
                # The provider also returns an exact empty object for a single
                # top-level text file. Nonempty objects remain malformed.
                if files is None or (type(files) is dict and not files):
                    files = []
                if not isinstance(files, list) or len(files) > 512:
                    self.note('detail', 'ASSRT_FILELIST_INVALID', ident)
                    continue
                # Assrt single-file details may leave filelist empty and expose
                # filename/url at the top level. Feed that documented shape
                # through exactly the same text, identity, URL and body gates.
                if not files:
                    filename, target = detail.get('filename'), detail.get('url')
                    if (isinstance(filename, str) and 0 < len(filename) <= 4096
                            and isinstance(target, str) and 0 < len(target) <= 8192):
                        files = [dict(f=filename, url=target)]
                files = [f for f in files if isinstance(f, dict) and Path(str(f.get('f', ''))).suffix.casefold() in TEXT_EXTENSIONS
                         and not EXCLUDE.search(str(f.get('f', '')))]
                # Filter the entire bounded package before choosing the first
                # two alternatives; S03E03 need not be in the first two entries.
                files = [f for f in files if rank(dict(source, filename=str(f['f'])), context) is not None]
                files.sort(key=lambda f: rank(dict(source, filename=str(f['f'])), context), reverse=True)
                for f in files[:2]:
                    self.guard(deadline, cancelled)
                    if choices and deadline - self.clock() < 7:
                        break
                    # Package labels cannot authorize a different year's or
                    # episode's file contained in that package.
                    file_source = dict(source, filename=str(f['f']))
                    if rank(file_source, context) is None:
                        continue
                    target = str(f.get('url', ''))
                    if target.startswith('http://'):
                        target = 'https://' + target[7:]
                    try:
                        extension = Path(f['f']).suffix.casefold()
                        raw = self.read(target, deadline, cancelled)
                    except (ValueError, OSError, LookupStopped) as error:
                        self.candidate_failure('download', error, ident, deadline, cancelled)
                        continue
                    try:
                        raw, bilingual = inspect_text(raw, extension, context['duration'])
                    except (ValueError, OSError, LookupError) as error:
                        self.candidate_failure('inspect', error, ident, deadline, cancelled)
                        continue
                    self.guard(deadline, cancelled)
                    file = publish(raw, extension, root)
                    record = dict(media=key, source={k: file_source.get(k) for k in ('native_name', 'title', 'videoname', 'filename', 'lang')},
                                  file=file, bilingual=bilingual, origin='assrt:' + str(ident), state='candidate')
                    if not choices:
                        deadline = self.improvement_deadline(deadline)
                    choices.append(record)
                    if record not in catalog and record not in additions:
                        additions.append(record)
                    best = max(choices, key=lambda r: candidate_rank(r, context))
                    if candidate_rank(best, context)[:3] == (1, 1, 1):
                        if additions:
                            self.save('candidates.json', (catalog + additions)[-128:])
                        return best
        if choices:
            if additions:
                self.save('candidates.json', (catalog + additions)[-128:])
            return max(choices, key=lambda r: candidate_rank(r, context))
        raise LookupStopped('MATCHED_SUBTITLE_UNAVAILABLE' if self.events else 'NO_MATCHED_CHINESE_TEXT')

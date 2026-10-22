"""Indexed public provenance, bounded share reads, and stable selection records."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from .api import Client, ShareError
from .identity import matches, normalized, queries, terms
from .routing import eligible_text, route_order

CATALOG = Path(__file__).resolve().parents[2] / 'resources' / 'catalog.sqlite3'
from bobbi_platform.paths import profile
CACHE = profile('script.module.bobbi.catalog', 'cache.sqlite3')
SITE = '115 资源目录'
CELL_PATTERN = r'(?:[A-Z]{1,2}[1-9]\d*|supp-[0-9a-f]{24})'


def guard(deadline=None, cancelled=None):
    if cancelled is not None and cancelled.is_set():
        raise ShareError('cancelled')
    if deadline is not None and time.monotonic() >= deadline:
        raise ShareError('deadline')


def bounded_sql(conn, deadline=None, cancelled=None):
    """Interrupt VM scans; SQLite fsync/OS calls remain cooperative boundaries."""
    guard(deadline, cancelled)
    if deadline is not None:
        # SQLite's busy-handler sleep accounting can substantially overshoot
        # short budgets on Windows. This optional catalog/cache path fails
        # closed on contention instead of spending the remaining result budget.
        conn.execute('PRAGMA busy_timeout=0')
    def interrupted():
        return int((cancelled is not None and cancelled.is_set()) or
                   (deadline is not None and time.monotonic() >= deadline))
    conn.set_progress_handler(interrupted, 250)


def readonly(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=1)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn


def has_share_status(conn):
    """Legacy snapshots have no availability overlay and remain compatible."""
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='share_status'").fetchone() is not None


class Cache:
    def __init__(self, path=CACHE, deadline=None, cancelled=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        guard(deadline, cancelled)
        self.db = sqlite3.connect(str(path), timeout=1 if deadline is None else 0)
        self.deadline, self.cancelled = deadline, cancelled
        try:
            bounded_sql(self.db, deadline, cancelled)
            self._initialize()
        except BaseException:
            self.db.close()
            raise

    def _initialize(self):
        self.db.execute('CREATE TABLE IF NOT EXISTS searches (key TEXT PRIMARY KEY, expires REAL, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS selections (key TEXT PRIMARY KEY, media TEXT, payload TEXT, seen REAL)')
        # Bounded cache, never any Cookie, account ID or signed URL.
        self.db.execute('DELETE FROM searches WHERE expires < ?', (time.time(),))
        self.db.execute('DELETE FROM selections WHERE seen < ?', (time.time() - 7 * 86400,))
        self.db.execute('DELETE FROM searches WHERE rowid IN (SELECT rowid FROM searches ORDER BY expires DESC LIMIT -1 OFFSET 2048)')
        self.db.execute('DELETE FROM selections WHERE rowid IN (SELECT rowid FROM selections ORDER BY seen DESC LIMIT -1 OFFSET 4096)')
        guard(self.deadline, self.cancelled)
        self.db.commit()

    def get(self, key):
        bounded_sql(self.db, self.deadline, self.cancelled)
        row = self.db.execute('SELECT payload FROM searches WHERE key=? AND expires>?', (key, time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, value, ttl=21600):
        guard(self.deadline, self.cancelled)
        self.db.execute('INSERT OR REPLACE INTO searches VALUES (?,?,?)', (key, time.time()+ttl, json.dumps(value)))
        self.db.commit()

    def persist(self, searches, selections):
        """One bounded transaction; cards are published only after commit.

        A stalled kernel COMMIT cannot be forcibly interrupted by SQLite's VM
        progress callback. Do not describe this as a hard I/O wall-clock bound.
        """
        guard(self.deadline, self.cancelled)
        now = time.time()
        try:
            for key, value, ttl in searches:
                bounded_sql(self.db, self.deadline, self.cancelled)
                self.db.execute('INSERT OR REPLACE INTO searches VALUES (?,?,?)',
                                (key, now+ttl, json.dumps(value)))
            for key, media, row in selections:
                bounded_sql(self.db, self.deadline, self.cancelled)
                self.db.execute('INSERT OR REPLACE INTO selections VALUES (?,?,?,?)',
                                (key + ':' + media, media, json.dumps(row), now))
            guard(self.deadline, self.cancelled)
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def remember(self, key, media, row):
        self.db.execute('INSERT OR REPLACE INTO selections VALUES (?,?,?,?)',
                        (key + ':' + media, media, json.dumps(row), time.time()))
        self.db.commit()

    def selected(self, key, media):
        row = self.db.execute('SELECT payload FROM selections WHERE key=? AND media=?', (key + ':' + media, media)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self):
        self.db.close()


def routes(spec, path=CATALOG, limit=6, deadline=None, cancelled=None):
    """Use indexed text to choose shares, never query every share on navigation."""
    if limit <= 0:
        return []
    guard(deadline, cancelled)
    conn = readonly(path)
    try:
        bounded_sql(conn, deadline, cancelled)
        aliases = [a for a in spec['aliases'][:24] if len(normalized(a)) >= 2]
        years = (spec['year'],)
        if spec.get('mode') == 'movies' and spec.get('_movie_years') is not None:
            from bobbi_core.movie_years import accepted_years
            years = accepted_years(spec.get('_movie_years'), spec.get('tmdb_id'), spec['year']) or years
        found = {}
        for alias in aliases:
            guard(deadline, cancelled)
            tokens = terms(alias)
            alias_norm = normalized(alias)
            if not tokens:
                continue
            counts = []
            for token in tokens:
                guard(deadline, cancelled)
                counts.append((conn.execute('SELECT n FROM term_counts WHERE term=?', (token,)).fetchone(), token))
            counts = [(int(row[0]), token) for row, token in counts if row]
            if not counts:
                continue
            _, token = min(counts)
            for row in conn.execute('SELECT e.* FROM terms t JOIN entries e ON e.id=t.entry_id WHERE t.term=? LIMIT 8000', (token,)):
                guard(deadline, cancelled)
                if not eligible_text(row['text']):
                    continue
                if alias_norm not in row['norm']:
                    continue
                # Routing may use a folder name with no year. The actual file
                # has a stricter year/type/episode gate before becoming a card.
                score = (4 if any(str(year) in row['text'] for year in years) else 0) + (3 if re.search(r'(?i)2160|4k|remux', row['text']) else 0)
                previous = found.get(row['group_key'])
                if previous is None or score > previous['score']:
                    found[row['group_key']] = dict(group=row['group_key'], origin=row['origin'], text=row['text'], score=score)
        result = []
        has_status = has_share_status(conn)
        def rank(item):
            guard(deadline, cancelled)
            return route_order(item, spec)
        for item in sorted(found.values(), key=rank):
            guard(deadline, cancelled)
            query = ('SELECT s.* FROM shares s LEFT JOIN share_status a ON a.cell=s.cell '
                     'WHERE s.group_key=? AND COALESCE(a.enabled,1)=1 ORDER BY s.cell'
                     if has_status else 'SELECT * FROM shares WHERE group_key=? ORDER BY cell')
            shares = []
            for row in conn.execute(query, (item['group'],)):
                guard(deadline, cancelled)
                shares.append(dict(row))
            if shares:
                result.append(dict(item, shares=shares))
                if len(result) >= limit:
                    break
        guard(deadline, cancelled)
        return result
    except sqlite3.OperationalError:
        guard(deadline, cancelled)
        raise
    finally:
        conn.close()


def share_for(cell, path=CATALOG):
    conn = readonly(path)
    try:
        row = conn.execute('SELECT * FROM shares WHERE cell=?', (cell,)).fetchone()
        if row is None:
            raise ShareError('invalid_locator')
        if has_share_status(conn):
            status = conn.execute('SELECT enabled FROM share_status WHERE cell=?', (cell,)).fetchone()
            if status is not None and not status['enabled']:
                raise ShareError('share_unavailable')
        return dict(row)
    finally:
        conn.close()


def fields(row):
    fid, cell = row['fid'], row['cell']
    source_ref = '补充分享 · ' + cell if cell.startswith('supp-') else '汇总!' + cell
    return dict(title=row['name'], type='Direct', indexer=SITE,
                subindexer=row['origin'] + ' / ' + source_ref,
                guid='qqdocs:' + cell + ':' + fid, size=row['size'],
                url='am6bqqdocs://' + cell + '/' + fid)


def search(spec, deadline, cancelled, catalogue=CATALOG, cache_path=CACHE, client=None, diagnostic=None):
    deadline = min(deadline, time.monotonic() + 18)
    # Leave a small submission window so useful matches survive optional work.
    work_deadline = deadline - min(.25, max(0, (deadline-time.monotonic())/4))
    planned, cache = [], None
    result, seen, requests, failures = [], set(), 0, []
    published = 0
    searches, selections = [], []
    try:
        planned = routes(spec, catalogue, deadline=work_deadline, cancelled=cancelled)
        query_values = queries(spec)
        if not planned or not query_values:
            return []
        guard(work_deadline, cancelled)
        api = client or Client()
        from bobbi_core.share_failure import account_scope, card_state, card_tuple
        cache = Cache(cache_path, deadline, cancelled)
        for route in planned:
            group_matched = False
            for share in route['shares'][:3]:
                for query in query_values:
                    if time.monotonic() >= work_deadline or requests >= 8:
                        break
                    guard(work_deadline, cancelled)
                    key = hashlib.sha256((share['code'] + ':' + share['password'] + ':' + query).encode()).hexdigest()
                    cached = cache.get(key)
                    if cached is None:
                        requests += 1
                        try:
                            rows = api.search(share, query, work_deadline, cancelled)
                            guard(work_deadline, cancelled)
                            cached = dict(rows=rows)
                            searches.append((key, cached, 21600 if rows else 600))
                        except ShareError as error:
                            failures.append(error.code)
                            if error.code in ('login_required', 'cancelled', 'deadline'):
                                if error.code == 'login_required' and not result:
                                    raise
                                if error.code == 'cancelled':
                                    return []
                                if error.code == 'login_required':
                                    work_deadline = time.monotonic()
                                break
                            if error.code == 'share_unavailable':
                                searches.append((key, {'rows': [], 'failure': error.code}, 900))
                            break
                    for row in cached.get('rows', []):
                        if time.monotonic() >= work_deadline or len(result) >= 16:
                            break
                        guard(work_deadline, cancelled)
                        if not matches(row['name'], spec):
                            continue
                        group_matched = True
                        # Mirrors of an identical filename/size are redundant.
                        unique = (row['name'].casefold(), row['size'])
                        if unique in seen:
                            continue
                        seen.add(unique)
                        item = dict(row, cell=share['cell'], origin=route['origin'])
                        entry = fields(item)
                        selections.append((entry['guid'], spec['media_key'], item))
                        result.append(entry)
                    if group_matched or len(result) >= 16:
                        break
                if group_matched or len(result) >= 16:
                    break
            if len(result) >= 16:
                break
        guard(deadline, cancelled)
        cache.persist(searches, selections)
        # Resolve display scope at publication, not before slow network IO.
        scope = account_scope(include_signed_out=True)
        for entry in result:
            state = card_state(cache.db, card_tuple(entry, spec['media_key']), scope)
            if state:
                entry.update(shareState=state, shareFailure=state['code'])
        guard(deadline, cancelled)
        published = len(result)
        return result
    except ShareError as error:
        if error.code not in ('deadline', 'cancelled'):
            raise
        failures.append(error.code)
        return []
    except sqlite3.OperationalError:
        # Busy disks or interrupted scans are a miss, never unresolvable cards.
        failures.append('cache_unavailable')
        return []
    finally:
        if cache is not None:
            cache.close()
        if diagnostic:
            diagnostic(dict(routes=len(planned), requests=requests, results=published, failures=sorted(set(failures))))


def selected(locator, guid, title, size, media, catalogue=CATALOG, cache_path=CACHE):
    match = re.fullmatch(r'am6bqqdocs://(' + CELL_PATTERN + r')/(\d{1,32})', locator or '')
    if not match or guid != 'qqdocs:' + match[1] + ':' + match[2]:
        raise ShareError('invalid_locator')
    cache = Cache(cache_path)
    try:
        row = cache.selected(guid, media)
    finally:
        cache.close()
    if not row:
        raise ShareError('refresh_required')
    if row['name'] != title or row['size'] != size or row['fid'] != match[2] or row['cell'] != match[1]:
        raise ShareError('identity_changed')
    return share_for(match[1], catalogue), row


def resolve(locator, guid, title, size, media, catalogue=CATALOG, cache_path=CACHE, client=None):
    from bobbi_core.share_failure import account_scope, record_result, PERMANENT
    api = client or Client()
    scope, started = account_scope(api), time.time()
    identity = dict(locator=locator, guid=guid, title=title, size=size, media=media)
    def remember(code):
        cache = None
        try:
            cache = Cache(cache_path, time.monotonic()+.2)
            record_result(cache.db, identity, scope, started, code)
        except (OSError, sqlite3.Error):
            pass  # Metadata writes must never mask the typed playback result.
        except ShareError as error:
            # Only Cache's own optional budget is disposable. Remote errors
            # and playback ownership checks live outside this local boundary.
            if error.code != 'deadline':
                raise
        finally:
            if cache is not None:
                cache.close()
    try:
        share, row = selected(locator, guid, title, size, media, catalogue, cache_path)
        result = api.resolve(share, row, time.monotonic() + 8)
    except ShareError as error:
        if error.code in PERMANENT:
            remember(error.code)
        raise
    remember('')
    return result

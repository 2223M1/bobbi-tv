"""Idle-only Juku refresh: page discovery, download, staged import, atomic publish.

Each call has the caller's absolute deadline and cancellation. There is one
bounded incoming snapshot, not a second active catalogue or a download queue.
An HTTP failure restarts its download later; completed downloads resume only
local record validation. Old successes survive transient failures and age.
"""
import json
import re
import sqlite3
import time

from bobbi_core import juku_api
from bobbi_core.juku_snapshot import SnapshotReader

PAGE_SIZE = 100
MAX_PAGES = 10
IMPORT_BATCH = 256
BACKOFF = 600
MAX_JOB_AGE = 3600
MAX_STAGED_ROWS = 32 * 1024 * 1024


def _read(cache, key):
    row = cache.db.execute('SELECT value FROM maintenance WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def _write(cache, key, value):
    cache.db.execute('INSERT OR REPLACE INTO maintenance VALUES(?,?)',
                     (key, json.dumps(value, separators=(',', ':'), allow_nan=False)))


def _revoke(cache, code, reason):
    cache.db.execute('INSERT OR REPLACE INTO library_visibility VALUES(?,1,?)', (code, reason))


def _drop_job(cache, path):
    with cache.db:
        cache.db.execute("DELETE FROM maintenance WHERE key='snapshot-job'")
        cache.db.execute('DELETE FROM snapshot_rows')
    if path.exists():
        path.unlink()  # Only the fixed, owned incoming file, never a media path.


def _page(cache, client, deadline, cancelled, cat):
    now = time.time()
    state = _read(cache, 'directory-scan') or dict(page=1, items=[], seen=[], started=now)
    if now - state['started'] > MAX_JOB_AGE:
        state = dict(page=1, items=[], seen=[], started=now)
    page = state['page']
    result = client.get('/shared-libraries/public', dict(page=page, pageSize=PAGE_SIZE), deadline)
    cat._guard(deadline, cancelled)
    if (not isinstance(result, dict) or not isinstance(result.get('items'), list)
            or len(result['items']) > PAGE_SIZE):
        raise ValueError('Public catalogue page shape')
    items = result['items']
    codes, selected = [], []
    for item in items:
        if (not isinstance(item, dict) or not re.fullmatch('[A-Za-z0-9_-]{1,64}', str(item.get('shareCode', '')))
                or type(item.get('version')) not in (str, int)
                or not 1 <= len(str(item['version'])) <= 128
                or ('isPublic' in item and type(item['isPublic']) is not bool)):
            raise ValueError('Public catalogue entry shape')
        codes.append(item['shareCode'])
        selected.append(dict(shareCode=item['shareCode'], version=str(item['version']),
                             isPublic=item.get('isPublic', True)))
    if len(set(codes)) != len(codes) or set(codes).intersection(state['seen']):
        raise ValueError('Public catalogue repeated page')
    state['items'].extend(selected)
    state['seen'].extend(codes)
    pagination = result.get('pagination') or {}
    total = pagination.get('total') if isinstance(pagination, dict) else None
    if total is not None:
        total = cat._number(total)
        if total < len(state['items']) or (not items and total > len(state['items'])):
            raise ValueError('Incomplete public catalogue page')
        if 'total' in state and total != state['total']:
            raise ValueError('Public catalogue changed during pagination')
        state['total'] = total
    more = (len(state['items']) < total) if total is not None else len(items) == PAGE_SIZE
    truncated = more and page >= MAX_PAGES
    with cache.db:
        # An explicit visibility withdrawal is authoritative even in a bounded
        # partial listing. Merely missing from such a listing is NOT removal.
        for item in items:
            if item.get('isPublic') is False:
                _revoke(cache, item['shareCode'], 'UPSTREAM_PRIVATE')
        if more and not truncated:
            state['page'] += 1
            _write(cache, 'directory-scan', state)
        else:
            _write(cache, 'directory', dict(items=state['items'], at=now, truncated=bool(truncated)))
            cache.db.execute("DELETE FROM maintenance WHERE key='directory-scan'")
            if not truncated:
                for row in cache.db.execute('SELECT code FROM libraries').fetchall():
                    if row[0] not in state['seen']:
                        _revoke(cache, row[0], 'UPSTREAM_REMOVED')
    return dict(state='DIRECTORY_PROGRESS' if more and not truncated else 'DIRECTORY_READY',
                libraries=len(state['items']), page=page, truncated=bool(truncated))


def _stage_row(cache, row, cat):
    previous = cache.db.execute('SELECT payload,conflict FROM snapshot_rows WHERE key=?', (row['key'],)).fetchone()
    if previous:
        if previous['conflict']:
            return
        merged = cat._unique([json.loads(previous['payload']), row])
        if not merged:
            cache.db.execute('UPDATE snapshot_rows SET conflict=1 WHERE key=?', (row['key'],))
            return
        row = merged[0]
    cache.db.execute('INSERT OR REPLACE INTO snapshot_rows VALUES(?,?,?,?,?,?,0)',
        (row['key'], row['tmdb'], row['kind'], row['season'], row['episode'], cat._encode(row)))


def _import(cache, job, path, deadline, cancelled, cat):
    stat = path.stat()
    if [stat.st_size, stat.st_mtime_ns] != job['file_identity']:
        raise ValueError('Staged snapshot changed')
    guard = lambda: cat._guard(deadline, cancelled)
    with path.open('rb') as source, cache.db:
        reader = SnapshotReader(source, job.get('cursor'), guard)
        for _ in range(IMPORT_BATCH):
            movie = reader.next_movie()
            if movie is None:
                break
            if reader.state['count'] > cat.MAX_MOVIES or not isinstance(movie.get('links'), list):
                raise ValueError('Snapshot movie budget/shape')
            for link in movie['links']:
                guard()
                job['links'] += 1
                if job['links'] > cat.MAX_LINKS or not isinstance(link, dict):
                    raise ValueError('Snapshot link budget/shape')
                if cat._directory_reference(link):
                    job['unsupported_directory'] += 1
                    continue
                try:
                    kind = cat._kind(movie.get('typeId'))
                except ValueError:
                    kind = None
                if kind is None:
                    job['rejected'] += 1
                    continue
                try:
                    cat.share_url(link.get('url'), link.get('password', ''))
                except (ValueError, TypeError):
                    job['rejected'] += 1
                    if ('115' in str(link.get('provider', '')) or
                            re.search(r'(?i)(?:^|[./])115(?:cdn)?\.com', str(link.get('url', '')))):
                        job['invalid_115'] += 1
                    continue
                try:
                    row = cat._row(movie, link, 'shared:' + job['code'])
                    if row:
                        _stage_row(cache, row, cat)
                except (ValueError, TypeError, KeyError):
                    job['invalid_115'] += 1
                    job['rejected'] += 1
            guard()
        job['cursor'] = reader.state
        if cache.db.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM snapshot_rows').fetchone()[0] > MAX_STAGED_ROWS:
            raise ValueError('Staged catalogue row quota')
        if reader.state['phase'] == 'done':
            library = reader.state['library']
            if (library.get('shareCode') != job['code'] or str(library.get('version')) != job['version']
                    or (library.get('itemCount') is not None and
                        cat._number(library['itemCount']) != reader.state['count'])):
                raise ValueError('Snapshot identity/count mismatch')
            if library.get('isPublic') is False:
                _revoke(cache, job['code'], 'UPSTREAM_PRIVATE')
                job['phase'] = 'REVOKED'
            else:
                job['phase'] = 'VALIDATED'
        _write(cache, 'snapshot-job', job)
    return dict(state=job['phase'], code=job['code'], movies=reader.state['count'])


def _publish(cache, job, path, cat):
    row = cache.db.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM snapshot_rows WHERE conflict=0').fetchone()
    count, size = row
    if job['phase'] == 'REVOKED' or (not count and job['invalid_115']):
        _drop_job(cache, path)
        return dict(state='REVOKED' if job['phase'] == 'REVOKED' else 'UNUSABLE', code=job['code'])
    with cache.db:
        code = job['code']
        cache.db.execute('DELETE FROM shared_rows WHERE library=?', (code,))
        cache.db.execute('DELETE FROM libraries WHERE code=?', (code,))
        cache._room(size, preserve=code)
        cache.db.execute('INSERT INTO shared_rows SELECT ?,key,tmdb,kind,season,episode,payload FROM snapshot_rows WHERE conflict=0', (code,))
        cache.db.execute('INSERT INTO libraries VALUES(?,?,?,?,?)', (code, job['version'], time.time(), count, size))
        cache.db.execute('DELETE FROM library_visibility WHERE code=?', (code,))
        cache.db.execute('DELETE FROM maintenance WHERE key=?', ('attempt:' + code,))
        cache.db.execute("DELETE FROM maintenance WHERE key='snapshot-job'")
        cache.db.execute('DELETE FROM snapshot_rows')
    if path.exists():
        path.unlink()
    return dict(state='UPDATED', code=code, candidates=count,
                **{key: job[key] for key in ('links', 'rejected', 'invalid_115', 'unsupported_directory')})


def refresh(state=None, deadline=None, cancelled=None, client=None):
    from bobbi_core import juku_catalog as cat
    deadline = time.monotonic() + 12 if deadline is None else deadline
    cancelled = cat._cancelled(cancelled)
    root = juku_api.state_path(state)
    client = client or juku_api.Client(state=root, cancelled=cancelled)
    # Separate from the auth lease, so session refresh does not recurse a lock.
    with juku_api.state_lock(root / 'refresh-owner', deadline, cancelled), cat._cache(root, deadline, cancelled) as cache:
        path = root / 'incoming-snapshot.json'
        job = _read(cache, 'snapshot-job')
        if job:
            try:
                if time.time()-job['created'] > MAX_JOB_AGE:
                    raise ValueError('Staged snapshot expired')
                return (_publish(cache, job, path, cat) if job['phase'] in ('VALIDATED', 'REVOKED')
                        else _import(cache, job, path, deadline, cancelled, cat))
            except juku_api.JukuError:
                raise  # Cancellation/deadline preserve the last committed checkpoint.
            except (ValueError, OSError):
                _drop_job(cache, path)
                raise
            except sqlite3.OperationalError as error:
                if (getattr(error, 'sqlite_errorcode', None) == 13
                        or str(error).lower() == 'database or disk is full'):
                    _drop_job(cache, path)
                # Busy/interrupted statements retain committed checkpoints;
                # a permanently oversized stage must not starve other libraries.
                raise
        directory = _read(cache, 'directory')
        if not directory or _read(cache, 'directory-scan') or directory['at'] < time.time()-cat.FRESH:
            last = _read(cache, 'directory-attempt') or 0
            if last > time.time()-30:
                return dict(state='BACKOFF', stage='directory')
            with cache.db:
                _write(cache, 'directory-attempt', time.time())
            result = _page(cache, client, deadline, cancelled, cat)
            with cache.db:
                cache.db.execute("DELETE FROM maintenance WHERE key='directory-attempt'")
            return result
        eligible, deferred = [], False
        for item in directory['items']:
            code = item['shareCode']
            if item.get('isPublic') is False:
                continue
            attempt = _read(cache, 'attempt:' + code) or 0
            if attempt > time.time()-BACKOFF:
                deferred = True
                continue
            old = cache.db.execute('SELECT version,at FROM libraries WHERE code=?', (code,)).fetchone()
            revoked = cache.db.execute('SELECT revoked FROM library_visibility WHERE code=?', (code,)).fetchone()
            if not old or str(item['version']) != old['version'] or old['at'] < time.time()-cat.FRESH or revoked:
                # Least recently attempted first, not a permanently failing
                # alphabetically first library. Successful siblings progress.
                eligible.append((attempt, old['at'] if old else 0, code, item))
        if not eligible:
            return dict(state='BACKOFF' if deferred else 'CURRENT', libraries=len(directory['items']),
                        truncated=directory['truncated'])
        _, _, code, item = min(eligible)
        with cache.db:
            _write(cache, 'attempt:' + code, time.time())
        try:
            transfer = client.get('/shared-libraries/detail/' + code, {}, deadline,
                                  max_bytes=juku_api.MAX_SNAPSHOT_JSON, destination=path)
        except juku_api.JukuError as error:
            if error.code in ('HTTP_403', 'HTTP_404', 'HTTP_410'):
                with cache.db:
                    _revoke(cache, code, error.code)
            raise
        cat._guard(deadline, cancelled)
        stat = path.stat()
        if stat.st_size != transfer['bytes']:
            raise ValueError('Snapshot transfer identity')
        job = dict(code=code, version=str(item['version']), phase='IMPORTING', created=time.time(),
                   file_identity=[stat.st_size, stat.st_mtime_ns], sha256=transfer['sha256'],
                   links=0, rejected=0, invalid_115=0, unsupported_directory=0)
        with cache.db:
            cache.db.execute('DELETE FROM snapshot_rows')
            _write(cache, 'snapshot-job', job)
        return dict(state='FETCHED', code=code, bytes=transfer['bytes'])

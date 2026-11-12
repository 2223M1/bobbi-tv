"""Rebuildable SQL read model; never a file identity or playback authority.

No JSON1/FTS extension is required. Contains searches scan normalized scalar
text, not serialized FileRefs. Only MediaIndex owns writes to these tables.
"""
from collections import OrderedDict
import hashlib
import json
import re
import time
import unicodedata
from uuid import uuid4

DEFAULT_LIMIT = 20
MAX_LIMIT = 32
REPLY_BYTES = 15000
CURSOR_SECONDS = 600
VIEWS = ('works', 'seasons', 'episodes', 'files')
AVAILABILITY = ('observed_present', 'observed_absent', 'source_unavailable', 'unverified')
STATES = ('unmatched', 'ambiguous', 'proposed', 'confirmed', 'ignored')
ROW_SCHEMA = ('id TEXT PRIMARY KEY,provider TEXT NOT NULL,account TEXT NOT NULL,'
    'work_id TEXT NOT NULL,season_id TEXT,episode_id TEXT,title TEXT NOT NULL,'
    'filename TEXT NOT NULL,title_sort TEXT NOT NULL,search_text TEXT NOT NULL,'
    'media_kind TEXT NOT NULL,season INTEGER,episode INTEGER,review_state TEXT NOT NULL,'
    'first_seen REAL,updated REAL NOT NULL,group_key TEXT NOT NULL,namespace TEXT NOT NULL,authority_generation TEXT NOT NULL,'
    'metadata_key TEXT,year INTEGER')


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def normalized(value):
    return unicodedata.normalize('NFKC', value).casefold()


def opaque(*parts):
    return hashlib.sha256(wire(parts)).hexdigest()


def scope_key(value):
    # SQL partition labels are not a fabricated authenticated cloud account.
    # Host checks the corresponding native-account or mounted authority first.
    if value.get('reference_kind') == 'mounted_path':
        return ('mounted_path', value['source_id'], value['namespace'])
    return (value['provider'], value['account_id'], value['epoch'])


def revision_key(value):
    """Persistent local scope; native login epochs remain cursor-only CAS."""
    if value.get('reference_kind') == 'mounted_path':
        return scope_key(value)
    return (value['provider'], value['account_id'], '')


def parameters(value):
    fields = {'view', 'source_id', 'review_state', 'availability', 'media_kind',
              'text', 'parent_entity_id', 'sort'}
    if type(value) is not dict or set(value) - fields:
        raise ValueError('CATALOG_QUERY_INVALID')
    result = dict(view='works', source_id=None, review_state=None, availability=None,
                  media_kind=None, text='', parent_entity_id=None, sort='name')
    result.update(value)
    for key, values in (('view', VIEWS), ('review_state', (None,) + STATES),
            ('availability', (None,) + AVAILABILITY), ('media_kind', (None, 'movie', 'tv', 'unknown')),
            ('sort', ('name', 'recent_added', 'recent_edited'))):
        if result[key] not in values:
            raise ValueError('CATALOG_QUERY_INVALID')
    for key, size in (('source_id', 32), ('parent_entity_id', 64)):
        if result[key] is not None and (type(result[key]) is not str or
                not re.fullmatch('[0-9a-f]{%d}' % size, result[key])):
            raise ValueError('CATALOG_QUERY_INVALID')
    text = result['text']
    if type(text) is not str or len(text) > 160 or re.search(r'[\x00-\x1f\x7f]', text):
        raise ValueError('CATALOG_QUERY_INVALID')
    result['text'] = normalized(text.strip())
    if result['view'] in ('seasons', 'episodes') and result['parent_entity_id'] is None:
        raise ValueError('CATALOG_QUERY_INVALID')
    return result


def create_projection(db, table='catalog_rows'):
    # Table names are private constants, not RPC parameters.
    assert table in ('catalog_rows', 'catalog_rows_build')
    db.execute('CREATE TABLE IF NOT EXISTS ' + table + '(' + ROW_SCHEMA + ')')


def project(db, file_id, table='catalog_rows'):
    assert table in ('catalog_rows', 'catalog_rows_build')
    row = db.execute('SELECT o.provider,o.account,o.ref,r.state,r.mapping,r.candidates,t.first_seen,t.updated '
        "FROM (SELECT id,provider,account,ref FROM objects UNION ALL SELECT id,'mounted_path',source,ref FROM typed_objects) o "
        'JOIN reviews r ON r.file=o.id LEFT JOIN object_times t ON t.file=o.id '
        'WHERE o.id=?', (file_id,)).fetchone()
    ref = json.loads(row['ref'])
    mapping = json.loads(row['mapping']) if row['mapping'] else None
    title, kind, season, episode = ref['name'], 'unknown', None, None
    work, season_id, episode_id = file_id, None, None
    metadata_key = None
    years = {candidate.get('year') for candidate in json.loads(row['candidates'])
             if type(candidate.get('year')) is int}
    year = next(iter(years)) if len(years) == 1 else None
    if mapping:
        title = mapping['title']
        if row['state'] == 'confirmed' and mapping['kind'] in ('movie', 'tv'):
            kind, season, episode = mapping['kind'], mapping['season'], mapping['episode']
            metadata_key = 'tmdb:%s:%d' % (kind, mapping['tmdb_id'])
            work = opaque(row['provider'], row['account'], kind, mapping['tmdb_id'])
            if kind == 'tv':
                season_id = opaque(work, 'season', season)
                episode_id = opaque(work, 'episode', season, episode)
    db.execute('INSERT OR REPLACE INTO ' + table + ' VALUES(' + ','.join('?' for _ in range(21)) + ')',
        (file_id, row['provider'], row['account'], work, season_id, episode_id, title,
         ref['name'], normalized(title), normalized(title + '\n' + ref['name']), kind,
         season, episode, row['state'], row['first_seen'], row['updated'] or 0,
         opaque(row['provider'], row['account'], ref['namespace'], ref['parent']),
         ref['namespace'], ref.get('mount_generation', ''), metadata_key, year))


class CatalogQuery:
    """Finite process-local cursors. Restart and writes invalidate continuation."""
    def __init__(self, index):
        self.index = index
        self.cursors = OrderedDict()
        self.clock = time.monotonic

    def query(self, expected, query=None, cursor=None, limit=DEFAULT_LIMIT):
        query = parameters({} if query is None else query)
        if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
            raise ValueError('CATALOG_PAGE_INVALID')
        if cursor is not None and (type(cursor) is not str or not re.fullmatch('[0-9a-f]{32}', cursor)):
            raise ValueError('CATALOG_CURSOR_STALE')
        scope = scope_key(expected)
        digest = opaque(query)
        with self.index.lock:
            db = self.index.db
            meta = db.execute('SELECT generation,revision FROM catalog_meta WHERE singleton=1').fetchone()
            revision = self.index.scope_revision(expected)
            # Mount availability is an observation, not the descriptor scope.
            binding = (scope, digest, meta['generation'], revision, expected.get('generation'))
            after = None
            if cursor:
                saved = self.cursors.get(cursor)
                if saved is None or saved[0] != binding or self.clock() >= saved[2]:
                    raise ValueError('CATALOG_CURSOR_STALE')
                after = saved[1]
            sql, args = self._sql(expected, query, after)
            rows = db.execute(sql, args + [limit + 1]).fetchall()
            result = dict(schema=1, items=[], next_cursor=None,
                          projection_revision=revision, truncated=False)
            continuation = uuid4().hex
            last = None
            for row in rows[:limit]:
                item = self._summary(row, query['view'])
                trial = dict(result, items=result['items'] + [item], next_cursor=continuation)
                if len(wire(trial)) > REPLY_BYTES:
                    if not result['items']:
                        raise ValueError('CATALOG_REPLY_LIMIT')
                    result['truncated'] = True
                    break
                result['items'].append(item)
                last = (row['sort_key'], row['entity_id'])
                result['truncated'] |= item['truncated']
            if len(rows) > len(result['items']):
                result['next_cursor'] = continuation
                self.cursors[continuation] = (binding, last, self.clock() + CURSOR_SECONDS)
                while len(self.cursors) > 128:
                    self.cursors.popitem(last=False)
            if len(wire(result)) > REPLY_BYTES:
                raise ValueError('CATALOG_REPLY_LIMIT')
            return result

    @staticmethod
    def _summary(row, view):
        title = row['filename'] if view == 'files' else row['title']
        if view == 'seasons':
            title = '%s · S%02d' % (title, row['season'])
        elif view == 'episodes':
            title = '%s · S%02dE%02d' % (title, row['season'], row['episode'])
        # A display-only limit. Stable identities, mapping and cursor are intact.
        return dict(entity_id=row['entity_id'], entity_kind={
            'works': 'work', 'seasons': 'season', 'episodes': 'episode', 'files': 'file'}[view],
            display_title=title[:160], media_kind=row['media_kind'],
            season=row['season'] if view != 'works' else None,
            episode=row['episode'] if view in ('episodes', 'files') else None,
            review_state=row['review_state'], availability=row['availability'],
            variant_count=row['variant_count'], available_count=row['available_count'],
            source_count=row['source_count'], truncated=len(title) > 160,
            metadata_key=row['metadata_key'], year=row['year'], art={})

    @staticmethod
    def _sql(expected, query, after):
        view = query['view']
        key = {'works': 'work_id', 'seasons': 'season_id', 'episodes': 'episode_id', 'files': 'id'}[view]
        conditions = ['p.provider=?', 'p.account=?', 'p.' + key + ' IS NOT NULL']
        args = list(scope_key(expected)[:2])
        if expected.get('reference_kind') == 'mounted_path':
            conditions.append('p.namespace=?')
            args.append(expected['namespace'])
        for field, column in (('review_state', 'review_state'), ('media_kind', 'media_kind')):
            if query[field] is not None:
                conditions.append('p.' + column + '=?')
                args.append(query[field])
        if query['source_id']:
            conditions.append('EXISTS(SELECT 1 FROM memberships f WHERE f.file=p.id AND f.source=?)')
            args.append(query['source_id'])
        if query['text']:
            conditions.append("p.search_text LIKE ? ESCAPE '\\'")
            args.append('%' + query['text'].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        parent = query['parent_entity_id']
        if parent:
            columns = ('work_id',) if view == 'seasons' else ('season_id',) if view == 'episodes' else ('work_id', 'season_id', 'episode_id')
            conditions.append('(' + ' OR '.join('p.' + column + '=?' for column in columns) + ')')
            args.extend([parent] * len(columns))
        availability = ("CASE WHEN EXISTS(SELECT 1 FROM memberships m JOIN catalog_sources s ON s.source=m.source "
            "WHERE m.file=p.id AND s.active=1 AND m.available=1) THEN 'observed_present' "
            "WHEN EXISTS(SELECT 1 FROM memberships m JOIN catalog_sources s ON s.source=m.source "
            "WHERE m.file=p.id AND s.active=1) THEN 'observed_absent' "
            "WHEN EXISTS(SELECT 1 FROM memberships m WHERE m.file=p.id) THEN 'source_unavailable' "
            "ELSE 'unverified' END")
        if expected.get('reference_kind') == 'mounted_path':
            generation = expected.get('generation', '')
            if generation:
                # Only hex digests produced by the mounted port reach this
                # internal read model; use parameters even for those digests.
                availability = ("CASE WHEN p.authority_generation!=? AND EXISTS(SELECT 1 FROM memberships m "
                    "JOIN catalog_sources s ON s.source=m.source WHERE m.file=p.id AND s.active=1) "
                    "THEN 'unverified' ELSE " + availability + ' END')
                args.insert(0, generation)
            else:
                availability = "'source_unavailable'"
        sql = 'WITH selected AS (SELECT p.*, ' + availability + ' AS availability FROM catalog_rows p WHERE ' + ' AND '.join(conditions) + ')'
        if query['availability']:
            sql += ', filtered AS (SELECT * FROM selected WHERE availability=?)'
            args.append(query['availability'])
        else:
            sql += ', filtered AS (SELECT * FROM selected)'
        # Unknown migration dates sort after real observations; never invent an
        # added date from a migration or metadata change.
        sort = {'name': 'MIN(p.title_sort)', 'recent_added': '-COALESCE(MAX(p.first_seen),0)',
                'recent_edited': '-MAX(p.updated)'}[query['sort']]
        if query['sort'] == 'name' and view in ('seasons', 'episodes'):
            sort = "printf('%06d:%06d',MIN(p.season),COALESCE(MIN(p.episode),0))"
        sql += (', grouped AS (SELECT p.' + key + ' AS entity_id,MIN(p.title) AS title,MIN(p.filename) AS filename,'
            'MIN(p.media_kind) AS media_kind,MIN(p.season) AS season,MIN(p.episode) AS episode,'
            'MIN(p.metadata_key) AS metadata_key,MIN(p.year) AS year,'
            'MIN(p.review_state) AS review_state,COUNT(DISTINCT p.id) AS variant_count,'
            "COUNT(DISTINCT CASE WHEN p.availability='observed_present' THEN p.id END) AS available_count,"
            'COUNT(DISTINCT CASE WHEN m.available=1 AND s.active=1 THEN m.source END) AS source_count,'
            "CASE WHEN MAX(p.availability='observed_present') THEN 'observed_present' "
            "WHEN MAX(p.availability='observed_absent') THEN 'observed_absent' "
            "WHEN MAX(p.availability='source_unavailable') THEN 'source_unavailable' ELSE 'unverified' END AS availability,"
            + sort + ' AS sort_key FROM filtered p LEFT JOIN memberships m ON m.file=p.id '
            'LEFT JOIN catalog_sources s ON s.source=m.source GROUP BY p.' + key + ') SELECT * FROM grouped')
        if after is not None:
            sql += ' WHERE (sort_key>? OR (sort_key=? AND entity_id>?))'
            args.extend([after[0], after[0], after[1]])
        return sql + ' ORDER BY sort_key,entity_id LIMIT ?', args

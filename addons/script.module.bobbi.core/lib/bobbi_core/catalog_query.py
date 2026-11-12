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
PROJECTION_SCHEMA = 6
VIEWS = ('works', 'seasons', 'episodes', 'files', 'supplements')
AVAILABILITY = ('observed_present', 'observed_absent', 'source_unavailable', 'unverified')
STATES = ('unmatched', 'ambiguous', 'proposed', 'confirmed', 'ignored')
ROW_SCHEMA = ('id TEXT PRIMARY KEY,provider TEXT NOT NULL,account TEXT NOT NULL,'
    'work_id TEXT NOT NULL,season_id TEXT,episode_id TEXT,title TEXT NOT NULL,'
    'filename TEXT NOT NULL,title_sort TEXT NOT NULL,search_text TEXT NOT NULL,'
    'media_kind TEXT NOT NULL,season INTEGER,episode INTEGER,review_state TEXT NOT NULL,'
    'first_seen REAL,updated REAL NOT NULL,group_key TEXT NOT NULL,namespace TEXT NOT NULL,authority_generation TEXT NOT NULL,'
    'metadata_key TEXT,year INTEGER,filename_sort TEXT NOT NULL')


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def normalized(value):
    return unicodedata.normalize('NFKC', value).casefold()


def opaque(*parts):
    return hashlib.sha256(wire(parts)).hexdigest()


def scope_key(value):
    # SQL partition labels are not a fabricated authenticated cloud account.
    # Host checks the corresponding native-account or mounted authority first.
    if value.get('reference_kind') in ('mounted_path', 'local_path'):
        return (value['reference_kind'], value['source_id'], value['namespace'])
    return (value['provider'], value['account_id'], value['epoch'])


def revision_key(value):
    """Persistent local scope; native login epochs remain cursor-only CAS."""
    if value.get('reference_kind') in ('mounted_path', 'local_path'):
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
    if result['view'] in ('seasons', 'episodes', 'supplements') and result['parent_entity_id'] is None:
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
    provider = ref.get('reference_kind', row['provider'])
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
            work = opaque(provider, row['account'], kind, mapping['tmdb_id'])
            if kind == 'tv':
                season_id = opaque(work, 'season', season)
                episode_id = opaque(work, 'episode', season, episode)
    version = (mapping or {}).get('version') or ''
    db.execute('INSERT OR REPLACE INTO ' + table + ' VALUES(' + ','.join('?' for _ in range(22)) + ')',
        (file_id, provider, row['account'], work, season_id, episode_id, title,
         ref['name'], normalized(title), normalized(title + '\n' + ref['name'] + '\n' + version), kind,
         season, episode, row['state'], row['first_seen'], row['updated'] or 0,
         opaque(provider, row['account'], ref['namespace'], ref['parent']),
         ref['namespace'], ref.get('mount_generation', ref.get('source_generation', '')), metadata_key, year, normalized(ref['name'])))


class CatalogQuery:
    """Finite process-local cursors. Restart and writes invalidate continuation."""
    def __init__(self, index):
        self.index = index
        self.cursors = OrderedDict()
        self.clock = time.monotonic

    @staticmethod
    def _partition(expected):
        where, args = 'p.provider=? AND p.account=?', list(scope_key(expected)[:2])
        if expected.get('reference_kind') in ('mounted_path', 'local_path'):
            where += ' AND p.namespace=?'
            args.append(expected['namespace'])
        return where, args

    def parent_descriptor(self, expected, parent_id):
        """Describe a confirmed group; persistent views retain meaning, not a grant."""
        if type(parent_id) is not str or not re.fullmatch('[0-9a-f]{64}', parent_id):
            raise ValueError('CATALOG_ID_INVALID')
        where, args = self._partition(expected)
        with self.index.lock:
            row = self.index.db.execute('SELECT p.* FROM catalog_rows p WHERE ' + where +
                " AND p.review_state='confirmed' AND p.metadata_key IS NOT NULL AND "
                'NOT EXISTS(SELECT 1 FROM file_supplements s WHERE s.file=p.id) AND '
                '(p.work_id=? OR p.season_id=? OR p.episode_id=?) LIMIT 1',
                args + [parent_id] * 3).fetchone()
            if row is None:
                raise ValueError('CATALOG_PARENT_CHANGED')
            kind = ('work' if row['work_id'] == parent_id else
                    'season' if row['season_id'] == parent_id else 'episode')
            return dict(entity_id=parent_id, entity_kind=kind, metadata_key=row['metadata_key'],
                season=row['season'] if kind != 'work' else None,
                episode=row['episode'] if kind == 'episode' else None)

    def describe_files(self, expected, file_ids):
        """One bounded local batch, without remote lookups, FileRefs or tickets."""
        if (type(file_ids) is not list or not 1 <= len(file_ids) <= DEFAULT_LIMIT or
                any(type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value) for value in file_ids)):
            raise ValueError('CATALOG_PAGE_INVALID')
        where, args = self._partition(expected)
        with self.index.lock:
            rows = self.index.db.execute('SELECT p.*,p.id AS entity_id FROM catalog_rows p WHERE ' +
                where + ' AND p.id IN (' + ','.join('?' for _ in file_ids) + ') ORDER BY p.id',
                args + file_ids).fetchall()
            details = self._file_details(self.index.db, rows, {}, expected)
            result = dict(items=[], truncated=False)
            for row in rows:
                detail = details[row['id']]
                detail.pop('_detail_truncated', None)
                item = dict(detail, entity_id=row['id'], entity_kind='file',
                    display_title=row['filename'][:160], work_title=row['title'][:160],
                    media_kind=row['media_kind'], metadata_key=row['metadata_key'],
                    season=row['season'], episode=row['episode'], review_state=row['review_state'],
                    parent_entity_id=(row['episode_id'] or row['work_id']) if row['metadata_key'] else None)
                if len(wire(dict(result, items=result['items'] + [item]))) > REPLY_BYTES:
                    result['truncated'] = True
                    break
                result['items'].append(item)
            return result

    def holdings(self, expected, identities):
        """Confirmed public identities in one SQL batch; membership is not a file."""
        if (type(identities) is not list or not 1 <= len(identities) <= DEFAULT_LIMIT or
                any(type(key) is not str or not re.fullmatch(r'tmdb:(movie|tv):[1-9]\d{0,8}', key)
                    for key in identities)):
            raise ValueError('CATALOG_PAGE_INVALID')
        where, args = self._partition(expected)
        with self.index.lock:
            # An absent/unbuilt local index is unknown, not evidence of no files.
            known = bool(self.index.db.execute('SELECT 1 FROM catalog_rows p WHERE ' + where +
                ' LIMIT 1', args).fetchone())
            rows = self.index.db.execute('SELECT p.metadata_key,p.work_id,COUNT(DISTINCT p.id) AS file_count,'
                'COUNT(DISTINCT p.episode_id) AS episode_count FROM catalog_rows p WHERE ' + where +
                " AND p.review_state='confirmed' AND NOT EXISTS(SELECT 1 FROM file_supplements s WHERE s.file=p.id) AND p.metadata_key IN (" +
                ','.join('?' for _ in identities) + ') GROUP BY p.metadata_key,p.work_id', args + identities).fetchall()
            found = {row['metadata_key']: dict(metadata_key=row['metadata_key'], entity_id=row['work_id'],
                entity_kind='work', media_kind=row['metadata_key'].split(':')[1],
                file_count=row['file_count'], episode_count=row['episode_count'], state='observed') for row in rows}
            return dict(items=[found.get(key, dict(metadata_key=key, state='not_indexed' if known else 'unknown',
                file_count=0 if known else None)) for key in dict.fromkeys(identities)])

    def query(self, expected, query=None, cursor=None, limit=DEFAULT_LIMIT, source_names=None):
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
            file_view = query['view'] in ('files', 'supplements')
            details = self._file_details(db, rows[:limit], source_names or {}, expected) if file_view else {}
            for row in rows[:limit]:
                item = self._summary(row, query['view'])
                if file_view:
                    item.update(details[row['entity_id']])
                    detail_truncated = item.pop('_detail_truncated')
                    item['truncated'] |= len(row['filename']) > 160 or detail_truncated
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

    def _file_details(self, db, rows, source_names, expected):
        # Decode only the bounded file page. Works/seasons/episodes retain the
        # scalar read path; no new schema or second metadata authority is needed.
        ids = [row['entity_id'] for row in rows]
        if not ids:
            return {}
        marks = ','.join('?' for _ in ids)
        names = {identifier: [] for identifier in ids}
        totals = {row['file']: row['total'] for row in db.execute(
            'SELECT file,COUNT(*) AS total FROM memberships WHERE file IN (' + marks + ') GROUP BY file', ids)}
        # Removed registrations remain historical memberships. Bound retrieval
        # as well as output, even after many add/remove cycles over years.
        source_select = ('SELECT file,source FROM (SELECT m.file,m.source FROM memberships m '
            'LEFT JOIN catalog_sources s ON s.source=m.source WHERE m.file=? '
            'ORDER BY COALESCE(s.active,0) DESC,m.source LIMIT 3)')
        sources_sql = ' UNION ALL '.join(source_select for _ in ids)
        for membership in db.execute(sources_sql, ids):
            source = membership['source']
            names[membership['file']].append((source, source_names.get(source, '已移除或未命名来源')))
        references = db.execute('SELECT o.id,o.ref,r.mapping,r.revision,s.detail AS supplement_detail FROM (SELECT id,ref FROM objects WHERE id IN (' + marks +
            ') UNION ALL SELECT id,ref FROM typed_objects WHERE id IN (' + marks +
            ')) o JOIN reviews r ON r.file=o.id LEFT JOIN file_supplements s ON s.file=o.id', ids + ids)
        result = {}
        for row in references:
            ref = json.loads(row['ref'])
            mapping = json.loads(row['mapping']) if row['mapping'] else {}
            version = (mapping or {}).get('version') or ''
            sources = names[row['id']]
            detail = dict(file_name=ref['name'][:160], file_size=ref['size'], version_label=version[:80],
                review_revision=row['revision'], observation_key=opaque(ref),
                sources=[dict(id=source, name=name[:80]) for source, name in sources[:3]],
                source_total=totals.get(row['id'], 0), _detail_truncated=len(version) > 80 or totals.get(row['id'], 0) > 3 or any(len(name) > 80 for _, name in sources))
            if ref.get('reference_kind') != 'mounted_path' and 'provider' in ref:
                # Display-only match with the saved observation, never a play permit.
                detail['history_key'] = opaque(ref['id'], ref['size'], ref.get('fingerprint'))
            from .catalog_supplements import summary
            relation = json.loads(row['supplement_detail']) if row['supplement_detail'] else None
            if relation:
                detail['supplement'] = summary(self.index, expected, relation)
            result[row['id']] = detail
        return result

    @staticmethod
    def _summary(row, view):
        title = row['filename'] if view in ('files', 'supplements') else row['title']
        if view == 'seasons':
            title = '%s · S%02d' % (title, row['season'])
        elif view == 'episodes':
            title = '%s · S%02dE%02d' % (title, row['season'], row['episode'])
        # A display-only limit. Stable identities, mapping and cursor are intact.
        return dict(entity_id=row['entity_id'], entity_kind={
            'works': 'work', 'seasons': 'season', 'episodes': 'episode', 'files': 'file', 'supplements': 'file'}[view],
            display_title=title[:160], media_kind=row['media_kind'],
            season=row['season'] if view != 'works' else None,
            episode=row['episode'] if view in ('episodes', 'files', 'supplements') else None,
            review_state=row['review_state'], availability=row['availability'],
            variant_count=row['variant_count'], available_count=row['available_count'],
            source_count=row['source_count'], truncated=len(title) > 160,
            metadata_key=row['metadata_key'], year=row['year'], art={})

    @staticmethod
    def _sql(expected, query, after):
        view = query['view']
        key = {'works': 'work_id', 'seasons': 'season_id', 'episodes': 'episode_id', 'files': 'id', 'supplements': 'id'}[view]
        conditions = ['p.provider=?', 'p.account=?', 'p.' + key + ' IS NOT NULL']
        args = list(scope_key(expected)[:2])
        if view != 'supplements':
            # The review workbench still needs to reach every original file.
            # All ordinary works/versions omit extras from main-media counts.
            if not (view == 'files' and query.get('review_state')):
                conditions.append('NOT EXISTS(SELECT 1 FROM file_supplements s WHERE s.file=p.id)')
        if expected.get('reference_kind') in ('mounted_path', 'local_path'):
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
            if view == 'supplements':
                conditions.append('EXISTS(SELECT 1 FROM file_supplements s WHERE s.file=p.id AND '
                    '(s.work_id=? OR s.parent_file=? OR (s.parent_file IS NULL AND s.work_id IN '
                    '(SELECT work_id FROM catalog_rows WHERE id=?))))')
                args.extend([parent] * 3)
            else:
                columns = ('work_id',) if view == 'seasons' else ('season_id',) if view == 'episodes' else ('work_id', 'season_id', 'episode_id')
                conditions.append('(' + ' OR '.join('p.' + column + '=?' for column in columns) + ')')
                args.extend([parent] * len(columns))
        availability = ("CASE WHEN EXISTS(SELECT 1 FROM memberships m JOIN catalog_sources s ON s.source=m.source "
            "WHERE m.file=p.id AND s.active=1 AND m.available=1) THEN 'observed_present' "
            "WHEN EXISTS(SELECT 1 FROM memberships m JOIN catalog_sources s ON s.source=m.source "
            "WHERE m.file=p.id AND s.active=1) THEN 'observed_absent' "
            "WHEN EXISTS(SELECT 1 FROM memberships m WHERE m.file=p.id) THEN 'source_unavailable' "
            "ELSE 'unverified' END")
        if expected.get('reference_kind') in ('mounted_path', 'local_path'):
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
        if query['sort'] == 'name' and view in ('files', 'supplements'):
            sort = 'MIN(p.filename_sort)'
        if query['sort'] == 'name' and view in ('seasons', 'episodes'):
            sort = "printf('%06d:%06d',MIN(p.season),COALESCE(MIN(p.episode),0))"
        # Count source memberships separately. Joining them into file aggregation
        # repeats the correlated presence checks once per historical membership.
        sql += (', source_counts AS (SELECT p.' + key + ' AS entity_id,'
            'COUNT(DISTINCT CASE WHEN m.available=1 AND s.active=1 THEN m.source END) AS source_count '
            'FROM filtered p LEFT JOIN memberships m ON m.file=p.id '
            'LEFT JOIN catalog_sources s ON s.source=m.source GROUP BY p.' + key + ')')
        sql += (', grouped AS (SELECT p.' + key + ' AS entity_id,MIN(p.title) AS title,MIN(p.filename) AS filename,'
            'MIN(p.media_kind) AS media_kind,MIN(p.season) AS season,MIN(p.episode) AS episode,'
            'MIN(p.metadata_key) AS metadata_key,MIN(p.year) AS year,'
            'MIN(p.review_state) AS review_state,COUNT(DISTINCT p.id) AS variant_count,'
            "COUNT(DISTINCT CASE WHEN p.availability='observed_present' THEN p.id END) AS available_count,"
            "CASE WHEN MAX(p.availability='observed_present') THEN 'observed_present' "
            "WHEN MAX(p.availability='observed_absent') THEN 'observed_absent' "
            "WHEN MAX(p.availability='source_unavailable') THEN 'source_unavailable' ELSE 'unverified' END AS availability,"
            + sort + ' AS sort_key FROM filtered p GROUP BY p.' + key + ') '
            'SELECT g.*,COALESCE(sc.source_count,0) AS source_count FROM grouped g '
            'LEFT JOIN source_counts sc ON sc.entity_id=g.entity_id')
        if after is not None:
            sql += ' WHERE (g.sort_key>? OR (g.sort_key=? AND g.entity_id>?))'
            args.extend([after[0], after[0], after[1]])
        return sql + ' ORDER BY g.sort_key,g.entity_id LIMIT ?', args

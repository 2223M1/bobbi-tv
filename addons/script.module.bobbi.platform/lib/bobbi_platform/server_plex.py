"""Plex library entries, Media versions and every Part, without HLS guesses.

Uses the existing Plex /api/v2/user/resources and PMS identity/library routes.
PMS Part IDs are not interchangeable with ratingKey or Media IDs.
"""
import re
from urllib.parse import unquote

from bobbi_core.server_ref import identifier, file_id, parts
from bobbi_core.server_description import observed
from .pan_accounts import PanError
from .pan_tokens import number, text, page_number
from .server_http import Session, address


def _id(value):
    try:
        return identifier(str(value) if type(value) is int else value)
    except ValueError:
        raise PanError('PAN_REPLY_INVALID') from None


def _container(value):
    if type(value) is not dict or type(value.get('MediaContainer')) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    return value['MediaContainer']


def _rows(value, key, limit=256):
    rows = value.get(key, [])
    if type(rows) is not list or len(rows) > limit or any(type(row) is not dict for row in rows):
        raise PanError('PAN_REPLY_INVALID')
    return rows


def _local_page(rows, page, size):
    offset = (page - 1) * size
    if offset > len(rows) or len({row['file_id'] for row in rows}) != len(rows):
        raise PanError('PAN_PAGE_EXPIRED')
    return dict(items=rows[offset:offset + size], has_more=offset + size < len(rows))


class Client:
    def __init__(self, value, session=None):
        self.saved = value
        self.session = session or Session('plex', value['location'], value['token'])

    def __repr__(self):
        return '<Plex library: credentials hidden>'

    def verify(self, cloud=None):
        cloud = cloud or Session('plex', 'https://plex.tv', self.saved['user_token'])
        # Registration has one total budget even though identity uses the
        # fixed Plex account origin and the separately configured PMS origin.
        cloud.deadline = getattr(self.session, 'deadline', None)
        cloud.operation = getattr(self.session, 'operation', None)
        user = cloud.request('/api/v2/user')
        uid = _id(user.get('id')) if type(user) is dict else _id(None)
        resources = cloud.request('/api/v2/resources', query={'includeHttps': 1, 'includeRelay': 1})
        sid = _id(_container(self.session.request('/identity')).get('machineIdentifier'))
        if (type(resources) is not list or len(resources) > 256 or not any(
                type(row) is dict and row.get('clientIdentifier') == sid
                and row.get('accessToken') == self.saved['token']
                and 'server' in str(row.get('provides', '')).split(',') for row in resources)):
            raise PanError('PAN_ACCOUNT_ID_INVALID')
        _rows(_container(self.session.request('/library/sections')), 'Directory')
        return sid, uid

    def _identity(self):
        if _container(self.session.request('/identity')).get('machineIdentifier') != self.saved['server_id']:
            raise PanError('PAN_ACCOUNT_ID_INVALID')

    def _files(self, entry, descriptions=None, progress=None):
        value = _container(self.session.request('/library/metadata/' + entry))
        rows = _rows(value, 'Metadata', 1)
        if len(rows) != 1 or _id(rows[0].get('ratingKey')) != entry:
            raise PanError('PAN_FILE_CHANGED')
        if progress is not None:
            from .server_progress import item_progress
            progress.update(item_progress('plex', entry, rows[0]))
        if descriptions is not None:
            item, ids = rows[0], {}
            guids = item.get('Guid')
            if type(guids) is list and len(guids) <= 32:
                for key in ('tmdb', 'imdb', 'tvdb'):
                    values = {row['id'][len(key) + 3:] for row in guids
                        if type(row) is dict and type(row.get('id')) is str
                        and row['id'].startswith(key + '://')}
                    if len(values) == 1:
                        ids[key] = values.pop()
            description = observed('plex', entry, item_type=item.get('type'),
                title=item.get('title'), overview=item.get('summary'), year=item.get('year'),
                series_title=item.get('grandparentTitle'), season=item.get('parentIndex'),
                episode=item.get('index'), ids=ids)
        result, seen = [], set()
        for media in _rows(rows[0], 'Media'):
            mid = _id(media.get('id'))
            all_parts = _rows(media, 'Part')
            for index, part in enumerate(all_parts, 1):
                pid = _id(part.get('id'))
                fid = file_id(entry, mid, pid, index, len(all_parts))
                key = part.get('key')
                if ((mid, pid) in seen or type(key) is not str
                        or not re.fullmatch(r'/library/parts/' + re.escape(pid) + r'/[0-9]+/[^/?#]+', key)):
                    raise PanError('PAN_REPLY_INVALID')
                seen.add((mid, pid))
                name = text(unquote(str(part.get('file', '')).replace('\\', '/').rsplit('/', 1)[-1]))
                if '/' in name or '\\' in name:
                    raise PanError('PAN_REPLY_INVALID')
                if len(all_parts) > 1:
                    stem, dot, ext = name.rpartition('.')
                    name = (stem if dot else name) + ' [分卷 %d-%d，不自动续播]' % (index, len(all_parts)) + ('.' + ext if dot else '')
                row = dict(file_id=fid, server_id=self.saved['server_id'], name=name,
                    size=number(part.get('size'), 1), directory=False)
                result.append((row, address(self.session.base, key)))
                if descriptions is not None:
                    descriptions[fid] = description
        if len(result) > 256:
            raise PanError('PAN_REPLY_INVALID')
        return result

    def list_files(self, parent='root', page=1, size=10):
        page_number(page, size)
        self._identity()
        if parent == 'root':
            rows = _rows(_container(self.session.request('/library/sections')), 'Directory')
            return _local_page([dict(file_id='section:' + _id(row.get('key')) + ':' + row['type'],
                name=text(row.get('title')), directory=True, size=0)
                for row in rows if row.get('type') in ('movie', 'show')], page, size)
        if re.fullmatch(r'item:[A-Za-z0-9_-]{1,128}', parent):
            operation = getattr(self.session, 'operation', None)
            descriptions = {} if operation is not None and operation.kind == 'scan' else None
            result = _local_page([row for row, _ in self._files(parent[5:], descriptions)], page, size)
            if descriptions is not None:
                result['catalog_descriptions'] = {row['file_id']: descriptions[row['file_id']] for row in result['items']}
            return result
        match = re.fullmatch(r'section:([A-Za-z0-9_-]{1,128}):(movie|show)', parent)
        if match is None:
            raise PanError('PAN_DIRECTORY_UNAVAILABLE')
        section, kind = match.groups()
        offset = (page - 1) * size
        value = _container(self.session.request('/library/sections/' + section + '/all', query={
            'type': 1 if kind == 'movie' else 4, 'X-Plex-Container-Start': offset, 'X-Plex-Container-Size': size}))
        rows = _rows(value, 'Metadata', size)
        total = number(value.get('totalSize'))
        if (str(value.get('librarySectionID')) != section or number(value.get('offset', 0)) != offset
                or offset > total or len(rows) != min(size, total - offset)):
            raise PanError('PAN_REPLY_INVALID')
        items = [dict(file_id='item:' + _id(row.get('ratingKey')), name=text(row.get('title')),
                      directory=True, size=0) for row in rows]
        if len({row['file_id'] for row in items}) != len(items):
            raise PanError('PAN_REPLY_INVALID')
        operation = getattr(self.session, 'operation', None)
        if operation is not None and operation.kind == 'scan':
            progress = getattr(operation, '_server_pages', {})
            previous = progress.get(parent)
            ids = {row['file_id'] for row in items}
            if previous and (previous[0] != total or previous[1] != offset or ids & previous[2]):
                raise PanError('PAN_PAGE_EXPIRED')
            progress[parent] = (total, offset + len(rows), ids | (previous[2] if previous else set()))
            operation._server_pages = progress
        return dict(items=items, has_more=offset + len(rows) < total)

    def resolve_original(self, selected):
        self._identity()
        entry, _, _, _, _ = parts(selected['file_id'])
        for row, url in self._files(entry):
            if row == selected:
                return dict(url=url, size=row['size'], original=True, headers=self.session.headers())
        raise PanError('PAN_FILE_CHANGED')

    def read_progress(self, selected):
        """Item progress only; exact Part lookup never upgrades its scope."""
        self._identity()
        progress = {}
        entry, _, _, _, _ = parts(selected['file_id'])
        if not any(row == selected for row, _ in self._files(entry, progress=progress)):
            raise PanError('PAN_FILE_CHANGED')
        return progress

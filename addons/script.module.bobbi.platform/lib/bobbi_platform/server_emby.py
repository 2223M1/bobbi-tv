"""Shared Jellyfin/Emby exact MediaSource original-file adapter.

Jellyfin protocol evidence: controllers at f03253bae0383eaa4a250da59b3b959e424483e5;
Emby dev.emby.media MediaInfoService PlaybackInfo / Videos static stream.
No live stream opening, transcode session, HLS or inferred first-version pick.
"""
from urllib.parse import urlencode

from bobbi_core.server_ref import identifier, file_id, parts
from bobbi_core.server_description import observed
from .pan_accounts import PanError
from .pan_tokens import number, text, page_number
from .server_http import Session, address


def _id(value):
    try:
        return identifier(value)
    except ValueError:
        raise PanError('PAN_REPLY_INVALID') from None


def _rows(value, key):
    rows = value.get(key) if type(value) is dict else None
    if type(rows) is not list or len(rows) > 256 or any(type(row) is not dict for row in rows):
        raise PanError('PAN_REPLY_INVALID')
    return rows


class Client:
    def __init__(self, provider, saved, session=None):
        self.provider = provider
        self.saved = saved
        self.session = session or Session(provider, saved['location'], saved['token'])

    def __repr__(self):
        return '<Jellyfin/Emby library: credentials hidden>'

    def verify(self):
        info, user = self.session.request('/System/Info'), self.session.request('/Users/Me')
        if type(info) is not dict or type(user) is not dict:
            raise PanError('PAN_REPLY_INVALID')
        return _id(info.get('Id')), _id(user.get('Id'))

    def _identity(self):
        if self.verify() != (self.saved['server_id'], self.saved['user_id']):
            raise PanError('PAN_ACCOUNT_ID_INVALID')

    def _item(self, entry):
        item = self.session.request('/Users/' + self.saved['user_id'] + '/Items/' + _id(entry))
        if type(item) is not dict or item.get('Id') != entry or item.get('IsFolder') is True:
            raise PanError('PAN_FILE_CHANGED')
        if item.get('PartCount', 1) != 1:
            raise PanError('PAN_MEDIA_UNSUPPORTED')  # AdditionalParts are not alternate versions.
        return item

    def _file(self, entry, media):
        mid = _id(media.get('Id'))
        if (media.get('Protocol') != 'File' or media.get('IsInfiniteStream') is True
                or media.get('RequiresOpening') is True or media.get('VideoType', 'VideoFile') != 'VideoFile'):
            raise PanError('PAN_MEDIA_UNSUPPORTED')
        path = media.get('Path')
        if type(path) is not str:
            raise PanError('PAN_REPLY_INVALID')
        name = text(path.replace('\\', '/').rsplit('/', 1)[-1])
        # Static MediaSource streams have one file identity; the same actual
        # MediaSource ID occupies version and part positions, never a fake 0.
        return dict(file_id=file_id(entry, mid, mid), server_id=self.saved['server_id'],
                    directory=False, name=name, size=number(media.get('Size'), 1))

    def list_files(self, parent='root', page=1, size=10):
        page_number(page, size)
        self._identity()
        offset = (page - 1) * size
        if parent.startswith('item:'):
            entry = _id(parent[5:])
            item = self._item(entry)
            rows = [self._file(entry, media) for media in _rows(item, 'MediaSources')]
            total = len(rows)
            items = rows[offset:offset + size]
        else:
            root = parent == 'root'
            if not root and not parent.startswith('folder:'):
                raise PanError('PAN_DIRECTORY_UNAVAILABLE')
            query = dict(StartIndex=offset, Limit=size, Recursive='false', EnableTotalRecordCount='true')
            if not root:
                query['ParentId'] = _id(parent[7:])
            value = self.session.request('/Users/' + self.saved['user_id'] + ('/Views' if root else '/Items'),
                                         query=None if root else query)
            rows, total = _rows(value, 'Items'), number(value.get('TotalRecordCount'))
            # Views may ignore StartIndex/Limit; locally slice its bounded list.
            if root:
                if total != len(rows):
                    raise PanError('PAN_REPLY_INVALID')
                rows = rows[offset:offset + size]
            if len(rows) != min(size, max(0, total - offset)):
                raise PanError('PAN_REPLY_INVALID')
            items = [dict(file_id=('folder:' if row.get('IsFolder') is True else 'item:') + _id(row.get('Id')),
                name=text(row.get('Name')), directory=True, size=0) for row in rows]
        if offset > total or len({row['file_id'] for row in items}) != len(items):
            raise PanError('PAN_REPLY_INVALID')
        operation = getattr(self.session, 'operation', None)
        if operation is not None and operation.kind == 'scan':
            progress = getattr(operation, '_server_pages', {})
            previous, ids = progress.get(parent), {row['file_id'] for row in items}
            if previous and (previous[0] != total or previous[1] != offset or ids & previous[2]):
                raise PanError('PAN_PAGE_EXPIRED')
            progress[parent] = (total, offset + len(items), ids | (previous[2] if previous else set()))
            operation._server_pages = progress
        result = dict(items=items, has_more=offset + len(items) < total)
        if parent.startswith('item:') and operation is not None and operation.kind == 'scan':
            ids = item.get('ProviderIds')
            ids = {key.lower(): value for key, value in ids.items() if key in ('Tmdb', 'Imdb', 'Tvdb')} if type(ids) is dict else {}
            description = observed(self.provider, entry,
                item_type='movie' if item.get('Type') == 'Movie' else 'episode' if item.get('Type') == 'Episode' else None,
                title=item.get('Name'), overview=item.get('Overview'), year=item.get('ProductionYear'),
                series_title=item.get('SeriesName'), season=item.get('ParentIndexNumber'),
                episode=item.get('IndexNumber'), ids=ids)
            result['catalog_descriptions'] = {row['file_id']: description for row in items}
        return result

    def resolve_original(self, selected):
        self._identity()
        entry, mid, part, _, count = parts(selected['file_id'])
        if mid != part or count != 1:
            raise PanError('PAN_MEDIA_UNSUPPORTED')
        # The actual PlaybackInfo response for this exact version must permit
        # a finite static file. Default support booleans are not mode selection.
        value = self.session.request('/Items/' + entry + '/PlaybackInfo', data=dict(
            UserId=self.saved['user_id'], MediaSourceId=mid, EnableDirectPlay=True,
            EnableDirectStream=False, EnableTranscoding=False, AutoOpenLiveStream=False))
        matching = [media for media in _rows(value, 'MediaSources') if media.get('Id') == mid]
        if len(matching) != 1 or matching[0].get('SupportsDirectPlay') is not True:
            raise PanError('PAN_MEDIA_UNSUPPORTED')
        self._item(entry)
        if self._file(entry, matching[0]) != selected:
            raise PanError('PAN_FILE_CHANGED')
        url = address(self.session.base, '/Videos/' + entry + '/stream') + '?' + urlencode(
            dict(Static='true', MediaSourceId=mid))
        return dict(url=url, size=selected['size'], original=True, headers=self.session.headers())

    def read_progress(self, selected):
        """UserData belongs to the item, not the chosen MediaSource version."""
        from .server_progress import item_progress
        self._identity()
        entry, _, _, _, _ = parts(selected['file_id'])
        item = self._item(entry)
        matching = [self._file(entry, media) for media in _rows(item, 'MediaSources')]
        if matching.count(selected) != 1:
            raise PanError('PAN_FILE_CHANGED')
        return item_progress(self.provider, entry, item)

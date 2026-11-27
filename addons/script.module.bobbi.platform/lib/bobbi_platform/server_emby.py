"""Shared Jellyfin/Emby exact MediaSource original-file adapter.

Jellyfin protocol evidence: controllers at f03253bae0383eaa4a250da59b3b959e424483e5;
Emby dev.emby.media MediaInfoService PlaybackInfo / Videos static stream.
No live stream opening, transcode session, HLS or inferred first-version pick.
"""
from urllib.parse import unquote, urlencode, urlsplit

from bobbi_core.server_ref import identifier, file_id, parts
from bobbi_core.server_description import observed
from .pan_accounts import PanError
from .pan_tokens import number, text, page_number
from .server_http import Session, address, at_origin, token


def authenticate(location, username, password, device_id):
    """Bootstrap only: password is sent once to the explicitly configured origin."""
    text(username, 256)
    if type(password) is not str or len(password) > 4096:
        raise PanError('PAN_CREDENTIALS_INVALID')
    session = Session('emby', location, None, device_id=device_id)
    with session.budget(8):
        result = session.request('/Users/AuthenticateByName', data={'Username': username, 'Pw': password})
    if type(result) is not dict or type(result.get('User')) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    server, user = _id(result.get('ServerId')), _id(result['User'].get('Id'))
    if result['User'].get('ServerId', server) != server:
        raise PanError('PAN_ACCOUNT_ID_INVALID')
    return server, user, token(result.get('AccessToken'))


def _id(value):
    try:
        return identifier(value)
    except ValueError:
        raise PanError('PAN_REPLY_INVALID') from None


def emby_media_origin_allowed(url: str, server_base: str, approved_origins: set[str]) -> bool:
    """Source-bound origin check for Emby cross-origin HTTP media (U09)."""
    u_parts = urlsplit(url)
    b_parts = urlsplit(server_base)
    u_scheme = u_parts.scheme.lower()
    b_scheme = b_parts.scheme.lower()
    u_port = u_parts.port or (443 if u_scheme == 'https' else 80)
    b_port = b_parts.port or (443 if b_scheme == 'https' else 80)
    u_host = (u_parts.hostname or '').lower()
    b_host = (b_parts.hostname or '').lower()
    if (u_scheme, u_host, u_port) == (b_scheme, b_host, b_port):
        return True
    if u_scheme == 'https' and b_host and u_host.endswith('.' + b_host):
        return True
    canonical = f'{u_scheme}://{u_parts.netloc.lower()}'
    return canonical in approved_origins


def static_original_url(base, entry, mid):
    """One canonical Emby/Jellyfin URL for an exact file version; never embeds credentials."""
    return address(base, '/Videos/' + _id(entry) + '/stream') + '?' + urlencode(
        dict(Static='true', MediaSourceId=_id(mid)))


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
        if self.provider == 'emby':
            # A password handshake identifies the user. Only legacy/imported
            # tokens with no bound ID require the optional self-discovery API.
            info = self.session.request('/System/Info/Public')
            uid = self.saved.get('user_id')
            user = self.session.request('/Users/' + _id(uid) if uid else '/Users/Me')
        else:
            info, user = self.session.request('/System/Info'), self.session.request('/Users/Me')
        if type(info) is not dict or type(user) is not dict:
            raise PanError('PAN_REPLY_INVALID')
        return _id(info.get('Id')), _id(user.get('Id'))

    def _identity(self, *, user_scoped_read=False):
        operation = getattr(self.session, 'operation', None)
        reusable = (self.provider == 'emby' and user_scoped_read and
                    getattr(operation, 'kind', None) == 'scan' and getattr(operation, 'expected', None))
        identity = (self.saved['server_id'], self.saved['user_id'])
        binding = (operation.expected.get('source_id'), operation.expected.get('generation'), *identity) if reusable else None
        if binding and getattr(operation, '_emby_verified_user', None) == binding:
            # The following authenticated /Users/<captured user>/... request
            # checks access on EVERY page. Check the server on every page too;
            # only the redundant user metadata GET is leased to this scan.
            info = self.session.request('/System/Info/Public')
            if type(info) is not dict or _id(info.get('Id')) != identity[0]:
                raise PanError('PAN_ACCOUNT_ID_INVALID')
            return
        if self.verify() != identity:
            raise PanError('PAN_ACCOUNT_ID_INVALID')
        if binding:
            operation._emby_verified_user = binding

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

    def _versions(self, entry, item):
        """Classify siblings independently; ambiguous IDs cannot yield a ticket."""
        versions = _rows(item, 'MediaSources')
        seen, rows, excluded = set(), [], {}
        for version in versions:
            mid = _id(version.get('Id'))
            if mid in seen:
                raise PanError('PAN_REPLY_INVALID')
            seen.add(mid)
            try:
                rows.append(self._file(entry, version))
            except PanError as error:
                reason = {'PAN_MEDIA_UNSUPPORTED': 'unsupported', 'PAN_REPLY_INVALID': 'unverified'}.get(str(error))
                if not reason:
                    raise
                excluded[reason] = excluded.get(reason, 0) + 1
        return rows, excluded

    def page_rows(self, parent, page, size, *, display=False, episode_order=False):
        """One server page. Online Kodi presentation never opens the optional local index."""
        page_number(page, size)
        offset = (page - 1) * size
        root = parent == 'root'
        view = self.provider == 'emby' and parent.startswith('view:')
        if not root and not view and not parent.startswith('folder:'):
            raise PanError('PAN_DIRECTORY_UNAVAILABLE')
        query = dict(StartIndex=offset, Limit=size, Recursive='false', EnableTotalRecordCount='true')
        route = '/Views' if root else '/Items'
        if view:
            if getattr(getattr(self.session, 'operation', None), 'kind', None) == 'scan':
                raise PanError('PAN_DIRECTORY_UNAVAILABLE')  # Dynamic view is not a scan scope.
            query.update(Recursive='true', IncludeItemTypes='Movie,Episode')
            if parent == 'view:recent':
                query.update(SortBy='DateCreated,SortName', SortOrder='Descending')
            elif parent == 'view:resume':
                route = '/Items/Resume'
                query.update(MediaTypes='Video')
            elif parent.startswith('view:search:'):
                query.update(SearchTerm=text(parent[len('view:search:'):], 120),
                             IncludeItemTypes='Movie,Series,Episode', SortBy='SortName', SortOrder='Ascending')
            else:
                raise PanError('PAN_DIRECTORY_UNAVAILABLE')
        elif not root:
            query['ParentId'] = _id(parent[7:])
            if episode_order and self.provider == 'emby':
                query.update(
                    IncludeItemTypes='Episode',
                    SortBy='ParentIndexNumber,IndexNumber,SortName',
                    SortOrder='Ascending',
                )
        if display and not root:
            query.update(Fields='Overview,Genres,ProductionYear,RunTimeTicks,UserData', EnableImageTypes='Primary', ImageTypeLimit=1)
        value = self.session.request('/Users/' + self.saved['user_id'] + route,
                                     query=None if root else query)
        rows, total = _rows(value, 'Items'), number(value.get('TotalRecordCount'))
        # Views may ignore StartIndex/Limit; locally slice its bounded list.
        if root:
            if total != len(rows):
                raise PanError('PAN_REPLY_INVALID')
            rows = rows[offset:offset + size]
        if len(rows) != min(size, max(0, total - offset)):
            raise PanError('PAN_REPLY_INVALID')
        if offset > total or len({_id(row.get('Id')) for row in rows}) != len(rows):
            raise PanError('PAN_REPLY_INVALID')
        return rows, total

    def season_episode_page(self, season_id, page, size):
        """Paginated season episode listing explicitly ordered by ParentIndexNumber,IndexNumber,SortName."""
        return self.page_rows('folder:' + _id(season_id), page, size, display=True, episode_order=True)

    def season_episodes_from(self, series_id, season_id, start_item_id, size=20):
        """Targeted Emby episode slice starting at start_item_id in season episode order."""
        if self.provider != 'emby':
            raise PanError('PAN_PROVIDER_INVALID')
        page_number(1, size)
        sid, seas_id, start_id = _id(series_id), _id(season_id), _id(start_item_id)
        query = dict(
            UserId=self.saved['user_id'],
            SeasonId=seas_id,
            StartItemId=start_id,
            Limit=size,
            EnableTotalRecordCount='true',
            Fields='Overview,Genres,ProductionYear,RunTimeTicks,UserData',
            EnableImageTypes='Primary',
            ImageTypeLimit=1,
        )
        value = self.session.request('/Shows/' + sid + '/Episodes', query=query)
        rows, total = _rows(value, 'Items'), number(value.get('TotalRecordCount'))
        if len(rows) != min(size, total) or len({_id(row.get('Id')) for row in rows}) != len(rows):
            raise PanError('PAN_REPLY_INVALID')
        return rows, total

    def list_files(self, parent='root', page=1, size=10):
        page_number(page, size)
        self._identity(user_scoped_read=True)
        offset = (page - 1) * size
        excluded = {}
        operation = getattr(self.session, 'operation', None)
        is_scan = operation is not None and operation.kind == 'scan'
        if parent.startswith('item:'):
            entry = _id(parent[5:])
            item = self._item(entry)
            rows, excluded = self._versions(entry, item)
            total = len(rows)
            items = rows[offset:offset + size]
        else:
            rows, total = self.page_rows(parent, page, size)
            items = [
                dict(
                    file_id=('folder:' if row.get('IsFolder') is True else 'item:') + _id(row.get('Id')),
                    name=text(row.get('Name')),
                    directory=True,
                    size=0,
                    **({'leaf_container': True} if is_scan and row.get('IsFolder') is not True else {}),
                )
                for row in rows
            ]
        if offset > total or len({row['file_id'] for row in items}) != len(items):
            raise PanError('PAN_REPLY_INVALID')
        if is_scan:
            verifier = getattr(operation, 'frontier_verifier', None)
            if callable(verifier):
                verifier(parent, items, page=page, size=size, total=total, has_more=offset + len(items) < total, from_adapter=True)
            elif not getattr(operation, 'frontier_managed', False):
                progress = getattr(operation, '_server_pages', {})
                previous, ids = progress.get(parent), {row['file_id'] for row in items}
                if previous and (previous[0] != total or previous[1] != offset or ids & previous[2]):
                    raise PanError('PAN_PAGE_EXPIRED')
                if offset + len(items) < total:
                    progress[parent] = (total, offset + len(items), ids | (previous[2] if previous else set()))
                else:
                    progress.pop(parent, None)
                operation._server_pages = progress
        result = dict(items=items, has_more=offset + len(items) < total)
        if is_scan:
            result['declared_total'] = total
        if excluded:
            result['excluded_versions'] = excluded
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

    def _playback_source(self, entry, mid, *, is_playback=False):
        # The actual PlaybackInfo response for this exact version must permit
        # a finite static file. Default support booleans are not mode selection.
        request = dict(
            UserId=self.saved['user_id'], MediaSourceId=mid, EnableDirectPlay=True,
            EnableDirectStream=False, EnableTranscoding=False, AutoOpenLiveStream=False)
        if self.provider == 'emby':
            request['IsPlayback'] = bool(is_playback)
        value = self.session.request('/Items/' + entry + '/PlaybackInfo', data=request)
        matching = [media for media in _rows(value, 'MediaSources') if media.get('Id') == mid]
        if len(matching) != 1 or matching[0].get('SupportsDirectPlay') is not True:
            raise PanError('PAN_MEDIA_UNSUPPORTED')
        if is_playback:
            psid = value.get('PlaySessionId')
            if psid is not None and (type(psid) is not str or len(psid) > 128 or any(ord(c) < 32 for c in psid)):
                raise PanError('PAN_REPLY_INVALID')
            return matching[0], (psid or '')
        return matching[0]

    def _probe_direct_media(self, item_id, media_id, *, authenticated=False, is_playback=False):
        if self.provider != 'emby':
            raise PanError('PAN_PROVIDER_INVALID')
        if type(authenticated) is not bool:
            raise PanError('PAN_ROUTE_REJECTED')
        entry, mid = _id(item_id), _id(media_id)
        self._identity()
        matching = [m for m in _rows(self._item(entry), 'MediaSources') if m.get('Id') == mid]
        if len(matching) != 1:
            raise PanError('PAN_FILE_CHANGED')
        chosen = matching[0]
        play_session_id = ''
        if is_playback:
            current, play_session_id = self._playback_source(entry, mid, is_playback=True)
        else:
            current = self._playback_source(entry, mid)
        for media in (chosen, current):
            if (media.get('Protocol') not in ('Http', 'File') or media.get('IsInfiniteStream')
                    or media.get('RequiresOpening') or media.get('RequiredHttpHeaders')
                    or media.get('VideoType', 'VideoFile') != 'VideoFile' or media.get('LiveStreamId')):
                raise PanError('PAN_MEDIA_UNSUPPORTED')
        if chosen.get('Protocol') != current['Protocol'] or chosen.get('Path') != current.get('Path'):
            raise PanError('PAN_FILE_CHANGED')
        if authenticated and (current['Protocol'] != 'File' or
                str(current.get('Path', '')).lower().startswith(('http:', 'https:'))):
            # The server's custom HTTP path is never a target for an account credential.
            raise PanError('PAN_MEDIA_UNSUPPORTED')
        if current['Protocol'] == 'Http':
            url = current.get('Path')
            # Even a short-lived server/CDN signature would appear in a generic Kodi log.
            if type(url) is not str or not at_origin(self.session.base, url) or urlsplit(url).query:
                raise PanError('PAN_EMBY_DIRECT_AUTH_REQUIRED')
            path = unquote(urlsplit(url).path)
            if ('%' in path or any(c in path for c in ('|', '?', '#', '\\', '\r', '\n')) or
                    path.lower().endswith(('.strm', '.m3u', '.m3u8', '.mpd', '.ism'))):
                raise PanError('PAN_MEDIA_UNSUPPORTED')
        else:
            url = static_original_url(self.session.base, entry, mid)
        # Prevent sending a token as a URI to either the probe or Kodi logs.
        if self.saved.get('token') and self.saved['token'] in unquote(url):
            # A File may prompt only for an actual anonymous 401/403, never a malformed URL.
            raise PanError('PAN_MEDIA_UNSUPPORTED' if current['Protocol'] == 'File'
                           else 'PAN_EMBY_DIRECT_AUTH_REQUIRED')
        size, mime = self.session.probe_media(url, authenticated=authenticated)
        for declared in (chosen.get('Size'), current.get('Size')):
            if declared is not None and number(declared, 1) != size:
                raise PanError('PAN_FILE_CHANGED')
        return url, mime, play_session_id

    def direct_original(self, item_id, media_id, *, authenticated=False):
        """One selection and probe. No streaming proxy or credentials in the returned URL."""
        url, mime, _ = self._probe_direct_media(item_id, media_id, authenticated=authenticated, is_playback=False)
        return dict(url=url, mime=mime)

    def open_playback_session(self, item_id, media_id, *, authenticated=False):
        """Explicit playback session inquiry (IsPlayback=True) + finite direct probe."""
        url, mime, play_session_id = self._probe_direct_media(
            item_id, media_id, authenticated=authenticated, is_playback=True)
        return dict(url=url, mime=mime, play_session_id=play_session_id)

    def set_played(self, item_id, played):
        """Explicit manual/EOF played toggle on server UserData."""
        if self.provider != 'emby':
            raise PanError('PAN_PROVIDER_INVALID')
        if type(played) is not bool:
            raise PanError('PAN_ROUTE_REJECTED')
        entry = _id(item_id)
        self._identity()
        self.session.request(
            '/Users/' + self.saved['user_id'] + '/PlayedItems/' + entry,
            method='POST' if played else 'DELETE',
            success_statuses=(200, 204),
            empty_response=True,
        )
        return dict(ok=True, item_id=entry, played=played)

    def set_favorite(self, item_id, favorite):
        """Explicit manual favorite toggle on server UserData."""
        if self.provider != 'emby':
            raise PanError('PAN_PROVIDER_INVALID')
        if type(favorite) is not bool:
            raise PanError('PAN_ROUTE_REJECTED')
        entry = _id(item_id)
        self._identity()
        self.session.request(
            '/Users/' + self.saved['user_id'] + '/FavoriteItems/' + entry,
            method='POST' if favorite else 'DELETE',
            success_statuses=(200, 204),
            empty_response=True,
        )
        return dict(ok=True, item_id=entry, favorite=favorite)

    def resolve_original(self, selected):
        self._identity()
        entry, mid, part, _, count = parts(selected['file_id'])
        if mid != part or count != 1:
            raise PanError('PAN_MEDIA_UNSUPPORTED')
        media = self._playback_source(entry, mid)
        current, _ = self._versions(entry, self._item(entry))
        if current.count(selected) != 1 or self._file(entry, media) != selected:
            raise PanError('PAN_FILE_CHANGED')
        url = static_original_url(self.session.base, entry, mid)
        return dict(url=url, size=selected['size'], original=True, headers=self.session.headers())

    def read_progress(self, selected):
        """UserData belongs to the item, not the chosen MediaSource version."""
        from .server_progress import item_progress
        self._identity()
        entry, _, _, _, _ = parts(selected['file_id'])
        item = self._item(entry)
        matching, _ = self._versions(entry, item)
        if matching.count(selected) != 1:
            raise PanError('PAN_FILE_CHANGED')
        return item_progress(self.provider, entry, item)

    def resolve_gateway_http(self, item_id, media_id, *, is_playback=False):
        """Resolve Emby HTTP / RequiredHttpHeaders finite direct media for SourceStreams gateway (U09).

        Preserves exact server_id / user_id / item_id / media_source_id identity and signed queries,
        strips cross-origin server Referer, and explicitly rejects HLS/DASH/live/BDMV/untrusted headers.
        """
        from bobbi_core import t4
        from bobbi_core.library_contract import LibraryError
        from bobbi_core.source_endpoint import endpoint as media_endpoint
        from .source_media_http import _origin_key

        if self.provider != 'emby':
            raise PanError('PAN_PROVIDER_INVALID')
        entry, mid = _id(item_id), _id(media_id)
        self._identity()
        detail = self._item(entry)
        matching = [m for m in _rows(detail, 'MediaSources') if m.get('Id') == mid]
        if len(matching) != 1:
            raise LibraryError('SOURCE_STREAM_CHANGED')
        chosen = matching[0]
        play_session_id = ''
        if is_playback:
            current, play_session_id = self._playback_source(entry, mid, is_playback=True)
        else:
            current = self._playback_source(entry, mid)

        for media in (chosen, current):
            if media.get('IsInfiniteStream') or media.get('RequiresOpening') or media.get('LiveStreamId'):
                raise LibraryError('MEDIA_NOT_FINITE')
            vtype = media.get('VideoType', 'VideoFile')
            if vtype is not None and vtype != 'VideoFile':
                raise LibraryError('MEDIA_TYPE_UNSUPPORTED')
            container = str(media.get('Container') or '').strip().lower()
            if container in ('m3u8', 'hls', 'dash', 'mpd', 'ism'):
                raise LibraryError('MEDIA_NOT_FINITE')
            if container in ('bluray', 'bdmv', 'dvd', 'video_ts', 'strm'):
                raise LibraryError('MEDIA_TYPE_UNSUPPORTED')

        if chosen.get('Protocol') != current.get('Protocol') or chosen.get('Path') != current.get('Path'):
            raise LibraryError('SOURCE_STREAM_CHANGED')
        if current.get('Protocol') != 'Http':
            raise LibraryError('SOURCE_STREAM_INVALID')

        url = current.get('Path')
        if not isinstance(url, str) or not url.strip():
            raise LibraryError('SOURCE_HTTP_URL')
        if self.saved.get('token') and self.saved['token'] in unquote(url):
            raise LibraryError('MEDIA_AUTH')

        raw_path_lower = unquote(urlsplit(url).path).lower()
        if raw_path_lower.endswith(('.m3u', '.m3u8', '.mpd', '.ism', '.pls')):
            raise LibraryError('MEDIA_NOT_FINITE')
        if raw_path_lower.endswith(('.strm', '.bdmv', '.ifo')) or '/bdmv/' in raw_path_lower or '/video_ts/' in raw_path_lower:
            raise LibraryError('MEDIA_TYPE_UNSUPPORTED')

        checked_url = media_endpoint(url, 'SOURCE_HTTP_URL')
        raw_hdrs = current.get('RequiredHttpHeaders')
        if raw_hdrs is None:
            raw_hdrs = chosen.get('RequiredHttpHeaders')
        cleaned_headers = t4.validate_headers(raw_hdrs)
        if 'Referer' in cleaned_headers and _origin_key(cleaned_headers['Referer']) != _origin_key(checked_url):
            cleaned_headers.pop('Referer', None)

        declared_sizes = [number(d, 1) for d in (chosen.get('Size'), current.get('Size')) if d is not None]
        if len(set(declared_sizes)) > 1:
            raise LibraryError('SOURCE_STREAM_CHANGED')
        declared_size = declared_sizes[0] if declared_sizes else None
        title = text(detail.get('Name') or current.get('Name') or mid)
        return dict(
            url=checked_url,
            headers=cleaned_headers,
            title=title,
            declared_size=declared_size,
            play_session_id=play_session_id,
            server_id=self.saved['server_id'],
            user_id=self.saved['user_id'],
            item_id=entry,
            media_source_id=mid,
        )

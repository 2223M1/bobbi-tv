"""Emby as an online Kodi directory. No scanner, history writer or player owner."""
from urllib.parse import quote, urlencode
import time

from bobbi_core.library_contract import LibraryError
from bobbi_core.playback_request import SelectionChanged
from bobbi_core.server_ref import identifier
from .emby_session import TICKS_PER_SECOND, ticks_to_seconds
from .owned_playback import emby_source_scope, reserve_playback
from .pan_accounts import PanError
from .pan_tokens import page_number
from .paths import ProfileBinding
from .server_emby import Client, static_original_url

PAGE = 20
BASE = 'plugin://plugin.video.bobbi.library/?'
FOLDERS = {'Folder', 'CollectionFolder', 'BoxSet', 'Series', 'Season', 'UserView'}
LEAVES = {'Movie': 'movie', 'Episode': 'episode', 'Video': 'video', 'MusicVideo': 'musicvideo',
          'Trailer': 'video'}


def link(**params):
    return BASE + urlencode(params)


def clean(value, limit, fallback=''):
    if not isinstance(value, str):
        return fallback
    # Server strings are display text, never Kodi markup or built-in commands.
    return ''.join(c if ord(c) >= 32 else ' ' for c in value[:limit]).strip().replace('[', '［').replace(']', '］') or fallback


def _fmt_clock(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f'{hours:d}:{minutes:02d}:{secs:02d}'
    return f'{minutes:02d}:{secs:02d}'


def _user_state(row: dict) -> tuple[float, bool, bool, int]:
    data = row.get('UserData')
    if not isinstance(data, dict):
        return 0.0, False, False, 0
    played = bool(data.get('Played') is True)
    favorite = bool(data.get('IsFavorite') is True)
    ticks = data.get('PlaybackPositionTicks')
    raw_ticks = ticks if type(ticks) is int and ticks > 0 else 0
    resume_sec = ticks_to_seconds(raw_ticks) if (raw_ticks > 0 and not played) else 0.0
    return resume_sec, played, favorite, raw_ticks


def projection(row):
    ident = identifier(row.get('Id'))
    title = clean(row.get('Name'), 512)
    if not title:
        raise PanError('PAN_REPLY_INVALID')
    kind = row.get('Type')
    folder = row.get('IsFolder') is True or kind in FOLDERS
    if not folder and kind not in LEAVES:
        return None
    info = dict(title=title, mediatype=LEAVES.get(kind, {'Series': 'tvshow', 'Season': 'season'}.get(kind, 'video')))
    for field, key, maximum in [('ProductionYear', 'year', 9999), ('IndexNumber', 'episode', 99999),
                                ('ParentIndexNumber', 'season', 9999)]:
        value = row.get(field)
        if key in ('season', 'episode') and kind != 'Episode':
            continue
        if type(value) is int and 0 <= value <= maximum:
            info[key] = value
    plot = clean(row.get('Overview'), 4096)
    if plot:
        info['plot'] = plot
    if kind == 'Episode' and clean(row.get('SeriesName'), 512):
        info['tvshowtitle'] = clean(row['SeriesName'], 512)
    ticks = row.get('RunTimeTicks')
    if type(ticks) is int and 0 < ticks < 2**63:
        info['duration'] = ticks // TICKS_PER_SECOND
    genres = row.get('Genres')
    if isinstance(genres, list):
        names = [clean(g, 80) for g in genres[:16] if isinstance(g, str)]
        if names:
            info['genre'] = names
    data = row.get('UserData')
    if isinstance(data, dict) and type(data.get('Played')) is bool:
        info['playcount'] = int(data['Played'])  # Display only; do not write a Kodi library row.
    tags = row.get('ImageTags')
    return ident, title, folder, info, tags.get('Primary') if type(tags) is dict else None


def _content_type(media_types: list[str]) -> str:
    unique = set(media_types)
    if len(unique) == 1:
        only = next(iter(unique))
        return {
            'movie': 'movies',
            'tvshow': 'tvshows',
            'season': 'seasons',
            'episode': 'episodes',
        }.get(only, 'videos')
    return 'videos'


def execute(handle, params, store, item):
    import xbmc
    import xbmcgui
    import xbmcplugin
    from . import runtime
    from .pan_ui import _failure
    binding, dialog = ProfileBinding(), xbmcgui.Dialog()
    action = params['action']
    play = action == 'emby_play'
    mark = action == 'emby_mark'
    from .optimization import observe
    started, outcome = time.monotonic(), None
    # Terminal callbacks are single-shot, including uncertain Kodi submissions.
    submitted = False

    def finish(ok=False):
        nonlocal submitted
        if not submitted:
            submitted = True
            if play:
                xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            elif not mark and handle >= 0:
                xbmcplugin.endOfDirectory(handle, succeeded=ok, cacheToDisc=False)

    try:
        root = binding.root()
        try:
            source, rev = store.source_snapshot(params.get('source', ''))
        except LibraryError as exc:
            raise PanError('PAN_ACCOUNT_CHANGED') from exc
        if (
            source.kind != 'media_server'
            or source.metadata.get('provider') != 'emby'
            or not source.password
        ):
            raise PanError('PAN_ACCOUNT_CHANGED')
        if action == 'browse':
            if set(params) != {'action', 'source'}:
                raise PanError('PAN_ROUTE_REJECTED')
        elif params.get('revision') != rev:
            raise PanError('PAN_ACCOUNT_CHANGED')

        saved = {
            'provider': 'emby',
            'location': source.location,
            'token': source.password,
            'server_id': source.metadata['server_id'],
            'user_id': source.metadata['user_id'],
        }
        emby_scope = emby_source_scope(
            source_id=source.id,
            generation=rev,
            server_id=saved['server_id'],
            user_id=saved['user_id'],
        )

        def is_current_source() -> bool:
            if xbmc.Monitor().abortRequested() or not binding.is_current():
                return False
            try:
                cur_src, cur_rev = store.source_snapshot(source.id)
                return cur_src == source and cur_rev == rev
            except LibraryError:
                return False

        def current():
            if not is_current_source():
                raise PanError('PAN_ACCOUNT_CHANGED')

        def route(act, **fields):
            return link(action=act, source=source.id, revision=rev, **fields)

        current()

        if mark:
            if set(params) != {'action', 'source', 'revision', 'id', 'op'}:
                raise PanError('PAN_ROUTE_REJECTED')
            entry = identifier(params['id'])
            op = params['op']
            if op not in ('played', 'unplayed', 'favorite', 'unfavorite'):
                raise PanError('PAN_ROUTE_REJECTED')
            call = runtime.bind_call(root / 'runtime.json')
            call('emby_user_state', {
                'source_scope': emby_scope,
                'item_id': entry,
                'operation': op,
            }, 12)
            current()
            submitted = True
            xbmc.executebuiltin('Container.Refresh')
            outcome = 'ok'
            return

        client = Client('emby', saved)
        rows = []
        if play:
            if set(params) - {'action', 'source', 'revision', 'id', 'resume_mode'} or 'id' not in params:
                raise PanError('PAN_ROUTE_REJECTED')
            resume_mode = params.get('resume_mode')
            if resume_mode is not None and resume_mode not in ('resume', 'start_over'):
                raise PanError('PAN_ROUTE_REJECTED')
            entry = identifier(params['id'])

            with reserve_playback(
                f'emby://{source.id}/{entry}',
                emby_scope,
                binding=binding,
                allow_starting=True,
            ) as reservation:
                with client.session.budget(12):
                    client._identity()
                    detail = client._item(entry)
                versions = detail.get('MediaSources')
                if not isinstance(versions, list) or not 1 <= len(versions) <= 256:
                    raise PanError('PAN_MEDIA_UNSUPPORTED')
                ids, labels = [], []
                for media in versions:
                    if type(media) is not dict:
                        raise PanError('PAN_REPLY_INVALID')
                    mid = identifier(media.get('Id'))
                    if mid in ids:
                        raise PanError('PAN_REPLY_INVALID')
                    ids.append(mid)
                    labels.append(clean(media.get('Name'), 160) or clean(media.get('Container'), 50) or '原片')
                labels = ['%d · %s' % (i + 1, label) for i, label in enumerate(labels)]
                current()
                reservation.require_current()
                index = 0 if len(ids) == 1 else dialog.select('选择 Emby 文件版本', labels)
                if not 0 <= index < len(ids):
                    return
                current()
                reservation.require_current()

                resume_sec, played_flag, _, raw_ticks = _user_state(detail)
                start_over = True
                chosen_resume = 0.0
                if resume_sec > 0:
                    if resume_mode == 'resume':
                        chosen_resume = resume_sec
                        start_over = False
                    elif resume_mode == 'start_over':
                        chosen_resume = 0.0
                        start_over = True
                    else:
                        pick_resume = dialog.select(
                            '选择播放起点',
                            [f'继续观看 ({_fmt_clock(resume_sec)})', '从头播放'],
                        )
                        if pick_resume not in (0, 1):
                            return
                        if pick_resume == 0:
                            chosen_resume = resume_sec
                            start_over = False

                current()
                reservation.require_current()
                resolve = runtime.bind_call(root / 'runtime.json')
                request = dict(
                    source_scope=emby_scope,
                    item_id=entry,
                    media_id=ids[index],
                    open_session=True,
                )
                options = '|redirect-limit=0'
                try:
                    result = resolve('pan_emby_direct', request, 28)
                except PanError as error:
                    if str(error) != 'PAN_EMBY_DIRECT_AUTH_REQUIRED' or versions[index].get('Protocol') != 'File':
                        raise
                    current()
                    reservation.require_current()
                    result = resolve('pan_emby_direct', dict(request, authenticated=True), 28)
                    # Only the canonical, verified original can receive this header.
                    # Neither the plugin URL, local RPC nor server query contains the token.
                    if result['url'] != static_original_url(saved['location'], entry, ids[index]):
                        raise PanError('PAN_DOWNLOAD_ORIGIN_REJECTED')
                    options += '&!X-Emby-Token=' + quote(saved['token'], safe='')

                proj = projection(detail)
                title = proj[1] if proj else clean(detail.get('Name'), 512, 'Emby')
                info = proj[3] if proj else {'title': title, 'mediatype': 'video'}
                art_dict = {}
                if proj and proj[4]:
                    from .emby_artwork import poster_factory
                    art_url = poster_factory(root, source.id, rev, store)(entry, proj[4])
                    if art_url:
                        art_dict = {'poster': art_url, 'thumb': art_url}

                next_spec = None
                if (
                    detail.get('Type') == 'Episode'
                    and isinstance(detail.get('SeasonId'), str)
                    and detail.get('SeasonId')
                    and type(detail.get('ParentIndexNumber')) is int
                    and type(detail.get('IndexNumber')) is int
                ):
                    try:
                        season_id = identifier(detail['SeasonId'])
                        next_spec = {
                            'resolver': 'emby_same_season',
                            'profile_root': str(root),
                            'season_id': season_id,
                            'season': detail['ParentIndexNumber'],
                            'episode': detail['IndexNumber'],
                        }
                    except ValueError:
                        next_spec = None

                source_meta = {
                    'provider': 'emby',
                    'server_id': saved['server_id'],
                    'user_id': saved['user_id'],
                    'source_id': source.id,
                    'source_generation': rev,
                    'item_id': entry,
                    'media_source_id': ids[index],
                    'play_session_id': str(result.get('play_session_id') or ''),
                    'initial_ticks': str(raw_ticks),
                    'initial_played': '1' if played_flag else '0',
                }
                reservation.submit(
                    handle,
                    result['url'] + options,
                    title=title,
                    source_meta=source_meta,
                    info=info,
                    art=art_dict,
                    mime=result['mime'],
                    resume_offset=chosen_resume,
                    start_over=start_over,
                    next_candidate=next_spec,
                    ready=is_current_source,
                )
                submitted = True
                outcome = 'handoff'  # Kodi accepted the URL; AV_START proves actual playback.
                return

        if set(params) - {'action', 'source', 'revision', 'parent', 'page', 'term'}:
            raise PanError('PAN_ROUTE_REJECTED')
        parent = params.get('parent', 'root')
        page = int(params.get('page', '1'))
        page_number(page, PAGE)
        term = params.get('term', '')
        if action == 'emby_search':
            term = dialog.input('搜索 Emby 电影、剧集或单集').strip()
            if not term:
                return
            parent = 'search'
        if parent == 'search' and not 1 <= len(term) <= 120 or term and parent != 'search':
            raise PanError('PAN_ROUTE_REJECTED')
        query = {'root': 'root', 'recent': 'view:recent', 'resume': 'view:resume', 'search': 'view:search:' + term}.get(parent)
        if query is None:
            if not parent.startswith('folder:'):
                raise PanError('PAN_ROUTE_REJECTED')
            query = 'folder:' + identifier(parent[7:])
        with client.session.budget(15):
            client._identity(user_scoped_read=True)
            page_rows, total = client.page_rows(query, page, PAGE, display=True)
        if parent == 'root' and page == 1:
            rows += [item('最近新增', route('emby_page', parent='recent')),
                     item('服务器的继续观看', route('emby_page', parent='resume')),
                     item('搜索 Emby', route('emby_search'))]
        from .emby_artwork import poster_factory
        poster = poster_factory(root, source.id, rev, store)
        media_types = []
        for record in page_rows:
            data = projection(record)
            if data is None:
                continue
            ident, title, folder, info, tag = data
            media_types.append(info.get('mediatype', 'video'))
            resume_sec, played_flag, fav_flag, _ = _user_state(record)
            label2_parts = []
            if fav_flag:
                label2_parts.append('已收藏')
            if resume_sec > 0:
                label2_parts.append('继续 ' + _fmt_clock(resume_sec))
            elif played_flag and not folder:
                label2_parts.append('已看')
            target = route('emby_page', parent='folder:' + ident) if folder else route('emby_play', id=ident)
            props = {}
            if resume_sec > 0:
                props['ResumeTime'] = str(int(resume_sec))
                if info.get('duration'):
                    props['TotalTime'] = str(int(info['duration']))
                props['Bobbi.Emby.ResumeSeconds'] = str(int(resume_sec))
            if fav_flag:
                props['Bobbi.Emby.Favorite'] = 'true'
            row = item(title, target, folder, label2=' · '.join(label2_parts), properties=props or None)
            row[1].setInfo('video', info)
            art = poster(ident, tag) if tag else ''
            if art:
                row[1].setArt({'poster': art, 'thumb': art})
            if hasattr(row[1], 'addContextMenuItems'):
                ctx = []
                if not folder and resume_sec > 0:
                    ctx.append(('从头播放', f'PlayMedia({route("emby_play", id=ident, resume_mode="start_over")})'))
                if not folder or record.get('Type') in ('Series', 'Season'):
                    ctx.append((
                        '标记为未看' if played_flag else '标记为已看',
                        f'RunPlugin({route("emby_mark", id=ident, op="unplayed" if played_flag else "played")})',
                    ))
                    ctx.append((
                        '取消 Emby 收藏' if fav_flag else '加入 Emby 收藏',
                        f'RunPlugin({route("emby_mark", id=ident, op="unfavorite" if fav_flag else "favorite")})',
                    ))
                if ctx:
                    row[1].addContextMenuItems(ctx)
            rows.append(row)
        if page * PAGE < total:
            fields = dict(parent=parent, page=page + 1)
            if term:
                fields['term'] = term
            rows.append(item('下一页', route('emby_page', **fields), properties={'Bobbi.NextPage': 'true'}))
        current()
        try:
            runtime.bind_call(root / 'runtime.json')(
                'emby_invalidation_status',
                {'source_id': source.id, 'generation': rev, 'confirm': True},
                1.0,
            )
        except Exception:
            pass
        xbmcplugin.setPluginCategory(handle, source.name + ' · Emby')
        xbmcplugin.setContent(handle, 'videos' if parent == 'root' else _content_type(media_types))
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        finish(True)
        outcome = 'ok'
    except SelectionChanged:
        outcome = 'changed'
    except (LibraryError, PanError, ValueError, OSError, RuntimeError) as error:
        outcome = {'PAN_ACCOUNT_CHANGED': 'changed', 'PAN_AUTH_REQUIRED': 'auth',
                   'PAN_SERVER_UNAUTHORIZED': 'auth',
                   'PAN_MEDIA_UNSUPPORTED': 'unsupported', 'PAN_NETWORK_ERROR': 'unavailable'}.get(str(error), 'failed')
        if isinstance(error, PanError):
            dialog.ok('Emby', _failure(error))
        else:
            dialog.ok('Emby', '连接、账号或所选内容已变化，请返回片库重试。')
    finally:
        finish()
        if outcome is not None:
            observe(binding.root(), 'emby_play' if play else ('emby_mark' if mark else 'emby_browse'), outcome, started)

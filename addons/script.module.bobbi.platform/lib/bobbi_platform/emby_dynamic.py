"""Emby as an online Kodi directory. No scanner, history writer or player owner."""
from hashlib import sha256
from urllib.parse import quote, urlencode
import time

from bobbi_core.library_contract import LibraryError
from bobbi_core.playback_request import SelectionChanged
from bobbi_core.server_ref import identifier
from .emby_session import TICKS_PER_SECOND, ticks_to_seconds
from .i18n import is_english
from .owned_playback import emby_source_scope, reserve_playback
from .pan_accounts import PanError
from .pan_tokens import page_number
from .paths import ProfileBinding
from .server_emby import Client, static_original_url

PAGE = 20
MAX_PAGE = 10000
HOME_RAIL_TOTAL_BUDGET_SECONDS = 6.0
HOME_SOURCE_MAX_BUDGET_SECONDS = 4.5
BASE = 'plugin://plugin.video.bobbi.library/?'
FOLDERS = {'Folder', 'CollectionFolder', 'BoxSet', 'Series', 'Season', 'UserView'}
LEAVES = {'Movie': 'movie', 'Episode': 'episode', 'Video': 'video', 'MusicVideo': 'musicvideo',
          'Trailer': 'video'}


def _t(zh_text: str, en_text: str) -> str:
    return en_text if is_english() else zh_text


def link(**params):
    return BASE + urlencode(params)


def clean(value, limit, fallback=''):
    if not isinstance(value, str):
        return fallback
    # Server strings are display text, never Kodi markup or built-in commands.
    return ''.join(c if ord(c) >= 32 else ' ' for c in value[:limit]).strip().replace('[', '［').replace(']', '］') or fallback


def version_labels(versions):
    """Distinguish only otherwise identical labels, using this item response."""
    names, facts = [], []
    for media in versions:
        name = clean(media.get('Name'), 160) or clean(media.get('Container'), 50) or _t('原片', 'Original')
        names.append(name)
        tracks = media.get('MediaStreams')
        tracks = [t for t in tracks[:256] if isinstance(t, dict)] if isinstance(tracks, list) else []
        video = next((t for t in tracks if t.get('Type') == 'Video'), {})
        width, height = video.get('Width'), video.get('Height')
        resolution = (f'{width}×{height}' if all(type(v) is int and 0 < v <= 32768 for v in (width, height)) else '')
        ticks = media.get('RunTimeTicks')
        duration = _fmt_clock(ticks / TICKS_PER_SECOND) if type(ticks) is int and 0 < ticks < TICKS_PER_SECOND * 864000 else ''
        langs = ', '.join(dict.fromkeys(clean(t.get('Language'), 16) for t in tracks
                            if t.get('Type') == 'Audio' and clean(t.get('Language'), 16)))
        facts.append((resolution, duration, langs, clean(video.get('Codec'), 16).upper(),
                      clean(media.get('Container'), 16).upper()))
    labels = list(names)
    for i, name in enumerate(names):
        peers = [j for j, n in enumerate(names) if j != i and n.casefold() == name.casefold()]
        parts = []
        for col, v in enumerate(facts[i]):
            if not peers:
                break
            if v and any(facts[j][col] != v for j in peers):
                if v.casefold() != name.casefold():
                    parts.append(v)
                peers = [j for j in peers if facts[j][col] == v]
        labels[i] = ' · '.join([name] + parts)
    return ['%d · %s' % (i + 1, label) for i, label in enumerate(labels)]


def menu_account(store, source):
    """An alias is display only. Scope the existing write to the card's source."""
    import re
    from bobbi_core.library_labels import visible_name
    if not callable(getattr(store, 'sources', None)):
        return ''
    server = source.metadata.get('server_id')
    accounts = sorted((s for s in store.sources() if server and s.kind == 'media_server'
        and s.metadata.get('provider') == 'emby' and s.metadata.get('server_id') == server
        and s.metadata.get('user_id') and s.password), key=lambda s:s.id)
    if len({s.metadata['user_id'] for s in accounts}) < 2:
        return ''
    def alias(s):
        name = visible_name(s.name)
        sensitive = [s.id, server, s.metadata.get('user_id')]
        if (not name or any(str(v).casefold() in name.casefold() for v in sensitive if v and len(str(v)) >= 6)
                or name in sensitive or re.search(r'(?:[\w-]+\.)+[a-zA-Z]{2,}|\d+\.\d+\.\d+\.\d+|[a-fA-F0-9]{16,}|:', name)):
            return ''
        return name[:60]
    name = alias(source)
    if name and sum(alias(s).casefold() == name.casefold() for s in accounts) == 1:
        return name
    n = next((i for i, s in enumerate(accounts, 1) if s.id == source.id), None)
    return _t(f'账号 {n}', f'Account {n}') if n else ''


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
    raw_ticks = ticks if type(ticks) is int and 0 < ticks < 2**63 else 0
    duration = row.get('RunTimeTicks')
    within_file = not (type(duration) is int and duration > 0 and raw_ticks >= duration)
    resume_sec = ticks_to_seconds(raw_ticks) if (raw_ticks and not played and within_file) else 0.0
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


def _profile_tag(root):
    # A display-route fence, not a credential; the actual registered account is still revalidated.
    return sha256(str(root).encode('utf-8')).hexdigest()


def _card_playback(record, projected, source, revision, profile_tag, *, resume_on_open=False):
    """Read-only actions for this Emby item. Routes recheck profile, source and version on use."""
    ident, _, folder, info, _ = projected
    seconds, played, favorite, _ = _user_state(record)
    versions = record.get('MediaSources')
    single = False
    if isinstance(versions, list) and len(versions) == 1 and isinstance(versions[0], dict):
        try:
            single = bool(identifier(versions[0].get('Id')))
        except ValueError:
            pass
    can_resume = not folder and seconds > 0 and single
    fields = dict(source=source.id, revision=revision, profile=profile_tag)
    target = (link(action='emby_page', parent='folder:' + ident, **fields) if folder else
              link(action='emby_play', id=ident, **fields,
                   **({'resume_mode': 'resume'} if resume_on_open and can_resume else {})))
    props = {'Bobbi.Emby.Authority': 'emby_server', 'Bobbi.Emby.SourceId': source.id,
             'Bobbi.Emby.SourceName': source.name}
    if favorite:
        props['Bobbi.Emby.Favorite'] = 'true'
    label = ''
    if not folder and seconds > 0:
        label = (_t('继续 ', 'Resume ') if can_resume else _t('服务器条目进度 · ', 'Server item progress · ')) + _fmt_clock(seconds)
        if can_resume:
            duration = info.get('duration', 0)
            props.update(ResumeTime=str(int(seconds)), PercentPlayed=str(max(1, min(99, round(100*seconds/duration))) if duration else 1))
            props['Bobbi.Emby.ResumeSeconds'] = props['ResumeTime']
            if duration:
                props['TotalTime'] = str(duration)
    elif not folder and played:
        label = _t('已看', 'Watched')
    return target, label, props, can_resume, played, favorite


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
    notice_only = action in ('emby_limit_notice', 'emby_jump')
    from .optimization import observe
    started, outcome = time.monotonic(), None
    # Terminal callbacks are single-shot in finally; failures stay succeeded=False.
    submitted = False
    succeeded = False
    confirm_sync = False
    read_revision = None
    root = None

    try:
        root = binding.root()
        profile_tag = _profile_tag(root)
        if 'profile' in params:
            params = dict(params)
            if params.pop('profile') != profile_tag:
                raise PanError('PAN_ACCOUNT_CHANGED')
        try:
            if action == 'browse':
                if set(params) != {'action', 'source'}:
                    raise PanError('PAN_ROUTE_REJECTED')
                source, rev = store.source_snapshot(params.get('source', ''))
            elif hasattr(store, 'source_session_snapshot'):
                req_rev = params.get('revision', '')
                source, matched = store.source_session_snapshot(params.get('source', ''), req_rev)
                if not matched:
                    raise PanError('PAN_ACCOUNT_CHANGED')
                _, rev = store.source_snapshot(source.id)
            else:
                req_rev = params.get('revision', '')
                source, rev = store.source_snapshot(params.get('source', ''))
                if req_rev != rev:
                    raise PanError('PAN_ACCOUNT_CHANGED')
        except LibraryError as exc:
            raise PanError('PAN_ACCOUNT_CHANGED') from exc
        if (
            source.kind != 'media_server'
            or source.metadata.get('provider') != 'emby'
            or not source.password
        ):
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
                if hasattr(store, 'source_session_snapshot'):
                    cur_src, ok = store.source_session_snapshot(source.id, rev)
                    return ok and cur_src == source
                cur_src, cur_rev = store.source_snapshot(source.id)
                return cur_src == source and cur_rev == rev
            except LibraryError:
                return False

        def current():
            if not is_current_source():
                raise PanError('PAN_ACCOUNT_CHANGED')

        def route(act, **fields):
            return link(action=act, source=source.id, revision=rev, profile=profile_tag, **fields)

        current()

        if action == 'emby_limit_notice':
            if set(params) - {'action', 'source', 'revision'}:
                raise PanError('PAN_ROUTE_REJECTED')
            submitted = True
            dialog.ok(
                'Emby',
                _t(
                    '当前单次平铺列表已达上限（前 10,000 页 / 200,000 项）。\n请使用「搜索 Emby」输入更精确的关键词，或从媒体库按「剧集 → 季」分级进入浏览完整内容。',
                    'Reached the single flat-list browse cap (first 10,000 pages / 200,000 items).\nUse "Search Emby" with a narrower keyword, or browse via Library -> Series -> Season to reach all items.',
                ),
            )
            outcome = 'ok'
            return

        if action == 'emby_jump':
            if set(params) - {'action', 'source', 'revision', 'parent', 'term', 'max_page'}:
                raise PanError('PAN_ROUTE_REJECTED')
            j_parent = params.get('parent', 'root')
            j_term = params.get('term', '')
            if j_parent == 'search' and not 1 <= len(j_term) <= 120 or j_term and j_parent != 'search':
                raise PanError('PAN_ROUTE_REJECTED')
            if j_parent not in ('root', 'recent', 'resume', 'search'):
                if not j_parent.startswith('folder:'):
                    raise PanError('PAN_ROUTE_REJECTED')
                j_parent = 'folder:' + identifier(j_parent[7:])
            try:
                max_allowed = min(MAX_PAGE, max(1, int(params.get('max_page', str(MAX_PAGE)))))
            except ValueError as exc:
                raise PanError('PAN_ROUTE_REJECTED') from exc
            submitted = True
            prompt_lbl = _t(f'输入要跳转的页码 (1 - {max_allowed})', f'Enter Page Number (1 - {max_allowed})')
            raw_page = (
                dialog.numeric(0, prompt_lbl)
                if hasattr(dialog, 'numeric')
                else dialog.input(prompt_lbl)
            )
            raw_str = str(raw_page or '').strip()
            if not raw_str:
                return
            if not raw_str.isdigit() or not (1 <= int(raw_str) <= max_allowed):
                dialog.ok('Emby', _t(f'请输入 1 到 {max_allowed} 之间的有效页码。', f'Please enter a valid page between 1 and {max_allowed}.'))
                return
            current()
            j_fields = dict(parent=j_parent, page=int(raw_str))
            if j_term:
                j_fields['term'] = j_term
            xbmc.executebuiltin(f'Container.Update("{route("emby_page", **j_fields)}")')
            outcome = 'ok'
            return

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
                ids = []
                for media in versions:
                    if type(media) is not dict:
                        raise PanError('PAN_REPLY_INVALID')
                    mid = identifier(media.get('Id'))
                    if mid in ids:
                        raise PanError('PAN_REPLY_INVALID')
                    ids.append(mid)
                labels = version_labels(versions)
                current()
                reservation.require_current()
                index = 0 if len(ids) == 1 else dialog.select(_t('选择 Emby 文件版本', 'Select Emby Media Version'), labels)
                if not 0 <= index < len(ids):
                    return
                current()
                reservation.require_current()

                resume_sec, played_flag, _, raw_ticks = _user_state(detail)
                start_over = True
                chosen_resume = 0.0
                if resume_sec > 0:
                    if resume_mode == 'resume' and len(ids) == 1:
                        chosen_resume = resume_sec
                        start_over = False
                    elif resume_mode == 'start_over':
                        chosen_resume = 0.0
                        start_over = True
                    else:
                        pick_resume = dialog.select(
                            (_t('所选版本：', 'Selected version: ') + labels[index] if len(ids) > 1 else _t('选择播放起点', 'Choose Playback Start')),
                            [
                                _t(f'继续观看 ({_fmt_clock(resume_sec)})', f'Resume from {_fmt_clock(resume_sec)}'),
                                _t('从头播放', 'Play from Start'),
                            ],
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
                    protocol = versions[index].get('Protocol')
                    if protocol == 'Http' and str(error) in ('PAN_EMBY_DIRECT_AUTH_REQUIRED', 'PAN_MEDIA_UNSUPPORTED'):
                        from .source_streams import open_emby_http_gateway_playback
                        result = open_emby_http_gateway_playback(
                            reservation, dialog, root,
                            source_id=source.id, generation=rev,
                            server_id=saved['server_id'], user_id=saved['user_id'],
                            item_id=entry, media_source_id=ids[index],
                            require_current=lambda: bool(current() or True), open_session=True,
                        )
                        if result is None:
                            return
                        options = ''
                        if result.get('identity_mode') == 'weak_session':
                            start_over, chosen_resume = True, 0.0
                    elif str(error) != 'PAN_EMBY_DIRECT_AUTH_REQUIRED' or protocol != 'File':
                        raise
                    else:
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
                        if isinstance(detail.get('SeriesId'), str) and detail.get('SeriesId'):
                            next_spec['series_id'] = identifier(detail['SeriesId'])
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
        try:
            snapshot = runtime.bind_call(root / 'runtime.json')(
                'emby_invalidation_status', {'source_id': source.id, 'generation': rev}, 1.0)
            value = snapshot.get('revision') if isinstance(snapshot, dict) else None
            if type(value) is int and value >= 0:
                read_revision = value
        except Exception:
            pass  # Browsing still works without a running Host; no false acknowledgement.
        parent = params.get('parent', 'root')
        page = int(params.get('page', '1'))
        page_number(page, PAGE)
        term = params.get('term', '')
        if action == 'emby_search':
            term = dialog.input(_t('搜索 Emby 电影、剧集或单集', 'Search Emby Movies, Series, or Episodes')).strip()
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
            rows += [item(_t('最近新增', 'Recently Added'), route('emby_page', parent='recent')),
                     item(_t('服务器的继续观看', 'Continue Watching (Server)'), route('emby_page', parent='resume')),
                     item(_t('搜索 Emby', 'Search Emby'), route('emby_search'))]
        from .emby_artwork import poster_factory
        poster = poster_factory(root, source.id, rev, store)
        media_types = []
        account_label = menu_account(store, source)
        for record in page_rows:
            data = projection(record)
            if data is None:
                continue
            ident, title, folder, info, tag = data
            media_types.append(info.get('mediatype', 'video'))
            target, status, props, can_resume, played_flag, fav_flag = _card_playback(record, data, source, rev, profile_tag)
            label2_parts = ([_t('已收藏', 'Favorite')] if fav_flag else []) + ([status] if status else [])
            row = item(title, target, folder, label2=' · '.join(label2_parts), properties=props or None)
            row[1].setInfo('video', info)
            art = poster(ident, tag) if tag else ''
            if art:
                row[1].setArt({'poster': art, 'thumb': art})
            if hasattr(row[1], 'addContextMenuItems'):
                ctx = []
                if can_resume:
                    ctx.append((_t('从头播放', 'Play from Start'), f'PlayMedia({route("emby_play", id=ident, resume_mode="start_over")})'))
                if not folder or record.get('Type') in ('Series', 'Season'):
                    ctx.append((
                        (_t(f'标记 {account_label} 未看', f'Mark Unwatched for {account_label}') if played_flag else
                         _t(f'标记 {account_label} 已看', f'Mark Watched for {account_label}')) if account_label else
                        (_t('标记为未看', 'Mark as Unwatched') if played_flag else _t('标记为已看', 'Mark as Watched')),
                        f'RunPlugin({route("emby_mark", id=ident, op="unplayed" if played_flag else "played")})',
                    ))
                    ctx.append((
                        (_t(f'从 {account_label} 的收藏中移除', f'Remove from Favorites for {account_label}') if fav_flag else
                         _t(f'加入 {account_label} 的收藏', f'Add to Favorites for {account_label}')) if account_label else
                        (_t('取消 Emby 收藏', 'Remove Emby Favorite') if fav_flag else _t('加入 Emby 收藏', 'Add to Emby Favorites')),
                        f'RunPlugin({route("emby_mark", id=ident, op="unfavorite" if fav_flag else "favorite")})',
                    ))
                if ctx:
                    row[1].addContextMenuItems(ctx)
            rows.append(row)
        if page * PAGE < total:
            if page < MAX_PAGE:
                fields = dict(parent=parent, page=page + 1)
                if term:
                    fields['term'] = term
                total_pages = (total + PAGE - 1) // PAGE
                capped_pages = min(MAX_PAGE, total_pages)
                next_kwargs = {'properties': {'Bobbi.NextPage': 'true'}}
                if capped_pages >= 3:
                    next_kwargs['label2'] = _t(f'第 {page} / {capped_pages} 页', f'Page {page} / {capped_pages}')
                next_row = item(_t('下一页', 'Next Page'), route('emby_page', **fields), **next_kwargs)
                if capped_pages >= 3 and hasattr(next_row[1], 'addContextMenuItems'):
                    jump_fields = dict(parent=parent, max_page=capped_pages)
                    if term:
                        jump_fields['term'] = term
                    next_row[1].addContextMenuItems([
                        (
                            _t(f'跳转到指定页 (1-{capped_pages})...', f'Jump to Page (1-{capped_pages})...'),
                            f'RunPlugin({route("emby_jump", **jump_fields)})',
                        )
                    ])
                rows.append(next_row)
            else:
                rows.append(
                    item(
                        _t('已达单列表浏览上限（前 200,000 项）· 请缩小搜索或按剧集季浏览',
                           'Browse Limit Reached (First 200,000 Items) · Narrow Search or Browse by Season'),
                        route('emby_limit_notice'),
                        False,
                        playable=False,
                        properties={'Bobbi.LimitNotice': 'true'},
                    )
                )
        current()
        xbmcplugin.setPluginCategory(handle, source.name + ' · Emby')
        xbmcplugin.setContent(handle, 'videos' if parent == 'root' else _content_type(media_types))
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        succeeded = True
        confirm_sync = True
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
            dialog.ok('Emby', _t('连接、账号或所选内容已变化，请返回片库重试。', 'Connection, account, or selected item changed; return to library and retry.'))
    finally:
        if play:
            if not submitted:
                submitted = True
                xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        elif not mark and not notice_only and handle >= 0 and not submitted:
            submitted = True
            xbmcplugin.endOfDirectory(handle, succeeded=succeeded, cacheToDisc=False)
            if succeeded and confirm_sync and root is not None and read_revision is not None:
                try:
                    runtime.bind_call(root / 'runtime.json')(
                        'emby_invalidation_status',
                        {'source_id': source.id, 'generation': rev, 'confirm': True,
                         'expected_revision': read_revision},
                        1.0,
                    )
                except Exception:
                    pass
        if outcome is not None:
            try:
                observe(root if root is not None else binding.root(),
                        'emby_play' if play else ('emby_mark' if mark else 'emby_browse'), outcome, started)
            except (OSError, ValueError, RuntimeError):
                pass


def execute_home_rail(handle: int, params: dict, *, registry_factory=None) -> None:
    """Populate Home Emby rails (`emby_resume` / `emby_recent`) with a single directory exit."""
    import xbmc
    import xbmcgui
    import xbmcplugin
    from .emby_artwork import poster_factory
    from .libraries import Registry
    from .optimization import observe

    started = time.monotonic()
    outcome = 'ok'
    succeeded = False
    root = None
    store = None
    rows = []
    media_types = []
    published_sources = []
    had_emby_source = False
    binding = ProfileBinding()

    def _aborted() -> bool:
        return bool(hasattr(xbmc, 'Monitor') and xbmc.Monitor().abortRequested())

    try:
        section = params.get('section', '')
        if section not in ('resume', 'recent'):
            return
        try:
            root = binding.root()
        except (OSError, ValueError, RuntimeError):
            return

        profile_tag = _profile_tag(root)
        reg_path = root / 'libraries.sqlite3'
        if not reg_path.is_file() and registry_factory is None:
            succeeded = True
            return

        store = registry_factory() if registry_factory is not None else Registry(reg_path, read_only=True, timeout=0.05)
        emby_sources = []
        for src in store.sources():
            if src.kind == 'media_server' and src.metadata.get('provider') == 'emby' and src.password:
                try:
                    snap_src, rev = store.source_snapshot(src.id)
                    emby_sources.append((snap_src, rev))
                except LibraryError:
                    continue
        if not emby_sources:
            succeeded = True
            return

        had_emby_source = True
        multi_source = len(emby_sources) > 1
        query = 'view:resume' if section == 'resume' else 'view:recent'
        per_source_limit = min(PAGE, max(4, PAGE // len(emby_sources)))
        rail_deadline = started + HOME_RAIL_TOTAL_BUDGET_SECONDS

        for source, rev in emby_sources:
            if len(rows) >= PAGE:
                break
            if _aborted() or not binding.is_current():
                rows = []
                media_types = []
                outcome = 'changed'
                break
            remaining_budget = rail_deadline - time.monotonic()
            if remaining_budget <= 0.25:
                outcome = 'unavailable'
                break
            saved = {
                'provider': 'emby',
                'location': source.location,
                'token': source.password,
                'server_id': source.metadata['server_id'],
                'user_id': source.metadata['user_id'],
            }
            client = Client('emby', saved)
            try:
                with client.session.budget(min(HOME_SOURCE_MAX_BUDGET_SECONDS, remaining_budget)):
                    client._identity(user_scoped_read=True)
                    page_rows, _ = client.page_rows(query, 1, PAGE, display=True)
            except (PanError, LibraryError, ValueError, OSError):
                outcome = 'unavailable'
                continue

            if _aborted() or not binding.is_current():
                rows = []
                media_types = []
                outcome = 'changed'
                break
            try:
                if store.source_snapshot(source.id) != (source, rev):
                    continue
            except LibraryError:
                continue

            poster = poster_factory(root, source.id, rev, store)
            added_for_source = 0
            for record in page_rows:
                if len(rows) >= PAGE or added_for_source >= per_source_limit:
                    break
                data = projection(record)
                if data is None:
                    continue
                ident, title, folder, info, tag = data
                media_types.append(info.get('mediatype', 'video'))
                target, status, props, _, _, _ = _card_playback(record, data, source, rev, profile_tag,
                    resume_on_open=section == 'resume')
                li = xbmcgui.ListItem(label=title)
                sub_parts = ([source.name] if multi_source else []) + ([status] if status else [])
                if sub_parts:
                    li.setLabel2(' · '.join(sub_parts))
                for k, v in props.items():
                    li.setProperty(k, v)
                if not folder:
                    li.setProperty('IsPlayable', 'true')
                    li.setInfo('video', dict({'size': -1}, **info))
                else:
                    li.setInfo('video', info)
                li.setContentLookup(False)
                art = poster(ident, tag) if tag else ''
                if art:
                    art_map = {'poster': art, 'thumb': art}
                    if section == 'resume':
                        art_map['landscape'] = art
                    li.setArt(art_map)
                else:
                    li.setArt({'icon': 'DefaultFolder.png' if folder else 'DefaultVideo.png'})
                rows.append((target, li, folder))
                added_for_source += 1
            if added_for_source:
                published_sources.append((source, rev, len(rows) - added_for_source, len(rows)))
        # A later slow source may span a profile switch or invalidate an earlier account.
        if not binding.is_current() or _aborted():
            outcome = 'changed'
        else:
            live_rows, live_types = [], []
            for source, rev, lo, hi in published_sources:
                try:
                    if store.source_snapshot(source.id) == (source, rev):
                        live_rows.extend(rows[lo:hi]); live_types.extend(media_types[lo:hi])
                except LibraryError:
                    continue
            rows, media_types = live_rows, live_types
            if not binding.is_current() or _aborted():
                outcome = 'changed'
        if outcome != 'changed':
            succeeded = True
    finally:
        if store is not None and registry_factory is None:
            store.close()
        if handle >= 0:
            if succeeded:
                if media_types:
                    xbmcplugin.setContent(handle, _content_type(media_types))
                xbmcplugin.addDirectoryItems(handle, rows, len(rows))
            xbmcplugin.endOfDirectory(handle, succeeded=succeeded, cacheToDisc=False)
        if had_emby_source and root is not None:
            observe(root, 'emby_browse', outcome, started)

"""Emby as an online Kodi directory. No scanner, history writer or player owner."""
from urllib.parse import quote, urlencode
import time

from bobbi_core.library_contract import LibraryError
from bobbi_core.server_ref import identifier
from .pan_accounts import PanError
from .pan_tokens import page_number
from .paths import ProfileBinding
from .server_accounts import Accounts
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


def projection(row):
    ident = identifier(row.get('Id'))
    title = clean(row.get('Name'), 512)
    if not title:
        raise PanError('PAN_REPLY_INVALID')
    kind = row.get('Type')
    folder = row.get('IsFolder') is True or kind in FOLDERS
    if not folder and kind not in LEAVES:
        return None
    info = dict(title=title, mediatype=LEAVES.get(kind, {'Series':'tvshow','Season':'season'}.get(kind, 'video')))
    for field, key, maximum in [('ProductionYear','year',9999), ('IndexNumber','episode',99999),
                                ('ParentIndexNumber','season',9999)]:
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
        info['duration'] = ticks // 10_000_000
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


def execute(handle, params, store, item):
    import xbmc
    import xbmcgui
    import xbmcplugin
    from .runtime import bind_call
    from .pan_ui import _failure
    binding, dialog = ProfileBinding(), xbmcgui.Dialog()
    action = params['action']
    play = action == 'emby_play'
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
            else:
                xbmcplugin.endOfDirectory(handle, succeeded=ok, cacheToDisc=False)
    try:
        root = binding.root()
        accounts = Accounts(root, current=binding.is_current)
        source, rev = store.source_snapshot(params['source'])
        if source.kind != 'media_server' or source.metadata.get('provider') != 'emby':
            raise PanError('PAN_ACCOUNT_CHANGED')
        active = accounts.snapshot('emby')
        if action == 'browse':
            if set(params) != {'action','source'}:
                raise PanError('PAN_ROUTE_REJECTED')
            if active.get('source_id') != source.id:
                if not dialog.yesno('切换 Emby 连接？', '打开「' + source.name + '」，之前连接的选片授权将失效。'):
                    return
                binding.require_current()
                active = bind_call(root / 'runtime.json')('pan_server_activate_emby', dict(
                    source_id=source.id, generation=rev, expected=active))
                rev = active['generation']
        elif active.get('source_id') != source.id or params.get('revision') != rev:
            raise PanError('PAN_ACCOUNT_CHANGED')
        if active.get('generation') != rev or not active.get('authenticated'):
            raise PanError('PAN_ACCOUNT_CHANGED')
        def current():
            if xbmc.Monitor().abortRequested() or not binding.is_current() or not accounts.is_current(active):
                raise PanError('PAN_ACCOUNT_CHANGED')
        def route(action, **fields):
            return link(action=action, source=source.id, revision=rev, **fields)
        current()
        client = Client('emby', accounts.credentials(active))
        rows = []
        if play:
            if set(params) != {'action','source','revision','id'}:
                raise PanError('PAN_ROUTE_REJECTED')
            entry = identifier(params['id'])
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
            index = 0 if len(ids) == 1 else dialog.select('选择 Emby 文件版本', labels)
            if not 0 <= index < len(ids):
                return
            current()
            resolve = bind_call(root / 'runtime.json')
            request = dict(expected=active, item_id=entry, media_id=ids[index])
            options = '|redirect-limit=0'
            try:
                result = resolve('pan_emby_direct', request, timeout=28)
            except PanError as error:
                if str(error) != 'PAN_EMBY_DIRECT_AUTH_REQUIRED' or versions[index].get('Protocol') != 'File':
                    raise
                current()
                result = resolve('pan_emby_direct', dict(request, authenticated=True), timeout=28)
                saved = accounts.credentials(active)
                # Only the canonical, verified original can receive this header.
                # Neither the plugin URL, local RPC nor server query contains the token.
                if result['url'] != static_original_url(saved['location'], entry, ids[index]):
                    raise PanError('PAN_DOWNLOAD_ORIGIN_REJECTED')
                options += '&!X-Emby-Token=' + quote(saved['token'], safe='')
            selected = xbmcgui.ListItem(path=result['url'] + options)
            selected.setContentLookup(False)
            selected.setMimeType(result['mime'])
            selected.setInfo('video', {'title': clean(detail.get('Name'), 512), 'mediatype': 'video'})
            current()
            def handoff():
                nonlocal submitted
                binding.require_current()
                submitted = True
                xbmcplugin.setResolvedUrl(handle, True, selected)
            accounts.run_if_current(active, handoff)
            outcome = 'handoff'  # Kodi accepted the URL; this is not playback-start proof.
            return
        if set(params) - {'action','source','revision','parent','page','term'}:
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
        query = {'root':'root','recent':'view:recent','resume':'view:resume','search':'view:search:' + term}.get(parent)
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
        for record in page_rows:
            data = projection(record)
            if data is None:
                continue
            ident, title, folder, info, tag = data
            target = route('emby_page', parent='folder:'+ident) if folder else route('emby_play', id=ident)
            row = item(title, target, folder)
            row[1].setInfo('video', info)
            art = poster(ident, tag) if tag else ''
            if art:
                row[1].setArt({'poster': art, 'thumb': art})
            rows.append(row)
        if page * PAGE < total:
            fields = dict(parent=parent, page=page+1)
            if term:
                fields['term'] = term
            rows.append(item('下一页', route('emby_page', **fields), properties={'Bobbi.NextPage':'true'}))
        current()
        xbmcplugin.setPluginCategory(handle, source.name + ' · Emby')
        xbmcplugin.setContent(handle, 'videos')
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        finish(True)
        outcome = 'ok'
    except (LibraryError, PanError, ValueError, OSError, RuntimeError) as error:
        outcome = {'PAN_ACCOUNT_CHANGED':'changed', 'PAN_AUTH_REQUIRED':'auth',
                   'PAN_MEDIA_UNSUPPORTED':'unsupported','PAN_NETWORK_ERROR':'unavailable'}.get(str(error), 'failed')
        if isinstance(error, PanError):
            dialog.ok('Emby', _failure(error))
        else:
            dialog.ok('Emby', '连接、账号或所选内容已变化，请返回片库重试。')
    finally:
        finish()
        if outcome is not None:
            observe(binding.root(), 'emby_play' if play else 'emby_browse', outcome, started)

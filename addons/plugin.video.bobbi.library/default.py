"""Unified user-library entrypoint. All writes affect bobbi local settings only."""
import sys
import json
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import uuid4
import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs
from bobbi_platform.library_ui import registry, message
from bobbi_platform.libraries import (LibraryError, MAX_DIRECTORY_ITEMS, directory_items,
                                      joined_path, relative_path)
from bobbi_platform.kodi import standard_handoff
from bobbi_platform.playback import selected_identity
from bobbi_platform.library_listing import source_presentation, native_listing, local_listing, file_info

PAGE_SIZE = 200
SELECTION = 'bobbi.portable_selection'


def route(**values):
    # Only local source IDs and relative item keys cross Kodi plugin URLs.
    return 'plugin://plugin.video.bobbi.library/?' + urlencode(values)


def item(label, target, folder=True, label2='', properties=None, info=None, *, playable=True):
    row = xbmcgui.ListItem(label=label)
    if label2:
        row.setLabel2(label2)
        # Kodi's native file window reapplies its %D secondary label mask.
        # Keep the location in a dedicated field too; do not abuse video tags
        # (production code / duration) or change native sorting to carry it.
        row.setProperty('Bobbi.Library.Location', label2)
    for key, value in (properties or {}).items():
        row.setProperty(key, value)
    if not folder and playable:
        # Kodi initializes size to zero. Unknown is -1, not a fabricated 0 B.
        row.setInfo('video', dict({'size': -1}, **(info or {})))
    row.setContentLookup(False)
    row.setArt({'icon': 'DefaultFolder.png' if folder or not playable else 'DefaultVideo.png'})
    if not folder:
        # Kodi executes nonfolder, nonplayable plugin items as script actions.
        # A modal menu is not a directory and must not cancel a fake listing.
        row.setProperty('IsPlayable', 'true' if playable else 'false')
    return target, row, folder


def listing_with_metadata(path):
    # Kodi already obtains size/date while listing SMB/NFS/WebDAV. A single
    # native listing replaces listdir + up to 200 separate remote Stat calls.
    if urlsplit(path).scheme not in ('smb', 'nfs', 'dav', 'davs'):
        try:
            return local_listing(path)
        except LibraryError:
            raise
        except OSError:
            pass
    try:
        response = json.loads(xbmc.executeJSONRPC(json.dumps(dict(jsonrpc='2.0', id=1,
            method='Files.GetDirectory', params=dict(directory=path, media='files',
                properties=['size', 'lastmodified'], limits=dict(start=0, end=MAX_DIRECTORY_ITEMS + 1))))))
        return native_listing(response, path)
    except LibraryError:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return directory_items(*xbmcvfs.listdir(path), pointers=True), {}


def execute(handle, params):
    action = params.get('action', 'root')
    handoff = None
    if action.startswith('mounted_'):
        from bobbi_platform.mounted_catalog_ui import execute as mounted_execute
        return mounted_execute(handle, params, item)
    if action == 'manage':
        xbmc.executebuiltin('RunScript(script.bobbi.setup,libraries)')
        if handle >= 0:  # Compatibility for previously saved folder URLs.
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
        return
    if action == 'native_files':
        from bobbi_platform.pan_ui import choose_files
        choose_files(xbmcgui.Dialog())
        if handle >= 0:
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
        return
    store = None
    try:
        store = registry(xbmcvfs.translatePath)
        rows = []
        category = '云盘与片库'
        if action == 'root':
            rows.append(item('管理片库来源', route(action='manage'), False, playable=False,
                             label2='连接云盘账号、CD2 挂载与局域网共享',
                             properties={'Bobbi.Library.Manage': 'true'}))
            for source in store.sources():
                kind, label2 = source_presentation(source)
                rows.append(item(source.name, route(action='browse', source=source.id),
                                 folder=(source.kind not in ('media_server', 't4') or
                                         source.metadata.get('provider') == 'emby'), playable=False,
                                 label2=label2, properties={'Bobbi.Library.Kind': kind}))
            rows.append(item('个人云盘', route(action='native_files'), False, playable=False,
                label2='浏览已连接的网盘，或使用已有 CD2 挂载',
                properties={'Bobbi.Library.Kind': 'native_pan'}))
            rows.append(item('影视海报库', 'plugin://plugin.video.bobbi/?action=personal_catalog',
                label2='已刮削电影、剧集与多版本片源',
                properties={'Bobbi.Library.Kind': 'personal_catalog'}))
        elif action in ('browse', 'play', 'play_pointer', 'emby_page', 'emby_play', 'emby_search'):
            source = store.get(params.get('source', ''))
            if action.startswith('emby_') or (action == 'browse' and source.kind == 'media_server'
                                              and source.metadata.get('provider') == 'emby'):
                from bobbi_platform.emby_dynamic import execute as online
                return online(handle, params, store, item)
            if source.kind == 't4':
                if action != 'browse' or set(params) != {'action', 'source'}:
                    raise LibraryError('INVALID_VALUE')
                from bobbi_platform.t4_ui import browse as browse_t4
                try:
                    browse_t4(xbmcgui.Dialog(), store, source)
                except LibraryError as error:
                    if error.code != 'T4_CANCELLED':
                        raise
                if handle >= 0:
                    xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
                return
            if source.kind == 'media_server':
                if action != 'browse' or set(params) - {'action', 'source'}:
                    raise LibraryError('INVALID_VALUE')
                from bobbi_platform.server_ui import browse as browse_server
                browse_server(xbmcgui.Dialog(), source)
                if handle >= 0:
                    xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
                return
            relative = relative_path(params.get('relative', ''))
            category = source.name + (' / ' + relative if relative else '')
            if action in ('play', 'play_pointer'):
                request = uuid4().hex
                xbmcgui.Window(10000).setProperty(SELECTION, request)
                revision = None
                if action == 'play_pointer':
                    from bobbi_platform.source_pointers import read
                    from bobbi_platform.source_streams import local_media_url
                    from bobbi_platform.runtime import bind_call
                    from bobbi_platform.paths import ProfileBinding
                    binding = ProfileBinding()
                    call = bind_call(binding.root() / 'runtime.json')
                    current, revision = store.source_snapshot(source.id)
                    if current != source:
                        raise LibraryError('SOURCE_STREAM_CHANGED')
                    target, observation = read(source, relative)
                    origin = urlsplit(target)
                    if not xbmcgui.Dialog().yesno('播放 STRM 指向的媒体？',
                            '将连接 ' + origin.scheme + '://' + origin.netloc + '，不会发送片库账号密码。'):
                        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
                        return
                    if not binding.is_current() or store.source_snapshot(source.id) != (source, revision):
                        raise LibraryError('SOURCE_STREAM_CHANGED')
                    result = call('source_stream_open', dict(source_id=source.id, generation=revision,
                        request_id=request, selection=dict(kind='strm', relative=relative, observation=observation)),
                        timeout=18)
                    url, title = local_media_url(result), relative.rsplit('/', 1)[-1][:-5]
                elif source.kind == 'catalog':
                    chosen = next((entry for entry in source.items if entry.id == params.get('entry')), None)
                    if chosen is None:
                        raise LibraryError('SOURCE_NOT_FOUND')
                    url, title = chosen.url, chosen.title
                else:
                    # A forged route must not invoke a script/.strm even if
                    # that file is present beneath a user-selected directory.
                    if not relative or not directory_items([], [relative.rsplit('/', 1)[-1]]):
                        raise LibraryError('INVALID_MEDIA_URL')
                    url, title = joined_path(source, relative), relative.rsplit('/', 1)[-1]
                identity = selected_identity(source.id + '\n' + url)
                def ready():
                    return (not xbmc.Monitor().abortRequested()
                            and xbmcgui.Window(10000).getProperty(SELECTION) == request
                            and (store.get(source.id) == source if revision is None else
                                 binding.is_current() and store.source_snapshot(source.id) == (source, revision)))
                handoff = standard_handoff(identity, handle, ready=ready)
                value = {'url': url, 'title': title}
                if action == 'play_pointer':
                    value['_bobbi_start_over'] = True
                result = handoff.submit(identity, value)
                if not result['opened']:
                    xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
                return
            try:
                offset = int(params.get('offset', '0'))
            except ValueError:
                raise LibraryError('INVALID_VALUE') from None
            if offset < 0 or offset >= MAX_DIRECTORY_ITEMS or offset % PAGE_SIZE:
                raise LibraryError('INVALID_VALUE')
            if source.kind == 'catalog':
                listing = source.items
                for entry in listing[offset:offset + PAGE_SIZE]:
                    label = entry.title + (' (%d)' % entry.year if entry.year else '')
                    rows.append(item(label, route(action='play', source=source.id, entry=entry.id), False,
                                     info=file_info(entry.size, entry.modified)))
            else:
                path = joined_path(source, relative)
                # Kodi's exists() treats slashless paths as files. Nested
                # folders must keep directory syntax, including local FUSE.
                if not path.endswith(('/', '\\')):
                    path += '\\' if '\\' in path else '/'
                if not xbmcvfs.exists(path):
                    raise LibraryError('SOURCE_UNAVAILABLE')
                listing, metadata = listing_with_metadata(path)
                for folder, name in listing[offset:offset + PAGE_SIZE]:
                    child = relative + '/' + name if relative else name
                    play_action = 'play_pointer' if name.lower().endswith('.strm') else 'play'
                    rows.append(item(name, route(action='browse' if folder else play_action,
                        source=source.id, relative=child), folder, info=metadata.get(name) if not folder else None))
            if len(listing) > offset + PAGE_SIZE:
                rows.append(item('下一页', route(action='browse', source=source.id, relative=relative,
                                               offset=offset + PAGE_SIZE), properties={'Bobbi.NextPage': 'true'}))
            if not listing:
                xbmcgui.Dialog().ok('没有找到视频', '目录可能为空或无法读取。请到“管理片库来源”检查连接。')
        else:
            raise LibraryError('INVALID_VALUE')
        if xbmc.Monitor().abortRequested():
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
            return
        xbmcplugin.setPluginCategory(handle, category)
        xbmcplugin.setContent(handle, 'files')
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    except (LibraryError, OSError, RuntimeError, ValueError):
        if action in ('play', 'play_pointer', 'emby_play') and (handoff is None or handoff.state in ('selected', 'cancelled')):
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        raise
    finally:
        if store is not None:
            store.close()


if __name__ == '__main__':
    handle = int(sys.argv[1])
    query = {}
    try:
        query = dict(parse_qsl(sys.argv[2].lstrip('?'), keep_blank_values=True, max_num_fields=8))
        execute(handle, query)
    except (LibraryError, OSError, RuntimeError, ValueError) as error:
        xbmc.log('[bobbi] library operation failed: ' + type(error).__name__, xbmc.LOGWARNING)
        xbmcgui.Dialog().ok('片库暂时不可用', message(error))
        # No alternate source or playback retry after an uncertain submission.
        if handle >= 0 and query.get('action') not in ('play', 'play_pointer', 'emby_play'):
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)

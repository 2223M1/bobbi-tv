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


def item(label, target, folder=True, label2='', properties=None, info=None):
    row = xbmcgui.ListItem(label=label)
    if label2:
        row.setLabel2(label2)
        # Kodi's native file window reapplies its %D secondary label mask.
        # Keep the location in a dedicated field too; do not abuse video tags
        # (production code / duration) or change native sorting to carry it.
        row.setProperty('Bobi.Library.Location', label2)
    for key, value in (properties or {}).items():
        row.setProperty(key, value)
    if not folder:
        # Kodi initializes size to zero. Unknown is -1, not a fabricated 0 B.
        row.setInfo('video', dict({'size': -1}, **(info or {})))
    row.setContentLookup(False)
    row.setArt({'icon': 'DefaultFolder.png' if folder else 'DefaultVideo.png'})
    if not folder:
        row.setProperty('IsPlayable', 'true')
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
        return directory_items(*xbmcvfs.listdir(path)), {}


def execute(handle, params):
    action = params.get('action', 'root')
    handoff = None
    if action == 'manage':
        xbmc.executebuiltin('RunScript(script.bobbi.setup,libraries)')
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
        return
    store = None
    try:
        store = registry(xbmcvfs.translatePath)
        rows = []
        category = '我的片库'
        if action == 'root':
            rows.append(item('管理片库来源', route(action='manage'),
                             properties={'Bobi.Library.Manage': 'true'}))
            for source in store.sources():
                kind, label2 = source_presentation(source)
                rows.append(item(source.name, route(action='browse', source=source.id),
                                 label2=label2, properties={'Bobi.Library.Kind': kind}))
        elif action in ('browse', 'play'):
            source = store.get(params.get('source', ''))
            relative = relative_path(params.get('relative', ''))
            category = source.name + (' / ' + relative if relative else '')
            if action == 'play':
                request = uuid4().hex
                xbmcgui.Window(10000).setProperty(SELECTION, request)
                if source.kind == 'catalog':
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
                            and store.get(source.id) == source)
                handoff = standard_handoff(identity, handle, ready=ready)
                result = handoff.submit(identity, {'url': url, 'title': title})
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
                    rows.append(item(name, route(action='browse' if folder else 'play',
                        source=source.id, relative=child), folder, info=metadata.get(name) if not folder else None))
            if len(listing) > offset + PAGE_SIZE:
                rows.append(item('下一页', route(action='browse', source=source.id, relative=relative,
                                               offset=offset + PAGE_SIZE), properties={'Bobi.NextPage': 'true'}))
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
        if action == 'play' and (handoff is None or handoff.state in ('selected', 'cancelled')):
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
        if query.get('action') != 'play':
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)

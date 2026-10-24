"""Kodi-native dialogs inherit the active cinema skin and remote navigation."""
from urllib.parse import urlsplit
from .environment import private_path
from .libraries import (Registry, LibraryError, MAX_CATALOG_BYTES, import_catalog,
                        vfs_source, joined_path, directory_items, split_location)

ERRORS = {
    'INVALID_LOCATION': '地址格式不正确。NAS 使用 SMB / NFS，网盘可使用 WebDAV。',
    'INVALID_MEDIA_URL': '片库只接受 HTTP(S) 视频直链，不接受插件命令、脚本或带账号密码的链接。',
    'INVALID_DOCUMENT': '不是受支持的片库文件。请选择 bobbi-library-v1 格式的 JSON。',
    'DUPLICATE_ITEM': '片库中有重复的条目标识，请先修正文件。',
    'CATALOG_TOO_LARGE': '片库文件过大；每份最多 2 MB、2000 个条目。',
    'SOURCE_NOT_FOUND': '此连接已移除或变更，请返回“我的片库”刷新。',
    'SOURCE_UNAVAILABLE': '未能访问这个目录。请检查 NAS 是否在线、网络、账号和共享权限。',
    'DIRECTORY_TOO_LARGE': '目录条目过多，请把连接指向更具体的子目录。',
    'TOO_MANY_SOURCES': '已达到 32 个连接上限，请移除不再使用的连接。',
    'STORAGE_UNAVAILABLE': '暂时无法保存片库设置，请稍后重试。已有文件不会被删除。',
    'UNKNOWN_STORAGE_VERSION': '片库配置由较新版本创建。请更新整套 bobbi 组件，不要删除原配置。',
    'INVALID_SOURCE': '本机片库配置格式不正确。请保留原文件并联系维护者，不要反复重装。',
}


def message(error):
    return ERRORS.get(getattr(error, 'code', ''), '这一步未完成，请检查地址、权限或文件格式后重试。')


def registry(translate):
    return Registry(private_path(translate, 'libraries.sqlite3'))


def _network(dialog, kind, previous=None):
    prefix = {'smb': 'smb://', 'nfs': 'nfs://', 'webdav': 'davs://'}[kind]
    heading = {'smb': 'NAS 地址和共享目录，例如 nas.local/Movies',
               'nfs': 'NFS 地址和导出目录，例如 nas.local/volume1/video',
               'webdav': 'WebDAV 地址，例如 https://nas.example/dav/'}[kind]
    location = dialog.input(heading, defaultt=previous.location if previous else '')
    if not location:
        return None
    if kind == 'webdav':
        if location.startswith('https://'):
            location = 'davs://' + location[8:]
        elif location.startswith('http://'):
            location = 'dav://' + location[7:]
    if '://' not in location:
        location = prefix + location
    root, embedded_user, embedded_password = split_location(location)
    if urlsplit(root).scheme not in ({'dav', 'davs'} if kind == 'webdav' else {kind}):
        raise LibraryError('INVALID_LOCATION')
    if embedded_user or embedded_password:
        dialog.ok('请分开填写账号', '地址栏不放账号密码；下一步单独填写，密码输入会隐藏。')
        return None
    name = dialog.input('给这个连接起名', defaultt=previous.name if previous else (
        '我的 NAS' if kind != 'webdav' else '我的网盘'))
    if not name:
        return None
    username = password = ''
    if kind != 'nfs':
        import xbmcgui
        credential_action = 1
        if previous:
            credential_action = dialog.select('连接账号', ['保留已存账号和密码', '重新填写账号和密码', '改用匿名访问'])
            if credential_action < 0:
                return None
        if credential_action == 0:
            username, password = previous.username, previous.password
        elif credential_action == 1:
            username = dialog.input('账号（匿名访问可以留空）')
            if username:
                password = dialog.input('密码', option=xbmcgui.ALPHANUM_HIDE_INPUT)
    if root.startswith('dav://') and not dialog.yesno('这是明文 HTTP 连接',
            '请只在可信家庭网络使用；远程访问建议改用 HTTPS。仍要保存这个连接吗？'):
        return None
    return vfs_source(name, root, username, password, source_id=previous.id if previous else None)


def _catalog(dialog, vfs, source_id=None):
    path = dialog.browse(1, '选择自己的片库 JSON 文件', 'files', mask='.json')
    if not path:
        return None
    file = vfs.File(path)
    try:
        raw = bytes(file.readBytes(MAX_CATALOG_BYTES + 1))
    finally:
        file.close()
    return import_catalog(raw, source_id=source_id)


def edit_source(dialog, vfs, store, previous):
    if previous.kind == 'catalog':
        source = _catalog(dialog, vfs, previous.id)
    else:
        scheme = urlsplit(previous.location).scheme
        if scheme in ('smb', 'nfs', 'dav', 'davs'):
            source = _network(dialog, 'webdav' if scheme in ('dav', 'davs') else scheme, previous)
        else:
            path = dialog.browse(0, '选择媒体目录', 'files', defaultt=previous.location)
            if not path:
                return False
            name = dialog.input('给这个片库起名', defaultt=previous.name)
            source = vfs_source(name, path, source_id=previous.id) if name else None
    if source is None:
        return False
    if not dialog.yesno('保存修改', '更新“' + previous.name + '”的本机连接配置？\n不会修改或删除远端媒体文件。'):
        return False
    # The whole document is validated before replacing any existing record.
    store.save(source)
    dialog.ok('已保存', '可以选择“检查连接”，然后到“我的片库”手动选片。')
    return True


def add_source(dialog, vfs, store):
    kinds = ['NAS / 网络共享（SMB）', 'NAS（NFS）', '网盘 / NAS（WebDAV）',
             '本机、U盘或 Kodi 已保存的网络目录', '导入自己的直链片库文件']
    choice = dialog.select('添加网盘 / NAS / 片库', kinds)
    if choice < 0:
        return False
    if choice < 3:
        source = _network(dialog, ('smb', 'nfs', 'webdav')[choice])
    elif choice == 3:
        path = dialog.browse(0, '选择媒体目录', 'files')
        if not path:
            return False
        name = dialog.input('给这个片库起名', defaultt='我的视频')
        source = vfs_source(name, path) if name else None
    else:
        source = _catalog(dialog, vfs)
    if source is None:
        return False
    detail = source.location if source.kind == 'vfs' else str(len(source.items)) + ' 个视频直链条目'
    if not dialog.yesno('添加“' + source.name + '”', detail + '\n仅保存到本机，不改动媒体文件。'):
        return False
    store.save(source)
    dialog.ok('已添加连接', '可在“我的片库”浏览和手动选片。\n地址已保存，不代表已验证视频可播。')
    return True


def check_source(dialog, vfs, source):
    if source.kind == 'catalog':
        dialog.ok('片库格式检查通过', '共有 %d 个有效格式的条目；尚未逐个访问或试播。' % len(source.items))
        return
    path = joined_path(source)
    if not vfs.exists(path):
        dialog.ok('尚未连接', '请检查地址、共享权限、账号及 NAS 是否在线。没有改动远端文件。')
        return
    rows = directory_items(*vfs.listdir(path))
    if not rows:
        dialog.ok('没有读到可显示的条目', '可能是空目录、没有视频，或共享权限不足；这不算播放验证通过。')
    else:
        dialog.ok('目录已读到', '可显示 %d 个文件夹或视频。\n未开始播放，也没有下载或修改文件。' % len(rows))


def manage(legacy_root=''):
    import xbmc
    import xbmcgui
    import xbmcvfs
    dialog = xbmcgui.Dialog()
    store = None
    changed = False
    navigated = False
    try:
        store = registry(xbmcvfs.translatePath)
        # Keep the earlier single-directory preference. Do not rewrite Kodi's
        # sources.xml/passwords.xml or overwrite unrelated addon settings.
        if legacy_root:
            try:
                changed = store.migrate_legacy(legacy_root)
            except LibraryError:
                dialog.ok('原目录尚未迁移', '原设置仍保留。请用“添加来源”重新选择目录。')
        while not xbmc.Monitor().abortRequested():
            sources = store.sources()
            choice = dialog.select('我的片库 · 网盘与 NAS', ['＋ 添加来源', '打开我的片库']
                + [source.name + (' · NAS / 目录' if source.kind == 'vfs' else ' · 直链片库') for source in sources])
            if choice < 0:
                return
            try:
                if choice == 0:
                    changed = add_source(dialog, xbmcvfs, store) or changed
                elif choice == 1:
                    if xbmc.getCondVisibility('System.HasAddon(plugin.video.bobbi.library)'):
                        xbmc.executebuiltin('ActivateWindow(Videos,plugin://plugin.video.bobbi.library/,return)')
                        navigated = True
                        return True  # Tell enclosing menus not to cover navigation.
                    dialog.ok('需要片库组件', '请安装同一版本的“bobbi 我的片库”组件。已保存的连接会保留。')
                else:
                    source = sources[choice - 2]
                    action = dialog.select(source.name, ['检查连接 / 片库格式',
                        '修改连接 / 账号' if source.kind == 'vfs' else '更新导入的片库',
                        '移除这个连接（不删除媒体文件）'])
                    if action == 0:
                        check_source(dialog, xbmcvfs, source)
                    elif action == 1:
                        changed = edit_source(dialog, xbmcvfs, store, source) or changed
                    elif action == 2 and dialog.yesno('仅移除连接',
                            '移除“' + source.name + '”的本机配置和已存账号。NAS、网盘及视频文件不受影响。'):
                        store.remove(source.id)
                        changed = True
                        dialog.ok('连接已移除', '远端媒体文件没有删除；以后可重新添加。')
            except (LibraryError, OSError, RuntimeError) as error:
                dialog.ok('未完成', message(error))
    except (LibraryError, OSError, RuntimeError, ValueError) as error:
        dialog.ok('片库设置暂时不可用', message(error))
    finally:
        if store is not None:
            store.close()
        if changed and not navigated:
            xbmc.executebuiltin('Container.Refresh')

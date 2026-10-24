"""Kodi-native dialogs inherit the active cinema skin and remote navigation."""
from urllib.parse import urlsplit, urlencode
from . import cd2_mounts
from .environment import private_path
from .libraries import (Registry, LibraryError, MAX_CATALOG_BYTES, import_catalog,
                        vfs_source, joined_path, directory_items, split_location)

ERRORS = {
    'INVALID_LOCATION': '地址格式不正确，请按输入框中的示例填写。',
    'INVALID_MEDIA_URL': '片库只接受 HTTP(S) 视频直链，不接受插件命令、脚本或带账号密码的链接。',
    'INVALID_DOCUMENT': '无法读取片库文件，请选择 bobbi-library-v1 格式的 JSON 文件。',
    'DUPLICATE_ITEM': '片库文件中有重复条目，请修正后重新导入。',
    'CATALOG_TOO_LARGE': '片库文件过大；每份最多 2 MB、2000 个条目。',
    'SOURCE_NOT_FOUND': '此连接已移除或变更，请返回“我的片库”刷新。',
    'SOURCE_UNAVAILABLE': '无法打开目录，请检查网络、账号及共享权限。',
    'DIRECTORY_TOO_LARGE': '目录条目过多，请把连接指向更具体的子目录。',
    'TOO_MANY_SOURCES': '已达到 32 个连接上限，请移除不再使用的连接。',
    'STORAGE_UNAVAILABLE': '无法保存片库设置，请稍后重试。',
    'UNKNOWN_STORAGE_VERSION': '片库需要较新版波比 TV，请更新后再打开，勿删除配置。',
    'INVALID_SOURCE': '片库配置无法读取，请保留原文件并联系维护者。',
}


def message(error):
    return ERRORS.get(getattr(error, 'code', ''), '这一步未完成，请检查地址、权限或文件格式后重试。')


def registry(translate):
    return Registry(private_path(translate, 'libraries.sqlite3'))


def _cd2_source(dialog, store):
    mounts = cd2_mounts.discover()
    if not mounts:
        dialog.ok('未发现 CD2 挂载', '请先在 CloudDrive 挂载网盘。远程 CD2 可通过 SMB 或 WebDAV 添加。')
        return None
    choice = dialog.select('选择 CD2 挂载目录', list(mounts)) if len(mounts) > 1 else 0
    if choice < 0 or choice >= len(mounts):
        return None
    path = mounts[choice]
    sources = store.sources()
    source = next((row for row in sources if row.kind == 'vfs'
                   and row.location.rstrip('/') == path), None)
    # A mount can disappear while the selector is open. Do not
    # silently save a stale path or label an ordinary directory as live CD2.
    if path not in cd2_mounts.discover():
        dialog.ok('CD2 挂载已变化', '请检查 CloudDrive 后重新打开。未修改片库来源。')
        return None
    if source is None:
        names = {row.name for row in sources}
        name, suffix = 'CD2 网盘', 2
        while name in names:
            name, suffix = 'CD2 网盘 %d' % suffix, suffix + 1
        source = vfs_source(name, path)
        store.save(source)
    return source


def open_existing_cd2(dialog=None):
    """Reuse the existing library owner; no alternate account or player stack."""
    import xbmc
    import xbmcgui
    import xbmcvfs
    dialog = dialog or xbmcgui.Dialog()
    if not xbmc.getCondVisibility('System.HasAddon(plugin.video.bobbi.library)'):
        dialog.ok('片库组件未安装', '请用波比 TV 完整安装包修复，CD2 设置保留。')
        return False
    store = None
    try:
        store = registry(xbmcvfs.translatePath)
        source = _cd2_source(dialog, store)
        if source is None:
            return False
        target = 'plugin://plugin.video.bobbi.library/?' + urlencode(
            dict(action='browse', source=source.id))
    except (LibraryError, OSError, RuntimeError, ValueError) as error:
        dialog.ok('未能打开 CD2 网盘', message(error))
        return False
    finally:
        if store is not None:
            store.close()
    xbmc.executebuiltin('ActivateWindow(Videos,' + target + ',return)')
    return True


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
        dialog.ok('请单独填写账号', '请从地址中移除账号密码，下一步再填写。')
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
            credential_action = dialog.select('连接账号', ['保留当前账号', '修改账号密码', '匿名访问'])
            if credential_action < 0:
                return None
        if credential_action == 0:
            username, password = previous.username, previous.password
        elif credential_action == 1:
            username = dialog.input('账号（匿名访问可以留空）')
            if username:
                password = dialog.input('密码', option=xbmcgui.ALPHANUM_HIDE_INPUT)
    if root.startswith('dav://') and not dialog.yesno('保存未加密连接？',
            'HTTP 会明文传输账号密码。仅建议在可信家庭网络使用，远程访问请改用 HTTPS。'):
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
    if not dialog.yesno('保存修改？', '更新“' + previous.name + '”的连接设置，媒体文件保留。'):
        return False
    # The whole document is validated before replacing any existing record.
    store.save(source)
    dialog.ok('已保存', '可到“我的片库”选片。' if source.kind == 'catalog' else
              '请选择“检查连接”，或到“我的片库”选片。')
    return True


def add_source(dialog, vfs, store):
    kinds = ['SMB 共享', 'NFS 共享', 'WebDAV 网盘',
             '本机 / U盘 / 已保存目录', '导入直链片库']
    if cd2_mounts.discover():
        kinds.append('已有 CD2 网盘（无需扫码）')
    choice = dialog.select('添加来源', kinds)
    if choice < 0 or choice >= len(kinds):
        return False
    if choice == 5:
        return _cd2_source(dialog, store) is not None
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
    dialog.ok('来源已保存', '到“我的片库”打开此来源即可选片。尚未检查连接。')
    return True


def check_source(dialog, vfs, source):
    if source.kind == 'catalog':
        dialog.ok('片库格式正确', '共 %d 个视频条目，尚未逐个试播。' % len(source.items))
        return
    path = joined_path(source)
    if not vfs.exists(path):
        dialog.ok('连接失败', '请确认设备在线，并检查地址、账号和共享权限。')
        return
    rows = directory_items(*vfs.listdir(path))
    if not rows:
        dialog.ok('目录中没有可显示的内容', '请检查目录是否有视频，以及当前账号是否有读取权限。')
    else:
        dialog.ok('连接成功', '找到 %d 个文件夹或视频，可以到“我的片库”选片。' % len(rows))


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
                dialog.ok('原目录未能导入', '原设置保留，请用“添加来源”重新选择。')
        while not xbmc.Monitor().abortRequested():
            sources = store.sources()
            choice = dialog.select('我的片库', ['＋ 添加来源', '打开我的片库']
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
                    dialog.ok('片库组件未安装', '请用波比 TV 完整安装包修复，已保存的来源保留。')
                else:
                    source = sources[choice - 2]
                    action = dialog.select(source.name, ['检查连接' if source.kind == 'vfs' else '检查片库格式',
                        '修改连接' if source.kind == 'vfs' else '重新导入片库',
                        '移除来源'])
                    if action == 0:
                        check_source(dialog, xbmcvfs, source)
                    elif action == 1:
                        changed = edit_source(dialog, xbmcvfs, store, source) or changed
                    elif action == 2 and dialog.yesno('移除来源？',
                            '将移除“' + source.name + '”的连接和已存账号，媒体文件保留。'):
                        store.remove(source.id)
                        changed = True
                        dialog.ok('来源已移除', '媒体文件保留，需要时可重新添加。')
            except (LibraryError, OSError, RuntimeError) as error:
                dialog.ok('未完成', message(error))
    except (LibraryError, OSError, RuntimeError, ValueError) as error:
        dialog.ok('片库设置暂时不可用', message(error))
    finally:
        if store is not None:
            store.close()
        if changed and not navigated:
            xbmc.executebuiltin('Container.Refresh')

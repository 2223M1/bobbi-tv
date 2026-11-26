"""Kodi-native dialogs inherit the active cinema skin and remote navigation."""
from urllib.parse import urlsplit, urlencode
from . import cd2_mounts
from .environment import private_path
from .i18n import is_english, tr
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

ERRORS_EN = {
    'INVALID_LOCATION': 'Invalid address format. Follow the example shown in the input prompt.',
    'INVALID_MEDIA_URL': 'Catalogs accept direct HTTP(S) media URLs only — no plugin commands, scripts, or embedded credentials.',
    'INVALID_DOCUMENT': 'Cannot read catalog file. Select a valid bobbi-library-v1 JSON file.',
    'DUPLICATE_ITEM': 'Catalog file contains duplicate items. Fix them and import again.',
    'CATALOG_TOO_LARGE': 'Catalog file is too large; each catalog supports up to 2 MB and 2000 items.',
    'SOURCE_NOT_FOUND': 'This connection was removed or changed. Return to "My Library" and refresh.',
    'SOURCE_UNAVAILABLE': 'Cannot open folder. Check network connectivity, credentials, and share permissions.',
    'DIRECTORY_TOO_LARGE': 'Folder has too many entries. Point the connection to a more specific subfolder.',
    'TOO_MANY_SOURCES': 'Reached the 32-connection limit. Remove unused connections first.',
    'STORAGE_UNAVAILABLE': 'Cannot save library settings right now. Please try again later.',
    'UNKNOWN_STORAGE_VERSION': 'Library requires a newer version of bobbi TV. Update before opening; do not delete your config.',
    'INVALID_SOURCE': 'Library configuration cannot be read. Keep the file and contact maintainers.',
}


def message(error):
    from .source_media_http import MESSAGES, localized_message
    code = getattr(error, 'code', '')
    if code in MESSAGES:
        return localized_message(code)
    if is_english():
        return ERRORS_EN.get(code, 'This step did not finish. Check the address, permissions, or file format and retry.')
    return ERRORS.get(code, '这一步未完成，请检查地址、权限或文件格式后重试。')


def registry(translate):
    return Registry(private_path(translate, 'libraries.sqlite3'))


def _cd2_source(dialog, store):
    en = is_english()
    mounts = cd2_mounts.discover()
    if not mounts:
        dialog.ok(
            tr(None, '未发现 CD2 挂载', 'No CD2 Mounts Found'),
            tr(None, '请先在 CloudDrive 挂载网盘。远程 CD2 可通过 SMB 或 WebDAV 添加。',
               'Mount your cloud drive in CloudDrive first. Remote CD2 instances can be added via SMB or WebDAV.'),
        )
        return None
    choice = dialog.select(tr(None, '选择 CD2 挂载目录', 'Select CD2 Mount Folder'), list(mounts)) if len(mounts) > 1 else 0
    if choice < 0 or choice >= len(mounts):
        return None
    path = mounts[choice]
    sources = store.sources()
    source = next((row for row in sources if row.kind == 'vfs'
                   and row.location.rstrip('/') == path), None)
    # A mount can disappear while the selector is open. Do not
    # silently save a stale path or label an ordinary directory as live CD2.
    if path not in cd2_mounts.discover():
        dialog.ok(
            tr(None, 'CD2 挂载已变化', 'CD2 Mount Changed'),
            tr(None, '请检查 CloudDrive 后重新打开。未修改片库来源。',
               'Check CloudDrive and reopen. Library sources were not modified.'),
        )
        return None
    if source is None:
        names = {row.name for row in sources}
        base_name = 'CD2 Drive' if en else 'CD2 网盘'
        name, suffix = base_name, 2
        while name in names:
            name, suffix = '%s %d' % (base_name, suffix), suffix + 1
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
        dialog.ok(
            tr(None, '片库组件未安装', 'Library Add-on Not Installed'),
            tr(None, '请用波比 TV 完整安装包修复，CD2 设置保留。',
               'Repair using the full bobbi TV release bundle; CD2 settings are kept.'),
        )
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
        dialog.ok(tr(None, '未能打开 CD2 网盘', 'Could Not Open CD2 Drive'), message(error))
        return False
    finally:
        if store is not None:
            store.close()
    xbmc.executebuiltin('ActivateWindow(Videos,' + target + ',return)')
    return True


def open_library(dialog):
    """Open existing sources without requiring a native cloud account."""
    import xbmc
    if not xbmc.getCondVisibility('System.HasAddon(plugin.video.bobbi.library)'):
        dialog.ok(
            tr(None, '片库组件未安装', 'Library Add-on Not Installed'),
            tr(None, '请用波比 TV 完整安装包修复，已保存的来源保留。',
               'Repair using the full bobbi TV release bundle; saved sources are kept.'),
        )
        return False
    xbmc.executebuiltin('ActivateWindow(Videos,plugin://plugin.video.bobbi.library/,return)')
    return True


def _network(dialog, kind, previous=None):
    en = is_english()
    prefix = {'smb': 'smb://', 'nfs': 'nfs://', 'webdav': 'davs://'}[kind]
    heading = {
        'smb': tr(32104, 'NAS 地址和共享目录，例如 nas.local/Movies', 'NAS host and shared folder, e.g. nas.local/Movies'),
        'nfs': tr(32105, 'NFS 地址和导出目录，例如 nas.local/volume1/video', 'NFS host and export path, e.g. nas.local/volume1/video'),
        'webdav': tr(32106, 'WebDAV 地址，例如 https://nas.example/dav/', 'WebDAV URL, e.g. https://nas.example/dav/'),
    }[kind]
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
        dialog.ok(
            tr(None, '请单独填写账号', 'Enter Credentials Separately'),
            tr(None, '请从地址中移除账号密码，下一步再填写。',
               'Remove username and password from the URL; you will enter them in the next step.'),
        )
        return None
    default_name = ('My NAS' if kind != 'webdav' else 'My Cloud') if en else ('我的 NAS' if kind != 'webdav' else '我的网盘')
    name = dialog.input(tr(32107, '给这个连接起名', 'Name this connection'), defaultt=previous.name if previous else default_name)
    if not name:
        return None
    username = password = ''
    if kind != 'nfs':
        import xbmcgui
        credential_action = 1
        if previous:
            credential_action = dialog.select(
                tr(None, '连接账号', 'Connection Credentials'),
                [
                    tr(None, '保留当前账号', 'Keep Current Credentials'),
                    tr(None, '修改账号密码', 'Change Username & Password'),
                    tr(None, '匿名访问', 'Anonymous Access'),
                ],
            )
            if credential_action < 0:
                return None
        if credential_action == 0:
            username, password = previous.username, previous.password
        elif credential_action == 1:
            username = dialog.input(tr(None, '账号（匿名访问可以留空）', 'Username (leave empty for anonymous access)'))
            if username:
                password = dialog.input(tr(None, '密码', 'Password'), option=xbmcgui.ALPHANUM_HIDE_INPUT)
    if root.startswith('dav://') and not dialog.yesno(
        tr(32108, '保存未加密连接？', 'Save Unencrypted Connection?'),
        tr(32109,
           'HTTP 会明文传输账号密码。仅建议在可信家庭网络使用，远程访问请改用 HTTPS。',
           'HTTP sends username and password in plaintext. Use only on a trusted home network; use HTTPS for remote access.'),
    ):
        return None
    return vfs_source(name, root, username, password, source_id=previous.id if previous else None)


def _catalog(dialog, vfs, source_id=None):
    path = dialog.browse(1, tr(None, '选择自己的片库 JSON 文件', 'Select Personal Catalog JSON File'), 'files', mask='.json')
    if not path:
        return None
    file = vfs.File(path)
    try:
        raw = bytes(file.readBytes(MAX_CATALOG_BYTES + 1))
    finally:
        file.close()
    return import_catalog(raw, source_id=source_id)


def edit_source(dialog, vfs, store, previous):
    en = is_english()
    if previous.kind == 'catalog':
        source = _catalog(dialog, vfs, previous.id)
    else:
        scheme = urlsplit(previous.location).scheme
        if scheme in ('smb', 'nfs', 'dav', 'davs'):
            source = _network(dialog, 'webdav' if scheme in ('dav', 'davs') else scheme, previous)
        else:
            path = dialog.browse(0, tr(None, '选择媒体目录', 'Select Media Folder'), 'files', defaultt=previous.location)
            if not path:
                return False
            name = dialog.input(tr(None, '给这个片库起名', 'Name this library'), defaultt=previous.name)
            source = vfs_source(name, path, source_id=previous.id) if name else None
    if source is None:
        return False
    confirm_body = (
        f'Update connection settings for "{previous.name}"? Media files are kept.'
        if en else ('更新“' + previous.name + '”的连接设置，媒体文件保留。')
    )
    if not dialog.yesno(tr(None, '保存修改？', 'Save Changes?'), confirm_body):
        return False
    # The whole document is validated before replacing any existing record.
    store.save(source)
    dialog.ok(
        tr(None, '已保存', 'Saved'),
        (tr(None, '可到“我的片库”选片。', 'Open "My Library" to browse titles.')
         if source.kind == 'catalog' else
         tr(None, '请选择“检查连接”，或到“我的片库”选片。', 'Choose "Check Connection" or open "My Library" to browse.')),
    )
    return True


def add_source(dialog, vfs, store, *, source_store=None, _handoff=None):
    en = is_english()
    entries = [
        ('smb', tr(32096, 'SMB 共享', 'SMB Share')),
        ('nfs', tr(32097, 'NFS 共享', 'NFS Share')),
        ('webdav', tr(32098, 'WebDAV 网盘', 'WebDAV Cloud')),
        ('folder', tr(32099, '本机 / U盘 / 已保存目录', 'Local / USB / Saved Folder')),
        ('catalog', tr(32100, '导入直链片库', 'Import Direct-Link Catalog')),
    ]
    if cd2_mounts.discover():
        entries.append(('cd2', tr(32101, '已有 CD2 网盘（无需扫码）', 'Existing CD2 Mount (No QR Needed)')))
    entries.append(('source_library', tr(32102, '源库网址', 'Source Library URL')))
    entries.append(('media_server', tr(32103, '媒体服务器 · Plex / Jellyfin / Emby', 'Media Server · Plex / Jellyfin / Emby')))
    entries.append(('t4', tr(32094, '小雅 / TVBox（T4）', 'Xiaoya / TVBox (T4)')))
    choice = dialog.select(tr(32082, '添加来源', 'Add Source'), [label for _, label in entries])
    if choice < 0 or choice >= len(entries):
        return False
    kind_key = entries[choice][0]
    if kind_key == 'source_library':
        from .source_library_ui import add
        return add(dialog, store, source_store=source_store)
    if kind_key == 'media_server':
        from .server_ui import add
        return add(dialog, store)
    if kind_key == 't4':
        from .t4_ui import add
        return add(dialog, vfs, store, _handoff=_handoff)
    if kind_key == 'cd2':
        return _cd2_source(dialog, store) is not None
    if kind_key in ('smb', 'nfs', 'webdav'):
        source = _network(dialog, kind_key)
    elif kind_key == 'folder':
        path = dialog.browse(0, tr(None, '选择媒体目录', 'Select Media Folder'), 'files')
        if not path:
            return False
        name = dialog.input(tr(None, '给这个片库起名', 'Name this library'), defaultt='My Videos' if en else '我的视频')
        source = vfs_source(name, path) if name else None
    else:
        source = _catalog(dialog, vfs)
    if source is None:
        return False
    detail = (source.location if source.kind == 'vfs'
              else (f'{len(source.items)} direct-link items' if en else str(len(source.items)) + ' 个视频直链条目'))
    confirm_title = f'Add "{source.name}"' if en else ('添加“' + source.name + '”')
    confirm_body = detail + ('\nSaved locally only; media files are untouched.' if en else '\n仅保存到本机，不改动媒体文件。')
    if not dialog.yesno(confirm_title, confirm_body):
        return False
    store.save(source)
    dialog.ok(
        tr(None, '来源已保存', 'Source Saved'),
        tr(None, '到“我的片库”打开此来源即可选片。尚未检查连接。',
           'Open this source in "My Library" to browse. Connection has not been checked yet.'),
    )
    return True


def check_source(dialog, vfs, source):
    if source.kind == 'catalog':
        dialog.ok(
            tr(None, '片库格式正确', 'Catalog Format Valid'),
            (tr(None, '共 %d 个视频条目，尚未逐个试播。', '%d video items found; individual playback not tested yet.')
             % len(source.items)),
        )
        return
    path = joined_path(source)
    if not vfs.exists(path):
        dialog.ok(
            tr(None, '连接失败', 'Connection Failed'),
            tr(None, '请确认设备在线，并检查地址、账号和共享权限。',
               'Verify the host is online and check the address, credentials, and share permissions.'),
        )
        return
    rows = directory_items(*vfs.listdir(path))
    if not rows:
        dialog.ok(
            tr(None, '目录中没有可显示的内容', 'No Visible Items in Folder'),
            tr(None, '请检查目录是否有视频，以及当前账号是否有读取权限。',
               'Check whether the folder contains videos and whether the account has read permission.'),
        )
    else:
        dialog.ok(
            tr(None, '连接成功', 'Connection Successful'),
            (tr(None, '找到 %d 个文件夹或视频，可以到“我的片库”选片。',
                'Found %d folders or videos. Open "My Library" to browse.')
             % len(rows)),
        )


def manage_outcome(legacy_root=''):
    import xbmc
    import xbmcgui
    import xbmcvfs
    from .server_ui import CANCELLED, CHANGED, NAVIGATED
    dialog = xbmcgui.Dialog()
    store = None
    changed = False
    navigated = False
    try:
        store = registry(xbmcvfs.translatePath)
        from .source_libraries import capture
        source_store = capture()
        # Keep the earlier single-directory preference. Do not rewrite Kodi's
        # sources.xml/passwords.xml or overwrite unrelated addon settings.
        if legacy_root:
            try:
                changed = store.migrate_legacy(legacy_root)
            except LibraryError:
                dialog.ok(
                    tr(None, '原目录未能导入', 'Could Not Import Previous Folder'),
                    tr(None, '原设置保留，请用“添加来源”重新选择。',
                       'Previous setting kept; reselect it via "Add Source".'),
                )
        while not xbmc.Monitor().abortRequested():
            en = is_english()
            online = source_store.current()
            sources = store.sources()
            active_emby = store.emby_binding()[0]
            source_rows = []
            for source in sources:
                if source.kind == 'vfs':
                    suffix = ' · NAS / Folder' if en else ' · NAS / 目录'
                elif source.kind == 'media_server':
                    is_act = (source.metadata.get('provider') == 'emby'
                              and active_emby is not None and active_emby.id == source.id)
                    if en:
                        suffix = ' · Media Server · Active' if is_act else ' · Media Server'
                    else:
                        suffix = ' · 媒体服务器 · 当前浏览' if is_act else ' · 媒体服务器'
                elif source.kind == 't4':
                    suffix = ' · T4 Sites' if en else ' · T4 站点'
                else:
                    suffix = ' · Direct Catalog' if en else ' · 直链片库'
                source_rows.append(source.name + suffix)
            online_rows = ([('Source Library · ' if en else '源库 · ') + online.name] if online else [])
            choice = dialog.select(
                tr(32081, '我的片库', 'My Library'),
                [
                    ('+ Add Source' if en else '＋ 添加来源'),
                    tr(32083, '打开我的片库', 'Open My Library'),
                ]
                + source_rows
                + online_rows
                + [tr(32084, '片库索引与任务', 'Library Index & Tasks')],
            )
            if choice < 0:
                return CHANGED if changed else CANCELLED
            try:
                if choice == 0:
                    handoff = []
                    changed = add_source(dialog, xbmcvfs, store, source_store=source_store, _handoff=handoff) or changed
                    if 'NAVIGATED' in handoff:
                        navigated = True
                        return NAVIGATED
                elif choice == 1:
                    if open_library(dialog):
                        navigated = True
                        return NAVIGATED  # Tell enclosing menus not to cover navigation.
                elif online and choice == len(sources) + 2:
                    from .source_library_ui import manage as manage_online
                    changed = manage_online(dialog, store, online) or changed
                elif choice == len(sources) + 2 + bool(online):
                    from .catalog_ui import manage as manage_index
                    if manage_index():
                        navigated = True
                        return NAVIGATED
                else:
                    source = sources[choice - 2]
                    if source.kind == 't4':
                        from .t4_ui import manage as manage_t4
                        handoff = []
                        changed = manage_t4(dialog, xbmcvfs, store, source, _handoff=handoff) or changed
                        if 'NAVIGATED' in handoff:
                            navigated = True
                            return NAVIGATED
                        continue
                    if source.kind == 'media_server':
                        from .server_ui import manage as manage_server
                        outcome = manage_server(dialog, store, source)
                        if outcome == NAVIGATED:
                            navigated = True
                            return NAVIGATED
                        changed = (outcome in (CHANGED, True)) or changed
                        continue
                    actions = [
                        (tr(None, '检查连接', 'Check Connection') if source.kind == 'vfs' else tr(None, '检查片库格式', 'Check Catalog Format')),
                        (tr(None, '修改连接', 'Edit Connection') if source.kind == 'vfs' else tr(None, '重新导入片库', 'Re-import Catalog')),
                        tr(None, '移除来源', 'Remove Source'),
                    ]
                    local_source = False
                    network_source = False
                    if source.kind == 'vfs':
                        from .scan_sources import LocalPort
                        try:
                            LocalPort.source_scope(source)
                            local_source = True
                            actions.append(tr(None, '作品、整理与扫描', 'Works, Organize & Scan'))
                        except ValueError:
                            from .network_sources import NetworkPort
                            try:
                                NetworkPort.source_scope(source)
                                network_source = True
                                actions.append(tr(None, '作品、整理与扫描（网络实验）', 'Works, Organize & Scan (Network Experimental)'))
                            except ValueError:
                                pass
                    action = dialog.select(source.name, actions)
                    if action == 0:
                        check_source(dialog, xbmcvfs, source)
                    elif action == 1:
                        changed = edit_source(dialog, xbmcvfs, store, source) or changed
                    elif action == 2 and dialog.yesno(
                        tr(None, '移除来源？', 'Remove Source?'),
                        (f'Remove connection and saved credentials for "{source.name}"? Media files are kept.'
                         if en else ('将移除“' + source.name + '”的连接和已存账号，媒体文件保留。')),
                    ):
                        store.remove(source.id)
                        changed = True
                        dialog.ok(
                            tr(None, '来源已移除', 'Source Removed'),
                            tr(None, '媒体文件保留，需要时可重新添加。', 'Media files are kept; you can add it again anytime.'),
                        )
                    elif action == 3 and (local_source or network_source):
                        # The sole personal catalog chooses the proven source
                        # lane. Immediate browsing remains unchanged.
                        from .runtime import call
                        local_rows = call('catalog_local_sources', {}, timeout=2)['items']
                        params = dict(action='personal_catalog', source=source.id)
                        if network_source:
                            params['reference_kind'] = 'network_path'
                        if any(row['id'] == source.id for row in local_rows):
                            params['reference_kind'] = 'local_path'
                        target = 'plugin://plugin.video.bobbi/?' + urlencode(params)
                        xbmc.executebuiltin('ActivateWindow(Videos,"' + target + '",return)')
                        navigated = True
                        return NAVIGATED
            except (LibraryError, OSError, RuntimeError) as error:
                dialog.ok(tr(None, '未完成', 'Not Completed'), message(error))
    except (LibraryError, OSError, RuntimeError, ValueError) as error:
        dialog.ok(tr(None, '片库设置暂时不可用', 'Library Settings Temporarily Unavailable'), message(error))
    finally:
        if store is not None:
            store.close()
        if changed and not navigated:
            xbmc.executebuiltin('Container.Refresh')
    return CHANGED if changed else CANCELLED


def manage(legacy_root=''):
    from .server_ui import NAVIGATED
    return True if manage_outcome(legacy_root) == NAVIGATED else None

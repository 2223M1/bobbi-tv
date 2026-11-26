"""Unified 4-domain Accounts & Sources Center and thin cloud settings UI."""
from .runtime import call
from . import cd2_mounts
from .i18n import is_english, tr
from .server_ui import CANCELLED, CHANGED, NAVIGATED

ACCOUNT_DOMAINS = ('services', 'servers', 'cloud', 'devices')


def validate_account_domain(domain):
    if domain is None:
        return None
    if type(domain) is not str or domain not in ACCOUNT_DOMAINS:
        raise ValueError('INVALID_ACCOUNT_DOMAIN')
    return domain


def _normalize_outcome(result):
    if result in (NAVIGATED, CHANGED, CANCELLED):
        return result
    return NAVIGATED if result else CANCELLED


def status():
    try:
        value = call('cloud_status', {}, timeout=.5)
        if (not isinstance(value, dict) or type(value.get('authenticated')) is not bool
                or not isinstance(value.get('preparation'), dict)):
            raise ValueError('CLOUD_STATUS_INVALID')
        return value
    except (ValueError, OSError, RuntimeError):
        return dict(authenticated=None, preparation={'state': 'HOST_UNAVAILABLE'})


def cd2_label(value):
    en = is_english()
    state = value.get('state')
    if state == 'RUNNING':
        dependency = value.get('dependency')
        if dependency == 'READY' and value.get('ready') is True:
            return 'Last check passed' if en else '最近检查通过'
        if dependency == 'CHECKING':
            return 'Checking in background' if en else '正在后台检查'
        if dependency == 'ACCOUNT_MISMATCH':
            return 'Cloud account mismatch' if en else '网盘账号不一致'
        if dependency == 'DEPENDENCY_UNAVAILABLE':
            return 'Connection failed, check sign-in' if en else '连接失败，请检查登录'
        return 'Connection not checked yet' if en else '尚未检查连接'
    if en:
        return {
            'NOT_CONFIGURED': 'Not configured (optional)',
            'STARTING': 'Starting',
            'WAITING_ACCOUNT': 'Waiting for 115 sign-in',
            'REVOKING': 'Switching account',
            'UNAVAILABLE': 'Check configuration',
            'STOPPED': 'Service stopped',
            'HOST_UNAVAILABLE': 'Cinema service unavailable',
        }.get(state, 'Status unavailable')
    return {
        'NOT_CONFIGURED': '未设置（可选）',
        'STARTING': '正在启动',
        'WAITING_ACCOUNT': '等待登录 115',
        'REVOKING': '正在切换账号',
        'UNAVAILABLE': '配置需要检查',
        'STOPPED': '后台已停止',
        'HOST_UNAVAILABLE': '影院后台暂不可用',
    }.get(state, '状态暂不可用')


def cd2_details(value):
    if is_english():
        return (
            '115 Pre-stage (CD2) · ' + cd2_label(value) + '\n\n'
            'CD2 is not required for watching 115 share sources.\n'
            'Existing CD2 mounts can be browsed directly in "My Library" without scanning a QR code. 115 share playback requires a one-time sign-in.\n'
            'Only 115 pre-staging requires signing in to the same 115 account in CloudDrive; other cloud mounts do not need 115 sign-in.\n'
            'If connection fails, check CloudDrive service and sign-in status first.\n\n'
            'This screen only displays background status and never creates transfer tasks. Check the source picker for file readiness.'
        )
    return ('115 提前存片（CD2） · ' + cd2_label(value) + '\n\n'
            '观看 115 分享片源无需 CD2。\n'
            '已有 CD2 挂载可直接在“我的片库”浏览，无需扫码。影院的 115 分享片源需单独登录一次。\n'
            '仅使用 115 提前存片时，需要在 CloudDrive 中登录与影院相同的 115 账号；其他网盘挂载不需要 115 登录。\n'
            '连接失败时，先到 CloudDrive 检查服务和登录状态。\n\n'
            '本页只显示后台状态，不会创建转存任务。文件是否就绪，请以选源页为准。')


def transport(dialog):
    import xbmcvfs
    from .environment import private_path
    from .transport_preferences import load, save
    root = private_path(xbmcvfs.translatePath, 'config.json').parent
    mode = load(root)
    selected = dialog.select(
        tr(None, '115 读取方式 · 重启 Kodi 后生效', '115 Read Mode · Takes Effect After Restart'),
        [
            tr(None, '整块读取（兼容模式）', 'Block Read (Compatible Mode)'),
            tr(None, '边下载边读取', 'Progressive Stream Read'),
        ],
        preselect=1 if mode else 0,
    )
    if selected in (0, 1):
        save(root, selected == 1)
        dialog.ok(
            tr(None, '已保存', 'Saved'),
            tr(None, '重启 Kodi 后生效，不影响当前播放。两种方式都保持原画质和原音轨。',
               'Takes effect after restarting Kodi without affecting active playback. Both modes preserve original video and audio.'),
        )
        return True
    return False


def account_label(value):
    if is_english():
        return {True: 'Signed in', False: 'Not signed in', None: 'Service unavailable'}[value['authenticated']]
    return {True: '已保存登录', False: '未登录', None: '后台暂不可用'}[value['authenticated']]


def connection_details(value, mounts):
    """Read-only projection; never enumerate cloud folders or expose credentials."""
    if is_english():
        mount_str = ('%d found' % len(mounts)) if mounts else 'None found'
        return (
            '115 Share Playback · ' + account_label(value) + '\n'
            '115 Pre-stage (CD2) · ' + cd2_label(value['preparation']) + '\n'
            'Local CD2 Mounts · ' + mount_str + '\n\n'
            '115 supports local QR sign-in, switching, and sign-out with one active share-playback account at a time. '
            'A saved sign-in does not guarantee the session is still valid or that every source is playable.\n\n'
            'Other cloud drives can be used via existing CloudDrive mounts or added to "My Library" via WebDAV / SMB. '
            'See "Native Multi-Cloud" for built-in QR and native drive support. '
            'Multiple connections can be saved, checked, edited, or removed independently without signing out of 115.\n\n'
            'CD2 mounts and 115 share sign-in are independent; detecting a mount does not prove its account or files are readable. '
            'Remote CD2 instances can still be added over WebDAV / SMB.\n\n'
            'Refreshing reads local status only and never re-authenticates, scans drives, transfers, or deletes files.'
        )
    return ('115 分享播放 · ' + account_label(value) + '\n'
            '115 提前存片（CD2） · ' + cd2_label(value['preparation']) + '\n'
            '本机 CD2 挂载 · ' + ('发现 %d 个' % len(mounts) if mounts else '未发现') + '\n\n'
            '115 支持本机扫码登录，可重新登录、切换或退出；同时使用一个分享播放账号。'
            '已保存登录不代表账号仍有效，也不代表所有片源都能播放。\n\n'
            '其他网盘可在 CloudDrive 中登录后使用已有挂载，或通过 WebDAV / SMB 添加到“我的片库”。'
            '能否连接取决于对应服务。内置扫码与原生接入进度请查看“原生多网盘”。'
            '已接线的个人盘可手选原文件播放，尚待实机验证；保存登录不代表播放可用。'
            '可以保存多个连接，并分别检查、修改或移除，不需要退出 115。\n\n'
            'CD2 挂载与 115 分享登录相互独立；发现挂载不代表已验证其中账号或文件可读。'
            '未发现本机挂载时，远程 CD2 仍可通过 WebDAV / SMB 使用。\n\n'
            '刷新状态只读取本机后台状态，不会重新登录、扫描网盘、转存或删除文件。'
            '检查连接需在“我的片库”中主动选择。')


def _configure_cd2(dialog, value):
    from .android_engine import available
    if available():
        from .android_preparation import show as configure
        configure(dialog)
    else:
        dialog.textviewer(tr(None, '115 提前存片（CD2）', '115 Pre-stage (CD2)'), cd2_details(value['preparation']))


def _manage_library():
    import xbmcvfs
    from .environment import private_path, load_config
    from .library_ui import manage_outcome
    config = load_config(private_path(xbmcvfs.translatePath, 'config.json'))
    return manage_outcome(config['library_root'])


def _plugin_setting(setting_id):
    try:
        import xbmcaddon
        return str(xbmcaddon.Addon('plugin.video.bobbi').getSetting(setting_id) or '').strip()
    except Exception:
        return ''


def _plugin_flag(setting_id):
    return _plugin_setting(setting_id).lower() == 'true'


def _run_plugin_action(action):
    import xbmc
    xbmc.executebuiltin('RunPlugin(plugin://plugin.video.bobbi/?action=' + action + ')')


def _services_summary():
    count = sum((
        _plugin_flag('is_trakt_auth'),
        _plugin_flag('simkl_authenticated'),
        _plugin_flag('stremio_loggedin'),
        _plugin_flag('nuvio_authenticated'),
        _plugin_flag('real_debid_authorized'),
        _plugin_flag('alldebrid_authorized'),
        bool(_plugin_setting('torbox_token')),
        bool(_plugin_setting('premiumize_token')),
        bool(_plugin_setting('offcloud_token')),
    ))
    if is_english():
        return ('%d connected' % count) if count else 'Trakt / Stremio / Nuvio / Debrid'
    return ('已连接 %d 项' % count) if count else 'Trakt / Stremio / Nuvio / Debrid'


def _servers_summary():
    import xbmcvfs
    from .library_ui import registry
    en = is_english()
    store = None
    try:
        store = registry(xbmcvfs.translatePath)
        servers = [s for s in store.sources() if s.kind == 'media_server']
        active_emby = store.emby_binding()[0]
    except Exception:
        return 'Emby / Jellyfin / Plex'
    finally:
        if store is not None:
            store.close()
    if not servers:
        return 'None saved' if en else '未保存连接'
    if active_emby is not None:
        return ('%d saved · Active %s' % (len(servers), active_emby.name)) if en else ('已存 %d 个 · 当前 %s' % (len(servers), active_emby.name))
    return ('%d saved' % len(servers)) if en else ('已存 %d 个连接' % len(servers))


def _devices_summary():
    import xbmcvfs
    from .environment import private_path
    from .pairing import load as load_pairing
    try:
        paired = load_pairing(private_path(xbmcvfs.translatePath, 'helper-pairing.json')) is not None
    except Exception:
        paired = False
    if is_english():
        return 'Helper paired · Temporary phone QR' if paired else 'BT Helper & temporary phone QR'
    return '助手已配对 · 手机临时授权' if paired else 'BT 助手与手机临时授权'


def _manage_service_item(dialog, service_key):
    if service_key == 'search_sources':
        _run_plugin_action('manage_search_sources')
        return NAVIGATED
    en = is_english()
    specs = {
        'trakt': ('Trakt', _plugin_flag('is_trakt_auth'), [
            ('trakt_auth', 'Sign in or re-authorize Trakt' if en else '登录或重新授权 Trakt'),
            ('trakt_auth_revoke', 'Sign out of Trakt' if en else '退出 Trakt'),
        ]),
        'simkl': ('Simkl', _plugin_flag('simkl_authenticated'), [
            ('simkl_auth', 'Sign in or re-authorize Simkl' if en else '登录或重新授权 Simkl'),
            ('simkl_logout', 'Sign out of Simkl' if en else '退出 Simkl'),
        ]),
        'stremio': ('Stremio', _plugin_flag('stremio_loggedin'), [
            ('stremio_login', 'Sign in to Stremio account' if en else '登录 Stremio 账号'),
            ('stremio_update', 'Sync account add-ons' if en else '同步账号插件源'),
            ('stremio_toggle_addons', 'Select stream add-ons' if en else '选择播放插件源'),
            ('stremio_toggle_catalogs', 'Select catalog add-ons' if en else '选择目录插件源'),
            ('stremio_toggle_tv_addons', 'Select live TV add-ons' if en else '选择直播插件源'),
            ('add_custom_stremio_addon', 'Add custom add-on URL' if en else '添加自定义插件源网址'),
            ('remove_custom_stremio_addon', 'Remove custom add-on' if en else '移除自定义插件源'),
            ('stremio_logout', 'Sign out of Stremio account' if en else '退出 Stremio 账号'),
        ]),
        'nuvio': ('Nuvio', _plugin_flag('nuvio_authenticated'), [
            ('nuvio_auth', 'Sign in to Nuvio account' if en else '登录 Nuvio 账号'),
            ('nuvio_toggle_addons', 'Select imported Nuvio sources' if en else '选择已导入的 Nuvio 来源'),
            ('nuvio_logout', 'Sign out of Nuvio account' if en else '退出 Nuvio 账号'),
        ]),
        'debrid': ('Debrid & Download Services' if en else 'Debrid 与下载加速服务', any((
            _plugin_flag('real_debid_authorized'),
            _plugin_flag('alldebrid_authorized'),
            bool(_plugin_setting('torbox_token')),
            bool(_plugin_setting('premiumize_token')),
            bool(_plugin_setting('offcloud_token')),
        )), [
            ('rd_auth', 'Real-Debrid · Authorize' if en else 'Real-Debrid · 授权登录'),
            ('rd_remove_auth', 'Real-Debrid · Remove Authorization' if en else 'Real-Debrid · 移除授权'),
            ('ad_auth', 'AllDebrid · Authorize' if en else 'AllDebrid · 授权登录'),
            ('ad_remove_auth', 'AllDebrid · Remove Authorization' if en else 'AllDebrid · 移除授权'),
            ('tb_auth', 'TorBox · Authorize' if en else 'TorBox · 授权登录'),
            ('tb_remove_auth', 'TorBox · Remove Authorization' if en else 'TorBox · 移除授权'),
            ('pm_auth', 'Premiumize · Authorize' if en else 'Premiumize · 授权登录'),
            ('pm_remove_auth', 'Premiumize · Remove Authorization' if en else 'Premiumize · 移除授权'),
            ('oc_auth', 'Offcloud · Authorize' if en else 'Offcloud · 授权登录'),
            ('oc_remove_auth', 'Offcloud · Remove Authorization' if en else 'Offcloud · 移除授权'),
            ('offcloud_info', 'Offcloud · Account Info' if en else 'Offcloud · 查看账户详情'),
            ('easynews_info', 'Easynews · Account Info' if en else 'Easynews · 查看账户详情'),
        ]),
    }
    title, authed, actions = specs[service_key]
    state_str = ('Signed in' if authed else 'Not signed in') if en else ('已登录' if authed else '未登录')
    heading = title + ' · ' + state_str
    choice = dialog.select(heading, [label for _, label in actions])
    if 0 <= choice < len(actions):
        _run_plugin_action(actions[choice][0])
        return NAVIGATED
    return CANCELLED


def _manage_services_domain(dialog):
    def build():
        en = is_english()
        rows = [
            ('service:trakt', 'Trakt · ' + (('Authorized' if _plugin_flag('is_trakt_auth') else 'Not signed in') if en else ('已授权' if _plugin_flag('is_trakt_auth') else '未登录'))),
            ('service:simkl', 'Simkl · ' + (('Authorized' if _plugin_flag('simkl_authenticated') else 'Not signed in') if en else ('已授权' if _plugin_flag('simkl_authenticated') else '未登录'))),
            ('service:stremio', 'Stremio · ' + (('Signed in' if _plugin_flag('stremio_loggedin') else 'Not signed in / custom add-ons') if en else ('已登录' if _plugin_flag('stremio_loggedin') else '未登录或仅自定义源'))),
            ('service:nuvio', 'Nuvio · ' + (('Signed in' if _plugin_flag('nuvio_authenticated') else 'Not signed in') if en else ('已登录' if _plugin_flag('nuvio_authenticated') else '未登录'))),
            ('service:debrid', ('Debrid Services · Real-Debrid / AllDebrid / TorBox / PM' if en else 'Debrid 与加速服务 · Real-Debrid / AllDebrid / TorBox / PM')),
            ('service:search_sources', tr(32077, '检索源管理 · 默认源增删 / 子站点 / 自定义源', 'Search Sources · Default & Custom Sources')),
        ]
        return tr(32071, '用户服务', 'User Services'), rows, (None, ())
    return _menu_loop(dialog, build)


def _open_media_servers_view(dialog):
    import xbmc
    if not xbmc.getCondVisibility('System.HasAddon(plugin.video.bobbi.library)'):
        dialog.ok(
            tr(None, '片库组件未安装', 'Library Add-on Not Installed'),
            tr(None, '请用波比 TV 完整安装包修复，已保存的服务器连接保留。',
               'Repair using the full bobbi TV release bundle; saved server connections are kept.'),
        )
        return CANCELLED
    xbmc.executebuiltin('ActivateWindow(Videos,plugin://plugin.video.bobbi.library/?action=root&kind=media_server,return)')
    return NAVIGATED


def _manage_servers_domain(dialog):
    import xbmc
    import xbmcvfs
    from .libraries import LibraryError
    from .library_ui import message, registry
    from .pan_accounts import SERVER_PROVIDERS
    from .server_ui import add as add_server, manage as manage_server

    provider_labels = dict(SERVER_PROVIDERS)
    monitor = xbmc.Monitor()
    store = None
    changed = False
    navigated = False
    try:
        store = registry(xbmcvfs.translatePath)
        while not monitor.abortRequested():
            en = is_english()
            servers = [s for s in store.sources() if s.kind == 'media_server']
            active_emby = store.emby_binding()[0]
            rows = [
                ('+ Add Media Server · Emby / Jellyfin / Plex' if en else '＋ 添加媒体服务器 · Emby / Jellyfin / Plex'),
                ('Browse All Media Servers' if en else '浏览全部媒体服务器'),
            ]
            for src in servers:
                prov = provider_labels.get(src.metadata.get('provider'), 'Media Server' if en else '媒体服务器')
                is_active = (src.metadata.get('provider') == 'emby'
                             and active_emby is not None and active_emby.id == src.id)
                active_tag = (' · Active Account' if en else ' · 当前浏览账号') if is_active else ''
                rows.append(src.name + ' · ' + prov + active_tag)
            choice = dialog.select(tr(32072, '媒体服务器', 'Media Servers'), rows)
            if choice < 0 or choice >= len(rows):
                return CHANGED if changed else CANCELLED
            if choice == 0:
                changed = bool(add_server(dialog, store)) or changed
            elif choice == 1:
                if _open_media_servers_view(dialog) == NAVIGATED:
                    navigated = True
                    return NAVIGATED
            else:
                outcome = _normalize_outcome(manage_server(dialog, store, servers[choice - 2]))
                if outcome == NAVIGATED:
                    navigated = True
                    return NAVIGATED
                if outcome == CHANGED:
                    changed = True
    except (LibraryError, OSError, RuntimeError, ValueError) as error:
        dialog.ok(tr(None, '媒体服务器设置暂不可用', 'Media Server Settings Unavailable'), message(error))
    finally:
        if store is not None:
            store.close()
        if changed and not navigated:
            xbmc.executebuiltin('Container.Refresh')
    return CHANGED if changed else CANCELLED


def _manage_devices_domain(dialog):
    # Opening this menu strictly reads local state only and NEVER creates a phone session.
    def build():
        en = is_english()
        rows = [
            ('device:helper', ('BT Helper & Engine · ' if en else 'BT 助手与下载后台 · ') + _devices_summary()),
            ('device:stremio_phone', 'Manage Stremio via Phone · Confirm to open temporary QR' if en else '手机管理 Stremio 来源 · 需确认后开启临时扫码'),
            ('device:import_phone', 'Upload Library or T4 Config via Phone · Confirm to open temporary QR' if en else '手机上传片库或 T4 配置 · 需确认后开启临时扫码'),
            ('device:info', 'Phone & Device Security Info' if en else '手机与设备安全说明'),
        ]
        return tr(32074, '设备与手机', 'Devices & Phone'), rows, (None, ())
    return _menu_loop(dialog, build)


def _dispatch_action(action, dialog, value, mounts=()):
    """Single account/connection navigation dispatcher across all hub views."""
    if action == 'mounted':
        from .library_ui import open_existing_cd2
        return NAVIGATED if open_existing_cd2(dialog) else CANCELLED
    if action == 'status':
        dialog.textviewer(
            tr(None, '网盘状态与支持范围', 'Cloud Status & Support Scope'),
            connection_details(value, mounts),
        )
        return CANCELLED
    if action == 'account':
        from .cloud_ui import login
        return CHANGED if login() else CANCELLED
    if action == 'library':
        return _normalize_outcome(_manage_library())
    if action == 'cd2':
        _configure_cd2(dialog, value)
        return CANCELLED
    if action == 'transport':
        return CHANGED if transport(dialog) else CANCELLED
    if action == 'native':
        from .pan_ui import manage
        return NAVIGATED if manage(dialog) else CANCELLED
    if action == 'preparation_tasks':
        from .catalog_ui import watch_preparation
        watch_preparation(dialog=dialog)
        return CANCELLED
    if action == 'files':
        from .pan_ui import choose_files
        return NAVIGATED if choose_files(dialog) else CANCELLED
    if action == 'details':
        return details_outcome(dialog)
    if action == 'domain_services':
        return _manage_services_domain(dialog)
    if action == 'domain_servers':
        return _manage_servers_domain(dialog)
    if action == 'domain_cloud':
        return show_outcome(dialog)
    if action == 'domain_devices':
        return _manage_devices_domain(dialog)
    if isinstance(action, str) and action.startswith('service:'):
        return _manage_service_item(dialog, action.partition(':')[2])
    if action == 'device:helper':
        import xbmc
        xbmc.executebuiltin('RunScript(script.bobbi.setup,helper)')
        return NAVIGATED
    if action == 'device:stremio_phone':
        _run_plugin_action('stremio_manage_phone')
        return NAVIGATED
    if action == 'device:import_phone':
        _run_plugin_action('source_import_manage_phone')
        return NAVIGATED
    if action == 'device:info':
        dialog.ok(
            tr(None, '设备与手机权限范围', 'Device & Phone Permission Scope'),
            tr(None, '打开菜单不会开启端口或创建会话。所有手机扫码管理均限定在当前选定功能，关闭二维码窗口即刻撤销。',
               'Opening menus never opens ports or creates sessions. Every phone QR session is scoped strictly to the selected task and revoked immediately when closed.'),
        )
        return CANCELLED
    return CANCELLED


def _menu_loop(dialog, build_menu):
    import xbmc
    import xbmcgui
    dialog = dialog or xbmcgui.Dialog()
    monitor = xbmc.Monitor()
    changed = False
    while not monitor.abortRequested():
        heading, rows, context = build_menu()
        choice = dialog.select(heading, [label for _, label in rows])
        if choice < 0 or choice >= len(rows):
            return CHANGED if changed else CANCELLED
        outcome = _normalize_outcome(_dispatch_action(rows[choice][0], dialog, *context))
        if outcome == NAVIGATED:
            return NAVIGATED
        if outcome == CHANGED:
            changed = True
    return CHANGED if changed else CANCELLED


def details_outcome(dialog):
    def build():
        en = is_english()
        value = status()
        mounts = cd2_mounts.discover()
        rows = [
            ('status', 'Status & Support Scope' if en else '状态与支持范围'),
            ('account', ('115 Account · ' + account_label(value) + ' · Sign In / Switch / Sign Out') if en else ('115 账号 · ' + account_label(value) + ' · 登录 / 切换 / 退出')),
            ('library', 'Multi-Cloud / NAS Connections · Add / Check / Edit / Remove' if en else '多网盘 / NAS 连接 · 添加 / 检查 / 修改 / 移除'),
            ('cd2', ('115 Pre-stage (CD2) · ' if en else '115 提前存片（CD2） · ') + cd2_label(value['preparation'])),
            ('transport', 'Advanced · 115 Read Mode' if en else '高级 · 115 读取方式'),
            ('refresh', 'Refresh Status' if en else '刷新状态'),
            ('native', 'Native Multi-Cloud · Sign-In & Verification' if en else '原生多网盘 · 接入与验证'),
            ('preparation_tasks', '115 Preparation Tasks · Read-Only Live Status' if en else '115 准备任务 · 只读实时状态'),
        ]
        return tr(32076, '网盘详细管理', 'Cloud Advanced Management'), rows, (value, mounts)
    return _menu_loop(dialog, build)


def details(dialog):
    """Optional management layer sharing the single hub loop and action dispatcher."""
    return True if details_outcome(dialog) == NAVIGATED else None


def show_outcome(dialog=None):
    def build():
        en = is_english()
        value = status()
        account = account_label(value)
        rows = [
            ('account', ('115 Share Playback · ' if en else '115 分享播放 · ') + account),
            ('cd2', ('115 Pre-stage (CD2) · ' if en else '115 提前存片（CD2） · ') + cd2_label(value['preparation'])),
            ('library', 'My Library · Multi-Cloud / NAS' if en else '我的片库 · 多网盘 / NAS'),
            ('details', 'Advanced Management' if en else '详细管理'),
            ('refresh', 'Refresh Status' if en else '刷新状态'),
            ('files', 'My Files · Native Cloud' if en else '我的文件 · 原生网盘'),
        ]
        if cd2_mounts.discover():
            rows.insert(0, ('mounted', 'Use Existing CD2 Mount · No QR Needed' if en else '使用已有 CD2 网盘 · 无需扫码'))
        return tr(32075, '网盘账号与连接', 'Cloud Accounts & Connections'), rows, (value,)
    return _menu_loop(dialog, build)


def show(dialog=None):
    return True if show_outcome(dialog) == NAVIGATED else None


def show_accounts(dialog=None, domain=None):
    """Unified 4-domain Accounts & Sources Center returning NAVIGATED / CHANGED / CANCELLED."""
    import xbmcgui
    checked = validate_account_domain(domain)
    dialog = dialog or xbmcgui.Dialog()
    if checked == 'services':
        return _manage_services_domain(dialog)
    if checked == 'servers':
        return _manage_servers_domain(dialog)
    if checked == 'cloud':
        return show_outcome(dialog)
    if checked == 'devices':
        return _manage_devices_domain(dialog)

    def build():
        value = status()
        rows = [
            ('domain_services', tr(32071, '用户服务', 'User Services') + ' · ' + _services_summary()),
            ('domain_servers', tr(32072, '媒体服务器', 'Media Servers') + ' · ' + _servers_summary()),
            ('domain_cloud', tr(32073, '网盘与共享来源', 'Cloud Drives & Shared Sources') + ' · 115 ' + account_label(value)),
            ('domain_devices', tr(32074, '设备与手机', 'Devices & Phone') + ' · ' + _devices_summary()),
        ]
        return tr(32070, '账号与来源中心', 'Accounts & Sources Center'), rows, (value,)

    return _menu_loop(dialog, build)

"""Thin cloud settings UI; existing account, preparation and library owners."""
from .runtime import call
from . import cd2_mounts


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
    state = value.get('state')
    if state == 'RUNNING':
        dependency = value.get('dependency')
        if dependency == 'READY' and value.get('ready') is True:
            return '最近检查通过'
        if dependency == 'CHECKING':
            return '正在后台检查'
        if dependency == 'ACCOUNT_MISMATCH':
            return '网盘账号不一致'
        if dependency == 'DEPENDENCY_UNAVAILABLE':
            return '连接失败，请检查登录'
        return '尚未检查连接'
    return {'NOT_CONFIGURED': '未设置（可选）', 'STARTING': '正在启动',
            'WAITING_ACCOUNT': '等待登录 115', 'REVOKING': '正在切换账号',
            'UNAVAILABLE': '配置需要检查', 'STOPPED': '后台已停止',
            'HOST_UNAVAILABLE': '影院后台暂不可用'}.get(state, '状态暂不可用')


def cd2_details(value):
    return ('CD2 · ' + cd2_label(value) + '\n\n'
            '观看 115 分享片源无需 CD2。\n'
            '已有 CD2 挂载可直接在“我的片库”浏览，无需扫码。影院的 115 分享片源需单独登录一次。\n'
            '需要提前存片或挂载网盘时，请在 CloudDrive 中登录与影院相同的 115 账号。\n'
            '连接失败时，先到 CloudDrive 检查服务和登录状态。\n\n'
            '本页只显示后台状态，不会创建转存任务。文件是否就绪，请以选源页为准。')


def transport(dialog):
    import xbmcvfs
    from .environment import private_path
    from .transport_preferences import load, save
    root = private_path(xbmcvfs.translatePath, 'config.json').parent
    mode = load(root)
    selected = dialog.select('115 读取方式 · 重启 Kodi 后生效',
        ['整块读取（兼容模式）', '边下载边读取'], preselect=1 if mode else 0)
    if selected in (0, 1):
        save(root, selected == 1)
        dialog.ok('已保存', '重启 Kodi 后生效，不影响当前播放。两种方式都保持原画质和原音轨。')


def account_label(value):
    return {True: '已保存登录', False: '未登录', None: '后台暂不可用'}[value['authenticated']]


def connection_details(value, mounts):
    """Read-only projection; never enumerate cloud folders or expose credentials."""
    return ('115 分享播放 · ' + account_label(value) + '\n'
            'CD2 提前存片 · ' + cd2_label(value['preparation']) + '\n'
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
        dialog.textviewer('CD2 · 提前存片', cd2_details(value['preparation']))


def _manage_library():
    import xbmcvfs
    from .environment import private_path, load_config
    from .library_ui import manage
    config = load_config(private_path(xbmcvfs.translatePath, 'config.json'))
    return manage(config['library_root'])


def details(dialog):
    """Optional management layer; account and connection owners remain unchanged."""
    import xbmc
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        value = status()
        mounts = cd2_mounts.discover()
        rows = [('status', '状态与支持范围'),
                ('account', '115 账号 · ' + account_label(value) + ' · 登录 / 切换 / 退出'),
                ('library', '多网盘 / NAS 连接 · 添加 / 检查 / 修改 / 移除'),
                ('cd2', 'CD2 提前存片 · ' + cd2_label(value['preparation'])),
                ('transport', '高级 · 115 读取方式'),
                ('refresh', '刷新状态'),
                ('native', '原生多网盘 · 接入与验证')]
        choice = dialog.select('网盘详细管理', [label for _, label in rows])
        if choice < 0 or choice >= len(rows):
            return
        action = rows[choice][0]
        if action == 'status':
            dialog.textviewer('网盘状态与支持范围', connection_details(value, mounts))
        elif action == 'account':
            from .cloud_ui import login
            login()  # Capture a fresh account generation in the existing owner.
        elif action == 'library':
            if _manage_library():
                return True  # Propagate navigation through every enclosing menu.
        elif action == 'cd2':
            _configure_cd2(dialog, value)
        elif action == 'transport':
            transport(dialog)
        elif action == 'native':
            from .pan_ui import manage
            if manage(dialog):
                return True


def show(dialog=None):
    import xbmc
    import xbmcgui
    dialog = dialog or xbmcgui.Dialog()
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        value = status()
        account = account_label(value)
        rows = [('account', '115 分享播放 · ' + account),
                ('cd2', 'CD2 提前存片 · ' + cd2_label(value['preparation'])),
                ('library', '我的片库 · 多网盘 / NAS'),
                ('details', '详细管理'),
                ('refresh', '刷新状态')]
        if cd2_mounts.discover():
            rows.insert(0, ('mounted', '使用已有 CD2 网盘 · 无需扫码'))
        choice = dialog.select('网盘账号与连接', [label for _, label in rows])
        if choice < 0 or choice >= len(rows):
            return
        action = rows[choice][0]
        if action == 'mounted':
            from .library_ui import open_existing_cd2
            if open_existing_cd2(dialog):
                return True  # Do not cover the opened library with this menu.
        elif action == 'account':
            from .cloud_ui import login
            login()  # Existing QR cancellation and account-generation CAS.
        elif action == 'cd2':
            _configure_cd2(dialog, value)
        elif action == 'library':
            if _manage_library():
                return True
        elif action == 'details':
            if details(dialog):
                return True

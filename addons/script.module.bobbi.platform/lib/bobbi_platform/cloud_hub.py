"""Thin cloud settings UI; existing account, preparation and library owners."""
from .runtime import call


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
    return {'NOT_CONFIGURED': '未接入（可选）', 'STARTING': '正在启动',
            'WAITING_ACCOUNT': '等待登录 115', 'REVOKING': '正在切换账号',
            'UNAVAILABLE': '配置需要检查', 'STOPPED': '后台已停止',
            'HOST_UNAVAILABLE': '影院后台暂不可用'}.get(state, '状态暂不可用')


def cd2_details(value):
    return ('CD2 · ' + cd2_label(value) + '\n\n'
            '观看 115 分享片源无需 CD2。\n'
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


def show(dialog=None):
    import xbmc
    import xbmcgui
    import xbmcvfs
    from .environment import private_path, load_config
    dialog = dialog or xbmcgui.Dialog()
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        value = status()
        account = {True: '已保存登录', False: '未登录', None: '后台暂不可用'}[value['authenticated']]
        rows = [('account', '115 账号 · ' + account),
                ('cd2', 'CD2 提前存片 · ' + cd2_label(value['preparation'])),
                ('library', '我的片库'),
                ('transport', '115 读取方式'),
                ('refresh', '刷新状态')]
        choice = dialog.select('网盘账号与 CD2', [label for _, label in rows])
        if choice < 0 or choice >= len(rows):
            return
        action = rows[choice][0]
        if action == 'account':
            from .cloud_ui import login
            login()  # Existing QR cancellation and account-generation CAS.
        elif action == 'cd2':
            dialog.textviewer('CD2 · 提前存片', cd2_details(value['preparation']))
        elif action == 'library':
            from .library_ui import manage
            config = load_config(private_path(xbmcvfs.translatePath, 'config.json'))
            if manage(config['library_root']):
                return True
        elif action == 'transport':
            transport(dialog)

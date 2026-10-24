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
            return '最近后台检查通过'
        if dependency == 'CHECKING':
            return '正在后台检查'
        if dependency == 'ACCOUNT_MISMATCH':
            return '网盘账号不一致'
        if dependency == 'DEPENDENCY_UNAVAILABLE':
            return '连接或账号检查暂未通过'
        return '尚未完成连接检查'
    return {'NOT_CONFIGURED': '未接入（可选）', 'STARTING': '正在启动',
            'WAITING_ACCOUNT': '等待登录 115', 'REVOKING': '正在切换账号',
            'UNAVAILABLE': '接入配置或依赖需要检查', 'STOPPED': '后台已停止',
            'HOST_UNAVAILABLE': '影院后台暂不可用'}.get(state, '状态暂不可用')


def cd2_details(value):
    return ('CD2 云准备 · ' + cd2_label(value) + '\n\n'
            '115 分享片源使用影院的扫码账号直连，不要求 CD2。\n'
            'CD2 用于已配置的云端准备和挂载；它自己的登录与影院账号分开管理，'
            '云准备时需要两边是同一 115 账号。\n'
            '这里读取现有后台状态，不另起服务、不转存、不重启或升级 CD2；'
            '检查通过不代表某个文件已准备好或可播放。\n\n'
            '若连接检查失败，请在现有 CloudDrive 管理页面检查服务和网盘登录。'
            '未接入时仍可使用 115 分享、本地与 NAS。')


def transport(dialog):
    import xbmcvfs
    from .environment import private_path
    from .transport_preferences import load, save
    root = private_path(xbmcvfs.translatePath, 'config.json').parent
    mode = load(root)
    selected = dialog.select('115 传输模式 · 下次启动 Kodi 生效',
        ['整块交付（回退模式）', '渐进交付（有界 8 MiB 队列）'], preselect=1 if mode else 0)
    if selected in (0, 1):
        save(root, selected == 1)
        dialog.ok('已保存，不中断当前播放', '下次启动 Kodi 后使用所选模式。\n'
                  '两种模式都保持原码流、原音轨，不转码，不整部缓存。')


def show(dialog=None):
    import xbmc
    import xbmcgui
    import xbmcvfs
    from .environment import private_path, load_config
    dialog = dialog or xbmcgui.Dialog()
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        value = status()
        account = {True: '已保存登录', False: '尚未登录', None: '后台暂不可用'}[value['authenticated']]
        rows = [('account', '115 账号 · ' + account),
                ('cd2', 'CD2 云准备 · ' + cd2_label(value['preparation'])),
                ('library', '我的片库 · 挂载目录 / NAS / WebDAV'),
                ('transport', '115 播放传输 · 渐进交付 / 整块回退'),
                ('refresh', '刷新后台状态（不连接云端、不自动播放）')]
        choice = dialog.select('网盘与 CD2', [label for _, label in rows])
        if choice < 0 or choice >= len(rows):
            return
        action = rows[choice][0]
        if action == 'account':
            from .cloud_ui import login
            login()  # Existing QR cancellation and account-generation CAS.
        elif action == 'cd2':
            dialog.textviewer('CD2 · 可选云准备', cd2_details(value['preparation']))
        elif action == 'library':
            from .library_ui import manage
            config = load_config(private_path(xbmcvfs.translatePath, 'config.json'))
            if manage(config['library_root']):
                return True
        elif action == 'transport':
            transport(dialog)

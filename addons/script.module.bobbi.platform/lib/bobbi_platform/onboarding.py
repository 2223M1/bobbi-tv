"""Plain-language first-run status; never equate installed with working."""

ENGINE_ERRORS = {
    'LOCAL_HTTP_UNAVAILABLE': '请先打开 bobbi 助手并点击“启动”，然后回来重试。',
    'LOCAL_HTTP_TIMEOUT': '本机助手响应超时，请打开助手查看状态，再回来重试。',
    'LOCAL_REQUEST_FAILED': '请先打开 bobbi 助手并点击“启动”，然后回来重试。',
    'ENGINE_AUTH_REJECTED': '配对已失效。请在助手重新导出配对文件，再导入一次。',
    'UNPROTECTED_OR_UNKNOWN_ENGINE': '后台端口被其他程序占用或不是受支持的助手，请打开助手查看状态。',
    'ENGINE_SETTINGS_NOT_ISOLATED': '助手设置与此版本不兼容，请在助手停止后重新启动，再重试。',
    'ENGINE_VERSION_MISMATCH': '助手与影院版本不配套，请安装同一发行版本后重试。',
    'METADATA_DEADLINE': '等待片源信息超时。可以重试，或手动选其他片源。',
    'NO_PLAYABLE_VIDEO_FILE': '这个片源没有可播放的视频文件，请手动选择其他片源。',
    'INVALID_PAIRING': '配对文件无效，请使用本机 bobbi 助手导出的文件。',
    'MAGNET_HASH_MISMATCH': '片源标识不一致，已停止解析。请刷新后重新选源。',
    'SELECTED_BTIH_REQUIRED': '这个片源缺少可核对的种子标识，请刷新后重新选源。',
}


def engine_message(code):
    return ENGINE_ERRORS.get(code, '本次未能连接或解析片源，请打开助手检查状态后重试。')


def steps(capabilities, library_root='', helper_state='not_paired', library_count=0):
    """Stable step IDs permit a simple remote-control menu and resumable UI."""
    kodi_ok = capabilities.get('standard_playback') is True
    helper_labels = {
        'android_builtin': '已内置，选源时启动',
        'ready': '已连接',
        'paired': '已配对，点此检查',
        'not_paired': '尚未连接', 'invalid': '需要重新配对', 'offline': '需要启动或重试',
        'adapter_ready': '已连接',
        'adapter_offline': '连接失败，点此重试',
        'adapter_invalid': '配置需要检查',
        'adapter_unavailable': '组件暂不可用',
        'adapter_configured': '已配置，点此检查',
    }
    library_label = ('需要检查' if library_count is None else
                     '已保存 %d 个来源' % library_count if library_count else
                     '原目录已保留' if library_root else '可跳过')
    return [
        ('check', '1. 检查播放器 · ' + ('通过' if kodi_ok else '需要处理')),
        ('helper', '2. BT 播放（可选）· ' + helper_labels.get(helper_state, '需要检查')),
        ('library', '3. 我的片库 · ' + library_label),
        ('language', '4. 原声与中文字幕'),
        ('test', '5. 选择视频试播'),
        ('cloud', '网盘账号与 CD2'),
        ('catalog', '海报与搜索设置'),
        ('cinema', '进入波比影院'),
        ('updates', '更新与恢复'),
        ('diagnostics', '检查与诊断'),
        ('status', '关于波比 TV'),
    ]


def summary(capabilities):
    if capabilities.get('standard_playback') is not True:
        return '暂时无法连接播放器，请重启 Kodi 后再检查。'
    return '播放器连接正常，可以选择视频试播。使用 115 或本地片库时，可跳过 BT 设置。'

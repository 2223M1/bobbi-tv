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
        'ready': '已连接（还需实播检验）',
        'not_paired': '尚未连接', 'invalid': '需要重新配对', 'offline': '需要启动或重试',
    }
    library_label = ('需要检查' if library_count is None else
                     '已保存 %d 个来源' % library_count if library_count else
                     '原目录已保留' if library_root else '可跳过')
    return [
        ('check', '1. 检查播放器 · ' + ('通过' if kodi_ok else '需要处理')),
        ('helper', '2. 可选 BT 后台（115 / NAS 无需）· ' + helper_labels.get(helper_state, '需要检查')),
        ('library', '3. 我的网盘 / NAS / 片库 · ' + library_label),
        ('language', '4. 原声与中文字幕 · 打开播放器设置'),
        ('test', '5. 试播自己的视频 · 手动选择，不自动播放'),
        ('cloud', '115 账号 · 用自己的手机扫码登录'),
        ('catalog', '影视海报与搜索 · 配置 TMDb / 自选检索服务'),
        ('cinema', '进入波比影院 · 切换新皮肤'),
        ('updates', '更新与恢复 · 原版插件管理 / 波比签名包'),
        ('status', '发行状态 · 私人候选与实机验收状态'),
    ]


def summary(capabilities):
    if capabilities.get('standard_playback') is not True:
        return ('尚未通过播放器检查。此版需要 Kodi 21；先确认安装版本，再点“重新检查”。\n'
                '没有修改现有 Kodi、账号或音画设置。')
    return ('Kodi 21 标准播放接口检查通过。\n'
            '这不代表影片、HDR、音频直通或自动续播已经验收。\n'
            '下一步可连接本机助手，或直接选择自己的视频测试。')

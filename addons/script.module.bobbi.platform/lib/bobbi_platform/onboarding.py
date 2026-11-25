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

_ENGINE_ERROR_SPECS = {
    'LOCAL_HTTP_UNAVAILABLE': (32017, '请先打开 bobbi 助手并点击“启动”，然后回来重试。',
                               'Open bobbi Helper and tap "Start" first, then return and retry.'),
    'LOCAL_HTTP_TIMEOUT': (32018, '本机助手响应超时，请打开助手查看状态，再回来重试。',
                           'Local Helper timed out. Open Helper to check its status, then retry.'),
    'LOCAL_REQUEST_FAILED': (32017, '请先打开 bobbi 助手并点击“启动”，然后回来重试。',
                             'Open bobbi Helper and tap "Start" first, then return and retry.'),
    'ENGINE_AUTH_REJECTED': (32019, '配对已失效。请在助手重新导出配对文件，再导入一次。',
                             'Pairing expired. Export a new pairing file in Helper and import it again.'),
    'UNPROTECTED_OR_UNKNOWN_ENGINE': (32020, '后台端口被其他程序占用或不是受支持的助手，请打开助手查看状态。',
                                      'Port is occupied by another app or an unsupported helper. Open Helper to check status.'),
    'ENGINE_SETTINGS_NOT_ISOLATED': (32021, '助手设置与此版本不兼容，请在助手停止后重新启动，再重试。',
                                     'Helper settings are incompatible with this version. Stop and restart Helper, then retry.'),
    'ENGINE_VERSION_MISMATCH': (32022, '助手与影院版本不配套，请安装同一发行版本后重试。',
                                'Helper and Cinema versions do not match. Install the matching release and retry.'),
    'METADATA_DEADLINE': (32023, '等待片源信息超时。可以重试，或手动选其他片源。',
                          'Timed out waiting for source metadata. Retry or pick another source manually.'),
    'NO_PLAYABLE_VIDEO_FILE': (32024, '这个片源没有可播放的视频文件，请手动选择其他片源。',
                               'No playable video file found in this source. Please pick another source.'),
    'INVALID_PAIRING': (32025, '配对文件无效，请使用本机 bobbi 助手导出的文件。',
                        'Invalid pairing file. Use the file exported by bobbi Helper on this device.'),
    'MAGNET_HASH_MISMATCH': (32026, '片源标识不一致，已停止解析。请刷新后重新选源。',
                             'Source hash mismatch; resolution stopped. Refresh and select a source again.'),
    'SELECTED_BTIH_REQUIRED': (32027, '这个片源缺少可核对的种子标识，请刷新后重新选源。',
                               'Missing verifiable torrent hash. Refresh and select a source again.'),
}


def _tr(msg_id, zh_text, en_text):
    from .i18n import tr
    return tr(msg_id, zh_text, en_text)


def engine_message(code):
    spec = _ENGINE_ERROR_SPECS.get(code)
    if spec is not None:
        return _tr(*spec)
    return _tr(
        32028,
        '本次未能连接或解析片源，请打开助手检查状态后重试。',
        'Could not connect or resolve this source. Open Helper to check status and retry.',
    )


def steps(capabilities, library_root='', helper_state='not_paired', library_count=0):
    """Stable step IDs permit a simple remote-control menu and resumable UI."""
    kodi_ok = capabilities.get('standard_playback') is True
    helper_specs = {
        'android_builtin': (32029, '已内置，选源时启动', 'Built-in'),
        'ready': (32030, '已连接', 'Connected'),
        'paired': (32031, '已配对，点此检查', 'Paired, check'),
        'not_paired': (32032, '尚未连接', 'Not paired'),
        'invalid': (32033, '需要重新配对', 'Re-pair'),
        'offline': (32034, '需要启动或重试', 'Start/retry'),
        'adapter_ready': (32030, '已连接', 'Connected'),
        'adapter_offline': (32035, '连接失败，点此重试', 'Retry check'),
        'adapter_invalid': (32036, '配置需要检查', 'Check config'),
        'adapter_unavailable': (32037, '组件暂不可用', 'Unavailable'),
        'adapter_configured': (32038, '已配置，点此检查', 'Check status'),
    }
    helper_label = _tr(*helper_specs.get(helper_state, (32039, '需要检查', 'Needs check')))
    library_label = (
        _tr(32039, '需要检查', 'Needs check')
        if library_count is None
        else (_tr(32040, '已保存 %d 个来源', '%d sources') % library_count)
        if library_count
        else _tr(32041, '原目录已保留', 'Kept folder')
        if library_root
        else _tr(32042, '可跳过', 'Skippable')
    )
    check_state = _tr(32043, '通过', 'OK') if kodi_ok else _tr(32044, '需要处理', 'Action needed')
    return [
        ('check', _tr(32045, '1. 检查播放器 · %s', '1. Player · %s') % check_state),
        ('helper', _tr(32046, '2. BT 播放（可选）· %s', '2. BT (Optional) · %s') % helper_label),
        ('library', _tr(32047, '3. 我的片库 · %s', '3. My Library · %s') % library_label),
        ('language', _tr(32048, '4. 原声与中文字幕', '4. Audio & Subtitles')),
        ('test', _tr(32049, '5. 选择视频试播', '5. Test Playback')),
        ('cloud', _tr(32050, '网盘账号与 CD2', 'Cloud Accounts & CD2')),
        ('catalog', _tr(32051, '海报与搜索设置', 'Posters & Search')),
        ('cinema', _tr(32052, '进入波比影院', 'Enter bobbi Cinema')),
        ('updates', _tr(32053, '更新与恢复', 'Updates & Recovery')),
        ('diagnostics', _tr(32054, '检查与诊断', 'Check & Diagnostics')),
        ('status', _tr(32055, '关于波比 TV', 'About bobbi TV')),
    ]


def summary(capabilities):
    if capabilities.get('standard_playback') is not True:
        return _tr(
            32056,
            '暂时无法连接播放器，请重启 Kodi 后再检查。',
            'Cannot connect to the player right now. Restart Kodi and check again.',
        )
    return _tr(
        32057,
        '播放器连接正常，可以选择视频试播。使用 115 或本地片库时，可跳过 BT 设置。',
        'Player connection is ready for test playback. You can skip BT setup when using 115 or local libraries.',
    )

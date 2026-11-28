"""User-facing interpretation of existing startup outcomes; confers no retry or seek rights."""
_MESSAGES = {
    'invalid_binding': ('文件身份信息不一致，请刷新后重新选择片源。', 'File identity is inconsistent. Refresh and select the source again.'),
    'selected_file_missing': ('所选文件已变化或已不在该片源中，请返回选源。', 'The selected file changed or is no longer in this source. Return to sources.'),
    'no_candidate': ('该片源没有合格的正片文件，请选择其他片源。', 'No eligible feature file in this source. Choose another source.'),
    'metadata_timeout': ('读取种子文件列表超时，请重试或换源。', 'Timed out reading the torrent file list. Retry or choose another source.'),
    'buffer_timeout': ('所选视频未缓冲到可起播的数据，请在原列表重试或换源。', 'The selected video did not buffer enough to start. Retry here or choose another source.'),
    'preload_error': ('所选视频预载失败，请重试或换源。', 'Preloading the selected video failed. Retry or choose another source.'),
    'startup_timeout': ('播放器未及时确认起播，请重试或换源。', 'Playback did not report a start in time. Retry or choose another source.'),
    'fullscreen_denied': ('视频未能进入全屏，已停止本次播放，请重试。', 'Could not enter fullscreen. Playback was stopped; please retry.'),
    'torrent_download_timeout': ('下载种子超时，请重试或换源。', 'The torrent download timed out. Retry or choose another source.'),
    'torrent_download_failed': ('未取得有效种子，请刷新片源后重试。', 'No valid torrent was received. Refresh the sources and retry.'),
    'torrserver_error': ('本机 BT 服务未能提供所选视频，请重试或换源。', 'The local BT service could not deliver this video. Retry or choose another source.'),
    'source_identity_mismatch': ('种子与所选片源不符，已停止播放准备。请刷新片源。', 'The torrent does not match the selected source. Refresh the sources.'),
}


def startup_message(category, *, episode=False, english=False):
    if category == 'target_unresolved':
        pair = (('无法确认所选集数，请换一个片源。', 'Could not verify this episode. Choose another source.') if episode else
                ('无法确认所选正片，请换一个片源。', 'Could not verify the selected feature. Choose another source.'))
    elif category in ('cancelled', 'aborted'):
        pair = ('播放准备已中止，请重新选源。', 'Playback preparation stopped. Select a source again.')
    else:
        pair = _MESSAGES.get(category if isinstance(category,str) else '',
            ('该片源暂时无法播放，请选择其他片源或重试。', 'Playback is unavailable. Choose another source or retry.'))
    return pair[bool(english)]


def failure_domain(category):
    """Only known terminal categories get a layer in exported diagnostics."""
    if category in ('share_revoked','share_unavailable','source_identity_mismatch','torrent_download_timeout','torrent_download_failed','metadata_timeout','torrserver_error'):
        return 'source'
    if category in ('no_candidate','invalid_binding','target_unresolved','selected_file_missing','identity_changed'):
        return 'file_selection'
    if category in ('preload_error','buffer_timeout'):
        return 'file_buffer'
    if category in ('fullscreen_denied','startup_timeout'):
        return 'player_output'
    return None

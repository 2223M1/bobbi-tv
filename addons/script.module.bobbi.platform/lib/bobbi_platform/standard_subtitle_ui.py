"""One explicit user action for a late standard-player subtitle candidate."""


def request_id(player):
    if callable(getattr(player, 'getPlayingItem', None)):
        value = player.getPlayingItem().getProperty('bobbi.standard.request')
        if value:
            return value
    return player.getVideoInfoTag().getUniqueID('bobbi_request')


def offer(player, dialog, call):
    try:
        request = request_id(player)
        if not request:
            return False
        candidate = call('standard_playback', dict(operation='subtitle_candidate', request_id=request))
        if not candidate:
            return False
        choice = dialog.select('中文字幕', ['加载本片已匹配的中文候选', '继续搜索其他字幕'])
        if choice == 1:
            return False
        if choice == 0:
            # This is the user's own action, not a late automatic retry. Stock
            # Kodi lacks atomic conditional setters; never queue/retry it.
            current = call('standard_playback', dict(operation='subtitle_candidate', request_id=request))
            if (current == candidate and player.isPlayingVideo() and request_id(player) == request
                    and player.getPlayingFile() == candidate['url'].partition('|')[0]):
                player.setSubtitles(candidate['file'])
        return True
    except (AttributeError, ValueError, RuntimeError, OSError):
        return False

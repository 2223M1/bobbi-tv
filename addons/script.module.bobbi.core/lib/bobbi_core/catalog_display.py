"""IO-free descriptions shared by version rows, history and management clients."""
from datetime import datetime, timezone


def _media_facts(card):
    from .file_media_facts import checked
    try:
        return checked(card.get('media_facts'), card.get('observation_key'))
    except (ValueError, TypeError, KeyError):
        return None


def _duration(value):
    seconds = int(value)
    return '%d:%02d:%02d' % (seconds // 3600, seconds // 60 % 60, seconds % 60)


def size_label(value):
    if type(value) is not int or value <= 0:
        return ''
    for suffix in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or suffix == 'TiB':
            return ('%.1f' % value).rstrip('0').rstrip('.') + ' ' + suffix
        value /= 1024


def file_description(card, position=None, duration=None):
    pieces = []
    if card.get('version_label'):
        pieces.append('人工备注：' + card['version_label'])
    size = size_label(card.get('file_size'))
    if size:
        pieces.append(size + '（来源目录记录）')
    facts = _media_facts(card)
    if facts and facts['duration_seconds'] is not None:
        pieces.append('历史观测时长 ' + _duration(facts['duration_seconds']) if facts['state'] == 'matched'
                      else '历史时长待重新核验')
    if position is not None and position > 0:
        pieces.append('上次播放此文件 · %d:%02d' % (position // 60, position % 60))
        if not duration:
            pieces.append('总时长未知')
    return ' · '.join(pieces)


def media_facts_text(card):
    # The catalogue's filename and user version note are not detector output.
    facts = _media_facts(card)
    evidence = ['时长：未知（没有此文件的匹配历史观测）']
    if facts and facts['duration_seconds'] is not None:
        duration = _duration(facts['duration_seconds'])
        evidence = [
            '时长：' + duration if facts['state'] == 'matched' else
                '当前文件时长未知；旧观察记录为 ' + duration + '，待重新核验。',
            '依据：播放器历史观测时长，不是探测总时长，也不保证片尾完整。',
            '历史记录时间：' + datetime.fromtimestamp(facts['recorded_at'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            '历史文件观察：' + facts['observation_key'],
            '与当前已保存的完整文件观察匹配；未做实时文件核验。' if facts['state'] == 'matched' else
                '历史观察与当前目录记录不同；保留原证据，不用于当前文件时长或播放判断。',
        ]
    streams = ['音轨：未知', '字幕：未知']
    video = ['分辨率：未知', '视频编码：未知']
    if facts and facts['state'] == 'matched' and 'playback_start' in facts:
        start = facts['playback_start']
        observed = start['facts']
        selected_video = observed.get('video')
        if selected_video is not None:
            if selected_video['width'] is not None and selected_video['height'] is not None:
                video[0] = '启动时视频分辨率：%d × %d' % (selected_video['width'], selected_video['height'])
            if selected_video['codec'] is not None:
                video[1] = '启动时视频编码：' + selected_video['codec']
            video.append('依据：该次启动时播放器报告的视频流；不代表显示输出、HDR 或直接播放／转码模式。')
        audio, subtitle = observed['audio'], observed['subtitle']
        if audio is not None:
            fields = [audio['codec'], str(audio['channels']) + ' 声道' if audio['channels'] else None, audio['language']]
            streams[0] = '启动时选中音轨：' + (' · '.join(filter(None, fields)) or '属性未知')
        if subtitle is not None:
            fields = [subtitle['language'], subtitle['name'],
                      '强制标记' if subtitle['forced'] is True else None,
                      '听障标记' if subtitle['impaired'] is True else None]
            streams[1] = '启动时选中字幕：' + (' · '.join(filter(None, fields)) or '属性未知')
        streams += ['启动时播放器目录：%d 音轨 / %d 字幕；字幕显示设置%s。' % (
            observed['audio_count'], observed['subtitle_count'], '开启' if observed['subtitle_visible'] else '关闭'),
            '启动快照时间：' + datetime.fromtimestamp(start['recorded_at'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            '仅为该次播放启动观察，不是永久选择；不证明字幕内嵌、实际渲染、音频直通或服务器转码。']
    elif facts and 'playback_start' in facts:
        streams.append('旧启动观察与当前文件记录不同，音轨和字幕待重新核验。')
        if 'video' in facts['playback_start']['facts']:
            video.append('旧启动视频观察与当前文件记录不同，分辨率和视频编码待重新核验。')
    description = ''
    if card.get('server_description') is not None:
        from .server_description import text
        try:
            description = text(card['server_description'])
        except (ValueError, TypeError, KeyError):
            pass
    return '\n'.join(filter(None, [card.get('file_name') or card.get('display_title'), description,
        file_description(card), *evidence,
        *video, 'HDR：未知', *streams,
        '文件大小来自目录观察，版本备注来自人工整理；均不证明编码、剪辑时间轴或当前可播放性。',
        '实际播放仍会核验当前账号与原文件，不会自动改用其他版本。']))

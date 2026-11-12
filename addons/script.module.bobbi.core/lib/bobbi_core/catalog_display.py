"""IO-free descriptions shared by version rows, history and management clients."""


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
    if position is not None and position > 0:
        pieces.append('上次播放此文件 · %d:%02d' % (position // 60, position % 60))
        if not duration:
            pieces.append('总时长未知')
    return ' · '.join(pieces)


def media_facts_text(card):
    # The catalogue's filename and user version note are not detector output.
    return '\n'.join(filter(None, [card.get('file_name') or card.get('display_title'),
        file_description(card), '分辨率 / 编码 / HDR / 音轨 / 字幕：尚无此文件的已核对检测结果。',
        '文件大小来自目录观察，版本备注来自人工整理；均不证明编码、剪辑时间轴或当前可播放性。',
        '实际播放仍会核验当前账号与原文件，不会自动改用其他版本。']))

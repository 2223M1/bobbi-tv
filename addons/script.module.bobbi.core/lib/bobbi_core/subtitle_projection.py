"""Bound subtitle metadata for local cards, never permission to apply a track.

No subtitle/font reads, cloud queries or Kodi calls in the UI. Actual playback
still checks the resource, native request, immutable bytes and font activation.
"""
import json
import re


def generation(db):
    row = db.execute("SELECT value FROM settings WHERE key='subtitle_generation'").fetchone()
    return int(row[0]) if row else 0


def checked(value, video):
    if (not isinstance(value, dict) or set(value) != {
            'kind', 'video_key', 'subtitle_sha256', 'fonts_ready'}
            or value['kind'] != 'external_chinese_binding'
            or value['video_key'] != video['key']
            or not re.fullmatch('[0-9a-f]{64}', str(value['subtitle_sha256']))
            or type(value['fonts_ready']) is not bool):
        raise ValueError('Subtitle card metadata belongs to another binding')
    return dict(value)


def records(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='subtitle_current'").fetchone():
        return {}
    result = {}
    rows = db.execute('''SELECT c.video_key,r.payload FROM subtitle_current c
        JOIN subtitle_revisions r ON c.revision=r.seq ORDER BY c.binding_key LIMIT 8193''').fetchall()
    if len(rows) > 8192:
        raise ValueError('Subtitle projection record budget')
    for row in rows:
        record = json.loads(row['payload'])
        if (record.get('chinese_ready') is not True or record.get('full_dialogue') is not True
                or record.get('forced') is not False or record.get('manual_intent') != 0
                or record.get('extension') not in {'.srt', '.ass', '.ssa', '.vtt'}
                or record['video']['key'] != row['video_key']):
            continue
        value = checked(dict(kind='external_chinese_binding', video_key=row['video_key'],
            subtitle_sha256=record['subtitle_sha256'], fonts_ready=record['fonts_ready']), record['video'])
        previous = result.get(row['video_key'])
        if previous is None or (value['fonts_ready'] and not previous['fonts_ready']):
            result[row['video_key']] = value
    return result


def source_label(source):
    value = getattr(source, 'preparedSubtitle', None)
    if (not isinstance(value, dict) or getattr(source, 'type', '') != 'Direct'
            or not str(getattr(source, 'guid', '')).startswith('bobi:')
            or not getattr(source, 'preparedResourceId', '')
            or value.get('kind') != 'external_chinese_binding'
            or type(value.get('fonts_ready')) is not bool):
        return ''
    return '外挂中文已绑定·播放时复核' if value['fonts_ready'] else '外挂中文已校时·字体样式待复核'


def source_card_label(source):
    """Short badge only; the full qualification remains in source_label/reason."""
    if not source_label(source):
        return ''
    return '已绑定·待复核' if source.preparedSubtitle['fonts_ready'] else '已校时·字体待验'

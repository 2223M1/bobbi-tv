"""Query Kodi's real TV channels without exposing stream URLs."""
import re
import unicodedata
from datetime import datetime, timezone


def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    digits = {char: str(index) for index, char in enumerate('零一二三四五六七八九')}
    digits['两'] = '2'
    def station(match):
        number = match[1]
        if '十' in number:
            tens, units = number.split('十', 1)
            number = str(int(digits.get(tens, tens) or '1') * 10 + int(digits.get(units, units) or '0'))
        else:
            number = ''.join(digits.get(char, char) for char in number)
        return 'cctv' + str(int(number))
    text = re.sub(r'(?:cctv|央视|中央)\s*[-－—]?\s*([零一二两三四五六七八九十\d]+)\s*(?:套|台|频道)?', station, text)
    text = re.sub(r'(cctv\d+)(?:加|plus)', r'\1+', text)
    return re.sub(r'[\s\-－—_·]+', '', text)


def _channels(rpc, cancelled, extra=()):
    if not rpc('PVR.GetProperties', {'properties': ['available']}).get('available'):
        raise ValueError('Kodi 直播电视尚未就绪，请先配置 PVR 客户端和频道。')
    rows, seen, start = [], set(), 0
    while True:
        if cancelled():
            raise InterruptedError('已取消频道查询。')
        result = rpc('PVR.GetChannels', {'channelgroupid': 'alltv',
            'properties': ['channel', 'channeltype', 'channelnumber', 'subchannelnumber', 'hidden', 'locked', 'thumbnail'] + list(extra),
            'limits': {'start': start, 'end': start + 500}})
        batch = result.get('channels', [])
        for row in batch:
            identifier = row.get('channelid')
            if type(identifier) is not int or identifier < 1 or identifier in seen or row.get('hidden'):
                continue
            if row.get('channeltype', 'tv') != 'tv':
                continue
            seen.add(identifier)
            rows.append(row)
        start += len(batch)
        if not batch or start >= result.get('limits', {}).get('total', start):
            break
    return rows


def _matches(row, query):
    name = normalize(row.get('channel') or row.get('label', ''))
    if not query:
        return True
    if query.isdecimal():
        return int(query) == row.get('channelnumber')
    if re.fullmatch(r'cctv\d+\+?', query):
        actual = re.match(r'cctv\d+\+?', name)
        return actual is not None and actual[0] == query
    return query in name


def _selected(rows, query):
    return sorted((row for row in rows if _matches(row, query)), key=lambda row: (
        normalize(row.get('channel') or row.get('label', '')) != query,
        row.get('channelnumber', 0), row.get('subchannelnumber', 0), row['channelid']))


def search(rpc, query='', offset=0, limit=12, cancelled=lambda: False):
    rows = _channels(rpc, cancelled)
    query = normalize(query.strip())
    station = re.fullmatch(r'cctv\d+\+?', query)
    matches = _selected(rows, query)
    preferred = next((row for row in matches if not row.get('locked')), None) if query and (station or len(matches) == 1) else None
    # The recommended ID must be visible in this page, never an unreturned ID.
    selected = matches[offset:offset + limit]
    preferred_id = preferred['channelid'] if preferred in selected else None
    return {'channels': selected, 'total': len(matches),
            'next_offset': offset + limit if offset + limit < len(matches) else None,
            'preferred_id': preferred_id,
            'note': '同一央视台有多条线路时，按 Kodi 频道顺序推荐第一条未锁定线路。' if station and len(matches) > 1 else ''}


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        # Kodi JSON-RPC EPG timestamps without an offset are UTC.
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def _broadcast(value, now, current=True):
    if not isinstance(value, dict) or not value.get('title'):
        return None
    start, end = _time(value.get('starttime')), _time(value.get('endtime'))
    if current and (value.get('isactive') is False or start and start > now or end and end <= now):
        return None
    if not current and (end and end <= now):
        return None
    result = {key: value[key] for key in ('broadcastid', 'title', 'originaltitle', 'genre',
        'year', 'isseries', 'episodename', 'episodenum', 'seasonnum') if key in value}
    for key in ('plotoutline', 'plot'):
        if value.get(key):
            result[key] = re.sub(r'\[/?(?:COLOR(?: [^\]]*)?|B|I)\]', '', value[key], flags=re.I)[:600]
    for key, date in (('starttime', start), ('endtime', end)):
        if date:
            result[key] = date.astimezone().isoformat(timespec='seconds')
    return result


def epg(rpc, query='', offset=0, limit=200, include_next=False, cancelled=lambda: False):
    """Expose actual current EPG for the model to interpret; do not classify genres."""
    fields = ['broadcastnow'] + (['broadcastnext'] if include_next else [])
    rows = _selected(_channels(rpc, cancelled, fields), normalize(query.strip()))
    now = datetime.now(timezone.utc)
    programs = []
    for row in rows:
        if cancelled():
            raise InterruptedError('已取消节目单查询。')
        item = {key: value for key, value in row.items() if key not in ('broadcastnow', 'broadcastnext')}
        item['current_program'] = _broadcast(row.get('broadcastnow'), now)
        if include_next:
            item['next_program'] = _broadcast(row.get('broadcastnext'), now, current=False)
        programs.append(item)
    available = sum(row['current_program'] is not None for row in programs)
    end = offset + limit
    return {'channels': programs[offset:end], 'total': len(programs),
        'with_current_program': available, 'without_current_program': len(programs) - available,
        'next_offset': end if end < len(programs) else None,
        'queried_at': now.astimezone().isoformat(timespec='seconds'),
        'note': '时间带时区偏移。节目来自 Kodi EPG；类型可能为未知，请结合实际节目名称和简介判断。current_program=null 表示当前节目单缺失，不能据频道名称断言正在播什么。'}

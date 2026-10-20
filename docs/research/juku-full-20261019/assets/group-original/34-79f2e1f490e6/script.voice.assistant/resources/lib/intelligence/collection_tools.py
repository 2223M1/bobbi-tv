"""Verified video queues and opaque favourite references; media paths never reach the model."""
import hashlib
import json
import re
from .library_tools import verified
from .ui_context import text


def queue_rows(tools):
    value = tools.rpc('Playlist.GetItems', {'playlistid': 1, 'properties': ['title', 'file'],
                      'limits': {'start': 0, 'end': 10000}})
    rows = value.get('items', [])
    if value.get('limits', {}).get('total', len(rows)) != len(rows):
        raise ValueError('待播队列过长或查询不完整，未修改。')
    return rows


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def player_position(tools):
    players = tools.rpc('Player.GetActivePlayers', {})
    if not any(row['playerid'] == 1 for row in players):return -1
    value = tools.rpc('Player.GetProperties', {'playerid': 1, 'properties': ['playlistid', 'position']})
    return value.get('position', -1) if value.get('playlistid') == 1 else -1


def get_playlist(tools, offset=0, limit=30, cancelled=lambda: False):
    tools.latest_matches = []
    rows = queue_rows(tools)
    tools.playlist_snapshot = fingerprint(rows)
    matches = []
    for position, row in enumerate(rows[offset:offset + limit], offset):
        item = {'position': position, 'title': text(row.get('title') or row.get('label')), 'type': row.get('type')}
        if row.get('type') in ('movie', 'episode') and type(row.get('id')) is int and row['id'] > 0:
            item.update(tools._remember([dict(row, **{row['type'] + 'id': row['id']})], row['type'])[0])
        matches.append(item)
    return {'items': matches, 'position': player_position(tools), 'total': len(rows),
            'next_offset': offset + len(matches) if matches and offset + len(matches) < len(rows) else None}


def edit_playlist(tools, action, kind=None, id=None, position=None, to=None, cancelled=lambda: False):
    rows = queue_rows(tools)
    if action in ('remove', 'move'):
        if tools.playlist_snapshot is None or tools.playlist_snapshot != fingerprint(rows):
            raise ValueError('待播队列尚未查询或已经变化，请先重新查询队列。')
        if position is None or position >= len(rows):raise ValueError('队列下标不存在。')
    if action in ('add', 'play_next'):
        if kind is None or id is None:raise ValueError('入队需要已查询的媒体类型和ID。')
        verified(tools, kind, id)
        item = {kind + 'id': id}
        if action == 'add':tools.rpc('Playlist.Add', {'playlistid': 1, 'item': item})
        else:
            target = max(0, player_position(tools) + 1)
            tools.rpc('Playlist.Insert', {'playlistid': 1, 'position': min(target, len(rows)), 'item': item})
    elif action == 'remove':tools.rpc('Playlist.Remove', {'playlistid': 1, 'position': position})
    elif action == 'move':
        if to is None or to >= len(rows):raise ValueError('目标队列下标不存在。')
        step = 1 if to > position else -1
        for current in range(position, to, step):
            if cancelled():raise InterruptedError('已取消，已完成的队列调整不会自动撤销。')
            tools.rpc('Playlist.Swap', {'playlistid': 1, 'position1': current, 'position2': current + step})
    else:tools.rpc('Playlist.Clear', {'playlistid': 1})
    tools.playlist_snapshot = None
    tools.acted = True
    return {'updated': action, 'queue': get_playlist(tools)}


def play_playlist(tools, position=0, resume=True, cancelled=lambda: False):
    rows = queue_rows(tools)
    if tools.playlist_snapshot is None or tools.playlist_snapshot != fingerprint(rows):
        raise ValueError('队列尚未查询或已经变化，请先查询队列。')
    if position >= len(rows):raise ValueError('队列没有这个下标。')
    first, resume_seconds = rows[position], 0
    if resume:
        kind, identifier = first.get('type'), first.get('id')
        if kind in ('movie', 'episode') and type(identifier) is int and identifier > 0:
            value = tools.rpc('VideoLibrary.Get' + ('Movie' if kind == 'movie' else 'Episode') + 'Details',
                              {kind + 'id': identifier, 'properties': ['resume']})[kind + 'details']
            resume_seconds = value.get('resume', {}).get('position', 0)
    from .playback_tools import start_queue
    start_queue(tools, position, first, resume_seconds, cancelled)
    result = {'requested_position': position, 'title': text(rows[position].get('title') or rows[position].get('label'))}
    if tools.defer_ui:return dict(result, **tools._queue_ui('ActivateWindow(FullscreenVideo)', 'video_queue'))
    tools.builtin('ActivateWindow(FullscreenVideo)');tools.fullscreen_requested = True
    return result


def episodes(tools, tvshowid, cancelled):
    verified(tools, 'tvshow', tvshowid)
    rows, seen, total = [], set(), None
    while len(rows) < 10000:
        if cancelled():raise InterruptedError('已取消。')
        start = len(rows)
        value = tools.rpc('VideoLibrary.GetEpisodes', {'tvshowid': tvshowid,
            'properties': ['title', 'showtitle', 'season', 'episode', 'resume', 'playcount', 'lastplayed'],
            'limits': {'start': start, 'end': start + 200}, 'sort': {'method': 'episode', 'order': 'ascending'}})
        batch, limits = value.get('episodes', []), value.get('limits', {})
        reported = limits.get('total')
        ids = [row['episodeid'] for row in batch]
        if (total is not None and reported != total or len(set(ids)) != len(ids) or seen.intersection(ids)
                or limits.get('start', start) != start or reported is not None and
                (start + len(batch) > reported or not batch and start < reported)):
            raise ValueError('剧集分页发生变化，未构建播放队列，请重新查询。')
        total = reported;seen.update(ids);rows.extend(batch)
        if total is not None and len(rows) == total or total is None and len(batch) < 200:
            return sorted(rows, key=lambda row: (row.get('season', 0), row.get('episode', 0), row['episodeid']))
    raise ValueError('剧集过多，未完整读取，未构建队列。')


def playlist_item(row):
    if row.get('type') in ('movie', 'episode') and type(row.get('id')) is int and row['id'] > 0:
        return {row['type'] + 'id': row['id']}
    if row.get('file'):return {'file': row['file']}
    raise ValueError('旧队列包含无法恢复的项目，未替换队列。')


def play_tvshow_queue(tools, tvshowid, season=None, episode=None, resume=True, cancelled=lambda: False):
    if episode is not None and season is None:raise ValueError('指定起始集时请同时指定季号。')
    rows = episodes(tools, tvshowid, cancelled)
    if not rows:raise ValueError('这部电视剧没有已入库的剧集。')
    if season is not None:
        candidates = [row for row in rows if row.get('season') == season
                      and (episode is None or row.get('episode') == episode)]
        if not candidates:raise ValueError('媒体库没有指定季集。')
        selected = candidates[0]
    else:
        from .watch_progress import beginning, continuation
        progress = continuation(rows) if resume else beginning(rows)
        if not progress.get('recommended'):
            result = dict(progress)
            result['candidates'] = tools._remember(progress.get('candidates', [])[:30], 'episode')
            tools.latest_matches = result['candidates']
            return dict(result, started=False, note='起点不明确，尚未替换队列，请先选择季集。')
        selected = progress['recommended']
    start = next(index for index, row in enumerate(rows) if row['episodeid'] == selected['episodeid'])
    versions = {}
    for row in rows[start:]:versions.setdefault((row.get('season', 0), row.get('episode', 0)), []).append(row)
    duplicate = next((batch for batch in versions.values() if len(batch) > 1), None)
    if duplicate:
        candidates = tools._remember(duplicate[:30], 'episode')
        tools.latest_matches = candidates
        return {'started': False, 'status': 'multiple_versions', 'candidates': candidates,
                'note': '后续剧集存在多个版本，未替换队列；请先确认版本，可使用play_media播放选定单集。'}
    queued = rows[start:start + 500]
    previous = queue_rows(tools)
    restore = [playlist_item(row) for row in previous]
    if cancelled():raise InterruptedError('已取消。')
    try:
        tools.rpc('Playlist.Clear', {'playlistid': 1})
        for offset in range(0, len(queued), 100):
            if cancelled():raise InterruptedError('已取消。')
            tools.rpc('Playlist.Add', {'playlistid': 1, 'item': [{'episodeid': row['episodeid']} for row in queued[offset:offset + 100]]})
    except Exception:
        # No playback was started yet. Restore only the queue built by this operation.
        tools.rpc('Playlist.Clear', {'playlistid': 1})
        for offset in range(0, len(restore), 100):
            tools.rpc('Playlist.Add', {'playlistid': 1, 'item': restore[offset:offset + 100]})
        raise
    from .playback_tools import start_queue
    start_queue(tools, 0, selected, (selected.get('resume') or {}).get('position', 0) if resume else 0, cancelled, ordered=True)
    first = tools._remember([selected], 'episode')[0]
    tools.playlist_snapshot = None
    result = {'playing': first, 'queued_count': len(queued), 'remaining_not_queued': max(0, len(rows) - start - len(queued))}
    if tools.defer_ui:return dict(result, **tools._queue_ui('ActivateWindow(FullscreenVideo)', 'tvshow_queue'))
    tools.builtin('ActivateWindow(FullscreenVideo)');tools.fullscreen_requested = True
    return result


def set_playlist_mode(tools, shuffle=None, repeat=None, cancelled=lambda: False):
    if shuffle is None and repeat is None:raise ValueError('请提供随机播放或循环方式。')
    player = tools._player()
    if shuffle is not None:tools.rpc('Player.SetShuffle', {'playerid': player, 'shuffle': shuffle})
    if repeat is not None:tools.rpc('Player.SetRepeat', {'playerid': player, 'repeat': repeat})
    tools.acted = True
    return tools.rpc('Player.GetProperties', {'playerid': player, 'properties': ['shuffled', 'repeat']})


def favourite_key(row):
    return (row.get('type', ''), row.get('path', ''), row.get('window', '').casefold(), row.get('windowparameter', ''))


def favourite_id(row):
    return hashlib.sha256(json.dumps(favourite_key(row), ensure_ascii=False).encode()).hexdigest()[:32]


def favourites(tools):
    return tools.rpc('Favourites.GetFavourites', {'properties': ['path', 'window', 'windowparameter']}).get('favourites', [])


def list_favourites(tools, query='', offset=0, limit=20, cancelled=lambda: False):
    rows = [row for row in favourites(tools) if query.strip().casefold() in row.get('title', '').casefold()]
    matches = [{'id': favourite_id(row), 'title': text(row.get('title')), 'type': row.get('type')}
               for row in rows[offset:offset + limit]]
    tools.latest_matches = []
    return {'favourites': matches, 'total': len(rows),
            'next_offset': offset + len(matches) if matches and offset + len(matches) < len(rows) else None}


def open_favourite(tools, id, cancelled=lambda: False):
    if not re.fullmatch('[a-f0-9]{32}', id):raise ValueError('收藏ID无效，请先查询收藏。')
    row = next((row for row in favourites(tools) if favourite_id(row) == id), None)
    if row is None:raise ValueError('收藏已移除或变化，请重新查询。')
    if row['type'] == 'window':
        params = {'window': row['window']}
        if row.get('windowparameter'):params['parameters'] = [row['windowparameter']]
        return tools._interface_operations([{'method': 'GUI.ActivateWindow', 'params': params}], 'favourite_window')
    if row['type'] == 'media':
        tools.rpc('Player.Open', {'item': {'file': row['path']}})
        tools.acted = tools.playback_started = True
        return {'requested': text(row.get('title'))}
    if row['type'] == 'script':
        addonid = row.get('path', '').removeprefix('script://')
        if re.fullmatch('[a-zA-Z0-9_.-]{1,120}', addonid):return tools._open_addon(addonid)
    raise ValueError('该收藏类型暂不能直接打开，请打开Kodi收藏页面使用。')


def add_favourite(tools, kind='current', id=None, title='', cancelled=lambda: False):
    if kind == 'current':
        if id is not None:raise ValueError('收藏当前播放时不需要提供ID。')
        item = tools.rpc('Player.GetItem', {'playerid': tools._player(), 'properties': ['title', 'file']})['item']
        target = {'type': 'media', 'path': item.get('file', '')}
    else:
        if id is None:raise ValueError('收藏媒体需要已查询的ID。')
        item = verified(tools, kind, id)
        if kind == 'tvshow':target = {'type': 'window', 'window': 'videos', 'windowparameter': 'videodb://tvshows/titles/' + str(id) + '/'}
        else:
            item = tools.rpc('VideoLibrary.Get' + ('Movie' if kind == 'movie' else 'Episode') + 'Details',
                             {kind + 'id': id, 'properties': ['title', 'file']})[kind + 'details']
            target = {'type': 'media', 'path': item.get('file', '')}
    if target['type'] == 'media' and not target['path']:raise ValueError('Kodi没有提供可收藏的媒体地址。')
    if any(favourite_key(row) == favourite_key(target) for row in favourites(tools)):
        return {'already_present': True, 'id': favourite_id(target)}
    target['title'] = title.strip() or text(item.get('title') or item.get('label')) or '当前媒体'
    tools.rpc('Favourites.AddFavourite', target)
    tools.acted = True
    return {'added': True, 'id': favourite_id(target), 'title': target['title']}

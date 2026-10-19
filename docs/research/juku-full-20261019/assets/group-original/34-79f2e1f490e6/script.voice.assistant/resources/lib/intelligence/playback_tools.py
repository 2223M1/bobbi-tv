"""Bounded player metadata and track controls, without paths or GUI focus assumptions."""
from .ui_context import text
import threading
import time


def subset(row, keys):
    return {key: row[key] for key in keys if key in row}


def playback_watcher():
    try:import xbmc
    except ImportError:return None  # Non-Kodi protocol checks use a simulated RPC transport.
    class Started(xbmc.Player):
        def __init__(self):
            super().__init__()
            self.ready, self.failed = threading.Event(), threading.Event()
        def onAVStarted(self):self.ready.set()
        def onPlayBackError(self):self.failed.set()
    return Started()


def start_queue(tools, position, first, resume_seconds, cancelled, ordered=False):
    """Kodi ignores options.resume for playlist IDs; seek only the confirmed new item."""
    if cancelled():raise InterruptedError('已取消，未打开播放队列。')
    watcher = playback_watcher() if resume_seconds > 0 else None
    options = {'shuffled': False, 'repeat': 'off'} if ordered else {}
    tools.rpc('Player.Open', {'item': {'playlistid': 1, 'position': position}, 'options': options})
    tools.acted = tools.playback_started = True
    if resume_seconds <= 0:return
    deadline = time.monotonic() + 25
    while True:
        if cancelled():raise InterruptedError('已取消，队列打开请求已经发送。')
        if watcher is not None and watcher.failed.is_set():raise ValueError('Kodi播放失败，未执行断点定位。')
        ready = watcher is None or watcher.ready.is_set()
        if ready:
            try:
                row = tools.rpc('Player.GetItem', {'playerid': 1, 'properties': ['file']})['item']
                expected_kind = first.get('type') or ('episode' if 'episodeid' in first else 'movie')
                expected_id = first.get('id', first.get(expected_kind + 'id'))
                matches = (row.get('type') == expected_kind and row.get('id') == expected_id
                           if type(expected_id) is int and expected_id > 0
                           else bool(first.get('file')) and row.get('file') == first['file'])
                if not matches:
                    if watcher is not None:raise ValueError('当前播放项目已变化，未向其他影片执行断点定位。')
                else:break
            except ValueError:
                if watcher is not None:raise
        if time.monotonic() >= deadline:raise ValueError('队列打开请求已发送，但未确认首集就绪，未执行断点定位。')
        time.sleep(.05)
    milliseconds = round(resume_seconds * 1000)
    if cancelled():raise InterruptedError('已取消，未执行断点定位。')
    tools.rpc('Player.Seek', {'playerid': 1, 'value': {'time': {'hours': milliseconds // 3600000,
        'minutes': milliseconds // 60000 % 60, 'seconds': milliseconds // 1000 % 60, 'milliseconds': milliseconds % 1000}}})


def current_item(tools, playerid, include_cast=False):
    fields = ['title', 'year', 'showtitle', 'season', 'episode', 'plot', 'genre', 'director', 'runtime']
    if include_cast:fields.append('cast')
    row = tools.rpc('Player.GetItem', {'playerid': playerid, 'properties': fields})['item']
    result = subset(row, ('id', 'type', 'year', 'season', 'episode', 'runtime'))
    for key in ('title', 'label', 'showtitle'):
        if row.get(key):result[key] = text(row[key])
    result['plot'] = text(row.get('plot'), 2000)
    for key in ('genre', 'director'):
        result[key] = [text(item) for item in row.get(key, [])[:30] if isinstance(item, str)]
    if include_cast:
        result['cast'] = [{'name': text(item.get('name')), 'role': text(item.get('role'))}
                          for item in row.get('cast', [])[:50] if isinstance(item, dict)]
    if row.get('type') in ('movie', 'episode') and type(row.get('id')) is int and row['id'] > 0:
        tools._remember([dict(row, **{row['type'] + 'id': row['id']})], row['type'])
    return result


def get_playback_details(tools, include_cast=False, cancelled=lambda: False):
    tools.latest_matches = []
    player = tools._player()
    value = tools.rpc('Player.GetProperties', {'playerid': player, 'properties': [
        'speed', 'time', 'totaltime', 'percentage', 'canseek', 'canchangespeed', 'playlistid', 'position',
        'repeat', 'shuffled', 'audiostreams', 'currentaudiostream', 'subtitles', 'currentsubtitle', 'subtitleenabled']})
    for key in ('audiostreams', 'subtitles'):
        value[key] = [dict(subset(row, ('index', 'channels', 'codec', 'isdefault', 'isforced', 'isimpaired')),
            **{k: text(row[k]) for k in ('name', 'language') if k in row}) for row in value.get(key, [])[:128]]
    for key in ('currentaudiostream', 'currentsubtitle'):
        value[key] = subset(value.get(key, {}), ('index', 'language', 'name', 'codec', 'channels'))
    result = {'playerid': player, 'item': current_item(tools, player, include_cast),
              'paused': value.get('speed') == 0, 'playback': value}
    if player == 1:
        result['audio_delay_ms'] = -round(tools.rpc('Player.GetAudioDelay', {})['offset'] * 1000)
        result['view_mode'] = tools.rpc('Player.GetViewMode', {})
    return result


def set_playback_track(tools, track, index=None, enabled=None, cancelled=lambda: False):
    player = tools._player()
    if track == 'audio' and (index is None or enabled is not None):
        raise ValueError('切换音轨需要真实index，enabled只用于字幕。')
    if track == 'subtitle' and index is None and enabled is None:
        raise ValueError('请选择字幕索引或提供字幕开关。')
    if index is not None:
        field = 'audiostreams' if track == 'audio' else 'subtitles'
        rows = tools.rpc('Player.GetProperties', {'playerid': player, 'properties': [field]})[field]
        selected = next((row for row in rows if row.get('index') == index), None)
        if selected is None:raise ValueError('这个轨道索引当前不存在，请重新查询音轨和字幕。')
    else:selected = None
    if track == 'audio':
        tools.rpc('Player.SetAudioStream', {'playerid': player, 'stream': index})
    else:
        value = index if index is not None else 'on' if enabled else 'off'
        tools.rpc('Player.SetSubtitle', {'playerid': player, 'subtitle': value,
                  'enable': True if enabled is None else enabled})
        if index is not None and enabled is False:
            tools.rpc('Player.SetSubtitle', {'playerid': player, 'subtitle': 'off'})
    tools.acted = True
    return {'track': track, 'selected': subset(selected or {}, ('index', 'language', 'name')),
            'enabled': (True if enabled is None else enabled) if track == 'subtitle' else None}


def set_audio_delay(tools, milliseconds, relative=True, cancelled=lambda: False):
    player = tools._player()
    if player != 1:raise ValueError('声音同步调整需要当前播放视频。')
    offset = tools.rpc('Player.GetAudioDelay', {})['offset'] if relative else 0
    # Kodi delays the video for a positive native offset (audio is ahead).
    # Expose the natural speech convention: positive milliseconds delay audio.
    target = round((-offset * 1000 + milliseconds) / 25) * 25 / 1000
    if not -10 <= target <= 10:raise ValueError('调整后的声音偏移超出正负10秒。')
    value = tools.rpc('Player.SetAudioDelay', {'playerid': player, 'offset': float(-target)})
    tools.acted = True
    return {'audio_delay_ms': -round(value['offset'] * 1000)}


def adjust_subtitles(tools, delay_ms=None, move=None, steps=1, cancelled=lambda: False):
    if tools._player() != 1:raise ValueError('字幕调整需要当前播放视频。')
    if delay_ms is None and move is None:raise ValueError('请提供字幕延迟或位置调整。')
    if delay_ms is not None and delay_ms % 100:raise ValueError('字幕延迟以100毫秒为一格。')
    actions = []
    if delay_ms:
        actions += ['subtitledelayplus' if delay_ms > 0 else 'subtitledelayminus'] * (abs(delay_ms) // 100)
    if move:
        actions += [{'up': 'subtitleshiftup', 'down': 'subtitleshiftdown', 'align': 'subtitlealign'}[move]] * steps
    if not actions:return {'unchanged': True}
    operations = [{'method': 'Input.ExecuteAction', 'params': {'action': value}} for value in actions]
    return tools._interface_operations(operations, 'subtitle_adjustment')


def set_video_view(tools, mode=None, zoom_percent=None, cancelled=lambda: False):
    if tools._player() != 1:raise ValueError('画面调整需要当前播放视频。')
    if (mode is None) == (zoom_percent is None):raise ValueError('请选择画面模式或缩放百分比中的一项。')
    value = mode if mode is not None else {'zoom': zoom_percent / 100}
    tools.rpc('Player.SetViewMode', {'viewmode': value})
    tools.acted = True
    return {'view_mode': tools.rpc('Player.GetViewMode', {})}

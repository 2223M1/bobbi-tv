"""Deferred UI operations and a named Kodi sleep alarm, independent of key mappings."""
from ..data_paths import data_path
from datetime import datetime
import time
from ..storage import read_json, write_json

ALARM = 'voice_assistant_sleep'
ALARM_CONDITION = 'System.HasAlarm(' + ALARM + ')'
UI_ACTIONS = {'back', 'select', 'up', 'down', 'left', 'right', 'pageup', 'pagedown', 'info',
              'contextmenu', 'firstpage', 'lastpage', 'osd', 'playerprocessinfo'}


def perform_operations(action, rpc, cancelled=lambda: False):
    operations = action.get('operations', [])
    if not isinstance(operations, list) or not 0 < len(operations) <= 100:
        raise ValueError('界面操作列表无效。')
    expected = action.get('window_id')
    if expected is not None:
        actual = rpc('GUI.GetProperties', {'properties': ['currentwindow']})['currentwindow'].get('id')
        if actual != expected:raise ValueError('原来的Kodi页面已变化，未执行界面操作，请重新发起。')
    for operation in operations:
        if cancelled():raise InterruptedError('已取消。')
        method, params = operation['method'], operation['params']
        if method not in ('Input.ExecuteAction', 'Input.SendText', 'GUI.ActivateWindow'):
            raise ValueError('不支持的界面操作。')
        if method == 'Input.SendText':
            hidden = rpc('XBMC.GetInfoBooleans', {'booleans': ['System.HasHiddenInput']})
            if hidden.get('System.HasHiddenInput'):
                raise ValueError('当前是密码或PIN输入框，未写入语音文字。')
        rpc(method, params)


def interface_action(tools, action, count=1, cancelled=lambda: False):
    original = (tools.ui_context or {}).get('window', {}).get('id')
    if tools.defer_ui and original is None:
        raise ValueError('没有打开助手前的页面信息，请关闭助手后重新发起。')
    operations = [{'method': 'Input.ExecuteAction', 'params': {'action': action}} for _ in range(count)]
    return tools._interface_operations(operations, 'interface_' + action, original)


def send_search_text(tools, text, submit=False, cancelled=lambda: False):
    original = (tools.ui_context or {}).get('window', {}).get('id')
    if original != 10103:raise ValueError('请先打开Kodi搜索输入键盘，再调用语音输入文字。')
    return tools._interface_operations([{'method': 'Input.SendText', 'params': {'text': text, 'done': submit}}],
                                        'search_input', original)


def sleep_timer(tools, action, minutes=None, cancelled=lambda: False):
    if tools.profile is None:raise ValueError('当前入口没有提供定时器的数据目录。')
    path = data_path(tools.profile, 'sleep-timer.json')
    def active():
        return bool(tools.rpc('XBMC.GetInfoBooleans', {'booleans': [ALARM_CONDITION]}).get(ALARM_CONDITION))
    if action == 'status':
        value = read_json(path, {}) or {}
        running = active()
        expiry = value.get('expires_at')
        remaining = max(0, round(expiry - time.time())) if type(expiry) in (int, float) else None
        return {'active': running, 'remaining_seconds': remaining if running else 0,
                'expires_at': value.get('expires_at_iso') if running else None}
    if action == 'set':
        if minutes is None:raise ValueError('设置定时器需要指定分钟数。')
        tools.builtin('AlarmClock(' + ALARM + ',PlayerControl(Stop),' + str(minutes) + ',silent)')
        expiry = time.time() + minutes * 60
    else:
        if minutes is not None:raise ValueError('取消定时不需要填写分钟数。')
        tools.builtin('CancelAlarm(' + ALARM + ',silent)')
        expiry = None
    deadline = time.monotonic() + 1.5
    while active() != (action == 'set'):
        if cancelled():raise InterruptedError('已取消。')
        if time.monotonic() >= deadline:raise ValueError('Kodi尚未确认定时器状态，请查询定时状态。')
        time.sleep(.02)
    tools.acted = True
    value = {'expires_at': expiry, 'expires_at_iso': datetime.fromtimestamp(expiry).astimezone().isoformat(timespec='seconds') if expiry else None}
    write_json(path, value)
    return {'active': action == 'set', 'expires_at': value['expires_at_iso'], 'minutes': minutes,
            'action': 'stop_playback' if expiry else 'cancelled'}

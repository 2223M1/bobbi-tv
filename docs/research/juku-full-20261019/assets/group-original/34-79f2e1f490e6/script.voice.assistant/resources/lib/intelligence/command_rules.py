"""Whole-utterance rules for common local controls; no substring intent guesses."""
import re
import unicodedata

# These phrases explicitly request a restart. A plain "播放/看" never does.
RESTART_ACTION = (r'(?:(?:重新)?(?:从头|从开头|从最开始|从一开始)(?:开始)?(?:重新|再)?(?:播放|观看|看)(?:一遍|一次)?'
                  r'|重新(?:开始)?(?:播放|观看|看)(?:一遍|一次)?|(?:重播|重放|重看)(?:一遍|一次)?'
                  r'|再(?:播放|观看|看)(?:一遍|一次))')
RESTART_SUFFIX = r'(?:' + RESTART_ACTION + r'|从头(?:开始)?|从开头(?:开始)?|从最开始|重新开始)'


def number(value):
    value = unicodedata.normalize('NFKC', value)
    if value.isascii() and value.isdecimal():
        return int(value) if len(value) <= 4 else None
    digits = dict(zip('零〇一二两三四五六七八九', (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
    if value and all(char in digits for char in value):
        return int(''.join(str(digits[char]) for char in value)) if len(value) <= 4 else None
    if not value or re.search(r'[百千][一二两三四五六七八九]$', value):
        return None  # Omitted units such as "两百五" are ambiguous.
    result, digit, previous, was_digit = 0, 0, 10000, False
    for char in value:
        if char in digits:
            if was_digit and (digit != 0 or digits[char] == 0):
                return None
            digit = digits[char]
            was_digit = True
        elif char in '十百千':
            unit = {'十': 10, '百': 100, '千': 1000}[char]
            if unit >= previous or was_digit and digit == 0 or not was_digit and unit != 10:
                return None
            result += (digit or 1) * unit
            digit, previous, was_digit = 0, unit, False
        else:
            return None
    return result + digit


NUM = r'[0-9０-９零〇一二两三四五六七八九十百千]{1,8}'
ADDON_ALIASES = {
    '筛选': ('plugin.video.filteredmovies', 'Filtered Movies'),
    '筛选页': ('plugin.video.filteredmovies', 'Filtered Movies'),
    '遥控器': ('script.controller.switcher', 'Controller Switcher'),
}
SYSTEM_COMMANDS = {
    'shutdown': ('关机', '关闭系统', '系统关机', '关闭盒子', '关闭电视盒子', '关闭机顶盒',
                 '盒子关机', '电视盒子关机', '机顶盒关机', '关掉盒子', '关掉电视盒子', '关掉机顶盒',
                 '把盒子关掉', '把电视盒子关掉', '把机顶盒关掉', '把系统关掉', '关掉系统', '关闭coreelec'),
    'reboot': ('重启', '重启系统', '系统重启', '重新启动', '重新启动系统',
               '重启盒子', '重启电视盒子', '重启机顶盒', '重新启动盒子', '重新启动电视盒子', '重新启动机顶盒',
               '盒子重启', '电视盒子重启', '机顶盒重启', '把系统重启', '把盒子重启',
               '重启一下系统', '重启一下盒子', '重启一下电视盒子', '重启一下机顶盒', '重启coreelec', '重新启动coreelec'),
    'reboot_android': ('重启到安卓', '重启至安卓', '重启进入安卓', '重启到安卓系统', '重新启动到安卓',
                       '切换到安卓', '切换到安卓系统', '切回安卓', '切回安卓系统', '进入安卓', '启动安卓',
                       '返回安卓', '返回安卓系统', '回到安卓', '回到安卓系统',
                       '重启到android', '重启到android系统', '重启进入android', '重新启动到android',
                       '切换到android', '切换到android系统', '进入android', '返回android'),
    'suspend': ('挂起', '挂起系统', '系统挂起', '睡眠', '睡眠系统', '系统睡眠', '待机', '系统待机',
                '进入睡眠', '进入睡眠模式', '进入挂起', '进入挂起模式', '进入待机', '进入待机模式',
                '让系统睡眠', '让系统挂起', '让系统待机', '让盒子睡眠', '让盒子挂起', '让盒子待机',
                '盒子睡眠', '盒子挂起', '盒子待机', '挂起盒子', '挂起电视盒子', '挂起机顶盒',
                '把盒子挂起', '让电视盒子睡眠', '让电视盒子待机', '让机顶盒睡眠', '让机顶盒待机',
                '让系统进入睡眠', '让系统进入睡眠模式', '让盒子进入睡眠', '让盒子进入睡眠模式'),
}


def _tool(name, arguments, message):
    return {'tool': name, 'arguments': arguments, 'message': message}


def common_request(text):
    if not isinstance(text, str) or len(text) > 300:
        return None
    value = text.strip().rstrip('。!！')
    value = re.sub(r'^(?:请|麻烦)(?:你)?', '', value)
    value = re.sub(r'^(?:帮我|给我)', '', value).strip()
    short = re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).casefold()
    if re.fullmatch(RESTART_SUFFIX, short):
        return _tool('control_playback', {'action': 'restart'}, '已请求从头播放当前影片。')
    power = re.sub(r'(?:一下)?(?:吧)?$', '', short)
    for action, phrases in SYSTEM_COMMANDS.items():
        if power in phrases:
            operation = {'shutdown': '系统关机', 'reboot': '重启系统', 'reboot_android': '重启到安卓',
                         'suspend': '系统挂起（睡眠）'}[action]
            return _tool('system_action', {'action': action}, '已安排' + operation + '，将在本轮结束后执行。')
    for kind, noun in (('movie', '电影'), ('channel', '电视'), ('tvshow', '电视剧')):
        if short in ('继续看' + noun, '接着看' + noun, '继续播放' + noun):
            return {'continue_kind': kind}
    playback = {
        'pause': ('暂停', '暂停播放', '暂停一下'),
        'play': ('继续', '继续播放', '恢复播放'),
        'stop': ('停止', '停止播放', '结束播放'),
        'next': ('下一项', '下一首'), 'previous': ('上一项', '上一首')}
    messages = {'pause': '已暂停播放。', 'play': '已发送继续播放指令。', 'stop': '已停止播放。',
                'next': '已请求播放下一项。', 'previous': '已请求播放上一项。'}
    for action, phrases in playback.items():
        if short in phrases:
            return _tool('control_playback', {'action': action}, messages[action])
    for muted, phrases in ((True, ('静音', '开启静音', '关闭声音', '关声音')),
                           (False, ('取消静音', '关闭静音', '恢复声音', '打开声音'))):
        if short in phrases:
            return _tool('set_mute', {'muted': muted}, '已静音。' if muted else '已取消静音。')
    for enabled, phrases in ((True, ('打开字幕', '开启字幕', '显示字幕')),
                             (False, ('关闭字幕', '关字幕', '隐藏字幕'))):
        if short in phrases:
            return _tool('set_playback_track', {'track': 'subtitle', 'enabled': enabled},
                         '已打开字幕。' if enabled else '已关闭字幕。')
    destinations = {
        'home': ('返回主页', '回到主页', '打开主页'),
        'movies': ('打开电影库', '打开电影列表'),
        'tvshows': ('打开电视剧库', '打开电视剧列表'),
        'live_tv': ('看电视', '我要看电视', '打开电视', '打开直播', '打开直播电视'),
        'favourites': ('打开收藏', '打开收藏夹', '查看收藏'),
        'settings': ('打开设置', '打开Kodi设置', '打开kodi设置'),
        'fullscreen': ('全屏播放', '返回播放画面', '回到播放界面')}
    for destination, phrases in destinations.items():
        if short in phrases:
            return _tool('navigate', {'destination': destination}, '正在打开对应页面。')
    volume = re.fullmatch(r'(?:把)?(?:音量|声音)(?:调到|调成|设为|设置为|设置到|到)?'
                          r'(?:百分之)?(?P<number>' + NUM + r')(?:%|百分比)?', short)
    if volume:
        percent = number(volume['number'])
        if percent is not None and 0 <= percent <= 100:
            return _tool('set_volume', {'volume': percent}, '音量已设为{}%。'.format(percent))
        return None
    louder = ('声音大一点', '声音大点', '音量大一点', '音量大点', '调大音量', '提高音量')
    quieter = ('声音小一点', '声音小点', '音量小一点', '音量小点', '调小音量', '降低音量')
    if short in louder + quieter:
        return {'volume_delta': 5 if short in louder else -5}
    relative = re.fullmatch(r'(?:把)?音量(?P<action>增加|提高|调高|减小|降低|调低|减少)'
                            r'(?:百分之)?(?P<number>' + NUM + r')(?:%|个百分点)?', short)
    if relative:
        amount = number(relative['number'])
        if amount is not None and 1 <= amount <= 100:
            return {'volume_delta': amount if relative['action'] in ('增加', '提高', '调高') else -amount}
        return None
    seek = re.fullmatch(r'(?P<direction>快进|后退|快退)(?P<duration>.+)', short)
    if seek:
        duration = seek['duration']
        if duration == '半分钟':
            seconds = 30
        else:
            match = re.fullmatch(r'(?:(?P<minutes>' + NUM + r')(?:分钟|分))?'
                                 r'(?:(?P<seconds>' + NUM + r')(?:秒钟|秒)|(?P<half>半))?', duration)
            if not match or not any(match.groups()):
                return None
            minutes, seconds = number(match['minutes'] or '0'), number(match['seconds'] or '0')
            if minutes is None or seconds is None or match['half'] and not match['minutes']:
                return None
            seconds += minutes * 60 + (30 if match['half'] else 0)
        if not 1 <= seconds <= 3600:
            return None
        seconds *= 1 if seek['direction'] == '快进' else -1
        return _tool('seek_playback', {'seconds': seconds}, '已请求{}{}秒。'.format(
            '快进' if seconds > 0 else '后退', abs(seconds)))
    channel = re.fullmatch(r'(?:播放|我要看|我想看|看|切到|切换到)(?P<channel>(?:CCTV|cctv|央视|中央)[^，,。；;!?！？\r\n]{1,50})', value)
    if channel:
        return {'channel': channel['channel'].strip()}
    addon = re.fullmatch(r'(?:打开|启动|运行)(?:插件\s*)?'
                         r'(?:《(?P<quoted>[^《》\r\n]{1,120})》|(?P<addon>[^《》，,。；;!?！？\r\n]{1,120}))', value)
    if addon:
        name = (addon['quoted'] or addon['addon']).strip()
        if not addon['quoted']:
            alias = re.sub(r'\s+', '', unicodedata.normalize('NFKC', name)).casefold()
            if alias.endswith('插件'):
                alias = alias[:-2]
            target = ADDON_ALIASES.get(alias)
            if target:
                return _tool('open_addon', {'addonid': target[0]}, '正在打开插件：' + target[1] + '。')
        return {'addon': name, 'literal_name': bool(addon['quoted'])}
    return None

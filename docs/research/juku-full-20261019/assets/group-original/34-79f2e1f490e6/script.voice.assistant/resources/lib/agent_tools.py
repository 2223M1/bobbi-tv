"""Kodi and CoreELEC capabilities exposed to the model as named tools."""
import json
from pathlib import Path
import shutil
import subprocess
import time
import re
import math
from .intelligence.capability_specs import TOOLS as MEDIA_TOOLS, MODULES as MEDIA_MODULES, LABELS as MEDIA_LABELS


def definition(name, description, properties=None, required=()):
    return {'type': 'function', 'function': {'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties or {},
                       'required': list(required), 'additionalProperties': False}}}


def string(description, **kwargs):
    return dict(type='string', description=description, **kwargs)


def integer(description, minimum, maximum):
    return dict(type='integer', description=description, minimum=minimum, maximum=maximum)


TOOLS = [
    definition('get_kodi_status', '查询 Kodi 当前播放、音量、静音和版本。'),
    definition('capture_screen', '按需获取当前画面并直接提供图片，可用于描述视频场景、读取画面文字、查看 Kodi 界面或分析显示问题。auto 默认正在播放视频时提取纯视频帧（不含助手弹窗），否则截完整屏幕；video 只取视频帧，screen 截包含 Kodi 界面和字幕的屏幕。所有截图都排除助手自身弹窗；屏幕截图会暂时隐藏助手内容后立即恢复，不结束会话或改变播放。Code mode 下返回“元数据文本 + 换行 + data:image URL”字符串，必须提取 URL 并调用 image(URL) 才能看图，不能直接 text/JSON.stringify 整个返回值或猜 image/content 字段；一次成功后先读图，不为处理返回格式重复截图。',
        {'source': string('截图来源，默认auto；查看菜单、外挂字幕或界面时用screen，视频内容用video', enum=['auto', 'video', 'screen'])}),
    definition('search_channels', '查询 Kodi PVR 直播电视频道，不查影视库或插件。支持 CCTV1、CCTV一、央视一套、中央一台及频道名称/序号；推荐频道 recommended 可直接播放，同台多线路按 Kodi 频道顺序推荐。不同频道匹配时让用户选择。',
        {'query': string('频道名或频道序号；留空列出频道', maxLength=120),
         'offset': integer('分页起始位置，默认0；后续页使用 next_offset', 0, 1000000),
         'limit': integer('返回数量，默认12', 1, 30)}),
    definition('get_epg', '查询 Kodi PVR 直播电视当前节目单 EPG，返回各频道的节目名称、类型、简介和起止时间。询问哪些台正在放电影/体育等节目时，留空 query 查询全部频道，再根据节目内容判断；不按类型关键词过滤，不查媒体库。缺节目单的频道明确返回空值。',
        {'query': string('频道名或序号筛选；留空查询全部频道，不要填电影等节目类型', maxLength=120),
         'offset': integer('分页起始位置，默认0；后续页使用 next_offset', 0, 1000000),
         'limit': integer('返回频道数量，默认200', 1, 200),
         'include_next': {'type': 'boolean', 'description': '是否同时查询下一档节目，默认false'}}),
    definition('play_channel', '播放 search_channels 或 get_epg 返回的真实直播频道 ID。不能猜 ID；播放前会复查隐藏/锁定状态，助手让出前台后进入全屏。',
        {'channelid': integer('查询返回的真实频道 ID', 1, 2147483647)}, ['channelid']),
    definition('search_media', '在 Kodi 影视库按标题查找电影和电视剧。返回真实 ID；播放前先搜索。',
        {'query': string('影视名称，不包含“播放”等指令词', minLength=1, maxLength=120),
         'kind': string('影视类型', enum=['all', 'movie', 'tvshow']),
         'limit': integer('每类最多返回几条', 1, 10)}, ['query']),
    definition('get_episodes', '按集号查询电视剧剧集及观看记录。继续看、续播整部剧请用 get_tvshow_progress，不要只检查前几集。',
        {'tvshowid': integer('真实电视剧 ID', 1, 2147483647),
         'season': integer('季号；不填则所有季', 0, 1000),
         'offset': integer('分页起始位置，从 0 开始；后续页使用返回的 next_offset', 0, 1000000),
         'limit': integer('返回剧集数量', 1, 30)}, ['tvshowid']),
    definition('get_tvshow_progress', '查询已搜索电视剧全部剧集的观看进度，返回最近观看剧集和建议续播的真实 ID、resume 参数。有明确建议时直接调用 play_media，不必再让用户选集；记录不明确才询问。',
        {'tvshowid': integer('真实电视剧 ID', 1, 2147483647)}, ['tvshowid']),
    definition('play_media', '播放此前搜索或剧集查询返回的电影或剧集。默认从保存的断点续播；只有用户明确要求从头看、重新播放或重播时才设 resume=false，不清除观看记录。',
        {'kind': string('项目类型', enum=['movie', 'episode']),
         'id': integer('查询返回的真实 ID', 1, 2147483647),
         'resume': {'type': 'boolean', 'description': '默认true；仅明确要求从头播放时为false'}}, ['kind', 'id']),
    definition('control_playback', '暂停、继续、停止或切换上一项/下一项。仅用户明确要求从头播放当前影片时使用restart。',
        {'action': string('播放操作', enum=['pause', 'play', 'stop', 'next', 'previous', 'restart'])}, ['action']),
    definition('seek_playback', '在当前影片中快进或后退指定秒数。',
        {'seconds': integer('正数快进、负数后退', -3600, 3600)}, ['seconds']),
    definition('set_volume', '设置 Kodi 音量百分比。',
        {'volume': integer('音量，0 到 100', 0, 100)}, ['volume']),
    definition('set_mute', '设置 Kodi 静音状态。',
        {'muted': {'type': 'boolean', 'description': 'true 静音，false 取消静音'}}, ['muted']),
    definition('navigate', '打开 Kodi 的指定界面。live_tv 是直播电视频道列表，tvshows 是媒体库电视剧。语音窗口中会安排到本轮结束、助手让出前台后执行。',
        {'destination': string('界面', enum=['home', 'movies', 'tvshows', 'live_tv', 'settings', 'favourites', 'fullscreen'])},
        ['destination']),
    definition('get_system_status', '查询 CoreELEC 系统版本、运行时间、内存、存储、CPU 温度和负载。'),
    definition('upload_logs', '仅在用户明确要求上传/提交日志时使用。调用 CE 设置同款 pastekodi，上传最新 Kodi 日志、系统日志及相关配置到 paste.coreelec.org，返回短网址。请在回复中原样显示 url；排查问题时不要自行上传，不要另用 shell 重复上传。'),
    definition('search_addons', '按名称或 ID 查询本机已安装的可打开插件，包含启用状态。用户说插件名称时先查询，不能猜 ID；无结果时缩短关键词重查，query 留空可列出全部。多个匹配请用户选择，不要擅自启用已禁用插件。',
        {'query': string('插件名称关键词或 ID；空字符串列出全部', maxLength=120),
         'offset': integer('分页起始位置，默认 0；后续页使用 next_offset', 0, 1000000),
         'limit': integer('最多返回数量，默认 30', 1, 30)}, ['query']),
    definition('open_addon', '按 search_addons 查到的真实 ID 打开已安装的 Kodi 插件，不要猜 ID。语音窗口中会安排到本轮结束、助手让出前台后执行，deferred 表示尚未打开。',
        {'addonid': string('插件 ID', minLength=1, maxLength=120)}, ['addonid']),
    definition('get_settings', '按设置 ID 或名称查找 Kodi 设置；不返回密码、令牌。',
        {'query': string('设置 ID 或名称', minLength=1, maxLength=120)}, ['query']),
    definition('set_setting', '修改已经查到的 Kodi 设置，值用 JSON 标量表示。',
        {'setting': string('实际设置 ID', minLength=1, maxLength=120),
         'json_value': string('JSON 字符串、数字或布尔值', minLength=1, maxLength=512)}, ['setting', 'json_value']),
    definition('get_assistant_settings', '查询语音助手的录音、识别、超时和会话设置，不返回凭据或安全策略。',
        {'query': string('设置名称或 ID，可留空查询全部', maxLength=120)}),
    definition('set_assistant_setting', '修改语音助手的普通设置；凭据、权限和服务登录方式必须由用户在配置页调整。',
        {'setting': string('查询到的实际设置 ID', minLength=1, maxLength=120),
         'json_value': string('新值的 JSON 标量', minLength=1, maxLength=512)}, ['setting', 'json_value']),
    definition('system_action', '请求重启 Kodi、重启 CoreELEC、重启到安卓、关机或系统挂起（睡眠/待机）。单独说重启是重启整个系统；reboot_android 使用 CE 原生内部存储启动入口，suspend 是挂起到内存。按当前审批策略处理；本轮回复后才执行。',
        {'action': string('维护操作', enum=['restart_kodi', 'reboot', 'reboot_android', 'shutdown', 'suspend'])}, ['action']),
]
TOOLS += MEDIA_TOOLS
LABELS = {'get_kodi_status': '正在查询播放状态…', 'search_media': '正在查找影视…',
          'capture_screen': '正在获取画面…',
          'search_channels': '正在查询直播频道…', 'get_epg': '正在查询电视节目单…', 'play_channel': '正在播放直播频道…',
          'get_episodes': '正在查询剧集…', 'get_tvshow_progress': '正在查询观看进度…', 'play_media': '正在打开影片…',
          'control_playback': '正在控制播放…', 'seek_playback': '正在调整播放位置…',
          'set_volume': '正在设置音量…', 'set_mute': '正在设置静音…',
          'navigate': '正在打开界面…', 'open_addon': '正在打开插件…', 'get_system_status': '正在查询 CoreELEC 状态…',
          'upload_logs': '正在上传最新 Kodi 日志和配置…', 'search_addons': '正在查询已安装的插件…',
          'system_action': '等待确认系统操作…'}
LABELS.update(MEDIA_LABELS)
SYSTEM_ACTIONS = {
    'restart_kodi': ('重启 Kodi', '当前播放会中断，随后返回 Kodi。', ['restart', 'kodi']),
    'reboot': ('重启 CoreELEC', '电视盒子将重新启动，当前播放会中断。', ['reboot']),
    'reboot_android': ('重启到安卓', '电视盒子将重启并从内部存储启动安卓，当前播放会中断。', ['reboot']),
    'shutdown': ('关闭 CoreELEC', '电视盒子将关机，需要重新开机后才能继续使用。', ['poweroff']),
    'suspend': ('挂起 CoreELEC', '电视盒子将进入睡眠（待机）状态，当前播放会中断。', ['suspend']),
}


def validate_arguments(specification, arguments):
    parameters = specification['function']['parameters']
    if not isinstance(arguments, dict) or set(arguments) - set(parameters['properties']):
        raise ValueError('工具参数含有不支持的字段。')
    if any(name not in arguments for name in parameters['required']):
        raise ValueError('工具缺少必要参数。')
    for name, value in arguments.items():
        rule = parameters['properties'][name]
        expected = {'string': str, 'integer': int, 'boolean': bool, 'number': float}[rule['type']]
        if (expected is float and (type(value) not in (int, float) or type(value) is float and not math.isfinite(value))
                or expected is not float and type(value) is not expected):
            raise ValueError('工具参数类型错误：' + name)
        if 'enum' in rule and value not in rule['enum']:
            raise ValueError('不支持的操作：' + name)
        if expected is str and not rule.get('minLength', 0) <= len(value.strip()) <= rule.get('maxLength', 1000):
            raise ValueError('文字参数为空或过长。')
        if expected in (int, float) and not rule['minimum'] <= value <= rule['maximum']:
            raise ValueError('数值参数超出范围：' + name)


class KodiTools:
    def __init__(self, rpc, builtin=lambda value: None, confirm=lambda title, message: False,
                 system_enabled=True, media=(), permissions=None, assistant_get=None, assistant_set=None,
                 defer_ui=False, screen_capture=None, ui_context=None, profile=None):
        self.rpc, self.builtin, self.confirm = rpc, builtin, confirm
        self.system_enabled = system_enabled
        self.permissions = permissions
        self.assistant_get, self.assistant_set = assistant_get, assistant_set
        self.media = {(row['kind'], row['id']): row for row in media
                      if isinstance(row, dict) and row.get('kind') in ('movie', 'tvshow', 'episode', 'channel')
                      and type(row.get('id')) is int}
        self.ui_context = json.loads(json.dumps(ui_context)) if ui_context is not None else None
        selected = (self.ui_context or {}).get('selected') or {}
        selection = selected.get('media') or {}
        if selection.get('kind') in ('movie', 'tvshow', 'episode') and type(selection.get('id')) is int and selection['id'] > 0:
            # This ID/title pair was verified against the real Kodi library.
            self.media[(selection['kind'], selection['id'])] = dict(selection)
        self.acted, self.deferred, self.maintenance_declined = False, None, False
        self.playback_started = False
        self.fullscreen_requested = False
        self.latest_matches = []
        self.defer_ui, self.ui_action = defer_ui, None
        self.log_upload_result = None
        self.screen_capture = screen_capture
        self.profile = Path(profile) if profile is not None else None
        self.playlist_snapshot = None

    def definitions(self):
        return [tool for tool in TOOLS if (self.system_enabled or
                tool['function']['name'] not in ('get_system_status', 'system_action', 'upload_logs')) and
                (self.permissions is None or self.permissions.allows(tool['function']['name'])) and
                (tool['function']['name'] != 'get_assistant_settings' or self.assistant_get is not None) and
                (tool['function']['name'] != 'set_assistant_setting' or self.assistant_set is not None)]

    def label(self, name):
        return LABELS.get(name, '正在处理指令…')

    def execute(self, name, arguments, cancelled=lambda: False):
        if cancelled():
            raise InterruptedError('已取消。')
        specification = next((tool for tool in self.definitions() if tool['function']['name'] == name), None)
        if specification is None:
            return {'ok': False, 'error': '未提供该工具。'}
        try:
            validate_arguments(specification, arguments)
            if name in ('set_setting', 'set_assistant_setting') and self.permissions and self.permissions.needs_confirmation(name):
                if not self.confirm('修改 Kodi 设置', arguments['setting'] + '\n新值：' + arguments['json_value']):
                    return {'ok': False, 'error': '用户未批准，未修改设置。'}
            if name in MEDIA_MODULES:
                from importlib import import_module
                handler = import_module('.intelligence.' + MEDIA_MODULES[name], __package__)
                result = getattr(handler, name)(self, cancelled=cancelled, **arguments)
            elif name == 'get_tvshow_progress':
                result = self._get_tvshow_progress(cancelled=cancelled, **arguments)
            elif name == 'search_channels':
                result = self._search_channels(cancelled=cancelled, **arguments)
            elif name == 'get_epg':
                result = self._get_epg(cancelled=cancelled, **arguments)
            elif name == 'capture_screen':
                result = self._capture_screen(cancelled=cancelled, **arguments)
            elif name == 'upload_logs':
                result = self._upload_logs(cancelled)
            else:
                result = getattr(self, '_' + name)(**arguments)
            return dict(ok=True, **result)
        except ValueError as error:
            return {'ok': False, 'error': str(error)}

    def _get_kodi_status(self):
        application = self.rpc('Application.GetProperties', {'properties': ['volume', 'muted', 'name', 'version']})
        players = self.rpc('Player.GetActivePlayers', {})
        playing = []
        for player in players:
            identifier = player['playerid']
            properties = self.rpc('Player.GetProperties', {'playerid': identifier,
                'properties': ['speed', 'time', 'totaltime']})
            item = self.rpc('Player.GetItem', {'playerid': identifier, 'properties': ['title']})['item']
            playing.append(dict(properties, type=player['type'], title=item.get('title') or item.get('label', '')))
        return {'application': application, 'players': playing}

    def _capture_screen(self, source='auto', cancelled=lambda: False):
        import base64
        from .intelligence.screen import capture
        self.latest_matches = []
        result = (self.screen_capture or capture)(source, cancelled)
        data = result.pop('data')
        return dict(result, image_attached=True, _image='data:image/png;base64,' + base64.b64encode(data).decode('ascii'))

    def _remember(self, rows, kind):
        result = []
        for row in rows:
            item = {'kind': kind, 'id': row[kind + 'id'], 'title': row.get('title') or row.get('label', '')}
            item.update({key: row[key] for key in ('year', 'season', 'episode', 'showtitle', 'thumbnail', 'art',
                                                  'playcount', 'lastplayed', 'resume', 'watchedepisodes',
                                                  'channelnumber', 'subchannelnumber', 'locked',
                                                  'genre', 'rating', 'runtime', 'userrating') if key in row})
            self.media[(kind, item['id'])] = item
            result.append(item)
        return result

    def _search_channels(self, query='', offset=0, limit=12, cancelled=lambda: False):
        from .intelligence.live_tv import search
        result = search(self.rpc, query, offset, limit, cancelled)
        preferred = result.pop('preferred_id')
        result['channels'] = self._remember(result['channels'], 'channel')
        result['recommended'] = next((row for row in result['channels'] if row['id'] == preferred), None)
        self.latest_matches = result['channels']
        return result

    def _play_channel(self, channelid):
        channel = self.media.get(('channel', channelid))
        if channel is None:
            raise ValueError('这个频道 ID 不在查询结果中，请先查询直播频道。')
        actual = self.rpc('PVR.GetChannelDetails', {'channelid': channelid,
            'properties': ['channel', 'channeltype', 'hidden', 'locked']}).get('channeldetails', {})
        if actual.get('channelid') != channelid or actual.get('hidden') or actual.get('channeltype') != 'tv':
            raise ValueError('该直播频道已移除或不可见，请重新查询。')
        if actual.get('locked'):
            raise ValueError('该直播频道已锁定，请先在 Kodi 中解锁。')
        self.rpc('Player.Open', {'item': {'channelid': channelid}})
        self.acted = self.playback_started = True
        if self.defer_ui:
            return dict(self._queue_ui('ActivateWindow(FullscreenVideo)', 'live_tv'), requested=channel)
        self.builtin('ActivateWindow(FullscreenVideo)')
        self.fullscreen_requested = True
        return {'requested': channel}

    def _get_epg(self, query='', offset=0, limit=200, include_next=False, cancelled=lambda: False):
        from .intelligence.live_tv import epg
        # A program query must not turn every channel into an automatic recommendation.
        self.latest_matches = []
        result = epg(self.rpc, query, offset, limit, include_next, cancelled)
        rows = result['channels']
        result['channels'] = [dict(item, **{key: row[key] for key in ('current_program', 'next_program') if key in row})
            for item, row in zip(self._remember(rows, 'channel'), rows)]
        return result

    def _search_media(self, query, kind='all', limit=6):
        results = []
        for current, method, key in (('movie', 'VideoLibrary.GetMovies', 'movies'),
                                     ('tvshow', 'VideoLibrary.GetTVShows', 'tvshows')):
            if kind not in ('all', current):
                continue
            properties = ['title', 'year', 'thumbnail', 'art', 'playcount', 'lastplayed']
            properties += ['resume'] if current == 'movie' else ['watchedepisodes']
            value = self.rpc(method, {'properties': properties,
                'filter': {'field': 'title', 'operator': 'contains', 'value': query.strip()},
                'limits': {'start': 0, 'end': limit}, 'sort': {'method': 'title', 'order': 'ascending'}})
            results.extend(self._remember(value.get(key, []), current))
        self.latest_matches = results
        return {'matches': results, 'note': '多个结果请让用户选择；只能播放返回的 ID。'}

    def _get_episodes(self, tvshowid, season=None, limit=15, offset=0):
        if ('tvshow', tvshowid) not in self.media:
            raise ValueError('请先搜索这部电视剧。')
        parameters = {'tvshowid': tvshowid, 'properties': ['title', 'season', 'episode', 'showtitle', 'thumbnail', 'art',
                                                         'playcount', 'lastplayed', 'resume'],
                      'limits': {'start': offset, 'end': offset + limit}, 'sort': {'method': 'episode', 'order': 'ascending'}}
        if season is not None:
            parameters['season'] = season
        value = self.rpc('VideoLibrary.GetEpisodes', parameters)
        self.latest_matches = self._remember(value.get('episodes', []), 'episode')
        end = offset + len(self.latest_matches)
        total = value.get('limits', {}).get('total', end)
        return {'matches': self.latest_matches, 'total': total,
                'next_offset': end if self.latest_matches and end < total else None}

    def _get_tvshow_progress(self, tvshowid, cancelled=lambda: False):
        if ('tvshow', tvshowid) not in self.media:
            raise ValueError('请先搜索这部电视剧。')
        episodes, seen = [], set()
        total = None
        while len(episodes) < 10000:
            if cancelled():
                raise InterruptedError('已取消。')
            start = len(episodes)
            value = self.rpc('VideoLibrary.GetEpisodes', {'tvshowid': tvshowid,
                'properties': ['title', 'season', 'episode', 'showtitle', 'playcount', 'lastplayed', 'resume'],
                'sort': {'method': 'episode', 'order': 'ascending'},
                'limits': {'start': start, 'end': start + 200}})
            batch = value.get('episodes', [])
            limits = value.get('limits', {})
            reported_total = limits.get('total')
            if total is not None and reported_total != total:
                raise ValueError('查询期间剧集数量发生变化，请重新查询观看进度。')
            total = reported_total
            ids = [row['episodeid'] for row in batch]
            if (limits.get('start', start) != start or len(set(ids)) != len(ids) or seen.intersection(ids)
                    or (total is not None and (start + len(batch) > total or not batch and start < total))):
                raise ValueError('观看记录分页不完整或重复，请重新查询，暂不能确定续播位置。')
            seen.update(ids)
            episodes.extend(batch)
            if (total is not None and len(episodes) == total) or (total is None and len(batch) < 200):
                break
        else:
            raise ValueError('剧集过多，未完整读取观看记录，暂不能确定续播位置。')
        from .intelligence.watch_progress import continuation
        result = continuation(episodes)
        for key in ('last_played', 'recommended'):
            if result.get(key):
                result[key] = self._remember([result[key]], 'episode')[0]
        if result.get('candidates'):
            # Keep the response bounded, while exposing genuine selectable IDs.
            candidates = result['candidates']
            result['candidate_count'] = len(candidates)
            result['candidates'] = self._remember(candidates[:30], 'episode')
        self.latest_matches = [result['recommended']] if result.get('recommended') else result.get('candidates', [])
        return dict(result, total_episodes=len(episodes))

    def _play_media(self, kind, id, resume=True):
        item = self.media.get((kind, id))
        if item is None:
            raise ValueError('这个 ID 不在查询结果中，请先搜索影视。')
        self.rpc('Player.Open', {'item': {kind + 'id': id}, 'options': {'resume': resume}})
        self.acted = True
        self.playback_started = True
        return {'playing': item}

    def _search_addons(self, query, offset=0, limit=30):
        rows = self.rpc('Addons.GetAddons', {'properties': ['name', 'enabled']}).get('addons', [])
        normalize = lambda text: re.sub(r'\s+', '', text).casefold()
        query = normalize(query)
        matches = []
        for row in rows:
            if row.get('type') not in ('xbmc.python.script', 'xbmc.python.pluginsource'):
                continue
            if query and not any(query in normalize(row.get(key, '')) for key in ('name', 'addonid')):
                continue
            matches.append({key: row.get(key) for key in ('addonid', 'name', 'type', 'enabled')})
        matches.sort(key=lambda row: (normalize(row['name'] or ''), row['addonid'] or ''))
        end = offset + limit
        return {'addons': matches[offset:end], 'total': len(matches),
                'next_offset': end if end < len(matches) else None}

    def _open_addon(self, addonid):
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,120}', addonid):
            raise ValueError('插件 ID 无效。')
        addon = self.rpc('Addons.GetAddonDetails', {'addonid': addonid, 'properties': ['enabled']}).get('addon', {})
        if not addon.get('enabled'):
            raise ValueError('插件不存在或尚未启用。')
        command = 'RunAddon(' + addonid + ')'
        if self.defer_ui:
            return self._queue_ui(command, addonid)
        self.builtin(command)
        self.acted = True
        return {'requested': addonid}

    def _queue_ui(self, command, target):
        # Only the last destination should take foreground focus.
        self.ui_action = command
        self.acted = True
        return {'deferred': 'ui_navigation', 'target': target, 'status': 'pending',
                'note': '本轮回复保存、助手让出前台后执行；仅最后一个界面跳转生效，目前尚未确认打开。'}

    def _interface_operations(self, operations, target, window_id=None):
        """Opaque paths stay local; execute structured RPC only after our dialog closes."""
        action = {'operations': operations, 'target': target, 'window_id': window_id}
        if self.defer_ui:
            return self._queue_ui(action, target)
        from .intelligence.interface_tools import perform_operations
        perform_operations(action, self.rpc)
        self.acted = True
        return {'requested': target, 'executed': True}

    @staticmethod
    def _private_setting(identifier):
        return any(word in identifier.lower() for word in ('password', 'passwd', 'token', 'secret', 'apikey', 'api_key'))

    def _get_settings(self, query):
        rows = self.rpc('Settings.GetSettings', {'level': 'expert'}).get('settings', [])
        return {'settings': [{k: row[k] for k in ('id', 'label', 'value', 'type') if k in row}
            for row in rows if not self._private_setting(row.get('id', '')) and
            query.lower() in (row.get('id', '') + ' ' + row.get('label', '')).lower()][:30]}

    def _set_setting(self, setting, json_value):
        if self._private_setting(setting):
            raise ValueError('不通过语音修改凭据，请使用配置网页。')
        try:
            value = json.loads(json_value)
        except ValueError:
            raise ValueError('设置值必须是有效的 JSON 标量。') from None
        if type(value) not in (str, bool, int, float):
            raise ValueError('设置值必须是字符串、数字或布尔值。')
        result = self.rpc('Settings.SetSettingValue', {'setting': setting, 'value': value})
        if result is not True:
            raise ValueError('Kodi 拒绝了这个设置值。')
        self.acted = True
        return {'setting': setting, 'updated': True}

    def _get_assistant_settings(self, query=''):
        if self.assistant_get is None:
            raise ValueError('当前入口不支持助手设置查询。')
        return self.assistant_get(query)

    def _set_assistant_setting(self, setting, json_value):
        if self.assistant_set is None:
            raise ValueError('当前入口不支持助手设置修改。')
        try:
            value = json.loads(json_value)
        except ValueError:
            raise ValueError('新值必须是 JSON 标量。') from None
        if type(value) not in (str, int, bool, float):
            raise ValueError('新值必须是 JSON 标量。')
        return self.assistant_set(setting, value)

    def _player(self):
        players = self.rpc('Player.GetActivePlayers', {})
        if not players:
            raise ValueError('当前没有正在播放的媒体。')
        players.sort(key=lambda player: player['type'] != 'video')
        return players[0]['playerid']

    def _control_playback(self, action):
        playerid = self._player()
        if action in ('pause', 'play'):
            self.rpc('Player.PlayPause', {'playerid': playerid, 'play': action == 'play'})
        elif action == 'stop':
            self.rpc('Player.Stop', {'playerid': playerid})
        elif action == 'restart':
            if not self.rpc('Player.GetProperties', {'playerid': playerid, 'properties': ['canseek']}).get('canseek'):
                raise ValueError('当前播放不支持从头定位。')
            self.rpc('Player.Seek', {'playerid': playerid, 'value': {'percentage': 0.0}})
            self.rpc('Player.PlayPause', {'playerid': playerid, 'play': True})
        else:
            self.rpc('Player.GoTo', {'playerid': playerid, 'to': action})
        self.acted = True
        self.playback_started = action in ('play', 'next', 'previous', 'restart')
        return {'action': action}

    def _seek_playback(self, seconds):
        playerid = self._player()
        value = self.rpc('Player.GetProperties', {'playerid': playerid, 'properties': ['time', 'totaltime']})
        def as_seconds(clock):
            return clock['hours'] * 3600 + clock['minutes'] * 60 + clock['seconds']
        duration = as_seconds(value['totaltime'])
        position = max(0, as_seconds(value['time']) + seconds)
        if duration:
            position = min(position, duration)
        clock = {'hours': position // 3600, 'minutes': position // 60 % 60,
                 'seconds': position % 60, 'milliseconds': 0}
        self.rpc('Player.Seek', {'playerid': playerid, 'value': {'time': clock}})
        self.acted = True
        return {'position_seconds': position}

    def _set_volume(self, volume):
        actual = self.rpc('Application.SetVolume', {'volume': volume})
        self.acted = True
        return {'volume': actual}

    def _set_mute(self, muted):
        actual = self.rpc('Application.SetMute', {'mute': muted})
        self.acted = True
        return {'muted': actual}

    def _navigate(self, destination):
        actions = {'home': 'ActivateWindow(Home)', 'movies': 'ActivateWindow(Videos,movietitles,return)',
                   'tvshows': 'ActivateWindow(Videos,tvshowtitles,return)', 'settings': 'ActivateWindow(Settings)',
                   'live_tv': 'ActivateWindow(TVChannels)',
                   'favourites': 'ActivateWindow(Favourites)', 'fullscreen': 'ActivateWindow(FullscreenVideo)'}
        if destination == 'live_tv' and not self.rpc('PVR.GetProperties', {'properties': ['available']}).get('available'):
            raise ValueError('Kodi 直播电视尚未就绪，请先配置 PVR 客户端和频道。')
        if self.defer_ui:
            if destination == 'fullscreen' and not any(p.get('type') == 'video' for p in self.rpc('Player.GetActivePlayers', {})):
                raise ValueError('当前没有正在播放的视频。')
            return self._queue_ui(actions[destination], destination)
        self.builtin(actions[destination])
        if destination == 'fullscreen':
            self.fullscreen_requested = True
        self.acted = True
        return {'destination': destination}

    def _get_system_status(self):
        def read(path, fallback=''):
            try:
                return Path(path).read_text().strip()
            except OSError:
                return fallback
        release = dict(line.split('=', 1) for line in read('/etc/os-release').splitlines() if '=' in line)
        memory = {line.split(':')[0]: int(line.split()[1]) for line in read('/proc/meminfo').splitlines()
                  if ':' in line and len(line.split()) >= 2}
        disk = shutil.disk_usage('/storage')
        temperatures = []
        for path in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
            try:
                temperatures.append(round(float(path.read_text()) / 1000, 1))
            except (OSError, ValueError):
                pass
        return {'system': release.get('PRETTY_NAME', '').strip('"'),
                'uptime_seconds': round(float(read('/proc/uptime', '0').split()[0])),
                'memory_total_mib': round(memory.get('MemTotal', 0) / 1024),
                'memory_available_mib': round(memory.get('MemAvailable', 0) / 1024),
                'storage_total_gib': round(disk.total / 1024 ** 3, 2),
                'storage_free_gib': round(disk.free / 1024 ** 3, 2),
                'temperature_celsius': temperatures, 'load': read('/proc/loadavg').split()[:3]}

    def _upload_logs(self, cancelled):
        if self.log_upload_result is None:
            if not self.confirm('上传日志', '将最新 Kodi 日志、系统日志及相关配置上传到 paste.coreelec.org，并返回可分享的短网址。'):
                raise ValueError('用户取消了上传日志，未执行。')
            from .log_upload import upload
            self.log_upload_result = upload(cancelled=cancelled)
        self.acted = True
        return dict(self.log_upload_result)

    def _system_action(self, action):
        if self.maintenance_declined:
            raise ValueError('用户已取消本次维护操作。')
        if self.deferred:
            raise ValueError('本次已有一个维护操作等待执行。')
        if not shutil.which('systemd-run') or not shutil.which('systemctl'):
            raise ValueError('当前系统不支持延迟维护操作。')
        if action == 'suspend' and not self.rpc('System.GetProperties', {'properties': ['cansuspend']}).get('cansuspend'):
            raise ValueError('当前系统不支持挂起（睡眠）。')
        if action == 'reboot_android' and not shutil.which('rebootfromnand'):
            raise ValueError('当前系统没有重启到安卓的原生启动脚本。')
        title, message, unused = SYSTEM_ACTIONS[action]
        if not self.confirm(title, message):
            self.maintenance_declined = True
            raise ValueError('用户取消了该操作，未执行。')
        self.deferred = action
        return {'deferred': action, 'note': '策略已允许；本轮回复后调度执行，系统操作尚未执行。'}

    def commit_deferred(self, cancelled=lambda: False):
        if not self.deferred:
            return None
        if cancelled():
            raise InterruptedError('已取消维护操作。')
        action = self.deferred
        unit = 'voice-assistant-' + str(time.monotonic_ns())
        command = [shutil.which('systemd-run'), '--quiet', '--collect', '--on-active=5s', '--unit=' + unit]
        if action == 'reboot_android':
            helper = shutil.which('rebootfromnand')
            if not helper:
                raise ValueError('当前系统没有重启到安卓的原生启动脚本。')
            # The CE helper sets the internal-boot flag but need not reboot.
            # ExecStartPre runs only when the delayed unit fires. Its failure
            # prevents the reboot; cancellation before commit changes no flags.
            command.append('--property=ExecStartPre=' + helper)
        command += [shutil.which('systemctl')] + SYSTEM_ACTIONS[action][2]
        subprocess.run(command, check=True, capture_output=True, timeout=5)
        self.deferred = None
        self.acted = True
        return {'action': action, 'scheduled': True, 'delay_seconds': 5}

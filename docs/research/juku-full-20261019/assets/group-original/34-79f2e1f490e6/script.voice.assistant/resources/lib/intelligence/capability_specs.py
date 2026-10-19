"""Lightweight schemas for optional Kodi media capabilities; handlers load on demand."""


def text(label, **extra):
    return dict(type='string', description=label, maxLength=120, **extra)


def integer(label, low, high):
    return dict(type='integer', description=label, minimum=low, maximum=high)


def flag(label):
    return dict(type='boolean', description=label)


def spec(name, description, properties=None, required=()):
    return {'type': 'function', 'function': {'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties or {},
                       'required': list(required), 'additionalProperties': False}}}


MEDIA = ['movie', 'episode', 'tvshow']
TOOLS = [
    spec('get_playback_details', '查询当前影片的真实片名、季集、简介、进度、暂停状态、音轨和字幕索引；演职员表仅 include_cast=true 时返回。切轨前先查询，不猜语言或索引。',
         {'include_cast': flag('是否查询演职员表，默认false')}),
    spec('set_playback_track', '选择当前影片的真实音轨/字幕索引；必须先 get_playback_details。字幕可仅设置 enabled 开关，选择字幕时自动显示。',
         {'track': text('轨道类型', enum=['audio', 'subtitle']), 'index': integer('查询得到的真实索引', 0, 1024),
          'enabled': flag('仅用于字幕开关')}, ['track']),
    spec('set_audio_delay', '调整当前影片的音频同步，毫秒为单位；正数让声音延后、负数让声音提前。relative=true 在现值基础上调整，否则设置绝对偏移，最终值按25ms精度返回。',
         {'milliseconds': integer('偏移毫秒', -10000, 10000), 'relative': flag('相对调整，默认true')}, ['milliseconds']),
    spec('adjust_subtitles', '把字幕提前/延后或上下移动；delay_ms 正数延后、负数提前，100ms一格。需要让出助手窗口后执行，不修改按键绑定。',
         {'delay_ms': integer('字幕相对延迟，100ms的倍数', -5000, 5000),
          'move': text('字幕位置调整', enum=['up', 'down', 'align']), 'steps': integer('移动次数，默认1', 1, 20)}),
    spec('set_video_view', '设置当前影片的画面比例或缩放，不修改分辨率/HDR。normal恢复正常比例，original为原始尺寸。',
         {'mode': text('画面模式', enum=['normal', 'original', 'zoom', 'stretch16x9', 'stretch4x3', 'widezoom']),
          'zoom_percent': integer('缩放百分比，100为原大小', 50, 200)}),
    spec('find_media', '按组合条件查询真实媒体库：名称、类型、年份、评分、时长、导演、演员和观看状态；无需先列出整个片库。返回ID可直接播放/查询/入队。电视剧不支持时长条件。',
         {'kind': text('媒体类型，默认movie', enum=['movie', 'tvshow']), 'query': text('标题关键词，可空'),
          'genre': text('类型，如科幻、喜剧'), 'actor': text('演员姓名'), 'director': text('导演姓名'),
          'year_from': integer('起始年份', 1800, 2200), 'year_to': integer('结束年份', 1800, 2200),
          'min_rating': {'type': 'number', 'description': '最低评分，0至10', 'minimum': 0, 'maximum': 10},
          'max_minutes': integer('最长时长，分钟，仅电影', 1, 1440),
          'watched': text('观看状态，默认all', enum=['all', 'unwatched', 'watched', 'in_progress']),
          'sort': text('排序，默认rating', enum=['rating', 'year', 'title', 'dateadded', 'lastplayed', 'random']),
          'offset': integer('分页起点，默认0', 0, 1000000), 'limit': integer('最多条数，默认12', 1, 30)}),
    spec('get_media_details', '读取已搜索或当前选中影片/剧集/电视剧的简介、导演及演职员表，按真实媒体库ID查询；不通过人脸识别身份。',
         {'kind': text('类型', enum=MEDIA), 'id': integer('查询得到的ID', 1, 2147483647),
          'include_cast': flag('是否查询演员表，默认true')}, ['kind', 'id']),
    spec('update_watch_state', '修改已查询电影/剧集的观看状态、续播位置或个人评分。只修改明确提供的字段；reset_resume=true从头看，不删除媒体。',
         {'kind': text('类型', enum=['movie', 'episode']), 'id': integer('查询得到的ID', 1, 2147483647),
          'watched': flag('标为已看/未看'), 'reset_resume': flag('清零续播位置'),
          'rating': integer('个人评分，0清除评分，1至10打分', 0, 10)}, ['kind', 'id']),
    spec('get_playlist', '查询当前视频待播队列及位置，返回真实队列下标；后续移除/移动前先查询。',
         {'offset': integer('分页起点，默认0', 0, 1000000), 'limit': integer('最多条数，默认30', 1, 100)}),
    spec('edit_playlist', '编辑视频待播队列。add追加、play_next放到当前项后面、remove删除指定下标、move移动、clear清空。只接受已查询媒体ID，不自动开始播放。',
         {'action': text('操作', enum=['add', 'play_next', 'remove', 'move', 'clear']),
          'kind': text('媒体类型', enum=['movie', 'episode']), 'id': integer('查询得到的媒体ID', 1, 2147483647),
          'position': integer('查询得到的队列下标', 0, 10000), 'to': integer('目标队列下标', 0, 10000)}, ['action']),
    spec('play_playlist', '播放已经get_playlist查询的视频队列，从指定下标开始；队列有变化时需重新查询。',
         {'position': integer('查询得到的队列下标，默认0', 0, 10000), 'resume': flag('默认true，从首项断点继续；仅明确要求从头播放时为false')}),
    spec('play_tvshow_queue', '从指定季集开始按顺序连续播放已查询电视剧。未指定起点时按真实观看进度续播；有歧义返回候选。先构建队列再播放，替换现有视频待播队列。',
         {'tvshowid': integer('查询得到的电视剧ID', 1, 2147483647), 'season': integer('起始季号', 0, 1000),
          'episode': integer('起始集号，需同时提供season', 0, 10000), 'resume': flag('默认true，从断点继续；明确从头播放时false，未指定季集则从整剧开头播放')}, ['tvshowid']),
    spec('set_playlist_mode', '设置当前视频队列的随机播放和循环方式，只修改给出的选项。',
         {'shuffle': flag('是否随机'), 'repeat': text('循环方式', enum=['off', 'one', 'all'])}),
    spec('list_favourites', '按名称查询Kodi收藏，返回稳定的收藏ID，不返回真实文件路径；多个同名项请用户选择。',
         {'query': text('名称关键词，可空'), 'offset': integer('分页起点，默认0', 0, 1000000),
          'limit': integer('最多条数，默认20', 1, 50)}),
    spec('open_favourite', '打开 list_favourites 返回的真实收藏ID；窗口/插件在助手让出前台后打开。',
         {'id': text('查询返回的收藏ID', minLength=16)}, ['id']),
    spec('add_favourite', '收藏当前播放项目或已查询的电影/剧集/电视剧。已收藏时保持原样，不反向取消收藏。',
         {'kind': text('类型，默认current', enum=['current'] + MEDIA),
          'id': integer('非current时必须为已查询ID', 1, 2147483647), 'title': text('可选收藏名称')}),
    spec('sleep_timer', '设置/查询/取消本助手的停止播放定时器。只停止媒体，不关机；新定时覆盖本助手旧定时，不影响其他Kodi闹钟。',
         {'action': text('操作', enum=['set', 'status', 'cancel']),
          'minutes': integer('几分钟后停止播放，仅set时需要', 1, 1440)}, ['action']),
    spec('send_search_text', '向打开助手前的Kodi搜索键盘输入文字，默认不提交。请先打开目标搜索输入框再调用语音。助手让出前台、确认原键盘仍存在后才写入。',
         {'text': dict(type='string', description='输入的文字', minLength=1, maxLength=1000),
          'submit': flag('是否同时提交搜索，默认false')}, ['text']),
    spec('interface_action', '对打开助手前的Kodi页面执行返回、确认、翻页、信息、菜单或列表选择动作；让出助手窗口后执行，不改按键绑定。',
         {'action': text('动作', enum=['back', 'select', 'up', 'down', 'left', 'right', 'pageup', 'pagedown',
             'info', 'contextmenu', 'firstpage', 'lastpage', 'osd', 'playerprocessinfo']),
          'count': integer('次数，默认1', 1, 20)}, ['action']),
    spec('library_maintenance', '扫描新影视或刷新已查询的指定电影/剧集/电视剧资料。扫描和刷新是后台任务，返回accepted不等于已完成；不清理/删除媒体库，不忽略本地NFO。',
         {'action': text('操作', enum=['scan', 'refresh']), 'kind': text('刷新类型', enum=MEDIA),
          'id': integer('刷新对象的真实ID', 1, 2147483647)}, ['action']),
]

MODULES = {name: 'playback_tools' for name in ('get_playback_details', 'set_playback_track', 'set_audio_delay',
    'adjust_subtitles', 'set_video_view')}
MODULES.update({name: 'library_tools' for name in ('find_media', 'get_media_details', 'update_watch_state', 'library_maintenance')})
MODULES.update({name: 'collection_tools' for name in ('get_playlist', 'edit_playlist', 'play_playlist', 'play_tvshow_queue',
    'set_playlist_mode', 'list_favourites', 'open_favourite', 'add_favourite')})
MODULES.update({name: 'interface_tools' for name in ('sleep_timer', 'send_search_text', 'interface_action')})
LABELS = dict(zip(MODULES, ('正在查询影片和轨道…', '正在切换音轨或字幕…', '正在调整声音同步…',
    '正在调整字幕…', '正在调整画面比例…', '正在筛选媒体库…', '正在查询影片资料…', '正在更新观看记录…',
    '正在安排媒体库维护…', '正在查询待播队列…', '正在编辑待播队列…', '正在播放待播队列…', '正在安排连续播放…',
    '正在设置播放模式…', '正在查询收藏…', '正在打开收藏…', '正在添加收藏…', '正在处理睡眠定时…',
    '正在填写搜索文字…', '正在操作Kodi界面…')))

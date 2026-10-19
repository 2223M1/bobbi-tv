"""Continue the matching player or Kodi's latest real viewing history."""


def _resumable(row):
    value = row.get('resume') or {}
    position, total = value.get('position', 0), value.get('total', 0)
    return position > 0 and (total <= 0 or position < total)


def _choices(commands, text, rows, message, resume=True):
    choices = []
    for row in rows[:12]:
        # Only verified remembered metadata, never a selection's untrusted flag,
        # decides whether the subsequent click resumes rather than restarts.
        row['_command_resume'] = resume
        label = row['title']
        if row.get('showtitle'):
            label = '{} 第{}季第{}集：{}'.format(row['showtitle'], row.get('season', 0), row.get('episode', 0), label)
        elif row.get('year'):
            label += '（{}）'.format(row['year'])
        choices.append(dict(row, label=label, value=('继续播放：' if resume else '从头播放：') + label))
    commands.tools.latest_matches = rows[:12]
    return commands._outcome(text, message, choices)


def tvshow(commands, text, show, cancelled, progress, resume=True):
    if not resume:
        from .collection_tools import episodes
        from .watch_progress import beginning
        progress('正在查询电视剧开头的剧集…')
        result = beginning(episodes(commands.tools, show['id'], cancelled))
        if result.get('recommended'):
            chosen = commands.tools._remember([result['recommended']], 'episode')[0]
            return commands._play(text, chosen, False, cancelled, progress)
        rows = commands.tools._remember(result.get('candidates') or [], 'episode')
        return _choices(commands, text, rows, result['note'], resume=False)
    progress('正在查询电视剧观看进度…')
    result = commands.tools.execute('get_tvshow_progress', {'tvshowid': show['id']}, cancelled)
    if not result.get('ok'):
        return commands._outcome(text, '观看记录查询失败：' + result.get('error', '请稍后重试。'))
    chosen = result.get('recommended')
    if chosen and result.get('play'):
        outcome = commands._play(text, chosen, True, cancelled, progress)
        if result.get('status') == 'restart_episode' and outcome['tools'][-1]['ok']:
            # A dated viewing record need not have a saved playback offset.
            return commands._outcome(text, '最近观看的剧集未保存断点，将从本集开头播放。', trace=outcome['tools'])
        return outcome
    if result.get('status') == 'no_history':
        episodes = commands.tools.execute('get_episodes', {'tvshowid': show['id'], 'limit': 12}, cancelled)
        if not episodes.get('ok'):
            return commands._outcome(text, '剧集查询失败：' + episodes.get('error', '请稍后重试。'))
        return _choices(commands, text, episodes.get('matches') or [],
                        '《' + show['title'] + '》没有观看记录，请选择从哪一集开始。')
    return _choices(commands, text, result.get('candidates') or [],
                    '《' + show['title'] + '》：' + result.get('note', '没有可用的续播记录。'))


def resume(commands, text, kind, cancelled, progress):
    tools = commands.tools
    tools.latest_matches = []
    try:
        if cancelled():
            raise InterruptedError('已取消。')
        players = tools.rpc('Player.GetActivePlayers', {})
        for player in players:
            if cancelled():
                raise InterruptedError('已取消。')
            if player.get('type') != 'video':
                continue
            item = tools.rpc('Player.GetItem', {'playerid': player['playerid'],
                                               'properties': ['title', 'channeltype']}).get('item') or {}
            expected = 'episode' if kind == 'tvshow' else kind
            if item.get('type') == expected and (kind != 'channel' or item.get('channeltype') == 'tv'):
                return commands._common(text, {'tool': 'control_playback', 'arguments': {'action': 'play'},
                                              'message': '已发送继续播放指令。'}, cancelled, progress)
        progress('正在查询最近观看记录…')
        if kind == 'channel':
            if not tools.rpc('PVR.GetProperties', {'properties': ['available']}).get('available'):
                return commands._outcome(text, 'Kodi 直播电视尚未就绪，请先配置 PVR 客户端和频道。')
            # Kodi sorts with the full last-watched timestamp, even though the
            # serialized channel lastplayed field contains only a date.
            result = tools.rpc('PVR.GetChannels', {'channelgroupid': 'alltv',
                'properties': ['channel', 'channeltype', 'hidden', 'locked', 'lastplayed'],
                'sort': {'method': 'lastplayed', 'order': 'descending'}, 'limits': {'start': 0, 'end': 1}})
            rows = [row for row in result.get('channels', []) if row.get('lastplayed', '') > '1970-01-01'
                    and not row.get('hidden') and row.get('channeltype') == 'tv']
            if not rows:
                return commands._outcome(text, '没有找到最近观看的直播频道，请先指定频道。')
            row = dict(rows[0], title=rows[0].get('channel') or rows[0].get('label', ''))
            chosen = tools._remember([row], 'channel')[0]
            return commands._play(text, chosen, False, cancelled, progress)
        name, key = ('Movies', 'movies') if kind == 'movie' else ('TVShows', 'tvshows')
        fields = (['title', 'year', 'lastplayed', 'playcount', 'resume'] if kind == 'movie' else
                  ['title', 'year', 'lastplayed', 'watchedepisodes'])
        result = tools.rpc('VideoLibrary.Get' + name, {'properties': fields,
            'sort': {'method': 'lastplayed', 'order': 'descending'}, 'limits': {'start': 0, 'end': 13}})
        if cancelled():
            raise InterruptedError('已取消。')
        rows = [row for row in result.get(key, []) if row.get('lastplayed')]
        if not rows:
            return commands._outcome(text, '没有找到最近观看的' + ('电影' if kind == 'movie' else '电视剧') + '记录，请先指定片名。')
        latest = rows[0]['lastplayed']
        rows = tools._remember([row for row in rows if row['lastplayed'] == latest], kind)
        if len(rows) > 1:
            return _choices(commands, text, rows, '有多个相同时间的观看记录，请选择要继续看的一项。')
        chosen = rows[0]
        if kind == 'tvshow':
            return tvshow(commands, text, chosen, cancelled, progress)
        if not _resumable(chosen):
            total = (chosen.get('resume') or {}).get('total', 0)
            if chosen.get('playcount', 0) or total > 0 and chosen['resume'].get('position', 0) >= total:
                return _choices(commands, text, rows, '最近观看的《' + chosen['title'] + '》已看完；如需从头重播，请选择。')
            outcome = commands._play(text, chosen, True, cancelled, progress)
            if outcome['tools'][-1]['ok']:
                return commands._outcome(text, '最近观看的《' + chosen['title'] + '》未保存断点，将从头播放。', trace=outcome['tools'])
            return outcome
        return commands._play(text, chosen, True, cancelled, progress)
    except (ValueError, OSError, RuntimeError) as error:
        # Recognized continuation failures stay local, so a failed playback write
        # cannot be retried by the model with a guessed title or channel.
        if isinstance(error, InterruptedError):
            raise
        return commands._outcome(text, '未能继续播放：' + str(error))

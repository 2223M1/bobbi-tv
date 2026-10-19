"""Optional local commands before an agent; unmatched requests have no side effects."""
import json
import re
import unicodedata


def normalize(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).casefold()


def media_request(text):
    """Accept a whole, explicit play utterance, never a keyword within a task."""
    if not isinstance(text, str) or len(text) > 500:
        return None
    from .command_rules import RESTART_ACTION, RESTART_SUFFIX
    value = text.strip()
    prefix = r'(?:请|麻烦)?(?:帮我|给我)?(?:我想要|我想|我要|想)?'
    match = re.fullmatch(
        prefix + r'(?P<verb>' + RESTART_ACTION + r'|继续播放|接着播放|继续看|接着看|播放|观看|看)'
        r'(?:一下)?\s*(?P<name>.+?)\s*[。!！]?', value)
    if match:
        restart = bool(re.fullmatch(RESTART_ACTION, match['verb']))
        name = match['name'].strip()
        tail = re.fullmatch(r'(?P<name>.+?)\s*[,，]?\s*' + RESTART_SUFFIX, name)
        if tail:
            name, restart = tail['name'].strip(), True
    else:
        # "把《片名》从头播放" / "《片名》再看一遍".
        tail = re.fullmatch(prefix + r'(?:(?:把|将)(?P<name>.+?)|(?P<quoted>《[^《》\r\n]+》))\s*[,，]?\s*'
                            + RESTART_SUFFIX + r'\s*[。!！]?', value)
        if not tail:
            return None
        name, restart = (tail['name'] or tail['quoted']).strip(), True
    # A negative/compound tail must not become a near-matching title after
    # stripping the restart phrase. Exact literal titles may still end in 别.
    unclear_restart = restart and tail and re.search(
        r'(?:不要|不用|不必|不想|不能|不需要|别|然后|之后|之前|并且|并|再|接着)$', name)
    # Quoting makes a title containing punctuation explicit. Extra instructions
    # outside the closing book-title marks must still go to the agent.
    quoted = re.fullmatch(r'(?:(?P<kind>电影|电视剧|直播频道|电视频道|频道|电视)\s*)?《(?P<title>[^《》\r\n]{1,200})》'
                          r'(?:\s*[（(](?P<year>\d{4})[）)])?', name)
    if quoted:
        title, year = quoted['title'], quoted['year']
        kind = quoted['kind']
        literal_title = title
    else:
        if any(mark in name for mark in '《》，,。；;？?！!\r\n'):
            return None
        unquoted = re.fullmatch(r'(?P<title>[^()（）]{1,200}?)(?:\s*[（(](?P<year>\d{4})[）)])?', name)
        if not unquoted:
            return None
        title, year = unquoted['title'].strip(), unquoted['year']
        literal_title = title
        if title in ('电影', '影片', '电视剧', '电视', '直播', '这部', '这部电影', '这个'):
            return None
        if title.startswith(('一部', '几部', '一些', '随便', '随机')):
            return None
        typed = re.fullmatch(r'(?P<kind>电视剧|直播频道|电视频道|频道|电影)\s*(?P<title>.+)', title)
        kind = typed['kind'] if typed else None
        if typed:
            title = typed['title'].strip()
            if title.startswith(('一部', '几部', '一些', '随便', '随机')):
                return None
    if not title.strip() or year and not 1800 <= int(year) <= 2200:
        return None
    return {'title': title.strip(), 'literal_title': literal_title, 'year': int(year) if year else None,
            'kind': {'电影': 'movie', '电视剧': 'tvshow', '频道': 'channel', '直播频道': 'channel',
                     '电视频道': 'channel', '电视': 'channel'}.get(kind, 'all'),
            'resume': not restart,
            'allow_fuzzy': not unclear_restart and (bool(quoted) or not re.search(
                r'(?:然后|之后|之前|并且|并|再|接着)(?:请|帮我|给我|把)?'
                r'(?:打开|关闭|播放|暂停|停止|关机|重启|睡眠|挂起|静音|音量|字幕)', title))}


def movie_request(text):
    request = media_request(text)
    return {key: request[key] for key in ('title', 'year', 'resume')} if request else None


class Commands:
    def __init__(self, tools):
        self.tools = tools

    def process(self, text, selection=None, cancelled=lambda: False, progress=lambda value: None):
        if cancelled():
            raise InterruptedError('已取消。')
        if selection is not None:
            return self._selected(text, selection, cancelled, progress)
        from .command_rules import common_request
        common = common_request(text)
        if common is not None:
            return self._common(text, common, cancelled, progress)
        request = media_request(text)
        if request is None:
            return None
        if request['kind'] in ('tvshow', 'channel'):
            from .command_media import lookup
            return lookup(self, text, request, cancelled, progress)
        progress('正在查找电影…')
        literal_title = request['literal_title']
        query = {'field': 'title', 'operator': 'is', 'value': literal_title}
        if request['year'] is not None:
            query = {'and': [query, {'field': 'year', 'operator': 'is', 'value': str(request['year'])}]}
        try:
            value = self.tools.rpc('VideoLibrary.GetMovies', {
                'properties': ['title', 'year', 'thumbnail', 'art', 'playcount', 'lastplayed', 'resume'],
                'filter': query, 'limits': {'start': 0, 'end': 12},
                'sort': {'method': 'title', 'order': 'ascending'}})
        except (ValueError, OSError, RuntimeError):
            # Only the read failed; falling back cannot repeat a playback write.
            return None
        if cancelled():
            raise InterruptedError('已取消。')
        rows = value.get('movies') or []
        rows = [row for row in rows if normalize(row.get('title', '')) == normalize(literal_title)
                and (request['year'] is None or row.get('year') == request['year'])]
        if not rows:
            from .command_media import lookup
            return lookup(self, text, request, cancelled, progress)
        total = value.get('limits', {}).get('total', len(rows))
        matches = self.tools._remember(rows, 'movie')
        self.tools.latest_matches = matches
        if len(matches) == 1 and total == 1:
            return self._play(text, matches[0], request['resume'], cancelled, progress)
        for row in matches:
            row['_command_resume'] = request['resume']
        choices = [dict(row, label=row['title'] + ('（{}）'.format(row['year']) if row.get('year') else ''),
                        value='播放《' + row['title'] + '》') for row in matches]
        return self._outcome(text, '找到多个同名影片或版本，请选择要播放的一项。', choices)

    def _common(self, text, request, cancelled, progress):
        if 'continue_kind' in request:
            from .command_resume import resume
            return resume(self, text, request['continue_kind'], cancelled, progress)
        if 'addon' in request:
            from .ui_context import plain
            names = {normalize(request['addon'])}
            query = request['addon']
            if not request.get('literal_name') and query.endswith('插件') and len(query) > 2:
                query = query[:-2].strip()
                names.add(normalize(query))
            result = self.tools.execute('search_addons', {'query': query, 'limit': 30}, cancelled)
            if not result.get('ok'):
                return self._outcome(text, '插件查询失败：' + result.get('error', '请稍后重试。'))
            def aliases(row):
                name = plain(row.get('name', ''))
                # Edition labels are display qualifiers, e.g. "名称 · CE".
                # Only a whole primary name may omit them; do not fuzzy-launch.
                primary = re.split(r'\s+[·|]\s+', name, maxsplit=1)[0]
                primary = re.sub(r'\s*[（(][^()（）]*[）)]$', '', primary)
                return {normalize(name), normalize(primary), normalize(row.get('addonid', ''))}
            matches = [row for row in result.get('addons', []) if names.intersection(aliases(row))]
            if not matches:
                return None
            if len(matches) != 1 or result.get('next_offset') is not None:
                choices = [{'label': plain(row['name']) + '（' + row['addonid'] + '）',
                            'value': '打开插件 ' + row['addonid'], 'kind': 'none', 'id': 0} for row in matches]
                return self._outcome(text, '找到多个同名插件，请选择。', choices)
            request = {'tool': 'open_addon', 'arguments': {'addonid': matches[0]['addonid']},
                       'message': '正在打开插件：' + plain(matches[0]['name']) + '。'}
        elif 'channel' in request:
            result = self.tools.execute('search_channels', {'query': request['channel']}, cancelled)
            if not result.get('ok'):
                return self._outcome(text, '频道查询失败：' + result.get('error', '请稍后重试。'))
            chosen = result.get('recommended')
            if chosen:
                return self._play(text, chosen, False, cancelled, progress)
            matches = result.get('channels') or []
            if not matches:
                from .command_media import lookup
                return lookup(self, text, {'title': request['channel'], 'kind': 'channel',
                                           'year': None, 'resume': False,
                                           'allow_fuzzy': (media_request('播放' + request['channel']) or {}).get('allow_fuzzy', False)},
                              cancelled, progress)
            choices = [dict(row, label=row['title'], value='播放' + row['title']) for row in matches]
            return self._outcome(text, '请确认要播放的频道。', choices)
        elif 'volume_delta' in request:
            if cancelled():
                raise InterruptedError('已取消。')
            current = self.tools.rpc('Application.GetProperties', {'properties': ['volume']})['volume']
            target = max(0, min(100, round(current + request['volume_delta'])))
            request = {'tool': 'set_volume', 'arguments': {'volume': target},
                       'message': '音量已设为{}%。'.format(target)}
        progress(self.tools.label(request['tool']))
        result = self.tools.execute(request['tool'], request['arguments'], cancelled)
        trace = [{'name': request['tool'], 'arguments': request['arguments'], 'ok': result.get('ok', True)}]
        message = request['message'] if result.get('ok', True) else '未能执行：' + result.get('error', '请稍后重试。')
        return self._outcome(text, message, trace=trace)

    def _selected(self, text, selection, cancelled, progress):
        if not isinstance(selection, dict):
            return self._outcome(text, '所选项目无效，请重新选择。')
        kind, identifier = selection.get('kind'), selection.get('id')
        if kind not in ('movie', 'episode', 'channel', 'tvshow') or type(identifier) is not int:
            return None
        remembered = self.tools.media.get((kind, identifier))
        if remembered is None or normalize(selection.get('title', '')) != normalize(remembered['title']):
            return self._outcome(text, '这个项目已不在当前查询结果中，请重新选择。')
        if kind == 'tvshow' and not (remembered.get('_command_resume') or remembered.get('_command_tvshow')):
            return None
        if kind in ('movie', 'episode', 'tvshow'):
            name = {'movie': 'Movie', 'episode': 'Episode', 'tvshow': 'TVShow'}[kind]
            actual = self.tools.rpc('VideoLibrary.Get' + name + 'Details', {
                kind + 'id': identifier, 'properties': ['title']}).get(kind + 'details') or {}
            if (actual.get(kind + 'id') != identifier
                    or normalize(actual.get('title', '')) != normalize(remembered['title'])):
                return self._outcome(text, '媒体库项目已变化，请重新查询后再播放。')
        elif kind == 'channel':
            actual = self.tools.rpc('PVR.GetChannelDetails', {'channelid': identifier,
                'properties': ['channel']}).get('channeldetails') or {}
            if (actual.get('channelid') != identifier
                    or normalize(actual.get('channel') or actual.get('label', '')) != normalize(remembered['title'])):
                return self._outcome(text, '直播频道已变化，请重新查询后再播放。')
        if kind == 'tvshow':
            from .command_resume import tvshow
            return tvshow(self, text, remembered, cancelled, progress,
                          resume=remembered.get('_command_resume', True))
        return self._play(text, remembered, remembered.get('_command_resume', True), cancelled, progress)

    def _play(self, text, item, resume, cancelled, progress):
        progress('正在打开影片…' if item['kind'] != 'channel' else '正在打开直播频道…')
        name = 'play_channel' if item['kind'] == 'channel' else 'play_media'
        arguments = ({'channelid': item['id']} if name == 'play_channel' else
                     {'kind': item['kind'], 'id': item['id'], 'resume': resume})
        result = self.tools.execute(name, arguments, cancelled)
        trace = [{'name': name, 'arguments': arguments, 'ok': result.get('ok', True)}]
        if not result.get('ok', True):
            return self._outcome(text, '未能打开：' + result.get('error', '请重新查询后重试。'), trace=trace)
        # Player.Open acknowledges a request; only the UI's actual full-screen
        # playback check may close the conversation. Do not claim AV has started.
        return self._outcome(text, '正在打开《' + item['title'] + '》。', trace=trace)

    @staticmethod
    def _outcome(text, message, choices=(), trace=()):
        reply = json.dumps({'message': message, 'interaction': 'continue', 'choices': list(choices)}, ensure_ascii=False)
        return {'reply': reply, 'turn': [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': reply}],
                'tools': list(trace), 'agent_backend': 'local', 'model_invocations': 0}

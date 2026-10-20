"""Resolve approximate media requests locally, with a clear lead required to autoplay."""


def artwork(tools, item, cancelled):
    """Fetch art only for visible choices; the whole-library index stays small."""
    from .commands import normalize
    kind = item['kind']
    if kind not in ('movie', 'tvshow'):
        return
    if cancelled():
        raise InterruptedError('已取消查找。')
    name = 'Movie' if kind == 'movie' else 'TVShow'
    try:
        value = tools.rpc('VideoLibrary.Get' + name + 'Details', {
            kind + 'id': item['id'], 'properties': ['title', 'thumbnail', 'art']}).get(kind + 'details') or {}
    except InterruptedError:
        raise
    except (ValueError, OSError, RuntimeError):
        return  # Missing artwork must not discard a selectable media result.
    if cancelled():
        raise InterruptedError('已取消查找。')
    if value.get(kind + 'id') == item['id'] and normalize(value.get('title', '')) == normalize(item['title']):
        item.update({key: value[key] for key in ('thumbnail', 'art') if key in value})


def lookup(commands, text, request, cancelled, progress):
    from .media_catalog import catalogue
    from .media_match import rank
    progress('正在比较片名和读音…')
    try:
        rows = []
        automatic = False
        if request['kind'] in ('all', 'tvshow'):
            from .commands import normalize
            query = {'field': 'title', 'operator': 'is', 'value': request['title']}
            if request['year'] is not None:
                query = {'and': [query, {'field': 'year', 'operator': 'is', 'value': str(request['year'])}]}
            value = commands.tools.rpc('VideoLibrary.GetTVShows', {'properties': ['title', 'year'],
                'filter': query, 'limits': {'start': 0, 'end': 12}})
            exact = [item for item in value.get('tvshows', [])
                     if normalize(item.get('title', '')) == normalize(request['title'])
                     and (request['year'] is None or item.get('year') == request['year'])]
            rows = [dict(row={'kind': 'tvshow', 'id': item['tvshowid'], 'title': item['title'],
                              'year': item.get('year', 0)}, score=1.) for item in exact]
            automatic = len(rows) == 1 and value.get('limits', {}).get('total', len(rows)) == 1
        if not rows:
            if not request.get('allow_fuzzy', True):
                return None
            rows, automatic = rank(request['title'], catalogue(commands.tools, request['kind'], cancelled),
                                   request['year'], cancelled)
    except InterruptedError:
        raise
    except (ValueError, OSError, RuntimeError):
        return None  # No action was attempted; an enabled agent can still search.
    if not rows:
        return None
    choices = []
    for candidate in rows:
        item = dict(candidate['row'])
        if not automatic:
            artwork(commands.tools, item, cancelled)
        item['_command_resume'] = request['resume']
        if item['kind'] == 'tvshow':
            item['_command_tvshow'] = True
        commands.tools.media[(item['kind'], item['id'])] = item
        category = {'movie': '电影', 'tvshow': '电视剧', 'channel': '直播频道'}[item['kind']]
        label = item['title'] + ('（{}）'.format(item['year']) if item.get('year') else '') + ' · ' + category
        choices.append(dict(item, label=label, value='播放《' + item['title'] + '》'))
    if cancelled():
        raise InterruptedError('已取消查找。')
    commands.tools.latest_matches = [commands.tools.media[(row['kind'], row['id'])] for row in choices]
    if automatic:
        # The index is only a source of candidates. Check current title/ID and
        # channel lock state again before handing anything to Player.Open.
        outcome = commands._selected(text, choices[0], cancelled, progress)
    else:
        outcome = commands._outcome(text, '找到这些相近的影视或频道，请选择要播放的一项。', choices)
    if outcome is not None:
        outcome['matching'] = {'query': request['title'], 'automatic': automatic,
            'best_score': round(rows[0]['score'], 4), 'second_score': round(rows[1]['score'], 4) if len(rows) > 1 else 0,
            'candidates': len(rows),
            'target': {key: rows[0]['row'][key] for key in ('kind', 'id', 'title')} if automatic else None}
    return outcome

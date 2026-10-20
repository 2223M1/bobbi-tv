"""Structured library queries and explicit metadata updates using verified Kodi IDs."""
from .ui_context import text

KINDS = {'movie': ('Movie', 'movies'), 'tvshow': ('TVShow', 'tvshows'), 'episode': ('Episode', 'episodes')}


def verified(tools, kind, identifier):
    if (kind, identifier) not in tools.media:
        raise ValueError('这个媒体ID不在已查询结果中，请先搜索或读取当前影片。')
    name = KINDS[kind][0]
    value = tools.rpc('VideoLibrary.Get' + name + 'Details', {kind + 'id': identifier, 'properties': ['title']})
    row = value[kind + 'details']
    if row.get(kind + 'id') != identifier:
        raise ValueError('媒体库项目已变化，请重新查询。')
    return row


def find_media(tools, kind='movie', query='', genre='', actor='', director='', year_from=None, year_to=None,
               min_rating=None, max_minutes=None, watched='all', sort='rating', offset=0, limit=12,
               cancelled=lambda: False):
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError('起始年份不能大于结束年份。')
    if kind == 'tvshow' and max_minutes is not None:
        raise ValueError('电视剧没有可靠的整剧时长字段，请对电影使用时长条件。')
    rules = []
    def rule(field, operator, value):rules.append({'field': field, 'operator': operator, 'value': value})
    for field, value in (('title', query), ('genre', genre), ('actor', actor), ('director', director)):
        if value.strip():rule(field, 'contains', value.strip())
    if year_from is not None or year_to is not None:
        rule('year', 'between', [str(year_from or 1800), str(year_to or 2200)])
    if min_rating is not None:rule('rating', 'between', [str(min_rating), '10'])
    if max_minutes is not None:
        seconds = max_minutes * 60 + 1
        rule('time', 'lessthan', '{:02d}:{:02d}:{:02d}'.format(seconds // 3600, seconds // 60 % 60, seconds % 60))
    if watched in ('watched', 'unwatched'):
        rule('playcount', 'greaterthan' if watched == 'watched' else 'is', '0')
    elif watched == 'in_progress':rule('inprogress', 'true', 'true')
    properties = ['title', 'year', 'genre', 'rating', 'runtime', 'thumbnail', 'art', 'playcount', 'lastplayed']
    properties += ['resume'] if kind == 'movie' else ['watchedepisodes']
    params = {'properties': properties, 'limits': {'start': offset, 'end': offset + limit},
              'sort': {'method': sort, 'order': 'ascending' if sort == 'title' else 'descending'}}
    if rules:params['filter'] = rules[0] if len(rules) == 1 else {'and': rules}
    value = tools.rpc('VideoLibrary.Get' + KINDS[kind][0] + 's', params)
    matches = tools._remember(value.get(KINDS[kind][1], []), kind)
    tools.latest_matches = matches
    total = value.get('limits', {}).get('total', offset + len(matches))
    return {'matches': matches, 'total': total,
            'next_offset': offset + len(matches) if matches and offset + len(matches) < total else None,
            'note': '结果来自Kodi媒体库；没有填写的资料无法参与准确筛选。'}


def get_media_details(tools, kind, id, include_cast=True, cancelled=lambda: False):
    tools.latest_matches = []
    verified(tools, kind, id)
    fields = ['title', 'genre', 'plot', 'rating', 'userrating', 'runtime', 'playcount', 'lastplayed']
    if kind != 'episode':fields.append('year')
    fields += ['director', 'resume'] if kind != 'tvshow' else ['watchedepisodes', 'episode']
    if kind == 'episode':fields += ['showtitle', 'season', 'episode']
    if include_cast:fields.append('cast')
    value = tools.rpc('VideoLibrary.Get' + KINDS[kind][0] + 'Details', {kind + 'id': id, 'properties': fields})
    row = value[kind + 'details']
    result = {key: row[key] for key in ('year', 'rating', 'userrating', 'runtime', 'playcount', 'lastplayed',
        'resume', 'watchedepisodes', 'season', 'episode') if key in row}
    result.update(kind=kind, id=id, title=text(row.get('title') or row.get('label')), plot=text(row.get('plot'), 2000))
    for key in ('genre', 'director'):
        if key in row:result[key] = [text(item) for item in row[key][:30] if isinstance(item, str)]
    if row.get('showtitle'):result['showtitle'] = text(row['showtitle'])
    if include_cast:
        result['cast'] = [{'name': text(item.get('name')), 'role': text(item.get('role'))}
                          for item in row.get('cast', [])[:50] if isinstance(item, dict)]
    return {'media': result}


def update_watch_state(tools, kind, id, watched=None, reset_resume=False, rating=None, cancelled=lambda: False):
    verified(tools, kind, id)
    params = {kind + 'id': id}
    if watched is not None:params['playcount'] = 1 if watched else 0
    if reset_resume:params['resume'] = {'position': 0.0, 'total': 0.0}
    if rating is not None:params['userrating'] = rating
    if len(params) == 1:raise ValueError('请说明要修改观看状态、续播位置还是评分。')
    tools.rpc('VideoLibrary.Set' + KINDS[kind][0] + 'Details', params)
    tools.acted = True
    row = tools.media[(kind, id)]
    if watched is not None:row['playcount'] = params['playcount']
    if reset_resume:row['resume'] = params['resume']
    if rating is not None:row['userrating'] = rating
    return {'updated': dict(params, kind=kind, id=id)}


def library_maintenance(tools, action, kind=None, id=None, cancelled=lambda: False):
    if action == 'scan':
        if kind is not None or id is not None:raise ValueError('扫描不需要指定媒体ID；指定影片请使用refresh。')
        tools.rpc('VideoLibrary.Scan', {'showdialogs': False})
    else:
        if kind is None or id is None:raise ValueError('刷新资料需要已查询的媒体类型和ID。')
        verified(tools, kind, id)
        tools.rpc('VideoLibrary.Refresh' + KINDS[kind][0], {kind + 'id': id, 'ignorenfo': False})
    tools.acted = True
    return {'accepted': True, 'action': action, 'kind': kind, 'id': id,
            'note': 'Kodi已接收后台任务，尚未确认扫描或刷新完成。'}

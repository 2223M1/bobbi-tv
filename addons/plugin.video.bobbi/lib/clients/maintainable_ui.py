"""Thin Kodi directories; no scheduler, cloud writes or alternate player."""
import sys
from urllib.parse import urlencode


def url(action, **params):
    return 'plugin://plugin.video.bobbi/?' + urlencode(dict(action=action, **params))


def entries(action):
    if action == 'am6b_home':
        return [
            ('我的片库', 'plugin://plugin.video.bobbi.library/',
             '浏览已添加的网盘、NAS 和本机视频，选择原画质播放。'),
            ('管理片库来源', 'plugin://plugin.video.bobbi.library/?action=manage',
             '添加或修改连接。移除来源不会删除视频。'),
            ('影院设置', url('bobbi_setup'),
             '管理账号、播放偏好和更新。'),
            ('发现片单', url('am6b_discovery'),
             '按海报选片，再查看可用片源。'),
        ]
    if action == 'am6b_discovery':
        return [
            ('电影', url('am6b_streaming_catalog', section='movie', page=1), '非动漫电影片单 · 资源待选择'),
            ('电视剧', url('am6b_streaming_catalog', section='tv', page=1), '非动漫剧集片单 · 资源待选择'),
            ('本季度动漫', url('search_item', api='tmdb', mode='anime', submode='tv', category='Anime_Current_Quarter'), '动漫剧集片单 · 资源待选择'),
            ('动漫电影', url('search_item', api='tmdb', mode='anime', submode='movies', category='Anime_Movies_New'), '动漫电影片单 · 资源待选择'),
            ('搜索影视', url('am6b_streaming_search', section='multi'), '按影视名称搜索，不自动提交云任务'),
        ]
    raise ValueError('Unknown maintainable UI route')


def helper_pick(params):
    """TMDb Helper RunPlugin adapter with numeric identity, not a fake resolver."""
    import json
    import re
    import xbmcgui
    tmdb_id = str(params.get('id', ''))
    kind = params.get('kind')
    if kind not in {'movie', 'tv'} or not re.fullmatch(r'[1-9][0-9]{0,11}', tmdb_id):
        raise ValueError('TMDb numeric identity required')
    tv_data = {}
    if kind == 'tv':
        season, episode = str(params.get('season', '')), str(params.get('episode', ''))
        if not re.fullmatch(r'[0-9]{1,4}', season) or not re.fullmatch(r'[1-9][0-9]{0,3}', episode):
            raise ValueError('Exact season and episode required')
        tv_data = {'season': int(season), 'episode': int(episode)}
    from lib.utils.tmdb_init import ensure_tmdb_init
    from lib.clients.tmdb.utils.utils import tmdb_get
    ensure_tmdb_init()
    details = tmdb_get(kind + '_details', {
        'id': tmdb_id, 'language': 'en-US', 'append_to_response': 'external_ids',
    })
    if not details:
        xbmcgui.Dialog().notification('波比TV', '影片资料加载失败，请稍后重试')
        return
    name = getattr(details, 'title' if kind == 'movie' else 'name', '')
    if not isinstance(name, str) or not name.strip():
        xbmcgui.Dialog().notification('波比TV', '片名暂时不可用，请稍后重试')
        return
    external = getattr(details, 'external_ids', None) or {}
    ids = {'tmdb_id': tmdb_id, 'imdb_id': external.get('imdb_id') or getattr(details, 'imdb_id', None),
           'tvdb_id': external.get('tvdb_id')}
    from lib.search import run_search_entry
    run_search_entry({'query': name, 'mode': 'movies' if kind == 'movie' else 'tv',
                      'media_type': kind, 'ids': json.dumps(ids), 'tv_data': json.dumps(tv_data),
                      'force_select': True, 'skip_cancel_on_back': True})


def handle(params):
    import xbmcgui
    import xbmcplugin
    action = params.get('action', 'am6b_home')
    if action == 'bobbi_setup':
        import xbmc
        xbmc.executebuiltin('RunScript(script.bobbi.setup)')
        xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=False)
        return
    handle_id = int(sys.argv[1])
    rows = []
    for label, target, description in entries(action):
        item = xbmcgui.ListItem(label=label)
        item.setInfo('video', {'title': label, 'plot': description})
        item.setProperty('IsPlayable', 'false')
        item.setContentLookup(False)
        rows.append((target, item, True))
    xbmcplugin.setContent(handle_id, 'files')
    xbmcplugin.setPluginCategory(handle_id, '波比TV' if action == 'am6b_home' else '发现片单 · 资源待选择')
    xbmcplugin.addDirectoryItems(handle_id, rows)
    xbmcplugin.endOfDirectory(handle_id, cacheToDisc=False)

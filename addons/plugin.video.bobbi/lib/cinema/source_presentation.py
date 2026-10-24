"""Source-picker display fields, separate from search and playback identity."""
from urllib.parse import unquote
from bobbi_core.search_completion import provider_diagnostics, provider_failed

from lib.cinema.frontend_contract import chinese, clean_title, image_url, integer, text, translations


def window_fields(info, details=None, season_details=None):
    details, season_details = details or {}, season_details or {}
    mode = info.get('mode') or info.get('media_type')
    movie = mode in ('movie', 'movies')
    titles = translations(details, 'movie' if movie else 'tv')
    zh = titles['zh'] or chinese(info.get('bobi_title_zh')) or chinese(clean_title(info.get('title')))
    en = titles['en'] or text(info.get('bobi_title_en'))
    original = text(details.get('original_title') or details.get('original_name') or info.get('original_title'))
    work = zh or en or clean_title(info.get('title') or info.get('query')) or original
    result = dict(display_title=work, original_title=en or original,
                  season_episode='', display_subtitle='',
                  poster=image_url(details.get('poster_path') or info.get('poster'), 'w342'),
                  fanart=image_url(details.get('backdrop_path') or info.get('fanart'), 'w1280'))
    if movie:
        year = integer(text(details.get('release_date'))[:4]) or integer(info.get('year'))
        runtime = integer(details.get('runtime')) or integer(info.get('runtime'))
        result['display_subtitle'] = ' · '.join(v for v in (
            str(year) if year else '', '{}分钟'.format(runtime) if runtime else '') if v)
    elif mode in ('tv', 'tvshow', 'episode', 'anime'):
        tv = info.get('tv_data') if isinstance(info.get('tv_data'), dict) else {}
        season = integer(info.get('display_season', tv.get('season')))
        episode = integer(info.get('display_episode', tv.get('episode')))
        result['season_episode'] = ' · '.join(v for v in (
            '特别篇' if season == 0 else '第{}季'.format(season) if season is not None else '',
            '第{}集'.format(episode) if episode is not None else '') if v)
        # Lookup uses the original catalogue pair, not the production-season label.
        exact_episode = integer(tv.get('episode'))
        row = next((e for e in season_details.get('episodes', [])
                    if e.get('episode_number') == exact_episode), {})
        title = row.get('name') or tv.get('display_name_zh') or info.get('episode_title_zh') or tv.get('display_name') or tv.get('name') or info.get('episode_display_title')
        result['display_subtitle'] = unquote(text(title))
    return result


def search_status(providers, has_results):
    """PARTIAL can mean a deliberate query budget, not a failed provider."""
    terminal = {'COMPLETE', 'PARTIAL', 'FAILED', 'TIMEOUT', 'CANCELLED'}
    pending = sum(row.get('state') not in terminal for row in providers.values())
    partial = sum(row.get('state') == 'PARTIAL' for row in providers.values())
    failures = sum(provider_failed(row) for row in providers.values())
    status = ('正在查询 {} 个来源'.format(pending) if pending else
              '部分来源未完成' if failures else '查询完成' if has_results else '未找到匹配片源')
    error = '{} 个来源查询失败或超时'.format(failures) if failures else ''
    diagnostic = '{} 个来源仅返回部分结果'.format(partial) if partial else ''
    return status, error, diagnostic


def recommendation_label(recommended, caution, status):
    if recommended:
        return '需核实' if caution else '推荐'
    return {'Download': '待验证', 'Cached': '已标记缓存', 'Added': '待就绪',
            '待验证片源': '待验证', '服务标记已缓存': '已标记缓存', '已提交 · 待就绪': '待就绪'}.get(status, '')


def source_site_label(label, source_type, filter_option=False):
    """Project user-facing labels without changing provider identities.

    Cards already say BT种子. Filters still need a selectable label; neither
    projection changes the source's indexer, provider, aliases or identity.
    """
    key = text(label).casefold()
    if source_type == 'Direct' and key in {'juku', 'juku · 115分享'}:
        return '115 资源目录'
    if key == 'animegarden':
        return '动漫检索'
    if key == 'jacktook':
        return '影院来源'
    if key == 'torrserver':
        return '本机 BT 后台'
    if source_type == 'Torrent' and key == 'jackett':
        return 'BT种子' if filter_option else ''
    return label

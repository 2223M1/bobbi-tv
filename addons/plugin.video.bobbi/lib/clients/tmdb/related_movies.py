"""Lazy, conservative TV-to-movie discovery. Never merge movie IDs into seasons.

TMDb has no TV-to-movie collection edge. We label these as related-film
candidates, requiring a full catalog title plus an explicit film marker,
matching original language and animation class. No substring/fuzzy matching,
per-work tables, searches per home card, or special-episode substitution.
"""
import json
import re
import time
import unicodedata
from datetime import timedelta

# A policy change must not reuse a previously successful empty result.
CACHE_PREFIX = 'bobi_related_movies_v3:'


def plain(value):
    return value.to_dict() if hasattr(value, 'to_dict') else value


def normalized(value):
    return ''.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', str(value or '')).casefold()))


def film_root(value):
    text = unicodedata.normalize('NFKC', str(value or '')).strip()
    prefix = r'^(?:劇場版|剧场版|電影版|电影版|映画|Gekijouban\b|Gekijōban\b)[\s:：·「『-]*'
    suffix = r'[\s:：·-]*(?:劇場版|剧场版|電影版|电影版|(?:the\s+)?movie|the\s+motion\s+picture)\s*$'
    root, count = re.subn(prefix, '', text, count=1, flags=re.I)
    if not count:
        root, count = re.subn(suffix, '', text, count=1, flags=re.I)
    return normalized(root) if count else ''


def marked_subtitle(value, titles):
    """Full catalog title, film marker and delimited subtitle in one alias."""
    text = unicodedata.normalize('NFKC', value).strip().casefold()
    marker = (r'(?:劇場版|剧场版|電影版|电影版|電影|电影|映画|'
              r'\b(?:gekijouban|gekijōban|eiga|(?:the\s+)?movie|the\s+motion\s+picture)\b)')
    roots = []
    for pattern in ('^' + marker + r'[\s:·「『-]*', r'[\s:·-]*' + marker + '$'):
        root, count = re.subn(pattern, '', text, count=1)
        if count:
            roots.append(root)
    for title in titles:
        base = unicodedata.normalize('NFKC', title).strip().casefold()
        # Keep the actual title boundary before removing any punctuation;
        # a normalized string prefix would also accept unrelated longer names.
        for root in roots:
            if root.startswith(base):
                subtitle = re.fullmatch(r'[\s:·-]+(.+)', root[len(base):])
                if subtitle and normalized(subtitle.group(1)):
                    return True
        if text.startswith(base):
            subtitle = re.fullmatch(r'[\s:·-]+' + marker + r'[\s:·-]+(.+)', text[len(base):])
            if subtitle and normalized(subtitle.group(1)):
                return True
    return False


def aliases(details, kind):
    keys = ('name', 'original_name') if kind == 'tv' else ('title', 'original_title')
    values = [details.get(k, '') for k in keys]
    alt = details.get('alternative_titles') or {}
    values += [v.get('title', '') for v in alt.get('results', alt.get('titles', []))[:128] if isinstance(v, dict)]
    return list(dict.fromkeys(v for v in values if isinstance(v, str) and 2 <= len(v.strip()) <= 512))


def related(show, movie):
    if not isinstance(show, dict) or not isinstance(movie, dict):
        return False
    if type(movie.get('id')) is not int or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', movie.get('release_date') or ''):
        return False
    if not show.get('original_language') or show['original_language'] != movie.get('original_language'):
        return False
    def animated(item):
        return 16 in (item.get('genre_ids') or [v.get('id') for v in item.get('genres', [])])
    if animated(show) != animated(movie):
        return False
    if movie.get('runtime') is not None and (type(movie['runtime']) is not int or movie['runtime'] < 40):
        return False
    titles, names = aliases(show, 'tv'), aliases(movie, 'movie')
    trusted = {normalized(v) for v in titles}
    roots = {film_root(v) for v in names} - {''}
    if trusted & roots:
        return True
    # Subtitle-bearing names are weaker evidence than the exact film root.
    # Require real feature-length metadata, never a missing/guessed runtime.
    return (type(movie.get('runtime')) is int and movie['runtime'] >= 40
            and any(marked_subtitle(name, titles) for name in names))


def candidate(show, movie):
    """Cheap shortlist only; full movie alternative titles decide association."""
    if related(show, movie):
        return True
    # Some translations omit 'The Movie'. Permit catalog-title + a delimited
    # subtitle for the detail lookup, never for final inclusion or playback.
    if show.get('original_language') != movie.get('original_language'):
        return False
    titles = aliases(show, 'tv')
    for name in aliases(movie, 'movie'):
        # Search results generally lack runtime. This only authorizes the
        # bounded details lookup; related() still checks the complete metadata.
        if marked_subtitle(name, titles):
            return True
        text = unicodedata.normalize('NFKC', name).casefold()
        for alias in titles:
            base = unicodedata.normalize('NFKC', alias).casefold()
            if text == base or (text.startswith(base) and re.match(r'[\s:：·-]', text[len(base):])):
                return True
    return False


def directory_entry(ids):
    import xbmc
    from lib.utils.kodi.utils import make_list_item, build_url
    if xbmc.getSkinDir() != 'skin.bobbi.cinema' or not (ids or {}).get('tmdb_id'):
        return None
    item = make_list_item(label='剧场版 / 相关电影')
    item.getVideoInfoTag().setTitle('剧场版 / 相关电影')
    item.getVideoInfoTag().setPlot('按完整作品名与电影标识查找独立电影；不是特别篇或观影礼仪短片。')
    item.setProperty('IsPlayable', 'false')
    return (build_url('bobi_related_movies', ids={'tmdb_id': ids['tmdb_id']}), item, True)


def movie_entries(movies, inline=False):
    """Independent movie actions, never series episodes or playable resolver URLs."""
    from lib.clients.tmdb.base import BaseTmdbClient
    from lib.utils.general.utils import set_media_infoTag
    from lib.utils.kodi.utils import make_list_item
    rows = []
    for movie in movies:
        title = movie.get('title') or movie.get('original_title')
        item = make_list_item(label=title)
        set_media_infoTag(item, data=movie, mode='movies')
        item.setProperty('Bobi.RelationEvidence', 'catalog-full-title-film-marker')
        row = BaseTmdbClient.add_media_directory_item(list_item=item, mode='movies', title=title,
            ids={'tmdb_id': movie['id']}, media_type='movie', batch=True)
        # BaseTmdbClient predates manual source picking; this action only opens
        # the usual movie search. It must not start a Kodi resolver callback.
        item.setProperty('IsPlayable', 'false')
        if inline:
            caption = '相关电影 · ' + title
            item.setLabel(caption)
            item.getVideoInfoTag().setTitle(caption)
        rows.append(row)
    return rows


def checked_cache(identifier, cached, now=None):
    """Recheck association evidence without fetching data on the season page."""
    now = time.time() if now is None else now
    if (not isinstance(cached, dict) or cached.get('schema') != 2
            or type(identifier) is not int or identifier <= 0 or cached.get('id') != identifier
            or not isinstance(cached.get('show'), dict) or cached['show'].get('id') != identifier
            or type(cached.get('time')) not in (int, float)
            or not 0 <= now - cached['time'] < 7 * 86400
            or not isinstance(cached.get('movies'), list) or len(cached['movies']) > 5):
        return None
    try:
        movies = cached['movies']
        if len({value['id'] for value in movies}) != len(movies):
            return None
        if not all(related(cached['show'], value) for value in movies):
            return None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return cached


def directory_entries(ids, include_cached=False):
    entry = directory_entry(ids)
    if not entry:
        return []
    rows = []
    if include_cached:
        from lib.db.cached import cache
        try:
            identifier = int(ids['tmdb_id'])
            saved = checked_cache(identifier, cache.get(CACHE_PREFIX + str(identifier)))
            if saved is not None:
                rows = movie_entries(saved['movies'], inline=True)
        except (OSError, ValueError, TypeError, KeyError):
            pass  # Optional movie metadata cannot remove the season browser.
    return rows + [entry]


def append_directory_entry(ids, include_cached=False):
    from lib.utils.kodi.utils import add_directory_items_batch
    rows = directory_entries(ids, include_cached=include_cached)
    if rows:
        add_directory_items_batch(rows)


def discover(identifier, fetch, cached=None, now=None):
    """At most two searches + five candidate details, only on explicit entry."""
    now = time.time() if now is None else now
    valid = checked_cache(identifier, cached, now) is not None
    if valid and 0 <= now - cached.get('time', 0) < 86400:
        return cached, False
    try:
        show = plain(fetch('tv_details', {'id': identifier, 'language': 'zh-CN', 'append_to_response': 'alternative_titles'}))
        if not isinstance(show, dict) or show.get('id') != identifier:
            raise ValueError('TV metadata unavailable')
        queries = list(dict.fromkeys(v for v in (show.get('original_name'), show.get('name')) if v))[:2]
        if not queries:
            raise ValueError('TV title unavailable')
        candidates = {}
        for query in queries:
            page = plain(fetch('search_movie', {'query': query, 'page': 1}))
            # The bundled AsObj maps an empty JSON array to {} on to_dict().
            # Accept this only when the provider explicitly reports zero hits;
            # malformed/failed responses must still use the failure path.
            if isinstance(page, dict) and page.get('total_results') == 0 and page.get('results') == {}:
                page = dict(page, results=[])
            if not isinstance(page, dict) or not isinstance(page.get('results'), list):
                raise ValueError('Movie search unavailable')
            for value in page['results'][:20]:
                if candidate(show, value):
                    candidates[value['id']] = value
        movies = []
        for movie_id in sorted(candidates)[:5]:
            value = plain(fetch('movie_details', {'id': movie_id, 'language': 'zh-CN', 'append_to_response': 'alternative_titles,external_ids'}))
            if not isinstance(value, dict) or value.get('id') != movie_id:
                raise ValueError('Movie details unavailable')
            if related(show, value):
                movies.append(value)
        evidence = {key: show[key] for key in ('id', 'name', 'original_name', 'original_language',
                    'genres', 'genre_ids', 'alternative_titles') if key in show}
        return dict(schema=2, id=identifier, time=now, show=evidence,
                    movies=sorted(movies, key=lambda m: m['release_date'])), False
    except Exception:
        if valid and 0 <= now - cached.get('time', 0) < 7 * 86400:
            return cached, True
        raise


def show_related_movies(params):
    from lib.db.cached import cache
    from lib.clients.tmdb.utils.utils import tmdb_get
    from lib.utils.general.utils import set_content_type
    from lib.utils.kodi.utils import make_list_item, build_url, add_directory_items_batch, end_of_directory, apply_section_view, notification, kodilog
    from lib.utils.directory_failure import fail_directory
    try:
        identifier = int(json.loads(params.get('ids', '{}')).get('tmdb_id', 0))
        if identifier <= 0:
            raise ValueError('TV ID required')
        key = CACHE_PREFIX + str(identifier)
        value, stale = discover(identifier, tmdb_get, cache.get(key))
        if not stale:
            cache.set(key, value, timedelta(days=7))
    except Exception as error:
        kodilog('Related movie catalog failed: ' + type(error).__name__)
        return fail_directory('相关电影资料请求失败，可重试')
    if stale:
        notification('网络不可用，显示最近缓存的相关电影')
    rows = movie_entries(value['movies'])
    set_content_type('movies')
    if not rows:
        notification('未找到可可靠关联的电影，可在全局电影搜索中继续查找')
        item = make_list_item(label='暂无可可靠关联的电影 · 返回作品')
        item.getVideoInfoTag().setTitle('暂无可可靠关联的电影 · 返回作品')
        item.setProperty('IsPlayable', 'false')
        rows.append((build_url('show_seasons_details', ids={'tmdb_id': identifier}, mode='tv', media_type='tv'), item, True))
    add_directory_items_batch(rows)
    end_of_directory()
    apply_section_view('view.movies', content_type='movies')

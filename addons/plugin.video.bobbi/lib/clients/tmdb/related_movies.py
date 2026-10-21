"""Bounded, conservative TV-to-movie discovery. Never merge IDs into seasons.

TMDb has no TV-to-movie collection edge. We label these as related-film
candidates, requiring a full catalog title plus an explicit film marker,
matching original language and animation class. No substring/fuzzy matching,
per-work tables, searches per home card, or special-episode substitution.
"""
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

# A policy change must not reuse a previously successful empty result.
CACHE_PREFIX = 'bobi_related_movies_v4:'
MAX_PAGES = 500  # TMDb's actual ceiling; wall-time, not five pages, bounds a pass.
MAX_MOVIES = 100


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


def directory_entry(ids, label='相关电影资料未完成 · 重试'):
    import xbmc
    from lib.utils.kodi.utils import make_list_item, build_url
    if xbmc.getSkinDir() != 'skin.bobbi.cinema' or not (ids or {}).get('tmdb_id'):
        return None
    item = make_list_item(label=label)
    item.getVideoInfoTag().setTitle(label)
    item.getVideoInfoTag().setPlot('当前电影目录尚未确认完整；可重试，不代表没有关联电影。')
    item.setProperty('Bobi.CatalogStatus', 'incomplete')
    item.setProperty('IsPlayable', 'false')
    return (build_url('bobi_related_movies', ids={'tmdb_id': ids['tmdb_id']}), item, True)


def movie_entries(movies, inline=False):
    """Independent movie actions, never series episodes or playable resolver URLs."""
    from lib.clients.tmdb.base import BaseTmdbClient
    from lib.utils.general.utils import set_media_infoTag
    from lib.utils.kodi.utils import make_list_item, build_url
    rows = []
    for movie in movies:
        title = movie.get('title') or movie.get('original_title')
        item = make_list_item(label=title)
        set_media_infoTag(item, data=movie, mode='movies')
        item.setProperty('Bobi.RelationEvidence', 'catalog-full-title-film-marker')
        ids = {'tmdb_id': movie['id']}
        if (movie.get('external_ids') or {}).get('imdb_id'):
            ids['imdb_id'] = movie['external_ids']['imdb_id']
        BaseTmdbClient.add_media_directory_item(list_item=item, mode='movies', title=title,
            ids=ids, media_type='movie', batch=True)
        # A checked film card already has its own identity. No extra movie
        # detail hop; the normal search still enriches/rechecks that identity.
        row = (build_url('search', mode='movies', media_type='movie', query=title,
                         ids=ids, force_select=True), item, False)
        # BaseTmdbClient predates manual source picking; this action only opens
        # the usual movie search. It must not start a Kodi resolver callback.
        item.setProperty('IsPlayable', 'false')
        item.setProperty('Bobi.RelatedMovie', 'true')
        rows.append(row)
    return rows


def checked_cache(identifier, cached, now=None):
    """Recheck association evidence without fetching data on the season page."""
    now = time.time() if now is None else now
    if (not isinstance(cached, dict) or cached.get('schema') != 3
            or type(identifier) is not int or identifier <= 0 or cached.get('id') != identifier
            or not isinstance(cached.get('show'), dict) or cached['show'].get('id') != identifier
            or type(cached.get('time')) not in (int, float)
            or not 0 <= now - cached['time'] < 7 * 86400
            or type(cached.get('complete')) is not bool
            or not isinstance(cached.get('movies'), list) or len(cached['movies']) > MAX_MOVIES):
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


def directory_entries(ids, include_cached=False, prepared=None):
    import xbmc
    if xbmc.getSkinDir() != 'skin.bobbi.cinema' or not (ids or {}).get('tmdb_id'):
        return []
    rows, saved = [], prepared
    if include_cached and saved is None:
        from lib.db.cached import cache
        try:
            identifier = int(ids['tmdb_id'])
            saved = checked_cache(identifier, cache.get(CACHE_PREFIX + str(identifier)))
            if saved is not None and time.time() - saved['time'] >= 86400:
                saved = dict(saved, stale=True)
        except (OSError, ValueError, TypeError, KeyError):
            pass  # Optional movie metadata cannot remove the season browser.
    label = '相关电影资料未完成 · 重试'
    if saved is not None:
        rows = movie_entries(saved.get('movies', []), inline=True)
        if saved.get('complete') and not saved.get('stale'):
            return rows
        label = ('相关电影使用旧缓存 · 重试' if saved.get('stale') else
                 '电影目录未查全 · 重试')
    return rows + [directory_entry(ids, label)]


def append_directory_entry(ids, include_cached=False, prepared=None):
    from lib.utils.kodi.utils import add_directory_items_batch
    rows = directory_entries(ids, include_cached=include_cached, prepared=prepared)
    if rows:
        add_directory_items_batch(rows)


def discover(identifier, fetch, cached=None, now=None, show=None, deadline=None, cancelled=lambda: False, quiet=False):
    """Selected work only. Page explicitly, retain every verified film, no top-5.

    Two IO workers share a wall-time budget. Partial/failed discovery is never
    a complete negative result. Already verified films survive sibling failure.
    """
    from bobbi_core.metadata_transport import request_budget
    now = time.time() if now is None else now
    deadline = time.monotonic() + 12 if deadline is None else deadline
    valid = checked_cache(identifier, cached, now) is not None
    if valid and cached['complete'] and 0 <= now - cached.get('time', 0) < 86400:
        return cached, False

    def request(action, args):
        if cancelled() or time.monotonic() >= deadline:
            raise TimeoutError('MOVIE_DISCOVERY_BUDGET')
        with request_budget(deadline, cancelled, quiet=quiet):
            return plain(fetch(action, args))

    try:
        show = plain(show) if show is not None else request('tv_details', identifier)
        if (not isinstance(show, dict) or show.get('id') != identifier
                or not show.get('original_language') or not ('genres' in show or 'genre_ids' in show)):
            raise ValueError('TV metadata unavailable')
        queries = list(dict.fromkeys(v for v in (show.get('original_name'), show.get('name')) if v))[:2]
        if not queries:
            raise ValueError('TV title unavailable')
        def search(query):
            candidates, complete = {}, True
            pages, total, seen = 1, None, set()
            for number in range(1, MAX_PAGES + 1):
                if number > pages:
                    break
                try:
                    page = request('search_movie', {'query': query, 'page': number})
                except Exception:
                    return candidates, False
                # AsObj maps an empty array to {}; only explicit zero is valid.
                if isinstance(page, dict) and page.get('total_results') == 0 and page.get('results') == {}:
                    page = dict(page, results=[])
                if (not isinstance(page, dict) or not isinstance(page.get('results'), list)
                        or type(page.get('total_results')) is not int or page['total_results'] < 0):
                    return candidates, False
                received_pages = page.get('total_pages')
                # A provider must state pagination. A short first page alone
                # cannot prove there are no later films.
                expected_pages = ({0, 1} if page['total_results'] == 0
                                  else {(page['total_results'] + 19) // 20})
                if type(received_pages) is not int or received_pages not in expected_pages:
                    received_pages, complete = 1, False
                if number == 1:
                    pages, total = received_pages, page['total_results']
                if (received_pages != pages or page['total_results'] != total
                        or page.get('page') != number
                        or len(page['results']) != min(20, max(0, total - 20 * (number - 1)))):
                    complete = False
                complete = complete and pages <= MAX_PAGES and len(page['results']) <= 20
                for value in page['results'][:20]:
                    if (not isinstance(value, dict) or type(value.get('id')) is not int
                            or not value.get('original_language') or not aliases(value, 'movie')):
                        complete = False
                        continue
                    if value['id'] in seen:
                        complete = False
                    seen.add(value['id'])
                    if candidate(show, value):
                        candidates[value['id']] = value
            return candidates, complete

        candidates, complete = {}, True
        movies = {row['id']: row for row in cached['movies']} if valid else {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(search, query) for query in queries]
            for future in futures:
                try:
                    found, done = future.result()
                    candidates.update(found)
                    complete = complete and done
                except Exception:
                    complete = False
            identifiers = sorted(candidates)
            # Rotate the first pair on each pass. A persistent slow prefix
            # must not consume every subsequent pass before later films run.
            # This cursor grants no identity/completeness: every pass still
            # validates the entire current candidate set or stays partial.
            detail_after = cached.get('detail_after') if valid and not cached['complete'] else None
            if type(detail_after) is int and detail_after in identifiers:
                split = identifiers.index(detail_after) + 1
                identifiers = identifiers[split:] + identifiers[:split]
            else:
                detail_after = None
            # Submit pairs, not a hundred queued jobs that outlive navigation.
            for offset in range(0, len(identifiers), 2):
                if cancelled() or time.monotonic() >= deadline or len(movies) >= MAX_MOVIES:
                    complete = False
                    break
                # Canonical full details are also consumed by the source
                # picker; don't warm a reduced payload under a different key.
                pending = [(movie_id, pool.submit(request, 'movie_details', movie_id))
                    for movie_id in identifiers[offset:offset + 2]]
                if offset == 0:
                    # Rotating past the LAST submitted pair would starve a
                    # final candidate that starts with insufficient budget:
                    # cursor=end would repeat the original slow prefix forever.
                    detail_after = pending[-1][0]
                for movie_id, future in pending:
                    try:
                        value = future.result()
                        if (not isinstance(value, dict) or value.get('id') != movie_id
                                or not value.get('original_language') or not aliases(value, 'movie')
                                or not ('genres' in value or 'genre_ids' in value)
                                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value.get('release_date') or '')):
                            raise ValueError('Movie details unavailable')
                        if related(show, value):
                            movies[movie_id] = value
                        elif value.get('alternative_titles') is None:
                            # A legacy canonical payload may be the validated
                            # fallback after its one-time alias upgrade failed.
                            complete = False
                        else:
                            movies.pop(movie_id, None)
                    except Exception:
                        complete = False
        if cancelled():
            raise TimeoutError('MOVIE_DISCOVERY_CANCELLED')
        if complete:
            movies = {key: value for key, value in movies.items() if key in candidates}
        complete = complete and len(movies) <= MAX_MOVIES
        evidence = {key: show[key] for key in ('id', 'name', 'original_name', 'original_language',
                    'genres', 'genre_ids', 'alternative_titles') if key in show}
        return dict(schema=3, id=identifier, time=cached['time'] if valid and not complete else now,
                    show=evidence, complete=complete,
                    detail_after=None if complete else detail_after,
                    movies=sorted(movies.values(), key=lambda m: (m['release_date'], m['id']))[:MAX_MOVIES]), bool(not complete and valid)
    except Exception:
        if valid and 0 <= now - cached.get('time', 0) < 7 * 86400:
            return cached, True
        raise


def load(identifier, show=None, deadline=None, cancelled=lambda: False, quiet=False):
    from lib.db.cached import cache
    from lib.clients.tmdb.utils.utils import tmdb_get
    key = CACHE_PREFIX + str(identifier)
    value, stale = discover(identifier, tmdb_get, cache.get(key), show=show,
                            deadline=deadline, cancelled=cancelled, quiet=quiet)
    if not cancelled():
        cache.set(key, value, timedelta(days=7))
    return dict(value, stale=stale)


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
        value = load(identifier)
        stale = value.get('stale')
    except Exception as error:
        kodilog('Related movie catalog failed: ' + type(error).__name__)
        return fail_directory('相关电影资料请求失败，可重试')
    if stale:
        notification('网络不可用，显示最近缓存的相关电影')
    rows = movie_entries(value['movies'])
    set_content_type('movies')
    if not value['complete'] or stale:
        rows.append(directory_entry({'tmdb_id': identifier}, '电影目录未查全 · 重试'))
    elif not rows:
        notification('未找到可可靠关联的电影，可在全局电影搜索中继续查找')
        item = make_list_item(label='未找到已确认关联的电影 · 打开作品季目录')
        item.getVideoInfoTag().setTitle('未找到已确认关联的电影 · 打开作品季目录')
        item.setProperty('IsPlayable', 'false')
        rows.append((build_url('show_seasons_details', ids={'tmdb_id': identifier}, mode='tv', media_type='tv'), item, True))
    add_directory_items_batch(rows)
    end_of_directory()
    apply_section_view('view.movies', content_type='movies')

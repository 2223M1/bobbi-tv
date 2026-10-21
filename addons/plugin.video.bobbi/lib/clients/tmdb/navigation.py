"""One selected-work preparation phase, backed by existing detail caches.

No home-card fanout, player/transfer side effects, or workers surviving this
directory invocation. Prepared pages are account-neutral public metadata.
"""
from concurrent.futures import ThreadPoolExecutor
import time


def regular_seasons(metadata):
    # Future/zero-episode seasons still exist: do not turn a multi-season show
    # into a single-season show just because its next season has not aired.
    return sorted({row.get('season_number') for row in metadata.get('seasons', [])
                   if hasattr(row, 'get') and type(row.get('season_number')) is int
                   and row['season_number'] > 0})


def prepare(metadata, ids, deadline=None, cancelled=None, preferred_season=None, quiet=False):
    import xbmc
    from bobbi_core.metadata_transport import request_budget
    from lib.clients.tmdb import episode_order, related_movies
    from lib.clients.tmdb.detail_cache import valid
    from lib.utils.views.shows import _fetch_localized_season_pages
    from lib.utils.kodi.utils import kodilog

    started = time.monotonic()
    deadline = min(deadline, started + 8) if deadline is not None else started + 8
    monitor = xbmc.Monitor()
    cancelled = cancelled or monitor.abortRequested
    result = dict(order=None, movies=None, pages={})
    seasons = regular_seasons(metadata)
    animated = any(genre.get('id') == 16 for genre in metadata.get('genres', []) if hasattr(genre, 'get'))

    def bounded(fn, *args, **kwargs):
        if cancelled() or time.monotonic() >= deadline:
            return None
        with request_budget(deadline, cancelled, quiet=quiet):
            return fn(*args, **kwargs)

    # Usually one or two seasons. For long shows warm first/latest, not an
    # unbounded history. Subsequent clicks reuse precisely the same cache keys.
    warm = seasons if len(seasons) <= 2 else [seasons[0], seasons[-1]]
    if preferred_season in seasons:
        warm = list(dict.fromkeys([preferred_season] + warm))[:2]
    with ThreadPoolExecutor(max_workers=3) as pool:
        movies = pool.submit(bounded, related_movies.load, int(ids['tmdb_id']),
                             show=metadata, deadline=deadline, cancelled=cancelled, quiet=quiet)
        order = (pool.submit(bounded, episode_order.get_order, ids['tmdb_id'], fetch=True)
                 if animated and metadata.get('number_of_seasons') == 1 else None)
        pages = {number: pool.submit(bounded, _fetch_localized_season_pages,
                                    ids['tmdb_id'], number, deadline=deadline, cancelled=cancelled, quiet=quiet)
                 for number in warm}
        for name, future in [('movies', movies), ('order', order)]:
            if future is not None:
                try:
                    result[name] = future.result()
                except Exception as error:
                    kodilog('Navigation preparation {}: {}'.format(name, type(error).__name__))
        for number, future in pages.items():
            try:
                page = future.result()
                if page and any(valid('season_details', {'id': ids['tmdb_id'], 'season': number}, value)
                                for value in page.values()):
                    result['pages'][number] = page
            except Exception as error:
                kodilog('Navigation season preparation: ' + type(error).__name__)
    kodilog('Navigation preparation finished: elapsed_ms={} seasons={} movies={} complete={}'.format(
        round((time.monotonic() - started) * 1000), len(result['pages']),
        len((result['movies'] or {}).get('movies', [])), bool((result['movies'] or {}).get('complete'))))
    return result

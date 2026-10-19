"""Authorised Juku catalog adapter using the existing selected-share transport."""
import time
from threading import Lock

SITE = 'Juku · 115分享'


def enabled():
    try:
        import xbmcaddon
        return xbmcaddon.Addon('plugin.video.bobbi').getSetting('juku_enabled').strip().lower() == 'true'
    except (ImportError, RuntimeError):
        return False


def _query_cancelled(cancelled):
    """User cancellation is immediate; addon-setting reads are at most 1 Hz.

    The HTTP deadline watcher and search worker can both call this guard. A
    disabled request stays cancelled even if the switch is toggled back on.
    The caller already checked the initial setting before constructing it.
    """
    stopped = cancelled.is_set if hasattr(cancelled, 'is_set') else cancelled or (lambda: False)
    next_check, disabled, lock = time.monotonic() + 1, False, Lock()
    def check():
        nonlocal next_check, disabled
        if stopped():
            return True
        with lock:
            now = time.monotonic()
            if not disabled and now >= next_check:
                disabled = not enabled()
                next_check = now + 1
            return disabled
    return check


def is_source(source):
    return (getattr(source, 'type', '') == 'Direct'
            and getattr(source, 'indexer', '') == SITE
            and str(getattr(source, 'guid', '')).startswith('juku:')
            and str(getattr(source, 'url', '')).startswith('am6bjuku://'))


def find_sources(ids, mode, season, episode, year, aliases, release_order,
                 deadline, cancelled, movie_years=None, publish=None):
    from bobbi_core.search_completion import SearchResults, SearchCompletion, replace_rows
    if not enabled() or not ids.get('tmdb_id') or not aliases or year is None:
        return SearchResults([], SearchCompletion(planned=1, skipped=1))
    cancelled = _query_cancelled(cancelled)
    if cancelled():
        return SearchResults([], SearchCompletion(planned=1, skipped=1))
    import json
    from bobbi_core.juku_catalog import search, fields, verified
    from bobbi_catalog.identity import media_key
    from lib.domain.torrent import TorrentStream
    from lib.utils.general.processors import PreProcessBuilder
    from lib.utils.kodi.utils import kodilog
    spec = dict(tmdb_id=ids['tmdb_id'], mode=mode, season=season, episode=episode,
                year=year, aliases=list(aliases), release_order=release_order,
                media_key=media_key(ids['tmdb_id'], mode, season, episode))
    if mode == 'movies':
        from bobbi_core.movie_years import MovieYears
        if type(movie_years) is MovieYears and str(movie_years.tmdb_id) == str(ids['tmdb_id']):
            spec['_movie_years'] = movie_years
    def convert(rows):
        sources = []
        for row in rows:
            source = TorrentStream(**fields(row))
            source.catalogIdentity = dict(tmdb_id=str(ids['tmdb_id']), mode=mode,
                                          season=season, episode=episode)
            # Metadata age is never proof of file readability or account scope.
            source.verifiedShareFile = verified(row)
            sources.append(source)
        PreProcessBuilder(sources).extract_codec_hdr().filter_by_quality()
        return replace_rows(rows, sources)
    def progress(rows):
        if publish is not None and not cancelled():
            publish(convert(rows))
    rows = search(spec, deadline, cancelled,
        diagnostic=lambda value: kodilog('bobbi Juku search: ' + json.dumps(value, sort_keys=True)),
        publish=progress if publish is not None else None)
    if cancelled():
        return SearchResults([], rows.completion.combine(SearchCompletion(planned=1, skipped=1)))
    return convert(rows)


def resolve_source(source, item):
    if not enabled():
        raise RuntimeError('Juku 目录已关闭，请选择其他来源')
    from bobbi_catalog.api import ShareError
    from bobbi_catalog.identity import media_key
    from bobbi_catalog.stream import resolve
    tv = item.get('tv_data') or {}
    key = media_key((item.get('ids') or {}).get('tmdb_id'), item.get('mode'),
                    tv.get('season'), tv.get('episode'))
    try:
        # Registers only the stable selected tuple. The resident ShareStream
        # obtains/renews the actual URL using the user's own 115 authorization.
        return resolve(source.url, source.guid, source.title, source.size, key, account=item.get('_account'))
    except ShareError as error:
        messages = {'login_required': '115 登录已失效，请重新授权自己的网盘账号',
                    'share_unavailable': '这个分享已失效，请选择其他来源',
                    'identity_changed': '分享文件已变化，请刷新片源',
                    'refresh_required': '请刷新片源后重新选择文件'}
        raise RuntimeError(messages.get(error.code, '115 分享暂时无法解析，请重试或选择其他来源')) from None


def next_source(current, identity, cancelled, deadline):
    if not enabled():
        return None, 'PROVIDER_DISABLED'
    from bobbi_core.juku_catalog import next_file
    return next_file(current, identity, _query_cancelled(cancelled), deadline)

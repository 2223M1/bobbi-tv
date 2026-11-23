"""Authorised catalogue adapter using the existing selected-share transport."""
SITE = '自选源库 · 115'


def enabled():
    from bobbi_platform.source_libraries import capture
    try:
        return capture().current() is not None
    except (ImportError, OSError, ValueError, RuntimeError):
        return False


def _query_cancelled(cancelled, context=None):
    """Freeze this endpoint; edits revoke late discovery without touching video."""
    from bobbi_core.source_library import cancellation
    from bobbi_platform.source_libraries import capture_context
    context = context or capture_context()
    source = context.source if context is not None else None
    check = cancellation(source, cancelled) if source else lambda: True
    check.source = source
    check.share_reader = context.reader if source else None
    return check


def is_source(source):
    return (getattr(source, 'type', '') == 'Direct'
            and getattr(source, 'indexer', '') in (SITE, '自选源库 · 115分享')
            and str(getattr(source, 'guid', '')).startswith('sharelib:')
            and str(getattr(source, 'url', '')).startswith('am6bsharelib://'))


def find_sources(ids, mode, season, episode, year, aliases, release_order,
                 deadline, cancelled, movie_years=None, publish=None, source_check=None):
    from bobbi_core.search_completion import SearchResults, SearchCompletion, replace_rows
    if not ids.get('tmdb_id') or not aliases or year is None:
        return SearchResults([], SearchCompletion(planned=1, skipped=1))
    if source_check is None:
        if not enabled():
            return SearchResults([], SearchCompletion(planned=1, skipped=1))
        source_check = _query_cancelled(cancelled)
    cancelled = source_check
    if cancelled():
        return SearchResults([], SearchCompletion(planned=1, skipped=1))
    import json
    from bobbi_core.sharelib_catalog import search, fields, verified
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
        state=cancelled.source.root, client=cancelled.source.client(cancelled),
        share_reader=cancelled.share_reader,
        diagnostic=lambda value: kodilog('bobbi ShareLib search: ' + json.dumps(value, sort_keys=True)),
        publish=progress if publish is not None else None)
    if cancelled():
        return SearchResults([], rows.completion.combine(SearchCompletion(planned=1, skipped=1)))
    return convert(rows)


def resolve_source(source, item):
    if not enabled():
        raise RuntimeError('共享目录已关闭，请选择其他来源')
    from bobbi_catalog.identity import media_key
    from bobbi_catalog.stream import resolve
    tv = item.get('tv_data') or {}
    key = media_key((item.get('ids') or {}).get('tmdb_id'), item.get('mode'),
                    tv.get('season'), tv.get('episode'))
    # Registration only; preserve typed errors for the owning resolver UI.
    # The resident stream obtains the URL using the user's own authorization.
    return resolve(source.url, source.guid, source.title, source.size, key, account=item.get('_account'))


def next_source(current, identity, cancelled, deadline):
    if not enabled():
        return None, 'PROVIDER_DISABLED'
    from bobbi_core.sharelib_catalog import next_file
    check = _query_cancelled(cancelled)
    if check():
        return None, 'PROVIDER_DISABLED'
    return next_file(current, identity, check, deadline, state=check.source.root,
                     client=check.source.client(check))

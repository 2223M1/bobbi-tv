"""Optional Tencent catalogue bridge, isolated from the user's other providers."""
SITE = '115 资源目录'


def enabled():
    try:
        import xbmcaddon
        return xbmcaddon.Addon('script.module.bobbi.catalog').getSetting('enabled').lower() != 'false'
    except (ImportError, RuntimeError):
        return False


def is_source(source):
    return (getattr(source, 'type', '') == 'Direct' and getattr(source, 'indexer', '') == SITE
            and str(getattr(source, 'guid', '')).startswith('qqdocs:'))


def find_sources(ids, mode, season, episode, year, aliases, release_order, deadline, cancelled, movie_years=None):
    if not enabled() or not aliases or year is None:
        return []
    from bobbi_catalog.catalog import search
    from bobbi_catalog.identity import media_key
    from lib.domain.torrent import TorrentStream
    from lib.utils.general.processors import PreProcessBuilder
    from lib.utils.kodi.utils import kodilog
    import json
    spec = dict(mode=mode, year=int(year), aliases=list(aliases),
                season=(release_order or {}).get('season', season),
                episode=(release_order or {}).get('episode', episode),
                media_key=media_key(ids.get('tmdb_id'), mode, season, episode))
    if mode == 'movies':
        from bobbi_core.movie_years import MovieYears
        if type(movie_years) is MovieYears and str(movie_years.tmdb_id) == str(ids.get('tmdb_id')):
            spec.update(year=movie_years.primary_year, tmdb_id=movie_years.tmdb_id,
                        _movie_years=movie_years)
    sources = [TorrentStream(**row) for row in search(spec, deadline, cancelled,
        diagnostic=lambda value: kodilog('AM6B QQdocs search: ' + json.dumps(value, sort_keys=True)))]
    for source in sources:
        source.catalogIdentity = dict(tmdb_id=str(ids['tmdb_id']), mode=mode,
                                      season=season, episode=episode)
    PreProcessBuilder(sources).extract_codec_hdr().filter_by_quality()
    return sources


def resolve_source(source, item):
    if not enabled():
        raise RuntimeError('115 目录已关闭，请选择其他来源')
    from bobbi_catalog.api import ShareError
    try:
        from bobbi_catalog.stream import resolve
        from bobbi_catalog.identity import media_key
        tv = item.get('tv_data') or {}
        key = media_key((item.get('ids') or {}).get('tmdb_id'), item.get('mode'), tv.get('season'), tv.get('episode'))
        url = resolve(source.url, source.guid, source.title, source.size, key)
    except ShareError as error:
        messages = {'login_required': '115 分享登录已失效，请在影院设置重新扫码',
                    'share_unavailable': '这个分享已失效或访问码已变化，请选其他来源',
                    'identity_changed': '分享文件已变化，请刷新片源',
                    'refresh_required': '请刷新片源后重新选择 115 目录文件'}
        raise RuntimeError(messages.get(error.code, '115 目录暂时无法解析，请重试或选择其他来源')) from None
    # Hash-only evidence can be compared to the native selected-file receipt.
    # Never persist the signed address in provider/search/quick-play caches.
    try:
        import hashlib
        import json
        from pathlib import Path
        import time
        from bobbi_catalog.catalog import CACHE
        proof = dict(guid=source.guid, filename=source.title, media=key, at=time.time(),
                     url_sha256=hashlib.sha256(url.encode()).hexdigest(),
                     transport_sha256=hashlib.sha256(url.split('|', 1)[0].encode()).hexdigest())
        path = Path(CACHE).parent / 'last-resolution.json'
        path.write_text(json.dumps(proof), encoding='utf-8')
    except (OSError, ValueError):
        pass
    return url

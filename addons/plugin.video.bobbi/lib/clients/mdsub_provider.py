"""Optional MDsub bridge for the shared manual/automatic Cinema candidate pool."""


def find_sources(ids, mode, season, episode):
    try:
        import xbmcaddon
        addon = xbmcaddon.Addon('script.module.bobbi.mdsub')
        if addon.getSetting('enabled').lower() == 'false':
            return []
        from bobbi_mdsub.catalog import load, find_sources as find, source_fields
        from lib.domain.torrent import TorrentStream
        from lib.utils.general.processors import PreProcessBuilder
        rows = find(load(), (ids or {}).get('tmdb_id'), mode, season, episode)
        sources = [TorrentStream(**source_fields(row)) for row in rows]
        for source in sources:
            source.catalogIdentity = dict(tmdb_id=str(ids['tmdb_id']), mode=mode,
                                          season=season, episode=episode)
        # Keep the stable origin locator and one card; the actual player freshly
        # verifies personal-cloud identity before switching transport to 115.
        try:
            from bobbi_core.direct_cloud_client import snapshot, entry
            view = snapshot()
        except ImportError:
            view = {}
        for source in sources:
            lookup = dict(selection_policy='exact', request_id='0' * 32, ids=ids, mode=mode,
                tv_data=dict(season=season, episode=episode),
                direct_source=dict(provider='mdsub', guid=source.guid, locator=source.url, title=source.title, size=source.size))
            ready = entry(lookup, view) if view else None
            if ready and ready['state'] == 'ready':
                source.directCloudKey = ready['key']
                source.indexer = '115 · CD2 · 漫迪'
                source.subindexer = '个人 115 · 文件与读取已核验'
        # Exact ID/episode membership is already validated by the separate
        # catalogue. Do not re-filter its remapped filenames as torrent packs.
        PreProcessBuilder(sources).extract_codec_hdr().filter_by_quality()
        return sources
    except (ImportError, RuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        import xbmc
        xbmc.log('AM6B MDsub catalogue unavailable: ' + type(error).__name__, xbmc.LOGWARNING)
        return []

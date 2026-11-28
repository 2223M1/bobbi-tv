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
        # Exact ID/episode membership is already validated by the separate
        # catalogue. Do not re-filter its remapped filenames as torrent packs.
        PreProcessBuilder(sources).extract_codec_hdr().filter_by_quality()
        return sources
    except (ImportError, RuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        import xbmc
        xbmc.log('AM6B MDsub catalogue unavailable: ' + type(error).__name__, xbmc.LOGWARNING)
        return []

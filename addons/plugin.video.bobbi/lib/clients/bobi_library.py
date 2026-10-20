"""波比TV personal source index. Fast local listing; no cloud scan in the UI."""
import json
import os
import sys
from urllib.parse import urlencode

INDEX_LIMIT = 4 * 1024 * 1024


def local_path(root, path):
    if root != '/storage/videos/Clouddrive/CloudDrive' or not isinstance(path, str) or not path.startswith('/115open/') or any(p in {'.', '..'} for p in path.split('/')) or '\x00' in path:
        raise ValueError('Invalid personal library path')
    return root + path


def load_prepared_index():
    import xbmcvfs
    from lib.cinema.prepared_index import load
    path = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.bobbi/bobi-prepared.json')
    try:
        return load(path)
    except FileNotFoundError:
        return {'titles': [], 'generation': 0}


def load_ready_index():
    """Read the one published projection; never promote legacy/unqualified rows."""
    from datetime import datetime, timezone
    import xbmcvfs
    from lib.cinema.prepared_index import load
    path = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.bobbi/bobi-prepared.json')
    try:
        data = load(path)
        # Historical prepared rows without a per-resource qualification token
        # remain visible in the legacy library, but not on the ready shelf.
        titles = []
        for title in data['titles']:
            sources = [s for s in title['sources'] if s.get('prepared_qualification')]
            if sources:
                titles.append(dict(title, sources=sources))
        # Publication is atomic; this timestamp describes the snapshot only,
        # not a promise about present cloud availability or successful playback.
        stamp = datetime.fromtimestamp(os.stat(path).st_mtime, timezone.utc).isoformat(timespec='seconds')
        return dict(data, titles=titles, snapshot_published_at=stamp)
    except FileNotFoundError:
        return {'titles': [], 'generation': 0, 'snapshot_published_at': ''}


def prepared_generation():
    import xbmcvfs
    from lib.cinema.prepared_index import read_generation
    return read_generation(xbmcvfs.translatePath('special://profile/addon_data/plugin.video.bobbi/bobi-prepared.json'))


def load_index(path=None):
    data = _load_legacy_index(path)
    if path is not None:
        return data
    try:
        prepared = load_prepared_index()
        groups = {(str(t.get('tmdb_id')), t['kind']): dict(t, sources=list(t['sources'])) for t in data['titles']}
        for title in prepared['titles']:
            key = (str(title.get('tmdb_id')), title['kind'])
            if key not in groups:
                groups[key] = dict(title, sources=[])
            additions = title['sources']
            identifiers = {entry['key'] for entry in additions}
            groups[key]['sources'] = additions + [entry for entry in groups[key]['sources'] if entry.get('key') not in identifiers]
        if len(groups) > 1000:
            raise ValueError('Combined library title budget exceeded')
        return dict(data, titles=list(groups.values()), prepared_generation=prepared['generation'])
    except (OSError, ValueError, KeyError, TypeError):
        # Do not make the user's original library inaccessible if the separate
        # prepared snapshot is missing/corrupt. Never promote its invalid rows.
        return data


def _load_legacy_index(path=None):
    if path is None:
        import xbmcvfs
        path = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.bobbi/bobi-library.json')
    try:
        if os.path.getsize(path) > INDEX_LIMIT:
            raise ValueError('Library index exceeds budget')
        with open(path, encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('titles'), list) or len(data['titles']) > 1000:
            raise ValueError('Unsupported library index')
        for title in data.get('titles', []):
            if not isinstance(title, dict) or title.get('kind') not in {'movie', 'tv'} or not isinstance(title.get('sources'), list):
                raise ValueError('Invalid library title')
            for source in title.get('sources', []):
                if not isinstance(source, dict):
                    raise ValueError('Invalid library source')
                local_path(data.get('mount_root'), source['path'])
        return data
    except FileNotFoundError:
        return {'schema_version': 1, 'titles': [], 'mount_root': '/storage/videos/Clouddrive/CloudDrive'}


def find_sources(data, tmdb_id, mode, season=None, episode=None):
    if not tmdb_id:
        return []
    kind = 'tv' if mode in {'tv', 'anime', 'episode'} else 'movie'
    results = []
    for title in data.get('titles', []):
        if str(title.get('tmdb_id', '')) != str(tmdb_id) or title['kind'] != kind:
            continue
        for source in title['sources']:
            if kind == 'movie' or (str(source.get('season')) == str(season) and str(source.get('episode')) == str(episode)):
                identity = dict(tmdb_id=str(tmdb_id), mode='movies' if kind == 'movie' else 'tv',
                                season=season, episode=episode)
                results.append(to_source(data, source, identity))
    return results


def to_source(data, entry, identity=None):
    from lib.domain.torrent import TorrentStream
    from lib.utils.general.processors import PreProcessBuilder
    source = TorrentStream(title=entry['title'], type='Direct', indexer='115 · CD2',
                           bobiAnimeRelease=entry.get('origin') == 'bt-anime',
                           size=entry['bytes'], url=local_path(data['mount_root'], entry['path']),
                           guid='bobi:' + entry['key'],
                           catalogIdentity=identity or {},
                           localSubtitles=[local_path(data['mount_root'], p) for p in entry.get('subtitles', [])[:4]])
    source.preparedResourceId = entry.get('key', '') if entry.get('state') == 'qualified' else ''
    source.preparedVersionKey = entry.get('prepared_version_key', '')
    source.preparedInfoHash = entry.get('prepared_source_info_hash', '')
    from lib.utils.general.source_resolution import bind_prepared_profile
    source.preparedMediaProfile = bind_prepared_profile(source, entry)
    if source.preparedResourceId and entry.get('prepared_subtitle'):
        from bobbi_core.video_context import checked_video
        from lib.cinema.subtitle_projection import checked
        try:
            video = checked_video(entry.get('video_context'))
            if (video['release_key'] == source.preparedVersionKey
                    and video['selected']['source_info_hash'] == source.preparedInfoHash):
                source.preparedSubtitle = checked(entry['prepared_subtitle'], video)
        except (ValueError, KeyError, TypeError):
            pass  # Invalid optional subtitle projection does not hide the video.
    # Existing resolver accepts native filesystem Direct sources. No debrid
    # "cached" claim or signed URL persistence. Explicit BT-anime provenance
    # preserves preference after the verified release is copied into 115.
    PreProcessBuilder([source]).extract_codec_hdr().filter_by_quality()
    return source


def _url(action, **params):
    return 'plugin://plugin.video.bobbi/?' + urlencode({'action': action, **params})


def handle(params):
    import xbmcgui
    import xbmcplugin
    handle_id = int(sys.argv[1])
    try:
        ready_view = params.get('view') == 'ready'
        data = load_ready_index() if ready_view else load_index()
        title = next((t for t in data['titles'] if t['key'] == params.get('key')), None)
        if params.get('action') == 'bobi_open':
            if title is None:
                raise ValueError('Unknown library title')
            season, episode = params.get('season'), params.get('episode')
            entries = [s for s in title['sources'] if title['kind'] == 'movie' or (str(s['season']) == season and str(s['episode']) == episode)]
            if not entries:
                raise ValueError('Episode file not indexed')
            from lib.search import run_search_entry
            info = {k: title[k] for k in ('title', 'original_title', 'year', 'first_air_date', 'overview', 'poster', 'fanart', 'thumb') if k in title}
            info.update({'mode': 'movies' if title['kind'] == 'movie' else 'tv',
                    'query': title['original_title'], 'display_title': title['title'],
                    'ids': {'tmdb_id': str(title.get('tmdb_id', ''))},
                    'genre_ids': [16] if title.get('anime') else [],
                    'tv_data': {'season': int(season), 'episode': int(episode)} if season and episode else {}})
            # Sidecars remain associated with each exact selected file.
            identity = dict(tmdb_id=str(title.get('tmdb_id', '')), mode=info['mode'],
                            season=season, episode=episode)
            sources = [to_source(data, entry, identity) for entry in entries]
            import xbmc
            if xbmc.getSkinDir() != 'skin.bobbi.cinema':
                from lib.search import show_source_select
                from lib.utils.general.utils import set_watched_title
                set_watched_title(info['query'], info['ids'], info['mode'], media_type=title['kind'])
                show_source_select(sources, info['mode'], info['ids'], info['tv_data'],
                                   info['query'], title['kind'], False, source_metadata=info)
                return
            # Keep qualified file/sidecar bindings, but use the same full source
            # pool as ordinary title playback rather than a cloud-only island.
            run_search_entry(dict(query=info['query'], mode=info['mode'],
                ids=json.dumps(info['ids']), tv_data=json.dumps(info['tv_data']),
                media_type=title['kind'], force_select=params.get('force_select', False)),
                catalog_sources=sources)
            return
        rows = []
        if title and title['kind'] == 'tv':
            pairs = sorted({(s['season'], s['episode']) for s in title['sources']})
            records = [(title, '第 {} 季 · 第 {} 集'.format(s, e), False, {'key': title['key'], 'season': s, 'episode': e}) for s, e in pairs]
            content = 'episodes'
        else:
            section = params.get('section', 'all')
            records = [(t, t['title'], t['kind'] == 'tv', {'key': t['key']}) for t in data['titles']
                       if section == 'all' or (section == 'movie' and t['kind'] == 'movie' and not t['anime'])
                       or (section == 'tv' and t['kind'] == 'tv' and not t['anime'])
                       or (section == 'anime' and t['anime'])]
            content = 'movies' if section == 'movie' else 'videos'
        for record, label, folder, query in records:
            item = xbmcgui.ListItem(label=label)
            item.setLabel2(record['original_title'])
            item.setContentLookup(False)
            item.setInfo('video', {'title': label, 'originaltitle': record['original_title'], 'year': record['year'], 'plot': record.get('overview', '')})
            item.setArt({key: record.get(key, '') for key in ('poster', 'fanart', 'thumb')})
            from lib.clients.tmdb.frontend_metadata import apply
            mode = 'episode' if 'episode' in query else 'movie' if record['kind'] == 'movie' else 'tv'
            apply(item, record.get('tmdb_id'), mode, dict(record, ready=ready_view, **query))
            item.setProperty('Bobi.SourceState', '已准备索引 · 播放前复核' if ready_view else '已有文件 · 播放待验证')
            if ready_view:
                query['view'] = 'ready'
                item.setProperty('Bobi.SnapshotPublishedAt', data.get('snapshot_published_at', ''))
            # bobi_open is a UI playback action. It does not fulfill a
            # Kodi setResolvedUrl callback, regardless of the active skin.
            item.setProperty('IsPlayable', 'false')
            rows.append((_url('bobi_library' if folder else 'bobi_open', **query), item, folder))
        xbmcplugin.setContent(handle_id, content)
        if ready_view:
            stamp = data.get('snapshot_published_at') or '尚无快照'
            xbmcplugin.setPluginCategory(handle_id, '已准备资源 · 索引更新 ' + stamp)
        xbmcplugin.addDirectoryItems(handle_id, rows)
        xbmcplugin.endOfDirectory(handle_id, cacheToDisc=False)
        from lib.clients.tmdb.frontend_metadata import flush
        flush()
    except (ValueError, OSError, KeyError, TypeError):
        xbmcgui.Dialog().notification('波比TV', '片库索引不可用，请刷新索引或使用原始网盘浏览')
        if handle_id >= 0:
            xbmcplugin.endOfDirectory(handle_id, succeeded=False, cacheToDisc=False)

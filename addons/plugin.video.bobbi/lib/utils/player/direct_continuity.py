"""Same-release continuation for indexed direct providers, independent of BT prep.

Catalog identity proves the work/episode; parent share/directory and release
envelope prove the edition. No fuzzy global search, cloud task or signed cache.
"""
from copy import deepcopy
import re
import time
from uuid import uuid4

EPISODE = re.compile(r'(?i)(?<![a-z0-9])s(\d{1,2})[ ._-]*e(\d{1,3})(?![a-z0-9])')
QUALITY = re.compile(r'(?i)(?<![a-z0-9])(?:2160|1080|720|576|480)[pi](?![a-z0-9])')


def episode_data(current, season, episode):
    # An allowlist prevents previous subtitles, resume positions, native file
    # receipts, provider tokens and UI reservations leaking into the next file.
    keys = ('title', 'query', 'ids', 'mode', 'media_type', 'poster', 'description',
            'anime', 'selection_policy', 'fanart', 'thumb')
    result = {key: deepcopy(current[key]) for key in keys if key in current}
    result.update(tv_data=dict(season=season, episode=episode), autoplay=True,
                  playnext_context=True, cinema_continuity=True, is_torrent=False)
    if current.get('selection_policy') == 'exact':
        result['request_id'] = uuid4().hex
    return result


def release_envelope(name, season, episode):
    """Only a single explicit S/E plus full technical/group suffix is eligible.

    Episode-specific prose between S/E and quality is not a release identity.
    Preserve the entire title prefix and technical suffix, including revision,
    subtitles, codec, edition, group and container; do not equate resolution.
    """
    if not isinstance(name, str) or len(name) > 2048 or re.search(r'[\x00-\x1f/\\]', name):
        return None
    markers = list(EPISODE.finditer(name))
    if len(markers) != 1:
        return None
    marker = markers[0]
    if (int(marker[1]), int(marker[2])) != (season, episode):
        return None
    tail = name[marker.end():]
    if re.match(r'(?i)\s*(?:e\d|[-~–]\s*(?:s\d+\s*)?e?\d)', tail):
        return None
    quality = QUALITY.search(tail)
    if not quality:
        return None
    # Fail closed on edition/revision tags in the episode-title area.
    prose = tail[:quality.start()]
    if re.search(r'(?i)\[|\]|\(|\)|\b(?:v\d+|repack|proper|extended|uncut|dubbed)\b', prose):
        return None
    prefix = re.sub(r'[\W_]+', ' ', name[:marker.start()].casefold()).strip()
    suffix = tail[quality.start():].casefold()
    if not prefix or not re.search(r'\.(?:mkv|mp4|m4v|avi|webm|ts)$', suffix):
        return None
    return prefix, season, suffix


def attach_source(source, data):
    guid, locator = getattr(source, 'guid', ''), getattr(source, 'url', '')
    if data.get('is_torrent') or not isinstance(guid, str):
        return
    provider = 'mdsub' if guid.startswith('mdsub:') else 'qqdocs' if guid.startswith('qqdocs:') else None
    if provider:
        data['direct_source'] = dict(provider=provider, guid=guid, locator=locator,
                                    title=source.title, size=source.size)


def _identity(current):
    if current.get('mode') not in ('tv', 'anime', 'episode') or current.get('is_torrent'):
        return None
    tv, ids = current.get('tv_data') or {}, current.get('ids') or {}
    try:
        tmdb, season, episode = int(ids['tmdb_id']), int(tv['season']), int(tv['episode'])
        if min(tmdb, season, episode) < 1:
            return None
        return tmdb, season, episode
    except (KeyError, TypeError, ValueError):
        return None


def _mdsub(current, identity):
    from bobbi_mdsub.catalog import load, find_sources, source_fields
    import xbmcaddon
    if xbmcaddon.Addon('script.module.bobbi.mdsub').getSetting('enabled').lower() == 'false':
        return None, 'PROVIDER_DISABLED'
    tmdb, season, episode = identity
    catalog = load()
    pointer = current.get('direct_source') or {}
    anchors = []
    for row in find_sources(catalog, tmdb, 'tv', season, episode):
        fields = source_fields(row)
        if (row['episodes'] == [episode] and fields['title'] == current.get('source_title')
                and fields['url'] == pointer.get('locator', current.get('url'))
                and (not pointer or (pointer.get('guid') == fields['guid'] and pointer.get('size') == row['size']))):
            anchors.append(row)
    if len(anchors) != 1:
        return None, 'CURRENT_CATALOG_IDENTITY_MISSING'
    anchor = anchors[0]
    envelope = release_envelope(anchor['path'].rsplit('/', 1)[-1], season, episode)
    if envelope is None:
        return None, 'RELEASE_ENVELOPE_UNPROVEN'
    rows = [row for row in find_sources(catalog, tmdb, 'tv', season, episode + 1)
            if row['episodes'] == [episode + 1]
            and row['path'].rsplit('/', 1)[0] == anchor['path'].rsplit('/', 1)[0]
            and release_envelope(row['path'].rsplit('/', 1)[-1], season, episode + 1) == envelope]
    if len(rows) != 1:
        return None, 'NEXT_MISSING_OR_AMBIGUOUS'
    return source_fields(rows[0]), 'INDEXED_DIRECT_SAME_RELEASE'


def _qqdocs(current, identity, cancelled):
    from bobbi_catalog.catalog import Cache, Client, fields, share_for
    from bobbi_catalog.identity import media_key
    from lib.clients.qqdocs_provider import enabled
    if not enabled():
        return None, 'PROVIDER_DISABLED'
    tmdb, season, episode = identity
    pointer = current.get('direct_source') or {}
    if pointer.get('provider') != 'qqdocs':
        return None, 'CURRENT_CATALOG_IDENTITY_MISSING'
    cache = Cache()
    try:
        anchor = cache.selected(pointer['guid'], media_key(tmdb, 'tv', season, episode))
        if (not anchor or fields(anchor)['url'] != pointer.get('locator')
                or anchor['name'] != current.get('source_title') or anchor['size'] != pointer.get('size')):
            return None, 'CURRENT_CATALOG_IDENTITY_MISSING'
        envelope = release_envelope(anchor['name'], season, episode)
        if envelope is None:
            return None, 'RELEASE_ENVELOPE_UNPROVEN'
        # One share-read request to the selected, identity-checked share only.
        # No different document row, no general title search or cloud task.
        deadline = time.monotonic() + 6
        rows = Client().search(share_for(anchor['cell']), 'S{:02d}E{:02d}'.format(season, episode + 1), deadline)
        if cancelled():
            return None, 'CANCELLED'
        candidates = [r for r in rows if release_envelope(r['name'], season, episode + 1) == envelope]
        if len(candidates) != 1:
            return None, 'NEXT_MISSING_OR_AMBIGUOUS'
        row = dict(candidates[0], cell=anchor['cell'], origin=anchor['origin'])
        result = fields(row)
        cache.remember(result['guid'], media_key(tmdb, 'tv', season, episode + 1), row)
        return result, 'INDEXED_DIRECT_SAME_RELEASE'
    finally:
        cache.close()


def next_direct_data(current, index, cancelled=lambda: False):
    identity = _identity(current)
    if not identity or cancelled():
        return None, 'NOT_DIRECT_EPISODE'
    pointer = current.get('direct_source') or {}
    provider = pointer.get('provider')
    if not provider and current.get('indexer') == '漫迪 MDsub':
        provider = 'mdsub'  # Existing history must still pass exact catalog URL checks.
    if provider == 'mdsub':
        fields, reason = _mdsub(current, identity)
    elif provider == 'qqdocs':
        fields, reason = _qqdocs(current, identity, cancelled)
    else:
        return None, 'NO_DIRECT_CATALOG_ADAPTER'
    if not fields or cancelled():
        return None, reason if not cancelled() else 'CANCELLED'
    tmdb, season, episode = identity
    result = episode_data(current, season, episode + 1)
    result.update(url=fields['url'], source_title=fields['title'], size=fields['size'],
                  type='Direct', indexer=fields['indexer'], _catalog_next=True,
                  direct_source=dict(provider=provider, guid=fields['guid'], locator=fields['url'],
                                     title=fields['title'], size=fields['size']))
    # Prefer a qualified 115 mirror of this exact catalog file, not any BT
    # release of the episode. player.run() revalidates its qualification.
    mirrors = [row for title in index.get('titles', [])
               if title.get('kind') == 'tv' and str(title.get('tmdb_id')) == str(tmdb)
               for row in title.get('sources', [])
               if (row.get('season'), row.get('episode')) == (season, episode + 1)
               and row.get('title') == fields['title'] and row.get('bytes') == fields['size']
               and row.get('state') == 'qualified' and row.get('prepared_qualification')
               and all(row.get(k) for k in ('key', 'prepared_version_key', 'prepared_source_info_hash'))]
    if mirrors:
        from lib.clients.bobi_library import local_path
        row = sorted(mirrors, key=lambda r: r['key'])[0]
        result.update(url=local_path(index['mount_root'], row['path']), indexer='115 · CD2',
                      prepared_resource_id=row['key'], prepared_version_key=row['prepared_version_key'],
                      prepared_source_info_hash=row['prepared_source_info_hash'])
        result.pop('_catalog_next', None)
        return result, 'QUALIFIED_115_CATALOG_MIRROR'
    return result, reason


def resolve_direct(data, cancelled):
    """Resolve only the reserved next catalog file immediately before starting."""
    if cancelled():
        raise RuntimeError('CONTINUATION_CANCELLED')
    pointer = data['direct_source']
    identity = _identity(data)
    if not identity or pointer['title'] != data['source_title'] or pointer['size'] != data['size']:
        raise ValueError('DIRECT_IDENTITY_CHANGED')
    tmdb, season, episode = identity
    if pointer['provider'] == 'mdsub':
        import xbmcaddon
        from bobbi_mdsub.catalog import load, find_sources, source_fields
        if xbmcaddon.Addon('script.module.bobbi.mdsub').getSetting('enabled').lower() == 'false':
            raise ValueError('PROVIDER_DISABLED')
        rows = [source_fields(row) for row in find_sources(load(), tmdb, 'tv', season, episode)
                if row['episodes'] == [episode]]
        rows = [row for row in rows if row['guid'] == pointer['guid'] and row['url'] == pointer['locator']
                and row['title'] == pointer['title'] and row['size'] == pointer['size']]
        if len(rows) != 1:
            raise ValueError('DIRECT_IDENTITY_CHANGED')
        url = rows[0]['url']
    elif pointer['provider'] == 'qqdocs':
        from lib.clients.qqdocs_provider import enabled
        from bobbi_catalog.stream import resolve
        from bobbi_catalog.identity import media_key
        if not enabled():
            raise ValueError('PROVIDER_DISABLED')
        url = resolve(pointer['locator'], pointer['guid'], pointer['title'], pointer['size'],
                      media_key(tmdb, 'tv', season, episode))
        data['transient_url'] = True
        data['qqdocs_locator'] = pointer['locator']
    else:
        raise ValueError('UNSUPPORTED_DIRECT_PROVIDER')
    if cancelled():
        raise RuntimeError('CONTINUATION_CANCELLED')
    return url


class ProgressWatchdog:
    """No-progress deadline, not an EOF detector; pause/seek never count as stall."""
    def __init__(self, timeout=90.0):
        self.timeout, self.position, self.since = timeout, None, None

    def stalled(self, now, position, suspended=False):
        if suspended or self.position is None or abs(position - self.position) >= 0.25:
            self.position, self.since = position, now
            return False
        return self.since is not None and now - self.since >= self.timeout

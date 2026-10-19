"""Same-release continuation for indexed direct providers, independent of BT prep.

Catalog identity proves the work/episode; parent share/directory and release
envelope prove the edition. No fuzzy global search, cloud task or signed cache.
"""
from copy import deepcopy
import time
from uuid import uuid4

from lib.cinema import _shared
from bobbi_core.catalog_release import release_envelope


def episode_data(current, season, episode):
    # An allowlist prevents previous subtitles, resume positions, native file
    # receipts, provider tokens and UI reservations leaking into the next file.
    keys = ('title', 'query', 'ids', 'mode', 'media_type', 'poster', 'description',
            'anime', 'selection_policy', 'fanart', 'thumb', '_account')
    result = {key: deepcopy(current[key]) for key in keys if key in current}
    result.update(tv_data=dict(season=season, episode=episode), autoplay=True,
                  playnext_context=True, cinema_continuity=True, is_torrent=False)
    if current.get('selection_policy') == 'exact':
        result['request_id'] = uuid4().hex
    return result


def attach_source(source, data):
    guid, locator = getattr(source, 'guid', ''), getattr(source, 'url', '')
    if data.get('is_torrent') or not isinstance(guid, str):
        return
    from lib.clients.catalog_providers import provider_for
    provider = 'mdsub' if guid.startswith('mdsub:') else provider_for(source)
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
    from bobbi_catalog.catalog import Cache, fields, share_for
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
        from bobbi_platform.runtime import call
        expected = current.get('_account')
        if not expected:
            return None, 'ACCOUNT_SCOPE_REQUIRED'
        # Host gives this read six seconds; the normal three-second IPC timeout
        # must not discard a valid slow same-share continuation response.
        receipt = call('share_search', dict(account=expected, share=share_for(anchor['cell']),
            query='S{:02d}E{:02d}'.format(season, episode + 1)), timeout=6.5)
        if receipt.get('account') != expected or not isinstance(receipt.get('rows'), list):
            return None, 'ACCOUNT_SCOPE_CHANGED'
        rows = receipt['rows']
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
    elif provider == 'juku':
        from lib.clients.juku_provider import next_source
        fields, reason = next_source(current, identity, cancelled, time.monotonic() + 16)
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
    data.pop('_share', None)  # Never carry previous-file subtitle authority.
    if pointer['provider'] in ('qqdocs', 'juku'):
        from bobbi_platform.runtime import call
        expected = data.get('_account')
        if not expected or call('account_status', {}) != expected:
            raise RuntimeError('ACCOUNT_SCOPE_CHANGED')
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
                      media_key(tmdb, 'tv', season, episode), account=data['_account'])
        data['transient_url'] = True
        data['qqdocs_locator'] = pointer['locator']
    elif pointer['provider'] == 'juku':
        from lib.clients.juku_provider import resolve_source, SITE
        from lib.domain.torrent import TorrentStream
        source = TorrentStream(type='Direct', guid=pointer['guid'], url=pointer['locator'],
            title=pointer['title'], size=pointer['size'], indexer=SITE)
        url = resolve_source(source, data)
        data['transient_url'] = True
        data['juku_locator'] = pointer['locator']
    else:
        raise ValueError('UNSUPPORTED_DIRECT_PROVIDER')
    if cancelled():
        raise RuntimeError('CONTINUATION_CANCELLED')
    if pointer['provider'] in ('qqdocs', 'juku'):
        from bobbi_catalog.identity import media_key
        if call('account_status', {}) != data['_account']:
            raise RuntimeError('ACCOUNT_SCOPE_CHANGED')
        data['_share'] = dict(locator=pointer['locator'], guid=pointer['guid'],
            title=pointer['title'], size=pointer['size'], account=deepcopy(data['_account']),
            media=media_key(tmdb, 'tv', season, episode))
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

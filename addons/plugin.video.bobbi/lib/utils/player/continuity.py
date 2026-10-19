"""Same-version next-episode policy; no global cache, transcode or PC dependency.

Exact autoplay requires a qualified prepared binding and the verified current
release key. Filename-family matching is legacy compatibility, never its proof.
"""
import re
from uuid import uuid4
from urllib.parse import quote

from lib.cinema import _shared  # dependency bootstrap
from bobbi_core.release_names import family, specifications

CLOUD_ROOT = '/storage/videos/Clouddrive/CloudDrive'
HEAD_BYTES = 8 * 1024 * 1024






def same_version(current, candidate):
    # Exact normalized release family preserves episode-independent group,
    # edition, audio and subtitle tags. Do not equate just "1080p" with a release.
    a, b = family(current), family(candidate)
    return bool(a and a == b and specifications(current) == specifications(candidate))


def next_cloud_data(current, index):
    if current.get('mode') not in ('tv', 'anime', 'episode'):
        return None
    if current.get('selection_policy') == 'exact' and not re.fullmatch(
            '[0-9a-f]{64}', str(current.get('prepared_version_key', ''))):
        return None  # Retry when the current-source preparation proves its family.
    ids, tv = current.get('ids') or {}, current.get('tv_data') or {}
    try:
        season, episode = int(tv['season']), int(tv['episode'])
    except (KeyError, TypeError, ValueError):
        return None
    if season < 1 or episode < 1 or not ids.get('tmdb_id'):
        return None
    from lib.clients.bobi_library import local_path
    target = (season, episode + 1)
    # No season skipping, no missing-episode skipping, no near-title lookup.
    eligible = []
    for title in index.get('titles', []):
        if title.get('kind') != 'tv' or str(title.get('tmdb_id')) != str(ids['tmdb_id']):
            continue
        # Additional-track variants require both exact current/next records,
        # same-pack provenance and actual primary audio/video demux evidence.
        # Legacy or unprepared titles keep the existing strict family policy.
        anchors = []
        if current.get('selection_policy') == 'exact':
            from lib.utils.general.cinema_source_dedupe import _normalized_btih
            source_hash = _normalized_btih(current.get('prepared_source_info_hash') or current.get('info_hash'))
            for candidate in title.get('sources', []):
                if (source_hash and (candidate.get('season'), candidate.get('episode')) == (season, episode)
                        and candidate.get('prepared_version_key') == current.get('prepared_version_key')
                        and candidate.get('prepared_source_info_hash') == source_hash
                        and (not current.get('prepared_resource_id')
                             or candidate.get('key') == current['prepared_resource_id'])):
                    anchors.append(candidate)
        for entry in title.get('sources', []):
            if (entry.get('season'), entry.get('episode')) != target:
                continue
            # Exact automatic playback must pass through the prepared-resource
            # revalidation in player.run(), never a filename-only legacy entry.
            if current.get('selection_policy') == 'exact' and (
                    entry.get('state') != 'qualified'
                    or not all(isinstance(entry.get(key), str) and entry[key] for key in
                               ('key', 'prepared_version_key', 'prepared_source_info_hash'))):
                continue
            version = current.get('prepared_version_key')
            compatible_variant = False
            if version and entry.get('prepared_version_key') != version and len(anchors) == 1:
                from lib.cinema.pack_media_equivalence import compatible_next
                from bobbi_core.episode_revision import qualified_next
                compatible_variant = qualified_next(anchors[0], entry) or compatible_next(anchors[0], entry)
            if ((version and entry.get('state') == 'qualified' and entry.get('prepared_version_key') == version)
                    or compatible_variant
                    or (not version and same_version(current.get('source_title', ''), entry.get('title', '')))):
                eligible.append(entry)
    if not eligible:
        return None
    # Multiple mirrors of the same release: stay in the current parent first.
    current_parent = str(current.get('url', '')).rsplit('/', 1)[0]
    eligible.sort(key=lambda e: local_path(index['mount_root'], e['path']).rsplit('/', 1)[0] != current_parent)
    entry = eligible[0]
    from lib.utils.player.direct_continuity import episode_data
    result = episode_data(current, season, episode + 1)
    for field in ('progress', 'current_time', 'total_time', 'resume', 'next_tv_data',
                  'playback_session_id', 'stream_subtitles', 'subtitles_path', 'simkl_resume_progress',
                  'trakt_resume_progress', 'magnet', 'info_hash', 'is_pack', 'pack_type', 'pack_seasons',
                  'episode_binding', 'request_id'):
        result.pop(field, None)
    result.update(url=local_path(index['mount_root'], entry['path']), source_title=entry['title'],
                  type='Direct', indexer='115 · CD2', is_torrent=False,
                  tv_data={'season': season, 'episode': episode + 1},
                  autoplay=True, playnext_context=True, cinema_continuity=True,
                  subtitles_path=[local_path(index['mount_root'], p) for p in entry.get('subtitles', [])[:4]])
    for key in ('prepared_version_key', 'prepared_source_info_hash'):
        result.pop(key, None)
        if entry.get(key):
            result[key] = entry[key]
    result.pop('prepared_resource_id', None)
    if entry.get('state') == 'qualified':
        result['prepared_resource_id'] = entry['key']
    if current.get('selection_policy') == 'exact':
        result['request_id'] = uuid4().hex
    return result


def warm_cloud_head(path, cancelled, session=None):
    """One 8 MiB range read; bounded, cancellable, no persistent local media.

    This warms the existing CD2 route, not the whole episode. A failed/expired
    warmup must never cause title substitution or be reported as ready media.
    """
    import time
    import requests
    from lib.clients.bobi_library import local_path
    cloud_path = str(path)[len(CLOUD_ROOT):] if str(path).startswith(CLOUD_ROOT + '/') else ''
    local_path(CLOUD_ROOT, cloud_path)
    if cancelled():
        return {'state': 'CANCELLED', 'bytes': 0}
    own_session = session is None
    session = session or requests.Session()
    session.trust_env = False
    # Legacy route previously observed on this box's CD2 0.8.20 and verified
    # independently by bounded media-header probes. Never export signed URLs.
    url = 'http://127.0.0.1:19798/static/http/127.0.0.1:19798/False/' + quote(cloud_path, safe='')
    started, count = time.monotonic(), 0
    try:
        with session.get(url, headers={'Range': 'bytes=0-{}'.format(HEAD_BYTES - 1)},
                         timeout=(2, 4), stream=True, allow_redirects=False) as response:
            if response.status_code != 206 or not response.headers.get('Content-Range', '').startswith('bytes 0-'):
                return {'state': 'RANGE_UNAVAILABLE', 'bytes': 0}
            for chunk in response.iter_content(65536):
                if cancelled():
                    return {'state': 'CANCELLED', 'bytes': count}
                if time.monotonic() - started > 16:
                    return {'state': 'TIME_BUDGET', 'bytes': count}
                count += min(len(chunk), HEAD_BYTES - count)
                if count >= HEAD_BYTES:
                    break
        return {'state': 'HEAD_READ_NOT_PLAYBACK_PROOF', 'bytes': count,
                'seconds': round(time.monotonic() - started, 3)}
    except (requests.RequestException, OSError):
        return {'state': 'UNAVAILABLE', 'bytes': count}
    finally:
        if own_session:
            session.close()

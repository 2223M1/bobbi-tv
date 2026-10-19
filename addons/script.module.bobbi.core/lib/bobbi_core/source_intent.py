"""Bind a normal exact-playback intent to freshly read torrent metadata.

The UI supplies a selection, never a verification flag. The service repeats
the same exact-selector contract over actual metadata before requesting any
cloud work. A trusted episode mapping is derived here, not copied from IPC.
"""
import hashlib
import json
from pathlib import PurePosixPath
import re

from bobbi_core.release_names import family
from bobbi_core.release_identity import bound_family
from bobbi_core.episode_identity import bind_selected_episode

VIDEO_SUFFIXES = {'.mkv', '.mp4', '.m4v', '.avi', '.ts', '.m2ts', '.mov', '.webm'}


def mapped_family(media, path, catalog):
    """Fingerprint a file only after exact selection; retain release variants."""
    from bobbi_core.catalog_identity import release_context
    pair = release_context(media, catalog)
    season, episode = (pair['season'], pair['episode']) if pair else (media['season'], media['episode'])
    name = PurePosixPath(path).name
    try:
        return bound_family(name, season, episode)
    except ValueError:
        if not pair or not pair['absolute_episode']:
            raise
        return bound_family(name, season, episode, pair['absolute_episode'])


def checked_body(body):
    if not isinstance(body, dict) or set(body) != {'request_id', 'media', 'selected', 'purpose'}:
        raise ValueError('Unknown source-intent fields')
    if not isinstance(body['request_id'], str) or not re.fullmatch('[0-9a-f]{32}', body['request_id']):
        raise ValueError('Exact playback request identity required')
    if body['purpose'] not in ('current', 'next', 'manual', 'recommendation'):
        raise ValueError('Unknown preparation purpose')
    media, selected = body['media'], body['selected']
    if not isinstance(media, dict) or set(media) != {'tmdb_id', 'kind', 'season', 'episode', 'anime', 'title', 'release_title'}:
        raise ValueError('Exact source catalog context required')
    if (type(media['tmdb_id']) is not int or media['tmdb_id'] <= 0 or media['kind'] not in {'movie', 'tv'}
            or type(media['anime']) is not bool):
        raise ValueError('Stable catalog identity required')
    for key in ('title', 'release_title'):
        if not isinstance(media[key], str) or not 1 <= len(media[key]) <= 1024 or '\x00' in media[key]:
            raise ValueError('Bounded title context required')
    if any(type(media[k]) is not int for k in ('season', 'episode')):
        raise ValueError('Integer episode identity required')
    if media['kind'] == 'tv' and (media['season'] < 1 or media['episode'] < 1):
        raise ValueError('Regular exact episode required')
    if media['kind'] == 'movie' and (media['season'] != 0 or media['episode'] != 0):
        raise ValueError('Movie cannot carry an episode')
    required = {'source_info_hash', 'torrent_file_id', 'torrent_path', 'torrent_file_bytes'}
    if not isinstance(selected, dict) or set(selected) != required:
        raise ValueError('Exact handoff file tuple required')
    source_hash = selected['source_info_hash']
    if not isinstance(source_hash, str) or not re.fullmatch('[0-9a-f]{40}', source_hash):
        raise ValueError('Normalized torrent hash required')
    if (type(selected['torrent_file_id']) is not int or selected['torrent_file_id'] < 0
            or type(selected['torrent_file_bytes']) is not int or selected['torrent_file_bytes'] <= 0
            or not isinstance(selected['torrent_path'], str) or not 1 <= len(selected['torrent_path']) <= 4096):
        raise ValueError('Exact positive file tuple required')
    return media, selected, source_hash


def verified_intents(body, metadata, account, destination, selector, catalog, include_next=True):
    media, selected, source_hash = checked_body(body)
    if metadata.get('hash', '').lower() != source_hash:
        raise ValueError('Fresh metadata belongs to another torrent')
    files = metadata.get('file_stats')
    if not isinstance(files, list) or not 1 <= len(files) <= 4096:
        raise ValueError('Complete bounded torrent file metadata required')
    seen_ids, seen_paths = set(), set()
    total, videos = 0, []
    for item in files:
        file_id, path, length = item.get('id'), item.get('path'), item.get('length')
        if type(file_id) is not int or file_id < 0 or type(length) is not int or length < 0:
            raise ValueError('Malformed torrent file identity')
        if (not isinstance(path, str) or not path or '\\' in path or '\x00' in path
                or PurePosixPath(path).is_absolute() or any(p in ('', '.', '..') for p in path.split('/'))
                or file_id in seen_ids or path in seen_paths):
            raise ValueError('Nonunique or unsafe torrent metadata')
        seen_ids.add(file_id)
        seen_paths.add(path)
        total += length
        if length and PurePosixPath(path).suffix.lower() in VIDEO_SUFFIXES:
            videos.append(dict(id=file_id, path=path, length=length))
    if total <= 0:
        raise ValueError('Empty torrent')
    is_tv = media['kind'] == 'tv'
    from bobbi_core.catalog_identity import release_context, release_binding
    current_pair = release_context(media, catalog) if is_tv else None
    # Match JackTorr's exact playback input: TorrServer's display title may
    # contain only the catalog name, while the selected release carries the
    # season. Keep both so conflicting seasons still fail closed. This context
    # never replaces the real file tuple or independent catalog identity proof.
    selection_title = ' '.join(str(metadata.get(key) or '') for key in ('title', 'name'))
    selection_title += ' ' + media['release_title']
    def choose(episode):
        target = dict(media, episode=episode)
        pair = release_context(target, catalog) if is_tv else None
        if current_pair and (not pair or pair['season'] != current_pair['season']):
            raise ValueError('Next catalog episode crosses release season')
        season = (pair['season'] if pair else media['season']) if is_tv else ''
        local_episode = pair['episode'] if pair else episode
        binding = None
        if is_tv:
            binding = (release_binding(target, catalog, source_hash) if pair else
                       bind_selected_episode({'tmdb_id': media['tmdb_id']},
                                             {'season': season, 'episode': episode}, source_hash))
        return selector(videos, season, local_episode if is_tv else '', selection_title,
                        source_hash, json.dumps(binding) if binding else '')
    current = choose(media['episode'])
    expected = dict(id=selected['torrent_file_id'], path=selected['torrent_path'], length=selected['torrent_file_bytes'])
    if any(type(selected[key]) is not int for key in ('torrent_file_id', 'torrent_file_bytes')) or current != expected:
        raise ValueError('Handoff selection does not match authoritative exact target')
    from bobbi_core.catalog_identity import prove_work
    work_identity = prove_work(media, current['path'], catalog)
    release_family = (mapped_family(media, current['path'], catalog)
                      if is_tv else family(PurePosixPath(current['path']).name))
    if not release_family:
        raise ValueError('Release version unavailable')
    version = hashlib.sha256(release_family.encode('utf-8')).hexdigest()
    targets = [(media['episode'], current, body['purpose'])]
    if is_tv and include_next:
        try:
            following = choose(media['episode'] + 1)
            next_media = dict(media, episode=media['episode'] + 1)
            from bobbi_core.release_names import specifications
            following_family = mapped_family(next_media, following['path'], catalog) if following else ''
            same_family = release_family == following_family
            if following and not same_family:
                from bobbi_core.episode_revision import compatible_pair
                same_family = compatible_pair(PurePosixPath(current['path']).name,
                    PurePosixPath(following['path']).name, media['season'], media['episode'], version,
                    hashlib.sha256(following_family.encode()).hexdigest())
            audio_candidate = False
            if following and not same_family:
                from bobbi_core.release_identity import audio_capsule_candidate
                if PurePosixPath(current['path']).parent == PurePosixPath(following['path']).parent:
                    try:
                        audio_candidate = (mapped_family(media, audio_capsule_candidate(PurePosixPath(current['path']).name), catalog)
                            == mapped_family(next_media, audio_capsule_candidate(PurePosixPath(following['path']).name), catalog))
                    except ValueError:
                        pass
            if (following and (same_family or audio_candidate)
                    and specifications(current['path']) == specifications(following['path'])):
                prove_work(next_media, following['path'], catalog)
                targets.append((media['episode'] + 1, following, 'next'))
        except ValueError:
            # The exact current file was already independently proved. An
            # ambiguous/foreign E+1 must not cancel preparation of that file;
            # it remains absent from the result and cannot be published ready.
            pass
    result = []
    for episode, item, purpose in targets:
        # Each variant retains its OWN exact key. Preparing an additional-track
        # candidate is not permission to autoplay it as the current version.
        target_version = (hashlib.sha256(mapped_family(dict(media, episode=episode), item['path'], catalog).encode()).hexdigest()
                          if is_tv else version)
        media_id = ('tmdb:tv:{}:s{}:e{}'.format(media['tmdb_id'], media['season'], episode) if is_tv
                    else 'tmdb:movie:{}'.format(media['tmdb_id']))
        request = dict(provider='115', account=account, destination=destination, source_info_hash=source_hash,
                       media_id=media_id, version_key=target_version, bytes_required=total, purpose=purpose)
        selection = dict(file=item, title=media['title'], release_title=PurePosixPath(item['path']).name,
                         anime=media['anime'], request_id=body['request_id'],
                         work_identity=work_identity,
                         metadata_sha256=hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        result.append((request, selection))
    return result

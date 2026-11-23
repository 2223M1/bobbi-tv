"""Prove one following release from actual metadata, never search labels alone.

This pure adapter neither fetches nor submits. The service supplies the frozen
verified current source and freshly fetched candidate metadata/catalog. Exactly
one anchored window target is returned to the existing durable preparation
queue; no recursion, quality-first substitution or cloud-ready flag is manufactured.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import PurePosixPath

from bobbi_core.catalog_identity import prove_work, release_context, release_binding
from bobbi_core.release_identity import bound_family
from bobbi_core.source_intent import checked_body, checked_target_offset, verified_intents, mapped_family, VIDEO_SUFFIXES
from bobbi_core.episode_identity import bind_selected_episode


def verified_anchor(anchor, selection, catalog):
    media, selected, source_hash = checked_body(anchor)
    if media['kind'] != 'tv' or anchor['purpose'] not in ('current', 'manual'):
        raise ValueError('Next discovery must be anchored to an actual current episode')
    expected = dict(id=selected['torrent_file_id'], path=selected['torrent_path'], length=selected['torrent_file_bytes'])
    if selection.get('file') != expected or selection.get('request_id') != anchor['request_id']:
        raise ValueError('Frozen current-source selection does not match anchor')
    proof = prove_work(media, expected['path'], catalog)
    old_work = selection.get('work_identity', {})
    if any(old_work.get(key) != proof[key] for key in ('provider', 'id', 'kind', 'matched_title', 'catalog_year')):
        raise ValueError('Current work identity changed')
    original_family = mapped_family(media, expected['path'], catalog)
    return media, original_family, proof


def verified_next(anchor, selection, metadata, account, destination, selector, catalog, target_offset=1):
    target_offset = checked_target_offset(target_offset)
    media, original_family, _ = verified_anchor(anchor, selection, catalog)
    source = metadata.get('hash', '')
    if not isinstance(source, str) or len(source) != 40 or set(source) - set('0123456789abcdef'):
        raise ValueError('Fresh exact candidate hash required')
    files = metadata.get('file_stats')
    if not isinstance(files, list) or not 1 <= len(files) <= 4096:
        raise ValueError('Bounded complete candidate metadata required')
    # verified_intents below validates every file's path, size, ID and total.
    # This preliminary selection must not treat file-list positions as IDs.
    videos = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise ValueError('Malformed candidate entry')
        if PurePosixPath(item['path']).suffix.lower() in VIDEO_SUFFIXES:
            videos.append({key: item[key] for key in ('id', 'path', 'length')})
    season, episode = media['season'], media['episode'] + target_offset
    next_media = dict(media, episode=episode)
    pair = release_context(next_media, catalog)
    current_pair = release_context(media, catalog)
    if current_pair and (not pair or pair['season'] != current_pair['season']):
        raise ValueError('Next catalog episode crosses release season')
    binding = (release_binding(next_media, catalog, source) if pair else
               bind_selected_episode({'tmdb_id': media['tmdb_id']}, {'season': season, 'episode': episode}, source))
    chosen = selector(videos, pair['season'] if pair else season, pair['episode'] if pair else episode,
                      str(metadata.get('title') or ''), source,
                      json.dumps(binding) if binding else '')
    request_body = deepcopy(anchor)
    request_body['purpose'] = 'next'
    request_body['media'].update(episode=episode, release_title=PurePosixPath(chosen['path']).name)
    request_body['selected'] = dict(source_info_hash=source, torrent_file_id=chosen['id'],
                                    torrent_path=chosen['path'], torrent_file_bytes=chosen['length'])
    targets = verified_intents(request_body, metadata, account, destination, selector, catalog, include_next=False)
    from bobbi_core.episode_revision import compatible_pair
    original_key = hashlib.sha256(original_family.encode()).hexdigest()
    if len(targets) != 1 or (targets[0][0]['version_key'] != original_key and not (target_offset == 1 and compatible_pair(
            PurePosixPath(anchor['selected']['torrent_path']).name, PurePosixPath(chosen['path']).name,
            media['season'], media['episode'], original_key, targets[0][0]['version_key']))):
        raise ValueError('Candidate is not the selected release family')
    return targets[0]

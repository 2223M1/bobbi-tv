"""Supplemental next-file proof for one exact pack with commentary variants.

This does not replace release keys. Both resources retain their independent
keys and must still pass normal fresh prepared-file resolution before playback.
"""
import hashlib
from pathlib import PurePosixPath
import re

from bobbi_core.release_identity import audio_capsule_candidate, bound_family
from bobbi_core.release_media_profile import same_main_media
from bobbi_core.video_context import checked_video


def compatible_next(first, following):
    try:
        a, b = checked_video(first['video_context']), checked_video(following['video_context'])
        current = re.fullmatch(r'tmdb:tv:([1-9]\d*):s([1-9]\d*):e([1-9]\d*)', a['media_id'])
        if current is None:
            return False
        work, season, episode = map(int, current.groups())
        if b['media_id'] != 'tmdb:tv:{}:s{}:e{}'.format(work, season, episode+1):
            return False
        for entry, context in ((first, a), (following, b)):
            if (entry['state'] != 'qualified' or entry['prepared_version_key'] != context['release_key']
                    or entry['prepared_source_info_hash'] != context['selected']['source_info_hash']
                    or entry['bytes'] != context['selected']['torrent_file_bytes']
                    or not re.fullmatch('[0-9a-f]{64}', entry.get('prepared_qualification', ''))):
                return False
        if (first['prepared_account'] != following['prepared_account']
                or not first['prepared_account'] or first['key'] == following['key']
                or a['selected']['source_info_hash'] != b['selected']['source_info_hash']
                or a['selected']['torrent_file_id'] == b['selected']['torrent_file_id']):
            return False
        ap, bp = PurePosixPath(a['selected']['torrent_path']), PurePosixPath(b['selected']['torrent_path'])
        if ap.parent != bp.parent:
            return False
        # The episode-specific original fingerprints must agree with the keys
        # actually qualified by the service, not a UI-supplied compatibility flag.
        for context, path, number in ((a, ap, episode), (b, bp, episode+1)):
            original = bound_family(path.name, season, number)
            if hashlib.sha256(original.encode()).hexdigest() != context['release_key']:
                return False
        if (bound_family(audio_capsule_candidate(ap.name), season, episode)
                != bound_family(audio_capsule_candidate(bp.name), season, episode+1)):
            return False
        return same_main_media(first['prepared_media_profile'], following['prepared_media_profile'])
    except (KeyError, TypeError, ValueError):
        return False

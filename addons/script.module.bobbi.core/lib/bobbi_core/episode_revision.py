"""Adjacent-episode compatibility, separate from exact resource/version identity.

An episode-local 09v2 repair does not require episode 10 to be v2 too. Only a
revision attached to the verified episode marker is ignored for continuation.
Standalone v2, editions, groups and technical tags remain significant. Exact
release keys, file tuples and cloud qualifications are never rewritten.
"""
import hashlib
from pathlib import PurePosixPath
import re

from bobbi_core.release_identity import bound_family
from bobbi_core.filename_semantics import parse_filename
from bobbi_core.release_names import specifications


def continuation_family(name, season, episode):
    bound_family(name, season, episode)  # Reject ambiguous/wrong episode first.
    removals = parse_filename(name).revision_spans
    for start, end in sorted(removals, reverse=True):
        name = name[:start] + name[end:]
    return bound_family(name, season, episode)


def compatible_pair(first, following, season, episode, first_key, next_key):
    """Recheck both *strict* keys before comparing one E -> E+1 relation."""
    try:
        for name, number, key in ((first, episode, first_key), (following, episode + 1, next_key)):
            if hashlib.sha256(bound_family(name, season, number).encode()).hexdigest() != key:
                return False
        return (continuation_family(first, season, episode)
                == continuation_family(following, season, episode + 1)
                and specifications(first) == specifications(following))
    except (TypeError, ValueError):
        return False


def qualified_next(first, following):
    """Both independent cloud records must be qualified and tuple-bound."""
    from bobbi_core.video_context import checked_video
    try:
        a, b = checked_video(first['video_context']), checked_video(following['video_context'])
        current = re.fullmatch(r'tmdb:tv:([1-9]\d*):s([1-9]\d*):e([1-9]\d*)', a['media_id'])
        if not current:
            return False
        work, season, episode = map(int, current.groups())
        if b['media_id'] != 'tmdb:tv:{}:s{}:e{}'.format(work, season, episode + 1):
            return False
        for entry, context, number in ((first, a, episode), (following, b, episode + 1)):
            if (entry['state'] != 'qualified' or (entry['season'], entry['episode']) != (season, number)
                    or entry['prepared_version_key'] != context['release_key']
                    or entry['prepared_source_info_hash'] != context['selected']['source_info_hash']
                    or entry['bytes'] != context['selected']['torrent_file_bytes']
                    or entry['title'] != PurePosixPath(context['selected']['torrent_path']).name
                    or not re.fullmatch('[0-9a-f]{64}', entry.get('prepared_qualification', ''))):
                return False
        if (not first['prepared_account'] or first['prepared_account'] != following['prepared_account']
                or first['key'] == following['key']):
            return False
        return compatible_pair(PurePosixPath(a['selected']['torrent_path']).name,
                               PurePosixPath(b['selected']['torrent_path']).name, season, episode,
                               a['release_key'], b['release_key'])
    except (KeyError, TypeError, ValueError):
        return False

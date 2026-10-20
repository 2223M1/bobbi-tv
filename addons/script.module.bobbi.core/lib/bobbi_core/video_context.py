"""Neutral verified video-file identity, independent of subtitle availability.

The existing media/release/file tuple and digest bytes are unchanged. This
module does no network IO, subtitle parsing, font work or full-file hashing.
"""
import hashlib
import json
from pathlib import PurePosixPath
import re

from bobbi_core.ledger import encode
from bobbi_core.preparation import MEDIA


def digest(value, length=64):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', value):
        raise ValueError('Normalized digest required')
    return value


def video_identity(media_id, release_key, selected):
    if not isinstance(media_id, str) or not MEDIA.fullmatch(media_id):
        raise ValueError('Exact media and episode identity required')
    digest(release_key)
    keys = {'source_info_hash', 'torrent_file_id', 'torrent_path', 'torrent_file_bytes'}
    if not isinstance(selected, dict) or set(selected) != keys:
        raise ValueError('Verified source file tuple required')
    digest(selected['source_info_hash'], 40)
    path = selected['torrent_path']
    if (type(selected['torrent_file_id']) is not int or selected['torrent_file_id'] < 0
            or type(selected['torrent_file_bytes']) is not int or selected['torrent_file_bytes'] <= 0
            or not isinstance(path, str) or not 1 <= len(path) <= 4096 or '\\' in path or '\x00' in path
            or PurePosixPath(path).is_absolute() or any(p in ('', '.', '..') for p in path.split('/'))):
        raise ValueError('Invalid exact file tuple')
    value = dict(media_id=media_id, release_key=release_key, selected=dict(selected))
    value['key'] = hashlib.sha256(encode(value).encode('utf-8')).hexdigest()
    return value


def checked_video(value):
    if not isinstance(value, dict) or set(value) != {'media_id', 'release_key', 'selected', 'key'}:
        raise ValueError('Exact video context required')
    rebuilt = video_identity(value['media_id'], value['release_key'], value['selected'])
    if rebuilt != value:
        raise ValueError('Video identity changed')
    return rebuilt


def migrate_entry(entry):
    """Consume the old field once at a persisted/protocol input boundary.

Never write two names, alter a file tuple, or choose one conflicting identity.
New producers emit video_context only; old disk snapshots can still be read.
"""
    if not isinstance(entry, dict):
        raise ValueError('Video-bearing record required')
    if 'subtitle_video' in entry:
        legacy = checked_video(entry['subtitle_video'])
        if 'video_context' in entry and checked_video(entry['video_context']) != legacy:
            raise ValueError('Conflicting legacy video context')
        entry['video_context'] = legacy
        del entry['subtitle_video']
    return entry


def prepared_video(queue, resource, source_hash):
    """Derive identity only through the existing qualified personal-cloud map."""
    from bobbi_core.prepared_qualification import qualification_token
    item = queue.ledger.get(resource)
    if item['state'] != 'ready' or item['suppressed']:
        raise ValueError('Cloud video is not qualified')
    qualification_token(queue, item, source_hash)
    rows = queue.db.execute('''SELECT b.evidence FROM prepared_bindings b
        JOIN tasks t ON t.id=b.task WHERE b.resource=? AND t.account=? AND t.source_hash=?''',
        (resource, item['account'], source_hash)).fetchall()
    identities = []
    for row in rows:
        proof = json.loads(row['evidence'])
        selected = dict(source_info_hash=source_hash, torrent_file_id=proof['torrent_file_id'],
                        torrent_path=proof['torrent_path'], torrent_file_bytes=proof['bytes'])
        identities.append(video_identity(item['media_id'], item['version_key'], selected))
    if not identities or any(row != identities[0] for row in identities):
        raise ValueError('Ambiguous cloud-to-source binding')
    return identities[0]

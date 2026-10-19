"""Local display facts for one qualified prepared file, not playback authority.

Only the personal-index converter issues this typed envelope. Provider JSON and
serialized dict copies cannot assert probe provenance. The published token is
historical metadata, not a signature or a substitute for fresh prepared resolve.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from bobbi_core.ledger import checked_cloud_file, encode, resource_id
from bobbi_core.release_media_profile import checked_profile
from bobbi_core.resolution import resolution_class
from bobbi_core.subtitle_binding import checked_video, digest


@dataclass(frozen=True)
class _PreparedMediaProfile:
    binding_json: str
    profile_json: str


@dataclass(frozen=True)
class ResolutionFacts:
    resolution: int
    measured: str = ''
    caution: str = ''


def _media_id(identity):
    if not isinstance(identity, dict) or identity.get('mode') not in ('movies', 'tv'):
        raise ValueError('Exact catalogue identity required')
    def number(key, minimum):
        value = identity.get(key)
        if (type(value) not in (int, str) or not re.fullmatch(r'[0-9]{1,12}', str(value))
                or int(value) < minimum):
            raise ValueError('Exact numeric catalogue identity required')
        return str(int(value))
    tmdb = number('tmdb_id', 1)
    if identity['mode'] == 'movies':
        return 'tmdb:movie:' + tmdb
    return 'tmdb:tv:{}:s{}:e{}'.format(tmdb, number('season', 0), number('episode', 1))


def _source_binding(source):
    if source.type != 'Direct' or source.indexer != '115 · CD2':
        raise ValueError('Prepared personal-index transport required')
    keys = ('title', 'url', 'guid', 'preparedResourceId', 'preparedVersionKey', 'preparedInfoHash')
    values = {key: getattr(source, key) for key in keys}
    if any(not isinstance(value, str) or not 1 <= len(value) <= 8192 for value in values.values()):
        raise ValueError('Bounded immutable source identifiers required')
    if type(source.size) is not int or source.size <= 0:
        raise ValueError('Exact file size required')
    return encode(dict(values, size=source.size, media=_media_id(source.catalogIdentity)))


def bind_prepared_profile(source, entry):
    """Validate the published exact-file projection; copy only optional facts.

    Malformed or old metadata loses this annotation, not its source card. No
    database, network, live availability check or playback permission is added.
    """
    try:
        if entry.get('state') != 'qualified':
            return None
        digest(entry.get('prepared_qualification'))
        profile = deepcopy(checked_profile(entry.get('prepared_media_profile')))
        video = checked_video(entry.get('subtitle_video'))
        media = _media_id(source.catalogIdentity)
        file = checked_cloud_file(dict(provider='115', account=entry.get('prepared_account'),
            file_id=entry.get('prepared_file_id'), cloud_path=entry.get('path'),
            bytes=entry.get('bytes'), kind='video', media_id=media,
            version_key=entry.get('prepared_version_key')))
        if (resource_id(file) != source.preparedResourceId
                or source.guid != 'bobi:' + source.preparedResourceId
                or source.url != '/storage/videos/Clouddrive/CloudDrive' + file['cloud_path']
                or video['media_id'] != media or video['release_key'] != source.preparedVersionKey
                or video['selected']['source_info_hash'] != source.preparedInfoHash
                or video['selected']['torrent_file_bytes'] != source.size):
            return None
        return _PreparedMediaProfile(_source_binding(source), encode(profile))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        return None


def source_resolution(source):
    """One conservative resolution decision shared by badges and ranking."""
    title = str(getattr(source, 'title', '') or '')
    fallback = ResolutionFacts(resolution_class(title))
    envelope = getattr(source, 'preparedMediaProfile', None)
    if type(envelope) is not _PreparedMediaProfile:
        return fallback
    try:
        if (type(envelope.binding_json) is not str or type(envelope.profile_json) is not str
                or len(envelope.profile_json) > 4096 or envelope.binding_json != _source_binding(source)):
            return fallback
        video = checked_profile(json.loads(envelope.profile_json))['video']
        dimensions = '{}×{}'.format(video['width'], video['height'])
        measured = resolution_class(dimensions)
        # Appending dimensions to the existing parser detects conflicting and
        # ambiguous title claims without duplicating its parsing policy.
        conflict = (resolution_class(title + ' ' + dimensions) != measured
                    or bool(fallback.resolution and fallback.resolution != measured))
        named_dimensions = re.findall(r'(?<![a-z0-9])(\d{3,5})\s*[x×]\s*(\d{3,5})(?![a-z0-9])', title, re.I)
        conflict = conflict or any((int(w), int(h)) != (video['width'], video['height'])
                                   for w, h in named_dimensions)
        caution = '分辨率标记冲突' if conflict else '非标准尺寸·待核对' if not measured else ''
        return ResolutionFacts(measured, '已备探测' + dimensions, caution)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        return fallback

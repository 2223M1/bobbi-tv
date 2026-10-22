"""Prefer an existing 115 copy of the SAME release; never merge by film/quality.

Pure candidate projection: no network, cloud tasks, file deletion or playback.
Uncertain equivalence stays separate. A cloud error must not silently start BT.
"""
import base64
import json
import re
import unicodedata
from urllib.parse import parse_qsl, urlsplit

from lib.utils.parsers.resolution import resolution_class


def _positive_bytes(value):
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,16}', value):
        return int(value)
    return 0  # Never treat rounded GB labels/floats as exact bytes.


def _normalized_btih(value):
    """Representation equality only; never rewrite the source or its identity."""
    if isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{40}', value):
        return value.lower()
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z2-7]{32}', value):
        return base64.b32decode(value.upper()).hex()
    return ''


def _bt_evidence(source):
    value = getattr(source, 'infoHash', '')
    normalized = _normalized_btih(value)
    if value not in ('', None) and not normalized:
        return '', True
    locator = getattr(source, 'url', '')
    if locator is None:
        locator = ''
    if not isinstance(locator, str):
        return '', True
    # URL parsers may strip leading C0 controls/spaces, or embedded CR/LF/TAB.
    # Reject these before scheme dispatch so a disguised conflicting magnet
    # cannot enter the less-specific name/byte equality path.
    if len(locator) > 16384 or any(ord(char) < 33 or ord(char) == 127 or char.isspace() for char in locator):
        return '', True
    if not locator.lower().startswith('magnet:'):
        return normalized, False
    # A contradictory/malformed magnet may not be hidden even by the separate
    # exact-name/bytes fallback. Bound parsing and require every BTIH to agree.
    try:
        parts = urlsplit(locator)
        if parts.netloc or parts.path or parts.fragment:
            return '', True
        fields = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=64)
        hashes = [_normalized_btih(item[9:]) for key, item in fields
                  if key.lower() == 'xt' and item.lower().startswith('urn:btih:')]
    except ValueError:
        return '', True
    if not normalized or not hashes or any(item != normalized for item in hashes):
        return '', True
    return normalized, False


def _bt_hash(source):
    return _bt_evidence(source)[0]


def _is_raw_bt(source):
    if _bt_evidence(source)[1]:
        return False
    kind = getattr(source, 'type', '')
    locator = str(getattr(source, 'url', '') or '')
    torrent = (kind == 'Torrent' or (kind == 'Stremio' and _bt_hash(source)
               and (not locator or locator.startswith('magnet:?'))))
    return (torrent
            and not getattr(source, 'debridType', '')
            and not getattr(source, 'addedToDebrid', False)
            and not getattr(source, 'isCached', False))


def _is_115_copy(source, context):
    if getattr(source, 'shareFailure', ''):
        return False
    from lib.utils.general.cinema_source_rank import catalog_identity_matches
    if (getattr(source, 'type', '') != 'Direct' or not catalog_identity_matches(source, context)
            or not _positive_bytes(getattr(source, 'size', 0))):
        return False
    guid = str(getattr(source, 'guid', '') or '')
    locator = str(getattr(source, 'url', '') or '')
    site = getattr(source, 'indexer', '')
    return bool(
        (site == '115 · CD2' and guid.startswith('bobi:')
         and locator.startswith('/storage/videos/Clouddrive/CloudDrive/115open/'))
        or (site in ('115 资源目录', '腾讯文档 · 115分享') and guid.startswith('qqdocs:')
            and locator.startswith('am6bqqdocs://'))
        or (site == 'Juku · 115分享' and guid.startswith('juku:')
            and locator.startswith('am6bjuku://')
            and getattr(source, 'verifiedShareFile', False) is True))


def _release_name(value):
    """Conservative full-name equality, not fuzzy title/edition matching."""
    if not isinstance(value, str) or not value or len(value) > 1024:
        return ''
    value = unicodedata.normalize('NFC', value).strip()
    if any(c in value for c in ('\n', '\r', '\x00', '/', '\\', '…', '...')):
        return ''  # Paths, multi-title descriptions and truncated names are not evidence.
    # Case/separator differences and the optional container suffix are the
    # only normalization. Retain PROPER, REPACK, editions, audio/sub tags, group
    # and every season/episode token. Do not strip brackets and their contents.
    value = re.sub(r'\.(?:mkv|mp4|m4v|avi|ts|m2ts)$', '', value, flags=re.I)
    if not resolution_class(value):
        return ''
    if not re.search(r'hevc|[hx][. _-]?26[45]|avc|web[. _-]?(?:dl|rip)|blu[. _-]?ray|bdremux|remux|bdrip', value, re.I):
        return ''
    return re.sub(r'[.\s_]+', ' ', value.casefold()).strip()


def _file_key(source):
    if getattr(source, 'isPack', False) or getattr(source, 'requiresCatalogEpisodeProof', False):
        return None  # A pack's total byte count does not identify its target file.
    size = _positive_bytes(getattr(source, 'size', 0))
    name = _release_name(getattr(source, 'title', ''))
    suffix = re.search(r'\.(mkv|mp4|m4v|avi|ts|m2ts)$', str(getattr(source, 'title', '')).strip(), re.I)
    return (name, size, suffix[1].lower() if suffix else '') if name and size else None


def unique_bt_releases(sources):
    """Project equivalent raw BT encodings to one card, not a new identity.

    Base32 and hexadecimal BTIH describe the same swarm. Keep the original
    first source (including its locator and required file proof), never merge
    by display title, or collapse different per-file choices in a batch.
    This does not claim that metadata or media bytes have been verified.
    """
    result, seen = [], set()
    for source in sources:
        metadata = getattr(source, 'stremioMetadata', {})
        key = None
        if _is_raw_bt(source) and _bt_hash(source) and isinstance(metadata, dict):
            index, path = metadata.get('fileIdx'), metadata.get('filename')
            # Malformed hints are not evidence for equivalence. Do not raise
            # or silently drop a card because a provider returned a container.
            if ((index is None or type(index) is int) and
                    (path is None or isinstance(path, str))):
                # Nested behaviorHints and external/local subtitle attachments
                # affect what the selected card plays. Preserve differing or
                # malformed payloads instead of silently losing that choice.
                try:
                    payload = json.dumps(dict(metadata=metadata,
                        subtitles=getattr(source, 'streamSubtitles', []),
                        local_subtitles=getattr(source, 'localSubtitles', []),
                        prepared_subtitle=getattr(source, 'preparedSubtitle', {})),
                        ensure_ascii=False, sort_keys=True, allow_nan=False)
                    if len(payload.encode('utf-8')) <= 16384:
                        key = (_bt_hash(source), payload,
                               bool(getattr(source, 'requiresCatalogEpisodeProof', False)))
                except (TypeError, ValueError, RecursionError):
                    pass
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        result.append(source)
    return result


def prefer_115_copies(sources, context=None):
    """Hide raw BT only with a validated 115 counterpart in this request.

    Prepared copies have the original infohash plus an exact requested-episode
    binding, so they may also supersede their parent season pack. For shares
    without that provenance require an exact full release name AND byte size,
    and never collapse an ambiguous pack. All other releases remain selectable.
    """
    sources = list(sources)
    hashes, files = set(), set()
    for source in sources:
        if not _is_115_copy(source, context or {}):
            continue
        original = str(getattr(source, 'preparedInfoHash', '') or '').lower()
        version = str(getattr(source, 'preparedVersionKey', '') or '')
        if (getattr(source, 'preparedResourceId', '')
                and re.fullmatch(r'[0-9a-f]{40}', original)
                and re.fullmatch(r'[0-9a-f]{64}', version)):
            hashes.add(original)
        key = _file_key(source)
        if key:
            files.add(key)
            # A BT display title often omits the container suffix. Two explicit
            # DIFFERENT container types, however, are not the same-file proof.
            files.add((key[0], key[1], ''))
    if not hashes and not files:
        return sources
    return [source for source in sources if not (
        _is_raw_bt(source) and
        ((_bt_hash(source) and _bt_hash(source) in hashes) or _file_key(source) in files))]

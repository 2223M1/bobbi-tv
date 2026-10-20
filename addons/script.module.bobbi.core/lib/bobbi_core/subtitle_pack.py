"""Same-release sidecars selected through JackTorr's existing exact matcher.

These are preparation-owner functions, not an IPC accepting caller-supplied
readiness. The source metadata and actual fetched bytes remain separate proofs.
Same-pack provenance is not a cross-release timing correlation or visual test.
"""
import hashlib
from pathlib import PurePosixPath
import re

from bobbi_core.metadata_cache import normalized
from bobbi_core.subtitle_binding import checked_video, digest
from bobbi_core.subtitle_cues import parse


def select(video, metadata, matcher):
    checked_video(video)
    metadata, raw = normalized(metadata)
    chosen = video['selected']
    media = dict(id=chosen['torrent_file_id'], path=chosen['torrent_path'],
                 length=chosen['torrent_file_bytes'])
    if metadata['hash'] != chosen['source_info_hash'] or media not in metadata['file_stats']:
        raise ValueError('Selected video is absent from the verified release')
    candidates = matcher(media['path'], metadata['file_stats'])
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    if candidate not in metadata['file_stats'] or candidate == media:
        raise ValueError('Matcher returned a file outside this release')
    path = PurePosixPath(candidate['path'])
    if (path.suffix.casefold() not in {'.srt', '.ass', '.ssa'}
            or not 0 < candidate['length'] <= 2 * 1024 * 1024):
        raise ValueError('Bounded text sidecar required')
    # Do not promote signs/songs-only tracks, even if their filename says CHS.
    if re.search(r'(?i)\b(?:forced|signs|songs)\b|特效|招牌|仅字幕牌|僅字幕牌', candidate['path']):
        return None
    return dict(video_key=video['key'], source_info_hash=metadata['hash'],
                metadata_sha256=hashlib.sha256(raw).hexdigest(),
                video_file=media, subtitle_file=dict(candidate))


def timing(video, raw, selection, duration):
    """Make evidence after exact cloud/torrent mapping and bounded byte read.

Chinese dialogue must actually be present throughout the file. This is a
conservative content gate, not proof of translation quality or complete speech.
"""
    checked_video(video)
    if not isinstance(raw, bytes) or len(raw) != selection['subtitle_file']['length']:
        raise ValueError('Sidecar bytes differ from selected release tuple')
    extension = PurePosixPath(selection['subtitle_file']['path']).suffix.casefold()
    cues = parse(raw, extension)
    chinese = sum(bool(re.search(r'[\u3400-\u9fff]', cue['text'])) for cue in cues)
    proof = dict(kind='same_release', video_key=video['key'],
                 subtitle_sha256=hashlib.sha256(raw).hexdigest(), selection=selection,
                 dialogue_cues=len(cues), chinese_cues=chinese)
    proof['state'] = ('SAME_RELEASE_CHINESE_TEXT'
                      if chinese
                      else 'CHINESE_DIALOGUE_NOT_PROVEN')
    validate(video, raw, proof)
    return proof


def validate(video, raw, proof):
    """Recheck compact evidence; metadata digest is provenance, not a media hash.

Membership and uniqueness are checked by select() against the immutable
MetadataCache before IO. They must not be inferred from this compact record.
"""
    checked_video(video)
    required = {'kind', 'video_key', 'subtitle_sha256', 'selection',
                'dialogue_cues', 'chinese_cues', 'state'}
    legacy = required | {'duration', 'chinese_windows'}
    if not isinstance(proof, dict) or set(proof) not in (required, legacy) or proof['kind'] != 'same_release':
        raise ValueError('Complete release sidecar evidence required')
    selection = proof['selection']
    fields = {'video_key', 'source_info_hash', 'metadata_sha256', 'video_file', 'subtitle_file'}
    if not isinstance(selection, dict) or set(selection) != fields:
        raise ValueError('Complete exact release selection required')
    selected = video['selected']
    if (proof['video_key'] != video['key'] or selection['video_key'] != video['key']
            or selection['source_info_hash'] != selected['source_info_hash']
            or selection['video_file'] != dict(id=selected['torrent_file_id'],
                path=selected['torrent_path'], length=selected['torrent_file_bytes'])
            or proof['subtitle_sha256'] != hashlib.sha256(raw).hexdigest()):
        raise ValueError('Release timing belongs to another source or bytes')
    digest(selection['metadata_sha256'])
    file = selection['subtitle_file']
    # Reuse metadata tuple validation, including canonical paths and unique IDs.
    normalized(dict(hash=selected['source_info_hash'], title='',
                    file_stats=[selection['video_file'], file]))
    if len(raw) != file['length'] or not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError('Release subtitle length changed')
    extension = PurePosixPath(file['path']).suffix.casefold()
    cues = parse(raw, extension)
    chinese = sum(bool(re.search(r'[\u3400-\u9fff]', cue['text'])) for cue in cues)
    state = 'SAME_RELEASE_CHINESE_TEXT' if chinese else 'CHINESE_DIALOGUE_NOT_PROVEN'
    if (type(proof['dialogue_cues']) is not int or type(proof['chinese_cues']) is not int
            or proof['dialogue_cues'] != len(cues) or proof['chinese_cues'] != chinese
            or (set(proof) == required and proof['state'] != state)):
        raise ValueError('Release subtitle verdict differs from actual dialogue')
    return bool(chinese)

"""Bounded, release-specific Chinese sidecars from the selected torrent only."""

import json
import os
import re
import time
from urllib.parse import quote


MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
MATCHER_POLICY = 'declared-group-language-v1'
_EXTENSIONS = {".ass", ".ssa", ".srt"}
_SIMPLIFIED = {"chs", "sc", "jpsc", "zh-cn", "zh-hans", "简体", "简体中文", "简中"}
_TRADITIONAL = {"cht", "tc", "jptc", "zh-tw", "zh-hant", "繁体", "繁體", "繁體中文", "繁中"}
_CHINESE = {"zh", "chi", "zho", "chinese", "中文"}


def checked_context(metadata, file_identity):
    """Tie subtitle discovery to the exact torrent file already bound for playback."""
    from bobbi_core.playback_request import torrent_file_identity
    if not isinstance(metadata, dict) or set(metadata) != {'info_hash', 'file'}:
        raise ValueError('Exact torrent subtitle context required')
    selected = metadata['file']
    if not isinstance(selected, dict) or set(selected) != {'id', 'path', 'length'}:
        raise ValueError('Exact torrent file required')
    if _safe_path(selected.get('path')) is None:
        raise ValueError('Invalid torrent path')
    identity = torrent_file_identity(metadata['info_hash'], selected['id'], selected['path'], selected['length'])
    if (file_identity != identity and not (isinstance(file_identity, str)
            and re.fullmatch(r'transport:[0-9a-f]{64}\|' + re.escape(identity), file_identity))):
        raise ValueError('Subtitle torrent does not belong to playing file')
    return dict(info_hash=metadata['info_hash'].lower(), file=dict(selected))


def fetch_candidate(session, base_url, auth, metadata, row, context, deadline, cancelled, root=None, transport=None):
    """Read exact same-package text only, within the common worker's deadline."""
    from bobbi_core.subtitle_candidates import LookupStopped, inspect_text, publish, ROOT
    from bobbi_core.subtitle_io import read_http, SubtitleIOStopped
    metadata = checked_context(metadata, row['file_identity'])
    deadline = min(deadline, time.monotonic() + 8.0)

    def guard():
        if cancelled() or time.monotonic() >= deadline:
            raise LookupStopped('TORRENT_SUBTITLE_CANCELLED_OR_TIMEOUT')

    def read(url, method='GET', json_body=None):
        guard()
        try:
            raw = (transport or read_http)(url, deadline, cancelled, MAX_SUBTITLE_BYTES,
                mode='torrent', method=method, json_body=json_body, auth=auth)
        except SubtitleIOStopped as error:
            raise LookupStopped(str(error)) from error
        guard()
        return raw

    guard()
    info = json.loads(read(base_url.rstrip('/') + '/torrents', 'POST',
                           {'action': 'get', 'hash': metadata['info_hash']}))
    if not isinstance(info, dict) or str(info.get('hash', '')).lower() != metadata['info_hash']:
        raise ValueError('Torrent metadata identity changed')
    files = info.get('file_stats')
    if not isinstance(files, list) or len(files) > 4096:
        raise ValueError('Bounded torrent file metadata required')
    selected = metadata['file']
    matches = [file for file in files if isinstance(file, dict) and file.get('id') == selected['id']]
    if len(matches) != 1 or any(matches[0].get(key) != value for key, value in selected.items()):
        raise ValueError('Playing torrent file identity changed')
    choices = matching_chinese_sidecars(selected['path'], files)
    if not choices:
        raise LookupStopped('NO_EXACT_TORRENT_CHINESE_SIDECAR')
    candidate = choices[0]
    url = base_url.rstrip('/') + '/stream/' + quote(candidate['path'])
    url += '?link={}&index={}&play'.format(metadata['info_hash'], candidate['id'])
    raw = read(url)
    if len(raw) != candidate['length']:
        raise ValueError('Incomplete torrent subtitle')
    extension = os.path.splitext(candidate['path'])[1].lower()
    raw, bilingual = inspect_text(raw, extension, context['duration'])
    guard()
    return dict(file=publish(raw, extension, root or ROOT), bilingual=bilingual,
                origin='same-torrent', state='candidate')


def full_chinese_track(streams):
    """Select a declared full Chinese track, never foreign or forced signs-only."""
    candidates = []
    for stream in streams if isinstance(streams, list) else []:
        if not isinstance(stream, dict) or type(stream.get("index")) is not int or stream["index"] < 0:
            continue
        language = str(stream.get("language") or "").casefold().replace("_", "-")
        rank = _language(language)
        name = str(stream.get("name") or "").casefold()
        if rank is None or stream.get("isforced") or stream.get("forced") or re.search(r"\b(?:forced|signs|songs)\b|招牌|仅字幕牌|僅字幕牌", name):
            continue
        candidates.append((rank, bool(re.search(r"\b(?:sdh|hearing impaired)\b", name)), stream["index"]))
    return min(candidates)[2] if candidates else None


def _safe_path(path):
    if not isinstance(path, str) or not path or len(path) > 2048:
        return None
    path = path.replace("\\", "/")
    if path.startswith("/") or any(char in path for char in (":", "\x00", "?", "#")):
        return None
    if any(part in ("", ".", "..") for part in path.split("/")):
        return None
    return path


def _language(label):
    label = label.casefold().strip(" ._[]()")
    if label in _SIMPLIFIED:
        return 0
    if label in _TRADITIONAL:
        return 1
    if label in _CHINESE:
        return 2
    return None


def _sidecar_language(label, media_stem):
    """Language or a release's declared group plus language; no edition erasure.

    E.g. [GroupA&GroupB] ... .GroupA-SC.ass has the exact video stem plus
    a group already declared by that release. An arbitrary Extended/Commentary
    suffix is not language metadata and remains ineligible.
    """
    rank = _language(label)
    if rank is not None:
        return rank
    label = label.casefold().strip(' ._[]()')
    groups = re.match(r'^(?:\[[^\[\]]{1,128}\]\s*)+', media_stem)
    if not groups:
        return None
    for language in sorted(_SIMPLIFIED | _TRADITIONAL | _CHINESE, key=len, reverse=True):
        if not label.endswith(language):
            continue
        prefix = label[:-len(language)]
        if not prefix or prefix[-1] not in '._-':
            continue
        group = prefix.rstrip('._-')
        if (not re.fullmatch(r'[\w&+ -]{1,64}', group)
                or re.search(r'(?i)\b(?:extended|uncut|dubbed|commentary|forced|signs|songs|sdh)\b', group)):
            continue
        if re.search(r'(?<!\w)' + re.escape(group) + r'(?!\w)', groups[0]):
            return _language(language)
    return None


def matching_chinese_sidecars(media_path, file_stats):
    """Choose one exact release basename; ambiguity is not resolved by guessing."""
    media_path = _safe_path(media_path)
    if not media_path or not isinstance(file_stats, (list, tuple)):
        return []
    media_stem = os.path.splitext(media_path.rsplit("/", 1)[-1])[0].casefold()
    matches = []
    for candidate in file_stats[:4096]:
        if not isinstance(candidate, dict):
            continue
        path = _safe_path(candidate.get("path"))
        length = candidate.get("length")
        file_id = candidate.get("id")
        if not path or type(length) is not int or not 0 < length <= MAX_SUBTITLE_BYTES:
            continue
        if type(file_id) is not int or file_id < 1:
            continue
        stem, extension = os.path.splitext(path.rsplit("/", 1)[-1])
        if extension.casefold() not in _EXTENSIONS:
            continue
        stem = stem.casefold()
        if stem == media_stem:
            ranks = [_language(folder) for folder in path.split("/")[:-1]]
            ranks = [rank for rank in ranks if rank is not None]
            rank = min(ranks) if ranks else None
        elif stem.startswith(media_stem) and stem[len(media_stem):len(media_stem) + 1] in ". _[ (":
            rank = _sidecar_language(stem[len(media_stem):], media_stem)
        else:
            rank = None
        if rank is not None:
            matches.append((rank, candidate))
    if not matches:
        return []
    best_rank = min(rank for rank, _ in matches)
    best = [candidate for rank, candidate in matches if rank == best_rank]
    return best if len(best) == 1 else []

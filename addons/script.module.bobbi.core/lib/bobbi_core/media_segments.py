"""Bounded segment suggestions, never a player, EOF or version authority."""
import hashlib
import json
import math

KINDS = ('recap', 'intro', 'outro')
LABELS = {'recap': '建议跳过回顾', 'intro': '建议跳过片头', 'outro': '建议跳过片尾'}


def number(value, maximum=864000):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum


def normalize(raw, file_identity, duration, fetched_at):
    """Public episode timestamps remain manual suggestions for this exact file.

    A matching title/duration is not an edition proof. Overlapping or malformed
    provider ranges invalidate the whole small response rather than choosing an
    arbitrary winner. Raw public-episode cache keys do not grant applicability.
    """
    if (type(raw) is not dict or not set(raw) <= set(KINDS)
            or type(file_identity) is not str or not 0 < len(file_identity) <= 1024
            or not number(duration) or duration <= 0 or not number(fetched_at, 2**53-1)):
        return []
    try:
        if len(json.dumps(raw, allow_nan=False).encode('utf-8')) > 8192:
            return []
    except (ValueError, TypeError):
        return []
    result = []
    file_hash = hashlib.sha256(file_identity.encode('utf-8')).hexdigest()
    for kind in KINDS:
        row = raw.get(kind)
        if row is None:
            continue
        if type(row) is not dict:
            return []
        start, end = row.get('start_ms'), row.get('end_ms')
        if not number(start, 864000000) or not number(end, 864000000):
            return []
        start, end = round(start), round(end)
        if not 0 <= start < end <= round(duration * 1000) or end - start > 900000:
            return []
        for key, value in (('start_sec', start), ('end_sec', end)):
            if key in row and (not number(row[key]) or abs(row[key] * 1000 - value) > 1):
                return []
        item = dict(kind=kind, start_ms=start, end_ms=end, source='introdb',
                    evidence='public_episode', file_sha256=file_hash, fetched_at=fetched_at)
        identity = [kind, start, end, item['source'], item['evidence'], file_hash]
        item['segment_id'] = hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()
        result.append(item)
    ordered = sorted(result, key=lambda row: row['start_ms'])
    if any(left['end_ms'] > right['start_ms'] for left, right in zip(ordered, ordered[1:])):
        return []
    return ordered


def current(segments, position_ms, duration_ms, file_identity, now):
    """A suggestion is usable only within its current bounded media interval."""
    if (not number(position_ms, 864000000) or not number(duration_ms, 864000000)
            or duration_ms <= 0 or type(file_identity) is not str
            or not number(now, 2**53-1)):
        return None
    file_hash = hashlib.sha256(file_identity.encode('utf-8')).hexdigest()
    for row in segments:
        if (row['file_sha256'] == file_hash and 0 <= now - row['fetched_at'] <= 86400
                and row['start_ms'] <= position_ms < row['end_ms'] <= duration_ms):
            return row
    return None

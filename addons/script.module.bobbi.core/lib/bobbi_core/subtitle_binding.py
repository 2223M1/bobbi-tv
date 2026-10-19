"""Exact-file subtitle binding contracts, not title/filename-based sync claims.

Pure validation shared by the existing preparation owner and subtitle client.
Video identity is the verified torrent file tuple, not a URL content hash.
Nothing here fetches subtitles, controls Kodi or declares visual acceptance.
"""
import hashlib
import json
import math
from pathlib import PurePosixPath
import re

from bobbi_core.ledger import encode
from bobbi_core.preparation import MEDIA
from bobbi_core.subtitle_language import CHINESE_CODES

MAX_SUBTITLE_BYTES = 8 * 1024 * 1024


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
        raise ValueError('Exact subtitle video context required')
    rebuilt = video_identity(value['media_id'], value['release_key'], value['selected'])
    if rebuilt != value:
        raise ValueError('Subtitle video identity changed')
    return rebuilt


def prepared_video(queue, resource, source_hash):
    """Derive the BT identity only through the existing qualified cloud mapping."""
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


def same_file_timing(video, subtitle_sha256, extracted_video_key):
    """For a demuxed track/verified file-attached subtitle, not a same-name download."""
    checked_video(video)
    digest(subtitle_sha256)
    if extracted_video_key != video['key']:
        raise ValueError('Track was extracted from another file')
    return dict(kind='same_file', video_key=video['key'], subtitle_sha256=subtitle_sha256,
                reference='demuxed_track', state='SAME_FILE_TIMELINE_NOT_VISUAL_PROOF')


def content_summary(raw, extension):
    from bobbi_core.fonts import ass_font_requirements, subtitle_text
    if extension in {'.sup', '.sub'}:
        return dict(verified=False, reason='PICTURE_PARSE_NOT_INTEGRATED', fonts=[])
    text = subtitle_text(raw)
    fonts = []
    if extension in {'.ass', '.ssa'}:
        fonts = ass_font_requirements(raw)['fonts']
        cues = re.findall(r'(?im)^\s*Dialogue\s*:', text)
    else:
        if extension == '.vtt' and not text.lstrip().startswith('WEBVTT'):
            raise ValueError('WebVTT signature required')
        stamp = r'(?:\d{1,2}:)?[0-5]\d:[0-5]\d[,.]\d{3}'
        cues = re.findall(r'(?m)^\s*' + stamp + r'\s+-->\s+' + stamp + r'[^\n]*\n[^\n]+', text)
    if not 1 <= len(cues) <= 100000:
        raise ValueError('No bounded subtitle dialogue cues')
    return dict(verified=True, cue_count=len(cues), fonts=fonts)


def six_window_timing(video, subtitle_sha256, reference_sha256, duration, measurements,
                      offset=0.0, scale=1.0):
    """Validate analyzer evidence; these values are not a title-match shortcut.

    Measurements must come from the actual bound video's reference after the
    declared transform. Empty windows, outliers and non-finite data fail closed.
    """
    checked_video(video)
    digest(subtitle_sha256)
    digest(reference_sha256)
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)
    if (not finite(duration) or not 60 <= duration <= 21600 or not finite(offset)
            or abs(offset) > 600 or not finite(scale) or not 0.9 <= scale <= 1.1
            or not isinstance(measurements, list) or len(measurements) != 6):
        raise ValueError('Six bounded timing windows and finite transform required')
    windows = []
    for index, row in enumerate(measurements):
        if not isinstance(row, dict) or set(row) != {'at', 'samples', 'outliers', 'residuals', 'overlap_f1'}:
            raise ValueError('Complete timing measurements required')
        at, samples, outliers, residuals = row['at'], row['samples'], row['outliers'], row['residuals']
        if (not finite(at) or not index * duration / 6 <= at < (index + 1) * duration / 6
                or type(samples) is not int or not 5 <= samples <= 10000
                or type(outliers) is not int or not 0 <= outliers <= samples
                or not isinstance(residuals, list) or len(residuals) != samples
                or any(not finite(value) for value in residuals)
                or not finite(row['overlap_f1']) or not 0 <= row['overlap_f1'] <= 1):
            raise ValueError('Missing or malformed dispersed timing samples')
        passed = (outliers == 0 and max(abs(value) for value in residuals) <= .5
                  and row['overlap_f1'] >= .75)
        windows.append(dict(row, passed=passed))
    return dict(kind='six_windows', video_key=video['key'], subtitle_sha256=subtitle_sha256,
                reference_sha256=reference_sha256, duration=duration, offset=offset, scale=scale,
                windows=windows, state='TIMING_CORRELATION_NOT_VISUAL_PROOF' if all(w['passed'] for w in windows)
                else 'TIMING_REJECTED')


def binding(video, raw, extension, language, full_dialogue, forced, origin, timing=None,
            font_result=None, manual_intent=0):
    """Build an independently inspectable candidate; readiness is computed, not supplied."""
    checked_video(video)
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_SUBTITLE_BYTES:
        raise ValueError('Bounded subtitle bytes required')
    if extension not in {'.srt', '.ass', '.ssa', '.sup', '.sub', '.vtt'}:
        raise ValueError('Unsupported subtitle representation')
    if (not isinstance(language, str) or len(language) > 32 or type(full_dialogue) is not bool
            or type(forced) is not bool or type(manual_intent) is not int or manual_intent < 0):
        raise ValueError('Explicit track classification and manual intent required')
    if (not isinstance(origin, dict) or set(origin) != {'kind', 'id'}
            or origin['kind'] not in {'media_attachment', 'same_release_pack', 'provider', 'legacy_candidate', 'manual'}
            or not isinstance(origin['id'], str) or not re.fullmatch(r'[A-Za-z0-9_:.\-]{1,256}', origin['id'])):
        raise ValueError('Stable subtitle origin, never credentials or a signed URL')
    sha256 = hashlib.sha256(raw).hexdigest()
    content = content_summary(raw, extension)
    chinese = language.lower().replace('_', '-') in CHINESE_CODES and full_dialogue and not forced
    timing_ok = False
    if timing is not None:
        if not isinstance(timing, dict) or timing.get('video_key') != video['key'] or timing.get('subtitle_sha256') != sha256:
            raise ValueError('Timing belongs to different video/subtitle bytes')
        if timing.get('kind') == 'same_file':
            expected = same_file_timing(video, sha256, timing['video_key'])
            if timing != expected or origin['kind'] != 'media_attachment':
                raise ValueError('Same-file proof requires the actual attached track')
            timing_ok = True
        elif timing.get('kind') == 'same_release':
            from bobbi_core.subtitle_pack import validate
            if origin['kind'] != 'same_release_pack':
                raise ValueError('Release proof cannot qualify another provider')
            timing_ok = validate(video, raw, timing)
        elif timing.get('kind') == 'six_windows':
            measurements = [{k: v for k, v in row.items() if k != 'passed'} for row in timing['windows']]
            expected = six_window_timing(video, sha256, timing['reference_sha256'], timing['duration'],
                                         measurements, timing['offset'], timing['scale'])
            if timing != expected:
                raise ValueError('Timing verdict differs from its measurements')
            timing_ok = expected['state'] == 'TIMING_CORRELATION_NOT_VISUAL_PROOF'
        else:
            raise ValueError('Unsupported timing evidence')
    fonts_ok = extension not in {'.ass', '.ssa'}
    font_hashes = []
    if font_result is not None:
        if font_result.get('subtitle_sha256') != sha256:
            raise ValueError('Fonts belong to another subtitle')
        font_hashes = sorted({digest(row['sha256']) for row in font_result['selected']})
        fonts_ok = (not font_result['missing']
                    and font_result.get('status') == 'EXACT_FONTS_READY_NOT_VISUAL_PROOF'
                    and not any(row.get('synthetic_style_may_be_needed') for row in font_result['selected'])
                    and all(any(row.get('request') == wanted for row in font_result['selected'])
                            for wanted in content['fonts']))
    result = dict(schema=1, video=video, subtitle_sha256=sha256, bytes=len(raw), extension=extension,
                  language=language, full_dialogue=full_dialogue, forced=forced, origin=dict(origin),
                  timing=timing, content=content, font_hashes=font_hashes, manual_intent=manual_intent,
                  chinese_ready=chinese and timing_ok and content['verified'], fonts_ready=fonts_ok,
                  state='READY_NOT_VISUAL_PROOF' if chinese and timing_ok and fonts_ok and content['verified'] else 'CANDIDATE_NOT_READY')
    result['key'] = hashlib.sha256(encode([video['key'], sha256]).encode('utf-8')).hexdigest()
    return result


def style_reviewable(record):
    """Original ASS may render with its complete fonts while style QA stays open.

    This does NOT change binding(), fonts_ready, missing-font gates or acceptance.
    Synthetic glyph shaping is native libass behavior, not permission to claim
    exact styles, replace the family, alter ASS bytes or accept wrong timing.
    """
    fonts = record.get('font_result') or {}
    return bool(record.get('extension') in {'.ass', '.ssa'}
        and record.get('state') == 'CANDIDATE_NOT_READY' and record.get('chinese_ready') is True
        and record.get('fonts_ready') is False
        and fonts.get('subtitle_sha256') == record.get('subtitle_sha256')
        and fonts.get('status') == 'SYNTHETIC_STYLE_REQUIRED_NOT_VISUAL_PROOF'
        and fonts.get('missing') == [] and fonts.get('selected')
        and all(any(row.get('request') == wanted for row in fonts['selected'])
                for wanted in record['content']['fonts']))

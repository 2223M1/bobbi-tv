"""Exact-file subtitle binding contracts, not title/filename-based sync claims.

Pure validation shared by the existing preparation owner and subtitle client.
Video identity is the verified torrent file tuple, not a URL content hash.
Nothing here fetches subtitles, controls Kodi or declares visual acceptance.
"""
import hashlib
import re

from bobbi_core.ledger import encode
from bobbi_core.subtitle_language import CHINESE_CODES
from bobbi_core.video_context import digest, video_identity, checked_video, prepared_video

MAX_SUBTITLE_BYTES = 8 * 1024 * 1024


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
        try:
            fonts = ass_font_requirements(raw)['fonts']
        except ValueError:
            # Font introspection is optional; Kodi/libass handles the original
            # styles. The separate cue parser still validates actual ASS text.
            pass
        cues = re.findall(r'(?im)^\s*Dialogue\s*:', text)
    else:
        if extension == '.vtt' and not text.lstrip().startswith('WEBVTT'):
            raise ValueError('WebVTT signature required')
        stamp = r'(?:\d{1,2}:)?[0-5]\d:[0-5]\d[,.]\d{3}'
        cues = re.findall(r'(?m)^\s*' + stamp + r'\s+-->\s+' + stamp + r'[^\n]*\n[^\n]+', text)
    if not 1 <= len(cues) <= 100000:
        raise ValueError('No bounded subtitle dialogue cues')
    from bobbi_core.subtitle_cues import parse
    dialogue = parse(raw, extension)
    chinese = sum(bool(re.search(r'[\u3400-\u9fff]', row['text'])) for row in dialogue)
    return dict(verified=True, cue_count=len(cues), chinese_cues=chinese, fonts=fonts)


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
    # Timing metadata is historical provenance only. Keep its file identity
    # checks, but never infer translation completeness or load permission from
    # correlation windows, playback duration or an offset/scale verdict.
    if timing is not None:
        if not isinstance(timing, dict) or timing.get('video_key') != video['key'] or timing.get('subtitle_sha256') != sha256:
            raise ValueError('Timing belongs to different video/subtitle bytes')
        if timing.get('kind') == 'same_file':
            expected = same_file_timing(video, sha256, timing['video_key'])
            if timing != expected or origin['kind'] != 'media_attachment':
                raise ValueError('Same-file proof requires the actual attached track')
        elif timing.get('kind') == 'same_release':
            from bobbi_core.subtitle_pack import validate
            if origin['kind'] != 'same_release_pack':
                raise ValueError('Release proof cannot qualify another provider')
            validate(video, raw, timing)
        elif timing.get('kind') == 'six_windows':
            # Read legacy records without running or applying the old analyzer.
            # The immutable subtitle bytes themselves are always revalidated.
            pass
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
    chinese = chinese and content['verified'] and content.get('chinese_cues', 0) > 0
    result = dict(schema=2, video=video, subtitle_sha256=sha256, bytes=len(raw), extension=extension,
                  language=language, full_dialogue=full_dialogue, forced=forced, origin=dict(origin),
                  timing=timing, content=content, font_hashes=font_hashes, manual_intent=manual_intent,
                  chinese_ready=chinese, fonts_ready=fonts_ok,
                  state='READY_NOT_VISUAL_PROOF' if chinese else 'CANDIDATE_NOT_READY')
    result['key'] = hashlib.sha256(encode([video['key'], sha256]).encode('utf-8')).hexdigest()
    return result


def style_reviewable(record):
    """Original ASS may render with its complete fonts while style QA stays open.

    This does NOT change binding(), fonts_ready or content admission.
    Synthetic glyph shaping is native libass behavior, not permission to claim
    exact styles, replace the family, alter ASS bytes or accept wrong timing.
    """
    fonts = record.get('font_result') or {}
    return bool(record.get('extension') in {'.ass', '.ssa'}
        and record.get('state') in {'CANDIDATE_NOT_READY', 'READY_NOT_VISUAL_PROOF'}
        and record.get('chinese_ready') is True
        and record.get('fonts_ready') is False
        and fonts.get('subtitle_sha256') == record.get('subtitle_sha256')
        and fonts.get('status') == 'SYNTHETIC_STYLE_REQUIRED_NOT_VISUAL_PROOF'
        and fonts.get('missing') == [] and fonts.get('selected')
        and all(any(row.get('request') == wanted for row in fonts['selected'])
                for wanted in record['content']['fonts']))

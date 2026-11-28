"""Filename evidence for live-action movie/TV lists; no provider or playback IO."""
import re
from functools import lru_cache
from typing import NamedTuple


def anime_context(context):
    return (context.get('mode') == 'anime' or context.get('media_kind') in
            ('anime_movie', 'anime_series') or 16 in (context.get('genre_ids') or []))


def cinema_quality_order(context):
    return context.get('mode') in ('movie', 'movies', 'tv') and not anime_context(context)


# ASCII tag boundaries also recognize tags next to Chinese text; not substrings
# of longer codec names, groups or titles. "." is a separator, "+" meaningful.
def _tag(pattern):
    return re.compile(r'(?<![a-z0-9])(?:' + pattern + r')(?![a-z0-9])', re.I).search


_REMUX = _tag(r'(?:uhd\s*|bd\s*)?remux')
_DISC = _tag(r'blu\s*ray|bd(?:25|50|66|100)?|bdremux|bdmv|bdiso|uhdbd')
_STRUCTURE = _tag(r'bdmv|bdiso|bd(?:25|50|66|100)')
_COMPLETE = _tag(r'complete|full(?:\s*disc)?|untouched')
_DISC_RIP = _tag(r'bd\s*rip|br\s*rip')
_WEBDL = _tag(r'web\s*(?:dl|download|mux)')
_WEBRIP = _tag(r'web\s*rip')
_WEB = _tag(r'web')
_HDTV = _tag(r'hdtv|pdtv')
_DVD = _tag(r'dvd(?:[59]|rip|remux)?')
_DV = _tag(r'dv|dovi|dolby\s*vision|dvhe|dvh1|dv\s*p(?:5|7|8)(?:\s*1)?')
_HDR10 = _tag(r'hdr\s*10(?:\+|\s*plus)?')
_HDR = _tag(r'hdr|hlg|pq')
_HLG = _tag('hlg')
_SDR = _tag(r'sdr')
# In dvhe.08.06, 06 is a LEVEL, not the HDR10 base-layer compatibility ID.
_P5 = _tag(r'(?:dvhe|dvh1)\s*0?5|(?:p(?:rofile)?\s*|dv\s*)0?5')
_P7 = _tag(r'(?:dvhe|dvh1)\s*0?7|(?:p(?:rofile)?\s*|dv\s*)0?7')
_P81 = _tag(r'(?:p(?:rofile)?\s*|dv\s*)0?8\s+1')
_LOW = _tag(r'cam(?:rip)?|hdcam|hdts|telesync|telecine|screener|dvdscr|hdtsrip|tsrip')
_NO_HDR_BASE = _tag(r'(?:no|without|w/o)\s*hdr(?:\s*10)?(?:\s*fallback)?|dv\s*only')
_GENERATED = _tag(r'(?:fake|generated|converted)\s*(?:dv|dovi|hdr)|sdr\s*(?:to|2)\s*(?:dv|dovi|hdr)')
_SPLIT = re.compile(r'[\W_]+')
_SEPARATORS = re.compile(r'[._\[\](){}\-/]+')
_ISO = re.compile(r'\.iso\s*$', re.I).search


class ReleaseQuality(NamedTuple):
    origin: int
    origin_label: str
    dynamic: int
    dynamic_label: str
    low: bool


def quality_text(title, context):
    # An exact leading catalogue name is not a release tag ("Cam", "Remux").
    # Split both the alias and filename using the same separators.
    aliases = (context.get('original_title'), context.get('title'), context.get('query'))
    for alias in sorted({s for s in aliases if isinstance(s, str) and s.strip()}, key=len, reverse=True):
        bits = tuple(filter(None, _SPLIT.split(alias)))
        if bits:
            match = _prefix(bits).match(title)
            if match:
                return title[match.end():].strip()
    return title


@lru_cache(maxsize=64)
def _prefix(words):
    return re.compile(r'[\W_]*' + r'[\W_]+'.join(map(re.escape, words)) + r'(?=[\W_]|$)', re.I)


@lru_cache(maxsize=512)
def release_quality(title):
    text = _SEPARATORS.sub(' ', title).casefold()
    disc = bool(_DISC(text)) or '蓝光' in text or '藍光' in text
    remux = bool(_REMUX(text))
    # A WEB remux need not contain a Blu-ray video stream. ISO/MKV alone
    # doesn't establish a source; a Blu-ray-labelled disc image/structure does.
    if _WEBRIP(text):
        origin = (3, 'WEBRip')
    elif _WEBDL(text):
        origin = (4, 'WEB-DL')
    elif _DVD(text):
        origin = (1, 'DVD')
    elif _STRUCTURE(text) or (disc and (_ISO(title) or _COMPLETE(text))) or '原盘' in text or '原盤' in text:
        origin = (7, '原盘') if disc or 'uhd' in text else (5, '原盘·来源未标')
    elif disc and remux:
        origin = (7, '蓝光 REMUX')
    elif _DISC_RIP(text):
        origin = (3, 'BDRip/BRRip')
    elif disc:
        origin = (6, '蓝光发行')
    elif _WEB(text):
        origin = (2, 'WEB·制式未标')
    elif remux:
        origin = (5, 'REMUX·来源未标')
    elif _HDTV(text):
        origin = (2, '电视录制')
    else:
        origin = (0, '')

    dv, hdr10 = bool(_DV(text)) or '杜比视界' in text or '杜比視界' in text, bool(_HDR10(text))
    if _GENERATED(text):
        dynamic = (0, '转换动态范围·待验')
    elif _SDR(text):
        dynamic = (0, 'SDR/混合标记' if dv or hdr10 or _HDR(text) else 'SDR')
    elif dv and (_P5(text) or _NO_HDR_BASE(text) or re.search(r'w/o\s*hdr', title, re.I)):
        dynamic = (2, '杜比视界 P5·无 HDR10 回退' if _P5(text) else '杜比视界·无 HDR10 回退标记')
    elif dv and (hdr10 or _P7(text) or _P81(text)):
        dynamic = (4, '杜比视界 + HDR10 底层标记')
    elif hdr10:
        dynamic = (3, 'HDR10+' if re.search(r'hdr\s*10(?:\+|\s*plus)', text) else 'HDR10')
    elif dv:
        dynamic = (2, '杜比视界·HDR10 回退未标')
    elif _HDR(text):
        dynamic = (2, 'HLG' if _HLG(text) else 'HDR 标记')
    else:
        dynamic = (0, '')
    return ReleaseQuality(*origin, *dynamic, bool(_LOW(text)) or '枪版' in text or '槍版' in text)

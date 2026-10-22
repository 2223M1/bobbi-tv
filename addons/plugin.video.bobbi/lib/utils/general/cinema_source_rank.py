"""Local title and bound prepared-resolution preferences; never playback proof.

No network, media probing, source substitution, cache writes or autoplay here.
Scores compare candidates for the SAME title/episode already selected upstream.
Size is deliberately not a quality score (packs and multi-audio inflate it).
"""
import re

from lib.utils.general.source_resolution import source_resolution
from lib.utils.parsers.title_parser import detect_chinese_subtitle_kind


# Personal default, not a universal league table. Per-title comparisons may
# justify another group; retain all alternatives and the original release name.
ANIME_GROUPS = (("VCB-Studio", 2), ("LoliHouse", 1))


def chinese_subtitle_preference(source):
    """Explicit format/language evidence; no audio or Multi-Subs inference.

    A supplied URL is not proof of download success. Labels deliberately say
    pending verification until the selected source is actually inspected/played.
    """
    from lib.cinema.subtitle_projection import source_label
    prepared = source_label(source)
    if prepared:
        return 2, prepared
    for track in getattr(source, 'streamSubtitles', None) or []:
        if not isinstance(track, dict):
            continue
        evidence = {k: track.get(k, '') for k in ('lang', 'language', 'title', 'name')}
        if (track.get('url') or track.get('path')) and detect_chinese_subtitle_kind(stream_subtitles=[evidence]):
            return 2, '外置中文字幕·待验'
    title = str(getattr(source, 'title', '') or '')
    if re.search(r'无中文字幕|无中字|no\s+chinese\s+sub', title, re.I):
        return 0, ''
    kinds = []
    # Keep explicit language/format in the same segment, e.g. do not read
    # "English external / Chinese embedded" as external Chinese.
    for segment in re.split(r'[\[\]【】/|;；]', title):
        if not detect_chinese_subtitle_kind(segment):
            continue
        if re.search(r'外挂|外置|external|sidecar', segment, re.I):
            kinds.append(2)
        elif re.search(r'内嵌|内封|embedded|muxed|hard\s?subs?|soft\s?subs?', segment, re.I):
            kinds.append(1)
    preference = max(kinds, default=0)
    if (not preference and detect_chinese_subtitle_kind(title)
            and re.search(r'中文字幕|中英字幕|中英双语字幕|简中|繁中|简体字幕|繁体字幕|中字|(?<![a-z])ch[st](?![a-z])', title, re.I)):
        return 1, '中文字幕文件名标记·待验'
    if not preference and re.search(r'(?:-|\[|【)(?:漫迪字幕组|咩瓦译制)(?:\]|】|\.|\s|$)', title):
        return 1, '字幕组译制标记·待验'
    return preference, {2: '外置中文字幕标记·待验', 1: '内嵌中文字幕标记·待验', 0: ''}[preference]


def catalog_identity_matches(source, context):
    """Equal evidence for all catalogues, bound to this exact media request."""
    identity = getattr(source, 'catalogIdentity', None)
    if not isinstance(identity, dict) or not identity:
        return False
    requested = (context.get('ids') or {}).get('tmdb_id')
    if not requested or str(identity.get('tmdb_id')) != str(requested):
        return False
    if identity.get('mode') != context.get('mode'):
        return False
    if context.get('mode') == 'tv':
        tv = context.get('tv_data') or {}
        return all(tv.get(k) is not None and str(identity.get(k)) == str(tv[k])
                   for k in ('season', 'episode'))
    return context.get('mode') == 'movies'


def uses_anime_groups(context, source):
    anime = context.get("mode") == "anime" or context.get("media_kind") in {
        "anime_movie", "anime_series"
    } or 16 in (context.get("genre_ids") or [])
    return bool(anime and getattr(source, "type", "") == "Torrent"
                and not getattr(source, "addedToDebrid", False)
                and not getattr(source, "debridType", ""))


def _number(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _title_evidence(title, context):
    """Positive filename clues only, not TMDb/IMDb identity verification.

    Do not credit an interior substring: Call Me by Your Name is not Your Name.
    Keep unmatched/localized results visible, below matching alternatives.
    """
    if context.get('catalog_aliases'):
        from lib.cinema.candidate_titles import matches
        target = context.get('release_order') or context.get('tv_data') or {}
        season = _number(target.get('season')) if context.get('mode') == 'tv' else 0
        if matches(title, context['catalog_aliases'], context.get('mode'), release_season=season or None):
            return 2, False
    def normalized(value):
        return re.sub(r"[\W_]+", " ", str(value or "").casefold()).strip()
    aliases = {normalized(context.get(key)) for key in ("title", "original_title", "query")}
    aliases.discard("")
    if not aliases:
        return 1, False
    stripped = re.sub(r"\[[^\]]*\]", " ", title)
    segments = [normalized(segment) for segment in re.split(r"[/|()]", stripped)]
    suffix = r"(?:19\d\d|20\d\d|2160p?|1080[pi]|720p|480p|4k|blu|bluray|bd|bdrip|web|remux|hevc|s\d+(?:e\d+)?|\d+)(?:\b|\s)"
    for alias in aliases:
        for segment in segments:
            if segment == alias or (segment.startswith(alias + " ") and re.match(suffix, segment[len(alias)+1:])):
                return 2, False
    return 1, True


def source_preference(source, context=None):
    """Return an order key and short *claimed* reasons, never a URL or token."""
    context = context or {}
    title = str(getattr(source, "title", "") or "")
    text = re.sub(r"[._\[\]()\-]+", " ", title).casefold()

    def has(pattern):
        return bool(re.search(r"(?<!\w)(?:" + pattern + r")(?!\w)", text))

    resolution_facts = source_resolution(source)
    resolution = resolution_facts.resolution
    remux = has(r"remux|bdremux")
    bluray = has(r"blu\s?ray|bdrip|bdremux|bd")
    origin = 4 if remux else 3 if bluray else 2 if has(r"web\s?dl|webmux") else 1 if has(r"webrip|web") else 0
    hevc = has(r"hevc|[hx]\s?265|ma10p")
    avc = has(r"avc|[hx]\s?264|hi10p")
    tenbit = has(r"10\s?bits?|hi10p|ma10p|main\s?10")
    risks = []
    if resolution_facts.caution:
        risks.append(resolution_facts.caution)
    if has(r"trailer|teaser|sample|preview|cam|camrip|hdcam|telesync|screener") or "预告" in text:
        risks.append("预告/样片/低质标记")
    if has(r"ai\s?upscale(?:d)?|upscale(?:d)?|interpolat(?:ed|ion)|svp|60fps|120fps") or "补帧" in text:
        risks.append("放大/高帧率版本需复核")
    # G12B F9 has not passed these decode gates; do not prefer TV-native AV1
    # capability over the capabilities of the external playback device.
    if resolution == 4320 or has(r"av1|av01|vvc|h\s?266|4320p|8k") or (avc and tenbit and not hevc):
        risks.append("盒端解码风险")
    size = _number(getattr(source, "size", 0))
    if context.get("mode") in {"movies", "movie"} and 0 < size < 200 * 1024 * 1024 and not getattr(source, "isPack", False):
        risks.append("电影体积异常·需核实正片")
    bt = (getattr(source, "type", "") == "Torrent" and not getattr(source, "debridType", "")
          and not getattr(source, "addedToDebrid", False) and not getattr(source, "isCached", False))
    seeders = _number(getattr(source, "seeders", 0))
    # No seed count is not proof of failure, but cannot outrank a plausible
    # live alternative solely on filename quality. Keep it visible below.
    availability = int(not bt or seeders > 0)
    group, group_score = "", 0
    known_cloud_anime = (getattr(source, 'bobiAnimeRelease', False) is True
                         and getattr(source, 'type', '') == 'Direct'
                         and str(getattr(source, 'guid', '')).startswith('bobi:')
                         and (16 in (context.get('genre_ids') or []) or context.get('mode') == 'anime'))
    if uses_anime_groups(context, source) or known_cloud_anime:
        for name, priority in ANIME_GROUPS:
            # Only release group brackets or end-of-name tags, not film titles.
            escaped = re.escape(name)
            if re.search(r"\[[^\]]*(?<![\w-])" + escaped + r"(?![\w-])[^\]]*\]|-" + escaped + r"(?:\.(?:mkv|mp4))?$", title, re.I):
                group, group_score = name, priority
                break
    dv = has(r"dv|dovi|dolby\s?vision")
    hdr = has(r"hdr(?:10\+?)?|pq")
    # LG reports no HDR10+ support. It receives the same HDR score as HDR10.
    # DV is only a tie-break between comparable sources, never a codec/profile
    # compatibility claim. Hybrid labels do not establish a better master.
    dynamic_range = 2 if dv and not has("hybrid") else 1 if hdr or dv else 0
    chinese = int(has(r"chs|cht|sc|tc|chinese|简繁|简体|繁体") or "中字" in text)
    # Codec efficiency is not picture quality: an 8-bit HEVC re-encode must not
    # outrank an equally labelled AVC WEB-DL solely because it says HEVC.
    identity, title_unknown = _title_evidence(title, context)
    if catalog_identity_matches(source, context):
        # A validated localized filename is as eligible as a matching BT name,
        # not better just because it came from one particular catalogue.
        identity, title_unknown = 2, False
    elif getattr(source, 'catalogIdentity', None):
        risks.append('目录身份/季集不匹配')
    subtitle_score, subtitle_reason = chinese_subtitle_preference(source)
    # Preserve the explicit anime encode-group policy. Within that tier,
    # resolution wins, then Chinese evidence across ALL source transports.
    # No catalogue/platform identifier participates in quality tie-breaking.
    # Unknown titles, unavailable torrents and codec risks remain demoted.
    key = (int(not risks), min(identity, 2), availability, group_score, resolution,
           subtitle_score, origin, dynamic_range, int(tenbit), chinese, min(seeders, 1000))
    if getattr(source, 'shareFailure', '') in ('share_revoked', 'identity_changed'):
        risks.append('分享已失效 · 可手动重试' if source.shareFailure == 'share_revoked' else '文件已变化 · 可手动重试')
        key = (-1,) + key[1:]  # Failed shares cannot outrank ordinary candidates.
    parts = []
    if group:
        parts.append(group + " 优先")
    if subtitle_reason:
        parts.append(subtitle_reason)
    if resolution:
        parts.append("4K" if resolution == 2160 else str(resolution) + "p")
    if origin:
        parts.append({4: "REMUX", 3: "蓝光", 2: "WEB-DL", 1: "WEB"}[origin])
    if dv:
        parts.append("DV标记·待验")
    elif hdr:
        parts.append("HDR标记")
    if risks:
        parts = risks
    elif not availability:
        parts.append("无已知做种")
    if title_unknown:
        parts.append("片名待核对")
    if resolution_facts.measured:
        parts.append(resolution_facts.measured)
    return {"key": key, "reason": " · ".join(parts) or "信息不足", "caution": bool(risks or not availability or title_unknown)}


def rank_sources(sources, context=None):
    """Prefer exact 115 copies, then stable-sort the remaining release objects."""
    from lib.utils.general.cinema_source_dedupe import prefer_115_copies, unique_bt_releases
    sources = unique_bt_releases(prefer_115_copies(sources, context))
    return sorted(sources, key=lambda source: source_preference(source, context)["key"], reverse=True)

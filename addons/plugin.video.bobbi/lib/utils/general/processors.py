import re
from enum import Enum
from typing import Dict, List, Optional

from lib.clients.base import TorrentStream
from lib.utils.kodi.utils import get_setting, kodilog
from lib.utils.parsers.title_parser import extract_codec_hdr
from lib.utils.general.source_resolution import source_resolution


def explicit_episode_conflict(title, season, episode):
    """Reject a positively named different episode/range before broad pack rules.

    A pack marker or matching episode subtitle cannot override S01 E15-E28
    when the requested episode is S01E01. No inference from sizes/seed counts.
    """
    # Reuse the existing pack parser for season sets/ranges. Bare anime
    # episode numbers remain unknown here; file-level mapping owns that proof.
    from lib.utils.parsers.pack_parser import detect_pack_scope
    title = str(title or '')
    normalized = re.sub(r'(?i)(?<![a-z0-9])(\d{1,2})x(\d{1,3})(?!\d)',
                        r'S\1E\2', title)
    normalized = re.sub(r'(?i)\b(?:season|saison)\s*0*(\d{1,2})\s*(?:episode|ep)\s*0*(\d{1,3})\b',
                        r'S\1E\2', normalized)
    finished_seasons = re.findall(r'(?i)\[S0*(\d+)\s+Fin\]', title)
    if finished_seasons and int(season) not in {int(n) for n in finished_seasons}:
        return True
    scopes = list(re.finditer(
        r'(?i)(?<![a-z0-9])s(\d{1,2})[ ._-]*e(\d{1,3})'
        r'(?:\s*[-–~]\s*(?:s(\d{1,2})\s*)?e?(\d{1,3})(?![a-z0-9]))?'
        r'(?!\d)', normalized))
    if not scopes:
        from bobbi_core.pack_parser import scoped_episode_span
        span = scoped_episode_span(title, int(season))
        return (detect_pack_scope(title, season)['pack_type'] == 'mismatch'
                or bool(span and not span[0] <= int(episode) <= span[1]))
    for scope in scopes:
        start_season, start_episode = int(scope[1]), int(scope[2])
        end_season = int(scope[3]) if scope[3] else start_season
        end_episode = int(scope[4]) if scope[4] else start_episode
        if (start_season == end_season == int(season)
                and start_episode <= int(episode) <= end_episode):
            return False
    return True


class Quality(Enum):
    LOW = ("480p", "[B][COLOR orange]480p[/COLOR][/B]")
    MEDIUM = ("720p", "[B][COLOR orange]720p[/COLOR][/B]")
    HIGH = ("1080p", "[B][COLOR blue]1080p[/COLOR][/B]")
    ULTRA = ("2160", "[B][COLOR yellow]4k[/COLOR][/B]")
    UNKNOWN = ("N/A", "[B][COLOR yellow]N/A[/COLOR][/B]")


class SourceCategory(Enum):
    BLURAY_UHD = (
        "BluRay/UHD",
        [
            "BluRay",
            "BluRay REMUX",
            "BRRip",
            "BDRip",
            "UHDRip",
            "REMUX",
            "BLURAY",
            "DolbyVision",
            "HDR10",
        ],
    )
    WEB_HD = (
        "WEB/HD",
        [
            "WEB-DL",
            "WEB-DLRip",
            "WEBRip",
            "HDRip",
            "WEBMux",
            "AMZN",
        ],
    )
    DVD_TV_SAT = (
        "DVD/TV/SAT",
        ["DVD", "DVDRip", "HDTV", "SATRip", "TVRip", "PPVRip", "PDTV", "DVDR", "DVD-R"],
    )
    CAM_SCREENER = (
        "CAM/Screener",
        ["CAM", "CAMRip", "SCREENER", "TeleSync", "TeleCine", "SCR"],
    )
    UNKNOWN = ("Unknown", [None])


class SortField(Enum):
    SEEDS = "seeders"
    SIZE = "size"
    DATE = "publishDate"
    QUALITY = "quality"
    CACHED = "isCached"


class BaseProcessBuilder:
    def __init__(self, results: List[TorrentStream]):
        self.results: List[TorrentStream] = results

    def is_season_pack_candidate(self, title, season_num):
        from lib.utils.parsers.pack_parser import detect_pack_scope
        scope = detect_pack_scope(title, current_season=season_num)
        if scope['pack_type'] == 'mismatch':
            return False
        if scope['pack_type'] == 'episode':
            return False
        if scope['pack_type'] in ('season', 'multi_season'):
            return scope['is_pack'] and int(season_num) in scope['pack_seasons']
        # Keep historical complete/range spellings. This only permits a card;
        # never resolve an episode from the package label instead of its files.
        return bool(re.search('|'.join(self.get_season_pack_patterns(season_num)), title))

    def get_season_pack_patterns(self, season_num: int) -> list:
        season_fill = f"{int(season_num):02}"
        return [
            rf"\.S{season_num}\.",
            rf"\.S{season_fill}\.",
            rf"\sS{season_num}\s",
            rf"\sS{season_fill}\s",
            rf"\.{season_num}\.season",
            r"total\.season",
            r"season",
            r"the\.complete",
            r"complete",
            r"integrale",
            rf"Saison {season_num}" r"S(\d{2})E(\d{2})-(\d{2})",
            rf"\.season\.{season_num}\.",
            rf"\.season{season_num}\.",
            rf"\.season\.{season_fill}\.",
            rf"s1 to {season_num}",
            rf"s1 to s{season_num}",
            rf"s01 to {season_fill}",
            rf"s01 to s{season_fill}",
            rf"s1 thru {season_num}",
            rf"s1 thru s{season_num}",
            rf"s01 thru {season_fill}",
            rf"s01 thru s{season_fill}",
            rf"\[S{season_fill}\]",
            rf"\[S{season_num}\]" rf"\(S{season_fill}\)",
            rf"(?i:\[S0*{int(season_num)}\s+Fin\])",
            rf"\(S{season_num}\)",
            rf"\[Season {season_num}\]",
            rf"\[Season {season_fill}\]",
        ]

    def get_results(self) -> List[TorrentStream]:
        return self.results


class PostProcessBuilder(BaseProcessBuilder):
    def __init__(self, results: List[TorrentStream]):
        super().__init__(results)

    @staticmethod
    def _resolve_sort_field(sort_by: str) -> Optional[SortField]:
        if not sort_by:
            return None

        normalized = str(sort_by).strip()
        if not normalized or normalized.lower() == "none":
            return None

        member = SortField.__members__.get(normalized.upper())
        if member:
            return member

        for field in SortField:
            if field.value.casefold() == normalized.casefold():
                return field

        return None

    def check_season_pack(self, season: int) -> "PostProcessBuilder":
        for res in self.results:
            res.isPack = self.is_season_pack_candidate(res.title, season)
        return self

    def sort_results(self) -> "PostProcessBuilder":
        sort_by = get_setting("indexers_sort_by")
        sort_field = self._resolve_sort_field(sort_by)
        if sort_field:
            self.results = sorted(
                self.results,
                key=lambda r: getattr(r, sort_field.value, 0),
                reverse=True,
            )
        return self

    def limit_results(self) -> "PostProcessBuilder":
        limit = int(get_setting("indexers_total_results", 10))
        self.results = self.results[:limit]
        return self


class PreProcessBuilder(BaseProcessBuilder):
    def __init__(self, results: List[TorrentStream]):
        super().__init__(results)

    def remove_duplicates(self) -> "PreProcessBuilder":
        seen_values: List[str] = []
        unique_results: List[TorrentStream] = []
        retained = {}
        for res in self.results:
            key = (
                getattr(res, "infoHash", None)
                or getattr(res, "title", None)
                or getattr(res, "guid", None)
            )
            if key and key not in seen_values:
                unique_results.append(res)
                seen_values.append(key)
                retained[key] = res
            elif key and getattr(res, 'requiresCatalogEpisodeProof', False):
                retained[key].requiresCatalogEpisodeProof = True
        self.results = unique_results
        return self

    def filter_season_packs(self, season_num: int) -> List[TorrentStream]:
        return [res for res in self.results if self.is_season_pack_candidate(res.title, season_num)]

    def filter_sources(
        self, episode_name: str, episode_num: int, season_num: int, anime_aliases=None, anime_range_context=None
    ) -> "PreProcessBuilder":
        if anime_aliases:
            from bobbi_core.candidate_titles import chinese_episode_context, matches
            guarded = []
            for res in self.results:
                context = chinese_episode_context(res.title, anime_aliases)
                if context == () or (context and context[1] == int(episode_num)
                        and (context[0] == int(season_num) or (context[0] is None and int(season_num) == 1))
                        and matches(res.title, anime_aliases, 'tv', int(season_num))):
                    guarded.append(res)
            self.results = guarded
        self.results = [res for res in self.results
                        if not explicit_episode_conflict(res.title, season_num, episode_num)]

        include_season_packs = get_setting("include_season_packs")
        season_pack_results: List[TorrentStream] = []
        if include_season_packs:
            kodilog("Including season packs in filtering")
            season_pack_results = self.filter_season_packs(season_num)

        episode_fill = f"{int(episode_num):02}"
        season_fill = f"{int(season_num):02}"
        str_season = str(int(season_num))
        patterns = [
            rf"S{season_fill}E{episode_fill}",  # SXXEXX format
            rf"S{str_season}E{episode_fill}",  # SXEXX format (non-padded season)
            rf"{season_fill}x{episode_fill}",  # XXxXX format (zero-padded)
            rf"{str_season}x{episode_fill}",  # XxXX format (non-padded season)
            rf"\.S{season_fill}E{episode_fill}",  # .SXXEXX format
            rf"\sS{season_fill}E{episode_fill}\s",  # season and episode surrounded by spaces
            r"Cap\.",  # match "Cap."
        ]
        if episode_name:
            patterns.append(re.escape(episode_name))

        episode_results = [
            res for res in self.results if re.search("|".join(patterns), res.title, re.IGNORECASE)
        ]
        from bobbi_core.pack_parser import scoped_episode_span
        for res in self.results:
            span = scoped_episode_span(res.title, int(season_num))
            if span == (int(episode_num), int(episode_num)) and res not in episode_results:
                episode_results.append(res)
        # Group names are not episode evidence. Only ID-bound animation
        # aliases permit unqualified first-season numbering; every group uses
        # the same title/episode gate, before exact file resolution.
        if anime_aliases and int(season_num) == 1:
            from lib.utils.general.anime_identity import first_season_episode
            for res in self.results:
                if (res not in episode_results
                        and first_season_episode(res.title, anime_aliases, int(season_num), int(episode_num))):
                    episode_results.append(res)
            from bobbi_core.anime_range_candidates import eligible
            for res in self.results:
                if eligible(res.title, anime_range_context, int(season_num), int(episode_num)):
                    res.requiresCatalogEpisodeProof = True
                    if res not in episode_results:
                        episode_results.append(res)
        self.results = season_pack_results + episode_results
        return self

    def filter_by_quality(self) -> "PreProcessBuilder":
        quality_buckets: Dict[Quality, List[TorrentStream]] = {quality: [] for quality in Quality}
        for res in self.results:
            facts = source_resolution(res)
            quality = {480: Quality.LOW, 720: Quality.MEDIUM, 1080: Quality.HIGH,
                       2160: Quality.ULTRA}.get(facts.resolution, Quality.UNKNOWN)
            res.quality = quality.value[1]
            # Keep canonical labels: quality tabs compare their complete text.
            # Exact dimensions/cautions are exposed by the shared rank reason.
            if facts.measured and facts.resolution == 4320:
                res.quality = '[B][COLOR orange]8K[/COLOR][/B]'
            quality_buckets[quality].append(res)

        self.results = (
            quality_buckets[Quality.ULTRA]
            + quality_buckets[Quality.HIGH]
            + quality_buckets[Quality.MEDIUM]
            + quality_buckets[Quality.LOW]
        )
        if get_setting("unknown_quality_enabled", True):
            self.results += quality_buckets[Quality.UNKNOWN]
        return self

    def filter_by_source(self) -> "PreProcessBuilder":
        """
        Categorize torrents into SourceCategory buckets and filter them

        depending on Kodi settings (quality_filter group).
        """
        source_buckets: Dict[SourceCategory, List[TorrentStream]] = {

            cat: [] for cat in SourceCategory
        }

        for res in self.results:
            title = res.title.upper()
            matched_category = None
            for cat in SourceCategory:
                for keyword in cat.value[1]:
                    if keyword and keyword.upper() in title:
                        source_buckets[cat].append(res)
                        matched_category = cat
                        break
                if matched_category:
                    break
            if not matched_category:
                source_buckets[SourceCategory.UNKNOWN].append(res)

        allowed_results: List[TorrentStream] = []
        if get_setting("bluray_hd_enabled", True):
            allowed_results.extend(source_buckets[SourceCategory.BLURAY_UHD])
        if get_setting("web_hd_enabled", True):
            allowed_results.extend(source_buckets[SourceCategory.WEB_HD])
        if get_setting("dvd_tv_enabled", True):
            allowed_results.extend(source_buckets[SourceCategory.DVD_TV_SAT])
        if get_setting("cam_screener_enabled", True):
            allowed_results.extend(source_buckets[SourceCategory.CAM_SCREENER])
        if get_setting("unknown_enabled", True):
            allowed_results.extend(source_buckets[SourceCategory.UNKNOWN])

        self.results = allowed_results
        return self

    def filter_by_size(self) -> "PreProcessBuilder":
        min_size = int(get_setting("minimum_size") or 0)
        max_size = int(get_setting("maximum_size") or 100000)

        def parse_size(res: TorrentStream) -> Optional[int]:
            size_bytes = getattr(res, "size", None)
            if not size_bytes:
                return None
            try:
                return int(size_bytes) // (1024 * 1024)  # Convert bytes → MB
            except (ValueError, TypeError):
                return None

        filtered = []
        for res in self.results:
            size = parse_size(res)
            if size is None or min_size <= size <= max_size:
                filtered.append(res)

        self.results = filtered
        return self

    def extract_codec_hdr(self) -> "PreProcessBuilder":
        for res in self.results:
            codec, hdr = extract_codec_hdr(res.title)
            res.codec = codec
            res.hdr = hdr
        return self

    def filter_by_codec(self) -> "PreProcessBuilder":
        hevc_enabled = get_setting("codec_hevc_enabled", True)
        av1_enabled = get_setting("codec_av1_enabled", True)
        h264_enabled = get_setting("codec_h264_enabled", True)

        if hevc_enabled and av1_enabled and h264_enabled:
            return self

        filtered = []
        for res in self.results:
            if not res.codec:
                filtered.append(res)
                continue
            if res.codec == "HEVC" and not hevc_enabled:
                continue
            if res.codec == "AV1" and not av1_enabled:
                continue
            if res.codec == "H.264" and not h264_enabled:
                continue
            filtered.append(res)

        self.results = filtered
        return self

    def filter_by_hdr(self) -> "PreProcessBuilder":
        dv_enabled = get_setting("dolby_vision_enabled", True)
        hdr10_enabled = get_setting("hdr10_enabled", True)
        hdr_enabled = get_setting("hdr_enabled", True)

        if dv_enabled and hdr10_enabled and hdr_enabled:
            return self

        filtered = []
        for res in self.results:
            if not res.hdr:
                filtered.append(res)
                continue
            if res.hdr == "DV" and not dv_enabled:
                continue
            if res.hdr in ("HDR10", "HDR10+") and not hdr10_enabled:
                continue
            if res.hdr == "HDR" and not hdr_enabled:
                continue
            filtered.append(res)

        self.results = filtered
        return self

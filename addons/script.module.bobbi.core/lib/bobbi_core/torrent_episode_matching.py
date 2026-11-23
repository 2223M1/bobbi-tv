import re
from bobbi_core.filename_semantics import STRONG, WEAK, MULTI, parse_filename


_STRONG_PATTERNS = STRONG
_EPISODE_PATTERN, _ANIME_EPISODE_PATTERN = WEAK
_MULTI_EPISODE_SUFFIX = MULTI
_SEASON_PATTERNS = (
    re.compile(
        r"(?<![A-Za-z0-9])season[ ._-]*(?P<season>[0-9]+)(?![0-9])\b(?![ ._-]*bits?\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![A-Za-z0-9])s0*(?P<season>[0-9]+)(?![0-9])",
        re.IGNORECASE,
    ),
)


def _normalize_number(value):
    if isinstance(value, bool) or value is None:
        return None
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]+", value):
        return None
    return int(value)


def _has_strong_match(path, season, episode):
    parsed = parse_filename(path)
    matches, weak_tokens = parsed.strong, parsed.explicit
    return bool(matches) and all(
        int(match.group("season")) == season
        and int(match.group("episode")) == episode
        and not parsed.range_after(match)
        for match in matches
    ) and all(int(match.group("episode")) == episode for match in weak_tokens)


def _season_contexts(text):
    contexts = set()
    for pattern in _SEASON_PATTERNS:
        contexts.update(int(match.group("season")) for match in pattern.finditer(text))
    contexts.update(int(value) for value in re.findall(
        r'(?i)(?<!\w)([1-9]\d?)(?:st|nd|rd|th)[ ._-]+season\b', text))
    digits = dict(zip('一二三四五六七八九', range(1, 10)))
    for token in re.findall(r'第\s*([0-9一二三四五六七八九十]+)\s*[季期]', text):
        if token.isascii() and token.isdigit():
            number = int(token)
        elif token in digits:
            number = digits[token]
        elif token.count('十') == 1:
            tens, units = token.split('十')
            if (tens and tens not in digits) or (units and units not in digits):
                continue
            number = digits.get(tens, 1) * 10 + digits.get(units, 0)
        else:
            continue
        if 1 <= number <= 99:
            contexts.add(number)
    return contexts


def _release_season_contexts(torrent_title, season):
    """A declared covering range is pack scope, never per-file identity.

    Remove only a complete ascending Sx-Sy range containing the target.
    Single/conflicting season markers remain constraints. This contributes
    no season evidence: an unlabelled file still needs a trusted binding.
    """
    pattern = r'(?i)(?<![A-Za-z0-9])s0*([1-9][0-9]*)[ ._]*[-~–～][ ._]*s0*([1-9][0-9]*)(?![A-Za-z0-9])'
    def scope(match):
        start, end = int(match[1]), int(match[2])
        return ' ' if 1 <= start < end <= 100 and start <= season <= end else match[0]
    return _season_contexts(re.sub(pattern, scope, torrent_title))


def _has_matching_season_context(path, torrent_title, season):
    path_contexts = _path_season_contexts(path, season)
    title_contexts = _release_season_contexts(torrent_title, season)
    contexts = path_contexts | title_contexts
    if not contexts or season not in contexts:
        return False
    return path_contexts.issubset({season}) and title_contexts.issubset({season})


def _path_season_contexts(path, season):
    """A covering parent pack is not the selected file's season branch."""
    parts = re.split(r'[/\\]', path)
    contexts = _season_contexts(parts[-1])
    for parent in parts[:-1]:
        contexts.update(_release_season_contexts(parent, season))
    return contexts


def _has_episode_only_match(path, torrent_title, season, episode):
    if not _has_matching_season_context(path, torrent_title, season):
        return False
    # Pack folders can contain episode ranges; only the media basename selects a file.
    basename = re.split(r"[/\\]", path)[-1]
    parsed = parse_filename(basename)
    matches = parsed.explicit + parsed.anime
    return bool(matches) and all(
        int(match.group("episode")) == episode
        and not parsed.range_after(match)
        for match in matches
    )


def match_episode_file(candidate_files, season, episode, torrent_title=""):
    """Return one unambiguous candidate matching the requested TV episode."""
    season = _normalize_number(season)
    episode = _normalize_number(episode)
    if season is None or episode is None:
        return None

    torrent_title = str(torrent_title or "")
    matches = []
    for candidate in candidate_files:
        path = candidate.get("path", "") if isinstance(candidate, dict) else ""
        if not isinstance(path, str):
            continue
        contexts = _path_season_contexts(path, season) | _release_season_contexts(torrent_title, season)
        if contexts - {season}:
            continue
        strong_tokens = bool(parse_filename(path).strong)
        if strong_tokens and _has_strong_match(path, season, episode):
            matches.append((2, candidate))
        elif not strong_tokens and _has_episode_only_match(path, torrent_title, season, episode):
            matches.append((1, candidate))

    if not matches:
        return None

    best_score = max(score for score, _ in matches)
    best_matches = [candidate for score, candidate in matches if score == best_score]
    if len(best_matches) != 1:
        return None
    return best_matches[0]

import re


_STRONG_PATTERNS = (
    re.compile(
        r"(?<![A-Za-z0-9])s0*(?P<season>[0-9]+)[ ._-]*e0*(?P<episode>[0-9]+)(?![0-9])",
        re.IGNORECASE,
    ),
    re.compile(
        # The conventional 1x02 token is contiguous and has a short season
        # field. Video geometry (720x480, 1920x1080, etc.) is not episode
        # evidence. Longer explicit SnnnEnnn tokens remain supported above.
        # Do not allow separators: DD2.0.x264 is an audio/codec tag.
        r"(?<![A-Za-z0-9])(?P<season>[0-9]{1,2})x(?P<episode>[0-9]+)(?![0-9])",
        re.IGNORECASE,
    ),
)
_EPISODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:episode|ep|e)[ ._-]*(?P<episode>[0-9]+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_ANIME_EPISODE_PATTERN = re.compile(
    r"(?:\s-\s*|\[)(?P<episode>[0-9]{1,3})(?:v[0-9]+)?(?=$|[ ._\]])",
    re.IGNORECASE,
)
_MULTI_EPISODE_SUFFIX = re.compile(
    r"(?:[ ._]*e0*[0-9]+|[ ._]*[-–~～+&][ ._]*(?:"
    r"(?:s0*[0-9]+[ ._-]*)?e(?:p(?:isode)?)?[ ._-]*[0-9]+|"
    r"[0-9]+(?![A-Za-z0-9])))",
    re.IGNORECASE,
)
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
    matches = [match for pattern in _STRONG_PATTERNS for match in pattern.finditer(path)]
    weak_tokens = list(_EPISODE_PATTERN.finditer(path))
    return bool(matches) and all(
        int(match.group("season")) == season
        and int(match.group("episode")) == episode
        and not _MULTI_EPISODE_SUFFIX.match(path[match.end() :])
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
    path_contexts = _season_contexts(path)
    title_contexts = _release_season_contexts(torrent_title, season)
    contexts = path_contexts | title_contexts
    if not contexts or season not in contexts:
        return False
    return path_contexts.issubset({season}) and title_contexts.issubset({season})


def _has_episode_only_match(path, torrent_title, season, episode):
    if not _has_matching_season_context(path, torrent_title, season):
        return False
    # Pack folders can contain episode ranges; only the media basename selects a file.
    basename = re.split(r"[/\\]", path)[-1]
    matches = list(_EPISODE_PATTERN.finditer(basename))
    if not matches:
        matches = list(_ANIME_EPISODE_PATTERN.finditer(basename))
    return bool(matches) and all(
        int(match.group("episode")) == episode
        and not _MULTI_EPISODE_SUFFIX.match(basename[match.end() :])
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
        contexts = _season_contexts(path) | _release_season_contexts(torrent_title, season)
        if contexts - {season}:
            continue
        strong_tokens = any(pattern.search(path) for pattern in _STRONG_PATTERNS)
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


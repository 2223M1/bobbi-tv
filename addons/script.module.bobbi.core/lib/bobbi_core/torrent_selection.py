"""Bounded, non-interactive file selection for an explicitly selected release."""

import json
import os
import re
from bobbi_core.filename_semantics import parse_filename

from .torrent_episode_matching import (
    _ANIME_EPISODE_PATTERN,
    _EPISODE_PATTERN,
    _MULTI_EPISODE_SUFFIX,
    _STRONG_PATTERNS,
    _has_strong_match,
    _normalize_number,
    _season_contexts,
    _release_season_contexts,
    match_episode_file,
)


class ExactSelectionError(ValueError):
    def __init__(self, category):
        self.category = category
        super(ExactSelectionError, self).__init__(category)


def is_sample_or_trailer(path):
    """Recognize explicit extra markers, not title substrings or file size."""
    parts = re.split(r"[/\\]", path)
    if any(part.casefold() in {"sample", "samples", "trailer", "trailers"} for part in parts[:-1]):
        return True
    stem = os.path.splitext(parts[-1])[0]
    return bool(re.search(r"(?:^|[ ._\-\[(])(?:sample|trailer)(?:[\])])?$", stem, re.IGNORECASE))


_MOVIE_EXTRA_DIRECTORIES = frozenset({
    "sp", "sps", "extras", "bonus", "bonus features", "special features",
    "specials", "featurettes", "interviews", "pvs", "cms", "ncop", "nced",
    "映像特典", "特典", "花絮", "幕后花絮",
})
_MOVIE_EXTRA_TAG = re.compile(
    r"(?:sp|pv|cm|ncop|nced|menu|making(?:[ ._-]*of)?|featurette|interview|"
    r"event|iv|(?:special[ ._-]*)?trailer|tv[ ._-]*special)(?:[ ._-]*\d{1,3})?",
    re.IGNORECASE,
)
_NAMED_MOVIE_EXTRA_DIRECTORY = re.compile(
    r"(?P<title>.+?)[ ._-]+(?:extras|bonus(?:[ ._-]+features)?|"
    r"special[ ._-]+features|featurettes|interviews)"
    r"(?:-(?P<group>[a-z0-9][a-z0-9_.-]{0,63}))?",
    re.IGNORECASE,
)


def _named_movie_extra_directory(parts, index):
    """Require a title-bound extra folder under its explicitly dated release."""
    if index == 0:
        return False
    match = _NAMED_MOVIE_EXTRA_DIRECTORY.fullmatch(parts[index])
    if match is None:
        return False
    parent = parts[index - 1]
    group = match.group('group')
    if group and not parent.casefold().endswith('-' + group.casefold()):
        return False
    title = re.sub(r"[ ._-]+", " ", match.group('title').casefold()).strip()
    dated_parent = re.sub(r"[ ._-]+", " ", parent.casefold()).strip()
    if not title or not dated_parent.startswith(title + ' '):
        return False
    # A title ending in "Extras" is not an extra folder. The matching title
    # must end immediately before the release year in the parent directory.
    suffix = dated_parent[len(title) + 1:]
    return bool(re.match(r"[\[(]?(?:18|19|20)\d{2}[\])]?(?: |$)", suffix))


def movie_candidates(candidate_files):
    """Exclude only explicit supplemental content in a selected movie release.

    No largest-file guess: two cuts, discs or movies remain ambiguous. Do not
    apply this classification to TV episodes, where specials can be targets.
    """
    main = []
    for candidate in candidate_files:
        path = candidate["path"]
        if is_sample_or_trailer(path):
            continue
        parts = re.split(r"[/\\]", path)
        if any(re.sub(r"[ ._-]+", " ", part.casefold()).strip() in _MOVIE_EXTRA_DIRECTORIES
               for part in parts[:-1]):
            continue
        if any(_named_movie_extra_directory(parts, index) for index in range(len(parts) - 1)):
            continue
        stem = os.path.splitext(parts[-1])[0]
        # Bracketed release tags after a title, never substrings such as
        # "The Interview" or the leading fansub/group name.
        if any(re.sub(r"\[[^\[\]]*\]", "", stem[:tag.start()]).strip(" ._-")
               and _MOVIE_EXTRA_TAG.fullmatch(tag.group(1).strip())
               for tag in re.finditer(r"\[([^\[\]]+)\]", stem)):
            continue
        main.append(candidate)
    return main


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ExactSelectionError("invalid_binding")
        result[key] = value
    return result


def load_episode_binding(raw, info_hash, season, episode):
    """Validate a caller-proven mapping; never derive an episode offset here."""
    if raw in ("", None):
        return None
    if not isinstance(raw, str):
        raise ExactSelectionError("invalid_binding")
    try:
        if len(raw.encode("utf-8")) > 2048:
            raise ExactSelectionError("invalid_binding")
        binding = json.loads(raw, object_pairs_hook=_unique_json_object)
    except (UnicodeError, ValueError, RecursionError):
        raise ExactSelectionError("invalid_binding")
    required = {"media_id", "season", "episode", "absolute_episode", "source_info_hash", "provenance"}
    if not isinstance(binding, dict) or set(binding) != required:
        raise ExactSelectionError("invalid_binding")
    if (not isinstance(binding["media_id"], str)
            or not re.fullmatch(r"(?:tmdb|tvdb|anilist|anidb):[1-9][0-9]{0,11}", binding["media_id"])
            or not isinstance(binding["provenance"], str)
            or not re.fullmatch(r"[a-z][a-z0-9._:-]{0,95}", binding["provenance"])):
        raise ExactSelectionError("invalid_binding")
    for key in ("season", "episode", "absolute_episode"):
        if type(binding[key]) is not int or not 1 <= binding[key] <= 100000:
            raise ExactSelectionError("invalid_binding")
    source_hash = binding["source_info_hash"]
    if (not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", source_hash)
            or not isinstance(info_hash, str) or source_hash.lower() != info_hash.lower()
            or binding["season"] != _normalize_number(season)
            or binding["episode"] != _normalize_number(episode)):
        raise ExactSelectionError("invalid_binding")
    return binding


def _bound_episode_match(files, season, episode, absolute_episode, torrent_title, continuous=False):
    matches = []
    for candidate in files:
        path = candidate["path"]
        contexts = _season_contexts(path) | _release_season_contexts(torrent_title, season)
        # A trusted first-season identity has no offset ambiguity. Later
        # continuous numbering still needs an explicit season on the release
        # or file; a covering multi-season pack alone cannot establish it.
        needs_scope = continuous and not (season == 1 and absolute_episode == episode)
        if contexts - {season} or (needs_scope and contexts != {season}):
            continue
        if parse_filename(path).strong:
            if _has_strong_match(path, season, episode):
                matches.append((2, candidate))
            continue
        basename = re.split(r"[/\\]", path)[-1]
        parsed = parse_filename(basename)
        tokens = parsed.explicit + parsed.anime
        numbers = {int(token.group('episode')) for token in tokens}
        allowed = {episode, absolute_episode} if continuous else {absolute_episode}
        if tokens and len(numbers) == 1 and numbers.issubset(allowed) and all(
                not parsed.range_after(token) for token in tokens):
            matches.append((1, candidate))
    if not matches:
        return None
    if continuous:
        # Different local/continuous files cannot silently outrank one another.
        return matches[0][1] if len(matches) == 1 else None
    strongest = max(score for score, _ in matches)
    best = [candidate for score, candidate in matches if score == strongest]
    return best[0] if len(best) == 1 else None


def select_exact_file(candidate_files, season="", episode="", torrent_title="", info_hash="", episode_binding=""):
    """Return exactly one verified target or fail without opening a selection UI."""
    files = [candidate for candidate in candidate_files if not is_sample_or_trailer(candidate["path"])]
    binding = load_episode_binding(episode_binding, info_hash, season, episode)
    if not files:
        raise ExactSelectionError("no_candidate")
    if not (season or episode):
        files = movie_candidates(files)
        if not files:
            raise ExactSelectionError("no_candidate")
        if binding is not None or len(files) != 1:
            raise ExactSelectionError("target_unresolved")
        return files[0]
    normalized_season, normalized_episode = _normalize_number(season), _normalize_number(episode)
    if normalized_season is None or normalized_episode is None:
        raise ExactSelectionError("target_unresolved")
    if binding is not None:
        chosen = _bound_episode_match(files, normalized_season, normalized_episode,
                                      binding["absolute_episode"], str(torrent_title or ""),
                                      continuous=binding['provenance'].startswith('tmdb-continuous-order:'))
    else:
        chosen = match_episode_file(files, season, episode, torrent_title=torrent_title)
    if chosen is None:
        raise ExactSelectionError("target_unresolved")
    return chosen


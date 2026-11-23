"""Episode-bound release family, used only after exact-file/work validation.

Do not erase every number in a filename: 86, Part 2, v2, resolution and audio
specifications remain part of the release. The result is NOT identity proof.
"""
import re

from bobbi_core.release_names import family, specifications
from bobbi_core.filename_semantics import STRONG, WEAK, MULTI, parse_filename


def bound_family(name, season, episode, absolute_episode=None):
    if (not isinstance(name, str) or not 1 <= len(name) <= 4096 or '/' in name or '\\' in name
            or any(type(v) is not int or not 1 <= v <= 100000 for v in (season, episode))):
        raise ValueError('A basename and previously verified episode identity are required')
    if absolute_episode is not None and (type(absolute_episode) is not int or not 1 <= absolute_episode <= 100000):
        raise ValueError('Malformed previously verified absolute episode')
    parsed = parse_filename(name)
    strong, matches = parsed.strong, parsed.markers
    wanted = episode if strong or absolute_episode is None else absolute_episode
    if (not matches or any(int(m['episode']) != wanted or parsed.range_after(m) for m in matches)
            or any(int(m['season']) != season for m in strong)):
        raise ValueError('Release episode markers are missing or conflict with selected file')
    # The leading [group] cannot be interpreted as an episode. Explicit weak
    # markers conflicting with a strong marker also invalidate the family.
    if strong:
        weak = parsed.explicit
        if any(int(m['episode']) != episode for m in weak):
            raise ValueError('Conflicting secondary episode marker')
    spans = sorted({(m.start(), m.end(), m.groupdict().get('revision') or '') for m in matches}, reverse=True)
    end = len(name)
    for start, stop, revision in spans:
        if stop > end:
            raise ValueError('Overlapping episode markers')
        # Feed a fixed syntactic marker to the legacy normalizer, which folds
        # case first and then inserts uppercase EP. This is only a fingerprint
        # token, never a media/episode identity or a selector input. Keeping its
        # exact bytes avoids invalidating already published version keys.
        name = name[:start] + ' S00E00 ' + revision + name[stop:]
        end = start
    return family(name)


def same_bound_release(current, following, season, episode, current_absolute=None, next_absolute=None):
    return (bound_family(current, season, episode, current_absolute)
            == bound_family(following, season, episode + 1, next_absolute)
            and specifications(current) == specifications(following))


def audio_capsule_candidate(name):
    """Normalize one explicit codec capsule for preparation, NOT autoplay.

    Preserve group, revision, video codec and primary audio label. Only suffix
    audio labels in an unambiguous video/audio bracket may differ; arbitrary
    words elsewhere in the title are never erased. Demux proof is still needed.
    """
    pattern = re.compile(r'\[(?P<video>x26[45]|h26[45]|hevc|avc)_(?P<main>flac|aac|ac3|eac3|dts|truehd|opus)'
                         r'(?P<extra>(?:_(?:flac|aac|ac3|eac3|dts|truehd|opus))*)\]', re.I)
    matches = list(pattern.finditer(name))
    if len(matches) != 1:
        raise ValueError('One explicit video/audio capsule required')
    match = matches[0]
    return name[:match.start()] + '[{}_{}]'.format(match['video'], match['main']) + name[match.end():]

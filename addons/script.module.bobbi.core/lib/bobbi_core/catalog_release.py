"""Shared edition check for independently work/episode-bound catalog files.

This is never a title search, readiness assertion or substitute for a selected
file locator. Callers must establish catalog identity and directory membership
first. Multiple encodes of an episode remain separate candidates.
"""
import re

from bobbi_core.episode_revision import continuation_family
from bobbi_core.release_names import specifications


EPISODE = re.compile(r'(?i)(?<![a-z0-9])s(\d{1,2})[ ._-]*e(\d{1,3})(?=v[1-9]\d*(?:[ ._\]\)]|$)|[^a-z0-9]|$)')
QUALITY = re.compile(r'(?i)(?<![a-z0-9])(?:2160|1080|720|576|480)[pi](?![a-z0-9])')
EXTENSION = re.compile(r'(?i)\.(mkv|mp4|m4v|avi|webm|ts)$')


def release_envelope(name, season, episode):
    """Edition fingerprint, including anime numbering and episode-local repair.

    The longstanding S/E grammar drops only episode-title prose before resolution.
    Other explicit episode grammars reuse the BT continuation rules, preserving
    group, codec, quality, edition and standalone revision tokens. Containers remain
    distinct. An episode-local 09v2 can continue to 10, but standalone v2 cannot.
    """
    if (not isinstance(name, str) or len(name) > 2048 or re.search(r'[\x00-\x1f/\\]', name)
            or type(season) is not int or type(episode) is not int or min(season, episode) < 1):
        return None
    extension = EXTENSION.search(name)
    if not extension or not QUALITY.search(name):
        return None
    markers = list(EPISODE.finditer(name))
    if markers:
        if len(markers) != 1:
            return None
        marker = markers[0]
        if (int(marker[1]), int(marker[2])) != (season, episode):
            return None
        tail = name[marker.end():]
        tail = re.sub(r'(?i)^v[1-9]\d*(?=[ ._\]\)]|$)', '', tail, count=1)
        if re.match(r'(?i)\s*(?:e\d|[-~–]\s*(?:s\d+\s*)?e?\d)', tail):
            return None
        quality = QUALITY.search(tail)
        if not quality:
            return None
        prose = tail[:quality.start()]
        if re.search(r'(?i)\[|\]|\(|\)|\b(?:v\d+|repack|proper|extended|uncut|dubbed)\b', prose):
            return None
        prefix = re.sub(r'[\W_]+', ' ', name[:marker.start()].casefold()).strip()
        suffix = tail[quality.start():].casefold()
        return (prefix, season, suffix) if prefix else None
    try:
        return ('episode-bound', season, continuation_family(name, season, episode),
                specifications(name), extension[1].casefold())
    except (ValueError, TypeError):
        return None

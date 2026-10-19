"""Bounded unscoped anime-range *candidate* grammar; never season/file proof.

Catalogue identity, genre, original S1 and a regular 1:1 cached mapping are
prerequisites. Every admitted card also requires a catalogue-bearing playback
handoff. Release groups, ranges and packaging labels do not grant identity.
"""
import re
import unicodedata

from .candidate_titles import normalized
from .episode_identity import catalog_identity, load_mappings, mapped_episode

_OPEN = {'[': ']', '【': '】', '(': ')'}
_SPECIAL = re.compile(
    r'(?i)(?<![a-z0-9])(?:ova|oav|oad|ona|sp|specials?|movie|film|ncop|nced|pv|cm)'
    r'(?:[ ._-]*[0-9]+)?(?![a-z0-9])|劇場版|剧场版|总集篇|總集篇|総集編|番外|特别篇|特別篇')
_GROUP = re.compile(r'(?i)字幕[组組社]|工作室|fansubs?|subbers?|raws?|studio|team|group|encode(?:rs?)?')
_RANGE = re.compile(
    r'^(?:全\s*)?([0-9]{1,3})\s*[-–~至]\s*([0-9]{1,3})\s*'
    r'(?:集|话|話)?\s*(?:合集|全集|全)?\s*(?:\+\s*(?:特典|映像特典))?$')
_TECH = re.compile(
    r'(?i)(?:(?:2160|1080|720|576|480)[pi]|[48]k|\d{3,4}x\d{3,4}|'
    r'web(?:-?dl|rip)?|blu-?ray|bd(?:rip)?|h\.?26[45]|x26[45]|'
    r'(?:hevc|avc)(?:-(?:8|10|12)bits?)?|av1|aac|flac|opus|ac3|eac3|'
    r'dts|truehd|mp3|pcm|[1-8]\.[01]|(?:8|10|12)-?bits?|ma10p|hi10p|'
    r'hdr(?:10\+?)?|dv|dovi|chs|cht|sc|tc|gb|gbk|big5|zh(?:-cn|-tw|-hk)?|'
    r'jpn|jp|eng|en|chinese|japanese|english|dual-audio|multi-audio|'
    r'mp4|mkv|avi|ts|m2ts|fin|end|[a-f0-9]{8})')
_SUBTITLE = re.compile(
    r'(?:(?:简|簡|繁|简繁|簡繁)(?:体|體)?)?'
    r'(?:(?:内封|內封|内嵌|內嵌|外挂|外掛))?'
    r'(?:(?:中英日|中日|中英|中文|日文|中日文|中英日文|中日双语|中日雙語|中英双语|中英雙語|双语|雙語))?'
    r'(?:(?:内封|內封|内嵌|內嵌|外挂|外掛))?(?:字?幕)?')


def context(details, tmdb_id, catalog_season, release_season, episode, mappings=None):
    """Construct only from exact-ID details and an existing regular S1 map."""
    if (type(catalog_season) is not int or catalog_season != 1
            or type(release_season) is not int or release_season != 1
            or type(episode) is not int or not 1 <= episode <= 999
            or not isinstance(details, dict)
            or not isinstance(details.get('genres'), list)
            or not any(isinstance(row, dict) and row.get('id') == 16 for row in details['genres'])):
        return None
    catalog = catalog_identity(details, tmdb_id)
    if catalog is None or type(catalog.get('year')) is not int:
        return None
    mappings = load_mappings() if mappings is None else mappings
    targets = mappings.get('tmdb_show:{}:s1'.format(catalog['tmdb_id']), {}) if isinstance(mappings, dict) else {}
    if (not isinstance(targets, dict) or len(targets) != 1
            or mapped_episode(mappings, catalog['tmdb_id'], 1, episode) != episode):
        return None
    return dict(catalog=catalog, catalog_season=1, release_season=1, episode=episode, genre_id=16)


def _valid_context(value, season, episode):
    if (not isinstance(value, dict) or type(season) is not int or season != 1
            or type(episode) is not int or not 1 <= episode <= 999
            or value.get('catalog_season') != 1 or value.get('release_season') != 1
            or value.get('episode') != episode or value.get('genre_id') != 16):
        return False
    catalog = value.get('catalog')
    return bool(isinstance(catalog, dict) and type(catalog.get('tmdb_id')) is int
        and catalog['tmdb_id'] > 0 and type(catalog.get('year')) is int and 1000 <= catalog['year'] <= 2999
        and isinstance(catalog.get('aliases'), list) and 1 <= len(catalog['aliases']) <= 16
        and all(isinstance(alias, str) and 2 <= len(alias) <= 128 and alias.strip() == alias for alias in catalog['aliases']))


def _tokens(text):
    """Top-level blocks plus text; nesting/closers must balance completely."""
    result, index = [], 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text[index] in _OPEN:
            start, stack = index, []
            while index < len(text):
                char = text[index]
                if char in _OPEN:
                    stack.append(_OPEN[char])
                elif char in _OPEN.values():
                    if not stack or stack.pop() != char:
                        return None
                    if not stack:
                        result.append(('block', text[start + 1:index].strip(), text[start]))
                        index += 1
                        break
                index += 1
            else:
                return None
        elif text[index] in _OPEN.values():
            return None
        else:
            start = index
            while index < len(text) and text[index] not in ''.join(_OPEN) + ''.join(_OPEN.values()):
                index += 1
            result.append(('text', text[start:index].strip(), ''))
    return result


def _bound_title(value, aliases, year):
    trusted = {normalized(alias).replace(' ', '') for alias in aliases}
    trusted.discard('')
    def complete(text):
        if not re.fullmatch(r"[\w\s./|:_’'()\-]+", text):
            return False
        text = normalized(text).replace(' ', '')
        if not text:
            return False
        positions = {0}
        for _ in range(4):
            positions = {start + len(alias) for start in positions for alias in trusted if text.startswith(alias, start)}
            if len(text) in positions:
                return True
        return False
    if complete(value):
        return True
    dated = re.fullmatch(r'(.+?)[ ._]+\(?((?:19|20)[0-9]{2})\)?', value)
    return bool(dated and int(dated[2]) == year and complete(dated[1]))


def _technical(value, year, allow_bonus=False):
    if not value or _SPECIAL.search(value):
        return False
    if allow_bonus and value in ('特典', '映像特典', '+特典', '+映像特典', '全', '合集', '全集'):
        return True
    if value in ('★高清收藏版', '高清收藏版'):
        return True
    if re.fullmatch(r'(?:19|20)[0-9]{2}', value):
        return int(value) == year
    # A dot is a separator except inside a recognized codec/channel token.
    # Lex the full token first; never turn h.265, 5.1 or an unknown 01.5
    # episode suffix into apparently harmless independent numbers.
    tokens = []
    for segment in re.split(r'[\s_/&+]+', value):
        while segment:
            match = _TECH.match(segment)
            if match and (match.end() == len(segment) or segment[match.end()] == '.'):
                tokens.append(match[0])
                segment = segment[match.end():].lstrip('.')
            else:
                tokens.append(segment)
                break
    return bool(tokens and all(_TECH.fullmatch(token) or (token and _SUBTITLE.fullmatch(token))
        or re.fullmatch(r'(?i)BD-(?:MP4|MKV)', token) for token in tokens))


def eligible(title, value, season, episode):
    """True means candidate only; caller must mark restricted playback proof."""
    if (not _valid_context(value, season, episode) or not isinstance(title, str)
            or not 1 <= len(title) <= 2048):
        return False
    tokens = _tokens(unicodedata.normalize('NFKC', title).strip())
    if not tokens:
        return False
    ranges = [(index, _RANGE.fullmatch(token[1])) for index, token in enumerate(tokens) if token[0] == 'block']
    ranges = [(index, match) for index, match in ranges if match]
    if len(ranges) != 1:
        return False
    index, match = ranges[0]
    start, end = int(match[1]), int(match[2])
    if not 1 <= start <= episode <= end <= 999:
        return False
    catalog = value['catalog']
    aliases, year = catalog['aliases'], catalog['year']
    prefix = list(tokens[:index])
    if prefix and not _bound_title(prefix[0][1], aliases, year):
        kind, group, opening = prefix.pop(0)
        if (kind != 'block' or not 1 <= len(group) <= 100 or _SPECIAL.search(group)
                or (opening == '【' and not _GROUP.search(group))
                or re.search(r'(?i)(?:\bpart\b|第.*[部季期]|[0-9]\s*\+\s*[0-9]|特典|[0-9]{4})', group)
                or _technical(group, year)):
            return False
    title_count = 0
    for _, text, _ in prefix:
        if re.fullmatch(r'(?:19|20)[0-9]{2}', text):
            if int(text) != year:
                return False
        elif _bound_title(text, aliases, year):
            title_count += 1
        else:
            return False
    return bool(1 <= title_count <= 4 and all(_technical(token[1], year, allow_bonus=True) for token in tokens[index + 1:]))


def check_file_tail(path, year):
    """Additional restrictions AFTER the original strict basename work check.

    A correct filename under an arbitrary differently named directory remains
    a correct filename. Explicit bonus directory components do not. Work names
    containing Special/Movie are already consumed before tail classification.
    """
    if not isinstance(path, str) or not path or len(path) > 8192 or type(year) is not int:
        raise ValueError('Bounded actual filename and catalogue year required')
    parts = re.split(r'[/\\]', path)
    extras = {'sp', 'special', 'specials', 'extras', 'bonus', 'bonus features', 'special features',
              'ncop', 'nced', 'pv', 'pvs', 'cm', 'cms', 'ova', 'oad', 'oav', 'ona', '特典', '映像特典', '番外'}
    bonus_directory = '(?:' + '|'.join(re.escape(tag) for tag in sorted(extras)) + r')(?:[ ._-]*[0-9]{1,6})?'
    if any(re.fullmatch(bonus_directory, unicodedata.normalize('NFKC', part).casefold().strip())
           for part in parts[:-1]):
        raise ValueError('Bonus directory cannot supply a regular range episode')
    name = re.sub(r'(?i)\.(?:mkv|mp4|m4v|avi|ts|m2ts)$', '', parts[-1])
    name = re.sub(r'^\[[^\[\]]{1,80}\][ ._-]*', '', name, count=1)
    marker = re.search(r'(?i)(?<![a-z0-9])(?:s\d+[ ._-]*e\d+|\d+[ ._-]*x[ ._-]*\d+)(?:v\d+)?(?![a-z0-9])|'
                       r'(?<![a-z0-9])(?:episode|ep|e)[ ._-]*\d+(?:v\d+)?(?![a-z0-9])|'
                       r'\s-\s*\d{1,3}(?:v\d+)?(?=$|[ ._\[])|\[\d{1,3}(?:v\d+)?\]', name)
    if marker is None:
        raise ValueError('Actual regular episode marker required')
    tail = name[marker.end():].strip(' ._-')
    tokens = _tokens(unicodedata.normalize('NFKC', tail))
    if tokens is None or any(not _technical(token[1], year, allow_bonus=False) for token in tokens):
        raise ValueError('Unknown, conflicting-year or bonus episode suffix')

"""Explicit movie-year contradictions, not a new work/readiness authority.

The producer builds a per-request handoff only from same-ID process evidence.
The consumer checks that bounded handoff against its existing owner selection.
It is not accepted as MovieYears by other APIs or as proof against a malicious
local client. Unknown names/evidence remain unknown, never verified matches.
"""
import json
import re
import unicodedata

from .movie_years import PROVENANCE, accepted_years

MAX_BINDING_BYTES = 8192
YEAR = re.compile(r'(?<![^\W_])(?:18|19|20)\d{2}(?![^\W_])')
SELECTION = re.compile(r'(?:bt:[0-9a-f]{40}|transport:[0-9a-f]{64})')


def _aliases(values):
    if not isinstance(values, (list, tuple)):
        return []
    return list(dict.fromkeys(value.strip() for value in values
        if isinstance(value, str) and 1 <= len(value.strip()) <= 512))[:32]


def declared_years(name, aliases):
    """Protect complete catalog title tokens without erasing bilingual labels."""
    if not isinstance(name, str) or not name or len(name) > 4096:
        return set()
    text = unicodedata.normalize('NFKC', name).casefold()
    title_spans = []
    for segment in re.finditer(r'[^/|\\\r\n]+', text):
        for alias in _aliases(aliases):
            words = re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', alias).casefold())
            if not words:
                continue
            pattern = r'(?<![^\W_])' + r'[\W_]+'.join(re.escape(word) for word in words) + r'(?![^\W_])'
            match = re.search(pattern, segment[0])
            if match is None:
                continue
            prefix = segment[0][:match.start()]
            for _ in range(3):
                prefix = re.sub(r'^\s*(?:\[[^\[\]]{1,100}\]|【[^【】]{1,100}】)[ ._-]*', '', prefix, count=1)
            if not all(word.isdecimal() for word in words) or not prefix.strip(' ._-(['):
                # Protect the title occurrence, never every repeated numeric
                # token: 1917.1917 still declares the second 1917 as its year.
                # A full named title can follow subtitle/release descriptors;
                # a numeric-only alias cannot erase an interior year field.
                title_spans.append((segment.start() + match.start(), segment.start() + match.end()))
    return {int(match[0]) for match in YEAR.finditer(text)
            if not any(start <= match.start() and match.end() <= end for start, end in title_spans)}


def year_status(names, aliases, years):
    """Only a single explicit release year per name can establish a conflict."""
    if not years:
        return dict(status='unknown', reason='catalog_year_unavailable')
    observed = False
    ambiguous = False
    for name in names:
        declared = declared_years(name, aliases)
        if len(declared) == 1:
            observed = True
            if not declared.issubset(years):
                return dict(status='conflict', reason='explicit_movie_year_mismatch')
        elif declared:
            ambiguous = True
    if ambiguous:
        return dict(status='unknown', reason='multiple_release_years')
    return (dict(status='compatible', reason='explicit_year_compatible') if observed else
            dict(status='unknown', reason='release_year_absent'))


def evidence_status(names, aliases, evidence, tmdb_id):
    return year_status(names, aliases, accepted_years(evidence, tmdb_id, None))


def make_binding(evidence, tmdb_id, aliases, request_id, selection_identity):
    years = accepted_years(evidence, tmdb_id, None)
    if not years:
        return None
    if (not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id)
            or not isinstance(selection_identity, str) or not SELECTION.fullmatch(selection_identity)):
        raise ValueError('Movie handoff requires the current request and source')
    names = _aliases(aliases)
    if not names:
        return None
    value = dict(version=1, request_id=request_id, selection_identity=selection_identity,
        tmdb_id=tmdb_id, aliases=names, primary_year=evidence.primary_year,
        years=list(years), provenance=PROVENANCE)
    # Keep the canonical/original aliases first; the optional tail is bounded.
    while len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > MAX_BINDING_BYTES:
        value['aliases'].pop()
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate movie handoff field')
        result[key] = value
    return result


def load_binding(raw, request_id, selection_identity):
    if raw is None or raw == '':
        return None
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_BINDING_BYTES:
        raise ValueError('Bounded movie handoff required')
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise ValueError('Malformed movie handoff') from None
    required = {'version', 'request_id', 'selection_identity', 'tmdb_id',
                'aliases', 'primary_year', 'years', 'provenance'}
    if (type(value) is not dict or set(value) != required
            or type(value['version']) is not int or value['version'] != 1
            or not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id)
            or value['request_id'] != request_id
            or not isinstance(selection_identity, str) or not SELECTION.fullmatch(selection_identity)
            or value['selection_identity'] != selection_identity
            or type(value['tmdb_id']) is not int or not 0 < value['tmdb_id'] <= 999999999999
            or type(value['primary_year']) is not int or not 1000 <= value['primary_year'] <= 9999
            or value['provenance'] != PROVENANCE
            or type(value['aliases']) is not list or not value['aliases']
            or value['aliases'] != _aliases(value['aliases'])):
        raise ValueError('Movie handoff does not match the request')
    years = value['years']
    if (type(years) is not list or not 1 <= len(years) <= 4
            or any(type(year) is not int or not 1000 <= year <= value['primary_year'] for year in years)
            or years != sorted(set(years)) or value['primary_year'] not in years):
        raise ValueError('Invalid movie handoff years')
    return value


def binding_status(binding, names):
    if binding is None:
        return dict(status='unknown', reason='catalog_year_unavailable')
    return year_status(names, binding['aliases'], tuple(binding['years']))


# This deliberately small file-only grammar is not the search-card grammar.
# Expanding search admission must not silently expand a playback refusal rule.
_FILE_TECHNICAL = re.compile(
    r'(?i)(?:(?:2160|1080|720|576|480)[pi]|[48]k|\d{3,4}x\d{3,4}|'
    r'web(?:-?dl|rip)?|blu-?ray|bdrip|bdremux|remux|h\.?26[45]|x26[45]|'
    r'(?:hevc|avc)(?:-(?:8|10|12)bits?)?|av1|aac|flac|opus|ac3|eac3|'
    r'dts|truehd|mp3|pcm|[1-8]\.[01]|(?:8|10|12)-?bits?|ma10p|hi10p|'
    r'hdr(?:10\+?)?|dv|dovi|chs|cht|sc|tc|gb|gbk|big5|zh(?:-cn|-tw|-hk)?|'
    r'简(?:体|中|繁)?|簡(?:體|中|繁)?|繁(?:体|體|中|简|簡)?|'
    r'(?:简|簡|繁|简繁|簡繁)?(?:体|體)?(?:中(?:文|日)?|日)?'
    r'(?:字?幕|(?:内封|內封|内嵌|內嵌|外挂|外掛)(?:字?幕)?)|[a-f0-9]{8})')


def _file_technical_tail(text):
    while text:
        text = text.strip()
        if not text:
            return True
        if text[0] in '[【(':
            closing = {'[': ']', '【': '】', '(': ')'}[text[0]]
            end = text.find(closing, 1)
            if end < 0:
                return False
            content, text = text[1:end], text[end + 1:]
        else:
            marker = re.search(r'[\[【(]', text)
            end = marker.start() if marker else len(text)
            content, text = text[:end], text[end:]
        tokens = [token for token in re.split(r'[\s_&+]+', content.strip()) if token]
        if not tokens or any(not _FILE_TECHNICAL.fullmatch(token) for token in tokens):
            return False
    return True


def file_identity_status(binding, basename):
    """Refuse only a bound movie's fully named, yearless, bare-numbered file.

    Caller must validate the current owner/source/file and load_binding first.
    This is never positive movie identity or TV classification. Parent names,
    card years and another file cannot supply evidence about this basename.
    """
    unknown = dict(status='unknown', reason='numbered_movie_identity_not_established')
    if (binding is None or not binding.get('years') or not isinstance(basename, str)
            or not basename or len(basename) > 4096 or re.search(r'[/\\\r\n]', basename)):
        return unknown
    aliases = _aliases(binding.get('aliases'))
    if not aliases or declared_years(basename, aliases):
        return unknown
    text = unicodedata.normalize('NFKC', basename).casefold().strip()
    text = re.sub(r'\.(?:mkv|mp4|avi|ts|m2ts)$', '', text)
    patterns = []
    for alias in aliases:
        words = re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', alias).casefold())
        if words:
            title = r'[\W_]+'.join(re.escape(word) for word in words)
            patterns.append(r'(?:' + title + r'|\[' + title + r'\]|【' + title + r'】)(?![^\W_])')
    # Try the title itself first; a trusted bracketed title is not a group.
    for attempt in range(2):
        ends = [match.end() for pattern in patterns if (match := re.match(pattern, text))]
        if ends:
            # The most complete trusted title wins: "Film 2" is not "Film" + 2.
            suffix = text[max(ends):]
            number = re.match(r'^\s*(?:-\s*[0-9]{1,3}|\[[0-9]{1,3}\])(?=$|[\s.\[【(])', suffix)
            if number and _file_technical_tail(suffix[number.end():]):
                return dict(status='identity_insufficient', reason='yearless_bare_number_after_movie_title')
            return unknown
        if attempt == 0:
            group = re.match(r'^(?:\[[^\[\]]{1,100}\]|【[^【】]{1,100}】)\s*', text)
            if group:
                text = text[group.end():]
                continue
        break
    return unknown

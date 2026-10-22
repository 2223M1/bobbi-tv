"""Shared catalogue work/season/type boundary for TV cards and actual files.

Catalogue aliases are supplied by the ID-checked producer. Release text only
constrains that identity; it never supplies a new alias or a season mapping.
Unknown semantic words survive the closed metadata grammar.
"""
import re
import unicodedata

from .catalog_identity import normalized
from .filename_semantics import parse_filename
from .pack_parser import detect_pack_scope, release_season_markers
from .torrent_episode_matching import _release_season_contexts


_BONUS = re.compile(r'(?i)(?<![a-z0-9])(?:ova|oav|oad|ona|sp|specials?|extras?|bonus|'
    r'movie|film|ncop|nced|pv|cm)(?![a-z0-9])|剧场版|劇場版|特别篇|特別篇|番外|特典')
_RANGE = re.compile(r'(?i)(?<![a-z0-9])s0*([1-9]\d?)[ ._]*[-~–～][ ._]*s0*([1-9]\d?)(?![a-z0-9])')
_EP_RANGE = re.compile(r'(?<!\d)(?:全\s*)?\d{1,3}\s*[-~–～]\s*\d{1,3}(?:\s*[话話集])?(?!\d)')
_PACK = re.compile(r'(?i)\b(?:complete(?:\s+(?:tv\s+)?series|\s+collection)?|batch|collection|'
    r'full\s+series|all\s+seasons)\b|合集|全集|全')
_VIDEO_EXTENSION = re.compile(r'(?i)\.(?:3g2|3gp|asf|avc|avi|bivx|divx|dv|dvr-ms|evo|f4v|'
    r'fli|flv|h264|m2t|m2ts|m2v|m4v|mk3d|mkv|mov|mp4|mpeg|mpg|mts|nuv|ogm|ogv|pva|qt|'
    r'rcv|rec|rmvb|svq3|tp|trp|ts|ty|vc1|vdr|viv|vob|vp3|webm|wmv|xvid)$')


def _consume_aliases(text, aliases):
    # Work names are consumed before interpreting words such as Movie/Special.
    # Remaining text must still be metadata: a matching bilingual segment does
    # not erase another segment's sequel/arc name.
    # Work-level alternative titles sometimes also name a particular season
    # or special. When a complete base alias is present, do not erase that
    # additional scope merely because the longer string is also in TMDb.
    # A canonical name containing "Special" with no shorter base is unchanged.
    names = {normalized(a) for a in aliases if isinstance(a, str)} - {''}
    found = False
    for alias in sorted(names, key=len, reverse=True):
        qualified = False
        for base in names:
            if len(base) >= len(alias) or not alias.startswith(base):
                continue
            suffix = alias[len(base):]
            if not (suffix.startswith(' ') or (not base[-1].isascii() and not suffix[0].isascii())):
                continue
            if (_BONUS.search(suffix) or release_season_markers(suffix)
                    or re.search(r'(?i)\bseason\b|[季期]', suffix)):
                qualified = True
                break
        if qualified:
            continue
        pattern = r'(?<![a-z0-9])' + r'[\W_]*'.join(re.escape(t) for t in alias.split()) + r'(?![a-z0-9])'
        text, count = re.subn(pattern, ' ', text, flags=re.I)
        found = found or bool(count)
    return text, found


def release_scope(title, aliases, season, year=None, allow_pack=True, filename=False):
    """Return matched/conflict/unknown without inventing a release identity."""
    from .anime_range_candidates import _technical, _tokens
    if (not isinstance(title, str) or not 0 < len(title) <= 4096
            or type(season) is not int or not 0 <= season <= 100000
            or not aliases):
        return 'unknown'
    years = year if isinstance(year, tuple) else (() if year is None else (year,))
    if len(years) > 2 or any(type(y) is not int or not 1000 <= y <= 2999 for y in years):
        return 'unknown'
    text = unicodedata.normalize('NFKC', title).strip()
    if filename:
        # The caller has already restricted this to a real video-file row.
        text = text.rsplit('.', 1)[0] if '.' in text else text
    else:
        text = _VIDEO_EXTENSION.sub('', text)
    # A single conventional leading release group is not work evidence. Do not
    # discard a block containing a catalogue name plus an unknown qualifier.
    group = re.match(r'^\[([^\[\]]{1,100})\][ ._-]*', text)
    if group:
        _, named = _consume_aliases(group[1], aliases)
        if not named and not _BONUS.search(group[1]) and not release_season_markers(group[1]):
            text = text[group.end():]
    text = re.sub(r'^[★☆*\s]*(?:[1-9]|1[0-2]|[一二三四五六七八九十]{1,3})\s*月新番[★☆*\s]*', '', text, count=1)
    text, named = _consume_aliases(text, aliases)
    dated = re.compile(r'(?i)(?<![a-z0-9])((?:19|20)\d{2})(?![a-z0-9])')
    if years and any(int(match[1]) not in years for match in dated.finditer(text)):
        return 'conflict'
    text = dated.sub(' ', text)
    scope = detect_pack_scope(text, season)
    is_pack = bool(allow_pack and scope['is_pack'] and season in scope['pack_seasons'])
    # A covering pack can include separate bonus branches. The selected branch
    # is assessed independently below; a plain "S1 OVA" is still a conflict.
    if is_pack and '+' in text:
        branches = text.split('+')
        if all(_BONUS.search(branch) for branch in branches[1:]):
            text = branches[0]
    if season == 0:
        text = _BONUS.sub(' ', text)
    if _BONUS.search(text):
        return 'conflict'
    if _release_season_contexts(text, season) - {season}:
        return 'conflict'
    def covering(match):
        first, last = int(match[1]), int(match[2])
        return ' ' if allow_pack and first <= season <= last and first < last else match[0]
    text = _RANGE.sub(covering, text)
    # Conventional suffix groups follow an explicit technical token. This is
    # packaging syntax only, never an alias or a season source. Unknown words
    # before the episode/technical boundary still remain unresolved.
    text = re.sub(r'(?i)((?:2160|1080|720|576|480)[pi]|[xh][ .]?26[45]|hevc|avc|av1|'
                  r'flac|aac|e?ac3|dts|truehd|[1-8]\.[01])-[a-z0-9][a-z0-9_.-]{1,63}$', r'\1', text)
    if allow_pack:
        season_spans = release_season_markers(text)
        # "Season 2 - 01" is a season followed by an episode, not an
        # episode range that may consume the season's numeric evidence.
        text = _EP_RANGE.sub(lambda match: match[0] if any(
            match.start() < end and match.end() > start
            for start, end, _ in season_spans) else ' ', text)
    # Reuse the existing exact episode grammar; it alone owns episode numbers.
    parsed = parse_filename(text)
    spans = [(m.start(), m.end()) for m in parsed.markers]
    spans += [(start, end) for start, end, number in release_season_markers(text) if number == season]
    for start, end in sorted(set(spans), reverse=True):
        text = text[:start] + ' ' * (end - start) + text[end:]
    if allow_pack:
        text = _PACK.sub(' ', text)
    text = re.sub(r'[\[【]\s*第\s*\d{1,3}\s*[話话集]\s*[\]】]', ' ', text)
    if re.search(r'(?i)\bseason\b|[季期]', text):
        return 'unknown'  # A symbolic season is not an independently mapped number.
    tokens = _tokens(text)
    if tokens is None:
        return 'unknown'
    for _, token, _ in tokens:
        token = re.sub(r'^[\W_]+|[\W_]+$', '', token)
        if not token:
            continue
        if re.fullmatch(r'(?:19|20)\d{2}', token):
            if years and int(token) not in years:
                return 'conflict'
            continue
        token = re.sub(r'(?i)\b(dual|multi)[ ._-]+audio\b', r'\1-audio', token)
        token = re.sub(r'(?i)(?<![a-z0-9])(?:repack|proper|rerip)(?![a-z0-9])', ' ', token).strip(' ._-')
        if not token:
            continue
        if not _technical(token, years[0] if years else None):
            return 'unknown'
    return 'matched' if named else 'context'


def check_episode_scope(path, releases, aliases, season, year=None, require_work=True):
    """Check the selected file and every semantically relevant ancestor.

    Pure episode basenames may inherit a complete work alias from their
    selected release/branch. Only work, season or type-bearing parents constrain
    that identity; an unrelated Downloads/container name supplies no evidence.
    """
    if not isinstance(path, str) or not path or len(path) > 8192:
        raise ValueError('Actual selected episode path required')
    parts = re.split(r'[/\\]', path)
    status = release_scope(parts[-1], aliases, season, year, allow_pack=False, filename=True)
    if status == 'conflict' or (require_work and status == 'unknown'):
        raise ValueError('Actual episode catalogue identity unresolved')
    if status == 'unknown' and not require_work:
        from .catalog_identity import release_title
        try:
            actual, _ = release_title(parts[-1], 'tv')
        except ValueError:
            actual = ''
        if (actual and actual not in {'video', 'episode', 'main', '正片'}
                and actual not in {normalized(alias) for alias in aliases}):
            raise ValueError('Named manual candidate differs from the catalogue work')
    work_matched = status == 'matched'
    inside_work_branch = False
    for index, text in enumerate(list(releases) + parts[:-1]):
        if not isinstance(text, str) or not text:
            continue
        context = release_scope(text, aliases, season, year)
        _, named = _consume_aliases(unicodedata.normalize('NFKC', text), aliases)
        scoped = bool(named or release_season_markers(text) or _BONUS.search(text)
                      or re.search(r'(?i)\bseason\b|[季期]', text))
        related = index < len(releases) or inside_work_branch or scoped
        if index >= len(releases) and scoped:
            inside_work_branch = True
        if related and (context == 'conflict' or (require_work and context == 'unknown')):
            raise ValueError('Selected release or directory contradicts the episode identity')
        work_matched = work_matched or context == 'matched'
    if require_work and not work_matched:
        raise ValueError('No complete catalogue work identity in the selected file branch')

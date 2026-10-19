"""Cheap catalog-alias screening before a search result becomes a source card.

This is not a work/episode/file proof. The exact resolver and preparation
catalog checks remain mandatory. No network, fuzzy substring or sample list.
"""
import re
import unicodedata


def normalized(value):
    return ' '.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', value).casefold()))


_SPECIAL = re.compile(
    r'(?i)(?<![a-z0-9])(?:ova|oav|oad|sp|specials?|movie)(?:[ ._-]*[0-9]+)?(?![a-z0-9])'
    r'|劇場版|剧场版|总集篇|總集篇|総集編|特典|番外|特别篇|特別篇')
_GROUP = re.compile(r'(?i)字幕[组組社]|工作室|fansubs?|subbers?|raws?|studio|team|group|encode(?:rs?)?')
_RELEASE_TECHNICAL = re.compile(
    r'(?i)(?:(?:2160|1080|720|576|480)[pi]|[48]k|\d{3,4}x\d{3,4}|'
    r'web(?:-?dl|rip)?|blu-?ray|bdrip|h\.?26[45]|x26[45]|(?:hevc|avc)(?:-(?:8|10|12)bits?)?|av1|'
    r'aac|flac|opus|ac3|eac3|dts|truehd|mp3|pcm|[1-8]\.[01]|'
    r'(?:8|10|12)-?bits?|ma10p|hi10p|hdr(?:10\+?)?|dv|dovi|'
    r'chs|cht|sc|tc|gb|gbk|big5|zh(?:-cn|-tw|-hk)?|'
    r'简(?:体|中|繁)?|簡(?:體|中|繁)?|繁(?:体|體|中|简|簡)?|'
    r'(?:简|簡|繁|简繁|簡繁)?(?:体|體)?(?:中(?:文|日)?|日)?(?:字?幕|(?:内封|內封|内嵌|內嵌|外挂|外掛)(?:字?幕)?)|'
    r'mp4|mkv|avi|ts|m2ts|[a-f0-9]{8})')


def _technical_tail(text):
    """Consume every suffix character; unknown words are not release metadata."""
    text = re.sub(r'(?i)\.(?:mkv|mp4|avi|ts|m2ts)$', '', text).strip()
    while text:
        if text[0] in '[【(':
            closing = {'[': ']', '【': '】', '(': ')'}[text[0]]
            end = text.find(closing, 1)
            if end < 0:
                return False
            content, text = text[1:end], text[end + 1:].strip()
        else:
            marker = re.search(r'[\[【(]', text)
            end = marker.start() if marker else len(text)
            content, text = text[:end], text[end:].strip()
        tokens = [token for token in re.split(r'[\s_/&+]+', content.strip()) if token]
        if not tokens or any(not _RELEASE_TECHNICAL.fullmatch(token) for token in tokens):
            return False
    return True


def _trusted_title_block(value, trusted):
    """Fully consume at most four same-work aliases with known separators."""
    if not isinstance(value, str) or not re.fullmatch(r"[\w\s./|:_’'()\-]+", value):
        return False
    value = normalized(value).replace(' ', '')
    if value in trusted:
        return True
    positions = {0}
    for _ in range(4):
        positions = {start + len(alias) for start in positions for alias in trusted
                     if value.startswith(alias, start)}
        if len(value) in positions:
            return True
        if not positions:
            break
    return False


def chinese_episode_context(title, aliases):
    """Complete grammar: () absent, None invalid, (explicit_season, episode).

    New Chinese syntax cannot fall back to the permissive old title boundary.
    Both catalogue and episode gates use this same complete parse. It is not
    season, subtitle, pack, file, or playback proof.
    """
    if not isinstance(title, str) or not title or len(title) > 2048:
        return None
    text = unicodedata.normalize('NFKC', title).strip()
    if not re.search(r'[\[【]\s*第', text):
        return ()
    trusted = {normalized(a).replace(' ', '') for a in aliases
               if isinstance(a, str) and 2 <= len(a.strip()) <= 512}
    trusted.discard('')
    # A complete catalogue name beginning with 第 is a title, not an introducer.
    probe = re.sub(r'\[([^\[\]]*)\]|【([^【】]*)】',
        lambda block: ' ' * len(block[0]) if _trusted_title_block(block[1] or block[2], trusted)
        else block[0], text)
    if not re.search(r'[\[【]\s*第', probe):
        return ()  # Pure old syntax follows its byte-for-byte original path.
    if not trusted:
        return None
    stack = []
    for char in text:
        if char in '[【(':
            stack.append(char)
        elif char in ']】)':
            if not stack or stack.pop() != {']': '[', '】': '【', ')': '('}[char]:
                return None
    if stack:
        return None
    group = re.match(r'^(?:\[([^\[\]]{1,100})\]|【([^【】]{1,100})】)\s*', text)
    if group and not _trusted_title_block(group[1] or group[2], trusted):
        token = group[1] or group[2]
        if (_SPECIAL.search(token) or re.match(r'\s*第', token)
                or (group[2] and not _GROUP.search(token))):
            return None
        text = text[group.end():]
    text = re.sub(r'^[★☆*\s]*(?:[1-9]|1[0-2]|[一二三四五六七八九十]{1,3})\s*月新番[★☆*\s]*', '', text, count=1)
    count = 0
    while count < 4:
        block = re.match(r'^(?:\[([^\[\]]{1,512})\]|【([^【】]{1,512})】)\s*', text)
        if not block or not _trusted_title_block(block[1] or block[2], trusted):
            break
        text = text[block.end():]
        count += 1
    explicit_season = explicit_episode = None
    start = re.search(r'[\[【]\s*第', text)
    if not start:
        return None
    prefix = text[:start.start()].strip()
    for explicit in (r's([0-9]{1,2})[ ._-]*e([0-9]{1,3})',
                     r'([0-9]{1,2})x([0-9]{1,3})',
                     r'(?:season|saison)\s*([0-9]{1,2})\s*(?:episode|ep)\s*([0-9]{1,3})'):
        labelled = re.search(r'(?i)(?:\[\s*)?(?<!\w)' + explicit + r'(?:\s*\])?\s*$', prefix)
        if labelled:
            explicit_season, explicit_episode = int(labelled[1]), int(labelled[2])
            prefix = prefix[:labelled.start()].strip()
            break
    if (count and prefix) or (not count and not _trusted_title_block(prefix, trusted)):
        return None
    text = text[start.start():]
    # Only unconsumed release labels are type assertions. A completely bound
    # title such as "Special A" or "Movie 43" remains a title, not a special.
    if _SPECIAL.search(text):
        return None
    marker = re.match(r'^(?:\[\s*第\s*([0-9]{1,3})\s*[話话集]\s*\]|'
                      r'【\s*第\s*([0-9]{1,3})\s*[話话集]\s*】)', text)
    if not marker or not _technical_tail(text[marker.end():]):
        return None
    number = int(marker[1] or marker[2])
    if not 1 <= number <= 999 or (explicit_season is not None
            and (not 1 <= explicit_season <= 99 or explicit_episode != number)):
        return None
    return (explicit_season, number)


def chinese_episode_numbers(title, aliases):
    context = chinese_episode_context(title, aliases)
    return (context[1],) if context else context


def _wrapped_tv_title_matches(title, trusted):
    """Recognize bounded CJK-wrapped catalogue names, not arbitrary tags.

    A release may have one leading group and a conventional month announcement,
    followed by one or more complete catalogue title blocks. Every such block
    must be a trusted alias; an interior title or a different trailing work is
    never sufficient for additional admission. This is additive only: legacy
    grammar stays owned by the established matcher and existing episode gate.
    """
    text = unicodedata.normalize('NFKC', title).strip()
    group = re.match(r'^(?:\[([^\[\]]{1,100})\]|【([^【】]{1,100})】)\s*', text)
    invalid_prefix = False
    if group and normalized(group[1] or group[2]).replace(' ', '') not in trusted:
        token = group[1] or group[2]
        invalid_prefix = bool(_SPECIAL.search(token) or (group[2] and not _GROUP.search(token)))
        text = text[group.end():]
    text = re.sub(r'^[★☆*\s]*(?:[1-9]|1[0-2]|[一二三四五六七八九十]{1,3})\s*月新番[★☆*\s]*', '', text, count=1)
    if not text.startswith('【'):
        return False
    if invalid_prefix:
        return False
    count = 0
    while text.startswith('【') and count < 4:
        block = re.match(r'^【([^【】]{1,512})】\s*', text)
        if not block or normalized(block[1]).replace(' ', '') not in trusted:
            return False
        text = text[block.end():]
        count += 1
    if not count or text.startswith('【'):
        return False
    # Do not reinterpret a labelled special/movie as an ordinary TV episode.
    if _SPECIAL.search(text):
        return False
    # A title block must be immediately followed by episode/season syntax.
    # Technical-only blocks, another title, ranges and years are not evidence.
    marker = re.match(
        r'(?i)(?:(?:s\d{1,2}[ ._-]*e\d{1,3})'
        r'|(?:(?:s\d{1,2}|第\s*[0-9一二三四五六七八九十]+\s*[季期])\s*)?'
        r'(?:\[\d{1,3}(?:v\d+)?\]|-\s*\d{1,3}(?:v\d+)?))'
        r'(?=$|[\s.\[【(])', text)
    return bool(marker and _technical_tail(text[marker.end():]))


def _legacy_matches(title, aliases, mode, release_season=None):
    if not isinstance(title, str) or not title or len(title) > 2048:
        return False
    trusted = {normalized(a).replace(' ', '') for a in aliases
               if isinstance(a, str) and 2 <= len(a.strip()) <= 512}
    trusted.discard('')
    if not trusted:
        return False
    if mode in ('movie', 'movies'):
        from bobbi_core.movie_release_kind import conflict
        if conflict(title, aliases):
            return False
    # Only an independently resolved release season permits stripping an anime
    # sequel label. A base title without that context still rejects sequels.
    season_spans = []
    if release_season is not None:
        if type(release_season) is not int or not 0 <= release_season <= 99 or mode != 'tv':
            return False
        from bobbi_core.pack_parser import release_season_markers, detect_pack_scope
        scope = detect_pack_scope(title, release_season)
        if scope['pack_type'] == 'mismatch':
            return False
        if release_season > 1 and release_season not in scope['pack_seasons']:
            return False
        season_spans = release_season_markers(title)
        if season_spans and {number for _, _, number in season_spans} != {release_season}:
            return False
    if mode == 'tv' and release_season is not None:
        if _wrapped_tv_title_matches(title, trusted):
            return True
    # Group tags do not identify the work. Technical suffixes provide a title
    # boundary, not permission to accept an interior fragment of another name.
    texts = [title]
    for _ in range(3):
        stripped = re.sub(r'^\s*\[[^\[\]]{1,100}\][ ._-]*', '', texts[-1], count=1)
        if stripped == texts[-1]:
            break
        texts.append(stripped)
    boundary = r'(?<!\w)(?:19\d{2}|20\d{2}|2160p?|1080[pi]|720p|480p|4k|uhd|blu[ ._-]?ray|bd(?:rip)?|web(?:[ ._-]?dl|rip)?|remux|hevc)(?!\w)'
    if mode == 'tv':
        boundary += (r'|(?<!\w)(?:s\d+(?:[ ._-]*e\d+)?|\d+x\d+|season[ ._-]*\d+)(?!\w)'
                     r'|\s-\s*\d{1,3}(?:v\d+)?(?=$|[ ._\[(])|\[\d{1,3}(?:v\d+)?\]')
    for text in texts:
        for segment in re.split(r'[/|()]', text):
            # Numeric movie names such as 1917 are titles, not release years.
            ends = [match.start() for match in re.finditer(boundary, segment, re.I)] + [len(segment)]
            if release_season is not None:
                ends += [start for start, _, number in release_season_markers(segment) if number == release_season]
            for end in ends:
                name = segment[:end].strip(' ._-[]')
                if normalized(name).replace(' ', '') in trusted:
                    return True
    return False


def matches(title, aliases, mode, release_season=None):
    if mode == 'tv':
        context = chinese_episode_context(title, aliases)
        if context != ():
            if not context:
                return False
            if context[0] is not None:
                # Preserve only explicit SxxEyy expressions already admitted
                # by the old title grammar, with the Chinese number agreeing.
                return _legacy_matches(title, aliases, mode, release_season)
            from bobbi_core.pack_parser import release_season_markers, detect_pack_scope
            return bool(type(release_season) is int and release_season == 1
                        and not release_season_markers(title)
                        and detect_pack_scope(title, 1)['pack_type'] == 'none')
    return _legacy_matches(title, aliases, mode, release_season)

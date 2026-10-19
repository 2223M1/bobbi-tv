"""Conservative title/year/episode checks, independent of Kodi and filenames' claims."""
import re
import unicodedata

VIDEO = ('.mkv', '.mp4', '.m4v', '.avi', '.ts', '.m2ts')
YEAR = re.compile(r'(?<!\d)(?:18|19|20)\d{2}(?!\d)')
CONTROL = re.compile(r'[\x00-\x1f\x7f]')
# Boundaries apply to fields, except at the end of a proven declaration: that
# position can start S01E01E02 / S01E01S02E01 without allowing E23 inside a hash.
EPISODE_LABEL = r'e(?:p(?:isode)?)?[ ._-]*'
CONNECTOR = r'[-~–—〜～+&,、至到]'
CHINESE_NUMBER = r'\d{1,3}(?:v\d+)?'
TOKEN_END = r'(?=$|[^a-z0-9]|s\d{1,2}[ ._-]*e\d|' + EPISODE_LABEL + r'\d)'
DECLARATION = re.compile(
    r'(?i)(?:(?:s(?P<season>\d{1,2})[ ._-]*e(?P<full>\d{1,3})'
    r'|' + EPISODE_LABEL + r'(?P<short>\d{1,3}))(?:v\d+)?' + TOKEN_END +
    r'|第\s*(?P<chinese>' + CHINESE_NUMBER + r'(?:\s*' + CONNECTOR +
    r'\s*(?:第\s*)?' + CHINESE_NUMBER + r')*)\s*[集话話](?:v\d+)?)'
)
EPISODE_CONTINUATION = re.compile(
    r'(?i)\s*' + CONNECTOR + r'\s*(?:' + EPISODE_LABEL + r')?'
    r'(\d{1,3})(?:v\d+)?(?![ ._-]*bit(?![a-z0-9]))' + TOKEN_END
)
CRC_FIELD = re.compile(r'(?i)\[[0-9a-f]{8}\]|【[0-9a-f]{8}】|\([0-9a-f]{8}\)')
BRACKET_FIELD = re.compile(r'\[([^\]]+)\]|【([^】]+)】')
SEASON_FIELD = re.compile(r'(?i)(?<![a-z0-9])s(\d{1,2})(?:v\d+)?(?![a-z0-9])')
SEASON_CONTINUATION = re.compile(
    r'(?i)\s*' + CONNECTOR + r'\s*s?(\d{1,2})(?:v\d+)?'
    r'(?![ ._-]*bit(?![a-z0-9]))(?![a-z0-9])'
)


def _complete_declaration_end(text, position, known_ends):
    # A lookahead for E/S alone is insufficient: 7E23ABCD must not become
    # episode 7 followed by an incomplete E23 token. Validate the whole run.
    visited = []
    complete = True
    while position < len(text) and text[position].isascii() and text[position].isalnum():
        if position in known_ends:
            complete = known_ends[position]
            break
        visited.append(position)
        following = DECLARATION.match(text, position)
        if following is None:
            complete = False
            break
        position = following.end()
    # Each adjacent run is validated once even in a near-limit filename.
    known_ends.update((end, complete) for end in visited)
    return complete


def _episode_declarations(filename):
    """Read every field; only declaration chains can omit token boundaries.

    An exact eight-hex bracket field is checksum syntax, not proof of a CRC
    computed from content. Other bracket fields, including [E02], stay visible.
    Revisions belong to their preceding declaration. Bare numbers only acquire
    episode meaning in a directly connected list/range, never from a year,
    quality field or an arbitrary numeric title.
    """
    text = unicodedata.normalize('NFKC', filename)
    text = CRC_FIELD.sub(lambda match: ' ' * len(match[0]), text)
    declarations = []
    known_ends = {}
    position = 0
    chain_end = -1
    while True:
        marker = DECLARATION.search(text, position)
        if marker is None:
            break
        position = marker.end()
        chinese = marker['chinese'] is not None
        # 第 and 集/话/話 delimit a declaration themselves. Adjacent END/codec
        # fields must not erase it; ASCII E/S tokens still require full runs.
        if (not chinese and marker.start() != chain_end and marker.start() and
                text[marker.start()-1].isascii() and text[marker.start()-1].isalnum()):
            continue
        if not chinese and not _complete_declaration_end(text, position, known_ends):
            continue
        season = int(marker['season']) if marker['season'] is not None else None
        numbers = (re.findall(r'(\d{1,3})(?:v\d+)?', marker['chinese'], re.I) if marker['chinese'] is not None
                   else [marker['full'] or marker['short']])
        for number in numbers:
            declarations.append((season, int(number), marker['full'] is not None))
        # Continue from each actual token, including repeated E01 declarations.
        while True:
            continuation = EPISODE_CONTINUATION.match(text, position)
            if continuation is None or not _complete_declaration_end(text, continuation.end(), known_ends):
                break
            declarations.append((None, int(continuation[1]), False))
            position = continuation.end()
        chain_end = position
    return declarations


def _standalone_seasons(fields):
    """Read bounded Snn fields/range endpoints without inferring any segments."""
    seasons = set()
    for marker in SEASON_FIELD.finditer(fields):
        seasons.add(int(marker[1]))
        position = marker.end()
        while True:
            continuation = SEASON_CONTINUATION.match(fields, position)
            if continuation is None:
                break
            seasons.add(int(continuation[1]))
            position = continuation.end()
    return seasons


def _scoped_episodes(declarations):
    seasons = {season for season, _, full in declarations if full}
    # A leading E/EP declaration can use the filename's sole explicit season.
    # Its number must still agree: no absolute-to-season offset is inferred.
    season = next(iter(seasons)) if len(seasons) == 1 else None
    declared = set()
    for explicit_season, episode, full in declarations:
        if full:
            season = explicit_season
        declared.add((season, episode))
    return declared


def declared_episodes(filename):
    """Return all declared identities; None denotes an unproven season.

    Ranges retain endpoints, never expand into selectable segments. This raw
    helper has no trusted title aliases; matches() also establishes title scope.
    """
    return _scoped_episodes(_episode_declarations(filename))


def _release_fields(filename, title_end, aliases):
    """Protect a proven title, while retaining untrusted leading group fields."""
    prefix = filename[:title_end]
    trusted = {normalized(value) for value in aliases}
    fields = [' '] * len(prefix)
    for bracket in BRACKET_FIELD.finditer(prefix):
        if normalized(bracket[0]) not in trusted:
            fields[bracket.start():bracket.end()] = bracket[0]
    return ''.join(fields) + filename[title_end:]


def normalized(text):
    text = unicodedata.normalize('NFKD', str(text)).casefold()
    return ''.join(c for c in text if c.isalnum())


def terms(text):
    text = unicodedata.normalize('NFKD', str(text)).casefold()
    values = set(re.findall(r'[a-z0-9]{3,}', text)) - {'the', 'and', 'for', 'with'}
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        values.update(run[i:i+2] for i in range(max(1, len(run)-1)) if len(run[i:i+2]) == 2)
    return sorted(values)


def title_prefix(text):
    text = re.split(r'\|-|[├└]─*', str(text))[-1].strip()
    marker = re.search(r'(?i)(?<!\d)(?:18|19|20)\d{2}(?!\d)|(?<![a-z0-9])s\d{1,2}(?:e\d+)?|\b(?:2160p|1080p|720p)\b', text)
    return text[:marker.start()] if marker else text


def same_title(prefix, aliases):
    aliases = {normalized(v) for v in aliases if len(normalized(v)) >= 2}
    # Release-group brackets may precede a title; title brackets are retained.
    prefix = re.sub(r'\[([^\]]+)\]|【([^】]+)】',
                    lambda m: m[0] if normalized(m[0]) in aliases else '', prefix)
    value = normalized(prefix)
    if not value or not aliases:
        return False
    candidates = {value}
    if value.startswith('the'):
        candidates.add(value[3:])
    aliases |= {v[3:] for v in aliases if v.startswith('the') and len(v) > 5}
    # Permit a bilingual prefix only if every part is a trusted title alias.
    for _ in range(3):
        if '' in candidates or candidates & aliases:
            return True
        candidates = {value[len(alias):] for value in candidates for alias in aliases if value.startswith(alias)}
    return False


def matches(filename, spec):
    if not isinstance(filename, str):
        return False
    filename = unicodedata.normalize('NFKC', filename)
    if (len(filename) > 1024 or CONTROL.search(filename)
            or '/' in filename or '\\' in filename or not filename.lower().endswith(VIDEO)):
        return False
    year = str(spec.get('year') or '')
    if not re.fullmatch(r'(?:18|19|20)\d{2}', year):
        return False
    years = (int(year),)
    if spec['mode'] == 'movies' and spec.get('_movie_years') is not None:
        from bobbi_core.movie_years import accepted_years
        years = accepted_years(spec.get('_movie_years'), spec.get('tmdb_id'), int(year))
    markers = [m for m in YEAR.finditer(filename) if int(m[0]) in years]
    title_marker = next((m for m in markers if same_title(filename[:m.start()], spec['aliases'])), None)
    if title_marker is None:
        return False
    fields = _release_fields(filename, title_marker.start(), spec['aliases'])
    declarations = _episode_declarations(fields)
    episodes = [(season, episode) for season, episode, full in declarations if full]
    if spec['mode'] == 'movies':
        return not episodes and not _standalone_seasons(fields)
    if spec['mode'] != 'tv' or len(episodes) != 1:
        return False
    episode = episodes[0]
    if _standalone_seasons(fields) - {episode[0]}:
        return False
    # No segment map exists here: a containing multi-episode file is not an
    # exact single-episode identity, regardless of punctuation or repetition.
    if _scoped_episodes(declarations) != {episode}:
        return False
    return episode == (int(spec['season']), int(spec['episode']))


def queries(spec):
    aliases = spec['aliases']
    english = [v for v in aliases if re.search(r'[a-zA-Z]{3}', v) and not re.search(r'[\u3400-\u9fff]', v)]
    chinese = [v for v in aliases if re.search(r'[\u3400-\u9fff]{2}', v)]
    result = []
    if english:
        words = re.findall(r'[a-zA-Z]{3,}', english[0])
        words = [v for v in words if v.casefold() not in ('the', 'and', 'for', 'with')]
        if words:
            result.append(max(words, key=len))
    if chinese:
        result.append(chinese[0][:40])
    return list(dict.fromkeys(result))[:2]


def media_key(tmdb_id, mode, season=None, episode=None):
    if mode not in ('movies', 'tv') or not str(tmdb_id).isdigit():
        raise ValueError('invalid-media-identity')
    return '%s:%s:%s:%s' % (mode, int(tmdb_id), int(season or 0) if mode == 'tv' else 0,
                           int(episode or 0) if mode == 'tv' else 0)

"""Conservative work identity from service-fetched catalog data, not UI labels."""
import hashlib
import json
from pathlib import PurePosixPath
import re
import time
import unicodedata


def normalized(title):
    return ' '.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', title).casefold()))


def release_title(path, kind):
    name = PurePosixPath(path).stem
    # One leading release-group tag is conventional. Other title text, including
    # numbers and Movie/OVA/Part suffixes, is preserved for exact token matching.
    name = re.sub(r'^\[[^\[\]]{1,80}\][ ._-]*', '', name, count=1)
    if kind == 'tv':
        marker = re.search(r'(?i)(?<![a-z0-9])(?:s\d+[ ._-]*e\d+|\d+[ ._-]*x[ ._-]*\d+)(?!\d)|'
                           r'(?<![a-z0-9])(?:episode|ep|e)[ ._-]*\d+(?![a-z0-9])|'
                           r'\s-\s*\d{1,3}(?:v\d+)?(?=$|[ ._\[])|\[\d{1,3}(?:v\d+)?\]', name)
        if not marker:
            raise ValueError('No exact episode marker separates work and release metadata')
        name = name[:marker.start()].strip(' ._-')
    year_match = re.search(r'(?:^|[ ._(\[])((?:19|20)\d{2})(?=$|[ ._)\]])', name)
    year = int(year_match[1]) if year_match else None
    if year_match:
        before, after = name[:year_match.start()], name[year_match.end():]
        if kind == 'tv':
            # Year is one token, not permission to discard an unknown Movie,
            # Part or another title between the year and episode marker.
            name = before + ' ' + after
        else:
            suffix = after.strip(' ._)]')
            suffix = re.sub(r'-[A-Za-z0-9][A-Za-z0-9_-]{1,64}$', '', suffix)
            tokens = normalized(suffix).split()
            technical = re.compile(r'(?:\d{1,3}|(?:2160|1080|720|480)p|[48]k|uhd|bluray|blu|ray|bdrip|brrip|web|dl|webrip|'
                r'remux|hdr(?:10)?|dv|dovi|hevc|avc|[xh]26[45]|h|265|264|aac|dts|hd|ma|truehd|atmos|ddp?|flac|opus|'
                r'ac3|eac3|dual|audio|multi|proper|repack|extended|unrated|directors|cut|remastered|10bit|8bit|[0-9a-f]{8})')
            if any(not technical.fullmatch(token) for token in tokens):
                raise ValueError('Unknown title text after movie year')
            name = before
    elif kind == 'movie':
        raise ValueError('Movie release year is required to distinguish editions/remakes')
    title = normalized(name)
    if len(title.replace(' ', '')) < 2:
        raise ValueError('Short/empty release title remains unresolved')
    return title, year


def prove_work(media, path, catalog):
    if (not isinstance(catalog, dict) or catalog.get('provider') != 'tmdb'
            or catalog.get('id') != media['tmdb_id'] or catalog.get('kind') != media['kind']
            or not isinstance(catalog.get('aliases'), list) or not catalog['aliases']
            or not catalog.get('response_sha256') or type(catalog.get('year')) is not int):
        raise ValueError('Service-fetched catalog identity required')
    actual, year = release_title(path, media['kind'])
    aliases = {normalized(name) for name in catalog['aliases'] if isinstance(name, str)}
    if actual not in aliases and media['kind'] == 'tv':
        pair = release_context(media, catalog)
        if not pair and media.get('season') in catalog.get('release_seasons', []):
            pair = {'season': media['season']}
        if pair:
            from bobbi_core.pack_parser import release_season_markers
            spans = release_season_markers(actual)
            # Remove only a trailing, independently proved season label; never
            # an arbitrary sequel/arc suffix or interior title substring.
            if len(spans) == 1:
                start, end, number = spans[0]
                if number == pair['season'] and not actual[end:].strip():
                    actual = actual[:start].strip()
    if actual not in aliases:
        raise ValueError('Actual torrent work title is not a complete trusted catalog alias')
    from bobbi_core.movie_years import accepted_years
    years = accepted_years(catalog.get('_movie_years'), media['tmdb_id'], catalog['year']) if media['kind'] == 'movie' else (catalog['year'],)
    if year is not None and year not in years:
        raise ValueError('Release year identifies a different work')
    if catalog.get('ambiguous') and year is None:
        raise ValueError('Same-name works require a verified release year')
    return dict(provider='tmdb', id=catalog['id'], kind=catalog['kind'], matched_title=actual,
                release_year=year, catalog_year=catalog['year'],
                response_sha256=catalog['response_sha256'], expected_runtime=catalog.get('runtime_seconds', 0))


def release_context(media, catalog):
    """Use only the service-fetched order; IPC cannot supply an order/binding."""
    from bobbi_core.episode_order import lookup, continuous_episode
    order = catalog.get('episode_order')
    if order is None:
        return None
    if (catalog.get('id') != media['tmdb_id'] or order.get('tmdb_id') != media['tmdb_id']
            or media['kind'] != 'tv'):
        raise ValueError('Foreign service episode order')
    pair = lookup(order, media['season'], media['episode'])
    if pair is None:
        raise ValueError('Catalog episode absent from service episode order')
    pair['absolute_episode'] = continuous_episode(order, pair)
    return pair


def release_binding(media, catalog, source_hash):
    pair = release_context(media, catalog)
    if not pair:
        return None
    return dict(media_id='tmdb:' + str(media['tmdb_id']), season=pair['season'], episode=pair['episode'],
        absolute_episode=pair['absolute_episode'] or pair['episode'], source_info_hash=source_hash,
        provenance=('tmdb-continuous-order:' if pair['absolute_episode'] else 'tmdb-production-order:') + pair['provider_group'])


class Catalog:
    def __init__(self, session, api_key):
        if not isinstance(api_key, str) or not api_key:
            raise ValueError('Configured TMDb API key required')
        self.session, self.api_key = session, api_key
        self.cache = {}

    def _get(self, path, params):
        values = dict(params, api_key=self.api_key)
        with self.session.get('https://api.themoviedb.org/3/' + path,
                              params=values, timeout=(3.05, 8), stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError('Catalog identity unavailable')
            raw = bytearray()
            started = time.monotonic()
            for block in response.iter_content(65536):
                if len(raw) + len(block) > 1024 * 1024 or time.monotonic() - started > 15:
                    raise ValueError('Catalog identity response budget exceeded')
                raw.extend(block)
        return json.loads(raw), hashlib.sha256(raw).hexdigest()

    def lookup(self, media):
        key = (media['kind'], media['tmdb_id'], bool(media.get('anime')), 1)
        found = self.cache.get(key)
        if found and time.monotonic() - found[0] < 3600:
            return found[1]
        kind, identifier = key[:2]
        append = 'alternative_titles,release_dates' if kind == 'movie' else 'alternative_titles'
        try:
            value, digest = self._get('{}/{}'.format(kind, identifier), {'language': 'en-US', 'append_to_response': append})
        except (OSError, ValueError):
            if kind != 'movie':
                raise
            # Optional release history must not remove the existing single-year
            # identity path if the appended response is unavailable.
            value, digest = self._get('{}/{}'.format(kind, identifier), {'language': 'en-US', 'append_to_response': 'alternative_titles'})
        if value.get('id') != identifier:
            raise ValueError('Catalog returned another identity')
        name_key, original_key, date_key = ('name', 'original_name', 'first_air_date') if kind == 'tv' else ('title', 'original_title', 'release_date')
        aliases = [value.get(name_key, ''), value.get(original_key, '')]
        alternatives = value.get('alternative_titles', {})
        aliases += [item.get('title', '') for item in alternatives.get('results', alternatives.get('titles', []))[:128]]
        aliases = list(dict.fromkeys(name for name in aliases if isinstance(name, str) and name.strip()))
        date = value.get(date_key, '')
        if not aliases or not re.match(r'\d{4}-\d{2}-\d{2}$', date):
            raise ValueError('Catalog lacks a canonical title/year')
        matches, search_digest = self._get('search/' + kind, {'query': aliases[0], 'language': 'en-US', 'page': 1})
        normalized_aliases = {normalized(alias) for alias in aliases}
        ambiguous = matches.get('total_pages', 1) > 1 or any(item.get('id') != identifier and normalized(item.get(name_key, '')) in normalized_aliases
                        for item in matches.get('results', []))
        runtimes = value.get('episode_run_time', []) if kind == 'tv' else [value.get('runtime', 0)]
        runtime = min((number for number in runtimes if type(number) is int and number > 0), default=0) * 60
        result = dict(provider='tmdb', id=identifier, kind=kind, aliases=aliases, year=int(date[:4]),
                      ambiguous=ambiguous, response_sha256=hashlib.sha256((digest + search_digest).encode()).hexdigest(),
                      runtime_seconds=runtime)
        if kind == 'movie':
            from bobbi_core.movie_years import from_details
            result['_movie_years'] = from_details(value, identifier)
        if kind == 'tv':
            result['release_seasons'] = [row['season_number'] for row in value.get('seasons', [])
                if isinstance(row, dict) and type(row.get('season_number')) is int and row['season_number'] > 0]
        if kind == 'tv' and media.get('anime') and value.get('number_of_seasons') == 1:
            from bobbi_core.episode_order import validate_group
            listing, listing_digest = self._get('tv/{}/episode_groups'.format(identifier), {'language': 'en-US'})
            candidates = [row for row in listing.get('results', []) if row.get('type') in (6, 7)
                and 1 < row.get('group_count', 0) <= 100 and 1 < row.get('episode_count', 0) <= 3000]
            orders = {}
            if len(candidates) <= 2:
                for row in candidates:
                    group_id = row.get('id', '')
                    if not isinstance(group_id, str) or not re.fullmatch('[0-9a-f]{24}', group_id):
                        continue
                    document, _ = self._get('tv/episode_group/' + group_id, {'language': 'en-US'})
                    try:
                        order = validate_group(identifier, listing, document)
                    except ValueError:
                        continue
                    orders[order['digest']] = order
            result['episode_order'] = next(iter(orders.values())) if len(orders) == 1 else None
            result['episode_order_listing_sha256'] = listing_digest
        if len(self.cache) >= 128:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = time.monotonic(), result
        return result

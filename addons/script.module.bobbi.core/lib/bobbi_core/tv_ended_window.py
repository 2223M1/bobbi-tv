"""Narrow negative evidence for explicitly dated editions of completed TV.

A year inside a broadcast window is UNKNOWN, not a work/episode/file match.
This cannot authorize playback or replace any existing exact-file consumer.
"""
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import re
import unicodedata

from .movie_identity import declared_years

PROVENANCE = 'tmdb.tv.completed_window.v1'
_TECHNICAL_YEAR = re.compile(r'(?i)remaster|(?<![^\W_])re[ ._-]{1,4}master(?:ed|ing)?(?![^\W_])|restor|anniversary|edition|reissue|repack|re.?encode|重制|重製|修复|修復|周年|再版')


@dataclass(frozen=True)
class EndedWindow:
    tmdb_id: int
    season: int
    episode: int
    first_year: int
    last_year: int
    aliases: tuple
    dates_digest: str
    order_digest: str = ''
    provenance: str = PROVENANCE


def _date(value):
    if type(value) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _mapped(order, target, tmdb_id, season, episode):
    """Revalidate cached mapping identity; order digest never proves air dates."""
    if type(order) is not dict or type(target) is not dict or order.get('schema') != 1 or order.get('tmdb_id') != tmdb_id:
        return None
    try:
        seasons = order['seasons']
        if type(seasons) is not list or not 2 <= len(seasons) <= 100:
            return None
        rows = []
        for block in seasons:
            episodes = block['episodes']
            if type(episodes) is not list or not 1 <= len(episodes) <= 1000 or len(rows) + len(episodes) > 2000:
                return None
            rows.extend(episodes)
        if len(rows) < 2:
            return None
        identities = [tuple(row[key] for key in ('catalog_season', 'catalog_episode', 'episode_id', 'season', 'episode')) for row in rows]
        if any(type(number) is not int or not 1 <= number <= 999999999 for identity in identities for number in identity):
            return None
        if (len({row[:2] for row in identities}) != len(rows) or len({row[2] for row in identities}) != len(rows)
                or len({row[3:] for row in identities}) != len(rows)):
            return None
        digest = hashlib.sha256(json.dumps(identities, separators=(',', ':')).encode()).hexdigest()
        matches = [row for row in rows if (row['catalog_season'], row['catalog_episode']) == (season, episode)]
        if digest != order.get('digest') or digest != target.get('order_digest') or len(matches) != 1:
            return None
        if target.get('provider_group') != order.get('provider_group') or not re.fullmatch('[0-9a-f]{24}', str(order.get('provider_group', ''))):
            return None
        if any(target.get(key) != matches[0].get(key) for key in ('catalog_season', 'catalog_episode', 'episode_id', 'season', 'episode')):
            return None
        return digest
    except (KeyError, TypeError, AttributeError):
        return None


def from_details(details, tmdb_id, season, episode, order=None, release_order=None):
    if (type(details) is not dict or type(tmdb_id) is not int or tmdb_id <= 0
            or type(details.get('id')) is not int or details['id'] != tmdb_id
            or type(season) is not int or season < 1 or type(episode) is not int or episode < 1
            or details.get('status') not in ('Ended', 'Canceled') or details.get('in_production') is not False
            or details.get('next_episode_to_air') is not None or details.get('success') is False
            or 'error' in details or 'errors' in details):
        return None
    first, last = _date(details.get('first_air_date')), _date(details.get('last_air_date'))
    if first is None or last is None or first > last:
        return None
    rows = details.get('seasons')
    if type(rows) is not list or not 1 <= len(rows) <= 200:
        return None
    if any(type(row) is not dict or type(row.get('season_number')) is not int or not 0 <= row['season_number'] <= 999 for row in rows):
        return None
    regular = [row for row in rows if type(row) is dict and type(row.get('season_number')) is int and row['season_number'] > 0]
    if (type(details.get('number_of_seasons')) is not int or len(regular) != details['number_of_seasons']
            or len({row['season_number'] for row in regular}) != len(regular)
            or any(type(row.get('episode_count')) is not int or not 1 <= row['episode_count'] <= 10000 for row in regular)):
        return None
    target = [row for row in regular if row['season_number'] == season]
    if len(target) != 1 or type(target[0].get('episode_count')) is not int or not 1 <= episode <= target[0]['episode_count']:
        return None
    if any(_date(row.get('air_date')) is None or not first <= _date(row['air_date']) <= last for row in regular):
        return None
    order_digest = ''
    if order is not None or release_order is not None:
        order_digest = _mapped(order, release_order, tmdb_id, season, episode)
        if order_digest is None:
            return None
    aliases = [details.get('name'), details.get('original_name')]
    translations = details.get('translations')
    if type(translations) is dict and type(translations.get('translations')) is list:
        aliases += [row['data'].get('name') for row in translations['translations'][:128]
                    if type(row) is dict and type(row.get('data')) is dict]
    alternate = details.get('alternative_titles')
    if type(alternate) is dict and type(alternate.get('results')) is list:
        aliases += [row.get('title') for row in alternate['results'][:128] if type(row) is dict]
    aliases = tuple(dict.fromkeys(name.strip() for name in aliases if type(name) is str and 1 <= len(name.strip()) <= 512))[:128]
    if not aliases:
        return None
    dates = [tmdb_id, first.isoformat(), last.isoformat(), details['status'],
        [(row['season_number'], row['air_date'], row.get('episode_count')) for row in regular]]
    digest = hashlib.sha256(json.dumps(dates, separators=(',', ':')).encode()).hexdigest()
    return EndedWindow(tmdb_id, season, episode, first.year, last.year, aliases, digest, order_digest)


def _edition_year(name, aliases):
    if type(name) is not str or not 1 <= len(name) <= 2048:
        return None
    text = unicodedata.normalize('NFKC', name).casefold()
    if _TECHNICAL_YEAR.search(text):
        return None
    years = declared_years(name, aliases)
    if len(years) != 1:
        return None
    for segment in re.split(r'[/|\\\r\n]', text):
        segment = segment.strip()
        for _ in range(3):
            segment = re.sub(r'^\[[^\[\]]{1,100}\][ ._-]*', '', segment, count=1)
        for alias in aliases:
            words = re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', alias).casefold())
            if not words:
                continue
            title = r'[\W_]+'.join(re.escape(word) for word in words)
            match = re.match(r'^' + title + r'[ ._-]+[\[(]?((?:18|19|20)\d{2})[\])]?[ ._-]+\[?(?:s\d{1,2}(?:[ ._-]*e\d{1,3})?|season[ ._-]+\d{1,2})(?=$|[\W_])', segment)
            if match and int(match[1]) in years:
                return int(match[1])
    return None


def status(name, evidence, tmdb_id, season, episode):
    if (type(evidence) is not EndedWindow or evidence.provenance != PROVENANCE
            or any(type(number) is not int or number <= 0 for number in (tmdb_id, season, episode))
            or (evidence.tmdb_id, evidence.season, evidence.episode) != (tmdb_id, season, episode)
            or type(evidence.first_year) is not int or type(evidence.last_year) is not int
            or not 1000 <= evidence.first_year <= evidence.last_year <= 9999
            or type(evidence.aliases) is not tuple or not 1 <= len(evidence.aliases) <= 128
            or any(type(alias) is not str or not 1 <= len(alias) <= 512 for alias in evidence.aliases)
            or type(evidence.dates_digest) is not str or not re.fullmatch('[0-9a-f]{64}', evidence.dates_digest)):
        return dict(status='unknown', reason='completed_catalog_unavailable')
    year = _edition_year(name, evidence.aliases)
    if year is not None and not evidence.first_year <= year <= evidence.last_year:
        return dict(status='conflict', reason='explicit_edition_outside_completed_broadcast_window')
    return dict(status='unknown', reason='not_an_explicit_outside_window_conflict')

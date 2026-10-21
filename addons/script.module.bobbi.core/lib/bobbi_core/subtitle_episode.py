"""Subtitle-only unseasoned episode evidence; never grants video continuation."""
from dataclasses import dataclass
import re

from .filename_semantics import parse_filename


@dataclass(frozen=True)
class SingleSeason:
    tmdb: int
    episodes: int


def from_details(data, identifier):
    if (not isinstance(data, dict) or type(identifier) is not int or identifier <= 0
            or type(data.get('id')) is not int or data['id'] != identifier
            or not isinstance(data.get('seasons'), list) or not data.get('name')):
        return None
    seasons = [row for row in data['seasons'] if isinstance(row, dict) and row.get('season_number') != 0]
    if (len(seasons) != 1 or type(seasons[0].get('season_number')) is not int
            or seasons[0]['season_number'] != 1 or type(seasons[0].get('episode_count')) is not int
            or not 1 <= seasons[0]['episode_count'] <= 10000
            or data.get('number_of_seasons', 1) != 1):
        return None
    return SingleSeason(identifier, seasons[0]['episode_count'])


def matches(filename, context, declared_seasons):
    parsed = parse_filename(filename)
    target = (context['season'], context['episode'])
    if parsed.strong:
        return parsed.episode_pairs() == {target}
    scope = context.get('_subtitle_single_season')
    authorized = (declared_seasons == {target[0]} or
        isinstance(scope, SingleSeason) and type(context.get('tmdb')) is int and scope.tmdb == context['tmdb']
        and target[0] == 1 and 1 <= target[1] <= scope.episodes)
    if not authorized:
        return False
    # EP01 / [01] reuse the common parser, but a range never becomes one file.
    markers = parsed.markers
    if any(parsed.range_after(marker) for marker in markers):
        return False
    numbers = {int(marker['episode']) for marker in markers}
    asian = tuple(re.finditer(r'第\s*(\d{1,4})\s*[话話集回]', filename))
    if any(re.match(r'\s*[-–~～+&]', filename[m.end():]) for m in asian):
        return False
    numbers.update(int(m[1]) for m in asian)
    return numbers == {target[1]}

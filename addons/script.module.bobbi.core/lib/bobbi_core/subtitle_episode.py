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


def declarations(text, title):
    """Subtitle-only, title-aware season/special evidence, never video authority."""
    words = re.findall(r'[^\W_]+', title, re.UNICODE)
    if words:
        text = re.sub(r'(?<![^\W_])' + r'[\W_]+'.join(map(re.escape, words))
                      + r'(?![^\W_])', ' ', text, flags=re.I)
    seasons = {int(s) for s in re.findall(r'(?i)(?<![a-z0-9])s(\d{1,3})(?=e\d|[^a-z0-9]|$)', text)}
    seasons.update(int(s) for s in re.findall(r'(?i)\bseason[ ._-]+(\d{1,3})\b', text))
    seasons.update(int(s) for s in re.findall(r'(?i)\b(\d{1,3})(?:st|nd|rd|th)[ ._-]+season\b', text))
    for token in re.findall(r'第\s*([0-9零〇一二两兩三四五六七八九十百]+)\s*[季期]', text):
        if token.isdecimal():
            seasons.add(int(token))
        else:
            digits = dict(zip('零〇一二两兩三四五六七八九', (0, 0, 1, 2, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
            total = current = 0
            for char in token:
                if char in digits:
                    current = digits[char]
                else:
                    total += (current or 1) * (10 if char == '十' else 100)
                    current = 0
            seasons.add(total + current)
    if re.search(r'(?i)(?<![a-z0-9])(?:ova|oad|specials?|sp)(?![a-z0-9])|番外篇?|特别篇|特別篇|特典', text):
        seasons.add(0)
    return seasons


def matches(filename, context, declared_seasons):
    parsed = parse_filename(filename)
    target = (context['season'], context['episode'])
    seasons = set(declared_seasons) | declarations(filename, context['title'])
    if seasons and seasons != {target[0]}:
        return False
    asian = tuple(re.finditer(r'第\s*(\d{1,4})\s*[话話集回]', filename))
    # Lists are not single-episode files, including bare second numbers and
    # bracketed/revised forms. This does not change the common video grammar.
    for marker in parsed.markers + asian:
        if re.match(r'(?:v\d+)?[\s\]\)]*[,，、;；/+&–~～-]\s*(?:第|(?:s\d+)?e(?:p(?:isode)?)?\s*)?\d',
                    filename[marker.end():], re.I):
            return False
    if parsed.strong:
        return parsed.episode_pairs() == {target}
    scope = context.get('_subtitle_single_season')
    authorized = (seasons == {target[0]} or
        isinstance(scope, SingleSeason) and type(context.get('tmdb')) is int and scope.tmdb == context['tmdb']
        and target[0] == 1 and 1 <= target[1] <= scope.episodes)
    if not authorized:
        return False
    # EP01 / [01] reuse the common parser, but a range never becomes one file.
    markers = parsed.markers
    if any(parsed.range_after(marker) for marker in markers):
        return False
    numbers = {int(marker['episode']) for marker in markers}
    if any(re.match(r'\s*[-–~～+&]', filename[m.end():]) for m in asian):
        return False
    numbers.update(int(m[1]) for m in asian)
    return numbers == {target[1]}

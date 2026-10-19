"""Pure latest-started-season presentation; never a playback/episode identity."""
from datetime import date
import re


def _number(value):
    return value if type(value) is int and 0 < value < 1000000000 else 0


def _day(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def poster_path(value):
    return value if isinstance(value, str) and re.fullmatch(r'/[A-Za-z0-9_-]+\.(?:jpg|png|webp)', value) else ''


def _text(value):
    return ' '.join(value.replace('\x00', '').split())[:2048] if isinstance(value, str) else ''


def _merged_season(details, order, today):
    """Use only an existing validated production order covering the current ep."""
    if (not isinstance(order, dict) or order.get('schema') != 1
            or order.get('tmdb_id') != details.get('id')):
        return None
    groups = order.get('seasons')
    if not isinstance(groups, list) or not 2 <= len(groups) <= 100:
        return None
    latest = details.get('last_episode_to_air') or {}
    last_id = _number(latest.get('id'))
    last_date = _day(latest.get('air_date'))
    seen, candidates = set(), []
    for group in groups:
        number = _number(group.get('season'))
        episodes = group.get('episodes')
        if not number or not isinstance(episodes, list) or len(episodes) > 1000:
            return None
        days = []
        for row in episodes:
            episode_id = _number(row.get('episode_id'))
            if not episode_id or episode_id in seen:
                return None
            seen.add(episode_id)
            aired = _day(row.get('air_date'))
            if aired and aired <= today:
                days.append(aired)
        if days:
            candidates.append((min(days), number))
    if len(seen) > 2000 or not candidates or (last_date and last_date <= today and last_id not in seen):
        return None
    started, number = max(candidates)
    return dict(tmdb_id=details['id'], season=number, season_name='', air_date=started.isoformat(),
        poster_path=poster_path(details.get('poster_path')), poster_origin='series_fallback',
        overview='', provenance='validated_production_order')


def latest_season(details, today, order=None):
    """Prefer an aired regular season, excluding specials and future posters."""
    if not isinstance(details, dict) or not _number(details.get('id')) or not isinstance(today, date):
        return None
    if details.get('number_of_seasons') == 1:
        merged = _merged_season(details, order, today)
        if merged:
            return merged
        # Do not pretend an aggregate catalogue's "season 1" is its newest
        # production season when the provider advertises a split but it is not
        # yet unambiguously resolved. Fall back to the series card instead.
        listing = (details.get('episode_groups') or {}).get('results') or []
        if any(row.get('type') in (6, 7) and row.get('group_count', 0) > 1 for row in listing):
            return None
    rows = details.get('seasons')
    if not isinstance(rows, list) or len(rows) > 100:
        return None
    last = details.get('last_episode_to_air') or {}
    last_day = _day(last.get('air_date'))
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        number, started = _number(row.get('season_number')), _day(row.get('air_date'))
        observed = number and last.get('season_number') == number and last_day and last_day <= today
        if not number or (started and started > today) or (not started and not observed):
            continue
        if not _number(row.get('episode_count')) and not observed:
            continue
        candidates.append((started or last_day, number, row))
    if not candidates:
        return None
    _started, number, selected = max(candidates, key=lambda entry: entry[:2])
    art = poster_path(selected.get('poster_path'))
    return dict(tmdb_id=details['id'], season=number, season_name=_text(selected.get('name')),
        air_date=selected.get('air_date') if _day(selected.get('air_date')) else '',
        poster_path=art or poster_path(details.get('poster_path')),
        poster_origin='season' if art else 'series_fallback', overview=_text(selected.get('overview')),
        provenance='tmdb_season')


def title_for(series_title, view):
    series_title = _text(series_title)
    number = _number(view.get('season')) if isinstance(view, dict) else 0
    if not number:
        return series_title
    name = _text(view.get('season_name'))
    generic = re.fullmatch(r'(?:Season\s*\d+|S\d+|第\s*[\d一二三四五六七八九十百]+\s*[季期部])', name, re.I)
    if not name or name == series_title or generic or re.search(r'[ぁ-ゖァ-ヺ]', name):
        return '{} · 第{}季'.format(series_title, number)
    normalized = lambda text: re.sub(r'[\W_]+', '', text).casefold()
    if normalized(name).startswith(normalized(series_title)):
        return name
    return '{} · {}'.format(series_title, name)

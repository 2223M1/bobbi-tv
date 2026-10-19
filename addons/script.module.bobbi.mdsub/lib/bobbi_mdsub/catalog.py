"""Exact-ID, local-only source listing. Stable public URLs resolve at playback.

The reviewed catalogue is a package asset, not a cache of signed download URLs.
No network calls, player calls, tasks, account access or full media downloads.
Updating the independently versioned addon updates the catalogue atomically.
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode

MAX_BYTES = 8 * 1024 * 1024
MAX_FILES = 16000
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.webm', '.mov', '.m4v'}
DEFAULT_INDEX = Path(__file__).resolve().parents[2] / 'resources' / 'catalog.json'


def checked_path(path):
    if (not isinstance(path, str) or not path.startswith('/') or path.startswith('//')
            or len(path) > 2048 or len(path.split('/')) < 3
            or any(part in ('', '.', '..') or part.startswith('._') for part in path.split('/')[1:])
            or any(ord(char) < 32 or ord(char) == 127 for char in path) or '\\' in path
            or Path(path).suffix.casefold() not in VIDEO_EXTENSIONS):
        raise ValueError('INVALID_MDSUB_PATH')
    return path


def raw_url(path):
    return 'https://pan.mdsub.top/api/raw?' + urlencode({'path': checked_path(path)})


def validate(data):
    if (not isinstance(data, dict) or type(data.get('schema')) is not int or data.get('schema') != 1
            or not isinstance(data.get('files'), list) or len(data['files']) > MAX_FILES
            or not isinstance(data.get('catalog_date'), str)):
        raise ValueError('INVALID_MDSUB_CATALOG')
    seen = set()
    for row in data['files']:
        if not isinstance(row, dict):
            raise ValueError('INVALID_MDSUB_ROW')
        path = checked_path(row['path'])
        if (row.get('kind') not in ('tv', 'movie') or type(row.get('tmdb_id')) is not int
                or row['tmdb_id'] <= 0 or type(row.get('size')) is not int or row['size'] < 16384
                or not isinstance(row.get('work'), str) or not row['work']
                or not isinstance(row.get('evidence'), str)):
            raise ValueError('INVALID_MDSUB_IDENTITY')
        if row['kind'] == 'tv':
            if (type(row.get('season')) is not int or row['season'] < 0
                    or not isinstance(row.get('episodes'), list) or not 1 <= len(row['episodes']) <= 100
                    or any(type(e) is not int or e < 1 for e in row['episodes'])
                    or len(set(row['episodes'])) != len(row['episodes'])):
                raise ValueError('INVALID_MDSUB_EPISODES')
        elif 'season' in row or 'episodes' in row:
            raise ValueError('MOVIE_EPISODE_CONFLICT')
        key = (path, row['kind'], row['tmdb_id'], row.get('season'))
        if key in seen:
            raise ValueError('DUPLICATE_MDSUB_ROW')
        seen.add(key)
    return data


def load(path=None):
    target = Path(path or DEFAULT_INDEX)
    with target.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('MDSUB_CATALOG_TOO_LARGE')
    return validate(json.loads(raw))


def find_sources(data, tmdb_id, mode, season=None, episode=None):
    """Never fall back to approximate titles, IMDb guesses or a different episode."""
    if not re.fullmatch(r'[1-9][0-9]*', str(tmdb_id or '')):
        return []
    kind = {'tv': 'tv', 'episode': 'tv', 'movies': 'movie', 'movie': 'movie'}.get(mode)
    if kind is None:
        return []
    if kind == 'tv':
        if not re.fullmatch(r'[0-9]+', str(season)) or not re.fullmatch(r'[1-9][0-9]*', str(episode)):
            return []
        season, episode = int(season), int(episode)
    return [dict(row) for row in data['files']
            if row['tmdb_id'] == int(tmdb_id) and row['kind'] == kind
            and (kind == 'movie' or row['season'] == season and episode in row['episodes'])]


def source_fields(row):
    path = checked_path(row['path'])
    suffix = ' · 合并集，需手动定位' if len(row.get('episodes', [])) > 1 else ''
    part = re.search(r'(?i)S\d+E\d+([ab])\.', path.rsplit('/', 1)[-1])
    if part:
        suffix += ' · 分段 ' + part[1].upper() + '，需另选后续段'
    title = path.rsplit('/', 1)[-1]
    # Preserve the original filename, including the actual credited team.
    return dict(title=title + suffix, type='Direct', indexer='漫迪 MDsub',
                subindexer='公开片库 · 直连' + suffix,
                guid='mdsub:' + hashlib.sha256(path.encode('utf-8')).hexdigest(),
                url=raw_url(path), size=row['size'])

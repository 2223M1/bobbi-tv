"""Maintainer-provided application configuration, not a user's TMDb account."""
import json
from pathlib import Path
import re

ATTRIBUTION = ('This application uses TMDB and the TMDB APIs but is not endorsed, '
               'certified, or otherwise approved by TMDB.')


def tmdb_key(path=None):
    path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / 'resources/tmdb-project.json'
    try:
        if path.is_symlink() or path.stat().st_size > 2048:
            return ''
        value = json.loads(path.read_text(encoding='utf-8'))
        if (type(value) is not dict or set(value) != {'schema', 'application', 'api_key', 'use', 'attribution'}
                or type(value['schema']) is not int or value['schema'] != 1
                or value['application'] != 'Bobbi TV' or value['use'] != 'personal-noncommercial'
                or value['attribution'] != ATTRIBUTION
                or not isinstance(value['api_key'], str) or not re.fullmatch('[a-f0-9]{32}', value['api_key'])):
            return ''
        return value['api_key']
    except (OSError, ValueError):
        return ''

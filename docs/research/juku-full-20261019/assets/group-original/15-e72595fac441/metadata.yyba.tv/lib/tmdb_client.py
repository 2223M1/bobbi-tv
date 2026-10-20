# -*- coding: utf-8 -*-
"""TMDB API client."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from lib import settings
from lib.http_client import get_json


def clean_search_title(title: str, year: Optional[str] = None) -> str:
    clean_title = (title or '').strip()
    if year and str(year).isdigit():
        clean_title = re.sub(rf'[\.\s_-]{year}[\.\s_-]', ' ', clean_title)
        clean_title = re.sub(r'[\.\s_-]+$', '', clean_title).strip()
    return clean_title


def _lang_params(include_images: bool = False) -> Dict[str, Any]:
    lang = settings.get_tmdb_language()
    params: Dict[str, Any] = {'language': lang}
    if include_images:
        short = lang.split('-')[0] if lang else 'zh'
        params['include_image_language'] = f'{short},null,en'
    return params


def search_movie(title: str, year: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {'query': clean_search_title(title, year), **_lang_params()}
    if year and str(year).isdigit():
        params['year'] = str(year)
    data = get_json('/search/movie', params)
    if not data:
        return []
    return data.get('results', []) or []


def get_movie(tmdb_id: str) -> Optional[Dict[str, Any]]:
    params = {'append_to_response': 'credits', **_lang_params(include_images=True)}
    data = get_json(f'/movie/{tmdb_id}', params)
    return data if isinstance(data, dict) else None


def search_tv(title: str, year: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {'query': clean_search_title(title, year), **_lang_params()}
    if year and str(year).isdigit():
        params['first_air_date_year'] = str(year)
    data = get_json('/search/tv', params)
    if not data:
        return []
    return data.get('results', []) or []


def get_tv(tmdb_id: str) -> Optional[Dict[str, Any]]:
    params = {'append_to_response': 'credits', **_lang_params(include_images=True)}
    data = get_json(f'/tv/{tmdb_id}', params)
    return data if isinstance(data, dict) else None


def get_episode(tmdb_id: str, season: int, episode: int) -> Optional[Dict[str, Any]]:
    params = _lang_params(include_images=True)
    data = get_json(f'/tv/{tmdb_id}/season/{season}/episode/{episode}', params)
    return data if isinstance(data, dict) else None


def get_season_episodes(tmdb_id: str, season: int) -> List[Dict[str, Any]]:
    params = _lang_params()
    data = get_json(f'/tv/{tmdb_id}/season/{season}', params)
    if not data:
        return []
    return data.get('episodes', []) or []

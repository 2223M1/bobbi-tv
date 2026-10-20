# -*- coding: utf-8 -*-
"""TMDB JSON 转 Kodi ListItem（剧集 / 单集）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import xbmc
import xbmcgui

from lib.tmdb_api import FANART_SIZE, POSTER_SIZE, PROFILE_SIZE, STILL_SIZE, TmdbApi

_LOG = 'YYBA TV ListItem'


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _split_names(value: str) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(' / ') if part.strip()]


def _format_genres(items) -> str:
    if not items:
        return ''
    names = [item.get('name', '') for item in items if isinstance(item, dict)]
    return ' / '.join(name for name in names if name)


def _build_cast(credits: dict) -> List[Dict[str, Any]]:
    cast: List[Dict[str, Any]] = []
    for item in (credits or {}).get('cast', [])[:20]:
        if not isinstance(item, dict):
            continue
        name = item.get('name') or ''
        role = item.get('character') or ''
        if not name:
            continue
        profile = item.get('profile_path') or ''
        cast.append({
            'name': name,
            'role': role,
            'order': _safe_int(item.get('order'), len(cast)),
            'thumbnail': TmdbApi.build_image_url(profile, PROFILE_SIZE) if profile else '',
        })
    return cast


def _make_actors(cast) -> list:
    if not cast:
        return []
    try:
        from xbmc import Actor
    except ImportError:
        return []

    actors = []
    for entry in cast:
        if isinstance(entry, dict):
            name = entry.get('name') or ''
            role = entry.get('role') or ''
            thumb = entry.get('thumbnail') or ''
            order = _safe_int(entry.get('order'))
            if not name:
                continue
            try:
                actors.append(Actor(name, role, order, thumb))
            except TypeError:
                try:
                    actors.append(Actor(name, role, thumb))
                except TypeError:
                    actors.append(Actor(name, role))
    return actors


def tmdb_tv_json_to_meta(data: Dict[str, Any]) -> Dict[str, Any]:
    credits = data.get('credits') or {}
    first_air = data.get('first_air_date') or ''
    year = first_air[:4] if len(first_air) >= 4 else ''
    uniqueids = {'tmdb': str(data.get('id') or '')}
    if data.get('external_ids', {}).get('imdb_id'):
        uniqueids['imdb'] = data['external_ids']['imdb_id']
    creators = [
        c.get('name', '') for c in (data.get('created_by') or [])
        if isinstance(c, dict) and c.get('name')
    ]
    poster_path = data.get('poster_path') or ''
    backdrop_path = data.get('backdrop_path') or ''
    return {
        'title': data.get('name') or '',
        'originaltitle': data.get('original_name') or data.get('name') or '',
        'plot': data.get('overview') or '',
        'year': year,
        'premiered': first_air,
        'rating': str(data.get('vote_average') or ''),
        'votes': str(data.get('vote_count') or ''),
        'tagline': data.get('tagline') or '',
        'genre': _format_genres(data.get('genres')),
        'director': ' / '.join(creators[:5]),
        'country': _format_genres(data.get('production_countries')),
        'status': data.get('status') or '',
        'uniqueids': uniqueids,
        'cast': _build_cast(credits),
        'poster_url': TmdbApi.build_image_url(poster_path, POSTER_SIZE),
        'fanart_url': TmdbApi.build_image_url(backdrop_path, FANART_SIZE),
    }


def tmdb_episode_json_to_meta(
    data: Dict[str, Any], season: int = 0, episode: int = 0,
) -> Dict[str, Any]:
    air_date = data.get('air_date') or ''
    still_path = data.get('still_path') or ''
    season_num = data.get('season_number') if data.get('season_number') is not None else season
    episode_num = data.get('episode_number') if data.get('episode_number') is not None else episode
    uniqueids = {'tmdb': str(data.get('id') or '')}
    return {
        'title': data.get('name') or '',
        'plot': data.get('overview') or '',
        'season': season_num,
        'episode': episode_num,
        'aired': air_date,
        'rating': str(data.get('vote_average') or ''),
        'runtime': str(data.get('runtime') or ''),
        'uniqueids': uniqueids,
        'thumb_url': TmdbApi.build_image_url(still_path, STILL_SIZE) if still_path else '',
    }


def search_item_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    first_air = item.get('first_air_date') or ''
    year = first_air[:4] if len(first_air) >= 4 else ''
    poster_path = item.get('poster_path') or ''
    return {
        'title': item.get('name') or '',
        'year': year,
        'poster_url': TmdbApi.build_image_url(poster_path, POSTER_SIZE) if poster_path else '',
    }


def _add_artwork(list_item: xbmcgui.ListItem, url: str, art_type: str) -> None:
    if not url or not url.startswith(('http://', 'https://')):
        return
    if hasattr(list_item, 'getVideoInfoTag'):
        try:
            tag = list_item.getVideoInfoTag()
            if hasattr(tag, 'addAvailableArtwork'):
                tag.addAvailableArtwork(url, art_type)
                return
        except Exception:
            pass
    if hasattr(list_item, 'addAvailableArtwork'):
        try:
            list_item.addAvailableArtwork(url, art_type)
        except Exception:
            pass


def _apply_art(list_item: xbmcgui.ListItem, meta: Dict[str, Any]) -> None:
    poster = (meta.get('poster_url') or '').strip()
    fanart = (meta.get('fanart_url') or '').strip()
    thumb = (meta.get('thumb_url') or '').strip()
    art = {}
    if poster.startswith(('http://', 'https://')):
        for art_type in ('poster', 'thumb', 'icon', 'banner'):
            _add_artwork(list_item, poster, art_type)
        art.update({'poster': poster, 'thumb': poster, 'icon': poster, 'banner': poster})
    if fanart.startswith(('http://', 'https://')):
        _add_artwork(list_item, fanart, 'fanart')
        art['fanart'] = fanart
        list_item.setAvailableFanart([{'image': fanart}])
    if thumb.startswith(('http://', 'https://')) and not poster:
        _add_artwork(list_item, thumb, 'thumb')
        art.update({'thumb': thumb, 'icon': thumb})
    if art:
        list_item.setArt(art)


def _build_setinfo_dict(
    meta: Dict[str, Any],
    media_type: str = '',
    episodeguide: str = '',
) -> Dict[str, Any]:
    """Kodi VideoInfoScanner 依赖 setInfo('video') 读取 episodeguide / season / episode。"""
    info: Dict[str, Any] = {}
    if media_type:
        info['mediatype'] = media_type
    title = meta.get('title') or ''
    if title:
        info['title'] = str(title)
    if meta.get('originaltitle'):
        info['originaltitle'] = str(meta['originaltitle'])
    if meta.get('tvshowtitle'):
        info['tvshowtitle'] = str(meta['tvshowtitle'])
    plot = meta.get('plot') or ''
    if plot:
        info['plot'] = str(plot)
    if meta.get('year'):
        info['year'] = _safe_int(meta['year'])
    if meta.get('rating'):
        info['rating'] = _safe_float(meta.get('rating'))
    if meta.get('premiered'):
        info['premiered'] = str(meta['premiered'])
    if meta.get('aired'):
        info['aired'] = str(meta['aired'])
    if meta.get('genre'):
        info['genre'] = str(meta['genre'])
    if meta.get('status'):
        info['status'] = str(meta['status'])
    if meta.get('season') is not None and meta.get('season') != '':
        info['season'] = _safe_int(meta.get('season'))
    if meta.get('episode') is not None and meta.get('episode') != '':
        info['episode'] = _safe_int(meta.get('episode'))
    if episodeguide:
        info['episodeguide'] = episodeguide
    return info


def _apply_video_info(
    list_item: xbmcgui.ListItem,
    meta: Dict[str, Any],
    cast=None,
    media_type: str = '',
    episodeguide: str = '',
) -> None:
    if hasattr(list_item, 'getVideoInfoTag'):
        try:
            tag = list_item.getVideoInfoTag()
            if media_type and hasattr(tag, 'setMediaType'):
                tag.setMediaType(media_type)
            display_title = meta.get('title') or ''
            if display_title:
                tag.setTitle(str(display_title))
            if meta.get('originaltitle'):
                tag.setOriginalTitle(str(meta['originaltitle']))
            tag.setPlot(str(meta.get('plot') or ''))
            if meta.get('year'):
                tag.setYear(_safe_int(meta['year']))
            tag.setRating(_safe_float(meta.get('rating')))
            tag.setVotes(_safe_int(meta.get('votes')))
            tag.setDuration(_safe_int(meta.get('runtime')))
            if meta.get('premiered'):
                tag.setPremiered(str(meta['premiered']))
            if meta.get('aired'):
                tag.setFirstAired(str(meta['aired']))
            if meta.get('tagline'):
                tag.setTagLine(str(meta['tagline']))
            genres = _split_names(str(meta.get('genre') or ''))
            if genres and hasattr(tag, 'setGenres'):
                tag.setGenres(genres)
            directors = _split_names(str(meta.get('director') or ''))
            if directors and hasattr(tag, 'setDirectors'):
                tag.setDirectors(directors)
            countries = _split_names(str(meta.get('country') or ''))
            if countries and hasattr(tag, 'setCountries'):
                tag.setCountries(countries)
            if meta.get('status') and hasattr(tag, 'setTvShowStatus'):
                tag.setTvShowStatus(str(meta['status']))
            if meta.get('tvshowtitle') and hasattr(tag, 'setTvShowTitle'):
                tag.setTvShowTitle(str(meta['tvshowtitle']))
            if meta.get('season') is not None and meta.get('season') != '' and hasattr(tag, 'setSeason'):
                tag.setSeason(_safe_int(meta.get('season')))
            if meta.get('episode') is not None and meta.get('episode') != '' and hasattr(tag, 'setEpisode'):
                tag.setEpisode(_safe_int(meta.get('episode')))
            if cast:
                actors = _make_actors(cast)
                if actors:
                    tag.setCast(actors)
            uniqueids = meta.get('uniqueids') or {}
            if uniqueids:
                tag.setUniqueIDs(uniqueids, 'tmdb')
            if episodeguide and hasattr(tag, 'setEpisodeGuide'):
                tag.setEpisodeGuide(episodeguide)
        except Exception as err:
            xbmc.log(f'[{_LOG}] VideoInfoTag failed: {err}', xbmc.LOGWARNING)

    info = _build_setinfo_dict(meta, media_type=media_type, episodeguide=episodeguide)
    if info:
        list_item.setInfo('video', info)


def build_tvshow_list_item(
    meta: Dict[str, Any],
    folder_title: str = '',
    episodeguide: str = '',
    episodeguide_url: str = '',
) -> xbmcgui.ListItem:
    display = folder_title or meta.get('title') or 'Unknown'
    guide = episodeguide or episodeguide_url
    list_item = xbmcgui.ListItem(label=display, offscreen=True)
    show_meta = dict(meta)
    show_meta['title'] = display
    show_meta['tvshowtitle'] = display
    _apply_art(list_item, show_meta)
    _apply_video_info(
        list_item,
        show_meta,
        cast=meta.get('cast') or [],
        media_type='tvshow',
        episodeguide=guide,
    )
    return list_item


def build_episode_list_item(meta: Dict[str, Any], show_title: str = '') -> xbmcgui.ListItem:
    title = meta.get('title') or 'Unknown'
    list_item = xbmcgui.ListItem(label=title, offscreen=True)
    ep_meta = dict(meta)
    if show_title:
        ep_meta['tvshowtitle'] = show_title
    season = _safe_int(ep_meta.get('season'))
    episode = _safe_int(ep_meta.get('episode'))
    if season > 0 and episode > 0:
        list_item.setLabel2(f'S{season:02d}E{episode:02d}')
    _apply_art(list_item, ep_meta)
    _apply_video_info(list_item, ep_meta, media_type='episode')
    return list_item


def build_find_item(title: str, meta: Optional[Dict[str, Any]] = None) -> xbmcgui.ListItem:
    list_item = xbmcgui.ListItem(label=title, offscreen=True)
    if meta:
        _apply_art(list_item, meta)
    _apply_video_info(list_item, {'title': title}, media_type='tvshow')
    return list_item

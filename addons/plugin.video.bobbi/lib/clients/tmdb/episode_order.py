"""Bounded cached production-season orders for collapsed anime catalogs."""
from datetime import timedelta
from bobbi_core.image_cache import image_url as tmdb_image_url
from lib.cinema.episode_order import validate_group, lookup, continuous_episode


def get_order(tmdb_id, fetch=False):
    from lib.db.cached import cache
    try:
        identifier = int(tmdb_id)
    except (ValueError, TypeError):
        return None
    if identifier <= 0:
        return None
    key = 'bobi_episode_order_v1:' + str(identifier)
    try:
        saved = cache.get(key)
    except (OSError, ValueError):
        # An unavailable optional order cache must not crash unrelated shows.
        return None
    if isinstance(saved, dict):
        return saved.get('order')
    if not fetch:
        return None
    from lib.api.tmdbv3api.tmdb import TMDb
    from lib.utils.tmdb_init import ensure_tmdb_init
    ensure_tmdb_init()
    client = TMDb()
    def request(path):
        value = client._request_obj(path, params='language=zh-CN', add_lang=False)
        return value.to_dict() if hasattr(value, 'to_dict') else value
    try:
        listing = request('/tv/{}/episode_groups'.format(identifier))
        candidates = [row for row in listing.get('results', []) if row.get('type') in (6, 7)
                      and 1 < row.get('group_count', 0) <= 100 and 1 < row.get('episode_count', 0) <= 3000]
        # Never silently choose the first of multiple differing production edits.
        if len(candidates) > 2:
            return None
        orders = []
        for row in candidates:
            try:
                order = validate_group(identifier, listing, request('/tv/episode_group/' + row['id']))
                orders.append(order)
            except ValueError:
                continue
        unique = {order['digest']: order for order in orders}
        result = next(iter(unique.values())) if len(unique) == 1 else None
        from bobbi_core.metadata_transport import request_remaining
        if not request_remaining(24):
            return None
        cache.set(key, {'order': result}, timedelta(hours=24))
        return result
    except Exception as error:
        from lib.utils.kodi.utils import kodilog
        kodilog('Episode order unavailable: ' + type(error).__name__)
        return None


def release_pair(ids, tv_data):
    if not isinstance(ids, dict) or not isinstance(tv_data, dict):
        return None
    order = get_order(ids.get('tmdb_id'))
    return lookup(order, tv_data.get('season'), tv_data.get('episode'))


def selected_release_binding(ids, tv_data, info_hash, title):
    """Bind an explicit release season to a provider-mapped catalog episode.

    A bare/unlabelled old pack cannot borrow an offset. The existing exact
    file selector must still prove a unique media file in this selected hash.
    """
    import re
    if not isinstance(info_hash, str) or not re.fullmatch('[0-9a-fA-F]{40}', info_hash):
        return None
    pair = release_pair(ids, tv_data)
    if pair is None:
        return None
    from lib.search import _cinema_catalog_aliases
    from lib.cinema.candidate_titles import matches
    if not matches(title, _cinema_catalog_aliases(ids, 'tv'), 'tv', release_season=pair['season']):
        return None
    from lib.utils.parsers.pack_parser import detect_pack_scope
    from lib.utils.general.processors import explicit_episode_conflict
    scope = detect_pack_scope(title, pair['season'])
    if scope['pack_type'] == 'mismatch' or explicit_episode_conflict(title, pair['season'], pair['episode']):
        return None
    if pair['season'] not in scope['pack_seasons'] and scope['pack_type'] != 'episode':
        return None
    absolute = continuous_episode(get_order(ids['tmdb_id']), pair)
    return dict(media_id='tmdb:' + str(ids['tmdb_id']), season=pair['season'], episode=pair['episode'],
                absolute_episode=absolute or pair['episode'], source_info_hash=info_hash.lower(),
                provenance=('tmdb-continuous-order:' if absolute else 'tmdb-production-order:') + pair['provider_group'])


def show_collapsed_seasons(metadata, title, ids, mode, media_type, prepared=None):
    import xbmc
    if xbmc.getSkinDir() != 'skin.bobbi.cinema' or metadata.get('number_of_seasons') != 1:
        return False
    genres = metadata.get('genres', [])
    if not any((genre.get('id') if hasattr(genre, 'get') else None) == 16 for genre in genres):
        return False
    order = prepared.get('order') if prepared is not None else get_order(ids.get('tmdb_id'), fetch=True)
    if order is None:
        return False
    from lib.utils.kodi.utils import make_list_item, build_url, add_directory_items_batch, end_of_directory, apply_section_view
    from lib.utils.general.utils import set_content_type
    from lib.clients.tmdb.frontend_metadata import apply
    items = []
    for season in order['seasons']:
        item = make_list_item(label='第 {} 季'.format(season['season']))
        item.setProperty('IsPlayable', 'false')
        # Production-season labels are display-only; never fetch them as TMDb seasons.
        apply(item, ids.get('tmdb_id'), 'tv', dict(title=title))
        item.getVideoInfoTag().setMediaType('season')
        item.getVideoInfoTag().setSeason(season['season'])
        item.getVideoInfoTag().setTitle('第 {} 季'.format(season['season']))
        poster = metadata.get('poster_path')
        if poster:
            item.setArt({'poster': tmdb_image_url(poster, 'w342')})
        url = build_url('bobi_order_episodes', ids=ids, tv_name=title, season=season['season'],
                        digest=order['digest'], mode=mode, media_type=media_type)
        items.append((url, item, True))
    # Do not relabel all specials as movies; keep the provider's special IDs.
    if any(season.get('season_number') == 0 for season in metadata.get('seasons', [])):
        item = make_list_item(label='特别篇 / OVA')
        apply(item, ids.get('tmdb_id'), 'season', dict(title=title, season=0))
        item.setProperty('IsPlayable', 'false')
        items.append((build_url('show_episodes_details', ids=ids, tv_name=title, season=0,
                               mode=mode, media_type=media_type), item, True))
    set_content_type('season')
    from lib.clients.tmdb.related_movies import directory_entries
    items.extend(directory_entries(ids, include_cached=True,
        prepared=prepared.get('movies') if prepared is not None else None))
    add_directory_items_batch(items)
    end_of_directory()
    apply_section_view('view.seasons', content_type='seasons')
    return True


def show_order_episodes(params):
    import json
    from datetime import date
    from lib.utils.kodi.utils import add_directory_items_batch, end_of_directory, apply_section_view, notification
    from lib.utils.general.utils import set_content_type
    from lib.utils.views.shows import _process_episode
    ids = json.loads(params.get('ids', '{}'))
    order = get_order(ids.get('tmdb_id'))
    if order is None or params.get('digest') != order['digest']:
        notification('分季数据已更新或不可用，请返回作品重新打开')
        end_of_directory()
        return
    number = int(params.get('season', 0))
    selected = next((row for row in order['seasons'] if row['season'] == number), None)
    rows = []
    today = date.today().isoformat()
    if selected:
        for row in selected['episodes']:
            # A future/unannounced episode must not be advertised as playable.
            if not row['air_date'] or row['air_date'] > today:
                continue
            episode = dict(row, id=row['episode_id'], episode_number=row['catalog_episode'],
                           season_number=row['catalog_season'])
            _, url, item = _process_episode(episode, params.get('tv_name', ''), row['catalog_season'],
                ids, 'tv', 'tv', {}, localized_titles={'zh': row['name'], 'display': row['name']}, display_order=row)
            if item is not None:
                rows.append((url, item, False))
    set_content_type('episode')
    add_directory_items_batch(rows)
    end_of_directory()
    apply_section_view('view.episodes', content_type='episodes')

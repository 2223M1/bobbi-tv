import json
import time
from bobbi_core.image_cache import image_url as tmdb_image_url

from lib.clients.tmdb.base import BaseTmdbClient
from lib.clients.tmdb.utils.utils import add_kodi_dir_item, tmdb_get
from lib.utils.general.utils import (
    add_next_button,
    execute_thread_pool,
    set_content_type,
    set_media_infoTag,
    set_pluging_category,
)
from lib.utils.kodi.utils import (
    build_url,
    add_directory_items_batch,
    apply_section_view,
    end_of_directory,
    make_list_item,
    notification,
    show_keyboard,
    translation,
)


def relationship_request(path, params):
    """One explicit, bounded public metadata request on the existing cache."""
    import xbmc
    from bobbi_core.metadata_transport import request_budget
    monitor = xbmc.Monitor()
    deadline = time.monotonic() + 8
    with request_budget(deadline, monitor.abortRequested, quiet=True):
        value = tmdb_get(path, params)
    if monitor.abortRequested():
        raise InterruptedError('RELATIONSHIP_CANCELLED')
    if time.monotonic() >= deadline:
        raise TimeoutError('RELATIONSHIP_DEADLINE')
    return value.to_dict() if hasattr(value, 'to_dict') else value


def relationship_failure(action, params, empty=False):
    item = make_list_item(label='暂无关联信息 · 选择重试' if empty else '关联信息暂不可用 · 选择重试')
    item.setProperty('IsPlayable', 'false')
    item.setProperty('Bobi.Rail.State', 'empty' if empty else 'error')
    add_directory_items_batch([(build_url(action, **params), item, True)])
    end_of_directory(cache=False)


def relationship_works(credits, action, params):
    """20 cards from credit summaries; no per-card details or source search."""
    import xbmc
    from lib.clients.tmdb.anime_fast_catalog import _generic_item
    from bobbi_core.image_cache import image_batch
    try:
        page = max(1, min(100, int(params.get('page', 1))))
    except (ValueError, TypeError):
        page = 1
    unique = {}
    for credit in credits[:2000]:
        if not isinstance(credit, dict) or credit.get('media_type') not in ('movie', 'tv'):
            continue
        identifier = credit.get('id')
        if type(identifier) is not int or identifier <= 0:
            continue
        unique.setdefault((credit['media_type'], identifier), credit)
    ordered = sorted(unique.values(), key=lambda c: (c.get('release_date') or c.get('first_air_date') or '', c['id']), reverse=True)
    rows, owned = [], []
    with image_batch():
        for credit in ordered[(page-1)*20:page*20]:
            item = _generic_item(credit)
            if item:
                # Enter the existing manual work/season/source flow. A visible
                # recommendation is not a prepared or directly playable file.
                item[1].setProperty('IsPlayable', 'false')
                rows.append(item)
                owned.append((item[1], 'tmdb:%s:%d' % (credit['media_type'], credit['id'])))
    if owned and not xbmc.Monitor().abortRequested():
        from lib.utils.views.catalog_owned import annotate
        annotate(owned)
    if xbmc.Monitor().abortRequested():
        end_of_directory(cache=False)
        return
    if len(ordered) > page*20:
        item = make_list_item(label='下一页')
        item.setProperty('Bobi.NextPage', 'true')
        rows.append((build_url(action, **dict(params, page=page+1)), item, True))
    if not rows:
        relationship_failure(action, params, empty=True)
        return
    add_directory_items_batch(rows)
    end_of_directory(cache=False)
    apply_section_view('view.movies', content_type='videos')


class PeopleClient(BaseTmdbClient):
    @staticmethod
    def relationships(params):
        """A work's explicit collection, cast and director IDs, loaded on click."""
        from lib.cinema.frontend_contract import integer
        identifier, kind = integer(params.get('id')), params.get('kind')
        if not identifier or kind not in ('movie', 'tv'):
            end_of_directory(cache=False)
            return
        route_params = dict(id=identifier, kind=kind)
        try:
            details = relationship_request(kind + '_details', dict(id=identifier, append_to_response='credits'))
        except InterruptedError:
            end_of_directory(cache=False)
            return
        except Exception:
            details = None
        if not isinstance(details, dict) or str(details.get('id')) != str(identifier):
            relationship_failure('bobi_relationships', route_params)
            return
        rows = []
        collection = details.get('belongs_to_collection') or {}
        collection = collection if isinstance(collection, dict) else {}
        if kind == 'movie' and integer(collection.get('id')):
            item = make_list_item(label='同系列 · ' + str(collection.get('name') or '系列电影'))
            item.setProperty('Bobi.CardKey', 'tmdb:collection:' + str(collection['id']))
            rows.append((build_url('handle_collection_details', collection_id=collection['id']), item, True))
        credits = details.get('credits') or {}
        credits = credits if isinstance(credits, dict) else {}
        people = [('director', p) for p in (credits.get('crew') or [])
                  if isinstance(p, dict) and p.get('job') == 'Director'][:8]
        people += [('cast', p) for p in (credits.get('cast') or []) if isinstance(p, dict)][:20]
        seen = set()
        for role, person in people:
            person_id = integer(person.get('id'))
            if not person_id or (role, person_id) in seen:
                continue
            seen.add((role, person_id))
            item = make_list_item(label=('导演 · ' if role == 'director' else '演员 · ') + str(person.get('name') or '未命名人物'))
            item.setProperty('Bobi.CardKey', 'tmdb:person:%s:%s' % (person_id, role))
            item.setProperty('IsPlayable', 'false')
            image = tmdb_image_url(person.get('profile_path') or '', 'w185')
            if image:
                item.setArt({'thumb': image, 'poster': image})
            rows.append((build_url('handle_tmdb_person_details', person_id=person_id, mode='multi', role=role), item, True))
        if not rows:
            relationship_failure('bobi_relationships', route_params, empty=True)
            return
        import xbmc
        if xbmc.Monitor().abortRequested():
            end_of_directory(cache=False)
            return
        add_directory_items_batch(rows)
        end_of_directory(cache=False)
        apply_section_view('view.movies', content_type='videos')

    def get_image_url(self, path):
        if not path:
            return ""
        return tmdb_image_url(path, 'w500')

    def search_people(self, mode, page=1):
        set_pluging_category(translation(90081))
        set_content_type(mode)

        query = show_keyboard(id=30241) if page == 1 else None
        if not query:
            end_of_directory(cache=False)
            return

        data = tmdb_get("search_people", params={"query": query, "page": page})
        if not data or getattr(data, "total_results", 0) == 0:
            notification(translation(90389))
            end_of_directory(cache=False)
            return

        execute_thread_pool(data.results, PeopleClient.show_people_details, mode)

        add_next_button(
            "handle_tmdb_query",
            query="tmdb_people",
            subquery="search_people",
            page=page + 1,
            mode=mode,
        )
        end_of_directory()

    @staticmethod
    def search_people_by_id(params):
        set_pluging_category(translation(90078))
        mode = params.get("mode", "tv")
        media_type = params.get("media_type", "")
        set_content_type(mode)

        ids = json.loads(params.get("ids", "{}"))
        tmdb_id = ids.get("tmdb_id")
        if not tmdb_id:
            notification(translation(90400))
            return

        if mode == "movies" or media_type == "movie":
            credits = tmdb_get("movie_credits", params=tmdb_id)
        else:
            credits = tmdb_get("tv_credits", params=tmdb_id)

        if not credits:
            notification(translation(90418))
            return

        def get_media_credits(person):
            person_id = person.get("id")
            if not person_id:
                return
            PeopleClient.show_people_details(person, mode)

        execute_thread_pool(credits.cast, get_media_credits)

        end_of_directory()

    def show_popular_people(self, mode, page=1):
        set_pluging_category(translation(90079))
        set_content_type(mode)

        data = tmdb_get("popular_people", params=page)
        if not data or getattr(data, "total_results", 0) == 0:
            notification(translation(90389))
            return

        execute_thread_pool(data.results, PeopleClient.show_people_details, mode)

        add_next_button(
            "handle_tmdb_query",
            query="tmdb_people",
            subquery="popular_people",
            page=page + 1,
            mode=mode,
        )
        end_of_directory()

    def show_trending_people(self, mode, page=1):
        set_pluging_category(translation(90080))
        set_content_type(mode)

        data = tmdb_get("trending_people", params=page)
        if not data or getattr(data, "total_results", 0) == 0:
            notification(translation(90389))
            return

        execute_thread_pool(data.results, PeopleClient.show_people_details, mode)

        add_next_button(
            "handle_tmdb_query",
            query="tmdb_people",
            subquery="latest_people",
            page=page + 1,
            mode=mode,
        )

        end_of_directory()

    @staticmethod
    def show_people_details(person, mode):
        details = tmdb_get("person_details", params=person.get("id"))
        list_item = make_list_item(label=person.get("name", "Unknown"))
        set_media_infoTag(list_item, data=details, mode=mode)
        add_kodi_dir_item(
            list_item=list_item,
            url=build_url("handle_tmdb_person_info", mode=mode, person_id=person.get("id")),
            is_folder=False,
        )

    @staticmethod
    def handle_tmdb_person_info(params):
        from lib.gui.actor_info_window import ActorInfoWindow
        from lib.utils.kodi.utils import ADDON_PATH

        params.get("mode")
        person_id = params.get("person_id")
        window = ActorInfoWindow(
            "actor_info.xml",
            ADDON_PATH,
            person_id=person_id,
        )
        window.doModal()
        del window

    @staticmethod
    def handle_tmdb_person_details(params):
        # Reuse the existing person directory instead of a second async dialog.
        # Native plugin-directory cancellation discards an obsolete completion.
        from lib.cinema.frontend_contract import integer
        identifier = integer(params.get('person_id'))
        mode = params.get("mode")
        role = params.get('role', 'cast')
        if not identifier or mode not in ('movies', 'tv', 'multi') or role not in ('cast', 'director'):
            end_of_directory(cache=False)
            return
        set_pluging_category(translation(90420))
        set_content_type(mode)
        route_params = dict(person_id=identifier, mode=mode, role=role, page=params.get('page', 1))
        try:
            data = relationship_request('person_credits', identifier)
        except InterruptedError:
            end_of_directory(cache=False)
            return
        except Exception:
            data = None
        if not isinstance(data, dict) or (data.get('id') is not None and str(data['id']) != str(identifier)):
            relationship_failure('handle_tmdb_person_details', route_params)
            return
        credits = data.get('cast' if role == 'cast' else 'crew') or []
        credits = [c for c in credits if isinstance(c, dict)
                   and (role != 'director' or c.get('job') == 'Director')
                   and (mode == 'multi' or c.get('media_type') == ('movie' if mode == 'movies' else 'tv'))]
        relationship_works(credits, 'handle_tmdb_person_details', route_params)

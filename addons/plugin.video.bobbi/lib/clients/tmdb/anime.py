from lib.clients.tmdb.anime_metadata import (
    _am6b_apply_anime_title_properties,
    _am6b_build_catalog_title_map,
    _am6b_catalog_localized_title,
    _am6b_catalog_title,
    _am6b_translation_title,
    _am6b_value,
    _am6b_verified_titles,
)
from lib.clients.tmdb.base import BaseTmdbClient
from lib.db.pickle_db import PickleDatabase
from lib.utils.general.utils import (
    Animation,
    Anime,
    Cartoons,
    add_next_button,
    execute_thread_pool,
    set_media_infoTag,
    set_pluging_category,
)
from lib.utils.kodi.utils import (
    end_of_directory,
    kodilog,
    make_list_item,
    notification,
    show_keyboard,
    translation,
)


class TmdbAnimeClient(BaseTmdbClient):
    def handle_anime_search_query(self, page):
        if page == 1:
            query = show_keyboard(id=30241)
            if query:
                PickleDatabase().set_key("anime_query", query)
                return query
            return None
        return PickleDatabase().get_key("anime_query")

    @staticmethod
    def set_anime_category_label(category):
        labels = {
            Anime.AIRING: translation(90039),
            Anime.CURRENT_QUARTER: "本季度动漫 / CURRENT SEASON ANIME",
            Anime.MOVIES_NEW: "动漫电影上新 / NEW ANIME FILMS",
            Anime.POPULAR: translation(90064),
            Anime.POPULAR_RECENT: translation(90038),
            Anime.TOP_RATED: translation(90042),
        }
        label = labels.get(category)
        if label is not None:
            set_pluging_category(label)

    def handle_anime_category_query(
        self, client, category, submode, page, language=None, set_label=True
    ):
        if set_label:
            self.set_anime_category_label(category)
        if category == Anime.AIRING:
            return client.anime_on_the_air(submode, page, language=language)
        elif category == Anime.CURRENT_QUARTER:
            return client.anime_current_quarter(submode, page, language=language)
        elif category == Anime.MOVIES_NEW:
            return client.anime_movies_new(page, language=language)
        elif category == Anime.POPULAR:
            return client.anime_popular(submode, page, language=language)
        elif category == Anime.POPULAR_RECENT:
            return client.anime_popular_recent(submode, page, language=language)
        elif category == Anime.TOP_RATED:
            return client.anime_top_rated(submode, page, language=language)
        else:
            kodilog(f"Invalid category: {category}")
            return None

    def process_anime_results(self, data, submode, page, mode, category, catalog_title_map=None):
        if data.total_results == 0:
            notification("No results found")
            return
        execute_thread_pool(
            data.results,
            TmdbAnimeClient.show_anime_results,
            submode,
            catalog_title_map or {},
        )
        add_next_button("next_page_anime", page=page, mode=mode, submode=submode, category=category)
        end_of_directory()

    @staticmethod
    def handle_anime_years_or_genres(category, mode, page, submode):
        if category == Anime.YEARS:
            TmdbAnimeClient.show_years_items(mode, page, submode)
        elif category == Anime.GENRES:
            TmdbAnimeClient.show_genres_items(mode, page, submode)
        else:
            kodilog(f"Invalid category: {category}")
            return None

    @staticmethod
    def handle_animation_or_cartoons_query(client, category, submode, page):
        if category == Animation().POPULAR:
            return client.animation_popular(submode, page)
        elif category == Cartoons.POPULAR:
            return client.cartoons_popular(submode, page)
        else:
            kodilog(f"Invalid category: {category}")
            return None

    @staticmethod
    def show_anime_results(res, mode, catalog_title_map=None):
        tmdb_id = res.get("id", "")
        catalog_title_map = catalog_title_map or {}
        titles = catalog_title_map.get(tmdb_id, {})
        original_key = "original_title" if mode == "movies" else "original_name"
        original = _am6b_value(res, original_key, "")
        original = original.strip() if isinstance(original, str) else ""
        if mode == "movies":
            provider_title = res.title
        elif mode == "tv":
            provider_title = res.name
        else:
            kodilog(f"Invalid mode: {mode}")
            return None

        display_title = titles.get("zh") or titles.get("en") or provider_title or original
        search_title = titles.get("en") or original or display_title

        # The click route resolves full details and external IDs immediately
        # before source search. Avoid doing the same remote details request for
        # every poster merely to render the directory.
        ids = {"tmdb_id": tmdb_id}
        list_item = make_list_item(label=display_title)
        set_media_infoTag(list_item, data=res, mode=mode)
        _am6b_apply_anime_title_properties(list_item, res, mode, titles)
        TmdbAnimeClient.add_media_directory_item(list_item, mode, search_title, ids)

from datetime import date, datetime, timedelta

from lib.api.tmdbv3api.tmdb import TMDb
from lib.api.tmdbv3api.utils import get_current_date, get_dates, years_tvshows


# AM6B_STREAMING_HOME_CATALOG_V1
def _am6b_tokyo_today(utc_now=None):
    """Return the current Tokyo date without depending on host timezone data."""
    utc_now = utc_now or datetime.utcnow()
    return (utc_now + timedelta(hours=9)).date()


def _am6b_quarter_bounds(today):
    """Return inclusive calendar-quarter bounds for a date."""
    start_month = ((today.month - 1) // 3) * 3 + 1
    start = date(today.year, start_month, 1)
    if start_month == 10:
        next_start = date(today.year + 1, 1, 1)
    else:
        next_start = date(today.year, start_month + 3, 1)
    return start, next_start - timedelta(days=1)


class TmdbAnime(TMDb):
    _urls = {
        "discover_tv": "/discover/tv",
        "discover_movie": "/discover/movie",
        "search_tv": "/search/tv",
        "search_movie": "/search/movie",
        "tv_keywords": "/tv/%s/keywords",
        "movie_keywords": "/movie/%s/keywords",
    }

    def _request_localized(self, action, params, language=None, **kwargs):
        if language:
            params = f"{params}&language={language}" if params else f"language={language}"
            return self._request_obj(
                action,
                params=params,
                add_lang=False,
                **kwargs,
            )
        return self._request_obj(action, params=params, **kwargs)

    def cartoons_popular(self, mode, page_no, language=None):
        return self._request_localized(
            (self._urls["discover_tv"] if mode == "tv" else self._urls["discover_movie"]),
            params=f"with_keywords=6513-cartoon&page={page_no}",
            language=language,
        )

    def animation_popular(self, mode, page_no, language=None):
        return self._request_localized(
            (self._urls["discover_tv"] if mode == "tv" else self._urls["discover_movie"]),
            params=f"with_keywords=297442&page={page_no}",
            language=language,
        )

    def anime_popular(self, mode, page_no, language=None):
        return self._request_localized(
            (self._urls["discover_tv"] if mode == "tv" else self._urls["discover_movie"]),
            params=f"with_keywords=210024&page={page_no}",
            language=language,
        )

    def anime_popular_recent(self, mode, page_no, language=None):
        return self._request_localized(
            (self._urls["discover_tv"] if mode == "tv" else self._urls["discover_movie"]),
            params=(
                "with_keywords=210024&sort_by=first_air_date.desc&include_null_first_air_dates=false&first_air_date_year={}&page={}".format(
                    years_tvshows[0]["id"], page_no
                )
            ),
            language=language,
        )

    def anime_current_quarter(self, mode, page_no, today=None, language=None):
        """Japanese anime with episodes airing in the current Tokyo quarter.

        TMDb often stores sequels/cours under the original series ID. Its
        first_air_date stays at season one's premiere, so that field must not
        decide whether a returning series belongs in this quarter's catalogue.
        Movie discovery retains its release-date semantics.
        """
        today = today or _am6b_tokyo_today()
        start, end = _am6b_quarter_bounds(today)
        date_key = "air_date" if mode == "tv" else "primary_release_date"
        sort_by = "popularity.desc" if mode == "tv" else "primary_release_date.asc"
        return self._request_localized(
            (self._urls["discover_tv"] if mode == "tv" else self._urls["discover_movie"]),
            params=(
                "with_keywords=210024&with_original_language=ja&"
                f"sort_by={sort_by}&include_null_first_air_dates=false&"
                f"{date_key}.gte={start.isoformat()}&{date_key}.lte={end.isoformat()}&"
                f"page={page_no}"
            ),
            language=language,
        )

    def anime_movies_new(self, page_no, today=None, language=None):
        """Japanese anime films ordered by their known release date, newest first."""
        today = today or _am6b_tokyo_today()
        return self._request_localized(
            self._urls["discover_movie"],
            params=(
                "with_keywords=210024&with_original_language=ja&"
                "sort_by=primary_release_date.desc&"
                f"primary_release_date.lte={today.isoformat()}&page={page_no}"
            ),
            language=language,
        )

    def anime_year(self, params):
        year_param = "first_air_date_year" if params["mode"] == "tv" else "primary_release_year"
        return self._request_obj(
            (self._urls["discover_tv"] if params["mode"] == "tv" else self._urls["discover_movie"]),
            params="with_keywords=210024&include_null_first_air_dates=false&{}={}&page={}".format(
                year_param, params["year"], params["page"]
            ),
        )

    def anime_genres(self, params):
        return self._request_obj(
            (self._urls["discover_tv"] if params["mode"] == "tv" else self._urls["discover_movie"]),
            params="&with_keywords=210024&with_genres={}&include_null_first_air_dates=false&first_air_date.lte={}&page={}".format(
                params["genre_id"], get_current_date(), params["page"]
            ),
        )

    def anime_on_the_air(self, mode, page_no, language=None):
        current_date, future_date = get_dates(7, reverse=False)
        return self._request_localized(
            (self._urls["discover_tv"] if mode == "tv" else self._urls["discover_movie"]),
            params=f"with_keywords=210024&air_date.gte={current_date}&air_date.lte={future_date}&page={page_no}",
            language=language,
        )

    def anime_top_rated(self, mode, page_no, language=None):
        return self._request_localized(
            (self._urls["discover_tv"] if mode == "tv" else self._urls["discover_movie"]),
            params=f"with_keywords=210024&sort_by=vote_average.desc&vote_count.gte=100&page={page_no}",
            language=language,
        )

    def anime_search(self, query, mode, page_no, adult=False, language=None):
        from urllib.parse import urlencode
        params = urlencode({'query': query, 'page': page_no})

        if adult is not None:
            params += "&include_adult={}".format("true" if adult else "false")

        return self._request_localized(
            self._urls["search_tv"] if mode == "tv" else self._urls["search_movie"],
            params=params,
            key="results",
            language=language,
        )

    def tmdb_keywords(self, mode, tmdb_id):
        return self._request_obj(
            (self._urls["tv_keywords"] if mode == "tv" else self._urls["movie_keywords"]) % tmdb_id,
        )

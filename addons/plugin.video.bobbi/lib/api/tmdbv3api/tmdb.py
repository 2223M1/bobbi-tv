import ast
import logging
import os
import time

import requests

from .as_obj import AsObj
from .exceptions import TMDbException

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache

logger = logging.getLogger(__name__)


class TMDb:
    """Small, bounded TMDb transport shared by the bundled API objects.

    The original library cached an unlimited number of raw Response objects,
    issued requests without a timeout, and could sleep recursively for an
    unbounded provider reset interval.  On an always-on Android TV box that
    combination grows memory over time and lets metadata work compete with
    playback indefinitely.  This transport keeps the public API intact while
    bounding cache size, connection/read time, retries, and retry delay.
    """

    _session = None
    TMDB_API_KEY = "TMDB_API_KEY"
    TMDB_LANGUAGE = "TMDB_LANGUAGE"
    TMDB_SESSION_ID = "TMDB_SESSION_ID"
    TMDB_WAIT_ON_RATE_LIMIT = "TMDB_WAIT_ON_RATE_LIMIT"
    TMDB_DEBUG_ENABLED = "TMDB_DEBUG_ENABLED"
    TMDB_CACHE_ENABLED = "TMDB_CACHE_ENABLED"
    TMDB_PROXIES = "TMDB_PROXIES"

    REQUEST_CACHE_MAXSIZE = 128
    REQUEST_CACHE_TTL_SECONDS = 900
    REQUEST_TIMEOUT = (3.05, 8.0)
    MAX_GET_ATTEMPTS = 2
    MAX_RETRY_DELAY_SECONDS = 1.5
    RETRY_STATUS_CODES = frozenset((429, 500, 502, 503, 504))

    def __init__(self, obj_cached=True, session=None):
        if self.__class__._session is None or session is not None:
            self.__class__._session = requests.Session() if session is None else session
        self._base = "https://api.themoviedb.org/3"
        self._remaining = 40
        self._reset = None
        self.obj_cached = obj_cached
        if os.environ.get(self.TMDB_LANGUAGE) is None:
            os.environ[self.TMDB_LANGUAGE] = "en-US"

    @property
    def page(self):
        return os.environ["page"]

    @property
    def total_results(self):
        return os.environ["total_results"]

    @property
    def total_pages(self):
        return os.environ["total_pages"]

    @property
    def api_key(self):
        return os.environ.get(self.TMDB_API_KEY)

    @property
    def proxies(self):
        raw_value = os.environ.get(self.TMDB_PROXIES)
        if raw_value is None:
            return None
        try:
            value = ast.literal_eval(raw_value)
        except (SyntaxError, ValueError):
            logger.warning("Ignoring invalid TMDb proxy configuration")
            return None
        if not isinstance(value, dict):
            logger.warning("Ignoring non-dictionary TMDb proxy configuration")
            return None
        return value

    @proxies.setter
    def proxies(self, proxies):
        if proxies is None:
            os.environ.pop(self.TMDB_PROXIES, None)
            return
        if not isinstance(proxies, dict):
            raise ValueError("TMDb proxies must be a dictionary or None")
        os.environ[self.TMDB_PROXIES] = repr(proxies)

    @api_key.setter
    def api_key(self, api_key):
        os.environ[self.TMDB_API_KEY] = str(api_key)

    @property
    def language(self):
        return os.environ.get(self.TMDB_LANGUAGE)

    @language.setter
    def language(self, language):
        os.environ[self.TMDB_LANGUAGE] = language

    @property
    def has_session(self):
        return True if os.environ.get(self.TMDB_SESSION_ID) else False

    @property
    def session_id(self):
        if not os.environ.get(self.TMDB_SESSION_ID):
            raise TMDbException(
                "Must Authenticate to create a session run Authentication(username, password)"
            )
        return os.environ.get(self.TMDB_SESSION_ID)

    @session_id.setter
    def session_id(self, session_id):
        os.environ[self.TMDB_SESSION_ID] = session_id

    @property
    def wait_on_rate_limit(self):
        return os.environ.get(self.TMDB_WAIT_ON_RATE_LIMIT) != "False"

    @wait_on_rate_limit.setter
    def wait_on_rate_limit(self, wait_on_rate_limit):
        os.environ[self.TMDB_WAIT_ON_RATE_LIMIT] = str(wait_on_rate_limit)

    @property
    def debug(self):
        return os.environ.get(self.TMDB_DEBUG_ENABLED) == "True"

    @debug.setter
    def debug(self, debug):
        os.environ[self.TMDB_DEBUG_ENABLED] = str(debug)

    @property
    def cache(self):
        return os.environ.get(self.TMDB_CACHE_ENABLED) != "False"

    @cache.setter
    def cache(self, cache):
        os.environ[self.TMDB_CACHE_ENABLED] = str(cache)

    @staticmethod
    def _freeze_proxies(proxies):
        if not proxies:
            return None
        return tuple(sorted((str(key), str(value)) for key, value in proxies.items()))

    @staticmethod
    def _thaw_proxies(proxies):
        if not proxies:
            return None
        return dict(proxies)

    @classmethod
    def _retry_delay(cls, response, attempt):
        headers = getattr(response, "headers", {}) or {}
        raw_delay = headers.get("Retry-After")
        try:
            delay = float(raw_delay)
        except (TypeError, ValueError):
            delay = 0.25 * attempt
        return max(0.0, min(cls.MAX_RETRY_DELAY_SECONDS, delay))

    @classmethod
    def _request_with_bounds(cls, requester, method, url, data, json_payload, proxies):
        method = str(method or "GET").upper()
        attempts = cls.MAX_GET_ATTEMPTS if method == "GET" else 1
        last_error = None

        for attempt in range(1, attempts + 1):
            try:
                response = requester(
                    method,
                    url,
                    data=data,
                    json=json_payload,
                    proxies=proxies,
                    timeout=cls.REQUEST_TIMEOUT,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(min(cls.MAX_RETRY_DELAY_SECONDS, 0.25 * attempt))
                    continue
                raise TMDbException(
                    "TMDb request failed after {} attempt(s)".format(attempts)
                )

            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code in cls.RETRY_STATUS_CODES and attempt < attempts:
                time.sleep(cls._retry_delay(response, attempt))
                continue

            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                last_error = exc
                raise TMDbException(
                    "TMDb request failed with HTTP status {}".format(status_code or "unknown")
                )
            return response

        raise TMDbException(
            "TMDb request failed{}".format(
                " after a transport error" if last_error is not None else ""
            )
        )

    @staticmethod
    @lru_cache(maxsize=REQUEST_CACHE_MAXSIZE)
    def cached_request(method, url, data, json, proxies, cache_bucket):
        return TMDb._request_with_bounds(
            requests.request,
            method,
            url,
            data,
            json,
            TMDb._thaw_proxies(proxies),
        )

    def cache_clear(self):
        return self.cached_request.cache_clear()

    def _request_obj(
        self,
        action,
        params="",
        call_cached=True,
        method="GET",
        data=None,
        json=None,
        key=None,
        add_lang=True,
    ):
        if self.api_key is None or self.api_key == "":
            raise TMDbException("No API key found.")

        if add_lang:
            url = "{}{}?api_key={}&{}&language={}".format(
                self._base,
                action,
                self.api_key,
                params,
                self.language,
            )
        else:
            url = "{}{}?api_key={}&{}".format(
                self._base,
                action,
                self.api_key,
                params,
            )

        method_upper = str(method or "GET").upper()
        can_cache = (
            self.cache
            and self.obj_cached
            and call_cached
            and method_upper == "GET"
            and data is None
            and json is None
        )
        if can_cache:
            req = self.cached_request(
                method_upper,
                url,
                None,
                None,
                self._freeze_proxies(self.proxies),
                int(time.monotonic() // self.REQUEST_CACHE_TTL_SECONDS),
            )
        else:
            req = self._request_with_bounds(
                self.__class__._session.request,
                method_upper,
                url,
                data,
                json,
                self.proxies,
            )

        headers = getattr(req, "headers", {}) or {}
        if "X-RateLimit-Remaining" in headers:
            try:
                self._remaining = int(headers["X-RateLimit-Remaining"])
            except (TypeError, ValueError):
                pass
        if "X-RateLimit-Reset" in headers:
            try:
                self._reset = int(headers["X-RateLimit-Reset"])
            except (TypeError, ValueError):
                pass

        try:
            payload = req.json()
        except (TypeError, ValueError):
            raise TMDbException("TMDb returned an invalid JSON response")

        if "page" in payload:
            os.environ["page"] = str(payload["page"])
        if "total_results" in payload:
            os.environ["total_results"] = str(payload["total_results"])
        if "total_pages" in payload:
            os.environ["total_pages"] = str(payload["total_pages"])

        if self.debug:
            logger.info(payload)
            logger.info(self.cached_request.cache_info())

        if "errors" in payload:
            raise TMDbException(payload["errors"])
        if "success" in payload and payload["success"] is False:
            raise TMDbException(payload["status_message"])

        return AsObj(payload, key=key)

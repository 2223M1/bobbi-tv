import time
from typing import Any, Callable, Dict, List, Optional

from requests.exceptions import Timeout as RequestsTimeout

from bobbi_core.search_completion import SearchCompletion, SearchResults
from lib.clients.base import BaseClient, TorrentStream
from lib.jacktook.utils import kodilog
from lib.utils.kodi.logging import summarize_locator_for_log
from lib.utils.kodi.settings import get_prowlarr_timeout
from lib.utils.kodi.utils import get_setting, notification, translation


class Prowlarr(BaseClient):
    def __init__(self, host: str, apikey: str, port: str, notification: Callable, *, settings_getter=None) -> None:
        super().__init__(host, notification)
        self.base_url = f"{self.host}:{port}/api/v1/search"
        self.apikey = apikey
        self._setting = settings_getter or (lambda key: get_setting(key))
        self._timeout = ((lambda: int(settings_getter('prowlarr_timeout', 20)))
                         if settings_getter is not None else lambda: get_prowlarr_timeout())

    @staticmethod
    def _parse_indexer_ids(indexers: Optional[str]) -> List[str]:
        if not indexers:
            return []
        return [i.strip() for i in str(indexers).replace(",", " ").split() if i.strip()]

    def _build_query_shards(
        self,
        query: str,
        mode: str,
        season: Optional[int],
        episode: Optional[int],
        indexers: Optional[str],
        year: Optional[int],
    ) -> List[Dict[str, Any]]:
        indexer_ids = self._parse_indexer_ids(indexers)
        shards: List[Dict[str, Any]] = []
        if mode == "tv" and season:
            if episode:
                params_ep: Dict[str, Any] = {
                    "query": f"{query} S{season:02d}E{episode:02d}",
                    "type": "search",
                    "categories": [5000, 8000],
                }
                if indexer_ids:
                    params_ep["indexerIds"] = indexer_ids
                shards.append(params_ep)
            if self._setting("include_season_packs"):
                params_season: Dict[str, Any] = {
                    "query": f"{query} S{season:02d}",
                    "type": "search",
                    "categories": [5000, 8000],
                }
                if indexer_ids:
                    params_season["indexerIds"] = indexer_ids
                shards.append(params_season)
            return shards

        query_with_year = f"{query} {year}" if (mode == "movies" and year) else query
        params: Dict[str, Any] = {
            "query": query_with_year,
            "type": "search",
        }
        if mode == "movies":
            params["categories"] = [2000, 8000]
        elif mode == "anime":
            params["categories"] = [2000, 5070, 5000, 127720, 140679]
        if indexer_ids:
            params["indexerIds"] = indexer_ids
        shards.append(params)
        return shards

    def search(
        self,
        query: str,
        mode: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        indexers: Optional[str] = None,
        variant=None,
        year: Optional[int] = None,
        *,
        cancelled=None,
        deadline: Optional[float] = None,
    ) -> SearchResults:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Api-Key": self.apikey,
        }
        season_num = self._coerce_int(season)
        episode_num = self._coerce_int(episode)
        try:
            shards = self._build_query_shards(query, mode, season_num, episode_num, indexers, year)
        except Exception as e:
            self.handle_exception(f"{translation(30230)}: {e!s}")
            return SearchResults([], SearchCompletion(1, failed=1))

        if not shards:
            return SearchResults([], SearchCompletion())

        results: List[TorrentStream] = []
        succeeded = 0
        failed = 0
        skipped = 0
        timed_out = 0
        is_cancelled = cancelled if callable(cancelled) else (lambda: False)

        for params in shards:
            if is_cancelled():
                skipped += 1
                continue
            try:
                configured_timeout = max(0.05, float(self._timeout()))
            except (TypeError, ValueError):
                configured_timeout = 20.0
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out += 1
                    continue
                req_timeout: Any = max(0.05, min(configured_timeout, remaining))
            else:
                req_timeout = configured_timeout

            try:
                response = self.session.get(
                    self.base_url,
                    params=params,
                    timeout=req_timeout,
                    headers=headers,
                )
            except (RequestsTimeout, TimeoutError) as e:
                timed_out += 1
                self.handle_exception(f"{translation(30230)}: {e!s}")
                continue
            except Exception as e:
                if "timeout" in type(e).__name__.casefold():
                    timed_out += 1
                else:
                    failed += 1
                self.handle_exception(f"{translation(30230)}: {e!s}")
                continue

            if is_cancelled():
                skipped += 1
                continue

            status_code = getattr(response, "status_code", None)
            if status_code != 200:
                failed += 1
                notification(f"{translation(30230)} {status_code}")
                continue

            try:
                parsed = self.parse_response(response)
            except Exception as e:
                failed += 1
                self.handle_exception(f"{translation(30230)}: {e!s}")
                continue

            succeeded += 1
            if parsed:
                results.extend(parsed)

        return SearchResults(
            results,
            SearchCompletion(
                planned=len(shards),
                succeeded=succeeded,
                failed=failed,
                skipped=skipped,
                timed_out=timed_out,
            ),
        )

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def parse_response(self, res: Any) -> List[TorrentStream]:
        response = res.json()
        if not isinstance(response, list):
            raise ValueError("Prowlarr response payload must be a JSON list")
        results = []
        for item in response:
            if not isinstance(item, dict):
                raise ValueError("Prowlarr result item must be a JSON object")
            title = item.get("title", "")
            provider = item.get("indexer")
            guid = item.get("guid", "")
            download_url = item.get("downloadUrl", "")
            magnet_url = item.get("magnetUrl", "")
            info_url = item.get("infoUrl", "")
            info_hash = item.get("infoHash", "")

            kodilog(
                "Prowlarr parsed result: title={!r}, provider={!r}, guid={!r}, download={!r}, magnet={!r}, info={!r}, infohash={!r}, has_magnet={}, has_http_url={}, has_infohash={}".format(
                    title,
                    provider,
                    summarize_locator_for_log(guid),
                    summarize_locator_for_log(download_url),
                    summarize_locator_for_log(magnet_url),
                    summarize_locator_for_log(info_url),
                    str(info_hash).lower()[:12],
                    bool(
                        str(magnet_url).startswith("magnet:?")
                        or str(download_url).startswith("magnet:?")
                        or str(guid).startswith("magnet:?")
                    ),
                    bool(
                        str(download_url).startswith(("http://", "https://"))
                        or str(info_url).startswith(("http://", "https://"))
                        or str(guid).startswith(("http://", "https://"))
                    ),
                    bool(info_hash),
                )
            )

            results.append(
                TorrentStream(
                    title=title,
                    type="Torrent",
                    indexer="Prowlarr",
                    provider=provider,
                    peers=int(item.get("peers") or 0),
                    seeders=int(item.get("seeders") or 0),
                    guid=guid,
                    infoHash=info_hash,
                    size=int(item.get("size") or 0),
                    languages=item.get("languages") if isinstance(item.get("languages"), list) else [],
                    fullLanguages=item.get("fullLanguages", ""),
                    publishDate=item.get("publishDate", ""),
                    url=download_url,
                )
            )
        return results

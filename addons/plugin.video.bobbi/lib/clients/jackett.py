import concurrent.futures
import re
from math import ceil
import time
import xml.etree.ElementTree as ET
from typing import Any, List, Optional
from urllib.parse import quote, urlencode, urlsplit

import requests
import xbmc

from lib.clients.base import BaseClient
from lib.domain.torrent import TorrentStream
from lib.jacktook.utils import kodilog
from lib.utils.general.utils import USER_AGENT_HEADER
from lib.utils.kodi.logging import summarize_locator_for_log
from lib.utils.kodi.settings import get_jackett_timeout
from lib.utils.kodi.utils import get_setting, notification, translation
from lib.utils.parsers import xmltodict


def _normalize_jackett_host(host: str) -> str:
    cleaned = str(host or "").strip().rstrip("/")
    if cleaned and not cleaned.startswith(("http://", "https://")):
        cleaned = "http://" + cleaned
    return cleaned


def discover_jackett_indexers(
    host: str,
    port: str,
    apikey: str,
    timeout: float = 4.0,
    session: Optional[requests.Session] = None,
) -> List[dict]:
    """Return configured Jackett sub-indexers as ``[{'id': ..., 'title': ...}, ...]``."""
    norm_host = _normalize_jackett_host(host)
    if not norm_host:
        return []
    clean_port = str(port or "").strip()
    parsed_host = urlsplit(norm_host)
    endpoint_base = f"{norm_host}:{clean_port}" if clean_port and parsed_host.port is None else norm_host
    url = f"{endpoint_base}/api/v2.0/indexers/all/results/torznab/api?apikey={quote(str(apikey or '').strip())}&t=indexers&configured=true"

    own_session = session is None
    sess = session or requests.Session()
    if own_session:
        sess.headers.update(USER_AGENT_HEADER.copy())
    try:
        response = sess.get(url, timeout=timeout)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    finally:
        if own_session:
            sess.close()

    items: List[dict] = []
    seen = set()
    for node in root.findall("indexer"):
        idx_id = (node.get("id") or "").strip()
        if node.get("configured") != "true" or not re.fullmatch(r"[a-zA-Z0-9_-]+", idx_id) or idx_id in seen:
            continue
        seen.add(idx_id)
        title = (node.findtext("title") or node.get("name") or idx_id).strip() or idx_id
        items.append({"id": idx_id, "title": title})
    return items


class Jackett(BaseClient):
    def __init__(
        self,
        host: str,
        apikey: str,
        port: str,
        notification,
        session: Optional[requests.Session] = None,
        *, settings_getter=None, disabled_indexers=None, profile_root=None,
    ) -> None:
        super().__init__(host, notification)
        self.apikey = apikey
        self.port = port
        self.host = host
        self.base_url = self._make_base_url("all")
        self.session = session or requests.Session()
        self.session.headers.update(USER_AGENT_HEADER.copy())
        self._configured_indexers = None
        self._indexer_caps = {}
        self._indexer_anime_caps = {}
        self._disabled_indexers = disabled_indexers
        self._profile_root = profile_root
        self._setting = settings_getter or (lambda key: get_setting(key))
        self._timeout = ((lambda: int(settings_getter('jackett_timeout', 20)))
                         if settings_getter is not None else lambda: get_jackett_timeout())

    def _get_disabled_indexers(self) -> frozenset:
        if self._disabled_indexers is not None:
            return frozenset(str(x).strip() for x in self._disabled_indexers if str(x).strip())
        try:
            from lib.utils.user_sources import load_user_sources

            prefs = load_user_sources(self._profile_root)
            return frozenset(prefs.get("disabled_jackett_indexers") or ())
        except Exception:
            return frozenset()

    @classmethod
    def search_custom_torznab(
        cls,
        source_spec: dict,
        query: str,
        mode: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        year: Optional[int] = None,
        *,
        title_queries=(),
        timeout: float = 8.0,
        deadline: Optional[float] = None,
        cancelled=None,
        session: Optional[requests.Session] = None,
    ):
        from bobbi_core.search_completion import SearchCompletion, SearchResults
        from lib.utils.user_sources import validate_torznab_url

        is_cancelled = cancelled or (lambda: False)
        if is_cancelled() or (deadline is not None and time.monotonic() >= deadline):
            return SearchResults([], SearchCompletion(1, timed_out=1))

        try:
            base_url = validate_torznab_url(source_spec.get("url", ""))
        except ValueError:
            return SearchResults([], SearchCompletion(1, failed=1))

        name = str(source_spec.get("name") or "Custom Torznab").strip() or "Custom Torznab"
        apikey = str(source_spec.get("apikey") or "").strip()
        params = {}
        if apikey and "apikey=" not in base_url.lower():
            params["apikey"] = apikey
        params["q"] = str(query or "").strip()
        if mode == "tv" and season is not None:
            params["t"] = "tvsearch"
            params["season"] = season
            if episode is not None:
                params["ep"] = episode
        elif mode == "movies":
            params["t"] = "movie"
            if year:
                params["year"] = year
        else:
            params["t"] = "search"

        sep = "&" if "?" in base_url else "?"
        req_url = base_url + sep + urlencode(params)
        remaining = (deadline - time.monotonic()) if deadline is not None else float(timeout)
        if remaining <= 0:
            return SearchResults([], SearchCompletion(1, timed_out=1))
        req_timeout = max(0.2, min(float(timeout), remaining))

        own_session = session is None
        sess = session or requests.Session()
        if own_session:
            sess.headers.update(USER_AGENT_HEADER.copy())
        try:
            response = sess.get(req_url, timeout=req_timeout)
            if response.status_code != 200:
                return SearchResults([], SearchCompletion(1, failed=1))
            parser = cls(host=base_url, apikey=apikey, port="", notification=lambda *a, **k: None, session=sess)
            parsed = parser.parse_response(response)
            if parsed is None:
                return SearchResults([], SearchCompletion(1, failed=1))
            for row in parsed:
                row.provider = f"{name} · {row.provider}" if row.provider and row.provider != name else name
            return SearchResults(parsed, SearchCompletion(1, succeeded=1))
        except requests.Timeout:
            return SearchResults([], SearchCompletion(1, timed_out=1))
        except Exception:
            return SearchResults([], SearchCompletion(1, failed=1))
        finally:
            if own_session:
                sess.close()

    def _search_cinema(self, query, mode, season, episode, categories,
                       additional_params, year, anime_absolute_query, anime_release_query='', title_queries=(), movie_years=None, movie_tmdb_id=None, movie_imdb_id=None, anime_title_queries=(), cancelled=None, deadline=None, publish=None, query_cache=None, slot_factory=None):
        """Keep successful per-indexer results, not Jackett's slow all wrapper.

        Discover only already-configured providers. Four globally admitted
        workers share an eight-second budget; a late DNS worker retains its
        admission but cannot publish after return. Identity filtering remains
        downstream and is applied equally to streamed and final candidates.
        """
        from lib.clients.jackett_fanout import fetch_independent, fetch_inventory
        from bobbi_core.search_completion import SearchCompletion, SearchResults
        cancelled = cancelled or (lambda: xbmc.Monitor().abortRequested() is True)
        # Interactive results stream immediately. Allow bounded supplementation
        # to use the existing user budget instead of abandoning most aliases at
        # eight seconds. Background callers still own their shorter deadline.
        budget = min(25, self._timeout()) if publish is not None else min(8, self._timeout())
        deadline = min(deadline if deadline is not None else float('inf'), time.monotonic() + budget)
        inventory_key = self.base_url + '&t=indexers&configured=true'
        if self._configured_indexers is None and query_cache is not None:
            cached_inventory = query_cache.get('jackett-inventory', inventory_key)
            if cached_inventory and self._valid_inventory(cached_inventory[0]):
                value = cached_inventory[0]
                self._configured_indexers = value['ids']
                self._indexer_caps = value['movie']
                self._indexer_anime_caps = value['anime']
        if self._configured_indexers is None:
            inventory = fetch_inventory(self.session, self.base_url + '&t=indexers&configured=true',
                                        deadline, cancelled, **({'slot_factory': slot_factory} if slot_factory is not None else {}))
            if not inventory:
                return SearchResults([], inventory.completion)
            discovery = inventory[0]
            discovery.raise_for_status()
            root = ET.fromstring(discovery.content)
            ids = [node.get('id') for node in root.findall('indexer')
                   if node.get('configured') == 'true' and re.fullmatch(r'[a-zA-Z0-9_-]+', node.get('id', ''))]
            if not ids or len(ids) > 16:
                raise ValueError('Configured indexer inventory is empty or too large')
            self._configured_indexers = ids
            self._indexer_caps = {node.get('id'): self._movie_caps(node.find('caps'))
                                  for node in root.findall('indexer') if node.get('id') in ids}
            self._indexer_anime_caps = {node.get('id'): self._anime_caps(node)
                                       for node in root.findall('indexer') if node.get('id') in ids}
            if query_cache is not None and not cancelled() and time.monotonic() < deadline:
                query_cache.put('jackett-inventory', inventory_key, [dict(ids=ids,
                    movie=self._indexer_caps, anime=self._indexer_anime_caps)])
        # Inventory is shared across titles, but scheduling belongs to this
        # search. A preceding movie must not change an anime's first work slots.
        self._configured_indexers = sorted(self._configured_indexers,
            key=lambda value: (bool(anime_absolute_query or anime_release_query)
                               and value not in ('nyaasi', 'tokyotosho'), value))
        disabled_indexers = self._get_disabled_indexers()
        if disabled_indexers:
            active_indexers = [idx for idx in self._configured_indexers if idx not in disabled_indexers]
            if not active_indexers:
                return SearchResults([], SearchCompletion())
            self._configured_indexers = active_indexers
        titles = list(dict.fromkeys([query] + [q for q in title_queries if isinstance(q, str) and q.strip()]))[:3]
        specs = [(title, mode, season, episode, False) for title in titles]
        include_packs = mode == 'tv' and season and self._setting('include_season_packs')
        if include_packs:
            specs.extend((title, mode, season, None, True) for title in titles)
        if anime_absolute_query and mode == 'tv' and str(season) == '1' and episode:
            specs.insert(0, (anime_absolute_query, 'anime', None, None, False))
        # Interleave catalog aliases within each provider, instead of making a
        # slow/irrelevant localized query consume a complete fallback round.
        if mode == 'movies':
            urls = self._movie_urls(titles, year, categories, additional_params,
                                    movie_years, movie_tmdb_id, movie_imdb_id)
        elif mode == 'tv' and (anime_title_queries or anime_absolute_query or anime_release_query):
            queries = anime_title_queries or [('unknown', title) for title in titles]
            urls = self._anime_urls(queries, season, episode, categories, additional_params)
        elif mode == 'tv':
            urls = self._tv_fallback_urls(titles, season, episode, categories, additional_params, include_packs)
        else:
            urls = [self._build_url(self._make_base_url(provider), title, kind, sn, ep,
                               categories, additional_params, season_pack=pack, year=release_year)
                for pack_value in (False, True) for provider in self._configured_indexers
                for title, kind, sn, ep, pack in specs if pack == pack_value
                for release_year in (year,)]
        if mode == 'movies' and anime_release_query and 'nyaasi' in self._configured_indexers:
            # Broad newest-first pages may omit older preferred releases.
            # Two explicit queries share the same budget; they are candidates,
            # not an exemption from title/season/episode/subtitle filtering.
            urls = [self._build_url(self._make_base_url('nyaasi'), anime_release_query + ' ' + group, 'anime')
                    for group in ('VCB-Studio', 'LoliHouse')] + urls
            # Torznab season/ep excludes releases using 第二季 [01] / S2 - 01.
            # One bounded native search also gives all groups equal discovery;
            # downstream full-alias and exact season/episode gates still apply.
            urls.insert(0, self._build_url(self._make_base_url('nyaasi'), query, 'anime'))
        from lib.clients.fanout_diagnostics import FanoutReceipt, make_plan, observe
        cached_rows, missing, cached_count, cached_age = [], [], 0, 0
        cache_observed_at = time.monotonic()
        for url in dict.fromkeys(urls):
            cached = query_cache.get('jackett-query', url) if query_cache is not None else None
            if cached is None:
                missing.append(url)
            else:
                cached_rows.extend(cached)
                cached_count += 1
                cached_age = max(cached_age, getattr(getattr(cached, 'completion', None), 'snapshot_age', 0))
        cached_completion = SearchCompletion(cached_count, succeeded=cached_count, snapshot_age=cached_age)
        if cached_rows and publish is not None and not cancelled() and time.monotonic() < deadline:
            publish(SearchResults(cached_rows, cached_completion))
        plan = make_plan(missing, query, mode, season, episode, year,
            title_queries, anime_title_queries, anime_absolute_query, anime_release_query,
            movie_tmdb_id, movie_imdb_id)
        request_timeout = 2.0
        if mode == 'tv' and (anime_title_queries or anime_absolute_query or anime_release_query):
            request_timeout = self._anime_request_timeout(urls, deadline)
        results, parse_failures, processed = list(cached_rows), 0, 0
        def parse_ready(response):
            nonlocal parse_failures, processed
            processed += 1
            if cancelled() or time.monotonic() >= deadline:
                parse_failures += 1
                return None
            parsed = self.parse_response(response)
            if parsed is None:
                parse_failures += 1
            else:
                results.extend(parsed)
                if query_cache is not None and not cancelled() and time.monotonic() < deadline:
                    key = getattr(response, '_bobbi_query_url', None)
                    if key is not None:
                        query_cache.put('jackett-query', key, parsed)
                if parsed and publish is not None and not cancelled() and time.monotonic() < deadline:
                    # The caller applies the same media/episode identity filter
                    # to streamed and final rows before the stable list session.
                    publish(SearchResults(parsed, SearchCompletion(1, succeeded=1)))
            return parsed
        # Leave a bounded settle margin inside the provider's original budget.
        # Successful responses are parsed on arrival, never discarded merely
        # because a different request runs to this network deadline.
        responses = fetch_independent(self.session, plan, budget=budget,
                                      deadline=deadline - .25, cancelled=cancelled,
                                      request_timeout=request_timeout, on_response=parse_ready,
                                      **({'slot_factory': slot_factory} if slot_factory is not None else {}))
        parse_failures += len(responses) - processed
        receipt = getattr(responses, 'fanout_receipt', None)
        receipt = receipt if isinstance(receipt, FanoutReceipt) else None
        if receipt is not None:
            observe(receipt, 'emit', 'parse_complete')
        kodilog('Cinema Jackett independent responses: {}/{}; candidates: {}'.format(len(responses), len(urls), len(results)))
        if cached_count:
            from dataclasses import replace
            cached_completion = replace(cached_completion,
                snapshot_age=cached_age + ceil(time.monotonic() - cache_observed_at))
        if isinstance(responses, SearchResults):
            completion = responses.completion.with_parse_failures(parse_failures).combine(cached_completion)
        else:
            # Compatibility with injected transports lacking a receipt is
            # conservative: missing responses can never claim completeness.
            planned = len(missing)
            completion = SearchCompletion(planned, len(responses) - parse_failures,
                                          planned - len(responses) + parse_failures).combine(cached_completion)
        kodilog('Cinema Jackett completion: {} {}'.format(completion.state, completion.summary()))
        result = SearchResults(results, completion)
        reference = observe(receipt, 'reference')
        if reference is not None:
            result.fanout_diagnostic_ref = reference
        return result

    @staticmethod
    def _valid_inventory(value):
        """A damaged optional snapshot must fall back to live discovery."""
        if not isinstance(value, dict):
            return False
        ids = value.get('ids')
        if (not isinstance(ids, list) or not 0 < len(ids) <= 16
                or any(not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', key) for key in ids)
                or len(set(ids)) != len(ids)):
            return False
        def params(fields):
            return fields is None or isinstance(fields, (set, frozenset, list, tuple)) and len(fields) <= 32 and all(
                isinstance(field, str) for field in fields)
        for kind in ('movie', 'anime'):
            mapping = value.get(kind)
            if not isinstance(mapping, dict) or any(key not in mapping for key in ids):
                return False
            for key in ids:
                caps = mapping[key]
                if kind == 'movie' and caps is None:
                    continue
                fields = ('search', 'movie-search') if kind == 'movie' else ('search', 'tv-search')
                if not isinstance(caps, dict) or any(field not in caps or not params(caps[field]) for field in fields):
                    return False
                if kind == 'movie':
                    categories = caps.get('categories')
                    if not isinstance(categories, (set, frozenset, list, tuple)) or any(type(cat) is not int for cat in categories):
                        return False
                else:
                    kinds = caps.get('release_types')
                    if (not isinstance(caps.get('language', ''), str) or not isinstance(kinds, dict)
                            or len(kinds) > 512 or any(not isinstance(k, str)
                            or not re.fullmatch(r'[0-9]{1,6}', k) or v not in ('animation', 'live_action')
                            for k, v in kinds.items())):
                        return False
        return True

    def _tv_fallback_urls(self, titles, season, episode, categories, additional_params, include_packs):
        """Replace each ordinary TV request using the existing inventory caps.

        Missing metadata must not make a generic-only provider receive tvsearch.
        Unknown capabilities permit bounded generic text, as for anime/movies.
        Partial TV-only searches use declared fields; downstream identity and
        exact-episode gates remain authoritative. No aliases or requests added.
        """
        common = {key: value for key, value in (additional_params or {}).items()
                  if str(key).lower() not in ('t', 'q', 'season', 'ep', 'cat', 'apikey')}
        if categories:
            common['cat'] = ','.join(map(str, categories))
        packs = (False, True) if include_packs else (False,)
        urls = []
        for pack in packs:
            target = {key: value for key, value in (('season', season), ('ep', None if pack else episode))
                      if value is not None and value != ''}
            required = {'q'} | set(target)
            for provider in self._configured_indexers[:16]:
                caps = self._indexer_anime_caps.get(provider, {})
                tv = caps.get('tv-search') or frozenset()
                generic = caps.get('search')
                generic = frozenset(('q',)) if generic is None else generic
                if required <= tv:
                    kind, fields = 'tvsearch', target
                elif 'q' in generic:
                    kind, fields = 'search', {}
                elif 'q' in tv:
                    kind, fields = 'tvsearch', {key: value for key, value in target.items() if key in tv}
                else:
                    continue
                base = self._make_base_url(provider)
                for title in titles[:3]:
                    params = dict(common, q=title, t=kind, **fields)
                    urls.append(base + '&' + urlencode(params))
        # Generic and partial queries often collapse the episode/pack pair.
        return list(dict.fromkeys(urls))

    @staticmethod
    def _anime_caps(indexer):
        # Custom Torznab category numbers are local to each indexer. The
        # existing configured-indexers request includes its category names.
        kinds = {}
        for node in indexer.iterfind('caps/categories//*'):
            key = node.get('id', '')
            if node.tag not in ('category', 'subcat') or not re.fullmatch(r'[0-9]{1,6}', key):
                continue
            label = node.get('name', '').strip().casefold().split(' - ', 1)[0]
            kind = {'live action':'live_action', 'live-action':'live_action', 'anime':'animation',
                    'tv/anime':'animation', 'movies/anime':'animation', 'animation':'animation'}.get(label)
            if kind:
                kinds[key] = kind if kinds.get(key, kind) == kind else ''
                if len(kinds) > 512:
                    kinds.clear()
                    break
        result = {'language': indexer.get('language') or indexer.findtext('language') or '',
                  'release_types': {k:v for k,v in kinds.items() if v}}
        for kind in ('search', 'tv-search'):
            node = indexer.find('caps/searching/' + kind)
            if node is not None and node.get('available') == 'no':
                result[kind] = frozenset()
            elif node is not None and node.get('available') == 'yes' and node.get('supportedParams') is not None:
                result[kind] = frozenset(value.strip().lower() for value in node.get('supportedParams').split(','))
            else:
                result[kind] = None
        return result

    @staticmethod
    def _anime_request_timeout(urls, deadline):
        """Give cold indexers a fair share of the existing first-round budget.

        A fixed two-second read timeout discarded cold Chinese indexers while
        an immediate identical search found their warmed results. The plan is
        already provider-round-robin: divide the remaining time by its first
        round's four-worker waves, not by all speculative alias requests.
        Leave startup/parse/reap headroom and never let one request take more
        than four seconds. The supervised batch still owns the hard deadline.
        """
        providers = len({urlsplit(url).path for url in urls})
        waves = max(1, (providers + 3) // 4)
        available = max(0.0, deadline - time.monotonic() - 0.8)
        return max(0.1, min(4.0, available / waves))

    def _anime_urls(self, queries, season, episode, categories, additional_params):
        """Fair provider rounds, never release-group-specific discovery.

        At most four ID-bound language aliases and twelve URLs per provider.
        First-season title+episode text avoids a newest-page-only response;
        broad titles remain for packs and alternative numbering conventions.
        Later seasons never guess absolute numbering. All downstream gates apply.
        The unchanged fanout owns the four-worker/eight-second shared budget.
        """
        from lib.utils.general.anime_identity import provider_anime_titles
        queries = [(language, title.strip()) for language, title in queries[:4]
                   if isinstance(language, str) and isinstance(title, str) and 2 <= len(title.strip()) <= 512]
        queues = []
        for provider in self._configured_indexers[:16]:
            caps = getattr(self, '_indexer_anime_caps', {}).get(provider, {})
            generic, tv = caps.get('search'), caps.get('tv-search')
            generic = frozenset(('q',)) if generic is None else generic
            tv = tv or frozenset()
            titles = provider_anime_titles(queries, caps.get('language'))
            base, urls = self._make_base_url(provider), []
            # Reserve each supported query mode for the preferred language
            # BEFORE expanding aliases. A fourth alias must not evict all packs.
            for title in titles:
                if 'q' in generic:
                    if str(season) == '1' and str(episode).isdigit() and 1 <= int(episode) <= 999:
                        urls.append(self._build_url(base, '{} {:02d}'.format(title, int(episode)), 'anime',
                            categories=categories, additional_params=additional_params))
                    urls.append(self._build_url(base, title, 'anime', categories=categories,
                        additional_params=additional_params))
                if {'q', 'season', 'ep'} <= tv and season and episode:
                    urls.append(self._build_url(base, title, 'tv', season, episode, categories,
                        additional_params))
                if {'q', 'season'} <= tv and season and self._setting('include_season_packs'):
                    urls.append(self._build_url(base, title, 'tv', season, None, categories,
                        additional_params, season_pack=True))
            queues.append(list(dict.fromkeys(urls))[:12])
        return [queue[index] for index in range(12) for queue in queues if index < len(queue)]

    @staticmethod
    def _movie_caps(caps):
        """Reuse the configured inventory; unknown caps never imply ID/year support."""
        if caps is None:
            return None
        result = {}
        for kind in ('search', 'movie-search'):
            node = caps.find('searching/' + kind)
            # Missing declarations are unknown, not an explicit disable.
            if node is not None and node.get('available') == 'no':
                result[kind] = frozenset()
            elif node is not None and node.get('available') == 'yes' and node.get('supportedParams') is not None:
                result[kind] = frozenset(value.strip().lower() for value in node.get('supportedParams').split(','))
            else:
                result[kind] = None
        result['categories'] = frozenset(int(node.get('id')) for node in caps.findall('categories//*')
            if re.fullmatch(r'[0-9]{4}', node.get('id', '')) and 2000 <= int(node.get('id')) < 3000)
        return result

    def _movie_urls(self, titles, year, categories, additional_params,
                    evidence, tmdb_id, imdb_id):
        """ID-first queues plus bounded text supplementation, in one shared fanout.

        At most 16 providers * 13 requests: one ID, then primary-year and
        broad text for each of at most three aliases, then alternate years.
        Broad text retains releases whose names omit a year; downstream gates
        still reject known conflicts. The cap truncates only the lowest
        priority alternate-year combinations after URL deduplication.
        Round-robin queues let every provider start before any gets a second
        slot. ID success/emptiness never suppresses the text supplement.
        """
        from bobbi_core.movie_years import accepted_years
        proven = accepted_years(evidence, tmdb_id, None)
        years = ((evidence.primary_year,) + tuple(y for y in proven if y != evidence.primary_year)
                 if proven else accepted_years(None, None, year) or (None,))
        queues = []
        for provider in self._configured_indexers[:16]:
            caps = self._indexer_caps.get(provider)
            movie = (caps['movie-search'] or frozenset()) if caps else frozenset()
            generic = caps['search'] if caps else None
            if generic is None:
                generic = frozenset(('q',))  # Unknown: only the bounded generic text plan.
            supported = caps['categories'] if caps else frozenset()
            requested = {str(value) for value in categories or ()}
            selected = sorted(value for value in supported if not requested or
                              str(value) in requested or '2000' in requested)
            if requested and not selected:
                # An explicit unsupported category must not become an all-site query.
                continue
            if not requested and 2000 in selected:
                selected = [2000]
            common = {key: value for key, value in (additional_params or {}).items()
                      if str(key).lower() not in ('t', 'q', 'year', 'cat', 'imdbid', 'tmdbid')}
            if selected:
                common['cat'] = ','.join(map(str, selected))
            params = []
            if proven and 'tmdbid' in movie:
                params.append(dict(t='movie', tmdbid=tmdb_id))
            elif proven and 'imdbid' in movie and isinstance(imdb_id, str) and re.fullmatch(r'tt[0-9]{7,12}', imdb_id):
                params.append(dict(t='movie', imdbid=imdb_id))
            kind = ('movie' if {'q', 'year'} <= movie else
                    'search' if 'q' in generic else 'movie' if 'q' in movie else None)
            if kind:
                for release_year in years[:4]:
                    for title in titles[:3]:
                        title = title.strip()
                        suffix = str(release_year) if release_year else ''
                        text = title if not suffix or re.search(r'(?:^|\s)' + suffix + r'$', title) else title + ' ' + suffix
                        query = dict(t=kind, q=text)
                        if kind == 'movie' and 'year' in movie and release_year:
                            query['year'] = release_year
                        params.append(query)
                        if release_year == years[0]:
                            params.append(dict(t=kind, q=title))
            base = self._make_base_url(provider)
            queues.append(list(dict.fromkeys(base + '&' + urlencode(dict(common, **query)) for query in params))[:13])
        return [queue[index] for index in range(13) for queue in queues if index < len(queue)]

    def _make_base_url(self, indexer_id: str) -> str:
        return f"{self.host}:{self.port}/api/v2.0/indexers/{indexer_id}/results/torznab/api?apikey={self.apikey}"

    def _build_url(
        self,
        base_url: str,
        query: str,
        mode: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        categories: Optional[List[int]] = None,
        additional_params: Optional[dict] = None,
        season_pack=False,
        year: Optional[int] = None,
    ) -> str:
        url = f"{base_url}&q={quote(query)}"
        if mode == "tv":
            url += "&t=tvsearch"
            if season_pack:
                url += f"&season={season}"
            else:
                url += f"&season={season}&ep={episode}"
        elif mode == "movies":
            url += "&t=movie"
        else:
            url += "&t=search"

        if categories:
            url += f"&cat={','.join(map(str, categories))}"

        if year and mode == "movies":
            url += f"&year={year}"

        if additional_params:
            for key, value in additional_params.items():
                url += f"&{key}={value}"

        return url

    def search_indexer(
        self,
        base_url,
        query: str,
        mode: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        categories: Optional[List[int]] = None,
        additional_params: Optional[dict] = None,
        year: Optional[int] = None,
        anime_absolute_query: str = '',
    ) -> Optional[List[TorrentStream]]:
        try:
            results = []
            futures = []
            with concurrent.futures.ThreadPoolExecutor() as executor:
                if anime_absolute_query and mode == 'tv' and str(season) == '1' and episode:
                    # Bounded parallel search: Torznab tvsearch season/ep loses
                    # common anime "- 01" releases. Normal episode filtering
                    # still runs downstream; this is not an autoplay decision.
                    anime_url = self._build_url(base_url, anime_absolute_query, 'anime')
                    futures.append(executor.submit(self.session.get, anime_url, timeout=self._timeout()))
                if mode == "tv" and season:
                    if episode:
                        url_ep = self._build_url(
                            base_url,
                            query,
                            mode,
                            season,
                            episode,
                            categories,
                            additional_params,
                            year=year,
                        )
                        futures.append(
                            executor.submit(self.session.get, url_ep, timeout=self._timeout())
                        )
                    if self._setting("include_season_packs"):
                        url_season = self._build_url(
                            base_url,
                            query,
                            mode,
                            season,
                            None,
                            categories,
                            additional_params,
                            season_pack=True,
                            year=year,
                        )
                        futures.append(
                            executor.submit(
                                self.session.get,
                                url_season,
                                timeout=self._timeout(),
                            )
                        )
                else:
                    url = self._build_url(
                        base_url,
                        query,
                        mode,
                        season,
                        episode,
                        categories,
                        additional_params,
                        year=year,
                    )
                    futures.append(
                        executor.submit(self.session.get, url, timeout=self._timeout())
                    )

            for future in concurrent.futures.as_completed(futures):
                try:
                    response = future.result()
                except requests.RequestException as error:
                    # An optional anime query failure must not discard the
                    # successful normal episode query (or the reverse).
                    kodilog('Jackett request failed: ' + type(error).__name__)
                    continue
                if response.status_code == 200:
                    res = self.parse_response(response)
                    if res:
                        results.extend(res)
                else:
                    notification(f"{translation(30229)} ({response.status_code})")
            return results if results else None
        except Exception as e:
            self.handle_exception(f"{translation(30229)}: {e!s}")
            return None

    def search(
        self,
        query: str,
        mode: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        categories: Optional[List[int]] = None,
        additional_params: Optional[dict] = None,
        variant=None,
        year: Optional[int] = None,
        anime_absolute_query: str = '',
        anime_release_query: str = '',
        title_queries=(),
        movie_years=None,
        movie_tmdb_id=None,
        movie_imdb_id=None,
        anime_title_queries=(),
        cancelled=None,
        deadline=None,
        publish=None,
        query_cache=None,
        slot_factory=None,
    ) -> Optional[List[TorrentStream]]:
        try:
            if xbmc.getSkinDir() == 'skin.bobbi.cinema':
                try:
                    return self._search_cinema(query, mode, season, episode, categories,
                                               additional_params, year, anime_absolute_query, anime_release_query, title_queries, movie_years, movie_tmdb_id, movie_imdb_id, anime_title_queries, cancelled, deadline, publish, query_cache, slot_factory)
                except requests.Timeout:
                    # A timed-out inventory request precedes the bounded fanout.
                    from bobbi_core.search_completion import SearchCompletion, SearchResults
                    return SearchResults([], SearchCompletion(1, timed_out=1))
            return self.search_indexer(
                self.base_url,
                query,
                mode,
                season,
                episode,
                categories,
                additional_params,
                year=year,
                **({'anime_absolute_query': anime_absolute_query} if anime_absolute_query else {}),
            )
        except Exception as e:
            self.handle_exception(f"{translation(30229)}: {e!s}")
            return None

    def parse_response(self, res: Any) -> Optional[List[TorrentStream]]:
        try:
            if getattr(res, '_am6b_parse_failed', False) is True:
                return None
            # This URL is set by the fanout from its own task ordinal, not
            # taken from a release/feed. Never join one tracker's IDs to another.
            bound_url = getattr(res, '_bobbi_query_url', None)
            path = urlsplit(bound_url).path if isinstance(bound_url, str) else ''
            source = re.search(r'/api/v2\.0/indexers/([a-zA-Z0-9_-]+)/results/torznab/api$', path)
            indexer_id = source[1] if source else ''
            # Actual network RSS has already been parsed in the bounded HTTP
            # worker. Legacy/injected response fixtures still use this parser.
            supervised_items = getattr(res, '_am6b_items', None)
            if isinstance(supervised_items, list):
                results = []
                for item in supervised_items:
                    self.extract_result(results, item, indexer_id)
                return results
            # HTTP200 <error>/HTML is not an authoritative empty search.
            root = ET.fromstring(res.content)
            channels = [child for child in root if child.tag.rsplit('}', 1)[-1] == 'channel']
            if (root.tag.rsplit('}', 1)[-1] != 'rss' or len(channels) != 1
                    or any(node.tag.rsplit('}', 1)[-1] == 'error' for node in root.iter())):
                raise ValueError('Invalid RSS search response')
            res_dict = xmltodict.parse(res.content)
            if res_dict:
                rss = res_dict.get('rss')
                if not isinstance(rss, dict) or 'channel' not in rss:
                    raise ValueError('Unsupported RSS root/channel namespace')
                channel = rss['channel'] or {}
                if not isinstance(channel, dict):
                    raise ValueError('Unsupported RSS channel structure')
                items = channel.get("item")
                expected_items = sum(child.tag.rsplit('}', 1)[-1] == 'item' for child in channels[0])
                mapped_items = (len(items) if isinstance(items, list) else 1) if items is not None else 0
                if expected_items != mapped_items or (expected_items and not items):
                    raise ValueError('Unsupported RSS item namespace/structure')
                if not items:
                    return []
                results: List[TorrentStream] = []
                for item in items if isinstance(items, list) else [items]:
                    self.extract_result(results, item, indexer_id)
                kodilog(f"Parsed {len(results)} results from Jackett")
                return results
        except Exception as e:
            self.handle_exception(f"Error parsing Jackett response: {e!s}")
            return None

    def extract_result(self, results: List[TorrentStream], item: dict, indexer_id='') -> None:
        attrs = item.get("torznab:attr", [])
        if isinstance(attrs, dict):
            attrs = [attrs]
        attributes = {attr.get("@name"): attr.get("@value") for attr in attrs}
        enclosure = item.get("enclosure", {})
        if not isinstance(enclosure, dict):
            enclosure = {}
        link = item.get("link", "")
        guid = item.get("guid", "")
        info_hash = str(attributes.get("infohash", ""))
        enclosure_url = enclosure.get("@url", "")
        indexer = item.get("jackettindexer")
        indexer = indexer if isinstance(indexer, dict) else {}
        provider = indexer.get("#text", "")
        release_type = ''
        if indexer_id and indexer.get('@id') == indexer_id:
            mapping = self._indexer_anime_caps.get(indexer_id, {}).get('release_types', {})
            # A row may supply both generic TV and a specific category, via
            # either RSS or repeated Torznab attributes. Mixed evidence is unknown.
            categories = item.get('category', [])
            cats = categories if isinstance(categories, list) else [categories]
            tagged = [a.get('@value') for a in attrs if a.get('@name') == 'category']
            kinds = {mapping[c] for c in (*cats, *tagged) if isinstance(c, str) and c in mapping}
            if len(kinds) == 1:
                release_type = kinds.pop()

        kodilog(
            "Jackett parsed result: title={!r}, provider={!r}, guid={!r}, link={!r}, enclosure={!r}, infohash={!r}, has_magnet={}, has_http_url={}, has_infohash={}".format(
                item.get("title", ""),
                provider,
                summarize_locator_for_log(guid),
                summarize_locator_for_log(link),
                summarize_locator_for_log(enclosure_url),
                info_hash[:12].lower(),
                bool(str(link).startswith("magnet:?") or str(guid).startswith("magnet:?")),
                bool(
                    str(link).startswith(("http://", "https://"))
                    or str(guid).startswith(("http://", "https://"))
                    or str(enclosure_url).startswith(("http://", "https://"))
                ),
                bool(info_hash),
            )
        )

        results.append(
            TorrentStream(
                title=item.get("title", ""),
                type="Torrent",
                indexer="Jackett",
                publishDate=item.get("pubDate", ""),
                provider=provider,
                guid=guid,
                url=link,
                size=item.get("size", ""),
                seeders=int(attributes.get("seeders", 0) or 0),
                peers=int(attributes.get("peers", 0) or 0),
                infoHash=info_hash,
                jackettReleaseType=release_type,
                languages=[],
                fullLanguages="",
            )
        )

import concurrent.futures
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, List, Optional
from urllib.parse import quote, urlencode, urlsplit

import requests
import xbmc

from lib.clients.base import BaseClient
from lib.domain.torrent import TorrentStream
from lib.bobbi.utils import kodilog
from lib.utils.general.utils import USER_AGENT_HEADER
from lib.utils.kodi.logging import summarize_locator_for_log
from lib.utils.kodi.settings import get_jackett_timeout
from lib.utils.kodi.utils import get_setting, notification, translation
from lib.utils.parsers import xmltodict


class Jackett(BaseClient):
    def __init__(
        self,
        host: str,
        apikey: str,
        port: str,
        notification,
        session: Optional[requests.Session] = None,
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

    def _search_cinema(self, query, mode, season, episode, categories,
                       additional_params, year, anime_absolute_query, anime_release_query='', title_queries=(), movie_years=None, movie_tmdb_id=None, movie_imdb_id=None, anime_title_queries=(), cancelled=None, deadline=None):
        """Keep successful per-indexer results, not Jackett's slow all wrapper.

        Discover only already-configured providers. Four transient workers,
        shared eight-second request budget; never keep Kodi threads alive after
        returning. Ranking and exact episode/title filtering remain downstream.
        """
        from lib.clients.jackett_fanout import fetch_independent, fetch_inventory
        from bobbi_core.search_completion import SearchCompletion, SearchResults
        cancelled = cancelled or (lambda: xbmc.Monitor().abortRequested() is True)
        deadline = min(deadline if deadline is not None else float('inf'),
                       time.monotonic() + min(8, get_jackett_timeout()))
        if self._configured_indexers is None:
            inventory = fetch_inventory(self.session, self.base_url + '&t=indexers&configured=true',
                                        deadline, cancelled)
            if not inventory:
                return SearchResults([], inventory.completion)
            discovery = inventory[0]
            discovery.raise_for_status()
            root = ET.fromstring(discovery.content)
            ids = [node.get('id') for node in root.findall('indexer')
                   if node.get('configured') == 'true' and re.fullmatch(r'[a-zA-Z0-9_-]+', node.get('id', ''))]
            if not ids or len(ids) > 16:
                raise ValueError('Configured indexer inventory is empty or too large')
            # Anime-specialist providers must get work slots before broad sites.
            ids.sort(key=lambda value: (bool(anime_absolute_query or anime_release_query)
                                       and value not in ('nyaasi', 'tokyotosho'), value))
            self._configured_indexers = ids
            self._indexer_caps = {node.get('id'): self._movie_caps(node.find('caps'))
                                  for node in root.findall('indexer') if node.get('id') in ids}
            self._indexer_anime_caps = {node.get('id'): self._anime_caps(node)
                                       for node in root.findall('indexer') if node.get('id') in ids}
        titles = list(dict.fromkeys([query] + [q for q in title_queries if isinstance(q, str) and q.strip()]))[:3]
        specs = [(title, mode, season, episode, False) for title in titles]
        include_packs = mode == 'tv' and season and get_setting('include_season_packs')
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
        plan = make_plan(list(dict.fromkeys(urls)), query, mode, season, episode, year,
            title_queries, anime_title_queries, anime_absolute_query, anime_release_query,
            movie_tmdb_id, movie_imdb_id)
        request_timeout = 2.0
        if mode == 'tv' and (anime_title_queries or anime_absolute_query or anime_release_query):
            request_timeout = self._anime_request_timeout(urls, deadline)
        responses = fetch_independent(self.session, plan, budget=min(8, get_jackett_timeout()),
                                      deadline=deadline, cancelled=cancelled,
                                      request_timeout=request_timeout)
        results, parse_failures = [], 0
        receipt = getattr(responses, 'fanout_receipt', None)
        receipt = receipt if isinstance(receipt, FanoutReceipt) else None
        parse_stage = 'parse_complete'
        try:
            for index, response in enumerate(responses):
                if cancelled() or time.monotonic() >= deadline:
                    parse_failures += len(responses) - index
                    for skipped_index in range(index, len(responses)):
                        observe(receipt, 'parse_end', skipped_index, None)
                    break
                if receipt is not None:
                    observe(receipt, 'parse_start', index)
                try:
                    parsed = self.parse_response(response)
                except BaseException:
                    if receipt is not None:
                        observe(receipt, 'parse_end', index, exception=True)
                    raise
                if receipt is not None:
                    observe(receipt, 'parse_end', index, parsed)
                if parsed is None:
                    parse_failures += 1
                else:
                    results.extend(parsed)
        except BaseException:
            parse_stage = 'parse_exception'
            raise
        finally:
            if receipt is not None:
                observe(receipt, 'emit', parse_stage)
        kodilog('Cinema Jackett independent responses: {}/{}; candidates: {}'.format(len(responses), len(urls), len(results)))
        if isinstance(responses, SearchResults):
            completion = responses.completion.with_parse_failures(parse_failures)
        else:
            # Compatibility with injected transports lacking a receipt is
            # conservative: missing responses can never claim completeness.
            planned = len(set(urls))
            completion = SearchCompletion(planned, len(responses) - parse_failures,
                                          planned - len(responses) + parse_failures)
        kodilog('Cinema Jackett completion: {} {}'.format(completion.state, completion.summary()))
        result = SearchResults(results, completion)
        reference = observe(receipt, 'reference')
        if reference is not None:
            result.fanout_diagnostic_ref = reference
        return result

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
        result = {'language': indexer.get('language') or indexer.findtext('language') or ''}
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
                if {'q', 'season'} <= tv and season and get_setting('include_season_packs'):
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
                    futures.append(executor.submit(self.session.get, anime_url, timeout=get_jackett_timeout()))
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
                            executor.submit(self.session.get, url_ep, timeout=get_jackett_timeout())
                        )
                    if get_setting("include_season_packs"):
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
                                timeout=get_jackett_timeout(),
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
                        executor.submit(self.session.get, url, timeout=get_jackett_timeout())
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
    ) -> Optional[List[TorrentStream]]:
        try:
            if xbmc.getSkinDir() == 'skin.bobbi.cinema':
                try:
                    return self._search_cinema(query, mode, season, episode, categories,
                                               additional_params, year, anime_absolute_query, anime_release_query, title_queries, movie_years, movie_tmdb_id, movie_imdb_id, anime_title_queries, cancelled, deadline)
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
            # Actual network RSS has already been parsed in the supervised
            # child. Legacy/injected response fixtures still use this parser.
            supervised_items = getattr(res, '_am6b_items', None)
            if isinstance(supervised_items, list):
                results = []
                for item in supervised_items:
                    self.extract_result(results, item)
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
                    self.extract_result(results, item)
                kodilog(f"Parsed {len(results)} results from Jackett")
                return results
        except Exception as e:
            self.handle_exception(f"Error parsing Jackett response: {e!s}")
            return None

    def extract_result(self, results: List[TorrentStream], item: dict) -> None:
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
        provider = item.get("jackettindexer", {}).get("#text", "")

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
                languages=[],
                fullLanguages="",
            )
        )

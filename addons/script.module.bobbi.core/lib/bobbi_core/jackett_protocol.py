"""Bounded, headless Jackett discovery. Every result is an unverified candidate.

The configured-indexer inventory, Torznab paths and XML fields match the Kodi
Jackett adapter. No Kodi modules, settings readers, UI callbacks or provider
writes are imported here. The caller supplies the exact numeric-IP HTTP endpoint
and private API key. Search evidence never replaces authoritative torrent file
metadata, catalog identity, release matching or cloud qualification.

One wall-clock budget covers inventory, all requests and parsing. A joined
watchdog shuts down active sockets at the deadline, including slow response
headers/bodies. Numeric endpoints avoid an uninterruptible DNS lookup. Socket
connect still relies on its OS timeout; cancellation cannot interrupt a connect
before the socket is returned, but its result is rejected. Cancellation predicates
must be nonblocking (for example Event.is_set). No HTTP/TLS redirect is followed.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
import base64
import hashlib
import http.client
import ipaddress
import math
import re
import socket
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import xml.etree.ElementTree as ET


CONNECT_TIMEOUT = 3.05
READ_TIMEOUT = 8.0
MAX_BUDGET = 8.0
MAX_INDEXERS = 16
MAX_CANDIDATES = 64
MAX_ITEMS = 512
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_INVENTORY_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_WORKERS = 4
_INDEXER = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class JackettProtocolError(ValueError):
    """A fixed diagnostic code; never retain response text or a locator."""

    def __init__(self, code):
        self.code = code
        super().__init__('Jackett protocol: ' + code)


@dataclass(frozen=True)
class Candidate:
    key: str
    info_hash: str
    link: str = field(repr=False)
    title: str = field(repr=False)
    bytes: object
    category: tuple
    indexer: str


@dataclass(frozen=True)
class SearchResult:
    candidates: tuple
    indexers: tuple
    errors: tuple
    complete: bool
    state: str = 'CANDIDATES_ONLY_NOT_READY'


@dataclass(frozen=True)
class AbsoluteEpisodeQuery:
    """Caller-proven mapping context, not a verification API or ready flag.

    The caller must obtain this context from its trusted mapping/catalog path.
    This adapter checks its shape and target binding only. In particular it does
    not prove that any search-result hash belongs to the mapped anime/cour.
    """

    title: str = field(repr=False)
    media_id: str
    season: int
    episode: int
    absolute_episode: int
    source_info_hash: str
    provenance: str
    mapping_sha256: str

    def query_for(self, tmdb_id, season, episode):
        if (self.media_id != 'tmdb:' + str(tmdb_id)
                or self.season != season or self.episode != episode
                or type(self.season) is not int or type(self.episode) is not int
                or not _positive(self.absolute_episode)
                or _hash(self.source_info_hash) != self.source_info_hash
                or not self.source_info_hash
                or not isinstance(self.provenance, str)
                or not re.fullmatch(r'[a-z][a-z0-9._:-]{0,95}', self.provenance)
                or not isinstance(self.mapping_sha256, str)
                or not _SHA256.fullmatch(self.mapping_sha256)):
            raise JackettProtocolError('invalid_absolute_binding')
        return '{} {:02d}'.format(_text(self.title, 512), self.absolute_episode)


def _positive(value):
    return type(value) is int and 1 <= value <= 100000


def _text(value, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise JackettProtocolError('invalid_text')
    return value.strip()


def _hash(value):
    if not isinstance(value, str):
        return ''
    if re.fullmatch(r'[0-9a-fA-F]{40}', value):
        return value.lower()
    if re.fullmatch(r'[A-Za-z2-7]{32}', value):
        return base64.b32decode(value.upper()).hex()
    return ''


def _tag(element):
    return element.tag.rsplit('}', 1)[-1]


def _xml(raw, limit):
    if not isinstance(raw, bytes) or not raw or len(raw) > limit:
        raise JackettProtocolError('response_size')
    try:
        document = raw.decode('utf-8-sig')
        if '\x00' in document or '<!doctype' in document.lower() or '<!entity' in document.lower():
            raise JackettProtocolError('unsafe_xml')
        parser = ET.XMLPullParser(events=('start', 'end'))
        root, depth, nodes = None, 0, 0
        for offset in range(0, len(document), 4096):
            parser.feed(document[offset:offset + 4096])
            for event, element in parser.read_events():
                if event == 'start':
                    root = element if root is None else root
                    depth, nodes = depth + 1, nodes + 1
                    if depth > 32 or nodes > 8192:
                        raise JackettProtocolError('xml_complexity')
                else:
                    depth -= 1
        parser.close()
        return root
    except (UnicodeError, ET.ParseError):
        raise JackettProtocolError('invalid_xml') from None


def parse_inventory(raw):
    root = _xml(raw, MAX_INVENTORY_BYTES)
    if root is None or _tag(root) != 'indexers':
        raise JackettProtocolError('invalid_inventory')
    configured = [item for item in root if _tag(item) == 'indexer' and item.get('configured') == 'true']
    if len(configured) > MAX_INDEXERS:
        raise JackettProtocolError('too_many_indexers')
    indexers = {item.get('id', '') for item in configured
                if _INDEXER.fullmatch(item.get('id', '')) and item.get('id') != 'all'}
    if not indexers:
        raise JackettProtocolError('empty_inventory')
    return tuple(sorted(indexers, key=lambda value: (value not in ('nyaasi', 'tokyotosho'), value)))


def _one(item, name):
    values = [child for child in item if _tag(child) == name]
    if len(values) > 1:
        raise JackettProtocolError('ambiguous_item')
    return (values[0].text or '').strip() if values else ''


def _locator(value):
    if not isinstance(value, str) or not value or len(value) > 8192 or any(ord(c) < 32 for c in value):
        return '', ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme == 'magnet' and not parsed.netloc and not parsed.path:
            hashes = {_hash(v[9:]) for v in parse_qs(parsed.query).get('xt', []) if v.lower().startswith('urn:btih:')}
            if len(hashes) == 1 and '' not in hashes:
                return value, next(iter(hashes))
        elif (parsed.scheme in ('http', 'https') and parsed.hostname
              and not parsed.username and not parsed.password and not parsed.fragment):
            parsed.port  # Reject malformed/overflow ports without echoing the URL.
            return value, ''
    except ValueError:
        pass
    return '', ''


def _candidate(item, indexer):
    title = _text(_one(item, 'title'), 1024)
    attrs = {}
    for attr in item:
        if _tag(attr) == 'attr':
            key, value = attr.get('name', ''), attr.get('value', '')
            attrs.setdefault(key, []).append(value)
    reported = attrs.get('infohash', [])
    hashes = {_hash(value) for value in reported}
    if '' in hashes or len(hashes) > 1:
        raise JackettProtocolError('invalid_infohash')
    enclosures = [child for child in item if _tag(child) == 'enclosure']
    locators = [_one(item, 'link'), _one(item, 'guid')]
    locators += [item.get('url', '') for item in enclosures] + attrs.get('magneturl', [])
    valid = []
    for value in locators:
        link, info_hash = _locator(value)
        if link:
            valid.append(link)
        if info_hash:
            hashes.add(info_hash)
    if len(hashes) > 1:
        raise JackettProtocolError('conflicting_infohash')
    info_hash = next(iter(hashes), '')
    link = valid[0] if valid else ('magnet:?xt=urn:btih:' + info_hash if info_hash else '')
    if not link:
        raise JackettProtocolError('missing_locator')
    sizes = [_one(item, 'size')] + attrs.get('size', []) + [child.get('length', '') for child in enclosures]
    numbers = set()
    for value in sizes:
        if value:
            if not re.fullmatch(r'[0-9]{1,19}', value) or not 0 < int(value) <= 2 ** 63 - 1:
                raise JackettProtocolError('invalid_size')
            numbers.add(int(value))
    if len(numbers) > 1:
        raise JackettProtocolError('conflicting_size')
    categories = attrs.get('category', []) + [(child.text or '').strip() for child in item if _tag(child) == 'category']
    categories = tuple(sorted({int(value) for value in categories if re.fullmatch(r'[0-9]{1,6}', value)}))
    key = 'btih:' + info_hash if info_hash else 'locator:' + hashlib.sha256(link.encode()).hexdigest()
    return Candidate(key, info_hash, link, title, next(iter(numbers), None), categories, indexer)


def parse_candidates(raw, indexer):
    if not isinstance(indexer, str) or not _INDEXER.fullmatch(indexer) or indexer == 'all':
        raise JackettProtocolError('invalid_indexer')
    root = _xml(raw, MAX_RESPONSE_BYTES)
    if root is None or _tag(root) != 'rss':
        raise JackettProtocolError('invalid_results')
    channels = [child for child in root if _tag(child) == 'channel']
    if len(channels) != 1:
        raise JackettProtocolError('invalid_results')
    items = [child for child in channels[0] if _tag(child) == 'item']
    if len(items) > MAX_ITEMS:
        raise JackettProtocolError('too_many_items')
    result = []
    for item in items:
        try:
            result.append(_candidate(item, indexer))
        except JackettProtocolError:
            continue  # Malformed siblings cannot manufacture or erase a candidate.
    return tuple(result)


class _Budget:
    def __init__(self, seconds, cancelled):
        self.deadline = time.monotonic() + seconds
        self.cancelled = cancelled
        self.reason = ''
        self.sockets = set()
        self.bytes = 0
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.watchdog = threading.Thread(target=self._watch, name='cinema-jackett-deadline')

    def remaining(self):
        self.check()
        return max(.001, self.deadline - time.monotonic())

    def _reason(self):
        try:
            if self.cancelled():
                return 'cancelled'
        except Exception:
            return 'cancelled'
        return 'deadline' if time.monotonic() >= self.deadline else ''

    def check(self):
        reason = self._reason() or self.reason
        if reason:
            raise JackettProtocolError(reason)

    def consume(self, count):
        self.check()
        with self.lock:
            self.bytes += count
            if self.bytes > MAX_TOTAL_BYTES:
                self.reason = 'total_response_size'
                raise JackettProtocolError(self.reason)

    def attach(self, sock):
        with self.lock:
            self.sockets.add(sock)
        self.check()

    def detach(self, sock):
        with self.lock:
            self.sockets.discard(sock)

    def _watch(self):
        while not self.stop.wait(.02):
            reason = self._reason() or self.reason
            if reason:
                self.reason = reason
                with self.lock:
                    active = tuple(self.sockets)
                for sock in active:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                return

    def __enter__(self):
        self.check()
        self.watchdog.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.watchdog.join()


class JackettProtocol:
    """Numeric-IP HTTP adapter. Supply secrets privately; never log its inputs."""

    def __init__(self, endpoint, api_key):
        try:
            parsed = urlsplit(endpoint)
            ipaddress.ip_address(parsed.hostname or '')
            if (parsed.scheme != 'http' or not parsed.port or parsed.path not in ('', '/')
                    or parsed.query or parsed.fragment or parsed.username or parsed.password):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise JackettProtocolError('invalid_numeric_http_endpoint') from None
        self._host, self._port = parsed.hostname, parsed.port
        self._api_key = _text(api_key, 256)

    def _path(self, indexer, params):
        if not _INDEXER.fullmatch(indexer):
            raise JackettProtocolError('invalid_indexer')
        return '/api/v2.0/indexers/{}/results/torznab/api?{}'.format(
            indexer, urlencode(dict(apikey=self._api_key, **params)))

    def _request(self, path, budget, limit):
        connection, response, active_socket = None, None, None
        try:
            connection = http.client.HTTPConnection(self._host, self._port,
                timeout=min(CONNECT_TIMEOUT, budget.remaining()))
            connection.connect()
            active_socket = connection.sock
            budget.attach(active_socket)
            active_socket.settimeout(min(READ_TIMEOUT, budget.remaining()))
            connection.request('GET', path, headers={'Accept': 'application/xml',
                'Accept-Encoding': 'identity', 'Connection': 'close', 'User-Agent': 'BobiTV-Jackett/1'})
            response = connection.getresponse()
            budget.check()
            if response.status != 200:
                raise JackettProtocolError('authentication' if response.status in (401, 403) else 'http_status')
            if response.getheader('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                raise JackettProtocolError('unsupported_encoding')
            length = response.getheader('Content-Length')
            if length is not None and (not length.isdigit() or int(length) > limit):
                raise JackettProtocolError('response_size')
            data = bytearray()
            while True:
                budget.check()
                block = response.read1(min(65536, limit + 1 - len(data)))
                budget.check()
                if not block:
                    if length is not None and len(data) != int(length):
                        raise JackettProtocolError('truncated_response')
                    return bytes(data)
                budget.consume(len(block))
                data.extend(block)
                if len(data) > limit:
                    raise JackettProtocolError('response_size')
        except JackettProtocolError:
            raise
        except (OSError, http.client.HTTPException, ValueError):
            budget.check()
            raise JackettProtocolError('transport_error') from None
        finally:
            if response is not None:
                response.close()
            if active_socket is not None:
                budget.detach(active_socket)
            if connection is not None:
                connection.close()

    def search_tv(self, title, tmdb_id, season, episode, *, absolute_query=None,
                  cancelled=lambda: False, budget=MAX_BUDGET, candidate_priority=None):
        title = _text(title, 512)
        if (type(tmdb_id) is not int or tmdb_id <= 0 or not _positive(season)
                or not _positive(episode) or not callable(cancelled)):
            raise JackettProtocolError('invalid_target')
        if type(budget) not in (float, int) or not math.isfinite(budget) or not 0 < budget <= MAX_BUDGET:
            raise JackettProtocolError('invalid_budget')
        if candidate_priority is not None and not callable(candidate_priority):
            raise JackettProtocolError('invalid_candidate_priority')
        specs = [dict(q=title, t='tvsearch', season=season, ep=episode)]
        if absolute_query is not None:
            if not isinstance(absolute_query, AbsoluteEpisodeQuery):
                raise JackettProtocolError('invalid_absolute_binding')
            specs.insert(0, dict(q=absolute_query.query_for(tmdb_id, season, episode), t='search'))
        with _Budget(budget, cancelled) as scope:
            raw = self._request(self._path('all', dict(t='indexers', configured='true')), scope, MAX_INVENTORY_BYTES)
            indexers = parse_inventory(raw)
            scope.check()
            jobs = [(indexer, spec) for spec in specs for indexer in indexers]
            results, errors = {}, []
            def fetch(indexer, spec):
                response = self._request(self._path(indexer, spec), scope, MAX_RESPONSE_BYTES)
                candidates = parse_candidates(response, indexer)
                scope.check()
                return candidates
            with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix='cinema-jackett') as executor:
                futures = {executor.submit(fetch, indexer, spec): position
                           for position, (indexer, spec) in enumerate(jobs)}
                for future in as_completed(futures):
                    position = futures[future]
                    try:
                        results[position] = future.result()
                    except JackettProtocolError as error:
                        errors.append((jobs[position][0], error.code))
            # Only cancellation invalidates already-finished siblings. A deadline
            # may return earlier candidates, explicitly marked incomplete.
            if scope._reason() == 'cancelled' or scope.reason == 'cancelled':
                raise JackettProtocolError('cancelled')
            if scope.reason and not any(code == scope.reason for _, code in errors):
                errors.append(('', scope.reason))
            candidates, sizes, conflicting = {}, {}, set()
            for position in sorted(results):
                for candidate in results[position]:
                    previous = candidates.get(candidate.key)
                    if candidate.bytes is not None:
                        if sizes.setdefault(candidate.key, candidate.bytes) != candidate.bytes:
                            conflicting.add(candidate.key)
                    if previous is None or (candidate_priority is not None
                            and candidate_priority(candidate) < candidate_priority(previous)):
                        candidates[candidate.key] = candidate
            for key in conflicting:
                # Indexers report rounded or differently scaled display sizes.
                # A common BTIH still names one torrent; clear the untrusted
                # size hint, not the candidate. Actual metadata/file proof and
                # cloud byte qualification remain mandatory downstream.
                candidates[key] = replace(candidates[key], bytes=None)
            if conflicting:
                errors.append(('', 'conflicting_candidate_size'))
            if len(candidates) > MAX_CANDIDATES:
                errors.append(('', 'candidate_limit'))
            ordered = list(candidates.values())
            if candidate_priority is not None:
                # Caller-owned pure rank only: no IO, readiness or filtering.
                # Ranking after the cap loses relevant older releases behind
                # unrelated newest-first results returned by broad indexers.
                ordered.sort(key=candidate_priority)
            bounded = tuple(ordered[:MAX_CANDIDATES])
            final_reason = scope._reason() or scope.reason
            if final_reason == 'cancelled':
                raise JackettProtocolError('cancelled')
            if final_reason and not any(code == final_reason for _, code in errors):
                errors.append(('', final_reason))
            return SearchResult(bounded, indexers, tuple(sorted(set(errors))), not errors)

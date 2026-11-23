"""Pinned, paired local TorrServer client; no Kodi/native playback authority.

Only the user's exact selected BTIH may be added, once, without persistence.
Metadata and an explicit user file selection are required before a media URL
is returned. No URL torrent fetch, cloud task, first-video guess or retry-add.

Official TorrServer permits existing-torrent media streaming without Basic
authentication. Consequently another local app can potentially read the same
loopback stream. Pairing protects management, NOT media confidentiality. The
returned stream URL never contains credentials; this is not a native receipt.
"""
import base64
from dataclasses import dataclass
import http.client
import json
import re
import socket
from threading import Event, Timer
from time import monotonic, sleep
from urllib.parse import parse_qsl, urlencode, urlsplit

ENDPOINT = 'http://127.0.0.1:8090'
ENGINE_VERSION = 'MatriX.147'
MAX_RESPONSE = 1024 * 1024
REQUEST_TIMEOUT = 2.0
METADATA_BUDGET = 30.0
VIDEO_EXTENSIONS = frozenset(('.mkv', '.mp4', '.m4v', '.avi', '.mov', '.webm', '.ts', '.m2ts', '.mts', '.mpg', '.mpeg', '.vob', '.wmv', '.flv', '.ogm', '.ogv'))


class TorrServerError(RuntimeError):
    """Fixed category only: never interpolate credentials, locators or HTTP IO."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Cancelled(TorrServerError):
    pass


class MetadataTimeout(TorrServerError):
    pass


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise TorrServerError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(TorrServerError('INVALID_JSON_NUMBER')))
    except (UnicodeError, ValueError, RecursionError):
        raise TorrServerError('INVALID_JSON') from None


def selected_magnet(expected_hash, magnet=None):
    """Validate, but never reserialize/drop trackers from a supplied magnet."""
    if not isinstance(expected_hash, str) or not re.fullmatch('[0-9a-fA-F]{40}', expected_hash):
        raise TorrServerError('SELECTED_BTIH_REQUIRED')
    expected_hash = expected_hash.lower()
    if magnet is None or magnet == '':
        return expected_hash, 'magnet:?xt=urn:btih:' + expected_hash
    if (not isinstance(magnet, str) or len(magnet) > 16384
            or any(ord(char) < 32 for char in magnet)):
        raise TorrServerError('INVALID_MAGNET')
    try:
        parsed = urlsplit(magnet)
        if parsed.scheme.lower() != 'magnet' or parsed.netloc or parsed.path or parsed.fragment:
            raise TorrServerError('MAGNET_ONLY_NO_URL_DOWNLOAD')
        pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=128)
        hashes = []
        for key, value in pairs:
            if key.lower() != 'xt':
                continue
            if not value.lower().startswith('urn:btih:'):
                raise TorrServerError('UNSUPPORTED_MAGNET_IDENTITY')
            encoded = value[9:]
            if re.fullmatch('[0-9a-fA-F]{40}', encoded):
                hashes.append(encoded.lower())
            elif re.fullmatch('[A-Z2-7a-z]{32}', encoded):
                hashes.append(base64.b32decode(encoded.upper()).hex())
            else:
                raise TorrServerError('INVALID_MAGNET_BTIH')
        if len(hashes) != 1 or hashes[0] != expected_hash:
            raise TorrServerError('MAGNET_HASH_MISMATCH')
    except (ValueError, UnicodeError):
        raise TorrServerError('INVALID_MAGNET') from None
    return expected_hash, magnet


def checked_pairing(value):
    if isinstance(value, (str, bytes)):
        if len(value) > 4096:
            raise TorrServerError('INVALID_PAIRING')
        value = _json(value)
    if (not isinstance(value, dict)
            or set(value) != {'schema', 'engine', 'version', 'url', 'username', 'password'}
            or value['schema'] != 'bobbi-local-engine-v1' or value['engine'] != 'TorrServer'
            or value['version'] != ENGINE_VERSION or value['url'] != ENDPOINT
            or not isinstance(value['username'], str)
            or not re.fullmatch('bobbi_[0-9a-f]{12}', value['username'])
            or not isinstance(value['password'], str)
            or not re.fullmatch('[0-9a-f]{48}', value['password'])):
        raise TorrServerError('INVALID_PAIRING')
    return dict(value)


@dataclass(frozen=True)
class VideoFile:
    """Exact metadata tuple, not a catalogue episode or playback receipt."""
    id: int
    path: str
    size: int


def checked_files(value, expected_hash):
    """MatriX.147 state/state.go and torr/torrent.go: returned IDs are 1-based.

    Do not enumerate or independently path-sort and thereby change stream IDs.
    Empty file_stats means metadata is pending, not permission to guess a file.
    """
    if (not isinstance(value, dict) or not isinstance(value.get('hash'), str)
            or not re.fullmatch('[0-9a-fA-F]{40}', value['hash'])
            or value['hash'].lower() != expected_hash):
        raise TorrServerError('RETURNED_TORRENT_HASH_MISMATCH')
    rows = value.get('file_stats')
    if rows is None or rows == []:
        return ()
    if not isinstance(rows, list) or len(rows) > 4096:
        raise TorrServerError('INVALID_FILE_METADATA')
    result, ids, paths = [], set(), set()
    for row in rows:
        if (not isinstance(row, dict) or not {'id', 'path', 'length'}.issubset(row)
                or type(row['id']) is not int or not 1 <= row['id'] <= len(rows)
                or type(row['length']) is not int or not 0 <= row['length'] < 2 ** 63
                or not isinstance(row['path'], str) or not 1 <= len(row['path']) <= 4096):
            raise TorrServerError('INVALID_FILE_METADATA')
        path = row['path']
        if (path.startswith('/') or '\\' in path or ':' in path
                or any(part in ('', '.', '..') for part in path.split('/'))
                or any(ord(char) < 32 for char in path)
                or row['id'] in ids or path.casefold() in paths):
            raise TorrServerError('UNSAFE_OR_DUPLICATE_FILE_METADATA')
        ids.add(row['id'])
        paths.add(path.casefold())
        result.append(VideoFile(row['id'], path, row['length']))
    return tuple(result)


def local_http(method, url, headers, body, timeout, max_bytes):
    """Stdlib-only fixed-loopback transport; never use proxies or redirects.

    Injected transports must provide the same timeout/size/no-redirect contract.
    Connection/read IO gets the remaining request budget, not an unbounded wait.
    """
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.netloc != '127.0.0.1:8090'
            or parsed.path not in ('/settings', '/echo', '/torrents') or parsed.query or parsed.fragment
            or method != ('GET' if parsed.path == '/echo' else 'POST')
            or type(max_bytes) is not int or not 0 < max_bytes <= MAX_RESPONSE
            or type(timeout) not in (float, int) or not 0 < timeout <= REQUEST_TIMEOUT):
        raise TorrServerError('LOCAL_TRANSPORT_CONTRACT_REJECTED')
    deadline = monotonic() + timeout
    connection = http.client.HTTPConnection('127.0.0.1', 8090, timeout=timeout)
    peer = [None]
    expired = Event()
    def expire():
        # A socket inactivity timeout alone permits slow-drip HTTP headers to
        # run forever. Close this one request at its absolute wall deadline.
        expired.set()
        if peer[0] is not None:
            try:
                peer[0].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()
    watchdog = Timer(timeout, expire)
    watchdog.daemon = True
    watchdog.start()
    try:
        connection.connect()
        peer_socket = connection.sock
        peer[0] = peer_socket
        peer_socket.settimeout(max(.001, deadline - monotonic()))
        connection.request(method, parsed.path, body=body, headers=headers)
        peer_socket.settimeout(max(.001, deadline - monotonic()))
        response = connection.getresponse()
        chunks, count = [], 0
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TorrServerError('LOCAL_HTTP_TIMEOUT')
            peer_socket.settimeout(remaining)
            chunk = response.read1(min(65536, max_bytes + 1 - count))
            if not chunk:
                if expired.is_set() or monotonic() >= deadline:
                    raise TorrServerError('LOCAL_HTTP_TIMEOUT')
                return response.status, b''.join(chunks)
            count += len(chunk)
            if count > max_bytes:
                raise TorrServerError('LOCAL_RESPONSE_LIMIT')
            chunks.append(chunk)
    except TorrServerError:
        raise
    except Exception:
        if expired.is_set() or monotonic() >= deadline:
            raise TorrServerError('LOCAL_HTTP_TIMEOUT') from None
        raise TorrServerError('LOCAL_HTTP_UNAVAILABLE') from None
    finally:
        watchdog.cancel()
        connection.close()


class TorrServerClient:
    """One paired engine, injected IO, and no background or automatic choice.

    select_source's budget includes readiness, add and metadata polling. The
    interactive file picker is outside that network budget; no network/control
    request is made after the user's choice. Caller still checks its own workflow
    cancellation immediately before standard Kodi playback submission.
    """
    def __init__(self, pairing, transport=None, clock=monotonic, wait=sleep):
        checked = checked_pairing(pairing)
        self._authorization = 'Basic ' + base64.b64encode(
            (checked['username'] + ':' + checked['password']).encode('ascii')).decode('ascii')
        self._transport = transport or local_http
        self._clock, self._wait = clock, wait

    def __repr__(self):
        return '<TorrServerClient paired-loopback credentials=redacted>'

    @staticmethod
    def _cancelled(cancelled):
        try:
            result = cancelled()
        except Exception:
            raise TorrServerError('CANCEL_CHECK_FAILED') from None
        if result:
            raise Cancelled('USER_CANCELLED')

    def _request(self, method, path, deadline, cancelled, payload=None, auth=True):
        self._cancelled(cancelled)
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise MetadataTimeout('METADATA_DEADLINE')
        headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity'}
        if auth:
            headers['Authorization'] = self._authorization
        body = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        try:
            response = self._transport(method, ENDPOINT + path, headers, body,
                                       min(REQUEST_TIMEOUT, remaining), MAX_RESPONSE)
        except TorrServerError as error:
            safe = {'LOCAL_TRANSPORT_CONTRACT_REJECTED', 'LOCAL_HTTP_TIMEOUT',
                    'LOCAL_RESPONSE_LIMIT', 'LOCAL_HTTP_UNAVAILABLE'}
            raise TorrServerError(error.code if error.code in safe else 'LOCAL_REQUEST_FAILED') from None
        except Exception:
            raise TorrServerError('LOCAL_REQUEST_FAILED') from None
        self._cancelled(cancelled)
        if self._clock() >= deadline:
            raise MetadataTimeout('METADATA_DEADLINE')
        if (not isinstance(response, tuple) or len(response) != 2
                or type(response[0]) is not int or not isinstance(response[1], bytes)
                or len(response[1]) > MAX_RESPONSE):
            raise TorrServerError('INVALID_LOCAL_RESPONSE')
        return response

    def _ready(self, deadline, cancelled):
        status, _ = self._request('POST', '/settings', deadline, cancelled,
                                  {'action': 'get'}, auth=False)
        if status != 401:
            raise TorrServerError('UNPROTECTED_OR_UNKNOWN_ENGINE')
        status, raw = self._request('POST', '/settings', deadline, cancelled, {'action': 'get'})
        if status != 200:
            raise TorrServerError('ENGINE_AUTH_REJECTED')
        settings = _json(raw)
        safety = {'UseDisk': False, 'EnableBonjour': False, 'EnableLPD': False,
                  'EnableDLNA': False, 'DisableUPNP': True}
        if (not isinstance(settings, dict)
                or any(type(settings.get(key)) is not bool or settings[key] is not value
                       for key, value in safety.items())):
            raise TorrServerError('ENGINE_SETTINGS_NOT_ISOLATED')
        status, raw = self._request('GET', '/echo', deadline, cancelled)
        if status != 200 or raw.strip() != ENGINE_VERSION.encode('ascii'):
            raise TorrServerError('ENGINE_VERSION_MISMATCH')
        return True

    def ready(self, cancelled=lambda: False):
        return self._ready(self._clock() + 6.0, cancelled)

    def select_source(self, expected_hash, magnet=None, choose_file=None,
                      cancelled=lambda: False, budget=METADATA_BUDGET):
        expected_hash, magnet = selected_magnet(expected_hash, magnet)
        if not callable(choose_file):
            raise Cancelled('EXPLICIT_VIDEO_FILE_CHOICE_REQUIRED')
        if type(budget) not in (int, float) or not 0 < budget <= METADATA_BUDGET:
            raise TorrServerError('INVALID_METADATA_BUDGET')
        deadline = self._clock() + budget
        self._ready(deadline, cancelled)
        # Never retry add, including a lost HTTP reply after possible acceptance.
        status, raw = self._request('POST', '/torrents', deadline, cancelled,
            {'action': 'add', 'link': magnet, 'save_to_db': False})
        if status != 200:
            raise TorrServerError('TORRENT_ADD_REJECTED')
        files = checked_files(_json(raw), expected_hash)
        for _ in range(121):  # Independent iteration cap for injected clocks.
            if files:
                break
            self._cancelled(cancelled)
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise MetadataTimeout('METADATA_DEADLINE')
            self._wait(min(.25, remaining))
            status, raw = self._request('POST', '/torrents', deadline, cancelled,
                                       {'action': 'get', 'hash': expected_hash})
            if status != 200:
                raise TorrServerError('TORRENT_METADATA_UNAVAILABLE')
            files = checked_files(_json(raw), expected_hash)
        if not files:
            raise MetadataTimeout('METADATA_DEADLINE')
        candidates = tuple(file for file in files if file.size > 0
                           and any(file.path.lower().endswith(ext) for ext in VIDEO_EXTENSIONS))
        if not candidates:
            raise TorrServerError('NO_PLAYABLE_VIDEO_FILE')
        self._cancelled(cancelled)
        try:
            selected = choose_file(candidates)
        except Exception:
            raise TorrServerError('FILE_SELECTION_FAILED') from None
        self._cancelled(cancelled)
        if selected is None:
            raise Cancelled('USER_CANCELLED_FILE_CHOICE')
        if not isinstance(selected, VideoFile) or selected not in candidates:
            raise TorrServerError('FILE_CHOICE_NOT_FROM_SELECTED_TORRENT')
        # MatriX.147 uses file_stats.id verbatim, not zero-based metainfo order.
        url = ENDPOINT + '/stream?' + urlencode({'link': expected_hash, 'index': selected.id}) + '&play'
        return {'url': url, 'info_hash': expected_hash, 'selection_identity': 'bt:' + expected_hash,
                'file_id': selected.id, 'file_path': selected.path, 'size': selected.size,
                'evidence': 'selected-torrent-metadata-and-user-file-choice-only'}

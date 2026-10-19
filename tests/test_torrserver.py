"""Offline MatriX.147 protocol tests using injected HTTP, not engine playback."""
import base64
import json
from threading import Event
from time import monotonic
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_platform.torrserver import (Cancelled, ENDPOINT, ENGINE_VERSION, MAX_RESPONSE,
    MetadataTimeout, TorrServerClient, TorrServerError, VideoFile, checked_files,
    checked_pairing, selected_magnet)

HASH = '0123456789abcdef0123456789abcdef01234567'
OTHER = 'a' * 40
PAIRING = {'schema': 'bobbi-local-engine-v1', 'engine': 'TorrServer',
    'version': ENGINE_VERSION, 'url': ENDPOINT, 'username': 'bobbi_0123456789ab',
    'password': 'a' * 48}
SETTINGS = {'UseDisk': False, 'EnableBonjour': False, 'EnableLPD': False,
            'EnableDLNA': False, 'DisableUPNP': True}
FILES = [{'id': 1, 'path': 'Release/readme.txt', 'length': 100},
         {'id': 2, 'path': 'Release/Episode02.mkv', 'length': 2000},
         {'id': 3, 'path': 'Release/Episode03.mp4', 'length': 3000}]


def encoded(value):
    return json.dumps(value).encode()


class FakeEngine:
    def __init__(self):
        self.now = 0.0
        self.requests = []
        self.unauth_status = 401
        self.auth_status = 200
        self.settings = dict(SETTINGS)
        self.version = ENGINE_VERSION.encode()
        self.add = {'hash': HASH, 'file_stats': []}
        self.metadata = [{'hash': HASH, 'file_stats': FILES}]
        self.status = 200
        self.cancel = False
        self.on_request = None
        self.client = TorrServerClient(PAIRING, self.transport, lambda: self.now, self.wait)

    def wait(self, duration):
        self.now += duration

    def transport(self, method, url, headers, body, timeout, maximum):
        payload = json.loads(body) if body else None
        self.requests.append((method, url, dict(headers), payload, timeout, maximum))
        if self.on_request:
            self.on_request(method, url, headers, payload)
        if url.endswith('/settings'):
            return ((self.auth_status, encoded(self.settings)) if 'Authorization' in headers
                    else (self.unauth_status, b''))
        if url.endswith('/echo'):
            return 200, self.version
        assert url == ENDPOINT + '/torrents' and method == 'POST'
        if payload['action'] == 'add':
            return self.status, encoded(self.add)
        assert payload == {'action': 'get', 'hash': HASH}
        row = self.metadata.pop(0) if len(self.metadata) > 1 else self.metadata[0]
        return 200, encoded(row)

    def select(self, **kwargs):
        return self.client.select_source(HASH, choose_file=lambda files: files[-1], **kwargs)


@pytest.fixture
def engine():
    return FakeEngine()


def test_exact_hash_tracker_preservation_and_user_returned_one_based_file_id(engine):
    magnet = 'magnet:?xt=urn:btih:' + HASH + '&dn=Episode%20pack&tr=udp%3A%2F%2Ftracker.example%3A80&tr=https%3A%2F%2Ftracker.example%2Fa'
    seen = []
    def choose(files):
        seen.append(files)
        return files[1]
    result = engine.client.select_source(HASH.upper(), magnet, choose)
    assert isinstance(seen[0], tuple)
    assert seen[0] == (VideoFile(2, 'Release/Episode02.mkv', 2000), VideoFile(3, 'Release/Episode03.mp4', 3000))
    parsed = urlsplit(result['url'])
    query = parse_qs(parsed.query, keep_blank_values=True)
    assert parsed.netloc == '127.0.0.1:8090'
    assert query == {'link': [HASH], 'index': ['3'], 'play': ['']}
    assert result['file_id'] == 3 and result['file_path'] == 'Release/Episode03.mp4'
    assert result['selection_identity'] == 'bt:' + HASH
    assert 'password' not in result['url'] and PAIRING['password'] not in result['url']
    adds = [request[3] for request in engine.requests if request[3] and request[3].get('action') == 'add']
    assert adds == [{'action': 'add', 'link': magnet, 'save_to_db': False}]
    assert all(request[4] <= 2 and request[5] == MAX_RESPONSE for request in engine.requests)
    assert 'Authorization' not in engine.requests[0][2]
    for request in engine.requests[1:]:
        assert request[2]['Authorization'].startswith('Basic ')
        assert PAIRING['username'] not in request[1] and PAIRING['password'] not in request[1]
    assert [request[1].split('/')[-1] for request in engine.requests[:3]] == ['settings', 'settings', 'echo']


def test_base32_and_bare_selected_hash(engine):
    encoded_hash = base64.b32encode(bytes.fromhex(HASH)).decode().lower()
    magnet = 'magnet:?xt=urn:btih:' + encoded_hash + '&tr=udp%3A%2F%2Ft.example%3A80'
    assert selected_magnet(HASH, magnet) == (HASH, magnet)
    assert selected_magnet(HASH)[1] == 'magnet:?xt=urn:btih:' + HASH
    assert engine.select()['info_hash'] == HASH


@pytest.mark.parametrize('expected,magnet', [('', None), (None, 'magnet:?xt=urn:btih:' + HASH),
    ('b' * 32, None), (HASH, 'https://example.com/a.torrent'),
    (HASH, 'magnet:?xt=urn:btih:' + OTHER), (HASH, 'magnet:?dn=hashless'),
    (HASH, 'magnet:?xt=urn:btih:' + HASH + '&xt=urn:btih:' + HASH),
    (HASH, 'magnet:?xt=urn:btih:not-valid'), (HASH, 'magnet://remote?xt=urn:btih:' + HASH)])
def test_bad_hash_magnet_or_url_rejected_before_http(engine, expected, magnet):
    with pytest.raises(TorrServerError):
        engine.client.select_source(expected, magnet, lambda files: files[0])
    assert engine.requests == []


@pytest.mark.parametrize('change', [{'url': 'http://192.0.2.1:8090'},
    {'url': 'http://user:pass@127.0.0.1:8090'}, {'url': ENDPOINT + '?password=x'},
    {'username': 'bobbi'}, {'password': 'short'}, {'version': 'MatriX.146'}])
def test_pairing_only_fixed_helper_installation_contract(change):
    with pytest.raises(TorrServerError, match='INVALID_PAIRING'):
        checked_pairing(dict(PAIRING, **change))


def test_duplicate_pairing_keys_and_unknown_fields_rejected():
    raw = json.dumps(PAIRING).replace('"engine": "TorrServer"', '"engine": "TorrServer", "engine": "TorrServer"')
    with pytest.raises(TorrServerError):
        checked_pairing(raw)
    with pytest.raises(TorrServerError):
        checked_pairing(dict(PAIRING, port=8090))


@pytest.mark.parametrize('fault', ['unauth200', 'auth401', 'wrong_version', 'unsafe_settings', 'missing_settings'])
def test_echo_alone_is_not_readiness_and_management_must_be_protected(engine, fault):
    if fault == 'unauth200':
        engine.unauth_status = 200
    elif fault == 'auth401':
        engine.auth_status = 401
    elif fault == 'wrong_version':
        engine.version = b'MatriX.146'
    elif fault == 'unsafe_settings':
        engine.settings['UseDisk'] = True
    else:
        engine.settings.pop('EnableDLNA')
    with pytest.raises(TorrServerError):
        engine.select()
    assert not any(request[3] and request[3].get('action') == 'add' for request in engine.requests)


@pytest.mark.parametrize('where', ['add', 'get'])
def test_server_hash_mismatch_never_returns_stream(engine, where):
    target = engine.add if where == 'add' else engine.metadata[0]
    target['hash'] = OTHER
    with pytest.raises(TorrServerError, match='HASH_MISMATCH'):
        engine.select()


@pytest.mark.parametrize('rows', [[{'id': 0, 'path': 'zero.mkv', 'length': 100}],
    [{'id': True, 'path': 'bool.mkv', 'length': 100}],
    [{'id': 1, 'path': 'bad.mkv', 'length': -1}],
    [{'id': 1, 'path': '../bad.mkv', 'length': 100}],
    [{'id': 1, 'path': '/bad.mkv', 'length': 100}],
    [{'id': 1, 'path': 'C:\\bad.mkv', 'length': 100}],
    [{'id': 1, 'path': 'a.mkv', 'length': 1}, {'id': 1, 'path': 'b.mkv', 'length': 1}],
    [{'id': 1, 'path': 'a.mkv', 'length': 1}, {'id': 2, 'path': 'A.MKV', 'length': 1}],
    [{'id': 1, 'path': 'a.mkv'}]])
def test_invalid_duplicate_and_unsafe_file_tuples_rejected(engine, rows):
    engine.metadata[0]['file_stats'] = rows
    with pytest.raises(TorrServerError):
        engine.select()


def test_metadata_timeout_is_bounded_and_never_readds(engine):
    engine.metadata = [{'hash': HASH, 'file_stats': []}]
    with pytest.raises(MetadataTimeout):
        engine.select(budget=1)
    assert engine.now <= 1
    assert sum(bool(request[3] and request[3].get('action') == 'add') for request in engine.requests) == 1


def test_cancel_before_add_and_while_waiting_does_not_retry(engine):
    with pytest.raises(Cancelled):
        engine.select(cancelled=lambda: True)
    assert engine.requests == []
    engine.metadata = [{'hash': HASH, 'file_stats': []}]
    def wait(duration):
        engine.now += duration
        engine.cancel = True
    engine.client._wait = wait
    with pytest.raises(Cancelled):
        engine.select(cancelled=lambda: engine.cancel)
    assert sum(bool(request[3] and request[3].get('action') == 'add') for request in engine.requests) == 1


def test_no_first_video_automatic_choice_even_for_one_video(engine):
    with pytest.raises(Cancelled, match='CHOICE_REQUIRED'):
        engine.client.select_source(HASH)
    assert engine.requests == []
    with pytest.raises(Cancelled, match='FILE_CHOICE'):
        engine.client.select_source(HASH, choose_file=lambda files: None)


def test_nonvideo_and_forged_choice_rejected(engine):
    engine.metadata[0]['file_stats'] = [{'id': 1, 'path': 'readme.txt', 'length': 5}]
    with pytest.raises(TorrServerError, match='NO_PLAYABLE'):
        engine.select()
    engine.metadata[0]['file_stats'] = FILES
    with pytest.raises(TorrServerError, match='NOT_FROM_SELECTED'):
        engine.client.select_source(HASH, choose_file=lambda files: VideoFile(1, 'other.mkv', 500))
    with pytest.raises(TorrServerError, match='NOT_FROM_SELECTED'):
        engine.client.select_source(HASH, choose_file=lambda files: 0)


def test_cancel_from_file_picker_returns_no_media(engine):
    def choose(files):
        engine.cancel = True
        return files[0]
    with pytest.raises(Cancelled):
        engine.client.select_source(HASH, choose_file=choose, cancelled=lambda: engine.cancel)


def test_add_reply_lost_is_terminal_not_an_add_retry(engine):
    original = engine.client._transport
    def lost(method, url, headers, body, timeout, maximum):
        result = original(method, url, headers, body, timeout, maximum)
        if body and json.loads(body).get('action') == 'add':
            raise OSError('reply lost')
        return result
    engine.client._transport = lost
    with pytest.raises(TorrServerError, match='LOCAL_REQUEST_FAILED'):
        engine.select()
    assert sum(bool(request[3] and request[3].get('action') == 'add') for request in engine.requests) == 1


def test_credentials_are_not_in_diagnostics_or_result(engine):
    secret = PAIRING['password']
    def bad(*args):
        raise OSError('Authorization: ' + engine.client._authorization + secret)
    engine.client._transport = bad
    with pytest.raises(TorrServerError) as failure:
        engine.select()
    assert secret not in str(failure.value) and secret not in repr(engine.client)
    assert engine.client._authorization not in str(failure.value)
    assert failure.value.__suppress_context__


@pytest.mark.parametrize('result', [(302, b''), (200, b'x' * (MAX_RESPONSE + 1)),
    (200, b'{"hash":"' + HASH.encode() + b'","hash":"' + HASH.encode() + b'"}'),
    (200, b'not-json')])
def test_redirect_oversize_duplicate_json_or_invalid_response_fails_closed(engine, result):
    original = engine.client._transport
    def corrupt(method, url, headers, body, timeout, maximum):
        if url.endswith('/torrents'):
            return result
        return original(method, url, headers, body, timeout, maximum)
    engine.client._transport = corrupt
    with pytest.raises(TorrServerError):
        engine.select()


def test_returned_engine_ids_are_not_resorted_or_zero_based():
    rows = [{'id': 2, 'path': 'b.mkv', 'length': 20}, {'id': 1, 'path': 'a.mkv', 'length': 10}]
    assert checked_files({'hash': HASH, 'file_stats': rows}, HASH) == (
        VideoFile(2, 'b.mkv', 20), VideoFile(1, 'a.mkv', 10))


def test_default_transport_has_no_remote_proxy_redirect_surface(monkeypatch):
    from bobbi_platform import torrserver
    made = []
    class Peer:
        def settimeout(self, value):
            assert 0 < value <= 2
        def shutdown(self, how):
            pass
    class Response:
        status = 302
        def read1(self, maximum):
            return b''
    class Connection:
        def __init__(self, host, port, timeout):
            made.append((host, port, timeout))
            self.sock = Peer()
        def connect(self):
            pass
        def request(self, method, path, body, headers):
            assert method == 'GET' and path == '/echo'
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(torrserver.http.client, 'HTTPConnection', Connection)
    assert torrserver.local_http('GET', ENDPOINT + '/echo', {}, None, 1, 100) == (302, b'')
    assert made == [('127.0.0.1', 8090, 1)]  # No redirect is followed.
    with pytest.raises(TorrServerError):
        torrserver.local_http('GET', 'http://example.com/echo', {}, None, 1, 100)


def test_absolute_transport_deadline_interrupts_slow_headers_without_network(monkeypatch):
    from bobbi_platform import torrserver
    stopped = Event()
    class Peer:
        def settimeout(self, value):
            pass
        def shutdown(self, how):
            stopped.set()
    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock = Peer()
        def connect(self):
            pass
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            stopped.wait(.5)
            raise OSError('simulated slow header connection closed')
        def close(self):
            pass
    monkeypatch.setattr(torrserver.http.client, 'HTTPConnection', Connection)
    start = monotonic()
    with pytest.raises(TorrServerError) as failure:
        torrserver.local_http('GET', ENDPOINT + '/echo', {}, None, .02, 100)
    assert failure.value.code == 'LOCAL_HTTP_TIMEOUT'
    assert stopped.is_set() and monotonic() - start < .5


def test_injected_transport_custom_exception_cannot_smuggle_credentials(engine):
    def failed(*args):
        raise TorrServerError(PAIRING['password'])
    engine.client._transport = failed
    with pytest.raises(TorrServerError) as failure:
        engine.select()
    assert failure.value.code == 'LOCAL_REQUEST_FAILED'
    assert PAIRING['password'] not in str(failure.value)

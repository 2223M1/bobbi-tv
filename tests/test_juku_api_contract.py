"""Synthetic offline protocol/state tests; no Juku library or credentials copied."""
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import io
import json
from pathlib import Path
import socket
import ssl
import sys
from threading import Event, Thread
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import juku_api as api


@pytest.fixture(autouse=True)
def isolated_crypto_selection(monkeypatch):
    monkeypatch.setattr(api, 'BASE', 'https://catalog.example.invalid')
    monkeypatch.setattr(api, '_CRYPTO_NAMESPACE', None)


def session(access='access-one', expires_in=3600, device='installation-device'):
    def stamp(seconds):
        return datetime.fromtimestamp(time.time()+seconds, timezone.utc).isoformat()
    return dict(deviceId=device, accessToken=access, refreshToken='refresh-one',
                accessExpiresAt=stamp(expires_in), refreshExpiresAt=stamp(7200))


class Response(io.BytesIO):
    def __init__(self, data=None, raw=None, headers=None):
        super().__init__(raw if raw is not None else json.dumps(dict(success=True, data=data)).encode())
        self.headers = headers or {}


class Opener:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        assert timeout > 0
        step = self.steps.pop(0)
        if callable(step):
            step = step(request)
        if isinstance(step, BaseException):
            raise step
        return step


def http_error(code):
    return HTTPError(api.BASE, code, 'synthetic rejection', {}, io.BytesIO(b'private-server-body'))


class Key:
    def public_key(self):
        return self

    def export_key(self, format):
        assert format == 'DER'
        return b'own-synthetic-public-key'


@pytest.fixture
def client(tmp_path, monkeypatch):
    opener = Opener()
    monkeypatch.setattr(api.Client, '_key', lambda self: Key())
    monkeypatch.setattr(api, 'sign_payload', lambda key, payload: hashlib.sha512(payload).digest())
    return api.Client(state=tmp_path, opener=opener), opener


def save(client, row=None):
    client.root.mkdir(parents=True, exist_ok=True)
    api.atomic_json(client.root / 'session.json', row or session())


def test_rfc3986_query_and_eight_line_signing_contract():
    query = api.canonical_query({'q': 'A B+中', 'page': 1})
    assert query == 'page=1&q=A%20B%2B%E4%B8%AD'
    message = api.signing_string('get', '/videos/search', query, b'', '1000', 'nonce', 'device', 'token')
    assert message.decode().split('\n') == [
        'GET', '/videos/search', query, hashlib.sha256(b'').hexdigest(), '1000', 'nonce', 'device', 'token']


@pytest.mark.parametrize('value', [None, '', '2026-10-19T00:00:00', 'invalid', 123])
def test_expiry_requires_an_explicit_timezone(value):
    assert api.expires(value) == 0


@pytest.mark.parametrize('change', [
    dict(refreshToken=''), dict(accessToken=['wrong']), dict(deviceId='bad\nheader'),
    dict(accessExpiresAt='2026-10-19T00:00:00'), dict(refreshExpiresAt='invalid'),
])
def test_session_schema_is_complete_and_header_safe(change):
    with pytest.raises(api.JukuError, match='AUTH_SCHEMA'):
        api.checked_session(dict(session(), **change))


def test_valid_session_is_reused_without_register_or_refresh(client):
    value, opener = client
    save(value)
    opener.steps = [Response({'items': []})]
    assert value.get('/videos/search', {'q': 'Synthetic Film'}) == {'items': []}
    assert len(opener.calls) == value.requests == 1
    request = opener.calls[0][0]
    assert request.get_method() == 'GET'
    assert request.get_header('X-access-token') == 'access-one'
    assert len(base64.b64decode(request.get_header('X-signature'))) == 64
    assert 'Synthetic%20Film' in request.full_url


def test_new_install_registers_own_public_key_without_cloud_account(client):
    value, opener = client
    opener.steps = [Response(session()), Response([])]
    value.get('/shared-libraries/public')
    registration = opener.calls[0][0]
    body = json.loads(registration.data)
    assert registration.full_url.endswith('/auth/device/register')
    assert body['installId'].startswith('bobitv-')
    assert body['publicKey'] == base64.b64encode(b'own-synthetic-public-key').decode()
    assert set(body) == {'publicKey', 'installId', 'platform', 'appVersion'}
    assert not registration.has_header('X-access-token')
    assert api.load_json(value.root / 'session.json')['accessToken'] == 'access-one'


def test_expired_session_refreshes_unsigned_without_register(client):
    value, opener = client
    save(value, session(expires_in=-1))
    opener.steps = [Response(session(access='new-access')), Response({'items': []})]
    value.get('/videos/search')
    refresh = opener.calls[0][0]
    assert refresh.full_url.endswith('/auth/device/refresh')
    assert json.loads(refresh.data) == {'deviceId': 'installation-device', 'refreshToken': 'refresh-one'}
    assert not refresh.has_header('X-signature')
    assert opener.calls[1][0].get_header('X-access-token') == 'new-access'


def test_401_refreshes_once_and_retries_with_rotated_token(client):
    value, opener = client
    save(value)
    opener.steps = [http_error(401), Response(session(access='new-access')), Response({'ok': 1})]
    assert value.get('/videos/123') == {'ok': 1}
    assert [request.get_method() for request, _ in opener.calls] == ['GET', 'POST', 'GET']
    assert not any('/register' in request.full_url for request, _ in opener.calls)


def test_concurrent_401_reuses_other_process_rotation_instead_of_refreshing(client):
    value, opener = client
    save(value)
    def rotate(request):
        save(value, session(access='rotated-elsewhere'))
        return http_error(401)
    opener.steps = [rotate, Response([])]
    assert value.get('/videos/123') == []
    assert len(opener.calls) == 2
    assert opener.calls[1][0].get_header('X-access-token') == 'rotated-elsewhere'


def test_second_401_sets_cooldown_without_registration_storm(client):
    value, opener = client
    save(value)
    opener.steps = [http_error(401), Response(session(access='new-access')), http_error(401), http_error(401)]
    with pytest.raises(api.JukuError, match='HTTP_401'):
        value.get('/videos/123')
    with pytest.raises(api.JukuError, match='AUTH_RETRY_LATER'):
        value.get('/videos/123')
    assert len(opener.calls) == 4
    assert sum(request.get_method() == 'POST' for request, _ in opener.calls) == 1


@pytest.mark.parametrize('code', [403, 429])
def test_forbidden_or_rate_limit_never_refreshes_or_reregisters(client, code):
    value, opener = client
    save(value)
    opener.steps = [http_error(code)]
    with pytest.raises(api.JukuError, match='HTTP_' + str(code)):
        value.get('/videos/123')
    assert len(opener.calls) == 1


def test_failed_initial_registration_is_cooled_across_client_instances(client):
    value, opener = client
    opener.steps = [http_error(503)]
    with pytest.raises(api.JukuError, match='HTTP_503'):
        value.get('/videos/123')
    another = api.Client(state=value.root, opener=opener)
    with pytest.raises(api.JukuError, match='AUTH_RETRY_LATER'):
        another.get('/videos/123')
    assert len(opener.calls) == 1
    diagnostic = (value.root / 'auth-attempt.json').read_text()
    assert 'private-server-body' not in diagnostic and 'Token' not in diagnostic


def test_refresh_cannot_change_device_identity_and_does_not_destroy_session(client):
    value, opener = client
    original = session(expires_in=-1)
    save(value, original)
    opener.steps = [Response(session(device='another-device'))]
    with pytest.raises(api.JukuError, match='AUTH_SCHEMA'):
        value.get('/videos/123')
    assert api.load_json(value.root / 'session.json') == original


@pytest.mark.parametrize('raw', [b'not-json', b'[]', b'{}'])
def test_corrupt_or_empty_session_does_not_create_a_new_device(client, raw):
    value, opener = client
    (value.root / 'session.json').write_bytes(raw)
    with pytest.raises(api.JukuError, match='STATE_SCHEMA|AUTH_SCHEMA'):
        value.get('/videos/123')
    assert opener.calls == []


@pytest.mark.parametrize('path,kwargs,code', [
    ('/play', {}, 'CATALOGUE_PATH_ONLY'),
    ('/videos/1', {'max_bytes': api.MAX_JSON + 1}, 'RESPONSE_LIMIT_CONFIG'),
    ('/shared-libraries/detail/test', {'max_bytes': api.MAX_SNAPSHOT_JSON + 1}, 'RESPONSE_LIMIT_CONFIG'),
    ('/videos/1', {'deadline': float('nan')}, 'DEADLINE_CONFIG'),
    ('/videos/1', {'deadline': 0}, 'DEADLINE'),
    ('/videos/search', {'params': {'q': 'x' * 9000}}, 'QUERY_LIMIT'),
    ('/videos/search', {'params': {'q': ['bad']}}, 'QUERY_SCHEMA'),
])
def test_invalid_call_fails_before_authentication(client, path, kwargs, code):
    value, opener = client
    with pytest.raises(api.JukuError, match=code):
        value.get(path, **kwargs)
    assert opener.calls == []
    assert not (value.root / 'installation.json').exists()


def test_large_snapshot_limit_is_explicit_and_shared_detail_only(client):
    value, opener = client
    save(value)
    payload = {'padding': 'x' * (api.MAX_JSON + 1)}
    opener.steps = [Response(payload)]
    assert value.get('/shared-libraries/detail/synthetic', max_bytes=api.MAX_SNAPSHOT_JSON) == payload
    opener.steps = [Response({}, headers={'Content-Length': str(api.MAX_JSON + 1)})]
    with pytest.raises(api.JukuError, match='RESPONSE_LIMIT'):
        value.get('/shared-libraries/detail/synthetic')


@pytest.mark.parametrize('response,code', [
    (lambda: Response(raw=b'bad-json'), 'RESPONSE_SCHEMA'),
    (lambda: Response(raw=b'[]'), 'API_REJECTED'),
    (lambda: Response(raw=b'{"success":false,"data":"secret"}'), 'API_REJECTED'),
    (lambda: Response({}, headers={'Content-Encoding': 'gzip'}), 'ENCODING'),
    (lambda: Response({}, headers={'Content-Length': '-1'}), 'RESPONSE_LIMIT'),
])
def test_unusable_responses_fail_without_token_or_body_in_exception(client, response, code):
    value, opener = client
    save(value)
    opener.steps = [response()]
    with pytest.raises(api.JukuError) as captured:
        value.get('/videos/123')
    assert str(captured.value) == code


def test_edge_fallback_is_two_attempts_with_fresh_nonce(client):
    value, first = client
    save(value)
    first.steps = [URLError(socket.timeout())]
    second = Opener(Response({'items': []}))
    value.openers = [first, second]
    assert value.get('/videos/search') == {'items': []}
    assert value.requests == 2
    assert first.calls[0][0].get_header('X-nonce') != second.calls[0][0].get_header('X-nonce')
    assert first.calls[0][0].full_url.startswith(api.BASE)


def test_default_transport_has_two_verified_hostname_edges(tmp_path):
    value = api.Client(state=tmp_path)
    transports = [next(handler for handler in opener.handlers if isinstance(handler, api.EdgeHTTPSHandler))
                  for opener in value.openers]
    assert [handler.edge_ip for handler in transports] == list(api.EDGES)
    assert all(handler._context.check_hostname and handler._context.verify_mode == ssl.CERT_REQUIRED
               for handler in transports)


def test_explicit_proxy_does_not_fallback_outside_proxy(tmp_path):
    value = api.Client(state=tmp_path, proxy='http://127.0.0.1:8088')
    assert len(value.openers) == 1
    with pytest.raises(api.JukuError, match='EDGE_CONFIG'):
        api.Client(state=tmp_path, proxy='http://127.0.0.1:8088', edge_ip=api.EDGES[0])


def test_socket_deadline_survives_connection_close_headers(monkeypatch):
    """A real local socketpair proves slow-body shutdown, not a mocked timer."""
    local, remote = socket.socketpair()
    monkeypatch.setattr(api.socket, 'create_connection', lambda *args: local)
    context = SimpleNamespace(wrap_socket=lambda sock, server_hostname: sock,
                              check_hostname=True, verify_mode=ssl.CERT_REQUIRED)
    connection = api.EdgeConnection('catalog.example.invalid', api.EDGES[0], time.monotonic()+.20,
                                    lambda: False, context=context, timeout=1)
    sent = Event()
    def server():
        try:
            remote.recv(4096)
            remote.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n{')
            sent.set()
            sent.wait(.5)
            time.sleep(.3)
        finally:
            remote.close()
    worker = Thread(target=server, daemon=True)
    worker.start()
    began = time.monotonic()
    response = None
    try:
        connection.request('GET', '/')
        response = connection.getresponse()
        assert sent.wait(.3)
        assert not connection._watch_stop.is_set(), 'Connection: close killed deadline before body'
        with pytest.raises((OSError, http.client.HTTPException)):
            response.read()
        assert time.monotonic()-began < 1
    finally:
        if response is not None:
            response.close()
        connection.close()
        remote.close()
        worker.join(1)
    assert connection._watch_stop.is_set()


def test_independent_p256_signature_wire_format():
    """Independent cryptography verification; production Crypto was live-probed separately."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    key = ec.generate_private_key(ec.SECP256R1())
    payload = api.signing_string('GET', '/videos/123', '', b'', '1000', 'nonce', 'device', 'access')
    signature = key.sign(payload, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(signature)
    wire = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
    assert len(base64.b64decode(base64.b64encode(wire))) == 64
    key.public_key().verify(utils.encode_dss_signature(int.from_bytes(wire[:32], 'big'),
                                                      int.from_bytes(wire[32:], 'big')),
                            payload, ec.ECDSA(hashes.SHA256()))


def test_system_crypto_package_loader_does_not_expose_other_site_packages(tmp_path, monkeypatch):
    package = tmp_path / 'Crypto'
    package.mkdir()
    (package / '__init__.py').write_text('__version__ = "synthetic"\n', encoding='utf-8')
    (package / 'Synthetic.py').write_text('value = "only-this-package"\n', encoding='utf-8')
    monkeypatch.setattr(api.sysconfig, 'get_path', lambda name: str(tmp_path))
    before = list(sys.path)
    existing = {name: module for name, module in sys.modules.items() if name == 'Crypto' or name.startswith('Crypto.')}
    for name in existing:
        monkeypatch.delitem(sys.modules, name)
    try:
        loaded = api._load_crypto_module('Crypto', 'Synthetic')
        assert loaded.value == 'only-this-package'
        assert sys.path == before
        assert sys.modules['Crypto'].__path__ == [str(package)]
    finally:
        for name in list(sys.modules):
            if name == 'Crypto' or name.startswith('Crypto.'):
                sys.modules.pop(name, None)


def test_missing_system_crypto_is_explicit_without_path_widening(tmp_path, monkeypatch):
    monkeypatch.setattr(api.sysconfig, 'get_path', lambda name: str(tmp_path))
    before = list(sys.path)
    for name in list(sys.modules):
        if name == 'Crypto' or name.startswith('Crypto.'):
            monkeypatch.delitem(sys.modules, name)
    def missing(name):
        raise ModuleNotFoundError(name)
    monkeypatch.setattr(api.importlib, 'import_module', missing)
    with pytest.raises(api.JukuError, match='CRYPTO_UNAVAILABLE'):
        api.crypto_module('Crypto.PublicKey.ECC')
    assert sys.path == before


def crypto_suites(monkeypatch, broken_alias=False, missing_official=False, bad_verify=False):
    calls, generated, signed, verified = [], [], [], []
    modules, classes = {}, {}
    for namespace in ('Cryptodome', 'Crypto'):
        classes[namespace] = type('EccKey', (), {'__module__': namespace+'.PublicKey.ECC',
                                               'public_key': lambda self: self})
    for namespace in classes:
        def generate(curve, namespace=namespace):
            assert curve == 'P-256'
            generated.append(namespace)
            return classes[namespace]()
        def new(key, mode, encoding, namespace=namespace):
            assert mode == 'fips-186-3' and encoding == 'binary'
            wanted = 'Crypto' if namespace == 'Cryptodome' and broken_alias else namespace
            if not isinstance(key, classes[wanted]):
                raise ValueError('Unsupported key type')
            def sign(digest):
                signed.append(namespace)
                return b's'*64
            def verify(digest, signature):
                verified.append(namespace)
                if bad_verify or signature != b's'*64:
                    raise ValueError('Invalid signature')
            return SimpleNamespace(sign=sign, verify=verify)
        modules[namespace+'.PublicKey.ECC'] = SimpleNamespace(generate=generate)
        modules[namespace+'.Signature.DSS'] = SimpleNamespace(new=new)
        modules[namespace+'.Hash.SHA256'] = SimpleNamespace(new=lambda payload: payload)
    def load(namespace, suffix):
        name = namespace+'.'+suffix
        calls.append(name)
        if missing_official and namespace == 'Cryptodome':
            raise api.JukuError('CRYPTO_UNAVAILABLE')
        if name not in modules:
            raise api.JukuError('CRYPTO_UNAVAILABLE')
        return modules[name]
    monkeypatch.setattr(api, '_load_crypto_module', load)
    return SimpleNamespace(modules=modules, calls=calls, generated=generated, signed=signed, verified=verified)


def test_official_kodi_cryptodome_namespace_is_preferred_and_probed_once(monkeypatch):
    suite = crypto_suites(monkeypatch)
    assert api.crypto_module('Crypto.Hash.SHA256') is suite.modules['Cryptodome.Hash.SHA256']
    assert api.crypto_module('Cryptodome.PublicKey.ECC') is suite.modules['Cryptodome.PublicKey.ECC']
    assert suite.generated == suite.signed == suite.verified == ['Cryptodome']
    assert api._CRYPTO_NAMESPACE == 'Cryptodome'


@pytest.mark.parametrize('broken_alias,missing_official', [(True, False), (False, True)])
def test_complete_crypto_suite_fallback_for_ce_mixed_alias_or_absent_package(monkeypatch, broken_alias, missing_official):
    suite = crypto_suites(monkeypatch, broken_alias, missing_official)
    ecc = api.crypto_module('Cryptodome.PublicKey.ECC')
    assert ecc is suite.modules['Crypto.PublicKey.ECC']
    assert api.crypto_module('Crypto.Signature.DSS') is suite.modules['Crypto.Signature.DSS']
    assert api.crypto_module('Cryptodome.Hash.SHA256') is suite.modules['Crypto.Hash.SHA256']
    assert suite.signed == suite.verified == ['Crypto']
    assert api._CRYPTO_NAMESPACE == 'Crypto'


def test_namespace_never_changes_after_keys_are_exposed(monkeypatch):
    suite = crypto_suites(monkeypatch)
    api.crypto_module('Crypto.PublicKey.ECC')
    del suite.modules['Cryptodome.Signature.DSS']
    with pytest.raises(api.JukuError, match='CRYPTO_UNAVAILABLE'):
        api.crypto_module('Crypto.Signature.DSS')
    assert api._CRYPTO_NAMESPACE == 'Cryptodome'
    assert not any(name.startswith('Crypto.') for name in suite.calls)


def test_neither_namespace_verifies_signature_fails_closed(monkeypatch):
    suite = crypto_suites(monkeypatch, bad_verify=True)
    with pytest.raises(api.JukuError, match='CRYPTO_UNAVAILABLE'):
        api.crypto_module('Crypto.PublicKey.ECC')
    assert api._CRYPTO_NAMESPACE is None
    assert suite.verified == ['Cryptodome', 'Crypto']


def test_raw_body_limit_is_enforced_without_content_length(client):
    value, opener = client
    save(value)
    opener.steps = [Response({'payload': 'x' * 100})]
    with pytest.raises(api.JukuError, match='RESPONSE_LIMIT'):
        value.get('/videos/123', max_bytes=16)


def test_key_import_must_be_private_p256(tmp_path, monkeypatch):
    (tmp_path / 'device.pem').write_bytes(b'synthetic-public-only-key')
    ecc = SimpleNamespace(import_key=lambda raw: SimpleNamespace(has_private=lambda: False, curve='NIST P-256'))
    monkeypatch.setattr(api, 'crypto_module', lambda name: ecc)
    value = api.Client(state=tmp_path, opener=Opener())
    with pytest.raises(api.JukuError, match='AUTH_KEY_INVALID'):
        value._key()


def test_missing_private_key_cannot_silently_regenerate_for_existing_session(tmp_path, monkeypatch):
    api.atomic_json(tmp_path / 'session.json', session())
    monkeypatch.setattr(api, 'crypto_module', lambda name: SimpleNamespace())
    value = api.Client(state=tmp_path, opener=Opener())
    with pytest.raises(api.JukuError, match='AUTH_KEY_MISSING'):
        value._key()

"""Opt-in URL -> actual catalogue protocol -> the existing search/share owners."""
import importlib.util
from contextlib import closing
import io
import json
from pathlib import Path
import socket
import ssl
import sys
import time
from threading import Thread
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import source_library as source, juku_api as api, share_catalog
from bobbi_platform import source_library_ui as ui
from bobbi_platform.libraries import Registry, import_catalog


@pytest.fixture(autouse=True)
def profile(tmp_path, monkeypatch):
    monkeypatch.setattr(source, 'profile', lambda: tmp_path)
    monkeypatch.setattr(api, 'BASE', '')
    return tmp_path


def load(relative):
    path = ROOT / 'addons/plugin.video.bobbi/lib' / relative
    spec = importlib.util.spec_from_file_location('optin_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('url', ['http://catalog.example', 'file:///x', 'plugin://x',
    'https://u:p@catalog.example', 'https://catalog.example?q=key',
    'https://catalog.example/#key', 'https://catalog.example/a',
    'https://catalog.example\\bad', 'https://catalog.example:99999', '', None])
def test_invalid_endpoint_is_not_saved_or_contacted(url, profile, monkeypatch):
    monkeypatch.setattr(socket, 'create_connection', lambda *a: pytest.fail('network'))
    with pytest.raises(source.SourceLibraryError):
        source.save(url)
    assert source.current() is None and not list(profile.glob('*'))


def test_normalization_and_same_endpoint_keep_scope():
    first = source.save('Catalog.Example:443/')
    assert first.endpoint == 'https://catalog.example'
    assert source.save('https://catalog.example/shared-libraries/public') == first
    assert source.normalize('https://catalog.example:9443') == 'https://catalog.example:9443'


def test_defaults_and_legacy_settings_do_not_enable(profile):
    (profile/'juku').mkdir()
    (profile/'juku/config.json').write_text('{"base":"https://old.example"}')
    (profile/'settings.xml').write_text('<setting id="juku_enabled">true</setting>')
    assert source.current() is None and not share_catalog.juku_enabled()
    with pytest.raises(api.JukuError, match='CATALOGUE_DISABLED'):
        api.Client()


def test_host_switch_never_reuses_identity_or_cached_rows(profile):
    a = source.save('https://a.example')
    a.root.mkdir(parents=True)
    (a.root/'session.json').write_text('{"accessToken":"old-secret"}')
    (a.root/'catalog.sqlite3').write_bytes(b'old-catalog')
    client = api.Client(opener=object())
    b = source.save('https://b.example')
    assert b.root != a.root and not b.root.exists()
    fresh = api.Client(opener=object())
    assert fresh.base == b.endpoint and fresh.root == b.root
    assert client.cancelled()
    with pytest.raises(api.JukuError, match='SOURCE_CHANGED'):
        api.Client(state=a.root, opener=object())
    source.remove()
    assert source.current() is None and fresh.cancelled()
    assert (a.root/'session.json').exists()  # Removing a connection is not deleting accounts/media.


def test_remove_readd_revokes_inflight_generation(monkeypatch):
    a = source.save('https://a.example')
    check = source.cancellation(a)
    source.remove()
    b = source.save(a.endpoint)
    assert a.root == b.root and a.generation != b.generation
    assert check()


def test_new_client_default_is_direct_verified_tls_without_fixed_edges():
    source.save('https://catalog.example')
    client = api.Client()
    assert len(client.openers) == 1
    handler = next(h for h in client.opener.handlers if isinstance(h, api.EdgeHTTPSHandler))
    assert handler.edge_ip is None and handler.expected_host == 'catalog.example'
    assert handler._context.check_hostname and handler._context.verify_mode == ssl.CERT_REQUIRED


def test_cdn_routes_apply_only_to_observed_cdn_dns_and_standard_port():
    def rows(*ips):return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip,443)) for ip in ips]
    assert api.direct_destinations(rows('192.0.2.1'),443) == [('192.0.2.1',443)]
    assert api.direct_destinations(rows('104.21.64.244'),9443) == [('104.21.64.244',9443)]
    assert api.direct_destinations(rows('104.21.64.244'),443) == [
        (ip,443) for ip in (*api.EDGES, '104.21.64.244')]


def test_tls_failure_tries_second_dns_address_without_changing_hostname(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.2', 443))])
    calls = []
    conn = api.EdgeConnection('catalog.example', None, time.monotonic()+3, lambda: False,
        expected_host='catalog.example', timeout=3, context=ssl.create_default_context())
    def connect(destination, host):
        calls.append((destination, host))
        if len(calls) == 1:
            raise TimeoutError()
    monkeypatch.setattr(conn, '_connect_one', connect)
    conn.connect()
    assert calls == [(('192.0.2.1', 443), 'catalog.example'), (('192.0.2.2', 443), 'catalog.example')]
    conn.close()


def test_real_http_response_after_failed_first_tls_attempt(monkeypatch):
    # Real sockets/HTTPConnection state, not merely an asserted retry call count.
    first, failed_peer = socket.socketpair()
    second, peer = socket.socketpair()
    pairs = [first, second]
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.2', 443))])
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k:pairs.pop(0))
    attempts = []
    def handshake(raw, server_hostname):
        attempts.append(server_hostname)
        if len(attempts)==1:
            raise TimeoutError('first handshake')
        return raw
    context = SimpleNamespace(wrap_socket=handshake, check_hostname=True,
        verify_mode=ssl.CERT_REQUIRED, post_handshake_auth=False)
    conn = api.EdgeConnection('catalog.example', None, time.monotonic()+3, lambda:False,
        expected_host='catalog.example', timeout=3, context=context)
    def serve():
        try:
            peer.recv(8192)
            peer.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}')
        finally:
            peer.close()
    worker = Thread(target=serve, daemon=True)
    worker.start()
    try:
        conn.request('GET', '/shared-libraries/public')
        response = conn.getresponse()
        try:
            assert response.status == 200 and response.read() == b'{}'
        finally:
            response.close()
        assert attempts == ['catalog.example', 'catalog.example']
    finally:
        conn.close()
        first.close()
        second.close()
        failed_peer.close()
        peer.close()
        worker.join(1)


@pytest.mark.parametrize('result', [{}, {'items':[{}]}, {'items': 'html'},
    {'items':[dict(shareCode='x/y', version=1)]}])
def test_malformed_public_directory_not_saved(result, monkeypatch):
    old = source.save('https://previous.example')
    monkeypatch.setattr(api.Client, 'get', lambda *a, **k: result)
    with pytest.raises(source.SourceLibraryError, match='SOURCE_FORMAT'):
        source.check('https://new.example', time.monotonic()+1)
    assert source.current() == old


def test_cancelled_check_and_success_dont_publish_until_ui_saves(monkeypatch):
    monkeypatch.setattr(api.Client, 'get', lambda *a, **k: {'items':[]})
    with pytest.raises(api.JukuError, match='CANCELLED'):
        source.check('https://catalog.example', time.monotonic()+1, lambda: True)
    assert source.check('https://catalog.example', time.monotonic()+1) == 'https://catalog.example'
    assert source.current() is None


def test_registry_only_submits_after_optin_and_removal_rejects_old_routes(monkeypatch):
    registry = load('clients/catalog_providers.py')
    calls = []
    qq = SimpleNamespace(SITE='115', find_sources=object())
    jk = load('clients/juku_provider.py')
    monkeypatch.setattr(registry, '_adapter', lambda name: qq if name=='qqdocs' else jk)
    manager = SimpleNamespace(deadline=time.monotonic()+1, cancelled=lambda:False,
        submit_task=lambda *a, **k:calls.append(a[1]))
    def submit():
        registry.submit_catalogs(manager, {}, 'movies', 0, 0, 2026, ['Movie'], None)
    submit()
    assert calls == ['qqdocs']
    source.save('https://catalog.example')
    submit()
    assert calls == ['qqdocs', 'qqdocs', 'juku']
    card = SimpleNamespace(type='Direct', guid='juku:'+'a'*64, url='am6bjuku://'+'a'*64, indexer=jk.SITE)
    assert registry.provider_for(card) == 'juku'
    source.remove()
    assert registry.provider_for(card) is None
    with pytest.raises(ValueError, match='SHARE_CATALOG_UNAVAILABLE'):
        share_catalog.catalog(dict(locator=card.url, guid=card.guid))


def test_idle_owner_attaches_after_save_and_detaches_after_worker_finishes():
    host = SimpleNamespace(refresh=None, refresh_worker=None, refresh_due=99)
    source.observe_host(host)
    assert host.refresh is None
    source.save('https://catalog.example')
    source.observe_host(host)
    assert host.refresh is source.refresh and host.refresh_due == 0
    host.refresh_worker = object()
    source.remove()
    source.observe_host(host)
    assert host.refresh is source.refresh
    assert host.refresh(time.monotonic()+1, lambda: False) == {'state':'DISABLED'}
    host.refresh_worker = None
    source.observe_host(host)
    assert host.refresh is None


def test_probe_sends_only_own_new_device_identity(monkeypatch):
    calls = []
    class Key:
        def public_key(self):return self
        def export_key(self, format):return b'own-test-key'
    monkeypatch.setattr(api.Client, '_key', lambda s: Key())
    from datetime import datetime, timezone
    future = datetime.fromtimestamp(time.time()+3600, timezone.utc).isoformat()
    def request(self, method, path, params, body, session, key, deadline, *a):
        calls.append((self.base, path, json.loads(body) if body else {}))
        if method == 'POST':
            return dict(deviceId='own', accessToken='access', refreshToken='refresh',
                accessExpiresAt=future, refreshExpiresAt=future)
        return {'items':[]}
    monkeypatch.setattr(api.Client, '_request', request)
    assert source.check('https://catalog.example', time.monotonic()+3)
    assert calls[0][1] == '/auth/device/register'
    assert set(calls[0][2]) == {'publicKey','platform','appVersion','installId'}
    assert calls[1][1] == '/shared-libraries/public'
    assert source.current() is None


def test_actual_dialog_entry_saves_only_successful_connection(profile, monkeypatch):
    from bobbi_platform import library_ui
    monkeypatch.setattr(library_ui.cd2_mounts, 'discover', lambda: ())
    shown = []
    dialog = SimpleNamespace(select=lambda title, items:items.index('源库网址'),
        input=lambda *a, **k:'https://catalog.example', ok=lambda *a:shown.append(a))
    monkeypatch.setattr(ui, 'operation', lambda action:action(time.monotonic()+1, lambda:False))
    monkeypatch.setattr(api.Client, 'get', lambda *a, **k:dict(items=[]))
    with closing(Registry(profile/'libraries.sqlite3')) as store:
        assert library_ui.add_source(dialog, None, store)
    assert source.current().endpoint == 'https://catalog.example'
    assert shown[-1][0] == '源库已连接'


def test_failed_or_cancelled_ui_does_not_replace_existing(profile, monkeypatch):
    old = source.save('https://previous.example')
    shown = []
    dialog = SimpleNamespace(input=lambda *a, **k:'https://new.example', ok=lambda *a:shown.append(a))
    monkeypatch.setattr(ui, 'operation', lambda action:None)
    assert not ui.add(dialog, None, old) and source.current() == old
    def fail(action):raise api.JukuError('HTTP_503')
    monkeypatch.setattr(ui, 'operation', fail)
    assert not ui.add(dialog, None, old) and source.current() == old
    assert '原来源保留' in shown[-1][1]


def test_remote_json_uses_normal_catalog_validation_and_byte_limit(monkeypatch):
    import urllib.request
    raw = json.dumps(dict(schema='bobbi-library-v1', name='My library',
        items=[dict(id='1', title='Movie', url='https://video.example/movie.mkv')])).encode()
    class Response(io.BytesIO):
        headers = {'Content-Length':str(len(raw))}
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *a:SimpleNamespace(
        open=lambda *a, **k:Response(raw)))
    result = source.read_document('https://catalog.example/movies.json', time.monotonic()+1)
    assert len(result.items)==1 and source.current() is None
    Response.headers = {'Content-Length':str(len(raw)+1)}
    with pytest.raises(api.JukuError, match='SHORT_READ'):
        source.read_document('https://catalog.example/movies.json', time.monotonic()+1)


def test_profile_corruption_never_enables_network(profile):
    (profile/'source-library.json').write_text('{bad')
    assert source.current() is None
    (profile/'source-library.json').write_text(json.dumps(dict(schema=1, endpoint='https://example', generation='bad')))
    assert source.current() is None

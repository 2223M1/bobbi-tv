"""Loopback HTTP and launcher regression suite for R01 (PB-02) & R02 (PB-04)."""
from http.client import HTTPConnection
from http.server import HTTPServer
import importlib.util
import json
from pathlib import Path
import sys
from threading import Event, Thread
from types import ModuleType, SimpleNamespace

import pytest

from bobbi_platform.paths import ProfileBinding

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addons' / 'plugin.video.bobbi'


def _load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, PLUGIN / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def stremio_env(monkeypatch, tmp_path):
    profile_dir = [tmp_path / 'profile_A']
    binding = ProfileBinding(lambda addon: profile_dir[0] / addon)

    secret_url = 'https://stremio.example.invalid/TOKEN_DO_NOT_LEAK_998877/manifest.json'
    store = {
        'user': [
            dict(
                transportName='custom',
                transportUrl=secret_url,
                manifest=dict(
                    id="existing.addon'quote",
                    name='Existing Synthetic Addon',
                    version='1.0.0',
                    description='Synthetic stream addon',
                    resources=['stream'],
                    types=['movie'],
                ),
            )
        ],
        'streams': ["existing.addon'quote|0123456789abcdef"],
        'catalogs': [],
        'tv': [],
    }

    class FakeCache:
        def get(self, key):
            value = store.get(key)
            return json.loads(json.dumps(value)) if value is not None else None

        def set(self, key, value, *args, **kwargs):
            store[key] = json.loads(json.dumps(value))

    def stub_module(mod_name, **attrs):
        mod = ModuleType(mod_name)
        mod.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, mod_name, mod)
        return mod

    def instance_key(addon):
        manifest = addon.get('manifest') or {}
        aid = manifest.get('id') or 'unknown'
        return f'{aid}|0123456789abcdef'

    fetch_gate = dict(enter=Event(), release=Event(), payload=None)
    fetch_gate['release'].set()

    def fake_redirect_get(getter, target_url, **kwargs):
        fetch_gate['enter'].set()
        assert fetch_gate['release'].wait(3)
        payload = fetch_gate['payload'] or dict(
            id='new.synthetic.addon',
            name='New Synthetic Addon',
            version='2.1.0',
            description='Added via paired session',
            resources=['stream', 'catalog'],
            types=['movie', 'series'],
        )
        raw = json.dumps(payload).encode('utf-8')
        return SimpleNamespace(
            url=target_url,
            raise_for_status=lambda: None,
            iter_content=lambda chunk_size=8192: [raw],
        )

    stub_module('lib.api.stremio.addon_manager', build_addon_instance_key=instance_key)
    stub_module(
        'lib.clients.stremio.constants',
        STREMIO_ADDONS_CATALOGS_KEY='catalogs',
        STREMIO_ADDONS_KEY='streams',
        STREMIO_TV_ADDONS_KEY='tv',
        STREMIO_USER_ADDONS='user',
        decode_selected_ids=lambda v: list(v or []),
        encode_selected_ids=lambda v: list(v),
    )
    stub_module(
        'lib.clients.stremio.protocol',
        MAX_RESOURCE_JSON_BYTES=65536,
        is_safe_http_url=lambda u: u.startswith('https://'),
        request_with_safe_redirects=fake_redirect_get,
    )
    stub_module('lib.db.cached', cache=FakeCache())
    stub_module('lib.utils.general.utils', USER_AGENT_HEADER={'User-Agent': 'test'})
    stub_module('lib.utils.kodi.utils', kodilog=lambda *a: None, ADDON_PATH=str(PLUGIN), translation=lambda i: f'L{i}', notification=lambda *a: None)

    phone_mod = _load('lib.services.phone_management', 'lib/services/phone_management.py')
    monkeypatch.setitem(sys.modules, 'lib.services.phone_management', phone_mod)
    web_mod = _load('lib.services.webserver', 'lib/services/webserver.py')
    monkeypatch.setitem(sys.modules, 'lib.services.webserver', web_mod)

    server = HTTPServer(('127.0.0.1', 0), web_mod.StremioRequestHandler)
    origin = f'http://127.0.0.1:{server.server_port}'
    manager = phone_mod.PhoneManagement(
        {'local_scope': 'stremio_addons'},
        origin,
        scopes=phone_mod.STREMIO_SCOPES,
        profile_binding=binding,
    )
    server.phone_management = manager
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    worker.start()

    def request(path, body=None, headers=None, method='POST'):
        conn = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            raw_body = phone_mod.encode(body) if body is not None else (b'{}' if method == 'POST' else None)
            merged = {'Host': f'127.0.0.1:{server.server_port}'}
            if method == 'POST':
                merged['Content-Type'] = 'application/json'
                merged['Origin'] = origin
            if headers:
                merged.update(headers)
            conn.request(method, path, body=raw_body, headers=merged)
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    try:
        yield SimpleNamespace(
            request=request,
            server=server,
            manager=manager,
            phone_mod=phone_mod,
            web_mod=web_mod,
            store=store,
            secret_url=secret_url,
            profile_dir=profile_dir,
            fetch_gate=fetch_gate,
            tmp_path=tmp_path,
        )
    finally:
        manager.revoke()
        server.shutdown()
        server.server_close()
        worker.join(2)


def test_r01_01_02_anonymous_legacy_routes_and_unpaired_server_rejected_without_mutation(stremio_env):
    before = json.loads(json.dumps(stremio_env.store))
    with pytest.raises(ValueError, match='PHONE_MANAGEMENT_REQUIRED'):
        stremio_env.web_mod.StremioWebServer(port=0, phone_management=None)

    for manager_state in (stremio_env.manager, None):
        stremio_env.server.phone_management = manager_state
        status, headers, body = stremio_env.request('/api/addons', method='GET', headers={'Origin': 'https://evil.invalid'})
        assert status == 404
        assert 'Access-Control-Allow-Origin' not in headers
        assert b'TOKEN_DO_NOT_LEAK_998877' not in body

        del_status, del_headers, _ = stremio_env.request('/api/addons/existing', method='DELETE', headers={'Origin': 'https://evil.invalid'})
        assert del_status == 404
        assert 'Access-Control-Allow-Origin' not in del_headers

        root_status, _, _ = stremio_env.request('/', method='GET')
        assert root_status == 404

        opt_status, opt_headers, _ = stremio_env.request('/api/addons', method='OPTIONS')
        assert opt_status == 403
        assert 'Access-Control-Allow-Origin' not in opt_headers

    assert stremio_env.store == before
    assert not (PLUGIN / 'resources' / 'web' / 'index.html').exists()


def test_r01_03_04_origin_csrf_redacted_crud_and_logo_protocol_gate(stremio_env):
    code = stremio_env.manager.pairing_url.split('#')[1]
    status, headers, raw = stremio_env.request('/manage/api/pair', body={'code': code})
    assert status == 200
    session = json.loads(raw)
    assert session['scopes'] == ['stremio_addons']
    cookie = headers['Set-Cookie'].split(';')[0]
    csrf = session['csrf']

    # Wrong Origin or missing/wrong CSRF rejected; no cache side effects
    before = json.loads(json.dumps(stremio_env.store))
    assert stremio_env.request(
        '/manage/api',
        body={'action': 'stremio_remove', 'params': {'id': "existing.addon'quote|0123456789abcdef"}},
        headers={'Cookie': cookie, 'X-Bobbi-CSRF': csrf, 'Origin': 'http://evil.invalid'},
    )[0] == 403
    assert stremio_env.request(
        '/manage/api',
        body={'action': 'stremio_remove', 'params': {'id': "existing.addon'quote|0123456789abcdef"}},
        headers={'Cookie': cookie, 'X-Bobbi-CSRF': 'wrong'},
    )[0] == 403
    # Unrelated catalog scope rejected
    assert stremio_env.request(
        '/manage/api',
        body={'action': 'catalog_items', 'params': {}},
        headers={'Cookie': cookie, 'X-Bobbi-CSRF': csrf},
    )[0] == 403
    assert stremio_env.store == before

    auth = {'Cookie': cookie, 'X-Bobbi-CSRF': csrf}
    # List redacts transportUrl while keeping exact host and ID
    status, _, raw = stremio_env.request('/manage/api', body={'action': 'stremio_list', 'params': {}}, headers=auth)
    assert status == 200
    listed = json.loads(raw)
    assert b'TOKEN_DO_NOT_LEAK_998877' not in raw
    assert 'transportUrl' not in listed['items'][0]
    assert listed['items'][0]['id'] == "existing.addon'quote|0123456789abcdef"
    assert listed['items'][0]['host'] == 'stremio.example.invalid'

    # Reject non-HTTP(S) manifest logo at validation/add boundary (R02-03)
    stremio_env.fetch_gate['payload'] = dict(
        id='bad.logo.addon',
        name='Bad Logo',
        logo='javascript:alert(1)',
        resources=['stream'],
        types=['movie'],
    )
    bad_status, _, bad_raw = stremio_env.request(
        '/manage/api',
        body={'action': 'stremio_add', 'params': {'url': 'https://good.example.invalid/manifest.json'}},
        headers=auth,
    )
    assert bad_status == 400 and json.loads(bad_raw)['error'] == 'STREMIO_LOGO_REJECTED'
    assert len(stremio_env.store['user']) == 1

    # Add, toggle, and remove synthetic addon
    stremio_env.fetch_gate['payload'] = None
    add_status, _, add_raw = stremio_env.request(
        '/manage/api',
        body={'action': 'stremio_add', 'params': {'url': 'https://addon.example.invalid/SECRET_KEY_2/manifest.json'}},
        headers=auth,
    )
    assert add_status == 200
    assert b'SECRET_KEY_2' not in add_raw
    added = json.loads(add_raw)['addon']
    assert added['id'] == 'new.synthetic.addon|0123456789abcdef'

    tog_status, _, _ = stremio_env.request(
        '/manage/api',
        body={'action': 'stremio_toggle', 'params': {'id': added['id'], 'category': 'stream', 'enabled': False}},
        headers=auth,
    )
    assert tog_status == 200
    assert added['id'] not in stremio_env.store['streams']

    rem_status, _, _ = stremio_env.request(
        '/manage/api',
        body={'action': 'stremio_remove', 'params': {'id': added['id']}},
        headers=auth,
    )
    assert rem_status == 200
    assert len(stremio_env.store['user']) == 1


@pytest.mark.parametrize('reason', ['qr_closed', 'profile_switched'])
def test_r01_05_revoked_or_switched_inflight_add_never_commits_to_cache(stremio_env, reason):
    code = stremio_env.manager.pairing_url.split('#')[1]
    status, headers, raw = stremio_env.request('/manage/api/pair', body={'code': code})
    assert status == 200
    auth = {'Cookie': headers['Set-Cookie'].split(';')[0], 'X-Bobbi-CSRF': json.loads(raw)['csrf']}

    stremio_env.fetch_gate['enter'].clear()
    stremio_env.fetch_gate['release'].clear()
    outcomes = []

    def inflight_add():
        outcomes.append(
            stremio_env.request(
                '/manage/api',
                body={'action': 'stremio_add', 'params': {'url': 'https://late.example.invalid/manifest.json'}},
                headers=auth,
            )
        )

    t = Thread(target=inflight_add)
    t.start()
    assert stremio_env.fetch_gate['enter'].wait(3)

    if reason == 'qr_closed':
        stremio_env.manager.revoke()
    else:
        stremio_env.profile_dir[0] = stremio_env.tmp_path / 'profile_B'

    stremio_env.fetch_gate['release'].set()
    t.join(3)
    assert not t.is_alive()
    assert outcomes[0][0] == 401
    assert len(stremio_env.store['user']) == 1


def test_stremio_manage_phone_launcher_uses_paired_grant_and_revokes_on_close(stremio_env, monkeypatch):
    captured = {}

    class DummyQR:
        def __init__(self, *args):
            pass

        def setup(self, **kwargs):
            captured['setup'] = kwargs

        def doModal(self):
            captured['live_during_modal'] = not captured['server'].phone_management.closed

    class DummyServer:
        is_running = True

        def __init__(self, port=8081, phone_management=None):
            captured['port'] = port
            captured['manager'] = phone_management
            self.phone_management = phone_management
            captured['server'] = self

        def start(self):
            captured['started'] = True

        def stop(self):
            self.phone_management.revoke()
            captured['stopped'] = True

    monkeypatch.setitem(
        sys.modules,
        'xbmcgui',
        SimpleNamespace(Dialog=lambda: SimpleNamespace(yesno=lambda *a: True)),
    )
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda p: str(stremio_env.tmp_path / p.rsplit('/', 1)[-1])))
    monkeypatch.setitem(sys.modules, 'lib.gui.qr_progress_dialog', SimpleNamespace(QRProgressDialog=DummyQR))
    monkeypatch.setitem(sys.modules, 'lib.utils.debrid.qrcode_utils', SimpleNamespace(make_qrcode=lambda u: '/tmp/qr.png'))
    monkeypatch.setattr(stremio_env.web_mod, 'StremioWebServer', DummyServer)
    monkeypatch.setattr(stremio_env.web_mod, 'get_local_ip', lambda: '192.168.1.50')

    launcher = _load('lib.clients.stremio.manage_phone', 'lib/clients/stremio/manage_phone.py')
    assert launcher.stremio_manage_phone({}) is True
    assert captured['manager'].scopes == stremio_env.phone_mod.STREMIO_SCOPES
    assert '/manage#' in captured['setup']['url']
    assert captured['live_during_modal'] is True
    assert captured['stopped'] is True and captured['manager'].closed is True

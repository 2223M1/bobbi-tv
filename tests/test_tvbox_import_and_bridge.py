"""Closed-loop regression suite for TVBox / T4 3-channel import, paired chunked source_import,
format-probed lives export, and check_t4_bridge validator.

Covers R19-01..14 and REV-12.
"""
from __future__ import annotations

import base64
import hashlib
from http.client import HTTPConnection
from http.server import HTTPServer
import importlib.util
import json
from pathlib import Path
import sys
from threading import Thread
from types import ModuleType, SimpleNamespace

import pytest

from bobbi_core.library_contract import LibraryError
from bobbi_platform import library_ui, t4_ui
from bobbi_platform.libraries import Registry
from bobbi_platform.paths import ProfileBinding

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addons' / 'plugin.video.bobbi'


def _load_mod(name: str, full_path: Path):
    spec = importlib.util.spec_from_file_location(name, full_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic_20660b_tvbox_config() -> bytes:
    """Build a deterministic 20,660-byte synthetic TVBox config (0 type-4, 50 type-3, 7 lives)."""
    sites = []
    for idx in range(50):
        sites.append({
            'key': f'csp_synth_{idx:02d}',
            'name': f'测试爬虫源 {idx:02d}',
            'type': 3,
            'api': 'csp_AList' if idx % 2 == 0 else 'csp_WebDAV',
            'searchable': 1,
            'quickSearch': 1,
            'filterable': 1,
            'jar': './spider.jar;md5;0123456789abcdef0123456789abcdef',
            'ext': f'https://alist-synth-{idx:02d}.example.invalid/dav/config_{idx:04d}.json',
        })
    lives = [
        {
            'name': f'测试直播源 {i + 1}',
            'type': 0,
            'url': f'https://live-synth.example.invalid/list_{i + 1}.m3u',
            'epg': 'https://epg.example.invalid/?ch={name}&date={date}',
        }
        for i in range(7)
    ]
    doc = {
        'spider': './spider.jar;md5;0123456789abcdef0123456789abcdef',
        'wallpaper': 'https://img.example.invalid/wall.jpg',
        'sites': sites,
        'lives': lives,
        'parses': [{'name': 'jx1', 'type': 0, 'url': 'https://jx.example.invalid/?url='}],
        'doh': [{'name': 'DNSPod', 'url': 'https://doh.pub/dns-query'}],
    }
    raw = json.dumps(doc, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) < 20660:
        pad_needed = 20660 - len(raw) - 18
        doc['_note'] = 'x' * max(1, pad_needed)
        raw = json.dumps(doc, ensure_ascii=False, indent=2).encode('utf-8')
    return raw


@pytest.fixture
def import_server(monkeypatch, tmp_path):
    profile_dir = [tmp_path / 'profile_main']
    binding = ProfileBinding(lambda addon: profile_dir[0] / addon)

    def stub_mod(mod_name, **attrs):
        m = ModuleType(mod_name)
        m.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, mod_name, m)
        return m

    stub_mod('lib.api.stremio.addon_manager', build_addon_instance_key=lambda a: 'id|0')
    stub_mod(
        'lib.clients.stremio.constants',
        STREMIO_ADDONS_CATALOGS_KEY='catalogs',
        STREMIO_ADDONS_KEY='streams',
        STREMIO_TV_ADDONS_KEY='tv',
        STREMIO_USER_ADDONS='user',
        decode_selected_ids=lambda v: list(v or []),
        encode_selected_ids=lambda v: list(v),
    )
    stub_mod(
        'lib.clients.stremio.protocol',
        MAX_RESOURCE_JSON_BYTES=65536,
        is_safe_http_url=lambda u: True,
        request_with_safe_redirects=lambda *a, **kw: None,
    )
    stub_mod('lib.db.cached', cache=SimpleNamespace(get=lambda k: None, set=lambda *a, **kw: None))
    stub_mod('lib.utils.general.utils', USER_AGENT_HEADER={'User-Agent': 'test'})
    stub_mod('lib.utils.kodi.utils', kodilog=lambda *a: None, ADDON_PATH=str(PLUGIN), translation=lambda i: f'L{i}', notification=lambda *a: None)
    phone_mod = _load_mod('lib.services.phone_management', PLUGIN / 'lib/services/phone_management.py')
    monkeypatch.setitem(sys.modules, 'lib.services.phone_management', phone_mod)
    web_mod = _load_mod('lib.services.webserver', PLUGIN / 'lib/services/webserver.py')
    monkeypatch.setitem(sys.modules, 'lib.services.webserver', web_mod)

    assert phone_mod.MAX_BODY == 8192

    server = HTTPServer(('127.0.0.1', 0), web_mod.StremioRequestHandler)
    origin = f'http://127.0.0.1:{server.server_port}'
    manager = phone_mod.PhoneManagement(
        {'local_scope': 'source_import'},
        origin,
        scopes=phone_mod.SOURCE_IMPORT_SCOPES,
        profile_binding=binding,
    )
    server.phone_management = manager
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    worker.start()

    def post_json(path: str, payload: dict, headers: dict | None = None):
        raw = phone_mod.encode(payload)
        assert len(raw) <= phone_mod.MAX_BODY
        conn = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            hdrs = {
                'Host': f'127.0.0.1:{server.server_port}',
                'Origin': origin,
                'Content-Type': 'application/json',
            }
            if headers:
                hdrs.update(headers)
            conn.request('POST', path, body=raw, headers=hdrs)
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), json.loads(resp.read().decode('utf-8'))
        finally:
            conn.close()

    try:
        yield SimpleNamespace(
            post=post_json,
            manager=manager,
            phone_mod=phone_mod,
            web_mod=web_mod,
            binding=binding,
            profile_dir=profile_dir,
            tmp_path=tmp_path,
        )
    finally:
        manager.revoke()
        server.shutdown()
        server.server_close()
        worker.join(2.0)


def test_paired_chunked_20kb_tvbox_upload_idempotency_hash_cleanup_and_zero_registry_pollution(import_server):
    """R19-06, R19-11..14: 20KB+ JSON uploaded in 4096B chunks under MAX_BODY=8192; 0 type-4 writes nothing."""
    code = import_server.manager.pairing_url.split('#')[1]
    st, hdrs, sess = import_server.post('/manage/api/pair', {'code': code})
    assert st == 200 and sess['scopes'] == ['source_import']
    auth = {'Cookie': hdrs['Set-Cookie'].split(';')[0], 'X-Bobbi-CSRF': sess['csrf']}

    raw_cfg = _synthetic_20660b_tvbox_config()
    assert len(raw_cfg) > 20000
    digest = hashlib.sha256(raw_cfg).hexdigest()
    uid = 'a1' * 16

    st, _, begin_res = import_server.post('/manage/api', {
        'action': 'source_import_begin',
        'params': {
            'upload_id': uid,
            'file_name': 'my_ext_synth.json',
            'total_bytes': len(raw_cfg),
            'sha256': digest,
        },
    }, auth)
    assert st == 200 and begin_res['offset'] == 0

    chunk_size = 4096
    for pos in range(0, len(raw_cfg), chunk_size):
        piece = raw_cfg[pos:pos + chunk_size]
        b64 = base64.b64encode(piece).decode('ascii')
        st, _, ch_res = import_server.post('/manage/api', {
            'action': 'source_import_chunk',
            'params': {'upload_id': uid, 'offset': pos, 'data_b64': b64},
        }, auth)
        assert st == 200
        assert ch_res['offset'] == pos + len(piece)
        if pos == 0:
            # Idempotent retry of chunk 0 succeeds without corrupting offset!
            st_retry, _, retry_res = import_server.post('/manage/api', {
                'action': 'source_import_chunk',
                'params': {'upload_id': uid, 'offset': 0, 'data_b64': b64},
            }, auth)
            assert st_retry == 200 and retry_res['offset'] == len(piece)

    st, _, commit_res = import_server.post('/manage/api', {
        'action': 'source_import_commit',
        'params': {'upload_id': uid},
    }, auth)
    assert st == 200
    assert commit_res['awaiting_tv_confirm'] is False
    diag = commit_res['diagnosis']
    assert diag['can_save_t4'] is False
    assert diag['counts']['type4'] == 0
    assert diag['counts']['type3'] == 50
    assert diag['counts']['lives'] == 7
    assert '://' not in json.dumps(commit_res)

    # Verify zero staging files left and zero Registry created!
    plat_root = import_server.binding.root('script.module.bobbi.platform')
    assert not (plat_root / 'source-import-staging').exists()
    assert not (plat_root / 'libraries.sqlite3').exists()

    # Out-of-order chunk offset or tampered hash fails closed and cleans up temp file
    uid_bad = 'b2' * 16
    import_server.post('/manage/api', {
        'action': 'source_import_begin',
        'params': {'upload_id': uid_bad, 'file_name': 'bad.json', 'total_bytes': 10, 'sha256': '0' * 64},
    }, auth)
    st_gap, _, _ = import_server.post('/manage/api', {
        'action': 'source_import_chunk',
        'params': {'upload_id': uid_bad, 'offset': 4, 'data_b64': base64.b64encode(b'1234').decode('ascii')},
    }, auth)
    assert st_gap == 409
    assert not (plat_root / 'source-import-staging').exists()

    # Revoke during active upload deletes temp file immediately (R19-13)
    uid_rev = 'c3' * 16
    import_server.post('/manage/api', {
        'action': 'source_import_begin',
        'params': {'upload_id': uid_rev, 'file_name': 'rev.json', 'total_bytes': 100, 'sha256': 'f' * 64},
    }, auth)
    assert (plat_root / 'source-import-staging' / f'{uid_rev}.part').is_file()
    import_server.manager.revoke()
    assert not (plat_root / 'source-import-staging').exists()


def test_phone_upload_valid_t4_commits_only_after_tv_confirmation(import_server, monkeypatch):
    """R19-02, R19-11: Valid T4 config uploaded by phone requires TV yesno confirmation before Registry save."""
    valid_t4 = json.dumps({
        'sites': [{
            'key': 'phone_t4',
            'name': '手机导入 T4',
            'type': 4,
            'api': '/api/t4/vod',
            'searchable': 1,
        }]
    }).encode('utf-8')
    digest = hashlib.sha256(valid_t4).hexdigest()
    base_url = 'https://bridge.example.invalid/sub/all.json'

    class DummyQR:
        def __init__(self, *a):
            pass

        def setup(self, **kw):
            self.url = kw['url']

        def doModal(self):
            code = self.url.split('#')[1]
            _, hdrs, sess = post_fn('/manage/api/pair', {'code': code})
            auth = {'Cookie': hdrs['Set-Cookie'].split(';')[0], 'X-Bobbi-CSRF': sess['csrf']}
            uid = 'd4' * 16
            post_fn('/manage/api', {
                'action': 'source_import_begin',
                'params': {
                    'upload_id': uid,
                    'file_name': 't4.json',
                    'total_bytes': len(valid_t4),
                    'sha256': digest,
                    'base_url': base_url,
                },
            }, auth)
            post_fn('/manage/api', {
                'action': 'source_import_chunk',
                'params': {'upload_id': uid, 'offset': 0, 'data_b64': base64.b64encode(valid_t4).decode('ascii')},
            }, auth)
            st, _, res = post_fn('/manage/api', {
                'action': 'source_import_commit',
                'params': {'upload_id': uid},
            }, auth)
            assert st == 200 and res['awaiting_tv_confirm'] is True

    active_srv = {}

    def post_fn(path, payload, headers=None):
        srv = active_srv['server']
        raw = import_server.phone_mod.encode(payload)
        conn = HTTPConnection('127.0.0.1', srv.port, timeout=3)
        try:
            hdrs = {
                'Host': f'127.0.0.1:{srv.port}',
                'Origin': f'http://127.0.0.1:{srv.port}',
                'Content-Type': 'application/json',
            }
            if headers:
                hdrs.update(headers)
            conn.request('POST', path, body=raw, headers=hdrs)
            r = conn.getresponse()
            return r.status, dict(r.getheaders()), json.loads(r.read().decode('utf-8'))
        finally:
            conn.close()

    orig_ws = import_server.web_mod.StremioWebServer

    class EphemeralWS(orig_ws):
        def __init__(self, port=8081, phone_management=None):
            # Bind ephemeral port and align PhoneManagement origin for loopback test
            super().__init__(port=0, phone_management=phone_management)
            active_srv['server'] = self

        def start(self):
            super().start()
            self.port = self._server.server_port
            self.phone_management.origin = f'http://127.0.0.1:{self.port}'
            self.phone_management.host = f'127.0.0.1:{self.port}'

    plat_root = import_server.binding.root('script.module.bobbi.platform')
    plat_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr('bobbi_platform.paths.ProfileBinding', lambda: import_server.binding)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(executebuiltin=lambda *a: None))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        Dialog=lambda: SimpleNamespace(yesno=lambda *a: True, ok=lambda *a: None, select=lambda *a: 0)
    ))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(plat_root)))
    monkeypatch.setitem(sys.modules, 'lib.gui.qr_progress_dialog', SimpleNamespace(QRProgressDialog=DummyQR))
    monkeypatch.setitem(sys.modules, 'lib.utils.debrid.qrcode_utils', SimpleNamespace(make_qrcode=lambda u: '/tmp/q.png'))

    launcher = _load_mod('lib.clients.stremio.manage_phone', PLUGIN / 'lib/clients/stremio/manage_phone.py')
    monkeypatch.setattr(launcher, 'StremioWebServer', EphemeralWS)
    monkeypatch.setattr(launcher, 'get_local_ip', lambda: '127.0.0.1')

    assert launcher.source_import_manage_phone({}) is True
    reg = Registry(plat_root / 'libraries.sqlite3', read_only=True)
    try:
        saved = reg.sources()
        assert len(saved) == 1 and saved[0].kind == 't4'
        assert saved[0].metadata['sites'][0]['api'] == 'https://bridge.example.invalid/api/t4/vod'
    finally:
        reg.close()


def test_three_tv_import_channels_native_handoff_and_probed_lives_export(tmp_path, monkeypatch):
    """R19-01..10: TV phone launcher, native WebDAV handoff, and probed standalone lives M3U8 export."""
    builtins = []
    monkeypatch.setattr('bobbi_platform.paths.ProfileBinding', lambda: SimpleNamespace(require_current=lambda: None))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(executebuiltin=lambda cmd: builtins.append(cmd)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ALPHANUM_HIDE_INPUT=1))

    store = Registry(tmp_path / 'libraries.sqlite3')
    try:
        # Option 2 ('phone') triggers paired phone import plugin action
        dlg_phone = SimpleNamespace(select=lambda *a: 2)
        assert t4_ui.add(dlg_phone, None, store) is False
        assert builtins == ['RunPlugin(plugin://plugin.video.bobbi/?action=source_import_manage_phone)']

        # Option 3 ('native_handoff' -> 'webdav') guides user into native WebDAV source
        inputs = iter(['https://alist.example.invalid/dav/', '我的小雅 AList', ''])
        selects = iter([3, 0])
        dlg_dav = SimpleNamespace(
            select=lambda *a: next(selects),
            input=lambda *a, **kw: next(inputs),
            yesno=lambda *a: True,
            ok=lambda *a: None,
        )
        assert t4_ui.add(dlg_dav, None, store) is True
        assert len(store.sources()) == 1 and store.sources()[0].location == 'davs://alist.example.invalid/dav/'
    finally:
        store.close()

    # Format-probed lives export converts TVBox #genre# txt into #EXTM3U without touching PVR settings!
    raw_cfg = _synthetic_20660b_tvbox_config()
    genre_txt = '央视频道,#genre#\nCCTV-1,https://live.example.invalid/cctv1.m3u8\n卫视,#genre#\n湖南卫视,https://live.example.invalid/hnws.m3u8\n'.encode('utf-8')
    exported = t4_ui.export_probed_lives_playlist(raw_cfg, tmp_path / 'exports', index=0, fetch_fn=lambda u: genre_txt)
    assert exported['channel_count'] == 2
    content = Path(exported['path']).read_text(encoding='utf-8')
    assert content.startswith('#EXTM3U\n') and 'group-title="央视频道",CCTV-1' in content

    # HTML or JSON disguised as a live playlist is rejected!
    for bad_live in (b'<html>404</html>', b'{"error":"denied"}', b''):
        with pytest.raises(LibraryError):
            t4_ui.export_probed_lives_playlist(raw_cfg, tmp_path / 'exports', index=0, fetch_fn=lambda u: bad_live)


def test_check_t4_bridge_cli_respects_searchable_flag():
    """REV-12: tools/check_t4_bridge.py skips search when searchable=False and validates all 5 steps when True."""
    bridge = _load_mod('check_t4_bridge', ROOT / 'tools/check_t4_bridge.py')

    def fake_fetch(url):
        if 'wd=' in url:
            return json.dumps({'list': [{'vod_id': 'v1', 'vod_name': 'Movie'}]}).encode('utf-8')
        if 'ids=' in url:
            return json.dumps({
                'list': [{'vod_id': 'v1', 'vod_name': 'Movie', 'vod_play_from': 'L1', 'vod_play_url': 'Ep1$e1'}]
            }).encode('utf-8')
        if 'play=' in url:
            return json.dumps({'parse': 0, 'url': 'https://t4.example.invalid/m.mp4'}).encode('utf-8')
        return json.dumps({
            'class': [{'type_id': '1', 'type_name': 'Film'}],
            'list': [{'vod_id': 'v1', 'vod_name': 'Movie'}],
        }).encode('utf-8')

    fake_media = lambda u, h: {'identity_mode': 'weak_session', 'size': 8192}

    res_no_search = bridge.probe_t4_site(
        {'key': 'k1', 'name': 'NoSearch', 'api': 'https://t4.example.invalid/vod', 'extend': '', 'searchable': False},
        fetch_fn=fake_fetch,
        media_probe_fn=fake_media,
    )
    assert res_no_search['steps']['search'] == 'SKIPPED'
    assert res_no_search['steps']['play'].startswith('PASS')

    res_search = bridge.probe_t4_site(
        {'key': 'k2', 'name': 'WithSearch', 'api': 'https://t4.example.invalid/vod', 'extend': '', 'searchable': True},
        fetch_fn=fake_fetch,
        media_probe_fn=fake_media,
    )
    assert res_search['steps']['search'] == 'PASS'
    assert res_search['steps']['play'].startswith('PASS')


def test_router_dispatches_source_import_manage_phone_without_tmdb_init(monkeypatch):
    """Real-device regression: RunPlugin(?action=source_import_manage_phone) must dispatch directly in router.py."""
    from types import SimpleNamespace
    monkeypatch.syspath_prepend(str(ROOT / 'addons/plugin.video.bobbi'))
    from lib import router

    called = []
    ended = []
    monkeypatch.setitem(
        sys.modules,
        'lib.clients.stremio.manage_phone',
        SimpleNamespace(source_import_manage_phone=lambda p: called.append(dict(p)) or True),
    )
    monkeypatch.setitem(
        sys.modules,
        'xbmcplugin',
        SimpleNamespace(endOfDirectory=lambda h, succeeded=True, cacheToDisc=True: ended.append((h, succeeded, cacheToDisc))),
    )
    assert router._get_route_handler('source_import_manage_phone') is router._route_stremio

    monkeypatch.setattr(sys, 'argv', ['plugin://plugin.video.bobbi/', '-1', '?action=source_import_manage_phone'])
    router.addon_router()
    assert called == [{'action': 'source_import_manage_phone'}]
    assert ended == []

    monkeypatch.setattr(sys, 'argv', ['plugin://plugin.video.bobbi/', '7', '?action=source_import_manage_phone'])
    router.addon_router()
    assert len(called) == 2
    assert ended == [(7, False, False)]


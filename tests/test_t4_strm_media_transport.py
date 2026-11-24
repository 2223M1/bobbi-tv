"""Closed-loop regression tests for T4 persistent tokens, native directory, controlled redirects,
weak_session STRM/T4 Range transport, and cloud explicit expiry parsing.

Covers R13-01..05, R14-01..08, R15, REV-08, REV-10, and REV-11.
"""
from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from threading import Thread
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, parse_qsl, urlsplit
from urllib.request import Request, urlopen

import pytest

from bobbi_core import t4
from bobbi_core.library_contract import LibraryError
from bobbi_platform import pan_stream, source_media_http, t4_http, t4_ui
from bobbi_platform.host import Host
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.pan_tokens import parse_download_expiry
from bobbi_platform.t4_tokens import MAX_TOKENS, T4TokenStore
from test_library_plugin import plugin


def test_t4_token_store_url_vod_id_persistence_lru_and_no_raw_fallback(tmp_path):
    """R13-01, R13-02, R13-05, REV-11: Opaque tokens hide URL-shaped vod_id and fail closed on expiry."""
    db_path = tmp_path / 't4-tokens.sqlite3'
    sid = 'a' * 32
    gen1 = '1' * 64
    gen2 = '2' * 64
    shash = 'c' * 64
    secret_vod = 'https://alist.lan.internal:5678/Aliyun/剧集/S01E01.mkv?sign=secret-never-leak'

    with T4TokenStore(db_path) as store:
        tok = store.put_item(sid, gen1, shash, secret_vod)
        assert re.fullmatch(r'[0-9a-f]{32}', tok)
        assert 'secret' not in tok and 'http' not in tok

    # Re-open across simulated restart
    with T4TokenStore(db_path, read_only=True) as ro:
        assert ro.get_item(sid, gen1, shash, tok) == secret_vod
        # Generation mismatch fails closed with T4_TOKEN_EXPIRED
        with pytest.raises(LibraryError, match='T4_TOKEN_EXPIRED'):
            ro.get_item(sid, gen2, shash, tok)

    # Bounded LRU eviction at MAX_TOKENS=4096: evicted token raises T4_TOKEN_EXPIRED and NEVER sends raw token!
    api_calls = []
    cfg = json.dumps({
        'sites': [{
            'key': 's1', 'name': 'S1', 'type': 4, 'api': 'https://t4.example.invalid/vod',
        }]
    }).encode('utf-8')
    src = t4.preview(cfg).source('https://t4.example.invalid/cfg.json')
    site = src.metadata['sites'][0]
    real_shash = t4_http._opaque(site['key'])

    with T4TokenStore(db_path) as store:
        first_tok = store.put_item(src.id, gen1, real_shash, secret_vod)
        for idx in range(MAX_TOKENS + 10):
            store.put_item(src.id, gen1, real_shash, f'vod-filler-{idx}')

    with T4TokenStore(db_path, read_only=True) as ro:
        choice = t4_http.selection_with_token(site, first_tok, 'LineA', 'ep1')
        with pytest.raises(LibraryError, match='T4_TOKEN_EXPIRED'):
            t4_http.resolve_selected(
                src,
                choice,
                generation=gen1,
                token_store=ro,
                fetch=lambda url: api_calls.append(url) or b'{}',
            )
    # Zero remote calls made when token expired!
    assert api_calls == []


def test_t4_custom_site_headers_only_sent_to_configured_api_origin(monkeypatch):
    """R13-03: Site custom headers are sent to site['api'] origin and stripped for any other origin."""
    sent_headers = []

    class FakeConn:
        def __init__(self, *a, **kw):
            pass

        def request(self, method, target, headers=None):
            sent_headers.append(dict(headers or {}))

        def getresponse(self):
            body = b'{"class":[],"list":[]}'
            pos = [0]

            def read1(n):
                if pos[0] >= len(body):
                    return b''
                chunk = body[pos[0]:pos[0] + n]
                pos[0] += len(chunk)
                return chunk

            return SimpleNamespace(
                status=200,
                getheader=lambda k, d='': d,
                read1=read1,
            )

        def close(self):
            pass

    monkeypatch.setattr(source_media_http, 'HTTPSConnection', FakeConn)
    hdrs = {'User-Agent': 'CustomTVBox/2.0', 'Referer': 'https://api.t4.invalid/'}

    t4_http.read(
        'https://api.t4.invalid/vod?filter=true',
        time.monotonic() + 5.0,
        lambda: False,
        headers=hdrs,
        expected_origin='https://api.t4.invalid/vod',
    )
    assert sent_headers[-1]['User-Agent'] == 'CustomTVBox/2.0'
    assert sent_headers[-1]['Referer'] == 'https://api.t4.invalid/'

    t4_http.read(
        'https://other.t4.invalid/vod?filter=true',
        time.monotonic() + 5.0,
        lambda: False,
        headers=hdrs,
        expected_origin='https://api.t4.invalid/vod',
    )
    assert 'Referer' not in sent_headers[-1]
    assert 'User-Agent' not in sent_headers[-1]


def test_weak_session_strm_and_controlled_3_hop_redirects(plugin, tmp_path, monkeypatch):
    """R14-01..08, REV-10: Weak/no-ETag 206 streams never send If-Match, follow <=3 redirects, abort on size change."""
    state = SimpleNamespace(
        payload=b'ABCDEFGHIJ',
        etag_header='W/"weak-etag-1"',  # Weak ETag; rejects If-Match with 412 like real nginx/CDN!
        mime='video/x-matroska',
        declared_size=10,
        redirect_hops=2,
        downgrade_scheme=False,
        loop_redirect=False,
        seen_requests=[],
    )

    class UpstreamHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            host_hdr = self.headers.get('Host', '')
            if_match = self.headers.get('If-Match')
            if_range = self.headers.get('If-Range')
            referer = self.headers.get('Referer')
            rng = self.headers.get('Range', '')
            state.seen_requests.append((host_hdr, self.path, rng, if_match, if_range, referer))

            # Real RFC 9110 servers reject If-Match against weak/absent ETag with 412!
            if if_match or if_range:
                self.send_error(412)
                return

            if self.path.startswith('/hop0'):
                if state.redirect_hops >= 1:
                    self.send_response(302)
                    self.send_header('Location', '/hop0' if state.loop_redirect else '/hop1?step=1')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
            if self.path.startswith('/hop1') and state.redirect_hops >= 2:
                self.send_response(302)
                scheme = 'http' if state.downgrade_scheme else 'https'
                next_loc = (
                    f'{scheme}://cdn.storage.invalid/hop2?sig=keep_raw'
                    if state.redirect_hops == 2
                    else '/hop2'
                )
                self.send_header('Location', next_loc)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if self.path == '/hop2' and state.redirect_hops >= 3:
                if state.redirect_hops > 3:
                    self.send_response(302)
                    self.send_header('Location', '/hop3')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                self.send_response(302)
                self.send_header('Location', 'https://cdn.storage.invalid/final.mkv?sig=keep_raw')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if self.path == '/hop3' and state.redirect_hops > 3:
                self.send_response(302)
                self.send_header('Location', '/hop4-too-many')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return

            m = re.fullmatch(r'bytes=(\d+)-(\d+)', rng)
            start, end = int(m[1]), int(m[2])
            chunk = state.payload[start:end + 1]
            self.send_response(206)
            self.send_header('Content-Type', state.mime)
            self.send_header('Content-Range', f'bytes {start}-{end}/{state.declared_size}')
            self.send_header('Content-Length', str(len(chunk)))
            if state.etag_header:
                self.send_header('ETag', state.etag_header)
            self.end_headers()
            self.wfile.write(chunk)

    server = ThreadingHTTPServer(('127.0.0.1', 0), UpstreamHandler)
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    worker.start()

    def fake_connection(url, remaining, **kwargs):
        u = urlsplit(url)
        assert u.hostname in ('xiaoya.lan', 'cdn.storage.invalid', 'secure.origin.invalid')
        target = (u.path or '/') + ('?' + u.query if u.query else '')
        return HTTPConnection('127.0.0.1', server.server_port, timeout=remaining()), target

    monkeypatch.setattr(source_media_http, 'connection', fake_connection)

    media_dir = tmp_path / 'strm_dir'
    media_dir.mkdir()
    strm_file = media_dir / 'Movie.strm'
    strm_file.write_bytes(b'http://xiaoya.lan:5678/hop0?token=lan\n')
    src = vfs_source('Xiaoya STRM', str(media_dir))
    reg = Registry(plugin.path)
    reg.save(src)
    reg.close()

    monkeypatch.setattr(
        plugin.module.xbmcgui,
        'Dialog',
        lambda: SimpleNamespace(yesno=lambda *a: True, ok=lambda *a: None),
    )
    host = Host(tmp_path)
    host.start()
    try:
        # 1. Open weak-ETag STRM across 2 redirects (LAN HTTP -> relative -> HTTPS CDN)
        plugin.module.execute(17, {'action': 'play_pointer', 'source': src.id, 'relative': 'Movie.strm'})
        assert plugin.resolved[-1][:2] == (17, True)
        li = plugin.resolved[-1][2]
        assert li.properties['StartOffset'] == '0'
        req_id = li.properties['bobbi.standard.request']
        assert host.owned_tracks[req_id]['data']['_owned_source']['identity_mode'] == 'weak_session'

        # Seek 1 & Seek 2 succeed with ZERO If-Match / If-Range headers and preserved signed query!
        with urlopen(Request(li.path, headers={'Range': 'bytes=0-3'}), timeout=3) as r1:
            assert r1.status == 206 and r1.read() == b'ABCD'
        with urlopen(Request(li.path, headers={'Range': 'bytes=6-9'}), timeout=3) as r2:
            assert r2.status == 206 and r2.read() == b'GHIJ'
        assert any('sig=keep_raw' in req[1] for req in state.seen_requests)
        assert all(req[3] is None and req[4] is None for req in state.seen_requests)

        # 2. Mutating total file size mid-session immediately aborts weak_session Range!
        state.declared_size = 99
        with pytest.raises((HTTPError, OSError)):
            urlopen(Request(li.path, headers={'Range': 'bytes=2-5'}), timeout=3).read()
        state.declared_size = 10

        # 3. 4-hop redirect, redirect loop, and HTTPS -> HTTP downgrade all fail closed!
        state.redirect_hops = 4
        with pytest.raises(LibraryError, match='MEDIA_REDIRECT'):
            source_media_http.probe_stream('https://secure.origin.invalid/hop0', {'Referer': 'https://secure.origin.invalid/'})

        state.redirect_hops = 2
        state.loop_redirect = True
        with pytest.raises(LibraryError, match='MEDIA_REDIRECT'):
            source_media_http.probe_stream('https://secure.origin.invalid/hop0', {})
        state.loop_redirect = False

        state.downgrade_scheme = True
        with pytest.raises(LibraryError, match='MEDIA_REDIRECT'):
            source_media_http.probe_stream('https://secure.origin.invalid/hop0', {})
        state.downgrade_scheme = False

        # Cross-origin redirect strips Referer!
        state.seen_requests.clear()
        res = source_media_http.probe_stream(
            'https://secure.origin.invalid/hop0',
            {'Referer': 'https://secure.origin.invalid/'},
        )
        assert res['identity_mode'] == 'weak_session'
        assert state.seen_requests[-1][5] is None
    finally:
        host.close()
        server.shutdown()
        server.server_close()
        worker.join(2.0)


def test_t4_native_kodi_directory_and_external_cdn_approval(plugin, tmp_path, monkeypatch):
    """R13-01, R14-02, R15: Native Kodi T4 directory routes (site -> cat/search -> detail -> play) + CDN prompt."""
    url_shaped_vod = 'https://internal.xiaoya/folder/科幻片$10086'

    def fake_t4_read(url, deadline, cancelled, **kwargs):
        q = parse_qs(urlsplit(url).query)
        if 'play' in q:
            return json.dumps({
                'parse': 0,
                'url': 'https://ext-cdn.provider.invalid/video/film.mp4',
                'header': {'Referer': 'https://t4.provider.invalid/'},
            }).encode('utf-8')
        if 'ids' in q:
            assert q['ids'] == [url_shaped_vod]
            return json.dumps({
                'list': [{
                    'vod_id': url_shaped_vod,
                    'vod_name': '星际穿越',
                    'vod_pic': 'https://img.provider.invalid/poster.jpg',
                    'vod_remarks': '4K HDR',
                    'vod_content': '穿越虫洞寻找新家园。',
                    'vod_play_from': '主线路$$$备用线路',
                    'vod_play_url': '正片$ep_main_1$$$正片$ep_bak_1',
                }]
            }).encode('utf-8')
        return json.dumps({
            'class': [{'type_id': 'scifi/2026', 'type_name': '科幻'}],
            'list': [{
                'vod_id': url_shaped_vod,
                'vod_name': '星际穿越',
                'vod_pic': 'https://img.provider.invalid/poster.jpg',
                'vod_remarks': '4K HDR',
            }],
            'pagecount': 1,
        }).encode('utf-8')

    def fake_probe_stream(url, headers, *a, **kw):
        assert url == 'https://ext-cdn.provider.invalid/video/film.mp4'
        # Cross-origin approved CDN must NOT receive private T4 API Referer!
        assert 'Referer' not in headers
        return {
            'size': 4096,
            'etag': '',
            'mime': 'video/mp4',
            'identity_mode': 'weak_session',
            'final_url': url,
        }

    monkeypatch.setattr(t4_ui, 'read', fake_t4_read)
    monkeypatch.setattr(t4_http, 'read', fake_t4_read)
    monkeypatch.setattr('bobbi_platform.source_streams.probe_stream', fake_probe_stream)

    cfg = json.dumps({
        'sites': [{
            'key': 'xy_t4',
            'name': '小雅 T4',
            'type': 4,
            'api': 'https://t4.provider.invalid/vod',
            'searchable': 1,
        }]
    }).encode('utf-8')
    src = t4.preview(cfg).source('https://t4.provider.invalid/config.json')
    reg = Registry(plugin.path)
    reg.save(src)
    reg.close()

    approvals = []
    monkeypatch.setattr(
        plugin.module.xbmcgui,
        'Dialog',
        lambda: SimpleNamespace(
            yesno=lambda title, body: approvals.append((title, body)) or True,
            input=lambda *a: '星际',
            ok=lambda *a: None,
        ),
    )

    host = Host(tmp_path)
    host.start()
    try:
        # Root shows T4 source as a real folder
        plugin.rows.clear()
        plugin.module.execute(17, {})
        t4_root = next((t, r, f) for t, r, f in plugin.rows if r.label == '小雅 T4')
        assert t4_root[2] is True

        # Browse T4 home -> renders Search, Category, and Recommended card with opaque token
        plugin.rows.clear()
        plugin.module.execute(17, dict(parse_qsl(urlsplit(t4_root[0]).query)))
        assert [r.label for _, r, _ in plugin.rows] == ['搜索本站', '科幻', '星际穿越']
        detail_url, card_item, is_folder = plugin.rows[2]
        assert is_folder is True
        assert 'internal.xiaoya' not in detail_url and '10086' not in detail_url
        assert card_item.art.get('poster') == 'https://img.provider.invalid/poster.jpg'

        # Open detail directory -> playable multi-line episodes with plot
        plugin.rows.clear()
        plugin.module.execute(17, dict(parse_qsl(urlsplit(detail_url).query)))
        assert plugin.content == 'episodes'
        assert [r.label for _, r, _ in plugin.rows] == ['主线路 · 正片', '备用线路 · 正片']
        play_url, ep_item, ep_folder = plugin.rows[0]
        assert ep_folder is False and ep_item.properties['IsPlayable'] == 'true'
        assert ep_item.info['plot'] == '穿越虫洞寻找新家园。'
        assert 'ep_main_1' not in play_url

        # Play episode -> prompts once for external CDN origin -> opens owned weak_session stream!
        plugin.module.execute(17, dict(parse_qsl(urlsplit(play_url).query)))
        assert len(approvals) == 1 and 'https://ext-cdn.provider.invalid' in approvals[0][1]
        assert plugin.resolved[-1][:2] == (17, True)
        assert plugin.resolved[-1][2].path.startswith('http://127.0.0.1:')
    finally:
        host.close()


def test_cloud_download_explicit_utc_expiry_parsing():
    """REV-08: Explicit ISO-8601 UTC and signed query epochs parse cleanly; absent expiry returns None."""
    now = 1_795_520_000.0
    iso_exp = datetime.fromtimestamp(now + 900, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    assert parse_download_expiry(iso_exp, '', now=now) == pytest.approx(now + 900)
    assert parse_download_expiry(
        None,
        f'https://cdn.alipan.com/video.mkv?x-oss-expires={int(now + 600)}&sig=abc',
        now=now,
    ) == pytest.approx(now + 600)
    # No fabricated TTL when upstream provides no explicit expiry
    assert parse_download_expiry(None, 'https://download.123pan.cn/file', now=now) is None

    res = pan_stream.address(
        {'provider': 'aliyun', 'size': 1024},
        {
            'url': f'https://cdn.alipan.com/video.mkv?x-oss-expires={int(now + 600)}',
            'size': 1024,
            'original': True,
            'headers': {'User-Agent': 'UA', 'Referer': 'https://www.alipan.com/'},
        },
        clock=lambda: now,
    )
    assert res.expires_at == pytest.approx(now + 600)

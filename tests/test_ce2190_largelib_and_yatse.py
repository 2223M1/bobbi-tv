"""CE2190 regression suite: large-library scale fixes (CAP-01/02/03), Emby UX ideas, and Yatse/Fuse3 smoothness."""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack, closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import struct
import sys
from threading import Thread
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, parse_qsl, urlsplit
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[1]
for rel in (
    'addons/script.module.bobbi.core/lib',
    'addons/script.module.bobbi.platform/lib',
    'addons/plugin.video.bobbi',
):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from bobbi_core.image_cache import ImageService
from bobbi_core.library_contract import Source
from bobbi_platform import emby_artwork, emby_dynamic, emby_session, runtime
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.server_plex import Client as PlexClient


def _png_1x1() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>II5B', 1, 1, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00'))
        + chunk(b'IEND', b'')
    )


PNG = _png_1x1()


class _FakeListItem:
    def __init__(self, label='', path=''):
        self.label = label
        self.label2 = ''
        self.path = path
        self.properties = {}
        self.context = []
        self.art = {}
        self.info = {}

    def setLabel2(self, value):
        self.label2 = value

    def setInfo(self, kind, value):
        self.info = dict(value)

    def setArt(self, value):
        self.art = dict(value)

    def addContextMenuItems(self, value):
        self.context = list(value)

    def setProperty(self, key, value):
        self.properties[key] = value

    def setContentLookup(self, _flag):
        pass


def test_cap01_large_season_next_episode_lookup_beyond_200_gaps_shifts_and_bounds(tmp_path):
    """CAP-01: >200-episode season next-episode lookup resolves in O(1)/O(log N) bounded HTTP requests."""
    counts = Counter()

    def ep_row(prefix: str, item_num: int, ep_index: int, *, season_num: int = 1, season_id: str = 'bigseason'):
        return {
            'Id': f'{prefix}{item_num}',
            'Name': f'Episode {ep_index:06d}',
            'Type': 'Episode',
            'IsFolder': False,
            'ParentIndexNumber': season_num,
            'IndexNumber': ep_index,
            'SeriesName': 'Long Series',
            'SeasonId': season_id,
        }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            u = urlsplit(self.path)
            q = parse_qs(u.query)
            counts[u.path] += 1
            if u.path == '/System/Info/Public':
                obj = {'Id': 's'}
            elif u.path == '/Users/u':
                obj = {'Id': 'u'}
            elif u.path == '/Users/u/Items':
                start = int(q['StartIndex'][0])
                size = int(q['Limit'][0])
                parent = q.get('ParentId', [''])[0]
                if parent == 'bigseason':
                    total = 1000
                    rows = [ep_row('g', i + 1, i + 1) for i in range(start, min(start + size, total))]
                elif parent == 'shifted':
                    # 15 leading specials (ParentIndexNumber=0) followed by 985 episodes (1..985)
                    total = 1000
                    rows = []
                    for i in range(start, min(start + size, total)):
                        if i < 15:
                            rows.append(ep_row('sp', i + 1, i + 1, season_num=0, season_id='shifted'))
                        else:
                            ep_no = i - 14
                            rows.append(ep_row('sh', ep_no, ep_no, season_num=1, season_id='shifted'))
                elif parent == 'gapseason':
                    # Episode 500 is missing: 1..499 then 501..1000 (total 999 items)
                    total = 999
                    rows = []
                    for i in range(start, min(start + size, total)):
                        ep_no = (i + 1) if i < 499 else (i + 2)
                        rows.append(ep_row('gp', ep_no, ep_no, season_num=1, season_id='gapseason'))
                elif parent == 'ultraseason':
                    # 250,000 episodes (> 200,000 single-directory ceiling)
                    total = 250000
                    rows = [ep_row('ul', i + 1, i + 1, season_id='ultraseason') for i in range(start, min(start + size, total))]
                else:
                    self.send_error(404)
                    return
                obj = {'Items': rows, 'TotalRecordCount': total}
            elif u.path.startswith('/Users/u/Items/'):
                ident = u.path.rsplit('/', 1)[1]
                prefix = ''.join(ch for ch in ident if ch.isalpha())
                num = int(''.join(ch for ch in ident if ch.isdigit()))
                obj = ep_row(prefix, num, num)
                if ident == 'g600':
                    obj['MediaSources'] = [
                        {'Id': 'm1', 'Protocol': 'File', 'Path': '/v/600a.mkv', 'Size': 100, 'SupportsDirectPlay': True},
                        {'Id': 'm2', 'Protocol': 'File', 'Path': '/v/600b.mkv', 'Size': 100, 'SupportsDirectPlay': True},
                    ]
                else:
                    obj['MediaSources'] = [
                        {'Id': f'm{num}', 'Protocol': 'File', 'Path': f'/v/{ident}.mkv', 'Size': 100, 'SupportsDirectPlay': True}
                    ]
            else:
                self.send_error(404)
                return
            raw = json.dumps(obj).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    th = Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    th.start()
    try:
        base = f'http://127.0.0.1:{srv.server_port}'
        store = Registry(tmp_path / 'libraries.sqlite3')
        source = Source(
            'b' * 32, 'Emby Scale', 'media_server', base, password='tok',
            metadata={'schema': 1, 'provider': 'emby', 'server_id': 's', 'user_id': 'u'},
        )
        store.save(source)
        rev = store.source_snapshot(source.id)[1]
        store.close()
        current = {'_owned_source': {'source_id': source.id, 'source_generation': rev, 'server_id': 's', 'user_id': 'u', 'provider': 'emby'}}

        # 1. Contiguous 1000-episode season: 199->200, 200->201, 999->1000 all succeed in <= 5 HTTP requests!
        for ep in (199, 200, 999):
            before = sum(counts.values())
            res = emby_session.resolve_next_episode_result(
                current,
                {'resolver': 'emby_same_season', 'profile_root': str(tmp_path), 'season_id': 'bigseason', 'season': 1, 'episode': ep},
                lambda: False,
                open_session=False,
            )
            used = sum(counts.values()) - before
            assert res.outcome == 'candidate', (ep, res)
            assert res.candidate['tv_data']['episode'] == ep + 1
            assert used <= 5, (ep, used)

        # 2. Final episode 1000 -> confirmed_end in <= 5 HTTP requests
        before = sum(counts.values())
        res_end = emby_session.resolve_next_episode_result(
            current,
            {'resolver': 'emby_same_season', 'profile_root': str(tmp_path), 'season_id': 'bigseason', 'season': 1, 'episode': 1000},
            lambda: False,
            open_session=False,
        )
        assert res_end.outcome == 'confirmed_end'
        assert (sum(counts.values()) - before) <= 5

        # 3. Shifted season (15 leading specials): 250 -> 251 resolved cleanly via binary search
        res_shift = emby_session.resolve_next_episode_result(
            current,
            {'resolver': 'emby_same_season', 'profile_root': str(tmp_path), 'season_id': 'shifted', 'season': 1, 'episode': 250},
            lambda: False,
            open_session=False,
        )
        assert res_shift.outcome == 'candidate' and res_shift.candidate['tv_data']['episode'] == 251

        # 4. Missing episode gap in >200-item season (499 -> 500 missing, 501 exists): never skips to 501; fails closed as page_limit
        res_gap = emby_session.resolve_next_episode_result(
            current,
            {'resolver': 'emby_same_season', 'profile_root': str(tmp_path), 'season_id': 'gapseason', 'season': 1, 'episode': 499},
            lambda: False,
            open_session=False,
        )
        assert res_gap.outcome == 'error' and res_gap.detail == 'page_limit'

        # 5. Multi-version episode 599 -> 600 requires explicit selection (never guesses)
        res_multi = emby_session.resolve_next_episode_result(
            current,
            {'resolver': 'emby_same_season', 'profile_root': str(tmp_path), 'season_id': 'bigseason', 'season': 1, 'episode': 599},
            lambda: False,
            open_session=False,
        )
        assert res_multi.outcome == 'needs_selection' and res_multi.detail == 'multi_version'

        # 6. Beyond 200,000-episode single-directory ceiling -> explicit page_limit (never false confirmed_end)
        res_ultra = emby_session.resolve_next_episode_result(
            current,
            {'resolver': 'emby_same_season', 'profile_root': str(tmp_path), 'season_id': 'ultraseason', 'season': 1, 'episode': 200050},
            lambda: False,
            open_session=False,
        )
        assert res_ultra.outcome == 'error' and res_ultra.detail == 'page_limit'
    finally:
        srv.shutdown()
        srv.server_close()
        th.join(2)


def test_cap03_directory_page_10000_limit_notice_and_deep_page_jump(tmp_path, monkeypatch):
    """CAP-03 + Jump UX: page 10000 never emits broken page=10001; deep lists expose Jump to Page."""
    http_calls = Counter()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            u = urlsplit(self.path)
            q = parse_qs(u.query)
            http_calls[u.path] += 1
            if u.path == '/System/Info/Public':
                obj = {'Id': 's'}
            elif u.path == '/Users/u':
                obj = {'Id': 'u'}
            elif u.path == '/Users/u/Items':
                start = int(q['StartIndex'][0])
                size = int(q['Limit'][0])
                parent = q.get('ParentId', [''])[0]
                total = 30000 if parent == 'movies' else 380000
                rows = [
                    {'Id': f'm{i + 1}', 'Name': f'Movie {i + 1:06d}', 'Type': 'Movie', 'IsFolder': False}
                    for i in range(start, min(start + size, total))
                ]
                obj = {'Items': rows, 'TotalRecordCount': total}
            else:
                self.send_error(404)
                return
            raw = json.dumps(obj).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    th = Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    th.start()
    try:
        base = f'http://127.0.0.1:{srv.server_port}'
        store = Registry(tmp_path / 'libraries.sqlite3')
        source = Source(
            'a' * 32, 'Emby Big', 'media_server', base, password='tok',
            metadata={'schema': 1, 'provider': 'emby', 'server_id': 's', 'user_id': 'u'},
        )
        store.save(source)
        rev = store.source_snapshot(source.id)[1]

        ui = SimpleNamespace(rows=[], endings=[], dialogs=[], builtins=[], numeric_pick='750')
        dialog = SimpleNamespace(
            ok=lambda *a: ui.dialogs.append(a),
            input=lambda *a: 'broad',
            numeric=lambda *a: ui.numeric_pick,
        )
        modules = {
            'xbmc': SimpleNamespace(
                Monitor=lambda: SimpleNamespace(abortRequested=lambda: False),
                executebuiltin=ui.builtins.append,
            ),
            'xbmcgui': SimpleNamespace(Dialog=lambda: dialog, ListItem=_FakeListItem),
            'xbmcvfs': SimpleNamespace(translatePath=lambda *a: str(tmp_path)),
            'xbmcplugin': SimpleNamespace(
                setPluginCategory=lambda *a: None,
                setContent=lambda *a: None,
                addDirectoryItems=lambda h, r, n: ui.rows.extend(r),
                endOfDirectory=lambda *a, **k: ui.endings.append(k),
                setResolvedUrl=lambda *a: None,
            ),
        }

        def make_item(label, target, folder=True, **kw):
            li = _FakeListItem(label)
            if kw.get('label2'):
                li.setLabel2(kw['label2'])
            li.properties.update(kw.get('properties') or {})
            return target, li, folder

        with ExitStack() as stack:
            stack.enter_context(closing(store))
            for mod_name, mod_val in modules.items():
                monkeypatch.setitem(sys.modules, mod_name, mod_val)
            monkeypatch.setattr(runtime, 'bind_call', lambda *a: lambda *b, **k: {'revision': 0})

            # 1. Page 10000 with total=380,000 in both ZH and EN: no broken page=10001 link!
            for english in (False, True):
                monkeypatch.setattr(emby_dynamic, 'is_english', lambda eng=english: eng)
                ui.rows.clear()
                ui.dialogs.clear()
                emby_dynamic.execute(
                    17,
                    {'action': 'emby_page', 'source': source.id, 'revision': rev, 'parent': 'search', 'term': 'broad', 'page': '10000'},
                    store,
                    make_item,
                )
                assert ui.endings[-1]['succeeded'] is True
                assert len(ui.rows) == 21
                tail_url, tail_item, tail_folder = ui.rows[-1]
                tail_params = dict(parse_qsl(urlsplit(tail_url).query))
                assert tail_folder is False
                assert tail_params['action'] == 'emby_limit_notice'
                assert 'page' not in tail_params
                assert tail_item.properties.get('Bobbi.LimitNotice') == 'true'
                assert 'Bobbi.NextPage' not in tail_item.properties
                assert ('200,000' in tail_item.label)

                before_http = sum(http_calls.values())
                endings_before = len(ui.endings)
                emby_dynamic.execute(-1, tail_params, store, make_item)
                assert sum(http_calls.values()) == before_http
                assert len(ui.endings) == endings_before
                assert len(ui.dialogs) == 1 and '200,000' in ui.dialogs[0][1]

            # 2. Deep-page jump on 30,000-movie folder (1,500 pages)
            monkeypatch.setattr(emby_dynamic, 'is_english', lambda: False)
            ui.rows.clear()
            ui.builtins.clear()
            emby_dynamic.execute(
                17,
                {'action': 'emby_page', 'source': source.id, 'revision': rev, 'parent': 'folder:movies', 'page': '1'},
                store,
                make_item,
            )
            assert len(ui.rows) == 21
            next_url, next_item, _ = ui.rows[-1]
            assert next_item.label == '下一页'
            assert next_item.label2 == '第 1 / 1500 页'
            assert len(next_item.context) == 1 and '1-1500' in next_item.context[0][0]
            jump_cmd = next_item.context[0][1]
            assert jump_cmd.startswith('RunPlugin(') and jump_cmd.endswith(')')
            jump_params = dict(parse_qsl(urlsplit(jump_cmd[len('RunPlugin('):-1]).query))
            emby_dynamic.execute(-1, jump_params, store, make_item)
            assert len(ui.builtins) == 1 and 'page=750' in ui.builtins[0]
    finally:
        srv.shutdown()
        srv.server_close()
        th.join(2)


def test_cap02_plex_hierarchical_tv_reaches_350k_episodes_with_zero_retained_scan_state():
    """CAP-02: Plex TV sections traverse Show -> Season -> Episode cleanly up to 350,000 episodes."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            u = urlsplit(self.path)
            q = parse_qs(u.query)
            if u.path == '/identity':
                obj = {'MediaContainer': {'machineIdentifier': 'pms1'}}
            elif u.path == '/library/sections':
                obj = {'MediaContainer': {'Directory': [
                    {'key': '1', 'type': 'movie', 'title': 'Movies'},
                    {'key': '2', 'type': 'show', 'title': 'TV Shows'},
                ]}}
            elif u.path == '/library/sections/2/all':
                start = int(q['X-Plex-Container-Start'][0])
                size = int(q['X-Plex-Container-Size'][0])
                ptype = q['type'][0]
                if ptype == '2':
                    total = 3500
                    rows = [{'ratingKey': f'sh{i + 1}', 'title': f'Show {i + 1:04d}'}
                            for i in range(start, min(start + size, total))]
                elif ptype == '3':
                    show_num = int(q['parent'][0][2:])
                    total = 1
                    rows = [{'ratingKey': f'se{show_num}', 'title': 'Season 1'}][start:start + size]
                elif ptype == '4':
                    season_num = int(q['parent'][0][2:])
                    total = 100
                    base_ep = (season_num - 1) * 100
                    rows = [{'ratingKey': str(base_ep + i + 1), 'title': f'Episode {base_ep + i + 1:06d}'}
                            for i in range(start, min(start + size, total))]
                else:
                    self.send_error(400)
                    return
                obj = {'MediaContainer': {'librarySectionID': 2, 'offset': start, 'totalSize': total, 'Metadata': rows}}
            else:
                self.send_error(404)
                return
            raw = json.dumps(obj).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    th = Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    th.start()
    try:
        base = f'http://127.0.0.1:{srv.server_port}'
        plex = PlexClient({'provider': 'plex', 'location': base, 'token': 'tok', 'user_token': 'utok', 'server_id': 'pms1'})
        plex.session.operation = SimpleNamespace(
            kind='scan',
            consume_request=lambda: None,
            check=lambda: None,
            deadline=time.monotonic() + 30.0,
            clock=time.monotonic,
        )

        shows = plex.list_files('section:2:show', 350, 10)
        assert shows['items'][-1]['file_id'] == 'show:2:sh3500' and not shows['has_more']
        seasons = plex.list_files('show:2:sh3500', 1, 10)
        assert seasons['items'][0]['file_id'] == 'season:2:se3500' and not seasons['has_more']
        for page in range(1, 11):
            eps = plex.list_files('season:2:se3500', page, 10)
        assert eps['items'][-1]['file_id'] == 'item:350000' and not eps['has_more']
        # Completed scan directories pop their progress entry (zero unbounded retained state)
        assert plex.session.operation._server_pages == {}
    finally:
        srv.shutdown()
        srv.server_close()
        th.join(2)


def test_home_rail_dead_source_cooldown_and_verified_primary_tag_lease(tmp_path, monkeypatch):
    """Smart Ideas #1 & #2: dead Emby sources cool down for sibling Home rails; verified poster tags halve HTTP calls."""
    emby_dynamic.reset_home_cooldowns()
    emby_artwork.clear_verified_primary_tags()
    art_calls = []

    class LiveServer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            art_calls.append(self.path)
            if self.path == '/System/Info/Public':
                body, ctype = json.dumps({'Id': 's_live'}).encode(), 'application/json'
            elif self.path == '/Users/u_live':
                body, ctype = json.dumps({'Id': 'u_live'}).encode(), 'application/json'
            elif self.path.startswith('/Users/u_live/Items'):
                if '/Items/m1' in self.path:
                    body = json.dumps({'Id': 'm1', 'ImageTags': {'Primary': 'ptag1'}}).encode()
                else:
                    body = json.dumps({
                        'Items': [{'Id': 'm1', 'Name': 'Live Film', 'Type': 'Movie', 'IsFolder': False, 'ImageTags': {'Primary': 'ptag1'}}],
                        'TotalRecordCount': 1,
                    }).encode()
                ctype = 'application/json'
            elif self.path.startswith('/Items/m1/Images/Primary?'):
                body, ctype = PNG, 'image/png'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(('127.0.0.1', 0), LiveServer)
    th = Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    th.start()

    # Reserve an unbound closed port for dead source
    import socket
    with socket.socket() as dead_sock:
        dead_sock.bind(('127.0.0.1', 0))
        dead_port = dead_sock.getsockname()[1]

    images = ImageService(tmp_path, private_art=emby_artwork.reader(tmp_path, lambda: True))
    images.start()
    try:
        store = Registry(tmp_path / 'libraries.sqlite3')
        dead_src = Source(
            '1' * 32, 'Offline VPS', 'media_server', f'http://127.0.0.1:{dead_port}', password='tok-dead',
            metadata={'schema': 1, 'provider': 'emby', 'server_id': 's_dead', 'user_id': 'u_dead'},
        )
        live_src = Source(
            '2' * 32, 'Local Emby', 'media_server', f'http://127.0.0.1:{srv.server_port}', password='tok-live',
            metadata={'schema': 1, 'provider': 'emby', 'server_id': 's_live', 'user_id': 'u_live'},
        )
        store.save(dead_src)
        store.save(live_src, activate_emby=store.emby_binding()[1])
        store.emby_art_key()
        store.close()

        rail_rows = []
        modules = {
            'xbmc': SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: False)),
            'xbmcgui': SimpleNamespace(ListItem=_FakeListItem),
            'xbmcvfs': SimpleNamespace(translatePath=lambda *a: str(tmp_path)),
            'xbmcplugin': SimpleNamespace(
                setContent=lambda *a: None,
                addDirectoryItems=lambda h, r, n: rail_rows.extend(r),
                endOfDirectory=lambda *a, **k: None,
            ),
        }
        for k, v in modules.items():
            monkeypatch.setitem(sys.modules, k, v)
        monkeypatch.setattr(emby_dynamic, 'ProfileBinding', lambda: SimpleNamespace(root=lambda: tmp_path, is_current=lambda: True))
        monkeypatch.setattr(emby_dynamic, 'is_english', lambda: False)

        # First rail (resume): dead_src fails & enters cooldown; live_src still renders!
        emby_dynamic.execute_home_rail(11, {'section': 'resume'})
        assert len(rail_rows) == 1 and rail_rows[0][1].label == 'Live Film'
        dead_rev = Registry(tmp_path / 'libraries.sqlite3').source_snapshot(dead_src.id)[1]
        assert emby_dynamic._home_source_cooling_down(dead_src.id, dead_rev, dead_src.location) is True

        # Second rail (recent): dead_src is skipped immediately via cooldown; poster URL skips redundant /Items/m1 GET!
        rail_rows.clear()
        t0 = time.monotonic()
        emby_dynamic.execute_home_rail(12, {'section': 'recent'})
        elapsed = time.monotonic() - t0
        assert elapsed < 1.5
        assert len(rail_rows) == 1
        poster_url = rail_rows[0][1].art['poster']
        before_art = len(art_calls)
        with urlopen(poster_url, timeout=4) as reply:
            assert reply.read() == PNG
        # Only 1 HTTP GET (/Items/m1/Images/Primary), NOT 2 (/Users/u_live/Items/m1 skipped by verified lease)!
        assert len(art_calls) - before_art == 1
        assert art_calls[-1].startswith('/Items/m1/Images/Primary?')
    finally:
        images.close()
        srv.shutdown()
        srv.server_close()
        th.join(2)
        emby_dynamic.reset_home_cooldowns()
        emby_artwork.clear_verified_primary_tags()


def test_yatse_fuse3_notification_guard_timers_expression_o1_nav_and_log_filter():
    """Verify Yatse reconnect toast guard, Timers.xml syntax fix, O(1) nav prefix expressions, and log filter."""
    # 1. DialogNotification.xml suppresses EventServer $LOCALIZE[790] & Yatse toasts and avoids HUD overlap
    notif_tree = ET.parse(ROOT / 'addons/skin.bobbi.cinema/1080p/DialogNotification.xml').getroot()
    vis = notif_tree.findtext(".//control[@type='group']/visible") or ''
    assert '!String.IsEqual(Control.GetLabel(401),$LOCALIZE[790])' in vis
    assert '!String.IsEqual(Control.GetLabel(401),Yatse)' in vis
    assert '!Window.IsActive(DialogVolumeBar.xml)' in vis
    assert '!Window.IsActive(DialogExtendedProgressBar.xml)' in vis

    # 2. Timers.xml has no [$EXP[BobbiHostHasVS10]] bracket parser error
    timers_raw = (ROOT / 'addons/skin.bobbi.cinema/1080p/Timers.xml').read_text(encoding='utf-8')
    assert '[$EXP[BobbiHostHasVS10]]' not in timers_raw
    assert '+ $EXP[BobbiHostHasVS10]</start>' in timers_raw

    # 3. Includes_HomeNav.generated.xml uses O(1) BobbiSpaceSeen_* prefix expressions (<= 3 atoms per slot!)
    nav_tree = ET.parse(ROOT / 'addons/skin.bobbi.cinema/1080p/Includes_HomeNav.generated.xml').getroot()
    exprs = {e.get('name'): (e.text or '') for e in nav_tree.findall('expression')}
    assert 'BobbiSpaceSeen_11_settings' in exprs
    assert exprs['BobbiSpaceSlot_12_settings'].count('$EXP[') == 3

    # 4. portable_runtime routes high-frequency chunk yields to LOGDEBUG while keeping lifecycle/errors at LOGINFO
    from lib import portable_runtime
    assert portable_runtime._is_noisy_chunk_observation('READ_YIELDED bytes=524288 remaining=1048576') is True
    assert portable_runtime._is_noisy_chunk_observation('{"event":"share_read","phase":"yield","bytes":1024}') is True
    assert portable_runtime._is_noisy_chunk_observation('{"event":"share_read","phase":"fetch_end","len":1024}') is True
    assert portable_runtime._is_noisy_chunk_observation('{"event":"share_read","phase":"begin"}') is False
    assert portable_runtime._is_noisy_chunk_observation('{"event":"share_read","phase":"end","outcome":"complete"}') is False
    assert portable_runtime._is_noisy_chunk_observation('{"event":"share_read","phase":"retry"}') is False
    assert portable_runtime._is_noisy_chunk_observation('{"event":"share_read","outcome":"failed"}') is False
    assert portable_runtime._is_noisy_chunk_observation('READ_WINDOW bytes=67108864 wall_ms=20000') is False
    assert portable_runtime._is_noisy_chunk_observation('STREAM_UNAVAILABLE') is False

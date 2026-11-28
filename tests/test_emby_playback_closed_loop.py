"""Comprehensive closed-loop regression suite for Emby playback, sync, multi-account isolation, and UI.

Covers R08-01..07, R09-01..06, R10-01..06, R15-01..05, and REV-09.
"""
from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import struct
from threading import Event, Lock, Thread
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, parse_qsl, urlsplit

import pytest

from bobbi_core.library_contract import Source
from bobbi_platform.emby_session import (
    EmbyInvalidationHub,
    EmbySessionReporter,
    TICKS_PER_SECOND,
    resolve_next_episode_data,
)
from bobbi_platform.host import Host
from bobbi_platform.libraries import Registry
from bobbi_platform.owned_playback import emby_source_scope
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.standard_session import StandardSession
from test_catalog_navigation import selected_actions
from test_library_plugin import plugin


def _ws_accept_key(sec_key: str) -> str:
    guid = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    digest = hashlib.sha1((sec_key + guid).encode('ascii')).digest()
    return base64.b64encode(digest).decode('ascii')


def _ws_text_frame(text: str) -> bytes:
    raw = text.encode('utf-8')
    assert len(raw) < 126
    return bytes([0x81, len(raw)]) + raw


class DualUserEmbyFixture:
    """Loopback HTTP + RFC 6455 WebSocket Emby server supporting multiple isolated users."""

    def __init__(self):
        self.lock = Lock()
        self.calls: list[tuple[str, str, str, object]] = []
        self.ws_enabled = True
        self.ws_sockets: list[socket.socket] = []
        self.drop_next_stop_reply = False
        self.fail_stop_network = False
        self.auth_revoked_tokens: set[str] = set()
        self.auto_mark_played_on_eof = True

        self.users = {
            'token-a': {'user_id': 'ua', 'server_id': 'srv1'},
            'token-b': {'user_id': 'ub', 'server_id': 'srv1'},
        }
        # Independent per-user state for identical ItemId='1001' + season episodes
        self.items = {}
        for uid in ('ua', 'ub'):
            self.items[(uid, '1001')] = {
                'Id': '1001',
                'Name': f'Shared Movie ({uid})',
                'Type': 'Movie',
                'IsFolder': False,
                'RunTimeTicks': 3600 * TICKS_PER_SECOND,
                'Overview': 'Movie plot',
                'MediaSources': [
                    {'Id': 'v4k', 'Name': '4K DV', 'Protocol': 'File', 'Path': '/m/1001-4k.mkv', 'SupportsDirectPlay': True, 'Size': 8},
                    {'Id': 'v1080', 'Name': '1080p', 'Protocol': 'File', 'Path': '/m/1001-1080.mkv', 'SupportsDirectPlay': True, 'Size': 8},
                ],
                'UserData': {
                    'Played': False,
                    'PlaybackPositionTicks': 900 * TICKS_PER_SECOND if uid == 'ua' else 0,
                    'IsFavorite': False,
                },
            }
            self.items[(uid, 'ep3')] = {
                'Id': 'ep3',
                'Name': 'Episode 3',
                'Type': 'Episode',
                'IsFolder': False,
                'SeriesName': 'Severance',
                'SeasonId': 'season2',
                'ParentIndexNumber': 2,
                'IndexNumber': 3,
                'RunTimeTicks': 1200 * TICKS_PER_SECOND,
                'Overview': 'Ep3 plot',
                'MediaSources': [
                    {'Id': 'ms3', 'Name': 'WebDL', 'Protocol': 'File', 'Path': '/tv/s02e03.mkv', 'SupportsDirectPlay': True, 'Size': 8},
                ],
                'UserData': {'Played': False, 'PlaybackPositionTicks': 0, 'IsFavorite': False},
            }
            self.items[(uid, 'ep4')] = {
                'Id': 'ep4',
                'Name': 'Episode 4',
                'Type': 'Episode',
                'IsFolder': False,
                'SeriesName': 'Severance',
                'SeasonId': 'season2',
                'ParentIndexNumber': 2,
                'IndexNumber': 4,
                'RunTimeTicks': 1200 * TICKS_PER_SECOND,
                'Overview': 'Ep4 plot',
                'MediaSources': [
                    {'Id': 'ms4', 'Name': 'WebDL', 'Protocol': 'File', 'Path': '/tv/s02e04.mkv', 'SupportsDirectPlay': True, 'Size': 8},
                ],
                'UserData': {'Played': False, 'PlaybackPositionTicks': 0, 'IsFavorite': False},
            }

        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def _handle(self):
                parsed = urlsplit(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)
                token = self.headers.get('X-Emby-Token', '')
                clen = int(self.headers.get('Content-Length') or '0')
                body_raw = self.rfile.read(clen) if clen > 0 else b''
                body_json = json.loads(body_raw.decode('utf-8')) if body_raw else None

                with fixture.lock:
                    fixture.calls.append((self.command, path, token, body_json))

                if path == '/embywebsocket':
                    if token in fixture.auth_revoked_tokens or token not in fixture.users:
                        self.send_response(401)
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    if not fixture.ws_enabled:
                        self.send_response(404)
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    sec_key = self.headers.get('Sec-WebSocket-Key', '')
                    self.send_response(101, 'Switching Protocols')
                    self.send_header('Upgrade', 'websocket')
                    self.send_header('Connection', 'Upgrade')
                    self.send_header('Sec-WebSocket-Accept', _ws_accept_key(sec_key))
                    self.end_headers()
                    self.wfile.flush()
                    with fixture.lock:
                        fixture.ws_sockets.append(self.connection)
                    while fixture.ws_enabled and not fixture._closed.is_set():
                        time.sleep(0.05)
                    return

                if path.startswith('/Videos/'):
                    self.send_response(206)
                    self.send_header('Content-Type', 'video/x-matroska')
                    self.send_header('Content-Range', 'bytes 0-0/8')
                    self.send_header('Content-Length', '1')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(b'x')
                    return

                if token in fixture.auth_revoked_tokens or token not in fixture.users:
                    self.send_response(401)
                    self.send_header('Content-Length', '2')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(b'{}')
                    return

                user = fixture.users[token]
                uid = user['user_id']

                if path == '/System/Info/Public':
                    self._json({'Id': user['server_id']})
                    return
                if path == f'/Users/{uid}':
                    self._json({'Id': uid})
                    return
                if path == f'/Users/{uid}/Items/Resume':
                    rows = [
                        v for (u, _), v in fixture.items.items()
                        if u == uid and v['UserData']['PlaybackPositionTicks'] > 0 and not v['UserData']['Played']
                    ]
                    self._json({'Items': rows, 'TotalRecordCount': len(rows)})
                    return
                if path == f'/Users/{uid}/Items':
                    parent = query.get('ParentId', [''])[0]
                    if parent == 'season2':
                        rows = [fixture.items[(uid, 'ep3')], fixture.items[(uid, 'ep4')]]
                    else:
                        rows = [fixture.items[(uid, '1001')], fixture.items[(uid, 'ep3')]]
                    limit = int(query.get('Limit', ['20'])[0])
                    start = int(query.get('StartIndex', ['0'])[0])
                    sliced = rows[start:start + limit]
                    self._json({'Items': sliced, 'TotalRecordCount': len(rows)})
                    return
                if path.startswith(f'/Users/{uid}/Items/'):
                    iid = path.rsplit('/', 1)[-1]
                    item = fixture.items.get((uid, iid))
                    if not item:
                        self.send_error(404)
                        return
                    self._json(item)
                    return
                if path.startswith('/Items/') and path.endswith('/PlaybackInfo'):
                    iid = path.split('/')[2]
                    item = fixture.items.get((uid, iid))
                    mid = body_json['MediaSourceId']
                    matched = [m for m in item['MediaSources'] if m['Id'] == mid]
                    self._json({
                        'MediaSources': matched,
                        'PlaySessionId': f'ps-{uid}-{iid}-{mid}',
                    })
                    return
                if path.startswith(f'/Users/{uid}/PlayedItems/'):
                    iid = path.rsplit('/', 1)[-1]
                    item = fixture.items[(uid, iid)]
                    if self.command == 'POST':
                        item['UserData']['Played'] = True
                        item['UserData']['PlaybackPositionTicks'] = 0
                    elif self.command == 'DELETE':
                        item['UserData']['Played'] = False
                        item['UserData']['PlaybackPositionTicks'] = 0
                    self._empty(204)
                    return
                if path.startswith(f'/Users/{uid}/FavoriteItems/'):
                    iid = path.rsplit('/', 1)[-1]
                    item = fixture.items[(uid, iid)]
                    item['UserData']['IsFavorite'] = (self.command == 'POST')
                    self._empty(204)
                    return
                if path in ('/Sessions/Playing', '/Sessions/Playing/Progress', '/Sessions/Playing/Stopped'):
                    iid = body_json['ItemId']
                    ticks = int(body_json.get('PositionTicks') or 0)
                    item = fixture.items[(uid, iid)]
                    if path == '/Sessions/Playing/Stopped':
                        if fixture.fail_stop_network:
                            self.connection.close()
                            return
                        dur = item['RunTimeTicks']
                        if fixture.auto_mark_played_on_eof and dur > 0 and ticks >= int(dur * 0.95):
                            item['UserData']['Played'] = True
                            item['UserData']['PlaybackPositionTicks'] = 0
                        else:
                            item['UserData']['PlaybackPositionTicks'] = ticks
                        if fixture.drop_next_stop_reply:
                            fixture.drop_next_stop_reply = False
                            self.connection.close()
                            return
                    else:
                        item['UserData']['PlaybackPositionTicks'] = ticks
                    self._empty(204)
                    return
                self.send_error(404)

            def _json(self, obj):
                raw = json.dumps(obj).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(raw)

            def _empty(self, code=204):
                self.send_response(code)
                self.send_header('Content-Length', '0')
                self.send_header('Connection', 'close')
                self.end_headers()

            do_GET = do_POST = do_DELETE = _handle

        self._closed = Event()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def push_ws_json(self, payload: dict) -> None:
        frame = _ws_text_frame(json.dumps(payload))
        with self.lock:
            socks = list(self.ws_sockets)
        for s in socks:
            try:
                s.sendall(frame)
            except OSError:
                pass

    def close(self):
        self._closed.set()
        self.ws_enabled = False
        with self.lock:
            socks = list(self.ws_sockets)
            self.ws_sockets.clear()
        for s in socks:
            try:
                s.close()
            except OSError:
                pass
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2.0)


@pytest.fixture
def emby_env(plugin, tmp_path, monkeypatch):
    srv = DualUserEmbyFixture()
    store = Registry(plugin.path)
    src_a = Source(
        'a' * 32,
        'Emby User A',
        'media_server',
        srv.base,
        password='token-a',
        metadata={'schema': 1, 'provider': 'emby', 'server_id': 'srv1', 'user_id': 'ua'},
    )
    src_b = Source(
        'b' * 32,
        'Emby User B',
        'media_server',
        srv.base,
        password='token-b',
        metadata={'schema': 1, 'provider': 'emby', 'server_id': 'srv1', 'user_id': 'ub'},
    )
    store.save(src_a)
    store.save(src_b, activate_emby=store.emby_binding()[1])
    rev_a = store.source_snapshot(src_a.id)[1]
    rev_b = store.source_snapshot(src_b.id)[1]
    store.close()

    picks = []
    dialogs = []
    dialog = SimpleNamespace(
        select=lambda title, opts: picks.pop(0) if picks else 0,
        input=lambda *a: 'Severance',
        ok=lambda *a: dialogs.append(a),
        yesno=lambda *a: True,
    )
    monkeypatch.setattr(plugin.module.xbmcgui, 'Dialog', lambda: dialog)

    host = Host(tmp_path)
    host.start()
    try:
        yield SimpleNamespace(
            srv=srv,
            host=host,
            src_a=src_a,
            rev_a=rev_a,
            src_b=src_b,
            rev_b=rev_b,
            picks=picks,
            dialogs=dialogs,
            tmp_path=tmp_path,
        )
    finally:
        host.close()
        srv.close()


def test_resume_900s_vs_start_over_and_failed_seek_reports_actual_clock(plugin, emby_env):
    """R08, R09-01, R09-02, REV-09 #6: 900s resume vs start-over, version binding, actual player clock."""
    srv = emby_env.srv
    host = emby_env.host

    # 1. Pick version 1 ('v1080') and pick 0 ('继续观看 (15:00)') -> StartOffset='900.0'
    emby_env.picks[:] = [1, 0]
    plugin.module.execute(17, {
        'action': 'emby_play',
        'source': emby_env.src_a.id,
        'revision': emby_env.rev_a,
        'id': '1001',
    })
    assert plugin.resolved[-1][:2] == (17, True)
    li = plugin.resolved[-1][2]
    assert li.properties['StartOffset'] == '900.0'
    req_id = li.properties['bobbi.standard.request']

    # Verify PlaybackInfo opened session with IsPlayback=True and NO /Sessions/Playing sent on handoff!
    pb_calls = [c for c in srv.calls if c[1] == '/Items/1001/PlaybackInfo']
    assert len(pb_calls) == 1 and pb_calls[0][3]['IsPlayback'] is True
    assert not any(c[1].startswith('/Sessions/') for c in srv.calls)

    # Simulate player failing to seek to 900s and actually starting at 0.5s!
    _, reporter = host._emby_runtime()
    tracked_data = host.owned_tracks[req_id]['data']
    assert tracked_data['_owned_source']['play_session_id'] == 'ps-ua-1001-v1080'

    host.notify_playback_event({
        'event': 'AV_START',
        'request_id': req_id,
        'position': 0.5,
        'duration': 3600.0,
        'paused': False,
        'observed_clock': True,
        'data': tracked_data,
    })
    # Pause for 30s, Unpause, seek to 1200s, then backward seek to 300s, then Stop
    host.notify_playback_event({
        'event': 'PROGRESS',
        'request_id': req_id,
        'position': 0.5,
        'duration': 3600.0,
        'paused': True,
        'trigger': 'Pause',
        'observed_clock': True,
        'data': tracked_data,
    })
    host.notify_playback_event({
        'event': 'PROGRESS',
        'request_id': req_id,
        'position': 1200.0,
        'duration': 3600.0,
        'paused': False,
        'trigger': 'TimeUpdate',
        'observed_clock': True,
        'data': tracked_data,
    })
    host.notify_playback_event({
        'event': 'PROGRESS',
        'request_id': req_id,
        'position': 300.0,
        'duration': 3600.0,
        'paused': False,
        'trigger': 'TimeUpdate',
        'observed_clock': True,
        'data': tracked_data,
    })
    host.notify_playback_event({
        'event': 'TERMINAL',
        'request_id': req_id,
        'position': 300.0,
        'duration': 3600.0,
        'paused': False,
        'reason': 'STOP',
        'observed_clock': True,
        'data': tracked_data,
    })
    # Late progress after TERMINAL must be strictly sealed out!
    accepted_after_seal = reporter.on_playback_event({
        'event': 'PROGRESS',
        'request_id': req_id,
        'position': 999.0,
        'duration': 3600.0,
        'paused': False,
        'trigger': 'TimeUpdate',
        'observed_clock': True,
        'data': tracked_data,
    })
    assert accepted_after_seal is False

    # Wait briefly for async worker to flush
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if any(c[1] == '/Sessions/Playing/Stopped' for c in srv.calls):
            break
        time.sleep(0.02)
    reporter.drain_once()

    sess_calls = [(c[1], c[3]) for c in srv.calls if c[1].startswith('/Sessions/')]
    assert sess_calls[0][0] == '/Sessions/Playing'
    # Actual clock 0.5s (5,000,000 ticks), NEVER StartOffset 900s!
    assert sess_calls[0][1]['PositionTicks'] == int(0.5 * TICKS_PER_SECOND)
    assert sess_calls[0][1]['PlaySessionId'] == 'ps-ua-1001-v1080'
    assert sess_calls[-1][0] == '/Sessions/Playing/Stopped'
    assert sess_calls[-1][1]['PositionTicks'] == 300 * TICKS_PER_SECOND
    assert srv.items[('ua', '1001')]['UserData']['PlaybackPositionTicks'] == 300 * TICKS_PER_SECOND

    # 2. Explicit start_over ('从头播放') sets StartOffset='0' without resume prompt
    emby_env.picks[:] = [0]
    plugin.module.execute(17, {
        'action': 'emby_play',
        'source': emby_env.src_a.id,
        'revision': emby_env.rev_a,
        'id': '1001',
        'resume_mode': 'start_over',
    })
    assert plugin.resolved[-1][2].properties['StartOffset'] == '0'


def test_cancel_before_av_start_never_reports_playing_or_stopped(emby_env, tmp_path):
    """R09-01: Pre-AV cancel/switch never sends /Sessions/Playing or /Sessions/Playing/Stopped."""
    hub = EmbyInvalidationHub(tmp_path)
    reporter = EmbySessionReporter(tmp_path, hub, start_worker=False)
    try:
        accepted = reporter.on_playback_event({
            'event': 'TERMINAL',
            'request_id': 'c' * 32,
            'position': 0.0,
            'duration': 0.0,
            'reason': 'CANCELLED',
            'observed_clock': False,
            'data': {
                '_owned_source': {
                    'provider': 'emby',
                    'server_id': 'srv1',
                    'user_id': 'ua',
                    'source_id': emby_env.src_a.id,
                    'source_generation': emby_env.rev_a,
                    'item_id': '1001',
                    'media_source_id': 'v4k',
                    'play_session_id': 'ps-never',
                }
            },
        })
        assert accepted is False
        reporter.drain_once()
        assert not any(c[1].startswith('/Sessions/') for c in emby_env.srv.calls)
    finally:
        reporter.close()
        hub.close()


def test_lost_stop_ack_checks_server_userdata_without_reposting_and_offline_conflict_discards(
    plugin, emby_env
):
    """R09-03, R09-05, REV-09 #4 & #10: Lost ACK avoids duplicate Stopped; external unplayed wins over offline Stop."""
    srv = emby_env.srv
    hub = EmbyInvalidationHub(emby_env.tmp_path)
    reporter = EmbySessionReporter(emby_env.tmp_path, hub, start_worker=False)
    meta = {
        'provider': 'emby',
        'server_id': 'srv1',
        'user_id': 'ua',
        'source_id': emby_env.src_a.id,
        'source_generation': emby_env.rev_a,
        'item_id': '1001',
        'media_source_id': 'v4k',
        'play_session_id': 'ps-lost-ack',
        'initial_ticks': str(900 * TICKS_PER_SECOND),
        'initial_played': '0',
    }
    try:
        # Case 1: Server applies Stopped (450s) and drops HTTP reply (lost ACK)
        req1 = '1' * 32
        srv.drop_next_stop_reply = True
        reporter.on_playback_event({
            'event': 'AV_START', 'request_id': req1, 'position': 400.0, 'duration': 3600.0,
            'paused': False, 'observed_clock': True, 'data': {'_owned_source': meta},
        })
        reporter.on_playback_event({
            'event': 'TERMINAL', 'request_id': req1, 'position': 450.0, 'duration': 3600.0,
            'paused': False, 'reason': 'STOP', 'observed_clock': True, 'data': {'_owned_source': meta},
        })
        reporter.drain_once(flush_pending=False)
        stop_posts_before = sum(1 for c in srv.calls if c[1] == '/Sessions/Playing/Stopped')
        assert stop_posts_before == 1
        assert req1 in reporter._pending_stops

        # Next flush reads server UserData (already 450s!) and resolves without a second POST!
        reporter._flush_pending_stops()
        stop_posts_after = sum(1 for c in srv.calls if c[1] == '/Sessions/Playing/Stopped')
        assert stop_posts_after == 1
        assert req1 not in reporter._pending_stops

        # Case 2: Network fails BEFORE Stopped reaches server; external client marks item Unplayed (0 ticks)
        req2 = '2' * 32
        srv.fail_stop_network = True
        reporter.on_playback_event({
            'event': 'AV_START', 'request_id': req2, 'position': 450.0, 'duration': 3600.0,
            'paused': False, 'observed_clock': True, 'data': {'_owned_source': meta},
        })
        reporter.on_playback_event({
            'event': 'TERMINAL', 'request_id': req2, 'position': 600.0, 'duration': 3600.0,
            'paused': False, 'reason': 'STOP', 'observed_clock': True, 'data': {'_owned_source': meta},
        })
        reporter.drain_once(flush_pending=False)
        assert req2 in reporter._pending_stops

        # External client manually resets to Unplayed while Bobbi TV is offline
        srv.items[('ua', '1001')]['UserData']['Played'] = False
        srv.items[('ua', '1001')]['UserData']['PlaybackPositionTicks'] = 0
        srv.fail_stop_network = False

        # Reconnect flush must read server UserData first and DISCARD stale offline 600s Stop!
        reporter._flush_pending_stops()
        assert req2 not in reporter._pending_stops
        assert srv.items[('ua', '1001')]['UserData']['PlaybackPositionTicks'] == 0
    finally:
        reporter.close()
        hub.close()


def test_http_401_marks_auth_required_and_halts_scope(emby_env):
    """R09-05, R10-05: Token revocation (401) marks AUTH_REQUIRED and halts background retries."""
    srv = emby_env.srv
    hub = EmbyInvalidationHub(emby_env.tmp_path)
    reporter = EmbySessionReporter(emby_env.tmp_path, hub, start_worker=False)
    meta = {
        'provider': 'emby',
        'server_id': 'srv1',
        'user_id': 'ua',
        'source_id': emby_env.src_a.id,
        'source_generation': emby_env.rev_a,
        'item_id': '1001',
        'media_source_id': 'v4k',
        'play_session_id': 'ps-401',
    }
    try:
        srv.auth_revoked_tokens.add('token-a')
        req = '4' * 32
        reporter.on_playback_event({
            'event': 'AV_START', 'request_id': req, 'position': 10.0, 'duration': 3600.0,
            'paused': False, 'observed_clock': True, 'data': {'_owned_source': meta},
        })
        reporter.drain_once()
        assert hub.auth_state(emby_env.src_a.id, emby_env.rev_a) == 'AUTH_REQUIRED'
        calls_count = len(srv.calls)
        # Subsequent events on the revoked scope are immediately rejected without network spam
        assert reporter.on_playback_event({
            'event': 'PROGRESS', 'request_id': req, 'position': 20.0, 'duration': 3600.0,
            'paused': False, 'observed_clock': True, 'data': {'_owned_source': meta},
        }) is False
        reporter.drain_once()
        assert len(srv.calls) == calls_count
    finally:
        srv.auth_revoked_tokens.discard('token-a')
        reporter.close()
        hub.close()


def test_multi_account_same_itemid_isolation_and_manual_mark(plugin, emby_env):
    """R10-03, R10-06, REV-09 #2: Account A and Account B share ItemId=1001 without cross-contamination."""
    srv = emby_env.srv

    # Browse Account A and Account B without switching global emby_binding or invalidating each other
    plugin.rows.clear()
    plugin.module.execute(17, {
        'action': 'emby_page', 'source': emby_env.src_a.id, 'revision': emby_env.rev_a, 'parent': 'folder:movies'
    })
    row_a = next(r for _, r, _ in plugin.rows if '1001' in r.label or 'Shared Movie' in r.label)
    # The server clock belongs to the entry, not either of its two cuts.
    assert 'ResumeTime' not in row_a.properties and '15:00' in row_a.properties['Bobbi.Library.Location']

    plugin.rows.clear()
    plugin.module.execute(17, {
        'action': 'emby_page', 'source': emby_env.src_b.id, 'revision': emby_env.rev_b, 'parent': 'folder:movies'
    })
    row_b = next(r for _, r, _ in plugin.rows if 'Shared Movie' in r.label)
    assert 'ResumeTime' not in row_b.properties

    # Mark Played + Favorite on Account B's ItemId=1001
    plugin.calls.clear()
    plugin.module.execute(-1, {
        'action': 'emby_mark', 'source': emby_env.src_b.id, 'revision': emby_env.rev_b, 'id': '1001', 'op': 'played'
    })
    plugin.module.execute(-1, {
        'action': 'emby_mark', 'source': emby_env.src_b.id, 'revision': emby_env.rev_b, 'id': '1001', 'op': 'favorite'
    })
    assert ('builtin', 'Container.Refresh') in plugin.calls
    assert srv.items[('ub', '1001')]['UserData']['Played'] is True
    assert srv.items[('ub', '1001')]['UserData']['IsFavorite'] is True
    # Account A's ItemId=1001 is completely untouched!
    assert srv.items[('ua', '1001')]['UserData']['Played'] is False
    assert srv.items[('ua', '1001')]['UserData']['PlaybackPositionTicks'] == 900 * TICKS_PER_SECOND
    assert srv.items[('ua', '1001')]['UserData']['IsFavorite'] is False


def test_websocket_5s_invalidation_and_30s_poll_fallback(emby_env):
    """R10-01, R10-02, R10-04: WS UserDataChanged triggers dirty revision <<5s; without WS, 25s poll detects delta."""
    srv = emby_env.srv
    clock_val = [100.0]
    hub = EmbyInvalidationHub(emby_env.tmp_path, clock=lambda: clock_val[0])
    try:
        hub.ensure_ws_listener(emby_env.src_a.id, emby_env.rev_a)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if hub.snapshot(emby_env.src_a.id, emby_env.rev_a)['ws_connected']:
                break
            time.sleep(0.02)
        snap0 = hub.mark_confirmed(emby_env.src_a.id, emby_env.rev_a)
        assert snap0['ws_connected'] is True
        assert snap0['refresh_target_seconds'] <= 5.0

        # Foreign user WS frame is ignored
        srv.push_ws_json({
            'MessageType': 'UserDataChanged',
            'Data': {'UserId': 'ub', 'UserDataList': [{'ItemId': '1001'}]},
        })
        time.sleep(0.1)
        assert hub.snapshot(emby_env.src_a.id, emby_env.rev_a)['revision'] == snap0['revision']

        # Matching user WS frame marks dirty in well under 5s!
        t0 = time.monotonic()
        srv.push_ws_json({
            'MessageType': 'UserDataChanged',
            'Data': {'UserId': 'ua', 'UserDataList': [{'ItemId': '1001', 'Played': True}]},
        })
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            snap1 = hub.snapshot(emby_env.src_a.id, emby_env.rev_a)
            if snap1['revision'] > snap0['revision']:
                break
            time.sleep(0.02)
        assert snap1['revision'] > snap0['revision']
        assert snap1['sync_state'] == 'dirty'
        assert (time.monotonic() - t0) < 2.0

        # Fallback poll without WS (<=30s budget)
        hub_no_ws = EmbyInvalidationHub(emby_env.tmp_path, clock=lambda: clock_val[0])
        try:
            s_init = hub_no_ws.poll_server_digest(emby_env.src_b.id, emby_env.rev_b)
            assert s_init['refresh_target_seconds'] <= 30.0
            srv.items[('ub', 'ep3')]['UserData']['Played'] = True
            clock_val[0] += 25.1
            s_next = hub_no_ws.poll_server_digest(emby_env.src_b.id, emby_env.rev_b)
            assert s_next['revision'] > s_init['revision']
            assert s_next['sync_state'] == 'dirty'
        finally:
            hub_no_ws.close()
    finally:
        hub.close()


def test_natural_eof_same_season_next_episode_and_dialog_video_info_routing(plugin, emby_env):
    """R09-04, R15-04, R15-05: NATURAL_EOF marks played + resolves S02E04; DialogVideoInfo routes library folders."""
    srv = emby_env.srv
    srv.auto_mark_played_on_eof = False  # Force readback set_played fallback!

    plugin.module.execute(17, {
        'action': 'emby_play',
        'source': emby_env.src_a.id,
        'revision': emby_env.rev_a,
        'id': 'ep3',
    })
    assert plugin.resolved[-1][:2] == (17, True)
    req_id = plugin.resolved[-1][2].properties['bobbi.standard.request']
    tracked = emby_env.host.owned_tracks[req_id]['data']
    assert tracked['_owned_next'] == {
        'resolver': 'emby_same_season',
        'profile_root': str(emby_env.tmp_path),
        'season_id': 'season2',
        'season': 2,
        'episode': 3,
    }

    # Resolve next episode S02E04 in same season
    nxt = resolve_next_episode_data(tracked, tracked['_owned_next'], lambda: False)
    assert nxt is not None
    assert nxt['title'] == 'Episode 4'
    assert nxt['tv_data'] == {'season': 2, 'episode': 4}
    assert nxt['_owned_source']['item_id'] == 'ep4'

    # End of season (after ep4) returns None instead of guessing another season
    assert resolve_next_episode_data(nxt, nxt['_owned_next'], lambda: False) is None

    # NATURAL_EOF readback verifies Played=True via POST /PlayedItems/ep3 when server didn't auto-mark
    _, reporter = emby_env.host._emby_runtime()
    emby_env.host.notify_playback_event({
        'event': 'AV_START', 'request_id': req_id, 'position': 1195.0, 'duration': 1200.0,
        'paused': False, 'observed_clock': True, 'data': tracked,
    })
    emby_env.host.notify_playback_event({
        'event': 'TERMINAL', 'request_id': req_id, 'position': 1200.0, 'duration': 1200.0,
        'paused': False, 'reason': 'NATURAL_EOF', 'observed_clock': True, 'data': tracked,
    })
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if srv.items[('ua', 'ep3')]['UserData']['Played'] is True:
            break
        time.sleep(0.02)
    reporter.drain_once()
    assert srv.items[('ua', 'ep3')]['UserData']['Played'] is True

    # DialogVideoInfo.xml routing for plugin.video.bobbi.library folders vs playable leaves
    folder_acts = selected_actions('981', videos=True, folder=True, bobbi=False, library=True)
    assert len(folder_acts) == 4 and folder_acts[1] == 'Dialog.Close(movieinformation,true)'
    leaf_acts = selected_actions('981', videos=True, folder=False, bobbi=False, library=True)
    assert leaf_acts == ['SendClick(8)']


def test_owned_playback_native_adapter_handle_uses_resolved_url_route():
    """Real-device regression: native PlaybackAuthority.claim_start requires route=='resolved_url' when handle >= 0."""
    from bobbi_core.playback_authority import PlaybackAuthority
    from bobbi_core.playback_request import Client as PlaybackClient
    from bobbi_platform.owned_playback import library_source_scope, reserve_playback

    class _IdleNative:
        def __init__(self):
            self.epoch = 0

        def state(self):
            return {
                'protocol': 1,
                'selection_epoch': self.epoch,
                'playback': None,
                'gui_generation': 1,
                'gui_user_intent': 1,
                'fullscreen_instance': '',
            }

        def intent(self, body):
            assert body['expected_epoch'] == self.epoch
            self.epoch += 1
            return {'reserved': True, 'selection_epoch': self.epoch}

    authority = PlaybackAuthority(_IdleNative())
    authority.configure_accounts(SimpleNamespace(
        is_current=lambda _s: True,
        run_if_current=lambda _s, fn, authenticated=True: fn(),
    ))
    scope = library_source_scope('a' * 32, 'b' * 64)
    tracked_calls = []

    def fake_host_call(action, body, timeout=3):
        if action == 'status':
            return {'playback_adapter': 'native'}
        if action == 'owned_playback_track':
            tracked_calls.append(body)
            return {'tracked': True}
        raise AssertionError(action)

    transport = (
        SimpleNamespace(is_current=lambda: True, require_current=lambda: None),
        PlaybackClient(lambda msg, timeout=0.3: authority.dispatch(msg)),
        fake_host_call,
    )
    resolved_items = []
    full_url = 'http://127.0.0.1:38000/stream/' + 'c' * 32 + '/video.mkv|redirect-limit=0&!X-Emby-Token=secret'
    props = {}
    fake_li = SimpleNamespace(
        setProperty=lambda k, v: props.__setitem__(k, v),
        getVideoInfoTag=lambda: SimpleNamespace(),
    )
    monkeypatch_xbmcgui = SimpleNamespace(ListItem=lambda label='', path='': fake_li)
    import sys as _sys
    from bobbi_platform.kodi import make_item as real_make_item
    old_xbmcgui = _sys.modules.get('xbmcgui')
    _sys.modules['xbmcgui'] = monkeypatch_xbmcgui
    try:
        with reserve_playback('t4://aaa/item1', scope, transport=transport) as res:
            out = res.submit(
                17,
                full_url,
                title='Native Route Check',
                source_meta={'provider': 't4', 'source_id': 'a' * 32, 'source_generation': 'b' * 64, 'item_id': 'p1'},
                start_over=True,
                resolve_fn=lambda h, ok, item: resolved_items.append((h, ok, item)),
                play_fn=lambda *_a, **_k: None,
                item_factory=real_make_item,
            )
    finally:
        if old_xbmcgui is None:
            _sys.modules.pop('xbmcgui', None)
        else:
            _sys.modules['xbmcgui'] = old_xbmcgui
    assert out['opened'] is True
    assert authority.owner.desired['start_claimed'] is True
    assert authority.owner.desired['route'] == 'resolved_url'
    assert authority.bound_url == hashlib.sha256(full_url.encode('utf-8')).hexdigest()
    assert props['bobitv.request_id'] == out['request_id']
    assert props['bobitv.file_identity'] == authority.owner.desired['file_identity']
    assert len(resolved_items) == 1 and resolved_items[0][:2] == (17, True)


def test_native_owned_resume_seek_waits_for_observed_clock_and_never_fabricates_position():
    """Real-device regression (Kodi 21 setResolvedUrl + REV-09 #8):
    1. make_item stamps VideoInfoTag.setResumePoint alongside StartOffset.
    2. When setResolvedUrl opens at 0s despite _resume_offset_seconds=900, _observe_owned_tracks
       dispatches one scoped seek and only emits AV_START once observed player clock reaches ~900s.
    3. If seeking fails (player clock stays near 1.2s), AV_START honestly reports 1.2s, never 900s.
    """
    import importlib.util as _importlib_util
    from pathlib import Path as _Path
    import sys as _sys
    import threading as _threading
    from bobbi_platform.kodi import make_item as real_make_item

    _pc_path = _Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi/lib/services/playback_control.py'
    _spec = _importlib_util.spec_from_file_location('_test_bobbi_playback_control', _pc_path)
    _mod = _importlib_util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_mod)
    PlaybackControlServer = _mod.PlaybackControlServer

    resume_calls = []
    props = {}
    fake_tag = SimpleNamespace(setResumePoint=lambda *a: resume_calls.append(a))
    fake_li = SimpleNamespace(
        setProperty=lambda k, v: props.__setitem__(k, v),
        getVideoInfoTag=lambda: fake_tag,
    )
    old_xbmcgui = _sys.modules.get('xbmcgui')
    old_xbmc = _sys.modules.get('xbmc')
    _sys.modules['xbmcgui'] = SimpleNamespace(ListItem=lambda label='', path='': fake_li)
    try:
        real_make_item('http://127.0.0.1/v.mkv', {
            'title': 'Resume Item',
            '_resume_offset_seconds': 900.0,
            'video_info': {'duration': 1920},
        })
        assert props['StartOffset'] == '900.0'
        assert resume_calls[-1] == (900.0, 1920.0)
    finally:
        if old_xbmcgui is None:
            _sys.modules.pop('xbmcgui', None)
        else:
            _sys.modules['xbmcgui'] = old_xbmcgui

    player_state = {'pos': 0.3, 'dur': 1920.0}
    dispatched = []
    emitted = []

    class _FakeAuthority:
        def __init__(self, inst):
            self.owner = SimpleNamespace(
                boot_id='b' * 32,
                epoch=1,
                observed={'request_id': 'a' * 32, 'native_instance': inst, 'av_started': True, 'paused': False},
                terminal=None,
            )
            self.last_native = None

        def dispatch(self, msg):
            dispatched.append(msg)
            if msg['operation'] == 'playback_presentation':
                return {
                    'available': True,
                    'can_seek': True,
                    'duration_ms': 1920000,
                    'expected': {'boot_id': 'b' * 32, 'epoch': 1, 'request_id': 'a' * 32},
                }
            if msg['operation'] == 'playback_command':
                return {'status': 'queued'}
            return {'accepted': True}

    fake_host = SimpleNamespace(
        lock=_threading.Lock(),
        owned_tracks={
            'a' * 32: {
                'cancelled': False,
                'account': {'provider': 'emby'},
                'data': {'_resume_offset_seconds': 900.0},
            }
        },
        notify_playback_event=lambda ev: emitted.append(ev),
    )

    _sys.modules['xbmc'] = SimpleNamespace(
        Player=lambda: SimpleNamespace(
            isPlayingVideo=lambda: True,
            getTime=lambda: player_state['pos'],
            getTotalTime=lambda: player_state['dur'],
        )
    )
    try:
        # Case A: Seek succeeds -> AV_START reports observed 900.4s
        srv = PlaybackControlServer.__new__(PlaybackControlServer)
        srv.host = fake_host
        srv.authority = _FakeAuthority('11111111-1111-4111-8111-111111111111')
        srv._owned_state = None
        srv._owned_poll_due = 0.0
        srv._owned_resume_seek = None

        srv._observe_owned_tracks(10.0)
        assert emitted == []
        assert any(m.get('operation') == 'playback_command' and m['command']['action'] == 'seek' for m in dispatched)

        player_state['pos'] = 900.4
        srv._observe_owned_tracks(10.5)
        assert len(emitted) == 1
        assert emitted[0]['event'] == 'AV_START'
        assert emitted[0]['position'] == 900.4

        # Case B: Seek fails to move stream -> after bounded wait, AV_START reports honest 1.2s (never 900s!)
        emitted.clear()
        dispatched.clear()
        player_state['pos'] = 0.2
        srv2 = PlaybackControlServer.__new__(PlaybackControlServer)
        srv2.host = fake_host
        srv2.authority = _FakeAuthority('22222222-2222-4222-8222-222222222222')
        srv2._owned_state = None
        srv2._owned_poll_due = 0.0
        srv2._owned_resume_seek = None

        srv2._observe_owned_tracks(20.0)
        assert emitted == []
        player_state['pos'] = 1.2
        srv2._observe_owned_tracks(22.6)
        assert len(emitted) == 1
        assert emitted[0]['event'] == 'AV_START'
        assert emitted[0]['position'] == 1.2
    finally:
        if old_xbmc is None:
            _sys.modules.pop('xbmc', None)
        else:
            _sys.modules['xbmc'] = old_xbmc




def test_multicut_resume_rail_waits_for_explicit_start_after_selecting_cut(plugin, emby_env):
    route = dict(action='emby_play', source=emby_env.src_a.id, revision=emby_env.rev_a,
                 id='1001', resume_mode='resume')
    emby_env.picks[:] = [1, -1]
    plugin.module.execute(17, route)
    assert not any(ok for _, ok, _ in plugin.resolved)
    assert not any(path.endswith('/PlaybackInfo') for _,path,_,_ in emby_env.srv.calls)
    emby_env.picks[:] = [1, 1]
    plugin.module.execute(17, route)
    _, ok, item = plugin.resolved[-1]
    assert ok and float(item.properties.get('StartOffset', 0)) == 0


def test_old_profile_card_cannot_start_same_server_item_in_a_different_profile(plugin, emby_env):
    before = len(emby_env.srv.calls)
    plugin.module.execute(17, dict(action='emby_play', source=emby_env.src_a.id,
        revision=emby_env.rev_a, id='1001', profile='0'*64, resume_mode='resume'))
    assert not any(ok for _,ok,_ in plugin.resolved) and len(emby_env.srv.calls)==before

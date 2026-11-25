"""Contract regression suite for U01, U02, U03, U04, and U05.

Covers contract groups:
- CT-INVALIDATION (A01-01, PB-01)
- CT-DRAIN (A01-03, A03-04, A15-02, PB-10)
- CT-EVENT-OWNER (R07-01..04, R08-04..05, A15-01, F-PB-04-1..4)
- CT-RESUME (R08-01..03)
- CT-NEXT-GRANT (R08-06, A02-01, A02-02, F-PB-02-1..3, PB-03)
- CT-NEXT-FACTS (A02-03, A02-04, PB-09)
- CT-TRACK-INTENT (R08-07)
- CT-EMBY-CONFLICT (A03-01..03, PB-07)
- CT-STORAGE-RECOVERY (F-PB-05-1..3)
- CT-PROGRESS-QUEUE (F-PB-06-1..4)
- CT-WEBSOCKET (A04-01..02, PB-08)
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
from queue import Queue
import socket
import sqlite3
import struct
import sys
import threading
from threading import Event, Lock, Thread
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for rel in ('addons/script.module.bobbi.core/lib', 'addons/script.module.bobbi.platform/lib'):
    if str(ROOT / rel) not in sys.path:
        sys.path.insert(0, str(ROOT / rel))

from bobbi_core.library_contract import Source
from bobbi_core.next_episode_summary import NextResolution, label, project
from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_core.playback_completion import terminal_end
from bobbi_platform import emby_session as emby_mod
from bobbi_platform.emby_session import (
    EmbyInvalidationHub,
    EmbySessionReporter,
    TICKS_PER_SECOND,
    _WSFrameStream,
    _WSProtocolError,
    build_ws_client_frame,
    verify_ws_handshake,
    ws_accept_digest,
)
from bobbi_platform.host import Host
from bobbi_platform.libraries import Registry
from bobbi_platform.owned_playback import (
    OwnedPlaybackReservation,
    emby_source_scope,
    next_selection_identity,
)
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.server_http import Session as ServerHttpSession


def _load_playback_control():
    spec = importlib.util.spec_from_file_location(
        '_u01_u05_playback_control',
        ROOT / 'addons/plugin.video.bobbi/lib/services/playback_control.py',
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _NativeHarness:
    """Deterministic Native boundary driving real PlaybackAuthority."""

    def __init__(self):
        self.current = None
        self.commands = []
        self.subtitle_commands = []
        self.epoch = 0
        self.gui = {'gui_generation': 1, 'gui_user_intent': 1, 'fullscreen_instance': '', 'windows': []}
        self.subtitles_payload = None
        self.on_state_read = None

    def state(self):
        if self.on_state_read is not None:
            self.on_state_read()
        return dict(protocol=1, selection_epoch=self.epoch, playback=deepcopy(self.current), **deepcopy(self.gui))

    def intent(self, cmd):
        if cmd['expected_epoch'] != self.epoch:
            return {'reserved': False, 'selection_epoch': self.epoch}
        self.epoch += 1
        return {'reserved': True, 'selection_epoch': self.epoch}

    def control(self, cmd):
        self.commands.append(deepcopy(cmd))
        return {'queued': True, 'command_id': cmd['command_id']}

    def subtitles(self):
        if self.subtitles_payload is None:
            raise RuntimeError('Subtitles unavailable on legacy boundary')
        return deepcopy(self.subtitles_payload)

    def subtitle(self, cmd):
        self.subtitle_commands.append(deepcopy(cmd))
        return {'queued': True}


def _make_server_frame(opcode: int, payload: bytes, *, fin: bool = True) -> bytes:
    b0 = (0x80 if fin else 0x00) | (opcode & 0x0F)
    plen = len(payload)
    if plen < 126:
        hdr = bytes([b0, plen])
    elif plen <= 65535:
        hdr = bytes([b0, 126]) + struct.pack('!H', plen)
    else:
        hdr = bytes([b0, 127]) + struct.pack('!Q', plen)
    return hdr + payload


def _parse_client_frame(raw: bytes) -> tuple[bool, int, bool, bytes, bytes]:
    assert len(raw) >= 6
    b0, b1 = raw[0], raw[1]
    fin = (b0 & 0x80) != 0
    opcode = b0 & 0x0F
    masked = (b1 & 0x80) != 0
    plen = b1 & 0x7F
    idx = 2
    if plen == 126:
        plen = struct.unpack('!H', raw[2:4])[0]
        idx = 4
    mask = raw[idx:idx + 4] if masked else b''
    body = raw[idx + (4 if masked else 0):idx + (4 if masked else 0) + plen]
    unmasked = bytes(b ^ mask[i & 3] for i, b in enumerate(body)) if masked else body
    return fin, opcode, masked, unmasked, raw[idx + (4 if masked else 0) + plen:]


# ==============================================================================
# U01: CT-INVALIDATION & CT-DRAIN (PB-01)
# ==============================================================================

@pytest.mark.parametrize('branch', ['ws_connected', 'throttled', 'auth_required'])
def test_u01_three_fast_paths_complete_under_100ms_with_zero_io_and_multi_account_concurrency(tmp_path, branch):
    """A01-01, PB-01: WS connected, throttled second poll, and AUTH_REQUIRED never reacquire _lock or perform IO."""
    clock = [100.0]
    hub = EmbyInvalidationHub(tmp_path, clock=lambda: clock[0])
    sid_a, gen_a = 'a' * 32, 'b' * 64
    sid_b, gen_b = 'c' * 32, 'd' * 64

    ok_client = SimpleNamespace(
        session=SimpleNamespace(budget=lambda _s: nullcontext()),
        _identity=lambda **_kw: None,
        page_rows=lambda *_a, **_kw: ([], 0),
    )
    if branch == 'throttled':
        first = hub.poll_server_digest(sid_a, gen_a, client_loader=lambda *_: (ok_client, {}))
        assert first['last_confirmed_at'] == 100.0
        clock[0] = 110.0
    elif branch == 'auth_required':
        hub.mark_auth_state(sid_a, gen_a, 'AUTH_REQUIRED')
    else:
        with hub._lock:
            hub._entry(sid_a, gen_a)['ws_connected'] = True

    def forbid_io(*_args):
        raise AssertionError('Fast-path poll must never invoke client_loader')

    t0 = time.monotonic()
    snap = hub.poll_server_digest(sid_a, gen_a, client_loader=forbid_io)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.1
    assert snap['revision'] >= 1

    # Concurrent snapshot / notify / second-account poll / close must never deadlock
    errors = []
    workers = []
    for idx in range(6):
        def _spin(i=idx):
            try:
                for _ in range(25):
                    hub.snapshot(sid_a, gen_a)
                    hub.notify_event(sid_b, gen_b, item_ids=[f'item-{i}'])
                    hub.poll_server_digest(sid_a, gen_a, client_loader=forbid_io)
            except BaseException as exc:
                errors.append(exc)
        t = Thread(target=_spin, daemon=True)
        workers.append(t)
        t.start()
    for t in workers:
        t.join(2.0)
        assert not t.is_alive()
    assert not errors
    assert hub.close() is True
    assert hub.close() is True  # Idempotent repeat close


# ==============================================================================
# U02: CT-EVENT-OWNER, CT-RESUME, CT-TRACK-INTENT,PB-02, PB-04
# ==============================================================================

@pytest.mark.parametrize(
    'case,comp,legacy_pos,expected_reason,expect_next',
    [
        ('valid_eof', {'schema': 1, 'valid': True, 'position_ms': 3599000, 'duration_ms': 3600000, 'age_us': 2000}, 3598.0, 'NATURAL_EOF', True),
        ('early_eof', {'schema': 1, 'valid': True, 'position_ms': 120000, 'duration_ms': 3600000, 'age_us': 1000}, 3599.0, 'ERROR', False),
        ('invalid_flag', {'schema': 1, 'valid': False, 'position_ms': 0, 'duration_ms': 0, 'age_us': 0}, 3599.0, 'ERROR', False),
        ('stale_age', {'schema': 1, 'valid': True, 'position_ms': 3600000, 'duration_ms': 3600000, 'age_us': 6_000_000}, 3599.0, 'ERROR', False),
        ('instance_mismatch', 'MISMATCH', 3599.0, 'ERROR', False),
        ('legacy_near_end', None, 3598.5, 'NATURAL_EOF', True),
        ('legacy_early_cut', None, 120.0, 'ERROR', False),
    ],
)
def test_u02_pb02_unified_terminal_end_drives_emby_and_next_identically(
    tmp_path, case, comp, legacy_pos, expected_reason, expect_next
):
    """F-PB-02-1..3, R08-06: Only terminal_end-verified NATURAL_EOF marks Played or launches auto-next."""
    pc = _load_playback_control()
    inst = '11111111-1111-4111-8111-111111111111'
    other_inst = '22222222-2222-4222-8222-222222222222'
    req = 'a' * 32
    sid, gen = 'b' * 32, 'c' * 64
    meta = {
        'provider': 'emby',
        'source_id': sid,
        'source_generation': gen,
        'server_id': 'srv1',
        'user_id': 'u1',
        'item_id': 'ep1',
        'media_source_id': 'ms1',
        'play_session_id': 'ps1',
    }
    data = {'_owned_source': meta, '_owned_next': {'resolver': 'emby_same_season'}}

    played_marked = []
    stopped_bodies = []

    class _Client:
        session = SimpleNamespace(
            budget=lambda *_: nullcontext(),
            request=lambda path, **kw: stopped_bodies.append((path, deepcopy(kw.get('data')))),
        )

        def _item(self, _iid):
            return {'UserData': {'Played': False, 'PlaybackPositionTicks': 0}}

        def set_played(self, iid, val):
            played_marked.append((iid, val))

    hub = EmbyInvalidationHub(tmp_path)
    reporter = EmbySessionReporter(tmp_path, hub, client_loader=lambda *_: (_Client(), {}), start_worker=False)
    events = []
    launched = []

    def _notify(ev):
        events.append(ev)
        reporter.on_playback_event(ev)

    reporter.on_playback_event({
        'event': 'AV_START',
        'request_id': req,
        'position': 10.0,
        'duration': 3600.0,
        'observed_clock': True,
        'data': data,
    })
    reporter.drain_once()

    if comp == 'MISMATCH':
        last_nat = {
            'native_instance': other_inst,
            'completion_observation': {'schema': 1, 'valid': True, 'position_ms': 3600000, 'duration_ms': 3600000, 'age_us': 500},
        }
        term_dict = {'native_instance': inst, 'request_id': req, 'reason': 'NATURAL_EOF'}
    elif comp is None:
        last_nat = {'native_instance': inst}
        term_dict = {'native_instance': inst, 'request_id': req, 'reason': 'NATURAL_EOF'}
    else:
        last_nat = {'native_instance': inst, 'completion_observation': comp}
        term_dict = {'native_instance': inst, 'request_id': req, 'reason': 'NATURAL_EOF', 'completion_observation': comp}

    srv = pc.PlaybackControlServer.__new__(pc.PlaybackControlServer)
    srv.host = SimpleNamespace(
        lock=Lock(),
        owned_tracks={req: {'cancelled': False, 'account': {}, 'data': data}},
        notify_playback_event=_notify,
    )
    srv.authority = SimpleNamespace(
        owner=SimpleNamespace(observed=None, terminal=term_dict, boot_id='d' * 32, epoch=1),
        last_native=last_nat,
        terminal_seen_at=99.8,
    )
    srv._owned_state = {
        'boot_id': 'd' * 32,
        'epoch': 1,
        'request_id': req,
        'native_instance': inst,
        'account': {},
        'data': data,
        'position': legacy_pos,
        'duration': 3600.0,
        'observed_clock': True,
        'last_obs_at': 99.0,
        'last_clock_at': 99.0,
    }
    srv._launch_owned_next = launched.append

    srv._observe_owned_tracks(100.0)
    reporter.drain_once()

    assert len(events) == 1
    assert events[0]['reason'] == expected_reason
    assert bool(launched) is expect_next
    assert bool(played_marked) is expect_next
    stop_call = next(b for p, b in stopped_bodies if p == '/Sessions/Playing/Stopped')
    assert stop_call['Failed'] is (expected_reason == 'ERROR')
    reporter.close()
    hub.close()


def test_u02_pb04_same_instance_clock_and_mid_call_switch_rejection(monkeypatch):
    """F-PB-04-1..4, A15-01: Rejects cross-instance B clock (including mid-call switch); preserves valid A clock."""
    pc = _load_playback_control()
    native = _NativeHarness()
    authority = PlaybackAuthority(native)
    req_a = 'a' * 32
    inst_a = '11111111-1111-4111-8111-111111111111'
    inst_b = '22222222-2222-4222-8222-222222222222'

    snap = authority.dispatch({'operation': 'snapshot'})
    accepted = authority.dispatch({
        'operation': 'select',
        'boot_id': snap['boot_id'],
        'epoch': snap['epoch'],
        'request_id': req_a,
        'selection_identity': 'rel-a',
    })
    ctx = {'boot_id': snap['boot_id'], 'epoch': accepted['epoch'], 'request_id': req_a}
    assert authority.dispatch(dict(ctx, operation='bind_file', selection_identity='rel-a', file_identity='rel-a|fa', url_sha256='1' * 64))['bound']
    assert authority.dispatch(dict(ctx, operation='claim_start', route='resolved_url'))['status'] == 'CLAIMED'
    native.current = dict(
        protocol=1,
        native_instance=inst_a,
        request_id=req_a,
        file_identity='rel-a|fa',
        url_sha256='1' * 64,
        phase='AV_STARTED',
        sequence=1,
        user_intent=0,
        paused=False,
        subtitle_intent=0,
        subtitle_auto_intent=0,
        audio_intent=0,
        open_epoch=native.epoch,
    )
    authority.refresh()

    emitted = []
    data_a = {'_owned_source': {'provider': 'emby', 'source_id': 'a' * 32, 'source_generation': 'b' * 64, 'server_id': 's', 'user_id': 'u', 'item_id': 'm1', 'media_source_id': 'ms1'}}
    srv = pc.PlaybackControlServer.__new__(pc.PlaybackControlServer)
    srv.host = SimpleNamespace(
        lock=Lock(),
        owned_tracks={req_a: {'cancelled': False, 'account': {}, 'data': data_a}},
        notify_playback_event=emitted.append,
    )
    srv.native = native
    srv.authority = authority
    srv._owned_state = None
    srv._owned_poll_due = 0.0
    srv._owned_resume_seek = None

    # 1. Valid bracketed read for A (120s / 3600s), pause, and seek to 300s (F-PB-04-4)
    clock_box = {'pos': 120.0, 'dur': 3600.0, 'switch_mid_call': False}

    def _get_time():
        if clock_box['switch_mid_call']:
            # Simulate native switching from A to B AFTER before_state and isPlayingVideo()!
            native.epoch += 1
            native.current = dict(native.current, native_instance=inst_b, request_id='', file_identity='', open_epoch=native.epoch)
            return 2700.0
        return clock_box['pos']

    monkeypatch.setitem(
        sys.modules,
        'xbmc',
        SimpleNamespace(
            Player=lambda: SimpleNamespace(
                isPlayingVideo=lambda: True,
                getTime=_get_time,
                getTotalTime=lambda: 4000.0 if clock_box['switch_mid_call'] else clock_box['dur'],
            )
        ),
    )

    srv._observe_owned_tracks(10.0)
    assert len(emitted) == 1 and emitted[0]['event'] == 'AV_START' and emitted[0]['position'] == 120.0

    # Seek on A to 300s -> emits PROGRESS with 300.0
    clock_box['pos'] = 300.0
    srv._observe_owned_tracks(12.0)
    assert emitted[-1]['event'] == 'PROGRESS' and emitted[-1]['position'] == 300.0

    # 2. Switch mid-call between isPlayingVideo() and getTime()/getTotalTime() (F-PB-04-2)!
    clock_box['switch_mid_call'] = True
    srv._observe_owned_tracks(14.0)
    # Must NOT emit PROGRESS with 2700.0!
    assert all(e['position'] != 2700.0 for e in emitted)
    assert srv._owned_state['position'] == 300.0

    # Next tick after authority refreshes observes B's takeover and emits TERMINAL for A with 300.0 (never 2700.0!)
    authority.refresh()
    srv._observe_owned_tracks(15.0)
    assert emitted[-1]['event'] == 'TERMINAL'
    assert emitted[-1]['position'] == 300.0 and emitted[-1]['duration'] == 3600.0


def test_u02_track_intent_manual_subtitle_preserved_over_late_auto():
    """R08-07 (CT-TRACK-INTENT): Manual subtitle/audio user intent is never overwritten by late automatic discovery."""
    native = _NativeHarness()
    authority = PlaybackAuthority(native)
    req = 'a' * 32
    inst = '11111111-1111-4111-8111-111111111111'
    snap = authority.dispatch({'operation': 'snapshot'})
    acc = authority.dispatch({'operation': 'select', 'boot_id': snap['boot_id'], 'epoch': snap['epoch'], 'request_id': req, 'selection_identity': 'rel-sub'})
    ctx = {'boot_id': snap['boot_id'], 'epoch': acc['epoch'], 'request_id': req}
    authority.dispatch(dict(ctx, operation='bind_file', selection_identity='rel-sub', file_identity='rel-sub|f1', url_sha256='2' * 64))
    authority.dispatch(dict(ctx, operation='claim_start', route='resolved_url'))

    # User manually toggled subtitles off (subtitle_intent=2 != subtitle_auto_intent=0)
    native.current = dict(
        protocol=1,
        native_instance=inst,
        request_id=req,
        file_identity='rel-sub|f1',
        url_sha256='2' * 64,
        phase='AV_STARTED',
        sequence=1,
        user_intent=1,
        paused=False,
        subtitle_intent=2,
        subtitle_auto_intent=0,
        audio_intent=1,
        open_epoch=native.epoch,
    )
    native.subtitles_payload = {
        'control_protocol': 1,
        'status': 'READY',
        'selection_epoch': native.epoch,
        'receipt': deepcopy(native.current),
        'visible': False,
        'current_index': 0,
        'audio_index': 1,
        'position_ms': 15000,
        'duration_ms': 1200000,
        'can_seek': True,
        'audio_streams': [{'index': 1, 'stream_key': '3' * 64, 'name': 'Japanese', 'language': 'jpn'}],
        'streams': [{'index': 0, 'stream_key': '4' * 64, 'name': '简体中文', 'language': 'zho'}],
    }
    authority.refresh()
    res = authority.dispatch(dict(ctx, operation='auto_chinese_subtitle', native_instance=inst))
    assert res['status'] == 'MANUAL_PRESERVED'
    assert native.subtitle_commands == []
    pres = authority.dispatch({'operation': 'playback_presentation', 'include_owner': True})
    assert pres['available'] is True and '手动控制' in pres['audio_status']


def test_u02_ct_resume_exact_instance_seek_and_supersession_guard():
    """A04-04 (CT-RESUME): Resume seek binds exact (boot_id, epoch, request_id, native_instance) and never leaks to B."""
    pc = _load_playback_control()
    native = _NativeHarness()
    authority = PlaybackAuthority(native)
    req_a, req_b = 'a' * 32, 'b' * 32
    inst_a, inst_b = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
    snap = authority.dispatch({'operation': 'snapshot'})
    acc_a = authority.dispatch({'operation': 'select', 'boot_id': snap['boot_id'], 'epoch': snap['epoch'], 'request_id': req_a, 'selection_identity': 'rel-a'})
    ctx_a = {'boot_id': snap['boot_id'], 'epoch': acc_a['epoch'], 'request_id': req_a}
    authority.dispatch(dict(ctx_a, operation='bind_file', selection_identity='rel-a', file_identity='rel-a|fa', url_sha256='1' * 64))
    authority.dispatch(dict(ctx_a, operation='claim_start', route='resolved_url'))
    native.current = dict(
        protocol=1, native_instance=inst_a, request_id=req_a, file_identity='rel-a|fa', url_sha256='1' * 64,
        phase='AV_STARTED', sequence=1, user_intent=0, paused=False,
        subtitle_intent=0, subtitle_auto_intent=0, audio_intent=0, open_epoch=native.epoch,
    )
    native.subtitles_payload = {
        'control_protocol': 1, 'status': 'READY', 'selection_epoch': native.epoch, 'receipt': deepcopy(native.current),
        'visible': True, 'current_index': -1, 'audio_index': 0, 'position_ms': 1000, 'duration_ms': 1200000,
        'can_seek': True, 'audio_streams': [], 'streams': [],
    }
    authority.refresh()
    srv = pc.PlaybackControlServer.__new__(pc.PlaybackControlServer)
    srv.host = SimpleNamespace(
        lock=Lock(),
        owned_tracks={
            req_a: {'cancelled': False, 'account': {}, 'data': {'_resume_offset_seconds': 600.0}},
            req_b: {'cancelled': False, 'account': {}, 'data': {}},
        },
        notify_playback_event=lambda _e: None,
    )
    srv.native = native
    srv.authority = authority
    srv._owned_state = None
    srv._owned_poll_due = 0.0
    srv._owned_resume_seek = None

    srv._observe_owned_tracks(time.monotonic())
    seek_cmds = [c for c in native.commands if c.get('action') == 'seek']
    assert len(seek_cmds) == 1
    assert [c for c in native.commands if c.get('native_instance') == inst_b] == []
    assert native.commands[0]['action'] == 'seek'
    assert native.commands[0]['position_ms'] == 600000
    assert native.commands[0]['native_instance'] == inst_a

    # Supersede with fresh selection B (start from 0s) -> B never receives A's 600s seek
    snap2 = authority.dispatch({'operation': 'snapshot'})
    acc_b = authority.dispatch({'operation': 'select', 'boot_id': snap2['boot_id'], 'epoch': snap2['epoch'], 'request_id': req_b, 'selection_identity': 'rel-b'})
    ctx_b = {'boot_id': snap2['boot_id'], 'epoch': acc_b['epoch'], 'request_id': req_b}
    authority.dispatch(dict(ctx_b, operation='bind_file', selection_identity='rel-b', file_identity='rel-b|fb', url_sha256='2' * 64))
    authority.dispatch(dict(ctx_b, operation='claim_start', route='resolved_url'))
    native.current = dict(native.current, native_instance=inst_b, request_id=req_b, file_identity='rel-b|fb', url_sha256='2' * 64, open_epoch=native.epoch)
    native.subtitles_payload = dict(native.subtitles_payload, selection_epoch=native.epoch, receipt=deepcopy(native.current), position_ms=1000)
    authority.refresh()
    srv._observe_owned_tracks(time.monotonic())
    seek_cmds = [c for c in native.commands if c.get('action') == 'seek']
    assert len(seek_cmds) == 1
    assert [c for c in native.commands if c.get('native_instance') == inst_b] == []


# ==============================================================================
# U03: CT-NEXT-GRANT & CT-NEXT-FACTS (PB-03, PB-09)
# ==============================================================================

def _setup_playing_episode_a(pc, monkeypatch):
    native = _NativeHarness()
    authority = PlaybackAuthority(native)
    req_a = 'a' * 32
    inst_a = '11111111-1111-4111-8111-111111111111'
    sid, gen = 'c' * 32, 'd' * 64
    scope = emby_source_scope(source_id=sid, generation=gen, server_id='srv1', user_id='u1')
    accounts = SimpleNamespace(
        is_current=lambda s: s == scope,
        require_current=lambda s, authenticated=True: s if s == scope else (_ for _ in ()).throw(PanError('PAN_ACCOUNT_CHANGED')),
        run_if_current=lambda s, fn, authenticated=True: fn() if s == scope else (_ for _ in ()).throw(PanError('PAN_ACCOUNT_CHANGED')),
    )
    authority.configure_accounts(accounts)

    snap = authority.dispatch({'operation': 'snapshot'})
    acc = authority.dispatch({
        'operation': 'select',
        'boot_id': snap['boot_id'],
        'epoch': snap['epoch'],
        'request_id': req_a,
        'selection_identity': 'transport:' + '1' * 64,
        'account_scope': scope,
    })
    ctx = {'boot_id': snap['boot_id'], 'epoch': acc['epoch'], 'request_id': req_a}
    url_a = 'http://127.0.0.1/ep1.mkv|redirect-limit=0'
    authority.dispatch(dict(
        ctx,
        operation='bind_file',
        selection_identity='transport:' + '1' * 64,
        file_identity='transport:' + '1' * 64 + '|' + '2' * 64,
        url_sha256=hashlib.sha256(url_a.encode()).hexdigest(),
        file_evidence='AUTO_VERIFIED_FILE',
    ))
    authority.dispatch(dict(ctx, operation='claim_start', route='resolved_url'))
    native.current = dict(
        protocol=1,
        native_instance=inst_a,
        request_id=req_a,
        file_identity='transport:' + '1' * 64 + '|' + '2' * 64,
        url_sha256=hashlib.sha256(url_a.encode()).hexdigest(),
        phase='AV_STARTED',
        sequence=1,
        user_intent=0,
        paused=False,
        subtitle_intent=0,
        subtitle_auto_intent=0,
        audio_intent=0,
        open_epoch=native.epoch,
    )
    authority.refresh()

    data_a = {
        'request_id': req_a,
        '_account': deepcopy(scope),
        'mode': 'tv',
        'selection_policy': 'exact',
        'file_evidence': 'AUTO_VERIFIED_FILE',
        '_emby_season_ref': 'abcd1234abcd1234',
        'tv_data': {'season': 1, 'episode': 1},
        '_owned_source': {
            'provider': 'emby',
            'source_id': sid,
            'source_generation': gen,
            'server_id': 'srv1',
            'user_id': 'u1',
            'item_id': 'ep1',
            'media_source_id': 'ms1',
        },
        '_owned_next': {
            'resolver': 'test_emby_next',
            'profile_root': '/tmp',
            'season_id': 's1',
            'season': 1,
            'episode': 1,
        },
    }
    host = SimpleNamespace(
        lock=Lock(),
        stopping=Event(),
        check_profile=lambda: True,
        playback_accounts=accounts,
        owned_tracks={req_a: {'cancelled': False, 'account': deepcopy(scope), 'data': deepcopy(data_a)}},
        notify_playback_event=lambda _ev: None,
    )
    now0 = time.monotonic()
    srv = pc.PlaybackControlServer.__new__(pc.PlaybackControlServer)
    srv.host = host
    srv.native = native
    srv.authority = authority
    srv._owned_state = {
        'boot_id': ctx['boot_id'],
        'epoch': ctx['epoch'],
        'request_id': req_a,
        'native_instance': inst_a,
        'account': deepcopy(scope),
        'data': deepcopy(data_a),
        'prefetched_next': None,
        'position': 1199.0,
        'duration': 1200.0,
        'observed_clock': True,
        'paused': False,
        'last_obs_at': now0 - 1.0,
        'last_clock_at': now0 - 1.0,
        'last_emit_at': now0 - 5.0,
    }
    srv._owned_poll_due = 0.0
    srv._owned_next_worker = None
    srv._owned_next_summaries = Queue(maxsize=8)
    srv._owned_next_candidates = Queue(maxsize=4)
    srv._owned_next_ready = Queue(maxsize=4)
    srv._owned_next_consumed_parents = []
    srv._owned_terminal_parent = None
    srv._owned_resume_seek = None
    return srv, authority, native, host, scope, req_a, inst_a, data_a


def test_u03_positive_uncontested_natural_eof_launches_child_once_without_generic_select(monkeypatch):
    """A02-02: Uncontested NATURAL_EOF within 3s window uses authorize_next + reserve_child and plays child exactly once."""
    pc = _load_playback_control()
    srv, authority, native, host, scope, req_a, inst_a, data_a = _setup_playing_episode_a(pc, monkeypatch)

    played_urls = []
    open_session_flags = []

    def _fake_resolver(_cur, _spec, _cancelled, *, open_session=True):
        open_session_flags.append(open_session)
        cand = {
            '_account': deepcopy(scope),
            'mode': 'tv',
            '_emby_season_ref': 'abcd1234abcd1234',
            'prepared_version_key': None,
            '_next_cloud_verified': False,
            '_next_recheck': not open_session,
            'url': 'http://127.0.0.1/ep2.mkv|redirect-limit=0',
            'title': 'Episode 2',
            'mime': 'video/x-matroska' if open_session else '',
            'video_info': {'title': 'Episode 2', 'mediatype': 'episode', 'season': 1, 'episode': 2},
            'tv_data': {'season': 1, 'episode': 2},
            '_owned_source': {
                'provider': 'emby',
                'source_id': scope['source_id'],
                'source_generation': scope['generation'],
                'server_id': 'srv1',
                'user_id': 'u1',
                'item_id': 'ep2',
                'media_source_id': 'ms2',
                'play_session_id': 'ps-ep2' if open_session else '',
            },
            '_owned_next': {'resolver': 'test_emby_next', 'profile_root': '/tmp', 'season_id': 's1', 'season': 1, 'episode': 2},
        }
        return NextResolution('candidate', candidate=cand)

    from bobbi_platform import owned_playback as op_mod
    monkeypatch.setitem(op_mod._NEXT_RESOLVERS, 'test_emby_next', _fake_resolver)
    monkeypatch.setattr(
        op_mod,
        'reserve_playback',
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Generic reserve_playback must NEVER be called by auto-next')),
    )
    fake_li = SimpleNamespace(setProperty=lambda *a: None, getVideoInfoTag=lambda: SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=lambda *a, **kw: fake_li))
    monkeypatch.setitem(
        sys.modules,
        'xbmc',
        SimpleNamespace(Player=lambda: SimpleNamespace(play=lambda url, item=None: played_urls.append(url))),
    )
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(setResolvedUrl=lambda *a: None))

    # 1. Summary prefetch runs during playback with open_session=False
    srv._prepare_owned_next_summary(authority.owner.boot_id, authority.owner.epoch, req_a, inst_a, scope, data_a)
    deadline = time.monotonic() + 1.0
    while srv._owned_next_summaries.empty() and time.monotonic() < deadline:
        time.sleep(0.01)
    srv._observe_owned_tracks(time.monotonic())
    assert open_session_flags == [False]
    assert srv._owned_state['prefetched_next'] is not None

    # 2. Parent A reaches verified NATURAL_EOF and player becomes idle
    comp = {'schema': 1, 'valid': True, 'position_ms': 1200000, 'duration_ms': 1200000, 'age_us': 800}
    eof_row = dict(native.current, phase='TERMINAL', reason='NATURAL_EOF', sequence=2, completion_observation=comp)
    authority.event('xbmc', 'Player.OnBobiState', eof_row)
    native.current = None
    authority.refresh()

    srv._observe_owned_tracks(time.monotonic())
    assert srv._owned_next_worker is not None
    srv._owned_next_worker.join(1.0)
    srv._observe_owned_tracks(time.monotonic())

    assert open_session_flags == [False, True]
    assert played_urls == ['http://127.0.0.1/ep2.mkv|redirect-limit=0']
    child_req = authority.owner.desired['request_id']
    assert child_req != req_a and child_req in host.owned_tracks

    # 3. Duplicate _launch_owned_next for same parent is strictly rejected (one-use grant!)
    srv._launch_owned_next(data_a)
    srv._observe_owned_tracks(time.monotonic())
    assert len(played_urls) == 1


@pytest.mark.parametrize('interference', ['b_not_open', 'b_open', 'b_av_started', 'gui_back', 'account_changed', 'expired_window'])
def test_u03_negative_contested_or_expired_never_hijacks_new_selection(monkeypatch, interference):
    """A02-01, A02-02, PB-03: Slow resolution contested by B (any phase), GUI action, account change, or >3s expiry never plays A-next."""
    pc = _load_playback_control()
    srv, authority, native, host, scope, req_a, inst_a, data_a = _setup_playing_episode_a(pc, monkeypatch)
    entered, release = Event(), Event()
    played_urls = []

    def _slow_resolver(_cur, _spec, _cancelled, *, open_session=True):
        entered.set()
        release.wait(2.0)
        return NextResolution('candidate', candidate={
            '_account': deepcopy(scope),
            'mode': 'tv',
            '_emby_season_ref': 'abcd1234abcd1234',
            '_next_recheck': False,
            'url': 'http://127.0.0.1/ep2.mkv|redirect-limit=0',
            'title': 'Episode 2',
            '_owned_source': {
                'provider': 'emby',
                'source_id': scope['source_id'],
                'source_generation': scope['generation'],
                'server_id': 'srv1',
                'user_id': 'u1',
                'item_id': 'ep2',
                'media_source_id': 'ms2',
            },
        })

    from bobbi_platform import owned_playback as op_mod
    monkeypatch.setitem(op_mod._NEXT_RESOLVERS, 'test_emby_next', _slow_resolver)
    monkeypatch.setitem(
        sys.modules,
        'xbmc',
        SimpleNamespace(Player=lambda: SimpleNamespace(play=lambda url, item=None: played_urls.append(url))),
    )
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(setResolvedUrl=lambda *a: None))

    comp = {'schema': 1, 'valid': True, 'position_ms': 1200000, 'duration_ms': 1200000, 'age_us': 500}
    authority.event('xbmc', 'Player.OnBobiState', dict(native.current, phase='TERMINAL', reason='NATURAL_EOF', sequence=2, completion_observation=comp))
    native.current = None
    authority.refresh()

    # Trigger cold auto-next on A's NATURAL_EOF
    srv._observe_owned_tracks(time.monotonic())
    assert entered.wait(1.0)

    req_b = 'b' * 32
    inst_b = '33333333-3333-4333-8333-333333333333'
    if interference in ('b_not_open', 'b_open', 'b_av_started'):
        snap = authority.dispatch({'operation': 'snapshot'})
        acc_b = authority.dispatch({
            'operation': 'select',
            'boot_id': snap['boot_id'],
            'epoch': snap['epoch'],
            'request_id': req_b,
            'selection_identity': 'transport:' + '9' * 64,
            'account_scope': scope,
        })
        url_b = 'http://127.0.0.1/movie-b.mkv'
        authority.dispatch({
            'operation': 'bind_file',
            'boot_id': snap['boot_id'],
            'epoch': acc_b['epoch'],
            'request_id': req_b,
            'selection_identity': 'transport:' + '9' * 64,
            'file_identity': 'transport:' + '9' * 64 + '|' + '8' * 64,
            'url_sha256': hashlib.sha256(url_b.encode()).hexdigest(),
        })
        authority.dispatch({'operation': 'claim_start', 'boot_id': snap['boot_id'], 'epoch': acc_b['epoch'], 'request_id': req_b, 'route': 'resolved_url'})
        if interference in ('b_open', 'b_av_started'):
            native.current = dict(
                protocol=1,
                native_instance=inst_b,
                request_id=req_b,
                file_identity='transport:' + '9' * 64 + '|' + '8' * 64,
                url_sha256=hashlib.sha256(url_b.encode()).hexdigest(),
                phase='OPEN' if interference == 'b_open' else 'AV_STARTED',
                sequence=1,
                user_intent=0,
                paused=False,
                subtitle_intent=0,
                subtitle_auto_intent=0,
                audio_intent=0,
                open_epoch=native.epoch,
            )
            authority.refresh()
    elif interference == 'gui_back':
        native.gui['gui_user_intent'] += 1
        authority.refresh()
        authority.dispatch({
            'operation': 'return_to_menu',
            'boot_id': authority.owner.boot_id,
            'epoch': authority.owner.epoch,
            'request_id': req_a,
            'native_instance': inst_a,
            'account_scope': scope,
        })
    elif interference == 'account_changed':
        scope['generation'] = 'f' * 64
    elif interference == 'expired_window':
        authority.terminal_seen_at -= 3.5

    release.set()
    srv._owned_next_worker.join(1.0)
    srv._observe_owned_tracks(time.monotonic())

    assert played_urls == []
    if interference in ('b_not_open', 'b_open', 'b_av_started'):
        assert authority.owner.desired['request_id'] == req_b
        assert not authority.owner.desired['cancelled']


def test_u03_pb09_five_distinct_summary_states_and_4k_to_1080p_not_same_release(tmp_path, monkeypatch):
    """A02-03, A02-04, PB-09: Distinct states for offline/auth/multi_version/page_limit/confirmed_end; 4K->1080p never SAME_RELEASE_PREPARED; zero PlaybackInfo during summary."""
    pc = _load_playback_control()
    sid, gen = 'a' * 32, 'b' * 64
    scope = emby_source_scope(source_id=sid, generation=gen, server_id='srv', user_id='usr')
    res_obj = OwnedPlaybackReservation(
        binding=None,
        playback_client=None,
        host_call=None,
        adapter='native',
        request_id='d' * 32,
        selection_identity='cur',
        account_scope=scope,
    )
    current = res_obj.build_data(
        'http://127.0.0.1/ep1-4k.mkv',
        title='Current 4K',
        source_meta={'provider': 'emby', 'server_id': 'srv', 'user_id': 'usr', 'source_id': sid, 'source_generation': gen, 'item_id': 'ep1', 'media_source_id': 'v4k'},
        info={'season': 1, 'episode': 1},
        next_candidate={'resolver': 'emby_same_season', 'profile_root': str(tmp_path), 'season_id': 's1', 'season': 1, 'episode': 1},
    )
    saved = {'location': 'http://127.0.0.1:8096', 'token': 'tok', 'server_id': 'srv', 'user_id': 'usr'}
    pb_sessions = []

    class _ModeClient:
        def __init__(self, mode):
            self.mode = mode
            self.session = SimpleNamespace(budget=lambda *_: nullcontext())

        def _identity(self, **_kw):
            if self.mode == 'auth':
                raise PanError('PAN_SERVER_UNAUTHORIZED')

        def page_rows(self, _parent, page, _size, display=True):
            if self.mode == 'network':
                raise PanError('PAN_NETWORK_ERROR')
            if self.mode == 'confirmed_end':
                return [], 0
            if self.mode == 'page_limit':
                start = 3 + (page - 1) * 20
                return [{'Type': 'Episode', 'ParentIndexNumber': 1, 'IndexNumber': i, 'Id': f'ep{i}'} for i in range(start, start + 20)], 205
            return [{'Type': 'Episode', 'ParentIndexNumber': 1, 'IndexNumber': 2, 'Id': 'ep2'}], 1

        def _item(self, iid):
            sources = [{'Id': 'v1080', 'Protocol': 'File', 'MediaStreams': [{'Type': 'Video', 'Width': 1920, 'Height': 1080}]}]
            if self.mode == 'multi_version':
                sources.append({'Id': 'v4k', 'Protocol': 'File'})
            return {'Id': iid, 'Name': 'Ep 2 (1080p)', 'MediaSources': sources, 'RunTimeTicks': 1200 * TICKS_PER_SECOND}

        def open_playback_session(self, *a, **kw):
            pb_sessions.append(self.mode)
            return {'url': 'http://127.0.0.1:8096/Videos/ep2/stream?Static=true&MediaSourceId=v1080', 'mime': 'video/x-matroska', 'play_session_id': 'ps2'}

    got = {}
    for mode in ('network', 'auth', 'multi_version', 'confirmed_end', 'page_limit', 'single_1080'):
        monkeypatch.setattr(emby_mod, '_load_emby_client', lambda *_a, _m=mode, **_k: (_ModeClient(_m), saved))
        srv = pc.PlaybackControlServer.__new__(pc.PlaybackControlServer)
        srv.host = SimpleNamespace(stopping=Event(), check_profile=lambda: True)
        srv._owned_next_summaries = Queue(maxsize=8)
        srv._prepare_owned_next_summary('e' * 32, 1, current['request_id'], 'inst-1', scope, current)
        got[mode] = srv._owned_next_summaries.get(timeout=1.0)['summary']

    assert pb_sessions == []
    states = [got[m]['state'] for m in ('network', 'auth', 'multi_version', 'confirmed_end', 'page_limit', 'single_1080')]
    assert len(set(states)) == 6
    assert got['confirmed_end']['state'] == 'complete'
    assert got['page_limit']['state'] == 'unavailable' and got['page_limit']['reason_code'] == 'SCAN_LIMIT_REACHED'
    assert got['single_1080']['state'] == 'preparing' and got['single_1080']['reason_code'] == 'FINAL_CHECK_REQUIRED'
    assert got['single_1080']['release_family_ref'] is None
    assert 'S01E02' in label(got['single_1080'])


# ==============================================================================
# U04: CT-STORAGE-RECOVERY, CT-PROGRESS-QUEUE, CT-EMBY-CONFLICT, CT-DRAIN
# ==============================================================================

def test_u04_pb05_sqlite_exclusive_lock_recovery_and_generation_isolation(tmp_path):
    """F-PB-05-1..3: Reporter survives SQLite EXCLUSIVE lock, recovers Playing->Progress->Stopped, and drops removed/re-generated sources."""
    unhandled = []
    old_hook = threading.excepthook
    threading.excepthook = lambda info: unhandled.append(info)
    try:
        reg = Registry(tmp_path / 'libraries.sqlite3')
        src = Source(
            'a' * 32,
            'Emby A',
            'media_server',
            'http://127.0.0.1:8096',
            password='tok-a',
            metadata={'schema': 1, 'provider': 'emby', 'server_id': 's1', 'user_id': 'u1'},
        )
        reg.save(src)
        rev1 = reg.source_snapshot(src.id)[1]
        reg.close()

        recorded = []

        class _FakeSession:
            def budget(self, *_a):
                return nullcontext()

            def request(self, path, **kw):
                if path == '/System/Info/Public':
                    return {'Id': 's1'}
                if path == '/Users/u1':
                    return {'Id': 'u1'}
                if path.startswith('/Users/u1/Items/'):
                    return {'Id': 'ep1', 'UserData': {'Played': True, 'PlaybackPositionTicks': 0}}
                recorded.append((path, kw.get('data', {}).get('PositionTicks')))
                return None

        orig_load = emby_mod._load_emby_client
        hub = EmbyInvalidationHub(tmp_path)
        reporter = EmbySessionReporter(
            tmp_path,
            hub,
            client_loader=lambda sid, gen: orig_load(tmp_path, sid, gen, session_factory=lambda _saved: _FakeSession()),
        )

        blocker = sqlite3.connect(tmp_path / 'libraries.sqlite3', timeout=0)
        blocker.execute('BEGIN EXCLUSIVE')
        meta = {
            'provider': 'emby',
            'source_id': src.id,
            'source_generation': rev1,
            'server_id': 's1',
            'user_id': 'u1',
            'item_id': 'ep1',
            'media_source_id': 'ms1',
            'play_session_id': 'ps1',
        }
        req = '1' * 32
        reporter.on_playback_event({'event': 'AV_START', 'request_id': req, 'position': 5.0, 'duration': 600.0, 'observed_clock': True, 'data': {'_owned_source': meta}})
        time.sleep(0.25)
        assert reporter._worker.is_alive()
        assert unhandled == []

        # Release SQLite lock -> worker recovers AV_START, then processes PROGRESS and TERMINAL in order!
        blocker.rollback()
        blocker.close()
        reporter.on_playback_event({'event': 'PROGRESS', 'request_id': req, 'position': 120.0, 'duration': 600.0, 'observed_clock': True, 'data': {'_owned_source': meta}})
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if [p for p, _ in recorded] == ['/Sessions/Playing', '/Sessions/Playing/Progress']:
                break
            time.sleep(0.03)
        reporter.on_playback_event({'event': 'TERMINAL', 'request_id': req, 'position': 600.0, 'duration': 600.0, 'reason': 'NATURAL_EOF', 'observed_clock': True, 'data': {'_owned_source': meta}})

        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline:
            if [p for p, _ in recorded] == ['/Sessions/Playing', '/Sessions/Playing/Progress', '/Sessions/Playing/Stopped']:
                break
            time.sleep(0.03)
        assert [p for p, _ in recorded] == ['/Sessions/Playing', '/Sessions/Playing/Progress', '/Sessions/Playing/Stopped']

        # Credential generation change discards stale work cleanly (F-PB-05-2)
        reg2 = Registry(tmp_path / 'libraries.sqlite3')
        reg2.save(Source(src.id, 'Emby A', 'media_server', 'http://127.0.0.1:8096', password='tok-a-rotated', metadata=src.metadata))
        rev2 = reg2.source_snapshot(src.id)[1]
        reg2.close()
        assert rev2 != rev1

        recorded.clear()
        reporter.on_playback_event({'event': 'AV_START', 'request_id': '2' * 32, 'position': 10.0, 'duration': 600.0, 'observed_clock': True, 'data': {'_owned_source': meta}})
        time.sleep(0.25)
        assert recorded == []
        assert reporter.close() is True
        assert hub.close() is True
    finally:
        threading.excepthook = old_hook


def test_u04_pb06_capacity_64_saturation_multi_account_coalescing_seal_and_task_count(tmp_path):
    """F-PB-06-1..4: 64-slot queue saturation recovers, coalesces per request/account, seals after TERMINAL, and keeps exact task_done count."""
    calls = []

    class _Client:
        session = SimpleNamespace(
            budget=lambda *_: nullcontext(),
            request=lambda path, **kw: calls.append((path, kw['data']['ItemId'], kw['data']['PositionTicks'])),
        )

        def _item(self, _iid):
            return {'UserData': {'Played': False, 'PlaybackPositionTicks': 0}}

    hub = EmbyInvalidationHub(tmp_path)
    reporter = EmbySessionReporter(tmp_path, hub, client_loader=lambda *_: (_Client(), {}), start_worker=False)

    def _ev(req, kind, pos, user='u1', item='i1'):
        return {
            'event': kind,
            'request_id': req,
            'position': pos,
            'duration': 1000.0,
            'observed_clock': True,
            'reason': 'STOP' if kind == 'TERMINAL' else '',
            'data': {
                '_owned_source': {
                    'provider': 'emby',
                    'source_id': 'a' * 32 if user == 'u1' else 'b' * 32,
                    'source_generation': 'c' * 64,
                    'server_id': 's1',
                    'user_id': user,
                    'item_id': item,
                    'media_source_id': 'm1',
                }
            },
        }

    # Fill all 64 slots
    for i in range(31):
        r = f'{i:032x}'
        reporter.on_playback_event(_ev(r, 'AV_START', 1.0))
        reporter.on_playback_event(_ev(r, 'TERMINAL', 2.0))
    req_a = 'e' * 32
    req_b = 'f' * 32
    reporter.on_playback_event(_ev(req_a, 'AV_START', 5.0, user='u1', item='itemA'))
    reporter.on_playback_event(_ev(req_b, 'AV_START', 6.0, user='u2', item='itemB'))
    assert reporter._queue.qsize() == 64

    # Both accounts emit multiple PROGRESS updates while queue is completely full!
    reporter.on_playback_event(_ev(req_a, 'PROGRESS', 20.0, user='u1', item='itemA'))
    reporter.on_playback_event(_ev(req_a, 'PROGRESS', 45.0, user='u1', item='itemA'))
    reporter.on_playback_event(_ev(req_b, 'PROGRESS', 80.0, user='u2', item='itemB'))
    reporter.on_playback_event(_ev(req_b, 'PROGRESS', 95.0, user='u2', item='itemB'))

    # Drain recovers unqueued coalesced progress with latest positions for BOTH accounts!
    reporter.drain_once(flush_pending=False)
    prog_calls = [(iid, ticks // TICKS_PER_SECOND) for path, iid, ticks in calls if path == '/Sessions/Playing/Progress']
    assert ('itemA', 45) in prog_calls
    assert ('itemB', 95) in prog_calls
    assert not reporter._coalesced_progress
    assert not reporter._queued_progress_markers
    assert reporter._queue.unfinished_tasks == 0

    # Subsequent PROGRESS after recovery continues working normally
    calls.clear()
    reporter.on_playback_event(_ev(req_a, 'PROGRESS', 60.0, user='u1', item='itemA'))
    reporter.drain_once(flush_pending=False)
    assert calls == [('/Sessions/Playing/Progress', 'itemA', 60 * TICKS_PER_SECOND)]

    # Terminal seal prevents any late progress
    reporter.on_playback_event(_ev(req_a, 'TERMINAL', 65.0, user='u1', item='itemA'))
    assert reporter.on_playback_event(_ev(req_a, 'PROGRESS', 99.0, user='u1', item='itemA')) is False
    reporter.drain_once(flush_pending=False)
    assert calls[-1] == ('/Sessions/Playing/Stopped', 'itemA', 65 * TICKS_PER_SECOND)
    assert reporter.close() is True
    assert reporter._queue.unfinished_tasks == 0
    hub.close()


def test_u04_pb07_conflict_variants_backward_seek_lost_ack_and_readd_isolation(tmp_path):
    """A03-01..03, PB-07: Offline 900s vs external 200/0/Played; live & offline backward seek 900->600; lost ACK effect_observed; delete+re-add isolation."""
    sid_a, gen_a1 = 'a' * 32, '1' * 64
    sid_b, gen_b1 = 'b' * 32, '2' * 64

    state = {
        (sid_a, 'u1', 'shared-item'): {'Played': False, 'PlaybackPositionTicks': 100 * TICKS_PER_SECOND},
        (sid_b, 'u2', 'shared-item'): {'Played': False, 'PlaybackPositionTicks': 500 * TICKS_PER_SECOND},
    }
    active_gens = {sid_a: gen_a1, sid_b: gen_b1}
    calls = []
    fail_stop = [False]

    def _loader(sid, gen):
        if active_gens.get(sid) != gen:
            raise PanError('PAN_ACCOUNT_CHANGED')
        uid = 'u1' if sid == sid_a else 'u2'

        class _C:
            session = SimpleNamespace(
                budget=lambda *_: nullcontext(),
                request=lambda path, **kw: _req(path, kw.get('data', {})),
            )

            def _item(self, iid):
                return {'UserData': deepcopy(state[(sid, uid, iid)])}

            def set_played(self, iid, val):
                state[(sid, uid, iid)]['Played'] = val

        def _req(path, body):
            calls.append((sid, path, body.get('PositionTicks')))
            if path.endswith('/Stopped') and fail_stop[0]:
                raise PanError('PAN_NETWORK_ERROR')
            if 'PositionTicks' in body:
                state[(sid, uid, body['ItemId'])]['PlaybackPositionTicks'] = body['PositionTicks']

        return _C(), {'server_id': 'srv1', 'user_id': uid}

    hub = EmbyInvalidationHub(tmp_path)
    reporter = EmbySessionReporter(tmp_path, hub, client_loader=_loader, start_worker=False)

    meta_a = {
        'provider': 'emby',
        'source_id': sid_a,
        'source_generation': gen_a1,
        'server_id': 'srv1',
        'user_id': 'u1',
        'item_id': 'shared-item',
        'media_source_id': 'ms1',
        'play_session_id': 'ps-a1',
    }

    # 1. Live backward seek (900s -> 600s) + offline Stop at 580s when server still holds our proven 600s baseline!
    req1 = '1' * 32
    reporter.on_playback_event({'event': 'AV_START', 'request_id': req1, 'position': 100.0, 'duration': 1800.0, 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    reporter.on_playback_event({'event': 'PROGRESS', 'request_id': req1, 'position': 900.0, 'duration': 1800.0, 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    assert state[(sid_a, 'u1', 'shared-item')]['PlaybackPositionTicks'] == 900 * TICKS_PER_SECOND
    # Backward seek to 600s in live session writes smaller 600s!
    reporter.on_playback_event({'event': 'PROGRESS', 'request_id': req1, 'position': 600.0, 'duration': 1800.0, 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    assert state[(sid_a, 'u1', 'shared-item')]['PlaybackPositionTicks'] == 600 * TICKS_PER_SECOND

    # Offline Stop at 550s over proven 600s baseline -> replays 550s when untouched!
    fail_stop[0] = True
    reporter.on_playback_event({'event': 'TERMINAL', 'request_id': req1, 'position': 550.0, 'duration': 1800.0, 'reason': 'STOP', 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    fail_stop[0] = False
    reporter._flush_pending_stops()
    assert state[(sid_a, 'u1', 'shared-item')]['PlaybackPositionTicks'] == 550 * TICKS_PER_SECOND
    # User B's identical item_id='shared-item' is untouched at 500s!
    assert state[(sid_b, 'u2', 'shared-item')]['PlaybackPositionTicks'] == 500 * TICKS_PER_SECOND

    # 2. Offline 900s Stop + second client saves 200s -> reconnect preserves 200s!
    req2 = '2' * 32
    reporter.on_playback_event({'event': 'AV_START', 'request_id': req2, 'position': 550.0, 'duration': 1800.0, 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    reporter.on_playback_event({'event': 'PROGRESS', 'request_id': req2, 'position': 890.0, 'duration': 1800.0, 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    fail_stop[0] = True
    reporter.on_playback_event({'event': 'TERMINAL', 'request_id': req2, 'position': 900.0, 'duration': 1800.0, 'reason': 'STOP', 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    state[(sid_a, 'u1', 'shared-item')]['PlaybackPositionTicks'] = 200 * TICKS_PER_SECOND
    fail_stop[0] = False
    reporter._flush_pending_stops()
    assert state[(sid_a, 'u1', 'shared-item')]['PlaybackPositionTicks'] == 200 * TICKS_PER_SECOND

    # 3. Account deleted and re-added (generation rotates) -> pending stop purged without touching server!
    req3 = '3' * 32
    reporter.on_playback_event({'event': 'AV_START', 'request_id': req3, 'position': 200.0, 'duration': 1800.0, 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    fail_stop[0] = True
    reporter.on_playback_event({'event': 'TERMINAL', 'request_id': req3, 'position': 777.0, 'duration': 1800.0, 'reason': 'STOP', 'observed_clock': True, 'data': {'_owned_source': meta_a}})
    reporter.drain_once(flush_pending=False)
    assert req3 in reporter._pending_stops
    active_gens[sid_a] = '9' * 64  # Re-added with new generation
    fail_stop[0] = False
    calls.clear()
    reporter._flush_pending_stops()
    assert req3 not in reporter._pending_stops
    assert calls == []
    assert state[(sid_a, 'u1', 'shared-item')]['PlaybackPositionTicks'] == 200 * TICKS_PER_SECOND
    reporter.close()
    hub.close()


def test_u04_pb10_real_host_close_retains_lease_on_undrained_worker_and_aborts_real_http_socket(tmp_path):
    """A03-04, A15-02, PB-10: Undrained slow worker prevents drained report & lease release, zero post-close HTTP; real Session aborts socket immediately."""
    # Part A: Slow non-abortable boundary (>3s) -> Host.close raises, retains lease, records UNKNOWN, zero post-close HTTP
    entered, release = Event(), Event()
    starts, reports, lease_releases = [], [], []
    sid, gen = 'a' * 32, 'b' * 64
    meta = {'provider': 'emby', 'source_id': sid, 'source_generation': gen, 'server_id': 's', 'user_id': 'u', 'item_id': 'i', 'media_source_id': 'm'}

    class _SlowBoundary:
        session = None

        def __init__(self):
            self.session = self

        def budget(self, *_a):
            return nullcontext()

        def request(self, path, **_kw):
            starts.append((path, time.monotonic()))
            if path == '/Sessions/Playing':
                entered.set()
                release.wait(5.0)
            return None

        def _item(self, _iid):
            starts.append(('GET_ITEM', time.monotonic()))
            return {'UserData': {}}

    hub = EmbyInvalidationHub(tmp_path)
    reporter = EmbySessionReporter(tmp_path, hub, client_loader=lambda *_: (_SlowBoundary(), {'server_id': 's', 'user_id': 'u'}))
    host = Host.__new__(Host)
    host.stopping, host.calls = Event(), Queue()
    host.lock, host.engine_lock = Lock(), Lock()
    for attr in ('pans', 'catalog', 'playback', 'images', 'preparation', 'streams', 'source_streams',
                 'engine', 'engine_worker', 'refresh_worker', 'diagnostic_worker'):
        setattr(host, attr, None)
    host.runtime = SimpleNamespace(
        close=lambda **_kw: None,
        lease=SimpleNamespace(close=lambda: lease_releases.append(time.monotonic())),
    )
    host.report = reports.append
    host.emby_sessions, host.emby_invalidation = reporter, hub
    host.unsubscribe = host.pan_unsubscribe = lambda: None

    try:
        reporter.on_playback_event({'event': 'AV_START', 'request_id': '1' * 32, 'position': 10.0, 'duration': 100.0, 'observed_clock': True, 'data': {'_owned_source': meta}})
        assert entered.wait(1.0)
        reporter.on_playback_event({'event': 'TERMINAL', 'request_id': '1' * 32, 'position': 20.0, 'duration': 100.0, 'reason': 'STOP', 'observed_clock': True, 'data': {'_owned_source': meta}})

        with pytest.raises(RuntimeError, match='EMBY_SESSIONS_DRAIN_PENDING'):
            host.close()
        close_returned_at = time.monotonic()
        assert reporter._worker.is_alive() is True
        assert 'SHUTDOWN_DRAINED_EMBY_SESSIONS' not in reports
        assert lease_releases == []
        # New events after close are rejected
        assert reporter.on_playback_event({'event': 'PROGRESS', 'request_id': '1' * 32, 'position': 30.0, 'duration': 100.0, 'observed_clock': True, 'data': {'_owned_source': meta}}) is False

        release.set()
        reporter._worker.join(1.0)
        assert not reporter._worker.is_alive()
        # Zero newly started HTTP requests after close()!
        assert [p for p, t in starts if t > close_returned_at] == []
        assert any(u['path'] == '/Sessions/Playing' and u['status'] == 'UNKNOWN' for u in reporter._unknown_requests)
        assert reporter._sessions['1' * 32]['started_sent'] is False

        # Second Host.close() drains cleanly and releases lease once
        host.close()
        assert 'SHUTDOWN_DRAINED_EMBY_SESSIONS' in reports
        assert len(lease_releases) == 1
        host.close()
        assert len(lease_releases) == 1
    finally:
        release.set()
        reporter._worker.join(1.0)
        hub.close()

    # Part B: Real ServerHttpSession socket blocked on slow TCP peer is aborted in <<1s by reporter.close()!
    srv_entered = Event()
    srv_stop = Event()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(2)
    port = listener.getsockname()[1]

    def _stall_server():
        try:
            conn, _ = listener.accept()
            srv_entered.set()
            srv_stop.wait(5.0)
            conn.close()
        except OSError:
            pass

    staller = Thread(target=_stall_server, daemon=True)
    staller.start()
    hub2 = EmbyInvalidationHub(tmp_path)
    real_client = SimpleNamespace(session=ServerHttpSession('emby', f'http://127.0.0.1:{port}', 'tok123'))
    reporter2 = EmbySessionReporter(tmp_path, hub2, client_loader=lambda *_: (real_client, {'server_id': 's', 'user_id': 'u'}))
    try:
        reporter2.on_playback_event({'event': 'AV_START', 'request_id': '2' * 32, 'position': 1.0, 'duration': 100.0, 'observed_clock': True, 'data': {'_owned_source': meta}})
        assert srv_entered.wait(1.5)
        t0 = time.monotonic()
        assert reporter2.close(timeout=2.0) is True
        assert (time.monotonic() - t0) < 1.0
        assert not reporter2._worker.is_alive()
    finally:
        srv_stop.set()
        listener.close()
        hub2.close()


# ==============================================================================
# U05: CT-WEBSOCKET (A04-01..02, PB-08)
# ==============================================================================

def test_u05_pb08_ws_handshake_verification_fragmentation_masked_pong_and_protocol_rejections(tmp_path):
    """A04-01, A04-02, PB-08: Handshake digest check, multi-frame UTF-8 + interleaved Ping->masked Pong, Close/oversized/bad-opcode cleanup."""
    # 1. Handshake validator unit checks
    key = base64.b64encode(b'0123456789abcdef').decode('ascii') if False else 'dGhlIHNhbXBsZSBub25jZQ=='
    valid_reply = SimpleNamespace(
        status=101,
        headers={
            'Upgrade': 'websocket',
            'Connection': 'keep-alive, Upgrade',
            'Sec-WebSocket-Accept': ws_accept_digest(key),
        },
    )
    assert verify_ws_handshake(valid_reply, key) is True
    assert verify_ws_handshake(SimpleNamespace(status=200, headers=valid_reply.headers), key) is False
    assert verify_ws_handshake(SimpleNamespace(status=101, headers={'Upgrade': 'h2c', 'Connection': 'Upgrade', 'Sec-WebSocket-Accept': ws_accept_digest(key)}), key) is False
    assert verify_ws_handshake(SimpleNamespace(status=101, headers={'Upgrade': 'websocket', 'Connection': 'close', 'Sec-WebSocket-Accept': ws_accept_digest(key)}), key) is False
    assert verify_ws_handshake(SimpleNamespace(status=101, headers={'Upgrade': 'websocket', 'Connection': 'Upgrade', 'Sec-WebSocket-Accept': 'wrongaccept=='}), key) is False

    # 2. Frame stream: multi-frame UTF-8 (split mid-Chinese char) + interleaved Ping + Close + protocol errors
    msg_obj = {'MessageType': 'UserDataChanged', 'Data': {'UserId': 'u1', 'Title': '剧集测试', 'UserDataList': [{'ItemId': 'ep9'}]}}
    raw_utf8 = json.dumps(msg_obj, ensure_ascii=False).encode('utf-8')
    # Split right inside a 3-byte UTF-8 Chinese character!
    zh_idx = raw_utf8.index('剧'.encode('utf-8')) + 1
    part1, part2, part3 = raw_utf8[:zh_idx], raw_utf8[zh_idx:zh_idx + 4], raw_utf8[zh_idx + 4:]

    stream = _WSFrameStream()
    ev1 = stream.feed(_make_server_frame(0x1, part1, fin=False))
    assert ev1 == []
    # Interleaved server Ping during fragmentation!
    ev_ping = stream.feed(_make_server_frame(0x9, b'ping-payload', fin=True))
    assert ev_ping == [('pong', b'ping-payload')]
    ev2 = stream.feed(_make_server_frame(0x0, part2, fin=False))
    assert ev2 == []
    ev3 = stream.feed(_make_server_frame(0x0, part3, fin=True))
    assert ev3 == [('text', raw_utf8.decode('utf-8'))]

    # Verify client Pong frame is strictly client-masked with exact payload
    pong_wire = build_ws_client_frame(0xA, b'ping-payload')
    fin, op, masked, unmasked, rest = _parse_client_frame(pong_wire)
    assert (fin, op, masked, unmasked, rest) == (True, 0xA, True, b'ping-payload', b'')

    # Reject binary opcode (0x2), unexpected continuation (0x0), >32 fragments, and oversized frames
    with pytest.raises(_WSProtocolError) as e_bin:
        _WSFrameStream().feed(_make_server_frame(0x2, b'bin'))
    assert e_bin.value.close_code == 1003

    with pytest.raises(_WSProtocolError):
        _WSFrameStream().feed(_make_server_frame(0x0, b'orphan'))

    s_many = _WSFrameStream()
    s_many.feed(_make_server_frame(0x1, b'a', fin=False))
    with pytest.raises(_WSProtocolError) as e_frag:
        for _ in range(33):
            s_many.feed(_make_server_frame(0x0, b'b', fin=False))
    assert e_frag.value.close_code == 1009

    # 3. Live loopback end-to-end WS server: bad accept fallback -> valid fragmented WS + Ping/Pong + Close -> clean socket release
    server_mode = ['bad_accept']
    client_frames_received = []
    ws_ready = Event()
    pong_received = Event()
    close_received = Event()

    class _WSHandler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_a):
            pass

        def do_GET(self):
            if self.path.startswith('/embywebsocket'):
                sec_key = self.headers.get('Sec-WebSocket-Key', '')
                self.send_response(101, 'Switching Protocols')
                self.send_header('Upgrade', 'websocket')
                self.send_header('Connection', 'Upgrade')
                accept = 'bad-digest' if server_mode[0] == 'bad_accept' else ws_accept_digest(sec_key)
                self.send_header('Sec-WebSocket-Accept', accept)
                self.end_headers()
                self.wfile.flush()
                if server_mode[0] == 'bad_accept':
                    return
                ws_ready.set()
                # Send fragmented UserDataChanged with interleaved Ping, then read Pong, then send Close(1000)
                self.connection.sendall(
                    _make_server_frame(0x1, part1, fin=False)
                    + _make_server_frame(0x9, b'emby-hb', fin=True)
                    + _make_server_frame(0x0, part2, fin=False)
                    + _make_server_frame(0x0, part3, fin=True)
                )
                self.connection.settimeout(2.0)
                wire = self.connection.recv(256)
                if wire:
                    fin_c, op_c, masked_c, body_c, _ = _parse_client_frame(wire)
                    client_frames_received.append((fin_c, op_c, masked_c, body_c))
                    if op_c == 0xA and masked_c and body_c == b'emby-hb':
                        pong_received.set()
                self.connection.sendall(_make_server_frame(0x8, struct.pack('!H', 1000), fin=True))
                try:
                    wire2 = self.connection.recv(256)
                    if wire2:
                        fin2, op2, masked2, body2, _ = _parse_client_frame(wire2)
                        client_frames_received.append((fin2, op2, masked2, body2))
                        if op2 == 0x8 and masked2:
                            close_received.set()
                except OSError:
                    pass
                return
            if self.path == '/System/Info/Public':
                raw = b'{"Id":"srv1"}'
            elif self.path == '/Users/u1':
                raw = b'{"Id":"u1"}'
            else:
                raw = b'{"Items":[],"TotalRecordCount":0}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), _WSHandler)
    httpd_thread = Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    httpd_thread.start()

    reg = Registry(tmp_path / 'libraries.sqlite3')
    src = Source(
        'a' * 32,
        'Emby WS',
        'media_server',
        f'http://127.0.0.1:{httpd.server_port}',
        password='tok-ws',
        metadata={'schema': 1, 'provider': 'emby', 'server_id': 'srv1', 'user_id': 'u1'},
    )
    reg.save(src)
    rev = reg.source_snapshot(src.id)[1]
    reg.close()

    clock = [100.0]
    hub = EmbyInvalidationHub(tmp_path, clock=lambda: clock[0])
    try:
        # Phase 1: Bad Sec-WebSocket-Accept is rejected and falls back to bounded 25s poll!
        hub.ensure_ws_listener(src.id, rev, force=True)
        time.sleep(0.2)
        snap_bad = hub.snapshot(src.id, rev)
        assert snap_bad['ws_connected'] is False
        polled = hub.poll_server_digest(src.id, rev)
        assert polled['last_confirmed_at'] == 100.0

        # Phase 2: Valid handshake + fragmented text + interleaved Ping->masked Pong + server Close->masked Close!
        server_mode[0] = 'ok'
        clock[0] = 130.0
        hub.ensure_ws_listener(src.id, rev, force=True)
        assert ws_ready.wait(2.0)
        assert pong_received.wait(2.0)
        assert close_received.wait(2.0)

        # Wait for worker cleanup after server Close
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not hub._ws_workers:
                break
            time.sleep(0.02)
        assert not hub._ws_workers
        snap_after = hub.snapshot(src.id, rev)
        assert snap_after['ws_connected'] is False
        assert 'ep9' in hub._entry(src.id, rev)['changed_items']
        assert hub.close() is True
    finally:
        hub.close()
        httpd.shutdown()
        httpd.server_close()
        httpd_thread.join(2.0)

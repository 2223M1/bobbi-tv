"""Bounded non-blocking Emby playback session reporter, invalidation hub, and next-episode resolver.

Implements R08, R09, R10, R15, and REV-09:
- Reserves request/epoch before PlaybackInfo; never sends /Sessions/Playing on handoff.
- Serializes Playing -> coalesced Progress (10s + Pause/Unpause + Seek) -> sealed Stopped per PlaySessionId.
- Reports actual observed player clock PositionTicks (never blindly echoing StartOffset).
- Halts credential generation on HTTP 401 (AUTH_REQUIRED); reconciles offline pending Stopped
  by re-reading server UserData first so external unwatched/newer progress is never overwritten.
- Maintains independent per-(source_id, generation) directory invalidation revisions via optional
  WebSocket hints + bounded foreground poll (<=5s on event, <=30s fallback without WS).
"""
from __future__ import annotations

import base64
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Full, Queue
import re
import select
import socket
import struct
from threading import Event, Lock, Thread
import time
from urllib.parse import urlencode, urlsplit

from bobbi_core.bounded_http import AttemptHandle, open_connection
from bobbi_core.library_contract import LibraryError
from bobbi_core.server_ref import identifier
from .libraries import Registry
from .owned_playback import emby_source_scope, register_next_resolver
from .pan_accounts import PanError
from .server_emby import Client, static_original_url

TICKS_PER_SECOND = 10_000_000
PENDING_STOP_TTL_SECONDS = 600.0
ALLOWED_EVENT_NAMES = frozenset({'TimeUpdate', 'Pause', 'Unpause'})


def seconds_to_ticks(seconds: float | int) -> int:
    if type(seconds) not in (int, float) or seconds <= 0:
        return 0
    return max(0, int(round(float(seconds) * TICKS_PER_SECOND)))


def ticks_to_seconds(ticks: int | None) -> float:
    if type(ticks) is not int or ticks <= 0:
        return 0.0
    return ticks / TICKS_PER_SECOND


def _scope_key(meta: dict) -> tuple[str, str, str, str]:
    return (
        str(meta.get('source_id', '')),
        str(meta.get('source_generation', '')),
        str(meta.get('server_id', '')),
        str(meta.get('user_id', '')),
    )


def _load_emby_client(root: Path, source_id: str, generation: str, *, session_factory=None) -> tuple[Client, dict]:
    reg_path = Path(root) / 'libraries.sqlite3'
    store = Registry(reg_path, read_only=True, timeout=0.1)
    try:
        src, rev = store.source_snapshot(source_id)
    except LibraryError as exc:
        raise PanError('PAN_ACCOUNT_CHANGED') from exc
    finally:
        store.close()
    if (
        rev != generation
        or src.kind != 'media_server'
        or src.metadata.get('provider') != 'emby'
        or not src.password
    ):
        raise PanError('PAN_ACCOUNT_CHANGED')
    saved = {
        'provider': 'emby',
        'location': src.location,
        'token': src.password,
        'server_id': src.metadata['server_id'],
        'user_id': src.metadata['user_id'],
    }
    session = session_factory(saved) if session_factory is not None else None
    return Client('emby', saved, session=session), saved


class EmbyInvalidationHub:
    """Per-(source_id, generation) directory invalidation tracker with optional WS + bounded poll."""

    WS_REFRESH_BUDGET_SECONDS = 5.0
    POLL_INTERVAL_SECONDS = 25.0
    POLL_READ_BUDGET_SECONDS = 5.0

    def __init__(self, root: Path, *, clock=time.monotonic):
        self.root = Path(root)
        self.clock = clock
        self._lock = Lock()
        self._states: OrderedDict[tuple[str, str], dict] = OrderedDict()
        self._stop = Event()
        self._ws_workers: dict[tuple[str, str], tuple[Event, Thread]] = {}

    def _entry(self, source_id: str, generation: str) -> dict:
        key = (source_id, generation)
        st = self._states.get(key)
        if st is None:
            st = {
                'revision': 1,
                'last_event_at': None,
                'last_confirmed_at': None,
                'sync_state': 'idle',
                'auth_state': 'OK',
                'changed_items': OrderedDict(),
                'ws_connected': False,
            }
            self._states[key] = st
            while len(self._states) > 16:
                old_key, _ = self._states.popitem(last=False)
                wk = self._ws_workers.pop(old_key, None)
                if wk is not None:
                    wk[0].set()
        else:
            self._states.move_to_end(key)
        return st

    def mark_auth_state(self, source_id: str, generation: str, state: str) -> int:
        with self._lock:
            st = self._entry(source_id, generation)
            st['auth_state'] = state
            st['sync_state'] = 'auth_required' if state == 'AUTH_REQUIRED' else st['sync_state']
            st['revision'] += 1
            if state == 'AUTH_REQUIRED':
                wk = self._ws_workers.pop((source_id, generation), None)
                if wk is not None:
                    wk[0].set()
            return st['revision']

    def auth_state(self, source_id: str, generation: str) -> str:
        with self._lock:
            st = self._states.get((source_id, generation))
            return st['auth_state'] if st else 'OK'

    def notify_event(self, source_id: str, generation: str, *, item_ids=(), kind: str = 'UserDataChanged') -> int:
        now = self.clock()
        with self._lock:
            st = self._entry(source_id, generation)
            st['revision'] += 1
            st['last_event_at'] = now
            st['sync_state'] = 'dirty'
            for iid in item_ids[:32]:
                if isinstance(iid, str) and iid:
                    st['changed_items'][iid] = (kind, now)
                    st['changed_items'].move_to_end(iid)
                    while len(st['changed_items']) > 128:
                        st['changed_items'].popitem(last=False)
            return st['revision']

    def mark_confirmed(self, source_id: str, generation: str, *, offline: bool = False) -> dict:
        now = self.clock()
        with self._lock:
            st = self._entry(source_id, generation)
            if offline:
                st['sync_state'] = 'offline'
            else:
                st['last_confirmed_at'] = now
                st['sync_state'] = 'synced'
            return {
                'revision': st['revision'],
                'sync_state': st['sync_state'],
                'auth_state': st['auth_state'],
                'ws_connected': st['ws_connected'],
                'last_event_at': st['last_event_at'],
                'last_confirmed_at': st['last_confirmed_at'],
                'poll_interval_seconds': self.POLL_INTERVAL_SECONDS,
                'refresh_target_seconds': (
                    self.WS_REFRESH_BUDGET_SECONDS if st['ws_connected']
                    else self.POLL_INTERVAL_SECONDS + self.POLL_READ_BUDGET_SECONDS
                ),
            }

    def snapshot(self, source_id: str, generation: str) -> dict:
        with self._lock:
            st = self._entry(source_id, generation)
            return {
                'revision': st['revision'],
                'sync_state': st['sync_state'],
                'auth_state': st['auth_state'],
                'ws_connected': st['ws_connected'],
                'last_event_at': st['last_event_at'],
                'last_confirmed_at': st['last_confirmed_at'],
                'poll_interval_seconds': self.POLL_INTERVAL_SECONDS,
                'refresh_target_seconds': (
                    self.WS_REFRESH_BUDGET_SECONDS if st['ws_connected']
                    else self.POLL_INTERVAL_SECONDS + self.POLL_READ_BUDGET_SECONDS
                ),
            }

    def poll_server_digest(self, source_id: str, generation: str, *, client_loader=None, force: bool = False) -> dict:
        """Bounded fallback server UserData/recent digest poll when WebSocket is unavailable (<=30s)."""
        now = self.clock()
        with self._lock:
            st = self._entry(source_id, generation)
            if st['auth_state'] == 'AUTH_REQUIRED':
                return self.snapshot(source_id, generation)
            if not force and st['ws_connected']:
                return self.snapshot(source_id, generation)
            last_poll = st.get('last_poll_at')
            if not force and last_poll is not None and (now - last_poll) < self.POLL_INTERVAL_SECONDS:
                return self.snapshot(source_id, generation)
            st['last_poll_at'] = now
        loader = client_loader or (lambda sid, gen: _load_emby_client(self.root, sid, gen))
        try:
            client, _ = loader(source_id, generation)
            with client.session.budget(self.POLL_READ_BUDGET_SECONDS):
                client._identity(user_scoped_read=True)
                resume_rows, _ = client.page_rows('view:resume', 1, 10, display=True)
                recent_rows, _ = client.page_rows('view:recent', 1, 10, display=True)
        except PanError as exc:
            code = str(exc)
            if code == 'PAN_SERVER_UNAUTHORIZED':
                self.mark_auth_state(source_id, generation, 'AUTH_REQUIRED')
            elif code == 'PAN_SERVER_FORBIDDEN':
                self.mark_auth_state(source_id, generation, 'FORBIDDEN')
            else:
                self.mark_confirmed(source_id, generation, offline=True)
            return self.snapshot(source_id, generation)
        digest_payload = []
        for tag_kind, rows in (('resume', resume_rows), ('recent', recent_rows)):
            for r in rows[:10]:
                ud = r.get('UserData') if isinstance(r.get('UserData'), dict) else {}
                digest_payload.append((
                    tag_kind,
                    str(r.get('Id', '')),
                    str(r.get('Name', '')),
                    bool(ud.get('Played', False)),
                    int(ud.get('PlaybackPositionTicks') or 0),
                    bool(ud.get('IsFavorite', False)),
                ))
        digest = hashlib.sha256(json.dumps(digest_payload, separators=(',', ':')).encode('utf-8')).hexdigest()
        with self._lock:
            st = self._entry(source_id, generation)
            prev_digest = st.get('last_poll_digest')
            st['last_poll_digest'] = digest
            st['last_confirmed_at'] = now
            if prev_digest is not None and prev_digest != digest:
                st['revision'] += 1
                st['last_event_at'] = now
                st['sync_state'] = 'dirty'
            elif st['sync_state'] == 'offline':
                st['sync_state'] = 'synced'
        return self.snapshot(source_id, generation)

    def ingest_ws_message(self, source_id: str, generation: str, expected_user_id: str, raw_text: str) -> bool:
        """Validate and process one Emby WebSocket JSON frame as an invalidation hint only."""
        try:
            msg = json.loads(raw_text)
        except (ValueError, TypeError):
            return False
        if not isinstance(msg, dict):
            return False
        mtype = msg.get('MessageType')
        data = msg.get('Data')
        if mtype == 'UserDataChanged' and isinstance(data, dict):
            if data.get('UserId') and data.get('UserId') != expected_user_id:
                return False
            entries = data.get('UserDataList') if isinstance(data.get('UserDataList'), list) else []
            iids = [str(r.get('ItemId')) for r in entries[:32] if isinstance(r, dict) and r.get('ItemId')]
            self.notify_event(source_id, generation, item_ids=iids, kind='UserDataChanged')
            return True
        if mtype in ('LibraryChanged', 'SeriesTimerCreated', 'RefreshProgress'):
            iids = []
            if isinstance(data, dict):
                for field in ('ItemsAdded', 'ItemsUpdated', 'ItemsRemoved'):
                    vals = data.get(field)
                    if isinstance(vals, list):
                        iids.extend(str(v) for v in vals[:16] if isinstance(v, (str, int)))
            self.notify_event(source_id, generation, item_ids=iids, kind=str(mtype))
            return True
        return False

    def ensure_ws_listener(self, source_id: str, generation: str, *, connect_fn=None) -> None:
        key = (source_id, generation)
        with self._lock:
            if self._stop.is_set():
                return
            st = self._entry(source_id, generation)
            if st['auth_state'] == 'AUTH_REQUIRED':
                return
            existing = self._ws_workers.get(key)
            if existing is not None and existing[1].is_alive():
                return
            stop_ev = Event()
            worker = Thread(
                target=self._ws_loop,
                args=(source_id, generation, stop_ev, connect_fn),
                name=f'bobbi-emby-ws-{source_id[:8]}',
                daemon=True,
            )
            self._ws_workers[key] = (stop_ev, worker)
            worker.start()

    def _ws_loop(self, source_id: str, generation: str, stop_ev: Event, connect_fn=None) -> None:
        key = (source_id, generation)
        try:
            _, saved = _load_emby_client(self.root, source_id, generation)
        except PanError:
            return
        u = urlsplit(saved['location'])
        ws_scheme = 'wss' if u.scheme == 'https' else 'ws'
        base_path = u.path.rstrip('/')
        ws_target = f'{base_path}/embywebsocket?{urlencode({"deviceId": "bobbitv-" + source_id[:16]})}'
        ws_url = f'{u.scheme}://{u.netloc}{ws_target}'
        ws_key = base64.b64encode(os.urandom(16)).decode('ascii')
        headers = {
            'Host': u.netloc,
            'Upgrade': 'websocket',
            'Connection': 'Upgrade',
            'Sec-WebSocket-Version': '13',
            'Sec-WebSocket-Key': ws_key,
            'X-Emby-Token': saved['token'],
            'User-Agent': 'Bobbi-MediaServer/1',
        }
        try:
            with AttemptHandle(
                deadline=time.monotonic() + 5.0,
                cancelled=lambda: stop_ev.is_set() or self._stop.is_set(),
            ) as attempt:
                if connect_fn is not None:
                    conn, target = connect_fn(ws_url, attempt)
                else:
                    conn, target = open_connection(ws_url, attempt, connect_cap=4.0)
                conn.request('GET', target, headers=headers)
                reply = conn.getresponse()
                if reply.status == 401:
                    conn.close()
                    self.mark_auth_state(source_id, generation, 'AUTH_REQUIRED')
                    return
                if reply.status != 101:
                    conn.close()
                    return
                raw_sock = getattr(conn.sock, '_raw', conn.sock)
                with self._lock:
                    self._entry(source_id, generation)['ws_connected'] = True
                # On reconnect, immediately mark dirty once so missed offline deltas are reconciled (R10-04).
                self.notify_event(source_id, generation, kind='WSReconnected')
                buf = bytearray()
                while not stop_ev.is_set() and not self._stop.is_set():
                    if self.auth_state(source_id, generation) == 'AUTH_REQUIRED':
                        break
                    rlist, _, _ = select.select([raw_sock], [], [raw_sock], 0.25)
                    if not rlist:
                        continue
                    try:
                        chunk = raw_sock.recv(4096)
                    except (BlockingIOError, OSError):
                        break
                    if not chunk:
                        break
                    buf.extend(chunk)
                    while len(buf) >= 2:
                        b0, b1 = buf[0], buf[1]
                        opcode = b0 & 0x0F
                        masked = (b1 & 0x80) != 0
                        plen = b1 & 0x7F
                        idx = 2
                        if plen == 126:
                            if len(buf) < 4:
                                break
                            plen = struct.unpack('!H', buf[2:4])[0]
                            idx = 4
                        elif plen == 127:
                            if len(buf) < 10:
                                break
                            plen = struct.unpack('!Q', buf[2:10])[0]
                            idx = 10
                        if plen > 262144:
                            return
                        mask_len = 4 if masked else 0
                        if len(buf) < idx + mask_len + plen:
                            break
                        mask = buf[idx:idx + 4] if masked else b''
                        payload = bytes(buf[idx + mask_len:idx + mask_len + plen])
                        del buf[:idx + mask_len + plen]
                        if masked:
                            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
                        if opcode == 0x8:
                            return
                        if opcode == 0x1:
                            self.ingest_ws_message(
                                source_id,
                                generation,
                                saved['user_id'],
                                payload.decode('utf-8', errors='replace'),
                            )
                conn.close()
        except Exception:
            pass
        finally:
            with self._lock:
                st = self._states.get(key)
                if st is not None:
                    st['ws_connected'] = False
            _ = ws_scheme

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            workers = list(self._ws_workers.values())
            self._ws_workers.clear()
        for ev, wk in workers:
            ev.set()
            wk.join(1.0)


class EmbySessionReporter:
    """Bounded non-blocking playback state reporter for Emby sessions."""

    def __init__(
        self,
        root: Path,
        invalidation: EmbyInvalidationHub,
        *,
        client_loader=None,
        clock=time.monotonic,
        start_worker: bool = True,
    ):
        self.root = Path(root)
        self.invalidation = invalidation
        self.client_loader = client_loader or (lambda sid, gen: _load_emby_client(self.root, sid, gen))
        self.clock = clock
        self._lock = Lock()
        self._queue: Queue = Queue(maxsize=64)
        self._coalesced_progress: dict[str, dict] = {}
        self._sessions: OrderedDict[str, dict] = OrderedDict()
        self._pending_stops: OrderedDict[str, dict] = OrderedDict()
        self._auth_halted_scopes: set[tuple[str, str, str, str]] = set()
        self._done = Event()
        self._worker: Thread | None = None
        if start_worker:
            self._worker = Thread(target=self._run, name='bobbi-emby-session', daemon=True)
            self._worker.start()

    def on_playback_event(self, payload: dict) -> bool:
        """Non-blocking callback invoked from resident playback owner."""
        if not isinstance(payload, dict) or self._done.is_set():
            return False
        data = payload.get('data')
        meta = data.get('_owned_source') if isinstance(data, dict) else None
        if not isinstance(meta, dict) or meta.get('provider') != 'emby':
            return False
        req_id = payload.get('request_id')
        if not isinstance(req_id, str) or not req_id:
            return False
        event_kind = payload.get('event')
        if event_kind not in ('AV_START', 'PROGRESS', 'TERMINAL'):
            return False
        skey = _scope_key(meta)
        with self._lock:
            if skey in self._auth_halted_scopes:
                return False
            sess = self._sessions.get(req_id)
            if sess is not None and sess.get('sealed'):
                # Progress after Stopped/Terminal is strictly sealed out (REV-09 #4).
                return False
            snap = {
                'event': event_kind,
                'request_id': req_id,
                'meta': deepcopy(meta),
                'position': float(payload.get('position') or 0.0),
                'duration': float(payload.get('duration') or 0.0),
                'paused': bool(payload.get('paused', False)),
                'trigger': str(payload.get('trigger') or 'TimeUpdate'),
                'reason': str(payload.get('reason') or ''),
                'observed_clock': bool(payload.get('observed_clock', True)),
                'queued_at': self.clock(),
            }
            if event_kind == 'TERMINAL':
                if sess is not None:
                    sess['sealed'] = True
                else:
                    # Never started AV -> do NOT send Stopped or Playing on pre-AV cancel (R09-01)!
                    return False
                self._coalesced_progress.pop(req_id, None)
            elif event_kind == 'AV_START':
                if sess is None:
                    self._sessions[req_id] = {
                        'meta': deepcopy(meta),
                        'started_sent': False,
                        'stopped_acked': False,
                        'sealed': False,
                        'last_ticks': 0,
                        'seq': 0,
                    }
                    while len(self._sessions) > 32:
                        self._sessions.popitem(last=False)
            elif event_kind == 'PROGRESS':
                if sess is None:
                    return False
                if req_id in self._coalesced_progress:
                    self._coalesced_progress[req_id] = snap
                    return True
                self._coalesced_progress[req_id] = snap

            try:
                self._queue.put_nowait(snap)
                return True
            except Full:
                if event_kind == 'PROGRESS':
                    self._coalesced_progress[req_id] = snap
                    return True
                # Evict one non-terminal item so AV_START / TERMINAL is never dropped.
                try:
                    dropped = self._queue.get_nowait()
                    if dropped.get('event') == 'TERMINAL':
                        self._queue.put_nowait(dropped)
                        return False
                    self._queue.put_nowait(snap)
                    return True
                except Empty:
                    return False

    def drain_once(self, *, flush_pending: bool = True) -> int:
        """Process all currently queued events synchronously (for deterministic tests and drain)."""
        processed = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            try:
                self._process_event(item)
                processed += 1
            finally:
                self._queue.task_done()
        if flush_pending:
            self._flush_pending_stops()
        return processed

    def _run(self) -> None:
        next_retry = self.clock() + 5.0
        while not self._done.is_set() or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.15)
            except Empty:
                if self.clock() >= next_retry and not self._done.is_set():
                    self._flush_pending_stops()
                    next_retry = self.clock() + 5.0
                continue
            try:
                self._process_event(item)
                if not self._done.is_set():
                    self._flush_pending_stops()
            finally:
                self._queue.task_done()

    def _process_event(self, item: dict) -> None:
        req_id = item['request_id']
        event_kind = item['event']
        if event_kind == 'PROGRESS':
            with self._lock:
                latest = self._coalesced_progress.pop(req_id, None)
                if latest is not None:
                    item = latest
        meta = item['meta']
        skey = _scope_key(meta)
        with self._lock:
            if skey in self._auth_halted_scopes:
                return
            sess = self._sessions.get(req_id)
            if sess is None:
                return
            if event_kind == 'PROGRESS' and sess.get('sealed'):
                return
            if event_kind == 'AV_START' and sess.get('started_sent'):
                return
            if event_kind == 'TERMINAL' and sess.get('stopped_acked'):
                return
            needs_playing_first = not sess.get('started_sent')

        pos_ticks = seconds_to_ticks(item['position']) if item['observed_clock'] else 0
        sess['seq'] += 1
        body = {
            'ItemId': meta['item_id'],
            'MediaSourceId': meta['media_source_id'],
            'PositionTicks': pos_ticks,
            'IsPaused': bool(item['paused']),
            'CanSeek': True,
            'PlayMethod': 'DirectPlay',
        }
        if meta.get('play_session_id'):
            body['PlaySessionId'] = meta['play_session_id']
        stop_body = {
            'ItemId': meta['item_id'],
            'MediaSourceId': meta['media_source_id'],
            'PositionTicks': pos_ticks,
            'Failed': item['reason'] == 'ERROR',
        }
        if meta.get('play_session_id'):
            stop_body['PlaySessionId'] = meta['play_session_id']

        try:
            client, _ = self.client_loader(meta['source_id'], meta['source_generation'])
        except PanError:
            return

        try:
            with client.session.budget(6):
                if needs_playing_first:
                    client.session.request(
                        '/Sessions/Playing',
                        data=body,
                        method='POST',
                        success_statuses=(200, 204),
                        empty_response=True,
                    )
                    with self._lock:
                        sess['started_sent'] = True
                        sess['last_ticks'] = pos_ticks
                if event_kind == 'AV_START':
                    pass
                elif event_kind == 'PROGRESS':
                    ev_name = item['trigger'] if item['trigger'] in ALLOWED_EVENT_NAMES else 'TimeUpdate'
                    body['EventName'] = ev_name
                    client.session.request(
                        '/Sessions/Playing/Progress',
                        data=body,
                        method='POST',
                        success_statuses=(200, 204),
                        empty_response=True,
                    )
                    with self._lock:
                        sess['last_ticks'] = pos_ticks
                elif event_kind == 'TERMINAL':
                    self._send_stop_with_readback(client, req_id, sess, meta, stop_body, item['reason'])
        except PanError as exc:
            code = str(exc)
            if code == 'PAN_SERVER_UNAUTHORIZED':
                with self._lock:
                    self._auth_halted_scopes.add(skey)
                    for k in [k for k, v in self._pending_stops.items() if _scope_key(v['meta']) == skey]:
                        self._pending_stops.pop(k, None)
                self.invalidation.mark_auth_state(meta['source_id'], meta['source_generation'], 'AUTH_REQUIRED')
            elif code == 'PAN_SERVER_FORBIDDEN':
                self.invalidation.mark_auth_state(meta['source_id'], meta['source_generation'], 'FORBIDDEN')
            elif event_kind == 'TERMINAL' and code in ('PAN_NETWORK_ERROR', 'PAN_BUDGET_EXHAUSTED', 'PAN_RATE_LIMITED'):
                self._queue_pending_stop(req_id, meta, stop_body, item['reason'], sess.get('baseline_userdata'))
                self.invalidation.mark_confirmed(meta['source_id'], meta['source_generation'], offline=True)

    def _send_stop_with_readback(self, client: Client, req_id: str, sess: dict, meta: dict, stop_body: dict, reason: str) -> None:
        client.session.request(
            '/Sessions/Playing/Stopped',
            data=stop_body,
            method='POST',
            success_statuses=(200, 204),
            empty_response=True,
        )
        # Bounded readback verification (R09-03, R09-04): never re-triggers playback.
        try:
            fresh = client._item(meta['item_id'])
            udata = fresh.get('UserData') if isinstance(fresh, dict) else None
            if reason == 'NATURAL_EOF' and isinstance(udata, dict) and udata.get('Played') is not True:
                client.set_played(meta['item_id'], True)
        except PanError:
            pass
        with self._lock:
            sess['stopped_acked'] = True
            self._pending_stops.pop(req_id, None)
        self.invalidation.notify_event(
            meta['source_id'],
            meta['source_generation'],
            item_ids=[meta['item_id']],
            kind='LocalPlaybackStopped',
        )

    def _queue_pending_stop(self, req_id: str, meta: dict, stop_body: dict, reason: str, baseline_userdata) -> None:
        now = self.clock()
        with self._lock:
            if req_id in self._pending_stops:
                return
            self._pending_stops[req_id] = {
                'meta': deepcopy(meta),
                'stop_body': deepcopy(stop_body),
                'reason': reason,
                'expires_at': now + PENDING_STOP_TTL_SECONDS,
                'attempts': 1,
                'last_ticks': stop_body['PositionTicks'],
                'baseline_userdata': deepcopy(baseline_userdata),
            }
            while len(self._pending_stops) > 16:
                self._pending_stops.popitem(last=False)

    def _flush_pending_stops(self) -> None:
        now = self.clock()
        with self._lock:
            items = list(self._pending_stops.items())
        for req_id, entry in items:
            meta = entry['meta']
            skey = _scope_key(meta)
            if now >= entry['expires_at'] or entry['attempts'] >= 5:
                with self._lock:
                    self._pending_stops.pop(req_id, None)
                continue
            with self._lock:
                if skey in self._auth_halted_scopes:
                    self._pending_stops.pop(req_id, None)
                    continue
            try:
                client, _ = self.client_loader(meta['source_id'], meta['source_generation'])
            except PanError:
                # Scope/account changed or removed -> never carry pending stop to new account (R09-06)!
                with self._lock:
                    self._pending_stops.pop(req_id, None)
                continue
            try:
                with client.session.budget(6):
                    # Check server UserData FIRST before replaying an uncertain/offline Stopped (REV-09 #4, #10):
                    fresh = client._item(meta['item_id'])
                    udata = fresh.get('UserData') if isinstance(fresh.get('UserData'), dict) else {}
                    srv_ticks = udata.get('PlaybackPositionTicks') or 0
                    srv_played = udata.get('Played')
                    with self._lock:
                        sess = self._sessions.get(req_id) or {'started_sent': True, 'stopped_acked': False}
                    try:
                        init_ticks = int(meta.get('initial_ticks') or '0')
                    except ValueError:
                        init_ticks = 0
                    # 1. Lost ACK check: if the server already recorded our Stopped state, never re-POST!
                    if entry['reason'] == 'NATURAL_EOF' and srv_played is True:
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                            sess['stopped_acked'] = True
                        self.invalidation.mark_confirmed(meta['source_id'], meta['source_generation'], offline=False)
                        continue
                    if (
                        entry['reason'] != 'NATURAL_EOF'
                        and entry['last_ticks'] > 0
                        and entry['last_ticks'] != init_ticks
                        and type(srv_ticks) is int
                        and abs(srv_ticks - entry['last_ticks']) <= 2 * TICKS_PER_SECOND
                    ):
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                            sess['stopped_acked'] = True
                        self.invalidation.mark_confirmed(meta['source_id'], meta['source_generation'], offline=False)
                        continue
                    # 2. Cross-client offline conflict check (R09-05):
                    had_prior_server_progress = sess.get('last_ticks', 0) > 0 or init_ticks > 0
                    if had_prior_server_progress and srv_played is False and srv_ticks == 0:
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                            sess['stopped_acked'] = True
                        self.invalidation.notify_event(
                            meta['source_id'],
                            meta['source_generation'],
                            item_ids=[meta['item_id']],
                            kind='OfflineConflictDiscarded',
                        )
                        continue
                    if srv_played is True or (type(srv_ticks) is int and srv_ticks > entry['last_ticks']):
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                            sess['stopped_acked'] = True
                        continue
                    entry['attempts'] += 1
                    if not sess.get('started_sent'):
                        client.session.request(
                            '/Sessions/Playing',
                            data=dict(entry['stop_body'], IsPaused=False, CanSeek=True, PlayMethod='DirectPlay'),
                            method='POST',
                            success_statuses=(200, 204),
                            empty_response=True,
                        )
                        with self._lock:
                            sess['started_sent'] = True
                    self._send_stop_with_readback(client, req_id, sess, meta, entry['stop_body'], entry['reason'])
                    self.invalidation.mark_confirmed(meta['source_id'], meta['source_generation'], offline=False)
            except PanError as exc:
                if str(exc) == 'PAN_SERVER_UNAUTHORIZED':
                    with self._lock:
                        self._auth_halted_scopes.add(skey)
                        self._pending_stops.pop(req_id, None)
                    self.invalidation.mark_auth_state(meta['source_id'], meta['source_generation'], 'AUTH_REQUIRED')

    def close(self) -> None:
        self._done.set()
        if self._worker is not None:
            self._worker.join(3.0)


def resolve_next_episode_data(current: dict, spec: dict, cancelled) -> dict | None:
    """Resolve the immediate next episode in the SAME season for Emby NATURAL_EOF continuation."""
    if cancelled():
        return None
    meta = current.get('_owned_source') or {}
    root_str = spec.get('profile_root')
    season_id = spec.get('season_id')
    season_num = spec.get('season')
    episode_num = spec.get('episode')
    source_id = meta.get('source_id')
    generation = meta.get('source_generation')
    if (
        not root_str
        or not source_id
        or not generation
        or not season_id
        or type(season_num) is not int
        or type(episode_num) is not int
    ):
        return None
    try:
        client, saved = _load_emby_client(Path(root_str), source_id, generation)
        with client.session.budget(8):
            client._identity(user_scoped_read=True)
            candidate = None
            for page_idx in range(1, 11):
                if cancelled():
                    return None
                rows, total = client.page_rows('folder:' + identifier(season_id), page_idx, 20, display=True)
                candidate = next(
                    (
                        r
                        for r in rows
                        if r.get('Type') == 'Episode'
                        and r.get('ParentIndexNumber') == season_num
                        and r.get('IndexNumber') == episode_num + 1
                    ),
                    None,
                )
                if candidate is not None or page_idx * 20 >= total:
                    break
            if candidate is None or cancelled():
                return None
            next_id = identifier(candidate.get('Id'))
            detail = client._item(next_id)
            versions = detail.get('MediaSources')
            if not isinstance(versions, list) or len(versions) != 1:
                # Ambiguous multi-version episode requires explicit user pick; do not guess.
                return None
            mid = identifier(versions[0].get('Id'))
            options = '|redirect-limit=0'
            try:
                opened = client.open_playback_session(next_id, mid, authenticated=False)
            except PanError as err:
                if str(err) != 'PAN_EMBY_DIRECT_AUTH_REQUIRED' or versions[0].get('Protocol') != 'File':
                    return None
                opened = client.open_playback_session(next_id, mid, authenticated=True)
                if opened['url'] != static_original_url(saved['location'], next_id, mid):
                    return None
                from urllib.parse import quote
                options += '&!X-Emby-Token=' + quote(saved['token'], safe='')
    except (PanError, ValueError, OSError):
        return None

    if cancelled():
        return None
    title = str(detail.get('Name') or f'Episode {episode_num + 1}')[:512]
    series_name = str(detail.get('SeriesName') or '')[:512]
    ticks = detail.get('RunTimeTicks')
    duration = (ticks // TICKS_PER_SECOND) if type(ticks) is int and ticks > 0 else 0
    scope = emby_source_scope(
        source_id=source_id,
        generation=generation,
        server_id=saved['server_id'],
        user_id=saved['user_id'],
    )
    return {
        '_account': scope,
        'url': opened['url'] + options,
        'title': title,
        'source_title': title,
        'mime': opened['mime'],
        'file_evidence': 'AUTO_VERIFIED_FILE',
        '_bobbi_start_over': True,
        '_resume_offset_seconds': 0,
        'video_info': {
            'title': title,
            'mediatype': 'episode',
            'tvshowtitle': series_name,
            'season': season_num,
            'episode': episode_num + 1,
            'plot': str(detail.get('Overview') or '')[:4096],
            **({'duration': duration} if duration > 0 else {}),
        },
        'tv_data': {'season': season_num, 'episode': episode_num + 1},
        '_owned_source': {
            'provider': 'emby',
            'server_id': saved['server_id'],
            'user_id': saved['user_id'],
            'source_id': source_id,
            'source_generation': generation,
            'item_id': next_id,
            'media_source_id': mid,
            'play_session_id': opened.get('play_session_id', ''),
        },
        '_owned_next': {
            'resolver': 'emby_same_season',
            'profile_root': root_str,
            'season_id': season_id,
            'season': season_num,
            'episode': episode_num + 1,
        },
    }


register_next_resolver('emby_same_season', resolve_next_episode_data)

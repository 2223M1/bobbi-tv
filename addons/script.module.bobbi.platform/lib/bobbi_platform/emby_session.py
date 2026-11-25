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
import ssl
import struct
from threading import Event, Lock, Thread, current_thread
import time
from urllib.parse import urlencode, urlsplit

from bobbi_core.bounded_http import AttemptHandle, open_connection
from bobbi_core.library_contract import LibraryError
from bobbi_core.next_episode_summary import NextResolution
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


class _ShutdownAbort(Exception):
    """Internal marker raised when reporter shutdown begins before or during HTTP."""


def _load_emby_client(root: Path, source_id: str, generation: str, *, session_factory=None) -> tuple[Client, dict]:
    reg_path = Path(root) / 'libraries.sqlite3'
    store = None
    try:
        store = Registry(reg_path, read_only=True, timeout=0.1)
        src, rev = store.source_snapshot(source_id)
    except LibraryError as exc:
        if str(exc) == 'STORAGE_UNAVAILABLE':
            raise PanError('PAN_STORAGE_UNAVAILABLE') from exc
        raise PanError('PAN_ACCOUNT_CHANGED') from exc
    finally:
        if store is not None:
            try:
                store.close()
            except LibraryError as exc:
                if str(exc) == 'STORAGE_UNAVAILABLE':
                    raise PanError('PAN_STORAGE_UNAVAILABLE') from exc
                raise PanError('PAN_ACCOUNT_CHANGED') from exc
            except OSError as exc:
                raise PanError('PAN_STORAGE_UNAVAILABLE') from exc
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


WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
WS_MAX_CONTROL_BYTES = 125
WS_MAX_FRAME_BYTES = 65536
WS_MAX_MESSAGE_BYTES = 262144
WS_MAX_FRAGMENTS = 32


def ws_accept_digest(ws_key: str) -> str:
    digest = hashlib.sha1((ws_key + WS_GUID).encode('ascii')).digest()
    return base64.b64encode(digest).decode('ascii')


def _header_value(reply, name: str) -> str:
    hdrs = getattr(reply, 'headers', None)
    if hdrs is not None and hasattr(hdrs, 'get_all'):
        vals = hdrs.get_all(name)
        if vals:
            return ', '.join(str(v) for v in vals)
    if hdrs is not None and hasattr(hdrs, 'get'):
        for k in (name, name.lower(), name.title()):
            val = hdrs.get(k)
            if val is not None:
                return str(val)
        if hasattr(hdrs, 'items'):
            matched = [str(v) for k, v in hdrs.items() if str(k).lower() == name.lower()]
            if matched:
                return ', '.join(matched)
    getter = getattr(reply, 'getheader', None)
    if callable(getter):
        val = getter(name)
        if val is not None:
            return str(val)
    return ''


def verify_ws_handshake(reply, ws_key: str) -> bool:
    """Validate RFC 6455 client opening handshake HTTP 101 + Upgrade + Connection + Sec-WebSocket-Accept."""
    if getattr(reply, 'status', None) != 101:
        return False
    upgrade_tokens = [t.strip().lower() for t in _header_value(reply, 'Upgrade').split(',') if t.strip()]
    if 'websocket' not in upgrade_tokens:
        return False
    conn_tokens = [t.strip().lower() for t in _header_value(reply, 'Connection').split(',') if t.strip()]
    if 'upgrade' not in conn_tokens:
        return False
    accept_raw = _header_value(reply, 'Sec-WebSocket-Accept')
    accept_parts = [p.strip() for p in accept_raw.split(',') if p.strip()]
    if len(accept_parts) != 1 or accept_parts[0] != ws_accept_digest(ws_key):
        return False
    return True


def build_ws_client_frame(opcode: int, payload: bytes = b'', *, mask_key: bytes | None = None) -> bytes:
    """Construct a mandatory client-masked RFC 6455 frame."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError('WS payload must be bytes')
    plen = len(payload)
    if (opcode & 0x08) and plen > WS_MAX_CONTROL_BYTES:
        raise ValueError('WS control frame payload exceeds 125 bytes')
    if plen > WS_MAX_FRAME_BYTES:
        raise ValueError('WS client frame payload exceeds limit')
    b0 = 0x80 | (opcode & 0x0F)
    mkey = bytes(mask_key) if (isinstance(mask_key, (bytes, bytearray)) and len(mask_key) == 4) else os.urandom(4)
    if plen < 126:
        header = bytes([b0, 0x80 | plen])
    else:
        header = bytes([b0, 0x80 | 126]) + struct.pack('!H', plen)
    masked = bytes(b ^ mkey[i & 3] for i, b in enumerate(payload))
    return header + mkey + masked


def _is_valid_close_code(code: int) -> bool:
    if 1000 <= code <= 1014:
        return code not in (1004, 1005, 1006)
    return 3000 <= code <= 4999


class _WSProtocolError(Exception):
    def __init__(self, close_code: int = 1002, reason: str = ''):
        super().__init__(reason)
        self.close_code = close_code


class _WSFrameStream:
    """Bounded RFC 6455 client frame & multi-frame UTF-8 text message decoder."""

    def __init__(self):
        self.buf = bytearray()
        self.frag_buf: bytearray | None = None
        self.frag_count: int = 0

    def feed(self, chunk: bytes) -> list[tuple[str, bytes | str]]:
        """Return ordered actions: ('text', str), ('pong', bytes), ('close', bytes)."""
        if chunk:
            self.buf.extend(chunk)
            if len(self.buf) > WS_MAX_FRAME_BYTES + 16:
                # Guard against a single unparsed oversized header+body accumulation
                b1 = self.buf[1] if len(self.buf) >= 2 else 0
                plen_hint = b1 & 0x7F
                if plen_hint in (126, 127) and len(self.buf) > WS_MAX_FRAME_BYTES + 14:
                    raise _WSProtocolError(1009, 'frame_buffer_exceeded')
        events: list[tuple[str, bytes | str]] = []
        while len(self.buf) >= 2:
            b0, b1 = self.buf[0], self.buf[1]
            fin = (b0 & 0x80) != 0
            rsv = b0 & 0x70
            if rsv != 0:
                raise _WSProtocolError(1002, 'nonzero_rsv')
            opcode = b0 & 0x0F
            masked = (b1 & 0x80) != 0
            plen = b1 & 0x7F
            idx = 2
            if plen == 126:
                if len(self.buf) < 4:
                    break
                plen = struct.unpack('!H', self.buf[2:4])[0]
                if plen < 126:
                    raise _WSProtocolError(1002, 'nonminimal_length_16')
                idx = 4
            elif plen == 127:
                if len(self.buf) < 10:
                    break
                if (self.buf[2] & 0x80) != 0:
                    raise _WSProtocolError(1002, 'negative_length_64')
                plen = struct.unpack('!Q', self.buf[2:10])[0]
                if plen < 65536:
                    raise _WSProtocolError(1002, 'nonminimal_length_64')
                idx = 10

            is_control = (opcode & 0x08) != 0
            if is_control:
                if opcode not in (0x8, 0x9, 0xA) or not fin or plen > WS_MAX_CONTROL_BYTES:
                    raise _WSProtocolError(1002, 'invalid_control_frame')
            else:
                if opcode == 0x2:
                    raise _WSProtocolError(1003, 'binary_unsupported')
                if opcode not in (0x0, 0x1):
                    raise _WSProtocolError(1002, 'invalid_data_opcode')
                if plen > WS_MAX_FRAME_BYTES:
                    raise _WSProtocolError(1009, 'frame_too_large')

            mask_len = 4 if masked else 0
            total_frame_len = idx + mask_len + plen
            if len(self.buf) < total_frame_len:
                break

            mask = bytes(self.buf[idx:idx + 4]) if masked else b''
            payload = bytes(self.buf[idx + mask_len:total_frame_len])
            del self.buf[:total_frame_len]
            if masked:
                payload = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))

            if opcode == 0x9:
                events.append(('pong', payload))
                continue
            if opcode == 0xA:
                events.append(('pong_ack', payload))
                continue
            if opcode == 0x8:
                if len(payload) == 1:
                    raise _WSProtocolError(1002, 'invalid_close_payload')
                if len(payload) >= 2:
                    code = struct.unpack('!H', payload[:2])[0]
                    if not _is_valid_close_code(code):
                        raise _WSProtocolError(1002, 'invalid_close_code')
                    try:
                        payload[2:].decode('utf-8')
                    except UnicodeDecodeError as exc:
                        raise _WSProtocolError(1007, 'invalid_close_utf8') from exc
                    events.append(('close', struct.pack('!H', code)))
                else:
                    events.append(('close', struct.pack('!H', 1000)))
                return events

            if opcode == 0x1:
                if self.frag_buf is not None:
                    raise _WSProtocolError(1002, 'interleaved_data_frame')
                if fin:
                    try:
                        text = payload.decode('utf-8')
                    except UnicodeDecodeError as exc:
                        raise _WSProtocolError(1007, 'invalid_utf8') from exc
                    events.append(('text', text))
                else:
                    if len(payload) > WS_MAX_MESSAGE_BYTES:
                        raise _WSProtocolError(1009, 'message_too_large')
                    self.frag_buf = bytearray(payload)
                    self.frag_count = 1
            elif opcode == 0x0:
                if self.frag_buf is None:
                    raise _WSProtocolError(1002, 'unexpected_continuation')
                self.frag_count += 1
                if self.frag_count > WS_MAX_FRAGMENTS or (len(self.frag_buf) + len(payload)) > WS_MAX_MESSAGE_BYTES:
                    raise _WSProtocolError(1009, 'fragmented_message_too_large')
                self.frag_buf.extend(payload)
                if fin:
                    raw_msg = bytes(self.frag_buf)
                    self.frag_buf = None
                    self.frag_count = 0
                    try:
                        text = raw_msg.decode('utf-8')
                    except UnicodeDecodeError as exc:
                        raise _WSProtocolError(1007, 'invalid_utf8') from exc
                    events.append(('text', text))
        return events


def _ws_send_frame(raw_sock, frame: bytes, stop_ev: Event, global_stop: Event) -> bool:
    deadline = time.monotonic() + 1.5
    view = memoryview(frame)
    sent = 0
    try:
        while sent < len(view):
            if stop_ev.is_set() or global_stop.is_set():
                break
            rem = deadline - time.monotonic()
            if rem <= 0:
                return False
            try:
                n = raw_sock.send(view[sent:])
            except (BlockingIOError, ssl.SSLWantWriteError):
                select.select([], [raw_sock], [raw_sock], min(0.05, rem))
                continue
            except ssl.SSLWantReadError:
                select.select([raw_sock], [], [raw_sock], min(0.05, rem))
                continue
            except OSError:
                return False
            if n <= 0:
                return False
            sent += n
        return True
    finally:
        view.release()


def _close_ws_resources(holder: dict) -> None:
    attempt = holder.get('attempt')
    if attempt is not None and hasattr(attempt, 'abort'):
        try:
            attempt.abort()
        except Exception:
            pass
    reply = holder.get('reply')
    if reply is not None:
        try:
            reply.close()
        except Exception:
            pass
    conn = holder.get('conn')
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    sock = holder.get('sock')
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


class EmbyInvalidationHub:
    """Per-(source_id, generation) directory invalidation tracker with optional WS + bounded poll."""

    WS_REFRESH_BUDGET_SECONDS = 5.0
    POLL_INTERVAL_SECONDS = 25.0
    POLL_READ_BUDGET_SECONDS = 5.0
    WS_IDLE_PING_SECONDS = 60.0
    WS_IDLE_PONG_TIMEOUT_SECONDS = 15.0

    def __init__(self, root: Path, *, clock=time.monotonic):
        self.root = Path(root)
        self.clock = clock
        self._lock = Lock()
        self._states: OrderedDict[tuple[str, str], dict] = OrderedDict()
        self._stop = Event()
        self._ws_workers: dict[tuple[str, str], tuple[Event, Thread, dict]] = {}

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
                'ws_failures': 0,
                'next_ws_at': 0.0,
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
        wk_to_stop = None
        with self._lock:
            st = self._entry(source_id, generation)
            st['auth_state'] = state
            st['sync_state'] = 'auth_required' if state == 'AUTH_REQUIRED' else st['sync_state']
            st['revision'] += 1
            if state == 'AUTH_REQUIRED':
                wk_to_stop = self._ws_workers.pop((source_id, generation), None)
                if wk_to_stop is not None:
                    wk_to_stop[0].set()
            rev = st['revision']
        if wk_to_stop is not None:
            _close_ws_resources(wk_to_stop[2])
        return rev

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
            return self._snapshot_locked(st)

    def _snapshot_locked(self, st: dict) -> dict:
        """Project a captured state while the caller owns self._lock; no lock or IO."""
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
            return self._snapshot_locked(self._entry(source_id, generation))

    def poll_server_digest(self, source_id: str, generation: str, *, client_loader=None, force: bool = False) -> dict:
        """Bounded fallback server UserData/recent digest poll when WebSocket is unavailable (<=30s)."""
        now = self.clock()
        with self._lock:
            st = self._entry(source_id, generation)
            if self._stop.is_set() or st['auth_state'] == 'AUTH_REQUIRED':
                return self._snapshot_locked(st)
            if not force and st['ws_connected']:
                return self._snapshot_locked(st)
            last_poll = st.get('last_poll_at')
            if not force and last_poll is not None and (now - last_poll) < self.POLL_INTERVAL_SECONDS:
                return self._snapshot_locked(st)
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
            return self._snapshot_locked(st)

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

    def ensure_ws_listener(self, source_id: str, generation: str, *, connect_fn=None, force: bool = False) -> None:
        key = (source_id, generation)
        now = self.clock()
        with self._lock:
            if self._stop.is_set():
                return
            st = self._entry(source_id, generation)
            if st['auth_state'] == 'AUTH_REQUIRED':
                return
            existing = self._ws_workers.get(key)
            if existing is not None:
                if existing[1].is_alive():
                    return
                self._ws_workers.pop(key, None)
            if not force and connect_fn is None and now < st.get('next_ws_at', 0.0):
                return
            stop_ev = Event()
            holder: dict = {'attempt': None, 'conn': None, 'reply': None, 'sock': None}
            worker = Thread(
                target=self._ws_loop,
                args=(source_id, generation, stop_ev, holder, connect_fn),
                name=f'bobbi-emby-ws-{source_id[:8]}',
                daemon=True,
            )
            entry = (stop_ev, worker, holder)
            self._ws_workers[key] = entry
            worker.start()

    def _ws_loop(
        self,
        source_id: str,
        generation: str,
        stop_ev: Event,
        holder: dict,
        connect_fn=None,
    ) -> None:
        key = (source_id, generation)
        upgraded = False
        try:
            _, saved = _load_emby_client(self.root, source_id, generation)
        except PanError as exc:
            if str(exc) == 'PAN_SERVER_UNAUTHORIZED':
                self.mark_auth_state(source_id, generation, 'AUTH_REQUIRED')
            with self._lock:
                st = self._states.get(key)
                if st is not None:
                    fails = int(st.get('ws_failures', 0)) + 1
                    st['ws_failures'] = fails
                    st['next_ws_at'] = self.clock() + min(25.0, float(2 ** min(fails - 1, 4)))
                cur = self._ws_workers.get(key)
                if cur is not None and cur[0] is stop_ev:
                    self._ws_workers.pop(key, None)
            return

        u = urlsplit(saved['location'])
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
                holder['attempt'] = attempt
                if connect_fn is not None:
                    conn, target = connect_fn(ws_url, attempt)
                else:
                    conn, target = open_connection(ws_url, attempt, connect_cap=4.0)
                holder['conn'] = conn
                conn.request('GET', target, headers=headers)
                reply = conn.getresponse()
                holder['reply'] = reply
                if reply.status == 401:
                    self.mark_auth_state(source_id, generation, 'AUTH_REQUIRED')
                    return
                if not verify_ws_handshake(reply, ws_key):
                    return
                raw_sock = getattr(conn.sock, '_raw', conn.sock)
                holder['sock'] = raw_sock
                raw_sock.setblocking(False)
                attempt.finish()
            # Handshake succeeded; detach 5s connect attempt while keeping socket in holder for close().
            holder['attempt'] = None
            upgraded = True

            stream = _WSFrameStream()
            # Drain any post-101 bytes buffered inside HTTPResponse.fp BufferedReader before raw recv!
            fp = getattr(holder.get('reply'), 'fp', None)
            raw_io = getattr(fp, 'raw', None) if fp is not None else None
            if fp is not None and raw_io is not None and hasattr(fp, 'read'):
                try:
                    raw_io.readinto = lambda _b: 0
                    initial_bytes = fp.read(WS_MAX_FRAME_BYTES) or b''
                except Exception:
                    initial_bytes = b''
            else:
                initial_bytes = b''

            with self._lock:
                st = self._entry(source_id, generation)
                st['ws_connected'] = True
                st['ws_failures'] = 0
                st['next_ws_at'] = 0.0
            # On reconnect, immediately mark dirty once so missed offline deltas are reconciled (R10-04).
            self.notify_event(source_id, generation, kind='WSReconnected')

            last_rx_at = self.clock()
            ping_sent_at: float | None = None

            def _handle_events(ev_list) -> bool:
                nonlocal last_rx_at, ping_sent_at
                for kind, data in ev_list:
                    last_rx_at = self.clock()
                    ping_sent_at = None
                    if kind == 'pong':
                        pong_frame = build_ws_client_frame(0xA, data)  # type: ignore[arg-type]
                        if not _ws_send_frame(raw_sock, pong_frame, stop_ev, self._stop):
                            return False
                    elif kind == 'pong_ack':
                        continue
                    elif kind == 'close':
                        close_frame = build_ws_client_frame(0x8, data)  # type: ignore[arg-type]
                        _ws_send_frame(raw_sock, close_frame, stop_ev, self._stop)
                        return False
                    elif kind == 'text':
                        self.ingest_ws_message(
                            source_id,
                            generation,
                            saved['user_id'],
                            data,  # type: ignore[arg-type]
                        )
                return True

            if initial_bytes:
                if not _handle_events(stream.feed(initial_bytes)):
                    return

            while not stop_ev.is_set() and not self._stop.is_set():
                if self.auth_state(source_id, generation) == 'AUTH_REQUIRED':
                    break
                rlist, _, xlist = select.select([raw_sock], [], [raw_sock], 0.2)
                if stop_ev.is_set() or self._stop.is_set():
                    break
                if xlist:
                    break
                if not rlist:
                    now_c = self.clock()
                    if ping_sent_at is not None:
                        if (now_c - ping_sent_at) >= self.WS_IDLE_PONG_TIMEOUT_SECONDS:
                            break
                    elif (now_c - last_rx_at) >= self.WS_IDLE_PING_SECONDS:
                        ping_frame = build_ws_client_frame(0x9, b'hb')
                        if not _ws_send_frame(raw_sock, ping_frame, stop_ev, self._stop):
                            break
                        ping_sent_at = now_c
                    continue
                try:
                    chunk = raw_sock.recv(8192)
                except (BlockingIOError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                if not _handle_events(stream.feed(chunk)):
                    break
        except _WSProtocolError as proto_err:
            raw_sock = holder.get('sock')
            if raw_sock is not None:
                try:
                    close_frame = build_ws_client_frame(0x8, struct.pack('!H', proto_err.close_code))
                    _ws_send_frame(raw_sock, close_frame, stop_ev, self._stop)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            _close_ws_resources(holder)
            with self._lock:
                st = self._states.get(key)
                if st is not None:
                    st['ws_connected'] = False
                    if not stop_ev.is_set() and not self._stop.is_set():
                        if upgraded:
                            st['next_ws_at'] = self.clock() + 1.0
                        else:
                            fails = int(st.get('ws_failures', 0)) + 1
                            st['ws_failures'] = fails
                            st['next_ws_at'] = self.clock() + min(25.0, float(2 ** min(fails - 1, 4)))
                cur = self._ws_workers.get(key)
                if cur is not None and cur[0] is stop_ev:
                    self._ws_workers.pop(key, None)

    def close(self) -> bool:
        self._stop.set()
        with self._lock:
            workers = list(self._ws_workers.items())
        for _key, entry in workers:
            entry[0].set()
            _close_ws_resources(entry[2])
        drained = True
        for key, entry in workers:
            wk = entry[1]
            if wk is not current_thread():
                wk.join(1.0)
            if wk.is_alive():
                drained = False
            else:
                with self._lock:
                    if self._ws_workers.get(key) is entry:
                        self._ws_workers.pop(key, None)
        return drained


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
        self._coalesced_progress: OrderedDict[str, dict] = OrderedDict()
        self._queued_progress_markers: set[str] = set()
        self._storage_retries: OrderedDict[str, dict] = OrderedDict()
        self._sessions: OrderedDict[str, dict] = OrderedDict()
        self._pending_stops: OrderedDict[str, dict] = OrderedDict()
        self._auth_halted_scopes: set[tuple[str, str, str, str]] = set()
        self._inflight: list[tuple[object, str, str]] = []
        self._unknown_requests: list[dict] = []
        self._worker_errors: int = 0
        self._done = Event()
        self._worker: Thread | None = None
        if start_worker:
            self._worker = Thread(target=self._run, name='bobbi-emby-session', daemon=True)
            self._worker.start()

    @staticmethod
    def _initial_baseline_from_meta(meta: dict) -> dict | None:
        raw_ticks = meta.get('initial_ticks')
        raw_played = meta.get('initial_played')
        if raw_ticks is None or raw_played is None:
            return None
        try:
            ticks = int(raw_ticks)
        except (TypeError, ValueError):
            return None
        if ticks < 0:
            return None
        if str(raw_played) in ('1', 'true', 'True'):
            played = True
        elif str(raw_played) in ('0', 'false', 'False'):
            played = False
        else:
            return None
        return {'PlaybackPositionTicks': ticks, 'Played': played}

    def _evict_one_non_terminal_locked(self) -> bool:
        """Evict one non-terminal item (preferring PROGRESS marker) with exact task_done accounting."""
        count = self._queue.qsize()
        if count <= 0:
            return False
        pulled = []
        for _ in range(count):
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            self._queue.task_done()
            pulled.append(item)
        if not pulled:
            return False
        drop_idx = next((i for i, x in enumerate(pulled) if x.get('event') == 'PROGRESS'), None)
        if drop_idx is None:
            drop_idx = next((i for i, x in enumerate(pulled) if x.get('event') != 'TERMINAL'), None)
        if drop_idx is None:
            for item in pulled:
                try:
                    self._queue.put_nowait(item)
                except Full:
                    break
            return False
        dropped = pulled.pop(drop_idx)
        if dropped.get('event') == 'PROGRESS':
            self._queued_progress_markers.discard(dropped.get('request_id', ''))
        for item in pulled:
            try:
                self._queue.put_nowait(item)
            except Full:
                if item.get('event') == 'PROGRESS':
                    self._queued_progress_markers.discard(item.get('request_id', ''))
                break
        return True

    def _schedule_unqueued_locked(self, *, now: float | None = None, allow_retries: bool = True) -> None:
        if self._done.is_set():
            return
        if allow_retries and self._storage_retries:
            cur_now = self.clock() if now is None else now
            for req_id in list(self._storage_retries.keys()):
                entry = self._storage_retries.get(req_id)
                if entry is None or cur_now < entry['due_at']:
                    continue
                sess = self._sessions.get(req_id)
                if sess is None or sess.get('sealed') or sess.get('started_sent'):
                    self._storage_retries.pop(req_id, None)
                    continue
                try:
                    self._queue.put_nowait(entry['item'])
                    self._storage_retries.pop(req_id, None)
                except Full:
                    break
        for req_id in list(self._coalesced_progress.keys()):
            if req_id in self._queued_progress_markers:
                continue
            sess = self._sessions.get(req_id)
            if sess is None or sess.get('sealed'):
                self._coalesced_progress.pop(req_id, None)
                continue
            try:
                self._queue.put_nowait({'event': 'PROGRESS', 'request_id': req_id})
                self._queued_progress_markers.add(req_id)
            except Full:
                break

    def _discard_queued_locked(self) -> None:
        self._coalesced_progress.clear()
        self._queued_progress_markers.clear()
        self._storage_retries.clear()
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                break
            self._queue.task_done()

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
            if self._done.is_set() or skey in self._auth_halted_scopes:
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
                self._storage_retries.pop(req_id, None)
            elif event_kind == 'AV_START':
                if sess is None:
                    init_base = self._initial_baseline_from_meta(meta)
                    self._sessions[req_id] = {
                        'meta': deepcopy(meta),
                        'scope': skey,
                        'started_sent': False,
                        'stopped_acked': False,
                        'reconciled': None,
                        'sealed': False,
                        'last_ticks': 0,
                        'baseline_userdata': init_base,
                        'initial_played': bool(init_base['Played']) if init_base is not None else False,
                        'seq': 0,
                    }
                    while len(self._sessions) > 32:
                        evicted_req, _ = self._sessions.popitem(last=False)
                        self._coalesced_progress.pop(evicted_req, None)
                        self._storage_retries.pop(evicted_req, None)
            elif event_kind == 'PROGRESS':
                if sess is None:
                    return False
                self._coalesced_progress[req_id] = snap
                self._coalesced_progress.move_to_end(req_id)
                while len(self._coalesced_progress) > 32:
                    old_req, _ = self._coalesced_progress.popitem(last=False)
                    if old_req == req_id:
                        break
                if req_id in self._queued_progress_markers:
                    return True
                try:
                    self._queue.put_nowait({'event': 'PROGRESS', 'request_id': req_id})
                    self._queued_progress_markers.add(req_id)
                except Full:
                    pass
                return True

            try:
                self._queue.put_nowait(snap)
                return True
            except Full:
                if not self._evict_one_non_terminal_locked():
                    return False
                try:
                    self._queue.put_nowait(snap)
                    return True
                except Full:
                    return False

    def drain_once(self, *, flush_pending: bool = True) -> int:
        """Process all currently queued events synchronously (for deterministic tests and drain)."""
        if self._done.is_set():
            return 0
        start_now = self.clock()
        with self._lock:
            self._schedule_unqueued_locked(now=start_now, allow_retries=True)
        processed = 0
        while not self._done.is_set():
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            try:
                self._process_event(item)
                processed += 1
            finally:
                self._queue.task_done()
                with self._lock:
                    self._schedule_unqueued_locked(now=start_now, allow_retries=False)
        if flush_pending and not self._done.is_set():
            self._flush_pending_stops()
        return processed

    def _run(self) -> None:
        next_retry = self.clock() + 5.0
        while not self._done.is_set():
            with self._lock:
                self._schedule_unqueued_locked(now=self.clock(), allow_retries=True)
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                if self._done.is_set():
                    break
                if self.clock() >= next_retry:
                    try:
                        self._flush_pending_stops()
                    except _ShutdownAbort:
                        break
                    except Exception:
                        self._worker_errors += 1
                    next_retry = self.clock() + 5.0
                continue
            try:
                if not self._done.is_set():
                    self._process_event(item)
                    if not self._done.is_set():
                        self._flush_pending_stops()
            except _ShutdownAbort:
                pass
            except Exception:
                self._worker_errors += 1
            finally:
                self._queue.task_done()
                if not self._done.is_set():
                    with self._lock:
                        self._schedule_unqueued_locked(now=self.clock(), allow_retries=True)
        with self._lock:
            self._discard_queued_locked()

    def _call_http(self, client, req_id: str, label: str, fn):
        token = (client, req_id, label)
        with self._lock:
            if self._done.is_set():
                raise _ShutdownAbort()
            self._inflight.append(token)
        try:
            res = fn()
        except BaseException:
            with self._lock:
                if token in self._inflight:
                    self._inflight.remove(token)
                if self._done.is_set():
                    self._record_unknown_locked(req_id, label)
                    raise _ShutdownAbort() from None
            raise
        with self._lock:
            if token in self._inflight:
                self._inflight.remove(token)
            if self._done.is_set():
                self._record_unknown_locked(req_id, label)
                raise _ShutdownAbort()
        return res

    def _record_unknown_locked(self, req_id: str, path: str) -> None:
        self._unknown_requests.append({
            'request_id': req_id,
            'path': path,
            'status': 'UNKNOWN',
            'at': self.clock(),
        })
        if len(self._unknown_requests) > 32:
            del self._unknown_requests[:-32]
        sess = self._sessions.get(req_id)
        if sess is not None:
            sess['shutdown_status'] = 'UNKNOWN'

    def _defer_storage_retry(self, item: dict) -> None:
        req_id = item['request_id']
        event_kind = item['event']
        now = self.clock()
        with self._lock:
            if self._done.is_set():
                return
            sess = self._sessions.get(req_id)
            if sess is None:
                return
            if event_kind == 'PROGRESS':
                if not sess.get('sealed') and req_id not in self._coalesced_progress:
                    self._coalesced_progress[req_id] = item
                return
            if event_kind == 'AV_START':
                if sess.get('sealed') or sess.get('started_sent'):
                    return
                attempts = int(item.get('storage_attempts') or 0) + 1
                if attempts > 8:
                    return
                retry_item = dict(item, storage_attempts=attempts)
                backoff = min(1.0, 0.05 * (2 ** (attempts - 1)))
                self._storage_retries[req_id] = {'item': retry_item, 'due_at': now + backoff}
                self._storage_retries.move_to_end(req_id)
                while len(self._storage_retries) > 32:
                    self._storage_retries.popitem(last=False)

    def _process_event(self, item: dict) -> None:
        if self._done.is_set():
            raise _ShutdownAbort()
        req_id = item['request_id']
        event_kind = item['event']
        if event_kind == 'PROGRESS':
            with self._lock:
                self._queued_progress_markers.discard(req_id)
                latest = self._coalesced_progress.pop(req_id, None)
                if latest is None:
                    return
                item = latest
        meta = item['meta']
        skey = _scope_key(meta)
        with self._lock:
            if self._done.is_set():
                raise _ShutdownAbort()
            if skey in self._auth_halted_scopes:
                return
            sess = self._sessions.get(req_id)
            if sess is None:
                return
            if event_kind == 'PROGRESS' and sess.get('sealed'):
                return
            if event_kind == 'AV_START' and sess.get('started_sent'):
                return
            if event_kind == 'TERMINAL' and (sess.get('stopped_acked') or sess.get('reconciled') is not None):
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
            client, saved = self.client_loader(meta['source_id'], meta['source_generation'])
            if isinstance(saved, dict) and (
                (saved.get('server_id') and saved['server_id'] != meta.get('server_id'))
                or (saved.get('user_id') and saved['user_id'] != meta.get('user_id'))
            ):
                raise PanError('PAN_ACCOUNT_CHANGED')
        except PanError as exc:
            code = str(exc)
            if code == 'PAN_STORAGE_UNAVAILABLE':
                if event_kind == 'TERMINAL':
                    self._queue_pending_stop(req_id, meta, stop_body, item['reason'], sess.get('baseline_userdata'))
                else:
                    self._defer_storage_retry(item)
                return
            if code == 'PAN_ACCOUNT_CHANGED':
                with self._lock:
                    self._sessions.pop(req_id, None)
                    self._coalesced_progress.pop(req_id, None)
                    self._storage_retries.pop(req_id, None)
                    self._pending_stops.pop(req_id, None)
            return

        try:
            with client.session.budget(6):
                if needs_playing_first:
                    self._call_http(
                        client,
                        req_id,
                        '/Sessions/Playing',
                        lambda: client.session.request(
                            '/Sessions/Playing',
                            data=body,
                            method='POST',
                            success_statuses=(200, 204),
                            empty_response=True,
                        ),
                    )
                    with self._lock:
                        sess['started_sent'] = True
                        sess['last_ticks'] = pos_ticks
                        sess['baseline_userdata'] = {
                            'PlaybackPositionTicks': pos_ticks,
                            'Played': bool(sess.get('initial_played', False)),
                        }
                if event_kind == 'AV_START':
                    pass
                elif event_kind == 'PROGRESS':
                    ev_name = item['trigger'] if item['trigger'] in ALLOWED_EVENT_NAMES else 'TimeUpdate'
                    body['EventName'] = ev_name
                    self._call_http(
                        client,
                        req_id,
                        '/Sessions/Playing/Progress',
                        lambda: client.session.request(
                            '/Sessions/Playing/Progress',
                            data=body,
                            method='POST',
                            success_statuses=(200, 204),
                            empty_response=True,
                        ),
                    )
                    with self._lock:
                        sess['last_ticks'] = pos_ticks
                        sess['baseline_userdata'] = {
                            'PlaybackPositionTicks': pos_ticks,
                            'Played': bool(sess.get('initial_played', False)),
                        }
                elif event_kind == 'TERMINAL':
                    self._send_stop_with_readback(client, req_id, sess, meta, stop_body, item['reason'])
        except _ShutdownAbort:
            raise
        except PanError as exc:
            if self._done.is_set():
                raise _ShutdownAbort() from None
            code = str(exc)
            if code == 'PAN_SERVER_UNAUTHORIZED':
                with self._lock:
                    self._auth_halted_scopes.add(skey)
                    for k in [k for k, v in self._pending_stops.items() if _scope_key(v['meta']) == skey]:
                        self._pending_stops.pop(k, None)
                self.invalidation.mark_auth_state(meta['source_id'], meta['source_generation'], 'AUTH_REQUIRED')
            elif code == 'PAN_SERVER_FORBIDDEN':
                self.invalidation.mark_auth_state(meta['source_id'], meta['source_generation'], 'FORBIDDEN')
            elif event_kind == 'TERMINAL' and code in (
                'PAN_NETWORK_ERROR',
                'PAN_BUDGET_EXHAUSTED',
                'PAN_RATE_LIMITED',
                'PAN_STORAGE_UNAVAILABLE',
            ):
                self._queue_pending_stop(req_id, meta, stop_body, item['reason'], sess.get('baseline_userdata'))
                self.invalidation.mark_confirmed(meta['source_id'], meta['source_generation'], offline=True)

    def _send_stop_with_readback(
        self,
        client: Client,
        req_id: str,
        sess: dict,
        meta: dict,
        stop_body: dict,
        reason: str,
    ) -> None:
        self._call_http(
            client,
            req_id,
            '/Sessions/Playing/Stopped',
            lambda: client.session.request(
                '/Sessions/Playing/Stopped',
                data=stop_body,
                method='POST',
                success_statuses=(200, 204),
                empty_response=True,
            ),
        )
        # Bounded readback verification (R09-03, R09-04): never re-triggers playback.
        try:
            fresh = self._call_http(
                client,
                req_id,
                f"/Users/{meta['user_id']}/Items/{meta['item_id']}",
                lambda: client._item(meta['item_id']),
            )
            udata = fresh.get('UserData') if isinstance(fresh, dict) else None
            if reason == 'NATURAL_EOF' and isinstance(udata, dict) and udata.get('Played') is not True:
                self._call_http(
                    client,
                    req_id,
                    f"/Users/{meta['user_id']}/PlayedItems/{meta['item_id']}",
                    lambda: client.set_played(meta['item_id'], True),
                )
        except _ShutdownAbort:
            raise
        except PanError:
            pass
        with self._lock:
            sess['stopped_acked'] = True
            sess['reconciled'] = 'acked'
            sess['baseline_userdata'] = {
                'PlaybackPositionTicks': 0 if reason == 'NATURAL_EOF' else stop_body['PositionTicks'],
                'Played': True if reason == 'NATURAL_EOF' else bool(sess.get('initial_played', False)),
            }
            self._pending_stops.pop(req_id, None)
        self.invalidation.notify_event(
            meta['source_id'],
            meta['source_generation'],
            item_ids=[meta['item_id']],
            kind='LocalPlaybackStopped',
        )

    def _queue_pending_stop(self, req_id: str, meta: dict, stop_body: dict, reason: str, baseline_userdata) -> None:
        if self._done.is_set():
            return
        now = self.clock()
        with self._lock:
            if self._done.is_set() or req_id in self._pending_stops:
                return
            self._pending_stops[req_id] = {
                'meta': deepcopy(meta),
                'scope': _scope_key(meta),
                'play_session_id': str(meta.get('play_session_id') or ''),
                'stop_body': deepcopy(stop_body),
                'reason': reason,
                'expires_at': now + PENDING_STOP_TTL_SECONDS,
                'attempts': 1,
                'storage_waits': 0,
                'last_ticks': stop_body['PositionTicks'],
                'baseline_userdata': deepcopy(baseline_userdata),
            }
            while len(self._pending_stops) > 16:
                self._pending_stops.popitem(last=False)

    def _flush_pending_stops(self) -> None:
        if self._done.is_set():
            return
        now = self.clock()
        with self._lock:
            items = list(self._pending_stops.items())
        for req_id, entry in items:
            if self._done.is_set():
                raise _ShutdownAbort()
            meta = entry['meta']
            skey = entry.get('scope') or _scope_key(meta)
            if now >= entry['expires_at'] or entry['attempts'] >= 5:
                with self._lock:
                    self._pending_stops.pop(req_id, None)
                continue
            with self._lock:
                if skey in self._auth_halted_scopes:
                    self._pending_stops.pop(req_id, None)
                    continue
            try:
                client, saved = self.client_loader(meta['source_id'], meta['source_generation'])
                if isinstance(saved, dict) and (
                    (saved.get('server_id') and saved['server_id'] != meta.get('server_id'))
                    or (saved.get('user_id') and saved['user_id'] != meta.get('user_id'))
                ):
                    raise PanError('PAN_ACCOUNT_CHANGED')
            except PanError as exc:
                if str(exc) == 'PAN_STORAGE_UNAVAILABLE':
                    entry['storage_waits'] = int(entry.get('storage_waits') or 0) + 1
                    if entry['storage_waits'] >= 16:
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                    continue
                # Scope/account changed or removed -> never carry pending stop to new account (R09-06)!
                with self._lock:
                    self._pending_stops.pop(req_id, None)
                continue
            try:
                with client.session.budget(6):
                    # Check server UserData FIRST before replaying an uncertain/offline Stopped (REV-09 #4, #10):
                    fresh = self._call_http(
                        client,
                        req_id,
                        f"/Users/{meta['user_id']}/Items/{meta['item_id']}",
                        lambda: client._item(meta['item_id']),
                    )
                    udata = fresh.get('UserData') if isinstance(fresh, dict) else None
                    if not isinstance(udata, dict):
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                        continue
                    srv_ticks = udata.get('PlaybackPositionTicks')
                    if srv_ticks is None:
                        srv_ticks = 0
                    srv_played = bool(udata.get('Played', False)) if udata.get('Played') is not None else False
                    with self._lock:
                        sess = self._sessions.get(req_id) or {
                            'started_sent': True,
                            'stopped_acked': False,
                            'reconciled': None,
                            'initial_played': False,
                        }
                    baseline = entry.get('baseline_userdata')

                    # 1. Effect already observed on server: reconcile as effect_observed without re-POSTing
                    #    or claiming a specific POST/PlaySessionId ACK.
                    if entry['reason'] == 'NATURAL_EOF' and srv_played is True:
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                            sess['reconciled'] = 'effect_observed'
                        self.invalidation.mark_confirmed(meta['source_id'], meta['source_generation'], offline=False)
                        continue
                    expected_played = baseline.get('Played') if isinstance(baseline, dict) else False
                    if (
                        entry['reason'] != 'NATURAL_EOF'
                        and type(srv_ticks) is int
                        and srv_played == expected_played
                        and abs(srv_ticks - entry['last_ticks']) <= 2 * TICKS_PER_SECOND
                        and (
                            not isinstance(baseline, dict)
                            or entry['last_ticks'] != baseline.get('PlaybackPositionTicks')
                        )
                    ):
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                            sess['reconciled'] = 'effect_observed'
                        self.invalidation.mark_confirmed(meta['source_id'], meta['source_generation'], offline=False)
                        continue

                    # 2. Proven baseline check (PB-07): never use max(position) or numeric ordering.
                    #    Only replay if server UserData still matches our session's proven last-confirmed baseline.
                    baseline_matches = (
                        isinstance(baseline, dict)
                        and type(baseline.get('PlaybackPositionTicks')) is int
                        and type(baseline.get('Played')) is bool
                        and srv_played == baseline['Played']
                        and type(srv_ticks) is int
                        and abs(srv_ticks - baseline['PlaybackPositionTicks']) <= 2 * TICKS_PER_SECOND
                    )
                    if not baseline_matches:
                        with self._lock:
                            self._pending_stops.pop(req_id, None)
                            sess['reconciled'] = 'conflict_discarded'
                        self.invalidation.notify_event(
                            meta['source_id'],
                            meta['source_generation'],
                            item_ids=[meta['item_id']],
                            kind='OfflineConflictDiscarded',
                        )
                        continue

                    entry['attempts'] += 1
                    if not sess.get('started_sent'):
                        playing_body = dict(entry['stop_body'], IsPaused=False, CanSeek=True, PlayMethod='DirectPlay')
                        playing_body.pop('Failed', None)
                        self._call_http(
                            client,
                            req_id,
                            '/Sessions/Playing',
                            lambda: client.session.request(
                                '/Sessions/Playing',
                                data=playing_body,
                                method='POST',
                                success_statuses=(200, 204),
                                empty_response=True,
                            ),
                        )
                        with self._lock:
                            sess['started_sent'] = True
                    self._send_stop_with_readback(client, req_id, sess, meta, entry['stop_body'], entry['reason'])
                    self.invalidation.mark_confirmed(meta['source_id'], meta['source_generation'], offline=False)
            except _ShutdownAbort:
                raise
            except PanError as exc:
                if str(exc) == 'PAN_SERVER_UNAUTHORIZED':
                    with self._lock:
                        self._auth_halted_scopes.add(skey)
                        self._pending_stops.pop(req_id, None)
                    self.invalidation.mark_auth_state(meta['source_id'], meta['source_generation'], 'AUTH_REQUIRED')

    def close(self, *, timeout: float = 3.0) -> bool:
        self._done.set()
        with self._lock:
            inflight = list(self._inflight)
            self._discard_queued_locked()
        for client, _req_id, _path in inflight:
            sess_http = getattr(client, 'session', None)
            attempt = getattr(sess_http, '_active_attempt', None)
            if attempt is not None and hasattr(attempt, 'abort'):
                try:
                    attempt.abort()
                except Exception:
                    pass
        if self._worker is not None and self._worker is not current_thread():
            self._worker.join(timeout)
            return not self._worker.is_alive()
        return True


def resolve_next_episode_result(
    current: dict,
    spec: dict,
    cancelled,
    *,
    open_session: bool = True,
) -> NextResolution:
    """Resolve the immediate next episode in the SAME season with explicit structured outcomes."""
    if cancelled():
        return NextResolution('cancelled')
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
        return NextResolution('error', detail='invalid_spec')

    season_ref = hashlib.sha256(f'{source_id}:{season_id}'.encode('utf-8')).hexdigest()[:16]
    selection_ref = {
        'mode': 'tv',
        '_emby_season_ref': season_ref,
        'tv_data': {'season': season_num, 'episode': episode_num + 1},
    }
    try:
        client, saved = _load_emby_client(Path(root_str), source_id, generation)
        with client.session.budget(8):
            client._identity(user_scoped_read=True)
            candidate = None
            exhausted_all = False
            for page_idx in range(1, 11):
                if cancelled():
                    return NextResolution('cancelled')
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
                if page_idx * 20 >= total:
                    exhausted_all = True
                if candidate is not None or exhausted_all:
                    break
            if cancelled():
                return NextResolution('cancelled')
            if candidate is None:
                if exhausted_all:
                    return NextResolution('confirmed_end')
                return NextResolution('error', detail='page_limit')

            next_id = identifier(candidate.get('Id'))
            detail = client._item(next_id)
            versions = detail.get('MediaSources')
            if not isinstance(versions, list) or len(versions) == 0:
                return NextResolution('error', detail='no_media_sources')
            if len(versions) > 1:
                # Ambiguous multi-version episode requires explicit user pick; do not guess.
                return NextResolution('needs_selection', selection=selection_ref, detail='multi_version')

            mid = identifier(versions[0].get('Id'))
            options = '|redirect-limit=0'
            if open_session:
                try:
                    opened = client.open_playback_session(next_id, mid, authenticated=False)
                except PanError as err:
                    if str(err) != 'PAN_EMBY_DIRECT_AUTH_REQUIRED' or versions[0].get('Protocol') != 'File':
                        return NextResolution('needs_selection', selection=selection_ref, detail=str(err))
                    opened = client.open_playback_session(next_id, mid, authenticated=True)
                    if opened['url'] != static_original_url(saved['location'], next_id, mid):
                        return NextResolution('error', detail='origin_mismatch')
                    from urllib.parse import quote
                    options += '&!X-Emby-Token=' + quote(saved['token'], safe='')
                final_url = opened['url'] + options
                mime = opened.get('mime', '')
                play_session_id = opened.get('play_session_id', '')
                needs_recheck = False
            else:
                if versions[0].get('Protocol') not in (None, 'File'):
                    return NextResolution('needs_selection', selection=selection_ref, detail='unsupported_protocol')
                final_url = static_original_url(saved['location'], next_id, mid) + options
                mime = ''
                play_session_id = ''
                needs_recheck = True
    except PanError as exc:
        code = str(exc)
        if code in ('PAN_SERVER_UNAUTHORIZED', 'PAN_SERVER_FORBIDDEN'):
            return NextResolution('auth', detail=code)
        if code in ('PAN_NETWORK_ERROR', 'PAN_BUDGET_EXHAUSTED', 'PAN_RATE_LIMITED', 'PAN_STORAGE_UNAVAILABLE'):
            return NextResolution('offline', detail=code)
        if code in ('PAN_EMBY_DIRECT_AUTH_REQUIRED', 'PAN_MEDIA_UNSUPPORTED'):
            return NextResolution('needs_selection', selection=selection_ref, detail=code)
        return NextResolution('error', detail=code)
    except (ValueError, OSError):
        return NextResolution('error', detail='invalid_reply')

    if cancelled():
        return NextResolution('cancelled')
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
    # Season grouping ref identifies SxxExx media ref only; never claim same-release version proof from season_id.
    return NextResolution(
        'candidate',
        candidate={
            '_account': scope,
            'mode': 'tv',
            '_emby_season_ref': season_ref,
            'prepared_version_key': None,
            '_next_cloud_verified': False,
            '_next_recheck': needs_recheck,
            'url': final_url,
            'title': title,
            'source_title': title,
            'mime': mime,
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
                'play_session_id': play_session_id,
            },
            '_owned_next': {
                'resolver': 'emby_same_season',
                'profile_root': root_str,
                'season_id': season_id,
                'season': season_num,
                'episode': episode_num + 1,
            },
        },
    )


def resolve_next_episode_data(current: dict, spec: dict, cancelled) -> dict | None:
    """Resolve the immediate next episode in the SAME season for Emby NATURAL_EOF continuation."""
    res = resolve_next_episode_result(current, spec, cancelled, open_session=True)
    return res.candidate if res.outcome == 'candidate' else None


register_next_resolver('emby_same_season', resolve_next_episode_result)

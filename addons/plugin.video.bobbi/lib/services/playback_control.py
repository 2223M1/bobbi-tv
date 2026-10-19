"""Resident service's serialized playback owner; never run in a GUI callback."""
import json
import os
from pathlib import Path
from queue import Empty, Queue
import selectors
import socket
import stat
import struct
import time

from lib.cinema.playback_authority import PlaybackAuthority, NativeObservationUnavailable
from lib.cinema.playback_ipc import MAX_FRAME, SOCKET_PATH


class KodiNative:
    def __init__(self):
        from bobbi_core.subtitle_lookup_portable import SubtitleLookup
        from lib.services.subtitle_fallback import SubtitleFallback
        self.subtitle_lookup = SubtitleLookup()
        self.subtitle_fallback = SubtitleFallback()
        self.subtitle_poll = 0
        self.subtitle_receipt = None

    def poll_io(self):
        self.subtitle_lookup.tick()
        if ((self.subtitle_receipt is not None or self.subtitle_fallback.key is not None)
                and time.monotonic() >= self.subtitle_poll):
            self.subtitle_poll = time.monotonic() + .5
            try:
                from bobbi_core.native_receipt import receipt as checked_receipt, subtitle_snapshot_follows
                snapshot = self.state()
                if (not isinstance(snapshot, dict) or type(snapshot.get('protocol')) is not int
                        or snapshot['protocol'] != 1 or 'playback' not in snapshot
                        or type(snapshot.get('selection_epoch')) is not int
                        or snapshot['selection_epoch'] < 0):
                    return
                raw = snapshot['playback']
                current = checked_receipt(raw) if raw is not None else None
                if raw is not None and current is None:
                    return
                if (current and current['phase'] == 'AV_STARTED'
                        and not subtitle_snapshot_follows(current, None)):
                    return
            except (OSError, ValueError, RuntimeError):
                return  # Unknown state is not a stop or permission to change subtitles.
            receipt = self.subtitle_receipt
            if (receipt and current and current.get('phase') == 'AV_STARTED'
                    and current.get('native_instance') == receipt.get('native_instance')
                    and current.get('request_id') == receipt.get('request_id')
                    and not subtitle_snapshot_follows(current, receipt)):
                return  # A stale live snapshot is not renewed automatic intent.
            self.subtitle_fallback.observe(current)
            if receipt is not None:
                import xbmcgui
                from lib.services.subtitle_fallback import receipt_key
                window = xbmcgui.Window(10000)
                owned_label = window.getProperty('AM6B.SubtitleStateOwner') == receipt['request_id']
                same = (current and current.get('phase') == 'AV_STARTED'
                        and receipt_key(current)[:4] == receipt_key(receipt)[:4])
                if not same:
                    self.subtitle_receipt = None
                    if owned_label:
                        window.clearProperty('AM6B.SubtitleState')
                        window.clearProperty('AM6B.SubtitleStateOwner')
                else:
                    # Poll may observe a manual change after the client has
                    # finished discovery. Preserve that same-sequence watermark.
                    self.subtitle_receipt = current
                    if owned_label and current.get('subtitle_intent') != current.get('subtitle_auto_intent'):
                        label = '字幕已由你手动控制'
                        if window.getProperty('AM6B.SubtitleState') != label:
                            window.setProperty('AM6B.SubtitleState', label)

    def close(self):
        self.subtitle_lookup.close()
        self.subtitle_fallback.close()

    @staticmethod
    def rpc(method, params=None):
        import xbmc
        response = json.loads(xbmc.executeJSONRPC(json.dumps(
            dict(jsonrpc='2.0', id=1, method=method, params=params or {}))))
        if 'error' in response:
            if (response.get('error') or {}).get('code') in (-32700, -32600, -32601, -32602):
                raise ValueError('Native playback protocol rejected')
            raise RuntimeError('Native playback protocol unavailable')
        return response.get('result')

    def state(self):
        return self.rpc('Player.BobiState')

    def control(self, command):
        return self.rpc('Player.BobiControl', command)

    def intent(self, command):
        return self.rpc('Player.BobiIntent', command)

    def fullscreen(self, command):
        return self.rpc('Player.BobiFullscreen', command)

    @staticmethod
    def loading_window(dialog_id, token):
        """Resident read of one registered resolver, not client-supplied state."""
        import xbmc
        import xbmcgui
        if type(dialog_id) is not int or not 10000 <= dialog_id < 100000:
            return None
        visible = bool(xbmc.getCondVisibility('Window.IsVisible({})'.format(dialog_id)))
        try:
            matching = xbmcgui.Window(dialog_id).getProperty('AM6B.ResolverToken') == token
        except RuntimeError:
            matching = False  # A destroyed window is not another owned window.
        return dict(visible=visible, matching=matching,
                    modal=bool(xbmc.getCondVisibility('System.HasModalDialog')),
                    active_window=xbmcgui.getCurrentWindowId())

    @staticmethod
    def handoff_diagnostic(request_id, stage, reason, attempt):
        import xbmc
        xbmc.log('[CINEMA-HANDOFF303] request={} stage={} reason={} attempt={}'.format(
            request_id[:8], stage, reason, attempt), xbmc.LOGINFO)

    @staticmethod
    def terminal_diagnostic(request_id, native_instance, reason):
        """Fixed native terminal evidence, never locators, credentials or guesses."""
        import re
        import xbmc
        from bobbi_core.native_receipt import UUID, TERMINALS
        if (not isinstance(request_id, str) or not re.fullmatch(r'(?:[0-9a-f]{32})?', request_id)
                or not isinstance(native_instance, str) or not UUID.fullmatch(native_instance)
                or not isinstance(reason, str) or reason not in TERMINALS):
            return False
        xbmc.log('[BOBBI-TERMINAL] request={} instance={} reason={}'.format(
            request_id, native_instance, reason), xbmc.LOGINFO)
        return True

    def subtitles(self):
        return self.rpc('Player.BobiSubtitles')

    def subtitle(self, command):
        return self.rpc('Player.BobiSubtitle', command)

    def subtitle_file(self, command):
        return self.rpc('Player.BobiSubtitleFile', command)

    def subtitle_candidate_current(self, candidate):
        return self.subtitle_fallback.candidate_account_current(candidate)

    def set_subtitle_context(self, receipt, context):
        # Lookup context is not presentation ownership. Only a verified AV
        # status publication may replace the label's cleanup receipt.
        self.subtitle_fallback.context(receipt, context)

    def cancel_external_subtitle_lookup(self):
        # Embedded Chinese can appear while a bounded external search is in
        # flight. Stop optional IO without joining/blocking the owner thread.
        self.subtitle_fallback.cancel.set()

    def publish_subtitle_status(self, captured, status, final_attempt=False):
        """Called only by the serialized authority after current-owner refresh."""
        from bobbi_core.native_receipt import receipt, subtitle_snapshot_follows
        current = receipt(captured)
        if (not current or not current['request_id']
                or not subtitle_snapshot_follows(current, None)
                or status == 'STALE'):
            return False
        labels = {'SUBTITLE_PREPARING': '正在查找中文字幕',
                  'QUEUED': '正在查找中文字幕',
                  'CANDIDATE_LOADED': '中文字幕已加载',
                  'CONFIRMED': '中文字幕已启用',
                  'NO_QUALIFIED_CHINESE_SUBTITLE': '未找到匹配中文字幕',
                  'MANUAL_PRESERVED': '字幕已由你手动控制',
                  'SUBTITLE_PROVIDER_AUTH_REQUIRED': '字幕来源未配置或认证失败 · 可手动选择',
                  'SUBTITLE_PROVIDER_RATE_LIMITED': '字幕来源配额受限 · 稍后重试',
                  'SUBTITLE_LOOKUP_TIMEOUT': '字幕匹配超时 · 可手动重试',
                  'SUBTITLE_LOOKUP_STOPPED': '字幕匹配已中止或到时 · 可手动选择',
                  'SUBTITLE_PROVIDER_UNAVAILABLE': '字幕来源暂不可用 · 可手动重试',
                  'SUBTITLE_CANDIDATE_UNAVAILABLE': '已匹配字幕候选但未能加载 · 可手动选择',
                  'SUBTITLE_TIMELINE_REJECTED': '字幕暂不可用 · 可手动选择',
                  'SUBTITLE_TEXT_REJECTED': '字幕正文未通过校验 · 可手动选择',
                  'SUBTITLE_IDENTITY_REJECTED': '字幕与当前文件不一致 · 未自动加载',
                  'SUBTITLE_CONTEXT_UNAVAILABLE': '影片身份资料不足 · 未自动匹配字幕',
                  'SUBTITLE_LOOKUP_UNAVAILABLE': '字幕匹配未完成 · 原因未确认，可手动选择'}
        final_statuses = {'CATALOG_UNAVAILABLE', 'INTENT_PROTOCOL_UNAVAILABLE',
                          'CONTROL_NOT_CONFIRMED', 'STREAM_IDENTITY_UNAVAILABLE',
                          'CONTROL_UNAVAILABLE', 'NO_FULL_CHINESE_TRACK',
                          'SUBTITLE_SERVICE_UNAVAILABLE', 'SUBTITLE_EXPORT_INVALID'}
        if not isinstance(status, str) or status not in set(labels) | final_statuses:
            return False
        previous = self.subtitle_receipt
        if (previous and previous.get('native_instance') == current['native_instance']
                and not subtitle_snapshot_follows(current, previous)):
            return False
        if current['subtitle_intent'] != current['subtitle_auto_intent']:
            status = 'MANUAL_PRESERVED'
        label = labels.get(status)
        if final_attempt:
            final_labels = {
                'CATALOG_UNAVAILABLE': '字幕轨信息暂不可读 · 可手动选择',
                'INTENT_PROTOCOL_UNAVAILABLE': '字幕控制状态不可确认 · 未自动修改',
                'CONTROL_NOT_CONFIRMED': '字幕启用尚未确认 · 可手动选择',
                'STREAM_IDENTITY_UNAVAILABLE': '字幕轨身份不可确认 · 未自动加载',
                'CONTROL_UNAVAILABLE': '字幕控制暂不可用 · 可手动选择',
                'NO_FULL_CHINESE_TRACK': '未发现完整中文字幕轨 · 可手动选择',
                'SUBTITLE_SERVICE_UNAVAILABLE': '字幕服务暂不可用 · 可手动选择',
                'SUBTITLE_EXPORT_INVALID': '字幕文件未通过校验 · 未自动加载',
                'SUBTITLE_PREPARING': '字幕匹配尚未完成 · 可手动选择',
                'QUEUED': '字幕启用尚未确认 · 可手动选择',
            }
            label = final_labels.get(status, label)
        if label is None:
            return False
        import xbmcgui
        window = xbmcgui.Window(10000)
        # This service is the only writer. A client interpreter must never
        # compare-then-clear these properties across a newer request's write.
        self.subtitle_receipt = current
        window.setProperty('AM6B.SubtitleStateOwner', current['request_id'])
        window.setProperty('AM6B.SubtitleState', label)
        return True

    def set_torrent_context(self, request_id, file_identity, metadata):
        self.subtitle_fallback.torrent_context(request_id, file_identity, metadata)

    def external_subtitle(self, receipt):
        prepared = self.subtitle_lookup.request(receipt)
        # Keep the existing exact same-release path first. A BT video without a
        # prepared cloud binding may still search subtitles, never create a task.
        if prepared.get('state') == 'ready':
            return prepared
        # A cloud preparation still pending must not block BT/external lookup.
        fallback = self.subtitle_fallback.request(receipt)
        if fallback.get('reason') == 'MEDIA_CONTEXT_MISSING' and prepared.get('state') == 'pending':
            return prepared
        return fallback


class PlaybackControlServer:
    def __init__(self, native=None, path=SOCKET_PATH, events=None):
        if path is None:
            # The authenticated portable IPC queues to this same actor on the
            # Kodi thread. No second authority or fabricated native receipts.
            self.path = self.listener = self.selector = self.lock = None
            self.clients = {}
            self.events = events if events is not None else Queue(maxsize=128)
            self.native = native or KodiNative()
            self.authority = PlaybackAuthority(self.native)
            self.refresh_pending, self.refresh_due, self.refresh_backoff = False, 0.0, .1
            return
        import fcntl
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.parent.is_symlink():
            raise ValueError('Playback socket directory cannot be a symlink')
        self.lock = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists() or self.path.is_symlink():
                existing = self.path.lstat()
                if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != os.getuid():
                    raise ValueError('Refuse to replace unknown socket path')
                self.path.unlink()  # Only stale owned socket after exclusive lock.
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self.inode = self.path.stat().st_ino
            self.listener.listen(4)
            self.listener.setblocking(False)
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.listener, selectors.EVENT_READ)
            self.clients = {}
            self.events = events if events is not None else Queue(maxsize=128)
            self.native = native or KodiNative()
            self.authority = PlaybackAuthority(self.native)
            self.refresh_pending = False
            self.refresh_due = 0.0
            self.refresh_backoff = .1
        except Exception:
            if hasattr(self, 'selector'):
                self.selector.close()
            if hasattr(self, 'listener'):
                self.listener.close()
            if (hasattr(self, 'inode') and self.path.exists()
                    and self.path.lstat().st_ino == self.inode
                    and stat.S_ISSOCK(self.path.lstat().st_mode)):
                self.path.unlink()
            os.close(self.lock)
            raise

    def _close_client(self, connection):
        self.selector.unregister(connection)
        self.clients.pop(connection, None)
        connection.close()

    def tick(self, budget=0.05):
        if not 0 <= budget <= 0.05:
            raise ValueError('Bounded resident-service tick required')
        poll_io = getattr(self.native, 'poll_io', None)
        if poll_io is not None:
            poll_io()
        lifecycle_changed = False
        for _ in range(32):
            try:
                sender, method, data = self.events.get_nowait()
            except Empty:
                break
            try:
                decoded = json.loads(data)
                if sender == 'xbmc' and method == 'Player.OnBobiWindow' and isinstance(decoded, dict):
                    lifecycle_changed = True
                else:
                    lifecycle_changed |= self.authority.event(sender, method, decoded)
            except (ValueError, TypeError):
                pass  # Malformed notification is not an authoritative event.
        if lifecycle_changed:
            self.refresh_pending = True
        if self.refresh_pending and time.monotonic() >= self.refresh_due:
            try:
                self.authority.refresh()
            except NativeObservationUnavailable:
                # Keep the same owner/epoch. Every IPC action still requires a
                # fresh native read, so unknown state grants no stale control.
                self.refresh_due = time.monotonic() + self.refresh_backoff
                self.refresh_backoff = min(2.0, self.refresh_backoff * 2)
            else:
                self.refresh_pending = False
                self.refresh_backoff = .1
        for key, mask in (self.selector.select(budget) if self.selector is not None else ()):
            connection = key.fileobj
            if connection is self.listener:
                client, _ = self.listener.accept()
                credentials = client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                _, uid, _ = struct.unpack('3i', credentials)
                if uid != os.getuid() or len(self.clients) >= 4:
                    client.close()
                    continue
                client.setblocking(False)
                self.clients[client] = dict(data=bytearray(), output=b'', deadline=time.monotonic() + 0.5)
                self.selector.register(client, selectors.EVENT_READ)
                continue
            record = self.clients[connection]
            try:
                if mask & selectors.EVENT_WRITE:
                    written = connection.send(record['output'])
                    record['output'] = record['output'][written:]
                    if not record['output']:
                        self._close_client(connection)
                    continue
                chunk = connection.recv(4096)
                if not chunk:
                    self._close_client(connection)
                    continue
                record['data'].extend(chunk)
                if len(record['data']) > MAX_FRAME:
                    self._close_client(connection)
                    continue
                if b'\n' not in record['data']:
                    continue
                line, trailing = bytes(record['data']).split(b'\n', 1)
                try:
                    if trailing:
                        raise ValueError('One command per connection')
                    result = self.authority.dispatch(json.loads(line))
                    answer = dict(ok=True, result=result)
                except (ValueError, TypeError, RuntimeError, OSError):
                    answer = dict(ok=False, error='PLAYBACK_OWNER_REJECTED')
                payload = json.dumps(answer, separators=(',', ':')).encode('utf-8') + b'\n'
                if len(payload) > MAX_FRAME:
                    self._close_client(connection)
                    continue
                record['output'] = payload
                self.selector.modify(connection, selectors.EVENT_WRITE)
            except (ConnectionError, OSError):
                self._close_client(connection)
        now = time.monotonic()
        for connection, record in tuple(self.clients.items()):
            if now >= record['deadline']:
                self._close_client(connection)

    def close(self):
        close_io = getattr(self.native, 'close', None)
        if close_io is not None:
            close_io()
        for connection in tuple(self.clients):
            self._close_client(connection)
        if self.selector is not None:
            self.selector.close()
        if self.listener is not None:
            self.listener.close()
        if self.path is not None and self.path.exists() and self.path.stat().st_ino == self.inode:
            self.path.unlink()
        if self.lock is not None:
            os.close(self.lock)

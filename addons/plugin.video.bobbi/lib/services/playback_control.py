"""Resident service's serialized playback owner; never run in a GUI callback."""
import json
import os
from pathlib import Path
from queue import Empty, Queue
import math
import selectors
import socket
import stat
import struct
import time

from bobbi_core.playback_authority import PlaybackAuthority, NativeObservationUnavailable
from bobbi_core.playback_ipc import MAX_FRAME, SOCKET_PATH


class KodiNative:
    def __init__(self, host=None):
        from bobbi_core.subtitle_lookup_portable import SubtitleLookup
        from lib.services.subtitle_fallback import SubtitleFallback
        def capture_preparation(receipt):
            if host is None:
                return None
            from bobbi_platform.prepared_sessions import from_host
            account = host.accounts.snapshot()
            if not account['authenticated']:
                return None
            session = from_host(host, account)
            return session.call if session is not None else None
        self.subtitle_lookup = SubtitleLookup(capture=capture_preparation)
        self.subtitle_fallback = SubtitleFallback(
            factory=host.subtitle_candidates if host is not None else None,
            root=host.subtitle_root if host is not None else None,
            current=host.check_profile if host is not None else (lambda: False))
        self.subtitle_poll = 0
        self.subtitle_receipt = None
        self.subtitle_label = ''
        self.presentation_receipt = None

    def poll_io(self):
        self.subtitle_lookup.tick()
        if ((self.subtitle_receipt is not None or self.subtitle_fallback.key is not None or self.presentation_receipt is not None)
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
            if self.presentation_receipt is not None:
                import xbmcgui
                from bobbi_core.playback_presentation import audio_status
                previous = self.presentation_receipt
                window = xbmcgui.Window(10000)
                if (not current or current.get('phase') != 'AV_STARTED'
                        or current.get('native_instance') != previous['native_instance']
                        or current.get('request_id') != previous['request_id']):
                    self.presentation_receipt = None
                    window.clearProperty('AM6B.AudioState')
                    window.clearProperty('AM6B.PlaybackStateOwner')
                else:
                    self.presentation_receipt = current
                    window.setProperty('AM6B.AudioState', audio_status(current))
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
                        self.subtitle_label = label
                        if window.getProperty('AM6B.SubtitleState') != label:
                            window.setProperty('AM6B.SubtitleState', label)

    def close(self):
        try:
            self.subtitle_lookup.close()
        finally:
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

    @staticmethod
    def continuation_diagnostic(value):
        """Bounded causal IDs/hashes only; no grant token, source URL or account."""
        import re
        import xbmc
        from bobbi_core.native_receipt import UUID, SHA
        keys = {'schema', 'stage', 'kind', 'parent_request_id', 'parent_native_instance',
                'selection_sha256', 'child_request_id'}
        if (type(value) is not dict or set(value) != keys or type(value['schema']) is not int
                or value['schema'] != 1 or value['stage'] not in ('GRANTED', 'CHILD_RESERVED')
                or value['kind'] not in ('natural', 'manual', 'transport')
                or not isinstance(value['parent_request_id'], str)
                or not re.fullmatch('[0-9a-f]{32}', value['parent_request_id'])
                or not isinstance(value['parent_native_instance'], str)
                or not UUID.fullmatch(value['parent_native_instance'])
                or not isinstance(value['selection_sha256'], str) or not SHA.fullmatch(value['selection_sha256'])
                or not isinstance(value['child_request_id'], str)
                or not re.fullmatch('[0-9a-f]{32}' if value['stage'] == 'CHILD_RESERVED' else '',
                                    value['child_request_id'])):
            return False
        xbmc.log('[BOBBI-CONTINUATION] '+json.dumps(value, sort_keys=True, separators=(',', ':')), xbmc.LOGINFO)
        return True

    def subtitles(self):
        return self.rpc('Player.BobiSubtitles')

    def video(self):
        # Not instance scoped by itself. The pure presentation read brackets
        # this with native receipts before any fields become start evidence.
        return self.rpc('Player.GetProperties', dict(playerid=1, properties=['currentvideostream']))

    def subtitle_status(self, captured):
        # The owner supplies a verified current receipt. Its manual watermark
        # outranks the previous automatic label, even before the next IO poll.
        if captured.get('subtitle_intent') != captured.get('subtitle_auto_intent'):
            return '字幕已由你手动控制'
        if (self.subtitle_receipt and captured.get('native_instance') == self.subtitle_receipt.get('native_instance')
                and captured.get('request_id') == self.subtitle_receipt.get('request_id')):
            return self.subtitle_label
        return '字幕状态尚未确认'

    def publish_playback_presentation(self, captured, view):
        """One resident publisher for the TV and browser's shared projection."""
        import xbmcgui
        self.presentation_receipt = captured
        window = xbmcgui.Window(10000)
        window.setProperty('AM6B.PlaybackStateOwner', captured['request_id'])
        window.setProperty('AM6B.AudioState', view['audio_status'])

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
        self.subtitle_lookup.cancel()

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
                  'SUBTITLE_PROVIDER_AUTH_REQUIRED': '字幕服务尚未登录或配置 · 可手动选择',
                  'SUBTITLE_PROVIDER_RATE_LIMITED': '字幕查询次数已达限制 · 请稍后重试',
                  'SUBTITLE_LOOKUP_TIMEOUT': '字幕匹配超时 · 可手动重试',
                  'SUBTITLE_LOOKUP_STOPPED': '字幕搜索已停止 · 可手动选择',
                  'SUBTITLE_PROVIDER_UNAVAILABLE': '字幕来源暂不可用 · 可手动重试',
                  'SUBTITLE_CANDIDATE_UNAVAILABLE': '找到字幕但加载失败 · 可手动选择',
                  'SUBTITLE_TIMELINE_REJECTED': '字幕暂不可用 · 可手动选择',
                  'SUBTITLE_TEXT_REJECTED': '字幕内容无效 · 可手动选择',
                  'SUBTITLE_IDENTITY_REJECTED': '字幕与当前文件不一致 · 未自动加载',
                  'SUBTITLE_CONTEXT_UNAVAILABLE': '影片资料不足 · 请手动选择字幕',
                  'SUBTITLE_LOOKUP_UNAVAILABLE': '字幕搜索未完成 · 可手动选择'}
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
                'CATALOG_UNAVAILABLE': '字幕列表读取失败 · 可手动选择',
                'INTENT_PROTOCOL_UNAVAILABLE': '未确认当前字幕设置 · 未自动修改',
                'CONTROL_NOT_CONFIRMED': '字幕启用尚未确认 · 可手动选择',
                'STREAM_IDENTITY_UNAVAILABLE': '无法确认字幕属于本片 · 未自动加载',
                'CONTROL_UNAVAILABLE': '字幕控制暂不可用 · 可手动选择',
                'NO_FULL_CHINESE_TRACK': '未找到完整中文字幕 · 可手动选择',
                'SUBTITLE_SERVICE_UNAVAILABLE': '字幕服务暂不可用 · 可手动选择',
                'SUBTITLE_EXPORT_INVALID': '字幕文件无效 · 未自动加载',
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
        self.subtitle_label = label
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
    def __init__(self, native=None, path=SOCKET_PATH, events=None, *, host=None):
        self.host = host
        self._owned_state = None
        self._owned_poll_due = 0.0
        self._local_owned_next = None
        self._owned_next_candidates = Queue(maxsize=4)
        self._owned_next_ready = Queue(maxsize=4)
        self._owned_next_consumed_parents = []
        self._owned_terminal_parent = None
        self._owned_resume_seek = None
        if path is None:
            # The authenticated portable IPC queues to this same actor on the
            # Kodi thread. No second authority or fabricated native receipts.
            self.path = self.listener = self.selector = self.lock = None
            self.clients = {}
            self.events = events if events is not None else Queue(maxsize=128)
            self.native = native or KodiNative(host=host)
            self.authority = PlaybackAuthority(self.native,
                subtitle_root=host.subtitle_root if host is not None else None,
                profile_current=host.check_profile if host is not None else (lambda: False))
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
            self.native = native or KodiNative(host=host)
            self.authority = PlaybackAuthority(self.native,
                subtitle_root=host.subtitle_root if host is not None else None,
                profile_current=host.check_profile if host is not None else (lambda: False))
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
        from lib.services.next_episode_summary import Display
        if not hasattr(self, 'next_display'):
            self.next_display = Display('native')
            self.next_display.clear()
        self.next_display.publish(None if self.refresh_pending else self.authority.next_summary_snapshot())
        self._observe_owned_tracks(now)

    def _observe_owned_tracks(self, now):
        host = getattr(self, 'host', None)
        if host is None:
            return
        self._drain_owned_next_queues()
        if not getattr(host, 'owned_tracks', None):
            return
        pending_summaries = getattr(self, '_owned_next_summaries', None)
        if pending_summaries is not None:
            while True:
                try:
                    msg = pending_summaries.get_nowait()
                except Empty:
                    break
                try:
                    cand = msg.pop('_prefetched_candidate', None) if isinstance(msg, dict) else None
                    reply = self.authority.dispatch(msg)
                    if (
                        isinstance(reply, dict)
                        and reply.get('accepted') is True
                        and isinstance(cand, dict)
                        and isinstance(self._owned_state, dict)
                        and self._owned_state.get('request_id') == msg.get('request_id')
                        and self._owned_state.get('native_instance') == msg.get('native_instance')
                    ):
                        self._owned_state['prefetched_next'] = dict(cand)
                except Exception:
                    pass

        observed = getattr(self.authority.owner, 'observed', None)
        obs_req = observed.get('request_id') if isinstance(observed, dict) else None
        obs_inst = observed.get('native_instance') if isinstance(observed, dict) else None
        obs_started = bool(observed.get('av_started')) if isinstance(observed, dict) else False

        prev = self._owned_state
        if prev is not None:
            with host.lock:
                prev_track = host.owned_tracks.get(prev['request_id'])
            prev_cancelled = prev_track is None or bool(prev_track.get('cancelled'))
            same_instance = obs_req == prev['request_id'] and obs_inst == prev['native_instance']
            if prev_cancelled or not same_instance:
                from bobbi_core.playback_completion import (
                    completion_observation as valid_completion,
                    terminal_end,
                )
                reason = 'SUPERSEDED' if (obs_inst and obs_inst != prev['native_instance']) else 'STOP'
                pos, dur = prev['position'], prev['duration']
                obs_clock = prev['observed_clock']
                term = getattr(self.authority.owner, 'terminal', None)
                matched_term = (
                    term
                    if isinstance(term, dict)
                    and term.get('native_instance') == prev['native_instance']
                    and term.get('request_id', prev['request_id']) == prev['request_id']
                    else None
                )
                if matched_term is not None:
                    reason = str(matched_term.get('reason') or 'STOP')
                term_doc = dict(matched_term) if matched_term is not None else {'reason': reason}
                last_nat = getattr(self.authority, 'last_native', None)
                if 'completion_observation' not in term_doc and isinstance(last_nat, dict):
                    if (
                        last_nat.get('native_instance') == prev['native_instance']
                        and last_nat.get('request_id', prev['request_id']) == prev['request_id']
                        and 'completion_observation' in last_nat
                    ):
                        term_doc['completion_observation'] = last_nat['completion_observation']
                    elif 'completion_observation' in last_nat and last_nat.get('native_instance') != prev['native_instance']:
                        term_doc['completion_observation'] = None
                if 'completion_observation' in term_doc:
                    checked_comp = valid_completion(term_doc.get('completion_observation'))
                    if checked_comp is not None and checked_comp['valid'] and checked_comp['age_us'] <= 5_000_000:
                        dur = checked_comp['duration_ms'] / 1000.0
                        pos = min(checked_comp['position_ms'], checked_comp['duration_ms']) / 1000.0
                        obs_clock = True
                if reason == 'NATURAL_EOF':
                    terminal_seen_at = getattr(self.authority, 'terminal_seen_at', None)
                    seen_fresh = (
                        terminal_seen_at is None
                        or (isinstance(terminal_seen_at, (int, float)) and 0.0 <= now - terminal_seen_at <= 5.0)
                    )
                    last_clock_at = prev.get('last_clock_at', prev.get('last_obs_at')) if prev.get('observed_clock') else None
                    if prev_cancelled or not seen_fresh or not terminal_end(term_doc, pos, dur, last_clock_at, now):
                        reason = 'ERROR'
                host.notify_playback_event({
                    'event': 'TERMINAL',
                    'request_id': prev['request_id'],
                    'account': dict(prev['account']),
                    'position': pos,
                    'duration': dur,
                    'paused': False,
                    'reason': reason,
                    'observed_clock': obs_clock,
                    'data': dict(prev['data']),
                })
                self._owned_state = None
                if reason == 'NATURAL_EOF' and isinstance(prev['data'].get('_owned_next'), dict):
                    owner_obj = getattr(self.authority, 'owner', None)
                    self._owned_terminal_parent = {
                        'boot_id': prev.get('boot_id') or getattr(owner_obj, 'boot_id', ''),
                        'epoch': prev.get('epoch') if prev.get('epoch') is not None else getattr(owner_obj, 'epoch', 0),
                        'request_id': prev['request_id'],
                        'native_instance': prev['native_instance'],
                        'account_scope': dict(prev['account']),
                        'prefetched_next': prev.get('prefetched_next'),
                    }
                    try:
                        self._launch_owned_next(prev['data'])
                    finally:
                        self._owned_terminal_parent = None

        if not obs_req or not obs_inst or not obs_started:
            return
        with host.lock:
            tracked = host.owned_tracks.get(obs_req)
        if not tracked or tracked.get('cancelled') or not isinstance(tracked.get('data'), dict):
            return
        first = self._owned_state is None or self._owned_state['native_instance'] != obs_inst
        if not first and now < self._owned_poll_due:
            return
        self._owned_poll_due = now + 1.0
        pos, dur, obs_clock, pres = self._sample_owned_clock(obs_req, obs_inst)
        cur_paused = bool(observed.get('paused', False))
        if first:
            resume_req = tracked['data'].get('_resume_offset_seconds')
            want_resume = (
                isinstance(resume_req, (int, float))
                and 5.0 <= float(resume_req) <= 864000.0
                and not tracked['data'].get('_bobbi_start_over')
                and not tracked['data'].get('_mounted_path')
            )
            if want_resume:
                seek_state = getattr(self, '_owned_resume_seek', None)
                if not isinstance(seek_state, dict) or seek_state.get('native_instance') != obs_inst:
                    seek_state = {
                        'native_instance': obs_inst,
                        'first_seen_at': now,
                        'attempted_at': None,
                        'seek_queued': False,
                    }
                    self._owned_resume_seek = seek_state
                if not obs_clock:
                    if (now - seek_state['first_seen_at']) < 1.5:
                        self._owned_poll_due = now + 0.15
                        return
                else:
                    target_sec = float(resume_req)
                    if target_sec < dur - 2.0 and pos < max(5.0, target_sec - 15.0):
                        if seek_state['attempted_at'] is None:
                            seek_queued = False
                            can_attempt_now = False
                            try:
                                from uuid import uuid4
                                if pres is None:
                                    pres = self.authority.dispatch({
                                        'operation': 'playback_presentation',
                                        'include_owner': True,
                                    })
                                can_attempt_now = (
                                    isinstance(pres, dict)
                                    and bool(pres.get('available'))
                                    and bool(pres.get('can_seek'))
                                    and int(round(target_sec * 1000)) < int(pres.get('duration_ms') or 0)
                                )
                                if can_attempt_now:
                                    cmd_res = self.authority.dispatch({
                                        'operation': 'playback_command',
                                        'command': {
                                            'expected': pres['expected'],
                                            'command_id': uuid4().hex,
                                            'action': 'seek',
                                            'params': {'position_ms': int(round(target_sec * 1000))},
                                        },
                                    })
                                    seek_queued = isinstance(cmd_res, dict) and cmd_res.get('status') in (
                                        'queued',
                                        'applied',
                                    )
                            except Exception:
                                seek_queued = False
                            if not can_attempt_now and (now - seek_state['first_seen_at']) < 0.8:
                                self._owned_poll_due = now + 0.15
                                return
                            seek_state['attempted_at'] = now
                            seek_state['seek_queued'] = seek_queued
                            if seek_queued:
                                self._owned_poll_due = now + 0.2
                                return
                        elif seek_state['seek_queued'] and (now - seek_state['attempted_at']) < 2.5:
                            self._owned_poll_due = now + 0.2
                            return

            self._owned_state = {
                'boot_id': getattr(self.authority.owner, 'boot_id', ''),
                'epoch': getattr(self.authority.owner, 'epoch', 0),
                'request_id': obs_req,
                'native_instance': obs_inst,
                'prefetched_next': None,
                'account': dict(tracked['account']),
                'data': dict(tracked['data']),
                'position': pos,
                'duration': dur,
                'observed_clock': obs_clock,
                'paused': cur_paused,
                'last_obs_at': now,
                'last_clock_at': now if obs_clock else None,
                'last_emit_at': now,
            }
            host.notify_playback_event({
                'event': 'AV_START',
                'request_id': obs_req,
                'account': dict(tracked['account']),
                'position': pos,
                'duration': dur,
                'paused': cur_paused,
                'observed_clock': obs_clock,
                'data': dict(tracked['data']),
            })
            if isinstance(tracked['data'].get('_owned_next'), dict):
                self._prepare_owned_next_summary(
                    self.authority.owner.boot_id,
                    self.authority.owner.epoch,
                    obs_req,
                    obs_inst,
                    dict(tracked['account']),
                    dict(tracked['data']),
                )
            return

        st = self._owned_state
        prev_paused = st['paused']
        prev_pos = st['position']
        prev_obs = st.get('last_clock_at') if st.get('last_clock_at') is not None else st['last_obs_at']
        if obs_clock:
            st['position'] = pos
            st['duration'] = dur
            st['observed_clock'] = True
            st['last_clock_at'] = now
            st['last_obs_at'] = now
        st['paused'] = cur_paused

        trigger = None
        if cur_paused != prev_paused:
            trigger = 'Pause' if cur_paused else 'Unpause'
        elif obs_clock:
            expected_adv = 0.0 if prev_paused else max(0.0, now - prev_obs)
            if abs(pos - (prev_pos + expected_adv)) >= 4.0:
                trigger = 'TimeUpdate'
        if trigger is None and obs_clock and (now - st['last_emit_at']) >= 10.0:
            trigger = 'TimeUpdate'
        if trigger is not None:
            st['last_emit_at'] = now
            host.notify_playback_event({
                'event': 'PROGRESS',
                'request_id': obs_req,
                'account': dict(st['account']),
                'position': st['position'],
                'duration': st['duration'],
                'paused': cur_paused,
                'trigger': trigger,
                'observed_clock': st['observed_clock'],
                'data': dict(st['data']),
            })

    def _sample_owned_clock(self, obs_req, obs_inst):
        pres = None
        try:
            pres = self.authority.dispatch({
                'operation': 'playback_presentation',
                'include_owner': True,
            })
        except Exception:
            pres = None
        if isinstance(pres, dict):
            if pres.get('available') is True:
                exp = pres.get('expected')
                if (
                    isinstance(exp, dict)
                    and exp.get('request_id') == obs_req
                    and exp.get('native_instance', obs_inst) == obs_inst
                ):
                    p_ms, d_ms = pres.get('position_ms'), pres.get('duration_ms')
                    if (
                        type(p_ms) is int
                        and type(d_ms) is int
                        and exp.get('native_instance') == obs_inst
                        and 0 <= p_ms <= d_ms
                        and 0 < d_ms <= 864000000
                    ):
                        return p_ms / 1000.0, d_ms / 1000.0, True, pres
            elif pres.get('mode') == 'external' or pres.get('reason') == 'PLAYBACK_SCOPE_CHANGED':
                return 0.0, 0.0, False, pres

        native_iface = getattr(self, 'native', None) or getattr(self.authority, 'native', None)
        try:
            if native_iface is not None:
                from bobbi_core.native_receipt import receipt as checked_receipt
                before_state = native_iface.state()
                res_epoch = getattr(self.authority, 'reservation_epoch', None)
                desired = getattr(getattr(self.authority, 'owner', None), 'desired', None)
                if (
                    not isinstance(before_state, dict)
                    or before_state.get('protocol') != 1
                    or type(before_state.get('selection_epoch')) is not int
                    or (res_epoch is not None and before_state['selection_epoch'] != res_epoch)
                ):
                    return 0.0, 0.0, False, pres
                before_rec = checked_receipt(before_state.get('playback'))
                if (
                    before_rec is None
                    or before_rec.get('phase') != 'AV_STARTED'
                    or before_rec.get('request_id') != obs_req
                    or before_rec.get('native_instance') != obs_inst
                    or not before_rec.get('file_identity')
                    or (
                        isinstance(desired, dict)
                        and desired.get('file_identity')
                        and before_rec.get('file_identity') != desired.get('file_identity')
                    )
                    or before_rec.get('open_epoch') != before_state['selection_epoch']
                ):
                    return 0.0, 0.0, False, pres
                import xbmc
                player = xbmc.Player()
                if not player.isPlayingVideo():
                    return 0.0, 0.0, False, pres
                p_val, d_val = player.getTime(), player.getTotalTime()
                after_state = native_iface.state()
                after_rec = (
                    checked_receipt(after_state.get('playback'))
                    if isinstance(after_state, dict)
                    and after_state.get('protocol') == 1
                    and after_state.get('selection_epoch') == before_state['selection_epoch']
                    else None
                )
                if (
                    after_rec is None
                    or after_rec.get('phase') != 'AV_STARTED'
                    or any(
                        after_rec.get(k) != before_rec.get(k)
                        for k in ('request_id', 'native_instance', 'file_identity', 'open_epoch')
                    )
                ):
                    return 0.0, 0.0, False, pres
            else:
                exp = pres.get('expected') if isinstance(pres, dict) and pres.get('available') is True else None
                if (
                    not isinstance(exp, dict)
                    or exp.get('request_id') != obs_req
                    or exp.get('native_instance', obs_inst) != obs_inst
                ):
                    return 0.0, 0.0, False, pres
                import xbmc
                player = xbmc.Player()
                if not player.isPlayingVideo():
                    return 0.0, 0.0, False, pres
                p_val, d_val = player.getTime(), player.getTotalTime()

            if (
                isinstance(p_val, (int, float))
                and isinstance(d_val, (int, float))
                and math.isfinite(p_val)
                and math.isfinite(d_val)
                and 0 <= p_val <= d_val
                and 0 < d_val < 864000
            ):
                return float(p_val), float(d_val), True, pres
        except Exception:
            pass
        return 0.0, 0.0, False, pres

    def _owned_next_coordinator(self):
        host = getattr(self, 'host', None)
        if host is None:
            return None
        coord = getattr(host, 'owned_next', None)
        if coord is not None:
            return coord
        local = getattr(self, '_local_owned_next', None)
        if local is None:
            from bobbi_platform.owned_playback import OwnedNextCoordinator
            local = self._local_owned_next = OwnedNextCoordinator(
                stopping=getattr(host, 'stopping', None),
                profile_current=getattr(host, 'check_profile', None),
            )
        return local

    def drain_owned_next(self, timeout=1.0):
        coord = self._owned_next_coordinator()
        return True if coord is None else coord.wait_idle(timeout)

    def _prepare_owned_next_summary(self, boot_id, epoch, request_id, native_instance, account_scope, current_data):
        coord = self._owned_next_coordinator()
        if coord is None:
            return
        if getattr(self, '_owned_next_summaries', None) is None:
            self._owned_next_summaries = Queue(maxsize=8)
        def _resolve(cancelled):
            try:
                from bobbi_core.next_episode_summary import project
                from bobbi_platform.owned_playback import resolve_owned_next_result
                res = resolve_owned_next_result(
                    current_data,
                    dict(current_data['_owned_next']),
                    cancelled,
                    open_session=False,
                )
                if cancelled() or res.outcome == 'cancelled':
                    return
                summary = project(current_data, resolution=res)
                payload = {
                    'operation': 'next_summary',
                    'boot_id': boot_id,
                    'epoch': epoch,
                    'request_id': request_id,
                    'native_instance': native_instance,
                    'account_scope': account_scope,
                    'summary': summary,
                }
                if res.outcome == 'candidate' and isinstance(res.candidate, dict):
                    payload['_prefetched_candidate'] = dict(res.candidate)
                self._owned_next_summaries.put_nowait(payload)
            except Exception:
                pass
        coord.submit('summary', _resolve)

    def _capture_parent_continuation_context(self, current_data):
        captured = getattr(self, '_owned_terminal_parent', None)
        if isinstance(captured, dict) and captured.get('request_id'):
            return dict(captured)
        owner = getattr(getattr(self, 'authority', None), 'owner', None)
        desired = getattr(owner, 'desired', None) if owner is not None else None
        terminal = getattr(owner, 'terminal', None) if owner is not None else None
        req_id = (
            current_data.get('request_id')
            or (terminal.get('request_id') if isinstance(terminal, dict) else '')
            or (desired.get('request_id') if isinstance(desired, dict) else '')
        )
        inst = (
            terminal.get('native_instance')
            if isinstance(terminal, dict) and terminal.get('request_id', req_id) == req_id
            else ''
        )
        return {
            'boot_id': getattr(owner, 'boot_id', '') if owner is not None else '',
            'epoch': getattr(owner, 'epoch', 0) if owner is not None else 0,
            'request_id': req_id,
            'native_instance': inst,
            'account_scope': dict(current_data.get('_account') or {}),
            'prefetched_next': None,
        }

    def _local_owner_transport(self):
        from bobbi_core.playback_request import Client as PlaybackClient
        host = self.host
        playback_client = PlaybackClient(lambda msg, timeout=0.3: self.authority.dispatch(msg))

        def local_host_call(action, body, timeout=3):
            if host.stopping.is_set() or (hasattr(host, 'check_profile') and not host.check_profile()):
                raise OSError('PROFILE_CHANGED')
            if hasattr(host, '_dispatch'):
                return host._dispatch(action, body)
            if action == 'owned_playback_track':
                with host.lock:
                    host.owned_tracks[body['request_id']] = {
                        'account': dict(body['account']),
                        'data': dict(body['data']),
                        'cancelled': False,
                    }
                return {'tracked': True}
            if action == 'owned_playback_cancel':
                with host.lock:
                    entry = host.owned_tracks.get(body['request_id'])
                    if entry is not None:
                        entry['cancelled'] = True
                return {'cancelled': True}
            if action == 'status':
                return {'playback_adapter': 'native'}
            raise ValueError('UNSUPPORTED_LOCAL_HOST_ACTION')

        return playback_client, local_host_call

    def _authorize_and_reserve_owned_next(self, parent_ctx, current_data, candidate):
        from uuid import uuid4
        from bobbi_platform.owned_playback import OwnedPlaybackReservation, next_selection_identity
        host = getattr(self, 'host', None)
        if host is None or host.stopping.is_set() or (hasattr(host, 'check_profile') and not host.check_profile()):
            return None
        boot_id = parent_ctx.get('boot_id')
        epoch = parent_ctx.get('epoch')
        req_id = parent_ctx.get('request_id')
        inst = parent_ctx.get('native_instance')
        if not boot_id or type(epoch) is not int or not req_id or not inst:
            return None
        parent_key = (boot_id, epoch, req_id, inst)
        consumed = getattr(self, '_owned_next_consumed_parents', None)
        if consumed is None:
            consumed = self._owned_next_consumed_parents = []
        if parent_key in consumed:
            return None
        scope = dict(candidate.get('_account') or parent_ctx.get('account_scope') or {})
        pb_accounts = getattr(host, 'playback_accounts', None)
        if pb_accounts is not None and scope and not pb_accounts.is_current(scope):
            return None
        auth_accounts = getattr(self.authority, 'accounts', None)
        include_scope = bool(scope) and (auth_accounts is not None or getattr(self.authority, 'selection_account', None) is not None)
        sel_identity = next_selection_identity(candidate)
        grant = self.authority.dispatch({
            'operation': 'authorize_next',
            'boot_id': boot_id,
            'epoch': epoch,
            'request_id': req_id,
            'native_instance': inst,
            'selection_identity': sel_identity,
            **({'account_scope': scope} if include_scope else {}),
        })
        if not isinstance(grant, dict) or grant.get('authorized') is not True:
            return None
        consumed.append(parent_key)
        if len(consumed) > 32:
            del consumed[:-32]
        child_req_id = uuid4().hex
        reserved = self.authority.dispatch({
            'operation': 'reserve_child',
            'boot_id': boot_id,
            'epoch': epoch,
            'request_id': req_id,
            'token': grant['token'],
            'child_request_id': child_req_id,
            'selection_identity': sel_identity,
            **({'account_scope': scope} if include_scope else {}),
        })
        playback_client, local_host_call = self._local_owner_transport()
        return OwnedPlaybackReservation.from_child_reservation(
            reserved_snapshot=reserved,
            child_request_id=child_req_id,
            selection_identity=sel_identity,
            account_scope=scope,
            playback_client=playback_client,
            host_call=local_host_call,
        )

    def _submit_owned_child_reservation(self, child_res, candidate):
        host = getattr(self, 'host', None)
        if host is None:
            child_res.cancel()
            return False
        cancelled = lambda: (
            host.stopping.is_set()
            or (hasattr(host, 'check_profile') and not host.check_profile())
            or (
                getattr(host, 'playback_accounts', None) is not None
                and bool(child_res.account_scope)
                and not host.playback_accounts.is_current(child_res.account_scope)
            )
        )
        try:
            with child_res:
                child_res.submit(
                    -1,
                    candidate['url'],
                    title=candidate['title'],
                    source_meta=candidate.get('_owned_source'),
                    info=candidate.get('video_info'),
                    mime=candidate.get('mime'),
                    start_over=True,
                    next_candidate=candidate.get('_owned_next'),
                    ready=lambda: not cancelled(),
                )
            return True
        except Exception:
            return False

    def _spawn_owned_next_session_open(self, child_res, parent_ctx, current_data, spec):
        coord = self._owned_next_coordinator()
        if coord is None:
            child_res.cancel()
            return
        if getattr(self, '_owned_next_ready', None) is None:
            self._owned_next_ready = Queue(maxsize=4)

        def _open_work(cancelled):
            try:
                from bobbi_platform.owned_playback import resolve_owned_next_result
                is_cancelled = lambda: cancelled() or child_res.cancelled
                final_res = resolve_owned_next_result(current_data, spec, is_cancelled, open_session=True)
                self._owned_next_ready.put_nowait((child_res, parent_ctx, final_res))
            except Exception:
                try:
                    from bobbi_core.next_episode_summary import NextResolution
                    self._owned_next_ready.put_nowait((child_res, parent_ctx, NextResolution('error')))
                except Exception:
                    pass

        if not coord.submit('session_open', _open_work, singleton=True):
            child_res.cancel()

    def _drain_owned_next_queues(self):
        from bobbi_platform.owned_playback import next_selection_identity
        cand_q = getattr(self, '_owned_next_candidates', None)
        if cand_q is not None:
            while True:
                try:
                    parent_ctx, current_data, res = cand_q.get_nowait()
                except Empty:
                    break
                try:
                    if res.outcome != 'candidate' or not isinstance(res.candidate, dict):
                        continue
                    child_res = self._authorize_and_reserve_owned_next(parent_ctx, current_data, res.candidate)
                    if child_res is None:
                        continue
                    if res.candidate.get('_next_recheck'):
                        self._spawn_owned_next_session_open(
                            child_res,
                            parent_ctx,
                            current_data,
                            dict(current_data['_owned_next']),
                        )
                    else:
                        self._submit_owned_child_reservation(child_res, res.candidate)
                except Exception:
                    pass

        ready_q = getattr(self, '_owned_next_ready', None)
        if ready_q is not None:
            while True:
                try:
                    child_res, _parent_ctx, final_res = ready_q.get_nowait()
                except Empty:
                    break
                try:
                    if (
                        final_res.outcome != 'candidate'
                        or not isinstance(final_res.candidate, dict)
                        or next_selection_identity(final_res.candidate) != child_res.selection_identity
                    ):
                        child_res.cancel()
                        continue
                    self._submit_owned_child_reservation(child_res, final_res.candidate)
                except Exception:
                    child_res.cancel()

    def _launch_owned_next(self, current_data):
        host = getattr(self, 'host', None)
        coord = self._owned_next_coordinator()
        if host is None or coord is None or not isinstance(current_data, dict) or not isinstance(current_data.get('_owned_next'), dict):
            return
        if coord.has_active_kind('candidate') or coord.has_active_kind('session_open'):
            return
        if getattr(self, '_owned_next_candidates', None) is None:
            self._owned_next_candidates = Queue(maxsize=4)
        if getattr(self, '_owned_next_ready', None) is None:
            self._owned_next_ready = Queue(maxsize=4)

        parent_ctx = self._capture_parent_continuation_context(current_data)
        spec = dict(current_data['_owned_next'])
        prefetched = parent_ctx.get('prefetched_next')
        if isinstance(prefetched, dict):
            try:
                child_res = self._authorize_and_reserve_owned_next(parent_ctx, current_data, prefetched)
            except Exception:
                child_res = None
            if child_res is None:
                return
            if prefetched.get('_next_recheck'):
                self._spawn_owned_next_session_open(child_res, parent_ctx, current_data, spec)
            else:
                self._submit_owned_child_reservation(child_res, prefetched)
            return

        def _work(cancelled):
            try:
                from bobbi_platform.owned_playback import resolve_owned_next_result
                res = resolve_owned_next_result(current_data, spec, cancelled, open_session=False)
                if cancelled() or res.outcome == 'cancelled':
                    return
                self._owned_next_candidates.put_nowait((parent_ctx, dict(current_data), res))
            except Exception:
                pass

        coord.submit('candidate', _work, singleton=True)

    def close(self):
        if hasattr(self, 'next_display'):
            self.next_display.clear()
        close_io = getattr(self.native, 'close', None)
        errors = []
        drained_next = True
        local_next = getattr(self, '_local_owned_next', None)
        if local_next is not None:
            drained_next = bool(local_next.close())
        def drain(action):
            try:
                action()
            except BaseException as error:
                errors.append(error)
        if close_io is not None:
            drain(close_io)
        for connection in tuple(self.clients):
            drain(lambda connection=connection: self._close_client(connection))
        if self.selector is not None:
            drain(self.selector.close)
        if self.listener is not None:
            drain(self.listener.close)
        if self.path is not None and self.path.exists() and self.path.stat().st_ino == self.inode:
            self.path.unlink()
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if errors:
            raise errors[0]
        return drained_next

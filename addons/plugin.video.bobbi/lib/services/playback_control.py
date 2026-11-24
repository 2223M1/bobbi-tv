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
        self._owned_next_worker = None
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
        if host is None or not getattr(host, 'owned_tracks', None):
            return
        observed = getattr(self.authority.owner, 'observed', None)
        obs_req = observed.get('request_id') if isinstance(observed, dict) else None
        obs_inst = observed.get('native_instance') if isinstance(observed, dict) else None
        obs_phase = observed.get('phase') if isinstance(observed, dict) else None

        prev = self._owned_state
        if prev is not None:
            with host.lock:
                prev_track = host.owned_tracks.get(prev['request_id'])
            prev_cancelled = prev_track is None or bool(prev_track.get('cancelled'))
            same_instance = obs_req == prev['request_id'] and obs_inst == prev['native_instance']
            if prev_cancelled or not same_instance or obs_phase == 'TERMINAL':
                reason = 'SUPERSEDED'
                pos, dur = prev['position'], prev['duration']
                obs_clock = prev['observed_clock']
                if same_instance and obs_phase == 'TERMINAL':
                    reason = str(observed.get('reason') or 'STOP')
                    comp = observed.get('completion_observation')
                    if isinstance(comp, dict):
                        cpos, cdur = comp.get('position'), comp.get('duration')
                        if isinstance(cpos, (int, float)) and isinstance(cdur, (int, float)) and cdur > 0:
                            pos, dur, obs_clock = float(cpos), float(cdur), True
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
                    self._launch_owned_next(prev['data'])

        if not obs_req or not obs_inst or obs_phase != 'AV_STARTED':
            return
        with host.lock:
            tracked = host.owned_tracks.get(obs_req)
        if not tracked or tracked.get('cancelled') or not isinstance(tracked.get('data'), dict):
            return
        first = self._owned_state is None or self._owned_state['native_instance'] != obs_inst
        if not first and now < self._owned_poll_due:
            return
        self._owned_poll_due = now + 1.0
        pos, dur, obs_clock = 0.0, 0.0, False
        try:
            import xbmc
            player = xbmc.Player()
            if player.isPlayingVideo():
                p_val, d_val = player.getTime(), player.getTotalTime()
                if (
                    isinstance(p_val, (int, float))
                    and isinstance(d_val, (int, float))
                    and 0 <= p_val <= d_val
                    and 0 < d_val < 864000
                ):
                    pos, dur, obs_clock = float(p_val), float(d_val), True
        except Exception:
            pass
        cur_paused = bool(observed.get('paused', False))
        if first:
            self._owned_state = {
                'request_id': obs_req,
                'native_instance': obs_inst,
                'account': dict(tracked['account']),
                'data': dict(tracked['data']),
                'position': pos,
                'duration': dur,
                'observed_clock': obs_clock,
                'paused': cur_paused,
                'last_obs_at': now,
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
            return

        st = self._owned_state
        prev_paused = st['paused']
        prev_pos = st['position']
        prev_obs = st['last_obs_at']
        if obs_clock:
            st['position'] = pos
            st['duration'] = dur
            st['observed_clock'] = True
        st['paused'] = cur_paused
        st['last_obs_at'] = now

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

    def _launch_owned_next(self, current_data):
        host = getattr(self, 'host', None)
        if host is None or (self._owned_next_worker is not None and self._owned_next_worker.is_alive()):
            return
        from threading import Thread
        def _work():
            try:
                import xbmc
                from bobbi_platform.owned_playback import reserve_playback, resolve_owned_next
                cancelled = lambda: host.stopping.is_set() or not host.check_profile()
                spec = dict(current_data['_owned_next'])
                nxt = resolve_owned_next(current_data, spec, cancelled)
                if not nxt or cancelled() or xbmc.Player().isPlaying():
                    return
                with reserve_playback(
                    f"emby-next://{nxt['_owned_source']['source_id']}/{nxt['_owned_source']['item_id']}",
                    nxt['_account'],
                ) as res:
                    res.submit(
                        -1,
                        nxt['url'],
                        title=nxt['title'],
                        source_meta=nxt['_owned_source'],
                        info=nxt.get('video_info'),
                        mime=nxt.get('mime'),
                        start_over=True,
                        next_candidate=nxt.get('_owned_next'),
                        ready=lambda: not cancelled() and not xbmc.Player().isPlaying(),
                    )
            except Exception:
                pass
        self._owned_next_worker = Thread(target=_work, name='bobbi-native-owned-next', daemon=True)
        self._owned_next_worker.start()

    def close(self):
        if hasattr(self, 'next_display'):
            self.next_display.clear()
        close_io = getattr(self.native, 'close', None)
        errors = []
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

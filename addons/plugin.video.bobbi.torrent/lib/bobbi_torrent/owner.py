"""Use the one current bobbi owner; properties convey cancellation, never rights."""
import hashlib
import json
import math
import re

from .backend import BackendError, MAX_DIAGNOSTIC_NUMBER


class Owner:
    def __init__(self, request_id, protocol=None, window=None, monitor=None):
        if not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id):
            raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
        if protocol is None:
            from bobbi_core import playback_request as protocol
        if window is None or monitor is None:
            import xbmc
            import xbmcgui
            window = window or xbmcgui.Window(10000)
            monitor = monitor or xbmc.Monitor()
        self.request_id, self.protocol = request_id, protocol
        self.window, self.monitor = window, monitor
        self.failure_attempted = False
        self.ready_probe = None

    def prepared_source_ready(self, request, info_hash, file, deadline):
        if 'ready_context' not in request:
            return False
        self.active()
        try:
            from bobbi_core.prepared_retry import ReadyProbe, decode_context
            if self.ready_probe is None:
                self.ready_probe = ReadyProbe(decode_context(request['ready_context'], self.request_id))
            ready = self.ready_probe.poll(info_hash, file, self.cancelled, deadline)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            ready = False  # Optional lookup failure leaves ordinary buffering intact.
        self.active()  # Cancellation or a new selection always wins the poll.
        return ready

    def cancelled(self):
        return (self.monitor.abortRequested()
            or self.window.getProperty('bobbi_active_player_session') != self.request_id
            or self.window.getProperty('bobbi_cinema_cancel') == self.request_id)

    def active(self):
        if self.monitor.abortRequested():
            raise BackendError('TORRENT_ABORTED', 'aborted')
        if self.window.getProperty('bobbi_cinema_cancel') == self.request_id:
            raise BackendError('TORRENT_CANCELLED', 'cancelled')
        if self.window.getProperty('bobbi_active_player_session') != self.request_id:
            raise BackendError('TORRENT_SUPERSEDED', 'superseded')
        # No property can grant admission; this reads the current native owner.
        try:
            return self.protocol.owned_state(self.request_id)
        except (OSError, RuntimeError, ValueError):
            raise BackendError('TORRENT_OWNER_UNAVAILABLE', 'superseded') from None

    def wait(self, seconds):
        try:
            finite = type(seconds) in (int, float) and math.isfinite(seconds)
        except OverflowError:
            finite = False
        if not finite:
            raise BackendError('TORRENT_WAIT_INVALID', 'invalid_request')
        # Kodi treats zero/negative timeouts as an unbounded wait. A deadline
        # can expire between the resolver's last check and this call; let the
        # original loop report that timeout after checking current ownership.
        if seconds > 0 and self.monitor.waitForAbort(seconds):
            raise BackendError('TORRENT_ABORTED', 'aborted')
        self.active()

    def progress(self, phase, percent=0):
        self.active()
        self.window.setProperty('bobbi_cinema_progress', json.dumps(dict(
            session=self.request_id, request_id=self.request_id,
            phase=phase, percent=max(0, min(100, int(percent))))))

    def selected(self, info_hash, file, final_url=None):
        self.active()
        payload = dict(session=self.request_id, request_id=self.request_id,
            source_info_hash=info_hash, torrent_file_id=file['id'],
            torrent_path=file['path'], torrent_file_bytes=file['length'])
        name = 'bobbi_cinema_preparation_target'
        if final_url is not None:
            payload['url_sha256'] = hashlib.sha256(final_url.encode('utf-8')).hexdigest()
            name = 'bobbi_cinema_target'
        self.window.setProperty(name, json.dumps(payload))

    def diagnostic(self, detail):
        import xbmc
        from .entry import failure_log
        xbmc.log(failure_log(BackendError('TORRENT_STAGE_OBSERVED', diagnostic=detail),
                            self.request_id), xbmc.LOGINFO)

    def wait_for_buffer(self, detail):
        import xbmcgui
        self.active()
        self.diagnostic(dict(detail, stage='buffering'))
        speed = detail.get('download_bps')
        rate = ('{:,} B/s'.format(speed) if type(speed) is int
                and 0 <= speed <= MAX_DIAGNOSTIC_NUMBER else '未知')
        answer = xbmcgui.Dialog().yesno('片源已定位，BT 供数仍不足',
            'BT 总下载速度：' + rate + '（非所选文件实测）\n'
            '当前等待的是你选定的文件，不会换版或降低画质。\n'
            '种子总缓存不能证明所选文件已连续读到；可继续等一轮，或返回选源。',
            nolabel='返回选源', yeslabel='继续等待一轮', autoclose=30000)
        self.active()  # A newer selection/stop while the dialog was up wins.
        return answer

    def choose_file(self, files):
        import xbmcgui
        from bobbi_core.torrent_startup import FILE_CHOICE_SECONDS
        self.active()
        # No preselection or timeout default. A choice means this file only,
        # never an assertion that its release/episode has been auto-verified.
        choice = xbmcgui.Dialog().select('无法自动确定正片 · 请核对真实文件（不自动续播）',
            ['%s  ·  %.2f GiB' % (f['path'].replace('[', '［').replace(']', '］'),
                                  f['length'] / 1024**3) for f in files], autoclose=FILE_CHOICE_SECONDS * 1000)
        self.active()
        return dict(files[choice]) if type(choice) is int and 0 <= choice < len(files) else None

    def bind(self, item, info_hash, file, url, resolution, original_audio_hint='',
             file_evidence='AUTO_VERIFIED_FILE'):
        self.active()
        p, request_id = self.protocol, self.request_id
        identity = p.resolved_torrent_file_identity(request_id, resolution, info_hash,
            file['id'], file['path'], file['length'])
        context = p.bind_and_claim(request_id, identity, url, self.cancelled, 'resolved_url',
                                   file_evidence=file_evidence)
        self.active()
        item.setProperty('bobitv.request_id', request_id)
        item.setProperty('bobitv.file_identity', identity)
        try:
            from time import time
            from bobbi_core.original_audio import attach
            attach(item, original_audio_hint, context, url, time())
        except Exception:
            pass  # Preference is not video admission.
        try:
            p.call(dict({k: context[k] for k in ('boot_id', 'epoch', 'request_id')},
                operation='torrent_subtitle_context', torrent=dict(info_hash=info_hash,
                    file={k: file[k] for k in ('id', 'path', 'length')})))
        except (OSError, RuntimeError, ValueError):
            pass  # Subtitle discovery is optional and remains off the video path.
        return context

    def failure(self, category):
        if self.failure_attempted:
            return False
        self.failure_attempted = True
        try:
            snapshot = self.protocol.owned_state(self.request_id)
            context = self.protocol.context(snapshot, self.request_id)
            return self.protocol.call(dict(context, operation='resolver_failed',
                category=category)).get('recorded') is True
        except (OSError, RuntimeError, ValueError):
            return False  # Never signal a newer request or revive an old owner.

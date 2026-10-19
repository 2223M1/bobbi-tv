# -*- coding: utf-8 -*-
"""Long-lived service: bind 54321 and serve the static MPD file.

In v0.4.0 this is the PRIMARY listener. The addon.py daemon-thread
fallback kicks in only when this service fails to bind (which
happens if service.py crashes or isn't started by Kodi).

Diagnostic philosophy: any failure in this file must surface in
xbmc.log. Service processes in Kodi are otherwise silent; if the
import chain breaks at startup, we have no way to know without
explicit try/except + log.
"""
import sys
import threading
import traceback


# ── Top-level diagnostic: import xbmc FIRST so we can log later ──
try:
    import xbmc
    xbmc.log('[plugin.video.bili] service: import xbmc OK', xbmc.LOGINFO)
except Exception:
    sys.stderr.write('plugin.video.bili service: FATAL cannot import xbmc\n')
    sys.stderr.write(traceback.format_exc() + '\n')
    sys.exit(1)

# ── Phase 1: xbmcvfs (needed by http_server) ──
try:
    import xbmcvfs
    xbmc.log('[plugin.video.bili] service: import xbmcvfs OK', xbmc.LOGINFO)
except Exception as e:
    xbmc.log('[plugin.video.bili] service: FATAL import xbmcvfs: %s\n%s' % (
        e, traceback.format_exc()), xbmc.LOGERROR)
    sys.exit(1)

# ── Phase 2: mpd_server ──
try:
    from playback.mpd_server import get_mpd_server
    xbmc.log('[plugin.video.bili] service: import mpd_server OK', xbmc.LOGINFO)
except Exception as e:
    xbmc.log('[plugin.video.bili] service: FATAL import mpd_server: %s\n%s' % (
        e, traceback.format_exc()), xbmc.LOGERROR)
    sys.exit(1)

# Live danmaku is intentionally NOT imported here. service.py used
# to call stop_all_live_danmaku() at shutdown, but that requires
# importing live.danmaku which pulls in xbmcvfs + zlib + thread +
# WebSocket deps. None of those are needed for serving the MPD.
# The danmaku threads' atexit hook handles cleanup on their own.


REFRESH_INTERVAL_S = 50 * 60  # 50 分钟调一次 API 拿新 m3u8 URL
                              # service.py 的 /live-m3u8/<room_id> 端点每次
                              # ffmpeg 来拉时都实时转发 CDN 拿新 sliding window，
                              # 因此 m3u8 manifest 内容不需要 daemon 主动刷新。
                              # 这里只是给 storage 里的 m3u8_url 续命，避免
                              # B 站 CDN 的 m3u8 URL 自身 expires (~1-2h) 过期。


class _LiveRefreshDaemon:
    """service.py 长跑进程内的 daemon 线程。

    每 50 分钟读 storage 拿当前 room_id，调 B 站 getRoomPlayInfo 拿新
    m3u8 URL → 写到 storage[room_id]['m3u8_url']。

    storage['live_refresh_state'] 数据形态：
        {
            <room_id>: {'m3u8_url': 'https://...bilivideo.com/.../index.m3u8?...'}
        }

    service.py 的 m3u8 转发端点 (/live-m3u8/<room_id>) 每次收到 ffmpeg
    请求时实时从 storage 读 m3u8_url，调 fetch_url_text 拉 B 站 CDN 当下
    一帧 sliding window，返回给 ffmpeg。ffmpeg HLS demuxer 每 ~4s
    refresh playlist，行为与"直拉 CDN"完全一致 —— segment URL 永远
    fresh，无 EOF、无 60 分钟 TRID 过期。

    daemon 线程本身不需要写 m3u8 manifest 内容（service.py 每次都实时
    fetch）。daemon 的任务只是**给 storage 里的 m3u8_url 续命**：B 站
    m3u8 URL 自身有 expires (~1-2h)，50 分钟 refresh 一次确保 storage
    里的 URL 在 expires 之前被替换。

    进程退出条件：
    - Kodi 关闭 → waitForAbort → 线程死
    - service.py run() finally → 线程死（不显式 stop）
    """
    def __init__(self):
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        xbmc.log('[live.refresh] daemon started', xbmc.LOGINFO)
        while not self._stop.is_set():
            try:
                self._refresh_all()
            except Exception as e:
                xbmc.log(
                    '[live.refresh] daemon error: %s\n%s' % (
                        e, traceback.format_exc(),
                    ), xbmc.LOGERROR,
                )
            # waitForAbort 语义：返回 True 表示 abort
            if self._stop.wait(REFRESH_INTERVAL_S):
                break
        xbmc.log('[live.refresh] daemon exited', xbmc.LOGINFO)

    def _refresh_all(self):
        """读 storage，给当前在播的房间的 m3u8_url 续命。"""
        from core import plugin

        # 必须用 read_storage（每次从 disk 读），不能用 get_storage 的
        # 进程内 cache：addon.py 写完后 service.py 内存 cache 看不到新值。
        state = plugin.read_storage('live_refresh_state')
        if not state:
            return

        # 早退出：player 没在播直播就跳过整个循环（避免无谓 API 调用）。
        # xbmc.getInfoLabel 在 fail-safe 上下文返回 ''，不需要 try/except。
        playing_path = xbmc.getInfoLabel('Player.Filenameandpath') or ''
        if '/live/' not in playing_path:
            return

        modified = False
        for room_id, entry in state.items():
            if not isinstance(entry, dict):
                continue
            # storage 残留：player 在播别的房间，跳过这个 room
            if '/%s' % room_id not in playing_path:
                continue
            if self._refresh_one(room_id, state):
                modified = True

        if modified:
            plugin.write_storage('live_refresh_state', state)

    def _refresh_one(self, room_id, state):
        """调 getRoomPlayInfo 拿新 m3u8 URL，更新 state[room_id]['m3u8_url']。

        返回 True 表示 state 有改动（caller 负责写回 disk）。
        失败时直接返回 False —— 下一轮 50 分钟后再试，避免在一个
        cycle 内阻塞 daemon。
        """
        from routes.live import fetch_live_m3u8_url

        try:
            new_url = fetch_live_m3u8_url(room_id, qn=10000)
        except Exception as e:
            xbmc.log(
                '[live.refresh] room=%s: API exception: %s' % (room_id, e),
                xbmc.LOGDEBUG,
            )
            return False

        if not new_url:
            xbmc.log(
                '[live.refresh] room=%s: getRoomPlayInfo returned no URL' % (
                    room_id,
                ),
                xbmc.LOGWARNING,
            )
            return False

        if new_url == state[room_id].get('m3u8_url', ''):
            xbmc.log(
                '[live.refresh] room=%s: m3u8_url unchanged' % room_id,
                xbmc.LOGDEBUG,
            )
            return False

        state[room_id]['m3u8_url'] = new_url
        xbmc.log(
            '[live.refresh] room=%s: m3u8_url renewed' % room_id,
            xbmc.LOGINFO,
        )
        return True


def run():
    from utils import getSetting  # 推迟到 run() 再 import，启动时少解析一个模块
    try:
        port = int(getSetting('server_port') or 54321)
    except Exception as e:
        xbmc.log(
            '[plugin.video.bili] service: cannot read server_port: %s; '
            'falling back to 54321' % e, xbmc.LOGWARNING,
        )
        port = 54321

    try:
        httpd = get_mpd_server(port=port)
    except Exception as e:
        xbmc.log(
            '[plugin.video.bili] service: FATAL get_mpd_server: %s\n%s' % (
                e, traceback.format_exc(),
            ), xbmc.LOGERROR,
        )
        return

    if not httpd:
        xbmc.log(
            '[plugin.video.bili] service: bind FAILED on :%s — port held '
            'by another process' % port, xbmc.LOGERROR,
        )
        return

    # Monitor.onSettingsChanged() 在用户改本插件设置并点确定时触发。
    # Kodi 默认不会自动重跑 plugin 列表（用户回到菜单看到的是改之前的
    # 状态），这里主动 Container.Refresh 强制重新求值 function.* 开关。
    # 必须用子类覆盖 onSettingsChanged 钩子；Kodi 在 settings dialog
    # close 后从内部线程调一次，waitForAbort 不会阻塞它。
    class _SettingsMonitor(xbmc.Monitor):
        def onSettingsChanged(self):
            xbmc.log(
                '[plugin.video.bili] service: onSettingsChanged -> Container.Refresh',
                xbmc.LOGINFO,
            )
            xbmc.executebuiltin('Container.Refresh')

    monitor = _SettingsMonitor()
    refresh_daemon = _LiveRefreshDaemon()
    refresh_thread = threading.Thread(
        target=refresh_daemon.run,
        daemon=True,
        name='live-refresh-daemon',
    )
    refresh_thread.start()
    xbmc.log(
        '[plugin.video.bili] service: MPD server listening on 0.0.0.0:%s' % port,
        xbmc.LOGINFO,
    )

    try:
        while not monitor.abortRequested():
            httpd.handle_request()
            if monitor.waitForAbort(0.5):
                break
    except Exception as e:
        xbmc.log(
            '[plugin.video.bili] service: serve loop error: %s\n%s' % (
                e, traceback.format_exc(),
            ), xbmc.LOGERROR,
        )
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass


if __name__ == '__main__':
    run()

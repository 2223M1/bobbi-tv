# -*- coding: utf-8 -*-
"""HTTP server bound to 0.0.0.0:54321 by service.py / addon.py.

Two responsibilities:
  1. Serve static `{cid}.mpd` files (DASH manifest) to
     inputstream.adaptive for vod playback. The MPD lives in
     special://temp/plugin.video.bili/<cid>.mpd and contains absolute
     CDN segment URLs (no segment proxy needed in v0.4.0+).

  2. Live m3u8 forwarding proxy at `/live-m3u8/<room_id>`: every ffmpeg
     HLS playlist refresh hits this endpoint, which reads the current
     cdn m3u8_url from disk storage and re-fetches the manifest from
     B 站. This gives ffmpeg the same sliding-window freshness as if it
     were talking to the CDN directly, sidestepping the 60-min CDN
     TRID expiry and the static-file EOF problem.

Bind lifecycle is owned by the caller (service.py primary,
addon.py daemon-thread fallback). This module just provides the
request handler class and the bind helper.
"""
from http import server as BaseHTTPServer
import os
import re
import socket
import xbmc
import xbmcvfs

from core import plugin
from api import fetch_url_text
from utils import rewrite_m3u8_relative_urls


class BilibiliRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.addon_id = 'plugin.video.bili'
        try:
            self.base_path = xbmcvfs.translatePath(
                'special://temp/%s' % self.addon_id
            ).decode('utf-8')
        except AttributeError:
            self.base_path = xbmcvfs.translatePath(
                'special://temp/%s' % self.addon_id
            )
        self.base_path = os.path.realpath(self.base_path)
        self.chunk_size = 1024 * 64
        BaseHTTPServer.BaseHTTPRequestHandler.__init__(
            self, request, client_address, server,
        )

    def _safe_file_path(self, url_path):
        """Resolve a URL path to a local file under special://temp/<addon_id>.

        Returns the absolute file path or None if the path is unsafe or
        doesn't end in `.mpd`. The path-traversal guard follows the
        v0.3.0 implementation.
        """
        qpos = url_path.find('?')
        if qpos != -1:
            url_path = url_path[:qpos]
        if not url_path.endswith('.mpd'):
            return None
        safe = url_path.strip('/').strip('\\')
        parts = [p for p in safe.replace('\\', '/').split('/') if p and p != '..']
        safe = '/'.join(parts)
        file_path = os.path.join(self.base_path, safe)
        file_path = os.path.realpath(file_path)
        if (
            not file_path.startswith(self.base_path + os.sep)
            and file_path != self.base_path
        ):
            return None
        return file_path

    def _send_mpd(self, file_path):
        """公共：发送 MPD 文件内容（GET 用 stream，HEAD 用 header-only）。"""
        if not os.path.isfile(file_path):
            self.send_error(404, 'File Not Found')
            return
        size = os.path.getsize(file_path)
        self.send_response(200)
        # inputstream.adaptive needs the standard DASH MIME type
        # to auto-detect the manifest format. application/xml+dash
        # is non-standard and adaptive rejects it.
        self.send_header('Content-Type', 'application/dash+xml')
        self.send_header('Content-Length', size)
        self.end_headers()
        # GET 时 method 不是 HEAD 才写 body
        if self.command != 'HEAD':
            try:
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(self.chunk_size)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except IOError:
                pass

    def _proxy_live_m3u8(self, room_id):
        """实时转发 B 站 CDN m3u8 给 ffmpeg。

        ffmpeg HLS demuxer 每 ~4s refresh playlist，每次访问本端点时：
        1. 从 storage 读当前 room_id 对应的 cdn m3u8 URL
        2. fetch CDN 拿最新一帧 sliding window
        3. 改写相对路径 segment URL 为绝对路径（防 ffmpeg 拼本地 base）
        4. 返回 application/vnd.apple.mpegurl 给 ffmpeg

        行为跟直接拉 CDN 完全一致（每次都 fresh），ffmpeg 永远拿到
        最新 segment URL → 无 EOF、无 60 分钟 TRID 过期。

        B 站 m3u8 URL 自身有效期 ~1-2 小时（看 query 里 expires=）。
        service.py daemon 线程每 50 分钟调 getRoomPlayInfo 拿新 m3u8 URL
        更新到 storage，保证 CDN 端不会因 m3u8 URL 过期而 403。
        """
        state = plugin.read_storage('live_refresh_state')
        entry = state.get(room_id)
        if not isinstance(entry, dict):
            self.send_error(404, 'No live stream state for room %s' % room_id)
            return
        cdn_m3u8_url = entry.get('m3u8_url', '') or ''
        if not cdn_m3u8_url:
            self.send_error(503, 'm3u8_url not initialized')
            return

        try:
            text = fetch_url_text(cdn_m3u8_url)
            text = rewrite_m3u8_relative_urls(text, cdn_m3u8_url)
        except Exception as e:
            xbmc.log(
                '[mpd_server] proxy live m3u8 failed room=%s: %s' % (
                    room_id, e,
                ),
                xbmc.LOGWARNING,
            )
            self.send_error(502, 'CDN fetch failed')
            return

        try:
            body = text.encode('utf-8')
            self.send_response(200)
            self.send_header(
                'Content-Type', 'application/vnd.apple.mpegurl',
            )
            self.send_header('Content-Length', str(len(body)))
            self.send_header(
                'Cache-Control', 'no-store, no-cache, must-revalidate',
            )
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            # HEAD 请求只发 header（与 _send_mpd 一致；不然 HEAD probe
            # 会触发 CDN fetch + body 写，浪费带宽 + 卡 service.py 线程）
            if self.command != 'HEAD':
                self.wfile.write(body)
        except IOError:
            # 客户端提前断连（ffmpeg 切流），安静忽略
            pass

    def do_GET(self):
        # 现有 MPD 端点
        if self.path.endswith('.mpd'):
            file_path = self._safe_file_path(self.path)
            if file_path:
                self._send_mpd(file_path)
                return
            self.send_error(403, 'Forbidden')
            return

        # Live m3u8 端点 `/live-m3u8/<room_id>` —— 实时转发 B 站 CDN
        m = re.match(r'^/live-m3u8/(\d+)/?$', self.path)
        if m:
            room_id = m.group(1)
            self._proxy_live_m3u8(room_id)
            return

        self.send_error(404, 'Not Found')

    def do_HEAD(self):
        # HEAD 走和 GET 一样的逻辑；_send_* 看 self.command 决定是否发 body
        self.do_GET()

    def log_message(self, format, *args):
        # Silence BaseHTTPServer's stderr logger; Kodi logs are sufficient.
        return


def get_mpd_server(port=None):
    """Bind and return a HTTPServer. Caller is responsible for serving.

    `port` defaults to 54321 (the historical default and Kodi addon
    setting default). Returns None if the bind fails (port already in use).

    SO_REUSEADDR is enabled on the server class so that the OS lets
    us rebind a port that is still in TIME_WAIT from a recently
    dead CPythonInvoker process. Without this, every navigation
    after the first one logs 'bind FAILED' until the OS reclaims the
    port.
    """
    port = int(port) if port else 54321
    try:
        # Set the class attribute before instantiating so the
        # socketserver base picks it up during bind().
        BaseHTTPServer.HTTPServer.allow_reuse_address = True
        server = BaseHTTPServer.HTTPServer(
            ('0.0.0.0', port), BilibiliRequestHandler,
        )
        return server
    except socket.error:
        return None

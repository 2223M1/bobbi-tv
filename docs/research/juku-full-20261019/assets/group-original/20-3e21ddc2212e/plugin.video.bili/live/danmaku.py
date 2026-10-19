# -*- coding:utf-8 -*-
"""B 站直播弹幕 ASS 叠加。

流程：
1. WBI 签名请求 getDanmuInfo 获取 token + host_list
2. ws:// 连接弹幕服务器，发送认证包（含 token + buvid）
3. 实时接收 DANMU_MSG → 构造 danmaku2ass 格式 → 写盘 + 周期性 setSubtitles
   触发 libass 重读（让 Kodi 渲染最新弹幕）
"""
import base64
import io
import json
import os
import re
import socket
import struct
import threading
import time
import zlib

import xbmc

from utils import getSetting, get_temp_path
from subtitle.danmaku2ass import ProcessComments, CalculateLength


# ── WebSocket 工具 ────────────────────────────────────────────────────

def _ws_send(sock, data):
    """发送 WebSocket 二进制帧（client → server 需要 mask）。"""
    if isinstance(data, str):
        data = data.encode('utf-8')
    frame = bytearray([0x82])  # FIN + binary
    length = len(data)
    if length < 126:
        frame.append(0x80 | length)
    elif length < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack('>H', length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack('>Q', length))
    mask_key = os.urandom(4)
    frame.extend(mask_key)
    frame.extend(bytes(b ^ mask_key[i % 4] for i, b in enumerate(data)))
    sock.send(bytes(frame))


def _bili_packet(opcode, body=b''):
    """B 站二进制协议包：16 字节头 + body。"""
    if isinstance(body, str):
        body = body.encode('utf-8')
    return struct.pack('>IHHII', 16 + len(body), 16, 1, opcode, 1) + body


# ── 客户端 ────────────────────────────────────────────────────────────

class LiveDanmakuClient:
    def __init__(self, room_id, ass_path, uid=0, cookie='',
                 font_size=25, opacity=1.0, stay_time=8, display_area=1.0,
                 buvid=''):
        self.room_id      = int(room_id)
        self.ass_path     = ass_path
        self.uid          = int(uid) if uid else 0
        self._cookie      = cookie
        self._buvid       = buvid
        self.font_size    = float(font_size)
        self._opacity     = float(opacity)
        self.stay_time    = float(stay_time)
        self.display_area = float(display_area)

        self.running      = False
        self._connected   = False  # True once WebSocket auth OK
        self.sock         = None
        # _start_time 在 __init__ 立即设（不等 WS auth）。timeline =
        # time.time() - _start_time 必须跟 Kodi PTS 起点错位最小，
        # 否则 libass 看到事件 Start 远小于 now（Kodi PTS），全部
        # 过期。__init__ 在 set_resolved_url 之前立即执行，错位 0~5s。
        self._start_time  = time.time()
        # 喂给 ProcessComments 的格式（9 字段，ProcessComments 按位置
        # 索引 [0]/[3]/[4]/[7]/[8]，c[1]/c[2] 是 dead slot，保留 None 占位）：
        #   (timeline, _, _, text, pos, color, size_px, height_px, width_px)
        # pos: 0=滚动, 1=底部居中, 2=顶部居中, 3=反向滚动
        self.danmaku_list = []
        self.lock         = threading.Lock()

    def _get_token_wbi(self):
        """WBI 签名请求 getDanmuInfo。"""
        try:
            from api import getWbiKeys, encWbi
            import requests
            params = encWbi({'id': str(self.room_id), 'type': '0'}, *getWbiKeys())
            full_url = 'https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo'
            h = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://live.bilibili.com/',
            }
            if self._cookie:
                h['Cookie'] = self._cookie
            r = requests.get(full_url, params=params, headers=h, timeout=10)
            data = r.json()
            xbmc.log('[live.danmaku] getDanmuInfo code=%s' % data['code'], xbmc.LOGDEBUG)
            if data['code'] == 0:
                return data['data']
        except Exception as e:
            xbmc.log('[live.danmaku] _get_token_wbi: %s' % str(e), xbmc.LOGWARNING)
        return None

    def _connect(self, host, port):
        """ws:// TCP 直连（不使用 websockets 库以减少依赖）。"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(8)
            sock.connect((host, port))
            key = base64.b64encode(os.urandom(16)).decode()
            req = (
                f'GET /sub HTTP/1.1\r\nHost: {host}\r\n'
                f'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                f'Sec-WebSocket-Key: {key}\r\n'
                f'Sec-WebSocket-Version: 13\r\n\r\n'
            )
            sock.send(req.encode())
            resp = b''
            while b'\r\n\r\n' not in resp:
                chunk = sock.recv(4096)
                if not chunk:
                    sock.close()
                    return None
                resp += chunk
            if b'101' not in resp:
                sock.close()
                return None
            self.sock = sock
            xbmc.log('[live.danmaku] ws connected %s:%s' % (host, port), xbmc.LOGDEBUG)
            return sock
        except Exception as e:
            xbmc.log('[live.danmaku] _connect: %s' % str(e), xbmc.LOGWARNING)
            return None

    def _send_auth(self, token):
        body = json.dumps({
            'uid':      self.uid,
            'roomid':   self.room_id,
            'protover': 2,
            'buvid':    self._buvid or '',
            'platform': 'web',
            'type':     2,
            'key':      token,
        })
        _ws_send(self.sock, _bili_packet(7, body))
        xbmc.log('[live.danmaku] auth sent', xbmc.LOGDEBUG)

    # ── 协议解析 → danmaku2ass 格式 ─────────────────────────────────────

    def _handle_message(self, body):
        """解析单条 B 站 WebSocket 消息，构造 danmaku2ass 兼容的元组。"""
        msg = json.loads(body.decode('utf-8', errors='replace'))
        if msg.get('cmd') != 'DANMU_MSG':
            return
        info = msg.get('info', [])
        if len(info) < 3:
            return
        meta = info[0]
        if not isinstance(meta, list) or len(meta) < 4:
            return

        # B 站弹幕属性（与 danmaku2ass ReadCommentsBilibili 解析逻辑一致）
        # 前面 `len(meta) >= 4` 已保证索引 [1..3] 存在
        mode     = int(meta[1])   # 1=滚动,4=底部,5=顶部
        fontsize = int(meta[2])
        color    = int(meta[3])

        text = str(info[1]) if info[1] else ''
        if not text.strip():
            return

        # 过滤非法控制字符 + 转义 ASS 特殊字符——避免乱码
        # ASS 里的特殊字符：\ 反斜杠、{ } 大括号会被解析为标签；换行符
        # 会强制换行导致字幕错位。danmaku2ass.ASSEscape 会处理这些，
        # 但它的处理不覆盖所有边缘情况（特别是控制字符）——这里提前过
        # 滤能让 ASS 输出更稳定。
        text = re.sub('[\x00-\x08\x0b\x0c\x0e-\x1f]', '�', text)
        # 换行符替换为斜杠（danmaku2ass 默认行为）——避免单条弹幕断行
        text = text.replace('\n', '/')
        text = text.replace('\r', '')

        # 映射到 danmaku2ass pos: 0=滚动, 1=底部, 2=顶部, 3=反向
        pos_map = {1: 0, 5: 1, 4: 2}
        pos = pos_map.get(mode)
        if pos is None:
            return

        size_px   = fontsize * self.font_size / 25.0
        # 换行符已替换为 /，单条弹幕按单行算
        height_px = size_px
        width_px  = CalculateLength(text) * size_px

        # danmaku2ass.ProcessComments 按位置索引读 tuple：c[0] timeline,
        # c[3] text, c[4] pos (int), c[7] height_px, c[8] width_px。早期
        # 实现里 c[1]=dm_ts, c[2]=seq 是 dead slot（无人读），保留
        # None 占位以维持 9 字段契约，比改 ProcessComments 索引安全。
        timeline = time.time() - self._start_time
        with self.lock:
            self.danmaku_list.append(
                (timeline, None, None, text, pos, color, size_px, height_px, width_px)
            )

    def _parse_binary(self, data):
        pos = 0
        while pos + 16 <= len(data):
            tl = struct.unpack_from('>I', data, pos)[0]
            hl = struct.unpack_from('>H', data, pos + 4)[0]
            pv = struct.unpack_from('>H', data, pos + 6)[0]
            op = struct.unpack_from('>I', data, pos + 8)[0]
            if tl < 16 or pos + tl > len(data):
                break
            body = data[pos + hl:pos + tl]
            pos += tl
            if pv == 2:
                try:
                    self._parse_binary(zlib.decompress(body))
                except zlib.error:
                    pass
                continue
            if op == 8:
                xbmc.log('[live.danmaku] auth OK (op=8)', xbmc.LOGDEBUG)
                self._connected = True
            elif op == 5:
                try:
                    self._handle_message(body)
                except Exception:
                    pass

    def _recv_loop(self):
        buf = b''
        if self.sock:
            self.sock.settimeout(1.0)  # 设置一次即可
        while self.running:
            sock = self.sock  # 快照引用，防止 stop() 置 None 后崩溃
            if not sock:
                break
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while len(buf) >= 2:
                    opcode = buf[0] & 0x0F
                    masked = (buf[1] & 0x80) != 0
                    plen   = buf[1] & 0x7F
                    offset = 2
                    if plen == 126:
                        if len(buf) < 4: break
                        plen = struct.unpack_from('>H', buf, offset)[0]
                        offset += 2
                    elif plen == 127:
                        if len(buf) < 10: break
                        plen = struct.unpack_from('>Q', buf, offset)[0]
                        offset += 8
                    if opcode == 0x8:
                        self.running = False
                        break
                    if masked:
                        if len(buf) < offset + 4 + plen: break
                        mk = buf[offset:offset + 4]
                        offset += 4
                        payload = bytes(buf[offset + i] ^ mk[i % 4] for i in range(plen))
                    else:
                        if len(buf) < offset + plen: break
                        payload = buf[offset:offset + plen]
                    offset += plen
                    buf = buf[offset:]
                    if opcode == 0x2:
                        self._parse_binary(payload)
                    elif opcode == 0x9:
                        try:
                            sock.send(bytes([0x8A, 0x00]))
                        except Exception:
                            pass
            except socket.timeout:
                continue
            except (OSError, ConnectionError, ConnectionResetError):
                break
            except Exception as e:
                xbmc.log('[live.danmaku] recv: %s' % str(e), xbmc.LOGWARNING)
                break

    def _run(self):
        # 1. WBI 签名获取 token
        info = self._get_token_wbi()
        if not info:
            xbmc.log('[live.danmaku] getDanmuInfo FAIL', xbmc.LOGERROR)
            return

        token = info.get('token', '')
        host_list = info.get('host_list', [])
        if not host_list or not token:
            xbmc.log('[live.danmaku] no host/token', xbmc.LOGERROR)
            return

        # 用最后一个 host（wiliwili 做法）
        host = host_list[-1].get('host', '')
        port = host_list[-1].get('ws_port', 2244)
        xbmc.log('[live.danmaku] using %s:%s' % (host, port), xbmc.LOGDEBUG)

        # 2. ws:// 连接
        if not self._connect(host, port):
            return

        # 3. 发送认证
        self._send_auth(token)

        # 4. 心跳线程
        def _hb():
            while self.running:
                sock = self.sock
                if not sock:
                    break
                time.sleep(30)
                if not self.running:
                    break
                sock = self.sock
                if sock:
                    try:
                        _ws_send(sock, _bili_packet(2, b'{}'))
                    except Exception:
                        pass
        threading.Thread(target=_hb, daemon=True).start()

        # 5. ASS 写入 + 刷新
        width  = 1920
        height = 540
        reserve_blank = int((1.0 - self.display_area) * height)

        def _writer():
            last_sync = 0
            live_marker = '/live/' + str(self.room_id)
            while self.running:
                time.sleep(3)
                if not self.running:
                    break
                with self.lock:
                    # timeline 用 time.time() - self._start_time（绝对
                    # 秒数）。曾试过 0-based 重新映射 Start——错的：
                    # m_track 在 m3u8 拉取触发重建时 libass 内部 PTS
                    # 不归零，事件被判过期。绝对秒数 + cutoff 过滤：
                    # 留 stay_time 窗口内的事件，去掉更早的 stale
                    # （m_track 重建后看到"全过期"屏幕空白，就是
                    # stale 引起的）。
                    now_offset = time.time() - self._start_time
                    cutoff = now_offset - self.stay_time - 2
                    snapshot = [c for c in self.danmaku_list
                                if c[0] >= cutoff]

                if not snapshot:
                    continue

                buf = io.StringIO()
                ProcessComments(
                    snapshot, buf, width, height, reserve_blank,
                    'sans-serif', self.font_size, self._opacity,
                    self.stay_time, self.stay_time,
                    [], False, None,
                )
                content = buf.getvalue()
                buf.close()

                # ── 后处理：把 \move(1920, ...) 起点改成 2120，让弹幕从 ──
                # 屏幕右外 200 像素处开始滚入，避免从屏幕右边缘突然出现。
                # 视频区域通常 <1920 宽（Kodi 半屏字幕），2120 在所有屏外。
                content = content.replace('\\move(1920,', '\\move(2120,')

                # 写盘
                tmp = self.ass_path + '.tmp'
                try:
                    # utf-8-sig 写 BOM 头：强制 libass 以 UTF-8 解码——避免
                    # Kodi 错把 UTF-8 文件当 GBK/系统编码读取导致"全屏乱码"
                    with open(tmp, 'w', encoding='utf-8-sig') as f:
                        f.write(content)
                    os.replace(tmp, self.ass_path)
                except Exception:
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass

                if not self.running:
                    break
                now = time.time()
                # 9 秒节拍调 setSubtitles——触发 m_track 重建并重读
                # ASS 文件。Kodi 21 在 m3u8 拉取时会自动调
                # GetExternalStreamDetails 重建 m_track（这是 v0.4.0
                # 已知问题："偶尔消失"），9s 节拍 setSubtitles 不能
                # 根除但能让消失间隔更规律。
                # 注意：3s 节拍会让 setSubtitles 每 3 秒调一次，
                # user 视觉上会感觉"弹幕闪一下"——不可接受。
                if now - last_sync < 9:
                    # 每 5 秒续期跨进程锁（避免别的进程接管）
                    if int(now) % 5 == 0:
                        _refresh_danmaku_lock(self.room_id)
                    continue
                last_sync = now
                try:
                    p = xbmc.Player()
                    if p.isPlaying():
                        cur = xbmc.getInfoLabel('Player.Filenameandpath') or ''
                        if live_marker in cur:
                            p.setSubtitles(self.ass_path)
                except Exception:
                    pass
        threading.Thread(target=_writer, daemon=True).start()

        self._recv_loop()

    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()
        # Wait for WebSocket auth to complete (typically <500 ms).
        # Before this fix we waited up to 5 s for the first danmaku
        # to arrive, but B 站 only sends an auth reply + heartbeats
        # on connect — no danmaku on an empty room. So the previous
        # wait would always run the full 10 × 0.5 s. Now we return
        # as soon as auth OK lands.
        for _ in range(20):
            if self._connected:
                return True
            if not self.running:
                return False
            time.sleep(0.1)
        xbmc.log(
            '[live.danmaku] start: auth not confirmed after 2 s, '
            'returning True anyway (daemon thread still running)',
            xbmc.LOGDEBUG,
        )
        return self.running

    def stop(self):
        self.running = False
        sock = self.sock
        self.sock = None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass


# ── 便捷函数 ────────────────────────────────────────────────────────────

_instances = {}


def _pid_alive(pid: int) -> bool:
    """跨平台 PID 存活检测。POSIX 用 signal 0；Windows 用 kernel32。

    PID 不存在 / 无权限 → False。Windows 上若 ctypes 不可用，退化为 True
    （让 timestamp 检查做主，避免误判存活）。
    """
    if pid <= 0:
        return False
    if os.name == 'nt':
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
            )
            if not h:
                return False
            try:
                code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                return code.value == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(h)
        except Exception:
            return True  # ctypes 不可用 → 假设活，让 timestamp 检查兜底
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_danmaku_lock(room_id, timeout_s=3):
    """跨进程单例锁：确保同一个 room 只有一个 LiveDanmakuClient 跑。

    锁文件 = /storage/.kodi/temp/plugin.video.bili/danmaku_<room_id>.lock
    内容 = "<pid>\\n<timestamp>"

    协议：
    - 检查锁文件存在？
      - 否 → 自己写新锁，返回 True
      - 是 → 读 PID + timestamp
        - PID 还活 且 timestamp 在 timeout_s 内 → 别的 client 在跑，返回 False
        - PID 死了 或 timestamp 太旧 → 接管（覆盖锁文件），返回 True
    """
    bp = get_temp_path()
    if not bp:
        return True  # fallback：拿不到 temp path 就不强制
    lock_path = os.path.join(bp, 'danmaku_%s.lock' % room_id)
    now_ts = time.time()
    my_pid = os.getpid()
    # 短时间 retry 等待别的进程退出
    deadline = now_ts + timeout_s
    while now_ts < deadline:
        if not os.path.exists(lock_path):
            try:
                with open(lock_path, 'w', encoding='utf-8') as f:
                    f.write('%d\n%.0f\n' % (my_pid, now_ts))
                return True
            except Exception:
                return True
        # 读锁
        try:
            with open(lock_path, 'r', encoding='utf-8') as f:
                content = f.read()
            parts = content.strip().split('\n')
            other_pid = int(parts[0])
            other_ts = float(parts[1]) if len(parts) > 1 else 0
        except Exception:
            other_pid, other_ts = 0, 0
        pid_alive = _pid_alive(other_pid)
        if pid_alive and (now_ts - other_ts) < timeout_s:
            # 别的进程还活且锁未过期，等它退
            time.sleep(0.3)
            now_ts = time.time()
            continue
        # 接管
        try:
            with open(lock_path, 'w', encoding='utf-8') as f:
                f.write('%d\n%.0f\n' % (my_pid, now_ts))
            return True
        except Exception:
            return True
    return True  # 超时兜底


def _release_danmaku_lock(room_id):
    bp = get_temp_path()
    if not bp:
        return
    lock_path = os.path.join(bp, 'danmaku_%s.lock' % room_id)
    try:
        # 只删自己的锁（防止误删其他进程）
        with open(lock_path, 'r', encoding='utf-8') as f:
            content = f.read()
        parts = content.strip().split('\n')
        if int(parts[0]) == os.getpid():
            os.remove(lock_path)
    except Exception:
        pass


def _refresh_danmaku_lock(room_id):
    """定期续期锁文件——表明本进程还活着。"""
    bp = get_temp_path()
    if not bp:
        return
    lock_path = os.path.join(bp, 'danmaku_%s.lock' % room_id)
    try:
        with open(lock_path, 'w', encoding='utf-8') as f:
            f.write('%d\n%.0f\n' % (os.getpid(), time.time()))
    except Exception:
        pass


def start_live_danmaku(room_id, uid=0, cookie=''):
    bp = get_temp_path()
    if not bp:
        return None, None
    path = os.path.join(bp, 'live_%s.ass' % room_id)

    # 跨进程单例锁——只允许一个 LiveDanmakuClient 写 .ass 文件
    # Kodi 21 在多次进同一直播频道时会派多个 add-on 进程，每
    # 个进程都调 start_live_danmaku，导致多个 client 争抢写
    # 同一个 .ass 文件——这是 v0.4.0 '偶尔消失' 的真正根因。
    if not _acquire_danmaku_lock(room_id):
        xbmc.log(
            '[live.danmaku] start: another process holds the lock for '
            'room=%s, skip' % room_id, xbmc.LOGINFO,
        )
        return path, None  # 返回 path 但 client=None

    buvid = ''
    try:
        from api import get_cookie_value
        buvid = get_cookie_value('buvid3')
    except Exception:
        pass

    # 占位 ASS（最小有效结构，无可见内容）
    # 关键：BOM + encoding='utf-8-sig' 确保 libass 识别 UTF-8
    ph = (
        '﻿'  # UTF-8 BOM——强制 libass 使用 UTF-8 解码，避免乱码
        '[Script Info]\n'
        '; Script generated by plugin.video.bili live danmaku\n'
        'ScriptType: v4.00+\n'
        'PlayResX: 1920\nPlayResY: 540\n'
        'Aspect Ratio: 1920:540\nCollisions: Normal\nWrapStyle: 2\n'
        'ScaledBorderAndShadow: yes\nYCbCr Matrix: TV.601\n\n'
        '[V4+ Styles]\n'
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, '
        'OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, '
        'ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
        'Alignment, MarginL, MarginR, MarginV, Encoding\n'
        'Style: R2L,sans-serif,25,&H00FFFFFF,&H00FFFFFF,&H00000000,'
        '&H00000000,0,0,0,0,100,100,0.00,0.00,1,1,0,7,0,0,0,0\n\n'
        '[Events]\n'
        'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    )
    try:
        with open(path, 'w', encoding='utf-8-sig') as f:
            f.write(ph)
    except Exception:
        pass

    key = str(room_id)
    if key in _instances:
        try:
            _instances[key].stop()
        except Exception:
            pass

    c = LiveDanmakuClient(
        room_id, path, uid, cookie,
        float(getSetting('font_size')),
        float(getSetting('opacity')),
        float(getSetting('danmaku_stay_time')),
        float(getSetting('display_area')),
        buvid,
    )
    ok = c.start()
    _instances[key] = c
    if not ok:
        xbmc.log('[live.danmaku] start FAIL for room=%s' % room_id, xbmc.LOGWARNING)
    return path, c


def stop_all_live_danmaku():
    """停止所有正在运行的直播弹幕线程。"""
    for key in list(_instances.keys()):
        c = _instances.pop(key, None)
        if c is not None:
            try:
                c.stop()
            except Exception:
                pass
        _release_danmaku_lock(key)

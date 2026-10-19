# -*- coding: utf-8 -*-
"""
pvr_config.py - 自动把 PVR IPTV Simple Client 指向本机 ysp-live 网关

目的：插件装完即可看电视，无需手动进 PVR 设置填地址。

做法：
  1. 找到 pvr.iptvsimple 的实例设置文件 instance-settings-*.xml
  2. 若 m3uUrl 未指向本机网关，则写入正确配置
  3. 通过 JSON-RPC 关闭再开启 pvr.iptvsimple，强制其从磁盘重读配置

Kodi 的 JSON-RPC 没有暴露 addon 设置读写接口（Settings.* 只管 Kodi 自身设置），
所以只能走「改文件 + 触发重载」这条路。

本模块不依赖 xbmc，可独立运行，便于在盒子上直接验证。
"""

import base64
import json
import os
import socket
import struct
import time
import xml.etree.ElementTree as ET

PVR_ADDON = 'pvr.iptvsimple'
INSTANCE_PREFIX = 'instance-settings-'
DEFAULT_PORT = 8767

# CoreELEC / LibreELEC 的固定路径，作为兜底
_COREELEC_PVR_DATA = '/storage/.kodi/userdata/addon_data/pvr.iptvsimple'
_COREELEC_DB_DIR = '/storage/.kodi/userdata/Database'


def _kodi_path(special):
    """把 special:// 路径解析成真实路径；非 Kodi 环境返回 None。

    用 xbmcvfs 解析可以让插件在 x86 桌面 Kodi（~/.kodi）、
    Windows（%APPDATA%\\Kodi）等环境下都找到正确的目录，
    而不是写死 CoreELEC 的 /storage/.kodi。
    """
    try:
        import xbmcvfs
        p = xbmcvfs.translatePath(special)
        if p and os.path.isdir(p):
            return p
    except Exception:
        pass
    return None


def get_pvr_data_dir():
    """pvr.iptvsimple 的 addon_data 目录（跨平台）。"""
    p = _kodi_path('special://userdata/addon_data/%s' % PVR_ADDON)
    if p:
        return p
    if os.path.isdir(_COREELEC_PVR_DATA):
        return _COREELEC_PVR_DATA
    return _COREELEC_PVR_DATA


def get_tv_db_path():
    """当前 Kodi 的 TV 数据库路径（版本号会变，不能写死 TV48.db）。"""
    d = _kodi_path('special://database')
    if d:
        # 取版本号最大的 TV*.db，兼容 Kodi 20/21/22 等
        import glob
        import re
        cands = []
        for f in glob.glob(os.path.join(d, 'TV*.db')):
            m = re.search(r'TV(\d+)\.db$', f)
            if m:
                cands.append((int(m.group(1)), f))
        if cands:
            return sorted(cands)[-1][1]
        # 数据库还没建时，按当前版本猜一个
        return os.path.join(d, 'TV.db')
    # 兜底：CoreELEC 上扫描 Database 目录
    if os.path.isdir(_COREELEC_DB_DIR):
        import glob
        import re
        cands = []
        for f in glob.glob(os.path.join(_COREELEC_DB_DIR, 'TV*.db')):
            m = re.search(r'TV(\d+)\.db$', f)
            if m:
                cands.append((int(m.group(1)), f))
        if cands:
            return sorted(cands)[-1][1]
    return os.path.join(_COREELEC_DB_DIR, 'TV48.db')


# 兼容旧代码里直接引用 PVR_DATA / TVDB 的地方
PVR_DATA = get_pvr_data_dir()
TVDB = get_tv_db_path()

# 需要写入的设置项：1 = 远程 URL
WANTED = {
    'm3uPathType': '1',
    'm3uCache': 'true',
    'm3uRefreshMode': '1',
    'm3uRefreshIntervalMins': '60',
}

# 回看（catchup）设置。
#
# iptvsimple 默认 catchupEnabled=false，此时 M3U 里的 catchup= 属性会被完全忽略，
# 在 EPG 里点过去的节目没有任何反应。ysp-live 的 M3U 用的是
# catchup="append"，因此 allChannelsCatchupMode 设为 2 (APPEND)。
#
# 注：allChannelsCatchupMode 的取值语义（来自 instance-settings.xml）：
#     0=DISABLED 1=DEFAULT 2=APPEND 3=SHIFT(SIPTV) 4=FLUSSONIC 5=XTREAM_CODES
CATCHUP = {
    'catchupEnabled': 'true',
    'catchupDays': '7',              # ysp-live 提供 7 天回看
    'allChannelsCatchupMode': '2',   # APPEND，与 M3U 的 catchup="append" 对应
    'catchupOverrideMode': '0',
    'catchupCorrection': '0',
    'catchupPlayEpgAsLive': 'false',
    'catchupOnlyOnFinishedProgrammes': 'false',
}


# ---------------------------------------------------------------- JSON-RPC
def _ws_call(method, params=None, host='127.0.0.1', port=9090, timeout=10):
    """最小 WebSocket JSON-RPC 客户端（Kodi 22 的 9090 只接受 WebSocket）。"""
    key = base64.b64encode(os.urandom(16)).decode()
    s = socket.create_connection((host, port), timeout=timeout)
    try:
        s.sendall((
            'GET /jsonrpc HTTP/1.1\r\n'
            'Host: %s:%d\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            'Sec-WebSocket-Key: %s\r\n'
            'Sec-WebSocket-Version: 13\r\n\r\n'
            % (host, port, key)).encode())

        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        status = buf.split(b'\r\n', 1)[0].decode('latin-1')
        if '101' not in status:
            raise RuntimeError('WebSocket 握手失败: %s' % status)

        payload = json.dumps({'jsonrpc': '2.0', 'method': method,
                              'params': params or {}, 'id': 1}).encode()
        mask = os.urandom(4)
        n = len(payload)
        h = bytearray([0x81])
        if n < 126:
            h.append(0x80 | n)
        elif n < 65536:
            h.append(0x80 | 126)
            h += struct.pack('>H', n)
        else:
            h.append(0x80 | 127)
            h += struct.pack('>Q', n)
        h += mask
        h += bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        s.sendall(bytes(h))

        def rd(cnt):
            d = b''
            while len(d) < cnt:
                c = s.recv(cnt - len(d))
                if not c:
                    break
                d += c
            return d

        out = b''
        while True:
            b1 = rd(1)
            if not b1:
                break
            fin = b1[0] & 0x80
            op = b1[0] & 0x0F
            b2 = rd(1)
            if not b2:
                break
            ln = b2[0] & 0x7F
            if ln == 126:
                ln = struct.unpack('>H', rd(2))[0]
            elif ln == 127:
                ln = struct.unpack('>Q', rd(8))[0]
            data = rd(ln)
            if op == 0x8:
                break
            if op == 0x9:
                continue
            out += data
            if fin:
                break
        return json.loads(out.decode('utf-8', 'replace'))
    finally:
        try:
            s.close()
        except Exception:
            pass


def set_addon_enabled(addonid, enabled):
    try:
        return _ws_call('Addons.SetAddonEnabled',
                        {'addonid': addonid, 'enabled': bool(enabled)})
    except Exception as e:
        return {'error': str(e)}


# ---------------------------------------------------------------- 设置文件
def find_settings_files():
    """返回所有 pvr.iptvsimple 实例设置文件的路径。"""
    out = []
    d = get_pvr_data_dir()
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if name.startswith(INSTANCE_PREFIX) and name.endswith('.xml'):
            out.append(os.path.join(d, name))
    return out


def read_url(path):
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None
    for st in root.iter('setting'):
        if st.get('id') == 'm3uUrl':
            return (st.text or '').strip()
    return None


def apply_settings(path, url, extra=None):
    """把 URL、回看设置及相关项写入指定实例文件。返回是否有改动。"""
    tree = ET.parse(path)
    root = tree.getroot()

    wanted = dict(WANTED)
    wanted.update(CATCHUP)
    wanted['m3uUrl'] = url
    if extra:
        wanted.update(extra)

    changed = False
    for st in root.iter('setting'):
        sid = st.get('id')
        if sid not in wanted:
            continue
        want = wanted[sid]
        cur = (st.text or '')
        if cur == want and 'default' not in st.attrib:
            continue
        # Kodi 一旦写入用户值就会去掉 default="true" 标记
        st.attrib.pop('default', None)
        st.text = want
        changed = True

    if changed:
        tree.write(path, encoding='utf-8', xml_declaration=False)
    return changed


def reload_pvr(wait=10.0):
    """关闭再开启 pvr.iptvsimple，强制其重读设置。

    实测（Kodi 22.0-BETA2）切换插件会触发：
        Destroying PVR client: addonId=pvr.iptvsimple, instanceId=1
        Creating PVR client:   addonId=pvr.iptvsimple, instanceId=1
    新客户端会重新读取 instance-settings-*.xml，因此改文件 + 切换即可生效，
    无需重启整个 Kodi。

    注意：这里**不要**调用 PVR.Scan。pvr.iptvsimple 是播放列表型后端，
    没有调谐器，无法扫描频道；调用它会让 Kodi 弹出
    「连接的 PVR 后端不支持频道扫描」(string #19192)。
    切换插件本身已足以重新加载频道列表，实测 64 路频道会立即回来。
    """
    set_addon_enabled(PVR_ADDON, False)
    time.sleep(2)
    r = set_addon_enabled(PVR_ADDON, True)
    time.sleep(wait)
    return r


# ---------------------------------------------------------------- 主流程
def build_url(port=DEFAULT_PORT, host='127.0.0.1', kodi=True):
    """构造 M3U 订阅地址。

    kodi=True 时带上 ?kodi=1，让网关输出 Kodi 能识别的 catchup-source
    （{utc}-{utcend}）；否则输出第三方播放器用的 ${(b)yyyyMMddHHmmss} 格式。
    这两种占位符互不兼容，所以必须区分。
    """
    url = 'http://%s:%d/all.m3u' % (host, port)
    if kodi:
        url += '?kodi=1'
    return url


def read_settings(path):
    """读出文件里所有 setting id -> 文本值。"""
    out = {}
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return out
    for st in root.iter('setting'):
        sid = st.get('id')
        if sid:
            out[sid] = (st.text or '').strip()
    return out


def is_configured(path, url):
    """URL 正确 **且** 回看设置齐全，才算配置完成。

    只比 URL 会导致老版本用户升级后回看设置不被补上。
    """
    cur = read_settings(path)
    if cur.get('m3uUrl') != url:
        return False
    for k, v in CATCHUP.items():
        if cur.get(k) != v:
            return False
    return True


def configure(port=DEFAULT_PORT, force=False, do_reload=True, log=None):
    """
    确保 PVR 指向本机网关。返回 (是否改动了文件, 说明文本)。
    """
    def _log(msg):
        if log:
            log(msg)

    url = build_url(port)
    files = find_settings_files()
    if not files:
        return False, '未找到 pvr.iptvsimple 实例设置文件（PVR 插件可能未初始化）'

    touched = []
    already = 0
    for f in files:
        if not force and is_configured(f, url):
            # 保持安静：这条每次复查都会命中，写日志会刷屏
            already += 1
            continue
        try:
            if apply_settings(f, url):
                touched.append(f)
                _log('已写入 %s -> %s' % (f, url))
        except Exception as e:
            _log('写入 %s 失败: %s' % (f, e))

    if not touched:
        if already:
            return False, 'PVR 已是本机网关，无需改动'
        return False, '未找到可写入的 PVR 实例设置文件'

    if do_reload:
        _log('触发 PVR 重载…')
        reload_pvr()

    return True, '已配置 %d 个实例: %s' % (len(touched), url)


# ---------------------------------------------------------------- 自检
def count_channels():
    try:
        import sqlite3
        con = sqlite3.connect(get_tv_db_path())
        try:
            return con.execute('select count(*) from channels').fetchone()[0]
        finally:
            con.close()
    except Exception as e:
        return 'err:%s' % e


def selftest(port=DEFAULT_PORT):
    """验证「改文件 + 切换插件」是否真的让 Kodi 重读设置。"""
    import shutil

    url_good = build_url(port)
    url_bad = 'http://127.0.0.1:1/definitely-missing.m3u'
    files = find_settings_files()

    print('实例文件:', files)
    if not files:
        print('无法自检：没有实例设置文件')
        return

    for f in files:
        print('  当前 m3uUrl =', read_url(f))
    print('起始频道数:', count_channels())

    backups = []
    for f in files:
        b = f + '.selftest-bak'
        shutil.copy2(f, b)
        backups.append((f, b))

    try:
        print('\n[1] 写入坏 URL')
        for f in files:
            apply_settings(f, url_bad)
            print('   ->', read_url(f))

        print('[2] 切换 pvr.iptvsimple 触发重载')
        reload_pvr(wait=10)

        n_bad = count_channels()
        print('[3] 坏 URL 下频道数:', n_bad)

        if n_bad == 0:
            print('\n>>> 结论：切换插件即可让 Kodi 重读设置 —— 自动配置可行')
        elif n_bad == 64:
            print('\n>>> 结论：切换插件不重读，需重启 Kodi 才能生效')
        else:
            print('\n>>> 结论：结果不确定（%s）' % n_bad)
    finally:
        print('\n[4] 还原')
        for f, b in backups:
            shutil.copy2(b, f)
            os.remove(b)
            print('   ->', read_url(f))
        reload_pvr(wait=10)
        print('[5] 还原后频道数:', count_channels())


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        port = DEFAULT_PORT
        for i, a in enumerate(sys.argv):
            if a == '--port' and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        selftest(port)
    else:
        p = DEFAULT_PORT
        for i, a in enumerate(sys.argv):
            if a == '--port' and i + 1 < len(sys.argv):
                p = int(sys.argv[i + 1])
        print(configure(p, log=print))

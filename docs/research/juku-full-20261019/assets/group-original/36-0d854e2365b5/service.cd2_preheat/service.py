# -*- coding: utf-8 -*-
"""
CD2 Preheat Service
监听 Kodi 媒体库焦点变化，对 CD2 挂载路径的文件预读开头到缓存。
起播时 MKV 头已在 CD2 缓存，冷启动从 4-8s 压到 1-2s。
onPlay 时自动取消正在进行的预读，播放优先。
ISO 文件预读量加倍（UDF 文件系统需要更多开头数据）。
"""
import os
import json
import time
import hashlib
import threading
import subprocess

import xbmc
import xbmcaddon
import xbmcgui


_ADDON = xbmcaddon.Addon()
_SETTINGS = {}                # 动态设置字典，SettingsMonitor 实时更新
_LAST_FOCUS = None            # 上次焦点路径（避免重复触发）
_LAST_PREHEAT = {}            # 文件指纹 -> 上次预读时间戳
_LOCK = threading.Lock()
_WORKER_SEM = None            # 并发信号量（延迟初始化，读 settings 后再建）
_CANCEL = threading.Event()   # onPlay 时设置，取消所有正在进行的预读
_ACTIVE_PROCS = []            # 正在运行的 dd 进程列表
_LAST_FOCUS_FILE = '/tmp/cd2_preheat_last_focus'  # service.py 写入，dialog_preheat 失焦时读取


def log(msg, level=xbmc.LOGINFO):
    if _ADDON.getSettingBool('debug_log'):
        xbmc.log(f'[CD2 Preheat] {msg}', level)


def get_setting_int(key, default=0):
    try:
        return int(_ADDON.getSetting(key) or default)
    except (ValueError, TypeError):
        return default


def get_setting_float(key, default=0.0):
    try:
        return float(_ADDON.getSetting(key) or default)
    except (ValueError, TypeError):
        return default


def get_prefixes():
    raw = _ADDON.getSetting('path_prefix') or ''
    return [p.strip() for p in raw.split(',') if p.strip()]


def auto_detect_cd2_paths():
    """自动检测 CD2 挂载路径（FUSE 挂载点包含 CloudDrive/CloudNAS 关键字）"""
    paths = []
    try:
        result = subprocess.run(['mount'], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split('\n'):
            if 'type fuse' in line or 'fuse.' in line:
                parts = line.split(' on ')
                if len(parts) >= 2:
                    mount_point = parts[1].split(' type ')[0]
                    lower_mp = mount_point.lower()
                    if any(kw in lower_mp for kw in ['clouddrive', 'cloudnas', 'cloudfs']):
                        if not mount_point.endswith('/'):
                            mount_point += '/'
                        paths.append(mount_point)
    except Exception as e:
        log(f'auto_detect error: {e}', xbmc.LOGWARNING)
    return paths


def is_local_path(path):
    if not path:
        return False
    lower = path.lower()
    if lower.startswith(('http://', 'https://', 'smb://', 'nfs://',
                         'rtsp://', 'rtmp://', 'udp://', 'plugin://')):
        return False
    return True


def resolve_strm(path):
    if not path:
        return None
    if path.lower().endswith('.strm'):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                content = f.read().strip()
            return content if content else None
        except Exception as e:
            log(f'read strm failed: {path} -> {e}', xbmc.LOGWARNING)
            return None
    return path


def http_jsonrpc(method, params=None, timeout=3):
    """
    通过 HTTP 调用 Kodi JSON-RPC（curl 子进程）。
    走网络栈，不经 Kodi Python 解释器，不会触发 __dynamic_cast 段错误。
    即使 curl 崩溃也不影响 Kodi 主进程。
    """
    try:
        req = {'jsonrpc': '2.0', 'method': method, 'id': 1}
        if params is not None:
            req['params'] = params
        # 用 URL 查询参数方式（避免 POST + Content-Type 复杂性）
        import urllib.parse
        query = urllib.parse.quote(json.dumps(req))
        cmd = ['curl', '-s', '-m', str(timeout),
               f'http://localhost:8080/jsonrpc?request={query}']
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 1)
        if result.returncode != 0 or not result.stdout:
            return None
        # 显式 UTF-8 解码（中文路径）
        try:
            text = result.stdout.decode('utf-8', errors='replace')
        except Exception:
            return None
        data = json.loads(text)
        return data.get('result')
    except Exception as e:
        log(f'http_jsonrpc error: {e}', xbmc.LOGWARNING)
        return None


def get_focus_path():
    """
    获取当前焦点项的文件路径（05:28 方案：直接 getInfoLabel，响应快）。
    警告：在窗口/ListItem 切换时可能触发 __dynamic_cast 段错误（C++ 层面，无法捕获）。
    """
    candidates = [
        xbmc.getInfoLabel('ListItem.FilenameAndPath'),
        xbmc.getInfoLabel('ListItem.Path'),
    ]
    for p in candidates:
        if p and not p.startswith('plugin://') and not p.startswith('addons://'):
            resolved = resolve_strm(p)
            if resolved:
                return resolved
    return None


def get_focus_path_http():
    """
    HTTP 版本（备用，不崩溃但慢）。
    当 getInfoLabel 方案崩溃时，可切换到这个函数。
    """
    result = http_jsonrpc('XBMC.GetInfoLabels',
                          {'labels': ['ListItem.FilenameAndPath', 'ListItem.Path']})
    if not isinstance(result, dict):
        return None
    candidates = [
        result.get('ListItem.FilenameAndPath', ''),
        result.get('ListItem.Path', ''),
    ]
    for p in candidates:
        if p and not p.startswith('plugin://') and not p.startswith('addons://'):
            resolved = resolve_strm(p)
            if resolved:
                return resolved
    return None


def get_window_info():
    """
    通过 HTTP JSON-RPC 获取当前窗口 ID 和控件 label。
    用于检测窗口变化和 ListItem 切换（control label 变化 = ListItem 切换）。
    """
    result = http_jsonrpc('GUI.GetProperties',
                          {'properties': ['currentwindow', 'currentcontrol']})
    if not isinstance(result, dict):
        return 0, ''
    win = result.get('currentwindow', {})
    ctrl = result.get('currentcontrol', {})
    return win.get('id', 0), ctrl.get('label', '')


def is_context_menu_active():
    """检测 10106 上下文菜单是否激活（通过 HTTP JSON-RPC）"""
    result = http_jsonrpc('GUI.GetProperties', {'properties': ['currentwindow']})
    if isinstance(result, dict):
        return result.get('currentwindow', {}).get('id', 0) == 10106
    return False


def should_preheat(path, prefixes):
    if not is_local_path(path):
        return False
    if not prefixes:
        return True
    for prefix in prefixes:
        if path.startswith(prefix):
            return True
    return False


def is_iso(path):
    """检测是否为 ISO 文件"""
    return path.lower().endswith('.iso')


def get_preheat_size(path, base_mb):
    """ISO 文件用独立预读大小（UDF 文件系统需要更多开头数据解析）"""
    if is_iso(path):
        iso_mb = get_setting_int('iso_head_mb', 16)
        return iso_mb if iso_mb > 0 else base_mb * 2
    return base_mb


def parse_time(s):
    """解析时间字符串（秒数或 h:mm:ss 格式），返回秒数"""
    if not s:
        return 0
    try:
        return float(s)
    except ValueError:
        pass
    parts = s.split(':')
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
    except ValueError:
        pass
    return 0


def get_resume_info(path):
    """
    获取续播位置信息（05:28 方案：直接 getInfoLabel）
    返回 (resume_sec, duration_sec) 或 None
    """
    try:
        play_count_str = xbmc.getInfoLabel('ListItem.PlayCount')
        if not play_count_str:
            return None
        try:
            if int(play_count_str) == 0:
                return None
        except ValueError:
            return None
        resume_str = xbmc.getInfoLabel('ListItem.ResumePoint')
        if not resume_str:
            return None
        resume_sec = parse_time(resume_str)
        if resume_sec <= 0:
            return None
        duration_str = xbmc.getInfoLabel('ListItem.Duration')
        if not duration_str:
            return None
        duration_sec = parse_time(duration_str)
        if duration_sec <= 0:
            return None
        if resume_sec < 60 or resume_sec / duration_sec > 0.95:
            return None
        log(f'resume info: {resume_sec:.0f}s / {duration_sec:.0f}s '
            f'({resume_sec/duration_sec*100:.0f}%)')
        return (resume_sec, duration_sec)
    except Exception:
        return None


def preheat_resume(path, resume_sec, duration_sec, preheat_mb=4, timeout=10):
    """
    预读续播位置附近的数据
    用文件大小 × (续播秒数 / 总时长) 估算字节偏移
    提前 2MB 预读，覆盖 Kodi seek 到续播位置前的数据
    """
    try:
        st = os.stat(path)
        size = st.st_size
        fraction = resume_sec / duration_sec
        offset = int(size * fraction) - 2 * 1024 * 1024  # 提前 2MB
        if offset < 0:
            offset = 0
        skip_mb = offset // (1024 * 1024)
        if skip_mb <= 0:
            return
        cmd = ['dd', f'if={path}', 'of=/dev/null', 'bs=1M',
               f'skip={skip_mb}', f'count={preheat_mb}',
               'iflag=fullblock', 'status=none']
        run_dd_cancellable(cmd, f'resume {preheat_mb}MB (skip {skip_mb}MB)', path, timeout)
    except Exception as e:
        log(f'resume error: {e}', xbmc.LOGWARNING)


def cancel_for_focus_change():
    """焦点变化时取消旧预读，快速恢复允许新预读（150ms）"""
    _CANCEL.set()
    with _LOCK:
        for proc in _ACTIVE_PROCS:
            try:
                proc.kill()
            except Exception:
                pass
        _ACTIVE_PROCS.clear()
    threading.Timer(0.15, _CANCEL.clear).start()


def cancel_all_preheat():
    """onPlay 时取消所有预读，2 秒内不允许新预读（播放优先）"""
    _CANCEL.set()
    with _LOCK:
        for proc in _ACTIVE_PROCS:
            try:
                proc.kill()
                log(f'cancelled preheat dd (pid={proc.pid})')
            except Exception:
                pass
        _ACTIVE_PROCS.clear()
    threading.Timer(2.0, _CANCEL.clear).start()


def run_dd_cancellable(cmd, label, path, timeout=10):
    """运行 dd 命令，支持 onPlay/新焦点时取消，超时 10 秒"""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        with _LOCK:
            _ACTIVE_PROCS.append(proc)
        start = time.time()
        while proc.poll() is None:
            if _CANCEL.is_set():
                try:
                    proc.kill()
                except Exception:
                    pass
                log(f'{label} cancelled: {path}')
                return False
            if time.time() - start > timeout:
                try:
                    proc.kill()
                except Exception:
                    pass
                log(f'{label} timeout ({timeout}s): {path}', xbmc.LOGWARNING)
                return False
            time.sleep(0.02)  # 20ms 检测周期，kill 后快速响应
        log(f'{label} ok: {path}')
        return True
    except Exception as e:
        log(f'{label} error: {e}', xbmc.LOGWARNING)
        return False
    finally:
        with _LOCK:
            if proc in _ACTIVE_PROCS:
                _ACTIVE_PROCS.remove(proc)


def preheat_head(path, size_mb):
    """预读文件开头 size_mb MB 到 CD2 缓存"""
    cmd = ['dd', f'if={path}', 'of=/dev/null', 'bs=1M',
           f'count={size_mb}', 'iflag=fullblock', 'status=none']
    run_dd_cancellable(cmd, f'head {size_mb}MB', path)


def preheat_tail(path, size_mb):
    """预读文件末尾 size_mb MB（覆盖 MKV Cues 索引）"""
    if size_mb <= 0:
        return
    try:
        st = os.stat(path)
    except Exception as e:
        log(f'stat error: {e}', xbmc.LOGWARNING)
        return
    size = st.st_size
    one_mb = 1024 * 1024
    if size <= size_mb * one_mb:
        return
    skip_mb = (size // one_mb) - size_mb
    if skip_mb <= 0:
        return
    cmd = ['dd', f'if={path}', 'of=/dev/null', 'bs=1M',
           f'skip={skip_mb}', f'count={size_mb}', 'iflag=fullblock', 'status=none']
    run_dd_cancellable(cmd, f'tail {size_mb}MB (skip {skip_mb}MB)', path)


def preheat_worker(path, head_mb, tail_mb, cooldown, force=False, skip_cooldown=False):
    """
    预读工作线程
    force=True: 取消旧预读（设置 _CANCEL + kill 旧进程），等待信号量
    skip_cooldown=True: 跳过 cooldown 检查（手动预读用）
    自动预读：force=True, skip_cooldown=False（取消旧预读但保留 cooldown）
    手动预读：force=True, skip_cooldown=True（取消旧预读 + 跳过 cooldown）
    弹窗预读：force=False, skip_cooldown=False（不取消旧预读，保留 cooldown）
    """
    global _WORKER_SEM
    if _WORKER_SEM is None:
        return
    # 先检查 cooldown（如果 skip_cooldown=False）
    # 避免：force 取消旧预读后，cooldown 跳过新预读，导致没有预读
    if not skip_cooldown:
        key = hashlib.md5(path.encode('utf-8')).hexdigest()[:12]
        now = time.time()
        with _LOCK:
            last = _LAST_PREHEAT.get(key, 0)
            if now - last < cooldown:
                log(f'cooldown skip ({int(now-last)}s < {cooldown}s): {path}')
                return
    if force:
        # force 模式：设置 _CANCEL + kill 旧进程
        # _CANCEL 让旧 worker 的后续 run_dd_cancellable 快速退出
        _CANCEL.set()
        with _LOCK:
            for proc in _ACTIVE_PROCS:
                try:
                    proc.kill()
                    log(f'force cancelled preheat dd (pid={proc.pid})')
                except Exception:
                    pass
            _ACTIVE_PROCS.clear()
        # 旧 worker 检测到 _CANCEL 和进程结束，会快速退出所有 run_dd 并 release 信号量
        deadline = time.time() + 1.0
        while True:
            if _WORKER_SEM.acquire(blocking=False):
                break
            if time.time() > deadline:
                log(f'preheat force timeout (busy, old worker not release): {path}')
                _CANCEL.clear()
                return
            time.sleep(0.02)
        # 清除 _CANCEL，新预读可以正常执行
        _CANCEL.clear()
    else:
        # 普通模式：非阻塞获取，忙时跳过
        if not _WORKER_SEM.acquire(blocking=False):
            log(f'preheat skip (busy, previous preheat running): {path}')
            return
    try:
        if _CANCEL.is_set():
            log(f'preheat skipped (cancelled): {path}')
            return
        key = hashlib.md5(path.encode('utf-8')).hexdigest()[:12]
        now = time.time()
        with _LOCK:
            last = _LAST_PREHEAT.get(key, 0)
            # skip_cooldown=True 时跳过 cooldown（用户主动行为优先）
            if not skip_cooldown and now - last < cooldown:
                log(f'cooldown skip ({int(now-last)}s < {cooldown}s): {path}')
                return
            _LAST_PREHEAT[key] = now
        # ISO 文件预读量加倍（UDF 文件系统需要更多开头数据）
        actual_head = get_preheat_size(path, head_mb)
        preheat_head(path, actual_head)
        # 续播预读（只在 resume_preheat 开关开启时执行）
        if _SETTINGS.get('resume_preheat', False):
            resume_info = get_resume_info(path)
            if resume_info:
                resume_sec, duration_sec = resume_info
                preheat_resume(path, resume_sec, duration_sec)
        preheat_tail(path, tail_mb)
    finally:
        _WORKER_SEM.release()


class PlayerMonitor(xbmc.Player):
    """监听播放事件，onPlay 时取消预读"""
    def onPlayBackStarted(self):
        log('onPlay -> cancelling all preheat (playback priority)')
        cancel_all_preheat()


class SettingsMonitor(xbmc.Monitor):
    """监听设置变化，实时重新读取关键设置（无需重启 Kodi）"""
    def onSettingsChanged(self):
        global _WORKER_SEM
        # 重新读取可能变化的设置
        new_auto = _ADDON.getSettingBool('auto_preheat')
        new_dialog = _ADDON.getSettingBool('dialog_preheat')
        new_resume = _ADDON.getSettingBool('resume_preheat')
        new_cooldown = get_setting_int('cooldown', 60)
        new_debounce = get_setting_float('debounce_sec', 0.5)
        new_poll = get_setting_int('poll_ms', 10)
        new_workers = get_setting_int('max_workers', 1)
        new_prefixes = get_prefixes()
        new_iso_head = get_setting_int('iso_head_mb', 16)
        # 更新全局变量（通过 _SETTINGS 字典传递给主循环）
        _SETTINGS['auto_preheat'] = new_auto
        _SETTINGS['dialog_preheat'] = new_dialog
        _SETTINGS['resume_preheat'] = new_resume
        _SETTINGS['cooldown'] = new_cooldown
        _SETTINGS['debounce_sec'] = new_debounce
        _SETTINGS['poll_ms'] = new_poll
        _SETTINGS['prefixes'] = new_prefixes
        _SETTINGS['iso_head_mb'] = new_iso_head
        # max_workers 变化时重建信号量
        if new_workers != _SETTINGS['max_workers']:
            _SETTINGS['max_workers'] = new_workers
            _WORKER_SEM = threading.Semaphore(new_workers)
            log(f'settings changed: max_workers -> {new_workers}, semaphore reset')
        log(f'settings changed: auto={new_auto} dialog={new_dialog} resume={new_resume} '
            f'cooldown={new_cooldown}s debounce={new_debounce}s poll={new_poll}ms '
            f'iso_head={new_iso_head}MB')


def main():
    global _WORKER_SEM
    head_mb = get_setting_int('head_mb', 4)
    tail_mb = get_setting_int('tail_mb', 0)
    # 初始化 _SETTINGS 字典（SettingsMonitor 会实时更新）
    _SETTINGS['auto_preheat'] = _ADDON.getSettingBool('auto_preheat')
    _SETTINGS['dialog_preheat'] = _ADDON.getSettingBool('dialog_preheat')
    _SETTINGS['resume_preheat'] = _ADDON.getSettingBool('resume_preheat')
    _SETTINGS['cooldown'] = get_setting_int('cooldown', 60)
    _SETTINGS['debounce_sec'] = get_setting_float('debounce_sec', 0.5)
    _SETTINGS['poll_ms'] = get_setting_int('poll_ms', 10)
    _SETTINGS['max_workers'] = get_setting_int('max_workers', 1)
    _SETTINGS['prefixes'] = get_prefixes()
    _SETTINGS['iso_head_mb'] = get_setting_int('iso_head_mb', 16)
    _WORKER_SEM = threading.Semaphore(_SETTINGS['max_workers'])

    # 启动时如果 path_prefix 为空，自动检测 CD2 挂载路径
    prefixes = _SETTINGS['prefixes']
    if not prefixes:
        detected = auto_detect_cd2_paths()
        if detected:
            _SETTINGS['prefixes'] = detected
            _ADDON.setSetting('path_prefix', ','.join(detected))
            log(f'auto-detected CD2 paths (path_prefix was empty): {detected}')
        else:
            log('path_prefix is empty and auto-detect found no CD2 mounts, '
                'all local files will be preheated', xbmc.LOGWARNING)

    log(f'service started | head={head_mb}MB iso_head={_SETTINGS["iso_head_mb"]}MB '
        f'tail={tail_mb}MB cooldown={_SETTINGS["cooldown"]}s poll={_SETTINGS["poll_ms"]}ms '
        f'workers={_SETTINGS["max_workers"]} debounce={_SETTINGS["debounce_sec"]}s '
        f'auto={_SETTINGS["auto_preheat"]} dialog={_SETTINGS["dialog_preheat"]} '
        f'prefixes={_SETTINGS["prefixes"]}')

    monitor = SettingsMonitor()
    player_monitor = PlayerMonitor()
    global _LAST_FOCUS

    # 05:28 方案：直接用 getInfoLabel，每 poll_ms 检测焦点变化，debounce 1s
    # 警告：在窗口/ListItem 切换时可能触发 __dynamic_cast 段错误
    # 如崩溃，切回 hybrid 模式（get_focus_path_http + 窗口稳定检测）

    pending_focus = None
    focus_stable_time = 0
    last_dialog_active = False
    last_focus_path = None

    log('service running (0528 mode: getInfoLabel direct)')

    while not monitor.abortRequested():
        try:
            prefixes = _SETTINGS['prefixes']
            cooldown = _SETTINGS['cooldown']
            poll_ms = _SETTINGS['poll_ms']
            auto_preheat = _SETTINGS['auto_preheat']
            dialog_preheat = _SETTINGS['dialog_preheat']
            debounce_sec = _SETTINGS['debounce_sec']

            cur_path = None

            # 需要检测焦点路径的情况：自动预读 或 弹窗预读
            # 用 HTTP JSON-RPC 替代 getInfoLabel（getInfoLabel 在 ListItem 切换时崩溃）
            need_focus_path = auto_preheat or dialog_preheat
            if need_focus_path:
                cur_path = get_focus_path_http()
                if cur_path:
                    last_focus_path = cur_path
                    # 只在路径变化时写入文件（减少 I/O）
                    try:
                        tmp = _LAST_FOCUS_FILE + '.tmp'
                        with open(tmp, 'w', encoding='utf-8') as f:
                            f.write(last_focus_path)
                        os.replace(tmp, _LAST_FOCUS_FILE)
                    except Exception:
                        pass

                # 自动预读：只有 auto_preheat=True 时才触发
                if auto_preheat:
                    if cur_path and cur_path != _LAST_FOCUS:
                        _LAST_FOCUS = cur_path
                        if should_preheat(cur_path, prefixes):
                            pending_focus = cur_path
                            focus_stable_time = time.time()
                            log(f'focus changed -> pending (debounce {debounce_sec}s): {cur_path}')
                        else:
                            log(f'focus skip (not in watch paths): {cur_path}')
                            pending_focus = None

                    if pending_focus and (time.time() - focus_stable_time) >= debounce_sec:
                        if not _CANCEL.is_set():
                            log(f'focus stable -> preheat: {pending_focus}')
                            t = threading.Thread(
                                target=preheat_worker,
                                args=(pending_focus, head_mb, tail_mb, cooldown),
                                kwargs={'force': True, 'skip_cooldown': False},
                                daemon=True
                            )
                            t.start()
                        pending_focus = None

            # 弹窗预读：检测 10106（上下文菜单），用 HTTP JSON-RPC 替代 getCondVisibility
            if dialog_preheat:
                is_trigger = is_context_menu_active()
                if is_trigger and not last_dialog_active:
                    path = last_focus_path
                    if path and should_preheat(path, prefixes):
                        log(f'dialog appeared -> immediate preheat: {path}')
                        t = threading.Thread(
                            target=preheat_worker,
                            args=(path, head_mb, tail_mb, cooldown),
                            daemon=True
                        )
                        t.start()
                    else:
                        log(f'dialog appeared but no valid path: {path}')
                last_dialog_active = is_trigger
        except Exception as e:
            log(f'main loop error: {e}', xbmc.LOGWARNING)

        monitor.waitForAbort(poll_ms / 1000.0)

    log('service stopped')


if __name__ == '__main__':
    main()

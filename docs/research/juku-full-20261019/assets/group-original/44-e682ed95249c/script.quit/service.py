
import os
import sys
import threading
import time

import xbmc
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
if ADDON_PATH and ADDON_PATH not in sys.path:
    sys.path.insert(0, ADDON_PATH)

from lib.base import write_cache, clear_cache

def _log(msg):
    try:
        xbmc.log('script.quit service: %s' % msg, xbmc.LOGINFO)
    except Exception:
        pass

def _enabled():
    try:
        return (ADDON.getSetting('preload_cache') or '').lower() != 'false'
    except Exception:
        return True

_core = None

def _core_mod():
    global _core
    if _core is None:
        import lib.core as _c
        _core = _c
    return _core

def _perf_probe():
    try:
        import marshal
        import importlib.util
        p = os.path.join(ADDON_PATH, 'lib', 'core.py')
        with open(p, encoding='utf-8') as fh:
            src = fh.read()
        t1 = time.time()
        compile(src, 'core.py', 'exec')
        t2 = time.time()
        _core_mod()
        t3 = time.time()
        pyc_ms = -1.0
        pyc = ''
        try:
            c = importlib.util.cache_from_source(p)
            pyc = c if os.path.exists(c) else ''
            if pyc:
                with open(pyc, 'rb') as fh:
                    fh.read(16)
                    marshal.load(fh)
                pyc_ms = (time.time() - t3) * 1000.0
        except Exception:
            pyc_ms = -1.0
        _log('性能基线: %dKB / %d 行源码 —— compile() %.1fms（1.0.8.26 之前每次弹窗白付）'
             ' vs 读 __pycache__ 字节码 %.1fms（现在入口只剩 6KB，命中缓存时连这步都不做）'
             % (len(src.encode('utf-8')) // 1024, src.count('\n') + 1,
                (t2 - t1) * 1000.0, pyc_ms))
        _log('字节码缓存: %s' % ('可用 ' + pyc if pyc else
                                 '不可用（插件目录只读 / 禁用了字节码写入）—— '
                                 '此时 core.py 每次 import 都要重编译（不影响命中缓存的开窗）'))
    except Exception as exc:
        _log('perf probe failed: %s' % exc)

def _cur_file():
    try:
        return (xbmc.getInfoLabel('Player.FilenameAndPath')
                or xbmc.getInfoLabel('Player.Filenameandpath') or '')
    except Exception:
        return ''

class QuitPreloader(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self._busy_file = None
        self._last_file = None
        self._lock = threading.Lock()

    def _build(self, fp):
        try:
            for _ in range(6):
                if self.abortRequested():
                    return
                if not xbmc.Player().isPlayingVideo():
                    return
                if _cur_file() != fp:
                    return
                try:
                    core = _core_mod()
                    payload = core.build_payload(quiet=True)
                except Exception as exc:
                    _log('build_payload failed: %s' % exc)
                    payload = None
                if payload and payload.get('content_text'):
                    if write_cache(payload):
                        _log('预构建完成 key=%s' % (payload.get('key') or '')[:60])
                    return
                self.waitForAbort(2.0)
        finally:
            with self._lock:
                if self._busy_file == fp:
                    self._busy_file = None

    def _maybe_start(self, fp):
        with self._lock:
            if self._busy_file == fp:
                return
            self._busy_file = fp
        threading.Thread(target=self._build, args=(fp,), daemon=True).start()

    def run(self):
        _log('started (addon v%s, 预加载=%s)'
             % (ADDON.getAddonInfo('version'), _enabled()))
        _perf_probe()
        try:
            if _enabled() and xbmc.Player().isPlayingVideo():
                fp = _cur_file()
                if fp:
                    self._last_file = fp
                    self._maybe_start(fp)
        except Exception:
            pass

        while not self.abortRequested():
            try:
                if xbmc.Player().isPlayingVideo():
                    fp = _cur_file()
                    if fp and fp != self._last_file:
                        self._last_file = fp
                        if _enabled():
                            self._maybe_start(fp)
                elif self._last_file:
                    self._last_file = None
                    clear_cache()
            except Exception as exc:
                _log('loop error: %s' % exc)
            self.waitForAbort(1.5)
        _log('stopped')

QuitPreloader().run()


import time

_T0 = time.time()

import os
import sys
import threading

import xbmc
import xbmcaddon
import xbmcgui

_T_XBMC = time.time()

try:
    from lib.base import stamp, set_t0, read_cache, cache_key
except ImportError:
    
    _p = xbmcaddon.Addon().getAddonInfo('path')
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
    from lib.base import stamp, set_t0, read_cache, cache_key

_T_BASE = time.time()

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')
VERSION = ADDON.getAddonInfo('version')

set_t0(_T0)

poster = ''
content_text = ''

def preload_enabled():
    try:
        return (ADDON.getSetting('preload_cache') or '').lower() != 'false'
    except Exception:
        return True

class ExitConfirm(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        super(ExitConfirm, self).__init__(*args, **kwargs)
        self.countdown = 10
        self.close_timer = None
        self.window_closed = False
        self.playback_stopped = False

    def onInit(self):
        stamp('onInit 开始设置属性')
        self.setProperty('PosterPath', poster)
        self.setProperty('ContentText', content_text)
        self._start_timer()
        stamp('onInit 完成（窗口已可见）')

    def _start_timer(self):
        self._cancel_timer()
        self.close_timer = threading.Timer(self.countdown, self._auto_close)
        self.close_timer.daemon = True
        self.close_timer.start()

    def _cancel_timer(self):
        if self.close_timer:
            self.close_timer.cancel()

    def _auto_close(self):
        if self.window_closed or self.playback_stopped:
            return
        xbmc.executebuiltin('Action(Back)')

    def _safe_close(self):
        if self.window_closed:
            return
        self.window_closed = True
        self._cancel_timer()
        self.close()

    def onClick(self, controlId):
        if controlId == 10:
            self.playback_stopped = True
            self._cancel_timer()
            self._safe_close()
            xbmc.sleep(300)
            xbmc.executebuiltin('PlayerControl(Stop)')
        else:
            self._safe_close()

    def onAction(self, action):
        if action.getId() in (0, 10, 92, 216, 247, 275):
            self._cancel_timer()
            self._safe_close()
            return
        self._start_timer()

def main():
    global poster, content_text

    stamp('入口就绪（stdlib+kodi %.0fms + lib.base %.0fms + Addon %.0fms）'
          % ((_T_XBMC - _T0) * 1000.0, (_T_BASE - _T_XBMC) * 1000.0,
             (time.time() - _T_BASE) * 1000.0))

    cur_file = (xbmc.getInfoLabel('Player.FilenameAndPath')
                or xbmc.getInfoLabel('Player.Filenameandpath') or '')

    hit = None
    if preload_enabled():
        try:
            cached = read_cache()
            if cached:
                k = cache_key(cur_file)
                if k and cached.get('key') == k:
                    hit = cached
        except Exception as exc:
            stamp('缓存读取异常（忽略）%s' % exc)

    if hit is not None:
        
        poster = hit.get('poster') or ''
        content_text = hit.get('content_text') or ''
        stamp('命中预加载缓存（零 DB 查询）key=%s' % (hit.get('key') or '')[:60])
    else:
        
        from lib.core import build_payload
        p = build_payload()
        poster = p.get('poster') or ''
        content_text = p.get('content_text') or ''

    if not content_text:
        content_text = '无法获取当前内容信息'

    win = ExitConfirm('confirm.xml', ADDON_PATH, 'Default', '720p')
    win.doModal()
    del win
    stamp('弹窗结束')

    import sys as _sys
    _core = _sys.modules.get('lib.core')
    if _core is not None:
        try:
            _core.sqlite_close(getattr(_core, 'conn', None))
        except Exception:
            pass

if __name__ == '__main__':
    main()

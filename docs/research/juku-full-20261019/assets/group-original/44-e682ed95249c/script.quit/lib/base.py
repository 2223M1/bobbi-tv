
import os
import time

import xbmc

DEBUG = False
_T0 = time.time()

_CACHE_NAME = 'sq1_preload.txt'
_CACHE_NAME_OLD = 'preload.json'
_MAGIC = 'SQ1'

def set_t0(t):
    global _T0
    _T0 = t

def stamp(msg):
    try:
        xbmc.log('script.quit 耗时 +%.0fms  %s'
                 % ((time.time() - _T0) * 1000.0, msg), xbmc.LOGINFO)
    except Exception:
        pass

def log(msg):
    if DEBUG:
        try:
            xbmc.log('script.quit: %s' % msg, xbmc.LOGINFO)
        except Exception:
            pass

_HEXDIGITS = '0123456789abcdefABCDEF'

def pct_unquote(text):
    s = str(text or '')
    if '%' not in s:
        return s
    out = bytearray()
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '%' and i + 2 < n and s[i + 1] in _HEXDIGITS and s[i + 2] in _HEXDIGITS:
            out.append(int(s[i + 1:i + 3], 16))
            i += 3
            continue
        out += ch.encode('utf-8', 'surrogateescape')
        i += 1
    try:
        return bytes(out).decode('utf-8', 'replace')
    except Exception:
        return s

def unquote_deep(text, rounds=3):
    s = str(text or '')
    for _ in range(rounds):
        if '%' not in s:
            break
        t = pct_unquote(s)
        if t == s:
            break
        s = t
    return s

_PROFILE = None

def _profile_dir():
    global _PROFILE
    if _PROFILE is not None:
        return _PROFILE
    _PROFILE = ''
    try:
        import xbmcaddon
        import xbmcvfs
        p = xbmcaddon.Addon().getAddonInfo('profile') or ''
        _PROFILE = (xbmcvfs.translatePath(p) or '').rstrip('/')
    except Exception:
        _PROFILE = ''
    return _PROFILE

def cache_dir():
    return _profile_dir()

def cache_key(fp):
    p = unquote_deep(fp or '')
    if not p:
        return ''
    seg = p.split('?', 1)[0].rstrip('/').rsplit('/', 1)[-1]
    if seg and seg.lower() not in ('redirect_url', 'redirect', 'play', 'index',
                                   'stream', 'proxy', 'open'):
        return seg
    
    seg2 = p.rstrip('/').rsplit('/', 1)[-1]
    return seg2 or p

def read_cache():
    d = cache_dir()
    if not d:
        return None
    try:
        with open(os.path.join(d, _CACHE_NAME), 'r', encoding='utf-8') as fh:
            if fh.readline().rstrip('\r\n') != _MAGIC:
                return None
            key = fh.readline().rstrip('\r\n')
            poster = fh.readline().rstrip('\r\n')
            text = fh.read()
        if not text:
            return None
        return {'key': key, 'poster': poster, 'content_text': text}
    except Exception:
        return None

def write_cache(payload):
    d = cache_dir()
    if not d or not payload or not payload.get('content_text'):
        return False
    try:
        if not os.path.isdir(d):
            os.makedirs(d)
        tmp = os.path.join(d, _CACHE_NAME + '.tmp')
        with open(tmp, 'w', encoding='utf-8') as fh:
            fh.write('%s\n%s\n%s\n%s'
                     % (_MAGIC, (payload.get('key') or '').replace('\n', ' '),
                        (payload.get('poster') or '').replace('\n', ' '),
                        payload.get('content_text') or ''))
        os.replace(tmp, os.path.join(d, _CACHE_NAME))
        return True
    except Exception as exc:
        log('write_cache failed: %s' % exc)
        return False

def clear_cache():
    d = cache_dir()
    if not d:
        return
    for name in (_CACHE_NAME, _CACHE_NAME_OLD):
        try:
            p = os.path.join(d, name)
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

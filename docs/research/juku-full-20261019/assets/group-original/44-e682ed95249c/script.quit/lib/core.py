
import os
import re
import time

import xbmc
import xbmcaddon
import xbmcvfs

from lib.base import log, stamp, unquote_deep, cache_key

ADDON = xbmcaddon.Addon()
VERSION = ADDON.getAddonInfo('version')

DEBUG = False

try:
    DIAG = (ADDON.getSetting('show_diag') or '').lower() == 'true'
except Exception:
    DIAG = False
FALLBACK_THUMB = True

LOCAL_ART_NAMES = ('poster.jpg', 'poster.png', 'poster.tbn', 'poster.webp',
                   'folder.jpg', 'folder.png', 'cover.jpg', 'cover.png',
                   'show.jpg', 'default.jpg', 'tvshow.poster.jpg', 'season-poster.jpg')

def label(name):
    try:
        return (xbmc.getInfoLabel(name) or '').strip()
    except Exception:
        return ''

def first(*values):
    for v in values:
        if v:
            return v
    return ''

def poster_of(art):
    return first(art.get('poster'), art.get('tvshow.poster'), art.get('season.poster'))

def thumb_of(art):
    return first(art.get('thumb'), art.get('tvshow.thumb'))

_POSTER_LABELS = (
    'Player.Art(poster)', 'Player.Art(tvshow.poster)', 'Player.Art(season.poster)',
    'VideoPlayer.Art(poster)', 'VideoPlayer.Art(tvshow.poster)', 'VideoPlayer.Art(season.poster)',
)
_THUMB_LABELS = ('Player.Art(thumb)', 'VideoPlayer.Art(thumb)')

def _first_label(names):
    for name in names:
        v = label(name)
        if v:
            return v
    return ''

def poster_from_infolabel():
    return _first_label(_POSTER_LABELS)

def thumb_from_infolabel():
    return _first_label(_THUMB_LABELS)

def valid_id(value):
    return value is not None and str(value) not in ('', '-1', 'None')

def is_url(text):
    return bool(text) and re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', text) is not None

def clean_plot(text):
    if not text:
        return ''
    s = unquote_deep(text)
    s = re.sub(r'[A-Za-z][A-Za-z0-9+.-]*://[^\s|]+', ' ', s)
    s = re.sub(r'/(?:emby_addon_mode|http|movies|tvshows|episodes)/[^\s]*', ' ', s)
    s = re.sub(r'%2[Ff]%2[Ff][^\s]*', ' ', s)
    s = re.sub(r'[A-Za-z0-9/]*picture/[^\s]*', ' ', s)
    s = re.sub(r'\s{2,}', ' ', s).strip(' ··| ')
    
    if re.search(r'%[0-9A-Fa-f]{2}', s) \
            or re.search(r'\.(?:mkv|mp4|ts|avi|iso|m2ts|wmv|flv|mov|rmvb)\s*$', s, re.I):
        return ''
    return s

def dirty_plot(text):
    text = text or ''
    return bool(re.search(r'[A-Za-z][A-Za-z0-9+.-]*://', text)
                or '/picture/' in text
                or '/emby_addon_mode/' in text)

def format_season_episode(season, episode):
    if not (season and episode):
        return ''
    try:
        return "第%d季第%d集" % (int(float(season)), int(float(episode)))
    except (TypeError, ValueError):
        return "第%s季第%s集" % (season, episode)

def parse_season_episode(path):
    if not path:
        return 0, 0
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,3})', path) or re.search(r'(\d{1,2})[xX](\d{1,3})', path)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'第\s*(\d{1,2})\s*季[\s._-]*第\s*(\d{1,3})\s*[集话話]', path)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'第\s*(\d{1,3})\s*[集话話]', path)
    if m:
        return season_from_path(path), int(m.group(1))
    return season_from_path(path), 0

def season_from_path(path):
    norm = norm_path(path)
    parts = [p for p in norm.split('/') if p][:-1]
    for d in reversed(parts[-2:]):
        m = re.match(r'^(?:s|season[\s._-]*|第\s*季?)(\d{1,2})\s*[季部]?$', d.strip(), re.IGNORECASE)
        if m:
            return int(m.group(1))
        m = re.match(r'^第\s*(\d{1,2})\s*季', d.strip())
        if m:
            return int(m.group(1))
    return 0

_EP_SPLIT_RE = re.compile(
    r'[Ss]\d{1,2}[\s._-]*[Ee]\d{1,3}'
    r'|(?<!\d)\d{1,2}\s*[xX]\s*\d{1,3}(?!\d)'
    r'|第\s*\d{1,2}\s*季[\s._-]*第\s*\d{1,3}\s*[集话話]'
    r'|第\s*\d{1,3}\s*[集话話]')
_MEDIA_EXT_RE = re.compile(
    r'\.(?:mkv|mp4|ts|avi|iso|m2ts|wmv|flv|mov|rmvb|strm)\s*$', re.IGNORECASE)

def cut_episode_tail(text):
    s = str(text or '').strip()
    if not s:
        return ''
    m = _EP_SPLIT_RE.search(s)
    if m and m.start() > 0:
        s = s[:m.start()]
    return s.strip(' -_.·－—~')

def derive_tv_meta(*srcs):
    for src in srcs:
        if not src:
            continue
        s, e = parse_season_episode(src)
        if s or e:
            show = show_title_from_path(src)
            
            show = cut_episode_tail(show)
            if show and len(show) >= 2 and show.lower() not in (
                    'season', 'special', 'tvshows', 'episodes', 'specials'):
                return show, (str(s) if s else ''), (str(e) if e else '')
    return '', '', ''

def norm_path(path):
    return str(path or '').split('|', 1)[0].split('#', 1)[0].replace('\\', '/').rstrip('/')

_QUALITY_TAGS = (
    r'2160p|1080p|1080i|720p|576p|480p|4k|8k|uhd|ultra[-.\s]?hd|hdr10\+?|hdr|sdr|dolby[-.\s]?vision'
    r'|blu[-.\s]?ray|bdrip|bdremux|remux|web[-.\s]?dl|webrip|hdtv|hdrip|dvdrip|dvd5|dvd9'
    r'|hevc|h\.?26[45]|x\.?26[45]|avc|vp9|av1'
    r'|truehd(?:[.\s]*\d(?:[.\s]\d)?)?|atmos|dts(?:[-.\s]?(?:hd|x|ma|es))*|杜比视界|杜比全景声'
    r'|ddp?[.\s]?\d(?:[.\s]\d)?|eac3|ac3|aac|flac|lpcm|opus'
    r'|repack|proper|rerip|extended|unrated|uncut|remastered|imax[-.\s]?enhanced|open[-.\s]?matte'
)
_QUALITY_TAG_RE = re.compile(r'(?i)[\s._\-]+(?:' + _QUALITY_TAGS + r')(?=[\s._\-]|$)')
_QUALITY_LEAD_RE = re.compile(r'(?i)^[\s._\-]*(?:' + _QUALITY_TAGS + r')(?=[\s._\-]|$)')
_TRAILING_YEAR_RE = re.compile(r'[\s._\-–—]+[\(（]?(19\d{2}|20\d{2})[\)）]?\s*$')
_EPISODE_NAME_RE = re.compile(
    r'(?:[Ss]\d{1,2}[\s._-]*[Ee]\d{1,3}'
    r'|(?<!\d)\d{1,2}\s*[xX]\s*\d{1,3}(?!\d)'
    r'|第\s*\d{1,3}\s*[集话話]'
    r'|第\s*\d{1,2}\s*[季部]'
    r'|(?:^|[\s._\-])[Ee][Pp]?\d{1,3}(?!\d))')
_RELEASE_GROUP_RE = re.compile(
    r'(?i)(-sh@|@|\b(HDChina|CHDBits|CMCT|FRDS|BeAst|MTeam|HDTime|PTHome|TorrenTGui|'
    r'WiKi|CtrlHD|DON|HDSky|OurBits|TTG)\b)')

def looks_like_release_name(text):
    t = str(text or '').strip()
    if not t:
        return False
    if '.' in t or '_' in t:
        return _QUALITY_TAG_RE.search(t) is not None or _QUALITY_LEAD_RE.search(t) is not None
    return _QUALITY_TAG_RE.search(t) is not None

def looks_like_path(text):
    t = str(text or '')
    if not t:
        return False
    if ('/' in t) or ('\\' in t) or ('%2F' in t) or ('://' in t):
        return True
    if re.search(r'\.(iso|mkv|mp4|ts|m2ts|avi|strm|bdmv)$', t, re.I) is not None:
        return True
    return looks_like_release_name(t)

STREAM_PREFIXES = ('http://', 'https://', 'ftp://', 'smb://', 'nfs://', 'plugin://',
                   'rtsp://', 'rtmp://', 'mms://', 'udp://', 'rtp://', 'redirect_url',
                   'addons://', 'udf://', 'bluray://', 'bdmv://', 'dvd://', 'vfs://')

def looks_like_stream_url(text):
    t = str(text or '').strip().lower()
    if not t:
        return False
    if t.startswith(STREAM_PREFIXES):
        return True
    return '://' in t

def strip_trailing_year(title):
    t = (title or '').strip()
    m = _TRAILING_YEAR_RE.search(t)
    if m:
        head = t[:m.start()].strip(' \t._-·:：')
        if len(head) >= 2:
            return head
    return t

def dedupe_repeat(text):
    s = str(text or '').strip()
    if not s or ' ' not in s:
        return s
    kept = []
    for p in s.split(' '):
        if p and len(p) >= 2:
            joined = ' '.join(kept)
            if joined.endswith(p) or (kept and kept[-1] == p):
                continue
        kept.append(p)
    return ' '.join(kept)

def extract_title_from_path(path):
    if not path:
        return None
    try:
        s = unquote_deep(norm_path(path))
        s = s.replace('%2F', '/').replace('%2f', '/').replace('%20', ' ')
        
        if '?' in s:
            s = s.split('?')[0]
        
        if '/' in s:
            s = s.split('/')[-1]
        if '\\' in s:
            s = s.split('\\')[-1]
        
        base, ext = os.path.splitext(s)
        if ext and len(ext) <= 5 and ext.lower() in (
                '.iso', '.mkv', '.mp4', '.ts', '.m2ts', '.avi', '.strm', '.bdmv'):
            s = base
        
        s = re.sub(r'\{[^}]*\}', ' ', s)
        
        cut = re.search(r'[\[\(\{（【]', s)
        if cut:
            s = s[:cut.start()]
        
        _cut = len(s)
        
        _m = re.search(r'[\u4e00-\u9fff][：:、，,。\s]*[A-Za-z]', s)
        if _m:
            _cut = min(_cut, _m.start() + 1)
        
        _my = re.search(r'[\s._]+(?:19|20)\d{2}(?=[\s._]|$)', s)
        if _my and _QUALITY_LEAD_RE.match(s[_my.end():]):
            _cut = min(_cut, _my.start())
        else:
            _mq = _QUALITY_TAG_RE.search(s)
            if _mq:
                _cut = min(_cut, _mq.start())
        if _cut < len(s):
            _trimmed = s[:_cut].strip(' \t\r\n.-_·:：')
            if _trimmed:
                s = _trimmed
        
        s = _RELEASE_GROUP_RE.sub(' ', s)
        s = re.sub(r'\s+', ' ', s).strip(' \t\r\n.-_·:：')
        
        if s and ' ' not in s and ('.' in s or '_' in s):
            s = re.sub(r'[._]', ' ', s)
            s = re.sub(r'\s+', ' ', s).strip()
        s = strip_trailing_year(s)
        
        if len(s) >= 2 and s.lower() != 'unknown':
            return s
    except Exception as exc:
        log('extract_title_from_path error: %s' % exc)
    return None

def is_tvshow_content(item_dict, path):
    try:
        mtype = (item_dict or {}).get('type')
        tvshowid = (item_dict or {}).get('tvshowid')
        movieid = (item_dict or {}).get('movieid')
        if mtype == 'episode':
            return True
        if valid_id(tvshowid):
            return True
        if mtype == 'movie' or valid_id(movieid):
            return False
        low = str(path or '').lower()
        if '/tvshows/' in low or '/episodes/' in low:
            return True
        if '/movies/' in low:
            return False
        return _EPISODE_NAME_RE.search(str(path or '')) is not None
    except Exception as exc:
        log('is_tvshow_content error: %s' % exc)
        return False

def smart_title(text):
    s = unquote_deep(norm_path(text)).strip()
    if not s or s.lower() in ('unknown', 'unknown.iso'):
        return ''
    if looks_like_path(s) or looks_like_stream_url(s):
        return dedupe_repeat(extract_title_from_path(s) or s)
    return dedupe_repeat(strip_trailing_year(s))

TITLE_JUNK = {'redirect_url', 'redirect', 'play', 'video', 'stream', 'file',
              'index', 'plugin', 'strm', 'emby_addon_mode', 'http', 'https',
              'movies', 'tvshows', 'episodes', 'media', 'download'}

def plausible_title(text, show='', ep_mode=False):
    s = clean_ep_title(text, show) if ep_mode else smart_title(text)
    if not s:
        return ''
    if s.lower() in TITLE_JUNK or looks_like_stream_url(s):
        return ''
    if '/' in s or '\\' in s or '%' in s:
        return ''
    return s

def is_pure_episode_number(text):
    cleaned = re.sub(r'[\d第集合话話\.\-\s]', '', str(text or '').strip())
    return not cleaned.strip()

def clean_ep_title(text, show=''):
    s = unquote_deep(text).strip()
    if show:
        low = s.lower()
        sh = str(show).strip().lower()
        for sep in (' - ', '－', '-'):
            if low.startswith(sh + sep):
                s = s[len(sh) + len(sep):].strip()
                break
    s = re.sub(r'^\s*\d{1,2}x\d{1,3}\s*\.\s*', '', s)
    s = re.sub(r'^\s*[Ss]\d{1,2}\s*[Ee]\d{1,3}\s*\.\s*', '', s)
    s = re.sub(r'^\s*第\s*\d{1,2}\s*季[^集话]*[集话]\s*[.·]?\s*', '', s)
    s = re.sub(r'^\s*第\s*\d{1,3}\s*[集话話]\s*[.·\-－]?\s*', '', s)
    return s.strip()

def episode_name_from_text(show, *srcs):
    for src in srcs:
        s = unquote_deep(src or '')
        if not s:
            continue
        m = re.search(r'[?&]file_path=([^&]+)', s)
        if m:
            try:
                s = pct_unquote(m.group(1))
            except Exception:
                s = m.group(1)
        else:
            s = s.split('?', 1)[0].split('|', 1)[0]
        if '/' in s:
            s = s.rstrip('/').rsplit('/', 1)[-1]
        s = _MEDIA_EXT_RE.sub('', s).strip()
        m = _EP_SPLIT_RE.search(s)
        if not m:
            continue
        rest = s[m.end():].strip(' -_.·－—~')
        if not rest:
            continue
        got = plausible_title(tidy_title(rest), show, ep_mode=True)
        if got:
            return got
    return ''

def vfs(path):
    try:
        return xbmcvfs.translatePath(path)
    except Exception:
        return path

def open_videos_db():
    import sqlite3
    for special in ('special://userdata/Database/', 'special://database/'):
        db_dir = vfs(special)
        try:
            if not xbmcvfs.exists(db_dir):
                continue
            files = xbmcvfs.listdir(db_dir)[1]
        except Exception:
            continue
        cands = [f for f in files if f.startswith('MyVideos') and f.endswith('.db')]

        def ver(f):
            m = re.search(r'(\d+)', f)
            return int(m.group(1)) if m else 0

        if not cands:
            continue
        cands.sort(key=ver, reverse=True)
        try:
            conn = sqlite3.connect(os.path.join(db_dir, cands[0]), timeout=1.0)
            conn.text_factory = lambda b: b.decode('utf-8', 'replace')
            return conn, cands[0]
        except Exception as exc:
            log('sqlite open %s failed: %s' % (cands[0], exc))
    return None, ''

def sqlite_close(conn):
    try:
        conn.close()
    except Exception:
        pass

def q1(conn, sql, *args):
    try:
        cur = conn.cursor()
        cur.execute(sql, tuple(args))
        return cur.fetchone()
    except Exception as exc:
        log('sqlite failed: %s args=%s / %s' % (sql, args, exc))
        return None

def title_candidates(path):
    norm = norm_path(path)
    parts = [p for p in norm.split('/') if p]
    if not parts:
        return []
    stem = os.path.splitext(parts[-1])[0]
    out = []

    def add(text):
        cand = tidy_title(text)
        if cand and cand not in out:
            out.append(cand)

    for pat in (r'[Ss]\d{1,2}[\s._-]*[Ee]\d{1,3}',
                r'(?<!\d)\d{1,2}\s*[xX]\s*\d{1,3}(?!\d)',
                r'第\s*\d{1,2}\s*季[\s._-]*第\s*\d{1,3}\s*[集话話]',
                r'第\s*\d{1,3}\s*[集话話]',
                r'[\s._-][Ee][Pp]?\d{1,3}(?!\d)'):
        m = re.search(pat, stem)
        if m and m.start() > 0:
            add(stem[:m.start()])
            break
    for d in list(reversed(parts[:-1]))[:3]:
        if re.match(r'^(?:s\d{1,2}|season[\s._-]*\d{1,2}|第\s*\d{1,2}\s*[季部]|specials?)$',
                    d, re.IGNORECASE):
            continue
        m = re.match(r'^(.*?)[\s._-]+(?:s\d{1,2}|season[\s._-]*\d{1,2}|第\s*\d{1,2}\s*[季部])$',
                     d, re.IGNORECASE)
        if m and m.group(1).strip():
            add(m.group(1))
        add(d)
    add(stem)
    return out

NESTED_BRACKET = re.compile(r'[\[\{\(（【][^\[\{\(（【\]\}\)）】]*[\]\}\)）】]')

def tidy_title(text):
    s = re.sub(r'[\._]+', ' ', str(text))
    s = re.sub(r'\{[^}]*\}', '', s)
    prev = None
    while prev != s:
        prev = s
        s = NESTED_BRACKET.sub(' ', s)
    s = re.sub(r'^[\]\}\)）】\s]+', '', s)
    s = re.sub(r'[\[\{\(（【\s]+$', '', s)
    s = re.sub(r'\b(2160p|1080p|720p|480p|4K|BluRay|BDRip|WEB[- ]?DL|WEBRip|HDR|HDTV|x264|x265|'
               r'HEVC|AAC|AC3|DDP5 1|TrueHD|Atmos|REMUX|DV|SDR)\b.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[\s.\-]?\d{4}\s*$', '', s)
    return re.sub(r'\s{2,}', ' ', s).strip(' -_.')

def show_title_from_path(path):
    cands = title_candidates(path)
    return cands[0] if cands else ''

def sqlite_art(conn, media_id, media_type):
    art = {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT type, url FROM art WHERE media_id = ? AND media_type = ?",
                    (media_id, media_type))
        for k, v in cur.fetchall():
            art[k] = v
    except Exception as exc:
        log('sqlite art failed: %s' % exc)
    return art

def sqlite_season_art(conn, showid, season):
    if not showid or not season:
        return {}
    try:
        num = int(float(season))
    except (TypeError, ValueError):
        return {}
    row = q1(conn, "SELECT idSeason FROM season WHERE idShow = ? AND season = ? LIMIT 1",
             showid, num)
    if not row or not row[0]:
        return {}
    art = sqlite_art(conn, row[0], 'season')
    return dict(('season.' + k, v) for k, v in art.items())

def sqlite_show_art(conn, showid, season):
    art = {}
    if showid:
        art.update(sqlite_season_art(conn, showid, season))
        art.update(sqlite_art(conn, showid, 'tvshow'))
    return art

def sqlite_find_file_exact(conn, path):
    norm = norm_path(path)
    if not norm:
        return None
    cands = []
    for c in (unquote_deep(norm), norm):
        if c and c not in cands:
            cands.append(c)
    for cand in cands:
        row = q1(conn, "SELECT idFile FROM files WHERE strFilename = ? LIMIT 1", cand)
        if row and row[0]:
            return row[0]
    return None

def sqlite_find_file_like(conn, path):
    norm = norm_path(path)
    if not norm:
        return None
    dec = unquote_deep(norm)
    base = os.path.basename(dec)
    if not base or '%' in base:
        return None
    rows = []
    try:
        cur = conn.cursor()
        cur.execute("SELECT idFile, strFilename FROM files WHERE strFilename LIKE ? LIMIT 20",
                    ('%' + base,))
        rows = cur.fetchall()
    except Exception as exc:
        log('files 查询失败: %s' % exc)
        return None
    parent = os.path.basename(os.path.dirname(dec))
    for fid, fn in rows:
        d = os.path.basename(os.path.dirname(str(fn or '').replace('\\', '/')))
        if parent and d == parent:
            log('files 模糊命中(父目录 %s 一致) idFile=%s' % (parent, fid))
            return fid
    return None

def sqlite_find_id(conn, table, id_col, name_col, title):
    if not title:
        return None
    for sql, arg in (("SELECT %s FROM %s WHERE %s = ? LIMIT 1" % (id_col, table, name_col), title),
                     ("SELECT %s FROM %s WHERE %s LIKE ? LIMIT 1" % (id_col, table, name_col),
                      '%' + title + '%')):
        row = q1(conn, sql, arg)
        if row and row[0]:
            return row[0]
    return None

def sqlite_show_name(conn, showid):
    row = q1(conn, "SELECT c00 FROM tvshow WHERE idShow = ? LIMIT 1", showid)
    return (row[0] or '') if row else ''

def sqlite_movie_name(conn, movieid):
    row = q1(conn, "SELECT c00 FROM movie WHERE idMovie = ? LIMIT 1", movieid)
    return (row[0] or '') if row else ''

def sqlite_episode_title(conn, showid, season, episode):
    if not (showid and season and episode):
        return ''
    try:
        s, e = int(float(season)), int(float(episode))
    except (TypeError, ValueError):
        return ''
    row = q1(conn, "SELECT c00 FROM episode WHERE idShow = ? AND season = ? AND episode = ? LIMIT 1",
             showid, s, e)
    return (row[0] or '') if row else ''

def sqlite_plot(conn, table, id_col, media_id):
    if not media_id:
        return ''
    row = q1(conn, "SELECT c01 FROM %s WHERE %s = ? LIMIT 1" % (table, id_col), media_id)
    return (row[0] or '') if row else ''

def sqlite_episode_plot(conn, showid, season, episode):
    if not (showid and season and episode):
        return ''
    try:
        s, e = int(float(season)), int(float(episode))
    except (TypeError, ValueError):
        return ''
    row = q1(conn, "SELECT c01 FROM episode WHERE idShow = ? AND season = ? AND episode = ? LIMIT 1",
             showid, s, e)
    return (row[0] or '') if row else ''

def _fill_from_file_id(conn, fid, out, file_path, season, episode):
    row = q1(conn, "SELECT idEpisode, idShow, c00, c01 FROM episode WHERE idFile = ? LIMIT 1", fid)
    if row and row[1]:
        out['art'] = sqlite_show_art(conn, row[1], season)
        out['note'] = 'sqlite:file→ep→tvshow(%s)' % row[1]
        out['ep_title'] = row[2] or ''
        if not out['ep_title']:
            s2, e2 = parse_season_episode(file_path)
            out['ep_title'] = sqlite_episode_title(conn, row[1],
                                                   season or s2, episode or e2)
        out['show_title'] = sqlite_show_name(conn, row[1])
        
        out['plot'] = row[3] or sqlite_episode_plot(conn, row[1], season, episode) \
            or sqlite_plot(conn, 'tvshow', 'idShow', row[1])
        log('sqlite: file→episode idShow=%s keys=%s 单集=%r'
            % (row[1], sorted(out['art'].keys()), out['ep_title']))
        return True
    row = q1(conn, "SELECT idMovie, c00, c01 FROM movie WHERE idFile = ? LIMIT 1", fid)
    if row and row[0]:
        out['art'] = sqlite_art(conn, row[0], 'movie')
        out['note'] = 'sqlite:file→movie(%s)' % row[0]
        out['movie_title'] = row[1] or ''
        out['plot'] = row[2] or ''
        log('sqlite: file→movie id=%s keys=%s 片名=%r'
            % (row[0], sorted(out['art'].keys()), out['movie_title']))
        return True
    return False

def sqlite_resolve(conn, file_path, show_title, season, episode=''):
    out = {'art': {}, 'note': '', 'title': '', 'ep_title': '',
           'show_title': '', 'movie_title': '', 'plot': ''}
    path_dec = unquote_deep(file_path)

    cands = []
    for t in [show_title] + title_candidates(path_dec):
        
        for v in title_variants(t):
            if v and v not in cands:
                cands.append(v)
    for t in cands:
        sid = sqlite_find_id(conn, 'tvshow', 'idShow', 'c00', t)
        if sid:
            out['art'] = sqlite_show_art(conn, sid, season)
            out['note'] = 'sqlite:标题→tvshow(%s)' % sid
            out['title'] = t
            out['show_title'] = sqlite_show_name(conn, sid)
            out['ep_title'] = sqlite_episode_title(conn, sid, season, episode)
            out['plot'] = sqlite_episode_plot(conn, sid, season, episode) \
                or sqlite_plot(conn, 'tvshow', 'idShow', sid)
            log('sqlite: 标题 %r → idShow=%s keys=%s' % (t, sid, sorted(out['art'].keys())))
            stamp('  sqlite·A标题直查 → tvshow(%s) 候选=%r' % (sid, t))
            return out
        mid = sqlite_find_id(conn, 'movie', 'idMovie', 'c00', t)
        if mid:
            out['art'] = sqlite_art(conn, mid, 'movie')
            out['note'] = 'sqlite:标题→movie(%s)' % mid
            out['title'] = t
            out['movie_title'] = sqlite_movie_name(conn, mid) or t
            out['plot'] = sqlite_plot(conn, 'movie', 'idMovie', mid)
            log('sqlite: 标题 %r → idMovie=%s keys=%s' % (t, mid, sorted(out['art'].keys())))
            stamp('  sqlite·A标题直查 → movie(%s) 候选=%r' % (mid, t))
            return out
    stamp('  sqlite·A标题直查 → 未命中（候选 %d 个）' % len(cands))

    fid = sqlite_find_file_exact(conn, file_path)
    if fid is not None and _fill_from_file_id(conn, fid, out, file_path, season, episode):
        stamp('  sqlite·B文件精确 → 命中 idFile=%s' % fid)
        return out
    stamp('  sqlite·B文件精确 → 未命中')

    fid = sqlite_find_file_like(conn, file_path)
    if fid is not None and _fill_from_file_id(conn, fid, out, file_path, season, episode):
        stamp('  sqlite·C文件模糊 → 命中 idFile=%s' % fid)
        return out

    out['title'] = cands[0] if cands else ''
    return out

_NET_SCHEME_RE = re.compile(
    r'^(https?|smb|nfs|ftp|ftps|afp|upnp|plugin|rtmp|rtsp|p2p|webdav|daap|udap)://',
    re.IGNORECASE)

def is_local_fs_path(p):
    p = (p or '').strip()
    if not p:
        return False
    if _NET_SCHEME_RE.match(p):
        return False
    if p.startswith('/') or re.match(r'^[a-zA-Z]:[\\/]', p):
        return True
    return False

def local_art_from_path(file_path):
    norm = norm_path(file_path)
    if re.match(r'^https?://', norm, re.IGNORECASE):
        return ''
    d = os.path.dirname(norm)
    for _ in range(4):
        if not d or d in ('/', '.', '\\'):
            break
        try:
            names = xbmcvfs.listdir(d)[1]
        except Exception:
            names = None
        if names:
            low = {str(n).lower() for n in names}
            for name in LOCAL_ART_NAMES:
                if name.lower() in low:
                    hit = d + '/' + name
                    log('localfile 命中 %s' % hit)
                    return hit
        elif names is None:
            
            for name in LOCAL_ART_NAMES:
                cand = d + '/' + name
                try:
                    if xbmcvfs.exists(cand):
                        log('localfile 命中 %s' % cand)
                        return cand
                except Exception:
                    pass
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ''

def resolve_poster(item, art, INFO, sqlite_lookup, file_path):
    
    chain = [
        ('sqlite', lambda: poster_of(sqlite_lookup)),
        ('item', lambda: poster_of(art)),
        ('infolabel', poster_from_infolabel),
    ]
    if is_local_fs_path(file_path):
        chain.append(('localfile', lambda: local_art_from_path(file_path)))
    for name, getter in chain:
        value = getter()
        if value:
            log('poster 命中 %s -> %s' % (name, value))
            return value, name
    if FALLBACK_THUMB:
        for name, getter in (('sqlite_thumb', lambda: thumb_of(sqlite_lookup)),
                             ('item_thumb', lambda: thumb_of(art)),
                             ('infolabel_thumb', thumb_from_infolabel)):
            value = getter()
            if value:
                log('poster 命中 %s -> %s' % (name, value))
                return value, name
    return '', ''

def bilingual_split(text):
    s = str(text or '').strip()
    m = re.match(r'^(.*?[\u4e00-\u9fff0-9）)」』\]])[\s._\-·－]+([A-Za-z].+)$', s)
    if not m:
        return []
    zh = m.group(1).strip(' -_.·－—')
    en = m.group(2).strip(' -_.·－—')
    out = []
    if len(zh) >= 2:
        out.append(zh)
    if len(en) >= 2:
        out.append(en)
    return out

def title_variants(text):
    out = []

    def add(t):
        t = dedupe_repeat(str(t or '').strip())
        if t and len(t) >= 2 and t not in out:
            out.append(t)

    add(text)
    if not out:
        return out
    base = out[0]
    for t in bilingual_split(base):
        add(t)
    for seg in re.split(r'[：:·—–]| - ', base):
        add(seg.strip(' -_.·－—'))
    return out

def title_fallback(conn, movie_title, tv_show, season, episode, is_ep=False):
    cands = []
    for t in (tv_show, movie_title):
        for v in title_variants(t):
            if v not in cands:
                cands.append(v)
    if not cands:
        return '', ''
    plot = ''
    poster = ''
    own = False
    if conn is None:
        conn, _db = open_videos_db()
        own = True
    if conn is not None:
        try:
            for cand in cands:
                if is_ep:
                    look = sqlite_resolve(conn, '', cand, season, episode)
                    if look.get('plot') and not is_url(look['plot']) and not plot:
                        plot = look['plot']
                    p = poster_of(look.get('art') or {})
                    if p and not poster:
                        poster = p
                else:
                    mid = sqlite_find_id(conn, 'movie', 'idMovie', 'c00', cand)
                    if mid:
                        mp = sqlite_plot(conn, 'movie', 'idMovie', mid)
                        if mp and not is_url(mp) and not plot:
                            plot = mp
                        p = poster_of(sqlite_art(conn, mid, 'movie'))
                        if p and not poster:
                            poster = p
                if plot and poster:
                    return plot, poster
        except Exception as exc:
            log('title_fallback sqlite failed: %s' % exc)
        finally:
            if own:
                sqlite_close(conn)
    
    if plot and poster:
        return plot, poster
    return plot, poster

item = {}
INFO = {'poster': '', 'show_thumb': '', 'item_thumb': '', 'plot': '', 'title': '',
        'show_title': '', 'season': '', 'episode': '', 'source': '',
        'show_art_keys': [], 'ep_art_keys': [], 'movie_art_keys': []}
art = {}
file_path = ''
path_dec = ''
show_label = ''
season = ''
episode = ''
season_label = ''
episode_label = ''
raw_title = ''
meta_show = ''
meta_s = ''
meta_e = ''
SQLite = {'art': {}, 'note': '', 'title': '', 'ep_title': '',
          'show_title': '', 'movie_title': '', 'plot': ''}
conn = None
db_name = ''
sqlite_lookup = {}
sqlite_note = ''
tv_show = ''
ep_name = ''
is_tv = False
is_episode = False
movie_title = ''
poster = ''
poster_source = ''
plot = ''
plot_source = ''
content_text = ''

def nz(v):
    return str(v or '').strip() not in ('', '0')

def build_text(plot, poster, plot_src='', poster_src=''):
    content_lines = []
    if tv_show and is_episode:
        parts = [tv_show]
        season_ep = format_season_episode(season, episode)
        if season_ep:
            parts.append(season_ep)
        if ep_name:
            parts.append(ep_name)
        content_lines.append("-".join(parts))
    elif is_episode and ep_name:
        content_lines.append(ep_name)
    elif movie_title:
        content_lines.append("电影：%s" % movie_title)
    elif ep_name:
        content_lines.append(ep_name)
    if plot:
        content_lines.append("简介：%s" % plot)
    if not content_lines:
        content_lines.append("无法获取当前内容信息")
    if DIAG and (not poster or not plot):
        content_lines.append("")
        content_lines.append("［诊断］v%s  db=%s  命中=%s"
                             % (VERSION, db_name or '(无)', poster_src or '(全空)'))
        content_lines.append("［诊断］tvshowid=%s episodeid=%s movieid=%s"
                             % (item.get('tvshowid'), item.get('episodeid'), item.get('movieid')))
        content_lines.append("［诊断］剧名=%s  推断=%s  季集=%s/%s  is_tv=%s"
                             % (show_label or '(无)', show_title_from_path(path_dec) or '(无)',
                                season or '(无)', episode or '(无)', is_tv))
        content_lines.append("［诊断］raw_title=%s" % (raw_title[:80] if raw_title else '(无)'))
        content_lines.append("［诊断］file=%s" % ((file_path or '')[:120]))
        content_lines.append("［诊断］item art: %s" % (", ".join(sorted(art.keys())) or "(空)"))
        content_lines.append("［诊断］rpc 整剧 art: %s" % (", ".join(INFO['show_art_keys']) or "(空)"))
        content_lines.append("［诊断］sqlite: %s  keys=%s"
                             % (sqlite_note or '(未命中)',
                                ", ".join(sorted(sqlite_lookup.keys())) or "(空)"))
        content_lines.append("［诊断］plot源=%s  item=%s  infolabel=%s"
                             % (plot_src or '(全空)',
                                '有' if item.get('plot') else '无',
                                '有' if label('VideoPlayer.Plot') else '无'))
    return "\n".join(content_lines)

def build_payload(quiet=False):
    global item, INFO, art, file_path, path_dec, show_label, season, episode
    global season_label, episode_label, raw_title, meta_show, meta_s, meta_e
    global SQLite, conn, db_name, sqlite_lookup, sqlite_note
    global tv_show, ep_name, is_tv, is_episode, movie_title
    global poster, poster_source, plot, plot_source, content_text

    def st(msg):
        if not quiet:
            stamp(msg)

    item = {}
    art = {}

    file_path = (label('Player.FilenameAndPath') or label('Player.Filenameandpath'))
    path_dec = unquote_deep(file_path)

    show_label = label('VideoPlayer.TVShowTitle')
    season = label('VideoPlayer.Season')
    episode = label('VideoPlayer.Episode')
    
    season_label, episode_label = season, episode
    
    raw_title = label('VideoPlayer.Title')
    if raw_title and raw_title.strip().lower() in ('unknown', 'unknown.iso'):
        raw_title = ''
    st('InfoLabel 基本标签读取完成')
    
    meta_show, meta_s, meta_e = derive_tv_meta(path_dec, raw_title, raw_title)
    if not (season and episode):
        season = season or meta_s
        episode = episode or meta_e
    log('季集号推导: 标签=%s/%s  文件名补=%s/%s  meta_show=%r'
        % (season_label or '(无)', episode_label or '(无)',
           meta_s or '(无)', meta_e or '(无)', meta_show or '(无)'))

    SQLite = {'art': {}, 'note': '', 'title': '', 'ep_title': '',
              'show_title': '', 'movie_title': '', 'plot': ''}
    conn = None
    conn, db_name = open_videos_db()
    st('open_videos_db 完成 db=%s' % (db_name or '无'))
    if conn is not None:
        try:
            SQLite = sqlite_resolve(conn, file_path, show_label, season, episode)
            log('sqlite db=%s 说明=%s 命中标题=%r 剧名=%r 单集=%r'
                % (db_name, SQLite['note'], SQLite['title'],
                   SQLite['show_title'], SQLite['ep_title']))
        except Exception as exc:
            log('sqlite resolve failed: %s' % exc)
    st('sqlite_resolve 完成 note=%s' % (SQLite['note'] or '无'))
    sqlite_lookup = SQLite['art']
    sqlite_note = SQLite['note']

    poster, poster_source = resolve_poster(item, art, INFO, sqlite_lookup, path_dec)
    st('resolve_poster 完成 source=%s' % (poster_source or '空'))

    log('file=%s' % file_path)
    log('poster=%r source=%s' % (poster, poster_source))

    tv_show = smart_title(show_label or INFO['show_title'] or SQLite['show_title'])
    
    if not tv_show and meta_show:
        tv_show = meta_show
    
    tv_show = dedupe_repeat(cut_episode_tail(tv_show) or tv_show)

    ep_name = (plausible_title(label('VideoPlayer.EpisodeName'), tv_show, ep_mode=True)
               or (plausible_title(SQLite['ep_title'], tv_show, ep_mode=True) if tv_show else '')
               or (plausible_title(raw_title, tv_show, ep_mode=True) if tv_show else '')
               or (episode_name_from_text(tv_show, raw_title, path_dec) if tv_show else ''))
    
    if ep_name and tv_show and (ep_name == tv_show or is_pure_episode_number(ep_name)):
        ep_name = ''

    is_tv = is_tvshow_content(item, path_dec) or bool(meta_s or meta_e)
    is_episode = is_tv or (nz(season) and nz(episode))

    movie_title = ''
    db_movie = smart_title(SQLite['movie_title'])
    if db_movie and (not raw_title or looks_like_path(raw_title)):
        movie_title = db_movie
    if not movie_title:
        movie_title = (plausible_title(raw_title)
                       or db_movie
                       or ('' if tv_show and is_episode else show_title_from_path(path_dec)))
    if tv_show and movie_title.startswith(tv_show + '-'):
        movie_title = movie_title[len(tv_show) + 1:].strip()
    if tv_show and movie_title == tv_show:
        movie_title = ''
    
    movie_title = re.sub(r'(?<=[\u4e00-\u9fff])\.(?=[A-Za-z])', ' ', movie_title)
    movie_title = dedupe_repeat(movie_title)
    st('标题推导完成 剧名=%r 单集=%r 片名=%r' % (tv_show or '', ep_name or '', movie_title or ''))

    plot, plot_source = '', ''
    for _src in ('infolabel', 'infolabel_outline', 'sqlite'):
        if _src == 'infolabel':
            _val = label('VideoPlayer.Plot')
        elif _src == 'infolabel_outline':
            _val = label('VideoPlayer.PlotOutline')
        else:
            _val = SQLite['plot']
        _clean = clean_plot(_val)
        if _clean:
            plot, plot_source = _clean, _src
            break
    log('plot 来源=%s len=%d' % (plot_source or '(全空)', len(plot)))
    st('plot 完成 来源=%s' % (plot_source or '空'))

    if not plot or not poster:
        fb_plot, fb_poster = title_fallback(conn, movie_title, tv_show, season, episode,
                                            is_ep=bool(is_episode))
        if fb_plot and not plot:
            plot, plot_source = fb_plot, 'title_fallback'
            log('标题反查 plot 命中 len=%d' % len(plot))
        if fb_poster and not poster:
            poster, poster_source = fb_poster, 'title_fallback'
            log('标题反查 poster 命中')
    st('title_fallback 完成 plot源=%s' % (plot_source or '空'))

    content_text = build_text(plot, poster, plot_source, poster_source)
    st('内容拼装完成，准备打开窗口')

    return {
        'v': VERSION,
        'key': cache_key(file_path),
        'file': file_path,
        'poster': poster,
        'poster_source': poster_source,
        'plot': plot,
        'plot_source': plot_source,
        'content_text': content_text,
        'tv_show': tv_show,
        'ep_name': ep_name,
        'movie_title': movie_title,
        'season': season,
        'episode': episode,
        'is_tv': bool(is_tv),
        'is_episode': bool(is_episode),
        'db': db_name,
        'note': sqlite_note,
        'ts': time.time(),
    }

def apply_payload(p):
    global poster, poster_source, plot, plot_source, content_text
    global tv_show, ep_name, movie_title, season, episode, is_tv, is_episode
    global file_path, path_dec, db_name, sqlite_note
    if not isinstance(p, dict):
        p = {}
    poster = p.get('poster') or ''
    poster_source = p.get('poster_source') or ''
    plot = p.get('plot') or ''
    plot_source = p.get('plot_source') or ''
    content_text = p.get('content_text') or '无法获取当前内容信息'
    tv_show = p.get('tv_show') or ''
    ep_name = p.get('ep_name') or ''
    movie_title = p.get('movie_title') or ''
    season = p.get('season') or ''
    episode = p.get('episode') or ''
    is_tv = bool(p.get('is_tv'))
    is_episode = bool(p.get('is_episode'))
    db_name = p.get('db') or ''
    sqlite_note = p.get('note') or ''
    if p.get('file'):
        file_path = p['file']
    if p.get('path_dec'):
        path_dec = p['path_dec']
    return p

# -*- coding:utf-8 -*-
"""点播播放：番剧分集 / 视频分P / 实际播放（DASH MPD → inputstream.adaptive）。

v0.4.0 流程：
  1. 调 B 站 playurl API (fnval=4048) 获取 DASH 数据
  2. playback/mpd.generate_mpd(dash) 生成 MPD XML
     - Video: per-Representation <SegmentBase indexRange> +
       <Initialization range> (v0.1.0 形态，让 adaptive 精准拼 Range)
     - Audio: 多 AdaptationSet (AAC / Dolby / Hi-Res FLAC, v0.3.0 形态)
     - BaseURL = B 站 CDN 直链（不过代理）
  3. MPD 写 special://temp/plugin.video.bili/{cid}.mpd
  4. plugin.set_resolved_url 把 http://127.0.0.1:{port}/{cid}.mpd 喂给
     inputstream.adaptive，4 个 properties：
       inputstream.adaptive.manifest_type     = 'mpd'
       inputstream.adaptive.manifest_headers  = 'Referer=https://www.bilibili.com'
       inputstream.adaptive.stream_headers    = 'Referer=https://www.bilibili.com'
       inputstream                              = 'inputstream.adaptive'
"""
import os

from core import plugin, xbmc, xbmcvfs
from utils import getSetting, get_temp_path, is_dash_capable, tag
from api import get_api_data, BILI_REFERER
from live import stop_all_live_danmaku
from playback import (
    generate_mpd, generate_ass, report_history,
)


# B 站 playurl fnval: 4048 = DASH (走 inputstream.adaptive); 1 = durl (单文件 MP4, 720P 上限)
DASH_FNVAL = 4048


def _try_wiliwili_playurl(bvid, cid, qn, fnval=None):
    if fnval is None:
        fnval = DASH_FNVAL
    params = {
        'bvid': bvid, 'cid': str(cid),
        'gaia_source': 'view-card', 'from_client': 'BROWSER',
        'is_main_page': 'false', 'need_fragment': 'false',
        'isGaiaAvoided': 'true', 'voice_balance': '1',
        'web_location': '1315873', 'qn': str(qn),
        'fourk': '1', 'fnval': str(fnval), 'fnver': '0',
    }
    try:
        from api import getWbiKeys, encWbi
        img_key, sub_key = getWbiKeys()
        params = encWbi(params, img_key, sub_key)
    except Exception as e:
        xbmc.log('[wiliwili-playurl] WBI sign failed: %s' % e, xbmc.LOGDEBUG)

    for path in ('/x/player/wbi/playurl', '/x/web-interface/playurl'):
        res = get_api_data(path, data=params, raw=True)
        if res.get('code') == 0 and (res.get('data') or res.get('result')):
            xbmc.log('[wiliwili-playurl] success via %s' % path, xbmc.LOGDEBUG)
            return path, res
        xbmc.log(
            '[wiliwili-playurl] %s failed code=%s msg=%s' % (
                path, res.get('code'), res.get('message', ''),
            ),
            xbmc.LOGDEBUG,
        )
    return None, res


def _media_id_to_season(media_id) -> int:
    res = get_api_data('/pgc/review/user', {'media_id': media_id})
    if res['code'] == 0:
        return res['result']['media']['season_id']
    return 0


@plugin.route('/bangumi/<type>/<id>/')
def bangumi(type, id):
    items = []
    if type == 'media_id':
        type = 'season_id'
        id = _media_id_to_season(id)
    res = get_api_data('/pgc/view/web/season', {type: id})
    if res['code'] != 0:
        return items
    for episode in res['result']['episodes']:
        if episode['badge']:
            label = tag('【' + episode['badge'] + '】', 'pink') + episode['share_copy']
        else:
            label = episode['share_copy']
        context_menu = [(
            '仅播放音频',
            f"PlayMedia({plugin.url_for('video', id=episode['bvid'], cid=episode['cid'], ispgc='true', audio_only='true', title=episode['share_copy'])})",
        )]
        items.append({
            'label': label,
            'path': plugin.url_for('video', id=episode['bvid'], cid=episode['cid'],
                                   ispgc='true', audio_only='false',
                                   title=episode['share_copy']),
            'is_playable': True,
            'icon': episode['cover'],
            'thumbnail': episode['cover'],
            'context_menu': context_menu,
            'info': {
                'mediatype': 'video', 'title': episode['share_copy'],
                'duration': episode['duration'] / 1000,
                'plot': f"{episode['share_copy']}\n{episode['bvid']}\nep{episode['ep_id']}",
            },
            'info_type': 'video',
        })
    return items


@plugin.route('/videopages/<id>/')
def videopages(id):
    videos = []
    res = get_api_data('/x/web-interface/view', {'bvid': id})
    data = res['data']
    if res['code'] != 0:
        return videos
    for item in data['pages']:
        pic = item.get('first_frame') or data['pic']
        context_menu = [(
            '仅播放音频',
            f"PlayMedia({plugin.url_for('video', id=data['bvid'], cid=item['cid'], ispgc='false', audio_only='true', title=item['part'])})",
        )]
        videos.append({
            'label': item['part'],
            'path': plugin.url_for('video', id=data['bvid'], cid=item['cid'],
                                   ispgc='false', audio_only='false',
                                   title=item['part']),
            'is_playable': True,
            'icon': pic, 'thumbnail': pic,
            'context_menu': context_menu,
            'info': {
                'mediatype': 'video', 'title': item['part'],
                'duration': item['duration'],
            },
            'info_type': 'video',
        })
    return videos


# ── 实际播放入口 ─────────────────────────────────────────────────────

@plugin.route('/video/<id>/<cid>/<ispgc>/<audio_only>/<title>/')
def video(id, cid, ispgc, audio_only, title):
    stop_all_live_danmaku()

    cid = str(cid)
    ispgc = ispgc == 'true'
    audio_only = audio_only == 'true'
    video_url = ''

    if cid == '0':
        res = get_api_data('/x/web-interface/view', {'bvid': id})
        if res['code'] != 0:
            return
        data = res['data']
        cid = data['pages'][0]['cid']
        if 'redirect_url' in data and 'bangumi/play/ep' in data['redirect_url']:
            ispgc = True
        else:
            ispgc = False

    if ispgc:
        url = '/pgc/player/web/playurl'
    else:
        url = None

    qn = getSetting('video_resolution')
    adaptive = is_dash_capable()
    fnval = DASH_FNVAL if adaptive else 1
    xbmc.log('[video] fnval=%d (adaptive %s)' % (fnval, 'on' if adaptive else 'off'),
             xbmc.LOGDEBUG)

    if ispgc:
        params = {'bvid': id, 'cid': cid, 'qn': qn, 'fnval': fnval,
                  'fnver': 0, 'fourk': 1}
        res = get_api_data(url, data=params, raw=True)
        if res.get('code') != 0:
            return
    else:
        wiliwili_url, res = _try_wiliwili_playurl(id, cid, qn, fnval=fnval)
        if wiliwili_url is None:
            xbmc.log('[video] wiliwili failed, fallback /x/player/playurl', xbmc.LOGDEBUG)
            params = {'bvid': id, 'cid': cid, 'qn': qn, 'fnval': fnval,
                      'fnver': 0, 'fourk': 1,
                      'from_client': 'BROWSER', 'isGaiaAvoided': 'true',
                      'web_location': '1315873', 'need_fragment': 'false'}
            res = get_api_data('/x/player/playurl', data=params, raw=True)
            if res.get('code') != 0:
                return
            url = '/x/player/playurl'
        else:
            url = wiliwili_url

    data = res['result'] if ispgc else res['data']
    port = getSetting('server_port') or '54321'

    # 1) audio_only: 单音轨 pipe 直连（不走 adaptive）
    if 'dash' in data and audio_only:
        from playback import collect_audio_tracks, select_by_user_pref
        tracks = select_by_user_pref(collect_audio_tracks(data['dash']))
        if not tracks:
            return
        t = tracks[0]
        video_url = {
            'label': title,
            'path': '%s|%s' % (t.base_url, BILI_REFERER),
            'is_playable': True,
        }
        plugin.set_resolved_url(video_url)
        return

    # 2) DASH: 写 MPD → set_resolved_url 喂 inputstream.adaptive
    if 'dash' in data:
        basepath = get_temp_path()
        if not basepath:
            return

        try:
            mpd_text = generate_mpd(data['dash'])
        except Exception as e:
            xbmc.log('[video] generate_mpd failed: %s' % e, xbmc.LOGERROR)
            return

        mpd_path = os.path.join(basepath, '%s.mpd' % cid)
        try:
            with xbmcvfs.File(mpd_path, 'w') as f:
                success = f.write(mpd_text)
            if not success:
                xbmc.log('[video] MPD write failed: %s' % mpd_path, xbmc.LOGERROR)
                return
        except Exception as e:
            xbmc.log('[video] MPD write error: %s' % e, xbmc.LOGERROR)
            return

        # 用 HTTP URL 喂 inputstream.adaptive。file:// 路径在某些
        # 平台 (Kodi libcurl sandbox) 不支持，必须走 HTTP 栈。
        # 静态 MPD server 由 http_server.py 跑在 service 进程里
        # (service.py 启动 xbmc.Monitor 循环 bind 54321)。如果
        # xbmc.service 扩展在某些部署上启动失败，daemon thread
        # fallback 在 addon.py 进程里也尝试 bind。
        mpd_url = 'http://127.0.0.1:%s/%s.mpd' % (port, cid)
        xbmc.log('[video] MPD written: %s → %s' % (mpd_path, mpd_url), xbmc.LOGDEBUG)
        video_url = {
            'path': mpd_url,
            'is_playable': True,
            'properties': {
                'inputstream': 'inputstream.adaptive',
                'inputstream.adaptive.manifest_type': 'mpd',
                'inputstream.adaptive.manifest_headers': BILI_REFERER,
                'inputstream.adaptive.stream_headers': BILI_REFERER,
            },
        }

    elif 'durl' in data:
        durl_url = data['durl'][0]['url']
        if durl_url:
            video_url = {
                'path': '%s|%s' % (durl_url, BILI_REFERER),
                'is_playable': True,
            }
    else:
        video_url = ''

    if not video_url:
        return

    ass = None
    if getSetting('enable_danmaku') == 'true':
        ass = generate_ass(cid)
    if getSetting('report_history') == 'true':
        report_history(id, cid)

    plugin.set_resolved_url(video_url, subtitles=ass)

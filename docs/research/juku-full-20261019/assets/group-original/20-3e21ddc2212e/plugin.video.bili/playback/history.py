# -*- coding:utf-8 -*-
"""播放历史上报（POST /x/click-interface/web/heartbeat）。"""
from core import xbmc
from api import get_cookie_value, post_data


def report_history(bvid: str, cid) -> dict:
    """上报播放进度到 B 站历史。失败仅写日志，不影响播放流程。"""
    data = {
        'bvid': bvid,
        'cid': cid,
        'csrf': get_cookie_value('bili_jct'),
    }
    res = post_data('https://api.bilibili.com/x/click-interface/web/heartbeat', data)
    if res.get('code') != 0:
        xbmc.log(
            '[playback.history] report_history failed: %s' % res.get('message', ''),
            xbmc.LOGWARNING,
        )
    return res

# -*- coding:utf-8 -*-
"""点播弹幕 ASS 生成：下载 B 站 XML → danmaku2ass 转 ASS。"""
import gzip
import os

import requests

from core import xbmc, xbmcvfs
from utils import get_temp_path, getSetting
from subtitle.danmaku2ass import Danmaku2ASS, ReadComments


# B 站偶发返回未声明 Content-Encoding 的 gzip 字节，requests 不会自动解压。
# 也偶发返回 UTF-8 BOM 头。这里手动兜底 (magic bytes 比信 Content-Encoding 头更稳)。
_GZIP_MAGIC = b'\x1f\x8b'
_UTF8_BOM = b'\xef\xbb\xbf'


# 点播弹幕上限：B 站热门点播视频 XML 可含数千条弹幕——不限制会导致
# ASS 数十 MB、Kodi 解析慢、CPU 高。改为"按视频时长均匀采样"——
# 保留视频全程的弹幕分布而非只取前 N 条，覆盖整段视频。
#
# 80 条 = 屏幕能同时渲染的弹幕数（同屏不超过 80）——这是"同屏数量限制"
# 的真正含义，与直播端的 live/danmaku.MAX_LIST=80 保持一致。
#
# 此外另加一个 500 的硬上限防止超长视频 ASS 仍然过大——
# 大于 500 条时按 500 均匀采样。
DANMAKU_SCREEN_CAP = 80
DANMAKU_TOTAL_CAP = 500


def generate_ass(cid) -> str | None:
    """为指定 cid 下载弹幕并生成 ASS 文件，返回 ASS 路径；已存在则直接返回缓存。"""
    basepath = get_temp_path()
    if not basepath:
        return
    xmlfile = os.path.join(basepath, str(cid) + '.xml')
    assfile = os.path.join(basepath, str(cid) + '.ass')
    if xbmcvfs.exists(assfile):
        return assfile

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/59.0.3071.115 Safari/537.36'
        )
    }
    try:
        res = requests.get(
            f'https://comment.bilibili.com/{cid}.xml',
            headers=headers, timeout=10,
        )
        # B 站有时返回 gzip 字节但不带 Content-Encoding 头 (违反 HTTP 规范)，
        # requests 不会自动解压。也有时返回 UTF-8 BOM 头。
        # 这里手动兜底：先按 Content-Encoding 头判断，再看 magic bytes。
        raw = res.content
        if res.headers.get('Content-Encoding') == 'gzip' or raw[:2] == _GZIP_MAGIC:
            raw = gzip.decompress(raw)
        if raw[:3] == _UTF8_BOM:
            raw = raw[3:]
        content = raw.decode('utf-8', errors='replace')
    except Exception as e:
        xbmc.log('[playback.ass] generate_ass failed to fetch danmaku: %s' % str(e), xbmc.LOGWARNING)
        return

    # get_temp_path 内部已调 make_dirs；这里不再重复调用，避免误判 None 为失败
    with xbmcvfs.File(xmlfile, 'w') as f:
        success = f.write(content)
    if not success:
        return

    # 读 XML → 均匀采样。danmaku2ass.ReadComments 默认读全部；
    # 我们先排序再按"DANMAKU_SCREEN_CAP 段时间窗口内最多 N 条"采样——
    # 视频每段（比如每 8s = stay_time）的弹幕上限 ≈ 同屏 80。
    # 总条数超 DANMAKU_TOTAL_CAP 时按 500 条均匀采样。
    try:
        all_comments = ReadComments(xmlfile, 'autodetect',
                                    font_size=float(getSetting('font_size')))
    except Exception as e:
        # minidom / 任何 XML 解析失败都吞掉,让视频正常播放 (无弹幕) 即可
        xbmc.log('[playback.ass] cid=%s danmaku parse failed: %s' % (cid, str(e)), xbmc.LOGWARNING)
        return
    all_comments.sort(key=lambda c: c[0])  # 按时间戳（c[0]）升序

    if len(all_comments) > DANMAKU_TOTAL_CAP:
        # 均匀采样到 DANMAKU_TOTAL_CAP 条：保留全程分布
        step = len(all_comments) / DANMAKU_TOTAL_CAP
        sampled = [all_comments[int(i * step)] for i in range(DANMAKU_TOTAL_CAP)]
        all_comments = sampled
        xbmc.log(
            '[playback.ass] cid=%s has too many danmaku, '
            'uniformly sampled to %d' % (cid, DANMAKU_TOTAL_CAP),
            xbmc.LOGINFO,
        )

    # "同屏 ≤ 80" = 任何 stay_time 时间窗口内 ≤ 80 条。
    # 算法：滑动窗口（窗口长度 = stay_time）扫一遍，保留每个窗口里
    # 超过 80 条的部分中"超出最早 80 条"的多余条——简化：直接对时间排序后
    # 切成 stay_time 段，每段最多 80 条（按时间均匀采样到 80）。
    duration = float(getSetting('danmaku_stay_time'))
    if duration > 0 and len(all_comments) > DANMAKU_SCREEN_CAP:
        # 视频总时长 = 最后一个弹幕的时间戳
        last_t = all_comments[-1][0]
        if last_t > duration:
            window_count = int(last_t / duration) + 1
            filtered = []
            for w in range(window_count):
                ws = w * duration
                we = ws + duration
                in_window = [c for c in all_comments if ws <= c[0] < we]
                if len(in_window) > DANMAKU_SCREEN_CAP:
                    step = len(in_window) / DANMAKU_SCREEN_CAP
                    in_window = [in_window[int(i * step)] for i in range(DANMAKU_SCREEN_CAP)]
                filtered.extend(in_window)
            all_comments = sorted(filtered, key=lambda c: c[0])
            xbmc.log(
                '[playback.ass] cid=%s applied %d-window cap of %d danmaku each' % (
                    cid, window_count, DANMAKU_SCREEN_CAP,
                ), xbmc.LOGINFO,
            )

    font_size = float(getSetting('font_size'))
    text_opacity = float(getSetting('opacity'))
    width = 1920
    height = 540
    reserve_blank = int((1.0 - float(getSetting('display_area'))) * height)
    Danmaku2ASS(
        None, 'autodetect', assfile,
        width, height,
        reserve_blank=reserve_blank,
        font_face='sans-serif',
        font_size=font_size,
        text_opacity=text_opacity,
        duration_marquee=duration,
        duration_still=duration,
        comments=all_comments,
    )
    if xbmcvfs.exists(assfile):
        return assfile

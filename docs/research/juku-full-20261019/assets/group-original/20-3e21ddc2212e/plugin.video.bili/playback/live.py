# -*- coding:utf-8 -*-
"""直播流分辨率 / 编码选择：按 codec (hevc 优先) × format (fmp4/hls 优先) × qn (高优先) 选最佳。

FLV vs fmp4/HLS 质量相同（同一 qn 是同一码率同一编码，只是容器不同）。
选择 format 实际是延迟/兼容性权衡：fmp4 切片小延迟低，HLS 切片居中，
FLV 整段切片延迟大且 v0.4.0 已主动放弃 FLV pipe 路径（看 routes/live.py
注释）。所以现代 format 优先。
"""
from core import xbmc
from utils import getSetting

# settings.xml 中 live_video_encoding 的 codecid 值（字符串字面量）
LIVECODEC_HEVC = '12'

# B 站直播流 codec_name 字符串（小写）。B 站目前没推 AV1 直播，但留
# 兼容分支以便未来直接启用。
_CODEC_BUCKET = {
    'hevc': 'hevc',
    'avc': 'avc',
    'av1': 'av1',
}


def choose_live_resolution(streams: list) -> dict | None:
    """从 B 站直播 API 返回的 streams 中选最佳编码，返回 dict：
        - urls, format_name, codec_name, current_qn, master_url

    优先级：
      1. codec：用户偏好的 codec（HEVC 优先 / AVC 优先）
      2. format：fmp4/HLS > FLV（fmp4 延迟低，HLS 切片小；FLV 已过时）
      3. qn：同 codec × format 内取最高清晰度
    """
    if not streams:
        return None

    # settings.xml option value 是字符串；用 .strip() 兜底前后空白。
    encoding = getSetting('live_video_encoding').strip()
    prefer_hevc = (encoding == LIVECODEC_HEVC)

    def _codes(lst):
        return ', '.join('%s(qn=%s)' % (c['codec_name'], c['current_qn']) for c in lst)

    # 全局 master_url（http_hls 协议才有，http_stream 没有）
    global_master_url = ''
    for s in streams:
        if s.get('master_url'):
            global_master_url = s['master_url']
            break

    # 按 (codec) × (modern format / FLV) 分类。modern = fmp4/ts/HLS
    # （除 FLV 外都是现代容器）。
    buckets = {(codec, fmt): [] for codec in _CODEC_BUCKET for fmt in ('modern', 'flv')}

    for stream in streams:
        for fmt in stream.get('format', []):
            is_flv = (fmt['format_name'] == 'flv')
            for codec in fmt['codec']:
                bucket_codec = _CODEC_BUCKET.get(codec.get('codec_name', ''))
                if not bucket_codec:
                    # 未知 codec（B 站推新格式时）— 跳过但记日志
                    xbmc.log(
                        '[playback.live] unknown live codec_name=%r, skipped' % (
                            codec.get('codec_name'),
                        ),
                        xbmc.LOGDEBUG,
                    )
                    continue
                bucket_fmt = 'flv' if is_flv else 'modern'
                buckets[(bucket_codec, bucket_fmt)].append({
                    'format_name': fmt['format_name'],
                    'codec_name': codec['codec_name'],
                    'current_qn': int(codec['current_qn']),
                    'urls': [
                        info['host'] + codec['base_url'] + info['extra']
                        for info in codec['url_info']
                    ],
                    'master_url': global_master_url,
                })

    def pick(lst):
        return max(lst, key=lambda x: x['current_qn']) if lst else None

    # 把 buckets 拆成局部变量便于日志输出
    modern_hevc, modern_avc, modern_av1 = buckets[('hevc', 'modern')], buckets[('avc', 'modern')], buckets[('av1', 'modern')]
    flv_hevc, flv_avc, flv_av1 = buckets[('hevc', 'flv')], buckets[('avc', 'flv')], buckets[('av1', 'flv')]

    xbmc.log(
        '[playback.live] available: hevc_modern=[%s] avc_modern=[%s] av1_modern=[%s] '
        'hevc_flv=[%s] avc_flv=[%s] av1_flv=[%s]' % (
            _codes(modern_hevc), _codes(modern_avc), _codes(modern_av1),
            _codes(flv_hevc), _codes(flv_avc), _codes(flv_av1),
        ),
        xbmc.LOGDEBUG,
    )

    # 链式 or 必须按"先 codec 偏好、再 format 偏好"严格排序。
    # 第一个非空桶胜出；桶内 pick 取最高 qn。
    if prefer_hevc:
        # HEVC：先 modern，再 FLV，再降级到 AVC
        best = (
            pick(modern_hevc) or pick(flv_hevc)
            or pick(modern_avc) or pick(flv_avc)
            or pick(modern_av1) or pick(flv_av1)
        )
    else:
        # AVC：先 modern，再 FLV，再降级到 HEVC（B 站某些直播只有 HEVC）
        best = (
            pick(modern_avc) or pick(flv_avc)
            or pick(modern_hevc) or pick(flv_hevc)
            or pick(modern_av1) or pick(flv_av1)
        )

    if not best:
        return None

    xbmc.log(
        '[playback.live] selected: %s/%s qn=%s' % (
            best['format_name'], best['codec_name'], best['current_qn']
        ),
        xbmc.LOGDEBUG,
    )
    return best

# -*- coding:utf-8 -*-
"""点播视频分辨率 / 编码选择。

B 站 playurl 响应的视频轨全部在 `dash.video` 里，Dolby Vision 轨通过
codec 字符串前缀区分（`dvh1` / `dvhe`）。没有独立的 `dash.dolby_video` 字段
（参考 wiliwili 源码 `Dash` 类定义）。

B 站 codecid 约定：7=AVC(H.264), 12=HEVC(H.265), 13=AV1。
"""
from utils import getSetting

# Dolby Vision 视频的 codec 字符串前缀
_DV_CODEC_PREFIXES = ('dvh1.', 'dvhe.')

# 按 settings.xml video_encoding 偏好值 → 编码优先级表
# 同一个 id 通常有多个 codecid 的轨（如 1080P 既有 HEVC 也有 AV1），
# MPD 中 Representation 顺序决定 player 默认选哪条。
_CODEC_PREFERENCE = {
    12: [12, 7, 13],   # 用户选 HEVC 优先 → HEVC > AVC > AV1
    7:  [7, 12, 13],   # 用户选 AVC 优先  → AVC > HEVC > AV1
    13: [13, 7, 12],   # 用户选 AV1 优先  → AV1 > AVC > HEVC
}


def _is_dolby_vision(video_track: dict) -> bool:
    """判断一个视频轨是否是杜比视界（DV）"""
    codecs = (video_track.get('codecs') or '').lower()
    return any(codecs.startswith(p) for p in _DV_CODEC_PREFIXES)


def _filter_by_preference(items: list, current_value, key: str = 'id') -> list:
    """按偏好值降级筛选。

    items 应按 key 降序排列。返回满足 `item[key] == current_value` 的项；
    没有匹配项时降级到 key 严格小于 current_value 的最大项；仍没有则
    返回空（让调用方决定后续动作）。
    """
    at = [i for i in items if i[key] == current_value]
    if at:
        return at
    below = [i for i in items if i[key] < current_value]
    if below:
        return [below[0]]
    return []


def _select_video_candidates(dash: dict, codec_preference: list) -> list:
    """从 dash.video 选候选轨（按 codec 字符串识别 DV）。

    排序：(DV 在前) → id 降序 → codec 按 codec_preference 顺序。
    codec_preference 是按用户偏好排好序的 codecid 列表，如 [12, 7, 13]。
    """
    all_videos = list(dash.get('video', []))
    if not all_videos:
        return []

    # 在每条轨上标 _source：DV 轨 → 'dolby'，其他 → 'regular'
    for v in all_videos:
        v['_source'] = 'dolby' if _is_dolby_vision(v) else 'regular'

    # codec → 偏好排名（0 最高）
    rank = {c: i for i, c in enumerate(codec_preference)}

    # DV 轨排前面（player 优先 DV），其余按 id desc、codec 按偏好**升序**排。
    # rank 越小越偏好（HEVC=0 < AVC=1 < AV1=2），所以同 id 内 rank
    # 升序 = 偏好优先。用 `reverse=True` 整体反号：id 取负就变 desc，
    # rank 保持原方向（升序）就是"小 rank 优先"。
    dv_tracks = [v for v in all_videos if v['_source'] == 'dolby']
    regular = [v for v in all_videos if v['_source'] == 'regular']
    regular.sort(
        key=lambda x: (-x.get('id', 0), rank.get(x.get('codecid', 7), 99)),
        reverse=False,
    )
    return dv_tracks + regular


def choose_resolution(dash: dict) -> list:
    """按 video_resolution + video_encoding 设置选视频 Representation 列表。

    关键设计：
    - **id 维度**：精确匹配用户的 id（分辨率档位）；无匹配则降级到
      最近一档（更小 id），再没有则返回空。
    - **codec 维度**：按用户偏好顺序在 MPD 中排 Representation（player
      默认选第一条），不跨 codec 凑数。
    - **DV 轨**：始终带在结果最前（player 优先 DV）。
    """
    try:
        current_id = int(getSetting('video_resolution'))
    except (TypeError, ValueError):
        current_id = 116
    try:
        current_codecid = int(getSetting('video_encoding'))
    except (TypeError, ValueError):
        # 默认 HEVC：与 settings.xml `<default>12</default>` 对齐
        current_codecid = 12

    codec_preference = _CODEC_PREFERENCE.get(current_codecid, [12, 7, 13])
    candidates = _select_video_candidates(dash, codec_preference)
    if not candidates:
        return []

    # 普通轨：按 id 降级到一档（_filter_by_preference 行为）
    regular = [v for v in candidates if v['_source'] == 'regular']
    if regular:
        by_resolution = _filter_by_preference(regular, current_id, 'id')
        # 同一 id 内可能有多 codec × 多 bandwidth 轨。按 codec 偏好分组，
        # **组内**再按 bandwidth 降序——保持 _select_video_candidates
        # 排好的 codec 顺序，只在同 codec 内让 player 选最高码率。
        if by_resolution:
            by_codec_then_bandwidth = []
            for codecid in codec_preference:
                group = [v for v in by_resolution if v.get('codecid') == codecid]
                group.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
                by_codec_then_bandwidth.extend(group)
            regular = by_codec_then_bandwidth
        else:
            # 该 id 没匹配，降级到更小 id 的**最高 id** 那一组
            available = [
                v for v in regular
                if v.get('codecid') in codec_preference
            ]
            if available:
                available.sort(key=lambda x: x.get('id', 0), reverse=True)
                top_id = available[0].get('id', 0)
                regular = [v for v in available if v.get('id', 0) == top_id]
                # 按 codec 偏好分组（保持偏好顺序），组内按 bandwidth 排
                by_codec_then_bandwidth = []
                for codecid in codec_preference:
                    group = [v for v in regular if v.get('codecid') == codecid]
                    group.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
                    by_codec_then_bandwidth.extend(group)
                regular = by_codec_then_bandwidth
            else:
                regular = []

    # DV 轨：总是带（DV 总是 HEVC，与用户偏好 HEVC 一致时最佳）。
    # 如果用户偏好是 AVC 但 DV 是 HEVC 仍带 → 让 player 决定；不强制降级。
    # DV 内部按 bandwidth 降序（保持 DV 自己的最高画质）。
    dv = [v for v in candidates if v['_source'] == 'dolby']
    dv.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)

    return dv + regular


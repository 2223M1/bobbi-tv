# -*- coding:utf-8 -*-
"""音轨收集 + 偏好选择。

B 站 playurl DASH 响应的音轨分散在三个字段（具体 ID 取决于大会员/视频可用性）：
  - data['dash']['audio'][]                  普通 AAC（典型 id: 30280 / 30232 / 30216）
  - data['dash']['dolby'] = {audio: [...]}   杜比嵌套对象，audio 是数组（典型 id: 30255 = E-AC-3 JOC, Atmos）
  - data['dash']['flac']  = {audio: {...}}   FLAC 嵌套对象，audio 是单条对象（典型 id: 30250 / 30251 / 30252）

旧 flat 形式 dash['dolby_audio'] / dash['flac_audio'] 仍然兼容（部分旧接口用）。

参考：https://github.com/xfangfang/wiliwili/blob/yoga/wiliwili/include/api/bilibili/result/video_detail_result.h
本模块把它们统一成 AudioTrack 列表，再按用户偏好 + 降级链挑选。
"""
from dataclasses import dataclass, field
from typing import List, Optional

from core import xbmc
from utils import getSetting


# B 站音频 id → (展示名, MPD label)
AUDIO_QUALITY_LABEL = {
    30216: ('低码',     '64K AAC'),
    30232: ('标准',     '132K AAC'),
    30280: ('高清',     '192K AAC'),
    30250: ('Hi-Res',   'FLAC 192K/24bit'),
    30251: ('Hi-Res',   'FLAC 192K/16bit'),
    30252: ('FLAC',     'FLAC 96K'),
    30255: ('杜比',     'E-AC-3 JOC (Atmos)'),
}

# 偏好常量（B 站 playurl 实际 id 约定）
# 192K AAC = '高清' 标签，30280
# Dolby E-AC-3 JOC (Atmos 基础层) id=30250（B 站实测：codecs=ac-3 或 ec-3）
# FLAC Hi-Res id=30251（B 站实测：codecs=fLaC）
PREF_ATMOS = 30250
PREF_HIRES = 30251
PREF_HIGH  = 30280
PREF_MED   = 30232
PREF_LOW   = 30216

# AAC 降级链（不含 30250/30251，避免选 Atmos/HiRes 时混进 AAC）
_AAC_FALLBACK = (PREF_HIGH, PREF_MED, PREF_LOW)


@dataclass
class AudioTrack:
    """统一的音轨表示，与 B 站来源字段无关。"""
    id: int
    base_url: str
    backup_url: list = field(default_factory=list)
    bandwidth: int = 0
    codecs: str = ''
    audio_sampling_rate: Optional[int] = None
    segment_base: Optional[dict] = None
    kind: str = 'aac'                # 'aac' | 'dolby' | 'flac'
    label: str = ''                  # 人类可读，用于 Kodi "音轨" 菜单
    channels: int = 0                # 声道数（0 表示未知，由 MPD 推断）
    audio_sample_size: int = 0       # 位深（0 表示未知）

    @classmethod
    def from_dash(cls, m: dict, kind: str) -> 'AudioTrack':
        track_id = m.get('id', 0)
        return cls(
            id=track_id,
            base_url=m.get('base_url', ''),
            backup_url=m.get('backup_url') or [],
            bandwidth=m.get('bandwidth', 0),
            # codecs 统一存小写：B 站实测有混合大小写（'fLaC'），
            # 下游 codec_mpd / _infer_kind 不必再 .lower()。
            codecs=(m.get('codecs') or '').lower(),
            audio_sampling_rate=m.get('audio_sampling_rate') or m.get('audioSamplingRate'),
            segment_base=m.get('SegmentBase'),
            kind=kind,
            label=AUDIO_QUALITY_LABEL.get(track_id, (str(track_id), ''))[0],
            # 多个可能的字段名（B 站不同版本/不同接口可能用不同名）
            channels=int(m.get('audio_channels') or m.get('channels') or m.get('channel_count') or 0),
            audio_sample_size=int(m.get('audio_sample_size') or m.get('bits_per_sample') or 0),
        )

    def is_valid(self) -> bool:
        return bool(self.id) and bool(self.base_url)

    @property
    def codec_mpd(self) -> str:
        """MPD 中使用的 codec 字符串（小写，DASH-IF 规范要求 ASCII 小写）。"""
        if 'ec-3' in self.codecs or 'ac-3' in self.codecs:
            return 'ec-3'
        if 'flac' in self.codecs:
            return 'flac'
        if 'mp4a' in self.codecs:
            return 'mp4a.40.2'
        # codecs 缺失时的兜底（B 站实测 id 30250 可能是 ec-3 或 flac，不能靠 id 猜，
        # 保守用 mp4a.40.2）
        if self.kind == 'dolby':
            return 'ec-3'
        if self.kind == 'flac':
            return 'flac'
        return 'mp4a.40.2'


def _infer_kind(track: dict) -> str:
    """根据 track 的 codecs 字符串判断音轨类型。

    B 站复用 id（30250 可以是 E-AC-3 也可以是 FLAC，30251/30252 同理），
    所以**不能**用 id 兜底，**必须**看 codecs 字符串：
      - 'ec-3' / 'eac3' / 'ac-3'   → Dolby E-AC-3 (Atmos JOC 基础层)
                                    B 站实测 id 30250 多用 'ac-3' 字面量，
                                    是 E-AC-3 的子集 / 简写
      - 'flac'                     → FLAC 无损
      - 'mp4a.40.2' / 其他         → AAC
    codecs 字段缺失时（极少数情况，实测未见）按最保守的 AAC 处理。
    """
    codecs = (track.get('codecs') or '').lower()
    if 'ec-3' in codecs or 'eac3' in codecs or 'ac-3' in codecs:
        return 'dolby'
    if 'flac' in codecs:
        return 'flac'
    return 'aac'


def collect_audio_tracks(dash: dict) -> List[AudioTrack]:
    """合并 dash.audio / dash.dolby.audio / dash.flac.audio 三处为统一列表。

    B 站 playurl 响应的实际结构（参考 wiliwili 解析器）：
      {
        "dash": {
          "audio":  [...],                // 普通 AAC
          "dolby": {"type": 2, "audio": [...]},  // 嵌套对象，含 Atmos 和部分 Hi-Res FLAC
          "flac":  {"display": true, "audio": {...}}  // 嵌套对象，另一部分 FLAC
        }
      }

    注：track 的 kind 按 codecs 字符串判断（B 站会把 Hi-Res FLAC 放在 dolby 字段）。
    """
    aac_raw = dash.get('audio', []) or []

    # Dolby / FLAC：嵌套结构（dash.dolby.audio[] / dash.flac.audio{}）。
    dolby_obj = dash.get('dolby')
    if isinstance(dolby_obj, dict):
        dolby_raw = dolby_obj.get('audio') or []
    else:
        dolby_raw = []
    flac_obj = dash.get('flac')
    if isinstance(flac_obj, dict):
        flac_raw = flac_obj.get('audio')
    else:
        flac_raw = None

    # 诊断：把响应的音轨全貌打到日志
    aac_ids = [a.get('id') for a in aac_raw if a.get('id')]
    dolby_ids = [a.get('id') for a in dolby_raw if a.get('id')]
    flac_id = flac_raw.get('id') if isinstance(flac_raw, dict) else None
    dolby_type = dolby_obj.get('type') if isinstance(dolby_obj, dict) else None
    has_flac_disp = flac_obj.get('display') if isinstance(flac_obj, dict) else None

    # 关键诊断：把第一个音轨的**全部字段名**打出来，看 B 站真实返回的字段
    # （特别是声道数、采样率、位深的字段名，我们猜的几个可能错）
    sample_track = None
    if dolby_raw:
        sample_track = dolby_raw[0]
    elif flac_raw and isinstance(flac_raw, dict):
        sample_track = flac_raw
    elif aac_raw:
        sample_track = aac_raw[0]
    if sample_track:
        xbmc.log(
            '[playback.audio] sample track all fields: %s' % list(sample_track.keys()),
            xbmc.LOGINFO,
        )
        xbmc.log(
            '[playback.audio] sample track values: %s' % {
                k: sample_track[k] for k in sample_track
                if k not in ('base_url', 'backup_url')
            },
            xbmc.LOGINFO,
        )

    xbmc.log(
        '[playback.audio] dash: aac=%s dolby.type=%s dolby=%s flac.display=%s flac=%s' % (
            aac_ids, dolby_type, dolby_ids, has_flac_disp, flac_id,
        ),
        xbmc.LOGINFO,
    )

    tracks: List[AudioTrack] = []
    for m in aac_raw:
        tracks.append(AudioTrack.from_dash(m, _infer_kind(m)))
    for m in dolby_raw:
        tracks.append(AudioTrack.from_dash(m, _infer_kind(m)))
    if isinstance(flac_raw, dict) and flac_raw.get('base_url'):
        tracks.append(AudioTrack.from_dash(flac_raw, _infer_kind(flac_raw)))
    valid = [t for t in tracks if t.is_valid()]
    # 诊断：报告每条音轨的 kind 归类，方便验证 FLAC/Atmos 是否被正确识别
    kind_summary = [(t.id, (t.codecs or '')[:20], t.kind, t.codec_mpd, t.label) for t in valid]
    xbmc.log('[playback.audio] kind: %s' % (kind_summary,), xbmc.LOGDEBUG)
    if not dolby_raw and not flac_raw and aac_ids:
        xbmc.log(
            '[playback.audio] only AAC tracks returned. '
            'Atmos/Hi-Res likely needs 大会员 + valid SESSDATA cookie + video must have those tracks.',
            xbmc.LOGWARNING,
        )
    return valid


def _premium(tracks: List[AudioTrack]) -> List[AudioTrack]:
    """Dolby + FLAC 高品质音轨（用于"用户选普通 AAC 时也拼到 MPD 末尾"）。"""
    return (
        [t for t in tracks if t.kind == 'dolby']
        + [t for t in tracks if t.kind == 'flac']
    )


def select_audio_tracks(tracks: List[AudioTrack], preference: int) -> List[AudioTrack]:
    """按用户偏好 + 降级链选音轨（去重保序），**但 FLAC/Atmos 总是包含**。

    行为：
      - 偏好 PREF_ATMOS(30255)：dolby → flac → 30280 → 30232 → 30216
      - 偏好 PREF_HIRES(30250)：flac → dolby → 30280 → 30232 → 30216
      - 其他 (30280/30232/30216)：用户首选 AAC → 然后 dolby/flac → 然后其他 AAC 降级

    **关键设计**：即使用户选了 30280（默认高清 AAC），FLAC 和 Dolby 也会被包含
    到 MPD 里，player 自己选。Kodi UI 音轨菜单能看到所有选项，user 想切 Hi-Res
    不用进插件设置。
    """
    if not tracks:
        return []
    by_id = {t.id: t for t in tracks}

    if preference == PREF_ATMOS:
        order: list = (
            [t for t in tracks if t.kind == 'dolby']
            + [t for t in tracks if t.kind == 'flac']
            + [by_id[q] for q in _AAC_FALLBACK if q in by_id]
        )
    elif preference == PREF_HIRES:
        order = (
            [t for t in tracks if t.kind == 'flac']
            + [t for t in tracks if t.kind == 'dolby']
            + [by_id[q] for q in _AAC_FALLBACK if q in by_id]
        )
    else:
        # 用户选普通 AAC：先放用户首选 + 降级链，再附加高品质音轨
        # （player 仍可切到高品质音轨，Kodi 音轨菜单也会显示）
        primary = by_id.get(preference)
        aac_order = ([primary] if primary else []) + [
            by_id[q] for q in _AAC_FALLBACK
            if q in by_id and q != preference
        ]
        order = aac_order + _premium(tracks)

    # 去重保序
    seen, result = set(), []
    for t in order:
        if t.id not in seen:
            seen.add(t.id)
            result.append(t)
    return result


def select_by_user_pref(tracks: List[AudioTrack]) -> List[AudioTrack]:
    """从 settings.xml 读取 audio_quality 后调 select_audio_tracks 的便捷封装。"""
    try:
        pref = int(getSetting('audio_quality'))
    except (TypeError, ValueError):
        pref = PREF_HIGH
    return select_audio_tracks(tracks, pref)

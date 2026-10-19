# -*- coding:utf-8 -*-
"""点播 / 直播播放辅助：listitem 构建、分辨率、MPD、ASS、历史、直播选择。"""
from .item import get_video_item, parse_plot
from .resolution import choose_resolution
from .audio import (
    AudioTrack, collect_audio_tracks, select_audio_tracks, select_by_user_pref,
    AUDIO_QUALITY_LABEL, PREF_ATMOS, PREF_HIRES, PREF_HIGH, PREF_MED, PREF_LOW,
)
from .mpd import generate_mpd
from .ass import generate_ass
from .history import report_history
from .live import choose_live_resolution

__all__ = [
    'get_video_item', 'parse_plot',
    'choose_resolution',
    'AudioTrack', 'collect_audio_tracks', 'select_audio_tracks', 'select_by_user_pref',
    'AUDIO_QUALITY_LABEL',
    'PREF_ATMOS', 'PREF_HIRES', 'PREF_HIGH', 'PREF_MED', 'PREF_LOW',
    'generate_mpd',
    'generate_ass',
    'report_history',
    'choose_live_resolution',
]

# -*- coding:utf-8 -*-
"""DASH MPD generation: B 站 playurl DASH → standard MPEG-DASH MPD.

v0.4.0 structure:
  - Video: v0.1.0 — per Representation, <SegmentBase indexRange="…"> +
    <Initialization range="…"/>. inputstream.adaptive uses these to
    splice init/media byte ranges precisely when Range-fetching from
    B 站 CDN.
  - Audio: v0.3.0 — one <AdaptationSet> per AudioTrack. AAC + Dolby +
    Hi-Res FLAC each get their own AS, with lang="zh-Hans",
    <AudioChannelConfiguration>, <Role value="main"/> on the primary
    AAC, and <SupplementalProperty value="JOC"/> on Dolby.

BaseURL points at B 站 CDN directly. inputstream.adaptive fetches
segments with `stream_headers=Referer=https://www.bilibili.com` —
no local proxy is involved.
"""
from xml.sax.saxutils import escape as _xml_escape

from .resolution import choose_resolution
from .audio import collect_audio_tracks, select_by_user_pref


# ── 工具函数 ────────────────────────────────────────────────────────────

def _duration_to_iso8601(seconds) -> str:
    if not seconds:
        return 'PT0S'
    s = float(seconds)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s - h * 3600 - m * 60
    if h:
        return 'PT%dH%dM%.3fS' % (h, m, sec)
    if m:
        return 'PT%dM%.3fS' % (m, sec)
    return 'PT%.3fS' % sec


def _amp(s: str) -> str:
    """Escape '&' for XML PCDATA/BaseURL. B 站 CDN URL 不会出现 <, >, ", '，
    所以这里只做最小化转义；属性值（label 等）走 _xml_escape。"""
    return s.replace('&', '&amp;')


# ── 视频 AdaptationSet (v0.1.0 形态) ────────────────────────────────────

def _build_video_as(videos: list) -> list:
    """Single video AS; one Representation per quality. Each Representation
    has its own <SegmentBase indexRange> + <Initialization range>."""
    if not videos:
        return []
    lines = [
        '\t\t<AdaptationSet mimeType="video/mp4" '
        'startWithSAP="1" segmentAlignment="true" '
        'scanType="progressive">\n',
    ]
    for v in videos:
        attrs = ['id="%s"' % v.get('id', '')]
        if 'bandwidth' in v:
            attrs.append('bandwidth="%d"' % v['bandwidth'])
        if 'codecs' in v:
            attrs.append('codecs="%s"' % v['codecs'])
        if 'frameRate' in v:
            attrs.append('frameRate="%s"' % v['frameRate'])
        if 'height' in v:
            attrs.append('height="%d"' % v['height'])
        if 'width' in v:
            attrs.append('width="%d"' % v['width'])
        lines.append('\t\t\t<Representation %s>\n' % ' '.join(attrs))
        lines.append(
            '\t\t\t\t<BaseURL>%s</BaseURL>\n'
            % _amp(v.get('baseUrl', ''))
        )
        for bu in v.get('backup_url') or []:
            lines.append('\t\t\t\t<BaseURL>%s</BaseURL>\n' % _amp(bu))
        sb = v.get('SegmentBase') or {}
        if 'indexRange' in sb and 'Initialization' in sb:
            lines.append(
                '\t\t\t\t<SegmentBase indexRange="%s">\n' % sb['indexRange']
            )
            lines.append(
                '\t\t\t\t\t<Initialization range="%s">'
                '</Initialization>\n' % sb['Initialization']
            )
            lines.append('\t\t\t\t</SegmentBase>\n')
        lines.append('\t\t\t</Representation>\n')
    lines.append('\t\t</AdaptationSet>\n')
    return lines


# ── 音频 AdaptationSet (v0.3.0 形态，多 AS) ─────────────────────────────

def _audio_channel_cfg(track) -> str:
    scheme = 'urn:mpeg:mpegB:cicp:ChannelConfiguration'
    if track.channels and track.channels > 0:
        v = track.channels
    elif track.kind == 'dolby':
        v = 7
    else:
        v = 2
    return (
        '<AudioChannelConfiguration schemeIdUri="%s" value="%d"/>'
    ) % (scheme, v)


def _build_audio_as(track, is_preferred: bool = False) -> list:
    codec_attr = track.codec_mpd
    channel_cfg = _audio_channel_cfg(track)
    label = _xml_escape(track.label or str(track.id))

    lines = [
        '\t\t<AdaptationSet contentType="audio" mimeType="audio/mp4" '
        'segmentAlignment="true" startWithSAP="1" '
        'lang="zh-Hans" '
        'codecs="%s" '
        'label="%s">\n' % (codec_attr, label),
    ]
    lines.append('\t\t\t%s\n' % channel_cfg)
    # Mark the user's preferred track as main so inputstream.adaptive
    # auto-selects it. We mark the *first* AS in the MPD (which is
    # the user-preferred track per select_audio_tracks ordering),
    # regardless of codec kind — without this, adaptive picks
    # based on the first AS in the manifest, which is what we want,
    # but the lack of <Role value="main"/> would make Kodi flag
    # the choice as 'supplementary' on some builds. Belt and braces.
    if is_preferred:
        lines.append(
            '\t\t\t<Role schemeIdUri="urn:mpeg:dash:role:2011" '
            'value="main"/>\n',
        )
    if track.kind == 'dolby':
        lines.append(
            '\t\t\t<SupplementalProperty '
            'schemeIdUri="tag:dolby.com,2018:dash:EC3_ExtensionType:2018" '
            'value="JOC"/>\n',
        )

    attrs = [
        'id="%d"' % track.id,
        'bandwidth="%d"' % track.bandwidth,
    ]
    if track.audio_sampling_rate:
        attrs.append('audioSamplingRate="%d"' % track.audio_sampling_rate)
    lines.append('\t\t\t<Representation %s>\n' % ' '.join(attrs))

    lines.append(
        '\t\t\t\t<BaseURL>%s</BaseURL>\n' % _amp(track.base_url)
    )
    for bu in track.backup_url or []:
        lines.append('\t\t\t\t<BaseURL>%s</BaseURL>\n' % _amp(bu))
    sb = track.segment_base or {}
    if 'indexRange' in sb and 'Initialization' in sb:
        lines.append(
            '\t\t\t\t<SegmentBase indexRange="%s">\n' % sb['indexRange']
        )
        lines.append(
            '\t\t\t\t\t<Initialization range="%s">'
            '</Initialization>\n' % sb['Initialization']
        )
        lines.append('\t\t\t\t</SegmentBase>\n')
    lines.append('\t\t\t</Representation>\n')
    lines.append('\t\t</AdaptationSet>\n')
    return lines


# ── 顶层 MPD ────────────────────────────────────────────────────────────

def generate_mpd(dash: dict) -> str:
    """Build the MPD XML.

    Single-arg signature matching v0.1.0 (the proxy-related
    cookie/ua/port params from v0.3.0 are gone — BaseURL is CDN-direct).
    """
    videos = choose_resolution(dash)
    audio_tracks = select_by_user_pref(collect_audio_tracks(dash))

    duration_iso = _duration_to_iso8601(dash.get('duration', 0))
    minbuf_ms = dash.get('min_buffer_time') or dash.get('minBufferTime') or 1.5
    minbuf_iso = _duration_to_iso8601(minbuf_ms)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" '
        'profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" '
        'type="static" '
        'mediaPresentationDuration="%s" '
        'minBufferTime="%s">\n' % (duration_iso, minbuf_iso),
        '\t<Period>\n',
    ]
    lines.extend(_build_video_as(videos))
    for idx, t in enumerate(audio_tracks):
        # First track per select_audio_tracks ordering is the
        # user's preferred one (Atmos / Hi-Res FLAC / primary AAC).
        # Mark it main so inputstream.adaptive auto-selects it.
        lines.extend(_build_audio_as(t, is_preferred=(idx == 0)))
    lines.append('\t</Period>\n</MPD>\n')
    return ''.join(lines)

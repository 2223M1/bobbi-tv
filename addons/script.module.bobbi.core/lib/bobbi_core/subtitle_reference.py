"""Sparse actual demux timing, using the existing single bounded ffprobe lane.

This reads the exact cloud file through its already qualified range reader;
it does not download a movie, parse an IMDb cache or infer PGS display timing
from packet arrival times. Insufficient samples stay insufficient.
"""
import math

from bobbi_core.media_probe import detail_probe, SOCKET_BUFFER, ANALYSIS_BYTES, ANALYSIS_MICROSECONDS
from bobbi_core.subtitle_binding import checked_video

TEXT_CODECS = {'subrip', 'ass', 'ssa', 'webvtt', 'mov_text'}


def sampling_windows(duration):
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 60 <= duration <= 21600:
        raise ValueError('Actual bounded duration required')
    # Each window stays inside its own sixth; sample a genuine continuous span.
    width = min(30.0, duration / 12)
    return [(duration * (index + .5) / 6 - width / 2,
             duration * (index + .5) / 6 + width / 2) for index in range(6)]


def reference_command(binary, port, token, index, windows):
    return [str(binary), '-v', 'error', '-threads', '1', '-protocol_whitelist', 'http,tcp',
            '-recv_buffer_size', str(SOCKET_BUFFER), '-probesize', str(ANALYSIS_BYTES),
            '-analyzeduration', str(ANALYSIS_MICROSECONDS), '-select_streams', str(index),
            '-read_intervals', ','.join('{:.3f}%{:.3f}'.format(a, b) for a, b in windows),
            '-show_packets', '-show_streams', '-show_entries',
            'packet=stream_index,pts_time,duration_time:stream=index,codec_type,codec_name',
            '-of', 'json', 'http://127.0.0.1:{}{}'.format(port, token)]


def packet_intervals(data, index, windows, duration):
    if not isinstance(data, dict) or not isinstance(data.get('packets'), list) or len(data['packets']) > 3000:
        raise ValueError('Bounded reference packets required')
    result = set()
    for row in data['packets']:
        if not isinstance(row, dict) or type(row.get('stream_index')) is not int or row['stream_index'] != index:
            raise ValueError('Unexpected demux stream identity')
        try:
            start, span = float(row['pts_time']), float(row['duration_time'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Packet has no explicit subtitle display duration') from None
        if not math.isfinite(start) or not math.isfinite(span) or start < 0 or not 0 < span <= 60 or start + span > duration:
            raise ValueError('Reference packet timing outside actual video')
        # Demux seeks may land at an earlier keyframe. Only the requested
        # continuous ranges are evidence; never extrapolate unseen intervals.
        if any(max(left, start) < min(right, start + span) for left, right in windows):
            result.add((start, start + span))
    if not result:
        raise ValueError('No timed reference packets in requested windows')
    return sorted(result)


def sample(binary, video, stream, duration, read, cancelled=lambda: False):
    checked_video(video)
    if (not isinstance(stream, dict) or stream.get('codec_type') != 'subtitle'
            or stream.get('codec_name') not in TEXT_CODECS
            or type(stream.get('index')) is not int or not 0 <= stream['index'] <= 255):
        raise ValueError('Verified timed text stream required; PGS needs display decoding')
    windows = sampling_windows(duration)
    index = stream['index']
    def parse(data):
        if data.get('streams') != [dict(index=index, codec_type='subtitle', codec_name=stream['codec_name'])]:
            raise ValueError('Actual reference stream changed')
        rows = packet_intervals(data, index, windows, duration)
        return dict(state='DEMUX_REFERENCE_NOT_SUBTITLE_ACCEPTANCE', video_key=video['key'],
                    stream_index=index, codec=stream['codec_name'], duration=duration,
                    windows=windows, intervals=rows)
    return detail_probe(binary, video['selected']['torrent_file_bytes'], read, cancelled,
        lambda binary, port, token: reference_command(binary, port, token, index, windows), parse)

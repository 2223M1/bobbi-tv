"""Bounded demux facts, not permission to change release or autoplay a file.

Only an independently proved exact episode/release pair may use these facts.
Missing required or unsupported facts reject compatibility, not ordinary playback.
Optional unsignalled color fields remain not_reported, never guessed BT.709/SDR.
No filename inference, provider access, transcoding or audio setting changes.
"""
from fractions import Fraction
import hashlib
import json
import re


def _token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9_.()+-]{1,64}', value):
        raise ValueError('Explicit bounded stream attribute required')
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Explicit bounded stream integer required')
    return value


def _commentary(row):
    # Match an explicit metadata label, not a filename or a substring such as
    # "No Commentary". Numbered commentary tracks do not change main audio.
    title = str(row.get('tags', {}).get('title', '')).strip()
    return (row.get('disposition', {}).get('comment') == 1
            or bool(re.fullmatch(r'(?:audio\s+)?commentary(?:\s+track(?:\s+[1-9][0-9]?)?)?',
                                 title, re.I)))


def checked_profile(value):
    if (not isinstance(value, dict)
            or set(value) != {'schema', 'video', 'main_audio', 'commentary_count', 'streams_sha256'}
            or type(value['schema']) is not int or value['schema'] != 1):
        raise ValueError('Complete media profile required')
    video, audio = value['video'], value['main_audio']
    if (not isinstance(video, dict) or set(video) != {'codec', 'width', 'height', 'pixel_format',
            'transfer', 'primaries', 'frame_rate'} or not isinstance(audio, dict)
            or set(audio) != {'codec', 'sample_rate', 'channels', 'layout', 'bits', 'language'}):
        raise ValueError('Complete video/main audio facts required')
    for key in ('codec', 'pixel_format', 'transfer', 'primaries'):
        _token(video[key])
    _integer(video['width'], 16, 16384)
    _integer(video['height'], 16, 16384)
    rate = video['frame_rate']
    if (not isinstance(rate, list) or len(rate) != 2
            or any(type(x) is not int or not 1 <= x <= 1000000 for x in rate)
            or not 1 <= Fraction(*rate) <= 240
            or [Fraction(*rate).numerator, Fraction(*rate).denominator] != rate):
        raise ValueError('Reduced finite measured frame rate required')
    for key in ('codec', 'layout', 'language'):
        _token(audio[key])
    if audio['language'] in {'und', 'unknown'}:
        raise ValueError('Unknown primary language')
    _integer(audio['sample_rate'], 8000, 768000)
    _integer(audio['channels'], 1, 32)
    _integer(audio['bits'], 0, 64)
    _integer(value['commentary_count'], 0, 31)
    if not isinstance(value['streams_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['streams_sha256']):
        raise ValueError('Observed stream input digest required')
    return value


def media_profile(streams):
    if (not isinstance(streams, list) or not 1 <= len(streams) <= 128
            or any(not isinstance(row, dict) for row in streams)):
        raise ValueError('Bounded actual demux streams required')
    seen = set()
    for row in streams:
        index = _integer(row.get('index'), 0, 255)
        if index in seen:
            raise ValueError('Nonunique demux stream identity')
        seen.add(index)
    videos = [row for row in streams if row.get('codec_type') == 'video'
              and not row.get('disposition', {}).get('attached_pic')]
    audios = [row for row in streams if row.get('codec_type') == 'audio']
    if len(videos) != 1 or not 1 <= len(audios) <= 32:
        raise ValueError('One video and an explicit primary audio required')
    video = videos[0]
    # Dolby Vision and other side-data need an explicit separate contract.
    # Do not lose their identity by comparing only HDR transfer characteristics.
    if video.get('side_data_list'):
        raise ValueError('Unsupported video side data for automatic compatibility')
    main = [row for row in audios if row.get('disposition', {}).get('default') == 1]
    if len(main) != 1:
        raise ValueError('Exactly one default primary audio required')
    main = main[0]
    if _commentary(main):
        raise ValueError('Default commentary is not main program audio proof')
    for row in audios:
        if row is main:
            continue
        if not _commentary(row):
            raise ValueError('Additional audio is not explicitly commentary')
    rate = video.get('avg_frame_rate')
    if not isinstance(rate, str) or not re.fullmatch(r'\d{1,7}/\d{1,7}', rate):
        raise ValueError('Measured rational frame rate required')
    try:
        rate = Fraction(rate)
        sample_rate = int(main['sample_rate'])
        bits = int(main.get('bits_per_raw_sample', '0'))
    except (ValueError, ZeroDivisionError, KeyError, TypeError):
        raise ValueError('Missing or invalid measured stream values') from None
    value = dict(schema=1,
        video=dict(codec=video.get('codec_name'), width=video.get('width'), height=video.get('height'),
            pixel_format=video.get('pix_fmt'), transfer=video.get('color_transfer', 'not_reported'),
            primaries=video.get('color_primaries', 'not_reported'), frame_rate=[rate.numerator, rate.denominator]),
        main_audio=dict(codec=main.get('codec_name'), sample_rate=sample_rate,
            channels=main.get('channels'), layout=main.get('channel_layout'), bits=bits,
            language=main.get('tags', {}).get('language')),
        commentary_count=len(audios)-1,
        streams_sha256=hashlib.sha256(json.dumps(streams, sort_keys=True, separators=(',', ':'),
            allow_nan=False).encode()).hexdigest())
    return checked_profile(value)


def same_main_media(first, following):
    """Necessary media condition only; does not prove title/episode/release."""
    first, following = checked_profile(first), checked_profile(following)
    return first['video'] == following['video'] and first['main_audio'] == following['main_audio']

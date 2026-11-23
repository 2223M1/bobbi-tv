"""Small observed start snapshot; not source probing or playback authority.

Only selected streams at this observation are retained. Optional video facts
come from a separately fenced native read, not a filename or output mode.
Catalog counts are not container completeness; subtitle origin, rendering,
output and transcode mode remain unknown. Missing attributes never inherit.
"""
from copy import deepcopy
import math
import re

from .playback_presentation import expected

FIELDS = frozenset(('audio_count', 'subtitle_count', 'audio', 'subtitle', 'subtitle_visible'))
OBSERVATION_FIELDS = frozenset(('schema', 'observation_key', 'recorded_at', 'expected',
                               'generation', 'session_id', 'facts'))


def _text(value, maximum):
    if value is None:
        return None
    if (type(value) is not str or not 0 < len(value) <= maximum
            or re.search(r'[\x00-\x1f\x7f]', value) or '://' in value):
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    return value


def checked(value):
    if type(value) is not dict or set(value) not in (FIELDS, FIELDS | {'video'}):
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    for key, limit in (('audio_count', 64), ('subtitle_count', 256)):
        if type(value[key]) is not int or not 0 <= value[key] <= limit:
            raise ValueError('PLAYBACK_START_FACTS_INVALID')
    if type(value['subtitle_visible']) is not bool:
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    audio, subtitle = value['audio'], value['subtitle']
    if audio is not None:
        if type(audio) is not dict or set(audio) != {'codec', 'channels', 'language'} or not value['audio_count']:
            raise ValueError('PLAYBACK_START_FACTS_INVALID')
        if audio['codec'] is not None and (type(audio['codec']) is not str or not
                re.fullmatch(r'[A-Za-z0-9_.()+-]{1,32}', audio['codec'])):
            raise ValueError('PLAYBACK_START_FACTS_INVALID')
        if audio['channels'] is not None and (type(audio['channels']) is not int or not 1 <= audio['channels'] <= 64):
            raise ValueError('PLAYBACK_START_FACTS_INVALID')
        _text(audio['language'], 32)
    if subtitle is not None:
        if (type(subtitle) is not dict or set(subtitle) != {'language', 'name', 'forced', 'impaired'}
                or not value['subtitle_count']):
            raise ValueError('PLAYBACK_START_FACTS_INVALID')
        _text(subtitle['language'], 32)
        _text(subtitle['name'], 128)
        if any(subtitle[key] is not None and type(subtitle[key]) is not bool for key in ('forced', 'impaired')):
            raise ValueError('PLAYBACK_START_FACTS_INVALID')
    if 'video' in value:
        video(value['video'])
    return deepcopy(value)


def video(value):
    """Strict optional saved shape; zero/missing raw dimensions stay unknown."""
    if type(value) is not dict or set(value) != {'codec', 'width', 'height'}:
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    if value['codec'] is not None and (type(value['codec']) is not str or not
            re.fullmatch(r'[A-Za-z0-9_.()+-]{1,32}', value['codec'])):
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    if any(value[key] is not None and (type(value[key]) is not int or not 1 <= value[key] <= 65535)
           for key in ('width', 'height')):
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    return dict(value)


def video_observation(properties, before, selection_epoch, after):
    """Global GetProperties is evidence only inside one native receipt fence.

    This read does not grant controls or claim atomic output/transcode facts.
    Failure discards only video; the earlier scoped audio/subtitle snapshot
    remains an observation of its own receipt, never a refreshed selection.
    """
    from .native_receipt import receipt
    try:
        first = receipt(before)
        if (first is None or type(after) is not dict or type(after.get('protocol')) is not int
                or after['protocol'] != 1 or type(selection_epoch) is not int
                or type(after.get('selection_epoch')) is not int
                or after['selection_epoch'] != selection_epoch):
            return None
        last = receipt(after.get('playback'))
        keys = ('request_id', 'native_instance', 'file_identity', 'url_sha256', 'phase',
                'open_epoch', 'sequence', 'user_intent', 'subtitle_intent', 'subtitle_auto_intent', 'audio_intent')
        if (last is None or first['phase'] != 'AV_STARTED' or not first['request_id']
                or first.get('open_epoch') != selection_epoch
                or any(key not in first or key not in last
                       or type(first[key]) is not type(last[key]) or first[key] != last[key] for key in keys)
                or any(type(first[key]) is not int or first[key] < 0 for key in
                       ('open_epoch', 'sequence', 'user_intent', 'subtitle_intent', 'subtitle_auto_intent', 'audio_intent'))):
            return None
        raw = properties['currentvideostream']
        if type(raw) is not dict or type(raw.get('index')) is not int or not 0 <= raw['index'] < 256:
            return None
        result = {key: raw.get(key) for key in ('codec', 'width', 'height')}
        if result['codec'] == '':
            result['codec'] = None
        for key in ('width', 'height'):
            if type(result[key]) is int and result[key] == 0:
                result[key] = None
        return video(result)
    except (ValueError, KeyError, TypeError):
        return None


def project(raw):
    """Only after presentation verified the receipt; invalid optional facts
    do not remove controls. Count the raw catalog, never its shortened view.
    """
    try:
        selected, counts = [], []
        for key, active, limit in (('audio_streams', 'audio_index', 64), ('streams', 'current_index', 256)):
            rows, index = raw[key], raw[active]
            if (type(rows) is not list or len(rows) > limit or type(index) is not int
                    or not -1 <= index < limit):
                return None
            seen = set()
            for row in rows:
                if (type(row) is not dict or type(row.get('index')) is not int
                        or not 0 <= row['index'] < limit or row['index'] in seen
                        or type(row.get('stream_key')) is not str
                        or not re.fullmatch('[0-9a-f]{64}', row['stream_key'])):
                    return None
                seen.add(row['index'])
            if index >= 0 and index not in seen:
                return None
            selected.append(next((row for row in rows if row['index'] == index), None))
            counts.append(len(rows))
        audio, subtitle = selected
        def text(row, key):
            return None if row.get(key) == '' else row.get(key)
        result = dict(audio_count=counts[0], subtitle_count=counts[1],
            audio=(dict(codec=text(audio, 'codec'),
                        channels=None if type(audio.get('channels')) is int and audio['channels'] == 0 else audio.get('channels'),
                        language=text(audio, 'language')) if audio is not None else None),
            subtitle=(dict(language=text(subtitle, 'language'), name=text(subtitle, 'name'),
                           forced=subtitle.get('isforced'), impaired=subtitle.get('isimpaired'))
                      if subtitle is not None else None), subtitle_visible=raw['visible'])
        return checked(result)
    except (ValueError, KeyError, TypeError):
        return None


def timestamp(value):
    if type(value) not in (int, float) or not 0 <= value < 4102444800 or not math.isfinite(value):
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    return value


def observation(value, file_ref):
    from .catalog_query import opaque
    from .file_ref import validate
    from .server_ref import PROVIDERS
    ref = validate(file_ref)
    if (type(value) is not dict or set(value) != OBSERVATION_FIELDS
            or type(value['schema']) is not int or value['schema'] != 1
            or value['observation_key'] != opaque(ref) or ref['provider'] in PROVIDERS
            or type(value['generation']) is not int or value['generation'] < 1
            or type(value['session_id']) is not str or not re.fullmatch('[0-9a-f]{32}', value['session_id'])):
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    return dict(schema=1, observation_key=value['observation_key'], recorded_at=timestamp(value['recorded_at']),
        expected=expected(value['expected']), generation=value['generation'], session_id=value['session_id'],
        facts=checked(value['facts']))


def public(value):
    if type(value) is not dict or set(value) != {'recorded_at', 'facts'}:
        raise ValueError('PLAYBACK_START_FACTS_INVALID')
    return dict(recorded_at=timestamp(value['recorded_at']), facts=checked(value['facts']))

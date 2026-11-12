"""One bounded native presentation and instance-scoped control contract."""
from hashlib import sha256
import json
import re

from .native_receipt import SHA, UUID, receipt

EXPECTED = frozenset(('boot_id', 'epoch', 'request_id', 'native_instance', 'file_sha256',
    'selection_epoch', 'expected_sequence', 'user_intent', 'subtitle_intent', 'audio_intent'))
ACTIONS = {'seek': {'position_ms'}, 'audio_stream': {'index', 'stream_key'},
           'manual_subtitle_stream': {'index', 'stream_key'}, 'subtitle_visible': {'visible'}}


def audio_status(row):
    if row.get('audio_intent', 0) > 0:
        return '音轨已由你手动控制'
    return '按作品原声语言选择' if row.get('audio_policy') == 'original_language_hint' else '按原生音轨偏好选择'


def expected(value):
    if type(value) is not dict or set(value) != EXPECTED:
        raise ValueError('PLAYBACK_EXPECTED_INVALID')
    if (not re.fullmatch('[0-9a-f]{32}', str(value['boot_id'])) or not UUID.fullmatch(str(value['native_instance']))
            or not re.fullmatch('[0-9a-f]{32}', str(value['request_id']))
            or not SHA.fullmatch(str(value['file_sha256']))
            or any(type(value[key]) is not int or not 0 <= value[key] < 2**53 for key in
                   ('epoch', 'selection_epoch', 'expected_sequence', 'user_intent', 'subtitle_intent', 'audio_intent'))):
        raise ValueError('PLAYBACK_EXPECTED_INVALID')
    return dict(value)


def command(value):
    if type(value) is not dict or set(value) != {'expected', 'command_id', 'action', 'params'}:
        raise ValueError('PLAYBACK_COMMAND_INVALID')
    scope = expected(value['expected'])
    action, params, ident = value['action'], value['params'], value['command_id']
    if (type(action) is not str or action not in ACTIONS or type(params) is not dict
            or set(params) != ACTIONS[action] or type(ident) is not str
            or not re.fullmatch('[0-9a-f]{32}', ident)):
        raise ValueError('PLAYBACK_COMMAND_INVALID')
    if action == 'seek' and (type(params['position_ms']) is not int or not 0 <= params['position_ms'] <= 864000000):
        raise ValueError('PLAYBACK_TARGET_INVALID')
    if action in ('audio_stream', 'manual_subtitle_stream') and (
            type(params['index']) is not int or not 0 <= params['index'] < 256
            or type(params['stream_key']) is not str or not SHA.fullmatch(params['stream_key'])):
        raise ValueError('PLAYBACK_STREAM_INVALID')
    if action == 'subtitle_visible' and type(params['visible']) is not bool:
        raise ValueError('PLAYBACK_VISIBILITY_INVALID')
    return dict(expected=scope, command_id=ident, action=action, params=dict(params))


def project(raw, boot_id, epoch, row, subtitle_label=''):
    """Only native instance-bound fields. Older native returns unavailable."""
    unavailable = dict(available=False, reason='SCOPED_CONTROL_UNAVAILABLE')
    if (type(raw) is not dict or type(raw.get('control_protocol')) is not int
            or raw.get('control_protocol') != 1 or raw.get('status') != 'READY'
            or receipt(raw.get('receipt')) is None or type(row) is not dict):
        return unavailable
    native = raw['receipt']
    keys = ('request_id', 'native_instance', 'file_identity', 'sequence', 'user_intent',
            'subtitle_intent', 'audio_intent', 'open_epoch')
    if (any(native.get(key) != row.get(key) for key in keys) or native.get('phase') != 'AV_STARTED'
            or raw.get('selection_epoch') != row.get('open_epoch')):
        return unavailable
    try:
        scope = expected(dict(boot_id=boot_id, epoch=epoch, request_id=row['request_id'],
            native_instance=row['native_instance'], file_sha256=sha256(row['file_identity'].encode()).hexdigest(),
            selection_epoch=row['open_epoch'], expected_sequence=row['sequence'], user_intent=row['user_intent'],
            subtitle_intent=row['subtitle_intent'], audio_intent=row['audio_intent']))
        position, duration = raw['position_ms'], raw['duration_ms']
        if (any(type(value) is not int or not 0 <= value <= 864000000 for value in (position, duration))
                or type(raw['can_seek']) is not bool or type(raw['visible']) is not bool):
            return unavailable
        result = dict(available=True, expected=scope, position_ms=position, duration_ms=duration,
            can_seek=raw['can_seek'] and duration > 0, subtitle_visible=raw['visible'],
            subtitle_status=str(subtitle_label)[:256], audio_status=audio_status(row),
            audio=[], subtitles=[], chapters=[])
        for source, target, active in (('audio_streams', 'audio', 'audio_index'), ('streams', 'subtitles', 'current_index')):
            streams = raw[source]
            if type(streams) is not list or len(streams) > 256:
                return unavailable
            # Long catalogs remain available on the TV, never flood the phone.
            selected = [item for item in streams if item.get('index') == raw.get(active)]
            shown = selected[:1] + [item for item in streams if item not in selected][:31]
            seen = set()
            for item in shown:
                index, key = item.get('index'), item.get('stream_key')
                if type(index) is not int or not 0 <= index < 256 or type(key) is not str or not SHA.fullmatch(key) or key in seen:
                    return unavailable
                seen.add(key)
                result[target].append(dict(index=index, stream_key=key, selected=index == raw.get(active),
                    name=str(item.get('name', ''))[:128], language=str(item.get('language', ''))[:32]))
            result[target + '_truncated'] = len(streams) > len(shown)
        for chapter in raw.get('chapters', [])[:32]:
            target = chapter.get('position_ms')
            if type(target) is not int or not 0 <= target < duration:
                continue
            result['chapters'].append(dict(name=str(chapter.get('name', ''))[:128], position_ms=target))
        result['chapters_truncated'] = bool(raw.get('chapters_truncated')) or len(raw.get('chapters', [])) > 32
        # Respect the existing browser reply limit even for long Unicode track
        # names. Prefer current tracks, and explicitly mark every shortened list.
        while len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > 12288:
            if result['chapters']:
                result['chapters'].pop()
                result['chapters_truncated'] = True
                continue
            target = max(('audio', 'subtitles'), key=lambda key: len(result[key]))
            candidates = [i for i, item in enumerate(result[target]) if not item['selected']]
            if not candidates:
                return unavailable
            result[target].pop(candidates[-1])
            result[target + '_truncated'] = True
        return result
    except (KeyError, ValueError, TypeError, AttributeError):
        return unavailable


def native_command(value):
    value = command(value)
    params = {key: item for key, item in value['expected'].items() if key not in ('boot_id', 'epoch')}
    return dict(params, **value['params'], action=value['action'], command_id=value['command_id'], control_protocol=1)


def result(value, original):
    """Old native accepted/queued events are not final execution evidence."""
    if (type(value) is not dict or type(value.get('control_protocol')) is not int
            or value['control_protocol'] != 1 or value.get('status') not in ('queued', 'applied', 'rejected', 'failed')
            or value.get('command_id') != original['command_id'] or value.get('action') != original['action']
            or any(value.get(key) != original['expected'][key] for key in ('request_id', 'native_instance', 'file_sha256'))):
        return None
    return dict(command_id=value['command_id'], status=value['status'])

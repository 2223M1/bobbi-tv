"""Bounded portable host client; explicit legacy Unix transport stays opt-in."""
import json
import socket
import time
from uuid import uuid4
from bobbi_core.capabilities import IPC_PROTOCOL, compatible

SOCKET_PATH = None  # Optional preparation is registered with the local host.


def call(method, body, socket_path=SOCKET_PATH, timeout=0.3):
    if method not in {'prepare', 'advance', 'status', 'ping', 'resolve', 'subtitle', 'font_preflight',
                      'catalog_prepare', 'catalog_status', 'catalog_resolve', 'share_open'}:
        raise ValueError('Unsupported preparation command')
    if type(timeout) not in (int, float) or not 0 < timeout <= 0.3:
        raise ValueError('Bounded preparation IPC timeout required')
    if socket_path is None:
        from bobbi_platform.runtime import call as host_call
        deadline = time.monotonic() + timeout
        scope = host_call('account_status', {}, timeout=min(.1, timeout))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Preparation account budget exceeded')
        value = host_call('preparation', dict(method=method, body=body, protocol=IPC_PROTOCOL,
                          account=scope), timeout=remaining)
        if not isinstance(value, dict) or not compatible(value.get('component')):
            raise ValueError('Preparation service component is incompatible')
        return value
    if not hasattr(socket, 'AF_UNIX'):
        raise OSError('Explicit Unix preparation transport unavailable')
    raw = json.dumps(dict(method=method, body=body, protocol=IPC_PROTOCOL), ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n'
    if len(raw) > 16384:
        raise ValueError('Preparation request exceeds byte budget')
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(socket_path)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Preparation connection budget exceeded')
        connection.settimeout(remaining)
        connection.sendall(raw)
        result = bytearray()
        while b'\n' not in result:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or len(result) >= 16384:
                raise TimeoutError('Preparation IPC budget exceeded')
            connection.settimeout(remaining)
            chunk = connection.recv(min(4096, 16384 - len(result)))
            if not chunk:
                raise ConnectionError('Preparation service closed without result')
            result.extend(chunk)
    value = json.loads(result)
    if not isinstance(value, dict) or value.get('ok') is not True:
        raise ValueError('Preparation service rejected request')
    if not compatible(value.get('component')):
        raise ValueError('Preparation service component is incompatible')
    return value


def prepare_fonts(data, context, cancelled=lambda: False):
    """Bounded local font working-set handoff, never a network font download.

    Preserve previously working ASS styles before creating the AV renderer.
    The three-second ceiling is not an unconditional delay: a completed local
    check or an unavailable cache returns immediately and cannot fail video.
    """
    if cancelled():
        raise RuntimeError('本次播放已取消')
    if not data.get('prepared_resource_id'):
        return dict(state='not_applicable')
    try:
        body = dict(context, resource_id=data['prepared_resource_id'],
                    source_info_hash=data['prepared_source_info_hash'])
    except (KeyError, TypeError, ValueError):
        return dict(state='unavailable', reason='FONT_PREFLIGHT_CONTEXT_UNAVAILABLE')
    deadline = time.monotonic() + 3
    while not cancelled():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return dict(state='unavailable', reason='FONT_PREFLIGHT_EXPIRED')
        try:
            result = call('font_preflight', body, timeout=min(0.3, remaining))
        except OSError:
            result = dict(state='pending')
        except (ValueError, TypeError, RuntimeError):
            result = dict(state='unavailable', reason='FONT_PREFLIGHT_SERVICE_UNAVAILABLE')
        if cancelled():
            break
        if not isinstance(result, dict):
            return dict(state='unavailable', reason='FONT_PREFLIGHT_REPLY_INVALID')
        if result.get('state') != 'pending':
            if result.get('state') == 'ready' and result.get('request_id') != context['request_id']:
                return dict(state='unavailable', reason='FONT_PREFLIGHT_REPLY_MISMATCH')
            return result
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    raise RuntimeError('本次播放已取消，未应用迟到的字体结果')


def resolve_entry(data, snapshot, entry, cancelled=lambda: False):
    from bobbi_core.preparation import MEDIA
    from bobbi_core.video_context import migrate_entry
    migrate_entry(entry)
    television = data.get('tv_data') or {}
    identifier = (data.get('ids') or {}).get('tmdb_id')
    media_id = ('tmdb:tv:{}:s{}:e{}'.format(identifier, television.get('season'), television.get('episode'))
                if data.get('mode') in {'tv', 'anime', 'episode'} else 'tmdb:movie:{}'.format(identifier))
    if not MEDIA.fullmatch(media_id):
        return None
    verification = uuid4().hex
    body = dict(request_id=data['request_id'], verification_id=verification, resource_id=entry['key'], generation=snapshot['generation'],
                account=snapshot['account'], source_info_hash=entry['prepared_source_info_hash'], media_id=media_id)
    if 'prepared_qualification' in entry:
        body['qualification'] = entry['prepared_qualification']
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not cancelled():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            # The server keys this read-only verification by the same nonce.
            # A lost reply must not create another job or bypass fresh identity
            # checks. Writes such as prepare/advance are NOT retried here.
            result = call('resolve', body, timeout=min(0.3, remaining))
        except OSError:
            result = {'state': 'pending'}
        if result.get('state') == 'ready':
            migrate_entry(result)
            expected = dict(request_id=data['request_id'], verification_id=verification, resource_id=entry['key'], generation=snapshot['generation'],
                            account=snapshot['account'], file_id=entry['prepared_file_id'], path=entry['path'],
                            bytes=entry['bytes'], version_key=entry['prepared_version_key'])
            if 'qualification' in body:
                expected['qualification'] = body['qualification']
            if 'video_context' in entry:
                expected['video_context'] = entry['video_context']
            return entry if all(result.get(key) == value for key, value in expected.items()) and not cancelled() else None
        if result.get('state') != 'pending':
            return None
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    return None


def source_intent(data, target):
    if (data.get('selection_policy') != 'exact' or not data.get('is_torrent')
            or not isinstance(target, dict) or target.get('request_id') != data.get('request_id')
            or target.get('session') != data.get('request_id')):
        return None
    try:
        is_tv = data.get('mode') in {'tv', 'anime', 'episode'}
        television = data.get('tv_data') or {}
        value = dict(request_id=data['request_id'], purpose='current',
                     media=dict(tmdb_id=int(data['ids']['tmdb_id']), kind='tv' if is_tv else 'movie',
                                season=int(television['season']) if is_tv else 0,
                                episode=int(television['episode']) if is_tv else 0,
                                anime=bool(data.get('anime')), title=data['title'], release_title=data['source_title']),
                     selected={key: target[key] for key in ('source_info_hash', 'torrent_file_id', 'torrent_path', 'torrent_file_bytes')})
        from bobbi_core.source_intent import checked_body
        checked_body(value)
        return value
    except (ValueError, KeyError, TypeError):
        return None


def advance_intent(data):
    """A prepared current episode still needs its own next episode prepared."""
    if data.get('selection_policy') != 'exact' or data.get('is_torrent') or data.get('mode') not in {'tv', 'anime', 'episode'}:
        return None
    try:
        import re
        ids, television = data['ids'], data['tv_data']
        message = dict(request_id=data['request_id'], resource_id=data['prepared_resource_id'],
            media_id='tmdb:tv:{}:s{}:e{}'.format(int(ids['tmdb_id']), int(television['season']), int(television['episode'])),
            version_key=data['prepared_version_key'], source_info_hash=data['prepared_source_info_hash'])
        if (not re.fullmatch('[0-9a-f]{32}', message['request_id']) or not re.fullmatch('[0-9a-f]{64}', message['resource_id'])
                or not re.fullmatch('[0-9a-f]{40}', message['source_info_hash'])
                or not isinstance(message['version_key'], str) or not message['version_key']):
            return None
        return message
    except (ValueError, KeyError, TypeError):
        return None

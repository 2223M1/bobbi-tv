"""Read-only same-file readiness, shared by the BT opener and its UI retry."""
import json
import re
import time
from copy import deepcopy
from uuid import uuid4


FAILURES = {'buffer_timeout', 'preload_error', 'prepared_ready'}


def eligible(snapshot, data, category):
    if (not isinstance(snapshot, dict) or not isinstance(data, dict)
            or data.get('selection_policy') != 'exact' or not data.get('is_torrent')
            or not re.fullmatch('[0-9a-fA-F]{40}', str(data.get('info_hash', '')))
            or (category is not None and category not in FAILURES)):
        return False
    desired = snapshot.get('desired') or {}
    if not isinstance(desired, dict):
        return False
    failure = (None if category is None else dict(request_id=data.get('request_id'), category=category))
    return bool(desired.get('request_id') == data.get('request_id')
        and desired.get('selection_identity') == 'bt:' + data['info_hash'].lower()
        and desired.get('resolver_failure') == failure
        and (category in {'buffer_timeout', 'preload_error'} or desired.get('cancelled') is False)
        and desired.get('start_claimed') is False and desired.get('observed_once') is False
        and snapshot.get('observed') is None)


def unchanged(before, after):
    return (before.get('boot_id') == after.get('boot_id') and before.get('epoch') == after.get('epoch')
            and before.get('desired') == after.get('desired') and after.get('observed') is None)


def load_index():
    import xbmcvfs
    from bobbi_core.prepared_index import load
    return load(xbmcvfs.translatePath(
        'special://profile/addon_data/plugin.video.bobbi/bobi-prepared.json'))


def verified_entry(data, category, intent, cancelled=lambda: False, budget=3.0,
                   verification_id=None, pending_on_timeout=False, verification_binding=None):
    """No selection, cloud submission, player command or timeout extension.

    The caller still needs the returned owner snapshot's CAS. A later opener
    repeats its own fresh verification; this result is never a play receipt.
    """
    if (cancelled() or not isinstance(data, dict) or not isinstance(intent, dict)
            or intent.get('request_id') != data.get('request_id')):
        return None
    from bobbi_core.playback_ipc import call
    from bobbi_core.prepared_index import selected_cloud
    from bobbi_core.preparation_client import resolve_entry, capture_account
    try:
        # Never capture a login which happened after this playback began.
        account = capture_account(data, allow_capture=False)
        before = call({'operation': 'snapshot'})
        if not eligible(before, data, category):
            return None
        prepared = load_index()
        entry = selected_cloud(data, prepared)
        selected = intent.get('selected')
        if (prepared.get('account_scope') != account or not account['authenticated']
                or not entry or not entry.get('prepared_qualification')
                or not isinstance(selected, dict)
                or selected != (entry.get('video_context') or {}).get('selected')):
            return None
        if verification_binding is not None:
            binding = dict(request_id=data['request_id'], account=account, generation=prepared['generation'],
                media={key: data.get(key) for key in ('mode', 'ids', 'tv_data')},
                projection_account=prepared['account'], entry={key: entry.get(key) for key in
                ('key', 'prepared_qualification', 'prepared_source_info_hash', 'prepared_file_id',
                 'prepared_version_key', 'path', 'bytes', 'video_context')})
            if verification_binding and verification_binding != binding:
                return None  # A pending nonce cannot be retargeted even to another ready file.
            verification_binding.update(deepcopy(binding))
        if not resolve_entry(data, prepared, entry, cancelled, budget=budget,
                verification_id=verification_id, pending_on_timeout=pending_on_timeout) or cancelled():
            return None
        after = call({'operation': 'snapshot'})
        if not unchanged(before, after) or not eligible(after, data, category) or cancelled():
            return None
        return prepared, entry, after
    except TimeoutError:
        if pending_on_timeout:
            raise
        return None
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return None


def checked_context(value):
    from bobbi_platform.account_manager import validate_snapshot
    if (not isinstance(value, dict) or set(value) !=
            {'schema', 'request_id', 'info_hash', 'mode', 'ids', 'tv_data', '_account'}
            or type(value['schema']) is not int or value['schema'] != 1
            or not re.fullmatch('[0-9a-f]{32}', str(value['request_id']))
            or not re.fullmatch('[0-9a-f]{40}', str(value['info_hash']))
            or value['mode'] not in {'movie', 'movies', 'tv', 'anime', 'episode'}
            or not isinstance(value['ids'], dict) or set(value['ids']) != {'tmdb_id'}
            or not re.fullmatch('[1-9][0-9]{0,9}', str(value['ids']['tmdb_id']))
            or not isinstance(value['tv_data'], dict)):
        raise ValueError('Exact optional readiness context required')
    television = value['mode'] in {'tv', 'anime', 'episode'}
    if (set(value['tv_data']) != ({'season', 'episode'} if television else set())
            or any(type(n) is not int or not 0 <= n <= 10000 for n in value['tv_data'].values())
            or (television and value['tv_data']['episode'] < 1)):
        raise ValueError('Exact optional readiness episode required')
    account = validate_snapshot(value['_account'], authenticated=True)
    return dict(value, _account=account, selection_policy='exact', is_torrent=True)


def decode_context(raw, request_id):
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 1024:
        raise ValueError('Bounded optional readiness context required')
    value = checked_context(json.loads(raw))
    if value['request_id'] != request_id:
        raise ValueError('Readiness context belongs to another request')
    return value


def attach_context(url, data):
    """Carry only original media/account scope, never credentials or proof."""
    from urllib.parse import parse_qsl, quote, urlsplit
    if not isinstance(url, str) or not url.startswith('plugin://plugin.video.bobbi.torrent/'):
        return url
    try:
        query = dict(parse_qsl(urlsplit(url).query, max_num_fields=24))
        if query.get('request_id') != data.get('request_id') or 'ready_context' in query:
            return url
        tv = data.get('tv_data') or {}
        value = dict(schema=1, request_id=data['request_id'], info_hash=data['info_hash'].lower(),
            mode=data['mode'], ids={'tmdb_id': str(data['ids']['tmdb_id'])},
            tv_data=({k: int(tv[k]) for k in ('season', 'episode')}
                     if data['mode'] in {'tv', 'anime', 'episode'} else {}), _account=data['_account'])
        checked_context(value)
        raw = json.dumps(value, separators=(',', ':'), ensure_ascii=True)
        decode_context(raw, data['request_id'])
        return url + '&ready_context=' + quote(raw)
    except (KeyError, TypeError, ValueError, RuntimeError, AttributeError):
        return url  # Optional readiness never prevents ordinary BT playback.


class ReadyProbe:
    """One resolver-local nonce, bounded polls; no persistent or global state."""
    def __init__(self, data, clock=time.monotonic):
        self.data, self.clock = data, clock
        self.due = self.expires = 0.0
        self.nonce = None
        self.binding = {}

    def poll(self, info_hash, file, cancelled, deadline):
        now = self.clock()
        if (now < self.due or now >= deadline or cancelled()
                or self.data['info_hash'] != info_hash):
            return False
        if self.nonce is None or now >= self.expires:
            self.nonce, self.expires = uuid4().hex, now + 3.0
            self.binding = {}
        intent = dict(request_id=self.data['request_id'], selected=dict(source_info_hash=info_hash,
            torrent_file_id=file['id'], torrent_path=file['path'], torrent_file_bytes=file['length']))
        self.due = now + .5
        try:
            result = verified_entry(self.data, None, intent, cancelled,
                budget=min(.3, deadline - now), verification_id=self.nonce, pending_on_timeout=True,
                verification_binding=self.binding)
        except TimeoutError:
            return False  # Same nonce next tick; never enqueue a new job per poll.
        self.nonce = None
        self.due = self.clock() + 2.0
        return result is not None and not cancelled() and self.clock() < deadline

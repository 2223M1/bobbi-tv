"""Local projection and bounded preparation IPC for selected direct sources."""
import json
from pathlib import Path
import time
from uuid import uuid4

from .runtime_paths import ProfilePath
SNAPSHOT = ProfilePath('bobi-direct.json')


def intent(data):
    source = data.get('direct_source')
    if not isinstance(source, dict) or source.get('provider') != 'mdsub' or data.get('selection_policy') != 'exact':
        return None
    try:
        tv = data.get('tv_data') or {}
        kind = 'tv' if data.get('mode') in ('tv', 'anime', 'episode') else 'movie'
        body = dict(request_id=data['request_id'], source=dict(source), media=dict(tmdb_id=int(data['ids']['tmdb_id']),
            kind=kind, season=int(tv['season']) if kind == 'tv' else 0, episode=int(tv['episode']) if kind == 'tv' else 0))
        from bobbi_core.direct_cloud import checked
        checked(body)
        return body
    except (KeyError, ValueError, TypeError):
        return None


def snapshot():
    try:
        with Path(SNAPSHOT).open('rb') as stream:
            raw = stream.read(8 * 1024**2 + 1)
        if len(raw) > 8 * 1024**2:
            return {}
        data = json.loads(raw)
        if 'account_scope' in data:
            from .prepared_index import scope_is_current
            if not scope_is_current(data['account_scope']):
                return {}
        return data if data.get('schema') == 1 and isinstance(data.get('entries'), list) else {}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def entry(data, view=None):
    body = intent(data)
    if body is None:
        return None
    from bobbi_core.direct_cloud import source_key
    key = source_key(body)
    matches = [row for row in (view if view is not None else snapshot()).get('entries', [])
               if row.get('key') == key and row.get('media') == body['media'] and row.get('source') == body['source']]
    return matches[0] if len(matches) == 1 else None


def prepare(data):
    body = intent(data)
    if body is None:
        return dict(state='not_applicable')
    from bobbi_core.preparation_client import call
    return call('catalog_prepare', body)


def resolve(data, cancelled=lambda: False):
    row = entry(data)
    if not row or row['state'] != 'ready':
        return None
    from bobbi_core.preparation_client import call
    body = dict(key=row['key'], request_id=data['request_id'], verification_id=uuid4().hex)
    deadline = time.monotonic() + 3
    while not cancelled() and time.monotonic() < deadline:
        try:
            result = call('catalog_resolve', body, timeout=min(.3, max(.001, deadline - time.monotonic())))
        except OSError:
            result = dict(state='pending')
        if result.get('state') == 'ready':
            from bobbi_core.direct_cloud import MOUNT
            expected = dict(body, proof=row['proof'], bytes=row['source']['size'], path=MOUNT + row['file']['path'])
            if all(result.get(k) == v for k, v in expected.items()) and not cancelled():
                return result
            return None
        if result.get('state') != 'pending':
            return None
        time.sleep(min(.05, max(0, deadline - time.monotonic())))
    return None

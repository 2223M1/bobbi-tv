"""Cloud-first continuation of the exact service-proved adjacent BT release."""
from copy import deepcopy

from lib.cinema import _shared
from bobbi_core.video_context import checked_video


def applies(data):
    return (data.get('selection_policy') == 'exact' and not data.get('direct_source')
            and bool(data.get('is_torrent') or data.get('prepared_source_info_hash')
                     or data.get('resolved_backend') == 'local_torrserver'))


def prepared_snapshot():
    from lib.clients.bobi_library import load_prepared_index
    try:
        return load_prepared_index()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return {'titles': []}  # Missing cloud projection does not revoke BT proof.


def current_selection(data):
    if isinstance(data.get('_bt_current_selected'), dict):
        return data['_bt_current_selected']
    if data.get('video_context'):
        return checked_video(data['video_context'])['selected']
    return None


def account_is_current(data):
    """Read through the same scoped host; never capture a replacement account."""
    from bobbi_core.preparation_client import call, capture_account
    try:
        call('ping', {}, timeout=.1, expected_account=capture_account(data, allow_capture=False))
        return True
    except (OSError, ValueError, TypeError, RuntimeError):
        return False


def _service_proof(data, cancelled):
    from bobbi_core.preparation_client import call, capture_account
    selected = current_selection(data)
    if selected is None or cancelled():
        return None
    account = capture_account(data, allow_capture=False)
    status = call('status', {'request_id': data['request_id']}, expected_account=account)
    if (cancelled() or status.get('request_id') != data['request_id']
            or status.get('state') != 'accepted'):
        return None
    proof = status.get('result', {}).get('source_proof')
    if not isinstance(proof, dict) or proof.get('request_id') != data['request_id']:
        return None
    anchor = checked_video(proof['anchor'])
    tv = data.get('tv_data') or {}
    media = 'tmdb:tv:{}:s{}:e{}'.format((data.get('ids') or {}).get('tmdb_id'), tv.get('season'), tv.get('episode'))
    if anchor['media_id'] != media or selected != anchor['selected']:
        return None
    return proof


def _bt_data(data, proof):
    row = proof.get('next') if proof else None
    if not isinstance(row, dict):
        return None
    anchor, context = checked_video(proof['anchor']), checked_video(row['video_context'])
    tv = data['tv_data']
    target = 'tmdb:tv:{}:s{}:e{}'.format(data['ids']['tmdb_id'], tv['season'], int(tv['episode']) + 1)
    if context['media_id'] != target or row.get('account') != proof['account']:
        return None
    same = anchor['release_key'] == context['release_key']
    if not same:
        from pathlib import PurePosixPath
        from bobbi_core.episode_revision import compatible_pair
        same = compatible_pair(PurePosixPath(anchor['selected']['torrent_path']).name,
            PurePosixPath(context['selected']['torrent_path']).name, int(tv['season']), int(tv['episode']),
            anchor['release_key'], context['release_key'])
    if not same:
        return None
    selected = context['selected']
    if selected['torrent_file_id'] < 1:
        return None
    from .direct_continuity import episode_data
    result = episode_data(data, int(tv['season']), int(tv['episode']) + 1)
    magnet = 'magnet:?xt=urn:btih:' + selected['source_info_hash']
    result.update(url=magnet, magnet=magnet, info_hash=selected['source_info_hash'],
        source_title=row['source_title'], size=selected['torrent_file_bytes'], type='Torrent',
        indexer='BT', is_torrent=True, prepared_version_key=context['release_key'],
        _bt_next_selected=deepcopy(selected), video_context=context,
        _next_recheck=True, _next_transport='bt')
    return result


def choose_next(current, index, cancelled=lambda: False, fresh=False, fresh_budget=1.0):
    """Bounded status read; readiness is verified before a final reservation.

    No status/lookup error can promote an unproved BT candidate. An already
    qualified cloud record can still be used when optional BT proof is absent.
    """
    if not applies(current) or cancelled():
        return None
    data = deepcopy(current)
    proof = None
    try:
        proof = _service_proof(data, cancelled)
        if proof:
            data['prepared_version_key'] = proof['anchor']['release_key']
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        pass
    from .continuity import next_cloud_data
    candidate = next_cloud_data(data, index)
    if candidate and fresh and not cancelled():
        from bobbi_core.preparation_client import resolve_entry
        entries = [row for title in index.get('titles', []) for row in title.get('sources', [])
                   if row.get('key') == candidate.get('prepared_resource_id')]
        try:
            if len(entries) != 1 or not resolve_entry(candidate, index, entries[0], cancelled,
                                                     budget=fresh_budget, pending_on_timeout=True):
                candidate = None
            else:
                candidate['_next_cloud_verified'] = True
                candidate['video_context'] = entries[0].get('video_context')
        except TimeoutError:
            # Native EOF's three-second reservation receipt cannot be spent
            # waiting on optional cloud IO. Pending is NOT evidence of absence:
            # retain this qualified 115 route and let the normal child resolver
            # finish fresh verification. It may fail, but never bounces to BT.
            candidate['_next_cloud_pending'] = True
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            candidate = None
    if candidate:
        candidate.update(_next_recheck=True, _next_transport='115')
    elif proof and not cancelled():
        try:
            candidate = _bt_data(data, proof)
        except (ValueError, KeyError, TypeError):
            candidate = None
    return candidate if (not cancelled() and (not fresh or account_is_current(data))) else None


def resolve_standard(data, cancelled, client=None):
    """Resolve the proved file once, without UI, under the standard EOF budget."""
    selected = data['_bt_next_selected']
    context = checked_video(data['video_context'])
    if selected != context['selected'] or cancelled():
        raise ValueError('BT_NEXT_SELECTION_CHANGED')
    if client is None:
        from lib.portable import local_client
        client = local_client()
    def choose(files):
        matches = [file for file in files if (file.id, file.path, file.size) ==
                   (selected['torrent_file_id'], selected['torrent_path'], selected['torrent_file_bytes'])]
        return matches[0] if len(matches) == 1 and not cancelled() else None
    resolved = client.select_source(selected['source_info_hash'], magnet=data['magnet'],
                                    choose_file=choose, cancelled=cancelled, budget=8.0)
    if (cancelled() or resolved.get('info_hash') != selected['source_info_hash']
            or resolved.get('file_id') != selected['torrent_file_id']
            or resolved.get('file_path') != selected['torrent_path']
            or resolved.get('size') != selected['torrent_file_bytes']):
        raise ValueError('BT_NEXT_SELECTION_CHANGED')
    result = deepcopy(data)
    result.pop('magnet', None)
    result.update(url=resolved['url'], is_torrent=False, resolved_backend='local_torrserver',
                  file_id=selected['torrent_file_id'], torrent_path=selected['torrent_path'],
                  torrent_file_bytes=selected['torrent_file_bytes'], file_evidence='AUTO_VERIFIED_FILE')
    return result

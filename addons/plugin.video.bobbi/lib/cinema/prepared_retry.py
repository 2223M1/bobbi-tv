"""One fresh selection of the identical prepared file after a pre-AV BT failure."""


def retryable(snapshot, data, category):
    """A failed/consumed opener or a changed user selection cannot grant a retry."""
    if (not isinstance(data, dict) or data.get('selection_policy') != 'exact'
            or not data.get('is_torrent') or category not in {'buffer_timeout', 'preload_error'}):
        return False
    desired = snapshot.get('desired') or {}
    return bool(desired.get('request_id') == data.get('request_id')
        and desired.get('selection_identity') == 'bt:' + str(data.get('info_hash', '')).lower()
        and desired.get('resolver_failure') == dict(request_id=data.get('request_id'), category=category)
        and desired.get('start_claimed') is False and desired.get('observed_once') is False
        and snapshot.get('observed') is None)


def unchanged(before, after):
    return (before.get('boot_id') == after.get('boot_id') and before.get('epoch') == after.get('epoch')
            and before.get('desired') == after.get('desired') and after.get('observed') is None)


def ready_source(data, category, intent, cancelled=lambda: False):
    """Read/verify only; never enqueue cloud work or authorize playback here.

    The caller mints a new request using the returned snapshot's CAS epoch.
    The normal prepared-source resolver and player repeat file verification.
    """
    if cancelled() or not isinstance(intent, dict) or intent.get('request_id') != data.get('request_id'):
        return None
    from lib.cinema.playback_ipc import call
    from lib.cinema.prepared_index import selected_cloud
    from lib.cinema.preparation_client import resolve_entry
    from lib.clients.bobi_library import load_prepared_index, to_source
    try:
        before = call({'operation': 'snapshot'})
        if not retryable(before, data, category):
            return None
        prepared = load_prepared_index()
        entry = selected_cloud(data, prepared)
        selected = intent.get('selected')
        # A pack/hash is not sufficient: require the precise file selected by
        # JackTorr before buffering (id + path + bytes), not a sibling variant.
        if (not entry or not isinstance(selected, dict)
                or selected != (entry.get('subtitle_video') or {}).get('selected')):
            return None
        if not resolve_entry(data, prepared, entry, cancelled) or cancelled():
            return None
        after = call({'operation': 'snapshot'})
        if not unchanged(before, after) or not retryable(after, data, category):
            return None
        tv = data.get('tv_data') or {}
        identity = dict(tmdb_id=str((data.get('ids') or {}).get('tmdb_id', '')),
                        mode=data.get('mode'), season=tv.get('season'), episode=tv.get('episode'))
        return to_source(prepared, entry, identity), after
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return None  # Unavailable verification preserves the ordinary error/picker.

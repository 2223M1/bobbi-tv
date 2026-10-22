"""One fresh selection of the identical prepared file before any native AV."""
from lib.cinema import _shared  # dependency bootstrap
from bobbi_core.prepared_retry import eligible as retryable, unchanged, verified_entry


def ready_source(data, category, intent, cancelled=lambda: False):
    """Read/verify only; never enqueue cloud work or authorize playback here.

    The caller mints a new request using the returned snapshot's CAS epoch.
    The normal prepared-source resolver and player repeat file verification.
    """
    result = verified_entry(data, category, intent, cancelled)
    if result is None:
        return None
    from lib.clients.bobi_library import to_source
    prepared, entry, after = result
    tv = data.get('tv_data') or {}
    identity = dict(tmdb_id=str((data.get('ids') or {}).get('tmdb_id', '')),
                    mode=data.get('mode'), season=tv.get('season'), episode=tv.get('episode'))
    try:
        return to_source(prepared, entry, identity), after, dict(data['_account'])
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return None

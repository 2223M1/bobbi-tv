"""Experimental read-only server progress, bound to the existing catalogue.

PMS viewOffset and Jellyfin/Emby UserData are item-level observations, not
version/Part content evidence. This module never saves history, reserves a
session, seeks, changes a mapping or sends progress. There is no sync database.
"""
from bobbi_core.catalog_query import opaque
from bobbi_core.file_ref import validate
from bobbi_core.server_ref import PROVIDERS, identifier, parts
from .pan_accounts import PanError, scope


def item_progress(provider, entry, item):
    """Whitelist known units from the existing item response; absent is unknown."""
    if provider not in PROVIDERS or type(item) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    entry = identifier(entry)
    if provider == 'plex':
        position, duration, count = item.get('viewOffset'), item.get('duration'), item.get('viewCount')
        if count is not None and (type(count) is not int or not 0 <= count < 2**31):
            raise PanError('PAN_REPLY_INVALID')
        played, unit = (count > 0 if count is not None else None), 1000
    else:
        user = item.get('UserData', {})
        if type(user) is not dict:
            raise PanError('PAN_REPLY_INVALID')
        position, duration, played = user.get('PlaybackPositionTicks'), item.get('RunTimeTicks'), user.get('Played')
        unit = 10000000
        if played is not None and type(played) is not bool:
            raise PanError('PAN_REPLY_INVALID')
    def seconds(value):
        if value is None:
            return None
        if type(value) is not int or not 0 <= value <= 864000 * unit:
            raise PanError('PAN_REPLY_INVALID')
        return value / unit
    position, duration = seconds(position), seconds(duration)
    duration = duration or None
    if position is not None and duration is not None and position > duration:
        raise PanError('PAN_REPLY_INVALID')
    return dict(scope='item', entry_id=entry, position=position, duration=duration, played=played)


def _target(catalog, expected, object_id):
    """Reuse the original source guard and FileRef; never search by title."""
    catalog._play_source(expected, object_id)
    index = catalog.index
    with index.lock:
        revision = index.scope_revision(expected)
        ref = validate(index.trusted_file(expected, object_id))
        item = index.item(expected, object_id)
        if (index.scope_revision(expected) != revision or
                item['file']['observation_key'] != opaque(ref)):
            raise PanError('PAN_FILE_CHANGED')
    if ref['provider'] not in PROVIDERS or (ref['provider'], ref['account_id']) != (
            expected['provider'], expected['account_id']):
        raise PanError('PAN_ACCOUNT_CHANGED')
    return ref, item, revision


def _history_available(history):
    # FileHistory.get intentionally includes this adapter's pending journal.
    # Do not present an unpersisted failed report as the stored comparison row.
    # Keep the original journal intact; this explicit read never flushes it.
    if history.database.has_pending():
        raise OSError('FILE_HISTORY_PENDING')


def inspect_progress(catalog, history, expected, object_id):
    """One explicit bounded read, not a poller or a playback/sync authority.

    Composition supplies the current profile's existing CatalogService and
    FileHistory. No credentials or scope are rediscovered from global state.
    Local index locks are released before HTTP; publication rechecks the exact
    scope and catalogue revision. The returned observations are not a lease.
    """
    expected = scope(expected, authenticated=True)
    if expected['provider'] not in PROVIDERS:
        raise PanError('PAN_PROVIDER_INVALID')
    catalog._profile()
    _history_available(history)
    ref, item, revision = _target(catalog, expected, object_id)
    selected = dict(file_id=ref['file_id'], server_id=ref['namespace'], name=ref['name'],
                    size=ref['size'], directory=False)
    pans = catalog.pans
    # These are metadata GETs only, using the existing per-provider lane,
    # cancellation, source-generation checks, budget and request ceiling.
    with pans.scan_operation(expected, max_requests=4, max_pages=1, max_items=1,
                             seconds=12, kind='metadata') as operation:
        with pans._using_client(expected, operation) as client:
            remote = client.read_progress(selected)
    current, fresh_item, fresh_revision = _target(catalog, expected, object_id)
    if current != ref or revision != fresh_revision or item != fresh_item:
        raise PanError('PAN_FILE_CHANGED')
    _history_available(history)
    try:
        local = history.get(ref['id'])
    except ValueError as error:
        if str(error) != 'FILE_HISTORY_NOT_FOUND':
            raise
        local = None
    _history_available(history)
    entry, media, part, part_index, part_count = parts(ref['file_id'])
    if remote['scope'] != 'item' or remote['entry_id'] != entry:
        raise PanError('PAN_FILE_CHANGED')
    local = local if local is not None and local['sequence'] > 0 else None
    disposition, reason = 'item_only', 'SERVER_CONTENT_IDENTITY_UNPROVEN'
    if remote['position'] is None and remote['played'] is None:
        disposition, reason = 'unavailable', 'SERVER_PROGRESS_UNKNOWN'
    if local is not None:
        completed = local['completion_reason'] == 'NATURAL_EOF'
        if local['file_ref'] != ref:
            disposition, reason = 'conflict', 'LOCAL_FILE_OBSERVATION_CHANGED'
        elif (remote['played'] is not None and remote['played'] != completed or
                remote['position'] is not None and remote['position'] != local['position']
                and not (remote['played'] is True and completed)):
            disposition, reason = 'conflict', 'LOCAL_AND_SERVER_PROGRESS_DIFFER'
    pans.accounts.require_current(expected)
    catalog._profile()
    return dict(experimental=True, disposition=disposition, reason=reason,
        resume_allowed=False, write_allowed=False, file_id=ref['id'], observation_key=opaque(ref),
        target=dict(provider=ref['provider'], server_id=ref['namespace'], entry_id=entry,
                    media_id=media, part_id=part, part_index=part_index, part_count=part_count),
        mapping=item['mapping'], mapping_revision=item['revision'], mapping_provenance=item['provenance'],
        local=({key: local[key] for key in ('position', 'duration', 'completion_reason',
            'generation', 'session_id', 'sequence')} if local is not None else None), remote=remote)

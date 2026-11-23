"""Read-only next-episode discovery; a native EOF permit owns its eventual UI.

No discovered candidate is resolved or played here. A manual source click must
create a new exact selection through the normal picker.
"""
from copy import deepcopy
from datetime import date
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4


def _position(data):
    if data.get('mode') not in ('tv', 'anime', 'episode'):
        return None
    try:
        values = tuple(int(value) for value in ((data.get('ids') or {})['tmdb_id'],
            (data.get('tv_data') or {})['season'], (data.get('tv_data') or {})['episode']))
        return values if min(values) > 0 else None
    except (KeyError, TypeError, ValueError):
        return None


def target_episode(current, cancelled):
    """Prove the adjacent aired catalogue episode, including a season boundary."""
    position = _position(current)
    if not position or cancelled():
        return None
    from lib.clients.tmdb.detail_cache import season_page_params, value
    from lib.clients.tmdb.utils.utils import tmdb_get
    tmdb, season, episode = position
    # The directory already warms this precise lean page. The unqualified
    # request has a different cache key and appends trailers/images/credits.
    def page(number):
        return tmdb_get('season_details', season_page_params(tmdb, number, 'en-US'))
    details = page(season)
    if cancelled():
        return None
    episodes = value(details, 'episodes') or []
    numbers = [value(row, 'episode_number') for row in episodes]
    # A stale/out-of-range current episode is not a season-ending receipt.
    if numbers.count(episode) != 1:
        return None
    next_season, next_episode = season, episode + 1
    if next_episode not in numbers:
        if any(type(number) is int and number > episode for number in numbers):
            return None  # A gap is not permission to skip an episode.
        show = tmdb_get('tv_details', tmdb)
        if cancelled():
            return None
        seasons = [value(row, 'season_number') for row in value(show, 'seasons') or []]
        if season + 1 not in seasons:
            return None
        next_season, next_episode = season + 1, 1
        details = page(next_season)
        if cancelled():
            return None
        episodes = value(details, 'episodes') or []
    matches = [row for row in episodes if value(row, 'episode_number') == next_episode]
    if len(matches) != 1:
        return None
    target = matches[0]
    try:
        if date.fromisoformat(value(target, 'air_date')) > date.today():
            return None
    except (AttributeError, TypeError, ValueError):
        return None  # Unknown/future release dates must not advance unattended.
    from lib.utils.player.direct_continuity import episode_data
    data = episode_data(current, next_season, next_episode)
    data.update(mode='tv', autoplay=False, query=current.get('query') or current.get('title', ''))
    data['tv_data']['name'] = value(target, 'name', '')
    return data


def picker_note(reason):
    # Callers pass only fixed lifecycle labels, never titles, IDs or URLs.
    import xbmc
    from lib.utils.kodi.utils import kodilog
    kodilog('[CINEMA-NEXT] PICKER_' + reason, level=xbmc.LOGINFO)


class NextSourceSearch:
    """One bounded, cancellable prefetch using the ordinary progressive search."""
    def __init__(self, current, stopped):
        self.current = deepcopy(current)
        self.stopped = stopped
        self.closed = Event()
        self.finished = Event()
        self.lock = Lock()
        self.entry = None
        self.account = None
        self.deadline = monotonic() + 35

    def cancelled(self):
        return self.closed.is_set() or self.stopped.is_set() or monotonic() >= self.deadline

    def start(self):
        try:
            Thread(target=self._prepare, name='BobbiNextSources', daemon=True).start()
        except RuntimeError:
            self.finished.set()
        return self

    def _prepare(self):
        phase = 'ACCOUNT'
        try:
            from bobbi_core.metadata_transport import request_budget
            from bobbi_platform.account_manager import validate_snapshot
            from bobbi_platform.runtime import call
            # Bind before even metadata IO. A BT parent may be independent of
            # 115, but a prefetched personal-library card is not accountless.
            account = validate_snapshot(call('account_status', {}, timeout=.3), authenticated=True)
            expected = self.current.get('_account')
            if expected is not None and validate_snapshot(expected, authenticated=True) != account:
                picker_note('ACCOUNT_CHANGED')
                return
            with self.lock:
                if self.cancelled():
                    return
                self.account = account
                self.current['_account'] = deepcopy(account)
            phase = 'TARGET'
            with request_budget(self.deadline, self.cancelled, quiet=True):
                data = target_episode(self.current, self.cancelled)
            if not data or self.cancelled():
                picker_note('TARGET_UNVERIFIED' if not self.cancelled() else 'DISCOVERY_CANCELLED')
                return
            phase = 'SEARCH'
            from lib.search import create_next_source_search
            session, pump = create_next_source_search(data, budget=min(30, max(.1, self.deadline - monotonic())))
            with self.lock:
                if self.cancelled():
                    pump.cancel()
                    return
                self.entry = (data, session, pump)
                pump.start()
            picker_note('SEARCH_STARTED')
        except Exception:
            # No background failure can open a window or turn into autoplay.
            picker_note(phase + '_UNAVAILABLE')
        finally:
            self.finished.set()

    def snapshot(self):
        with self.lock:
            return self.entry

    def account_scope(self):
        with self.lock:
            return deepcopy(self.account)

    def cancel(self):
        self.closed.set()
        with self.lock:
            if self.entry:
                self.entry[2].cancel()


def prefetch(player):
    job = getattr(player, '_cinema_picker_search', None)
    if job is None and _position(player.data):
        job = NextSourceSearch(player.data, player._cinema_cancel).start()
        player._cinema_picker_search = job
    return job


def queue(player, entries):
    """Consume EOF immediately, before any metadata, source search or history IO."""
    if player.data.get('selection_policy') != 'exact' or not _position(player.data):
        return False
    from bobbi_core.playback_request import context
    call = player.playback_client.call
    from bobbi_platform.account_manager import validate_snapshot
    child = uuid4().hex
    account = deepcopy(player.data.get('_account'))
    job = getattr(player, '_cinema_picker_search', None)
    captured = job.account_scope() if job is not None else None
    if captured is not None:
        if account is not None and account != captured:
            return False
        account = captured
    owner = None
    try:
        result = call(dict(player._owner_context, operation='reserve_next_picker',
            native_instance=player._native_instance, child_request_id=child,
            **({'account_scope': account} if account is not None else {})))
        if not result.get('reserved'):
            return False
        owner = context(result['snapshot'], child)
        account = validate_snapshot(result.get('account_scope'), authenticated=True)
    except (KeyError, AttributeError, OSError, ValueError, RuntimeError):
        if owner is not None:
            release({'_next_picker_context': owner}, playback_client=player.playback_client)
        return False  # Never replay a possibly accepted one-use reservation.
    player._cinema_natural_queued = True
    job = prefetch(player)
    entries.append(dict(data={'_next_picker_context': owner, '_account': account}, next_picker=job))
    return True


def picker_status(data, *, playback_client, wait_retry=None):
    call = playback_client.call
    owner = data.get('_next_picker_context')
    if not isinstance(owner, dict):
        return None
    message = dict(owner, operation='next_picker_status',
                   **({'account_scope': deepcopy(data['_account'])} if data.get('_account') is not None else {}))
    # An interactive window gets one immediate readback. At EOF, teardown can
    # occupy consecutive owner ticks; give the *reserved* child a bounded,
    # cancellable recovery window. Never retry the reservation or a player op.
    delays = (.08, .16, .32, .64) if wait_retry is not None else (0,)
    for attempt in range(len(delays) + 1):
        try:
            status = call(message)
        except OSError as error:
            if str(error) in ('RUNTIME_INSTANCE_CHANGED', 'PLAYBACK_BINDING_UNAVAILABLE', 'PROFILE_CHANGED'):
                picker_note('PERMIT_BINDING_RETIRED')
                break
            if attempt >= len(delays):
                picker_note('PERMIT_READ_UNAVAILABLE')
                break
            if wait_retry is not None and not wait_retry(delays[attempt]):
                break
            picker_note('PERMIT_READ_RECHECK')
            continue
        except (ValueError, RuntimeError):
            picker_note('PERMIT_REJECTED')
            break
        if not isinstance(status, dict):
            picker_note('PERMIT_READ_UNAVAILABLE')
            break
        if status.get('allowed') is True:
            snapshot = status.get('snapshot')
            return snapshot if isinstance(snapshot, dict) else None
        picker_note('PERMIT_REVOKED')
        break
    return None


def release(data, *, playback_client):
    """Retire only this UI reservation; a subsequent manual selection is untouched."""
    call = playback_client.call
    try:
        call(dict(data['_next_picker_context'], operation='cancel'))
    except (KeyError, OSError, ValueError, RuntimeError):
        pass


def discard(player, entries):
    job = getattr(player, '_cinema_picker_search', None)
    if job is None:
        return
    job.cancel()
    for entry in list(entries):
        if entry.get('next_picker') is job:
            release(entry['data'], playback_client=player.playback_client)
            entries.remove(entry)

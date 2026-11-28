"""Resident standard-Kodi observation and shared cinema policy adapters."""
from copy import deepcopy
from queue import Queue, Empty, Full
from uuid import uuid4
from threading import Event, Thread, Lock
import time

from bobbi_platform.standard_session import StandardSession
from bobbi_core.file_evidence import PLAY_ONCE_EVIDENCE


class HistoryWriter:
    """Bounded single writer; a slow disk must not stall callbacks or IPC."""
    def __init__(self, report, profile_root=None):
        from bobbi_platform.paths import profile_root as current_profile_root
        # Capture the owning runtime's path before the worker can outlive a
        # Kodi profile switch. Opening the database remains worker-only IO.
        self.profile_root = (profile_root if profile_root is not None else
                             current_profile_root('plugin.video.bobbi'))
        self.queue, self.done, self.report = Queue(maxsize=32), Event(), report
        self.admission = Lock()
        # References to the Queue's own jobs, including its one in-flight job.
        # This is not another consumption queue; it is bounded by 32 + 1.
        self._jobs = {}
        self.accepted = self.completed = self.failed = self.diagnostic_failures = 0
        self.worker_failed = False
        self.worker = Thread(target=self.run, name='bobbi-standard-history', daemon=True)
        self.worker.start()

    def save(self, data):
        """True means admitted, not durable. Only saturation coalesces reports."""
        snapshot = deepcopy(data)
        key = None
        try:
            from lib.db.file_history import coalescing_key
            key = coalescing_key(snapshot, self.profile_root)
        except ImportError:
            pass
        with self.admission:
            if self.done.is_set():
                return False
            job = dict(key=key, latest=snapshot, revision=1)
            try:
                if len(self._jobs) >= self.queue.maxsize + 1:
                    raise Full
                self.queue.put_nowait(job)
                self._jobs[id(job)] = job
                self.accepted += 1
                return True
            except Full:
                matches = [item for item in self._jobs.values()
                           if key is not None and item['key'] == key]
                latest = max(matches, key=lambda item: item['latest']['_file_history_sequence'],
                             default=None)
                if latest is not None and snapshot['_file_history_sequence'] > latest['latest']['_file_history_sequence']:
                    # Whole incoming observation; absence of facts still revokes.
                    latest.update(latest=snapshot, revision=latest['revision'] + 1)
                    self.accepted += 1
                    return True
        self.diagnose('HISTORY_QUEUE_FULL')
        return False

    def diagnose(self, code):
        try:
            self.report(code)
        except Exception:
            self.diagnostic_failures += 1

    def run(self):
        database = None
        while not self.done.is_set() or not self.queue.empty():
            try:
                job = self.queue.get(timeout=.1)
            except Empty:
                continue
            accounted = 0
            try:
                while True:
                    with self.admission:
                        data, revision = job['latest'], job['revision']
                    failed = False
                    try:
                        try:
                            from lib.db.pickle_db import PickleDatabase
                            from lib.utils.general.utils import set_watched_file
                            if database is None:
                                database = PickleDatabase(profile_root=self.profile_root)
                            if set_watched_file(data, database=database) is False:
                                failed = True
                                self.failed += 1
                                self.diagnose('HISTORY_WRITE_FAILED')
                        except Exception:
                            if not failed:
                                failed = True
                                self.failed += 1
                            self.diagnose('HISTORY_WRITE_FAILED')
                    except BaseException:
                        with self.admission:
                            self.worker_failed = True
                            self.done.set()  # Never admit work behind a dead worker.
                        if not failed:
                            self.failed += 1
                        try:
                            self.diagnose('HISTORY_WORKER_FAILED')
                        except BaseException:
                            pass  # Failure reporting cannot prevent drain accounting.
                        return
                    finally:
                        with self.admission:
                            # Count admitted reports covered by this attempted
                            # revision, not queue slots or successful disk writes.
                            # An unattempted newer revision must remain outstanding.
                            self.completed += revision - accounted
                            accounted = revision
                    with self.admission:
                        if job['revision'] == revision:
                            self._finish(job)
                            break
            finally:
                with self.admission:
                    self._finish(job)

    def _finish(self, job):
        """Admission lock held: remove exactly this Queue job once."""
        if self._jobs.get(id(job)) is job:
            del self._jobs[id(job)]
            self.queue.task_done()

    def close(self):
        with self.admission:
            self.done.set()
        self.worker.join()  # Every admission must be covered by an attempt.
        if self.worker_failed or self.completed != self.accepted or self._jobs or not self.queue.empty():
            raise RuntimeError('HISTORY_DRAIN_INCOMPLETE')


def discover(data, host, deadline, cancelled):
    from lib.services.subtitle_fallback import playback_context, discover_candidate
    provider = host.subtitle_candidates()
    return discover_candidate(playback_context(data, None), deadline,
        lambda: cancelled() or not host.check_profile(), provider, host.sidecar_candidate,
        root=host.subtitle_root)


def resolve_selected_cloud(data, cancelled, session):
    '''Read-only compatibility for an explicitly selected old personal copy.'''
    if data.get('direct_cloud_required') or data.get('direct_cloud_key'):
        resolved = session.direct_resolve(data, cancelled) if session else None
        if not resolved:
            raise ValueError('SELECTED_CLOUD_FILE_UNAVAILABLE')
        data.update(url=resolved['path'], direct_cloud_key=resolved['key'], size=resolved['bytes'])
        data.pop('direct_cloud_required', None)


def resolve_selected(data, cancelled, *, session=None):
    """Reuse verified resolvers without depending on native player receipts."""
    if data.get('_catalog_next'):
        from lib.utils.player.direct_continuity import resolve_direct
        data['url'] = resolve_direct(data, cancelled)
    resolve_selected_cloud(data, cancelled, session)
    if data.get('prepared_resource_id'):
        from lib.clients.bobbi_library import load_prepared_index, local_path
        from bobbi_core.prepared_transport import playback_path
        snapshot = load_prepared_index(session=session)
        entries = [entry for title in snapshot['titles'] for entry in title['sources']
                   if entry['key'] == data['prepared_resource_id']]
        entry = session.resolve_entry(data, snapshot, entries[0], cancelled) if session and len(entries) == 1 else None
        if not entry:
            raise ValueError('SELECTED_CLOUD_FILE_CHANGED')
        data.update(url=playback_path(snapshot['mount_root'], entry),
                    source_title=entry['title'], video_context=entry.get('video_context'),
                    subtitles_path=[] if entry.get('_playback_url') else [local_path(snapshot['mount_root'], path)
                                    for path in entry.get('subtitles', [])[:4]])
    if cancelled():
        raise RuntimeError('SELECTION_CANCELLED')
    return data


def next_data(current, cancelled, *, session=None):
    if current.get('file_evidence') in PLAY_ONCE_EVIDENCE or cancelled():
        return None
    if isinstance(current.get('_owned_next'), dict):
        from bobbi_platform.owned_playback import resolve_owned_next
        owned_next = deepcopy(current['_owned_next'])
        next_item = resolve_owned_next(current, owned_next, cancelled)
        if not next_item or cancelled():
            return None
        next_item.update(
            request_id=uuid4().hex,
            selection_policy='exact',
            _account=deepcopy(current['_account']),
            direct_playback_handoff=True,
        )
        return next_item
    from lib.utils.player.direct_continuity import is_catalog_source, next_direct_data
    if is_catalog_source(current):
        data, _ = next_direct_data(current, cancelled)
        previous = current.get('_continuation_direct_source')
        if data and previous is not None and data['direct_source'] != previous:
            return None  # The original candidate disappeared; do not resolve its replacement.
    else:
        from lib.utils.player.continuity import next_cloud_data
        from lib.utils.player.bt_continuity import applies, choose_next
        try:
            from lib.clients.bobbi_library import load_prepared_index
            index = load_prepared_index(session=session)
        except (OSError, ValueError, RuntimeError):
            index = {'titles': []}
        data = (choose_next(current, index, cancelled, fresh=bool(current.get('_continuation_final')), fresh_budget=3.0,
                            session=session)
                if applies(current) else next_cloud_data(current, index))
    if not data or cancelled():
        return None
    data.update(request_id=uuid4().hex, selection_policy='exact',
                _account=deepcopy(current['_account']), direct_playback_handoff=True)
    if data.get('_catalog_next') and not current.get('_continuation_final'):
        return data  # Metadata only. A long pause must not age a playable URL or register a stream.
    if data.get('_next_transport') == 'bt':
        from lib.utils.player.bt_continuity import resolve_standard
        # Keep a proved tuple provisional while the current episode plays.
        # Open the BT transport only after EOF's final cloud-first recheck.
        return resolve_standard(data, cancelled) if current.get('_continuation_final') else data
    if data.get('_next_cloud_verified'):
        return data if not cancelled() else None
    return resolve_selected(data, cancelled, session=session)


class StandardPlayback:
    def __init__(self, host):
        import xbmc
        self.host = host
        from lib.services.next_episode_summary import Display
        self.next_display = Display('standard')
        self.next_display.clear()
        self.closed = False
        self.prepared_request = None
        self.prepared_session = None
        self.events = Queue(maxsize=64)
        self.bound = ''
        self.bound_epoch = 0
        self._overflow_lock = Lock()
        self._overflowed = []
        self.last_handoff = None
        self.subtitle_worker = self.subtitle_job = self.subtitle_pending = None
        self.history = HistoryWriter(host.report, profile_root=getattr(host, 'plugin_root', None))
        self.session = StandardSession(getattr(host, 'playback_accounts', host.accounts), history=self.history.save,
            next_loader=self.next_with_subtitle, open_next=self.open_next,
            paused=lambda: xbmc.getCondVisibility('Player.Paused'),
            observer=getattr(host, 'notify_playback_event', None))
        parent = self
        class Player(xbmc.Player):
            def onPlayBackEnded(self):
                parent.event('ENDED')
            def onPlayBackStopped(self):
                parent.event('STOPPED')
            def onPlayBackError(self):
                parent.event('ERROR')
        self.player = Player()
        host.bind_owner(self.dispatch)
        host.playback = self  # Host owns final draining AND the runtime lease.

    def dispatch(self, body):
        if self.closed:
            raise RuntimeError('STANDARD_PLAYBACK_CLOSED')
        operation = body.get('operation')
        if operation == 'select':
            self.clear_subtitle_state()
            from bobbi_platform.prepared_sessions import from_host
            self.prepared_request = body.get('request_id')
            self.prepared_session = from_host(self.host, body.get('account'))
        if operation == 'subtitle_candidate':
            request = body['request_id']
            if self.session.current_request(request) and self.session.current['state'] == 'playing':
                row = self.session.current
                if row.get('subtitle'):
                    return dict(file=row['subtitle']['file'], url=row['data']['url'], request_id=request)
            return {}
        if operation == 'subtitle_start':
            request, data = body['request_id'], body['data']
            if not self.session.current_request(request) or data.get('_account') != self.session.current['account']:
                return {'state': 'stale'}
            self.subtitle_pending = dict(request_id=request, data=deepcopy(data),
                cancel=self.session.current['cancel'], deadline=time.monotonic() + 30)
            self._subtitles()
            return {'state': 'pending'}
        if operation == 'register':
            self._subtitles()
            body = deepcopy(body)
            row = self.session.current
            if row and body['request_id'] == row['request_id'] and row.get('subtitle'):
                if not body['data'].get('subtitles_path') and not body['data'].get('_manual_subtitles'):
                    body['data']['subtitles_path'] = [row['subtitle']['file']]
            result = self.session.dispatch(body)
            if result.get('accepted'):
                result['subtitles_path'] = body['data'].get('subtitles_path', [])
            return result
        result = self.session.dispatch(body)
        self._publish_next_summary()
        return result

    def _publish_next_summary(self):
        try:
            summary = self.session.next_summary()
        except Exception:
            # Presentation has no playback authority. Clear an old caption and
            # keep observing the actual session if its projection is unavailable.
            summary = None
        self.next_display.publish(summary)

    def clear_subtitle_state(self):
        row = self.session.current
        if not row:
            return
        import xbmcgui
        window = xbmcgui.Window(10000)
        if window.getProperty('AM6B.SubtitleStateOwner') == row['request_id']:
            for key in ('AM6B.SubtitleStateOwner', 'AM6B.SubtitleState', 'bobbi.standard.subtitle'):
                window.clearProperty(key)

    def next_with_subtitle(self, current, cancelled):
        accounts = getattr(self.host, 'playback_accounts', None) or self.host.accounts
        guard = lambda: cancelled() or not accounts.is_current(current['_account'])
        prepared = self.prepared_session if self.prepared_request == current.get('request_id') else None
        data = next_data(current, guard, session=prepared)
        if current.get('_continuation_final') or (data and (data.get('_next_transport') == 'bt'
                                                            or data.get('_catalog_next'))):
            # Ready media owns the remaining EOF budget. The existing subtitle
            # worker can discover an optional candidate after this handoff.
            return data if not guard() else None
        if data and not guard() and not data.get('subtitles_path'):
            # Optional IO cannot spend the media handoff's entire remaining
            # lease. Leave one second for publication/submission and keep the
            # original absolute EOF deadline. Slow/missing subtitles can still
            # be discovered by the existing background worker after submission.
            row = self.session.current
            budget = 2.0
            if row and row['terminal'] is not None:
                budget = min(budget, 19 - (self.session.clock() - row['terminal']))
            try:
                candidate = (discover(data, self.host, time.monotonic() + budget, guard)
                             if budget > 0 else None)
                if candidate and not guard():
                    data['subtitles_path'] = [candidate['file']]
            except (OSError, ValueError, RuntimeError):
                pass
        return data if not guard() else None

    def _subtitles(self):
        if self.subtitle_worker and not self.subtitle_worker.is_alive():
            self.subtitle_worker.join()
            job, self.subtitle_job, self.subtitle_worker = self.subtitle_job, None, None
            if (self.session.current_request(job['request_id']) and job.get('result')
                    and time.monotonic() < job['deadline']):
                row = self.session.current
                row['subtitle'] = job['result']
                # A stock player has no atomic user-intent check. Already
                # submitted files keep a late candidate, not an unscoped
                # setSubtitles call that could undo the user's manual Off.
                if row['state'] != 'selected':
                    import xbmcgui
                    window = xbmcgui.Window(10000)
                    window.setProperty('AM6B.SubtitleStateOwner', job['request_id'])
                    window.setProperty('AM6B.SubtitleState', '中文字幕候选已就绪 · 字幕菜单可选择')
                    window.setProperty('bobbi.standard.subtitle', job['result']['file'])
        if self.subtitle_worker is not None or self.subtitle_pending is None:
            return
        job, self.subtitle_pending = self.subtitle_pending, None
        if not self.session.current_request(job['request_id']):
            return
        self.subtitle_job = job
        def work():
            try:
                accounts = getattr(self.host, 'playback_accounts', None) or self.host.accounts
                cancelled = lambda: job['cancel'].is_set() or not accounts.is_current(job['data']['_account'])
                job['result'] = discover(job['data'], self.host, job['deadline'], cancelled)
                if cancelled():
                    job['result'] = None
            except Exception:
                job['result'] = None
        self.subtitle_worker = Thread(target=work, name='bobbi-standard-subtitles', daemon=True)
        self.subtitle_worker.start()

    def event(self, kind):
        # Callback captures the association established by actual AV samples
        # once on entry. Overflow records THIS captured request/epoch for the
        # serial resident tick; a callback thread never retires a newer session.
        request = getattr(self, 'bound', '') or ''
        epoch = getattr(self, 'bound_epoch', 0)
        try:
            self.events.put_nowait((request, epoch, kind))
        except Full:
            if request and not getattr(self, 'closed', False):
                lock = getattr(self, '_overflow_lock', None)
                if lock is None:
                    self._overflow_lock = lock = Lock()
                with lock:
                    overflowed = getattr(self, '_overflowed', None)
                    if overflowed is None:
                        self._overflowed = overflowed = []
                    entry = (request, epoch)
                    if entry not in overflowed:
                        overflowed.append(entry)
                        while len(overflowed) > 16:
                            overflowed.pop(0)
            host = getattr(self, 'host', None)
            if host is not None and hasattr(host, 'report'):
                try:
                    host.report('STANDARD_EVENT_OVERFLOW')
                except Exception:
                    pass

    def open_next(self, data):
        handoff, request = None, None
        try:
            from bobbi_platform.kodi import standard_handoff
            from bobbi_platform.playback import selected_identity
            request = data['request_id']
            if self.player.isPlaying():
                return
            self.clear_subtitle_state()
            self.session.select(request, data['_account'])
            self.prepared_request = request  # Carry the same account/Host binding to its child.
            if not self.session.register(request, data)['accepted']:
                return
            identity = selected_identity(data['url'])
            handoff = standard_handoff(identity, -1, ready=lambda: self.session.current_request(request)
                                      and not self.player.isPlaying())
            result = handoff.submit(identity, data)
            self.last_handoff = dict(request_id=request, status=result['status'])
            if not data.get('subtitles_path') and self.session.current_request(request):
                self.dispatch(dict(operation='subtitle_start', request_id=request, data=data))
        except Exception:
            # The single successor boundary owns this failure, not the host
            # loop. A send with lost/failed acknowledgement is NEVER replayed.
            status = ('submission_unknown' if handoff and handoff.state == 'submission_unknown'
                      else 'before_submission_failed')
            self.last_handoff = dict(request_id=request, status=status)
            if request and self.session.current_request(request):
                self.session.retire(status.upper())
            self.host.report('STANDARD_NEXT_' + status.upper())

    def _consume_overflows(self):
        lock = getattr(self, '_overflow_lock', None)
        if lock is None:
            return
        with lock:
            overflowed = getattr(self, '_overflowed', None)
            if not overflowed:
                return
            pending = list(overflowed)
            overflowed.clear()
        for request, epoch in pending:
            if (request and self.session.current_request(request)
                    and (not epoch or self.session.current['generation'] == epoch)):
                self.session.retire('EVENT_OVERFLOW')

    def tick(self):
        self._subtitles()
        playing = self.player.isPlaying()
        seen_stale = set()
        while True:
            try:
                queued = self.events.get_nowait()
            except Empty:
                break
            if len(queued) == 3:
                request, epoch, kind = queued
            else:
                request, kind = queued
                epoch = 0
            if not request or not self.session.current_request(request):
                seen_stale.add(request)
                continue
            if epoch and self.session.current['generation'] != epoch:
                continue
            self.session.terminal(request, kind, playing)
        self._consume_overflows()
        if playing:
            try:
                from bobbi_platform.standard_subtitle_ui import request_id
                url = self.player.getPlayingFile()
                # Music items need not expose a VideoInfoTag. Read their path
                # without asking a video-only API before checking takeover.
                video = self.player.isPlayingVideo()
                request = request_id(self.player) if video else ''
                if self.session.observe_other(request, url):
                    self.bound = ''
                    self.bound_epoch = 0
                elif video:
                    position, duration = self.player.getTime(), self.player.getTotalTime()
                    if self.session.observe(request, url, position, duration):
                        self.bound = request
                        self.bound_epoch = self.session.current['generation']
            except RuntimeError:
                pass  # Opening/seeking is not evidence of end or error.
        self.session.tick(playing=self.player.isPlaying())
        self._publish_next_summary()
        if self.session.current and not self.session.current_request(self.session.current['request_id']):
            self.clear_subtitle_state()

    def close(self):
        self.closed = True
        self.next_display.clear()
        errors = []
        # Revoke all accepted jobs before any possibly slow drain. Cancellation
        # is not completion; their code must leave before the host releases its
        # replacement lease. Keep attempting cleanup after a component error.
        for job in (self.subtitle_job, self.subtitle_pending):
            if job:
                job['cancel'].set()
        self.subtitle_pending = None
        for close in (self.clear_subtitle_state, self.session.close, self.history.close):
            try:
                close()
            except BaseException as error:
                errors.append(error)
        if self.subtitle_worker:
            try:
                self.subtitle_worker.join()
            except BaseException as error:
                errors.append(error)
        if errors:
            raise errors[0]

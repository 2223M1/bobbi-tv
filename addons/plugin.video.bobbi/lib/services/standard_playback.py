"""Resident standard-Kodi observation and shared cinema policy adapters."""
from copy import deepcopy
from queue import Queue, Empty, Full
from uuid import uuid4
from threading import Event, Thread, Lock
import time

from bobbi_platform.standard_session import StandardSession


class HistoryWriter:
    """Bounded single writer; a slow disk must not stall callbacks or IPC."""
    def __init__(self, report):
        self.queue, self.done, self.report = Queue(maxsize=32), Event(), report
        self.admission = Lock()
        self.accepted = self.completed = self.failed = self.diagnostic_failures = 0
        self.worker_failed = False
        self.worker = Thread(target=self.run, name='bobbi-standard-history', daemon=True)
        self.worker.start()

    def save(self, data):
        with self.admission:
            if self.done.is_set():
                return
            try:
                self.queue.put_nowait(deepcopy(data))
                self.accepted += 1
            except Full:
                self.diagnose('HISTORY_QUEUE_FULL')

    def diagnose(self, code):
        try:
            self.report(code)
        except Exception:
            self.diagnostic_failures += 1

    def run(self):
        while not self.done.is_set() or not self.queue.empty():
            try:
                data = self.queue.get(timeout=.1)
            except Empty:
                continue
            try:
                from lib.utils.general.utils import set_watched_file
                set_watched_file(data)
            except Exception:
                self.failed += 1
                self.diagnose('HISTORY_WRITE_FAILED')
            except BaseException:
                self.worker_failed = True
                self.failed += 1
                self.diagnose('HISTORY_WORKER_FAILED')
                return
            finally:
                self.completed += 1
                self.queue.task_done()

    def close(self):
        with self.admission:
            self.done.set()
        self.worker.join()  # Every accepted history write must finish.
        if self.worker_failed or self.completed != self.accepted or not self.queue.empty():
            raise RuntimeError('HISTORY_DRAIN_INCOMPLETE')


def discover(data, host, deadline, cancelled):
    from lib.services.subtitle_fallback import playback_context, discover_candidate
    from bobbi_core.subtitle_candidates import AssrtCandidates
    from bobbi_core.runtime_paths import ProfilePath
    provider = AssrtCandidates(None, ProfilePath('subtitle-cache283'), accounts=host.accounts)
    return discover_candidate(playback_context(data, None), deadline, cancelled,
                              provider, host.sidecar_candidate)


def resolve_selected(data, cancelled):
    """Reuse verified resolvers without depending on native player receipts."""
    if data.get('_catalog_next'):
        from lib.utils.player.direct_continuity import resolve_direct
        data['url'] = resolve_direct(data, cancelled)
    if data.get('direct_cloud_required') or data.get('direct_cloud_key'):
        from bobbi_core.direct_cloud_client import resolve
        resolved = resolve(data, cancelled)
        if not resolved:
            raise ValueError('SELECTED_CLOUD_FILE_UNAVAILABLE')
        data.update(url=resolved['path'], direct_cloud_key=resolved['key'], size=resolved['bytes'])
        data.pop('direct_cloud_required', None)
    if data.get('prepared_resource_id'):
        from lib.clients.bobi_library import load_prepared_index, local_path
        from bobbi_core.prepared_transport import playback_path
        from bobbi_core.preparation_client import resolve_entry
        snapshot = load_prepared_index()
        entries = [entry for title in snapshot['titles'] for entry in title['sources']
                   if entry['key'] == data['prepared_resource_id']]
        entry = resolve_entry(data, snapshot, entries[0], cancelled) if len(entries) == 1 else None
        if not entry:
            raise ValueError('SELECTED_CLOUD_FILE_CHANGED')
        data.update(url=playback_path(snapshot['mount_root'], entry),
                    source_title=entry['title'], video_context=entry.get('video_context'),
                    subtitles_path=[] if entry.get('_playback_url') else [local_path(snapshot['mount_root'], path)
                                    for path in entry.get('subtitles', [])[:4]])
    if cancelled():
        raise RuntimeError('SELECTION_CANCELLED')
    return data


def next_data(current, cancelled):
    if current.get('file_evidence') == 'USER_CONFIRMED_FILE':
        return None
    from lib.utils.player.direct_continuity import next_direct_data
    from lib.utils.player.continuity import next_cloud_data
    from lib.utils.player.bt_continuity import applies, choose_next, resolve_standard
    try:
        from lib.clients.bobi_library import load_prepared_index
        index = load_prepared_index()
    except (OSError, ValueError, RuntimeError):
        index = {'titles': []}
    data = (choose_next(current, index, cancelled, fresh=bool(current.get('_continuation_final')), fresh_budget=3.0)
            if applies(current) else next_cloud_data(current, index))
    if data is None:
        data, _ = next_direct_data(current, index, cancelled)
    if not data or cancelled():
        return None
    data.update(request_id=uuid4().hex, selection_policy='exact',
                _account=deepcopy(current['_account']), direct_playback_handoff=True)
    if data.get('_next_transport') == 'bt':
        # Keep a proved tuple provisional while the current episode plays.
        # Open the BT transport only after EOF's final cloud-first recheck.
        return resolve_standard(data, cancelled) if current.get('_continuation_final') else data
    if data.get('_next_cloud_verified'):
        return data if not cancelled() else None
    return resolve_selected(data, cancelled)


class StandardPlayback:
    def __init__(self, host):
        import xbmc
        self.host = host
        self.closed = False
        self.events = Queue(maxsize=64)
        self.bound = ''
        self.last_handoff = None
        self.subtitle_worker = self.subtitle_job = self.subtitle_pending = None
        self.history = HistoryWriter(host.report)
        self.session = StandardSession(host.accounts, history=self.history.save,
            next_loader=self.next_with_subtitle, open_next=self.open_next)
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
        return self.session.dispatch(body)

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
        guard = lambda: cancelled() or not self.host.accounts.is_current(current['_account'])
        data = next_data(current, guard)
        if current.get('_continuation_final') or (data and data.get('_next_transport') == 'bt'):
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
                cancelled = lambda: job['cancel'].is_set() or not self.host.accounts.is_current(job['data']['_account'])
                job['result'] = discover(job['data'], self.host, job['deadline'], cancelled)
                if cancelled():
                    job['result'] = None
            except Exception:
                job['result'] = None
        self.subtitle_worker = Thread(target=work, name='bobbi-standard-subtitles', daemon=True)
        self.subtitle_worker.start()

    def event(self, kind):
        # Callback captures the association established by actual AV samples,
        # not whichever pending selection happens to exist when dequeued.
        try:
            self.events.put_nowait((self.bound, kind))
        except Full:
            self.session.retire('EVENT_OVERFLOW')

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

    def tick(self):
        self._subtitles()
        playing = self.player.isPlaying()
        while True:
            try:
                request, kind = self.events.get_nowait()
            except Empty:
                break
            self.session.terminal(request, kind, playing)
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
                elif video:
                    position, duration = self.player.getTime(), self.player.getTotalTime()
                    if self.session.observe(request, url, position, duration):
                        self.bound = request
            except RuntimeError:
                pass  # Opening/seeking is not evidence of end or error.
        self.session.tick(playing=self.player.isPlaying())
        if self.session.current and not self.session.current_request(self.session.current['request_id']):
            self.clear_subtitle_state()

    def close(self):
        self.closed = True
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

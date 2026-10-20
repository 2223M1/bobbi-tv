"""One cancellable, bounded IO worker; native application stays serialized."""
from copy import deepcopy
import re
from threading import Event, Lock, Thread
import time


def playback_context(data, duration):
    ids = data.get('ids') or {}
    tv = data.get('tv_data') or {}
    release = str(data.get('source_title') or data.get('release_title') or '')[:1024]
    title = str(data.get('showtitle') or data.get('title') or '')[:256]
    mode = 'series' if data.get('mode') in ('tv', 'series', 'episode', 'anime') else 'movie'
    year = data.get('year')
    if isinstance(year, str) and re.fullmatch(r'[0-9]{4}', year):
        year = int(year)
    if type(year) is not int or not 1888 <= year <= 2100:
        from bobbi_core.movie_identity import declared_years
        years = declared_years(release, [title])
        year = next(iter(years)) if len(years) == 1 else None
    def number(value):
        return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None
    result = dict(title=title, mode=mode, year=year, release=release, duration=duration,
                imdb=ids.get('imdb_id'), tmdb=number(ids.get('tmdb_id')),
                season=number(tv.get('season')) if mode == 'series' else None,
                episode=number(tv.get('episode')) if mode == 'series' else None)
    if isinstance(data.get('_share'), dict):
        result['_share'] = deepcopy(data['_share'])
    return result


def receipt_key(row):
    return tuple(row.get(k) for k in ('native_instance', 'request_id', 'file_identity',
                                    'url_sha256', 'subtitle_intent', 'subtitle_auto_intent'))


def discover_candidate(context, deadline, cancelled, provider, share_provider=None,
                       torrent_receipt=None, clock=time.monotonic):
    """Shared discovery only. No native receipt creation or Kodi mutations."""
    context = dict(context)
    context.pop('_movie_years', None)
    if context.get('mode') == 'movie':
        from lib.clients.tmdb.movie_years import cached_movie_years
        evidence = cached_movie_years(context.get('tmdb'))
        if evidence is not None:
            context.update(year=evidence.primary_year, _movie_years=evidence)
    candidate = None
    if context.get('_share') and share_provider is not None:
        try:
            candidate = share_provider(context['_share'], context, deadline, cancelled)
        except (ValueError, OSError, RuntimeError):
            if cancelled() or clock() >= deadline:
                raise
    if candidate is None and context.get('_torrent') and torrent_receipt is not None:
        try:
            from bobbi_core.torrent_subtitles import fetch_candidate
            from bobbi_torrent.backend import subtitle_connection
            base, auth = subtitle_connection()
            candidate = fetch_candidate(None, base, auth, context['_torrent'], torrent_receipt,
                context, deadline, cancelled)
        except (ImportError, OSError, ValueError, RuntimeError) as error:
            if hasattr(provider, 'note'):
                from bobbi_core.subtitle_candidates import public_failure_reason
                provider.note('inspect', public_failure_reason(error))
    if candidate is None:
        candidate = provider.candidates(context, deadline, cancelled)
    return candidate


class SubtitleFallback:
    def __init__(self, factory=None, clock=time.monotonic):
        self.factory, self.clock = factory, clock
        self.contexts = {}
        self.key = None
        self.result = None
        self.worker = None
        self.cancel = Event()
        self.lock = Lock()
        self.deadline = 0
        self.torrent = None
        self.share_provider = None
        self.accounts = None

    def candidate_account_current(self, value):
        scope = value.get('account_scope') if isinstance(value, dict) else None
        if scope is None:
            return True
        try:
            return self.accounts is not None and self.accounts.is_current(scope) is True
        except (ValueError, RuntimeError, OSError):
            return False

    def torrent_context(self, request_id, file_identity, metadata):
        from bobbi_core.torrent_subtitles import checked_context
        self.torrent = (request_id, file_identity, checked_context(metadata, file_identity))

    def context(self, row, context):
        from bobbi_core.subtitle_candidates import identity
        try:
            identity(context)
        except (ValueError, TypeError):
            return
        key = receipt_key(row)
        # One bounded context per current instance; a new selection supersedes it.
        context = deepcopy(context)
        if self.torrent and self.torrent[:2] == (row['request_id'], row['file_identity']):
            context['_torrent'] = deepcopy(self.torrent[2])
        self.contexts = {key: context}

    def observe(self, row):
        if self.key is not None and (not row or row.get('phase') != 'AV_STARTED'
                or receipt_key(row) != self.key):
            self.cancel.set()
            self.key = None
            self.result = None

    def close(self):
        self.cancel.set()
        if self.worker is not None:
            # Isolated network I/O observes cancellation every 10ms and is
            # terminated/joined before its owning worker retires.
            self.worker.join(timeout=.3)

    def request(self, row):
        key = receipt_key(row)
        if row.get('subtitle_intent') != row.get('subtitle_auto_intent'):
            self.cancel.set()
            return dict(state='unavailable', reason='MANUAL_PRESERVED')
        with self.lock:
            if self.key == key:
                if self.clock() >= self.deadline and self.result is None:
                    self.cancel.set()
                    return dict(state='unavailable', reason='SUBTITLE_DEADLINE')
                if self.result is not None and not self.candidate_account_current(self.result):
                    return dict(state='unavailable', reason='SUBTITLE_ACCOUNT_CHANGED')
                return deepcopy(self.result) if self.result is not None else dict(state='pending')
            self.cancel.set()
            if self.worker is not None and self.worker.is_alive():
                return dict(state='pending')  # Never accumulate per-selection workers.
            if self.worker is not None:
                self.worker.join()
            context = self.contexts.get(key)
            if context is None:
                return dict(state='unavailable', reason='MEDIA_CONTEXT_MISSING')
            self.key, self.result = key, None
            self.cancel = Event()
            self.deadline = self.clock() + 30
            self.worker = Thread(target=self._run, args=(key, deepcopy(row), context, self.cancel, self.deadline),
                                 name='AM6B-subtitles283', daemon=True)
            self.worker.start()
            return dict(state='pending')

    def _run(self, key, row, context, cancelled, deadline):
        session = None
        provider = None
        try:
            if self.factory:
                provider = self.factory()
            else:
                from bobbi_core.subtitle_candidates import AssrtCandidates
                # HTTP executes in a fresh stdlib Python process, not this
                # interpreter's Requests socket/read or a daemon helper.
                from bobbi_core.runtime_paths import ProfilePath
                provider = AssrtCandidates(None, ProfilePath('subtitle-cache283'), accounts=self.accounts)
            candidate = discover_candidate(context, deadline, cancelled.is_set, provider,
                self.share_provider, row if self.factory is None else None, self.clock)
            answer = dict(state='candidate', file=candidate['file'], origin=candidate.get('origin'),
                          bilingual=candidate.get('bilingual', False), native_instance=row['native_instance'],
                          request_id=row['request_id'], subtitle_intent=row['subtitle_intent'])
            if candidate.get('account_scope') is not None:
                answer['account_scope'] = deepcopy(candidate['account_scope'])
                if not self.candidate_account_current(answer):
                    answer = dict(state='unavailable', reason='SUBTITLE_ACCOUNT_CHANGED')
        except Exception as error:
            # Public reason vocabulary only; provider URLs/tokens never enter logs.
            reason = str(error) if type(error).__name__ == 'LookupStopped' else type(error).__name__
            if not re.fullmatch(r'[A-Z_a-z0-9]{1,80}', reason):
                reason = type(error).__name__
            answer = dict(state='unavailable', reason=reason)
        finally:
            if session:
                session.close()
        with self.lock:
            if self.key == key and not cancelled.is_set() and self.clock() < deadline:
                self.result = answer
                try:
                    import xbmc
                    for event in getattr(provider, 'events', ())[-12:]:
                        xbmc.log('[AM6B subtitles297] stage={stage} candidate={candidate} reason={reason}'.format(**event), xbmc.LOGINFO)
                    xbmc.log('[AM6B subtitles283] ' + answer['state'] + ' ' + answer.get('reason', 'CANDIDATE_NOT_SYNC_PROOF'), xbmc.LOGINFO)
                except ImportError:
                    pass

"""Owner/IO adapter joining headless discovery to the single preparation lane."""
import time
from types import SimpleNamespace

from bobbi_core.discovery_queue import DiscoveryQueue
from bobbi_core.next_discovery import discover


class NextDiscovery:
    def __init__(self, queue, catalog, searcher, metadata_provider, selector, cache, cancelled=lambda: False,
                 playback_active=None, clock=time.monotonic, may_discover=None):
        self.jobs = DiscoveryQueue(queue)
        self.catalog, self.searcher, self.metadata_provider = catalog, searcher, metadata_provider
        self.selector, self.cache, self.cancelled = selector, cache, cancelled
        self.playback_active, self.clock = playback_active, clock
        self.may_discover = may_discover

    def after_intent(self, targets, admitted):
        # Same-pack current+next already has an exact target; no search needed.
        if len(targets) != 1 or len(admitted) != 1:
            return None
        request, _ = targets[0]
        if not request['media_id'].startswith('tmdb:tv:') or request['purpose'] not in ('current', 'manual'):
            return None
        return self.jobs.schedule(admitted[0]['task_id'], request['media_id'], request['version_key'])

    def claim(self): return self.jobs.claim()

    def perform(self, job):
        """IO thread only: no SQLite access. Cache only the winning proved list."""
        next_check, playback_seen = 0.0, False
        def paused():
            nonlocal next_check, playback_seen
            if self.cancelled() or playback_seen:
                return True
            # IO phase boundaries only, never the search socket watchdog or
            # complete()/SQLite owner. An already issued bounded request may
            # finish. Only the exact active source's next may continue;
            # unknown/new/unrelated playback or buffering pauses this job.
            if self.clock() >= next_check:
                if self.may_discover is not None:
                    playback_seen = self.may_discover(job) is not True
                elif self.playback_active is not None:
                    playback_seen = self.playback_active() is not False
                next_check = self.clock() + 1.0
            return playback_seen
        def cancelled():
            return self.cancelled() or playback_seen
        if paused():
            return {'state': 'UNAVAILABLE', 'reason': 'CANCELLED'}
        observed = {}
        def metadata(source, **kwargs):
            if paused(): raise TimeoutError('Playback pauses candidate metadata')
            value = self.cache.load(source)
            if value is None:
                value = self.metadata_provider(source, **kwargs)
            observed[source] = value
            return value
        def search_tv(*args, **kwargs):
            if paused(): raise TimeoutError('Playback pauses next discovery')
            return self.searcher.search_tv(*args, **kwargs)
        result = discover(job, self.catalog.lookup(job['payload']['anchor']['media']), SimpleNamespace(search_tv=search_tv),
                          metadata, self.selector, cancelled)
        if paused():
            return {'state': 'UNAVAILABLE', 'reason': 'CANCELLED', 'evidence': result.get('evidence', {})}
        if result['state'] == 'SOURCE_PROVED_NOT_CLOUD_READY':
            source = result['request']['source_info_hash']
            result['metadata_cached'] = self.cache.store(observed[source])
        return result

    def complete(self, job, result):
        if result.get('state') == 'SOURCE_PROVED_NOT_CLOUD_READY' and not self.cancelled():
            return self.jobs.accept(job['id'], job['nonce'], result['request'], result['selection'])
        return self.jobs.defer(job['id'], job['nonce'], 'CANCELLED' if self.cancelled() else result['reason'])

    def failed(self, job):
        return self.jobs.defer(job['id'], job['nonce'], 'DISCOVERY_IO_FAILED')

"""One bounded source-list subscription, independent of the playback authority.

Workers publish copies. Only the existing window loop renders snapshots. A
visible card is identified by a stable key, never by an old list ordinal.
"""
from copy import deepcopy
from hashlib import sha256
import json
from threading import RLock
from uuid import uuid4

from bobbi_core.playback_request import source_identity


class SourceListSession:
    TERMINAL = {'COMPLETE', 'PARTIAL', 'FAILED', 'TIMEOUT', 'CANCELLED'}

    def __init__(self, media, rank, limit=100, capacity=2048):
        if not 1 <= limit <= capacity <= 4096:
            raise ValueError('Bounded candidate and visible budgets required')
        self.media = json.dumps(media, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        self.epoch = uuid4().hex
        self.rank, self.limit, self.capacity = rank, limit, capacity
        self.lock = RLock()
        self.entries, self.providers = {}, {}
        self.revision = 0
        self.cancelled = False
        self.focus_key = None
        self.focus_position = 0
        self.confirmed = None
        self.metadata = {}

    def key(self, source):
        metadata = getattr(source, 'stremioMetadata', {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        # Without a verified BT/cloud exact-file mapping these stay separate.
        # Identical URLs or paths never establish cross-transport equivalence.
        identity = dict(media=self.media, release=source_identity(source),
                        transport=(getattr(source, 'preparedResourceId', '') or
                                   getattr(source, 'debridType', '') or 'unprepared'),
                        file_index=metadata.get('fileIdx'), file_path=metadata.get('filename'))
        return sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False).encode('utf-8')).hexdigest()

    def publish(self, epoch, provider, sources=(), state='COMPLETE', error='', completion=None):
        if state not in self.TERMINAL | {'PENDING', 'RUNNING'}:
            raise ValueError('Explicit provider lifecycle required')
        if completion is not None:
            from dataclasses import asdict
            from bobbi_core.search_completion import SearchCompletion
            if not isinstance(completion, SearchCompletion):
                raise ValueError('Explicit provider completion receipt required')
        copies = [(self.key(source), deepcopy(source)) for source in sources]
        with self.lock:
            if epoch != self.epoch or self.cancelled or self.confirmed:
                return False
            if self.providers.get(provider, {}).get('state') in self.TERMINAL:
                return False  # A timed-out producer cannot revive its subscription.
            if len(self.entries.keys() | {key for key, _ in copies}) > self.capacity:
                copies, state, error = [], 'FAILED', 'CANDIDATE_CAPACITY_EXCEEDED'
            for key, source in copies:
                retained = self.entries.setdefault(key, source)
                if getattr(source, 'requiresCatalogEpisodeProof', False):
                    retained.requiresCatalogEpisodeProof = True
            previous_completion = self.providers.get(provider, {}).get('completion')
            self.providers[provider] = dict(state=state, error=str(error)[:120], count=len(copies))
            if completion is not None:
                self.providers[provider]['completion'] = asdict(completion)
            elif previous_completion is not None:
                # Forced timeout/cancellation must not erase the already
                # published snapshot age/incompleteness evidence.
                self.providers[provider]['completion'] = previous_completion
            self.revision += 1
            return True

    def focus(self, key, position):
        with self.lock:
            if key in self.entries and not self.cancelled and not self.confirmed:
                self.focus_key, self.focus_position = key, max(0, int(position))

    def capture(self, epoch, key):
        with self.lock:
            if epoch != self.epoch or self.cancelled or self.confirmed or key not in self.entries:
                return None
            # A newer provider may supersede a card already rendered by the
            # GUI. Never resolve that stale key or silently substitute a file.
            if key not in {self.key(source) for source in self.rank(list(self.entries.values()))}:
                return None
            self.confirmed = key
            self.revision += 1
            return deepcopy(self.entries[key])

    def inspect(self, epoch, key):
        """Read one card for an explicit advanced action without claiming playback."""
        with self.lock:
            if epoch != self.epoch or self.cancelled or key not in self.entries:
                return None
            if key not in {self.key(source) for source in self.rank(list(self.entries.values()))}:
                return None
            return deepcopy(self.entries[key])

    def reopen(self):
        with self.lock:
            if not self.cancelled:
                self.confirmed = None
                self.revision += 1

    def invalidate_share(self, epoch, source):
        """Downgrade only the captured exact card; do not remove any candidate."""
        key = self.key(source)
        with self.lock:
            retained = self.entries.get(key)
            fields = ('url', 'guid', 'title', 'size', 'indexer', 'type')
            if (epoch != self.epoch or self.cancelled or self.confirmed != key or retained is None
                    or any(getattr(retained, name, None) != getattr(source, name, None) for name in fields)):
                return False
            retained.verifiedShareFile = False
            self.revision += 1
            return True

    def cancel(self):
        with self.lock:
            self.cancelled = True
            self.stop_queries()

    def stop_queries(self):
        with self.lock:
            for record in self.providers.values():
                if record['state'] not in self.TERMINAL:
                    record['state'] = 'CANCELLED'
            self.revision += 1

    def snapshot(self, full=False):
        with self.lock:
            # Rank the complete bounded set before the display cap.
            ranked = self.rank(list(self.entries.values()))
            recommended = self.key(ranked[0]) if ranked else None
            cap = self.capacity if full else self.limit
            visible = ranked[:cap]
            eligible_keys = {self.key(source) for source in ranked}
            if self.focus_key in eligible_keys:
                focused = self.entries[self.focus_key]
                visible = [source for source in visible if self.key(source) != self.focus_key]
                visible.insert(min(self.focus_position, len(visible)), focused)
                visible = visible[:cap]
            return deepcopy(dict(epoch=self.epoch, revision=self.revision, cancelled=self.cancelled,
                providers=self.providers, metadata=self.metadata, recommended_key=recommended,
                superseded_count=len(self.entries) - len(ranked),
                entries=[(self.key(source), source) for source in visible]))

    def status(self):
        with self.lock:
            return deepcopy(dict(revision=self.revision, providers=self.providers,
                                 cancelled=self.cancelled, confirmed=self.confirmed))

    def set_metadata(self, metadata):
        with self.lock:
            if not self.cancelled and not self.confirmed:
                self.metadata = deepcopy(metadata)
                self.revision += 1

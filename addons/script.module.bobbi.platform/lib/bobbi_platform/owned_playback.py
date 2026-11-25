"""Unified platform-to-owner playback admission adapter (R08 / PB-01).

Lives strictly in bobbi_platform with zero reverse imports into plugin.video.bobbi.
Routes reserve -> resolve -> register/bind -> handoff -> scoped cancel through the
single resident Host playback owner (standard or native).
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

import inspect

from bobbi_core.next_episode_summary import NextResolution
from bobbi_core.playback_request import (
    SelectionChanged,
    bind_and_claim,
    context,
)
from .kodi import make_item
from .playback import Handoff, check_media, selected_identity
from .playback_client import capture_transport


_NEXT_RESOLVERS: dict = {}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def next_selection_locator(candidate: dict) -> str:
    meta = candidate.get('_owned_source') if isinstance(candidate, dict) else None
    if isinstance(meta, dict) and meta.get('source_id') and meta.get('item_id'):
        provider = str(meta.get('provider') or 'owned')
        mid = str(meta.get('media_source_id') or '')
        base = f"{provider}-next://{meta['source_id']}/{meta['item_id']}"
        return f"{base}/{mid}" if mid else base
    raw_url = str((candidate or {}).get('url') or '').partition('|')[0]
    if not raw_url:
        raise ValueError('OWNED_NEXT_LOCATOR_MISSING')
    return raw_url


def next_selection_identity(candidate: dict) -> str:
    return 'transport:' + _sha256(next_selection_locator(candidate))


def register_next_resolver(name: str, fn) -> None:
    _NEXT_RESOLVERS[name] = fn


def _coerce_next_resolution(raw, cancelled) -> NextResolution:
    if isinstance(raw, NextResolution):
        return raw
    if isinstance(raw, dict):
        return NextResolution('candidate', candidate=raw)
    if cancelled():
        return NextResolution('cancelled')
    return NextResolution('error', detail='unresolved')


def resolve_owned_next_result(
    current: dict,
    spec: dict,
    cancelled,
    *,
    open_session: bool = True,
) -> NextResolution:
    if cancelled():
        return NextResolution('cancelled')
    if resolve_owned_next is not _default_resolve_owned_next:
        return _coerce_next_resolution(resolve_owned_next(current, spec, cancelled), cancelled)
    fn = _NEXT_RESOLVERS.get(spec.get('resolver')) if isinstance(spec, dict) else None
    if fn is None:
        return NextResolution('error', detail='unknown_resolver')
    try:
        sig = inspect.signature(fn)
        accepts_open = 'open_session' in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except (TypeError, ValueError):
        accepts_open = False
    raw = fn(current, spec, cancelled, open_session=open_session) if accepts_open else fn(current, spec, cancelled)
    return _coerce_next_resolution(raw, cancelled)


def _default_resolve_owned_next(current: dict, spec: dict, cancelled) -> dict | None:
    res = resolve_owned_next_result(current, spec, cancelled, open_session=True)
    return res.candidate if res.outcome == 'candidate' else None


resolve_owned_next = _default_resolve_owned_next


def library_source_scope(source_id: str, generation: str) -> dict:
    """Account-equivalent scope bound to a Registry source and its exact generation."""
    if (
        not isinstance(source_id, str)
        or not re.fullmatch(r'[0-9a-f]{32}', source_id)
        or not isinstance(generation, str)
        or not re.fullmatch(r'[0-9a-f]{64}', generation)
    ):
        raise ValueError('OWNED_SOURCE_SCOPE_INVALID')
    return {
        'kind': 'library_source',
        'source_id': source_id,
        'generation': generation,
    }


def emby_source_scope(
    *,
    source_id: str,
    generation: str,
    server_id: str,
    user_id: str,
) -> dict:
    """Playback scope bound to a specific Emby connection without global browse switching."""
    if (
        not isinstance(source_id, str)
        or not re.fullmatch(r'[0-9a-f]{32}', source_id)
        or not isinstance(generation, str)
        or not re.fullmatch(r'[0-9a-f]{64}', generation)
        or not isinstance(server_id, str)
        or not server_id
        or not isinstance(user_id, str)
        or not user_id
    ):
        raise ValueError('OWNED_EMBY_SCOPE_INVALID')
    return {
        'kind': 'emby_source',
        'provider': 'emby',
        'server_id': server_id,
        'user_id': user_id,
        'source_id': source_id,
        'generation': generation,
    }


def validate_owned_source_meta(meta: dict | None) -> dict:
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise ValueError('OWNED_SOURCE_META_INVALID')
    allowed = {
        'provider',
        'server_id',
        'user_id',
        'source_id',
        'source_generation',
        'item_id',
        'media_source_id',
        'play_session_id',
        'identity_mode',
        'initial_ticks',
        'initial_played',
        'handoff_monotonic',
    }
    if set(meta) - allowed:
        raise ValueError('OWNED_SOURCE_META_INVALID')
    cleaned = {}
    for k, v in meta.items():
        if v is None:
            continue
        if not isinstance(v, str) or len(v) > 256 or any(ord(c) < 32 for c in v):
            raise ValueError('OWNED_SOURCE_META_INVALID')
        cleaned[k] = v
    return cleaned


class OwnedPlaybackReservation:
    """Single user-intent playback reservation owned by Host."""

    def __init__(
        self,
        *,
        binding,
        playback_client,
        host_call,
        adapter: str,
        request_id: str,
        selection_identity: str,
        account_scope: dict,
        owner_context: dict | None = None,
    ):
        self.binding = binding
        self.playback_client = playback_client
        self.host_call = host_call
        self.adapter = adapter
        self.request_id = request_id
        self.selection_identity = selection_identity
        self.account_scope = deepcopy(account_scope)
        self.owner_context = deepcopy(owner_context) if owner_context else None
        self.submitted = False
        self.cancelled = False

    @classmethod
    def from_child_reservation(
        cls,
        *,
        reserved_snapshot: dict,
        child_request_id: str,
        selection_identity: str,
        account_scope: dict,
        playback_client,
        host_call,
        binding=None,
    ) -> OwnedPlaybackReservation:
        if not isinstance(child_request_id, str) or not re.fullmatch(r'[0-9a-f]{32}', child_request_id):
            raise ValueError('OWNED_REQUEST_ID_INVALID')
        owner_ctx = context(reserved_snapshot, child_request_id)
        return cls(
            binding=binding,
            playback_client=playback_client,
            host_call=host_call,
            adapter='native',
            request_id=child_request_id,
            selection_identity=selection_identity,
            account_scope=account_scope,
            owner_context=owner_ctx,
        )

    def is_current(self) -> bool:
        if self.cancelled:
            return False
        if self.binding is not None and not self.binding.is_current():
            return False
        try:
            if self.adapter == 'native':
                self.playback_client.owned_state(self.request_id, self.owner_context)
                return True
            if self.adapter == 'standard':
                reply = self.host_call(
                    'standard_playback',
                    {'operation': 'current', 'request_id': self.request_id},
                )
                return isinstance(reply, dict) and reply.get('current') is True
            reply = self.host_call(
                'owned_playback_current',
                {'request_id': self.request_id},
            )
            return isinstance(reply, dict) and reply.get('current') is True
        except (SelectionChanged, OSError, ValueError, RuntimeError):
            return False

    def require_current(self) -> None:
        if not self.is_current():
            raise SelectionChanged('PLAYBACK_SELECTION_SUPERSEDED')

    def build_data(
        self,
        url: str,
        *,
        title: str,
        source_meta: dict | None = None,
        info: dict | None = None,
        art: dict | None = None,
        mime: str | None = None,
        resume_offset: float | int = 0,
        start_over: bool = False,
        subtitles: list[str] | None = None,
        next_candidate: dict | None = None,
    ) -> dict:
        raw_url = url.partition('|')[0]
        check_media({'url': raw_url})
        meta = validate_owned_source_meta(source_meta)
        if meta.get('provider') == 'emby' and 'handoff_monotonic' not in meta:
            meta['handoff_monotonic'] = f'{time.monotonic():.3f}'
        info_dict = dict(info or {})
        art_dict = dict(art or {})
        data: dict = {
            'request_id': self.request_id,
            '_ui_reserved_request': self.request_id,
            '_account': deepcopy(self.account_scope),
            'url': url,
            'title': title,
            'source_title': title,
            'selection_policy': 'exact',
            'direct_playback_handoff': True,
            'file_evidence': 'AUTO_VERIFIED_FILE' if next_candidate else 'USER_CONFIRMED_FILE',
            '_owned_source': meta,
        }
        if info_dict:
            data['video_info'] = deepcopy(info_dict)
            if isinstance(info_dict.get('season'), int) or isinstance(info_dict.get('episode'), int):
                data['tv_data'] = {
                    k: info_dict[k]
                    for k in ('season', 'episode')
                    if isinstance(info_dict.get(k), int) and info_dict[k] >= 0
                }
        for key in ('poster', 'fanart', 'thumb'):
            if isinstance(art_dict.get(key), str) and art_dict[key]:
                data[key] = art_dict[key]
        if isinstance(mime, str) and mime:
            data['mime'] = mime
        if subtitles:
            data['subtitles_path'] = list(subtitles[:4])
        if next_candidate is not None:
            data['_owned_next'] = deepcopy(next_candidate)
            if (
                next_candidate.get('resolver') == 'emby_same_season'
                and isinstance(next_candidate.get('season_id'), str)
            ):
                import hashlib
                data['mode'] = 'tv'
                data['_emby_season_ref'] = hashlib.sha256(
                    f"{meta.get('source_id', '')}:{next_candidate['season_id']}".encode('utf-8')
                ).hexdigest()[:16]
        if start_over or not resume_offset or resume_offset <= 0:
            data['_bobbi_start_over'] = True
            data['_resume_offset_seconds'] = 0
        else:
            if type(resume_offset) not in (int, float) or not (0 < resume_offset <= 864000):
                raise ValueError('OWNED_RESUME_OFFSET_INVALID')
            data['_resume_offset_seconds'] = float(resume_offset)
        return data

    def submit(
        self,
        handle: int,
        url: str,
        *,
        title: str,
        source_meta: dict | None = None,
        info: dict | None = None,
        art: dict | None = None,
        mime: str | None = None,
        resume_offset: float | int = 0,
        start_over: bool = False,
        subtitles: list[str] | None = None,
        next_candidate: dict | None = None,
        ready=None,
        resolve_fn=None,
        play_fn=None,
        item_factory=make_item,
    ) -> dict:
        if self.cancelled or self.submitted:
            raise SelectionChanged('PLAYBACK_RESERVATION_CLOSED')
        if self.binding is not None:
            self.binding.require_current()
        if ready is not None and not ready():
            self.cancel()
            raise SelectionChanged('PLAYBACK_NOT_READY')

        data = self.build_data(
            url,
            title=title,
            source_meta=source_meta,
            info=info,
            art=art,
            mime=mime,
            resume_offset=resume_offset,
            start_over=start_over,
            subtitles=subtitles,
            next_candidate=next_candidate,
        )
        raw_url = url.partition('|')[0]
        handoff_id = selected_identity(f'{self.request_id}\n{raw_url}')

        if self.adapter == 'native':
            route = 'resolved_url' if handle >= 0 else 'player_play'
            file_identity = f'{self.selection_identity}|{_sha256(raw_url)}'
            # Native C++ VideoPlayer hashes file.GetDynPath() (full url including pipe options).
            claim = bind_and_claim(
                self.request_id,
                file_identity,
                url,
                lambda: self.cancelled or (ready is not None and not ready()),
                route,
                file_evidence=data['file_evidence'],
                owner_call=self.playback_client.call,
            )
            data['_owner_claim'] = claim
            self.host_call(
                'owned_playback_track',
                {'request_id': self.request_id, 'account': deepcopy(self.account_scope), 'data': deepcopy(data)},
            )
        elif self.adapter == 'standard':
            reg = self.host_call(
                'standard_playback',
                {'operation': 'register', 'request_id': self.request_id, 'data': data},
            )
            if not isinstance(reg, dict) or reg.get('accepted') is not True:
                raise SelectionChanged('STANDARD_REGISTRATION_REJECTED')
            if reg.get('subtitles_path'):
                data['subtitles_path'] = reg['subtitles_path']
        else:
            self.host_call(
                'owned_playback_track',
                {'request_id': self.request_id, 'account': deepcopy(self.account_scope), 'data': deepcopy(data)},
            )

        if resolve_fn is None or play_fn is None:
            import xbmc
            import xbmcplugin
            resolve_fn = resolve_fn or xbmcplugin.setResolvedUrl
            play_fn = play_fn or xbmc.Player().play

        def check_ready() -> bool:
            if self.cancelled:
                return False
            if self.binding is not None and not self.binding.is_current():
                return False
            if ready is not None and not ready():
                return False
            if self.adapter == 'standard':
                cur = self.host_call(
                    'standard_playback',
                    {'operation': 'current', 'request_id': self.request_id},
                )
                return isinstance(cur, dict) and cur.get('current') is True
            if self.adapter == 'starting':
                cur = self.host_call(
                    'owned_playback_current',
                    {'request_id': self.request_id},
                )
                return isinstance(cur, dict) and cur.get('current') is True
            return True

        handoff = Handoff(handoff_id, handle, resolve_fn, play_fn, item_factory, check_ready)
        outcome = handoff.submit(handoff_id, data)
        if not outcome.get('opened'):
            self.cancel()
            raise SelectionChanged('HANDOFF_CANCELLED')
        self.submitted = True
        return {
            'opened': True,
            'request_id': self.request_id,
            'adapter': self.adapter,
            'evidence': outcome.get('evidence', 'handoff'),
        }

    def cancel(self) -> None:
        if self.submitted or self.cancelled:
            return
        self.cancelled = True
        try:
            if self.adapter == 'native' and self.owner_context is not None:
                self.playback_client.call(dict(self.owner_context, operation='cancel'))
            elif self.adapter == 'standard':
                self.host_call(
                    'standard_playback',
                    {'operation': 'cancel', 'request_id': self.request_id},
                )
            else:
                self.host_call(
                    'owned_playback_cancel',
                    {'request_id': self.request_id},
                )
        except (OSError, ValueError, RuntimeError):
            pass

    def __enter__(self) -> OwnedPlaybackReservation:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.submitted:
            self.cancel()
        return False


def reserve_playback(
    selection_locator: str,
    account_scope: dict,
    *,
    binding=None,
    transport=None,
    request_id: str | None = None,
    allow_starting: bool = False,
) -> OwnedPlaybackReservation:
    """Step 1: Reserve request_id/epoch on Host BEFORE slow remote resolution."""
    if not isinstance(selection_locator, str) or not selection_locator:
        raise ValueError('OWNED_SELECTION_LOCATOR_REQUIRED')
    active_transport = transport if transport is not None else capture_transport(binding=binding)
    bound_profile, playback_client, host_call = active_transport
    status = host_call('status', {}, timeout=1.5)
    adapter = status.get('playback_adapter') if isinstance(status, dict) else None
    allowed_adapters = ('native', 'standard', 'starting') if allow_starting else ('native', 'standard')
    if adapter not in allowed_adapters:
        raise RuntimeError('PLAYBACK_ADAPTER_UNAVAILABLE')

    req_id = request_id or uuid4().hex
    if not isinstance(req_id, str) or not re.fullmatch(r'[0-9a-f]{32}', req_id):
        raise ValueError('OWNED_REQUEST_ID_INVALID')
    sel_identity = 'transport:' + _sha256(selection_locator)

    owner_ctx = None
    if adapter == 'native':
        snapshot = playback_client.read_snapshot()
        accepted = playback_client.select(
            snapshot,
            req_id,
            sel_identity,
            account_scope=deepcopy(account_scope),
        )
        owner_ctx = context(accepted, req_id)
    elif adapter == 'standard':
        host_call(
            'standard_playback',
            {'operation': 'select', 'request_id': req_id, 'account': deepcopy(account_scope)},
        )
    else:
        host_call(
            'owned_playback_reserve',
            {'request_id': req_id, 'account': deepcopy(account_scope)},
        )

    return OwnedPlaybackReservation(
        binding=bound_profile,
        playback_client=playback_client,
        host_call=host_call,
        adapter=adapter,
        request_id=req_id,
        selection_identity=sel_identity,
        account_scope=account_scope,
        owner_context=owner_ctx,
    )


class OwnedNextCoordinator:
    """Host-owned lifecycle for native next-episode summary prefetch and continuation probes.

    Tracks every background worker with explicit per-job cancellation so Host.close()
    can cancel and drain all in-flight next-episode work before releasing runtime.lease.
    """

    def __init__(self, *, stopping=None, profile_current=None):
        from threading import Event, Lock
        self._stopping = stopping
        self._profile_current = profile_current or (lambda: True)
        self._lock = Lock()
        self._closed = False
        self._jobs = {}
        self._seq = 0
        self._drained_total = 0

    def _is_stopping(self) -> bool:
        return bool(
            self._closed
            or (self._stopping is not None and self._stopping.is_set())
            or not self._profile_current()
        )

    def has_active_kind(self, kind: str) -> bool:
        with self._lock:
            dead = [jid for jid, row in self._jobs.items() if not row['thread'].is_alive()]
            for jid in dead:
                self._jobs.pop(jid, None)
                self._drained_total += 1
            return any(row['kind'] == kind and row['thread'].is_alive() for row in self._jobs.values())

    def submit(self, kind: str, fn, *, singleton: bool = False) -> bool:
        from threading import Event, Thread
        with self._lock:
            if self._is_stopping():
                return False
            dead = [jid for jid, row in self._jobs.items() if not row['thread'].is_alive()]
            for jid in dead:
                self._jobs.pop(jid, None)
                self._drained_total += 1
            if singleton and any(row['kind'] == kind and row['thread'].is_alive() for row in self._jobs.values()):
                return False
            self._seq += 1
            job_id = self._seq
            cancel_event = Event()

            def _cancelled() -> bool:
                return cancel_event.is_set() or self._is_stopping()

            def _runner():
                try:
                    if not _cancelled():
                        fn(_cancelled)
                finally:
                    with self._lock:
                        if self._jobs.pop(job_id, None) is not None:
                            self._drained_total += 1

            worker = Thread(target=_runner, name=f'bobbi-owned-next-{kind}-{job_id}', daemon=True)
            self._jobs[job_id] = {'kind': kind, 'cancel': cancel_event, 'thread': worker}
            worker.start()
            return True

    def cancel_all(self) -> int:
        with self._lock:
            items = list(self._jobs.values())
        for row in items:
            row['cancel'].set()
        return len(items)

    def wait_idle(self, timeout: float = 1.0) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            with self._lock:
                workers = [row['thread'] for row in self._jobs.values() if row['thread'].is_alive()]
            if not workers:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            workers[0].join(min(remaining, 0.05))

    def snapshot(self) -> dict:
        with self._lock:
            active = [row['kind'] for row in self._jobs.values() if row['thread'].is_alive()]
            return {
                'closed': self._closed,
                'active_count': len(active),
                'active_kinds': tuple(active),
                'drained_total': self._drained_total,
            }

    def close(self, timeout: float = 5.0) -> bool:
        with self._lock:
            self._closed = True
            items = list(self._jobs.values())
        for row in items:
            row['cancel'].set()
        deadline = time.monotonic() + max(0.0, float(timeout))
        for row in items:
            worker = row['thread']
            if worker.is_alive():
                remaining = max(0.0, deadline - time.monotonic())
                worker.join(remaining)
        with self._lock:
            dead = [jid for jid, row in self._jobs.items() if not row['thread'].is_alive()]
            for jid in dead:
                self._jobs.pop(jid, None)
                self._drained_total += 1
            still_alive = any(row['thread'].is_alive() for row in self._jobs.values())
        return not still_alive

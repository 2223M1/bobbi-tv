"""Real owner waits and resolver deadline races, no Kodi or device IO."""
import json
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from test_bobbi_torrent_adapter import RID, HASH, request, status, config
from bobbi_torrent.owner import Owner
from bobbi_torrent.backend import BackendError
from bobbi_torrent.resolver import Resolver
from bobbi_torrent import resolver as resolver_module


@pytest.fixture
def owner():
    state = SimpleNamespace(waits=[], reads=[], aborted=False, waited_abort=False,
        properties={'bobbi_active_player_session': RID}, after_wait=None, owner_error=False)
    def owned(request_id):
        state.reads.append(request_id)
        if state.owner_error:
            raise RuntimeError('synthetic superseded owner')
        return {'desired': {'request_id': request_id}}
    def wait(seconds):
        assert seconds > 0, 'Kodi would wait indefinitely for a non-positive timeout'
        state.waits.append(seconds)
        if state.after_wait: state.after_wait()
        return state.waited_abort
    state.value = Owner(RID, SimpleNamespace(owned_state=owned),
        SimpleNamespace(getProperty=lambda key: state.properties.get(key, '')),
        SimpleNamespace(abortRequested=lambda: state.aborted, waitForAbort=wait))
    return state


@pytest.mark.parametrize('seconds', [0, 0.0, -0.0, -1, -100.5])
def test_nonpositive_wait_only_checks_existing_owner(owner, seconds):
    assert owner.value.wait(seconds) is None
    assert owner.waits == [] and owner.reads == [RID]


@pytest.mark.parametrize('seconds', [None, True, False, '0', float('nan'), float('inf'), -float('inf'), 10**1000])
def test_invalid_or_nonfinite_wait_never_reaches_kodi(owner, seconds):
    with pytest.raises(BackendError) as raised:
        owner.value.wait(seconds)
    assert raised.value.code == 'TORRENT_WAIT_INVALID' and raised.value.category == 'invalid_request'
    assert owner.waits == [] and owner.reads == []


@pytest.mark.parametrize('seconds', [.00001, .1, .5, 1])
def test_positive_timeout_is_unchanged_and_still_rechecks_owner(owner, seconds):
    owner.value.wait(seconds)
    assert owner.waits == [seconds] and owner.reads == [RID]


@pytest.mark.parametrize('signal,category', [('abort', 'aborted'), ('cancel', 'cancelled'),
                                            ('new_request', 'superseded'), ('owner', 'superseded')])
@pytest.mark.parametrize('seconds', [0, .5])
def test_nonpositive_and_post_positive_wait_still_obey_cancellation_and_ownership(owner, signal, category, seconds):
    def change():
        if signal == 'abort': owner.aborted = True
        elif signal == 'cancel': owner.properties['bobbi_cinema_cancel'] = RID
        elif signal == 'new_request': owner.properties['bobbi_active_player_session'] = 'b' * 32
        else: owner.owner_error = True
    if seconds == 0: change()
    else: owner.after_wait = change
    with pytest.raises(BackendError) as raised:
        owner.value.wait(seconds)
    assert raised.value.category == category and owner.waits == ([] if seconds == 0 else [.5])


def test_real_monitor_abort_during_positive_wait_keeps_original_abort_result(owner):
    owner.waited_abort = True
    with pytest.raises(BackendError) as raised:
        owner.value.wait(.5)
    assert raised.value.category == 'aborted' and owner.waits == [.5] and not owner.reads


@pytest.mark.parametrize('stage', ['metadata', 'buffer_progress', 'buffer_retry'])
def test_actual_resolver_deadline_crossing_returns_timeout_not_infinite_kodi_wait(monkeypatch, stage):
    class Clock:
        def __init__(self): self.now, self.pending = 0., []
        def __call__(self):
            if self.pending: self.now = self.pending.pop(0)
            return self.now
    clock, abort, done = Clock(), Event(), Event()
    waits, errors, progress = [], [], []
    properties = {'bobbi_active_player_session': RID}
    def set_property(key, value):
        properties[key] = value
        if key == 'bobbi_cinema_progress':
            progress.append(json.loads(value)['phase'])
            if stage == 'buffer_progress' and progress.count('buffering') == 2:
                clock.now = 2.01
    def wait(seconds):
        waits.append(seconds)
        if seconds <= 0:
            return abort.wait()  # Exact Kodi zero-timeout semantics; finally prevents orphan test workers.
        clock.now += seconds
        return abort.is_set()
    protocol = SimpleNamespace(owned_state=lambda rid: {'desired': {'request_id': rid}},
        resolve_torrent=lambda rid, locator, source_hash, verified: dict(selection_identity='bt:' + HASH, info_hash=HASH),
        validate_torrent_resolution=lambda *args: 'bt:' + HASH)
    actual = Owner(RID, protocol,
        SimpleNamespace(getProperty=lambda key: properties.get(key, ''), setProperty=set_property),
        SimpleNamespace(abortRequested=abort.is_set, waitForAbort=wait))
    prompts = []
    actual.wait_for_buffer = lambda detail: prompts.append(detail) or False
    class Backend:
        config = config()
        count = 0
        def ready(self, active): active()
        def add(self, *args): args[-1]()
        def preload(self, *args): args[-1]()
        def status(self, info_hash, deadline, active):
            active()
            self.count += 1
            if stage == 'metadata':
                clock.now = 1.999
                return {'hash': HASH, 'file_stats': []}
            if self.count == 1: return status(ready=False)
            if stage == 'buffer_retry':
                clock.pending = [1.999, 2.01]
                raise BackendError('TORRENT_HTTP_TIMEOUT')
            return status(ready=False)
    if stage == 'metadata':
        original = resolver_module.metadata_files
        def metadata(value):
            result = original(value)
            clock.now = 2.01
            return result
        monkeypatch.setattr(resolver_module, 'metadata_files', metadata)
    resolver = Resolver(Backend(), actual, SimpleNamespace(), clock)
    def run():
        try: resolver.resolve(request())
        except Exception as error: errors.append(error)
        finally: done.set()
    worker = Thread(target=run)
    worker.start()
    try:
        assert done.wait(.5), 'Resolver entered the zero-duration unbounded wait'
        assert not any(seconds <= 0 for seconds in waits)
        assert len(errors) == 1 and isinstance(errors[0], BackendError)
        assert errors[0].category == ('metadata_timeout' if stage == 'metadata' else 'buffer_timeout')
        assert len(prompts) == (0 if stage == 'metadata' else 1)
    finally:
        abort.set()
        worker.join(1)
        assert not worker.is_alive()

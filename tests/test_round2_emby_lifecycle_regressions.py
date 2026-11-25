"""Second-round real reporter/hub regressions absent from the U01-U05 suite."""
from contextlib import nullcontext
from threading import Event
from types import SimpleNamespace

import pytest

from bobbi_platform import emby_session as mod
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.standard_session import StandardSession


def _event(kind, position=10.0):
    return {
        'event': kind, 'request_id': 'a' * 32, 'position': position,
        'duration': 3600.0, 'observed_clock': True, 'reason': 'STOP',
        'data': {'_owned_source': {
            'provider': 'emby', 'source_id': 'b' * 32,
            'source_generation': 'c' * 64, 'server_id': 'server',
            'user_id': 'user', 'item_id': 'item', 'media_source_id': 'media',
        }},
    }


def test_progress_storage_retry_waits_and_retains_latest_position(tmp_path):
    clock = [100.0]
    blocked = [False]
    blocked_calls = []
    sent = []
    client = SimpleNamespace(session=SimpleNamespace(
        budget=lambda *_: nullcontext(),
        request=lambda path, **kw: sent.append((path, kw['data']['PositionTicks'])),
    ))

    def load(*_args):
        if blocked[0]:
            blocked_calls.append(clock[0])
            # A second attempt in the same synchronous drain demonstrates the
            # original unbounded retry without hanging the test process.
            if blocked_calls.count(clock[0]) > 1:
                raise AssertionError('storage failure retried without backoff')
            raise PanError('PAN_STORAGE_UNAVAILABLE')
        return client, {'server_id': 'server', 'user_id': 'user'}

    hub = mod.EmbyInvalidationHub(tmp_path, clock=lambda: clock[0])
    reporter = mod.EmbySessionReporter(tmp_path, hub, client_loader=load,
                                       clock=lambda: clock[0], start_worker=False)
    try:
        assert reporter.on_playback_event(_event('AV_START'))
        reporter.drain_once(flush_pending=False)
        blocked[0] = True
        assert reporter.on_playback_event(_event('PROGRESS', 20))
        assert reporter.drain_once(flush_pending=False) == 1
        assert blocked_calls == [100.0]
        # New positions coalesce during the storage backoff, without wake spam.
        assert reporter.on_playback_event(_event('PROGRESS', 30))
        assert reporter.drain_once(flush_pending=False) == 0
        blocked[0] = False
        clock[0] += 1
        assert reporter.drain_once(flush_pending=False) == 1
        assert sent == [('/Sessions/Playing', 100000000),
                        ('/Sessions/Playing/Progress', 300000000)]
        assert not reporter._storage_retries
        assert reporter._queue.unfinished_tasks == 0
    finally:
        reporter.close()
        hub.close()


@pytest.mark.parametrize('retire', ['auth_halt', 'state_eviction'])
def test_hub_retains_retired_connection_worker_until_actual_exit(tmp_path, monkeypatch, retire):
    entered, release = Event(), Event()
    monkeypatch.setattr(mod, '_load_emby_client', lambda *_: (None, {
        'location': 'http://127.0.0.1:8096', 'token': 'fake',
        'server_id': 'server', 'user_id': 'user',
    }))

    def slow_connect(*_args):
        entered.set()
        assert release.wait(4)
        raise OSError('released after cancellation')

    hub = mod.EmbyInvalidationHub(tmp_path)
    sid, generation = 'a' * 32, 'b' * 64
    try:
        hub.ensure_ws_listener(sid, generation, connect_fn=slow_connect)
        assert entered.wait(1)
        worker = hub._ws_workers[(sid, generation)][1]
        if retire == 'auth_halt':
            hub.mark_auth_state(sid, generation, 'AUTH_REQUIRED')
        else:
            for index in range(16):
                hub.snapshot(str(index), generation)
        assert worker.is_alive()
        assert hub.close() is False, 'live retired worker must prevent a drained receipt'
        release.set()
        worker.join(1)
        assert not worker.is_alive()
        assert hub.close() is True
    finally:
        release.set()
        hub.close()


@pytest.mark.parametrize('opcode', [0x1, 0x8, 0x9, 0xA])
def test_websocket_rejects_server_masked_frames(opcode):
    # Reuse the production CLIENT encoder to supply an illegal server frame.
    raw = mod.build_ws_client_frame(opcode, b'' if opcode == 0x8 else b'x', mask_key=b'1234')
    with pytest.raises(mod._WSProtocolError) as failure:
        mod._WSFrameStream().feed(raw)
    assert failure.value.close_code == 1002


@pytest.mark.parametrize('valid_clock_arrives', [False, True])
def test_standard_unavailable_clock_does_not_clear_remote_resume(tmp_path, valid_clock_arrives):
    sent, history = [], []
    paused = [False]
    client = SimpleNamespace(
        session=SimpleNamespace(budget=lambda *_: nullcontext(),
            request=lambda path, **kw: sent.append((path, kw['data']['PositionTicks']))),
        _item=lambda _iid: {'UserData': {'Played': False, 'PlaybackPositionTicks': 400000000}},
    )
    hub = mod.EmbyInvalidationHub(tmp_path)
    reporter = mod.EmbySessionReporter(tmp_path, hub, client_loader=lambda *_: (client, {}),
                                       start_worker=False)
    session = StandardSession(SimpleNamespace(is_current=lambda _: True,
        require_current=lambda *_a, **_kw: None), history=history.append,
        paused=lambda: paused[0], observer=reporter.on_playback_event)
    request = _event('AV_START')['request_id']
    data = dict(_event('AV_START')['data'], request_id=request, _account={},
                url='http://127.0.0.1/movie.mkv', title='Movie')
    try:
        session.select(request, {})
        assert session.register(request, data)['accepted']
        assert session.observe(request, data['url'], 0, 0)
        reporter.drain_once(flush_pending=False)
        assert sent == [], 'an unavailable clock is not observed position zero'
        assert history == [], 'local progress must not save a synthetic initial zero'
        if valid_clock_arrives:
            # The first real clock must be emitted without a 10-second wait.
            assert session.observe(request, data['url'], 40, 3600)
            reporter.drain_once(flush_pending=False)
            assert sent == [('/Sessions/Playing', 400000000),
                            ('/Sessions/Playing/Progress', 400000000)]
            paused[0] = True
            assert session.observe(request, data['url'], None, None)
            reporter.drain_once(flush_pending=False)
            assert sent[-1] == ('/Sessions/Playing/Progress', 400000000)
        session.terminal(request, 'STOPPED')
        reporter.drain_once(flush_pending=False)
        if valid_clock_arrives:
            assert sent[-1] == ('/Sessions/Playing/Stopped', 400000000)
        else:
            assert sent == []
            assert history == []
    finally:
        reporter.close()
        hub.close()


def test_observed_zero_is_still_a_valid_start_over(tmp_path):
    sent = []
    client = SimpleNamespace(session=SimpleNamespace(budget=lambda *_: nullcontext(),
        request=lambda path, **kw: sent.append((path, kw['data']['PositionTicks']))))
    hub = mod.EmbyInvalidationHub(tmp_path)
    reporter = mod.EmbySessionReporter(tmp_path, hub, client_loader=lambda *_: (client, {}),
                                       start_worker=False)
    try:
        reporter.on_playback_event(_event('AV_START', 0))
        reporter.drain_once(flush_pending=False)
        assert sent == [('/Sessions/Playing', 0)]
    finally:
        reporter.close()
        hub.close()


def test_standard_first_real_clock_after_av_start_is_observable():
    events = []
    session = StandardSession(SimpleNamespace(is_current=lambda _: True,
        require_current=lambda *_a, **_kw: None), observer=events.append)
    request = 'd' * 32
    data = dict(request_id=request, _account={}, url='http://127.0.0.1/movie.mkv')
    session.select(request, {})
    session.register(request, data)
    assert session.observe(request, data['url'], 0, 0)
    assert session.observe(request, data['url'], 30, 3600)
    assert events[-1]['event'] == 'PROGRESS'
    assert events[-1]['position'] == 30
    assert events[-1]['observed_clock'] is True


@pytest.mark.parametrize('position,fresh,should_replay', [
    (200, {'PlaybackPositionTicks': 2010000000, 'Played': False}, False),
    (0, {}, False),
    (0, {'PlaybackPositionTicks': 0}, False),
    (0, {'Played': False}, False),
    (200, {'PlaybackPositionTicks': 2000000000, 'Played': False}, True),
])
def test_uncertain_stopped_requires_exact_complete_baseline(tmp_path, position, fresh, should_replay):
    blocked = [False]
    sent = []

    def request(path, **kw):
        if path.endswith('/Stopped') and blocked[0]:
            raise PanError('PAN_NETWORK_ERROR')
        sent.append(path)

    client = SimpleNamespace(session=SimpleNamespace(budget=lambda *_: nullcontext(), request=request),
                             _item=lambda _iid: {'UserData': fresh})
    hub = mod.EmbyInvalidationHub(tmp_path)
    reporter = mod.EmbySessionReporter(tmp_path, hub, client_loader=lambda *_: (client, {}),
                                       start_worker=False)
    try:
        reporter.on_playback_event(_event('AV_START', position))
        reporter.drain_once(flush_pending=False)
        blocked[0] = True
        reporter.on_playback_event(_event('TERMINAL', 900))
        reporter.drain_once(flush_pending=False)
        assert reporter._pending_stops
        blocked[0] = False
        sent.clear()
        reporter._flush_pending_stops()
        assert sent == (['/Sessions/Playing/Stopped'] if should_replay else [])
        assert not reporter._pending_stops
    finally:
        reporter.close()
        hub.close()


def test_uncertain_stopped_replays_backward_seek_after_own_progress_ack(tmp_path):
    blocked = [False]
    server_ticks = [0]
    sent = []

    def request(path, **kw):
        if path.endswith('/Stopped') and blocked[0]:
            raise PanError('PAN_NETWORK_ERROR')
        server_ticks[0] = kw['data']['PositionTicks']
        sent.append((path, server_ticks[0]))

    client = SimpleNamespace(session=SimpleNamespace(budget=lambda *_: nullcontext(), request=request),
        _item=lambda _iid: {'UserData': {'Played': False, 'PlaybackPositionTicks': server_ticks[0]}})
    hub = mod.EmbyInvalidationHub(tmp_path)
    reporter = mod.EmbySessionReporter(tmp_path, hub, client_loader=lambda *_: (client, {}),
                                       start_worker=False)
    try:
        reporter.on_playback_event(_event('AV_START', 100))
        reporter.drain_once(flush_pending=False)
        reporter.on_playback_event(_event('PROGRESS', 200))
        reporter.drain_once(flush_pending=False)
        blocked[0] = True
        reporter.on_playback_event(_event('TERMINAL', 150))
        reporter.drain_once(flush_pending=False)
        assert server_ticks[0] == 2000000000
        blocked[0] = False
        reporter._flush_pending_stops()
        assert sent[-1] == ('/Sessions/Playing/Stopped', 1500000000)
        assert server_ticks[0] == 1500000000
        assert not reporter._pending_stops
    finally:
        reporter.close()
        hub.close()

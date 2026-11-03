"""The actual run/monitor/drain boundary, not merely a populated next queue."""
from copy import deepcopy
from threading import Event
from time import monotonic
from types import MethodType, SimpleNamespace

import pytest

from test_transport_recovery_native import methods


@pytest.fixture
def boundary(monkeypatch):
    from bobbi_core import preparation_client, prepared_retry
    monkeypatch.setattr(preparation_client, 'capture_account', lambda *a, **kw: None)
    monkeypatch.setattr(prepared_retry, 'attach_context', lambda url, data: url)
    events, opened = [], []
    cancelled = Event()  # This is also the resolver's user-cancellation event.
    owns, aborted, child_signal = [True], [False], [None]

    class Child:
        _nextep_queue = []

        def __init__(self):
            self._cinema_cancel = Event()
            self._was_superseded = False
            self.kodi_monitor = SimpleNamespace(abortRequested=lambda: aborted[0])

        def run(self, data):
            opened.append(deepcopy(data))
            if child_signal[0] == 'cancel': self._cinema_cancel.set()
            elif child_signal[0] == 'superseded': self._was_superseded = True
            elif child_signal[0] == 'abort': aborted[0] = True

    env = dict(monotonic=monotonic, TERMINAL_RECONCILIATION_SECONDS=3.,
        get_setting=lambda *a: False, kodilog=lambda *a, **kw: None,
        xbmc=SimpleNamespace(LOGINFO=1, LOGWARNING=2, LOGERROR=3),
        close_busy_dialog=lambda: None, close_all_dialog=lambda: None, clear_property=lambda *a: None,
        make_listing=lambda data: object(), JacktookPLayer=Child)
    actor = SimpleNamespace(data={}, _cinema_cancel=cancelled, _provided_cancel_event=cancelled,
        _was_superseded=False, _transport_recovery=None, _transport_recovery_child=False,
        _transport_parent_queued=False, _cinema_natural_queued=False,
        _cinema_phase=lambda value: events.append(value),
        _activate_playback_session=lambda: True, clear_playback_properties=lambda: None,
        _is_trakt_tracking_excluded=lambda: True,
        mark_watched=lambda data: None,
        _wait_for_video_start=lambda: True, handle_playback_start=lambda: True,
        _record_started_history=lambda: None, start_cinema_preparation=lambda: None,
        select_audio_stream=lambda: None, handle_subtitle_selection=lambda: None,
        isPlayingVideo=lambda: False, skip_intro_enabled=False,
        _owns_playback_session=lambda: owns[0], _release_playback_session=lambda: None,
        wait_cinema_terminal=lambda **kw: None, offer_terminal_actions=lambda: None,
        handle_playback_stop=lambda: None, kodi_monitor=SimpleNamespace(abortRequested=lambda: aborted[0]),
        PLAYLIST=SimpleNamespace(clear=lambda: None),
        run_error=lambda error: pytest.fail('unexpected run failure: ' + repr(error)),
        kill_dialog=lambda: pytest.fail('unexpected monitor failure'))
    actor.set_constants = lambda data: (setattr(actor, 'data', data), setattr(actor, 'url', data['url']))
    for name, method in methods({'run', 'monitor', '_drain_nextep_queue'}, env).items():
        setattr(actor, name, MethodType(method, actor))
    actor.play_video = lambda item: actor.monitor()
    actor.queue_cinema_transport_end = lambda *a: False
    actor.queue_cinema_natural_end = lambda: None
    child = dict(url='https://media.invalid/next.mkv', request_id='b'*32,
        _ui_reserved_request='b'*32, selection_policy='exact',
        _selection_context=dict(boot_id='test', epoch=2, request_id='b'*32))

    def reserve(kind):
        # Separate tests exercise the real reserve_child/PlaybackOwner. Here
        # owner loss at successful reservation is the boundary precondition.
        owns[0] = False
        setattr(actor, '_cinema_natural_queued' if kind == 'eof' else '_transport_parent_queued', True)
        Child._nextep_queue.append({'data': deepcopy(child)})
        return True

    data = dict(url='https://media.invalid/current.mkv', request_id='a'*32,
        selection_policy='exact', mode='tv', cinema_continuity=True)
    return SimpleNamespace(actor=actor, event=cancelled, opened=opened, events=events,
        data=data, reserve=reserve, queue=Child._nextep_queue, aborted=aborted, owns=owns,
        child_signal=child_signal, child=child)


@pytest.mark.parametrize('kind', ['eof', 'transport'])
def test_reserved_child_survives_actual_parent_monitor_cleanup(boundary, kind):
    b = boundary
    if kind == 'eof':
        b.actor.queue_cinema_natural_end = lambda: b.reserve(kind)
    else:
        b.actor.queue_cinema_transport_end = lambda *a: b.reserve(kind)
    b.actor.run(b.data)
    assert len(b.opened) == 1
    assert b.opened[0]['request_id'] == 'b'*32
    assert b.opened[0]['direct_playback_handoff'] is True
    assert b.opened[0]['_queue_drained_by_parent'] is True
    assert not b.event.is_set(), 'normal retirement must not impersonate a UI cancellation'
    assert not b.owns[0], 'old callbacks have already lost their authority'
    assert not b.queue


@pytest.mark.parametrize('kind', ['eof', 'transport'])
@pytest.mark.parametrize('signal', ['cancel', 'abort', 'superseded'])
def test_explicit_cancellation_still_wins_after_reservation(boundary, kind, signal):
    b = boundary
    if kind == 'eof':
        b.actor.queue_cinema_natural_end = lambda: b.reserve(kind)
    else:
        b.actor.queue_cinema_transport_end = lambda *a: b.reserve(kind)
    def interrupt():
        if signal == 'cancel': b.event.set()
        elif signal == 'abort': b.aborted[0] = True
        else: b.actor._was_superseded = True
    b.actor.handle_playback_stop = interrupt
    b.actor.run(b.data)
    assert not b.opened
    if signal == 'cancel': assert b.event.is_set()


def test_no_reserved_child_preserves_old_cleanup(boundary):
    b = boundary
    b.actor.run(b.data)
    assert b.event.is_set() and not b.opened


def test_legacy_flag_alone_does_not_bypass_cleanup(boundary):
    b = boundary
    b.data['selection_policy'] = 'legacy'
    b.actor.PLAYLIST = SimpleNamespace(add=lambda *a: None)
    b.actor.queue_cinema_natural_end = lambda: b.reserve('eof')
    b.actor.run(b.data)
    assert b.event.is_set() and not b.opened


@pytest.mark.parametrize('signal', ['cancel', 'superseded', 'abort'])
def test_child_stop_does_not_consume_another_queued_entry(boundary, signal):
    b = boundary
    b.queue.extend([{'data': deepcopy(b.child)}, {'data': deepcopy(b.child)}])
    b.child_signal[0] = signal
    b.actor._drain_nextep_queue()
    assert len(b.opened) == 1


def test_manual_back_does_not_open_another_queued_entry(boundary, monkeypatch):
    from lib import search
    monkeypatch.setattr(search, 'show_next_sources', lambda data: False)
    b = boundary
    b.queue.extend([{'data': {}, 'results': [object()]}, {'data': deepcopy(b.child)}])
    b.actor._drain_nextep_queue()
    assert not b.opened

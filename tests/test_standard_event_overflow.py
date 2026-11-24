"""R07 / PB-03 regression: callback event-queue overflow stays scoped to its captured request."""
import importlib.util
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

from bobbi_platform.standard_session import StandardSession

ROOT = Path(__file__).resolve().parents[1]


def _load_standard_playback():
    path = ROOT / 'addons/plugin.video.bobbi/lib/services/standard_playback.py'
    spec = importlib.util.spec_from_file_location('test_standard_playback_r07', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_actor(module, session, *, playing=False):
    actor = module.StandardPlayback.__new__(module.StandardPlayback)
    actor.closed = False
    actor.session = session
    actor.bound = ''
    actor.bound_epoch = 0
    actor.events = Queue(maxsize=64)
    actor.subtitle_worker = actor.subtitle_job = actor.subtitle_pending = None
    actor.next_display = SimpleNamespace(publish=lambda summary: None, clear=lambda: None)
    actor.clear_subtitle_state = lambda: None
    actor.reports = []
    actor.host = SimpleNamespace(report=actor.reports.append)
    actor.player = SimpleNamespace(
        isPlaying=lambda: playing,
        isPlayingVideo=lambda: False,
        getPlayingFile=lambda: '',
    )
    return actor


def test_stale_callback_overflow_never_retires_newly_selected_session():
    module = _load_standard_playback()
    accounts = SimpleNamespace(require_current=lambda *a, **kw: None, is_current=lambda a: True)
    session = StandardSession(accounts)
    old, new = 'a' * 32, 'b' * 32

    session.select(old, {'account': 'user-A'})
    actor = _make_actor(module, session)
    actor.bound, actor.bound_epoch = old, session.current['generation']

    for _ in range(64):
        actor.events.put_nowait((old, 1, 'ENDED'))

    session.select(new, {'account': 'user-A'})
    assert session.current_request(new)

    # Callback arrives while bound still holds old A and the 64-item queue is saturated.
    actor.event('STOPPED')
    assert session.current_request(new)
    assert session.current['state'] == 'selected'
    assert not session.current['cancel'].is_set()
    assert actor.reports == ['STANDARD_EVENT_OVERFLOW']

    # Serial resident tick drains stale A events and stale A overflow without touching B.
    actor.tick()
    assert session.current_request(new)
    assert session.current['state'] == 'selected'
    assert not session.current['cancel'].is_set()


def test_current_session_self_overflow_fails_closed_on_serial_tick_without_fake_eof():
    module = _load_standard_playback()
    saved = []
    accounts = SimpleNamespace(require_current=lambda *a, **kw: None, is_current=lambda a: True)
    session = StandardSession(accounts, history=lambda row: saved.append(row) or True)
    req = 'c' * 32
    account = {'account': 'user-C'}

    session.select(req, account)
    session.register(req, {'request_id': req, '_account': account, 'url': 'https://media.example/video.mkv', 'title': 'Film'})
    assert session.observe(req, 'https://media.example/video.mkv', 120.0, 3600.0)

    actor = _make_actor(module, session, playing=False)
    actor.bound, actor.bound_epoch = req, session.current['generation']
    for _ in range(64):
        actor.events.put_nowait(('d' * 32, 0, 'STOPPED'))

    # Callback itself must NOT mutate session state on the callback thread.
    actor.event('STOPPED')
    assert session.current['state'] == 'playing'

    # Resident tick retires the current session as EVENT_OVERFLOW (never NATURAL_EOF).
    actor.tick()
    assert not session.current_request(req)
    assert session.current['state'] == 'retired'
    assert saved[-1]['terminal_reason'] == 'EVENT_OVERFLOW'
    assert saved[-1]['completed'] is False


def test_late_old_overflow_does_not_overwrite_current_overflow_latch():
    module = _load_standard_playback()
    saved = []
    accounts = SimpleNamespace(require_current=lambda *a, **kw: None, is_current=lambda a: True)
    session = StandardSession(accounts, history=lambda row: saved.append(row) or True)
    old, cur = '1' * 32, '2' * 32
    account = {'account': 'user-1'}

    session.select(cur, account)
    session.register(cur, {'request_id': cur, '_account': account, 'url': 'https://media.example/cur.mkv', 'title': 'Cur'})
    assert session.observe(cur, 'https://media.example/cur.mkv', 30.0, 600.0)

    actor = _make_actor(module, session, playing=False)
    for _ in range(64):
        actor.events.put_nowait(('9' * 32, 0, 'ENDED'))

    actor.bound, actor.bound_epoch = cur, session.current['generation']
    actor.event('STOPPED')
    # A late callback from an older generation arrives before tick.
    actor.bound, actor.bound_epoch = old, 1
    actor.event('ENDED')

    actor.tick()
    assert session.current['state'] == 'retired'
    assert saved[-1]['terminal_reason'] == 'EVENT_OVERFLOW'


def test_normal_under_limit_events_and_close_race_stay_bounded():
    module = _load_standard_playback()
    saved = []
    accounts = SimpleNamespace(require_current=lambda *a, **kw: None, is_current=lambda a: True)
    session = StandardSession(accounts, history=lambda row: saved.append(row) or True)
    req = 'e' * 32
    account = {'account': 'user-E'}

    session.select(req, account)
    session.register(req, {'request_id': req, '_account': account, 'url': 'https://media.example/ep1.mkv', 'title': 'Ep1'})
    assert session.observe(req, 'https://media.example/ep1.mkv', 45.0, 900.0)

    actor = _make_actor(module, session, playing=False)
    actor.bound, actor.bound_epoch = req, session.current['generation']
    actor.event('STOPPED')
    actor.event('STOPPED')  # Repeated terminal ignored cleanly after first retirement.
    actor.tick()
    assert session.current['state'] == 'retired'
    assert [row['terminal_reason'] for row in saved] == ['STARTED', 'STOP']

    # Closed actor ignores further overflow latches.
    actor.closed = True
    for _ in range(64):
        actor.events.put_nowait((req, 1, 'STOPPED'))
    actor.event('ERROR')
    assert not getattr(actor, '_overflowed', ())

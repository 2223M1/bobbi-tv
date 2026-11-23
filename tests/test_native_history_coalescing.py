"""One native writer job retains only its exact session's latest report.

Actual native method bodies, submit/defer, threads and profile disk storage;
Kodi/tracking and already-validated terminal receipts are boundary doubles.
"""
import ast
from copy import deepcopy
from pathlib import Path
import sys
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bobbi_core.file_ref import from_selected
from bobbi_platform.paths import ProfileBinding
from test_standard_file_history_close import disk, load
from test_standard_product import product
from test_ce2097_file_history import database
from test_playback_start_facts import scene, capture, history


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def lane(disk, monkeypatch):
    deferred = load('native_coalesce_deferred', 'addons/plugin.video.bobbi/lib/db/deferred_history.py')
    submission = load('native_coalesce_submit', 'addons/plugin.video.bobbi/lib/services/playback_history.py')
    monkeypatch.setitem(sys.modules, 'lib.db.deferred_history', deferred)
    workers, errors, logs, submissions = [], [], [], []
    def thread(target, **kwargs):
        args = kwargs.pop('args')
        def run():
            try:
                target(*args)
            except BaseException as error:
                errors.append(error)
        worker = Thread(target=run, **kwargs)
        assert worker.daemon is False
        workers.append(worker)
        return worker
    monkeypatch.setattr(deferred, 'Thread', thread)
    monkeypatch.setitem(sys.modules, 'lib.jacktook.utils', SimpleNamespace(kodilog=logs.append))
    def submit(data, **kwargs):
        result = submission.submit_native(data, **kwargs)
        submissions.append(result)
        return result
    monkeypatch.setitem(sys.modules, 'lib.services.playback_history', SimpleNamespace(submit_native=submit))
    path = ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    player = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'JacktookPLayer')
    methods = [node for node in player.body if isinstance(node, ast.FunctionDef)
               and node.name in ('mark_watched', 'handle_playback_stop', 'update_playback_progress',
                                 '_record_started_history')]
    native = ast.ClassDef(name='Native', bases=[], keywords=[], body=methods, decorator_list=[])
    namespace = dict(set_watched_file=lambda data: pytest.fail('Synchronous personal-file fallback'),
        kodilog=lambda message, **kwargs: logs.append(message), xbmc=SimpleNamespace(LOGINFO=1),
        monotonic=lambda: disk.product.clock[0],
        get_visibility=lambda name: name == 'Player.Paused' and disk.product.state.paused)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[native], type_ignores=[])), str(path), 'exec'), namespace)
    actor = namespace['Native']()
    ref = from_selected(disk.product.account,
        dict(file_id='native-file', name='Original.mkv', size=100, directory=False), 'original-parent')
    context = disk.files.FileHistory(disk.storage.PickleDatabase(profile_root=disk.root('A'))).begin(ref)
    actor.data = dict(_pan_file=True, _file_history=context, request_id='a' * 32,
        _account=deepcopy(disk.product.account), selection_policy='exact',
        current_time=10, total_time=100, url='https://fixture.invalid/SECRET')
    actor._file_history_binding = ProfileBinding()
    actor._terminal_reason = 'STOP'
    actor._cinema_phase = lambda phase: None
    actor._sync_yamtrack_watched = actor._queue_nuvio_progress_sync = lambda: None
    actor._delete_completed_simkl_playback = actor._delete_completed_trakt_playback = lambda: None
    actor._is_trakt_scrobble_enabled = lambda: False
    actor._is_trakt_tracking_excluded = lambda: True
    def join():
        for worker in workers:
            worker.join(3)
            assert not worker.is_alive()
        assert deferred._job is None
        assert deferred._lane.acquire(blocking=False)
        deferred._lane.release()
    yield SimpleNamespace(disk=disk, deferred=deferred, submission=submission, actor=actor,
        workers=workers, errors=errors, logs=logs, submissions=submissions, join=join)
    for gate in getattr(disk, '_native_gates', []):
        gate.release.set()
    join()


def blocked_start(lane):
    gate = lane.disk.block()
    lane.disk._native_gates = [gate]
    assert lane.actor.mark_watched(lane.actor.data) is None
    assert gate.entered.wait(2)
    return gate


@pytest.mark.parametrize('change', ['none', 'instance', 'cancel', 'early-pause'])
def test_native_checkpoint_before_stop_requires_same_live_instance_and_writer(lane, monkeypatch, change):
    actor, clock = lane.actor, lane.disk.product.clock
    actor._cinema_history_pending = True
    actor.playback_client, actor._owner_context, actor._native_instance = None, {}, 'fixture-instance'
    actor._cinema_cancel = Event()
    actor._owns_playback_session = actor._matches_requested_playback = lambda: True
    monkeypatch.setattr(sys.modules['lib.services.playback_history'], 'capture_start', lambda *_: False, raising=False)
    actor._record_started_history()
    lane.join()
    actor.getTotalTime = lambda: 100
    actor.getTime = lambda: 10
    actor.update_playback_progress()
    clock[0] += 2 if change == 'early-pause' else 30
    lane.disk.product.state.paused = change == 'early-pause'
    if change == 'instance':
        actor._matches_requested_playback = lambda: False
    elif change == 'cancel':
        actor._cinema_cancel.set()
    actor.getTime = lambda: 40
    actor.update_playback_progress()
    lane.join()
    row = lane.disk.read(actor.data)
    assert (row['completion_reason'], row['position']) == (
        ('PROGRESS', 40) if change in ('none', 'early-pause') else ('STARTED', 10))
    assert not lane.errors


@pytest.mark.parametrize('reason,parent', [('STOP', False), ('NATURAL_EOF', False), ('STOP', True)])
def test_real_native_stop_methods_coalesce_into_same_blocked_start_job(lane, reason, parent):
    gate = blocked_start(lane)
    actor = lane.actor
    actor._terminal_reason, actor._transport_parent_queued = reason, parent
    actor._cinema_natural_queued = reason == 'NATURAL_EOF'
    actor.data['current_time'] = 99 if reason == 'NATURAL_EOF' else 42
    assert actor.handle_playback_stop() is None
    assert lane.submissions == [True, True] and len(lane.workers) == 1
    gate.release.set()
    lane.join()
    row = lane.disk.read(actor.data)
    assert (row['position'], row['completion_reason'], row['sequence']) == (actor.data['current_time'], reason, 2)
    assert row['file_ref'] == actor.data['_file_history']['file_ref']
    assert not lane.errors and '[FILE-HISTORY] HISTORY_QUEUE_FULL' not in lane.logs


def test_highest_sequence_allows_backward_seek_and_snapshots_caller(lane):
    gate = blocked_start(lane)
    for position in (80, 17):
        lane.actor.data['current_time'] = position
        lane.actor.handle_playback_stop()
    lane.actor.data['current_time'] = 99
    gate.release.set()
    lane.join()
    row = lane.disk.read(lane.actor.data)
    assert (row['position'], row['sequence']) == (17, 3)
    assert [item[0]['current_time'] for item in lane.disk.attempts] == [10, 17]
    assert len(lane.workers) == 1


def test_unknown_zero_duration_reuses_file_history_normalization(lane):
    gate = blocked_start(lane)
    lane.actor.data.update(current_time=42, total_time=0)
    lane.actor.handle_playback_stop()
    assert lane.submissions == [True, True]
    gate.release.set()
    lane.join()
    row = lane.disk.read(lane.actor.data)
    assert (row['position'], row['duration'], row['completion_reason']) == (42, None, 'STOP')


@pytest.mark.parametrize('change', ['root', 'generation', 'session', 'request', 'file-ref',
    'lower-sequence', 'equal-sequence', 'invalid-sequence', 'missing-context', 'legacy'])
def test_inapplicable_or_stale_report_cannot_replace_active_job(lane, change):
    gate = blocked_start(lane)
    data = deepcopy(lane.actor.data)
    data.update(_file_history_sequence=2, current_time=42, terminal_reason='STOP')
    binding = lane.actor._file_history_binding
    if change == 'root':
        binding = ProfileBinding(lambda addon: lane.disk.root('B').parent / addon)
    if change == 'generation': data['_file_history']['generation'] += 1
    if change == 'session': data['_file_history']['session_id'] = 'b' * 32
    if change == 'request': data['request_id'] = 'b' * 32
    if change == 'file-ref': data['_file_history']['file_ref']['name'] = 'Renamed.mkv'
    if change == 'lower-sequence': data['_file_history_sequence'] = 0
    if change == 'equal-sequence': data['_file_history_sequence'] = 1
    if change == 'invalid-sequence': data['_file_history_sequence'] = True
    if change == 'missing-context': data.pop('_file_history')
    if change == 'legacy': data.pop('_pan_file')
    assert lane.deferred.defer_watched_file(data, profile_binding=binding) is False
    gate.release.set()
    lane.join()
    assert lane.disk.read(lane.actor.data)['position'] == 10 and len(lane.workers) == 1


def test_original_profile_drains_but_new_revoked_admission_never_revives_after_aba(lane):
    gate = blocked_start(lane)
    lane.actor.data['current_time'] = 42
    lane.actor.handle_playback_stop()
    binding = lane.actor._file_history_binding
    lane.disk.activate('B')
    assert not binding.is_current()
    assert not lane.submission.submit_native(lane.actor.data, reason='STOP', profile_binding=binding)
    lane.disk.activate('A')
    assert not binding.is_current()
    assert not lane.submission.submit_native(lane.actor.data, reason='STOP', profile_binding=binding)
    gate.release.set()
    lane.join()
    assert lane.disk.read(lane.actor.data)['position'] == 42
    assert lane.disk.storage.PickleDatabase(profile_root=lane.disk.root('B')).get_key(lane.disk.files.KEY) is None


def test_revocation_while_waiting_for_admission_rejects_only_new_report(lane):
    gate = blocked_start(lane)
    binding = lane.actor._file_history_binding
    checked, finished, calls = Event(), Event(), []
    def require_current():
        binding.require_current()
        calls.append(1)
        if len(calls) == 2:
            checked.set()  # Both pre-lock checks passed before waiting.
    lane.actor._file_history_binding = SimpleNamespace(
        require_current=require_current, root=binding.root)
    lane.actor.data['current_time'] = 42
    def stop():
        lane.actor.handle_playback_stop()
        finished.set()
    producer = Thread(target=stop)
    try:
        with lane.deferred._admission:
            producer.start()
            assert checked.wait(2) and not finished.is_set()
            lane.disk.activate('B')
        assert finished.wait(2)
        assert lane.submissions == [True, False]
        lane.disk.activate('A')
        assert not binding.is_current()
        gate.release.set()
        producer.join(3)
        lane.join()
        assert lane.disk.read(lane.actor.data)['position'] == 10
        assert lane.disk.storage.PickleDatabase(profile_root=lane.disk.root('B')).get_key(lane.disk.files.KEY) is None
    finally:
        gate.release.set()
        producer.join(5)


def test_old_coalesced_context_cannot_overwrite_new_generation_on_disk(lane):
    gate = blocked_start(lane)
    files = lane.disk.files.FileHistory(lane.disk.storage.PickleDatabase(profile_root=lane.disk.root('A')))
    current = files.begin(lane.actor.data['_file_history']['file_ref'])
    assert files.save(dict(lane.actor.data, _file_history=current, _file_history_sequence=1,
                           current_time=20, terminal_reason='STOP'))
    expected = files.get(current['file_ref']['id'])
    lane.actor.data['current_time'] = 99
    lane.actor._terminal_reason = 'NATURAL_EOF'
    lane.actor.handle_playback_stop()
    gate.release.set()
    lane.join()
    assert lane.disk.read(lane.actor.data) == expected


def test_failed_start_commit_and_newer_terminal_share_existing_pending_journal(lane, monkeypatch):
    original = lane.disk.storage._atomic_save
    writes = []
    def save(path, data):
        writes.append(deepcopy(data))
        if len(writes) == 1:
            raise OSError('injected first commit failure')
        return original(path, data)
    monkeypatch.setattr(lane.disk.storage, '_atomic_save', save)
    gate = blocked_start(lane)
    lane.actor.data['current_time'] = 42
    lane.actor.handle_playback_stop()
    gate.release.set()
    lane.join()
    assert [item[2] for item in lane.disk.attempts] == [False, True]
    assert len(lane.workers) == 1 and len(writes) == 2
    assert lane.disk.read(lane.actor.data)['position'] == 42
    assert not lane.deferred._databases[lane.disk.root('A')].has_pending()


def test_failed_final_commit_remains_pending_until_a_real_later_submission(lane, monkeypatch):
    original = lane.disk.storage._atomic_save
    def fail(*args): raise OSError('injected disk failure')
    monkeypatch.setattr(lane.disk.storage, '_atomic_save', fail)
    lane.actor.mark_watched(lane.actor.data)
    lane.join()
    assert lane.deferred._databases[lane.disk.root('A')].has_pending()
    assert lane.disk.read(lane.actor.data)['sequence'] == 0
    monkeypatch.setattr(lane.disk.storage, '_atomic_save', original)
    lane.actor.data['current_time'] = 42
    lane.actor.handle_playback_stop()
    lane.join()
    assert len(lane.workers) == 2 and lane.disk.read(lane.actor.data)['position'] == 42
    assert not lane.deferred._databases[lane.disk.root('A')].has_pending()


def test_failed_diagnostic_does_not_discard_an_already_admitted_newer_terminal(lane, monkeypatch):
    original = lane.disk.storage._atomic_save
    failed = [False]
    def save(path, data):
        if not failed[0]:
            failed[0] = True
            raise OSError('first commit failed')
        return original(path, data)
    monkeypatch.setattr(lane.disk.storage, '_atomic_save', save)
    monkeypatch.setitem(sys.modules, 'lib.jacktook.utils', SimpleNamespace(
        kodilog=lambda *a: (_ for _ in ()).throw(RuntimeError('diagnostic unavailable'))))
    gate = blocked_start(lane)
    lane.actor.data['current_time'] = 42
    lane.actor.handle_playback_stop()
    gate.release.set()
    lane.join()
    assert lane.disk.read(lane.actor.data)['position'] == 42 and len(lane.workers) == 1
    assert not lane.errors


@pytest.mark.parametrize('failure', ['deepcopy', 'capacity-check'])
def test_pre_worker_exception_cannot_leak_lane(lane, monkeypatch, failure):
    if failure == 'deepcopy':
        class Uncopyable:
            def __deepcopy__(self, memo): raise RuntimeError('cannot snapshot')
        data = dict(lane.actor.data, extra=Uncopyable())
    else:
        data = lane.actor.data
        def failed(): raise RuntimeError('cannot inspect pending journal')
        for index in range(4):
            lane.deferred._databases[lane.disk.root(str(index))] = SimpleNamespace(has_pending=failed)
    assert not lane.deferred.defer_watched_file(data, profile_binding=lane.actor._file_history_binding)
    lane.join()


@pytest.mark.parametrize('failure', ['construct', 'start'])
def test_worker_start_failure_releases_own_lane_once_and_allows_next_job(lane, monkeypatch, failure):
    original = lane.deferred.Thread
    def fail(**kwargs):
        if failure == 'construct': raise RuntimeError('cannot construct')
        return SimpleNamespace(start=lambda: (_ for _ in ()).throw(RuntimeError('cannot start')))
    monkeypatch.setattr(lane.deferred, 'Thread', fail)
    lane.actor.mark_watched(lane.actor.data)
    assert lane.submissions == [False]
    lane.join()
    monkeypatch.setattr(lane.deferred, 'Thread', original)
    lane.actor.data['current_time'] = 42
    lane.actor.handle_playback_stop()
    lane.join()
    assert lane.disk.read(lane.actor.data)['position'] == 42


@pytest.mark.parametrize('failure', ['import', 'diagnostic', 'fatal'])
def test_worker_exceptions_never_strand_or_release_another_jobs_lane(lane, monkeypatch, failure):
    adapter = sys.modules['lib.utils.general.utils']
    with monkeypatch.context() as patch:
        if failure == 'import':
            patch.setitem(sys.modules, 'lib.db.pickle_db', None)
            patch.setitem(sys.modules, 'lib.jacktook.utils', None)
        elif failure == 'diagnostic':
            patch.setattr(lane.disk.storage, '_atomic_save', lambda *a: (_ for _ in ()).throw(OSError()))
            patch.setitem(sys.modules, 'lib.jacktook.utils', SimpleNamespace(
                kodilog=lambda *a: (_ for _ in ()).throw(RuntimeError('diagnostic failed'))))
        else:
            patch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(
                set_watched_file=lambda *a, **kw: (_ for _ in ()).throw(SystemExit())))
        lane.actor.mark_watched(lane.actor.data)
        lane.join()
    assert bool(lane.errors) is (failure == 'fatal')
    assert sys.modules['lib.utils.general.utils'] is adapter
    lane.actor.data['current_time'] = 42
    lane.actor.handle_playback_stop()
    lane.join()
    assert lane.disk.read(lane.actor.data)['position'] == 42


def test_update_after_disk_write_before_revision_check_stays_in_same_worker(lane, monkeypatch):
    adapter = sys.modules['lib.utils.general.utils'].set_watched_file
    entered, release = Event(), Event()
    def save(data, database=None):
        result = adapter(data, database=database)
        if data['_file_history_sequence'] == 1:
            entered.set()
            assert release.wait(3)
        return result
    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(set_watched_file=save))
    try:
        lane.actor.mark_watched(lane.actor.data)
        assert entered.wait(2)
        lane.actor.data['current_time'] = 42
        lane.actor.handle_playback_stop()
        assert lane.submissions == [True, True]
        release.set()
        lane.join()
        assert len(lane.workers) == 1 and lane.disk.read(lane.actor.data)['position'] == 42
    finally:
        release.set()


def test_atomic_finish_cannot_lose_new_job_or_double_release_successor_lane(lane, monkeypatch):
    original = lane.deferred._finish
    entered, release, submitted = Event(), Event(), Event()
    first = [True]
    def finish(job):
        if first[0]:
            first[0] = False
            entered.set()
            assert release.wait(3)
        original(job)
    monkeypatch.setattr(lane.deferred, '_finish', finish)
    producer = None
    try:
        lane.actor.mark_watched(lane.actor.data)
        assert entered.wait(2)
        gate = lane.disk.block()
        lane.disk._native_gates = [gate]
        lane.actor.data['current_time'] = 42
        def stop():
            lane.actor.handle_playback_stop()
            submitted.set()
        producer = Thread(target=stop)
        producer.start()
        assert not submitted.wait(.1)
        release.set()
        assert submitted.wait(2) and gate.entered.wait(2)
        assert not lane.deferred._lane.acquire(blocking=False)
        gate.release.set()
        producer.join(3)
        lane.join()
        assert len(lane.workers) == 2 and lane.disk.read(lane.actor.data)['position'] == 42
    finally:
        release.set()
        if producer:
            producer.join(5)


@pytest.mark.parametrize('facts', ['retained', 'missing', 'invalid'])
def test_complete_terminal_snapshot_preserves_or_revokes_original_start_facts(scene, monkeypatch, facts):
    deferred = load('native_facts_coalesce', 'addons/plugin.video.bobbi/lib/db/deferred_history.py')
    submission = load('native_facts_submit', 'addons/plugin.video.bobbi/lib/services/playback_history.py')
    monkeypatch.setitem(sys.modules, 'lib.db.deferred_history', deferred)
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', scene.storage)
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', history)
    monkeypatch.setitem(sys.modules, 'lib.jacktook.utils', SimpleNamespace(kodilog=lambda *a: None))
    workers, entered, release = [], Event(), Event()
    def thread(**kwargs):
        worker = Thread(**kwargs)
        workers.append(worker)
        return worker
    monkeypatch.setattr(deferred, 'Thread', thread)
    def save(data, database=None):
        if data['_file_history_sequence'] == 1:
            entered.set()
            assert release.wait(3)
        return history.FileHistory(database).save(data)
    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(set_watched_file=save))
    scene.data['_file_history_sequence'] = 0
    assert capture(scene)  # The real scoped start projection, not invented facts.
    observed = deepcopy(scene.data['_file_start_observation'])
    try:
        assert submission.submit_native(scene.data, reason='STARTED', profile_binding=scene.binding)
        assert entered.wait(2)
        if facts == 'missing': scene.data.pop('_file_start_observation')
        if facts == 'invalid': scene.data['_file_start_observation']['expected']['native_instance'] = 'invalid'
        scene.data['current_time'] = 42
        assert submission.submit_native(scene.data, reason='STOP', profile_binding=scene.binding)
        scene.data.pop('_file_start_observation', None)  # Accepted data was copied.
        release.set()
        for worker in workers:
            worker.join(3)
            assert not worker.is_alive()
        restarted = history.FileHistory(scene.storage.PickleDatabase(profile_root=scene.binding.root('plugin.video.bobbi')))
        row = restarted.get(scene.file['id'])
        assert (row['position'], row['completion_reason'], row['sequence']) == (42, 'STOP', 2)
        stored = restarted.database.get_key_checked(history.FACTS_KEY) or {}
        if facts == 'retained':
            assert stored[scene.file['id']]['observation'] == observed
            assert stored[scene.file['id']]['binding']['sequence'] == 2
        else:
            assert scene.file['id'] not in stored  # Never restore an old job's evidence.
        assert len(workers) == 1 and deferred._job is None
    finally:
        release.set()
        for worker in workers:
            worker.join(5)

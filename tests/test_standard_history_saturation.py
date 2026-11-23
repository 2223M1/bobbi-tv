"""Bounded standard history: real callbacks, one writer, real profile disk.

Kodi/provider observations are fixtures, not device or native receipt proof.
The 17-session cases reproduce the original 32-queued plus one-writing load.
"""
from copy import deepcopy
from pathlib import Path
from threading import Event, Thread, get_ident
from types import SimpleNamespace
import sys

import pytest

from bobbi_core.file_ref import from_selected
from test_standard_product import product, handoff
from test_standard_file_history_close import disk, load
from test_ce2097_file_history import database
from test_playback_start_facts import scene, capture, history


def begin(disk, index):
    product = disk.product
    request = f'{index:032x}'
    data = dict(request_id=request, _account=deepcopy(product.account), selection_policy='exact',
        url=f'https://fixture.invalid/{index}.mkv', title='Saturation fixture',
        tv_data=dict(season=1, episode=index), mode='tv', file_evidence='AUTO_VERIFIED_FILE')
    product.actor.dispatch(dict(operation='select', request_id=request, account=data['_account']))
    ref = from_selected(product.account, dict(file_id=f'file-{index}',
        name=f'Original-{index}.mkv', size=100, directory=False), 'original-parent')
    files = disk.files.FileHistory(disk.storage.PickleDatabase(profile_root=disk.root('A')))
    data.update(_pan_file=True, _file_history=files.begin(ref))
    product.state.position = 10
    handoff(product, data)
    return data


def report(data, sequence=2, position=42, reason='STOP'):
    value = deepcopy(data)
    value.update(_file_history_sequence=sequence, current_time=position, total_time=100,
                 terminal_reason=reason, completed=reason == 'NATURAL_EOF')
    return value


@pytest.fixture
def full(disk, monkeypatch):
    entered, release = Event(), Event()
    adapter = sys.modules['lib.utils.general.utils'].set_watched_file
    databases = []
    def save(data, database=None):
        databases.append(database)
        if data['request_id'] == f'{1:032x}' and data['terminal_reason'] == 'STARTED':
            entered.set()
            assert release.wait(5)
        return adapter(data, database=database)
    monkeypatch.setattr(sys.modules['lib.utils.general.utils'], 'set_watched_file', save)
    first = begin(disk, 1)
    assert entered.wait(2)
    latest = first
    for index in range(2, 18):
        latest = begin(disk, index)
    actor = disk.product.actor
    writer = actor.history
    assert (writer.accepted, writer.completed, writer.queue.qsize(), len(writer._jobs)) == (33, 0, 32, 33)
    try:
        yield SimpleNamespace(disk=disk, actor=actor, writer=writer, first=first,
                              latest=latest, release=release, databases=databases)
    finally:
        release.set()


def drain(full):
    full.release.set()
    full.writer.close()
    assert full.writer.accepted == full.writer.completed
    assert not full.writer._jobs and not full.writer.queue.unfinished_tasks


@pytest.mark.parametrize('action', ['STOP', 'EOF', 'CLOSE'])
def test_real_17_sessions_keep_terminal_when_32_queue_slots_are_full(full, action, monkeypatch):
    disk, actor, writer = full.disk, full.actor, full.writer
    position = 99 if action == 'EOF' else 42
    reason = {'STOP': 'STOP', 'EOF': 'NATURAL_EOF', 'CLOSE': 'SERVICE_CLOSED'}[action]
    disk.observe(position)
    accepted, submitted, errors = [], Event(), []
    original = actor.session.history
    def save(data):
        result = original(data)
        accepted.append(result)
        submitted.set()
        return result
    actor.session.history = save
    closer = None
    try:
        if action == 'CLOSE':
            def close():
                try: actor.close()
                except BaseException as error: errors.append(error)
            closer = Thread(target=close)
            closer.start()
            assert submitted.wait(2) and closer.is_alive()
        else:
            disk.product.state.playing = False
            callback = actor.player.onPlayBackEnded if action == 'EOF' else actor.player.onPlayBackStopped
            assert callback() is None and actor.tick() is None
        assert accepted == [True] and writer.accepted == 34 and writer.completed == 0
        assert writer.queue.qsize() == 32 and len(writer._jobs) == 33
        assert not actor.session.current.get('history_error')
        assert actor.session.current['state'] == ('ended' if action == 'EOF' else 'retired')
        full.release.set()
        if closer:
            closer.join(3)
            assert not closer.is_alive() and not errors
        else:
            actor.close()
        row = disk.read(full.latest)
        assert (row['position'], row['completion_reason'], row['sequence']) == (position, reason, 2)
        assert (writer.accepted, writer.completed, writer.failed) == (34, 34, 0)
        assert len(disk.attempts) == 33  # One queued revision covers two admissions.
        assert len({id(db) for db in full.databases}) == 1
        assert len(disk.product.state.opened) == 17 and not disk.product.state.reports
        assert not writer._jobs and not writer.queue.unfinished_tasks
    finally:
        full.release.set()
        if closer: closer.join(5)


def test_latest_sequence_can_seek_back_and_does_not_prioritize_eof(full):
    assert full.writer.save(report(full.latest, 2, 99, 'NATURAL_EOF')) is True
    value = report(full.latest, 3, 17, 'STOP')
    assert full.writer.save(value) is True
    value['current_time'] = 80
    drain(full)
    row = full.disk.read(full.latest)
    assert (row['position'], row['sequence'], row['completion_reason']) == (17, 3, 'STOP')
    assert (full.writer.accepted, full.writer.completed, len(full.disk.attempts)) == (35, 35, 33)


@pytest.mark.parametrize('change', ['generation', 'session', 'request', 'file-name', 'file-parent',
    'file-size', 'file-fingerprint', 'lower', 'equal', 'boolean', 'missing-context', 'legacy'])
def test_full_other_identity_or_stale_report_is_rejected_without_replacement(full, change):
    value = report(full.latest)
    context = value['_file_history']
    if change == 'generation': context['generation'] += 1
    if change == 'session': context['session_id'] = 'b' * 32
    if change == 'request': value['request_id'] = 'b' * 32
    if change == 'file-name': context['file_ref']['name'] = 'Renamed.mkv'
    if change == 'file-parent': context['file_ref']['parent_id'] = 'elsewhere'
    if change == 'file-size': context['file_ref']['size'] += 1
    if change == 'file-fingerprint': context['file_ref']['fingerprint'] = 'c' * 40
    if change == 'lower': value['_file_history_sequence'] = 0
    if change == 'equal': value['_file_history_sequence'] = 1
    if change == 'boolean': value['_file_history_sequence'] = True
    if change == 'missing-context': value.pop('_file_history')
    if change == 'legacy': value.pop('_pan_file')
    assert full.writer.save(value) is False
    assert full.writer.accepted == 33 and len(full.writer._jobs) == 33
    drain(full)
    assert full.disk.read(full.latest)['sequence'] == 1
    assert full.disk.product.state.reports == ['HISTORY_QUEUE_FULL']


@pytest.mark.parametrize('kind,position,natural', [('STOPPED', 42, False), ('ENDED', 99, True)])
def test_real_terminal_refusal_marks_history_error_not_a_new_control_or_fake_eof(full, kind, position, natural):
    actor = full.actor
    full.disk.observe(position)
    actor.session.current['data']['_file_history']['session_id'] = 'b' * 32
    request = actor.session.current['request_id']
    assert actor.session.terminal(request, kind, playing=False) is natural
    assert actor.session.current['history_error'] is True
    assert actor.session.current['state'] == ('ended' if natural else 'retired')
    assert not actor.session.terminal(request, kind, playing=False)
    assert full.writer.accepted == 33
    drain(full)
    assert full.disk.read(full.latest)['sequence'] == 1
    assert len(full.disk.product.state.opened) == 17


@pytest.mark.parametrize('result', [None, True, False, 'exception'])
def test_history_callback_none_remains_compatible_but_false_is_explicit_failure(disk, result):
    disk.begin()
    actor = disk.product.actor
    actor.history.queue.join()
    def callback(data):
        if result == 'exception': raise RuntimeError('callback unavailable')
        return result
    actor.session.history = callback
    actor.session._save(actor.session.current, 'STOP')
    assert bool(actor.session.current.get('history_error')) is (result is False or result == 'exception')


def test_close_rejects_late_report_without_holding_admission_during_disk_join(full):
    finished, errors = Event(), []
    def close():
        try: full.writer.close()
        except BaseException as error: errors.append(error)
        finally: finished.set()
    closer = Thread(target=close)
    try:
        assert full.writer.save(report(full.latest))
        closer.start()
        assert full.writer.done.wait(2) and not finished.is_set()
        assert full.writer.admission.acquire(blocking=False)
        full.writer.admission.release()
        assert full.writer.save(report(full.latest, 3, 17)) is False
        full.actor.session._save(full.actor.session.current, 'SERVICE_CLOSED')
        assert full.actor.session.current['history_error']
        full.release.set()
        assert finished.wait(3)
        assert not errors and full.writer.accepted == full.writer.completed == 34
        assert full.disk.read(full.latest)['position'] == 42
    finally:
        full.release.set()
        closer.join(5)


def test_original_profile_drains_after_switch_and_aba_without_rebinding(full):
    full.disk.activate('B')
    assert full.writer.save(report(full.latest))
    full.disk.activate('A')
    drain(full)
    assert full.disk.read(full.latest)['position'] == 42
    assert full.disk.storage.PickleDatabase(profile_root=full.disk.root('B')).get_key(full.disk.files.KEY) is None
    assert all(Path(db._database_path).parent == full.disk.root('A') for db in full.databases)


def test_new_disk_generation_still_wins_over_old_coalesced_terminal(full):
    files = full.disk.files.FileHistory(full.disk.storage.PickleDatabase(profile_root=full.disk.root('A')))
    context = files.begin(full.latest['_file_history']['file_ref'])
    assert files.save(dict(report(full.latest, 1, 20), _file_history=context))
    expected = files.get(context['file_ref']['id'])
    assert full.writer.save(report(full.latest, 2, 99, 'NATURAL_EOF'))
    drain(full)
    assert full.disk.read(full.latest) == expected


def test_failed_commit_reuses_one_original_profile_pending_journal(full, monkeypatch):
    original = full.disk.storage._atomic_save
    writes = []
    def save(path, data):
        writes.append(1)
        if len(writes) == 1: raise OSError('first commit unavailable')
        return original(path, data)
    monkeypatch.setattr(full.disk.storage, '_atomic_save', save)
    assert full.writer.save(report(full.latest))
    drain(full)
    assert full.writer.failed == 1 and full.disk.read(full.latest)['position'] == 42
    assert full.disk.attempts[0][2] is False
    assert len({id(db) for db in full.databases}) == 1 and not full.databases[-1].has_pending()


def test_failed_last_coalesced_write_is_not_durability_and_needs_a_real_later_save(full, monkeypatch):
    original = full.disk.storage._atomic_save
    identifier = full.latest['_file_history']['file_ref']['id']
    def fail_terminal(path, data):
        if data.get(full.disk.files.KEY, {}).get(identifier, {}).get('sequence') == 2:
            raise OSError('terminal disk failure')
        return original(path, data)
    monkeypatch.setattr(full.disk.storage, '_atomic_save', fail_terminal)
    assert full.writer.save(report(full.latest))
    full.release.set()
    full.writer.queue.join()
    assert full.writer.accepted == full.writer.completed == 34 and full.writer.failed == 1
    assert full.databases[-1].has_pending() and full.disk.read(full.latest)['sequence'] == 0
    attempts = len(full.disk.attempts)
    monkeypatch.setattr(full.disk.storage, '_atomic_save', original)
    assert not Event().wait(.05) and len(full.disk.attempts) == attempts
    assert full.writer.save(report(full.latest, 3, 17))
    full.writer.close()
    assert full.disk.read(full.latest)['position'] == 17 and not full.databases[-1].has_pending()


def test_queue_full_diagnostics_run_outside_admission_and_failure_stays_nonfatal(full):
    seen = []
    def diagnose(code):
        assert full.writer.admission.acquire(blocking=False)
        full.writer.admission.release()
        seen.append(code)
        raise RuntimeError('diagnostic unavailable')
    full.writer.report = diagnose
    assert full.writer.save(dict(report(full.latest), request_id='b' * 32)) is False
    assert seen == ['HISTORY_QUEUE_FULL'] and full.writer.diagnostic_failures == 1
    assert full.writer.save(report(full.latest))
    drain(full)
    assert full.disk.read(full.latest)['position'] == 42


@pytest.mark.parametrize('facts', ['retained', 'missing', 'invalid'])
def test_full_inflight_snapshot_keeps_or_revokes_real_start_facts(scene, monkeypatch, facts):
    module = load('standard_saturation_facts', 'addons/plugin.video.bobbi/lib/services/standard_playback.py')
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', scene.storage)
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', history)
    entered, release = Event(), Event()
    def save(data, database=None):
        if data.get('_file_history_sequence') == 1:
            entered.set()
            assert release.wait(5)
        return history.FileHistory(database).save(data)
    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(set_watched_file=save))
    assert capture(scene)
    writer = module.HistoryWriter(lambda code: None, profile_root=scene.binding.root('plugin.video.bobbi'))
    try:
        assert writer.save(scene.data)
        assert entered.wait(2)
        for index in range(32): assert writer.save(dict(filler=index))
        value = report(scene.data)
        if facts == 'missing': value.pop('_file_start_observation')
        if facts == 'invalid': value['_file_start_observation']['expected']['native_instance'] = 'invalid'
        assert writer.save(value)
        value.pop('_file_start_observation', None)
        release.set()
        writer.close()
        files = history.FileHistory(scene.storage.PickleDatabase(profile_root=scene.binding.root('plugin.video.bobbi')))
        assert files.get(scene.file['id'])['position'] == 42
        saved = files.database.get_key_checked(history.FACTS_KEY) or {}
        assert (scene.file['id'] in saved) is (facts == 'retained')
        assert writer.accepted == writer.completed == 34 and not writer.failed
    finally:
        release.set()
        writer.close()


@pytest.fixture
def lane(disk, monkeypatch):
    """Standalone real writer, with each test choosing its IO boundary."""
    data = report(disk.begin(), 3, 10, 'PROGRESS')
    disk.product.actor.close()
    module = load('standard_saturation_races', 'addons/plugin.video.bobbi/lib/services/standard_playback.py')
    writers, releases = [], []
    def gate():
        entered, release = Event(), Event()
        releases.append(release)
        return entered, release
    def make(write, diagnose=lambda code: None):
        monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(set_watched_file=write))
        writer = module.HistoryWriter(diagnose, profile_root=disk.root('A'))
        writers.append(writer)
        return writer
    yield SimpleNamespace(disk=disk, module=module, data=data, make=make, gate=gate)
    for release in releases: release.set()
    for writer in writers:
        if writer.worker_failed:
            with pytest.raises(RuntimeError, match='HISTORY_DRAIN_INCOMPLETE'): writer.close()
        else:
            writer.close()


def fill(writer):
    for index in range(32): assert writer.save(dict(filler=index))
    assert writer.queue.qsize() == 32 and len(writer._jobs) == 33


def test_get_to_worker_handoff_has_no_unindexed_job_or_extra_capacity(lane, monkeypatch):
    entered, release = lane.gate()
    original = lane.module.Queue
    class GatedQueue(original):
        def get(self, *args, **kwargs):
            value = super().get(*args, **kwargs)
            if not entered.is_set():
                entered.set()
                assert release.wait(5)
            return value
    monkeypatch.setattr(lane.module, 'Queue', GatedQueue)
    attempted = []
    writer = lane.make(lambda data, database=None: attempted.append(deepcopy(data)))
    assert writer.save(lane.data) and entered.wait(2)
    assert writer.queue.qsize() == 0 and len(writer._jobs) == 1
    fill(writer)
    assert writer.save(report(lane.data, 4, 17))
    assert writer.save(dict(other=True)) is False
    assert len(writer._jobs) == 33 and writer.queue.unfinished_tasks == 33
    release.set()
    writer.close()
    assert attempted[0]['current_time'] == 17 and len(attempted) == 33
    assert writer.accepted == writer.completed == 34


def test_update_after_disk_io_before_finish_is_attempted_in_same_worker(lane):
    entered, release = lane.gate()
    attempted, databases = [], []
    def write(data, database=None):
        databases.append(database)
        if '_file_history' not in data: return
        attempted.append(deepcopy(data))
        result = lane.disk.files.FileHistory(database).save(data)
        if data['_file_history_sequence'] == 3:
            entered.set()
            assert release.wait(5)
        return result
    writer = lane.make(write)
    assert writer.save(lane.data) and entered.wait(2)
    assert lane.disk.read(lane.data)['sequence'] == 3
    fill(writer)
    assert writer.save(report(lane.data, 4, 99, 'NATURAL_EOF'))
    assert writer.save(report(lane.data, 5, 17, 'STOP'))
    release.set()
    writer.close()
    assert [data['_file_history_sequence'] for data in attempted] == [3, 5]
    assert writer.accepted == writer.completed == 35
    assert len(databases) == 34 and len({id(db) for db in databases}) == 1
    row = lane.disk.read(lane.data)
    assert (row['position'], row['sequence'], row['completion_reason']) == (17, 5, 'STOP')


@pytest.mark.parametrize('failure', ['exception', 'false'])
def test_failed_inflight_attempt_and_diagnostic_keep_newer_revision(lane, failure):
    entered, release = lane.gate()
    attempted = []
    def write(data, database=None):
        attempted.append(deepcopy(data))
        if data.get('_file_history_sequence') == 3:
            entered.set()
            assert release.wait(5)
            if failure == 'exception': raise OSError('first attempt unavailable')
            return False
        if '_file_history' in data:
            return lane.disk.files.FileHistory(database).save(data)
    def diagnose(code):
        assert writer.admission.acquire(blocking=False)
        writer.admission.release()
        raise RuntimeError('diagnostics unavailable')
    writer = lane.make(write, diagnose)
    assert writer.save(lane.data) and entered.wait(2)
    fill(writer)
    assert writer.save(report(lane.data, 4, 17))
    release.set()
    writer.close()
    assert writer.accepted == writer.completed == 34 and len(attempted) == 34
    assert writer.failed == writer.diagnostic_failures == 1
    assert lane.disk.read(lane.data)['position'] == 17


def test_retired_job_finally_cannot_remove_a_new_same_identity_job(lane, monkeypatch):
    retired, release_old = lane.gate()
    second, release_second = lane.gate()
    writer = lane.make(lambda data, database=None: (
        second.set(), release_second.wait(5)) if data['_file_history_sequence'] == 4 else None)
    lock = writer.admission
    pause = dict(owner=None, used=False)
    class PauseAfterRetirement:
        def __enter__(self): lock.acquire()
        def __exit__(self, *args):
            lock.release()
            if pause['owner'] == get_ident() and not pause['used']:
                pause['used'] = True
                retired.set()
                assert release_old.wait(5)
    writer.admission = PauseAfterRetirement()
    original = writer._finish
    def finish(job):
        original(job)
        if not pause['used']: pause['owner'] = get_ident()
    monkeypatch.setattr(writer, '_finish', finish)
    assert writer.save(lane.data) and retired.wait(2)
    assert writer.accepted == writer.completed == 1 and not writer._jobs
    assert writer.save(report(lane.data, 4, 17))
    release_old.set()
    assert second.wait(2)
    assert len(writer._jobs) == writer.queue.unfinished_tasks == 1
    assert writer.accepted == 2 and writer.completed == 1
    release_second.set()
    writer.close()
    assert writer.accepted == writer.completed == 2 and not writer.queue.unfinished_tasks


@pytest.mark.parametrize('fault', ['storage', 'diagnostic'])
def test_fatal_exit_never_hides_admitted_but_unattempted_revision(lane, fault):
    entered, release = lane.gate()
    attempted, codes = [], []
    def write(data, database=None):
        attempted.append(data)
        entered.set()
        assert release.wait(5)
        if fault == 'storage': raise SystemExit('fatal storage')
        return False
    def diagnose(code):
        assert writer.admission.acquire(blocking=False)
        writer.admission.release()
        codes.append(code)
        if fault == 'diagnostic': raise SystemExit('fatal diagnostic')
    writer = lane.make(write, diagnose)
    assert writer.save(lane.data) and entered.wait(2)
    fill(writer)
    assert writer.save(report(lane.data, 4, 17))
    release.set()
    writer.worker.join(2)
    assert not writer.worker.is_alive() and writer.worker_failed and writer.done.is_set()
    assert writer.accepted == 34 and writer.completed == 1 and writer.failed == 1
    assert len(attempted) == 1 and len(writer._jobs) == writer.queue.unfinished_tasks == 32
    assert writer.save(report(lane.data, 5, 18)) is False
    with pytest.raises(RuntimeError, match='HISTORY_DRAIN_INCOMPLETE'): writer.close()
    assert codes[-1] == 'HISTORY_WORKER_FAILED'


def test_import_failure_is_counted_then_later_submission_can_recover(lane, monkeypatch):
    attempted, codes = [], []
    writer = lane.make(lambda data, database=None: attempted.append(data), codes.append)
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, 'lib.db.pickle_db', None)
        assert writer.save(lane.data)
        writer.queue.join()
    assert writer.accepted == writer.completed == writer.failed == 1
    assert not attempted and codes == ['HISTORY_WRITE_FAILED']
    assert writer.save(report(lane.data, 4, 17))
    writer.close()
    assert writer.accepted == writer.completed == 2 and len(attempted) == 1


@pytest.mark.parametrize('phase', ['construct', 'start'])
def test_thread_setup_failure_cannot_claim_admission(lane, monkeypatch, phase):
    class FailedThread:
        def __init__(self, **kwargs):
            if phase == 'construct': raise RuntimeError('thread construction')
        def start(self): raise RuntimeError('thread start')
    monkeypatch.setattr(lane.module, 'Thread', FailedThread)
    with pytest.raises(RuntimeError, match='thread'):
        lane.module.HistoryWriter(lambda code: None, profile_root=lane.disk.root('A'))


def test_deepcopy_failure_has_no_admission_and_close_wins_copy_race(lane):
    entered, release = lane.gate()
    attempted, results = [], []
    writer = lane.make(lambda data, database=None: attempted.append(data))
    class Uncopyable:
        def __deepcopy__(self, memo): raise ValueError('copy unavailable')
    with pytest.raises(ValueError, match='copy unavailable'): writer.save(Uncopyable())
    assert writer.accepted == 0 and not writer._jobs
    class GatedCopy:
        def __deepcopy__(self, memo):
            entered.set()
            assert release.wait(5)
            return deepcopy(lane.data)
    producer = Thread(target=lambda: results.append(writer.save(GatedCopy())))
    producer.start()
    try:
        assert entered.wait(2)
        writer.close()
        release.set()
        producer.join(2)
        assert not producer.is_alive() and results == [False]
        assert writer.accepted == writer.completed == 0 and not attempted
    finally:
        release.set()
        producer.join(5)


def test_full_service_close_refusal_keeps_classification_and_single_control(full):
    full.disk.observe(42)
    full.actor.session.current['data']['_file_history']['session_id'] = 'b' * 32
    full.actor.session.close()
    assert full.actor.session.current['history_error']
    assert full.actor.session.current['state'] == 'retired'
    assert full.writer.accepted == 33
    drain(full)
    assert full.disk.read(full.latest)['sequence'] == 1
    assert len(full.disk.product.state.opened) == 17


def test_shared_key_preserves_captured_root_and_uses_complete_validation(lane):
    key = lane.disk.files.coalescing_key
    original = key(lane.data, lane.disk.root('A'))
    assert original is not None
    assert original != key(lane.data, lane.disk.root('B'))
    assert original == key(report(lane.data, 4, 17), lane.disk.root('A'))
    invalid = deepcopy(lane.data)
    invalid['_file_history']['file_ref']['size'] = True
    assert key(invalid, lane.disk.root('A')) is None

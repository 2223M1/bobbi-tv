"""Standard callbacks and shutdown through the actual profile history writer.

Kodi UI/player observations are doubles. Session policy, callback routing,
HistoryWriter threads, the production save adapter, FileHistory validation and
atomic on-disk database/restart reads are real; this is not a device test.
"""
import ast
from copy import deepcopy
from datetime import datetime
from functools import partial
import importlib.util
from pathlib import Path
import sys
from threading import Event, Thread
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

from bobbi_core.file_ref import from_selected
from bobbi_platform.pan_accounts import PanAccounts
from bobbi_platform.pan_http import credentials
from bobbi_platform.paths import ProfileBinding
from test_ce2096_pan_accounts import saved
from test_standard_product import product, selected, handoff


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def disk(product, monkeypatch, tmp_path):
    active = {'name': 'A'}
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda path: str(tmp_path / active['name'] / path.rsplit('/', 1)[-1]),
        mkdirs=lambda root: Path(root).mkdir(parents=True, exist_ok=True)))
    storage = load('standard_close_storage', 'addons/plugin.video.bobbi/lib/db/pickle_db.py')
    files = load('standard_close_files', 'addons/plugin.video.bobbi/lib/db/file_history.py')
    resident = load('standard_close_resident', 'addons/plugin.video.bobbi/lib/services/standard_playback.py')
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', storage)
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', files)
    monkeypatch.setattr(product.module, 'HistoryWriter', resident.HistoryWriter)

    # Execute the exact production adapter body, isolating its unrelated
    # module-level Kodi/provider imports, not substituting its persistence.
    path = ROOT / 'addons/plugin.video.bobbi/lib/utils/general/utils.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'set_watched_file')
    diagnostics, attempts, actors, gates, owners = [], [], [], {}, {}
    namespace = dict(pickle_db=storage.PickleDatabase(), unquote=unquote, datetime=datetime,
        kodilog=diagnostics.append, get_random_color=lambda *args, **kwargs: 'white',
        IndexerType=SimpleNamespace(DIRECT='direct', STREMIO_DEBRID='stremio'))
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)

    def adapter(data, database=None):
        gate = gates.get(data['request_id'])
        if gate:
            gate.entered.set()
            assert gate.release.wait(5), 'test storage must be released'
        result = namespace['set_watched_file'](data, database=database)
        attempts.append((deepcopy(data), database._database_path, result))
        return result

    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(set_watched_file=adapter))

    def root(name):
        return tmp_path / name / 'plugin.video.bobbi'

    def activate(name):
        active['name'] = name
        # Emulate a module imported in the new profile. The explicit writer
        # database must win over this active-profile legacy default.
        namespace['pickle_db'] = storage.PickleDatabase()

    def make(name='A'):
        activate(name)
        if name not in owners:
            owner = PanAccounts(tmp_path / name / 'pan-accounts.json',
                                {'quark': partial(credentials, 'quark')})
            owner.install(saved(), owner.snapshot('quark'))
            owners[name] = owner
        owner = owners[name]
        host = SimpleNamespace(accounts=owner, report=product.state.reports.append,
            bind_owner=lambda fn: None, plugin_root=root(name), stopping=Event())
        actor = product.module.StandardPlayback(host)
        actor.session.next_loader = None
        actor.session.clock = lambda: product.clock[0]
        actors.append(actor)
        product.actor, product.account = actor, owner.snapshot('quark')
        return actor

    def begin(letter='a', position=10, file_id='file-one'):
        data = selected(product, letter)
        ref = from_selected(product.account,
            dict(file_id=file_id, name='Original.mkv', size=100, directory=False), 'original-parent')
        context = files.FileHistory(storage.PickleDatabase(profile_root=product.actor.history.profile_root)).begin(ref)
        assert context
        data.update(_pan_file=True, _file_history=context)
        product.state.position = position
        handoff(product, data)
        return data

    def observe(position):
        product.state.position = position
        product.actor.tick()

    def read(data, name='A'):
        return files.FileHistory(storage.PickleDatabase(profile_root=root(name))).get(data['_file_history']['file_ref']['id'])

    def block(letter='a'):
        gate = SimpleNamespace(entered=Event(), release=Event())
        gates[letter * 32] = gate
        return gate

    make()
    yield SimpleNamespace(product=product, storage=storage, files=files, begin=begin,
        make=make, activate=activate, root=root, read=read, observe=observe, block=block,
        attempts=attempts, diagnostics=diagnostics, owners=owners)
    for gate in gates.values():
        gate.release.set()
    for actor in actors:
        actor.close()


def test_service_close_persists_latest_file_observation(disk):
    data = disk.begin()
    disk.observe(42)
    actor = disk.product.actor
    actor.close()
    row = disk.read(data)
    assert row['position'] == 42
    assert row['completion_reason'] == 'SERVICE_CLOSED'
    assert row['sequence'] == 2 and row['file_ref'] == data['_file_history']['file_ref']
    assert disk.files.record(row) == row
    assert not disk.attempts[-1][0]['completed']
    assert (actor.history.accepted, actor.history.completed, actor.history.failed) == (2, 2, 0)
    assert not actor.history.worker.is_alive()
    assert not disk.diagnostics and not disk.product.state.reports
    raw = (disk.root('A') / 'database.pickle').read_bytes()
    assert b'https://' not in raw and b'fixture-session' not in raw


def test_unclosed_player_has_durable_progress_without_pause_write_storm(disk):
    data = disk.begin(position=3)
    actor, clock = disk.product.actor, disk.product.clock
    actor.history.queue.join()
    clock[0] += 29
    disk.observe(32)
    assert actor.history.accepted == 1
    clock[0] += 1
    disk.observe(33)
    actor.history.queue.join()
    row = disk.read(data)  # Independent database, before either Stop or close.
    assert (row['position'], row['completion_reason'], row['sequence']) == (33, 'PROGRESS', 2)
    clock[0] += 1800
    for _ in range(5):
        disk.observe(33)
    assert actor.history.accepted == 2
    disk.observe(7)  # Intentional rewind is a new checkpoint, not a high-water mark.
    actor.history.queue.join()
    assert disk.read(data)['position'] == 7
    disk.product.state.playing = False
    actor.player.onPlayBackStopped()
    actor.tick()
    actor.history.queue.join()
    row = disk.read(data)
    assert (row['position'], row['completion_reason'], row['sequence']) == (7, 'STOP', 4)


def test_first_pause_saves_before_interval_and_does_not_repeat_while_idle(disk):
    data = disk.begin(position=3)
    actor, state, clock = disk.product.actor, disk.product.state, disk.product.clock
    clock[0] += 2
    state.paused = True
    disk.observe(5)
    actor.history.queue.join()
    row = disk.read(data)
    assert (row['position'], row['completion_reason'], row['sequence']) == (5, 'PROGRESS', 2)
    clock[0] += 1800
    disk.observe(5)
    state.paused = False
    disk.observe(5)
    state.paused = True
    disk.observe(5)
    assert actor.history.accepted == 2


@pytest.mark.parametrize('callback,position,reason,completed', [
    ('onPlayBackStopped', 99, 'STOP', False),
    ('onPlayBackError', 99, 'ERROR', False),
    ('onPlayBackEnded', 42, 'ERROR', False),
    ('onPlayBackEnded', 99, 'NATURAL_EOF', True),
])
def test_real_callbacks_keep_terminal_reason_when_service_then_closes(disk, callback, position, reason, completed):
    data = disk.begin()
    disk.observe(position)
    actor = disk.product.actor
    disk.product.state.playing = False
    getattr(actor.player, callback)()
    actor.tick()
    actor.close()
    row = disk.read(data)
    assert (row['position'], row['completion_reason'], row['sequence']) == (position, reason, 2)
    assert disk.attempts[-1][0]['completed'] is completed
    assert actor.history.failed == 0


def test_close_before_av_start_does_not_invent_progress(disk):
    data = selected(disk.product)
    disk.product.actor.dispatch(dict(operation='register', request_id=data['request_id'], data=data))
    disk.product.actor.close()
    assert disk.product.actor.history.accepted == 0 and not disk.attempts


def test_repeated_close_and_late_callback_cannot_submit_again(disk):
    data = disk.begin()
    disk.observe(99)
    actor = disk.product.actor
    actor.close()
    before = disk.read(data)
    disk.product.state.playing = False
    actor.player.onPlayBackEnded()
    actor.tick()
    actor.close()
    assert disk.read(data) == before
    assert before['completion_reason'] == 'SERVICE_CLOSED'
    assert actor.history.accepted == actor.history.completed == 2
    assert all(not item[0]['completed'] for item in disk.attempts)


def test_queued_unprocessed_ended_is_not_completion_evidence_at_close(disk):
    data = disk.begin()
    disk.observe(99)
    actor = disk.product.actor
    disk.product.state.playing = False
    actor.player.onPlayBackEnded()
    actor.close()  # No resident terminal reconciliation has accepted this event.
    assert disk.read(data)['completion_reason'] == 'SERVICE_CLOSED'
    assert not disk.attempts[-1][0]['completed']


@pytest.mark.parametrize('late', ['lower-sequence', 'equal-sequence', 'removed'])
def test_reordered_close_reports_cannot_rewind_or_revive_history(disk, late):
    data = disk.begin()
    disk.observe(42)
    actor = disk.product.actor
    actor.session.close()
    actor.history.queue.join()
    expected = disk.read(data)
    stale = deepcopy(disk.attempts[-1][0])
    stale.update(current_time=100, terminal_reason='NATURAL_EOF', completed=True,
        _file_history_sequence=1 if late == 'lower-sequence' else 2)
    if late == 'removed':
        files = disk.files.FileHistory(disk.storage.PickleDatabase(profile_root=disk.root('A')))
        assert files.remove(expected['id'], expected)
    actor.history.save(stale)
    actor.close()
    if late == 'removed':
        with pytest.raises(ValueError, match='FILE_HISTORY_NOT_FOUND'):
            disk.read(data)
    else:
        assert disk.read(data) == expected
    assert actor.history.accepted == actor.history.completed == 3 and actor.history.failed == 0


def test_profile_a_b_a_reverse_drain_keeps_original_file_and_profile(disk):
    binding = ProfileBinding()
    gate = disk.block()
    a = disk.product.actor
    first = disk.begin(position=10)
    assert gate.entered.wait(2)
    disk.observe(42)
    disk.make('B')
    assert not binding.is_current()
    second = disk.begin('b', position=22, file_id='file-two')
    b = disk.product.actor
    disk.activate('A')
    assert not binding.is_current()  # A return cannot resurrect the old lease.
    b.close()
    assert disk.read(second, 'B')['position'] == 22
    errors, finished = [], Event()
    def close_old():
        try:
            a.close()
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()
    closer = Thread(target=close_old)
    closer.start()
    try:
        assert not finished.wait(.1)
        gate.release.set()
        closer.join(3)
        assert finished.is_set() and not errors
    finally:
        gate.release.set()
        closer.join(5)
    assert disk.read(first)['position'] == 42
    for data, name, actor in ((first, 'A', a), (second, 'B', b)):
        row = disk.read(data, name)
        assert row['file_ref'] == data['_file_history']['file_ref']
        assert row['completion_reason'] == 'SERVICE_CLOSED'
        rows = disk.storage.PickleDatabase(profile_root=disk.root(name)).get_key(disk.files.KEY)
        assert set(rows) == {row['id']}
        assert actor.history.accepted == actor.history.completed == 2 and actor.history.failed == 0


def test_late_old_close_cannot_overwrite_new_same_file_generation(disk):
    gate = disk.block()
    old = disk.product.actor
    first = disk.begin()
    assert gate.entered.wait(2)
    disk.observe(99)
    disk.make('A')
    current = disk.begin('b', position=20)
    disk.product.actor.close()
    expected = disk.read(current)
    gate.release.set()
    old.close()
    assert expected['generation'] == first['_file_history']['generation'] + 1
    assert expected['position'] == 20 and expected['completion_reason'] == 'SERVICE_CLOSED'
    assert disk.read(first) == expected
    assert old.history.failed == 0  # True is a successful commit, not applied-row proof.


def test_account_a_b_a_late_callback_is_revoked_but_close_keeps_original_identity(disk):
    data = disk.begin()
    disk.observe(42)
    owner = disk.owners['A']
    original = deepcopy(disk.product.account)
    other = owner.install(saved(uid='other-user'), original)
    returned = owner.install(saved(), other)
    assert returned['account_id'] == original['account_id'] and returned['epoch'] > original['epoch']
    assert not owner.is_current(original)
    actor = disk.product.actor
    assert not actor.session.terminal(data['request_id'], 'ENDED')
    actor.close()
    row = disk.read(data)
    assert row['file_ref'] == data['_file_history']['file_ref']
    assert (row['position'], row['completion_reason'], row['sequence']) == (42, 'SERVICE_CLOSED', 2)


def test_close_disk_failure_preserves_previous_bytes_and_reports_failure(disk, monkeypatch):
    data = disk.begin()
    actor = disk.product.actor
    actor.history.queue.join()
    before = (disk.root('A') / 'database.pickle').read_bytes()
    disk.observe(42)
    def failed(*args):
        raise OSError('injected close write failure')
    monkeypatch.setattr(disk.storage, '_atomic_save', failed)
    actor.close()
    assert (disk.root('A') / 'database.pickle').read_bytes() == before
    assert disk.read(data)['position'] == 10
    assert actor.history.accepted == actor.history.completed == 2 and actor.history.failed == 1
    assert 'HISTORY_WRITE_FAILED' in disk.product.state.reports
    assert '[FILE-HISTORY] FILE_HISTORY_WRITE_FAILED' in disk.diagnostics
    assert not actor.history.worker.is_alive()


def test_earlier_cleanup_error_still_saves_and_drains_close_snapshot(disk, monkeypatch):
    data = disk.begin()
    disk.observe(42)
    actor = disk.product.actor
    with monkeypatch.context() as patch:
        def failed():
            raise OSError('injected subtitle cleanup failure')
        patch.setattr(actor, 'clear_subtitle_state', failed)
        with pytest.raises(OSError, match='subtitle cleanup'):
            actor.close()
    assert disk.read(data)['position'] == 42
    assert disk.read(data)['completion_reason'] == 'SERVICE_CLOSED'
    assert actor.history.accepted == actor.history.completed == 2 and actor.history.failed == 0
    assert not actor.history.worker.is_alive()

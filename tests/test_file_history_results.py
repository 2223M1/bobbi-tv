"""Real existing pickle journal: persistence receipts are not write authority."""
import ast
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_ce2097_file_history import database, history, module, playback, ACCOUNT, FILE
from bobbi_core.file_ref import from_selected

ROOT = Path(__file__).resolve().parents[1]


def adapter(monkeypatch):
    """Execute the production common branch, without importing Kodi globals."""
    source = (ROOT / 'addons/plugin.video.bobbi/lib/utils/general/utils.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'set_watched_file')
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', history)
    namespace = dict(kodilog=lambda *args: None)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual-common-history-adapter>', 'exec'), namespace)
    return namespace['set_watched_file']


def test_results_distinguish_stale_from_applied_and_preserve_bool(database):
    storage, root = database
    old, new = [history.FileHistory(storage.PickleDatabase(profile_root=root)) for _ in range(2)]
    ref = from_selected(ACCOUNT, FILE, '0')
    first = old.begin(ref)
    result = old.save_result(playback(first, position=42))
    assert result['disposition'] == 'applied' and result['receipt']['position'] == 42
    assert set(result['receipt']) == {'file_ref', 'generation', 'session_id', 'sequence',
                                     'completion_reason', 'position', 'duration'}
    assert 'SECRET' not in repr(result)
    second = new.begin(ref)
    assert new.save_result(playback(second, sequence=2, position=60))['disposition'] == 'applied'
    for data in (playback(first, sequence=99, reason='NATURAL_EOF', position=100),
                 playback(second, sequence=1, position=3), playback(second, sequence=2, position=60)):
        assert old.save_result(data) == dict(disposition='ignored_stale', receipt=None)
        assert old.save(data) is True
    assert new.get(ref['id'])['position'] == 60
    # Backward seeks are ordered observations, not a max(position) merge.
    assert new.save_result(playback(second, sequence=3, position=5))['receipt']['position'] == 5
    assert new.save_result({}) == dict(disposition='unsupported', receipt=None)
    assert new.save({}) is True
    assert new.save_result(playback(dict(second, token='SECRET'))) == dict(disposition='invalid', receipt=None)


@pytest.mark.parametrize('action', ['set', 'delete', 'key', 'file_report'])
def test_same_commit_later_operation_never_exposes_intermediate_success(database, action):
    storage, root = database
    db = storage.PickleDatabase(profile_root=root)
    files = history.FileHistory(db)
    context = files.begin(from_selected(ACCOUNT, FILE, '0'))
    assert files.save(playback(context, position=1))
    candidate = dict(files.get(context['file_ref']['id']), sequence=2, position=2.)
    db._queue(('file_report', history.KEY, candidate['id'], (candidate, None)), False)
    observed = db._pending[-1]
    later = dict(candidate, sequence=3, position=3.)
    operation = (action, history.KEY, None if action == 'key' else candidate['id'],
                 {} if action == 'key' else None if action == 'delete' else
                 (later, None) if action == 'file_report' else candidate)
    db._queue(operation, False)
    # Even equal-value generic set is a later writer, not this report's receipt.
    assert db._commit(observed=observed) == (True, 'superseded_in_commit')


def test_failed_pending_replay_does_not_resurrect_a_receipt(database, monkeypatch):
    storage, root = database
    db = storage.PickleDatabase(profile_root=root)
    files = history.FileHistory(db)
    context = files.begin(from_selected(ACCOUNT, FILE, '0'))
    before = (root / 'database.pickle').read_bytes()
    original = storage._atomic_save
    monkeypatch.setattr(storage, '_atomic_save', lambda *a: (_ for _ in ()).throw(OSError('fixture')))
    result = files.save_result(playback(context, position=42))
    assert result == dict(disposition='failed', receipt=None) and db.has_pending()
    assert (root / 'database.pickle').read_bytes() == before
    monkeypatch.setattr(storage, '_atomic_save', original)
    assert db.set_item('jt:lfh', 'unrelated', {'title': 'later'}) is True
    assert files.get(context['file_ref']['id'])['position'] == 42
    assert result == dict(disposition='failed', receipt=None)  # No retained callback/outbox.
    assert files.save_result(playback(context, position=42))['disposition'] == 'ignored_stale'


def test_common_adapter_sink_is_outside_lock_exception_isolated_and_bool_compatible(database, monkeypatch):
    storage, root = database
    db = storage.PickleDatabase(profile_root=root)
    files = history.FileHistory(db)
    context = files.begin(from_selected(ACCOUNT, FILE, '0'))
    save, results = adapter(monkeypatch), []
    def unlocked():
        with storage._writer_lock(db._database_path):
            return True
    def sink(result):
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(unlocked).result(timeout=.5)
        results.append(deepcopy(result))
        result['disposition'] = 'failed'  # Observer mutation cannot change bool.
        raise RuntimeError('observer broken')
    assert save(playback(context), database=db, result_sink=sink) is True
    assert results[0]['disposition'] == 'applied'
    assert save(playback(context), database=db, result_sink=sink) is True
    assert results[-1]['disposition'] == 'ignored_stale'
    assert save(playback(context, sequence=2, position=20), database=db) is True
    assert save(playback(context, sequence=0), database=db) is False


def test_reentrant_sink_receipt_is_commit_time_fact_not_a_current_generation_lease(database, monkeypatch):
    storage, root = database
    db = storage.PickleDatabase(profile_root=root)
    files = history.FileHistory(db)
    context = files.begin(from_selected(ACCOUNT, FILE, '0'))
    save, results = adapter(monkeypatch), []
    def sink(result):
        results.append(deepcopy(result))
        if result['receipt']['sequence'] == 1:
            assert save(playback(context, sequence=2, position=5), database=db, result_sink=sink) is True
    assert save(playback(context, sequence=1, position=42), database=db, result_sink=sink) is True
    assert [(row['disposition'], row['receipt']['sequence'], row['receipt']['position']) for row in results] == [
        ('applied', 1, 42), ('applied', 2, 5)]
    assert files.get(context['file_ref']['id'])['position'] == 5
    assert files.get(context['file_ref']['id'])['sequence'] == 2


@pytest.mark.parametrize('writer', ['native', 'standard'])
def test_actual_writer_reaches_same_committed_result_branch(database, monkeypatch, writer):
    storage, root = database
    files = history.FileHistory(storage.PickleDatabase(profile_root=root))
    context = files.begin(from_selected(ACCOUNT, FILE, '0'))
    save, results = adapter(monkeypatch), []
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', storage)
    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(
        set_watched_file=lambda data, **kw: save(data, result_sink=results.append, **kw)))
    data = dict(playback(context, position=42), request_id='a' * 32)
    if writer == 'native':
        target = module('receipt_native_lane', 'addons/plugin.video.bobbi/lib/db/deferred_history.py')
        binding = SimpleNamespace(require_current=lambda: None, root=lambda _: str(root))
        assert target.defer_watched_file(data, profile_binding=binding) is True
        assert target._lane.acquire(timeout=2)
        target._lane.release()
    else:
        target = module('receipt_standard_writer', 'addons/plugin.video.bobbi/lib/services/standard_playback.py')
        worker = target.HistoryWriter(lambda *a: None, profile_root=str(root))
        worker.save(data)
        worker.close()
    assert len(results) == 1 and results[0]['disposition'] == 'applied'
    assert results[0]['receipt']['completion_reason'] == 'STOP'
    assert history.FileHistory(storage.PickleDatabase(profile_root=root)).get(context['file_ref']['id'])['position'] == 42

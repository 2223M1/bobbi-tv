import os
import hashlib

import pytest

from lib.cinema import font_cache as module
from test_cinema_font_cache import cache, bound


def count_hashes(monkeypatch):
    calls = []
    original = module.file_hash
    def read(path, **kwargs):
        calls.append(path)
        return original(path, **kwargs)
    monkeypatch.setattr(module, 'file_hash', read)
    return calls


def test_idle_proof_is_reused_by_preflight_without_granting_activation(cache, monkeypatch):
    store, _ = cache
    row, sub = bound(store)
    calls = count_hashes(monkeypatch)
    plan = store.next_byte_action()
    assert store.warm_bytes(plan, lambda: True)['state'] == 'BYTE_PROOF_ONLY'
    assert calls == [store._path(row)]
    assert store.verify_plan(store.activation_plan('release1', sub))
    assert len(calls) == (1 if module.BYTE_PROOF_REUSE else 2)
    assert not list(store.native.iterdir())
    assert not store.ledger.db.execute('SELECT * FROM font_leases').fetchall()


def test_restart_discards_proof_and_seeds_current_working_set_first(cache, monkeypatch):
    store, _ = cache
    old, sub = bound(store)
    store.activate('release1', sub, 'request', lambda: True)
    other, _ = bound(store, 'release2', 'Other Font')
    plan = store.activation_plan('release1', sub)
    store.verify_plan(plan)
    restarted = module.FontCache(store.ledger, store.root, store.native)
    assert restarted._proofs == {}
    first = restarted.next_byte_action()
    assert set(record['sha256'] for record in first.values()) == {old['sha256']}
    calls = count_hashes(monkeypatch)
    restarted.verify_plan(plan)
    assert calls == [store._path(old)]
    assert restarted.next_byte_action()[str(store._path(other))]['sha256'] == other['sha256']


def test_new_file_without_idle_warmup_still_gets_full_hash(cache, monkeypatch):
    store, _ = cache
    row, sub = bound(store)
    calls = count_hashes(monkeypatch)
    store.verify_plan(store.activation_plan('release1', sub))
    assert calls == [store._path(row)]


def test_failed_hash_is_not_cached_and_does_not_loop_idle_jobs(cache, monkeypatch):
    store, _ = cache
    row, sub = bound(store)
    raw = store._path(row).read_bytes()
    store._path(row).write_bytes(b'x' * len(raw))
    plan = store.next_byte_action()
    with pytest.raises(ValueError, match='bytes differ'):
        store.warm_bytes(plan, lambda: True)
    assert not store._proofs and store.next_byte_action() is None
    store._path(row).write_bytes(raw)
    calls = count_hashes(monkeypatch)
    store.verify_plan(store.activation_plan('release1', sub))
    assert calls == [store._path(row)]


def test_paused_idle_work_reads_nothing_and_is_requeued(cache, monkeypatch):
    store, _ = cache
    row, sub = bound(store)
    calls = count_hashes(monkeypatch)
    plan = store.next_byte_action()
    result = store.warm_bytes(plan, lambda: False)
    store.finish_byte_action(plan, result)
    assert calls == [] and store._proofs == {}
    assert store.next_byte_action() == plan


def test_link_change_invalidates_proof_and_requires_fresh_bytes(cache, monkeypatch):
    store, _ = cache
    row, sub = bound(store)
    store.verify_plan(store.activation_plan('release1', sub))
    assert store._proofs
    store.activate('release1', sub, 'request', lambda: True,
                   verified=store.verify_plan(store.activation_plan('release1', sub)))
    assert store._proofs == {}  # A new ctime is not silently adopted.
    calls = count_hashes(monkeypatch)
    store.warm_bytes(store.next_byte_action(), lambda: True)
    assert calls == [store._path(row)]


def test_replacement_after_idle_proof_is_rehashed_not_silently_accepted(cache, monkeypatch):
    store, _ = cache
    row, sub = bound(store)
    plan = store.activation_plan('release1', sub)
    store.verify_plan(plan)
    path = store._path(row)
    old = path.stat()
    replacement = path.with_suffix('.replacement')
    replacement.write_bytes(path.read_bytes())
    os.utime(replacement, ns=(old.st_atime_ns, old.st_mtime_ns))
    os.replace(replacement, path)
    calls = count_hashes(monkeypatch)
    store.verify_plan(plan)
    assert calls == [path]


def test_next_reservation_prioritizes_already_queued_fonts(cache):
    store, _ = cache
    bound(store)
    row, sub = bound(store, 'nextrelease', 'Next Font')
    store.reserve('nextrelease', sub, 'next-owner')
    assert store.next_byte_action()[str(store._path(row))]['sha256'] == row['sha256']


def test_empty_warmup_queue_does_not_query_database_or_stat_files(cache, monkeypatch):
    store, _ = cache
    def forbidden(*args):
        pytest.fail('Empty warmup queue must not scan files or ledger')
    monkeypatch.setattr(store, '_record', forbidden)
    monkeypatch.setattr(module, 'file_stamp', forbidden)
    assert store.next_byte_action() is None


def test_bounded_queue_still_admits_priority_current_or_next_fonts(cache):
    store, _ = cache
    for index in range(256):
        store._queue_bytes('%064x' % index)
    store._queue_bytes('f' * 64, priority=True)
    assert len(store._byte_queued) == len(store._byte_queue) == 256
    assert store._byte_queue[0] == 'f' * 64


def test_idle_hash_yields_after_playback_starts_without_partial_proof(cache, tmp_path, monkeypatch):
    store, _ = cache
    path = tmp_path / 'large.ttf'
    raw = b'x' * (3 * 1024 * 1024)
    path.write_bytes(raw)
    plan = {str(path): dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())}
    ticks = iter(range(20))
    monkeypatch.setattr(module, 'monotonic', lambda: next(ticks))
    checks = []
    def allowed():
        checks.append(True)
        return len(checks) <= 3  # Entry, path, first 1 MiB; then playback starts.
    assert store.warm_bytes(plan, allowed) == {'state': 'PAUSED'}
    assert len(checks) == 4 and store._proofs == {}


def test_idle_playback_checks_are_rate_limited_not_one_rpc_per_chunk(cache, tmp_path, monkeypatch):
    store, _ = cache
    path = tmp_path / 'large.ttf'
    raw = b'x' * (3 * 1024 * 1024)
    path.write_bytes(raw)
    plan = {str(path): dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())}
    monkeypatch.setattr(module, 'monotonic', lambda: 1.0)
    checks = []
    def allowed():
        checks.append(True)
        return True
    assert store.warm_bytes(plan, allowed)['state'] == 'BYTE_PROOF_ONLY'
    assert checks == [True]

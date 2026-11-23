import hashlib
import os

import pytest

from lib.cinema import font_cache as module


def fixture_plan(tmp_path):
    first = tmp_path / 'object.ttf'
    first.write_bytes(b'bounded-font-verification-fixture')
    alias = tmp_path / 'native.ttf'
    os.link(first, alias)
    record = dict(bytes=first.stat().st_size, sha256=hashlib.sha256(first.read_bytes()).hexdigest())
    return first, alias, {str(first): dict(record), str(alias): dict(record)}


def test_same_inode_is_hashed_once_per_call_but_not_cached_between_calls(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    calls = []
    original = module.file_hash
    def read(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(module, 'file_hash', read)
    proof = module.verify_font_plan(plan)
    assert proof[str(first)] == proof[str(alias)]
    assert len(calls) == 1
    module.verify_font_plan(plan)
    assert len(calls) == 2


def test_conflicting_digest_for_same_inode_rejected(tmp_path):
    first, alias, plan = fixture_plan(tmp_path)
    plan[str(alias)]['sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        module.verify_font_plan(plan)


def test_file_mutation_after_hash_is_rejected(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    original = module.file_hash
    def mutate(path):
        digest = original(path)
        path.write_bytes(b'changed')
        return digest
    monkeypatch.setattr(module, 'file_hash', mutate)
    with pytest.raises(ValueError):
        module.verify_font_plan(plan)


def test_unchanged_process_proof_reuses_exact_bytes_but_still_checks_each_path(tmp_path, monkeypatch):
    plan = {}
    for index in range(8):
        path = tmp_path / ('font%d.ttf' % index)
        raw = ('font-%d' % index).encode()
        path.write_bytes(raw)
        alias = tmp_path / ('native%d.ttf' % index)
        os.link(path, alias)
        record = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        plan[str(path)] = dict(record)
        plan[str(alias)] = dict(record)
    proof = module.verify_font_plan(plan)
    calls = []
    original = module.file_stamp
    def stamp(path):
        calls.append(path)
        return original(path)
    hashes, original_hash = [], module.file_hash
    def read(path):
        hashes.append(path)
        return original_hash(path)
    monkeypatch.setattr(module, 'file_hash', read)
    monkeypatch.setattr(module, 'file_stamp', stamp)
    assert module.verify_font_plan(plan, proof) == proof
    assert len(calls) == 32 and set(calls) == set(plan)
    assert len(hashes) == (0 if module.BYTE_PROOF_REUSE else 8)


def test_same_size_replacement_with_restored_mtime_is_rejected(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    original = module.file_hash
    def replace(path):
        digest = original(path)
        info = alias.stat()
        replacement = tmp_path / 'replacement.ttf'
        replacement.write_bytes(alias.read_bytes())
        os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
        os.replace(replacement, alias)
        return digest
    monkeypatch.setattr(module, 'file_hash', replace)
    with pytest.raises(ValueError, match='changed during'):
        module.verify_font_plan(plan)


def test_other_font_mutation_after_its_hash_is_rejected(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    other = tmp_path / 'other.ttf'
    other.write_bytes(b'x')
    plan[str(other)] = dict(bytes=1, sha256=hashlib.sha256(b'x').hexdigest())
    original = module.file_hash
    def read(path):
        digest = original(path)
        if path == other:
            first.write_bytes(b'changed')
        return digest
    monkeypatch.setattr(module, 'file_hash', read)
    with pytest.raises(ValueError, match='changed during'):
        module.verify_font_plan(plan)


def test_hash_failure_does_not_return_partial_proof(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    other = tmp_path / 'other.ttf'
    other.write_bytes(b'x')
    plan[str(other)] = dict(bytes=1, sha256=hashlib.sha256(b'x').hexdigest())
    original = module.file_hash
    def read(path):
        if path == other:
            raise OSError('Cannot read font')
        return original(path)
    monkeypatch.setattr(module, 'file_hash', read)
    with pytest.raises(OSError, match='Cannot read'):
        module.verify_font_plan(plan)


def test_cached_proof_does_not_hide_same_size_same_mtime_content_change(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    proof = module.verify_font_plan(plan)
    before = first.stat()
    first.write_bytes(b'x' * before.st_size)
    os.utime(first, ns=(before.st_atime_ns, before.st_mtime_ns))
    calls = []
    original = module.file_hash
    def read(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(module, 'file_hash', read)
    with pytest.raises(ValueError, match='bytes differ'):
        module.verify_font_plan(plan, proof)
    assert calls


def test_new_inode_with_identical_bytes_and_mtime_gets_fully_rehashed(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    proof = module.verify_font_plan(plan)
    before = first.stat()
    replacement = tmp_path / 'replacement.ttf'
    replacement.write_bytes(first.read_bytes())
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(replacement, first)
    calls = []
    original = module.file_hash
    def read(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(module, 'file_hash', read)
    updated = module.verify_font_plan(plan, proof)
    assert first in calls
    assert updated[str(first)] != proof[str(first)]


def test_platform_without_change_time_never_reuses_byte_proof(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    proof = module.verify_font_plan(plan)
    monkeypatch.setattr(module, 'BYTE_PROOF_REUSE', False)
    calls, original = [], module.file_hash
    def read(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(module, 'file_hash', read)
    assert module.verify_font_plan(plan, proof) == proof
    assert calls == [first]


def test_missing_inode_identity_never_reuses_byte_proof(tmp_path, monkeypatch):
    first, alias, plan = fixture_plan(tmp_path)
    original_stamp = module.file_stamp
    def without_inode(path):
        before = original_stamp(path)
        return (before[0], 0, *before[2:])
    monkeypatch.setattr(module, 'file_stamp', without_inode)
    proof = module.verify_font_plan(plan)
    calls, original = [], module.file_hash
    def read(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(module, 'file_hash', read)
    module.verify_font_plan(plan, proof)
    assert calls == [first, alias]

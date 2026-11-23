"""Synthetic proof-contract tests, never a native build or device certificate."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import struct
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROOF = load('proof_contract', 'android_native_proof.py')


@pytest.fixture(scope='module')
def native():
    raw = bytearray(20 * 1024**2 + 1)
    raw[:4] = b'\x7fELF'
    struct.pack_into('<H', raw, 18, 183)
    return bytes(raw)


@pytest.fixture
def proof(native):
    inputs, paths = PROOF.canonical()
    return dict(inputs, schema=1, state='LINKED_NOT_DEVICE_VERIFIED', abi='arm64-v8a', clean_link=True,
        real_device_verified=False, build_command=PROOF.BUILD, compiled_units=sorted(PROOF.UNITS),
        source_files={path: 'a' * 64 for path in paths}, patched_tree='b' * 40,
        native_sha256=PROOF.digest(native), native_bytes=len(native),
        compile_database_sha256='c' * 64, cmake_cache_sha256='d' * 64,
        compiler_sha256='e' * 64, build_log_sha256='f' * 64)


def test_complete_contract_binds_exact_bytes_and_current_series(proof, native):
    assert PROOF.validate(proof, native, 'arm64-v8a') is proof


@pytest.mark.parametrize('field,value', [
    ('state', 'COMPILED_NOT_LINKED'), ('state', 'NOT_TESTED'), ('state', 'FAILED_NOT_PROVEN'),
    ('schema', True), ('clean_link', False), ('real_device_verified', True),
    ('source_base', 'a' * 40), ('series_sha256', '0' * 64), ('builder_sha256', '0' * 64),
    ('toolchain_lock_sha256', '0' * 64), ('native_sha256', '0' * 64),
    ('build_command', ['make']), ('compiled_units', []), ('source_files', {}),
    ('patched_tree', ''), ('compiler_sha256', ''), ('compile_database_sha256', ''),
])
def test_unproven_or_stale_claim_is_rejected(proof, native, field, value):
    proof[field] = value
    with pytest.raises(ValueError):
        PROOF.validate(proof, native, 'arm64-v8a')


def test_abi_changed_binary_and_patch_inventory_rejected(proof, native):
    with pytest.raises(ValueError):
        PROOF.validate(proof, native, 'armeabi-v7a')
    with pytest.raises(ValueError):
        PROOF.validate(proof, native[:-1] + b'x', 'arm64-v8a')
    proof['patches'] = {}
    with pytest.raises(ValueError):
        PROOF.validate(proof, native, 'arm64-v8a')


def test_missing_toolchain_cannot_produce_a_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(PROOF.shutil, 'which', lambda _: None)
    output = tmp_path / 'not-produced.json'
    with pytest.raises(ValueError, match='TOOLCHAIN_UNAVAILABLE'):
        PROOF.build(tmp_path / 'source', tmp_path / 'build', 'arm64-v8a', output)
    assert not output.exists()


def test_duplicate_proof_field_rejected(tmp_path):
    path = tmp_path / 'proof.json'
    path.write_text('{"state":"NOT_TESTED","state":"LINKED_NOT_DEVICE_VERIFIED"}')
    with pytest.raises(ValueError, match='Duplicate'):
        PROOF.read_json(path)


def test_stage_rejects_proof_before_any_destination_write(tmp_path, monkeypatch, proof, native):
    monkeypatch.syspath_prepend(str(ROOT))
    stage = load('android_host_stage', 'stage-android-host.py')
    library, receipt = tmp_path / 'native.so', tmp_path / 'proof.json'
    library.write_bytes(native)
    proof['state'] = 'COMPILED_NOT_LINKED'
    receipt.write_text(json.dumps(proof))
    destination = tmp_path / 'apk'
    with pytest.raises(ValueError, match='complete clean Android link'):
        stage.stage(destination, 'arm64-v8a', tmp_path / 'engine', library,
                    tmp_path / 'probe', tmp_path / 'fonts', receipt)
    assert not destination.exists()


@pytest.mark.parametrize('case', ['compilation_only', 'embedded_drift'])
def test_signing_rejects_before_private_key_access_even_with_legacy_flag(tmp_path, monkeypatch, proof, native, case):
    monkeypatch.syspath_prepend(str(ROOT))
    signer = load('android_host_sign', 'sign-host-apk.py')
    apk, receipt = tmp_path / 'input.apk', tmp_path / 'proof.json'
    host = {'native_build_proof': deepcopy(proof)}
    if case == 'compilation_only':
        proof['state'] = 'COMPILED_NOT_LINKED'
    else:
        host['native_build_proof']['series_sha256'] = '0' * 64
    receipt.write_text(json.dumps(proof))
    with zipfile.ZipFile(apk, 'w') as archive:
        archive.writestr('lib/arm64-v8a/libkodi.so', native)
        archive.writestr('assets/system/bobbi-android-host.json', json.dumps(host))
    output = tmp_path / 'never-signed.apk'
    monkeypatch.setattr(sys, 'argv', ['sign-host-apk.py', str(apk), str(output),
        '--abi', 'arm64-v8a', '--manifest', str(tmp_path / 'manifest.json'),
        '--native-proof', str(receipt), '--private-root', str(tmp_path / 'absent-private'), '--allow-legacy-host'])
    with pytest.raises(ValueError, match='complete clean Android link|independent canonical build proof'):
        signer.main()
    assert not output.exists()

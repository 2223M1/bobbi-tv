"""Receipt-less diagnosis is pure read, including when bootstrap is absent."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest

from test_ce_general_installer import signing, package

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ce_inspection', ROOT/'tools/inspect_ce_deployment.py')
inspection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspection)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_hashes(run):
    return {name: digest(run/name) for name in ('candidate.zip', 'controller.py', 'ce_state_migration.py')}


def tree(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob('*') if p.is_file()}


@pytest.fixture
def staged(tmp_path, signing):
    run = tmp_path/'run'
    run.mkdir()
    package(run/'candidate.zip', signing)
    (run/'controller.py').write_bytes((ROOT/'tools/deploy_ce_remote.py').read_bytes())
    (run/'ce_state_migration.py').write_text('raise AssertionError("Must not import migration")', encoding='utf-8')
    modules = []
    root = ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform'
    for name in ('updates', 'upstream_addons', 'signatures', 'offline_updates', 'ce_storage'):
        source = (root/(name+'.py')).read_text(encoding='utf-8')
        modules.append(dict(name=name, source=source, sha256=hashlib.sha256(source.encode()).hexdigest()))
    capacity = dict(runtime=dict(modules=modules, trust=signing[1]), layout=[], candidate_sha256=digest(run/'candidate.zip'))
    return run, capacity


def inspect(run, capacity, monkeypatch, *, hashes=None, loader=None):
    calls = []
    def show(args, timeout):
        assert args[:2] == ['systemctl', 'show']
        assert args[2] in ('kodi.service', 'bobitv-preparation.service')
        assert args[3] in ('--property=ActiveState', '--property=MainPID', '--property=UnitFileState')
        assert args[4] == '--value' and timeout == 4
        calls.append(args)
        return b'active\n'
    monkeypatch.setattr(subprocess, 'check_output', show)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('No subprocess mutation'))
    monkeypatch.setattr(subprocess, 'call', lambda *a, **kw: pytest.fail('No service control'))
    previous = {k: v for k, v in sys.modules.items() if k == '_bobbi_capacity' or k.startswith('_bobbi_capacity.')}
    before_path = list(sys.path)
    namespace = dict(RUN=str(run), HASHES=hashes if hashes is not None else frozen_hashes(run),
        CAPACITY=capacity, RUNTIME_LOADER=inspection.runtime_loader() if loader is None else loader,
        re_safe=lambda v: bool(re.fullmatch('[A-Z0-9_]{1,100}', v)))
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            exec(inspection.REMOTE, namespace)
        assert sys.path == before_path
        assert len(calls) == 6
        return json.loads(output.getvalue())
    finally:
        for name in list(sys.modules):
            if name == '_bobbi_capacity' or name.startswith('_bobbi_capacity.'):
                sys.modules.pop(name)
        sys.modules.update(previous)


def test_current_frozen_runtime_verifies_real_signed_bundle_without_bootstrap(staged, monkeypatch):
    run, capacity = staged
    before = tree(run)
    def forbidden(*args, **kwargs):
        pytest.fail('No extraction')
    monkeypatch.setattr(zipfile.ZipFile, 'extract', forbidden)
    monkeypatch.setattr(zipfile.ZipFile, 'extractall', forbidden)
    loader = inspection.runtime_loader() + '''
def forbidden(*args, **kwargs):
    raise AssertionError('No engine, lease, recovery or extraction')
package.updates.UpdateEngine.__init__=forbidden
package.offline_updates.SignedBundle.engine=forbidden
'''
    result = inspect(run, capacity, monkeypatch, loader=loader)
    assert result['diagnostic_scope'] == 'signed-bundle-read-only'
    assert result['current_signature_verified'] and result['input_hashes_verified']
    assert result['manifest']['sequence'] == 1
    assert 'precondition_error' not in result
    assert not (run/'bootstrap').exists()
    assert tree(run) == before


def test_legacy_run_hash_only_never_imports_controller_or_candidate(staged, monkeypatch):
    run, _ = staged
    (run/'controller.py').write_text('raise AssertionError("Legacy controller must not execute")', encoding='utf-8')
    before = tree(run)
    result = inspect(run, None, monkeypatch, loader='raise AssertionError("No runtime load")')
    assert result['diagnostic_scope'] == 'frozen-input-hash-only'
    assert result['input_hashes_verified']
    assert result['current_signature_verified'] is False
    assert result['not_checked'] == ['account_state', 'native_binary', 'deployment_preconditions']
    assert result['manifest']['sequence'] == 1
    assert not (run/'bootstrap').exists() and tree(run) == before


@pytest.mark.parametrize('name', ['candidate.zip', 'controller.py', 'ce_state_migration.py'])
@pytest.mark.parametrize('capacity_present', [False, True])
def test_missing_frozen_input_rejects_without_creating_bootstrap(staged, monkeypatch, name, capacity_present):
    run, capacity = staged
    hashes = frozen_hashes(run)
    (run/name).unlink()
    before = tree(run)
    result = inspect(run, capacity if capacity_present else None, monkeypatch, hashes=hashes)
    assert result['precondition_error']['code'] == 'DEPLOY_INPUT_MISSING'
    assert result['current_signature_verified'] is False
    assert 'input_hashes_verified' not in result
    assert not (run/'bootstrap').exists() and tree(run) == before


@pytest.mark.parametrize('name', ['candidate.zip', 'controller.py', 'ce_state_migration.py'])
@pytest.mark.parametrize('capacity_present', [False, True])
def test_bad_input_hash_rejects_before_runtime_or_controller(staged, monkeypatch, name, capacity_present):
    run, capacity = staged
    hashes = frozen_hashes(run)
    hashes[name] = '0'*64
    before = tree(run)
    result = inspect(run, capacity if capacity_present else None, monkeypatch, hashes=hashes,
                     loader='raise AssertionError("Must not load on bad input")')
    assert result['precondition_error']['code'] == 'DEPLOY_INPUT_HASH'
    assert not result['current_signature_verified']
    assert not (run/'bootstrap').exists() and tree(run) == before


@pytest.mark.parametrize('hashes', [{}, {'../outside': '0'*64}, {'candidate.zip': '0'*64, 'controller.py': 'private'}])
def test_invalid_frozen_input_paths_and_hash_fields_rejected(staged, monkeypatch, hashes):
    run, capacity = staged
    result = inspect(run, capacity, monkeypatch, hashes=hashes)
    assert result['precondition_error']['code'] == 'DEPLOY_INPUT_FIELDS'
    assert not (run/'bootstrap').exists()


def test_real_symlink_input_rejected(staged, monkeypatch):
    run, capacity = staged
    original = run/'controller.py'
    other = run/'stored-controller.py'
    original.rename(other)
    try:
        original.symlink_to(other)
    except OSError:
        pytest.skip('This Windows account cannot create symbolic links')
    result = inspect(run, capacity, monkeypatch)
    assert result['precondition_error']['code'] == 'DEPLOY_INPUT_PATH'
    assert not (run/'bootstrap').exists()


def test_capacity_digest_and_runtime_source_hash_fail_closed(staged, monkeypatch):
    run, capacity = staged
    capacity['candidate_sha256'] = '0'*64
    result = inspect(run, capacity, monkeypatch)
    assert result['precondition_error']['code'] == 'DEPLOY_CAPACITY_INPUT_HASH'
    capacity['candidate_sha256'] = digest(run/'candidate.zip')
    capacity['runtime']['modules'][0]['sha256'] = '0'*64
    result = inspect(run, capacity, monkeypatch)
    assert result['precondition_error']['code'] == 'DEPLOY_CAPACITY_INPUT_HASH'
    assert not (run/'bootstrap').exists()


def test_bad_current_signature_is_not_promoted_by_good_outer_hash(staged, monkeypatch):
    run, capacity = staged
    with zipfile.ZipFile(run/'candidate.zip') as source:
        content = {row.filename: source.read(row) for row in source.infolist()}
    content['release.sig'] = b'invalid-signature'
    with zipfile.ZipFile(run/'candidate.zip', 'w') as target:
        for name, raw in content.items():
            target.writestr(name, raw)
    capacity['candidate_sha256'] = digest(run/'candidate.zip')
    before = tree(run)
    result = inspect(run, capacity, monkeypatch)
    assert result['current_signature_verified'] is False
    assert 'precondition_error' in result and 'manifest' not in result
    assert not (run/'bootstrap').exists() and tree(run) == before
    legacy = inspect(run, None, monkeypatch)
    assert legacy['diagnostic_scope'] == 'frozen-input-hash-only'
    assert legacy['input_hashes_verified'] and legacy['current_signature_verified'] is False
    assert legacy['manifest']['sequence'] == 1


@pytest.mark.parametrize('fault', ['missing', 'oversize', 'malformed', 'duplicate'])
def test_legacy_manifest_is_bounded_and_unambiguous(staged, monkeypatch, fault):
    run, _ = staged
    with zipfile.ZipFile(run/'candidate.zip', 'w') as target:
        if fault != 'missing':
            value = b'x'*(1024*1024+1) if fault == 'oversize' else b'invalid'
            target.writestr('release.json', value)
            if fault == 'duplicate':
                with pytest.warns(UserWarning):
                    target.writestr('release.json', value)
    result = inspect(run, None, monkeypatch)
    assert result['current_signature_verified'] is False
    assert 'precondition_error' in result
    assert not (run/'bootstrap').exists()


def test_candidate_hashing_streams_and_never_reads_whole_archive(staged, monkeypatch):
    run, _ = staged
    hashes = frozen_hashes(run)
    original = Path.read_bytes
    def read_bytes(path):
        if path == run/'candidate.zip':
            pytest.fail('Candidate must be hashed in bounded chunks')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    result = inspect(run, None, monkeypatch, hashes=hashes)
    assert result['input_hashes_verified']


def test_receipt_branch_keeps_original_display_and_never_loads_inputs(staged, monkeypatch):
    run, capacity = staged
    (run/'deployment.json').write_text(json.dumps(dict(state='failed', flags={'private': True}, phase='stage')), encoding='utf-8')
    (run/'candidate.zip').unlink()
    result = inspect(run, capacity, monkeypatch, hashes={}, loader='raise AssertionError("Do not inspect inputs when receipt exists")')
    assert result['receipt_exists']
    assert result['receipt'] == dict(state='failed', phase='stage')
    assert set(result) == {'receipt_exists', 'receipt', 'units', 'new_profiles'}
    assert not (run/'bootstrap').exists()


def test_receipt_link_is_rejected_before_any_read_or_service_query(staged, monkeypatch):
    run, capacity = staged
    receipt = run/'deployment.json'
    receipt.write_text('{}', encoding='utf-8')
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == receipt or original(path))
    with pytest.raises(ValueError, match='DEPLOY_INPUT_PATH'):
        inspect(run, capacity, monkeypatch)


def test_script_uses_exact_driver_runtime_loader_only_for_new_runs(monkeypatch):
    run_id = '20261114-123456'
    frozen = dict(run='/storage/.local/share/bobbi-private-deploy/'+run_id, hashes={})
    monkeypatch.setattr(inspection, 'runtime_loader', lambda: pytest.fail('Legacy run must not load runtime'))
    assert 'CAPACITY=None' in inspection.script_for(run_id, frozen)
    monkeypatch.setattr(inspection, 'runtime_loader', lambda: 'trusted-loader')
    frozen['capacity'] = {'runtime': 'frozen'}
    assert "RUNTIME_LOADER='trusted-loader'" in inspection.script_for(run_id, frozen)
    for value in ('../outside', '20261114-123456/extra'):
        with pytest.raises(ValueError, match='DEPLOY_RUN_ID'):
            inspection.script_for(value, frozen)
    frozen['run'] = '/elsewhere'
    with pytest.raises(ValueError, match='Deployment run identity changed'):
        inspection.script_for(run_id, frozen)


@pytest.fixture
def local_inspection(tmp_path, monkeypatch):
    run_id = '20261114-123456'
    records = tmp_path/'review-evidence/ce-deploy-runs'
    records.mkdir(parents=True)
    record = dict(run='/storage/.local/share/bobbi-private-deploy/'+run_id, hashes={})
    (records/(run_id+'.json')).write_text(json.dumps(record), encoding='utf-8')
    monkeypatch.setattr(inspection, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    return run_id, tmp_path/'review-evidence'/('ce-'+run_id+'-inspect.json')


def test_existing_default_inspection_refuses_before_transport(local_inspection, monkeypatch):
    run_id, output = local_inspection
    output.write_bytes(b'old evidence must survive')
    monkeypatch.setattr(inspection.importlib.util, 'spec_from_file_location',
        lambda *a: pytest.fail('No transport load before output reservation'))
    with pytest.raises(FileExistsError):
        inspection.main(['--run-id', run_id, '--transport-source', 'unused'])
    assert output.read_bytes() == b'old evidence must survive'


@pytest.mark.parametrize('kind', ['missing-parent', 'link'])
def test_invalid_output_refuses_before_transport(local_inspection, monkeypatch, kind):
    run_id, default = local_inspection
    output = default.parent/'missing'/'inspect.json' if kind == 'missing-parent' else default
    if kind == 'link':
        original = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink', lambda path: path == output or original(path))
    monkeypatch.setattr(inspection.importlib.util, 'spec_from_file_location',
        lambda *a: pytest.fail('No transport load before output preflight'))
    with pytest.raises(ValueError, match='DEPLOY_INSPECTION_OUTPUT_PATH'):
        inspection.main(['--run-id', run_id, '--transport-source', 'unused', '--output', str(output)])
    assert not output.exists()


@pytest.mark.parametrize('connect_failure', [False, True])
def test_custom_output_reserved_before_connection_and_kept_on_failure(local_inspection, monkeypatch, connect_failure):
    run_id, default = local_inspection
    output = default.with_name('new-independent-inspection.json')
    calls = []
    def connect():
        assert json.loads(output.read_bytes()) == dict(state='unconfirmed', operation='deployment-inspection')
        calls.append('connect')
        if connect_failure:
            raise OSError('synthetic connection failure')
        client = SimpleNamespace(close=lambda: calls.append('close'))
        wire = SimpleNamespace(readonly=lambda client, script, deadline_seconds: (0, dict(receipt_exists=False), ''))
        return client, wire
    loader = SimpleNamespace(exec_module=lambda module: setattr(module, 'connect', connect))
    monkeypatch.setattr(inspection.importlib.util, 'spec_from_file_location', lambda *a: SimpleNamespace(loader=loader))
    monkeypatch.setattr(inspection.importlib.util, 'module_from_spec', lambda spec: SimpleNamespace())
    args = ['--run-id', run_id, '--transport-source', 'unused', '--output', str(output)]
    with redirect_stdout(io.StringIO()):
        if connect_failure:
            with pytest.raises(OSError):
                inspection.main(args)
        else:
            inspection.main(args)
    assert not default.exists()
    assert calls == (['connect'] if connect_failure else ['connect', 'close'])
    expected = dict(state='unconfirmed', operation='deployment-inspection') if connect_failure else dict(receipt_exists=False)
    assert json.loads(output.read_bytes()) == expected

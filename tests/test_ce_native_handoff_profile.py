"""CE2035 uses the existing maintainer transaction with separately pinned inputs."""
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_ce_native_reapply import harness, tool


def digest(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    old, candidate, conf = b'old native', b'handoff native', b'old dropin'
    monkeypatch.setattr(tool, 'OLD', digest(old))
    monkeypatch.setattr(tool, 'OLD_CONF', digest(conf))
    launch = ('FIX=' + digest(old) + '\nunchanged launcher behavior\n').encode()
    monkeypatch.setattr(tool, 'OLD_LAUNCH', digest(launch))
    baseline = tmp_path/'baseline'
    build = tmp_path/'handoff'
    baseline.mkdir()
    build.mkdir()
    (baseline/'baseline.bin').write_bytes(old)
    (build/'candidate.bin').write_bytes(candidate)
    proof = dict(state='BUILT_NOT_DEPLOYED', original_tree_unchanged=True,
                 baseline_sha256=digest(old), inputs={'verified-original-object': 'original-digest'})
    proof_path = baseline/'build-result.json'
    proof_path.write_text(json.dumps(proof))
    result = dict(proof, candidate_sha256=digest(candidate), baseline_proof=proof_path.as_posix())
    result_path = build/'build-result.json'
    result_path.write_text(json.dumps(result))
    profile = dict(tool.PROFILES['handoff2035'], candidate=digest(candidate),
                   baseline_proof=proof_path.as_posix(), baseline_proof_sha256=tool.sha_file(proof_path))
    layout = dict(files={
        '/storage/.am6b-repair284/native/launch.py': dict(source=launch.decode(), sha256=digest(launch)),
        '/storage/.am6b-repair284/native/kodi.bin': dict(sha256=digest(old))},
        dropins={'/storage/.config/system.d/kodi.service.d/60-am6b-subtitle284.conf': dict(sha256=digest(conf))},
        running=[dict(pid='123', sha256=digest(old))])
    layout_path = tmp_path/'layout.json'
    layout_path.write_text(json.dumps(layout))
    return SimpleNamespace(profile=profile, result=result, result_path=result_path, proof=proof,
                           proof_path=proof_path, layout=layout, layout_path=layout_path,
                           candidate=candidate, launch=launch)


def test_handoff_accepts_referenced_real_baseline_without_fabricated_control(artifacts):
    a = artifacts
    assert 'control_sha256' not in a.result
    files = tool.staged_files(a.result_path, a.profile, a.layout_path)
    assert files['kodi.bin'] == a.candidate
    assert files['launch.py'] == a.launch.replace(tool.OLD.encode(), a.profile['candidate'].encode())
    assert b'/2026102035/kodi.bin:' in files['next.conf']
    assert b'/2026102035/launch.py ' in files['next.conf']
    assert b'2026101908' not in files['next.conf']


@pytest.mark.parametrize('failure', ['candidate', 'proof_reference', 'proof_bytes', 'baseline_binary',
                                      'different_inputs', 'old_binary', 'dropin', 'launch', 'running'])
def test_handoff_rejects_unpinned_artifacts_and_layout_before_transport(artifacts, failure):
    a = artifacts
    if failure == 'candidate':
        (a.result_path.parent/'candidate.bin').write_bytes(b'changed')
    elif failure == 'proof_reference':
        a.result['baseline_proof'] = 'some-other-proof.json'
        a.result_path.write_text(json.dumps(a.result))
    elif failure == 'proof_bytes':
        a.proof_path.write_text(a.proof_path.read_text() + '\n')
    elif failure == 'baseline_binary':
        (a.proof_path.parent/'baseline.bin').write_bytes(b'changed')
    elif failure == 'different_inputs':
        a.result['inputs'] = {'verified-original-object': 'different-digest'}
        a.result_path.write_text(json.dumps(a.result))
    else:
        if failure == 'old_binary':
            a.layout['files']['/storage/.am6b-repair284/native/kodi.bin']['sha256'] = 'wrong'
        elif failure == 'dropin':
            a.layout['dropins']['/storage/.config/system.d/kodi.service.d/60-am6b-subtitle284.conf']['sha256'] = 'wrong'
        elif failure == 'launch':
            a.layout['files']['/storage/.am6b-repair284/native/launch.py']['source'] += '# changed'
        else:
            a.layout['running'] = []
        a.layout_path.write_text(json.dumps(a.layout))
    with pytest.raises(AssertionError):
        tool.staged_files(a.result_path, a.profile, a.layout_path)


def initial_handoff(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    original_path = h.ns['pathlib'].Path
    h.ns['pathlib'] = SimpleNamespace(Path=lambda value:
        h.generation if str(value) == tool.ENTRY_GENERATION_PATH else original_path(value))
    h.ns.update(MODE='apply', REQUIRED_SEQUENCE=2026102035, PROFILE_TAG='2035',
                GENERATION_KIND='entry_complete', GENERATION_PATH=tool.ENTRY_GENERATION_PATH)
    h.generation.write_text(json.dumps(dict(schema=1, sequence=2026102035,
        high_watermark=2026102035, phase='complete', tx='a'*32)))
    h.receipt.unlink()
    (h.base/'previous.conf').unlink()
    return h


@pytest.mark.parametrize('sequence', [2026101908, 2026102034, 2026102036, True, '2026102035'])
def test_handoff_initial_apply_requires_exact_program_generation(tmp_path, monkeypatch, sequence):
    h = initial_handoff(tmp_path, monkeypatch)
    h.generation.write_text(json.dumps(dict(sequence=sequence)))
    with pytest.raises(AssertionError):
        h.run()
    assert not h.calls and not h.receipt.exists()
    assert h.conf.read_bytes() == h.old_conf


def test_handoff_apply_rollback_reapply_keeps_same_transaction_and_old_overlay(tmp_path, monkeypatch):
    h = initial_handoff(tmp_path, monkeypatch)
    original_binary = h.oldbin.read_bytes()
    original_generation = h.generation.read_bytes()
    h.run()
    assert json.loads(h.receipt.read_text())['state'] == 'applied'
    assert (h.base/'previous.conf').read_bytes() == h.old_conf
    h.ns['MODE'] = 'rollback'
    h.run()
    assert h.conf.read_bytes() == h.old_conf
    h.ns['MODE'] = 'reapply'
    h.run()
    record = json.loads(h.receipt.read_text())
    assert record['state'] == 'applied' and record['action'] == 'reapply'
    assert any(row['state'] == 'rolled_back' for row in record['history'])
    assert h.oldbin.read_bytes() == original_binary
    assert h.generation.read_bytes() == original_generation


def test_handoff_restart_failure_restores_only_the_original_dropin(tmp_path, monkeypatch):
    h = initial_handoff(tmp_path, monkeypatch)
    h.state['fail_start_once'] = True
    original_binary = h.oldbin.read_bytes()
    with pytest.raises(RuntimeError, match='injected'):
        h.run()
    assert h.conf.read_bytes() == h.old_conf
    assert h.oldbin.read_bytes() == original_binary
    record = json.loads(h.receipt.read_text())
    assert record['state'] == 'recovered_after_failure' and record['recovered'] is True


def test_legacy_profile_pins_and_paths_remain_unchanged():
    old, new = tool.PROFILES['directory1908'], tool.PROFILES['handoff2035']
    assert old['candidate'] == tool.CANDIDATE == 'd750a88c3dc041d17ea34d06e2b2ddadcf4db0f9fffdaaa727c8a6b7427f21d3'
    assert old['sequence'] == 2026101908 and old['tag'] == '1908' and old['deadline'] == 110
    assert old['base'] == '/storage/.local/share/bobbi-native/2026101908'
    assert old['reports'] == tool.ROOT/'review-evidence'
    assert new['candidate'] == '632758f5d1ca5494e9b049446d3908bead70589b4d18640bb5d06e830a2b57eb'
    assert new['base'] != old['base'] and new['tag'] != old['tag']
    assert new['generation_path'] == tool.ENTRY_GENERATION_PATH
    assert new['generation_kind'] == 'entry_complete'


def test_handoff_stage_cli_uses_separate_stage_and_reports(artifacts, monkeypatch, tmp_path):
    a = artifacts
    monkeypatch.setitem(tool.PROFILES, 'handoff2035', a.profile)
    staged, directories, remote = {}, [], {}
    class StageFile(io.BytesIO):
        def __init__(self, path):
            super().__init__()
            self.path = path
        def __exit__(self, *args):
            staged[self.path] = self.getvalue()
            return super().__exit__(*args)
    class Sftp:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def mkdir(self, path): directories.append(path)
        def chmod(self, path, mode): pass
        def open(self, path, mode):
            assert mode == 'wx'
            return StageFile(path)
    client = SimpleNamespace(open_sftp=lambda: Sftp(), close=lambda: None)
    def readonly(connection, script, deadline_seconds):
        assert connection is client
        remote.update(script=script.decode(), deadline=deadline_seconds)
        return 0, {'receipt': 'stage-checked', 'staged_valid': True}, ''
    wire = SimpleNamespace(readonly=readonly)
    def execute(module): module.connect = lambda: (client, wire)
    monkeypatch.setattr(tool.importlib.util, 'spec_from_file_location',
                        lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=execute)))
    monkeypatch.setattr(tool.importlib.util, 'module_from_spec', lambda spec: SimpleNamespace())
    reports = tmp_path/'reports'
    reports.mkdir()
    previous = reports/'ce-native1908-stage-existing.json'
    previous.write_text('preserved')
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(sys, 'argv', ['ce_native_update.py', '--profile', 'handoff2035',
        '--transport-source', str(tmp_path), '--mode', 'stage', '--build-result', str(a.result_path),
        '--baseline-layout', str(a.layout_path), '--report-dir', str(reports)])
    tool.main()
    assert directories[-1] == '/storage/.local/share/bobbi-native/2026102035'
    assert len(staged) == 3 and all('/2026102035/' in name for name in staged)
    assert "REQUIRED_SEQUENCE=2026102035" in remote['script'] and remote['deadline'] == 330
    assert previous.read_text() == 'preserved'
    assert len(list(reports.glob('ce-native2035-stage-*.json'))) == 1

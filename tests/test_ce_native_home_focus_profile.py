"""The focus-only successor keeps completion and both maintenance chains intact."""
import json

import pytest

from test_ce_native_completion_profile import candidate, private_fixture
from test_ce_native_reapply import tool


@pytest.fixture
def focus_candidate(candidate):
    path, profile, report = candidate
    unit = 'xbmc/guilib/listproviders/DirectoryProvider.cpp'
    obj = path.parent/'DirectoryProvider.cpp.o'
    obj.write_bytes(b'production-directory-provider-object')
    dep = path.parent/'DirectoryProvider.cpp.o.d'
    dep.write_bytes(b'production-directory-provider-dependencies')
    report['objects'] = {unit: dict(sha256=tool.sha_file(obj), depfile_sha256=tool.sha_file(dep))}
    tests = dict(passed=True, tests=[])
    proof = path.parent/'production-tests/proof/result.json'
    for name, code in (('candidate', 0), ('pre_fix_negative_control', 1), ('update_only_negative_control', 1)):
        folder = proof.parent/name
        folder.mkdir(parents=True)
        source = folder/'actual_directory_visibility.inc'
        source.write_text(name+' production methods')
        binary = folder/'directory-visibility-test'
        binary.write_bytes(name.encode())
        tests['tests'].append(dict(name=name, passed=True, exit_code=code,
            extracted_sha256=tool.sha_file(source), binary_sha256=tool.sha_file(binary)))
    proof.write_text(json.dumps(tests))
    profile.update(build_kind='home_focus', predecessor_proof_sha256='b'*64)
    report.update(build_kind='home_focus', predecessor_unchanged=True,
        predecessor_proof_sha256='b'*64, completion_archives_unchanged=True,
        recompiled_units=[unit], production_tests=dict(path=proof.relative_to(path.parent).as_posix(),
            sha256=tool.sha_file(proof), candidate_passed=True, negative_control_failed=True,
            interleaved_control_failed=True))
    path.write_text(json.dumps(report))
    profile['build_proof_sha256'] = tool.sha_file(path)
    return path, profile, report, proof


def test_focus_candidate_requires_the_pinned_one_unit_production_proof(focus_candidate):
    path, profile, report, _ = focus_candidate
    assert tool.checked_build(path, profile)[0] == report


@pytest.mark.parametrize('damage', ['predecessor', 'proof', 'completion', 'unit', 'positive', 'negative', 'interleaved', 'path'])
def test_focus_rejects_incomplete_claim_even_when_outer_report_is_repinned(focus_candidate, damage):
    path, profile, report, _ = focus_candidate
    if damage == 'predecessor': report['predecessor_unchanged'] = False
    if damage == 'proof': report['predecessor_proof_sha256'] = 'c'*64
    if damage == 'completion': report['completion_archives_unchanged'] = False
    if damage == 'unit': report['recompiled_units'].append('xbmc/cores/VideoPlayer/VideoPlayer.cpp')
    if damage == 'positive': report['production_tests']['candidate_passed'] = False
    if damage == 'negative': report['production_tests']['negative_control_failed'] = False
    if damage == 'interleaved': report['production_tests']['interleaved_control_failed'] = False
    if damage == 'path': report['production_tests']['path'] = '../foreign/result.json'
    path.write_text(json.dumps(report))
    profile['build_proof_sha256'] = tool.sha_file(path)
    with pytest.raises(AssertionError): tool.checked_build(path, profile)


@pytest.mark.parametrize('damage', ['proof', 'candidate_source', 'candidate_binary', 'control_source', 'control_binary',
                                  'interleaved_source', 'interleaved_binary'])
def test_focus_rejects_changed_production_test_artifacts(focus_candidate, damage):
    path, profile, _, proof = focus_candidate
    target = proof
    if damage != 'proof':
        name = 'candidate' if damage.startswith('candidate_') else 'pre_fix_negative_control'
        if damage.startswith('interleaved_'): name = 'update_only_negative_control'
        filename = 'actual_directory_visibility.inc' if damage.endswith('_source') else 'directory-visibility-test'
        target = proof.parent/name/filename
    target.write_bytes(b'changed')
    with pytest.raises(AssertionError): tool.checked_build(path, profile)


@pytest.mark.parametrize('damage', ['control_passed', 'control_boolean', 'interleaved_passed',
                                  'interleaved_boolean', 'missing_control', 'test_failed'])
def test_focus_negative_control_must_actually_fail(focus_candidate, damage):
    path, profile, report, proof = focus_candidate
    tests = json.loads(proof.read_text())
    if damage == 'control_passed': tests['tests'][1]['exit_code'] = 0
    if damage == 'control_boolean': tests['tests'][1]['exit_code'] = True
    if damage == 'interleaved_passed': tests['tests'][2]['exit_code'] = 0
    if damage == 'interleaved_boolean': tests['tests'][2]['exit_code'] = True
    if damage == 'missing_control': tests['tests'].pop()
    if damage == 'test_failed': tests['passed'] = False
    proof.write_text(json.dumps(tests))
    report['production_tests']['sha256'] = tool.sha_file(proof)
    path.write_text(json.dumps(report))
    profile['build_proof_sha256'] = tool.sha_file(path)
    with pytest.raises(AssertionError): tool.checked_build(path, profile)


def test_focus_profile_uses_a_distinct_overlay_and_completion_as_rollback():
    focus = tool.PROFILES['homefocus2116']
    completion = tool.PROFILES['completion2114']
    assert focus['sequence'] == 2026102116
    assert focus['predecessor']['binary'] == completion['candidate']
    assert focus['predecessor']['binary_path'] == completion['base']+'/kodi.bin'
    assert focus['base'] != completion['base']
    assert completion['predecessor']['binary'] == tool.PROFILES['schema2043']['candidate']
    assert focus['minimum_versions'] == {'plugin.video.bobbi': '0.1.59',
        'script.module.bobbi.core': '0.1.60', 'script.module.bobbi.platform': '0.1.67'}


def test_runtime_recognizes_new_focus_host_and_both_rollback_hosts():
    from bobbi_core.runtime_paths import known_ce_native
    for name in ('homefocus2116', 'completion2114', 'schema2043'):
        assert known_ce_native(tool.PROFILES[name]['candidate'])


def test_focus_apply_accepts_only_current_2116_and_preserves_generation(tmp_path, monkeypatch):
    h, addons, entry = private_fixture(tmp_path, monkeypatch)
    profile = tool.PROFILES['homefocus2116']
    versions = profile['minimum_versions']
    h.generation.write_text(json.dumps(dict(sequence=2026102116, versions=versions)))
    for ident, version in versions.items():
        (addons/ident/'addon.xml').write_text('<addon id="'+ident+'" version="'+version+'"/>')
    h.ns.update(REQUIRED_SEQUENCE=profile['sequence'], MINIMUM_VERSIONS=versions)
    before = (h.generation.read_bytes(), entry.read_bytes())
    h.run()
    assert h.ns['out']['generation']['sequence'] == 2026102116
    assert before == (h.generation.read_bytes(), entry.read_bytes())


def test_focus_apply_requires_new_core_registration_before_service_stop(tmp_path, monkeypatch):
    h, _, _ = private_fixture(tmp_path, monkeypatch)
    profile = tool.PROFILES['homefocus2116']
    state = json.loads(h.generation.read_text())
    state['sequence'] = profile['sequence']
    h.generation.write_text(json.dumps(state))
    h.ns.update(REQUIRED_SEQUENCE=profile['sequence'], MINIMUM_VERSIONS=profile['minimum_versions'])
    with pytest.raises(AssertionError, match='INSTALL_COMPATIBLE_ADDONS_FIRST'): h.run()
    assert not h.calls and not h.receipt.exists()

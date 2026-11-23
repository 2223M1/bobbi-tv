"""Schema successor keeps both historical and immediately installed provenance."""
import json

import pytest

from test_ce_native_handoff_profile import artifacts, digest
from test_ce_native_reapply import tool
from test_ce_native_successor_profile import abi_report


def schema_report(a):
    profile = abi_report(a)
    previous_binary = b'original-audio predecessor'
    previous = a.result_path.parent.parent / 'predecessor'
    previous.mkdir()
    (previous / 'candidate.bin').write_bytes(previous_binary)
    previous_path = previous / 'build-result.json'
    previous_path.write_text(json.dumps(dict(state='BUILT_NOT_DEPLOYED',
        original_tree_unchanged=True, candidate_sha256=digest(previous_binary),
        baseline_inputs=a.proof['inputs'], inputs=a.proof['inputs'])))
    a.result.update(predecessor_proof=previous_path.as_posix(),
        predecessor_sha256=digest(previous_binary),
        **{'predecessor-relink_sha256': digest(previous_binary)},
        predecessor_unchanged=True, recompiled_units=['xbmc/interfaces/json-rpc/JSONRPC.cpp'])
    a.result_path.write_text(json.dumps(a.result))
    profile.update(predecessor_proof=previous_path.as_posix(),
        predecessor_proof_sha256=tool.sha_file(previous_path),
        predecessor=dict(binary=digest(previous_binary)),
        build_proof_sha256=tool.sha_file(a.result_path))
    verification = dict(state='VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED',
        build_result_sha256=profile['build_proof_sha256'], candidate_sha256=profile['candidate'],
        predecessor_sha256=digest(previous_binary), rpc_methods_exact=True)
    verification_path = a.result_path.parent / 'artifact-verification.json'
    verification_path.write_text(json.dumps(verification))
    profile['verification_sha256'] = tool.sha_file(verification_path)
    return profile, previous_path, verification_path, verification


def test_pinned_schema_successor_and_historical_baseline_are_both_required(artifacts):
    a = artifacts
    profile, _, _, _ = schema_report(a)
    assert tool.checked_build(a.result_path, profile)[1].read_bytes() == a.candidate
    assert a.result['baseline_sha256'] == tool.OLD
    assert a.result['predecessor_sha256'] != tool.OLD


@pytest.mark.parametrize('damage', ['previous_proof', 'previous_binary', 'verify_bytes',
    'method_validation', 'report_reference', 'relink', 'extra_unit', 'predecessor_changed'])
def test_schema_profile_rejects_unpinned_or_incomplete_chain(artifacts, damage):
    a = artifacts
    profile, previous, verification_path, verification = schema_report(a)
    if damage == 'previous_proof': previous.write_text(previous.read_text() + '\n')
    elif damage == 'previous_binary': (previous.parent / 'candidate.bin').write_bytes(b'changed')
    elif damage == 'verify_bytes': verification_path.write_text(verification_path.read_text() + '\n')
    elif damage == 'method_validation':
        verification['rpc_methods_exact'] = False
        verification_path.write_text(json.dumps(verification))
        profile['verification_sha256'] = tool.sha_file(verification_path)
    else:
        if damage == 'report_reference': a.result['predecessor_proof'] = 'other.json'
        if damage == 'relink': a.result['predecessor-relink_sha256'] = tool.OLD
        if damage == 'extra_unit': a.result['recompiled_units'].append('unexpected.cpp')
        if damage == 'predecessor_changed': a.result['predecessor_unchanged'] = False
        a.result_path.write_text(json.dumps(a.result))
        profile['build_proof_sha256'] = tool.sha_file(a.result_path)
    with pytest.raises(AssertionError):
        tool.checked_build(a.result_path, profile)


def test_schema_profile_is_a_new_generation_not_an_overwrite():
    new, old = tool.PROFILES['schema2043'], tool.PROFILES['audio2038']
    assert new['sequence'] == 2026102043
    assert new['predecessor']['binary'] == old['candidate']
    assert new['base'] != old['base']
    assert new['generation_kind'] == 'entry_complete'

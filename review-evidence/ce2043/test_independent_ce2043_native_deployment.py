"""Local deployment admission only: real frozen artifacts plus synthetic 3-layer negatives.

Never calls the maintainer CLI, SSH, device, systemctl or remote transport.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path('D:/AM6B-Project/bobbi-tv-ce2029-selfaudit-20261021')
OUT = Path('D:/AM6B-Project/ce2029-results-20261021')
RUN = Path('D:/AM6B-Project/ce2042-native-jsonrpc-schema-20261022/builds/run-1792626905471062171')
for location in (ROOT/'tests', ROOT/'tools', ROOT/'addons/script.module.bobbi.core/lib'):
    sys.path.insert(0, str(location))
from test_ce_native_reapply import tool
from test_ce_native_handoff_profile import initial_handoff
from bobbi_core import runtime_paths


def digest(value):
    return hashlib.sha256(value).hexdigest()


def test_real_artifacts_stage_exactly_three_files_from_fixed_8bb2_to_fixed_ba0327():
    profile = tool.PROFILES['schema2043']
    layout = json.loads(profile['layout'].read_text())
    files = tool.staged_files(RUN/'build-result.json', profile, profile['layout'])
    assert set(files) == {'kodi.bin', 'launch.py', 'next.conf'}
    assert files['kodi.bin'] == (RUN/'candidate.bin').read_bytes()
    assert digest(files['kodi.bin']) == profile['candidate'] == 'ba03279546193a8a5e6299b257e1321833dbf5b7b3ecc087ba67ed7dd2eb1991'
    old = profile['predecessor']
    assert old['binary'] == tool.PROFILES['audio2038']['candidate']
    launch = layout['files'][old['launch_path']]['source'].encode()
    assert digest(launch) == old['launch'] and launch.count(old['binary'].encode()) == 1
    assert files['launch.py'] == launch.replace(old['binary'].encode(), profile['candidate'].encode())
    compile(files['launch.py'], '<staged-launcher-no-execution>', 'exec')
    assert profile['base'] == '/storage/.local/share/bobbi-native/2026102043'
    assert files['next.conf'].decode() == ('[Service]\nBindReadOnlyPaths=' + profile['base'] +
        '/kodi.bin:/usr/lib/kodi/kodi.bin\nExecStart=\nExecStart=/usr/bin/python3 ' +
        profile['base'] + '/launch.py --standalone -fs $KODI_ARGS $KODI_DEBUG\n')


def test_real_three_level_inputs_are_exact_269_then_272_then_278_not_ancestor_subset():
    profile = tool.PROFILES['schema2043']
    old = json.loads(tool.local_artifact_path(profile['baseline_proof']).read_text())
    previous = json.loads(tool.local_artifact_path(profile['predecessor_proof']).read_text())
    current = json.loads((RUN/'build-result.json').read_text())
    assert [len(value['inputs']) for value in (old, previous, current)] == [269, 272, 278]
    assert previous['baseline_inputs'] == old['inputs']
    assert current['baseline_inputs'] == previous['inputs'] != old['inputs']
    assert not (current['baseline_inputs'].keys() & current['additional_inputs'].keys())
    assert current['inputs'] == dict(current['baseline_inputs'], **current['additional_inputs'])
    assert tool.checked_build(RUN/'build-result.json', profile)[1] == RUN/'candidate.bin'


@pytest.fixture
def three_layers(tmp_path, monkeypatch):
    dirs = [tmp_path/name for name in ('ancestor', 'immediate', 'candidate')]
    for directory in dirs:
        directory.mkdir()
    old_dir, previous_dir, new_dir = dirs
    old_bytes, previous_bytes, new_bytes = b'fixture-896', b'fixture-8bb2', b'fixture-ba0327'
    monkeypatch.setattr(tool, 'OLD', digest(old_bytes))
    (old_dir/'baseline.bin').write_bytes(old_bytes)
    (previous_dir/'candidate.bin').write_bytes(previous_bytes)
    (new_dir/'candidate.bin').write_bytes(new_bytes)
    old = dict(state='BUILT_NOT_DEPLOYED', original_tree_unchanged=True,
        baseline_sha256=digest(old_bytes), inputs={'old-a': 'a', 'old-b': 'b'})
    previous = dict(state='BUILT_NOT_DEPLOYED', original_tree_unchanged=True,
        candidate_sha256=digest(previous_bytes), baseline_inputs=dict(old['inputs']),
        inputs=dict(old['inputs'], predecessor_only='c'))
    current = dict(state='BUILT_NOT_DEPLOYED', original_tree_unchanged=True,
        baseline_sha256=digest(old_bytes), candidate_sha256=digest(new_bytes),
        baseline_proof=(old_dir/'build-result.json').as_posix(),
        predecessor_proof=(previous_dir/'build-result.json').as_posix(),
        baseline_inputs=dict(previous['inputs']), additional_inputs={'registrar_only': 'd'},
        inputs=dict(previous['inputs'], registrar_only='d'), predecessor_sha256=digest(previous_bytes),
        predecessor_unchanged=True, recompiled_units=['xbmc/interfaces/json-rpc/JSONRPC.cpp'])
    current['predecessor-relink_sha256'] = digest(previous_bytes)
    verification = dict(state='VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED',
        candidate_sha256=digest(new_bytes), predecessor_sha256=digest(previous_bytes), rpc_methods_exact=True)
    profile = dict(tool.PROFILES['schema2043'], candidate=digest(new_bytes),
        baseline_proof=current['baseline_proof'], predecessor_proof=current['predecessor_proof'],
        predecessor={'binary': digest(previous_bytes)})
    def save_and_pin_fixture():
        # Test-local pins permit reaching structural checks; production pins never change.
        for directory, value in ((old_dir, old), (previous_dir, previous), (new_dir, current)):
            (directory/'build-result.json').write_text(json.dumps(value))
        profile['baseline_proof_sha256'] = tool.sha_file(old_dir/'build-result.json')
        profile['predecessor_proof_sha256'] = tool.sha_file(previous_dir/'build-result.json')
        profile['build_proof_sha256'] = tool.sha_file(new_dir/'build-result.json')
        verification['build_result_sha256'] = profile['build_proof_sha256']
        (new_dir/'artifact-verification.json').write_text(json.dumps(verification))
        profile['verification_sha256'] = tool.sha_file(new_dir/'artifact-verification.json')
    save_and_pin_fixture()
    return SimpleNamespace(old=old, previous=previous, current=current, verification=verification,
        previous_dir=previous_dir, path=new_dir/'build-result.json', profile=profile, save=save_and_pin_fixture)


def test_independent_three_layer_fixture_with_distinct_immediate_inputs_is_accepted(three_layers):
    a = three_layers
    assert len(a.old['inputs']) == 2 and len(a.previous['inputs']) == 3 and len(a.current['inputs']) == 4
    assert tool.checked_build(a.path, a.profile)[1].read_bytes() == b'fixture-ba0327'


@pytest.mark.parametrize('damage,code', [
    ('skip_immediate', 'BASELINE_INPUTS_CHANGED'), ('extra_baseline', 'BASELINE_INPUTS_CHANGED'),
    ('wrong_baseline_digest', 'BASELINE_INPUTS_CHANGED'), ('previous_not_exact', 'PREDECESSOR_BASELINE_CHANGED'),
    ('overlap', 'ABI_INPUTS_OVERLAP'), ('unlisted_input', 'ABI_INPUTS_CHANGED'),
    ('empty_additional', 'ABI_INPUTS_MISSING'), ('relink', 'PREDECESSOR_RELINK_CHANGED'),
    ('extra_unit', 'PREDECESSOR_RELINK_CHANGED'), ('previous_changed', 'PREDECESSOR_RELINK_CHANGED'),
    ('wrong_previous_ref', 'PREDECESSOR_REFERENCE_CHANGED'), ('unverified_schema', 'RPC_SCHEMA_NOT_VERIFIED'),
])
def test_repinning_fixture_never_turns_three_layer_exact_checks_into_subset_acceptance(three_layers, damage, code):
    a = three_layers
    if damage == 'skip_immediate':
        a.current['baseline_inputs'] = dict(a.old['inputs'])
        a.current['inputs'] = dict(a.current['baseline_inputs'], **a.current['additional_inputs'])
    elif damage == 'extra_baseline': a.current['baseline_inputs']['foreign'] = 'x'
    elif damage == 'wrong_baseline_digest': a.current['baseline_inputs']['old-a'] = 'wrong'
    elif damage == 'previous_not_exact': a.previous['baseline_inputs']['extra'] = 'x'
    elif damage == 'overlap': a.current['additional_inputs']['old-a'] = 'a'
    elif damage == 'unlisted_input': a.current['inputs']['foreign'] = 'x'
    elif damage == 'empty_additional': a.current['additional_inputs'] = {}
    elif damage == 'relink': a.current['predecessor-relink_sha256'] = tool.OLD
    elif damage == 'extra_unit': a.current['recompiled_units'].append('other.cpp')
    elif damage == 'previous_changed': a.current['predecessor_unchanged'] = False
    elif damage == 'wrong_previous_ref': a.current['predecessor_proof'] = 'foreign.json'
    elif damage == 'unverified_schema': a.verification['rpc_methods_exact'] = False
    a.save()
    with pytest.raises(AssertionError, match=code):
        tool.checked_build(a.path, a.profile)


@pytest.mark.parametrize('damage', ['missing_running', 'multiple_running', 'wrong_running',
    'wrong_binary', 'wrong_launch_hash', 'changed_launch_source', 'wrong_dropin'])
def test_real_artifacts_do_not_rescue_wrong_installed_predecessor_layout(tmp_path, damage):
    profile = tool.PROFILES['schema2043']
    previous = profile['predecessor']
    layout = json.loads(profile['layout'].read_text())
    if damage == 'missing_running': layout['running'] = []
    elif damage == 'multiple_running': layout['running'] *= 2
    elif damage == 'wrong_running': layout['running'][0]['sha256'] = tool.OLD
    elif damage == 'wrong_binary': layout['files'][previous['binary_path']]['sha256'] = tool.OLD
    elif damage == 'wrong_launch_hash': layout['files'][previous['launch_path']]['sha256'] = '0' * 64
    elif damage == 'changed_launch_source': layout['files'][previous['launch_path']]['source'] += '\n'
    else: layout['dropins']['/storage/.config/system.d/kodi.service.d/60-am6b-subtitle284.conf']['sha256'] = '0' * 64
    path = tmp_path/'layout.json'
    path.write_text(json.dumps(layout))
    with pytest.raises(AssertionError):
        tool.staged_files(RUN/'build-result.json', profile, path)


@pytest.mark.parametrize('sequence', [2026102042, 2026102044])
def test_schema_initial_apply_rejects_wrong_program_generation_before_service_mutation(tmp_path, monkeypatch, sequence):
    h = initial_handoff(tmp_path, monkeypatch)
    h.ns['REQUIRED_SEQUENCE'] = tool.PROFILES['schema2043']['sequence']
    h.generation.write_text(json.dumps(dict(schema=1, sequence=sequence, high_watermark=sequence,
        phase='complete', host_pending=None, tx='a' * 32)))
    with pytest.raises(AssertionError, match='INSTALL_COMPATIBLE_ADDONS_FIRST|INITIAL_GENERATION_CHANGED'):
        h.run()
    assert not h.calls and not h.receipt.exists() and h.conf.read_bytes() == h.old_conf


def test_new_native_hash_retains_exact_existing_subtitle_abi_not_generic_hash_acceptance(monkeypatch):
    new = tool.PROFILES['schema2043']['candidate']
    monkeypatch.setattr(runtime_paths, '_coreelec', lambda: True)
    monkeypatch.setattr(runtime_paths, 'native_executable_sha256', lambda value: value)
    assert runtime_paths.native_subtitle_abi({'native_contract_available': True}, new) == dict(
        root=runtime_paths.CE_F9_ROOT, sha256=new)
    assert runtime_paths.native_subtitle_abi({'native_contract_available': True}, '0' * 64) is None
    assert runtime_paths.native_subtitle_abi({'native_contract_available': False}, new) is None

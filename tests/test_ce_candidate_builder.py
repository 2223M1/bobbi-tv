"""Tool-side guards; real CE compile/link evidence is recorded separately."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ce_candidate_builder', ROOT/'native/tests/ce_candidate_builder.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def predecessor(tmp_path):
    source = tmp_path/'source-candidate'
    source.mkdir()
    (source/'source.cpp').write_text('frozen source')
    (tmp_path/'candidate.bin').write_bytes(b'predecessor')
    proof = dict(state='BUILT_NOT_DEPLOYED', original_tree_unchanged=True,
        candidate_sha256=sha(tmp_path/'candidate.bin'), source_sha256=builder.source_hashes(source, sha),
        inputs={str(source/'source.cpp'): sha(source/'source.cpp')})
    (tmp_path/'build-result.json').write_text(json.dumps(proof))
    (tmp_path/'artifact-verification.json').write_text(json.dumps(dict(
        state='VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED', candidate_sha256=proof['candidate_sha256'])))
    return tmp_path, dict(verified_predecessor=True, predecessor_sha256=proof['candidate_sha256'],
        predecessor_proof_sha256=sha(tmp_path/'build-result.json'))


def test_both_predecessor_contracts_are_checked_without_writes(predecessor):
    path, profile = predecessor
    before = builder.source_hashes(path, sha)
    assert builder.checked_predecessor(profile, path, sha)['state'] == 'BUILT_NOT_DEPLOYED'
    assert builder.source_hashes(path, sha) == before


@pytest.mark.parametrize('damage', ['proof', 'binary', 'source', 'extra_source', 'verification', 'generation'])
def test_predecessor_guard_rejects_changed_inputs(predecessor, damage):
    path, profile = predecessor
    names = dict(proof='build-result.json', binary='candidate.bin', source='source-candidate/source.cpp',
                 extra_source='source-candidate/extra.h', verification='artifact-verification.json')
    if damage == 'generation': profile['predecessor_sha256'] = 'f'*64
    elif damage == 'verification':
        (path/names[damage]).write_text(json.dumps(dict(state='VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED', candidate_sha256='e'*64)))
    else: (path/names[damage]).write_text('changed')
    with pytest.raises(AssertionError): builder.checked_predecessor(profile, path, sha)


@pytest.mark.parametrize('command', ['gcc -o a', ': && gcc ; bad && :', ': && gcc | bad && :'])
def test_link_command_never_runs_an_unreviewed_shell_chain(command):
    with pytest.raises(AssertionError): builder.link_command(command)


def test_exact_compile_delta_allows_only_declared_context_changes(tmp_path):
    path = tmp_path/'canonical.patch'
    path.write_text('+new algorithm\n old context\n')
    assert builder.patch_bytes(path, [(' old context', ' CE context')]) == b'+new algorithm\n CE context\n'
    with pytest.raises(AssertionError, match='ADDITION'):
        builder.patch_bytes(path, [('+new algorithm', '+different algorithm')])
    with pytest.raises(AssertionError, match='CONTEXT_DRIFT'):
        builder.patch_bytes(path, [('missing', 'changed')])


def test_legacy_entries_have_one_shared_pipeline_and_keep_pinned_generation():
    import ast
    for name in ('completion', 'home_focus'):
        path = ROOT/'native/tests'/('build_ce_'+name+'_candidate.py')
        tree = ast.parse(path.read_text())
        assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.walk(tree))
        assert 'from ce_candidate_builder import main' in path.read_text()
    assert '0b54e0b6b3e982dd9e02f2867cdbc6fc3df36afd7709e7cf4c368ec655651f7c' in path.read_text()

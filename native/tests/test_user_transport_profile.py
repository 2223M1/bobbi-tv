"""Tamper controls for the offline native evidence verifier (no device access)."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import verify_ce_user_transport_candidate as gate


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))


@pytest.fixture
def built(tmp_path):
    source = tmp_path/'source-candidate'
    units = [unit[0] for unit in gate.PROFILE['units']]
    layout = set(gate.PROFILE['layout_units'])
    schema = {gate.RPC+'JSONRPC.cpp', gate.RPC+'JSONServiceDescription.cpp'}
    method = {'params': [{'name': 'action', 'enum': ['user_pause', 'user_resume', 'user_stop']}]}
    for relative in [*units, gate.PROFILE['layout_header']]:
        write(source/relative, relative)
    write(source/(gate.RPC+'schema/methods.json'), {'Player.BobiControl': method})
    header = tmp_path/'generated/ServiceDescription.h'
    write(header, 'generated')
    write(tmp_path/'candidate.bin', method)
    report = dict(state='BUILT_NOT_DEPLOYED', build_kind='user_transport', original_tree_unchanged=True,
        predecessor_unchanged=True, architecture_and_dependencies_unchanged=True,
        recompiled_units=units, objects={}, commands={},
        source_sha256=gate.builder.source_hashes(source, gate.sha),
        layout_consumers=[unit[1] for unit in gate.PROFILE['units'] if unit[0] in layout],
        schema_consumers=[unit[1] for unit in gate.PROFILE['units'] if unit[0] in schema],
        schema_include_sources=sorted(schema), binary_bobicontrol_schema_matches_source=True,
        binary_bobicontrol_schema_unchanged=False, schema_changed_methods=['Player.BobiControl'],
        generated_header_sha256=gate.sha(header), binary_bobicontrol=method,
        retained_archive_members={'build/guilib_listproviders/guilib_listproviders.a': {'retained': 'sha'}})
    for relative in units:
        obj = tmp_path/(Path(relative).name+'.o'); write(obj, relative)
        dep = Path(str(obj)+'.d')
        dependencies = [str(source/relative)]
        if relative in layout: dependencies.append(str(source/gate.PROFILE['layout_header']))
        if relative in schema: dependencies.append(str(header))
        write(dep, ' '.join(dependencies))
        report['objects'][relative] = dict(sha256=gate.sha(obj), depfile_sha256=gate.sha(dep))
        report['commands'][Path(relative).stem+'-compile'] = ['cc', '-c', str(source/relative), '-o', str(obj), '-MF', str(dep)]
    return tmp_path, report


def test_complete_consumer_schema_evidence(built):
    path, report = built
    gate.check_build(path, report, gate.read)


@pytest.mark.parametrize('damage', ['historical_kind', 'unit', 'object', 'layout_consumer', 'schema_consumer',
    'schema_include', 'schema_flag', 'schema_delta', 'source', 'binary', 'generated', 'dep',
    'repinned_wrong_dep', 'compile_command', 'home_archive'])
def test_tampered_build_evidence_fails_even_with_repinned_claims(built, damage):
    path, report = built
    if damage == 'historical_kind': report['build_kind'] = 'scoped_controls'
    if damage == 'unit': report['recompiled_units'].pop()
    if damage == 'object': (path/'VideoPlayer.cpp.o').write_text('changed')
    if damage == 'layout_consumer': report['layout_consumers'].pop()
    if damage == 'schema_consumer': report['schema_consumers'].pop()
    if damage == 'schema_include': report['schema_include_sources'].pop()
    if damage == 'schema_flag': report['binary_bobicontrol_schema_unchanged'] = True
    if damage == 'schema_delta': report['schema_changed_methods'] = []
    if damage == 'source': (path/'source-candidate'/gate.VIDEO).write_text('changed')
    if damage == 'binary': write(path/'candidate.bin', {'old': True})
    if damage == 'generated': (path/'generated/ServiceDescription.h').write_text('old')
    if damage in ('dep', 'repinned_wrong_dep'):
        dep=path/'JSONRPC.cpp.o.d'; dep.write_text('unrelated/schema.h')
        if damage == 'repinned_wrong_dep': report['objects'][gate.RPC+'JSONRPC.cpp']['depfile_sha256']=gate.sha(dep)
    if damage == 'compile_command': report['commands']['JSONRPC-compile'][2]='wrong.cpp'
    if damage == 'home_archive': report['retained_archive_members']={}
    with pytest.raises(AssertionError): gate.check_build(path, report, gate.read)


def test_original_19_are_not_transport_evidence():
    report = dict(compiled=True, passed=True, tests=[dict(name=name, passed=True) for name in gate.OLD_CASES])
    gate.case_rows(report, gate.OLD_CASES)
    with pytest.raises(AssertionError, match='ACTOR_CASE_SET'): gate.case_rows(report, gate.CASES)


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'failed', 'uncompiled', 'bare_pass'])
def test_actor_cases_are_exact_not_summary_booleans(damage):
    report = dict(compiled=True, passed=True, tests=[dict(name=name, passed=True) for name in gate.CASES])
    if damage == 'missing': report['tests'].pop()
    if damage == 'duplicate': report['tests'][-1]=deepcopy(report['tests'][0])
    if damage == 'failed': report['tests'][0]['passed']=False
    if damage == 'uncompiled': report['compiled']=False
    if damage == 'bare_pass': report['tests']=[]
    with pytest.raises(AssertionError): gate.case_rows(report, gate.CASES)


def test_pinned_hash_rejects_mutated_file(tmp_path):
    path=tmp_path/'proof';path.write_text('original');digest=gate.sha(path)
    gate.check_hash(path,digest,'changed')
    path.write_text('mutated')
    with pytest.raises(AssertionError):gate.check_hash(path,digest,'changed')


@pytest.fixture
def actor_evidence(tmp_path, monkeypatch):
    source=tmp_path/'source'
    relatives={gate.VIDEO,gate.HEADER,'xbmc/cores/VideoPlayer/DVDMessage.h',
        'xbmc/cores/BobiOpenGate.h','xbmc/utils/Variant.cpp','xbmc/utils/Variant.h',
        gate.RPC+'PlayerOperations.cpp','xbmc/application/ApplicationPlayer.cpp',
        'xbmc/cores/VideoPlayer/Process/ProcessInfo.cpp'}
    for relative in relatives:write(source/relative,relative)
    report=dict(compiled=True,passed=True,source=str(source),base_source=None,
        tests=[dict(name=name,passed=True) for name in gate.CASES],
        source_sha256={relative:gate.sha(source/relative) for relative in relatives},
        runner_sha256=gate.sha(gate.HERE/'run_scoped_actor_test.py'),
        fixture_sha256=gate.sha(gate.HERE/'scoped_actor_test.cpp'))
    for name,field in [('actual_scoped_actor.inc','extracted_sha256'),('actual_scoped_messages.inc','messages_sha256'),('scoped-actor-test','binary_sha256')]:
        write(tmp_path/name,name);report[field]=gate.sha(tmp_path/name)
    monkeypatch.setattr(gate.actor,'extracted',lambda *args:('actual_scoped_actor.inc','actual_scoped_messages.inc'))
    path=tmp_path/'result.json';write(path,report)
    return path,source,report


def test_actor_artifacts_are_bound_to_current_source(actor_evidence):
    path,source,_=actor_evidence
    gate.actor_artifacts(path,source,replay=False)


@pytest.mark.parametrize('damage',['source','foreign_source','runner','fixture','binary','messages','extracted','repinned_extracted'])
def test_actor_artifact_tampering_is_rejected(actor_evidence,damage):
    path,source,report=actor_evidence
    if damage=='source':write(source/gate.VIDEO,'changed')
    if damage=='foreign_source':report['source']=str(path.parent/'foreign')
    if damage in ('runner','fixture'):report[damage+'_sha256']='0'*64
    targets={'binary':'scoped-actor-test','messages':'actual_scoped_messages.inc','extracted':'actual_scoped_actor.inc','repinned_extracted':'actual_scoped_actor.inc'}
    if damage in targets:
        target=path.parent/targets[damage];write(target,'changed')
        if damage=='repinned_extracted':report['extracted_sha256']=gate.sha(target)
    write(path,report)
    with pytest.raises(AssertionError):gate.actor_artifacts(path,source,replay=False)


@pytest.fixture
def negative(tmp_path, monkeypatch):
    snapshot=tmp_path/'source';predecessor=tmp_path/'old'
    source_hashes={}
    for relative in (gate.VIDEO,gate.HEADER,gate.RPC+'PlayerOperations.cpp'):
        write(snapshot/relative,relative);source_hashes[relative]=gate.sha(snapshot/relative)
    rows=[]
    for name,expected in gate.MUTANTS.items():
        proof=tmp_path/name/'result.json'
        write(proof,dict(passed=False,tests=[dict(name=case,passed=case!=expected) for case in gate.CASES]))
        rows.append(dict(name=name,detected=True,expected_failed_case=expected,result=str(proof),sha256=gate.sha(proof),actor_passed=False))
    old=tmp_path/'old-result.json'
    write(old,dict(passed=True,tests=[dict(name=case,passed=True) for case in gate.OLD_CASES]))
    rows.append(dict(name='old_scoped_binary_is_not_transport_proof',detected=True,
        missing_required_cases=sorted(set(gate.CASES)-set(gate.OLD_CASES)),historical_actor_passed=True,
        result=str(old),sha256=gate.sha(old)))
    report=dict(passed=True,original_source_unchanged=True,source=str(snapshot),source_sha256=source_hashes,
        runner_sha256=gate.sha(gate.HERE/'check_user_transport_gate.py'),tests=rows)
    path=tmp_path/'negative.json';write(path,report)
    # Child artifact checker has its own direct-source/hash/extraction tests;
    # here isolate the parent gate's target failure checks.
    monkeypatch.setattr(gate,'actor_artifacts',lambda path,*args,**kwargs:gate.read(path))
    return path,snapshot,predecessor,report


def test_negative_cases_require_actual_target_failure(negative):
    path,snapshot,previous,_=negative
    gate.negative_artifacts(path,snapshot,previous,replay=False)


@pytest.mark.parametrize('damage',['missing','target','false_positive','old_missing','proof','source'])
def test_negative_summary_cannot_hide_wrong_evidence(negative,damage):
    path,snapshot,previous,report=negative
    if damage=='missing':report['tests'].pop()
    if damage=='target':report['tests'][0]['expected_failed_case']='unrelated'
    if damage=='false_positive':
        row=report['tests'][0];proof=Path(row['result']);child=gate.read(proof)
        for test in child['tests']:test['passed']=True
        write(proof,child);row['sha256']=gate.sha(proof)
    if damage=='old_missing':report['tests'][-1]['missing_required_cases']=[]
    if damage=='proof':Path(report['tests'][0]['result']).write_text('{}')
    if damage=='source':report['source']=str(previous)
    write(path,report)
    with pytest.raises(AssertionError):gate.negative_artifacts(path,snapshot,previous,replay=False)

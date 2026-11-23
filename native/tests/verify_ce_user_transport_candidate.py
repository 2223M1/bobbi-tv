"""Offline native user-transport evidence gate; never deploys or touches a device.

Rechecks real artifacts, reconstructs the exact source delta, checks archive
members and dependency consumers, and reruns the actual actor binaries. Decoder
and services are fixture dependencies; this is not a device/playback certificate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import ce_candidate_builder as builder
from build_ce_user_transport_candidate import PROFILE
import run_scoped_actor_test as actor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VIDEO = 'xbmc/cores/VideoPlayer/VideoPlayer.cpp'
HEADER = 'xbmc/cores/VideoPlayer/BobiScopedControl.h'
RPC = 'xbmc/interfaces/json-rpc/'
OLD_CASES = actor.CASES + ('ce_subtitle_resync', 'ce_subtitle_replacement',
    'ce_subtitle_new_manual', 'ce_subtitle_original_mode', 'ce_subtitle_non_demux')
CASES = OLD_CASES + actor.TRANSPORT_CASES + actor.CE_TRANSPORT_CASES
MUTANTS = {
    'premature_stop': 'user_stop_onexit',
    'rewritten_original': 'user_stop_original_scope',
    'foreign_terminal': 'user_stop_no_terminal_inference',
    'unscoped_resume': 'user_resume_replacement',
    'onexit_exception_gap': 'user_stop_unknown',
    'state_archive_missing': 'user_state_read',
    'pause_requires_seek': 'user_capabilities',
    'counter_type_gap': 'user_strict_counters',
    'ce_unscoped_vc1': 'user_ce_vc1_replacement',
    'no_final_retirement': 'user_retire_many',
    'retire_unknown': 'user_retirement_guards',
    'guest_retirement_state': 'user_retirement_real_state',
    'resume_tempo_retained': 'user_tempo_150',
    'speed_only_projection': 'user_tempo_projection',
    'speed_only_applied': 'user_tempo_applied_guard',
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def check_hash(path, expected, reason):
    assert Path(path).is_file() and sha(path) == expected, reason


def read(path):
    return json.loads(Path(path).read_text())


def case_rows(report, required, success=True):
    rows = report.get('tests', [])
    assert len(rows) == len(required) and {row['name'] for row in rows} == set(required), 'ACTOR_CASE_SET'
    assert report.get('compiled') is True, 'ACTOR_NOT_COMPILED'
    if success:
        assert report.get('passed') is True and all(row.get('passed') is True for row in rows), 'ACTOR_FAILED'
    return {row['name']: row for row in rows}


def actor_artifacts(path, expected_source=None, required=CASES, success=True, replay=True):
    path = Path(path)
    report = read(path)
    rows = case_rows(report, required, success)
    source = Path(report['source'])
    base = Path(report['base_source']) if report.get('base_source') else None
    if expected_source is not None:
        assert source.resolve() == Path(expected_source).resolve(), 'ACTOR_SOURCE_REFERENCE'
    check_hash(HERE/'run_scoped_actor_test.py', report['runner_sha256'], 'ACTOR_RUNNER_CHANGED')
    check_hash(HERE/'scoped_actor_test.cpp', report['fixture_sha256'], 'ACTOR_FIXTURE_CHANGED')
    for name, field in (('actual_scoped_actor.inc', 'extracted_sha256'),
                        ('actual_scoped_messages.inc', 'messages_sha256'),
                        ('scoped-actor-test', 'binary_sha256')):
        check_hash(path.parent/name, report[field], 'ACTOR_ARTIFACT_CHANGED:'+name)
    expected = {VIDEO, HEADER, 'xbmc/cores/VideoPlayer/DVDMessage.h',
        'xbmc/cores/BobiOpenGate.h', 'xbmc/utils/Variant.cpp', 'xbmc/utils/Variant.h'}
    if required != OLD_CASES:
        expected |= {RPC+'PlayerOperations.cpp', 'xbmc/application/ApplicationPlayer.cpp',
                     'xbmc/cores/VideoPlayer/Process/ProcessInfo.cpp'}
    assert set(report['source_sha256']) == expected, 'ACTOR_SOURCE_SET'
    for relative, digest in report['source_sha256'].items():
        check_hash(actor.dependency(source, relative, base), digest, 'ACTOR_SOURCE_CHANGED:'+relative)
    extracted, messages = actor.extracted(source, base)
    assert (path.parent/'actual_scoped_actor.inc').read_text() == extracted, 'ACTOR_EXTRACTION_CHANGED'
    assert (path.parent/'actual_scoped_messages.inc').read_text() == messages, 'ACTOR_MESSAGES_CHANGED'
    if replay:
        for name, row in rows.items():
            trial = subprocess.run([str(path.parent/'scoped-actor-test'), name], capture_output=True, text=True, timeout=20)
            assert (trial.returncode == 0) is row['passed'], 'ACTOR_REPLAY_MISMATCH:'+name
            assert trial.stdout+trial.stderr == row['output'], 'ACTOR_REPLAY_OUTPUT_CHANGED:'+name
    return report


def check_build(build, report, binary_method):
    build = Path(build)
    snapshot = build/'source-candidate'
    assert report.get('state') == 'BUILT_NOT_DEPLOYED' and report.get('build_kind') == 'user_transport', 'BUILD_KIND'
    for field in ('original_tree_unchanged', 'predecessor_unchanged', 'architecture_and_dependencies_unchanged'):
        assert report.get(field) is True, 'BUILD_INVARIANT:'+field
    units = {unit[0] for unit in PROFILE['units']}
    assert len(report['recompiled_units']) == len(units) and set(report['recompiled_units']) == units, 'REAL_CONSUMER_SET'
    assert set(report['objects']) == units, 'REAL_OBJECT_SET'
    assert builder.source_hashes(snapshot, sha) == report['source_sha256'], 'BUILD_SOURCE_CHANGED'
    layout = set(PROFILE['layout_units'])
    schema = {RPC+'JSONRPC.cpp', RPC+'JSONServiceDescription.cpp'}
    assert set(report['layout_consumers']) == {unit[1] for unit in PROFILE['units'] if unit[0] in layout}, 'LAYOUT_CONSUMER_SET'
    assert set(report['schema_consumers']) == {unit[1] for unit in PROFILE['units'] if unit[0] in schema}, 'SCHEMA_CONSUMER_SET'
    assert set(report['schema_include_sources']) == schema, 'SCHEMA_INCLUDE_SET'
    assert (report.get('binary_bobicontrol_schema_matches_source') is True and
            report.get('binary_bobicontrol_schema_unchanged') is False and
            report.get('schema_changed_methods') == ['Player.BobiControl']), 'SCHEMA_CHANGE_CONTRACT'
    header = build/'generated/ServiceDescription.h'
    check_hash(header, report['generated_header_sha256'], 'GENERATED_SCHEMA_CHANGED')
    for source in units:
        obj = build/(Path(source).name+'.o')
        dep = Path(str(obj)+'.d')
        check_hash(obj, report['objects'][source]['sha256'], 'OBJECT_CHANGED')
        check_hash(dep, report['objects'][source]['depfile_sha256'], 'DEPFILE_CHANGED')
        dependencies = dep.read_text().replace('\\\n', ' ').split()
        assert str(snapshot/source) in dependencies, 'WRONG_SOURCE_DEPENDENCY'
        if source in layout:
            assert str(snapshot/PROFILE['layout_header']) in dependencies, 'WRONG_LAYOUT_DEPENDENCY'
        if source in schema:
            assert str(header) in dependencies, 'WRONG_SCHEMA_DEPENDENCY'
        command = report['commands'][Path(source).stem+'-compile']
        for option, target in (('-o', obj), ('-c', snapshot/source), ('-MF', dep)):
            assert command.count(option) == 1 and command[command.index(option)+1] == str(target), 'COMPILE_COMMAND_CHANGED'
    expected = read(snapshot/(RPC+'schema/methods.json'))['Player.BobiControl']
    assert binary_method(build/'candidate.bin') == report['binary_bobicontrol'] == expected, 'STALE_BINARY_SCHEMA'
    actions = next(row['enum'] for row in expected['params'] if row['name'] == 'action')
    assert {'user_pause', 'user_resume', 'user_stop'} <= set(actions), 'USER_ACTION_SCHEMA_MISSING'
    assert report['retained_archive_members'].get('build/guilib_listproviders/guilib_listproviders.a'), 'HOME_ARCHIVE_LOST'


def negative_artifacts(path, snapshot, predecessor_source, replay=True):
    path = Path(path)
    report = read(path)
    assert report.get('passed') is True and report.get('original_source_unchanged') is True, 'NEGATIVE_GATE_FAILED'
    assert Path(report['source']).resolve() == Path(snapshot).resolve(), 'NEGATIVE_SOURCE_REFERENCE'
    check_hash(HERE/'check_user_transport_gate.py', report['runner_sha256'], 'NEGATIVE_RUNNER_CHANGED')
    assert set(report['source_sha256']) == {VIDEO, HEADER, RPC+'PlayerOperations.cpp'}, 'NEGATIVE_SOURCE_SET'
    for relative, digest in report['source_sha256'].items():
        check_hash(Path(snapshot)/relative, digest, 'NEGATIVE_SOURCE_CHANGED')
    rows = report['tests']
    old_name = 'old_scoped_binary_is_not_transport_proof'
    assert len(rows) == len(MUTANTS)+1 and {row['name'] for row in rows} == set(MUTANTS)|{old_name}, 'NEGATIVE_CASE_SET'
    for row in rows:
        assert row.get('detected') is True, 'NEGATIVE_NOT_DETECTED'
        proof = Path(row['result'])
        check_hash(proof, row['sha256'], 'NEGATIVE_ACTOR_PROOF_CHANGED')
        if row['name'] == old_name:
            historical = actor_artifacts(proof, predecessor_source, OLD_CASES, replay=replay)
            missing = sorted(set(CASES)-{trial['name'] for trial in historical['tests']})
            assert row['historical_actor_passed'] is True and row['missing_required_cases'] == missing and missing, 'OLD_PROOF_NOT_REJECTED'
        else:
            expected = MUTANTS[row['name']]
            assert row['expected_failed_case'] == expected and row['actor_passed'] is False, 'NEGATIVE_TARGET_CHANGED'
            mutant = actor_artifacts(proof, required=CASES, success=False, replay=replay)
            trials = {trial['name']: trial for trial in mutant['tests']}
            assert mutant['passed'] is False and trials[expected]['passed'] is False, 'NEGATIVE_FALSE_POSITIVE'
    return report


def verify(build, actor_proof, negative_proof, profile):
    build = Path(build).resolve()
    report = read(build/'build-result.json')
    for path, field in ((build/'build-result.json', 'build_proof_sha256'),
                        (build/'candidate.bin', 'candidate_sha256'),
                        (actor_proof, 'actor_proof_sha256'), (negative_proof, 'negative_proof_sha256')):
        check_hash(path, profile[field], 'PINNED_PROOF_CHANGED:'+field)
    assert profile['build_kind'] == 'user_transport' and profile['deployment_authority'] is False, 'OFFLINE_PROFILE_ONLY'
    assert profile['required_actor_cases'] == list(CASES), 'PROFILE_ACTOR_CASES'
    assert profile['required_negative_controls'] == MUTANTS, 'PROFILE_NEGATIVE_CASES'
    legacy = builder.module('user_transport_frozen_schema', ROOT/'ce-jsonrpc-schema-20261022/build_isolated.py')
    check_build(build, report, legacy.binary_method)
    predecessor = Path(profile['predecessor'])
    previous = builder.checked_predecessor(PROFILE, predecessor, sha)
    check_hash(build/'predecessor-relink.bin', PROFILE['predecessor_sha256'], 'PREDECESSOR_RELINK_CHANGED')
    assert report['predecessor-relink_sha256'] == report['predecessor_sha256'] == PROFILE['predecessor_sha256'], 'PREDECESSOR_IDENTITY'
    assert report['predecessor_proof_sha256'] == PROFILE['predecessor_proof_sha256'], 'PREDECESSOR_PROOF'
    assert report['candidate_sha256'] == profile['candidate_sha256'], 'CANDIDATE_IDENTITY'
    for path, digest in report['inputs'].items():
        check_hash(path, digest, 'FROZEN_INPUT_CHANGED:'+path)
    patch = ROOT/'patches'/PROFILE['patch']
    check_hash(patch, report['canonical_patch_sha256'], 'CANONICAL_PATCH_CHANGED')
    check_hash(ROOT/'patches/series.json', report['series_sha256'], 'SERIES_CHANGED')
    delta = builder.patch_bytes(patch, PROFILE['contexts'])
    assert hashlib.sha256(delta).hexdigest() == report['ce_context_patch_sha256'], 'CE_ADAPTATION_CHANGED'
    followup = ROOT/PROFILE['platform_patch']
    check_hash(followup, report['platform_patch_sha256'], 'CE_FOLLOWUP_CHANGED')
    with tempfile.TemporaryDirectory(prefix='user-transport-reconstruct-') as temporary:
        reconstructed = Path(temporary)/'source'
        shutil.copytree(predecessor/'source-candidate', reconstructed)
        subprocess.run(['git', 'apply', '--recount'], input=delta, cwd=reconstructed, check=True, capture_output=True)
        subprocess.run(['git', 'apply', '--recount', str(followup)], cwd=reconstructed, check=True, capture_output=True)
        assert builder.source_hashes(reconstructed, sha) == report['source_sha256'], 'CANONICAL_RECONSTRUCTION_CHANGED'
    before = read(predecessor/'source-candidate'/ (RPC+'schema/methods.json'))
    after = read(build/'source-candidate'/ (RPC+'schema/methods.json'))
    builder.schema_delta(before, after, ('Player.BobiControl',))
    before_actions = next(row for row in before['Player.BobiControl']['params'] if row['name'] == 'action')
    before_actions['enum'] += ['user_pause', 'user_resume', 'user_stop']
    assert before == after, 'SCHEMA_DELTA_EXCEEDS_USER_ACTIONS'
    origins = builder.archive_origins(legacy, previous, PROFILE, predecessor)
    assert set(report['retained_archive_members']) == set(origins), 'INHERITED_ARCHIVE_SET'
    for archive, origin in origins.items():
        target = build/Path(archive).name
        replaced = [Path(source).name+'.o' for source, _, container in PROFILE['units'] if container == archive]
        assert legacy.retained_members(origin, target, replaced) == report['retained_archive_members'][archive], 'RETAINED_MEMBERS_CHANGED'
        assert str(target) in report['commands']['candidate-link'], 'CANDIDATE_LINK_ARCHIVE_MISSING'
        for member in replaced:
            assert hashlib.sha256(legacy.tool('ar', 'p', target, member, binary=True)).hexdigest() == sha(build/member), 'LINKED_OBJECT_CHANGED'
    for flags in (['-A'], ['-d']):
        old, new = (legacy.tool('readelf', *flags, binary) for binary in (predecessor/'candidate.bin', build/'candidate.bin'))
        assert (builder.needed(old) == builder.needed(new) if flags == ['-d'] else old == new), 'ELF_ABI_DEPENDENCY_CHANGED'
    actor_artifacts(actor_proof, build/'source-candidate')
    negative_artifacts(negative_proof, build/'source-candidate', predecessor/'source-candidate')
    return dict(state='VERIFIED_OFFLINE_NOT_DEVICE_CERTIFIED', deployment_authority=False,
        candidate_sha256=sha(build/'candidate.bin'), build_proof_sha256=sha(build/'build-result.json'),
        actor_proof_sha256=sha(actor_proof), negative_proof_sha256=sha(negative_proof),
        verifier_sha256=sha(__file__), profile_sha256=None, actor_cases=len(CASES),
        negative_controls=len(MUTANTS)+1, real_translation_units=len(PROFILE['units']),
        frozen_inputs=len(report['inputs']), original_scoped_cases=len(OLD_CASES))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--actor', type=Path, required=True)
    parser.add_argument('--negative', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=HERE/'user_transport_profile.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.build, args.actor, args.negative, read(args.profile))
    result['profile_sha256'] = sha(args.profile)
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='user-transport-verified-', dir=args.output))
    (run/'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(dict(result=str(run/'result.json'), **result)))

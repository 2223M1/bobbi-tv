"""Check exact 8bb2 object inheritance and every RPC method in the real ELF."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from build_isolated import (ARCHIVES, BUILD, DESCRIPTION_SOURCE, HERE, PREDECESSOR, PREDECESSOR_SHA,
    PROOF_SHA, RPC_SOURCE, SCHEMA_CONSUMERS, SOURCE, TOOLS, VERIFICATION_SHA, binary_method,
    deps, retained_members, schema_consumers, sha, tool)


def binary_methods_bytes(raw):
    methods = {}
    for part in raw.split(b'\0'):
        match = re.match(rb'^"([A-Za-z0-9_.]+)": \{', part)
        if not match:
            continue
        try:
            value = json.loads(b'{'+part+b'}')
        except (ValueError, UnicodeDecodeError):
            continue
        name = match[1].decode('ascii')
        method = value.get(name)
        if not isinstance(method, dict) or method.get('type') != 'method':
            continue
        assert name not in methods, 'DUPLICATE_BINARY_METHOD:'+name
        methods[name] = method
    return methods


def verify_methods(raw, expected):
    actual = binary_methods_bytes(raw)
    assert set(actual) == set(expected), 'BINARY_METHOD_SET_MISMATCH'
    changed = sorted(name for name in actual if actual[name] != expected[name])
    assert not changed, 'BINARY_METHOD_SCHEMA_MISMATCH:'+repr(changed)
    return actual


def symbols(path):
    return {re.sub(r' \[clone .*$', '', line.split(None, 2)[2])
            for line in tool('nm', '-C', '--defined-only', path).splitlines()
            if len(line.split(None, 2)) == 3 and 'Bobi' in line}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-result', type=Path, required=True)
    args = parser.parse_args()
    run = args.build_result.parent
    proof = json.loads(args.build_result.read_text())
    assert proof['state'] == 'BUILT_NOT_DEPLOYED' and proof['original_tree_unchanged'] and proof['predecessor_unchanged']
    assert proof['recompiled_units'] == [RPC_SOURCE]
    assert sha(HERE/'build_isolated.py') == proof['builder_sha256']
    assert sha(PREDECESSOR/'build-result.json') == PROOF_SHA
    assert sha(PREDECESSOR/'artifact-verification.json') == VERIFICATION_SHA
    assert sha(PREDECESSOR/'candidate.bin') == PREDECESSOR_SHA == proof['predecessor-relink_sha256']
    assert all(sha(path) == digest for path, digest in proof['inputs'].items())
    assert all(sha(path) == digest for path, digest in proof['predecessor_inputs'].items())
    snapshot = run/'source-candidate'
    assert {str(p.relative_to(snapshot)): sha(p) for p in snapshot.rglob('*') if p.is_file()} == proof['source_sha256']
    previous = json.loads((PREDECESSOR/'build-result.json').read_text())
    assert set(proof['source_sha256']) == set(previous['source_sha256']) | {RPC_SOURCE}
    assert all(proof['source_sha256'][name] == digest for name, digest in previous['source_sha256'].items())
    consumers, includes = schema_consumers()
    assert set(consumers) == SCHEMA_CONSUMERS and consumers == proof['schema_consumers']
    assert includes == proof['schema_include_sources']
    header = run/'generated/ServiceDescription.h'
    old_header = PREDECESSOR/'candidate/generated/ServiceDescription.h'
    assert header.read_bytes() == old_header.read_bytes()
    assert sha(header) == proof['generated_header_sha256']
    rebuilt = proof['rebuilt_schema_consumer']
    reused = proof['reused_schema_consumer']
    for row, expected_header in ((rebuilt, header), (reused, old_header)):
        assert row['header'] == str(expected_header) and row['header_sha256'] == sha(header)
        assert sha(row['depfile']) == row['depfile_sha256']
        assert str(expected_header) in deps(row['depfile'])
        assert str(BUILD/'build/ServiceDescription.h') not in deps(row['depfile'])
    assert reused['source'] == DESCRIPTION_SOURCE and reused['new_header_byte_identical']
    candidate, unstripped = run/'candidate.bin', run/'candidate.unstripped'
    assert sha(candidate) == proof['candidate_sha256'] != PREDECESSOR_SHA
    expected = json.loads((snapshot/'xbmc/interfaces/json-rpc/schema/methods.json').read_text())
    actual = verify_methods(candidate.read_bytes(), expected)
    prior = binary_methods_bytes((PREDECESSOR/'candidate.bin').read_bytes())
    assert set(prior) == set(expected)
    assert sorted(name for name in expected if prior[name] != expected[name]) == ['Player.BobiControl']
    assert binary_method(candidate) == proof['binary_bobicontrol'] == expected['Player.BobiControl']
    report = dict(state='VERIFYING', build_result_sha256=sha(args.build_result), verifier_sha256=sha(__file__),
        candidate_sha256=sha(candidate), unstripped_sha256=sha(unstripped),
        predecessor_sha256=PREDECESSOR_SHA, source_predecessor_parity=True,
        schema_consumers=consumers, schema_include_sources=includes,
        schema_consumer_provenance=dict(rebuilt=rebuilt, reused=reused),
        rpc_method_count=len(actual), rpc_methods_exact=True,
        predecessor_changed_methods=['Player.BobiControl'], binary_bobicontrol=actual['Player.BobiControl'],
        retained_archive_members={})
    for archive in ARCHIVES:
        replaced = ('JSONRPC.cpp.o',) if archive == ARCHIVES[2] else ()
        new, old = run/Path(archive).name, PREDECESSOR/Path(archive).name
        report['retained_archive_members'][archive] = retained_members(old, new, replaced)
        assert report['retained_archive_members'][archive] == proof['retained_archive_members'][archive]
        if not replaced:
            assert sha(new) == sha(old), 'UNTOUCHED_ARCHIVE_CHANGED'
    import hashlib
    obj = run/'candidate'/Path(RPC_SOURCE).parent/'JSONRPC.cpp.o'
    member = tool('ar', 'p', run/'jsonrpc_interface.a', 'JSONRPC.cpp.o', binary=True)
    assert hashlib.sha256(member).hexdigest() == sha(obj) == rebuilt['object_sha256']
    member = tool('ar', 'p', run/'jsonrpc_interface.a', 'JSONServiceDescription.cpp.o', binary=True)
    assert hashlib.sha256(member).hexdigest() == reused['object_sha256']
    assert not (symbols(PREDECESSOR/'candidate.unstripped')-symbols(unstripped)), 'BOBI_SYMBOL_LOSS'
    for name in ('language', 'request_id', 'file_identity', 'url_sha256'):
        assert ('bobitv.original_audio.'+name).encode() in candidate.read_bytes()
    assert b'AM6B_DIAG event=' not in candidate.read_bytes()
    report.update(predecessor_bobi_symbols_preserved=True, original_audio_binding_properties_present=True)
    for label, flags in (('architecture_attributes', ['-A']), ('dependencies', ['-d'])):
        before, after = tool('readelf', *flags, PREDECESSOR/'candidate.bin'), tool('readelf', *flags, candidate)
        if label == 'dependencies':
            def needed(text):
                return [line.split(')', 1)[-1] for line in text.splitlines()
                        if any(token in line for token in ('(NEEDED)', '(RPATH)', '(RUNPATH)'))]
            before, after = needed(before), needed(after)
        assert before == after, label+'_DRIFT'
        report[label+'_unchanged'] = True
    restrip = run/'same-artifact-restrip.bin'
    assert not restrip.exists()
    shutil.copyfile(unstripped, restrip)
    subprocess.run([str(TOOLS/'armv8a-libreelec-linux-gnueabihf-strip'), '--strip-unneeded', str(restrip)], check=True)
    assert sha(restrip) == sha(candidate)
    report.update(state='VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED', same_artifact_restrip=True,
        original_tree_unchanged=all(sha(path) == digest for path, digest in proof['inputs'].items()),
        predecessor_unchanged=all(sha(path) == digest for path, digest in proof['predecessor_inputs'].items()),
        limitations='Exact 8bb2 object inheritance plus all 184 binary method schemas, not device handoff certification.')
    assert report['original_tree_unchanged'] and report['predecessor_unchanged']
    with (run/'artifact-verification.json').open('x') as out:
        json.dump(report, out, indent=2)
    print(json.dumps(dict(state=report['state'], candidate_sha256=sha(candidate), methods=len(actual),
                         verification=str(run/'artifact-verification.json'))), flush=True)


if __name__ == '__main__':
    main()

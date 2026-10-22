"""Verify the exact ARM artifact, retained archive members, and source provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from build_isolated import BUILD, EXPECTED, SOURCE, TOOLS, UNITS, UNSTRIPPED, sha

HERE = Path(__file__).resolve().parent
REVIEW = Path('/mnt/d/AM6B-Project/AM6B-review-release317-20261017/reviews/release317')


def tool(name, *args, binary=False):
    return subprocess.check_output([str(TOOLS/('armv8a-libreelec-linux-gnueabihf-' + name)),
                                    *map(str, args)], text=not binary)


def symbols(path):
    return {re.sub(r' \[clone .*$', '', line.split(None, 2)[2])
            for line in tool('nm', '-C', '--defined-only', path).splitlines()
            if len(line.split(None, 2)) == 3 and 'Bobi' in line}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-result', type=Path, required=True)
    args = parser.parse_args()
    run = args.build_result.parent
    result = json.loads(args.build_result.read_text())
    assert result['state'] == 'BUILT_NOT_DEPLOYED' and result['original_tree_unchanged']
    baseline = Path(result['baseline_proof']).parent/'baseline.bin'
    candidate, unstripped = run/'candidate.bin', run/'candidate.unstripped'
    assert sha(baseline) == EXPECTED and sha(BUILD/'kodi.bin') == UNSTRIPPED
    assert sha(candidate) == result['candidate_sha256']
    assert all(sha(run/'source-candidate'/name) == digest for name, digest in result['source_sha256'].items())
    report = dict(state='VERIFYING', build_result_sha256=sha(args.build_result),
                  candidate_sha256=sha(candidate), unstripped_sha256=sha(unstripped),
                  source_parity={}, retained_archive_members={})
    # This is a capability check against the real binary, not a false claim that
    # the current on-disk source was the source used to build its retained objects.
    missing = sorted(symbols(BUILD/'kodi.bin') - symbols(unstripped))
    assert not missing, 'BASELINE_BOBI_SYMBOL_LOSS:' + repr(missing)
    report['baseline_bobi_defined_symbols_preserved'] = True
    for name in ('language', 'request_id', 'file_identity', 'url_sha256'):
        key = ('bobitv.original_audio.' + name).encode()
        assert key in baseline.read_bytes() and key in candidate.read_bytes()
    assert b'AM6B_DIAG event=' not in candidate.read_bytes()
    report['original_audio_binding_properties_present'] = True
    # These two reconstructed starting TUs equal the older independently retained
    # clock317 audit source. Factory is unchanged; generated schema is audited by
    # method-set comparison below. VideoPlayer is the diagnosed/restored exception.
    for rel in ('xbmc/application/ApplicationPlayer.cpp', 'xbmc/interfaces/json-rpc/PlayerOperations.cpp'):
        previous = REVIEW/'continuation/clock317-native-source-audit/source'/rel
        assert sha(previous) == sha(HERE/'original'/rel), 'SOURCE_PARITY:' + rel
        report['source_parity'][rel] = dict(reference=str(previous), sha256=sha(previous))
    rel = 'xbmc/cores/playercorefactory/PlayerCoreConfig.cpp'
    assert sha(HERE/'original'/rel) == sha(run/'source-candidate'/rel)
    report['source_parity'][rel] = dict(unchanged=True, sha256=sha(HERE/'original'/rel))
    prior_header = REVIEW/'native/audio314/candidate/native-patched/xbmc/cores/VideoPlayer/VideoPlayer.h'
    assert sha(prior_header) == sha(run/'source-candidate/xbmc/cores/VideoPlayer/VideoPlayer.h')
    report['restored_exact_audio314_layout_sha256'] = sha(prior_header)
    before = json.loads((HERE/'original/xbmc/interfaces/json-rpc/schema/methods.json').read_text())
    after = json.loads((run/'source-candidate/xbmc/interfaces/json-rpc/schema/methods.json').read_text())
    assert set(before) <= set(after)
    changed = sorted(key for key in before if before[key] != after[key])
    assert changed == ['Player.BobiControl']
    report['rpc_schema_changed_methods'] = changed
    report['rpc_schema_existing_methods_preserved'] = True
    for archive in sorted({unit[2] for unit in UNITS}):
        old, new = BUILD/archive, run/Path(archive).name
        members = tool('ar', 't', old).splitlines()
        assert members == tool('ar', 't', new).splitlines()
        replacements = {Path(source).name + '.o' for source, _, path in UNITS if path == archive}
        retained = {}
        for member in members:
            if member not in replacements:
                previous, current = tool('ar', 'p', old, member, binary=True), tool('ar', 'p', new, member, binary=True)
                assert previous == current, 'RETAINED_OBJECT_CHANGED:' + member
                retained[member] = hashlib.sha256(current).hexdigest()
        report['retained_archive_members'][archive] = retained
    for label, flags in (('architecture_attributes', ['-A']), ('dependencies', ['-d'])):
        before, after = tool('readelf', *flags, baseline), tool('readelf', *flags, candidate)
        if label == 'dependencies':
            def needed(value):
                return [line.split(')', 1)[-1] for line in value.splitlines()
                        if any(token in line for token in ('(NEEDED)', '(RPATH)', '(RUNPATH)'))]
            before, after = needed(before), needed(after)
        assert before == after, label + '_DRIFT'
        report[label + '_unchanged'] = True
    restrip = run/'same-artifact-restrip.bin'
    assert not restrip.exists()
    shutil.copyfile(unstripped, restrip)
    subprocess.run([str(TOOLS/'armv8a-libreelec-linux-gnueabihf-strip'), '--strip-unneeded', str(restrip)], check=True)
    assert sha(restrip) == sha(candidate)
    report.update(state='VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED', same_artifact_restrip=True,
                  retained_object_scope='All unmodified members of all four replaced archives are byte-identical; other linker inputs remain original.',
                  limitations='Symbol/property and source audits establish listed retained contracts, not complete native behavioral equivalence.')
    with (run/'artifact-verification.json').open('x') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(dict(state=report['state'], candidate_sha256=sha(candidate),
                         verification=str(run/'artifact-verification.json'))))


if __name__ == '__main__':
    main()

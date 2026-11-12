"""Build one directory-provider TU on frozen completion2114 archives.

The maintained CE build and both older overlays are read-only. The predecessor
must relink byte-for-byte before replacing one copied archive member. This
builder never connects to a device.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

PREDECESSOR_SHA = '4177ade3b59b0c69062f0e49d1e6dc27fa4dba78aed883721e9e83d4fc36fc6a'
PREDECESSOR_PROOF_SHA = '0b54e0b6b3e982dd9e02f2867cdbc6fc3df36afd7709e7cf4c368ec655651f7c'
UNIT = 'xbmc/guilib/listproviders/DirectoryProvider.cpp'
OBJECT = 'build/guilib_listproviders/CMakeFiles/guilib_listproviders.dir/DirectoryProvider.cpp.o'
ARCHIVE = 'build/guilib_listproviders/guilib_listproviders.a'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predecessor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    legacy = module('focus_legacy_build', root/'ce-jsonrpc-schema-20261022/build_isolated.py')
    harness = module('directory_visibility_harness', root/'tests/run_directory_visibility_test.py')
    sha = legacy.sha
    proof = args.predecessor/'build-result.json'
    assert sha(proof) == PREDECESSOR_PROOF_SHA, 'PREDECESSOR_PROOF_CHANGED'
    previous = json.loads(proof.read_text())
    assert previous['state'] == 'BUILT_NOT_DEPLOYED' and previous['original_tree_unchanged']
    assert previous['candidate_sha256'] == sha(args.predecessor/'candidate.bin') == PREDECESSOR_SHA
    assert {str(p.relative_to(args.predecessor/'source-candidate')):sha(p)
            for p in (args.predecessor/'source-candidate').rglob('*') if p.is_file()} == previous['source_sha256']
    assert all(sha(path) == digest for path,digest in previous['inputs'].items()), 'FROZEN_INPUT_CHANGED'
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='ce-home-focus-', dir=args.output))
    snapshot = run/'source-candidate'
    shutil.copytree(args.predecessor/'source-candidate', snapshot)
    inputs = dict(previous['inputs'])
    for name in ('build-result.json', 'candidate.bin', *[Path(a).name for a in legacy.ARCHIVES]):
        path = args.predecessor/name
        inputs[str(path)] = sha(path)
    for path in (args.predecessor/'source-candidate').rglob('*'):
        if path.is_file(): inputs[str(path)] = sha(path)
    for relative in (*harness.METHODS, 'xbmc/guilib/GUIWindow.cpp'):
        path = legacy.SOURCE/relative
        inputs[str(path)] = sha(path)
        target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    patch = root/'patches/0007-bobbi-directory-visibility.patch'
    for path in (patch, root/'patches/series.json', Path(__file__),
                 root/'tests/run_directory_visibility_test.py', root/'tests/directory_visibility_test.cpp'):
        inputs[str(path)] = sha(path)
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=snapshot, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=snapshot, check=True)
    source_hashes = {str(p.relative_to(snapshot)):sha(p) for p in snapshot.rglob('*') if p.is_file()}
    report = dict(state='STARTED', build_kind='home_focus', predecessor_sha256=PREDECESSOR_SHA,
        predecessor_proof_sha256=PREDECESSOR_PROOF_SHA, canonical_patch_sha256=sha(patch),
        series_sha256=sha(root/'patches/series.json'), source_sha256=source_hashes,
        inputs=inputs, commands={}, objects={}, recompiled_units=[UNIT], retained_archive_members={})

    def execute(argv, label):
        report['commands'][label] = list(map(str, argv))
        with (run/(label+'.log')).open('w') as stream:
            subprocess.run(argv, cwd=legacy.BUILD, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=1200)

    raw = legacy.command('kodi.bin')
    assert raw.startswith(': && ') and raw.endswith(' && :')
    link = shlex.split(raw[5:-5])
    assert not any(arg in ('&&', ';', '|') for arg in link)
    replacements = {archive:run/Path(archive).name for archive in (*legacy.ARCHIVES, ARCHIVE)}
    assert ARCHIVE in link and str(legacy.BUILD/ARCHIVE) in inputs, 'DIRECTORY_LINK_INPUT_CHANGED'
    for archive, target in replacements.items():
        before = legacy.BUILD/archive if archive == ARCHIVE else args.predecessor/Path(archive).name
        shutil.copyfile(before, target)

    def relink(label):
        argv = [str(replacements.get(arg, arg)) for arg in link]
        binary = run/(label+'.unstripped')
        legacy.output_arg(argv, '-o', binary)
        execute(argv, label+'-link')
        stripped = run/(label+'.bin')
        shutil.copyfile(binary, stripped)
        execute([str(legacy.TOOLS/'armv8a-libreelec-linux-gnueabihf-strip'), '--strip-unneeded', str(stripped)], label+'-strip')
        report[label+'_sha256'] = sha(stripped)
        return stripped

    try:
        test_path, tests = harness.run(snapshot, run/'production-tests')
        report['production_tests'] = dict(path=str(test_path.relative_to(run)), sha256=sha(test_path),
            candidate_passed=tests['tests'][0]['passed'], negative_control_failed=tests['tests'][1]['passed'],
            interleaved_control_failed=tests['tests'][2]['passed'])
        obj = run/'DirectoryProvider.cpp.o'
        argv = shlex.split(legacy.command(OBJECT))
        argv[1:1] = ['-I'+str(snapshot/'xbmc')]
        argv += ['-iquote', str((legacy.SOURCE/UNIT).parent)]
        for option, value in (('-o', obj), ('-MF', str(obj)+'.d'), ('-MT', obj), ('-c', snapshot/UNIT)):
            legacy.output_arg(argv, option, value)
        execute(argv, 'DirectoryProvider-compile')
        dependencies = legacy.deps(str(obj)+'.d')
        assert str(snapshot/UNIT) in dependencies and str(legacy.SOURCE/UNIT) not in dependencies
        report['objects'][UNIT] = dict(sha256=sha(obj), depfile_sha256=sha(str(obj)+'.d'))
        assert sha(relink('predecessor-relink')) == PREDECESSOR_SHA, 'PREDECESSOR_RELINK_MISMATCH'
        target = replacements[ARCHIVE]
        execute([str(legacy.TOOLS/'armv8a-libreelec-linux-gnueabihf-gcc-ar'), 'r', str(target), str(obj)], 'DirectoryProvider-archive')
        execute([str(legacy.TOOLS/'armv8a-libreelec-linux-gnueabihf-gcc-ranlib'), str(target)], 'DirectoryProvider-ranlib')
        report['retained_archive_members'][ARCHIVE] = legacy.retained_members(legacy.BUILD/ARCHIVE, target, (obj.name,))
        for archive in legacy.ARCHIVES:
            assert sha(replacements[archive]) == sha(args.predecessor/Path(archive).name), 'COMPLETION_ARCHIVE_CHANGED'
        candidate = relink('candidate')
        assert sha(candidate) != PREDECESSOR_SHA and b'completion_observation' in candidate.read_bytes()
        assert legacy.binary_method(candidate) == legacy.binary_method(args.predecessor/'candidate.bin')
        for flags in (['-A'], ['-d']):
            before = legacy.tool('readelf', *flags, args.predecessor/'candidate.bin')
            after = legacy.tool('readelf', *flags, candidate)
            if flags == ['-d']:
                def needed(text):
                    return [line.split(')',1)[-1] for line in text.splitlines()
                            if any(token in line for token in ('(NEEDED)', '(RPATH)', '(RUNPATH)'))]
                before, after = needed(before), needed(after)
            assert before == after, 'NATIVE_ABI_OR_DEPENDENCY_DRIFT'
        report.update(state='BUILT_NOT_DEPLOYED', architecture_and_dependencies_unchanged=True,
            binary_bobicontrol_schema_unchanged=True, completion_archives_unchanged=True,
            bytes=candidate.stat().st_size)
    except BaseException:
        report['state'] = 'FAILED_NOT_DEPLOYED'
        raise
    finally:
        report['original_tree_unchanged'] = all(sha(path) == digest for path,digest in inputs.items())
        report['predecessor_unchanged'] = report['original_tree_unchanged']
        (run/'build-result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(run=str(run), state=report['state'], candidate_sha256=report.get('candidate_sha256'),
                              unchanged=report['original_tree_unchanged'])), flush=True)
        assert report['original_tree_unchanged']


if __name__ == '__main__':
    main()

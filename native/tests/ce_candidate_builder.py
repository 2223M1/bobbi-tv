"""One isolated CE overlay pipeline. Profiles declare only the proven delta.

The existing schema builder owns the frozen toolchain and archive primitives.
No maintained source, old proof or device is written. A candidate is not
deployment authority.
"""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def source_hashes(source, sha):
    return {str(path.relative_to(source)): sha(path) for path in source.rglob('*') if path.is_file()}


def checked_predecessor(profile, predecessor, sha):
    proof = predecessor/'build-result.json'
    if profile.get('predecessor_proof_sha256'):
        assert sha(proof) == profile['predecessor_proof_sha256'], 'PREDECESSOR_PROOF_CHANGED'
    previous = json.loads(proof.read_text())
    expected = previous['candidate_sha256']
    assert previous['state'] == 'BUILT_NOT_DEPLOYED' and previous['original_tree_unchanged']
    assert sha(predecessor/'candidate.bin') == expected, 'PREDECESSOR_BINARY_CHANGED'
    if profile.get('predecessor_sha256'):
        assert expected == profile['predecessor_sha256'], 'PREDECESSOR_GENERATION_CHANGED'
    if profile.get('verified_predecessor'):
        verified = json.loads((predecessor/'artifact-verification.json').read_text())
        assert verified['state'] == 'VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED'
        assert expected == verified['candidate_sha256'], 'PREDECESSOR_VERIFICATION_CHANGED'
    assert source_hashes(predecessor/'source-candidate', sha) == previous['source_sha256'], 'PREDECESSOR_SOURCE_CHANGED'
    assert all(sha(path) == digest for path, digest in previous['inputs'].items()), 'FROZEN_INPUT_CHANGED'
    return previous


def patch_bytes(patch, contexts):
    delta = patch.read_text()
    for before, after in contexts:
        assert delta.count(before) == 1, 'CANONICAL_CE_CONTEXT_DRIFT'
        assert [line for line in before.splitlines() if line.startswith('+')] == [
            line for line in after.splitlines() if line.startswith('+')], 'CANONICAL_ADDITION_CHANGED'
        delta = delta.replace(before, after)
    return delta.encode()


def link_command(raw):
    assert raw.startswith(': && ') and raw.endswith(' && :'), 'LINK_COMMAND_SHAPE_CHANGED'
    argv = shlex.split(raw[5:-5])
    assert not any(arg in ('&&', ';', '|') for arg in argv), 'LINK_SHELL_OPERATOR'
    return argv


def needed(text):
    return [line.split(')', 1)[-1] for line in text.splitlines()
            if any(token in line for token in ('(NEEDED)', '(RPATH)', '(RUNPATH)'))]


def build(profile, predecessor, output, entry, root=None):
    root = root or Path(__file__).resolve().parents[1]
    legacy_path = root/'ce-jsonrpc-schema-20261022/build_isolated.py'
    legacy = module('ce_frozen_schema_build', legacy_path)
    sha = legacy.sha
    previous = checked_predecessor(profile, predecessor, sha)
    expected = previous['candidate_sha256']
    patch = root/'patches'/profile['patch']
    series = root/'patches/series.json'
    declaration = json.loads(series.read_text())
    assert any(row['file'] == profile['patch'] and row['sha256'] == sha(patch)
               for row in declaration['patches']), 'CANONICAL_PATCH_NOT_IN_SERIES'
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=profile['prefix'], dir=output))
    snapshot = run/'source-candidate'
    inputs = dict(previous['inputs'])
    paths = [predecessor/name for name in ('build-result.json', 'candidate.bin',
             *[Path(archive).name for archive in legacy.ARCHIVES])]
    if profile.get('verified_predecessor'):
        paths.append(predecessor/'artifact-verification.json')
    paths += [patch, series, Path(entry), Path(__file__), legacy_path]
    paths += [path for path in (predecessor/'source-candidate').rglob('*') if path.is_file()]
    harness = None
    copy_sources = list(profile.get('copy_sources', ()))
    if profile.get('production_harness'):
        harness_path = root/'tests'/profile['production_harness']
        harness = module('ce_production_harness', harness_path)
        copy_sources += list(harness.METHODS)
        paths += [harness_path, root/'tests'/profile['production_fixture']]
    paths += [legacy.SOURCE/relative for relative in copy_sources]
    inputs.update({str(path): sha(path) for path in paths})
    report = dict(state='STARTED', build_kind=profile['name'], predecessor_sha256=expected,
        predecessor_proof_sha256=sha(predecessor/'build-result.json'), canonical_patch_sha256=sha(patch),
        series_sha256=sha(series), inputs=inputs, commands={}, objects={},
        recompiled_units=[unit[0] for unit in profile['units']], retained_archive_members={})

    def execute(argv, label):
        report['commands'][label] = list(map(str, argv))
        with (run/(label+'.log')).open('x') as stream:
            subprocess.run(argv, cwd=legacy.BUILD, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=1200)

    try:
        shutil.copytree(predecessor/'source-candidate', snapshot)
        for relative in copy_sources:
            target = snapshot/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(legacy.SOURCE/relative, target)
        delta = patch_bytes(patch, profile.get('contexts', ()))
        report['ce_context_patch_sha256'] = hashlib.sha256(delta).hexdigest()
        subprocess.run(['git', 'apply', '--recount', '--check'], input=delta, cwd=snapshot, check=True)
        subprocess.run(['git', 'apply', '--recount'], input=delta, cwd=snapshot, check=True)
        report['source_sha256'] = source_hashes(snapshot, sha)
        header = profile.get('layout_header')
        if header:
            deps = subprocess.check_output([str(legacy.TOOLS/'ninja'), '-C', str(legacy.BUILD), '-t', 'deps'], text=True)
            consumers = {block.splitlines()[0].split(':', 1)[0] for block in deps.split('\n\n')
                         if any(line.strip() == str(legacy.SOURCE/header) for line in block.splitlines())}
            assert consumers == {unit[1] for unit in profile['units']}, 'VIDEOPLAYER_LAYOUT_CONSUMER_DRIFT'
            report['layout_consumers'] = sorted(consumers)
        if harness:
            test_path, tests = harness.run(snapshot, run/'production-tests')
            report['production_tests'] = dict(path=str(test_path.relative_to(run)), sha256=sha(test_path),
                candidate_passed=tests['tests'][0]['passed'], negative_control_failed=tests['tests'][1]['passed'],
                interleaved_control_failed=tests['tests'][2]['passed'])

        def compile_unit(unit):
            source, original, archive = unit
            obj = run/(Path(source).name+'.o')
            argv = shlex.split(legacy.command(original))
            argv[1:1] = ['-I'+str(snapshot/'xbmc')]
            argv += ['-iquote', str((legacy.SOURCE/source).parent)]
            for option, value in (('-o', obj), ('-MF', str(obj)+'.d'), ('-MT', obj), ('-c', snapshot/source)):
                legacy.output_arg(argv, option, value)
            execute(argv, Path(source).stem+'-compile')
            dependencies = legacy.deps(str(obj)+'.d')
            dependency = header or source
            assert str(snapshot/dependency) in dependencies and str(legacy.SOURCE/dependency) not in dependencies
            report['objects'][source] = dict(sha256=sha(obj), depfile_sha256=sha(str(obj)+'.d'))
            return obj, archive

        link = link_command(legacy.command('kodi.bin'))
        archives = (*legacy.ARCHIVES, *profile.get('extra_archives', ()))
        assert len(archives) == len(set(archives)), 'DUPLICATE_ARCHIVE'
        replacements = {archive: run/Path(archive).name for archive in archives}
        assert len({path.name for path in replacements.values()}) == len(archives), 'ARCHIVE_NAME_COLLISION'
        origins = {archive: (predecessor/Path(archive).name if archive in legacy.ARCHIVES else legacy.BUILD/archive)
                   for archive in archives}
        for archive, origin in origins.items():
            assert archive in link and str(origin) in inputs, 'LINK_INPUT_CHANGED'
            shutil.copyfile(origin, replacements[archive])

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

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(profile['units'])) as pool:
            objects = list(pool.map(compile_unit, profile['units']))
        assert sha(relink('predecessor-relink')) == expected, 'PREDECESSOR_RELINK_MISMATCH'
        for obj, archive in objects:
            execute([str(legacy.TOOLS/'armv8a-libreelec-linux-gnueabihf-gcc-ar'), 'r', str(replacements[archive]), str(obj)], obj.stem+'-archive')
            execute([str(legacy.TOOLS/'armv8a-libreelec-linux-gnueabihf-gcc-ranlib'), str(replacements[archive])], obj.stem+'-ranlib')
        for archive, target in replacements.items():
            replaced = tuple(obj.name for obj, path in objects if path == archive)
            report['retained_archive_members'][archive] = legacy.retained_members(origins[archive], target, replaced)
        if profile.get('preserve_predecessor_archives'):
            assert all(sha(replacements[archive]) == sha(origins[archive]) for archive in legacy.ARCHIVES), 'COMPLETION_ARCHIVE_CHANGED'
            report['completion_archives_unchanged'] = True
        candidate = relink('candidate')
        assert sha(candidate) != expected and b'completion_observation' in candidate.read_bytes()
        assert legacy.binary_method(candidate) == legacy.binary_method(predecessor/'candidate.bin')
        for flags in (['-A'], ['-d']):
            before, after = (legacy.tool('readelf', *flags, binary) for binary in (predecessor/'candidate.bin', candidate))
            assert (needed(before) == needed(after) if flags == ['-d'] else before == after), 'NATIVE_ABI_OR_DEPENDENCY_DRIFT'
        report.update(state='BUILT_NOT_DEPLOYED', architecture_and_dependencies_unchanged=True,
                      binary_bobicontrol_schema_unchanged=True, bytes=candidate.stat().st_size)
    except BaseException:
        report['state'] = 'FAILED_NOT_DEPLOYED'
        raise
    finally:
        unchanged = all(sha(path) == digest for path, digest in inputs.items())
        report.update(original_tree_unchanged=unchanged, predecessor_unchanged=unchanged)
        (run/'build-result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(run=str(run), state=report['state'], candidate_sha256=report.get('candidate_sha256'),
                              unchanged=unchanged)), flush=True)
        assert unchanged, 'FROZEN_INPUT_CHANGED_DURING_BUILD'
    return run, report


def main(profile, entry, description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--predecessor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(profile, args.predecessor, args.output, entry)

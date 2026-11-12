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


def predecessor_inputs(profile, previous, sha):
    """Archived build scripts may replace evolved workspace paths, never bytes."""
    inputs = dict(previous['inputs'])
    for original, archived in profile.get('historical_inputs', {}).items():
        assert original in inputs and archived not in inputs, 'HISTORICAL_INPUT_SCOPE'
        expected = inputs.pop(original)
        assert sha(archived) == expected, 'HISTORICAL_INPUT_CHANGED'
        inputs[archived] = expected
    assert all(sha(path) == digest for path, digest in inputs.items()), 'FROZEN_INPUT_CHANGED'
    return inputs


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
    predecessor_inputs(profile, previous, sha)
    return previous


def patch_bytes(patch, contexts, variant_hunks=()):
    delta = patch.read_text()
    for before, after in contexts:
        assert delta.count(before) == 1, 'CANONICAL_CE_CONTEXT_DRIFT'
        assert [line for line in before.splitlines() if line.startswith('+')] == [
            line for line in after.splitlines() if line.startswith('+')], 'CANONICAL_ADDITION_CHANGED'
        delta = delta.replace(before, after)
    # Real downstream branches can contain extra behaviour, not just spelling
    # differences. These explicitly named hunks are reviewed separately; never
    # silently relax the context-only algorithm guard above.
    for name, before, after in variant_hunks:
        assert name and before != after and delta.count(before) == 1, 'PLATFORM_VARIANT_DRIFT'
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


def schema_delta(before, after, allowed):
    """A new schema must declare every changed method, not weaken the old gate."""
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    assert changed == set(allowed), 'UNDECLARED_SCHEMA_DELTA'
    assert all(key in before and key in after for key in allowed), 'SCHEMA_METHOD_REMOVED'
    return sorted(changed)


def archive_origins(legacy, previous, profile, predecessor):
    # An overlay must inherit ALL prior archive replacements (including Home),
    # not silently relink a newer delta against the original unfixed archive.
    inherited = tuple(dict.fromkeys((*legacy.ARCHIVES, *previous.get('retained_archive_members', {}))))
    extra = tuple(profile.get('extra_archives', ()))
    archives = tuple(dict.fromkeys((*inherited, *extra)))
    assert len(extra) == len(set(extra)), 'DUPLICATE_ARCHIVE'
    assert len({Path(path).name for path in archives}) == len(archives), 'ARCHIVE_NAME_COLLISION'
    return {archive: (predecessor/Path(archive).name if archive in inherited else legacy.BUILD/archive)
            for archive in archives}


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
    inputs = predecessor_inputs(profile, previous, sha)
    origins = archive_origins(legacy, previous, profile, predecessor)
    paths = [predecessor/name for name in ('build-result.json', 'candidate.bin',
             *[Path(archive).name for archive in legacy.ARCHIVES])]
    if profile.get('verified_predecessor'):
        paths.append(predecessor/'artifact-verification.json')
    paths += [patch, series, Path(entry), Path(__file__), legacy_path]
    followup = root/profile['platform_patch'] if profile.get('platform_patch') else None
    if followup:
        paths.append(followup)
    paths += [path for path in (predecessor/'source-candidate').rglob('*') if path.is_file()]
    paths += list(origins.values())
    schema = legacy.SOURCE/'xbmc/interfaces/json-rpc/schema'
    if profile.get('schema_methods'):
        paths += [schema/name for name in ('version.txt', 'license.txt', 'types.json', 'notifications.json')]
        paths.append(legacy.TOOLS/'JsonSchemaBuilder')
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
    if profile.get('historical_inputs'):
        report['historical_input_locations'] = profile['historical_inputs']

    def execute(argv, label, cwd=None):
        report['commands'][label] = list(map(str, argv))
        with (run/(label+'.log')).open('x') as stream:
            subprocess.run(argv, cwd=cwd or legacy.BUILD, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=1200)

    try:
        shutil.copytree(predecessor/'source-candidate', snapshot)
        for relative in copy_sources:
            target = snapshot/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(legacy.SOURCE/relative, target)
        variants = profile.get('variant_hunks', ())
        delta = patch_bytes(patch, profile.get('contexts', ()), variants)
        report['ce_context_patch_sha256'] = hashlib.sha256(delta).hexdigest()
        if variants:
            report['platform_variants'] = [name for name, before, after in variants]
        subprocess.run(['git', 'apply', '--recount', '--check'], input=delta, cwd=snapshot, check=True)
        subprocess.run(['git', 'apply', '--recount'], input=delta, cwd=snapshot, check=True)
        if followup:
            report['platform_patch_sha256'] = sha(followup)
            subprocess.run(['git', 'apply', '--recount', '--check', str(followup)], cwd=snapshot, check=True)
            subprocess.run(['git', 'apply', '--recount', str(followup)], cwd=snapshot, check=True)
        report['source_sha256'] = source_hashes(snapshot, sha)
        header = profile.get('layout_header')
        if header:
            deps = subprocess.check_output([str(legacy.TOOLS/'ninja'), '-C', str(legacy.BUILD), '-t', 'deps'], text=True)
            consumers = {block.splitlines()[0].split(':', 1)[0] for block in deps.split('\n\n')
                         if any(line.strip() == str(legacy.SOURCE/header) for line in block.splitlines())}
            layout_sources = set(profile.get('layout_units', [unit[0] for unit in profile['units']]))
            assert consumers == {unit[1] for unit in profile['units'] if unit[0] in layout_sources}, 'VIDEOPLAYER_LAYOUT_CONSUMER_DRIFT'
            report['layout_consumers'] = sorted(consumers)
        generated = None
        if profile.get('schema_methods'):
            methods = Path('xbmc/interfaces/json-rpc/schema/methods.json')
            report['schema_changed_methods'] = schema_delta(
                json.loads((predecessor/'source-candidate'/methods).read_text()),
                json.loads((snapshot/methods).read_text()), profile['schema_methods'])
            consumers, includes = legacy.schema_consumers()
            assert set(consumers) <= {unit[1] for unit in profile['units']}, 'SCHEMA_CONSUMER_NOT_REBUILT'
            report.update(schema_consumers=consumers, schema_include_sources=includes)
            generated = run/'generated'
            generated.mkdir()
            execute([str(legacy.TOOLS/'JsonSchemaBuilder'), str(schema/'version.txt'), str(schema/'license.txt'),
                str(snapshot/methods), str(schema/'types.json'), str(schema/'notifications.json')], 'schema', generated)
            report['generated_header_sha256'] = sha(generated/'ServiceDescription.h')
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
            if generated:
                argv[1:1] = ['-I'+str(generated)]
            argv += ['-iquote', str((legacy.SOURCE/source).parent)]
            for option, value in (('-o', obj), ('-MF', str(obj)+'.d'), ('-MT', obj), ('-c', snapshot/source)):
                legacy.output_arg(argv, option, value)
            execute(argv, Path(source).stem+'-compile')
            dependencies = legacy.deps(str(obj)+'.d')
            dependency = header if header and source in layout_sources else source
            assert str(snapshot/dependency) in dependencies and str(legacy.SOURCE/dependency) not in dependencies
            if generated and original in report['schema_consumers']:
                assert str(generated/'ServiceDescription.h') in dependencies, 'WRONG_SCHEMA_HEADER'
                assert str(legacy.BUILD/'build/ServiceDescription.h') not in dependencies, 'MIXED_SCHEMA_HEADER'
            report['objects'][source] = dict(sha256=sha(obj), depfile_sha256=sha(str(obj)+'.d'))
            return obj, archive

        link = link_command(legacy.command('kodi.bin'))
        archives = tuple(origins)
        replacements = {archive: run/Path(archive).name for archive in archives}
        assert len({path.name for path in replacements.values()}) == len(archives), 'ARCHIVE_NAME_COLLISION'
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
        actual_schema = legacy.binary_method(candidate)
        if generated:
            expected_schema = json.loads((snapshot/'xbmc/interfaces/json-rpc/schema/methods.json').read_text())['Player.BobiControl']
            assert actual_schema == expected_schema, 'BINARY_BOBICONTROL_SCHEMA_MISMATCH'
            report.update(binary_bobicontrol_schema_matches_source=True, binary_bobicontrol=actual_schema)
        else:
            assert actual_schema == legacy.binary_method(predecessor/'candidate.bin')
        for flags in (['-A'], ['-d']):
            before, after = (legacy.tool('readelf', *flags, binary) for binary in (predecessor/'candidate.bin', candidate))
            assert (needed(before) == needed(after) if flags == ['-d'] else before == after), 'NATIVE_ABI_OR_DEPENDENCY_DRIFT'
        report.update(state='BUILT_NOT_DEPLOYED', architecture_and_dependencies_unchanged=True,
                      binary_bobicontrol_schema_unchanged=not bool(generated), bytes=candidate.stat().st_size)
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

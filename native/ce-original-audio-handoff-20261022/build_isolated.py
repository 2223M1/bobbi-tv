"""Isolated F9 original-audio/handoff build; never modify the verified tree.

Ninja is queried only for its compiler/linker argv. All changed TUs, generated
schema, copied archives, depfiles and linked binaries live in a fresh run.
"""
import argparse
import concurrent.futures
import hashlib
import json
import shlex
import shutil
import subprocess
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
TARGET = Path('/opt/am6b-maintainable-r10-20260922/build.CoreELEC-Amlogic-ng.arm-21')
SOURCE = TARGET / 'build/kodi-e0614d7a6713369bbcfe42152223f1cdaec3dbf1'
BUILD = SOURCE / '.armv8a-libreelec-linux-gnueabihf'
TOOLS = TARGET / 'toolchain/bin'
EXPECTED = '8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b'
UNSTRIPPED = '571aa622dde43551b192d9ceb3dc9efdc28bb937a66e3c3ddf33e012bc17101a'
UNITS = (
    ('xbmc/cores/VideoPlayer/VideoPlayer.cpp', 'build/cores/VideoPlayer/CMakeFiles/VideoPlayer.dir/VideoPlayer.cpp.o', 'build/cores/VideoPlayer/VideoPlayer.a'),
    ('xbmc/application/ApplicationPlayer.cpp', 'build/application/CMakeFiles/application.dir/ApplicationPlayer.cpp.o', 'build/application/application.a'),
    ('xbmc/interfaces/json-rpc/PlayerOperations.cpp', 'build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/PlayerOperations.cpp.o', 'build/interfaces/json-rpc/jsonrpc_interface.a'),
    ('xbmc/interfaces/json-rpc/JSONServiceDescription.cpp', 'build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/JSONServiceDescription.cpp.o', 'build/interfaces/json-rpc/jsonrpc_interface.a'),
    ('xbmc/cores/playercorefactory/PlayerCoreConfig.cpp', 'build/cores/playercorefactory/CMakeFiles/playercorefactory.dir/PlayerCoreConfig.cpp.o', 'build/cores/playercorefactory/playercorefactory.a'),
)

LAYOUT_HEADER = 'xbmc/cores/VideoPlayer/VideoPlayer.h'
LAYOUT_CONSUMERS = {unit[1] for unit in UNITS if Path(unit[0]).name in
                    ('VideoPlayer.cpp', 'ApplicationPlayer.cpp', 'PlayerCoreConfig.cpp')}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def commands(target):
    return subprocess.check_output([str(TOOLS / 'ninja'), '-C', str(BUILD), '-t',
                                    'commands', target], text=True).splitlines()


def output_arg(args, switch, path):
    assert args.count(switch) == 1
    args[args.index(switch) + 1] = str(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory-archive', type=Path)
    parser.add_argument('--expected-installed')
    parser.add_argument('--compile-only', action='store_true')
    parser.add_argument('--baseline-proof', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    assert sha(BUILD / 'kodi.bin') == UNSTRIPPED
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run = args.output_dir / ('run-' + str(time.time_ns()))
    run.mkdir()
    snapshot = run / 'source-candidate'
    shutil.copytree(OUT / 'candidate', snapshot)
    link_raw = commands('kodi.bin')[-1]
    assert link_raw.startswith(': && ') and link_raw.endswith(' && :')
    link = shlex.split(link_raw[5:-5])
    compiler = {source: shlex.split(commands(obj)[-1]) for source, obj, _ in UNITS}
    dependency_output = subprocess.check_output([str(TOOLS / 'ninja'), '-C', str(BUILD),
                                                '-t', 'deps'], text=True)
    header_consumers = {block.splitlines()[0].split(':', 1)[0]
                        for block in dependency_output.split('\n\n')
                        if any(line.strip() == str(SOURCE / LAYOUT_HEADER)
                               for line in block.splitlines())}
    assert header_consumers == LAYOUT_CONSUMERS, 'VIDEOPLAYER_HEADER_CONSUMER_DRIFT'
    assert not any(value in ('&&', ';', '|') for value in link)
    inputs = {str(BUILD / value): sha(BUILD / value) for value in link
              if value.endswith(('.a', '.o', '.so')) and (BUILD / value).is_file()}
    for source, obj, _ in UNITS:
        for path in (SOURCE / source, BUILD / obj):
            inputs[str(path)] = sha(path)
        assert sha(OUT / 'original' / source) == sha(SOURCE / source)
    for path in (BUILD / 'build.ninja', BUILD / 'kodi.bin', BUILD / 'build/ServiceDescription.h'):
        inputs[str(path)] = sha(path)
    inputs[str(SOURCE / LAYOUT_HEADER)] = sha(SOURCE / LAYOUT_HEADER)
    assert sha(OUT / 'original' / LAYOUT_HEADER) == inputs[str(SOURCE / LAYOUT_HEADER)]
    if args.directory_archive:
        assert args.expected_installed and args.directory_archive.is_file()
        inputs[str(args.directory_archive)] = sha(args.directory_archive)
    report = dict(state='STARTED', inputs=inputs, builder_sha256=sha(__file__),
                  source_sha256={str(p.relative_to(snapshot)): sha(p) for p in snapshot.rglob('*') if p.is_file()},
                  commands={}, original_tree_unchanged=False,
                  header_consumers=sorted(header_consumers), dependency_headers={},
                  recompiled_units=[unit[0] for unit in UNITS])
    def execute(argv, label, cwd=BUILD):
        report['commands'][label] = [str(v) for v in argv]
        with (run / (label + '.log')).open('x') as log:
            subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=1200)
    def relink(label, replacements=None):
        argv = [str((replacements or {}).get(value, value)) for value in link]
        binary = run / (label + '.unstripped')
        output_arg(argv, '-o', binary)
        execute(argv, label + '-link')
        stripped = run / (label + '.bin')
        shutil.copyfile(binary, stripped)
        execute([str(TOOLS / 'armv8a-libreelec-linux-gnueabihf-strip'), '--strip-unneeded', str(stripped)], label + '-strip')
        report[label + '_sha256'] = sha(stripped)
        return stripped
    def compile_unit(unit, label):
        source, original_object, archive = unit
        directory = run / label / Path(source).parent
        directory.mkdir(parents=True, exist_ok=True)
        obj = directory / (Path(source).name + '.o')
        argv = list(compiler[source])
        argv[1:1] = ['-I' + str(run / label / 'generated'), '-I' + str(snapshot / 'xbmc')]
        argv += ['-iquote', str((SOURCE / source).parent)]
        output_arg(argv, '-o', obj)
        output_arg(argv, '-MF', str(obj) + '.d')
        output_arg(argv, '-MT', obj)
        output_arg(argv, '-c', snapshot / source)
        execute(argv, label + '-' + Path(source).stem + '-compile')
        dependencies = Path(str(obj) + '.d').read_text().replace('\\\n', ' ').split()
        if original_object in LAYOUT_CONSUMERS:
            assert str(snapshot / LAYOUT_HEADER) in dependencies, 'WRONG_LAYOUT_HEADER:' + source
            assert str(SOURCE / LAYOUT_HEADER) not in dependencies, 'MIXED_LAYOUT_HEADER:' + source
            report['dependency_headers'][source] = str(snapshot / LAYOUT_HEADER)
        return obj, archive
    try:
        generated = run / 'candidate/generated'
        generated.mkdir(parents=True)
        schema = SOURCE / 'xbmc/interfaces/json-rpc/schema'
        execute([str(TOOLS / 'JsonSchemaBuilder'), str(schema / 'version.txt'), str(schema / 'license.txt'),
                 str(snapshot / 'xbmc/interfaces/json-rpc/schema/methods.json'),
                 str(schema / 'types.json'), str(schema / 'notifications.json')], 'candidate-schema', generated)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            objects = list(pool.map(lambda unit: compile_unit(unit, 'candidate'), UNITS))
        if args.compile_only:
            report['state'] = 'COMPILED_NOT_LINKED'
            return
        if args.baseline_proof:
            proof = json.loads(args.baseline_proof.read_text())
            assert proof['original_tree_unchanged'] and proof['baseline_sha256'] == EXPECTED
            assert sha(args.baseline_proof.parent / 'baseline.bin') == EXPECTED
            assert all(inputs.get(path) == digest for path, digest in proof['inputs'].items())
            report['baseline_sha256'] = EXPECTED
            report['baseline_proof'] = str(args.baseline_proof)
            report['baseline_inputs'] = proof['inputs']
            report['additional_inputs'] = {path: digest for path, digest in inputs.items()
                                           if path not in proof['inputs']}
        else:
            assert sha(relink('baseline')) == EXPECTED, 'BASELINE_RELINK_MISMATCH'
        replacements = {}
        if args.directory_archive:
            directory_copy = run / 'verified-filesystem.a'
            shutil.copyfile(args.directory_archive, directory_copy)
            replacements['build/filesystem/filesystem.a'] = directory_copy
            assert sha(relink('installed-baseline', replacements)) == args.expected_installed, 'INSTALLED_BASELINE_MISMATCH'
        for obj, archive in objects:
            if archive not in replacements:
                copied = run / (Path(archive).name)
                shutil.copyfile(BUILD / archive, copied)
                replacements[archive] = copied
            execute([str(TOOLS / 'armv8a-libreelec-linux-gnueabihf-gcc-ar'), 'r', str(replacements[archive]), str(obj)],
                    'candidate-' + obj.stem + '-archive')
        for archive in set(a for _, a in objects):
            execute([str(TOOLS / 'armv8a-libreelec-linux-gnueabihf-gcc-ranlib'), str(replacements[archive])],
                    'candidate-' + Path(archive).stem + '-ranlib')
        candidate = relink('candidate', replacements)
        report['bytes'] = candidate.stat().st_size
        assert sha(candidate) not in (EXPECTED, args.expected_installed)
        report['state'] = 'BUILT_NOT_DEPLOYED'
    except BaseException as error:
        report.update(state='FAILED_NOT_DEPLOYED', error=type(error).__name__, detail=str(error))
        raise
    finally:
        report['original_tree_unchanged'] = all(sha(path) == digest for path, digest in inputs.items())
        (run / 'build-result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(run=str(run), state=report['state'], candidate=report.get('candidate_sha256'),
                              unchanged=report['original_tree_unchanged'])), flush=True)
        assert report['original_tree_unchanged']


if __name__ == '__main__':
    main()

"""Rebuild one C++ TU; relink copied archive without modifying the F9 tree.

The baseline relink must reproduce the installed stripped binary byte-for-byte.
Only Directory.cpp is rebuilt, so production playback/audio/DV objects remain.
All output, depfiles and archives live under a new run directory.
"""
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
OBJECT = 'build/filesystem/CMakeFiles/filesystem.dir/Directory.cpp.o'
ARCHIVE = 'build/filesystem/filesystem.a'
EXPECTED = '8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b'
UNSTRIPPED = '571aa622dde43551b192d9ceb3dc9efdc28bb937a66e3c3ddf33e012bc17101a'
ORIGINAL = '63272b95c5bddf39d3b48ce1ed9c6f82e2cba9f7e88004414d31e48082967232'


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
    assert sha(BUILD / 'kodi.bin') == UNSTRIPPED
    assert sha(SOURCE / 'xbmc/filesystem/Directory.cpp') == ORIGINAL
    assert sha(OUT / 'Directory.original.cpp') == ORIGINAL
    run = OUT / ('run-' + str(time.time_ns()))
    run.mkdir()
    cc = shlex.split(commands(OBJECT)[-1])
    link_raw = commands('kodi.bin')[-1]
    assert link_raw.startswith(': && ') and link_raw.endswith(' && :')
    link = shlex.split(link_raw[5:-5])
    assert link.count(ARCHIVE) == 2 and cc.count('-c') == 1
    assert not any(arg in ('&&', ';', '|') for arg in cc + link)
    # Freeze every explicit linker object/archive input and build control file.
    inputs = {str(BUILD / arg): sha(BUILD / arg) for arg in link
              if arg.endswith(('.a', '.o', '.so')) and (BUILD / arg).is_file()}
    for path in (BUILD / 'build.ninja', BUILD / 'kodi.bin', BUILD / OBJECT,
                 SOURCE / 'xbmc/filesystem/Directory.cpp'):
        inputs[str(path)] = sha(path)
    report = dict(state='STARTED', inputs=inputs, source_sha256=sha(OUT / 'Directory.patched.cpp'),
                  builder_sha256=sha(__file__), commands={}, original_tree_unchanged=False)
    def execute(args, label):
        report['commands'][label] = args
        with (run / (label + '.log')).open('x') as log:
            subprocess.run(args, cwd=BUILD, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=600)
    def relink(label, archive=None):
        args = list(link)
        if archive:
            args = [str(archive) if value == ARCHIVE else value for value in args]
        binary = run / (label + '.unstripped')
        output_arg(args, '-o', binary)
        execute(args, label + '-link')
        stripped = run / (label + '.bin')
        shutil.copyfile(binary, stripped)
        execute([str(TOOLS / 'armv8a-libreelec-linux-gnueabihf-strip'),
                 '--strip-unneeded', str(stripped)], label + '-strip')
        return stripped
    try:
        baseline = relink('baseline')
        report['baseline_sha256'] = sha(baseline)
        assert sha(baseline) == EXPECTED, 'BASELINE_RELINK_MISMATCH'
        # Preserve relative include lookup; no source/header in the original tree is edited.
        for label, source in (('control', OUT / 'Directory.original.cpp'),
                              ('candidate', OUT / 'Directory.patched.cpp')):
            directory = run / label
            directory.mkdir()
            obj = directory / 'Directory.cpp.o'
            args = list(cc)
            output_arg(args, '-o', obj)
            output_arg(args, '-MF', directory / 'Directory.cpp.o.d')
            output_arg(args, '-MT', obj)
            output_arg(args, '-c', source)
            args.extend(['-iquote', str(SOURCE / 'xbmc/filesystem')])
            execute(args, label + '-compile')
            archive = directory / 'filesystem.a'
            shutil.copyfile(BUILD / ARCHIVE, archive)
            execute([str(TOOLS / 'armv8a-libreelec-linux-gnueabihf-gcc-ar'),
                     'r', str(archive), str(obj)], label + '-archive')
            execute([str(TOOLS / 'armv8a-libreelec-linux-gnueabihf-gcc-ranlib'),
                     str(archive)], label + '-ranlib')
            binary = relink(label, archive)
            report[label + '_sha256'] = sha(binary)
            if label == 'control':
                assert sha(binary) == EXPECTED, 'CONTROL_RECOMPILE_MISMATCH'
            else:
                assert sha(binary) != EXPECTED
                report['bytes'] = binary.stat().st_size
        report['state'] = 'BUILT_NOT_DEPLOYED'
    except BaseException as error:
        report.update(state='FAILED_NOT_DEPLOYED', error=type(error).__name__, detail=str(error))
        raise
    finally:
        report['original_tree_unchanged'] = all(sha(path) == digest for path, digest in inputs.items())
        (run / 'build-result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(run=str(run), state=report['state'],
              baseline=report.get('baseline_sha256'), control=report.get('control_sha256'),
              candidate=report.get('candidate_sha256'), unchanged=report['original_tree_unchanged'])), flush=True)
        assert report['original_tree_unchanged']


if __name__ == '__main__':
    main()

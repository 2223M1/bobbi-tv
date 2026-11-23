"""Run the actual capsule against pinned Kodi types in a Linux host harness.

The bundled fmt headers are sufficient for this test. The maintained F9 Kodi
source tree and a host C++17 compiler remain explicit external dependencies.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_files(root, expected, label):
    actual = {}
    for name, wanted in expected.items():
        path = root/name
        if not path.is_file():
            raise RuntimeError(label + ' dependency missing: ' + str(path))
        actual[name] = sha(path)
        if actual[name] != wanted:
            raise RuntimeError(label + ' dependency hash mismatch: ' + name)
    return actual


def main():
    manifest = json.loads((HERE/'dependencies.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kodi-source', type=Path, default=Path(manifest['kodi']['default_source']))
    parser.add_argument('--candidate-root', type=Path, default=HERE.parent/'candidate')
    parser.add_argument('--compiler', default='g++')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='Parent for a fresh run directory; no artifacts are written into Kodi.')
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('Run inside WSL/Linux; see the PowerShell invocation in ../README.md.')
    compiler = shutil.which(args.compiler)
    if not compiler:
        parser.error('A Linux host C++17 compiler is required: ' + args.compiler)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run = args.output_dir/('run-' + str(time.time_ns()))
    run.mkdir()
    report = dict(state='STARTED', run=str(run), dependency_manifest_sha256=sha(HERE/'dependencies.json'))
    code = 1
    try:
        report['fmt_sha256'] = verify_files(HERE/'includes', manifest['fmt']['files'], 'fmt 10.2.1')
        report['kodi_sha256'] = verify_files(args.kodi_source, manifest['kodi']['files'], 'maintained F9 Kodi')
        header = args.candidate_root/'xbmc/cores/BobiHandoff.h'
        report['candidate_header_sha256'] = sha(header)
        if report['candidate_header_sha256'] != manifest['candidate_header_sha256']:
            raise RuntimeError('Candidate header differs from this harness dependency manifest')
        report['harness_sha256'] = sha(HERE/'handoff_registry_test.cpp')
        report['compiler'] = subprocess.check_output([compiler, '--version'], text=True, timeout=5).splitlines()[0]
        command = [compiler, '-std=c++17', '-O1', '-pthread', '-DTARGET_POSIX',
                   '-I' + str(args.candidate_root/'xbmc'), '-I' + str(args.kodi_source/'xbmc'),
                   '-I' + str(HERE/'includes'), str(HERE/'handoff_registry_test.cpp'),
                   str(args.kodi_source/'xbmc/utils/Variant.cpp'),
                   str(args.kodi_source/'xbmc/cores/VideoSettings.cpp'),
                   '-o', str(run/'handoff_registry_test')]
        report['command'] = command
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        report.update(compile_returncode=result.returncode, compile_output=result.stdout + result.stderr)
        code = result.returncode
        if code == 0:
            test = subprocess.run([str(run/'handoff_registry_test')], capture_output=True, text=True, timeout=15)
            report.update(returncode=test.returncode, output=test.stdout + test.stderr)
            code = test.returncode
        report['state'] = 'PASSED' if code == 0 else 'FAILED'
    except Exception as error:
        report.update(state='FAILED', error_type=type(error).__name__, detail=str(error))
        code = 1
    finally:
        (run/'registry-test-result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    return code


if __name__ == '__main__':
    raise SystemExit(main())

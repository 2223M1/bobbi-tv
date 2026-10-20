"""Run the independent PR2 contracts against the supplied real source tree.

No device, GitHub, account, install directory or source file is modified.
The installer probe creates isolated temporary files and loopback runtimes.
Run from a development Python environment with the repo test requirements.
Exit 0: all contracts passed. Exit 1: violations. Exit 2: harness errors.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REFERENCE_HEAD = '28819d202b6d4b4ff00367e46c37d8542a1b35af'


def run(command, repo, output, name, env):
    try:
        result = subprocess.run(command, cwd=repo, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=90)
        (output / (name + '.stdout')).write_text(result.stdout, encoding='utf-8')
        (output / (name + '.stderr')).write_text(result.stderr, encoding='utf-8')
        return result.returncode
    except subprocess.TimeoutExpired as error:
        (output / (name + '.stderr')).write_text(str(error), encoding='utf-8')
        return 124


def git_identity(repo):
    def git(*args):
        result = subprocess.run(['git', '-C', str(repo), *args],
            capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else None
    try:
        top = git('rev-parse', '--show-toplevel')
        if not top or Path(top).resolve() != repo:
            return {'kind': 'source-snapshot', 'commit': None, 'tree': None}
        return {'kind': 'git-checkout', 'commit': git('rev-parse', 'HEAD'),
                'tree': git('rev-parse', 'HEAD^{tree}'),
                'tracked_changes': git('status', '--porcelain', '--untracked-files=no') or ''}
    except (OSError, subprocess.SubprocessError):
        return {'kind': 'source-snapshot', 'commit': None, 'tree': None}


def source_identity(repo):
    manifest = json.loads((ROOT / 'SOURCE-PROVENANCE.json').read_text(encoding='utf-8'))
    rows = []
    for row in manifest['contract_sources']:
        path = repo / row['path']
        if not path.is_file():
            rows.append({'path': row['path'], 'missing': True})
            continue
        raw = path.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        rows.append({'path': row['path'], 'bytes': len(raw), 'git_blob_sha1': blob,
                     'sha256': hashlib.sha256(raw).hexdigest(),
                     'matches_reference': blob == row['git_blob_sha1']})
    return {'git': git_identity(repo), 'files': rows,
            'all_match_reference': all(row.get('matches_reference') is True for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path,
                        help='New results directory; existing evidence is never overwritten')
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if not (repo / 'addons/script.module.bobbi.platform').is_dir():
        parser.error('--repo must be the Bobbi repository root')
    if output.exists():
        parser.error('--output must be a new directory')
    output.mkdir(parents=True)
    env = dict(os.environ, BOBBI_REVIEW_REPO=str(repo), PYTHONDONTWRITEBYTECODE='1',
               PYTHONIOENCODING='utf-8')
    tests = []
    installer_code = run([sys.executable, str(ROOT / 'checks/reproduce_installer_boundaries.py'),
        '--repo', str(repo), '--output', str(output / 'installer.json')], repo, output, 'installer', env)
    try:
        document = json.loads((output / 'installer.json').read_text(encoding='utf-8'))
        tests.extend({'suite': 'installer', **row} for row in document['cases'])
    except (OSError, ValueError, KeyError):
        tests.append({'suite': 'installer', 'id': 'HARNESS', 'passed': False,
                      'error': 'Installer probe did not produce a valid receipt'})

    playback_code = run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        str(ROOT / 'checks/test_review_playback.py'),
        '--junitxml=' + str(output / 'playback.xml')], repo, output, 'playback', env)
    try:
        parsed = ET.parse(output / 'playback.xml').getroot()
        cases = list(parsed.iter('testcase'))
        if not cases:
            raise ValueError('No playback cases')
        for case in cases:
            failure, error, skipped = case.find('failure'), case.find('error'), case.find('skipped')
            row = {'suite': 'playback', 'id': case.get('name'),
                   'passed': failure is None and error is None and skipped is None}
            if error is not None or skipped is not None:
                row['error'] = 'Test setup error or skipped required contract'
            if failure is not None:
                row['assertion'] = failure.get('message')
            tests.append(row)
    except (OSError, ValueError, ET.ParseError):
        tests.append({'suite': 'playback', 'id': 'HARNESS', 'passed': False,
                      'error': 'Playback probe did not produce valid JUnit'})

    trial_code = run([sys.executable, str(ROOT / 'checks/run_trial_gate.py'), '--repo', str(repo),
        '--out', str(output / 'trial.json')], repo, output, 'trial', env)
    try:
        document = json.loads((output / 'trial.json').read_text(encoding='utf-8'))
        if document.get('errors'):
            raise ValueError('Trial harness errors')
        tests.extend({'suite': 'trial', 'id': row['name'], **row} for row in document['results'])
    except (OSError, ValueError, KeyError):
        tests.append({'suite': 'trial', 'id': 'HARNESS', 'passed': False,
                      'error': 'Trial probe did not produce a valid receipt'})

    exit_codes = {'installer': installer_code, 'playback': playback_code, 'trial': trial_code}
    errors = sum('error' in row for row in tests)
    if any(code not in (0, 1) for code in exit_codes.values()):
        errors = max(errors, 1)
    if len(tests) != 18:
        errors = max(errors, 1)
    versions = {}
    for package in ('pytest', 'cryptography', 'requests'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    report = {'schema': 1, 'reference_head': REFERENCE_HEAD,
        'scope': 'Production Python policies with explicit Kodi/provider IO doubles; real temporary files, processes and OS locks; no device certification',
        'source': source_identity(repo),
        'environment': {'python': sys.version, 'platform': platform.platform(), 'packages': versions},
        'count': len(tests), 'passed': sum(row['passed'] for row in tests),
        'failed': sum(not row['passed'] for row in tests), 'errors': errors,
        'exit_codes': exit_codes, 'tests': tests}
    (output / 'RESULT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('count', 'passed', 'failed', 'errors', 'exit_codes')}, ensure_ascii=False))
    for row in tests:
        print(('PASS' if row['passed'] else 'FAIL') + ' ' + row['suite'] + ' ' + row['id'])
    return 2 if errors else (1 if report['failed'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())

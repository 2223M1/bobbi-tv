#!/usr/bin/env python3
"""Run PR3 independent review contracts against an explicit Bobbi source tree.

Core: 14 contracts (installer 4, UI 5, native monitor 5).
Optional: 2 shutdown advisory contracts and 11 trial-driver controls, with
three informational command/receipt comparisons. No device or external-network action.
Exit 0: core passed; 1: core contract violations; 2: harness/setup errors.
Advisory violations remain visible but do not change an otherwise-green exit.
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
REFERENCE_HEAD = 'c8de17ae9dabbe0f37753e1751b1d88107311316'
REFERENCE_TREE = 'cc12e00ccba0d7cb9a8b310306437e0e8ef84ae3'


def git_identity(repo):
    def git(*arguments):
        value = subprocess.run(['git', '-C', str(repo), *arguments],
                               capture_output=True, text=True, timeout=10)
        return value.stdout.strip() if value.returncode == 0 else None
    try:
        top = git('rev-parse', '--show-toplevel')
        if top and Path(top).resolve() == repo:
            return dict(kind='git-checkout', commit=git('rev-parse', 'HEAD'),
                        tree=git('rev-parse', 'HEAD^{tree}'),
                        tracked_changes=git('status', '--porcelain', '--untracked-files=no'))
    except (OSError, subprocess.SubprocessError):
        pass
    return dict(kind='source-snapshot', commit=None, tree=None)


def source_identity(repo):
    reference = json.loads((ROOT / 'SOURCE-PROVENANCE.json').read_text(encoding='utf-8'))
    rows = []
    for original in reference['contract_sources']:
        path = repo / original['path']
        row = dict(path=original['path'])
        if path.is_file():
            raw = path.read_bytes()
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            row.update(bytes=len(raw), git_blob_sha1=blob, sha256=hashlib.sha256(raw).hexdigest(),
                       matches_review_head=blob == original['git_blob_sha1'])
        else:
            row['missing'] = True
        rows.append(row)
    return dict(git=git_identity(repo), files=rows,
                contract_sources_match_review_head=all(row.get('matches_review_head') is True for row in rows))


def run_suite(repo, output, env, name, filename, expected, extra=(), directory_output=False):
    destination = output / name if directory_output else output / (name + '.json')
    command = [sys.executable, str(ROOT / 'checks' / filename), '--repo', str(repo),
               '--output', str(destination), *extra]
    try:
        child = subprocess.run(command, cwd=repo, env=env, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=90)
        (output / (name + '.stdout')).write_text(child.stdout, encoding='utf-8')
        (output / (name + '.stderr')).write_text(child.stderr, encoding='utf-8')
        receipt = destination / 'RESULT.json' if directory_output else destination
        data = json.loads(receipt.read_text(encoding='utf-8'))
        rows = [dict(row) for row in data['tests']]
        if len(rows) != expected or child.returncode not in (0, 1, 2):
            raise ValueError('Unexpected case count or child exit code: %s / %s' % (len(rows), child.returncode))
        if name == 'shutdown':
            for row in rows:
                worker_errors = row.get('actual', {}).get('errors', [])
                if worker_errors:
                    row['harness_error'] = 'Shutdown worker exception: ' + '; '.join(map(str, worker_errors))
                    row['passed'] = False
        errors = sum(bool(row.get('error') or row.get('harness_error')) for row in rows)
        if data.get('errors', 0) > errors or (child.returncode == 2 and not errors):
            rows.append(dict(id='HARNESS-REPORTED-ERROR', passed=False,
                             harness_error='Child reported an execution error without an attributed case'))
            errors += 1
        summary = dict(count=len(rows), passed=sum(row.get('passed') is True for row in rows),
                       failed=sum(row.get('passed') is not True and not row.get('error')
                                  and not row.get('harness_error') for row in rows),
                       errors=errors, exit_code=child.returncode, tests=rows)
        if 'new_driver_observations' in data:
            summary['observations'] = data['new_driver_observations']
        return summary
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        message = type(error).__name__ + ': ' + str(error)
        return dict(count=1, passed=0, failed=0, errors=1, exit_code=2,
                    tests=[dict(id='HARNESS', passed=False, harness_error=message)])


def junit(suites, target, name):
    root = ET.Element('testsuites', name=name)
    for group, summary in suites.items():
        suite = ET.SubElement(root, 'testsuite', name=group, tests=str(summary['count']),
                              failures=str(summary['failed']), errors=str(summary['errors']))
        for row in summary['tests']:
            case = ET.SubElement(suite, 'testcase', classname=group, name=str(row.get('id', row.get('name', 'case'))))
            error = row.get('error') or row.get('harness_error')
            if error:
                ET.SubElement(case, 'error', message=str(error)).text = json.dumps(row, ensure_ascii=False, indent=2)
            elif row.get('passed') is not True:
                ET.SubElement(case, 'failure', message='Review contract violated').text = json.dumps(row, ensure_ascii=False, indent=2)
    ET.indent(root)
    ET.ElementTree(root).write(target, encoding='utf-8', xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory; prior evidence is never overwritten')
    parser.add_argument('--with-advisories', action='store_true')
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if not (repo / 'addons/plugin.video.bobbi').is_dir():
        parser.error('--repo must point to the repository root containing addons/')
    if output.exists():
        parser.error('--output must be a new directory')
    output.mkdir(parents=True)
    before = source_identity(repo)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    suites = {}
    for name, filename, count in [
        ('installer', 'reproduce_install_lifecycle.py', 4),
        ('ui', 'reproduce_native_list_focus.py', 5),
        ('native_monitor', 'reproduce_native_monitor.py', 5),
    ]:
        suites[name] = run_suite(repo, output, env, name, filename, count)
    advisory = {}
    if args.with_advisories:
        advisory['shutdown'] = run_suite(repo, output, env, 'shutdown', 'reproduce_standard_shutdown.py', 2)
        advisory['trial_driver'] = run_suite(repo, output, env, 'trial_driver', 'check_trial_drivers.py', 11,
            extra=('--evidence', str(ROOT / 'evidence/device-receipts')), directory_output=True)
    after = source_identity(repo)
    packages = {}
    for name in ('pytest', 'cryptography', 'requests'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    result = dict(schema=1, review_reference=dict(commit=REFERENCE_HEAD, tree=REFERENCE_TREE),
                  scope='Actual Python methods with explicit Kodi/IPC/GUI/DB boundary doubles; local loopback only, no device or external-network operations',
                  source_before=before, source_after=after,
                  source_bytes_unchanged=before['files'] == after['files'],
                  environment=dict(python=sys.version, platform=platform.platform(), packages=packages),
                  count=sum(row['count'] for row in suites.values()),
                  passed=sum(row['passed'] for row in suites.values()),
                  failed=sum(row['failed'] for row in suites.values()),
                  errors=sum(row['errors'] for row in suites.values()),
                  suites=suites, advisories=advisory,
                  advisory_errors=sum(row['errors'] for row in advisory.values()),
                  advisory_failures_are_nonblocking=True)
    if result['count'] != 14 or not result['source_bytes_unchanged']:
        result['errors'] += 1
    result['exit_code'] = 2 if result['errors'] or result['advisory_errors'] else 1 if result['failed'] else 0
    (output / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    junit(suites, output / 'review-core.xml', 'PR3 independent core contracts')
    if advisory:
        junit(advisory, output / 'review-advisories.xml', 'PR3 nonblocking observations')
    print(json.dumps({key: result[key] for key in ('count', 'passed', 'failed', 'errors', 'advisory_errors', 'source_bytes_unchanged', 'exit_code')}))
    for group, summary in suites.items():
        for row in summary['tests']:
            print(('PASS' if row.get('passed') else 'FAIL') + ' ' + group + ' ' + str(row.get('id', row.get('name', 'case'))))
    return result['exit_code']


if __name__ == '__main__':
    try:
        code = main()
    except Exception as error:
        print('HARNESS ERROR: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        code = 2
    raise SystemExit(code)

#!/usr/bin/env python3
"""Read-only, offline review runner. Does not install or modify a repository."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
GROUPS = ('lifecycle', 'installer', 'shutdown', 'ui', 'resolution')
COUNTS = {'lifecycle': 18, 'installer': 7, 'shutdown': 5, 'ui': 6, 'resolution': 12}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_package() -> None:
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text(encoding='utf-8'))
    expected = manifest['files']
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}
    if actual != set(expected) | {'MANIFEST.json'}:
        raise ValueError('PACKAGE_FILE_SET_MISMATCH')
    for name, digest in expected.items():
        p = ROOT / name
        if p.is_symlink() or sha256(p) != digest:
            raise ValueError('PACKAGE_HASH_MISMATCH:' + name)
    source = json.loads((ROOT / 'SOURCE-PROVENANCE.json').read_text(encoding='utf-8'))
    for row in source['records']:
        raw = (ROOT / row['local']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('SOURCE_HASH_MISMATCH:' + row['local'])
        if row['kind'] == 'complete_file':
            observed = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if observed != row['git_blob']:
                raise ValueError('SOURCE_GIT_BLOB_MISMATCH:' + row['local'])


def method_excerpt(text: str, class_name: str, method_name: str) -> str:
    tree = ast.parse(text)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name]
    if len(classes) != 1:
        raise ValueError('CANDIDATE_CLASS_CHANGED:' + class_name)
    methods = [n for n in classes[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name]
    if len(methods) != 1:
        raise ValueError('CANDIDATE_METHOD_CHANGED:' + class_name + '.' + method_name)
    node = methods[0]
    first = min([node.lineno] + [n.lineno for n in node.decorator_list])
    return '\n'.join(text.splitlines()[first - 1:node.end_lineno]) + '\n'


def candidate_snapshot(repo: Path, target: Path) -> dict:
    repo = repo.resolve(strict=True)
    if not repo.is_dir():
        raise ValueError('CANDIDATE_NOT_DIRECTORY')
    provenance = json.loads((ROOT / 'SOURCE-PROVENANCE.json').read_text(encoding='utf-8'))
    rows = []
    for row in provenance['records']:
        p = repo / row['path']
        if p.is_symlink() or repo not in p.resolve(strict=True).parents or p.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('CANDIDATE_SOURCE_PATH_INVALID:' + row['path'])
        raw = p.read_bytes()
        output = target / Path(row['local']).relative_to('source')
        output.parent.mkdir(parents=True, exist_ok=True)
        if row['kind'] == 'method_excerpt':
            content = method_excerpt(raw.decode('utf-8-sig'), row['source_class'], row['source_method']).encode('utf-8')
        else:
            content = raw
        output.write_bytes(content)
        rows.append({'path': row['path'], 'input_sha256': hashlib.sha256(raw).hexdigest(),
                     'test_input_sha256': hashlib.sha256(content).hexdigest(), 'kind': row['kind']})
    git = {}
    for label, args in [('head', ['rev-parse', 'HEAD']), ('tree', ['rev-parse', 'HEAD^{tree}']), ('status', ['status', '--porcelain'])]:
        try:
            p = subprocess.run(['git', '-C', str(repo)] + args, capture_output=True, text=True, timeout=10,
                               encoding='utf-8', errors='replace', check=False)
            git[label] = p.stdout.strip() if p.returncode == 0 else 'unavailable'
        except (OSError, subprocess.TimeoutExpired):
            git[label] = 'unavailable'
    return {'mode': 'candidate_read_only_copy', 'git': git, 'sources': rows,
            'note': 'Same review assertions, explicit doubles, not full repository or device validation.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New result directory outside this immutable review package')
    parser.add_argument('--candidate-repo', type=Path, help='Read candidate files; never changes the repository')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        verify_package()
        if args.verify_only:
            print('PACKAGE_AND_FROZEN_SOURCE_VERIFIED')
            return 0
        output = (args.output or ROOT.parent / ('CE2014-review-result-' + uuid.uuid4().hex[:8])).resolve()
        if output == ROOT or ROOT in output.parents or output.exists():
            raise ValueError('RESULT_DIRECTORY_MUST_BE_NEW_AND_OUTSIDE_PACKAGE')
        if args.candidate_repo and (output == args.candidate_repo.resolve() or args.candidate_repo.resolve() in output.parents):
            raise ValueError('RESULT_DIRECTORY_MUST_BE_OUTSIDE_CANDIDATE_REPOSITORY')
        output.mkdir(parents=True, exist_ok=False)
        results = []
        mode = {'mode': 'frozen_review_sources', 'commit': 'c8de17ae9dabbe0f37753e1751b1d88107311316'}
        with tempfile.TemporaryDirectory(prefix='bobbi-pr3-review-') as temp:
            source = ROOT / 'source'
            if args.candidate_repo:
                source = Path(temp) / 'candidate'
                mode = candidate_snapshot(args.candidate_repo, source)
            env = dict(os.environ)
            env.pop('REVIEW_CRASH', None)
            env['PYTHONUTF8'] = '1'
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            for group in GROUPS:
                command = [sys.executable, '-I', '-B', str(ROOT / 'checks/contracts.py'),
                           '--group', group, '--source-root', str(source), '--output', str(output / (group + '.json'))]
                try:
                    p = subprocess.run(command, cwd=str(output), env=env, capture_output=True, timeout=45, check=False)
                    (output / (group + '.stdout')).write_bytes(p.stdout)
                    (output / (group + '.stderr')).write_bytes(p.stderr)
                    value = json.loads((output / (group + '.json')).read_text(encoding='utf-8'))
                    value['process_exit'] = p.returncode
                    value['command'] = [sys.executable, '-I', '-B', 'checks/contracts.py', '--group', group]
                    if value['total'] != COUNTS[group]:
                        value['errors'] += 1
                        value['coverage_error'] = 'Unexpected case count; inspect boundary fixtures'
                    if p.returncode not in (0, 1, 2):
                        value['errors'] += 1
                    results.append(value)
                except (OSError, subprocess.TimeoutExpired, ValueError) as error:
                    results.append({'group': group, 'total': 0, 'passed': 0, 'failed': 0, 'errors': 1,
                                    'runner_error': type(error).__name__ + ':' + str(error)})
            summary = {k: sum(row[k] for row in results) for k in ('total', 'passed', 'failed', 'errors')}
            summary.update(mode=mode, groups=results, device_execution=False, repository_modified=False,
                           whole_suite_reexecuted=False,
                           meaning='Exit 1 denotes unmet correct-behavior assertions, not a repaired product.')
            summary['status'] = ('REVIEW_EXECUTION_ERROR' if summary['errors'] else
                                 'OPEN_FINDINGS_REPRODUCED' if summary['failed'] else
                                 'REVIEW_ASSERTIONS_PASS_NOT_RELEASE')
            (output / 'RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: summary[k] for k in ('total', 'passed', 'failed', 'errors', 'status')}, ensure_ascii=False))
        print('RESULT=' + str(output / 'RESULT.json'))
        return 2 if summary['errors'] else 1 if summary['failed'] else 0
    except (OSError, ValueError, KeyError) as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

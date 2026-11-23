"""Record one local command without conflating execution and acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def checkout_identity(root, receipt_files=()):
    """No recorder fallback: a command outside Git has unknown source identity."""
    root = Path(root).resolve()
    try:
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL).decode('utf-8').strip()
        top = Path(git('rev-parse', '--show-toplevel')).resolve()
        head, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
        raw = subprocess.check_output(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=all'],
                                      cwd=top, stderr=subprocess.DEVNULL).decode('utf-8')
        excluded = []
        for path in receipt_files:
            try:
                excluded.append(Path(path).resolve().relative_to(top).as_posix())
            except ValueError:
                pass
        rows = raw.rstrip('\0').split('\0') if raw else []
        effective = [r for r in rows if not (r.startswith('?? ') and r[3:] in excluded)]
        return dict(known=True, cwd=str(root), top_level=str(top), commit=head, tree=tree,
                    status=rows, effective_status=effective, dirty=bool(effective),
                    ignored_generated_receipts=excluded)
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        return dict(known=False, cwd=str(root), commit=None, tree=None, dirty=None,
                    reason='EXECUTION_CHECKOUT_UNKNOWN')


def identity_stable(before, after):
    return (before.get('known') is True and after.get('known') is True
            and all(before.get(k) == after.get(k) for k in
                    ('top_level', 'commit', 'tree', 'effective_status')))


def require_clean_receipt(value, commit, tree):
    """New handoffs must opt into schema 2; historical receipts stay unmodified."""
    before, after = value.get('execution_before', {}), value.get('execution_after', {})
    if (value.get('schema') != 2 or value.get('exit_code') != 0
            or not identity_stable(before, after) or before.get('dirty') is not False
            or before.get('commit') != commit or before.get('tree') != tree):
        raise ValueError('GATE_EXECUTION_IDENTITY_UNVERIFIED')
    return True


def run(name, command, root=None, output=None):
    if not name or Path(name).name != name or name in ('.', '..'):
        raise ValueError('INVALID_RECEIPT_NAME')
    root = Path(ROOT if root is None else root).resolve()
    output = Path(output).resolve() if output is not None else ROOT / 'review-evidence/ce2023' / name
    output.mkdir(parents=True, exist_ok=False)
    generated = [output / name for name in ('stdout.log', 'stderr.log', 'result.json')]
    before, recorder = checkout_identity(root, generated), checkout_identity(ROOT, generated)
    started = time.time()
    with (output / 'stdout.log').open('wb') as out, (output / 'stderr.log').open('wb') as err:
        p = subprocess.run(command, cwd=root, stdout=out, stderr=err,
                           env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1'))
    after = checkout_identity(root, generated)
    result = dict(schema=2, command=command, cwd=str(root), started=started,
                  elapsed=time.time()-started, exit_code=p.returncode,
                  runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  recorder_before=recorder, recorder_after=checkout_identity(ROOT, generated),
                  execution_before=before, execution_after=after,
                  execution_stable=identity_stable(before, after),
                  commit=before['commit'], dirty=before['dirty'])
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(name=name, exit_code=p.returncode, elapsed=result['elapsed'])), flush=True)
    return p.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cwd', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('name')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    raise SystemExit(run(args.name, args.command, root=args.cwd, output=args.output))

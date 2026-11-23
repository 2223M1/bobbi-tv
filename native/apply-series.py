"""Apply the locked generic Kodi patch series to a fresh checkout."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def apply(source):
    source = Path(source).resolve()
    directory = Path(__file__).resolve().parent / 'patches'
    series = json.loads((directory / 'series.json').read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if revision != series['base_commit']:
        raise ValueError('Wrong Kodi source revision')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=source):
        raise ValueError('Refusing to patch an existing or modified source tree')
    inputs = []
    for item in series['patches']:
        if Path(item['file']).name != item['file']:
            raise ValueError('Invalid patch path')
        path = directory / item['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Patch input changed: ' + item['file'])
        inputs.append(str(path))
    # Later patches intentionally extend files changed by earlier patches.
    # Build the sequence in a private index, then apply its single final diff.
    # A multi-file `git apply --check` checks all patches against the old tree.
    with tempfile.TemporaryDirectory(prefix='bobbi-patch-index-') as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary)/'index'))
        subprocess.run(['git', 'read-tree', 'HEAD'], cwd=source, env=env, check=True)
        for path in inputs:
            subprocess.run(['git', 'apply', '--cached', path], cwd=source, env=env, check=True)
        combined = subprocess.check_output(['git', 'diff', '--cached', '--binary'], cwd=source, env=env)
    subprocess.run(['git', 'apply', '--check'], input=combined, cwd=source, check=True)
    subprocess.run(['git', 'apply'], input=combined, cwd=source, check=True)


if __name__ == '__main__':
    apply(sys.argv[1])

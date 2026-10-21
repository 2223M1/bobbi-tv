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


def run(name, command, root=ROOT):
    output = ROOT / 'review-evidence/ce2023' / name
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    with (output / 'stdout.log').open('wb') as out, (output / 'stderr.log').open('wb') as err:
        p = subprocess.run(command, cwd=root, stdout=out, stderr=err,
                           env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1'))
    result = dict(command=command, cwd=str(root), started=started,
                  elapsed=time.time()-started, exit_code=p.returncode,
                  runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  dirty=True)
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(name=name, exit_code=p.returncode, elapsed=result['elapsed'])), flush=True)
    return p.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    raise SystemExit(run(args.name, args.command))

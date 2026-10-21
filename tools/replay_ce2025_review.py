"""Preserve independent CE2024 counterexamples against the next candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    a, b = (ROOT/'review-evidence/ce2025'/name for name in ('review-a', 'review-b'))
    environment = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                       PYTHONDONTWRITEBYTECODE='1', BOBBI_REVIEW_ROOT=str(ROOT))
    records = []

    def run(name, parameters, extra=None):
        directory = out/name
        directory.mkdir()
        began = time.time()
        env = dict(environment, BOBBI_REVIEW_OUTPUT=str(directory), **(extra or {}))
        with (directory/'stdout.log').open('wb') as stdout, (directory/'stderr.log').open('wb') as stderr:
            result = subprocess.run([sys.executable, *map(str, parameters)], cwd=ROOT, env=env,
                                    stdout=stdout, stderr=stderr)
        row = dict(name=name, command=[sys.executable, *map(str, parameters)], cwd=str(ROOT),
                   exit_code=result.returncode, seconds=time.time()-began,
                   interpretation='Independent probe result, not whole-product acceptance')
        (directory/'result.json').write_text(json.dumps(row, indent=2)+'\n', encoding='utf-8')
        records.append(row)
        print(json.dumps(dict(name=name, exit_code=result.returncode)), flush=True)
        return result.returncode

    if run('dependencies', [b/'checks/extract_delivery_dependencies.py', '--entry',
           ROOT/'review-packages/ce2024/script.bobbi.start-0.2.15-ce2024.zip', '--out', out/'dependencies/files']):
        return 2
    for name, script in (('quiesce', 'probe_quiesce_retry.py'), ('history', 'probe_history_report_failure.py'),
                         ('subtitle-enumeration', 'probe_subtitle_episode.py')):
        run(name, [a/'probes'/script, '--repo', ROOT])
    run('subtitle-scope', [b/'checks/reproduce_subtitle_scope.py', '--repo', ROOT,
                           '--output', out/'subtitle-scope/matrix.json'])
    run('identity', ['-m', 'pytest', '-q', '-p', 'no:cacheprovider', b/'checks/test_closure_gate_identity.py',
                     '--junitxml='+str(out/'identity/result.xml')])
    paths = [out/'dependencies/files'/name/'lib' for name in
             ('script.module.requests','script.module.urllib3','script.module.certifi','script.module.idna','script.module.chardet')]
    run('progressive', ['-m', 'pytest', '-q', '-p', 'no:cacheprovider', b/'checks/test_progressive_shutdown.py',
                        '--junitxml='+str(out/'progressive/result.xml')],
        {'PYTHONPATH': os.pathsep.join(map(str, paths))})
    run('decoder-historical', [b/'checks/decoder-reproduce.py', '--repo', ROOT,
        '--fixed-source', b/'evidence/source/FIXED-TREE.json', '--receipt',
        ROOT/'review-evidence/ce-new-work-grand_budapest-observe-1792551462588057300.json',
        '--output', out/'decoder-historical/result-evidence.json'])
    value = dict(command_records=records, head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                 note='Before repair: exit 1 is expected for reported defects; decoder exit 0 confirms historical loss, not repair',
                 runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'INDEX.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

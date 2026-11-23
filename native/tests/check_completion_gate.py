"""Exercise the real generic runner against isolated broken completion inputs.

The supplied full-series source is read-only. Each mutant uses its own copied
xbmc subtree; native gate failures must specifically name completion, while
the visibility positive and negative controls must remain green.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='completion-gate-', dir=args.output))
    header = Path('xbmc/cores/VideoPlayer/BobiCompletion.h')
    original = (args.source/header).read_bytes()
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    report = dict(scope='actual generic runner negative controls, not device playback',
                  original_header_sha256=sha(original), tests=[])
    for damage in ('success_disabled', 'missing_header'):
        case = run/damage
        snapshot = case/'source'
        shutil.copytree(args.source/'xbmc', snapshot/'xbmc')
        target = snapshot/header
        if damage == 'success_disabled':
            assert original.count(b'    m_valid = true;') == 1, 'COMPLETION_FIXTURE_DRIFT'
            target.write_bytes(original.replace(b'    m_valid = true;', b'    m_valid = false;'))
        else:
            target.unlink()  # Exact newly copied fixture only, never the supplied source.
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('run_generic.py')),
            '--source', str(snapshot), '--output', str(case/'results')], capture_output=True, text=True, timeout=300)
        (case/'runner.stdout.log').write_text(result.stdout)
        (case/'runner.stderr.log').write_text(result.stderr)
        reports = list((case/'results').glob('generic-*/result.json'))
        assert len(reports) == 1, 'GENERIC_GATE_REPORT_MISSING'
        observed = json.loads(reports[0].read_text())
        states = {row['name']: row['passed'] for row in observed['tests']}
        passed = result.returncode != 0 and states['completion_observation'] is False and all(
            state for name, state in states.items() if name != 'completion_observation')
        report['tests'].append(dict(damage=damage, passed=passed, exit_code=result.returncode,
            generic_report=str(reports[0]), generic_report_sha256=sha(reports[0].read_bytes())))
    report['original_source_unchanged'] = (args.source/header).read_bytes() == original
    (run/'result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(run=str(run), **report)))
    return 0 if report['original_source_unchanged'] and all(row['passed'] for row in report['tests']) else 1


if __name__ == '__main__':
    raise SystemExit(main())

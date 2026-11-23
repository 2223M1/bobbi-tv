"""Fresh canonical-source native semantics; never a linked Android/device proof."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(output, source=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='native-ci-', dir=output))
    series = json.loads((ROOT / 'patches/series.json').read_text())
    report = dict(schema=1, state='NOT_TESTED', scope='host C++ semantics from clean canonical patch series',
                  source_base=series['base_commit'], android_linked=False, real_device_verified=False,
                  series_sha256=hashlib.sha256((ROOT / 'patches/series.json').read_bytes()).hexdigest(), steps=[])
    missing = [tool for tool in ('git', 'g++') if shutil.which(tool) is None]
    code = 2

    def execute(name, command, cwd=None, timeout=600):
        log = directory / (name + '.log')
        with log.open('x', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        report['steps'].append(dict(name=name, exit_code=result.returncode, log=log.name,
                                   log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
        if result.returncode:
            raise RuntimeError('NATIVE_GATE_FAILED:' + name)

    try:
        if missing:
            report['reason'] = 'TOOLCHAIN_UNAVAILABLE:' + ','.join(missing)
        else:
            snapshot = directory / 'source'
            if source is not None:
                execute('clone', ['git', 'clone', '--quiet', '--shared', str(Path(source).resolve()), str(snapshot.resolve())])
            else:
                execute('init', ['git', 'init', '--quiet', str(snapshot.resolve())])
                execute('fetch', ['git', 'fetch', '--quiet', '--depth=1', 'https://github.com/xbmc/xbmc.git',
                                  series['base_commit']], cwd=snapshot)
                execute('checkout', ['git', 'checkout', '--quiet', '--detach', 'FETCH_HEAD'], cwd=snapshot)
            execute('apply-series', [sys.executable, str(ROOT / 'apply-series.py'), str(snapshot.resolve())])
            execute('generic-semantics', [sys.executable, str(ROOT / 'tests/run_generic.py'),
                '--source', str(snapshot.resolve()), '--output', str((directory / 'generic').resolve())])
            execute('completion-negative-controls', [sys.executable, str(ROOT / 'tests/check_completion_gate.py'),
                '--source', str(snapshot.resolve()), '--output', str((directory / 'negative').resolve())])
            report['state'], code = 'HOST_SEMANTICS_PASSED', 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        report.update(state='FAILED_NOT_PROVEN', reason=type(error).__name__)
        code = 1
    finally:
        path = directory / 'gate-result.json'
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(dict(result=str(path), state=report['state'], android_linked=False, real_device_verified=False)))
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, help='Optional pinned local git repository, cloned without modifying it')
    args = parser.parse_args()
    raise SystemExit(run(args.output, args.source))

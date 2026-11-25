"""Run production HTTP consumer contracts on exact Kodi floor and bundled bytes.

Requires normal test dependencies in this Python. --floor-archives accepts the
two official pinned ZIPs for offline operation; --fetch-floor fetches only those
public artifacts. No installed runtime or Kodi-owned addon is changed.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'release/http-runtime-policy.json'
SUITES = (
    'tests/test_bounded_http_deadlines.py',
    'tests/test_online_transport.py',
    'tests/test_metadata_transport.py',
    'tests/test_portable_http.py',
    'tests/test_source_media_convergence.py',
    'tests/test_t4_strm_media_transport.py',
    'tests/test_u06_u11_sources_http_phone_contracts.py',
    'tests/test_upstream_addons.py',
    'tests/test_upstream_updates.py',
    'tests/test_http_upgrade_runtime.py',
    'tests/test_round2_http_deadlines.py',
    'tests/test_round2_subtitle_http.py',
    'tests/test_ce2029_subtitle_architecture.py',
)


def source_identity(suites):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()
    return {'commit': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'),
        'dirty': bool(git('status', '--porcelain')), 'python': sys.version,
        'diff_sha256': hashlib.sha256(subprocess.check_output(
            ['git', '-C', str(ROOT), 'diff', '--binary', 'HEAD'])).hexdigest(),
        'policy_sha256': hashlib.sha256(POLICY.read_bytes()).hexdigest(),
        'suite_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in suites}}


def require_frozen_source(before, after=None):
    if before['dirty']:
        raise ValueError('Commit candidate changes before freezing the runtime matrix')
    if after is not None and before != after:
        raise ValueError('Source changed while the runtime matrix was running')


def prepare_floor(policy, output, archives=None):
    destination = output / 'floor-addons'
    destination.mkdir()
    for row in policy['floor_artifacts']:
        name = row['url'].rsplit('/', 1)[1]
        if archives is None:
            with urlopen(row['url'], timeout=20) as response:
                raw = response.read(row['bytes'] + 1)
        else:
            with (Path(archives) / name).open('rb') as stream:
                raw = stream.read(row['bytes'] + 1)
        if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('Pinned Kodi archive differs: ' + row['id'])
        (output / name).write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            seen = set()
            infos = archive.infolist()
            if sum(info.file_size for info in infos) > 8 * 1024 * 1024:
                raise ValueError('Runtime archive exceeds extraction budget')
            for info in infos:
                path = PurePosixPath(info.filename)
                if (path.is_absolute() or '..' in path.parts or not path.parts
                        or path.parts[0] != row['id'] or '\\' in info.filename
                        or ':' in info.filename or info.filename.casefold() in seen
                        or ((info.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError('Unsafe runtime archive member')
                seen.add(info.filename.casefold())
            archive.extractall(destination)
    return destination


def run_matrix(output, archives=None, extra_suites=()):
    before = source_identity((*SUITES, *extra_suites))
    require_frozen_source(before)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Output must be a new directory')
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep runtime evidence outside the source checkout')
    output.mkdir(parents=True)
    policy_bytes = POLICY.read_bytes()
    policy = json.loads(policy_bytes)
    report = {'schema': 1, 'policy_sha256': hashlib.sha256(policy_bytes).hexdigest(),
              'passed': False, 'device_verified': False, 'runtimes': {}}
    report['source'] = before
    try:
        floor = prepare_floor(policy, output, archives)
        for label, addons, expected in (
            ('kodi-floor', floor, policy['minimums']),
            ('bundled', ROOT / 'third_party/addons', policy['bundled']),
        ):
            libs = [str(addons / ('script.module.' + name) / 'lib') for name in ('requests', 'urllib3')]
            libs += [str(ROOT / 'third_party/addons' / ('script.module.' + name) / 'lib')
                     for name in ('certifi', 'chardet', 'idna')]
            libs += [str(ROOT / 'addons/script.module.bobbi.core/lib'),
                     str(ROOT / 'addons/script.module.bobbi.platform/lib')]
            env = dict(os.environ)
            for key in list(env):
                if key in ('PYTEST_ADDOPTS', 'BOBBI_REPO', 'BOBBI_REPO_ROOT', 'BOBBI_TEST_LOCAL') or key.startswith('BOBBI_AUDIT_'):
                    env.pop(key, None)
            env['PYTHONPATH'] = os.pathsep.join(libs)
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            env['BOBBI_HTTP_RUNTIME_EXPECTED'] = json.dumps(expected)
            probe = ('import json; from bobbi_platform.upstream_addons import inspect_http_runtime; '
                     'print(json.dumps(inspect_http_runtime()))')
            actual = json.loads(subprocess.check_output([sys.executable, '-B', '-c', probe],
                cwd=ROOT, env=env, text=True))
            for name in ('requests', 'urllib3'):
                if (actual[name]['version'] != expected['script.module.' + name]
                        or not Path(actual[name]['file']).is_relative_to(addons)):
                    raise ValueError('Wrong runtime loaded: ' + label + '/' + name)
            junit, logfile = output / (label + '.xml'), output / (label + '.log')
            command = [sys.executable, '-B', '-m', 'pytest', '-q', '-rs', *SUITES, *extra_suites,
                       '--junitxml=' + str(junit)]
            with logfile.open('w') as log:
                completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            xml = ET.parse(junit).getroot()
            suites = [xml] if xml.tag == 'testsuite' else list(xml.findall('testsuite'))
            counts = {key: sum(int(suite.get(key, '0')) for suite in suites)
                      for key in ('tests', 'failures', 'errors', 'skipped')}
            report['runtimes'][label] = {'loaded': actual, 'command': command,
                'returncode': completed.returncode, 'counts': counts,
                'junit_sha256': hashlib.sha256(junit.read_bytes()).hexdigest(),
                'log_sha256': hashlib.sha256(logfile.read_bytes()).hexdigest()}
            if completed.returncode != 0 or not counts['tests'] or counts['failures'] or counts['errors'] or counts['skipped']:
                raise ValueError('HTTP consumer matrix did not fully pass: ' + label)
        report['source_after'] = source_identity((*SUITES, *extra_suites))
        require_frozen_source(before, report['source_after'])
        report['passed'] = True
        return report
    finally:
        (output / 'runtime-matrix.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--floor-archives', type=Path)
    source.add_argument('--fetch-floor', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--extra-suite', action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(run_matrix(args.output, args.floor_archives, args.extra_suite), indent=2))

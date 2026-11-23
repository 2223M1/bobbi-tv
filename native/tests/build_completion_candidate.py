"""Compile affected real generic Kodi TUs in a fresh full-series checkout.

Uses an existing pinned Android compile database read-only. This is actual C++
compilation, not a linked/packaged host or a playback/device certification.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='completion-', dir=args.output))
    snapshot = run/'source'
    subprocess.run(['git', 'clone', '--quiet', '--shared', str(args.source), str(snapshot)], check=True)
    subprocess.run([sys.executable, str(root/'apply-series.py'), str(snapshot)], check=True)
    units = {'xbmc/cores/VideoPlayer/VideoPlayer.cpp', 'xbmc/application/ApplicationPlayer.cpp',
             'xbmc/cores/playercorefactory/PlayerCoreConfig.cpp'}
    includes = {str(path.relative_to(snapshot)) for path in (snapshot/'xbmc').rglob('*.cpp')
                if re.search(r'^\s*#\s*include\s*"(?:cores/VideoPlayer/)?VideoPlayer\.h"',
                             path.read_text(), re.M)}
    assert includes == units, 'VIDEOPLAYER_HEADER_CONSUMER_DRIFT'
    database = args.build/'compile_commands.json'
    commands = json.loads(database.read_text())
    before = {str(database): sha(database), str(args.source/'xbmc/cores/VideoPlayer/VideoPlayer.h'):
              sha(args.source/'xbmc/cores/VideoPlayer/VideoPlayer.h')}
    report = dict(state='STARTED', source_base='a3a448d26b8d560a65655dab2cd122994dc4e146',
                  full_series_applied=True, series_sha256=sha(root/'patches/series.json'),
                  units={}, scope='real Android C++ translation units; not linked or deployed')

    def compile_unit(relative):
        record = next(row for row in commands if row['file'] == str(args.source/relative))
        argv = [arg.replace(str(args.source), str(snapshot)) for arg in shlex.split(record['command'])]
        obj = run/(Path(relative).stem+'.o')
        argv[argv.index('-o')+1] = str(obj)
        argv += ['-MD', '-MF', str(obj)+'.d']
        log = run/(Path(relative).stem+'.log')
        with log.open('w') as stream:
            subprocess.run(argv, cwd=record['directory'], stdout=stream, stderr=subprocess.STDOUT,
                           timeout=1200, check=True)
        dependencies = Path(str(obj)+'.d').read_text().replace('\\\n', ' ').split()
        assert str(snapshot/'xbmc/cores/VideoPlayer/VideoPlayer.h') in dependencies
        assert not any(str(args.source) in value for value in dependencies), 'FROZEN_SOURCE_DEPENDENCY'
        return relative, dict(object=str(obj), sha256=sha(obj), command=argv, log=str(log))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            report['units'] = dict(pool.map(compile_unit, sorted(units)))
        helper = run/'completion-test'
        subprocess.run(['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
            '-I'+str(snapshot/'xbmc'), str(root/'tests/completion_observation_test.cpp'),
            str(snapshot/'xbmc/utils/Variant.cpp'), '-o', str(helper)], check=True)
        subprocess.run([str(helper)], check=True)
        report.update(state='COMPILED_NOT_LINKED', native_helper_passed=True)
    except BaseException:
        report['state'] = 'FAILED_NOT_DEPLOYED'
        raise
    finally:
        report['original_tree_unchanged'] = all(sha(path) == digest for path, digest in before.items())
        (run/'result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(run=str(run), state=report['state'], unchanged=report['original_tree_unchanged'])))


if __name__ == '__main__':
    main()

"""Replay immutable reviews with explicit caller/GUI-model corrections.

Original inputs and original failing receipts remain untouched. A now performs
one authority read, not two; B's select-count-zero assertion contradicts Kodi's
queued bind (review A). Its replacement requires exactly one FIFO compensation,
in addition to the unchanged item identity and no-reset assertions.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True  # Importing a frozen runner must not add pyc files.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--original-b', type=Path,
                        help='Original external review ZIP; extracted only in temporary workspace')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    with tempfile.TemporaryDirectory(prefix='ce2014-adapted-') as directory:
        temp = Path(directory)
        original = ROOT/'review-evidence/ce2014-review-a'
        adapted = temp/'a'
        shutil.copytree(original, adapted)
        lifecycle = adapted/'checks/reproduce_install_lifecycle.py'
        before_lifecycle = lifecycle.read_text(encoding='utf-8')
        after_lifecycle = before_lifecycle.replace('        server.start()\n',
            '        server.start()\n        server.can_quiesce = lambda: True  # existing fake Kodi Player is idle\n')
        after_lifecycle = after_lifecycle.replace('            while not release.wait(.003):\n                server.tick()\n',
            '            while not release.wait(.003) and not server.stopping.is_set():\n                server.tick()\n'
            '            if server.stopping.is_set():\n                server.close()\n')
        # This fixture runs actual HTTP threads. Its old accelerated clock
        # consumed a 15s deadline in 75ms, before a real 100ms server poll.
        after_lifecycle = after_lifecycle.replace('        return self.now\n', '        return time.monotonic()\n')
        after_lifecycle = after_lifecycle.replace('        self.now += max(1.0, seconds)\n        time.sleep(.005)\n',
                                                '        time.sleep(seconds)\n')
        lifecycle.write_text(after_lifecycle, encoding='utf-8')
        (args.output/'a-lifecycle-adapter.diff').write_text(''.join(difflib.unified_diff(
            before_lifecycle.splitlines(True), after_lifecycle.splitlines(True),
            fromfile='old host pump', tofile='cooperative host pump with the same idle Kodi IO')), encoding='utf-8')
        target = adapted/'checks/reproduce_native_monitor.py'
        before = target.read_text(encoding='utf-8')
        after = (ROOT/'review-evidence/ce2014-monitor-adapter.py').read_text(encoding='utf-8')
        target.write_text(after, encoding='utf-8')
        (args.output/'a-adapter.diff').write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='original monitor', tofile='single-read monitor seam')), encoding='utf-8')
        shutdown = adapted/'checks/reproduce_standard_shutdown.py'
        before_shutdown = shutdown.read_text(encoding='utf-8')
        # Original rendezvous releases IO only AFTER synchronous quiesce, so
        # a correct draining host reaches the unrelated 15s installer refusal.
        # Release from a different actor while quiesce waits. Separate product
        # tests cover never-released work and failure-closed ownership.
        after_shutdown = before_shutdown.replace('        started = time.monotonic()\n',
            '        if blocked:\n            threading.Timer(.8, release.set).start()\n        started = time.monotonic()\n')
        shutdown.write_text(after_shutdown, encoding='utf-8')
        (args.output/'a-shutdown-adapter.diff').write_text(''.join(difflib.unified_diff(
            before_shutdown.splitlines(True), after_shutdown.splitlines(True), fromfile='synchronous release rendezvous',
            tofile='independent IO completion')), encoding='utf-8')
        p = subprocess.run([sys.executable, '-B', str(adapted/'run_review.py'), '--repo', str(ROOT),
            '--output', str(args.output.resolve()/'a'), '--with-advisories'], env=env, capture_output=True)
        (args.output/'a.stdout').write_bytes(p.stdout); (args.output/'a.stderr').write_bytes(p.stderr)
        a = json.loads((args.output/'a/RESULT.json').read_text(encoding='utf-8'))
        package = ROOT/'review-evidence/ce2014-review-b'
        if args.original_b:
            with zipfile.ZipFile(args.original_b) as archive:
                names = archive.namelist()
                if any('..' in Path(n).parts or Path(n).is_absolute() or '\\' in n or ':' in n for n in names):
                    raise ValueError('Unsafe review member')
                archive.extractall(temp/'original-b')
            packages = list((temp/'original-b').glob('*/run_review.py'))
            if len(packages) != 1:
                raise ValueError('Ambiguous original review')
            package = packages[0].parent
            (args.output/'original-b-input.json').write_text(json.dumps(dict(
                file=args.original_b.name, sha256=hashlib.sha256(args.original_b.read_bytes()).hexdigest(),
                scope='External immutable review used only in temporary test workspace')), encoding='utf-8')
        spec = importlib.util.spec_from_file_location('frozen_b_runner', package/'run_review.py')
        runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
        runner.verify_package()  # Verify original bytes BEFORE adapting only IO expectation.
        source = temp/'b/source'
        provenance = runner.candidate_snapshot(ROOT, source)
        # The frozen B subset predates quiesce importing the real runtime.
        # Copy its new dependency verbatim, never synthesize a successful call.
        dependency = ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform/runtime.py'
        shutil.copyfile(dependency, source/'bobbi_platform/runtime.py')
        provenance['additional_dependencies'] = [dict(path=str(dependency.relative_to(ROOT)),
            sha256=hashlib.sha256(dependency.read_bytes()).hexdigest(), reason='cooperative installer status/call dependency')]
        scripts = temp/'b/checks'; shutil.copytree(package/'checks', scripts)
        target = scripts/'contracts.py'
        before = target.read_text(encoding='utf-8')
        assert before.count("actual['selects']==0") == 1
        after = before.replace("actual['selects']==0", "actual['selects']==1")
        target.write_text(after, encoding='utf-8')
        (args.output/'b-adapter.diff').write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='original zero-select assumption',
            tofile='one native bind compensation')), encoding='utf-8')
        groups = []
        for group in runner.GROUPS:
            output = args.output.resolve()/('b-'+group+'.json')
            p = subprocess.run([sys.executable,'-I','-B',str(target),'--group',group,
                '--source-root',str(source),'--output',str(output)], env=env,capture_output=True)
            (args.output/('b-'+group+'.stdout')).write_bytes(p.stdout)
            (args.output/('b-'+group+'.stderr')).write_bytes(p.stderr)
            groups.append(json.loads(output.read_text(encoding='utf-8')))
        b = {key: sum(g[key] for g in groups) for key in ('total','passed','failed','errors')}
        b.update(groups=groups,provenance=provenance)
        value = dict(scope='explicit adapted review contracts; not original unchanged oracle or device certification',
            a=a,b=b,passed=a['passed']==14 and not a['errors'] and not a['advisory_errors']
                and not any(row['failed'] for row in a['advisories'].values())
                and b['passed']==48 and not b['errors'])
        (args.output/'RESULT.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(a={k:a[k] for k in ('count','passed','failed','errors')},
            b={k:b[k] for k in ('total','passed','failed','errors')},passed=value['passed'])))
        return 0 if value['passed'] else 1


if __name__=='__main__': raise SystemExit(main())

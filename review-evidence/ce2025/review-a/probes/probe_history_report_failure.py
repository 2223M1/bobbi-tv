#!/usr/bin/env python3
"""Read-only historical fault-injection diagnostic, not a future CI gate.

Requires --repo ABSOLUTE_PATH to a trusted checkout/export. No project edits,
no bytecode writes, no device or external network connections. Only actual
product modules plus the documented Kodi/IO/clock boundary doubles are used;
the quiesce probe creates a disposable temporary marker and real OS lock.

--source-ref is an optional unverified caller label. Actual input SHA-256
values are emitted. stdout is JSON. Exit 1 = target defect reproduced;
0 = not reproduced within this narrow scope, not release certification;
2 = environment or source interface incompatible.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import threading
import types
from types import SimpleNamespace

sys.dont_write_bytecode = True
SOURCE_PATHS = (
    "addons/plugin.video.bobbi/lib/services/standard_playback.py",
    "addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py",
    "addons/script.module.bobbi.platform/lib/bobbi_platform/playback.py",
)


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps(dict(status='incompatible', error=message, exit_code=2)))
        raise SystemExit(2)


def run_probe(repo):
    ROOT = repo
    sys.path[:0] = [str(ROOT / 'addons/script.module.bobbi.platform/lib'),
                   str(ROOT / 'addons/plugin.video.bobbi')]
    from lib.services.standard_playback import HistoryWriter


    def probe(report_raises):
        entered, release = threading.Event(), threading.Event()
        attempted, diagnostic_codes, worker_errors = [], [], []

        def store(data):
            attempted.append(data['sequence'])
            if data['sequence'] == 1:
                entered.set()
                if not release.wait(2):
                    raise RuntimeError('audit barrier not released')
                raise OSError('injected history IO failure')

        def report(code):
            diagnostic_codes.append(code)
            if report_raises:
                raise RuntimeError('injected diagnostic sink failure')

        module = types.ModuleType('lib.utils.general.utils')
        module.set_watched_file = store
        sys.modules['lib.utils.general.utils'] = module
        previous_hook = threading.excepthook
        threading.excepthook = lambda args: worker_errors.append(args.exc_type.__name__)
        writer = HistoryWriter(report)
        try:
            writer.save({'sequence': 1})
            if not entered.wait(1):
                raise RuntimeError('history worker did not start')
            writer.save({'sequence': 2})
            release.set()
            close_error = None
            try:
                writer.close()
            except BaseException as error:
                close_error = type(error).__name__
            return dict(report_raises=report_raises, attempted=attempted,
                        diagnostic_codes=diagnostic_codes, worker_errors=worker_errors,
                        close_error=close_error, pending_records=writer.queue.qsize(),
                        worker_alive=writer.worker.is_alive())
        finally:
            release.set()
            writer.done.set()
            writer.worker.join(2)
            threading.excepthook = previous_hook

    result = dict(negative_control=probe(False), fault_injection=probe(True))
    result['defect_reproduced'] = (
        result['negative_control']['attempted'] == [1, 2]
        and result['negative_control']['pending_records'] == 0
        and result['fault_injection']['attempted'] == [1]
        and result['fault_injection']['pending_records'] == 1
        and result['fault_injection']['close_error'] is None
    )
    return result


def main():
    parser = JsonParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, type=Path, help='Absolute read-only source checkout/export')
    parser.add_argument('--source-ref', help='Unverified caller-declared source label')
    args = parser.parse_args()
    result = dict(purpose='historical_fault_injection_not_ci_gate',
                  declared_source_ref=args.source_ref, source_ref_verified=False,
                  source_root=str(args.repo), source_sha256={})
    try:
        if not args.repo.is_absolute():
            raise ValueError('--repo must be an absolute path')
        repo = args.repo.resolve(strict=True)
        if not repo.is_dir():
            raise ValueError('--repo must be a directory')
        result['source_root'] = str(repo)
        for name in SOURCE_PATHS:
            result['source_sha256'][name] = hashlib.sha256((repo/name).read_bytes()).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()):
            result.update(run_probe(repo))
        code = 1 if result['defect_reproduced'] else 0
        result['status'] = 'target_defect_reproduced' if code else 'not_reproduced_in_scope'
    except Exception as error:
        code = 2
        result.update(status='incompatible', error_type=type(error).__name__, error=str(error))
    result['exit_code'] = code
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""CE2049 independent QQdocs optional-write boundary probe.

Uses production catalog.resolve/selected/Cache + real temporary SQLite files.
The only two doubles are the remote API and a 250 ms scheduling/IO pause after
the real optional Cache deadline setup. The pause is only activated after the
remote resolve has produced its outcome. No Kodi, real account or network IO.
The CE2047 comparison compiles its unchanged resolve function from the saved
fixed-commit source and shares CE2049's otherwise unchanged selected/Cache code.
"""
import argparse
import ast
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--baseline', type=Path, default=Path(__file__).parent/'baseline/catalog.py')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    for addon in ('script.module.bobbi.platform', 'script.module.bobbi.catalog', 'script.module.bobbi.core'):
        sys.path.insert(0, str(args.source/'addons'/addon/'lib'))
    with patch('bobbi_platform.paths.profile', lambda *a, **k: Path('fixture-explicit-path-required')):
        from bobbi_catalog import catalog as qq
    from bobbi_catalog.api import ShareError

    old = ast.parse(args.baseline.read_text())
    old_fn = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == 'resolve')
    scope = dict(qq.__dict__)
    exec(compile(ast.Module(body=[old_fn], type_ignores=[]), str(args.baseline), 'exec'), scope)
    prior_resolve = scope['resolve']
    source_file = args.source/'addons/script.module.bobbi.catalog/lib/bobbi_catalog/catalog.py'
    receipt = dict(schema=1, source_commit='43e3a296f5982a6b235421cbffb61c3eae65a84e',
        source_sha256=hashlib.sha256(source_file.read_bytes()).hexdigest(),
        baseline_commit='1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd',
        baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        boundary='250 ms pause after real bounded_sql only in post-API optional metadata Cache',
        io='temporary real SQLite; synthetic remote API; no network/device/account', cases=[])
    real_bounded = qq.bounded_sql
    with tempfile.TemporaryDirectory(prefix='ce2049-share-review-') as temporary:
        root = Path(temporary)
        for version, resolve in [('ce2047_resolve', prior_resolve), ('ce2049_resolve', qq.resolve)]:
            for mode, pause in [('success', 0), ('success', .25), ('share_revoked', 0),
                                ('share_revoked', .25), ('identity_changed', .25), ('network_timeout', .25)]:
                run = root/(version+'-'+mode+'-'+str(pause)); run.mkdir()
                public, cache_path = run/'public.sqlite3', run/'cache.sqlite3'
                with closing(sqlite3.connect(public)) as db:
                    db.execute('CREATE TABLE shares(cell TEXT,group_key TEXT,code TEXT,password TEXT)')
                    db.execute("INSERT INTO shares VALUES('A1','g','sfixture','')")
                    db.commit()
                selected = dict(locator='am6bqqdocs://A1/123', guid='qqdocs:A1:123',
                    title='Review Fixture.2024.1080p.mkv',size=1024,media='movies:101:0:0')
                with closing(qq.Cache(cache_path)) as cache:
                    cache.remember(selected['guid'],selected['media'],
                        dict(name=selected['title'],size=1024,fid='123',cell='A1',origin='review'))
                state = dict(api_calls=0, api_finished=False, pause_count=0)
                class API:
                    account_scope = dict(account_id='review-fixture',epoch=1,authenticated=True)
                    def resolve(self,*a):
                        state['api_calls'] += 1
                        state['api_finished'] = True
                        if mode != 'success':
                            raise ShareError(mode, http_status=403, api_code=4100010)
                        return 'https://example.invalid/review-video.mkv'
                def delayed_bounded(db, deadline=None, cancelled=None):
                    real_bounded(db, deadline, cancelled)
                    if state['api_finished'] and deadline is not None and pause:
                        state['pause_count'] += 1
                        time.sleep(pause)
                started = time.monotonic()
                with patch.object(qq, 'bounded_sql', delayed_bounded):
                    try:
                        result = resolve(**selected,catalogue=public,cache_path=cache_path,client=API())
                        observed, api_code = ('success' if result == 'https://example.invalid/review-video.mkv' else 'wrong_url'), None
                    except ShareError as error:
                        observed, api_code = error.code, error.api_code
                row = dict(version=version,api_outcome=mode,pause_seconds=pause,
                    observed=observed,api_code=api_code,elapsed_seconds=round(time.monotonic()-started,3),
                    expected=mode,passed=observed==mode,**state)
                receipt['cases'].append(row)
    receipt['passed'] = sum(r['passed'] for r in receipt['cases'])
    receipt['failed'] = sum(not r['passed'] for r in receipt['cases'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    return int(receipt['failed'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())

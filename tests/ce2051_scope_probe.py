"""Replay no-further-provider account changes against explicit Git source."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core import share_failure as failure

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    path = 'addons/script.module.bobbi.core/lib/bobbi_core/source_list_session.py'
    raw = subprocess.check_output(['git', 'show', args.revision+':'+path], cwd=ROOT)
    namespace = {}
    exec(compile(raw, path, 'exec'), namespace)
    session = namespace['SourceListSession']({}, lambda rows:rows)
    selected = dict(locator='am6bqqdocs://A1/1', guid='qqdocs:A1:1', title='Fixture.mkv', size=1000, media='movies:1:0:0')
    scope = dict(account_id='fixture-a', epoch=1, authenticated=True)
    with closing(sqlite3.connect(':memory:')) as db:
        failure.record_result(db, selected, scope, 1, 'share_revoked')
        observed = failure.card_state(db, selected, scope)
    source = SimpleNamespace(url=selected['locator'], guid=selected['guid'], title=selected['title'],
                             size=1000, type='Direct', shareFailure=observed['code'], shareState=observed)
    session.publish(session.epoch, '115', [source], 'RUNNING')
    key = session.key(source)
    session.focus(key, 0)
    with patch.object(failure, 'account_scope', lambda **kw:dict(account_id='fixture-b', epoch=2, authenticated=True)):
        session.status()  # existing GUI tick; no provider result is delivered
        after = session.snapshot()
    receipt = dict(revision=args.revision, source_sha256=hashlib.sha256(raw).hexdigest(),
        current_failure=after['entries'][0][1].shareFailure, recommended=after['recommended_key']==key,
        retained=len(after['entries'])==1 and session.focus_key==key,
        expected='clear old account presentation even without any later provider rows')
    receipt['passed'] = not receipt['current_failure'] and receipt['recommended'] and receipt['retained']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(receipt))
    raise SystemExit(0 if receipt['passed'] else 1)

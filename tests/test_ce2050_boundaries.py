"""CE2049 independent counterexamples and ordered presentation regressions."""
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT/'addons'/addon/'lib'))
from bobbi_core import share_failure as failure
from bobbi_core.source_list_session import SourceListSession


@pytest.mark.parametrize('script,args', [
    ('optional_metadata.py', ['--source']),
    ('assert_connection_budget.py', ['--repo']),
    ('contract_catalog_epoch.py', ['--expect', 'fixed', '--repo']),
])
def test_independent_production_contracts(tmp_path, script, args):
    output = tmp_path/'receipt.json'
    command = [sys.executable, '-X', 'utf8', str(ROOT/'tests/repros/ce2050'/script),
               *args, str(ROOT), '--output', str(output)]
    run = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONUTF8='1'),
                         capture_output=True, text=True, encoding='utf-8', timeout=30)
    if script == 'assert_connection_budget.py' and output.exists():
        receipt = json.loads(output.read_text())
        if receipt.get('status') == 'INCONCLUSIVE':
            pytest.skip('Real dual-stack fixture unavailable: '+run.stdout)
    assert run.returncode == 0, run.stdout+run.stderr


def card(db, scope, title='Movie.2024.mkv'):
    fid = '1' if title == 'Movie.2024.mkv' else '2'
    selected = dict(locator='am6bqqdocs://A1/'+fid, guid='qqdocs:A1:'+fid, title=title,
                    size=1000, media='movies:101:0:0')
    state = failure.card_state(db, selected, scope)
    source = SimpleNamespace(url=selected['locator'], guid=selected['guid'], title=title,
        size=1000, indexer='115', type='Direct', shareState=state,
        shareFailure=state.get('code', ''), verifiedShareFile=False)
    return source, selected


def test_ordered_empty_failure_account_logout_and_stable_focus():
    scope = dict(account_id='fixture', epoch=1, authenticated=True)
    session = SourceListSession({'tmdb':101}, lambda rows:rows)
    def publish(source):
        assert session.publish(session.epoch, '115', [source], 'RUNNING')
    with closing(sqlite3.connect(':memory:')) as db:
        empty, selected = card(db, scope)
        failure.record_result(db, selected, scope, 10, 'share_revoked')
        failed, _ = card(db, scope)
        publish(failed)
        key = session.key(failed)
        session.focus(key, 0)
        publish(empty)  # Old empty response cannot erase a newer failure.
        assert session.snapshot()['entries'][0][1].shareFailure == 'share_revoked'
        failure.record_result(db, selected, scope, 20, '')
        success, _ = card(db, scope)
        publish(success)
        publish(failed)  # Old failure cannot erase newer explicit retry success.
        assert session.snapshot()['recommended_key'] == key
        assert session.snapshot()['entries'][0][1].shareFailure == ''
        failure.record_result(db, selected, scope, 30, 'identity_changed')
        failed_new, _ = card(db, scope)
        publish(failed_new)
        signed_out = dict(account_id='', epoch=2, authenticated=False)
        logout, _ = card(db, signed_out)
        publish(logout)
        publish(failed_new)
        assert session.snapshot()['entries'][0][1].shareFailure == ''
        assert session.focus_key == key and len(session.entries) == 1
        next_scope = dict(account_id='other', epoch=3, authenticated=True)
        failure.record_result(db, selected, next_scope, 40, 'share_revoked')
        other, _ = card(db, next_scope)
        publish(other)
        publish(logout)
        assert not session.snapshot()['recommended_key']
        # Adjacent tuple and BT candidates remain usable, not globally revoked.
        adjacent, _ = card(db, next_scope, 'Another.2024.mkv')
        publish(adjacent)
        bt = SimpleNamespace(title='Movie', infoHash='a'*40, type='torrent')
        session.publish(session.epoch, 'BT', [bt])
        assert len(session.snapshot()['entries']) == 3
        assert session.capture(session.epoch, key) is not None
        session.invalidate_share(session.epoch, other, 'identity_changed')
        session.reopen()
        publish(other)  # A stale provider cannot undo a fresh local failure.
        assert session.inspect(session.epoch, key).shareFailure == 'identity_changed'
        session.cancel()
        assert not session.publish(session.epoch, '115', [success])


def test_optional_state_read_failure_cannot_clear_observed_failure():
    scope = dict(account_id='fixture', epoch=1, authenticated=True)
    db = sqlite3.connect(':memory:')
    initial, selected = card(db, scope)
    failure.record_result(db, selected, scope, 10, 'share_revoked')
    failed, _ = card(db, scope)
    db.close()
    assert failure.card_state(db, selected, scope) == {}
    session = SourceListSession({}, lambda rows:rows)
    session.publish(session.epoch, '115', [failed], 'RUNNING')
    unavailable = deepcopy(failed)
    unavailable.shareState, unavailable.shareFailure = {}, ''
    session.publish(session.epoch, '115', [unavailable], 'COMPLETE')
    assert not session.snapshot()['recommended_key']


def test_real_connect_deadline_ipv4_ipv6_tls_and_reuse():
    run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'tests/ce2050_connect_probe.py')],
        capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert run.returncode == 0, run.stdout+run.stderr
    assert len(json.loads(run.stdout)['cases']) == 6


@pytest.mark.parametrize('transition', ['cancel', 'switch', 'logout', 'renew'])
def test_optional_write_deadline_never_bypasses_real_binding_owner(tmp_path, monkeypatch, transition):
    from test_ce2048_share_requery import qq
    from test_accounts import logged_in, credential
    from bobbi_core.share_stream import Binding
    from bobbi_catalog.api import ShareError
    manager, scope = logged_in(tmp_path/'account')
    public, cache_path = tmp_path/'public.sqlite3', tmp_path/'cache.sqlite3'
    with closing(sqlite3.connect(public)) as db:
        db.execute('CREATE TABLE shares(cell TEXT, group_key TEXT, code TEXT, password TEXT)')
        db.execute("INSERT INTO shares VALUES('A1','g','sfixture','')")
        db.commit()
    identity = dict(locator='am6bqqdocs://A1/123', guid='qqdocs:A1:123',
                    title='Fixture.2024.mkv', size=1024, media='movies:101:0:0')
    with closing(qq.Cache(cache_path)) as cache:
        cache.remember(identity['guid'], identity['media'],
                       dict(name=identity['title'], size=1024, fid='123', cell='A1'))
    calls = []
    class API:
        account_scope = scope
        def resolve(self, *args):
            calls.append(True)
            return 'https://fixture.115cdn.com/video|User-Agent=fixture'
    def resolve(body, account):
        return qq.resolve(**identity, catalogue=public, cache_path=cache_path, client=API())
    entry = Binding(dict(identity, request_id='a'*32), resolve, lambda url:True,
                    account=manager, scope=scope)
    original = qq.bounded_sql
    def delayed(db, deadline=None, cancelled=None):
        original(db, deadline, cancelled)
        if calls and deadline is not None:
            if transition == 'cancel': entry.revoke()
            elif transition == 'switch': manager.install(credential('456'), scope)
            elif transition == 'logout': manager.logout(scope)
            else: manager.install(credential('123'), scope)
            # The independent real-SQLite probe supplies the actual 250 ms
            # delay; this test isolates ownership changes at the same boundary.
            raise ShareError('deadline')
    monkeypatch.setattr(qq, 'bounded_sql', delayed)
    if transition == 'renew':
        assert entry.grant().startswith('https://fixture.115cdn.com/')
    else:
        with pytest.raises(OSError, match='SHARE_STOPPED'):
            entry.grant()
        assert entry.address is None
    assert calls == [True]

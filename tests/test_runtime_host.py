from pathlib import Path
import os
import subprocess
import sys
from threading import Event, Thread, get_ident
from types import SimpleNamespace
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.catalog/lib'))
from bobbi_platform.host import Host
from test_accounts import credential


def test_empty_host_imports_no_optional_backend_or_engine(tmp_path):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(ROOT / 'addons' / p / 'lib')
        for p in ('script.module.bobbi.platform', 'script.module.bobbi.core')))
    script = '''import sys
from bobbi_platform.host import Host
h=Host(sys.argv[1])
h.start()
h.tick()
assert h.dispatch('status', {})['preparation'] is False
assert h.dispatch('account_status', {})['authenticated'] is False
assert not any(p in sys.modules for p in ('requests','ctypes','bobbi_core.cd2',
 'bobbi_core.preparation_host','bobbi_platform.native_engine','lib.native_player'))
h.close()
'''
    subprocess.run([sys.executable, '-B', '-c', script, str(tmp_path)], env=env, check=True, timeout=10)


def test_owner_dispatch_runs_on_tick_thread_and_not_http_caller(tmp_path):
    h, replies, threads = Host(tmp_path), [], []
    h.start()
    h.bind_owner(lambda body: (threads.append(get_ident()), dict(body))[1])
    try:
        caller = Thread(target=lambda: replies.append(h.dispatch('playback', {'operation': 'snapshot'})))
        caller.start()
        until = time.monotonic() + 1
        while h.calls.empty() and time.monotonic() < until:
            time.sleep(.005)
        h.tick()
        caller.join(1)
        assert replies == [{'operation': 'snapshot'}]
        assert threads == [get_ident()]
    finally:
        h.close()


def test_expired_owner_request_never_dispatches_late(tmp_path):
    h, called = Host(tmp_path), []
    h.start()
    h.bind_owner(lambda body: called.append(body))
    try:
        with pytest.raises(ValueError, match='TIMEOUT'):
            h.dispatch('playback', {})
        h.tick()
        assert not called
    finally:
        h.close()


def native_state(hash_value='a' * 64):
    return dict(protocol=1, selection_epoch=7, playback=dict(protocol=1,
        native_instance='11111111-2222-3333-4444-555555555555', request_id='b' * 32,
        file_identity='share:fixture', url_sha256=hash_value, phase='AV_STARTED',
        sequence=12, user_intent=3, paused=False))


def test_revocation_stop_is_atomic_expected_native_instance_not_global_player(tmp_path):
    calls = []
    def rpc(method, body):
        calls.append((method, body))
        return native_state() if method == 'Player.BobiState' else {'queued': True}
    h = Host(tmp_path, native_rpc=rpc)
    try:
        assert not h._conditional_stop({'c' * 64})
        assert len(calls) == 1
        assert h._conditional_stop({'a' * 64})
        method, command = calls[-1]
        assert method == 'Player.BobiControl'
        assert command['action'] == 'stop' and command['expected_sequence'] == 12
        assert command['selection_epoch'] == 7 and command['user_intent'] == 3
        assert command['native_instance'] == native_state()['playback']['native_instance']
        assert not any(method == 'Player.Stop' for method, body in calls)
    finally:
        h.close()


def test_stock_host_never_synthesizes_native_stop(tmp_path):
    h = Host(tmp_path)
    try:
        assert h._conditional_stop({'a' * 64}) is False
    finally:
        h.close()


def test_catalog_phases_continue_without_minute_gap_and_shutdown_cancels(tmp_path):
    h, seen = Host(tmp_path), []
    h.start()
    def refresh(deadline, cancelled):
        seen.append(cancelled)
        return {'state': 'DIRECTORY_PROGRESS'}
    h.configure_catalog_refresh(refresh, lambda: True, delay=0)
    try:
        h.tick()
        h.refresh_worker.join(1)
        h.tick()
        assert 0 < h.refresh_due - time.monotonic() <= .11
        assert seen and not seen[0]()
    finally:
        h.close()
    assert seen[0]()


def test_account_status_does_not_expose_credentials(tmp_path):
    h = Host(tmp_path)
    h.start()
    try:
        old = h.dispatch('account_status', {})
        scope = h.dispatch('account_install', {'credentials': credential(), 'expected': old})
        assert set(scope) == {'account_id', 'epoch', 'authenticated'}
        assert h.dispatch('account_status', {}) == scope
        h.dispatch('account_logout', {'expected': scope})
        assert h.dispatch('account_status', {})['authenticated'] is False
    finally:
        h.close()


def test_share_search_captures_original_account_and_rejects_late_result(tmp_path, monkeypatch):
    from bobbi_catalog import api
    h = Host(tmp_path)
    h.start()
    a = h.accounts.install(credential(), h.accounts.snapshot())
    seen = []
    class Client:
        def __init__(self, session, account_scope):
            seen.append((session['cookies']['UID'], account_scope))
        def search(self, share, query, deadline, cancelled):
            assert 0 < deadline - time.monotonic() <= 6
            assert share == {'code': 'fixture123', 'password': 'pass'}
            h.accounts.install(credential('456'), a)
            assert cancelled()
            return [{'fid': '123', 'name': 'Fixture.mkv', 'size': 10}]
    monkeypatch.setattr(api, 'Client', Client)
    try:
        with pytest.raises(Exception, match='ACCOUNT_CHANGED'):
            h.dispatch('share_search', dict(account=a, share=dict(code='fixture123', password='pass', cell='A1'), query='Fixture'))
        assert seen[0][0].startswith('123_') and seen[0][1] == a
    finally:
        h.close()


def test_share_search_does_not_return_or_log_credentials(tmp_path, monkeypatch):
    from bobbi_catalog import api
    h = Host(tmp_path)
    h.start()
    a = h.accounts.install(credential(), h.accounts.snapshot())
    expected = [{'fid': '123', 'name': 'Fixture.mkv', 'size': 10}]
    class Client:
        def __init__(self, **kwargs):
            pass
        def search(self, *args, **kwargs):
            return expected
    monkeypatch.setattr(api, 'Client', Client)
    try:
        assert h.dispatch('share_search', dict(account=a, share=dict(code='fixture123', password='pass'),
                                               query='Fixture')) == {'account': a, 'rows': expected}
    finally:
        h.close()


def test_optional_engine_start_does_not_block_actor_and_close_race_stops_child(tmp_path, monkeypatch):
    started, release, closed = Event(), Event(), []
    class Engine:
        def tick(self, cancelled):
            assert get_ident() != actor
            started.set()
            release.wait(2)
            assert cancelled()
        def close(self):
            closed.append(True)
    monkeypatch.setitem(sys.modules, 'bobbi_platform.native_engine', SimpleNamespace(Engine=Engine))
    (tmp_path / 'engine').mkdir()
    (tmp_path / 'engine/enabled').write_text('fixture')
    h, actor = Host(tmp_path), get_ident()
    h.start()
    try:
        began = time.monotonic()
        h.tick()
        assert time.monotonic() - began < .1 and started.wait(1)
        h.close()
        assert not closed
        release.set()
        h.engine_worker.join(1)
        assert closed == [True] and h.engine is None
    finally:
        release.set()
        h.close()


@pytest.mark.parametrize('change', ['none', 'missing', 'epoch', 'switch_after_fetch'])
def test_sidecar_candidate_requires_scope_and_rechecks_after_provider(tmp_path, monkeypatch, change):
    from bobbi_core import share_subtitles
    from bobbi_platform.account_manager import AccountError
    h = Host(tmp_path)
    h.start()
    scope = h.accounts.install(credential(), h.accounts.snapshot())
    selected = dict(locator='fixture', guid='fixture', title='Fixture.mkv', size=10, media='fixture')
    def fetch(body, context, deadline, cancelled, **kwargs):
        assert body == selected and kwargs['account_scope'] == scope
        assert kwargs['account_guard']() is True
        result = dict(state='candidate', origin='same-share', account_scope=dict(scope))
        if change == 'missing':
            result.pop('account_scope')
        elif change == 'epoch':
            result['account_scope']['epoch'] += 1
        elif change == 'switch_after_fetch':
            h.accounts.install(credential('456'), scope)
            assert kwargs['account_guard']() is False
        return result
    monkeypatch.setattr(share_subtitles, 'fetch_candidate', fetch)
    try:
        if change == 'none':
            result = h.sidecar_candidate(dict(selected, account=scope), {}, time.monotonic()+1, lambda:False)
            assert result['account_scope'] == scope
        else:
            with pytest.raises(AccountError, match='ACCOUNT_CHANGED' if change == 'switch_after_fetch' else 'SCOPE_MISSING'):
                h.sidecar_candidate(dict(selected, account=scope), {}, time.monotonic()+1, lambda:False)
    finally:
        h.close()

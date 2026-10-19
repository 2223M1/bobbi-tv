from pathlib import Path
import json
import sys
from threading import Event, get_ident
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.preparation_host import PreparationHost, Lease, ScopedProvider, Session, configuration
from bobbi_core.cd2 import CD2, CD2Error, field
from bobbi_platform.account_manager import account_id, AccountError
from test_accounts import credential, logged_in


def eventually(test, timeout=2):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if test():
            return
        time.sleep(.005)
    assert test()


def test_cd2_real_numeric_uid_matches_official_login_and_not_nickname():
    client = CD2('fixture', 'http://127.0.0.1:19798/')
    api = field(1, '115open') + field(2, '123') + field(3, 'Different Nickname')
    client.list_directory = lambda path: [{1: [field(3, '/115open') + field(9, api)]}]
    try:
        assert client.provider_identity()['account_id'] == account_id(credential())
        assert client.provider_identity()['legacy_scope'] == client.account_scope()
    finally:
        client.session.close()


@pytest.mark.parametrize('name', ['nickname', '123_foo', '', '00123', '１２３'])
def test_cd2_non_uid_never_inferred_as_account(name):
    client = CD2('fixture', 'http://127.0.0.1:19798/')
    client.list_directory = lambda path: [{1: [field(3, '/115open') + field(9, field(1, '115open') + field(2, name))]}]
    try:
        with pytest.raises((CD2Error, UnicodeError)):
            client.provider_identity()
    finally:
        client.session.close()


def test_provider_does_not_mutate_mismatched_or_revoked_account(tmp_path):
    accounts, scope = logged_in(tmp_path)
    lease, mutations = Lease(accounts, scope), []
    identity = dict(account_id=scope['account_id'], legacy_scope='a' * 64)
    provider = SimpleNamespace(session=object(), provider_identity=lambda: dict(identity),
                               add_offline=lambda *args: mutations.append(args))
    guarded = ScopedProvider(provider, lease, 'a' * 64)
    identity['account_id'] = account_id(credential('456'))
    with pytest.raises(RuntimeError, match='MISMATCH'):
        guarded.add_offline('magnet:?fixture', '/115open/dest')
    identity['account_id'] = scope['account_id']
    lease.revoked.set()
    with pytest.raises(RuntimeError, match='REVOKED'):
        guarded.add_offline('magnet:?fixture', '/115open/dest')
    assert mutations == []


class FakeSession:
    def __init__(self, root, config, lease, playing, report):
        self.lease, self.owner = lease, get_ident()
        self.closed = False
        self.calls = []
    def dispatch(self, method, body):
        assert get_ident() == self.owner
        self.calls.append((method, body))
        return {'state': 'fixture-local-accepted', 'account': self.lease.scope}
    def tick(self):
        assert get_ident() == self.owner
    def close(self):
        self.closed = True


def test_preparation_single_owner_revokes_and_drains_before_new_account(tmp_path):
    accounts, a = logged_in(tmp_path)
    sessions, release, closing = [], Event(), Event()
    class BlockingClose(FakeSession):
        def __init__(self, *args):
            super().__init__(*args)
            sessions.append(self)
        def close(self):
            if self is sessions[0]:
                closing.set()
                assert release.wait(2)
            super().close()
    host = PreparationHost(tmp_path, accounts, {}, session_factory=BlockingClose)
    try:
        eventually(lambda: host.snapshot()['state'] == 'RUNNING')
        assert host.request('prepare', {'opaque': 'fixture'}, a)['state'] == 'fixture-local-accepted'
        b = accounts.install(credential('456'), a)
        assert sessions[0].lease.revoked.is_set()
        assert closing.wait(1)
        assert host.snapshot()['revoke']['admission_closed']
        assert not host.snapshot()['revoke']['drained']
        assert len(sessions) == 1
        with pytest.raises(AccountError):
            host.request('prepare', {}, a)
        release.set()
        eventually(lambda: len(sessions) == 2 and host.snapshot()['state'] == 'RUNNING')
        assert sessions[0].closed and host.snapshot()['revoke']['drained']
        assert host.request('prepare', {}, b)['account'] == b
        assert sessions[0].owner == sessions[1].owner != get_ident()
    finally:
        release.set()
        host.close()
        host.thread.join(2)


def test_same_uid_renewal_keeps_preparation_incarnation(tmp_path):
    accounts, a = logged_in(tmp_path)
    sessions = []
    def factory(*args):
        item = FakeSession(*args)
        sessions.append(item)
        return item
    host = PreparationHost(tmp_path, accounts, {}, session_factory=factory)
    try:
        eventually(lambda: host.snapshot()['state'] == 'RUNNING')
        renewed = accounts.install(credential(suffix='B_new'), a)
        assert renewed == a
        host.request('status', {}, a)
        assert len(sessions) == 1 and not sessions[0].lease.revoked.is_set()
    finally:
        host.close()
        host.thread.join(2)


def test_logout_then_same_uid_has_fresh_incarnation_not_resumed_old_queue(tmp_path):
    accounts, a = logged_in(tmp_path)
    sessions = []
    def factory(*args):
        item = FakeSession(*args)
        sessions.append(item)
        return item
    host = PreparationHost(tmp_path, accounts, {}, session_factory=factory)
    try:
        eventually(lambda: host.snapshot()['state'] == 'RUNNING')
        out = accounts.logout(a)
        eventually(lambda: sessions[0].closed)
        again = accounts.install(credential(), out)
        eventually(lambda: len(sessions) == 2)
        assert sessions[0].lease.scope['epoch'] != sessions[1].lease.scope['epoch']
        assert sessions[1].lease.scope == again
    finally:
        host.close()
        host.thread.join(2)


def test_disabled_or_partial_configuration_is_not_admitted(tmp_path):
    path = tmp_path / 'preparation.json'
    path.write_text(json.dumps({'schema': 1, 'enabled': False}))
    with pytest.raises(ValueError):
        configuration(path)


def test_late_io_result_cannot_publish_after_epoch_revocation(tmp_path):
    accounts, a = logged_in(tmp_path)
    lease = Lease(accounts, a)
    published = []
    accounts.logout(a)
    with pytest.raises(RuntimeError, match='REVOKED'):
        lease.commit(lambda: published.append('old-ready'))
    assert not published


def test_real_session_constructs_in_epoch_directory_without_cloud_io(tmp_path, monkeypatch):
    accounts, a = logged_in(tmp_path)
    token, tmdb = tmp_path / 'token', tmp_path / 'tmdb'
    token.write_text('fixture-local-token')
    tmdb.write_text('fixture-api-key')
    monkeypatch.setattr(CD2, 'rpc', lambda *args, **kwargs: pytest.fail('startup must not do provider IO'))
    config = dict(account='a' * 64, destination='/115open/fixture', cd2_endpoint='http://127.0.0.1:19798',
        torrserver_endpoint='http://127.0.0.1:8090', cd2_token_file=str(token), tmdb_api_key_file=str(tmdb),
        ffprobe='fixture-not-executed', download_capability='GetDownloadUrlPath')
    session = Session(tmp_path, config, Lease(accounts, a), lambda: False, lambda _: None)
    try:
        expected = tmp_path / 'preparation' / (a['account_id'][4:] + '-' + str(a['epoch'])) / 'resources.sqlite'
        assert expected.is_file()
        with pytest.raises(ValueError):
            session.dispatch('prepare', {})  # Local admission still validates input while CD2 is unverified.
        body = dict(request_id='a' * 32, purpose='current',
            media=dict(tmdb_id=1, kind='movie', season=0, episode=0, anime=False,
                       title='Fixture', release_title='Fixture.2025'),
            selected=dict(source_info_hash='b' * 40, torrent_file_id=1,
                          torrent_path='Fixture.2025.mkv', torrent_file_bytes=1000))
        assert session.dispatch('prepare', body)['state'] == 'queued'
        assert session.dispatch('prepare', body)['state'] == 'queued'
        assert session.queue.db.execute('SELECT COUNT(*) FROM preparation_intents').fetchone()[0] == 1
        assert session.dispatch('status', {'request_id': 'a' * 32})['state'] == 'queued'
        assert session.dispatch('status', {'request_id': 'c' * 32}) == dict(request_id='c' * 32, state='absent')
        assert session.dispatch('resolve', {})['reason'] == 'cloud_dependency_not_ready'
        snapshot = json.loads((tmp_path / 'bobi-direct.json').read_text())
        assert snapshot['account_scope'] == a and snapshot['entries'] == []
        assert not (tmp_path / 'bobi-prepared.json').exists()
        # An old host draining after runtime teardown still owns this ledger.
        with pytest.raises(OSError):
            Session(tmp_path, config, Lease(accounts, a), lambda: False, lambda _: None)
        accounts.logout(a)
        with pytest.raises(RuntimeError, match='REVOKED'):
            session.tick()
        assert not (tmp_path / 'bobi-prepared.json').exists()
    finally:
        session.close()

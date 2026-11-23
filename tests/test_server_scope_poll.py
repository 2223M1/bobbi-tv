"""Real Registry contention must not monopolize the playback owner queue."""
from dataclasses import replace
from queue import Queue
import sqlite3
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bobbi_core.library_contract import LibraryError, Source
from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_platform.host import Host, _Call
from bobbi_platform.libraries import Registry
from bobbi_platform.server_accounts import Accounts


def server_source():
    return Source('a' * 32, 'Fixture', 'media_server', 'http://127.0.0.1:8096',
        password='fixture-only', metadata=dict(schema=1, provider='emby',
            server_id='fixture-server', user_id='fixture-user'))


@pytest.fixture
def accounts(tmp_path):
    value = Accounts(tmp_path)
    for provider in ('emby', 'jellyfin', 'plex'):
        value.snapshot(provider)
    return value


def owner_host(accounts):
    """Real queue/tick/deadlines; no runtime socket or unrelated service IO."""
    host = object.__new__(Host)
    host.profile_revoked = False
    host.profile_current = lambda: True
    host.stopping = Event()
    host.pans = SimpleNamespace(servers=accounts)
    host.server_poll_due = 0
    host.account_changes = Event()
    host.owner_account_changed = lambda: pytest.fail('Unknown poll cannot declare account changed')
    host.calls, host.revocations = Queue(), Queue()
    host.owner = lambda value: dict(accepted=value['operation'] == 'snapshot')
    host.report = lambda code: None
    host._tick_catalog = host._tick_preparation = lambda: None
    host.engine_check = float('inf')
    return host


def test_poll_uses_one_read_only_open_and_no_writes(accounts, monkeypatch):
    original = sqlite3.connect
    calls, sql = [], []
    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        db = original(*args, **kwargs)
        db.set_trace_callback(sql.append)
        return db
    monkeypatch.setattr(sqlite3, 'connect', connect)
    accounts.poll()
    assert len(calls) == 1
    assert calls[0][1] == dict(uri=True, timeout=0)
    assert calls[0][0][0].endswith('?mode=ro')
    assert not any(row.split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'BEGIN'} for row in sql)


def test_read_only_open_never_creates_missing_storage(tmp_path):
    path = tmp_path / 'absent' / 'libraries.sqlite3'
    with pytest.raises(LibraryError):
        Registry(path, read_only=True)
    assert not path.parent.exists()


def test_read_only_open_never_migrates_or_creates_revision(accounts):
    with sqlite3.connect(accounts.path) as db:
        db.execute('DROP TABLE pan_directories')
    assert accounts.poll() is False
    with sqlite3.connect(accounts.path) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='pan_directories'").fetchall()
    store = Registry(accounts.path)
    store.save(server_source())
    store.db.execute("DELETE FROM metadata WHERE key LIKE 'source_revision:%'")
    store.db.commit()
    store.close()
    assert accounts.poll() is False
    with sqlite3.connect(accounts.path) as db:
        assert not db.execute("SELECT value FROM metadata WHERE key LIKE 'source_revision:%'").fetchall()
    # The existing explicit snapshot/migration path, not the owner poll,
    # retains responsibility for upgrading historical configuration epochs.
    assert accounts.snapshot('emby')['authenticated']


def test_busy_poll_is_unknown_not_logout_and_does_not_block_owner(accounts):
    store = Registry(accounts.path)
    store.save(server_source())
    store.close()
    expected = accounts.snapshot('emby')
    events = []
    accounts.subscribe(lambda old, new: events.append((old, new)))
    holder = sqlite3.connect(accounts.path)
    holder.execute('BEGIN EXCLUSIVE')
    # Use the real owner tick and real deadline, with only unrelated services
    # disabled. Queue admission precedes the deterministic locked observation.
    host = owner_host(accounts)
    job = _Call({'operation': 'snapshot'})
    host.calls.put_nowait(job)
    errors = []
    def tick():
        try:
            host.tick()
        except BaseException as error:
            errors.append(error)
    actor = Thread(target=tick)
    actor.start()
    try:
        assert job.done.wait(.25), 'Read-only observation waited behind writer'
        assert not job.error and job.result == {'accepted': True}
        assert not host.account_changes.is_set()
        assert accounts.observed['emby'] == expected and events == []
    finally:
        holder.rollback()
        holder.close()
        actor.join(2)
    assert not actor.is_alive() and errors == []
    # A later removal is still observed and revokes the old scope normally.
    store = Registry(accounts.path)
    store.remove(server_source().id)
    store.close()
    accounts.poll()
    assert not accounts.observed['emby']['authenticated']
    assert len(events) == 1
    assert not accounts.is_current(expected)


def test_metadata_select_late_lock_keeps_real_owner_queue_alive(accounts, monkeypatch):
    store = Registry(accounts.path)
    store.save(server_source())
    store.close()
    expected = accounts.snapshot('emby')
    events, locked = [], []
    accounts.subscribe(lambda old, new: events.append((old, new)))
    connect = sqlite3.connect
    holder = connect(accounts.path)

    class LateLockConnection(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            if statement.startswith('SELECT value FROM metadata WHERE key=') and not locked:
                # The actual schema/source reads have succeeded. Acquire a
                # real competing lock immediately before the metadata read;
                # constructor-only error handling cannot catch this failure.
                holder.execute('BEGIN EXCLUSIVE')
                locked.append(statement)
            return super().execute(statement, *args, **kwargs)

    def read_only_connection(*args, **kwargs):
        if kwargs.get('uri') is True:
            kwargs['factory'] = LateLockConnection
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', read_only_connection)
    host = owner_host(accounts)
    job = _Call({'operation': 'snapshot'})
    host.calls.put_nowait(job)
    try:
        host.tick()
        assert len(locked) == 1
        # Host.tick itself checks the production .25-second queue deadline.
        assert job.done.is_set() and not job.error and job.result == {'accepted': True}
        assert not host.account_changes.is_set()
        assert accounts.observed['emby'] == expected and events == []
    finally:
        holder.rollback()
        holder.close()


def test_busy_poll_preserves_real_selected_server_authority_and_strong_cas(accounts):
    store = Registry(accounts.path)
    store.save(server_source())
    store.close()
    expected = accounts.snapshot('emby')

    class IdleNative:
        def __init__(self):
            self.epoch, self.intents = 0, []

        def state(self):
            return dict(protocol=1, selection_epoch=self.epoch, playback=None,
                gui_generation=0, gui_user_intent=0, fullscreen_instance='')

        def intent(self, body):
            assert body['expected_epoch'] == self.epoch
            self.intents.append(dict(body))
            self.epoch += 1
            return dict(reserved=True, selection_epoch=self.epoch)

    native = IdleNative()
    authority = PlaybackAuthority(native)
    authority.configure_accounts(accounts)
    request_id = 'f' * 32
    selected = authority.dispatch(dict(operation='select', boot_id=authority.owner.boot_id,
        epoch=0, request_id=request_id, selection_identity='fixture-server-file', account_scope=expected))
    assert selected['desired']['request_id'] == request_id
    assert authority.selection_account == expected and len(native.intents) == 1
    host = owner_host(accounts)
    # Keep the real callback: the old path synthesized account_changes on a
    # failed poll, then waited in this callback and cancelled the valid scope.
    host.bind_owner(authority.dispatch, authority.account_changed)
    holder = sqlite3.connect(accounts.path)
    holder.execute('BEGIN EXCLUSIVE')
    job = _Call({'operation': 'snapshot'})
    host.calls.put_nowait(job)
    try:
        host.tick()
        assert job.done.is_set() and not job.error
        assert job.result['desired']['request_id'] == request_id
        assert job.result['desired']['cancelled'] is False
        assert authority.owner.desired['cancelled'] is False
        assert not host.account_changes.is_set() and len(native.intents) == 1
        assert accounts.observed['emby'] == expected
        with pytest.raises(LibraryError):
            accounts.run_if_current(expected, lambda: pytest.fail('Busy source granted authority'))
    finally:
        holder.rollback()
        holder.close()
    # Unknown observation never becomes a cached grant. The unchanged full
    # source/generation can authorize again only after its real CAS succeeds.
    assert accounts.is_current(expected)
    committed = []
    assert accounts.run_if_current(expected, lambda: committed.append('committed') or True) is True
    assert committed == ['committed']


def test_poll_keeps_authoritative_configuration_cas(accounts):
    store = Registry(accounts.path)
    source = server_source()
    store.save(source)
    store.close()
    original = accounts.snapshot('emby')
    store = Registry(accounts.path)
    store.remove(source.id)
    store.save(source)
    store.close()
    accounts.poll()
    assert accounts.observed['emby']['generation'] != original['generation']
    with pytest.raises(ValueError):
        accounts.run_if_current(original, lambda: pytest.fail('Old source granted authority'))


def test_strong_scope_checks_fail_fast_without_authorizing_a_busy_source(accounts, monkeypatch):
    store = Registry(accounts.path)
    store.save(server_source())
    store.close()
    expected = accounts.snapshot('emby')
    original = sqlite3.connect
    calls = []
    def connect(*args, **kwargs):
        calls.append(kwargs.get('timeout'))
        return original(*args, **kwargs)
    holder = original(accounts.path)
    holder.execute('BEGIN EXCLUSIVE')
    monkeypatch.setattr(sqlite3, 'connect', connect)
    try:
        assert not accounts.is_current(expected)
        with pytest.raises(LibraryError):
            accounts.run_if_current(expected, lambda: pytest.fail('Busy source authorized'))
        assert calls and set(calls) == {0}
    finally:
        holder.rollback()
        holder.close()
    assert accounts.is_current(expected)


def test_late_lock_after_schema_stays_unknown_and_cas_error_is_typed(accounts, monkeypatch):
    store = Registry(accounts.path)
    store.save(server_source())
    store.close()
    expected = accounts.snapshot('emby')
    holder = sqlite3.connect(accounts.path)
    snapshot = Registry._source_snapshot
    def locked_snapshot(self, source_id):
        holder.execute('BEGIN EXCLUSIVE')
        return snapshot(self, source_id)
    monkeypatch.setattr(Registry, '_source_snapshot', locked_snapshot)
    try:
        assert accounts.poll() is False
        assert accounts.observed['emby'] == expected
    finally:
        holder.rollback()
    # A lock acquired after construction must also be typed at the final CAS.
    monkeypatch.setattr(Registry, '_source_snapshot', snapshot)
    store = Registry(accounts.path, timeout=0)
    source, revision = store.source_snapshot(server_source().id)
    holder.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(LibraryError, match='STORAGE_UNAVAILABLE'):
            store.run_if_current(source, revision, lambda: pytest.fail('Busy CAS executed'))
    finally:
        holder.rollback()
        holder.close()
        store.close()


@pytest.mark.parametrize('aba', [False, True])
def test_late_poll_cannot_replace_newer_observation_even_empty_scope_aba(accounts, monkeypatch, aba):
    source = server_source()
    if not aba:
        store = Registry(accounts.path)
        store.save(source)
        store.close()
        accounts.snapshot('emby')
    initial = dict(accounts.observed['emby'])
    events = []
    accounts.subscribe(lambda old, new: events.append((old, new)))
    original = accounts._snapshot
    def interleave(store, provider):
        if provider == 'emby' and aba and store.read_only:
            writer = Registry(accounts.path)
            writer.save(source)
            writer.close()
        if provider == 'jellyfin':
            writer = Registry(accounts.path)
            if not aba:
                writer.save(replace(source, name='New configuration'))
            writer.close()
            accounts.snapshot('emby')
            if aba:
                writer = Registry(accounts.path)
                writer.remove(source.id)
                writer.close()
                accounts.snapshot('emby')
        return original(store, provider)
    monkeypatch.setattr(accounts, '_snapshot', interleave)
    assert accounts.poll() is True
    assert len(events) == (2 if aba else 1)
    if aba:
        assert accounts.observed['emby'] == initial
    else:
        assert accounts.observed['emby']['generation'] != initial['generation']
        assert accounts.observed['emby'] == events[-1][1]

"""Real SQLite contention: no injected lock exceptions, network or devices."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import sys
from threading import Event, Thread
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.catalog/lib'))
from bobbi_core import sharelib_catalog as cat, sharelib_api as api
from bobbi_core.source_library import Store, cancellation


SPEC = dict(tmdb_id=101, mode='movies', year=2024, aliases=['Lock Fixture'])


def row(index=1):
    movie = dict(tmdbId=101, typeId=1, year=2024, title='Lock Fixture', id=1, vodId=1)
    link = dict(url='https://115.com/s/sabcdef', fileId=str(index),
                fileName='Lock.Fixture.2024.%d.1080p.mkv' % index,
                fileSize=123456+index, parentFolderId='8')
    return cat._row(movie, link, 'shared:fixture')


def seed(root, **options):
    cache = cat.Cache(root, **options)
    cache.replace_library('fixture', 1, [row(), row(2)])
    return cache


def table_count(root, table):
    with sqlite3.connect(str(root/'catalog.sqlite3'), timeout=0) as db:
        return db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]


@contextmanager
def held_lock(root, kind):
    """The holder owns its connection in another thread and releases by Event."""
    acquired, release, released = Event(), Event(), Event()
    errors = []
    def hold():
        db = None
        try:
            db = sqlite3.connect(str(root/'catalog.sqlite3'), timeout=0)
            db.execute('BEGIN' if kind == 'reader' else 'BEGIN '+kind)
            if kind == 'reader':
                db.execute('SELECT * FROM libraries').fetchall()
            else:
                # EXCLUSIVE can also protect an empty, uninitialized database.
                if kind == 'IMMEDIATE':
                    db.execute("INSERT OR REPLACE INTO maintenance VALUES('holder', '1')")
            acquired.set()
            assert release.wait(3), 'Test failed to release holder'
        except BaseException as error:
            errors.append(error)
            acquired.set()
        finally:
            if db is not None:
                db.rollback()
                db.close()
            released.set()
    thread = Thread(target=hold)
    thread.start()
    assert acquired.wait(2), 'Holder failed to acquire real SQLite lock'
    try:
        assert not errors
        yield release, released
    finally:
        release.set()
        thread.join(3)
        assert not thread.is_alive()
        assert not errors


def observe_wait(monkeypatch, action):
    waits = []
    sleep = time.sleep
    def wait(seconds):
        waits.append(seconds)
        action(len(waits))
        sleep(seconds)
    monkeypatch.setattr(cat.time, 'sleep', wait)
    return waits


@pytest.mark.parametrize('operation', ['open', 'raw', 'selections'])
def test_real_lock_released_during_retry_commits_once(tmp_path, monkeypatch, operation):
    cache = None if operation == 'open' else seed(tmp_path)
    # A shared reader blocks COMMIT, not INSERT. The retry must first roll back
    # both staged selection rows, rather than carrying a half-write into retry.
    kind = 'EXCLUSIVE' if operation == 'open' else 'reader'
    with held_lock(tmp_path, kind) as (release, released):
        def unblock(number):
            if number == 1:
                if operation != 'open':
                    assert not cache.db.in_transaction
                    assert table_count(tmp_path, 'selections' if operation == 'selections' else 'raw_cache') == 0
                release.set()
                assert released.wait(2)
        waits = observe_wait(monkeypatch, unblock)
        if operation == 'open':
            cache = cat.Cache(tmp_path)
        elif operation == 'raw':
            cache.put_raw('fixture', {'value': 1})
        else:
            cache.remember(iter([row(), row(2)]), cat._spec(SPEC))
    try:
        assert waits and sum(waits) <= cat.SQLITE_RETRY_SECONDS
        assert not cache.db.in_transaction
        assert cache.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        if operation == 'selections':
            assert table_count(tmp_path, 'selections') == 2
            assert cache.select(row()['key'], cat._spec(SPEC)['media_key'])['name'] == row()['name']
        elif operation == 'raw':
            assert cache.get_raw('fixture') == {'value': 1}
        else:
            assert {r[0] for r in cache.db.execute('SELECT name FROM sqlite_master')} >= {n for n, _ in cache._SCHEMA}
    finally:
        cache.close()


@pytest.mark.parametrize('operation', ['open', 'raw', 'selections'])
def test_persistent_lock_has_small_shared_budget_and_no_half_write(tmp_path, operation):
    events = []
    cache = None if operation == 'open' else seed(tmp_path, diagnostic=events.append)
    start = time.monotonic()
    with held_lock(tmp_path, 'EXCLUSIVE' if operation == 'open' else 'reader'):
        with pytest.raises(sqlite3.OperationalError) as error:
            if operation == 'open':
                cat.Cache(tmp_path, deadline=time.monotonic()+10, diagnostic=events.append)
            elif operation == 'raw':
                cache.put_raw('fixture', {'value': 1})
            else:
                cache.remember([row(), row(2)], cat._spec(SPEC))
        assert cat._sqlite_primary_code(error.value) in (5, 6)
        assert time.monotonic()-start < 1  # Original 10 s deadline is not consumed.
        if cache is not None:
            assert cache._sqlite_retry_remaining == 0
            assert not cache.db.in_transaction
            assert table_count(tmp_path, 'raw_cache') == table_count(tmp_path, 'selections') == 0
            # A later operation cannot replenish the same instance's budget.
            start_again = time.monotonic()
            with pytest.raises(sqlite3.OperationalError):
                cache.remember([row()], cat._spec(SPEC))
            assert time.monotonic()-start_again < .1
            assert table_count(tmp_path, 'selections') == 0
    if cache is not None:
        cache.close()
    else:
        with sqlite3.connect(str(tmp_path/'catalog.sqlite3')) as db:
            assert not db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    assert events and all(set(event) == {'stage', 'state', 'reason', 'sqlite_primary_code'} for event in events)
    assert all(event['sqlite_primary_code'] in (5, 6) for event in events)


@pytest.mark.parametrize('operation', ['open', 'raw', 'selections'])
@pytest.mark.parametrize('stop', ['cancel', 'profile_revoke', 'deadline'])
def test_retry_observes_original_stop_and_rolls_back(tmp_path, monkeypatch, operation, stop):
    live = [True]
    store = Store(tmp_path/'profile', active=lambda: live[0])
    source = store.save('https://fixture.example.invalid')
    root = source.root
    root.mkdir(parents=True, exist_ok=True)
    cancel = Event()
    check = cancellation(source, cancel)
    cache = None if operation == 'open' else seed(root, deadline=time.monotonic()+10, cancelled=check)
    with held_lock(root, 'EXCLUSIVE' if operation == 'open' else 'reader'):
        # Fixture creation is not part of the operation's deadline. Start the
        # absolute limit only once the other connection owns its real lock.
        deadline = time.monotonic()+(.08 if stop == 'deadline' else 10)
        if cache is not None:
            cache.deadline = deadline
        def stop_wait(_):
            if stop == 'cancel':
                cancel.set()
            elif stop == 'profile_revoke':
                live[0] = False
        waits = observe_wait(monkeypatch, stop_wait)
        with pytest.raises(api.ShareLibError) as error:
            if operation == 'open':
                cat.Cache(root, deadline=deadline, cancelled=check)
            elif operation == 'raw':
                cache.put_raw('fixture', {'value': 1})
            else:
                cache.remember([row(), row(2)], cat._spec(SPEC))
        assert error.value.code == ('DEADLINE' if stop == 'deadline' else 'CANCELLED')
        assert waits
        if cache is not None:
            assert not cache.db.in_transaction
            assert table_count(root, 'raw_cache') == table_count(root, 'selections') == 0
    if cache is not None:
        cache.close()
    if stop == 'profile_revoke':
        live[0] = True
        assert check()  # ABA cannot revive the revoked source/profile.


def test_schema_nonbusy_error_is_not_retried_and_leaves_no_half_schema(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(cat.Cache, '_SCHEMA', (cat.Cache._SCHEMA[0], ('broken', 'CREATE TABLE broken(')))
    waits = observe_wait(monkeypatch, lambda _: pytest.fail('Non-BUSY SQL must not wait'))
    with pytest.raises(sqlite3.OperationalError) as error:
        cat.Cache(tmp_path, diagnostic=events.append)
    assert cat._sqlite_primary_code(error.value) not in (5, 6)
    assert not waits
    with sqlite3.connect(str(tmp_path/'catalog.sqlite3')) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    assert events[0]['stage'] == 'sqlite_open'


def test_nonbusy_selection_failure_does_not_retry_or_publish_partial_rows(tmp_path, monkeypatch):
    cache = seed(tmp_path)
    with cache.db:
        cache.db.execute('DROP TABLE selections')
    observe_wait(monkeypatch, lambda _: pytest.fail('No-such-table must not retry'))
    try:
        with pytest.raises(sqlite3.OperationalError):
            cache.remember([row()], cat._spec(SPEC))
        assert not cache.db.in_transaction
        assert table_count(tmp_path, 'shared_rows') == 2
    finally:
        cache.close()


def test_cancel_between_selection_rows_rolls_back_entire_batch(tmp_path, monkeypatch):
    cache = seed(tmp_path)
    cancel = Event()
    cache.cancelled = cancel.is_set
    original_encode = cat._encode
    encoded = []
    def encode(value):
        result = original_encode(value)
        if 'spec' in value:
            encoded.append(value['key'])
            cancel.set()
        return result
    monkeypatch.setattr(cat, '_encode', encode)
    try:
        with pytest.raises(api.ShareLibError, match='CANCELLED'):
            cache.remember([row(), row(2)], cat._spec(SPEC))
        assert len(encoded) == 1
        assert not cache.db.in_transaction
        assert table_count(tmp_path, 'selections') == 0
    finally:
        cache.close()


def test_search_lock_retry_does_not_repeat_http_or_return_unpersisted_locator(tmp_path, monkeypatch):
    original = seed(tmp_path)
    original.close()
    calls = []
    holder = held_lock(tmp_path, 'IMMEDIATE')
    entered = []
    class Client:
        def get(self, path, params, deadline):
            calls.append(path)
            entered.append(holder.__enter__())  # Only after Cache construction.
            return dict(items=[], pagination=dict(total=0))
    def unblock(_):
        release, released = entered[0]
        release.set()
        assert released.wait(2)
    waits = observe_wait(monkeypatch, unblock)
    try:
        rows = cat.search(SPEC, time.monotonic()+3, lambda: False, state=tmp_path, client=Client())
        assert waits and calls == ['/videos/search']
        assert len(rows) == 2 and rows.completion.complete
        with cat._cache(tmp_path, readonly=True) as cache:
            for candidate in rows:
                saved = cache.select(candidate['key'], cat._spec(SPEC)['media_key'])
                assert saved['name'] == candidate['name']
    finally:
        if entered:
            holder.__exit__(None, None, None)


def test_search_persistent_writer_never_returns_unpersisted_snapshot(tmp_path):
    cache = seed(tmp_path)
    cache.close()
    calls, events, entered = [], [], []
    holder = held_lock(tmp_path, 'IMMEDIATE')
    class Client:
        def get(self, path, params, deadline):
            calls.append(path)
            entered.append(holder.__enter__())
            return dict(items=[], pagination=dict(total=0))
    started = time.monotonic()
    try:
        with pytest.raises(sqlite3.OperationalError):
            cat.search(SPEC, time.monotonic()+10, lambda: False, state=tmp_path,
                       client=Client(), diagnostic=events.append)
        assert time.monotonic()-started < 1
        assert calls == ['/videos/search']
        assert table_count(tmp_path, 'selections') == 0
        assert table_count(tmp_path, 'shared_rows') == 2
        assert events[-1] == dict(stage='sqlite_selections', state='UNAVAILABLE',
                                  reason='OperationalError', sqlite_primary_code=5)
    finally:
        if entered:
            holder.__exit__(None, None, None)


def test_real_sqlite_locked_cursor_is_retried_after_cursor_release(tmp_path, monkeypatch):
    cache = seed(tmp_path)
    cursor = cache.db.execute('SELECT * FROM shared_rows')
    assert cursor.fetchone() is not None  # Another row keeps the cursor live.
    waits = observe_wait(monkeypatch, lambda _: cursor.close())
    errors = []
    def operation():
        try:
            with cache.db:
                cache.db.execute('DROP TABLE shared_rows')
        except sqlite3.OperationalError as error:
            errors.append(cat._sqlite_primary_code(error))
            raise
    try:
        cache._retry_sqlite('sqlite_open', operation)
        assert errors == [6] and waits
        assert not cache.db.in_transaction
    finally:
        cursor.close()
        cache.close()


def test_real_sqlite_full_does_not_retry_and_retains_previous_raw_value(tmp_path, monkeypatch):
    events = []
    cache = seed(tmp_path, diagnostic=events.append)
    cache.put_raw('fixture', {'value': 'previous'})
    pages = cache.db.execute('PRAGMA page_count').fetchone()[0]
    cache.db.execute('PRAGMA max_page_count='+str(pages))
    waits = observe_wait(monkeypatch, lambda _: pytest.fail('SQLITE_FULL must not retry'))
    try:
        with pytest.raises(sqlite3.OperationalError) as error:
            cache.put_raw('fixture', {'value': 'x'*100000})
        assert cat._sqlite_primary_code(error.value) == 13
        assert not waits and not cache.db.in_transaction
        assert cache.get_raw('fixture') == {'value': 'previous'}
        assert events[-1]['sqlite_primary_code'] == 13
    finally:
        cache.close()


@pytest.mark.parametrize('message,code', [
    ('database is locked', 5), ('database table is locked: fixture', 6),
    ('database schema is locked: main', 6), ('database or disk is full', None),
    ('unable to open database file', None), ('interrupted', None), ('no such table: fixture', None),
])
def test_python38_lock_classifier_is_narrow(message, code):
    assert cat._sqlite_primary_code(sqlite3.OperationalError(message)) == code

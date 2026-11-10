from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.file_ref import from_selected
from bobbi_core.media_library_index import MediaIndex
from bobbi_core.catalog_review import mapping, suggestion
from bobbi_core.job_snapshot import preparation, PREPARATION_STATES


def scope(account='a', provider='quark', epoch=1):
    return dict(provider=provider, account_id=provider + ':' + account * 64,
                epoch=epoch, authenticated=True)


def ref(number=1, expected=None, name=None, parent='folder'):
    expected = expected or scope()
    return from_selected(expected, dict(file_id=str(number), directory=False,
        name=name or 'Movie.%d.mkv' % number, size=1024), parent)


def insert(store, files, source='a' * 32, expected=None):
    task = store.start(source, expected or scope())
    store.begin(task)
    store.batch(task, files, dict(page=1), len(files))
    store.finish(task, 'completed')
    return task


def command(file, revision=0, action='confirm', title='Custom'):
    return dict(file_id=file['id'], expected_revision=revision, action=action,
        mapping=dict(kind='custom', title=title, tmdb_id=None, season=None, episode=None,
                     version=None) if action == 'confirm' else None)


@pytest.fixture
def index(tmp_path):
    store = MediaIndex(tmp_path / 'index.db')
    yield store
    store.close()


def test_identity_memberships_and_manual_bindings_are_independent(index):
    first = ref()
    insert(index, [first])
    insert(index, [first], source='b' * 32)
    assert index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 1
    assert index.db.execute('SELECT count(*) FROM memberships').fetchone()[0] == 2
    assert index.apply(scope(), 'c' * 32, [command(first)])['items'][0]['status'] == 'applied'
    moved = dict(first, name='Renamed.mkv', parent='another-folder')
    insert(index, [moved])
    row = index.items(scope())['items'][0]
    assert row['mapping']['title'] == 'Custom' and row['provenance'] == 'manual'
    assert row['file']['name'] == 'Renamed.mkv' and row['revision'] == 1
    assert index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 1


@pytest.mark.parametrize('terminal', ['failed', 'canceled', 'interrupted'])
def test_incomplete_generation_never_infers_missing(index, terminal):
    files = [ref(1), ref(2)]
    insert(index, files)
    task = index.start('a' * 32, scope())
    index.begin(task)
    index.batch(task, files[:1], dict(page=1), 1)
    index.finish(task, terminal, 'INCOMPLETE')
    assert len(index.items(scope(), source='a' * 32)['items']) == 2


def test_complete_generation_only_marks_own_membership_unavailable(index):
    file = ref()
    insert(index, [file])
    insert(index, [file], source='b' * 32)
    insert(index, [], source='a' * 32)
    assert index.items(scope(), source='a' * 32)['items'] == []
    assert len(index.items(scope(), source='b' * 32)['items']) == 1
    assert len(index.items(scope())['items']) == 1
    assert index.items(scope())['items'][0]['available'] is True
    insert(index, [], source='b' * 32)
    assert index.items(scope())['items'][0]['available'] is False


def test_checkpoint_batch_is_atomic_under_abort(index):
    task = index.start('a' * 32, scope())
    index.begin(task)
    index.db.execute("CREATE TRIGGER fail_batch BEFORE UPDATE ON scans BEGIN SELECT RAISE(ABORT,'fixture crash'); END")
    with pytest.raises(sqlite3.IntegrityError):
        index.batch(task, [ref()], dict(page=1), 1)
    assert index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 0
    assert index._scan(task)['checkpoint'] == {}
    index.db.execute('DROP TRIGGER fail_batch')
    index.batch(task, [ref()], dict(page=1), 1)
    assert index._scan(task)['checkpoint'] == dict(page=1)
    assert index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 1


def test_duplicate_batches_do_not_duplicate_counts_or_objects(index):
    task = index.start('a' * 32, scope())
    index.begin(task)
    for page in (1, 2, 1, 2):
        index.batch(task, [ref(page)], dict(page=page), 1)
    run = index._scan(task)
    assert (run['pages'], run['scanned'], run['discovered']) == (2, 2, 2)


def test_cross_account_same_id_not_merged_and_old_scope_hidden(index):
    insert(index, [ref()])
    other = scope('b')
    task = insert(index, [ref(expected=other)], 'b' * 32, other)
    assert index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 2
    assert len(index.items(other)['items']) == 1
    with pytest.raises(ValueError, match='ACCOUNT_MISMATCH'):
        index.jobs(scope(), task=task)


def test_recovery_marks_interrupted_and_preserves_committed_checkpoint(tmp_path):
    path = tmp_path / 'index.db'
    first = MediaIndex(path)
    task = first.start('a' * 32, scope())
    first.begin(task)
    first.batch(task, [ref()], dict(page=3), 1)
    first.close()
    second = MediaIndex(path)
    second.recover()
    try:
        assert second._scan(task)['state'] == 'interrupted'
        assert second._scan(task)['checkpoint'] == dict(page=3)
        assert len(second.items(scope())['items']) == 1
    finally:
        second.close()


def test_cancel_is_request_until_worker_ack_and_terminal_cannot_resurrect(index):
    task = index.start('a' * 32, scope())
    index.begin(task)
    receipt = index.cancel(task, scope())
    assert receipt['state'] == 'running' and receipt['cancel_requested']
    with pytest.raises(ValueError, match='STOPPED'):
        index.batch(task, [ref()], dict(page=1), 1)
    assert index.finish(task, 'completed')['state'] == 'canceled'
    assert index.finish(task, 'failed')['state'] == 'canceled'
    with pytest.raises(ValueError, match='TERMINAL'):
        index.begin(task)


def test_completion_wins_before_late_cancel(index):
    task = insert(index, [ref()])
    assert index.cancel(task, scope())['state'] == 'completed'
    assert not index.cancel(task, scope())['cancel_requested']


def test_review_cas_race_retry_and_undo_do_not_mutate_file(index):
    file = ref()
    insert(index, [file])
    before = index.db.execute('SELECT ref FROM objects').fetchone()[0]
    cmd = command(file)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda key: index.apply(scope(), key * 32, [cmd]), ['b', 'c']))
    statuses = [r['items'][0]['status'] for r in results]
    assert sorted(statuses) == ['applied', 'conflict']
    winning = 'b' if statuses[0] == 'applied' else 'c'
    assert index.apply(scope(), winning * 32, [cmd])['items'][0] == dict(status='applied', revision=1)
    assert index.apply(scope(), winning * 32, [command(file, title='Changed')])['items'][0]['status'] == 'conflict'
    assert index.apply(scope(), 'd' * 32, [command(file, 1, 'undo')])['items'][0]['revision'] == 2
    row = index.items(scope())['items'][0]
    assert row['mapping'] is None and row['revision'] == 2
    assert index.apply(scope(), 'e' * 32, [command(file, 1, 'undo')])['items'][0]['status'] == 'conflict'
    assert index.db.execute('SELECT ref FROM objects').fetchone()[0] == before


def test_partial_batch_results_and_preview_are_truthful(index):
    file = ref()
    insert(index, [file])
    commands = [command(file), command(ref(999)), command(file, revision=22)]
    assert [r['status'] for r in index.preview(scope(), commands)['items']] == ['ready', 'failed', 'conflict']
    assert index.items(scope())['items'][0]['revision'] == 0
    assert [r['status'] for r in index.apply(scope(), 'f' * 32, commands)['items']] == ['applied', 'failed', 'conflict']


def test_undo_preview_matches_actual_restored_mapping(index):
    file = ref()
    insert(index, [file])
    index.apply(scope(), 'a' * 32, [command(file, title='First')])
    index.apply(scope(), 'b' * 32, [command(file, 1, title='Second')])
    cmd = command(file, 2, 'undo')
    preview = index.preview(scope(), [cmd])['items'][0]
    assert preview['after']['title'] == 'First'
    index.apply(scope(), 'c' * 32, [cmd])
    assert index.items(scope())['items'][0]['mapping'] == preview['after']


@pytest.mark.parametrize('name,state,pair', [
    ('Show.S00E01.mkv', 'proposed', (0, 1)), ('Show.E01.mkv', 'ambiguous', (None, None)),
    ('Movie.1990.2020.mkv', 'ambiguous', (None, None)), ('Private.mkv', 'unmatched', (None, None)),
    ('Show.S01E01-E02.mkv', 'ambiguous', (None, None))])
def test_filename_is_only_a_conservative_suggestion(name, state, pair):
    result = suggestion(name)
    assert result[0] == state
    assert (result[2][0]['season'], result[2][0]['episode']) == pair


@pytest.mark.parametrize('change', [dict(kind='tv'), dict(tmdb_id=True), dict(season=1), dict(title='https://secret'), dict(kind='unknown')])
def test_mapping_never_invents_missing_tv_fields(change):
    value = command(ref())['mapping']
    value.update(change)
    with pytest.raises(ValueError):
        mapping(value)


def test_tv_zero_season_and_movie_identity_remain_distinct():
    tv = dict(kind='tv', title='Show', tmdb_id=10, season=0, episode=1, version=None)
    assert mapping(tv) == tv
    movie = dict(tv, kind='movie', season=None, episode=None)
    assert mapping(movie) != mapping(tv)


def test_page_limits_sensitive_projection_and_unknown_schema(index, tmp_path):
    for i in range(10):
        insert(index, [ref(i, name='长' * 1000 + '.mkv', parent='目' * 4000)])
    result = index.items(scope())
    assert result['next_offset'] == 5
    assert len(json.dumps(result, ensure_ascii=False).encode()) < 16384
    assert all(row['file']['truncated'] for row in result['items'])
    with pytest.raises(ValueError):
        index.items(scope(), limit=6)
    assert 'account_id' not in json.dumps(index.jobs(scope()))
    path = tmp_path / 'future.db'
    db = sqlite3.connect(path)
    db.execute('PRAGMA user_version=900')
    db.close()
    with pytest.raises(ValueError, match='SCHEMA_UNSUPPORTED'):
        MediaIndex(path)
    db = sqlite3.connect(path)
    assert db.execute('PRAGMA user_version').fetchone()[0] == 900
    db.close()


@pytest.mark.parametrize('state,public', PREPARATION_STATES.items())
def test_preparation_projection_is_readonly_whitelisted(state, public):
    row = dict(id='a' * 32, state=state, updated=1, payload={'secret': 'dont-export'})
    result = preparation(row, scope())
    assert result['state'] == public and row['state'] == state
    assert 'dont-export' not in json.dumps(result)
    assert result['result_summary'] == 'CANCEL_NOT_SUPPORTED'

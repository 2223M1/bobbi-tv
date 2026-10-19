import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
spec = importlib.util.spec_from_file_location('ce_state_migration', ROOT / 'tools/ce_state_migration.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ACCOUNT = 'b' * 64
SCOPE = dict(account_id='115:' + 'a' * 64, epoch=1, authenticated=True)
IDENTITY = dict(account_id=SCOPE['account_id'], legacy_scope=ACCOUNT)
DESTINATION = '/115open/movies'


def fixture(tmp_path):
    from bobbi_core.ledger import Ledger
    from bobbi_core.font_cache import FONT_DDL
    from bobbi_core.subtitle_store import DEFINITIONS
    source = tmp_path / 'old'
    source.mkdir()
    with Ledger(source / 'resources.sqlite') as ledger:
        for statement in FONT_DDL:
            ledger.db.execute(statement)
        for statement in DEFINITIONS.values():
            ledger.db.execute(statement)
        for i, state in enumerate(('ready', 'queued', 'space_blocked', 'downloading', 'mapping', 'submitting', 'checking')):
            ledger.db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (str(i), str(i) * 40, '{}', state, 100, 0, '115', ACCOUNT, DESTINATION, str(i), 0, 0, 0))
        ledger.db.execute('INSERT INTO resources VALUES(?,?,?)', ('res', json.dumps(dict(account=ACCOUNT, state='ready')), 1))
        ledger.db.execute('INSERT INTO prepared_bindings VALUES(?,?,?,?,?)', ('0', 'res', 'm', 'v', '{}'))
        ledger.db.execute('INSERT INTO preparation_intents VALUES(?,?,?,?,?)', ('intent', '{}', 'validating', 0, '{}'))
        ledger.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?)', ('watch', 'res', 'play', 600, '[[0,200]]', 0, None, 0))
        for kind, extension, data in (('fonts', '.ttf', b'font-fixture'), ('subtitles', '.ass', b'subtitle-fixture')):
            key = hashlib.sha256(data).hexdigest()
            obj = source / kind / 'objects' / (key + extension)
            obj.parent.mkdir(parents=True)
            obj.write_bytes(data)
            if kind == 'fonts':
                ledger.db.execute('INSERT INTO font_objects VALUES(?,?,?)',
                    (key, json.dumps(dict(sha256=key, extension=extension, bytes=len(data))), 0))
            else:
                ledger.db.execute('INSERT INTO subtitle_objects VALUES(?,?,?)', (key, len(data), extension))
    target = tmp_path / 'new' / ('a' * 64 + '-1')
    return source, target


def migrate(source, target, **kwargs):
    return m.migrate_preparation(source, target, kwargs.pop('identity', IDENTITY), SCOPE,
                                ACCOUNT, DESTINATION, kwargs.pop('stopped', lambda: None), **kwargs)


def test_ready_objects_wal_and_watch_preserved_without_unsent_replay(tmp_path):
    source, target = fixture(tmp_path)
    # Keep a committed WAL connection open to prove backup API, not raw copy.
    old = sqlite3.connect(str(source / 'resources.sqlite'))
    old.execute('INSERT INTO settings VALUES(?,?)', ('wal_only', 'kept'))
    old.commit()
    try:
        result = migrate(source, target)
        assert result['ledger']['counts']['prepared_bindings'] == 1
        assert result['objects']['count'] == 2
        with sqlite3.connect(target / 'resources.sqlite') as db:
            assert db.execute("SELECT value FROM settings WHERE key='wal_only'").fetchone() == ('kept',)
            states = dict(db.execute('SELECT id,state FROM tasks'))
            assert states == {'0':'ready','1':'suppressed','2':'suppressed','3':'downloading',
                              '4':'mapping','5':'uncertain','6':'mapping'}
            assert db.execute("SELECT reserved_bytes FROM tasks WHERE id='1'").fetchone() == (100,)
            assert db.execute('SELECT state FROM preparation_intents').fetchone() == ('failed',)
            assert db.execute('SELECT intervals,natural FROM sessions').fetchone() == ('[[0,200]]', 0)
        assert old.execute("SELECT state FROM tasks WHERE id='1'").fetchone() == ('queued',)
        assert old.execute('SELECT ended FROM sessions').fetchone() == (None,)
        assert list((target / 'fonts/objects').glob('*.ttf'))[0].read_bytes() == b'font-fixture'
        assert list((target / 'subtitles/objects').glob('*.ass'))[0].read_bytes() == b'subtitle-fixture'
    finally:
        old.close()


def test_wrong_uid_never_creates_new_epoch(tmp_path):
    source, target = fixture(tmp_path)
    with pytest.raises(ValueError, match='UID_MISMATCH'):
        migrate(source, target, identity=dict(IDENTITY, account_id='115:' + 'c'*64))
    assert not target.parent.exists()


def test_nonempty_epoch_never_overwritten(tmp_path):
    source, target = fixture(tmp_path)
    target.mkdir(parents=True)
    (target / 'mine').write_text('keep')
    with pytest.raises(ValueError, match='NEW_EPOCH'):
        migrate(source, target)
    assert (target / 'mine').read_text() == 'keep'


def test_corrupt_font_blocks_publish_preserves_source(tmp_path):
    source, target = fixture(tmp_path)
    font = next((source / 'fonts/objects').iterdir())
    font.write_bytes(b'font-corrupt')
    with pytest.raises(ValueError, match='OBJECT_CHANGED'):
        migrate(source, target)
    assert not target.exists()
    assert font.read_bytes() == b'font-corrupt'


def test_owner_resumed_cancels_before_publish(tmp_path):
    source, target = fixture(tmp_path)
    def stopped():
        raise RuntimeError('owner restarted')
    with pytest.raises(RuntimeError, match='restarted'):
        migrate(source, target, stopped=stopped)
    assert not target.parent.exists()


def test_unknown_db_tables_fail_closed(tmp_path):
    source, target = fixture(tmp_path)
    with sqlite3.connect(source / 'resources.sqlite') as db:
        db.execute('CREATE TABLE unexpected(secret TEXT)')
    with pytest.raises(ValueError, match='UNKNOWN_SCHEMA'):
        migrate(source, target)
    assert not target.exists()


def test_asset_link_never_followed(tmp_path):
    source, target = fixture(tmp_path)
    font = next((source / 'fonts/objects').iterdir())
    external = tmp_path / 'unrelated'
    external.write_bytes(font.read_bytes())
    font.unlink()
    try:
        font.symlink_to(external)
    except OSError:
        pytest.skip('host cannot create a symlink')
    with pytest.raises(ValueError, match='SYMLINK'):
        migrate(source, target)
    assert not target.exists()


def direct_fixture(source, state='waiting', account=ACCOUNT, destination=DESTINATION):
    with sqlite3.connect(source / 'direct.sqlite3') as db:
        db.execute('CREATE TABLE direct_jobs (key TEXT PRIMARY KEY, account TEXT, destination TEXT, '
                   'body TEXT, state TEXT, created REAL, due REAL, attempts INTEGER, evidence TEXT, error TEXT)')
        db.execute('INSERT INTO direct_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                   ('direct', account, destination, '{}', state, 0, 0, 0, '{}', ''))


@pytest.mark.parametrize('field', ['account', 'destination'])
def test_direct_null_scope_does_not_bypass_sql_comparison(tmp_path, field):
    source, target = fixture(tmp_path)
    direct_fixture(source, **{field: None})
    with pytest.raises(ValueError, match='DIRECT_SCOPE'):
        migrate(source, target)
    assert not target.exists()
    with sqlite3.connect(source / 'direct.sqlite3') as db:
        assert db.execute('SELECT state FROM direct_jobs').fetchone() == ('waiting',)


@pytest.mark.parametrize('state', ['unknown', '', None])
def test_direct_unknown_state_never_reaches_portable_worker(tmp_path, state):
    source, target = fixture(tmp_path)
    direct_fixture(source, state=state)
    with pytest.raises(ValueError, match='DIRECT_STATE'):
        migrate(source, target)
    assert not target.exists()


@pytest.mark.parametrize('kind', ['trigger', 'view'])
def test_direct_executable_schema_is_not_carried_into_host(tmp_path, kind):
    source, target = fixture(tmp_path)
    direct_fixture(source)
    with sqlite3.connect(source / 'direct.sqlite3') as db:
        if kind == 'trigger':
            db.execute("CREATE TRIGGER unsafe AFTER UPDATE ON direct_jobs BEGIN "
                       "UPDATE direct_jobs SET state='queued'; END")
        else:
            db.execute('CREATE VIEW unsafe AS SELECT * FROM direct_jobs')
    with pytest.raises(ValueError, match='DIRECT_SCOPE'):
        migrate(source, target)
    assert not target.exists()


@pytest.mark.parametrize('state,expected', [('queued', 'failed'), ('inspect', 'failed'),
    ('submit_ready', 'failed'), ('submitting', 'uncertain'), ('waiting', 'waiting'),
    ('uncertain', 'uncertain'), ('qualify', 'qualify'), ('ready', 'ready')])
def test_direct_submission_boundary_is_preserved(tmp_path, state, expected):
    source, target = fixture(tmp_path)
    direct_fixture(source, state=state)
    migrate(source, target)
    with sqlite3.connect(target / 'direct.sqlite3') as db:
        assert db.execute('SELECT state FROM direct_jobs').fetchone() == (expected,)
    with sqlite3.connect(source / 'direct.sqlite3') as db:
        assert db.execute('SELECT state FROM direct_jobs').fetchone() == (state,)


def add_same_release(source, with_metadata):
    from bobbi_core.metadata_cache import MetadataCache
    from bobbi_core.subtitle_pack import select
    from bobbi_core.torrent_subtitles import matching_chinese_sidecars
    from bobbi_core.video_context import video_identity
    raw = b'subtitle-fixture'
    key = hashlib.sha256(raw).hexdigest()
    video = video_identity('tmdb:tv:1:s1:e1', 'f' * 64,
        dict(source_info_hash='e' * 40, torrent_file_id=1,
             torrent_path='Fixture.S01E01.mkv', torrent_file_bytes=1000))
    metadata = dict(hash='e' * 40, title='Fixture', file_stats=[
        dict(id=1, path='Fixture.S01E01.mkv', length=1000),
        dict(id=2, path='Fixture.S01E01.chs.ass', length=len(raw))])
    selection = select(video, metadata, matching_chinese_sidecars)
    assert selection is not None
    record = dict(video=video, timing=dict(kind='same_release', selection=selection))
    with sqlite3.connect(source / 'resources.sqlite') as db:
        cursor = db.execute('INSERT INTO subtitle_revisions(binding_key,video_key,subtitle_sha256,payload,at) VALUES(?,?,?,?,?)',
                            ('bound', video['key'], key, json.dumps(record), 0))
        db.execute('INSERT INTO subtitle_current VALUES(?,?,?)', ('bound', video['key'], cursor.lastrowid))
    if with_metadata:
        MetadataCache(source / 'torrent-file-metadata').store(metadata)


def test_same_release_without_metadata_cannot_claim_successful_migration(tmp_path):
    source, target = fixture(tmp_path)
    add_same_release(source, with_metadata=False)
    with pytest.raises(ValueError, match='SUBTITLE_PACK_PROOF'):
        migrate(source, target)
    assert not target.exists()
    assert not (source / 'torrent-file-metadata').exists()


def test_same_release_metadata_is_preserved_and_rechecked(tmp_path):
    source, target = fixture(tmp_path)
    add_same_release(source, with_metadata=True)
    result = migrate(source, target)
    assert result['metadata_entries'] == 1
    from bobbi_core.metadata_cache import MetadataCache
    assert MetadataCache(target / 'torrent-file-metadata').load('e' * 40) == \
           MetadataCache(source / 'torrent-file-metadata').load('e' * 40)


def test_changed_same_release_selection_prevents_publish(tmp_path):
    source, target = fixture(tmp_path)
    add_same_release(source, with_metadata=True)
    with sqlite3.connect(source / 'resources.sqlite') as db:
        record = json.loads(db.execute('SELECT payload FROM subtitle_revisions').fetchone()[0])
        record['timing']['selection']['subtitle_file']['path'] = 'Different.S01E01.chs.ass'
        db.execute('UPDATE subtitle_revisions SET payload=?', (json.dumps(record),))
    with pytest.raises(ValueError, match='SUBTITLE_PACK_PROOF'):
        migrate(source, target)
    assert not target.exists()


@pytest.mark.parametrize('relation', ['same', 'child', 'parent', 'wrong_epoch'])
def test_source_and_target_ranges_are_disjoint_and_exact_epoch(tmp_path, relation):
    source, original_target = fixture(tmp_path)
    targets = {'same': source, 'child': source / original_target.name,
               'parent': source.parent, 'wrong_epoch': original_target.with_name('a' * 64 + '-2')}
    target = targets[relation]
    before = m.digest(source / 'resources.sqlite')
    with pytest.raises(ValueError, match='NEW_EPOCH'):
        migrate(source, target)
    assert m.digest(source / 'resources.sqlite') == before
    assert not list(source.glob('.migration-*'))


@pytest.mark.parametrize('failure_call', [2, 3, 5])
def test_lease_revocation_during_backup_or_asset_copy_never_publishes(tmp_path, failure_call):
    source, target = fixture(tmp_path)
    calls = []
    def stopped():
        calls.append(True)
        if len(calls) == failure_call:
            raise RuntimeError('owner restarted during migration')
    with pytest.raises(RuntimeError, match='during migration'):
        migrate(source, target, stopped=stopped)
    assert len(calls) == failure_call and not target.exists()
    with sqlite3.connect(source / 'resources.sqlite') as db:
        assert db.execute("SELECT state FROM tasks WHERE id='1'").fetchone() == ('queued',)
        assert db.execute('SELECT ended FROM sessions').fetchone() == (None,)


def test_final_lease_recheck_blocks_publication_after_complete_copy(tmp_path):
    source, target = fixture(tmp_path)
    def stopped():
        if target.parent.exists() and list(target.parent.glob('.migration-*/migration-receipt.json')):
            raise RuntimeError('owner restarted at final gate')
    with pytest.raises(RuntimeError, match='final gate'):
        migrate(source, target, stopped=stopped)
    assert not target.exists()
    # A failed new staging copy is preserved for diagnosis, never mistaken for
    # a live epoch and never cleaned up by touching the old source directory.
    assert len(list(target.parent.glob('.migration-*/migration-receipt.json'))) == 1

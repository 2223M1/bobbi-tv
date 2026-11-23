"""Read-only exact-observation history duration in the existing file surface."""
import pickle
import sys
from types import SimpleNamespace

import pytest

from bobbi_core.catalog_display import file_description, media_facts_text
from bobbi_core.catalog_query import opaque, wire
from bobbi_core.file_media_facts import MAX_BATCH, checked
from bobbi_core.media_library_index import MediaIndex
from bobbi_platform.host import Host
from test_ce2097_file_history import database, history, playback
from test_media_library_index import insert, ref, scope
from test_personal_catalog import catalog, plugin
from test_scan_source_ports import cd2, scan, query


def save(files, file, duration=100, reason='STOP', position=25):
    context = files.begin(file)
    assert files.save(dict(playback(context, reason=reason, position=position), total_time=duration))
    return context


@pytest.fixture
def scene(database, tmp_path):
    storage, root = database
    db = storage.PickleDatabase(profile_root=root / 'profile-a')
    files = history.FileHistory(db, clock=lambda: 1700000000)
    store = MediaIndex(tmp_path / 'media-index.sqlite3', file_facts=files.media_facts)
    yield SimpleNamespace(db=db, files=files, index=store, root=root, storage=storage)
    store.close()


def card(scene, file):
    return scene.index.describe_files(scope(), [file['id']])['items'][0]


def test_completed_file_fact_is_visible_and_history_schema_and_bytes_are_unchanged(scene):
    file = ref()
    insert(scene.index, [file])
    scene.db.set_item('jt:lfh', 'legacy', {'title': 'Original title history'})
    save(scene.files, file, reason='NATURAL_EOF', position=100)
    assert scene.files.rows() == []  # Completed history is not Continue Watching.
    path = scene.root / 'profile-a/database.pickle'
    original = path.read_bytes()
    before = list(scene.index.db.iterdump())
    value = card(scene, file)
    assert value['media_facts'] == dict(source='playback_history', observation_key=opaque(file),
        duration_seconds=100., recorded_at=1700000000, state='matched')
    assert '历史观测时长 0:01:40' in file_description(value)
    text = media_facts_text(value)
    assert '播放器历史观测时长' in text and '不是探测总时长' in text
    assert '2023-11-14 22:13:20 UTC' in text and opaque(file) in text
    assert path.read_bytes() == original and list(scene.index.db.iterdump()) == before
    stored = pickle.loads(original)
    assert set(stored[history.KEY][file['id']]) == history.FIELDS
    assert stored['jt:lfh'] == {'legacy': {'title': 'Original title history'}}
    assert scene.index.db.execute('PRAGMA user_version').fetchone()[0] == 4


@pytest.mark.parametrize('change', ['size', 'name', 'parent'])
def test_every_saved_observation_field_invalidates_duration_and_retains_original(scene, change):
    file = ref()
    insert(scene.index, [file])
    save(scene.files, file)
    original = scene.files.get(file['id'])
    replacement = dict(file, **{change: file['size'] + 1 if change == 'size' else 'changed'})
    insert(scene.index, [replacement])
    value = card(scene, replacement)
    assert value['media_facts']['state'] == 'verification_required'
    assert value['media_facts']['observation_key'] == opaque(file)
    assert value['observation_key'] == opaque(replacement)
    assert scene.files.get(file['id']) == original
    assert '历史时长待重新核验' in file_description(value)
    assert '当前文件时长未知；旧观察记录为 0:01:40' in media_facts_text(value)
    # Reserving a new writer is still not a new content observation.
    context = scene.files.begin(replacement)
    assert card(scene, replacement)['media_facts']['state'] == 'verification_required'
    assert scene.files.save(dict(playback(context), total_time=125))
    assert card(scene, replacement)['media_facts']['state'] == 'matched'
    assert card(scene, replacement)['media_facts']['duration_seconds'] == 125


@pytest.mark.parametrize('fingerprint', [None, {'kind': '115_sha1', 'value': 'b' * 40}])
def test_fingerprint_appearance_or_change_cannot_rebind_old_duration(scene, fingerprint):
    expected = scope(provider='115')
    file = dict(ref(expected=expected), fingerprint=fingerprint)
    insert(scene.index, [file], expected=expected)
    save(scene.files, file)
    replacement = dict(file, fingerprint={'kind': '115_sha1', 'value': 'c' * 40})
    insert(scene.index, [replacement], expected=expected)
    value = scene.index.describe_files(expected, [file['id']])['items'][0]
    assert value['media_facts']['state'] == 'verification_required'
    assert value['media_facts']['observation_key'] == opaque(file)


@pytest.mark.parametrize('duration', [None, 0])
def test_missing_duration_stays_unknown_without_filename_or_candidate_inference(scene, duration):
    file = ref(name='Film.2160p.HDR10.HEVC.Atmos.120min.mkv')
    insert(scene.index, [file])
    save(scene.files, file, duration=duration, position=0)
    value = card(scene, file)
    assert 'media_facts' not in value
    text = media_facts_text(dict(value, runtime=7200, prepared_media_profile={'video': {'height': 2160}}))
    assert '时长：未知' in text
    for field in ('分辨率', '编码', 'HDR', '音轨', '字幕'):
        assert field + '：未知' in text


def test_no_history_and_no_adapter_keep_all_media_fields_unknown(scene, tmp_path):
    file = ref()
    insert(scene.index, [file])
    assert 'media_facts' not in card(scene, file)
    store = MediaIndex(tmp_path / 'no-adapter.sqlite')
    try:
        insert(store, [file])
        assert 'media_facts' not in store.describe_files(scope(), [file['id']])['items'][0]
    finally:
        store.close()


def test_one_disk_read_per_bounded_file_page_and_no_work_layer_read(scene, monkeypatch):
    files = [ref(number) for number in range(32)]
    insert(scene.index, files[:20])
    insert(scene.index, files[20:], source='b' * 32)
    for file in files:
        save(scene.files, file)
    reads, original = [], scene.db.get_keys_checked
    def read(key):
        reads.append(key)
        return original(key)
    monkeypatch.setattr(scene.db, 'get_keys_checked', read)
    scene.index.query(scope(), query={'view': 'works'})
    assert reads == []
    cursor, seen = None, []
    while True:
        before = len(reads)
        page = scene.index.query(scope(), query={'view': 'files'}, limit=32, cursor=cursor)
        assert len(reads) == before + 1 and len(wire(page)) <= 15000
        assert all(row['media_facts']['state'] == 'matched' for row in page['items'])
        seen += [row['entity_id'] for row in page['items']]
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 32
    before = len(reads)
    scene.index.describe_files(scope(), [file['id'] for file in files[:20]])
    assert len(reads) == before + 1
    assert not scene.files.media_facts([ref(999)])


@pytest.mark.parametrize('references', [[], None, [None], [ref()] * (MAX_BATCH + 1)])
def test_batch_rejects_invalid_input_before_disk_read(references):
    files = history.FileHistory(SimpleNamespace(get_keys_checked=lambda key: pytest.fail('invalid batch read disk')))
    with pytest.raises(ValueError):
        files.media_facts(references)


def test_corrupt_one_record_does_not_hide_valid_sibling_or_rewrite_storage(scene):
    one, two = ref(1), ref(2)
    insert(scene.index, [one, two])
    save(scene.files, one)
    save(scene.files, two)
    scene.db.set_item(history.KEY, one['id'], {'version': 99})
    original = (scene.root / 'profile-a/database.pickle').read_bytes()
    rows = {row['entity_id']: row for row in scene.index.describe_files(scope(), [one['id'], two['id']])['items']}
    assert 'media_facts' not in rows[one['id']]
    assert rows[two['id']]['media_facts']['state'] == 'matched'
    assert (scene.root / 'profile-a/database.pickle').read_bytes() == original


@pytest.mark.parametrize('field', ['duration', 'updated_at'])
def test_extreme_corrupt_history_number_is_unknown_without_breaking_catalog(scene, field):
    file = ref()
    insert(scene.index, [file])
    save(scene.files, file)
    record = scene.files.get(file['id'])
    scene.db.set_item(history.KEY, file['id'], dict(record, **{field: 1 << 2000}))
    original = (scene.root / 'profile-a/database.pickle').read_bytes()
    assert 'media_facts' not in card(scene, file)
    assert (scene.root / 'profile-a/database.pickle').read_bytes() == original


@pytest.mark.parametrize('failure', ['unavailable', 'schema', 'foreign-record'])
def test_unavailable_or_wrong_history_never_attaches_other_facts(scene, monkeypatch, failure):
    file = ref()
    insert(scene.index, [file])
    save(scene.files, ref(2))
    foreign = scene.files.get(ref(2)['id'])
    def read(key):
        if failure == 'unavailable':
            raise OSError('private path unavailable')
        return {history.KEY: [] if failure == 'schema' else {file['id']: foreign}, history.FACTS_KEY: None}
    monkeypatch.setattr(scene.db, 'get_keys_checked', read)
    assert 'media_facts' not in card(scene, file)


def test_history_does_not_cross_accounts_or_source_memberships(scene):
    one, other = ref(1), ref(1, expected=scope('b'))
    insert(scene.index, [one])
    insert(scene.index, [one], source='c' * 32)
    insert(scene.index, [other], source='b' * 32, expected=scope('b'))
    save(scene.files, one)
    save(scene.files, other, duration=200)
    a = scene.index.describe_files(scope(), [one['id'], other['id']])['items']
    b = scene.index.describe_files(scope('b'), [one['id'], other['id']])['items']
    assert len(a) == len(b) == 1
    assert a[0]['media_facts']['duration_seconds'] == 100
    assert b[0]['media_facts']['duration_seconds'] == 200
    assert a[0]['source_total'] == 2


def test_typed_mounted_file_never_consumes_unrelated_native_file_history(cd2):
    service, source, _, _ = cd2
    scan(cd2)
    def forbidden(references):
        pytest.fail('typed mounted observation entered the native FileRef history adapter')
    service.index.file_facts = forbidden
    rows = query(cd2, query={'view': 'files'})['items']
    assert rows and all('media_facts' not in row for row in rows)


@pytest.mark.parametrize('invalid', ['wrong-type', 'secret-field', 'source', 'asserted-match'])
def test_query_discards_bad_optional_adapter_output_without_losing_file(scene, invalid):
    file = ref()
    insert(scene.index, [file])
    evidence = dict(source='playback_history', observation_key=opaque(file), duration_seconds=100, recorded_at=1000)
    if invalid == 'secret-field':
        evidence['token'] = 'SECRET'
    elif invalid == 'source':
        evidence['source'] = 'server_candidate'
    elif invalid == 'asserted-match':
        evidence.update(state='matched', observation_key='f' * 64)
    scene.index.file_facts = lambda references: [] if invalid == 'wrong-type' else {file['id']: evidence}
    value = card(scene, file)
    assert value['entity_id'] == file['id'] and 'media_facts' not in value


@pytest.mark.parametrize('change', [
    {'duration_seconds': True}, {'duration_seconds': float('nan')}, {'duration_seconds': float('inf')},
    {'duration_seconds': 1 << 2000}, {'recorded_at': 1 << 2000},
    {'duration_seconds': -1}, {'duration_seconds': 864001}, {'recorded_at': float('nan')},
    {'recorded_at': -1}, {'source': 'server_candidate'}, {'token': 'secret'},
    {'state': 'matched', 'observation_key': 'b' * 64},
])
def test_facts_projection_rejects_unbounded_or_asserted_authority(change):
    value = dict(source='playback_history', observation_key='a' * 64, duration_seconds=100, recorded_at=1000)
    with pytest.raises(ValueError, match='FILE_MEDIA_FACTS_INVALID'):
        checked(dict(value, **change), 'a' * 64)


def test_host_captures_history_adapter_profile_before_later_root_change(scene, tmp_path, monkeypatch):
    file = ref()
    save(scene.files, file)
    other = history.FileHistory(scene.storage.PickleDatabase(profile_root=tmp_path / 'profile-b'))
    save(other, file, duration=200)
    host = Host(tmp_path / 'host-a', plugin_root=scene.root / 'profile-a', file_history=scene.files)
    monkeypatch.setattr(host, '_pans', lambda: SimpleNamespace())
    catalog_service = host._catalog()
    try:
        assert catalog_service.index.file_facts.__self__ is scene.files
        insert(catalog_service.index, [file])
        host.plugin_root = tmp_path / 'profile-b'
        monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
            translatePath=lambda path: pytest.fail('bound facts adapter resolved current profile')))
        result = catalog_service.index.describe_files(scope(), [file['id']])['items'][0]
        assert result['media_facts']['duration_seconds'] == 100
    finally:
        catalog_service.close()


def test_profile_switch_during_fact_read_cannot_publish_and_old_host_never_revives(scene, tmp_path, monkeypatch):
    file = ref()
    save(scene.files, file)
    current, reports = [True], []
    host = Host(tmp_path / 'host-a', file_history=scene.files,
        profile_current=lambda: current[0], report=reports.append)
    host.accounts = object()
    pans = SimpleNamespace(accounts=SimpleNamespace(require_current=lambda expected: expected,
        run_if_current=lambda expected, operation: operation()))
    monkeypatch.setattr(host, '_pans', lambda: pans)
    owner = host._catalog()
    insert(owner.index, [file])
    original = scene.db.get_keys_checked
    def read(key):
        result = original(key)
        current[0] = False
        return result
    monkeypatch.setattr(scene.db, 'get_keys_checked', read)
    try:
        with pytest.raises(OSError, match='PROFILE_CHANGED'):
            host.dispatch('catalog_describe', dict(expected=scope(), file_ids=[file['id']]))
        current[0] = True
        with pytest.raises(OSError, match='PROFILE_CHANGED'):
            host.dispatch('catalog_describe', dict(expected=scope(), file_ids=[file['id']]))
        assert reports == ['PROFILE_CHANGED']
    finally:
        owner.close()


def test_existing_file_facts_tv_entry_displays_real_history_and_never_starts_playback(scene, catalog, monkeypatch):
    file = ref(expected=catalog.account)
    insert(scene.index, [file], expected=catalog.account)
    save(scene.files, file, duration=123)
    catalog.info_labels['Container.FolderPath'] = 'plugin://plugin.video.bobbi/?action=personal_catalog'
    views, calls = [], []
    original = catalog.rpc
    def rpc(action, body):
        calls.append(action)
        if action == 'catalog_describe':
            return scene.index.describe_files(body['expected'], body['file_ids'])
        return original(action, body)
    monkeypatch.setattr(sys.modules['xbmcgui'], 'Dialog', lambda: SimpleNamespace(
        textviewer=lambda title, text: views.append((title, text)),
        ok=lambda *args: pytest.fail('file facts entry failed')))
    catalog.catalog.manage(dict(catalog.params, mode='file_facts', object_id=file['id']), rpc=rpc)
    assert len(views) == 1 and views[0][0] == '本文件信息与依据'
    assert '0:02:03' in views[0][1] and '播放器历史观测时长' in views[0][1]
    assert '分辨率：未知' in views[0][1] and '音轨：未知' in views[0][1]
    assert calls == ['pan_status', 'catalog_describe', 'pan_status']
    assert not catalog.resolved

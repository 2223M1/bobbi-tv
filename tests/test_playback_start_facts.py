"""Scoped native start projection through real existing history/index storage.

Native replies are simulated; these checks are not device acceptance.
"""
from frozen_history import source_bytes
import ast
from copy import deepcopy
import json
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace, ModuleType
from uuid import uuid4

import pytest

from bobbi_core import playback_presentation, playback_start_facts
from bobbi_core.catalog_display import media_facts_text
from bobbi_core.catalog_query import opaque, wire
from bobbi_core.file_ref import locator
from bobbi_core.media_library_index import MediaIndex
from bobbi_core.playback_request import digest
from bobbi_platform.paths import ProfileBinding
from test_ce2097_file_history import database, history, module, playback, submission
from test_media_library_index import ref, scope, insert

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scene(database):
    storage, root = database
    current = ['A']
    binding = ProfileBinding(lambda addon: root / current[0] / addon)
    db = storage.PickleDatabase(profile_root=binding.root('plugin.video.bobbi'))
    files = history.FileHistory(db, clock=lambda: 1700000010)
    file = ref()
    context = files.begin(file)
    url = 'http://127.0.0.1:1234/stream/' + 'd' * 32 + '/video.mkv'
    identity = 'transport:' + digest(locator(file)) + '|transport:' + digest(url)
    owner = dict(boot_id='a' * 32, epoch=2, request_id='b' * 32, file_identity=identity)
    row = dict(protocol=1, native_instance=str(uuid4()), request_id=owner['request_id'], file_identity=identity,
        url_sha256=digest(url), phase='AV_STARTED', sequence=2, user_intent=0, paused=False,
        subtitle_intent=0, subtitle_auto_intent=0, audio_intent=0, open_epoch=3, control_protocol=1)
    raw = dict(control_protocol=1, status='READY', receipt=deepcopy(row), selection_epoch=3,
        position_ms=2000, duration_ms=100000, can_seek=True, visible=True, chapters=[], audio_index=0, current_index=0,
        audio_streams=[dict(index=0, stream_key='c' * 64, language='jpn', name='Audio', codec='aac', channels=2)],
        streams=[dict(index=0, stream_key='e' * 64, language='zho', name='简体', isforced=False, isimpaired=True)])
    data = dict(playback(context), selection_policy='exact', request_id=owner['request_id'], _account=scope(), url=url)
    calls = []
    def call(message, **kwargs):
        calls.append((message, kwargs))
        return playback_presentation.project(raw, owner['boot_id'], owner['epoch'], row)
    client = SimpleNamespace(call=call)
    index = MediaIndex(root / 'index.sqlite3', file_facts=files.media_facts)
    insert(index, [file])
    value = SimpleNamespace(storage=storage, root=root, db=db, files=files, file=file, context=context,
        owner=owner, row=row, raw=raw, data=data, client=client, calls=calls, binding=binding, current=current, index=index)
    yield value
    index.close()


def capture(scene):
    return submission.capture_start(scene.data, scene.client, scene.owner, scene.row['native_instance'],
                                    scene.binding, clock=lambda: 1700000000)


def card(scene):
    return scene.index.describe_files(scope(), [scene.file['id']])['items'][0]


def stored_facts(scene):
    return scene.db.get_key_checked(history.FACTS_KEY)[scene.file['id']]


def test_real_start_projection_roundtrip_is_one_atomic_history_row_and_readonly_index(scene):
    scene.raw['prepared_media_profile'] = {'codec': 'SECRET-CANDIDATE'}
    scene.raw['audio_streams'][0]['token'] = 'SECRET-TOKEN'
    scene.raw['streams'][0]['codec'] = 'SECRET-UNEXPOSED-CODEC'
    assert capture(scene)
    assert len(scene.calls) == 1 and scene.calls[0][0]['operation'] == 'playback_presentation'
    assert scene.files.save(scene.data)
    path = Path(scene.db._database_path)
    raw = path.read_bytes()
    stored = pickle.loads(raw)[history.KEY][scene.file['id']]
    assert stored['version'] == 1 and set(stored) == history.FIELDS
    assert pickle.loads(raw)[history.FACTS_KEY][scene.file['id']]['observation'] == scene.data['_file_start_observation']
    assert all(secret not in raw for secret in (b'SECRET', b'/stream/', b'url_sha256', b'file_identity', b'stream_key'))
    restarted = history.FileHistory(scene.storage.PickleDatabase(profile_root=path.parent))
    assert restarted.get(scene.file['id']) == stored
    before = list(scene.index.db.iterdump())
    value = card(scene)
    assert value['media_facts']['state'] == 'matched'
    start = value['media_facts']['playback_start']
    assert start['recorded_at'] == 1700000000
    assert start['facts']['audio'] == dict(codec='aac', channels=2, language='jpn')
    assert start['facts']['subtitle'] == dict(language='zho', name='简体', forced=False, impaired=True)
    text = media_facts_text(value)
    assert '启动时选中音轨：aac · 2 声道 · jpn' in text and '启动时选中字幕：zho · 简体' in text
    assert '不是永久选择' in text and '不证明字幕内嵌' in text
    for field in ('分辨率', '编码', 'HDR'):
        assert field + '：未知' in text
    assert path.read_bytes() == raw and list(scene.index.db.iterdump()) == before
    assert scene.index.db.execute('PRAGMA user_version').fetchone()[0] == 4


@pytest.mark.parametrize('key,value', [('native_instance', str(uuid4())), ('request_id', 'f' * 32),
    ('file_identity', 'different'), ('sequence', 3), ('user_intent', 1), ('audio_intent', 1),
    ('subtitle_intent', 1), ('open_epoch', 4), ('phase', 'OPEN')])
def test_different_receipt_is_not_start_evidence(scene, key, value):
    scene.raw['receipt'][key] = value
    scene.data['_file_start_observation'] = {'stale': True}
    assert not capture(scene) and '_file_start_observation' not in scene.data
    assert scene.files.save(scene.data)
    assert scene.files.get(scene.file['id'])['version'] == 1


@pytest.mark.parametrize('change', ['selection_epoch', 'protocol', 'status', 'instance', 'owner', 'identity', 'standard', 'no_binding'])
def test_start_capture_cannot_upgrade_unknown_or_unowned_playback(scene, change):
    binding, instance = scene.binding, scene.row['native_instance']
    if change == 'selection_epoch': scene.raw['selection_epoch'] += 1
    if change == 'protocol': scene.raw.pop('control_protocol')
    if change == 'status': scene.raw['status'] = 'CATALOG_LIMIT'
    if change == 'instance': instance = str(uuid4())
    if change == 'owner': scene.owner['epoch'] += 1; scene.client.call = lambda *a, **kw: playback_presentation.project(scene.raw, 'a'*32, 2, scene.row)
    if change == 'identity': scene.owner['file_identity'] += 'changed'
    if change == 'standard': scene.data['selection_policy'] = 'standard'
    if change == 'no_binding': binding = None
    assert not submission.capture_start(scene.data, scene.client, scene.owner, instance, binding)
    assert '_file_start_observation' not in scene.data


@pytest.mark.parametrize('kind', ['codec', 'channels', 'language', 'flags', 'name', 'duplicate', 'too_many', 'active'])
def test_bad_optional_metadata_does_not_disable_control_or_become_facts(scene, kind):
    if kind == 'codec': scene.raw['audio_streams'][0]['codec'] = 'https://secret'
    if kind == 'channels': scene.raw['audio_streams'][0]['channels'] = True
    if kind == 'language': scene.raw['audio_streams'][0]['language'] = 'x' * 33
    if kind == 'flags': scene.raw['streams'][0]['isforced'] = 1
    if kind == 'name': scene.raw['streams'][0]['name'] = 'secret\nheader'
    if kind == 'duplicate': scene.raw['audio_streams'].append(dict(scene.raw['audio_streams'][0], stream_key='f'*64))
    if kind == 'too_many': scene.raw['audio_streams'] = [dict(scene.raw['audio_streams'][0], index=i, stream_key='%064x' % i) for i in range(65)]
    if kind == 'active': scene.raw['audio_index'] = 7
    view = scene.client.call({})
    assert view['available'] and 'start_facts' not in view
    assert not capture(scene)


def test_missing_metadata_and_no_selected_track_are_unknown_not_another_tracks_facts(scene):
    scene.raw['audio_streams'][0].update(codec='', channels=0, language='')
    scene.raw['streams'][0].pop('isforced')
    scene.raw['streams'][0].pop('isimpaired')
    assert capture(scene)
    facts = scene.data['_file_start_observation']['facts']
    assert facts['audio'] == dict(codec=None, channels=None, language=None)
    assert facts['subtitle']['forced'] is None and facts['subtitle']['impaired'] is None
    scene.raw.update(audio_index=-1, current_index=-1)
    assert capture(scene)
    facts = scene.data['_file_start_observation']['facts']
    assert facts['audio'] is None and facts['subtitle'] is None
    assert facts['audio_count'] == facts['subtitle_count'] == 1


def test_v1_reopen_and_start_without_duration_remain_supported(scene):
    assert scene.files.save(scene.data)
    assert scene.files.get(scene.file['id'])['version'] == 1
    scene.data.update(_file_history=scene.files.begin(scene.file), current_time=0, total_time=None)
    assert capture(scene) and scene.files.save(scene.data)
    value = card(scene)
    assert value['media_facts']['duration_seconds'] is None
    assert '时长：未知' in media_facts_text(value) and '启动时选中音轨：aac' in media_facts_text(value)


def test_terminal_retains_start_timestamp_but_later_unknown_session_clears_it(scene):
    assert capture(scene) and scene.files.save(scene.data)
    observed = deepcopy(scene.data['_file_start_observation'])
    terminal = submission.snapshot(scene.data, 'NATURAL_EOF')
    terminal.update(current_time=100, total_time=100)
    assert scene.files.save(terminal)
    assert stored_facts(scene)['observation'] == observed and not scene.files.rows()
    scene.data['_file_history'] = scene.files.begin(scene.file)
    scene.raw.pop('control_protocol')
    assert not capture(scene)
    assert scene.files.save(scene.data)
    assert scene.files.get(scene.file['id'])['version'] == 1
    assert 'playback_start' not in card(scene)['media_facts']


def test_old_generation_or_sequence_never_writes_fact_beside_rejected_report(scene):
    assert capture(scene) and scene.files.save(scene.data)
    old = deepcopy(scene.data)
    writer = history.FileHistory(scene.storage.PickleDatabase(profile_root=Path(scene.db._database_path).parent))
    scene.data['_file_history'] = writer.begin(scene.file)
    scene.data['_file_history_sequence'] = 2
    scene.raw['audio_streams'][0].update(codec='flac', channels=6)
    assert capture(scene) and writer.save(scene.data)
    accepted = writer.get(scene.file['id'])
    accepted_facts = stored_facts(scene)
    old['_file_history_sequence'] = 999
    assert scene.files.save(old) is True  # Commit success is not report acceptance.
    late = deepcopy(scene.data)
    late['_file_history_sequence'] = 1
    late['_file_start_observation']['facts']['audio']['codec'] = 'old-codec'
    assert scene.files.save(late) is True
    assert writer.get(scene.file['id']) == accepted
    assert stored_facts(scene) == accepted_facts
    assert accepted_facts['observation']['facts']['audio']['codec'] == 'flac'


@pytest.mark.parametrize('field', ['size', 'name', 'parent', 'fingerprint'])
def test_replacement_reservation_retains_old_evidence_but_new_report_never_inherits(scene, field):
    if field == 'fingerprint':
        scene.file = ref(expected=scope(provider='115'))
        scene.context = scene.files.begin(scene.file)
        scene.data['_file_history'] = scene.context
        scene.owner['file_identity'] = 'transport:' + digest(locator(scene.file)) + '|transport:' + digest(scene.data['url'])
        scene.row['file_identity'] = scene.raw['receipt']['file_identity'] = scene.owner['file_identity']
    assert capture(scene) and scene.files.save(scene.data)
    old = scene.files.get(scene.file['id'])
    old_facts = stored_facts(scene)
    replacement = dict(scene.file, **{field: ({'kind': '115_sha1', 'value': 'f'*40} if field == 'fingerprint'
                           else scene.file['size'] + 1 if field == 'size' else 'changed')})
    insert(scene.index, [replacement], expected=scope(provider=replacement['provider']))
    evidence = scene.files.media_facts([replacement])[replacement['id']]
    from bobbi_core.file_media_facts import checked
    value = dict(media_facts=checked(evidence, opaque(replacement)), observation_key=opaque(replacement))
    assert value['media_facts']['state'] == 'verification_required'
    assert '音轨：未知' in media_facts_text(value) and '启动时选中音轨：aac' not in media_facts_text(value)
    next_context = scene.files.begin(replacement)
    saved = scene.files.get(scene.file['id'])
    assert saved['file_ref'] == old['file_ref'] and saved['position'] == old['position']
    assert stored_facts(scene) == old_facts  # Retained, not re-bound or published.
    assert 'playback_start' not in scene.files.media_facts([replacement])[replacement['id']]
    new = dict(playback(next_context), request_id=scene.data['request_id'], _file_start_observation=old_facts['observation'])
    assert scene.files.save(new)
    assert scene.files.get(scene.file['id'])['version'] == 1
    assert scene.file['id'] not in scene.db.get_key_checked(history.FACTS_KEY)


@pytest.mark.parametrize('change', ['context', 'request', 'secret', 'extra_video', 'timestamp'])
def test_invalid_start_payload_is_not_serialized_or_inherited(scene, change):
    assert capture(scene) and scene.files.save(scene.data)
    scene.data['_file_history_sequence'] += 1
    observed = scene.data['_file_start_observation']
    if change == 'context': observed['session_id'] = 'f' * 32
    if change == 'request': observed['expected']['request_id'] = 'f' * 32
    if change == 'secret': observed['token'] = 'SECRET'
    if change == 'extra_video': observed['facts']['video'] = {'codec': 'hevc'}
    if change == 'timestamp': observed['recorded_at'] = float('nan')
    assert scene.files.save(scene.data)
    assert scene.files.get(scene.file['id'])['version'] == 1
    assert b'SECRET' not in Path(scene.db._database_path).read_bytes()


def test_failed_commit_preserves_progress_and_facts_together(scene, monkeypatch):
    assert capture(scene) and scene.files.save(scene.data)
    before = Path(scene.db._database_path).read_bytes()
    scene.data['_file_history_sequence'] += 1
    scene.raw['audio_streams'][0]['codec'] = 'flac'
    assert capture(scene)
    monkeypatch.setattr(scene.storage, '_atomic_save', lambda *a: (_ for _ in ()).throw(OSError('full')))
    assert scene.files.save(scene.data) is False
    assert Path(scene.db._database_path).read_bytes() == before


@pytest.mark.parametrize('when', ['before', 'inflight'])
def test_profile_revoked_capture_never_publishes_or_revives_after_aba(scene, when):
    assert capture(scene)
    original = scene.client.call
    def call(*a, **kw):
        view = original(*a, **kw)
        scene.current[0] = 'B'
        return view
    if when == 'inflight': scene.client.call = call
    else: scene.current[0] = 'B'
    assert not capture(scene) and '_file_start_observation' not in scene.data
    scene.current[0] = 'A'
    assert not capture(scene)


def test_bound_existing_queue_drains_a_only_and_rejects_new_revoked_admission(scene, monkeypatch):
    subject = module('start_facts_deferred', 'addons/plugin.video.bobbi/lib/db/deferred_history.py')
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', scene.storage)
    monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(
        set_watched_file=lambda data, database: history.FileHistory(database).save(data)))
    queued = []
    class Thread:
        def __init__(self, target, args, **kw): self.target, self.args = target, args
        def start(self): queued.append(self)
    monkeypatch.setattr(subject, 'Thread', Thread)
    assert capture(scene)
    assert subject.defer_watched_file(scene.data, profile_binding=scene.binding)
    scene.current[0] = 'B'
    thread = queued.pop()
    thread.target(*thread.args)
    assert scene.files.get(scene.file['id'])['version'] == 1
    assert stored_facts(scene)['observation']['facts']['audio']['codec'] == 'aac'
    assert not (scene.root / 'B/plugin.video.bobbi/database.pickle').exists()
    assert not subject.defer_watched_file(scene.data, profile_binding=scene.binding)
    scene.current[0] = 'A'
    assert not subject.defer_watched_file(scene.data, profile_binding=scene.binding)
    assert not queued and subject._lane.acquire(blocking=False)
    subject._lane.release()


def test_same_file_other_profile_has_independent_facts(scene):
    assert capture(scene) and scene.files.save(scene.data)
    scene.current[0] = 'B'
    scene.binding = ProfileBinding(lambda addon: scene.root / scene.current[0] / addon)
    other = history.FileHistory(scene.storage.PickleDatabase(profile_root=scene.binding.root('plugin.video.bobbi')))
    scene.data['_file_history'] = other.begin(scene.file)
    scene.raw['audio_streams'][0]['codec'] = 'flac'
    assert capture(scene) and other.save(scene.data)
    assert other.media_facts([scene.file])[scene.file['id']]['playback_start']['facts']['audio']['codec'] == 'flac'
    assert stored_facts(scene)['observation']['facts']['audio']['codec'] == 'aac'


def test_standard_session_strips_inherited_native_evidence_before_its_existing_history_save(scene):
    from bobbi_platform.standard_session import StandardSession
    assert capture(scene)
    scene.data.update(ids={}, mode='file', title='My file')
    reports = []
    accounts = SimpleNamespace(require_current=lambda *a, **kw: None, is_current=lambda *a: True)
    session = StandardSession(accounts, history=reports.append)
    request = scene.data['request_id']
    session.select(request, scope())
    assert session.register(request, scene.data)['accepted']
    session.observe(request, scene.data['url'], 20, 100)
    session.terminal(request, 'STOP')
    assert reports and all('_file_start_observation' not in report for report in reports)
    for report in reports:
        assert scene.files.save(report)
    assert scene.files.get(scene.file['id'])['version'] == 1


@pytest.mark.parametrize('provider', ['plex', 'jellyfin', 'emby'])
def test_server_candidate_cannot_become_original_file_or_actual_transcode_facts(scene, provider):
    from bobbi_core.file_ref import from_selected
    from bobbi_core.server_ref import file_id
    server = from_selected(scope(provider=provider), dict(directory=False, server_id='server',
        file_id=file_id('entry', 'media', 'part'), name='File.mkv', size=1024), 'parent')
    scene.data['_file_history'] = scene.files.begin(server)
    scene.owner['file_identity'] = 'transport:' + digest(locator(server)) + '|transport:' + digest(scene.data['url'])
    scene.data['prepared_media_profile'] = {'video': {'codec': 'hevc', 'height': 2160}}
    scene.data['server_candidate'] = {'transcode': True, 'codec': 'aac'}
    assert not capture(scene) and not scene.calls
    assert scene.files.save(scene.data)
    assert scene.files.get(server['id'])['version'] == 1


def test_bounded_many_file_pages_take_one_history_snapshot_and_never_write(scene, monkeypatch):
    files = [ref(n, name='片'*150 + '.mkv') for n in range(32)]
    insert(scene.index, files[:20])
    insert(scene.index, files[20:], source='f'*32)
    for file in files:
        scene.data['_file_history'] = scene.files.begin(file)
        scene.owner['file_identity'] = 'transport:' + digest(locator(file)) + '|transport:' + digest(scene.data['url'])
        scene.row['file_identity'] = scene.raw['receipt']['file_identity'] = scene.owner['file_identity']
        assert capture(scene) and scene.files.save(scene.data)
    before = Path(scene.db._database_path).read_bytes()
    reads, original = [], scene.db.get_keys_checked
    def read(key): reads.append(key); return original(key)
    monkeypatch.setattr(scene.db, 'get_keys_checked', read)
    cursor, seen = None, []
    while True:
        count = len(reads)
        page = scene.index.query(scope(), query={'view': 'files'}, limit=32, cursor=cursor)
        assert len(reads) == count + 1 and len(wire(page)) <= 15000
        seen.extend(row['entity_id'] for row in page['items'])
        cursor = page['next_cursor']
        if cursor is None: break
    assert len(seen) == len(set(seen)) == 32
    assert Path(scene.db._database_path).read_bytes() == before
    with pytest.raises(ValueError): scene.files.media_facts(files + [ref(99)])


def test_actual_native_start_history_hook_captures_once_after_owned_av_and_reuses_writer(scene, monkeypatch):
    source = ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'
    cls = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(node, ast.ClassDef))
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_record_started_history')
    env = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), env)
    monkeypatch.setitem(sys.modules, 'lib.services.playback_history', submission)
    writes = []
    actor = SimpleNamespace(_cinema_history_pending=True, data=scene.data, playback_client=scene.client,
        _owner_context=scene.owner, _native_instance=scene.row['native_instance'], _file_history_binding=scene.binding,
        _owns_playback_session=lambda: True, _matches_requested_playback=lambda: True,
        _cinema_phase=lambda value: None, mark_watched=lambda data: writes.append(deepcopy(data)))
    env['_record_started_history'](actor)
    env['_record_started_history'](actor)
    assert len(writes) == len(scene.calls) == 1 and '_file_start_observation' in writes[0]
    actor._cinema_history_pending = True
    actor._matches_requested_playback = lambda: False
    env['_record_started_history'](actor)
    assert len(writes) == 1


@pytest.fixture
def legacy():
    """Actual frozen pre-slice code, not an approximation of a legacy writer."""
    modules = []
    for name in ('pickle_db', 'file_history'):
        source = source_bytes('319e3987f3a196ac9d5e214a82fcdf1ceed2a9c2', 'addons/plugin.video.bobbi/lib/db/' + name + '.py')
        subject = ModuleType('legacy_start_facts_' + name)
        exec(compile(source, '<frozen-v1-' + name + '>', 'exec'), subject.__dict__)
        modules.append(subject)
    return modules


def test_actual_old_reader_and_writer_roundtrip_preserves_v1_and_revokes_obsolete_facts(scene, legacy):
    assert capture(scene) and scene.files.save(scene.data)
    observed = stored_facts(scene)
    old_storage, old_history = legacy
    old_db = old_storage.PickleDatabase(profile_root=Path(scene.db._database_path).parent)
    old = old_history.FileHistory(old_db)
    assert old.get(scene.file['id']) == scene.files.get(scene.file['id'])
    assert old.rows()[0]['position'] == 97
    context = old.begin(scene.file)
    assert old.get(scene.file['id'])['position'] == 97  # Reservation preserves progress.
    assert old_db.get_key_checked(history.FACTS_KEY)[scene.file['id']] == observed
    assert 'playback_start' not in scene.files.media_facts([scene.file])[scene.file['id']]
    assert old.save(playback(context, sequence=3, position=10))
    assert scene.files.get(scene.file['id'])['position'] == 10
    assert 'playback_start' not in scene.files.media_facts([scene.file])[scene.file['id']]
    # Upgrading again captures fresh evidence; it never silently restores old facts.
    scene.data['_file_history'] = scene.files.begin(scene.file)
    scene.raw['audio_streams'][0]['codec'] = 'flac'
    assert capture(scene) and scene.files.save(scene.data)
    assert stored_facts(scene)['observation']['facts']['audio']['codec'] == 'flac'
    assert old.get(scene.file['id']) == scene.files.get(scene.file['id'])
    assert old.save(playback(context, sequence=999, position=80))  # Ignored old generation.
    assert stored_facts(scene)['observation']['facts']['audio']['codec'] == 'flac'


def test_actual_old_writer_in_same_generation_invalidates_sequence_bound_facts(scene, legacy):
    assert capture(scene) and scene.files.save(scene.data)
    old_storage, old_history = legacy
    old = old_history.FileHistory(old_storage.PickleDatabase(profile_root=Path(scene.db._database_path).parent))
    assert old.save(playback(scene.context, sequence=2, position=11))
    assert scene.file['id'] in scene.db.get_key_checked(history.FACTS_KEY)  # Old code preserves unknown namespaces.
    assert 'playback_start' not in scene.files.media_facts([scene.file])[scene.file['id']]


@pytest.mark.parametrize('operation', ['remove', 'delete', 'clear', 'evict', 'old_orphan'])
def test_deletion_and_history_eviction_own_dependent_fact_retention(scene, monkeypatch, legacy, operation):
    assert capture(scene) and scene.files.save(scene.data)
    row = scene.files.get(scene.file['id'])
    if operation == 'remove':
        assert scene.files.remove(scene.file['id'], dict(row, position=0)) is False
        assert stored_facts(scene)
        assert scene.files.remove(scene.file['id'], row)
    elif operation == 'delete':
        assert scene.db.delete_item(history.KEY, scene.file['id'])
    elif operation == 'clear':
        assert scene.db.set_key(history.KEY, {})
    else:
        if operation == 'old_orphan':
            old_storage, old_history = legacy
            old_db = old_storage.PickleDatabase(profile_root=Path(scene.db._database_path).parent)
            assert old_db.delete_item(history.KEY, scene.file['id'])
            assert scene.file['id'] in scene.db.get_key_checked(history.FACTS_KEY)
        monkeypatch.setattr(history, 'LIMIT', 1)
        assert scene.files.begin(ref(2))
    assert scene.file['id'] not in (scene.db.get_key_checked(history.FACTS_KEY) or {})
    assert not scene.files.media_facts([scene.file])


def test_report_and_facts_commit_once_and_missing_facts_revoke_on_accepted_report(scene, monkeypatch):
    assert capture(scene)
    saves, original = [], scene.storage._atomic_save
    def save(path, data): saves.append(deepcopy(data)); return original(path, data)
    monkeypatch.setattr(scene.storage, '_atomic_save', save)
    assert scene.files.save(scene.data)
    assert len(saves) == 1
    assert scene.file['id'] in saves[0][history.KEY] and scene.file['id'] in saves[0][history.FACTS_KEY]
    scene.data.pop('_file_start_observation')
    scene.data['_file_history_sequence'] += 1
    assert scene.files.save(scene.data)
    assert len(saves) == 2 and scene.file['id'] not in saves[1][history.FACTS_KEY]
    assert 'playback_start' not in card(scene)['media_facts']


@pytest.mark.parametrize('field', ['file_ref', 'generation', 'session_id', 'sequence'])
def test_dependent_binding_must_match_the_same_full_history_snapshot(scene, field):
    assert capture(scene) and scene.files.save(scene.data)
    entry = stored_facts(scene)
    binding = entry['binding']
    binding[field] = (dict(binding[field], name='Other.mkv') if field == 'file_ref' else
                      'f'*32 if field == 'session_id' else binding[field] + 1)
    scene.db.set_item(history.FACTS_KEY, scene.file['id'], entry)
    before = Path(scene.db._database_path).read_bytes()
    assert 'playback_start' not in card(scene)['media_facts']
    assert Path(scene.db._database_path).read_bytes() == before


@pytest.mark.parametrize('field', ['generation', 'sequence', 'file_ref_version'])
def test_dependent_binding_rejects_boolean_alias_for_integer_identity(scene, field):
    assert capture(scene) and scene.files.save(scene.data)
    entry = stored_facts(scene)
    if field == 'file_ref_version': entry['binding']['file_ref']['version'] = True
    else: entry['binding'][field] = True
    scene.db.set_item(history.FACTS_KEY, scene.file['id'], entry)
    assert 'playback_start' not in card(scene)['media_facts']

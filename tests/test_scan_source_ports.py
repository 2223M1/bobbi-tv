"""Real filesystem/SQLite/owner slice with synthetic kernel mount evidence.

No live CD2 account or device is used; capability remains not_device_verified.
"""
from copy import deepcopy
import importlib.util
import io
import os
from pathlib import Path
import sys
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import mounted_ref
from bobbi_core.file_ref import PROVIDERS
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.scan_sources import MountedPort
from test_catalog_service import Pans
from test_media_library_index import scope, ref
from test_library_plugin import plugin


@pytest.fixture
def cd2(tmp_path):
    media = tmp_path / 'CD2'
    media.mkdir()
    (media / 'Movie.mkv').write_bytes(b'original video bytes')
    (media / 'Season 0').mkdir()
    (media / 'Season 0' / 'Show.S00E01.mkv').write_bytes(b'special episode')
    registry = Registry(tmp_path / 'libraries.sqlite3')
    source = vfs_source('Existing CD2', media.as_posix())
    registry.save(source)
    registry.close()
    mounts = [dict(path=media.as_posix(), generation='a' * 64)]
    service = CatalogService(tmp_path, Pans(scope(), lambda *args: pytest.fail('No native-pan login or request')))
    service.mounted.port = MountedPort(tmp_path, mounts=lambda: deepcopy(mounts))
    yield service, source, media, mounts
    service.close()


def scan(cd2):
    service, source, media, mounts = cd2
    task = service.dispatch('catalog_mount_scan', dict(source_id=source.id))['task_id']
    service.worker.join(5)
    assert not service.worker.is_alive()
    return service.dispatch('catalog_mount_jobs', dict(source_id=source.id, task=task))['items'][0]


def query(cd2, **kwargs):
    service, source, media, mounts = cd2
    return service.dispatch('catalog_mount_query', dict(source_id=source.id, **kwargs))


def movie(cd2):
    return next(row for row in query(cd2, query=dict(view='files'))['items'] if row['display_title'] == 'Movie.mkv')


def prepare(cd2, object_id=None, request=None):
    service, source, media, mounts = cd2
    return service.dispatch('catalog_mount_prepare', dict(source_id=source.id, object_id=object_id or movie(cd2)['entity_id'],
        request_id=request or uuid4().hex, intent='play'))


@pytest.fixture(params=['native', 'standard'])
def mounted_ui(cd2, plugin, monkeypatch, request):
    """Real owner state/select commands; only Kodi and mount evidence are fake."""
    from bobbi_core.playback_owner import PlaybackOwner
    from bobbi_platform.standard_session import StandardSession
    from bobbi_platform import library_ui
    root = Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi'
    monkeypatch.syspath_prepend(str(root))
    def load(name, relative):
        spec = importlib.util.spec_from_file_location(name, root / relative)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setitem(sys.modules, name, module)
        return module
    catalog = load('lib.utils.views.personal_catalog', 'lib/utils/views/personal_catalog.py')
    playback = load('mounted_playback_test', 'lib/pan_playback.py')
    service = cd2[0]
    state = SimpleNamespace(plugin=plugin, adapter=request.param, calls=[], cancelled=False,
        closed=0, after_action=None, catalog=catalog, playback=playback, confirmed=True,
        account=dict(account_id='', epoch=0, authenticated=False))
    def require(account, authenticated=False):
        assert authenticated is False  # Mounted playback never requires login.
        if account != state.account:
            raise ValueError('ACCOUNT_CHANGED')
    state.owner = (PlaybackOwner() if state.adapter == 'native' else StandardSession(
        SimpleNamespace(require_current=require, is_current=lambda value: value == state.account)))
    def dispatch(action, body, **kwargs):
        state.calls.append((action, deepcopy(body)))
        if action == 'pan_status':
            return dict(providers=[])
        if action == 'account_status':
            return deepcopy(state.account)
        if action == 'playback':
            if state.adapter == 'standard':
                return state.owner.dispatch(body)
            operation = body['operation']
            if operation == 'snapshot':
                return state.owner.snapshot()
            args = (body['boot_id'], body['epoch'], body['request_id'])
            if operation == 'select':
                return state.owner.select(*args, body['selection_identity'])
            if operation == 'cancel':
                return dict(cancelled=state.owner.cancel(*args))
            pytest.fail('Mounted UI must not bind/claim/start native playback: ' + operation)
        result = service.dispatch(action, body)
        if state.after_action:
            state.after_action(action, body)
        return result
    def select_other(identifier):
        body = dict(operation='select', request_id=identifier)
        if state.adapter == 'native':
            snapshot = state.owner.snapshot()
            body.update(boot_id=snapshot['boot_id'], epoch=snapshot['epoch'], selection_identity='transport:other')
        else:
            body['account'] = deepcopy(state.account)
        return dispatch('playback', body)
    state.select_other = select_other
    state.dispatch = dispatch
    monkeypatch.setattr(playback, 'call', dispatch)
    state.play = lambda identifier: playback.mounted(dict(source=cd2[1].id, object_id=identifier), handle=17)
    original_dialog = sys.modules['xbmcgui'].Dialog
    monkeypatch.setattr(sys.modules['xbmcgui'], 'Dialog', lambda: SimpleNamespace(
        ok=original_dialog().ok, yesno=lambda *args: state.confirmed))
    monkeypatch.setattr(library_ui, 'registry', lambda _: Registry(service.root / 'libraries.sqlite3'))
    monkeypatch.setattr(sys.modules['xbmcgui'], 'DialogProgress', lambda: SimpleNamespace(
        create=lambda *args: None, iscanceled=lambda: state.cancelled,
        close=lambda: setattr(state, 'closed', state.closed + 1)), raising=False)
    yield state
    if state.adapter == 'standard':
        state.owner.close()


def test_real_list_index_query_recheck_original_handoff_identity(cd2):
    service, source, media, mounts = cd2
    assert scan(cd2)['state'] == 'completed'
    assert service.index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 0
    assert service.index.db.execute('SELECT count(*) FROM typed_objects').fetchone()[0] == 2
    assert len(query(cd2)['items']) == 2
    selected = movie(cd2)
    ticket = prepare(cd2, selected['entity_id'])['ticket']
    claimed = service.dispatch('catalog_mount_claim', dict(ticket=ticket))
    assert claimed['source_id'] == source.id and claimed['relative'] == 'Movie.mkv'
    assert claimed['resume_supported'] is False and len(claimed['identity']) == 64
    assert service.dispatch('catalog_mount_verify', dict(source_id=source.id,
        object_id=selected['entity_id'], request_id=ticket)) == dict(valid=True)
    with pytest.raises(ValueError, match='PLAY_EXPIRED'):
        service.dispatch('catalog_mount_claim', dict(ticket=ticket))
    assert '115' not in PROVIDERS and 'mounted_path' not in PROVIDERS
    assert ref()['provider'] == 'quark'  # Native v1 identity contract remains.


def test_rename_root_change_and_remount_never_inherit_reference_or_cursor(cd2):
    service, source, media, mounts = cd2
    scan(cd2)
    first = query(cd2, limit=1)
    old = movie(cd2)['entity_id']
    authority = service.mounted.authority(source.id)
    reference = service.index.trusted_mounted_file(authority, old)
    (media / 'Movie.mkv').rename(media / 'Renamed.mkv')
    with pytest.raises((ValueError, OSError)):
        prepare(cd2, old)
    scan(cd2)
    new = next(row for row in query(cd2, query=dict(view='files'))['items'] if row['display_title'] == 'Renamed.mkv')
    assert new['entity_id'] != old
    mounts[0]['generation'] = 'b' * 64
    assert query(cd2)['items']  # Descriptions survive; observations grant no permit.
    assert all(row['availability'] == 'unverified' for row in query(cd2)['items'])
    with pytest.raises(ValueError, match='CURSOR_STALE'):
        query(cd2, cursor=first['next_cursor'], limit=1)
    with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
        service.mounted.port.stat_by_reference(authority, reference)
    assert scan(cd2)['state'] == 'completed'
    assert query(cd2)['items']


def test_same_name_same_size_replacement_does_not_validate_old_observation(cd2):
    service, source, media, mounts = cd2
    scan(cd2)
    selected = movie(cd2)['entity_id']
    original = media / 'Movie.mkv'
    before = original.stat()
    replacement = media / 'replacement.tmp'
    replacement.write_bytes(b'x' * before.st_size)
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    replacement.replace(original)
    with pytest.raises(ValueError, match='FILE_CHANGED'):
        prepare(cd2, selected)
    assert not service.mounted.tickets


def test_mounted_path_validation_does_not_extend_native_fileref(cd2):
    service, source, media, mounts = cd2
    scan(cd2)
    authority = service.mounted.authority(source.id)
    value = service.index.trusted_mounted_file(authority, movie(cd2)['entity_id'])
    assert value['reference_kind'] == 'mounted_path'
    for relative in ('../private.mkv', '/etc/video.mkv', 'nested/../video.mkv', 'smb://secret/file.mkv', 'bad.strm|exec'):
        with pytest.raises(ValueError):
            mounted_ref.validate(dict(value, relative=relative))
    from bobbi_core.file_ref import validate
    with pytest.raises(ValueError):
        validate(value)


def test_incomplete_offline_cancel_or_symlink_scan_preserves_members(cd2, monkeypatch):
    service, source, media, mounts = cd2
    scan(cd2)
    initial = service.index.db.execute('SELECT count(*) FROM memberships WHERE available=1').fetchone()[0]
    from bobbi_platform.scan_sources import MountedSession
    original = MountedSession.list_page
    def offline(session, parent):
        page = original(session, parent)
        mounts.clear()
        return page
    monkeypatch.setattr(MountedSession, 'list_page', offline)
    service.dispatch('catalog_mount_scan', dict(source_id=source.id))
    service.worker.join(5)
    assert service.index._scan(service.task)['state'] == 'failed'
    assert service.index.db.execute('SELECT count(*) FROM memberships WHERE available=1').fetchone()[0] == initial
    mounts.append(dict(path=media.as_posix(), generation='a' * 64))
    def cancel(session, parent):
        page = original(session, parent)
        session.cancelled.set()
        return page
    monkeypatch.setattr(MountedSession, 'list_page', cancel)
    assert scan(cd2)['state'] == 'canceled'
    assert service.index.db.execute('SELECT count(*) FROM memberships WHERE available=1').fetchone()[0] == initial


def test_single_source_namespace_cannot_be_rebound_to_new_root(cd2):
    service, source, media, mounts = cd2
    scan(cd2)
    old = movie(cd2)['entity_id']
    changed = media / 'another'
    changed.mkdir()
    (changed / 'Movie.mkv').write_bytes(b'original video bytes')
    registry = Registry(service.root / 'libraries.sqlite3')
    registry.save(vfs_source('Rebound', changed.as_posix(), source_id=source.id))
    registry.close()
    assert query(cd2)['items'] == []
    with pytest.raises(ValueError, match='FILE_NOT_FOUND'):
        prepare(cd2, old)
    scan(cd2)
    assert movie(cd2)['entity_id'] != old


def test_bounded_large_directory_recheck_does_not_probe_unlimited_pages(cd2):
    service, source, media, mounts = cd2
    # Creation order is not relied on: inspect the actual directory order and
    # choose a real file beyond the strict 160-entry revalidation budget.
    for i in range(200):
        (media / ('extra-%03d.mkv' % i)).write_bytes(b'video')
    scan(cd2)
    with os.scandir(media) as entries:
        name = [entry.name for entry in entries if entry.is_file()][-1]
    authority = service.mounted.authority(source.id)
    target = mounted_ref.observed(authority, name, (media / name).stat())
    with pytest.raises(ValueError, match='RECHECK_INCOMPLETE'):
        prepare(cd2, target['id'])
    assert not service.mounted.tickets


def test_duplicate_cancel_before_start_and_after_claim_fail_closed(cd2):
    service, source, media, mounts = cd2
    scan(cd2)
    selected = movie(cd2)['entity_id']
    cancelled = uuid4().hex
    service.dispatch('catalog_mount_cancel_play', dict(source_id=source.id, request_id=cancelled))
    with pytest.raises(ValueError, match='CANCELLED'):
        prepare(cd2, selected, cancelled)
    key = uuid4().hex
    assert prepare(cd2, selected, key) == prepare(cd2, selected, key) == dict(ticket=key)
    service.dispatch('catalog_mount_claim', dict(ticket=key))
    assert prepare(cd2, selected, key) == dict(ticket=key) and not service.mounted.tickets
    service.dispatch('catalog_mount_cancel_play', dict(source_id=source.id, request_id=key))
    with pytest.raises(ValueError, match='PLAY_EXPIRED'):
        service.dispatch('catalog_mount_verify', dict(source_id=source.id, object_id=selected, request_id=key))


def test_real_ui_handoff_uses_trusted_selection_and_no_old_path_resume(cd2, mounted_ui):
    service, source, media, mounts = cd2
    scan(cd2)
    plugin = mounted_ui.plugin
    mounted_ui.play(movie(cd2)['entity_id'])
    assert [action for action, body in mounted_ui.calls if action.startswith('catalog_')] == [
        'catalog_mount_scope', 'catalog_mount_prepare', 'catalog_mount_claim', 'catalog_mount_verify']
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is True
    assert Path(plugin.resolved[0][2].path) == media / 'Movie.mkv'
    assert plugin.resolved[0][2].properties['StartOffset'] == '0'


@pytest.mark.parametrize('change', ['new_selection', 'replacement', 'remount'])
def test_ui_late_change_never_hands_off_old_file(cd2, mounted_ui, change):
    service, source, media, mounts = cd2
    scan(cd2)
    plugin = mounted_ui.plugin
    def changed():
        if change == 'new_selection':
            plugin.props['bobbi.portable_selection'] = 'newer'
        elif change == 'replacement':
            (media / 'Movie.mkv').write_bytes(b'replaced')
        else:
            mounts[0]['generation'] = 'f' * 64
    plugin.on_make = changed
    mounted_ui.play(movie(cd2)['entity_id'])
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is False
    assert not service.mounted.tickets


@pytest.mark.parametrize('phase', ['catalog_mount_prepare', 'catalog_mount_verify'])
def test_real_other_entry_select_revokes_late_mounted_handoff(cd2, mounted_ui, phase):
    service, source, media, mounts = cd2
    scan(cd2)
    plugin, newer = mounted_ui.plugin, '9' * 32
    def replace(action, body):
        if action == phase:
            mounted_ui.select_other(newer)  # Same real select operation used by pan/native entry.
    mounted_ui.after_action = replace
    mounted_ui.play(movie(cd2)['entity_id'])
    assert len(plugin.resolved) == 1 and plugin.resolved[0][1] is False
    snapshot = mounted_ui.dispatch('playback', dict(operation='snapshot'))
    assert snapshot['desired']['request_id'] == newer and not snapshot['desired']['cancelled']
    assert not service.mounted.tickets and not service.mounted.claims


def test_mounted_selection_revokes_older_pending_entry_without_native_claim(cd2, mounted_ui):
    service, source, media, mounts = cd2
    scan(cd2)
    previous = mounted_ui.select_other('8' * 32)
    mounted_ui.play(movie(cd2)['entity_id'])
    assert mounted_ui.plugin.resolved[0][1] is True
    if mounted_ui.adapter == 'native':
        assert not mounted_ui.owner.bind_file(previous['boot_id'], previous['epoch'], '8' * 32,
            'transport:other', 'late-file')
        assert not mounted_ui.owner.desired['start_claimed']
        assert mounted_ui.owner.observed is None  # Standard handoff is not a native receipt.
    else:
        assert not mounted_ui.owner.register('8' * 32, dict(request_id='8' * 32,
            _account=mounted_ui.account, url='https://example.test/late.mkv'))['accepted']


@pytest.mark.parametrize('phase', ['catalog_mount_prepare', 'catalog_mount_claim', 'catalog_mount_verify'])
def test_cancel_progress_before_late_result_never_opens(cd2, mounted_ui, phase):
    service, source, media, mounts = cd2
    scan(cd2)
    started, release, completed = Event(), Event(), Event()
    def delayed(action, body):
        if action == phase:
            started.set()
            assert release.wait(3)
            completed.set()
    mounted_ui.after_action = delayed
    thread = Thread(target=mounted_ui.play, args=(movie(cd2)['entity_id'],))
    thread.start()
    try:
        assert started.wait(3)
        mounted_ui.cancelled = True
        thread.join(3)
        assert not thread.is_alive() and mounted_ui.closed == 1
        assert not any(row[1] for row in mounted_ui.plugin.resolved)
        assert not service.mounted.tickets and not service.mounted.claims
        snapshot = mounted_ui.dispatch('playback', dict(operation='snapshot'))
        assert snapshot['desired']['cancelled']
    finally:
        release.set()
        thread.join(3)
    assert completed.wait(3)
    assert not any(row[1] for row in mounted_ui.plugin.resolved)
    assert [action for action, _ in mounted_ui.calls].count('catalog_mount_cancel_play') == 1


def test_unknown_selection_reply_is_never_reselected_and_only_own_intent_is_cancelled(cd2, mounted_ui, monkeypatch):
    service, source, media, mounts = cd2
    scan(cd2)
    def dropped(action, body, **kwargs):
        result = mounted_ui.dispatch(action, body, **kwargs)
        if action == 'playback' and body['operation'] == 'select':
            raise RuntimeError('lost select acknowledgement')
        return result
    monkeypatch.setattr(mounted_ui.playback, 'call', dropped)
    mounted_ui.play(movie(cd2)['entity_id'])
    assert not any(row[1] for row in mounted_ui.plugin.resolved)
    assert len([body for action, body in mounted_ui.calls
                if action == 'playback' and body['operation'] == 'select']) == 1
    snapshot = mounted_ui.dispatch('playback', dict(operation='snapshot'))
    assert snapshot['desired']['cancelled']


def test_kernel_mount_snapshot_binds_boot_id_and_mount_id(monkeypatch):
    from bobbi_platform import scan_sources
    state = dict(boot='12345678-1234-1234-1234-123456789abc', mount=42)
    original = Path.open
    def opened(path, *args, **kwargs):
        if str(path).replace('\\', '/') == '/proc/self/mountinfo':
            return io.StringIO('%d 1 0:43 / /media/CloudDrive rw - fuse.clouddrive cloudfs rw\n'
                              '44 1 8:1 / /ordinary rw - ext4 /dev/sda rw\n' % state['mount'])
        if str(path).replace('\\', '/') == '/proc/sys/kernel/random/boot_id':
            return io.StringIO(state['boot'])
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', opened)
    one = scan_sources.mount_records()
    assert len(one) == 1 and one[0]['path'] == '/media/CloudDrive'
    state['mount'] = 43
    two = scan_sources.mount_records()
    assert two[0]['generation'] != one[0]['generation']
    state['boot'] = 'abcdef12-1234-1234-1234-123456789abc'
    assert scan_sources.mount_records()[0]['generation'] != two[0]['generation']


def test_nonmounted_folder_and_credentials_never_become_cd2_index(cd2):
    service, source, media, mounts = cd2
    mounts.clear()
    assert service.dispatch('catalog_mount_sources', {}) == dict(items=[])
    with pytest.raises(ValueError, match='SOURCE_UNAVAILABLE'):
        service.dispatch('catalog_mount_scan', dict(source_id=source.id))
    assert service.index.db.execute('SELECT count(*) FROM typed_objects').fetchone()[0] == 0


def test_symbolic_link_is_incomplete_not_a_source_escape(cd2):
    service, source, media, mounts = cd2
    scan(cd2)
    initial = service.index.db.execute('SELECT count(*) FROM memberships WHERE available=1').fetchone()[0]
    try:
        (media / 'escape').symlink_to(service.root, target_is_directory=True)
    except OSError:
        pytest.skip('Host does not grant symlink creation; Linux run covers this case')
    result = scan(cd2)
    assert result['state'] == 'failed' and result['result_summary'] == 'CATALOG_SOURCE_UNSUPPORTED'
    assert service.index.db.execute('SELECT count(*) FROM memberships WHERE available=1').fetchone()[0] == initial


def test_utf8_directory_and_filename_uses_existing_local_filesystem_semantics(cd2):
    service, source, media, mounts = cd2
    (media / '特别篇🎬').mkdir()
    (media / '特别篇🎬' / '物语.S00E01.mkv').write_bytes(b'utf8 video')
    scan(cd2)
    file = query(cd2, query=dict(view='files', text='物语'))['items'][0]
    ticket = prepare(cd2, file['entity_id'])['ticket']
    assert service.dispatch('catalog_mount_claim', dict(ticket=ticket))['relative'] == '特别篇🎬/物语.S00E01.mkv'

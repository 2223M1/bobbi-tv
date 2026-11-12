"""Ordinary local directory through real Registry, index, scan, review and play.

Real temporary filesystem, no device/network protocol certification.
"""
from copy import deepcopy
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bobbi_core import local_ref, mounted_ref, typed_ref
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.scan_sources import LocalPort, MountedPort, MountedSession
from test_catalog_service import Pans
from test_media_library_index import scope, command
from test_library_plugin import plugin
from test_scan_source_ports import mounted_ui


@pytest.fixture
def local(tmp_path):
    media = tmp_path / '普通媒体'
    media.mkdir()
    (media / 'Movie.mkv').write_bytes(b'original video')
    (media / '特别篇').mkdir()
    (media / '特别篇' / 'Show.S00E01.mkv').write_bytes(b'special video')
    source = vfs_source('本地已有目录', media.as_posix())
    store = Registry(tmp_path / 'libraries.sqlite3')
    store.save(source)
    store.close()
    service = CatalogService(tmp_path, Pans(scope(), lambda *a: pytest.fail('No cloud account')))
    service.mounted.local_port = LocalPort(tmp_path, mounts=lambda: [])
    service.mounted.port = MountedPort(tmp_path, mounts=lambda: [])
    yield service, source, media, []
    service.close()


@pytest.fixture
def cd2(local):
    # Reuse only existing real playback-owner/Kodi scaffolding, not CD2 evidence.
    return local


def scan(local):
    service, source, _, _ = local
    task = service.dispatch('catalog_local_scan', dict(source_id=source.id))['task_id']
    service.worker.join(5)
    assert not service.worker.is_alive()
    return service.dispatch('catalog_local_jobs', dict(source_id=source.id, task=task))['items'][0]


def files(local):
    service, source, _, _ = local
    return service.dispatch('catalog_local_query', dict(source_id=source.id, query=dict(view='files')))['items']


def prepare(local, object_id=None, intent='play'):
    service, source, _, _ = local
    return service.dispatch('catalog_local_prepare', dict(source_id=source.id,
        object_id=object_id or files(local)[0]['entity_id'], request_id=uuid4().hex, intent=intent))['ticket']


def test_local_register_scan_review_work_version_exact_claim_and_no_cd2_identity(local):
    service, source, _, _ = local
    listed = service.dispatch('catalog_local_sources', {})['items']
    assert len(listed) == 1 and listed[0]['reference_kind'] == 'local_path'
    assert listed[0]['available'] is None and listed[0]['device_verified'] is False
    assert service.dispatch('catalog_mount_sources', {})['items'] == []
    assert scan(local)['state'] == 'completed'
    rows = files(local)
    assert len(rows) == 2
    expected = service.dispatch('catalog_local_scope', dict(source_id=source.id))
    selected = rows[0]['entity_id']
    edit = command(dict(id=selected), title='我的电影')
    preview = service.dispatch('catalog_local_preview', dict(source_id=source.id, commands=[edit]))
    assert preview['items'][0]['status'] == 'ready'
    request = uuid4().hex
    receipt = service.dispatch('catalog_local_apply', dict(source_id=source.id, request_id=request, commands=[edit]))
    assert receipt['items'][0]['status'] == 'applied'
    works = service.dispatch('catalog_local_query', dict(source_id=source.id, query=dict(view='works')))['items']
    work = next(row for row in works if row['display_title'] == '我的电影')
    versions = service.dispatch('catalog_local_query', dict(source_id=source.id,
        query=dict(view='files', parent_entity_id=work['entity_id'])))['items']
    assert [row['entity_id'] for row in versions] == [selected]
    ticket = prepare(local, selected)
    with pytest.raises(ValueError, match='REFERENCE_INVALID'):
        service.dispatch('catalog_mount_claim', dict(ticket=ticket))
    result = service.dispatch('catalog_local_claim', dict(ticket=ticket))
    assert result['object_id'] == selected and result['resume_supported'] is False
    assert service.dispatch('catalog_local_verify', dict(source_id=source.id,
        object_id=selected, request_id=ticket)) == dict(valid=True)
    with pytest.raises(ValueError, match='PLAY_EXPIRED'):
        service.dispatch('catalog_local_claim', dict(ticket=ticket))
    assert service.index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 0
    assert service.index.db.execute('SELECT count(*) FROM typed_objects').fetchone()[0] == 2
    assert typed_ref.scope_key(expected)[0] == 'local_path'


def test_strict_local_reference_cannot_be_cast_to_mount_or_native(local):
    service, source, media, _ = local
    authority = service.mounted.authority(source.id, 'local_path')
    reference = local_ref.observed(authority, 'Movie.mkv', (media / 'Movie.mkv').stat())
    assert typed_ref.validate(reference) == reference
    assert reference['root_signature']['inode'] == media.stat().st_ino
    with pytest.raises(ValueError):
        mounted_ref.validate(reference)
    for patch in (dict(reference_kind='mounted_path'), dict(source_generation=''),
                  dict(root_signature={'inode': 1}), dict(relative='../Movie.mkv'),
                  dict(mount_generation='a' * 64), dict(signature={'device': True})):
        with pytest.raises(ValueError):
            local_ref.validate(dict(reference, **patch))
    assert 'local_path' not in __import__('bobbi_core.file_ref', fromlist=['PROVIDERS']).PROVIDERS


def test_same_name_size_mtime_replacement_fails_old_observation(local):
    scan(local)
    service, source, media, _ = local
    selected = next(row['entity_id'] for row in files(local) if row['display_title'] == 'Movie.mkv')
    old = media / 'Movie.mkv'
    info = old.stat()
    replacement = media / 'replacement.tmp'
    replacement.write_bytes(b'x' * info.st_size)
    os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
    replacement.replace(old)
    with pytest.raises(ValueError, match='FILE_CHANGED'):
        prepare(local, selected)
    assert not service.mounted.tickets


def test_root_object_replacement_revokes_unclaimed_ticket_even_if_child_inode_is_kept(local):
    scan(local)
    service, source, media, _ = local
    ticket = prepare(local)
    original = media.with_name('原目录')
    media.rename(original)
    media.mkdir()
    for child in original.iterdir():
        child.rename(media / child.name)
    with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
        service.dispatch('catalog_local_claim', dict(ticket=ticket))
    with pytest.raises(ValueError, match='FILE_CHANGED'):
        prepare(local)


def test_offline_source_keeps_query_jobs_and_then_reconnects_without_new_identity(local, monkeypatch):
    assert scan(local)['state'] == 'completed'
    service, source, media, _ = local
    before = files(local)
    offline = media.with_name('offline')
    media.rename(offline)
    with monkeypatch.context() as patch:
        patch.setattr(service.mounted.local_port, 'describe', lambda *_: pytest.fail('Read-only listing touched disk'))
        assert files(local) == before
        assert service.dispatch('catalog_local_sources', {})['items']
        assert service.dispatch('catalog_local_jobs', dict(source_id=source.id))['items']
    with pytest.raises(ValueError, match='SOURCE_UNAVAILABLE'):
        prepare(local)
    offline.rename(media)
    ticket = prepare(local)
    assert service.dispatch('catalog_local_claim', dict(ticket=ticket))['object_id'] == before[0]['entity_id']


def test_config_root_change_cannot_borrow_namespace_or_ticket(local):
    scan(local)
    service, source, media, _ = local
    ticket = prepare(local)
    old_scope = service.dispatch('catalog_local_scope', dict(source_id=source.id))
    replacement = media.with_name('另一个来源')
    replacement.mkdir()
    store = Registry(service.root / 'libraries.sqlite3')
    store.save(vfs_source(source.name, replacement.as_posix(), source_id=source.id))
    store.close()
    with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
        service.dispatch('catalog_local_query', dict(source_id=source.id, namespace=old_scope['namespace']))
    with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
        service.dispatch('catalog_local_claim', dict(ticket=ticket))
    assert files(local) == []


def test_local_port_does_not_claim_network_or_current_cd2(local):
    service, source, media, _ = local
    for root in ('smb://nas/Movies/', 'nfs://nas/Movies/', 'davs://nas/Movies/'):
        with pytest.raises(ValueError, match='SOURCE_UNSUPPORTED'):
            LocalPort.source_scope(vfs_source('Network', root))
    with pytest.raises(ValueError, match='SOURCE_UNSUPPORTED'):
        LocalPort.source_snapshot(source, [dict(path=media.as_posix(), generation='a' * 64)])
    with pytest.raises(ValueError, match='SOURCE_UNAVAILABLE'):
        service.mounted.authority(source.id)


def test_interrupted_scan_does_not_mark_unvisited_files_absent(local, monkeypatch):
    scan(local)
    service, _, _, _ = local
    before = [tuple(row) for row in service.index.db.execute('SELECT * FROM memberships')]
    original = MountedSession.list_page
    def cancel(session, parent):
        result = original(session, parent)
        session.cancelled.set()
        return result
    monkeypatch.setattr(MountedSession, 'list_page', cancel)
    assert scan(local)['state'] == 'canceled'
    assert [tuple(row) for row in service.index.db.execute('SELECT * FROM memberships')] == before


def test_local_tv_exact_selection_reuses_resident_owner_and_standard_handoff(local, mounted_ui):
    scan(local)
    service, source, _, _ = local
    chosen = files(local)[0]['entity_id']
    mounted_ui.playback.mounted(dict(reference_kind='local_path', source=source.id, object_id=chosen),
                               handle=17, rpc=mounted_ui.dispatch)
    assert any(action == 'catalog_local_verify' for action, body in mounted_ui.calls)
    assert not any(action.startswith('catalog_mount_') for action, body in mounted_ui.calls)
    assert mounted_ui.plugin.resolved[-1][1] is True

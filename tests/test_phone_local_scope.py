"""Local source -> phone grant -> real Registry/MediaIndex, no cloud fixture."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from bobbi_platform.libraries import Registry, vfs_source
from test_ce2097_phone_management import phone, pair, invoke
from test_local_catalog_source import local, scan


@pytest.fixture
def granted(phone, local):
    service, source, _, _ = local
    assert scan(local)['state'] == 'completed'
    expected = service.dispatch('catalog_local_scope', dict(source_id=source.id))
    state = SimpleNamespace(module=phone.module, expected=expected, calls=[], now=100,
        headers={'Host': '127.0.0.1:8081', 'Origin': 'http://127.0.0.1:8081'})
    def rpc(action, body, **kwargs):
        state.calls.append((action, deepcopy(body)))
        return service.dispatch(action, body)
    state.manager = phone.module.PhoneManagement(expected, 'http://127.0.0.1:8081', rpc=rpc, clock=lambda: state.now)
    state.session, _ = pair(state)
    return state


def test_local_phone_reads_edits_and_recovers_original_review_receipt(granted, local):
    assert granted.session['catalog_kind'] == 'local'
    rows = invoke(granted, 'catalog_query', dict(query={'view': 'files'}))['items']
    assert len(rows) == 2
    command = dict(file_id=rows[0]['entity_id'], expected_revision=0, action='ignore', mapping=None)
    assert invoke(granted, 'catalog_preview', dict(commands=[command]))['items'][0]['status'] == 'ready'
    assert invoke(granted, 'catalog_apply', dict(commands=[command], request_id='d'*32))['items'][0]['status'] == 'applied'
    assert invoke(granted, 'catalog_receipt', dict(request_id='d'*32))['status'] == 'found'
    assert all(action.startswith('catalog_local_') for action, _ in granted.calls)
    assert invoke(granted, 'catalog_sources')['items'][0]['id'] == local[1].id


@pytest.mark.parametrize('action,args', [('catalog_history', {}), ('playback_presentation', {}),
    ('catalog_query', {'query': {'source_id': 'f'*32}}), ('catalog_scan', {'source_id': 'f'*32})])
def test_local_phone_does_not_gain_cloud_playback_or_other_source_authority(granted, action, args):
    with pytest.raises(granted.module.PhoneError, match='ACTION_FORBIDDEN'):
        invoke(granted, action, args)
    assert not any(name.startswith(('pan_', 'playback', 'catalog_mount_')) for name, _ in granted.calls)


@pytest.mark.parametrize('change', ['removed', 'rebound'])
def test_local_registered_scope_change_revokes_phone(granted, local, change):
    service, source, media, _ = local
    registry = Registry(service.root / 'libraries.sqlite3')
    try:
        if change == 'removed':
            registry.remove(source.id)
        else:
            registry.save(vfs_source('New root', (media / 'new-root').as_posix(), source_id=source.id))
    finally:
        registry.close()
    granted.calls.clear()
    with pytest.raises(granted.module.PhoneError, match='ACCOUNT_OR_SERVICE_CHANGED'):
        invoke(granted, 'catalog_query', {'query': {}})
    assert granted.manager.revoked.is_set()
    assert [name for name, _ in granted.calls] == ['catalog_local_scope']


def test_local_phone_cannot_be_constructed_with_playback_permission(phone, local):
    expected = local[0].dispatch('catalog_local_scope', dict(source_id=local[1].id))
    with pytest.raises(phone.module.PhoneError, match='ACTION_FORBIDDEN'):
        phone.module.PhoneManagement(expected, 'http://127.0.0.1:8081', rpc=lambda *a, **k: None,
            scopes=phone.module.SCOPES | {'playback_read'})

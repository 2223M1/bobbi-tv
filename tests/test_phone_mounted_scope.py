"""Real phone gate -> CatalogService -> Registry/SQLite; mount evidence is synthetic."""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import importlib.util
import sys

import pytest

from bobbi_platform.libraries import Registry, vfs_source
from test_ce2097_phone_management import phone, pair, invoke
from test_scan_source_ports import cd2, scan, movie


@pytest.fixture
def mounted(phone, cd2):
    service, source, _, _ = cd2
    scan(cd2)
    expected = service.dispatch('catalog_mount_scope', dict(source_id=source.id))
    state = SimpleNamespace(module=phone.module, expected=expected, calls=[], now=100,
        headers={'Host': '127.0.0.1:8081', 'Origin': 'http://127.0.0.1:8081'})
    def rpc(action, body, **kwargs):
        state.calls.append((action, deepcopy(body)))
        return service.dispatch(action, body)
    state.manager = phone.module.PhoneManagement(expected, 'http://127.0.0.1:8081', rpc=rpc, clock=lambda: state.now)
    pair(state)
    return state


def test_explicit_mounted_grant_queries_edits_and_reads_same_receipt_while_offline(mounted, cd2):
    service, source, _, mounts = cd2
    file_id = movie(cd2)['entity_id']
    mounts.clear()
    result = invoke(mounted, 'catalog_query', dict(query={}, limit=32))
    assert result['items'] and all(row['availability'] == 'source_unavailable' for row in result['items'])
    item = invoke(mounted, 'catalog_item', dict(file_id=file_id))
    assert item['file']['id'] == file_id and 'file_ref' not in item
    command = dict(file_id=file_id, expected_revision=item['revision'], action='confirm',
        mapping=dict(kind='movie', title='Reviewed movie', tmdb_id=123, season=None, episode=None, version=None))
    assert invoke(mounted, 'catalog_preview', dict(commands=[command]))['items'][0]['status'] == 'ready'
    assert invoke(mounted, 'catalog_apply', dict(commands=[command], request_id='d'*32))['items'][0]['status'] == 'applied'
    receipt = invoke(mounted, 'catalog_receipt', dict(request_id='d'*32))
    assert receipt['status'] == 'found' and receipt['items'][0]['status'] == 'applied'
    assert invoke(mounted, 'catalog_item', dict(file_id=file_id))['mapping']['title'] == 'Reviewed movie'
    for action, body in mounted.calls:
        assert action != 'pan_status' and 'expected' not in body
        if action != 'catalog_mount_scope':
            assert body['source_id'] == source.id and body['namespace'] == mounted.expected['namespace']


@pytest.mark.parametrize('action,params', [
    ('catalog_mount_query', {}), ('catalog_query', {'query': {}, 'scope': {}}),
    ('catalog_item', {'file_id': 'a'*64, 'expected': {}}),
    ('catalog_query', {'query': {'source_id': 'f'*32}}),
    ('catalog_items', {'source': 'f'*32}), ('catalog_group', {'file_id': 'a'*64, 'source_id': 'f'*32}),
    ('catalog_scan', {'source_id': 'f'*32}), ('catalog_history', {}),
])
def test_mounted_grant_cannot_expand_browser_scope(mounted, action, params):
    mounted.calls.clear()
    with pytest.raises(mounted.module.PhoneError, match='ACTION_FORBIDDEN'):
        invoke(mounted, action, params)
    assert all(action == 'catalog_mount_scope' for action, _ in mounted.calls)


def test_mounted_grant_does_not_advertise_an_unusable_native_playback_permission(mounted):
    with pytest.raises(mounted.module.PhoneError, match='ACTION_FORBIDDEN'):
        mounted.module.PhoneManagement(mounted.expected, 'http://127.0.0.1:8081',
            rpc=lambda *args,**kwargs: {}, scopes=mounted.module.SCOPES|mounted.module.PLAYBACK_SCOPES)


def test_old_native_grant_cannot_read_or_modify_mounted_files(phone, cd2):
    service, _, _, _ = cd2
    scan(cd2)
    file_id = movie(cd2)['entity_id']
    expected = service.pans.accounts.expected
    phone.expected = expected
    calls = []
    def rpc(action, body, **kwargs):
        calls.append((action, deepcopy(body)))
        if action == 'pan_status':
            return dict(providers=[dict(provider=expected['provider'], account=expected)])
        return service.dispatch(action, body)
    phone.manager = phone.module.PhoneManagement(expected, 'http://127.0.0.1:8081', rpc=rpc, clock=lambda: phone.now)
    pair(phone)
    with pytest.raises(phone.module.PhoneError, match='CATALOG_FILE_NOT_FOUND'):
        invoke(phone, 'catalog_item', dict(file_id=file_id))
    with pytest.raises(phone.module.PhoneError, match='ACTION_FORBIDDEN'):
        invoke(phone, 'catalog_mount_query')
    command = dict(file_id=file_id, expected_revision=0, action='ignore', mapping=None)
    preview = invoke(phone, 'catalog_preview', dict(commands=[command]))
    assert preview['items'][0]['status'] != 'ready'
    assert not [action for action, _ in calls if action.startswith('catalog_mount_')]
    assert service.index.item(service.dispatch('catalog_mount_scope', dict(source_id=cd2[1].id)), file_id)['revision'] == 0


def test_mounted_file_and_receipt_ids_from_another_registered_source_do_not_grant_access(mounted, cd2):
    service, _, media, _ = cd2
    foreign_root = media / 'Other source'
    foreign_root.mkdir()
    (foreign_root / 'Private.mkv').write_bytes(b'synthetic fixture')
    foreign = vfs_source('Other source', foreign_root.as_posix())
    registry = Registry(service.root / 'libraries.sqlite3')
    registry.save(foreign)
    registry.close()
    service.dispatch('catalog_mount_scan', dict(source_id=foreign.id))
    service.worker.join(5)
    assert not service.worker.is_alive()
    scope = service.dispatch('catalog_mount_scope', dict(source_id=foreign.id))
    row = service.dispatch('catalog_mount_query', dict(source_id=foreign.id, query={'view': 'files'}))['items'][0]
    command = dict(file_id=row['entity_id'], expected_revision=0, action='ignore', mapping=None)
    with pytest.raises(mounted.module.PhoneError, match='CATALOG_FILE_NOT_FOUND'):
        invoke(mounted, 'catalog_item', dict(file_id=row['entity_id']))
    assert invoke(mounted, 'catalog_preview', dict(commands=[command]))['items'][0]['status'] == 'failed'
    assert invoke(mounted, 'catalog_apply', dict(commands=[command], request_id='e'*32))['items'][0]['status'] == 'failed'
    assert service.index.item(scope, row['entity_id'])['revision'] == 0
    service.dispatch('catalog_mount_apply', dict(source_id=foreign.id, namespace=scope['namespace'],
        request_id='f'*32, commands=[command]))
    assert invoke(mounted, 'catalog_receipt', dict(request_id='f'*32)) == dict(status='missing', items=[])


@pytest.mark.parametrize('change', ['removed', 'rebound'])
def test_registered_scope_change_revokes_old_mounted_pairing(mounted, cd2, change):
    service, source, media, _ = cd2
    registry = Registry(service.root / 'libraries.sqlite3')
    try:
        if change == 'removed':
            registry.remove(source.id)
        else:
            registry.save(vfs_source('New root', (media / 'new-root').as_posix(), source_id=source.id))
    finally:
        registry.close()
    mounted.calls.clear()
    with pytest.raises(mounted.module.PhoneError, match='ACCOUNT_OR_SERVICE_CHANGED'):
        invoke(mounted, 'catalog_query', {'query': {}})
    assert mounted.manager.revoked.is_set()
    assert [action for action, _ in mounted.calls] == ['catalog_mount_scope']


@pytest.mark.parametrize('approved', [False, True])
def test_mounted_phone_pairing_requires_explicit_tv_source_namespace_approval(phone, monkeypatch, approved):
    expected = dict(reference_kind='mounted_path', source_id='a'*32, namespace='b'*64, generation='')
    prompts, grants, events = [], [], []
    manager = SimpleNamespace(pairing_url='http://127.0.0.1:8081/manage#synthetic', revoke=lambda:events.append('revoke'))
    server = SimpleNamespace(start=lambda:events.append('start'), is_running=True, stop=lambda:events.append('stop'))
    qr = SimpleNamespace(setup=lambda **kwargs:None, doModal=lambda:events.append('modal'))
    def confirm(title, body):
        prompts.append(body)
        return approved
    modules = {
        'xbmcgui': SimpleNamespace(Dialog=lambda:SimpleNamespace(yesno=confirm,select=lambda *args:0)),
        'lib.gui.qr_progress_dialog': SimpleNamespace(QRProgressDialog=lambda *args:qr),
        'lib.services.webserver': SimpleNamespace(StremioWebServer=lambda **kwargs:server, get_local_ip=lambda:'127.0.0.1'),
        'lib.utils.debrid.qrcode_utils': SimpleNamespace(make_qrcode=lambda value:''),
        'lib.utils.kodi.utils': SimpleNamespace(ADDON_PATH='',kodilog=lambda *args:None,translation=lambda value:value),
        'lib.services.phone_management': SimpleNamespace(SCOPES=phone.module.SCOPES,
            PhoneManagement=lambda value,origin,**kwargs:(grants.append(value) or manager)),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi/lib/clients/stremio/manage_phone.py'
    spec = importlib.util.spec_from_file_location('explicit_tv_phone_pairing', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.catalog_manage_phone(expected) is approved
    assert expected['source_id'] in prompts[0] and expected['namespace'] in prompts[0]
    assert '不授权其他挂载或网盘账号' in prompts[0]
    assert grants == ([expected] if approved else [])
    assert events == (['start', 'modal', 'stop'] if approved else [])


def test_tv_review_scope_adapter_keeps_namespace_on_every_call(monkeypatch):
    from bobbi_platform import catalog_ui
    expected = dict(reference_kind='mounted_path', source_id='a'*32, namespace='b'*64, generation='')
    calls = []
    monkeypatch.setattr(catalog_ui, 'call', lambda action,body,**kw:calls.append((action,body)))
    catalog_ui._call('catalog_preview', expected, commands=[])
    catalog_ui._call('catalog_jobs', expected, offset=0, limit=5)
    assert [action for action,_ in calls] == ['catalog_mount_preview', 'catalog_mount_jobs']
    assert all(body['source_id'] == expected['source_id'] and body['namespace'] == expected['namespace']
               and 'expected' not in body for _,body in calls)


def test_mounted_source_observation_is_real_but_never_exposes_another_grant(mounted, cd2):
    service, source, media, mounts = cd2
    registry = Registry(service.root / 'libraries.sqlite3')
    try:
        registry.save(vfs_source('Private other source', (media/'other').as_posix()))
    finally:
        registry.close()
    value = invoke(mounted, 'catalog_sources')
    assert len(value['items']) == 1 and value['items'][0]['id'] == source.id
    assert value['items'][0]['name'] == source.name
    observation = value['items'][0]['observation']
    assert observation['coverage'] == 'complete' and observation['latest_state'] == 'completed'
    assert observation['counts']['discovered'] > 0
    mounts.clear()
    offline = invoke(mounted, 'catalog_sources')['items'][0]
    assert offline['observation']['availability'] == 'source_unavailable'
    assert 'Private other source' not in repr(offline)

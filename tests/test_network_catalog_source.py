"""Experimental network lane, real Registry/SQLite/worker/review/phone/player.

Only Kodi's upstream VFS response is simulated: not device certification.
"""
from copy import deepcopy
from dataclasses import replace
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4

import pytest

from bobbi_core import network_ref, typed_ref
from bobbi_core.library_contract import MAX_DIRECTORY_ITEMS
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.network_sources import NetworkPort, network_listing
from test_catalog_service import Pans
from test_media_library_index import scope, command
from test_library_plugin import plugin
from test_scan_source_ports import mounted_ui
from test_ce2097_phone_management import phone, pair, invoke
from test_library_ui import context


class Upstream:
    def __init__(self):
        self.tree = {'': [('Movie.mkv', False, 1024, '2026-01-02T03:04:05.123456Z'),
                          ('特别篇', True, None, None), ('notes.txt', False, None, None)],
                     '特别篇': [('Show.S00E01.mkv', False, 512, '2026-01-02 03:04:05')]}
        self.calls, self.mutate = [], None

    def __call__(self, path, maximum):
        self.calls.append((path, maximum))
        parent = unquote(urlsplit(path).path).removeprefix('/Movies/').rstrip('/')
        rows = [dict(file=path.rstrip('/') + '/' + quote(name, safe='') + ('/' if folder else ''),
            filetype='directory' if folder else 'file', size=size, lastmodified=modified)
            for name, folder, size, modified in self.tree[parent]]
        result = dict(files=rows, limits=dict(start=0, end=len(rows), total=len(rows)))
        if self.mutate:
            self.mutate(result)
        return result


@pytest.fixture
def network(tmp_path, request):
    scheme = getattr(request, 'param', 'smb')
    source = vfs_source('Network source', scheme + '://nas/Movies/',
        '' if scheme == 'nfs' else 'private-user', '' if scheme == 'nfs' else 'secret-password')
    store = Registry(tmp_path / 'libraries.sqlite3')
    store.save(source)
    store.close()
    upstream = Upstream()
    service = CatalogService(tmp_path, Pans(scope(), lambda *a: pytest.fail('No native provider calls')))
    service.mounted.network_port = NetworkPort(tmp_path, fetch=upstream)
    yield service, source, upstream, []
    service.close()


@pytest.fixture
def cd2(network):
    return network  # Reuse the real portable-player owner fixture only.


def dispatch(network, action, **body):
    service, source, _, _ = network
    return service.dispatch('catalog_network_' + action, dict(source_id=source.id, **body))


def scan(network):
    task = dispatch(network, 'scan')['task_id']
    network[0].worker.join(5)
    assert not network[0].worker.is_alive()
    return dispatch(network, 'jobs', task=task)['items'][0]


def files(network):
    return dispatch(network, 'query', query=dict(view='files'))['items']


def movie(network):
    return next(row for row in files(network) if row['display_title'] == 'Movie.mkv')


def prepare(network, intent='play', request=None):
    return dispatch(network, 'prepare', object_id=movie(network)['entity_id'],
        request_id=request or uuid4().hex, intent=intent)['ticket']


def saved(network):
    return [tuple(row) for row in network[0].index.db.execute('SELECT * FROM memberships ORDER BY file')]


@pytest.mark.parametrize('network', ['smb', 'nfs', 'dav', 'davs'], indirect=True)
def test_registered_protocol_scan_review_version_claim_and_no_fake_native_identity(network):
    service, source, upstream, _ = network
    listed = service.dispatch('catalog_network_sources', {})['items']
    assert listed[0]['experimental'] and listed[0]['device_verified'] is False
    assert not upstream.calls  # Source/job/query discovery is configuration-only.
    assert scan(network)['state'] == 'completed'
    selected = movie(network)['entity_id']
    edit = command(dict(id=selected), title='My network movie')
    edit['mapping']['version'] = 'Original network cut'
    assert dispatch(network, 'preview', commands=[edit])['items'][0]['status'] == 'ready'
    receipt = dispatch(network, 'apply', commands=[edit], request_id=uuid4().hex)
    assert receipt['items'][0]['status'] == 'applied'
    works = dispatch(network, 'query', query=dict(view='works'))['items']
    work = next(row for row in works if row['display_title'] == 'My network movie')
    versions = dispatch(network, 'query', query=dict(view='files', parent_entity_id=work['entity_id']))['items']
    assert versions[0]['version_label'] == 'Original network cut'
    ticket = dispatch(network, 'prepare', object_id=selected, request_id=uuid4().hex, intent='play')['ticket']
    with pytest.raises(ValueError, match='REFERENCE_INVALID'):
        service.dispatch('catalog_mount_claim', dict(ticket=ticket))
    claim = service.dispatch('catalog_network_claim', dict(ticket=ticket))
    assert claim['resume_supported'] is False and claim['object_id'] == selected
    assert dispatch(network, 'verify', object_id=selected, request_id=ticket) == dict(valid=True)
    assert service.index.db.execute('SELECT count(*) FROM objects').fetchone()[0] == 0
    assert service.index.db.execute('SELECT count(*) FROM typed_objects').fetchone()[0] == 2
    authority = dispatch(network, 'scope')
    ref = service.index.trusted_mounted_file(authority, selected)
    assert ref['reference_kind'] == 'network_path' and 'signature' not in ref and 'root_signature' not in ref
    assert typed_ref.validate(ref) == ref
    from bobbi_core.file_ref import validate
    with pytest.raises(ValueError):
        validate(ref)
    public = repr((files(network), ref, claim, listed, receipt))
    for secret in ('private-user', 'secret-password', '://', 'nas'):
        assert secret not in public


@pytest.mark.parametrize('damage', ['missing_limits', 'partial', 'offset', 'duplicate', 'nested',
    'encoded_traversal', 'encoded_slash', 'foreign', 'file_trailing_slash', 'missing_size', 'missing_time', 'date_only'])
def test_incomplete_native_response_never_infers_absence(network, damage):
    assert scan(network)['state'] == 'completed'
    before = saved(network)
    def corrupt(result):
        rows = result['files']
        if damage == 'missing_limits':
            result.pop('limits')
        elif damage == 'partial':
            result['limits']['total'] += 1
        elif damage == 'offset':
            result['limits']['start'] = 1
        elif damage == 'duplicate':
            rows.append(deepcopy(rows[0]))
            result['limits'].update(end=len(rows), total=len(rows))
        elif damage in ('nested', 'encoded_traversal', 'encoded_slash', 'foreign', 'file_trailing_slash'):
            rows[0]['file'] = {'nested': rows[0]['file'] + '/nested.mkv',
                'encoded_traversal': rows[0]['file'].rsplit('/', 1)[0] + '/%2e%2e',
                'encoded_slash': rows[0]['file'].rsplit('/', 1)[0] + '/bad%2Ffile.mkv',
                'foreign': 'smb://other/Private.mkv', 'file_trailing_slash': rows[0]['file'] + '/'}[damage]
        elif damage == 'missing_size':
            rows[0].pop('size')
        elif damage == 'missing_time':
            rows[0].pop('lastmodified')
        else:
            rows[0]['lastmodified'] = '2026-01-02'
    network[2].mutate = corrupt
    job = scan(network)
    assert job['state'] == 'failed'
    assert job['result_summary'] in ('CATALOG_NETWORK_INCOMPLETE', 'CATALOG_NETWORK_METADATA_REQUIRED')
    assert saved(network) == before


@pytest.mark.parametrize('change', ['cancel', 'deadline', 'credentials', 'remove_readd'])
def test_late_native_io_cannot_publish_after_cancel_deadline_or_config_change(network, change):
    service, source, upstream, _ = network
    scan(network)
    before = saved(network)
    now = [0]
    service.mounted.network_port.clock = lambda: now[0]
    def mutate(result):
        upstream.mutate = None
        if change == 'cancel':
            service.cancel_event.set()
        elif change == 'deadline':
            now[0] = 1801
        else:
            store = Registry(service.root / 'libraries.sqlite3')
            try:
                if change == 'remove_readd':
                    store.remove(source.id)
                    store.save(source)
                else:
                    store.save(replace(source, password='replacement-secret'))
            finally:
                store.close()
    upstream.mutate = mutate
    job = scan(network)
    assert job['state'] in ('failed', 'canceled')
    assert saved(network) == before


def test_only_explicit_complete_scan_can_mark_missing_files_absent(network):
    scan(network)
    network[2].tree[''] = []
    assert scan(network)['state'] == 'completed'
    assert all(row['availability'] == 'observed_absent' for row in files(network))


def test_metadata_change_requires_explicit_start_selection_not_exact_resume(network):
    scan(network)
    service, source, upstream, _ = network
    selected = movie(network)['entity_id']
    authority = dispatch(network, 'scope')
    prior = service.index.trusted_mounted_file(authority, selected)
    name, folder, size, _ = upstream.tree[''][0]
    upstream.tree[''][0] = (name, folder, size, '2026-01-02T03:04:05.123457Z')
    with pytest.raises(ValueError, match='FILE_CHANGED'):
        prepare(network)
    ticket = prepare(network, intent='play_from_start')
    claim = service.dispatch('catalog_network_claim', dict(ticket=ticket))
    assert claim['resume_supported'] is False
    current = service.index.trusted_mounted_file(authority, selected)
    assert current['id'] == prior['id'] and not network_ref.same_observation(prior, current)
    assert service.mounted.network_port.capabilities['strong_content_identity'] is False


def test_registry_revision_equal_save_rotation_cas_and_recreate(network):
    service, source, _, _ = network
    store = Registry(service.root / 'libraries.sqlite3')
    try:
        original, revision = store.source_snapshot(source.id)
        store.save(source)
        assert store.source_snapshot(source.id) == (original, revision)
        writes = []
        assert store.run_if_current(original, revision, lambda: writes.append('first')) is None
        store.save(replace(source, password='rotated-secret'))
        assert store.source_snapshot(source.id)[1] != revision
        with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
            store.run_if_current(original, revision, lambda: writes.append('stale'))
        store.remove(source.id)
        store.save(source)
        assert store.source_snapshot(source.id)[1] != revision
        assert writes == ['first']
        assert store.db.execute('PRAGMA user_version').fetchone()[0] == 1
    finally:
        store.close()


def test_old_scope_ticket_and_query_cursor_are_revoked_after_credential_rotation(network):
    scan(network)
    service, source, _, _ = network
    prior = dispatch(network, 'scope')
    ticket = prepare(network)
    page = dispatch(network, 'query', query=dict(view='files'), limit=1)
    store = Registry(service.root / 'libraries.sqlite3')
    store.save(replace(source, password='rotated-secret'))
    store.close()
    with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
        service.dispatch('catalog_network_claim', dict(ticket=ticket))
    with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
        service.run_in_scope(prior, lambda: pytest.fail('stale publication'))
    with pytest.raises(ValueError, match='CURSOR_STALE'):
        dispatch(network, 'query', query=dict(view='files'), limit=1, cursor=page['next_cursor'])
    assert all(row['availability'] == 'unverified' for row in files(network))


def test_private_transport_error_is_sanitized_and_recheck_is_bounded(network):
    scan(network)
    port = network[0].mounted.network_port
    def fail(*args):
        raise OSError('smb://private-user:secret-password@nas/Movies/')
    port.fetch = fail
    with pytest.raises(ValueError, match='^CATALOG_SOURCE_UNAVAILABLE$'):
        prepare(network)
    port.fetch = network[2]
    network[2].tree[''] = [('Movie.mkv', False, 1024, '2026-01-02T03:04:05Z')] * 161
    with pytest.raises(ValueError, match='NETWORK_INCOMPLETE'):
        prepare(network)
    assert network[2].calls[-1][1] == MAX_DIRECTORY_ITEMS


@pytest.mark.parametrize('network', ['dav', 'davs'], indirect=True)
def test_large_directory_last_file_scan_prepare_claim_verify(network):
    upstream = network[2]
    target = upstream.tree[''][0]
    upstream.tree[''] = [('Z-%03d.mkv' % i, *target[1:]) for i in range(160)] + [target]
    assert scan(network)['state'] == 'completed'
    selected = movie(network)['entity_id']
    upstream.calls.clear()
    ticket = prepare(network)
    assert network[0].dispatch('catalog_network_claim', dict(ticket=ticket))['object_id'] == selected
    assert dispatch(network, 'verify', object_id=selected, request_id=ticket)['valid']
    assert [maximum for _, maximum in upstream.calls] == [MAX_DIRECTORY_ITEMS] * 3


def test_network_selection_rejects_truncated_or_over_budget_sibling_evidence(network):
    scan(network)
    upstream = network[2]
    upstream.mutate = lambda result: result['limits'].update(total=MAX_DIRECTORY_ITEMS + 1)
    with pytest.raises(ValueError, match='NETWORK_INCOMPLETE'):
        prepare(network)
    upstream.mutate = None
    upstream.tree[''] += [('note-%d.txt' % i, False, None, None) for i in range(MAX_DIRECTORY_ITEMS)]
    with pytest.raises(ValueError, match='NETWORK_INCOMPLETE'):
        prepare(network)


def test_network_tv_handoff_uses_same_owner_start_zero_and_never_native_history(network, mounted_ui):
    scan(network)
    source = network[1]
    mounted_ui.playback.mounted(dict(reference_kind='network_path', source=source.id,
        object_id=movie(network)['entity_id']), handle=17, rpc=mounted_ui.dispatch)
    assert mounted_ui.plugin.resolved[-1][1] is True
    item = mounted_ui.plugin.resolved[-1][2]
    assert item.properties['StartOffset'] == '0'
    assert item.path.startswith('smb://private-user:secret-password@nas/')
    assert any(action == 'catalog_network_verify' for action, _ in mounted_ui.calls)
    assert not any('history' in action or action.startswith('pan_') for action, _ in mounted_ui.calls)


def test_phone_network_grant_is_single_scope_and_credentials_revoke_it(phone, network):
    scan(network)
    expected = dispatch(network, 'scope')
    calls = []
    def rpc(action, body, **kwargs):
        calls.append((action, deepcopy(body)))
        return network[0].dispatch(action, body)
    phone.manager = phone.module.PhoneManagement(expected, 'http://127.0.0.1:8081', rpc=rpc, clock=lambda: phone.now)
    pair(phone)
    page = invoke(phone, 'catalog_query', dict(query=dict(view='files')))
    assert page['items'] and 'secret-password' not in repr(page)
    assert phone.manager._session_description()['catalog_kind'] == 'network'
    for action, body in calls:
        if action not in ('catalog_network_scope', 'catalog_network_sources'):
            assert body['generation'] == expected['generation']
    for action, args in [('catalog_history', {}), ('catalog_query', {'query': {'source_id': 'f' * 32}})]:
        with pytest.raises(phone.module.PhoneError, match='ACTION_FORBIDDEN'):
            invoke(phone, action, args)
    with pytest.raises(phone.module.PhoneError, match='ACTION_FORBIDDEN'):
        phone.module.PhoneManagement(expected, 'http://127.0.0.1:8081', rpc=rpc,
            scopes=phone.module.SCOPES | phone.module.PLAYBACK_SCOPES)
    store = Registry(network[0].root / 'libraries.sqlite3')
    store.save(replace(network[1], password='new-password'))
    store.close()
    with pytest.raises(phone.module.PhoneError, match='ACCOUNT_OR_SERVICE_CHANGED'):
        invoke(phone, 'catalog_query', dict(query={}))
    assert phone.manager.revoked.is_set()


def test_network_transport_never_runs_under_catalog_or_registry_publication_lock(network):
    service, source, upstream, _ = network
    def fetch(path, maximum):
        assert not service.lock.locked()
        # A second SQLite connection can acquire the write lock during I/O.
        store = Registry(service.root / 'libraries.sqlite3')
        try:
            with store.db:
                store.db.execute('BEGIN IMMEDIATE')
        finally:
            store.close()
        return upstream(path, maximum)
    service.mounted.network_port.fetch = fetch
    assert scan(network)['state'] == 'completed'
    ticket = prepare(network)
    service.dispatch('catalog_network_claim', dict(ticket=ticket))
    assert dispatch(network, 'verify', object_id=movie(network)['entity_id'], request_id=ticket)['valid']


@pytest.mark.parametrize('phase', ['catalog_network_scope', 'catalog_network_prepare', 'catalog_network_verify'])
def test_network_tv_late_profile_switch_never_hands_off(network, mounted_ui, monkeypatch, phase):
    import sys
    scan(network)
    original = sys.modules['xbmcvfs'].translatePath
    def after(action, body):
        if action == phase:
            monkeypatch.setattr(sys.modules['xbmcvfs'], 'translatePath', lambda value: original(value) + '/different-profile')
    mounted_ui.after_action = after
    mounted_ui.playback.mounted(dict(reference_kind='network_path', source=network[1].id,
        object_id=movie(network)['entity_id']), handle=17, rpc=mounted_ui.dispatch)
    assert mounted_ui.plugin.resolved[-1][1] is False


@pytest.mark.parametrize('change', ['credentials', 'remove_readd'])
def test_network_tv_late_registry_change_never_hands_off(network, mounted_ui, change):
    scan(network)
    service, source, _, _ = network
    def after(action, body):
        if action != 'catalog_network_prepare':
            return
        store = Registry(service.root / 'libraries.sqlite3')
        try:
            if change == 'remove_readd':
                store.remove(source.id)
                store.save(source)
            else:
                store.save(replace(source, password='late-password'))
        finally:
            store.close()
    mounted_ui.after_action = after
    mounted_ui.playback.mounted(dict(reference_kind='network_path', source=source.id,
        object_id=movie(network)['entity_id']), handle=17, rpc=mounted_ui.dispatch)
    assert mounted_ui.plugin.resolved[-1][1] is False


def test_network_production_source_menu_exposes_experimental_catalog_without_remote_io(context, monkeypatch):
    from bobbi_platform import library_ui, runtime
    source = vfs_source('Network', 'smb://nas/Movies/')
    context.store.save(source)
    context.selections = [2, 3]
    calls = []
    def rpc(action, body, **kwargs):
        calls.append(action)
        return dict(items=[])
    monkeypatch.setattr(runtime, 'call', rpc)
    context.vfs.listdir = lambda *a: pytest.fail('Menu must not enumerate network files')
    assert library_ui.manage() is True
    assert any('网络实验' in repr(row) for row in context.shown)
    assert 'reference_kind=network_path' in context.builtins[-1]
    assert not any('scan' in action for action in calls)


def test_readonly_network_query_does_not_fetch_and_old_route_generation_is_revoked(network, mounted_ui):
    scan(network)
    service, source, upstream, _ = network
    expected = dispatch(network, 'scope')
    route = mounted_ui.catalog.scope_params(expected)
    service.mounted.network_port.fetch = lambda *a: pytest.fail('descriptions are local')
    assert files(network)
    store = Registry(service.root / 'libraries.sqlite3')
    store.save(replace(source, password='changed'))
    store.close()
    with pytest.raises(ValueError, match='AUTHORITY_CHANGED'):
        mounted_ui.catalog.mounted_for(route, mounted_ui.dispatch)


def test_registry_legacy_source_gets_one_revision_without_schema_upgrade(network):
    store = Registry(network[0].root / 'libraries.sqlite3')
    try:
        with store.db:
            store.db.execute('DELETE FROM metadata WHERE key=?', ('source_revision:' + network[1].id,))
        first = store.source_snapshot(network[1].id)
        assert first == store.source_snapshot(network[1].id)
        assert len(first[1]) == 64
        assert store.db.execute('PRAGMA user_version').fetchone()[0] == 1
    finally:
        store.close()


def test_metadata_ref_rejects_fake_identity_and_secret_extra_fields(network):
    scan(network)
    reference = network[0].index.trusted_mounted_file(dispatch(network, 'scope'), movie(network)['entity_id'])
    for patch in (dict(root_signature={}), dict(signature={}), dict(url='smb://secret@nas/file'),
                  dict(source_generation=''), dict(reference_kind='local_path'), dict(size=True)):
        with pytest.raises(ValueError):
            typed_ref.validate(dict(reference, **patch))

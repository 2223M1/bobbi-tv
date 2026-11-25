"""R3 playback continuity, 4-domain Accounts & Sources Center, 3-state navigation, and S03 media_server filter."""
import ast
from contextlib import nullcontext
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_core.file_ref import from_selected
from bobbi_core.library_contract import Item, LibraryError, Source, vfs_source
from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_platform import account_dialog, cloud_hub, library_ui, server_ui
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.emby_session import EmbyInvalidationHub, EmbySessionReporter, _load_emby_client
from bobbi_platform.libraries import Registry
from bobbi_platform.owned_playback import emby_source_scope
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_service import PanService
from bobbi_platform.playback_accounts import PlaybackAccounts
from bobbi_platform.server_accounts import Accounts as ServerAccounts
from bobbi_platform.server_emby import Client as EmbyClient
from bobbi_platform.source_streams import SourceStreams
from test_ce2096_pan_stream import Upstream, read
from test_media_servers import BASE, EmbyWire
from test_library_ui import context as ui_context
from test_onboarding import setup_ui

ROOT = Path(__file__).resolve().parents[1]
for _extra_path in (str(ROOT / 'tests/private_baseline'), str(ROOT / 'addons/plugin.video.bobbi')):
    if _extra_path not in sys.path:
        sys.path.append(_extra_path)


def _make_emby_pair(root, *, current=lambda: True):
    wire = EmbyWire('emby')
    factory = lambda key, saved: EmbyClient(key, saved, wire)
    servers = ServerAccounts(root, current=current)
    a = servers.register('emby', 'A', BASE, 'fixture-secret', client_factory=factory)
    b = servers.register(
        'emby',
        'B',
        BASE,
        'fixture-other',
        client_factory=lambda *_: SimpleNamespace(
            session=SimpleNamespace(budget=lambda _: nullcontext()),
            verify=lambda: ('server1', 'user2'),
        ),
    )
    store = Registry(root / 'libraries.sqlite3')
    _, generation = store.source_snapshot(a['source_id'])
    a = servers.activate_emby(a['source_id'], generation, b)
    legacy = AccountManager(root / '115.json')
    pans = PanService(root, legacy, servers=servers, client_factory=factory)
    playback = PlaybackAccounts(legacy, lambda: pans, registry_root=root, current=current)
    return servers, store, pans, playback, a, b


def _switch_emby(servers, store, target):
    _, generation = store.source_snapshot(target['source_id'])
    return servers.activate_emby(target['source_id'], generation, servers.snapshot('emby'))


def test_r3_pb01_indexed_emby_stream_and_authority_survive_switches_and_revoke_on_real_changes(tmp_path):
    from test_playback_authority import Native, row

    profile_live = [True]
    servers, store, pans, playback, a, b = _make_emby_pair(tmp_path, current=lambda: profile_live[0])
    registered = store.save_directory('Existing Emby Movies', a, 'root')
    catalog = CatalogService(tmp_path, pans)
    native = Native()
    authority = PlaybackAuthority(native)
    authority.configure_accounts(playback)
    try:
        task = catalog.start_scan(a, registered['id'])['task_id']
        catalog.worker.join(3)
        assert not catalog.worker.is_alive()
        assert catalog.index.jobs(a, task=task)['items'][0]['state'] == 'completed'
        selected = pans.list_files(a, 'item:item1', 1)['items'][0]
        ref = from_selected(a, selected, 'item:item1')

        ticket = catalog.prepare_play(a, ref['id'], '1' * 32, 'play')['ticket']
        claimed = pans.claim_play(ticket)
        ready = pans.open_stream(a, claimed['selected'], ticket)
        seen = []
        pans.streams.session_factory = lambda: Upstream(seen)

        snapshot = authority.dispatch(dict(operation='snapshot'))
        state = authority.dispatch(dict(
            operation='select',
            boot_id=snapshot['boot_id'],
            epoch=snapshot['epoch'],
            request_id='1' * 32,
            selection_identity='server-file',
            account_scope=a,
        ))
        args = dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id='1' * 32)
        assert authority.dispatch(dict(
            args,
            operation='bind_file',
            selection_identity='server-file',
            file_identity='server-file|part',
            url_sha256='b' * 64,
            file_evidence='USER_CONFIRMED_FILE',
        )) == {'bound': True}
        assert authority.dispatch(dict(args, operation='claim_start', route='player_play'))['status'] == 'CLAIMED'
        native.current = row('1' * 32, 'server-file|part', url_sha256='b' * 64)
        authority.refresh()

        # Switch default browse account 25 times back and forth: admitted stream & authority stay live!
        for idx in range(25):
            _switch_emby(servers, store, b if idx % 2 == 0 else a)
            authority.account_changed()
            assert not authority.owner.desired['cancelled']
            status, _, body = read(ready['url'])
            assert status == 206 and body == b'cdef'

        # Forced address renewal on ShareStream after browse switch still resolves A's credentials cleanly.
        with pans.streams.lock:
            entry = pans.streams.records['1' * 32]
        entry.address = None
        status, _, body = read(ready['url'])
        assert status == 206 and body == b'cdef'

        # Strict negative controls: browse, scan, and new ticket admission reject stale scope `a`!
        with pytest.raises(PanError, match='PAN_ACCOUNT_CHANGED'):
            pans.list_files(a, 'item:item1', 1, refresh=True)
        with pytest.raises(PanError, match='PAN_ACCOUNT_CHANGED'):
            catalog.prepare_play(a, ref['id'], '2' * 32, 'play')

        # Profile switch revokes both PlaybackAccounts and ShareStream immediately.
        profile_live[0] = False
        assert not playback.is_current(a)
        status_prof, _, body_prof = read(ready['url'])
        assert status_prof in (404, 503) and body_prof != b'cdef'
        profile_live[0] = True

        # Password/token change on A revokes A's retained playback scope and stops PlaybackAuthority!
        src_a, rev_a = store.source_snapshot(a['source_id'])
        store.save(replace(src_a, password='rotated-secret'), expected_snapshot=(src_a, rev_a))
        assert not playback.is_current(a)
        authority.account_changed()
        assert authority.owner.desired['cancelled']
        assert native.commands[-1]['action'] == 'stop'
        status_after_pw, _, body_after_pw = read(ready['url'])
        assert status_after_pw in (404, 503) and body_after_pw != b'cdef'
    finally:
        catalog.close()
        pans.close()
        store.close()


def test_r3_pb02_credential_epoch_o1_storage_forged_gen_rejection_and_reporter_continuity(tmp_path):
    def verify_factory(provider, value):
        return SimpleNamespace(
            session=SimpleNamespace(budget=lambda _: nullcontext()),
            verify=lambda: ('server-1', value['token'].split('-')[-1]),
        )

    accounts = ServerAccounts(tmp_path)
    a = accounts.register('emby', 'A', 'http://127.0.0.1:8096', 'token-userA', client_factory=verify_factory)
    b = accounts.register('emby', 'B', 'http://127.0.0.1:8096', 'token-userB', client_factory=verify_factory)
    store = Registry(tmp_path / 'libraries.sqlite3')
    _, gen0 = store.source_snapshot(a['source_id'])
    accounts.activate_emby(a['source_id'], gen0, accounts.snapshot('emby'))
    src_a, playing_gen = store.source_snapshot(a['source_id'])
    scope = emby_source_scope(
        source_id=src_a.id,
        generation=playing_gen,
        server_id='server-1',
        user_id='userA',
    )
    playback = PlaybackAccounts(AccountManager(tmp_path / '115.json'), lambda: None, registry_root=tmp_path)
    streams = SourceStreams(tmp_path, lambda: True)

    sends = []

    def session_factory(saved):
        def request(path, **kw):
            if path.startswith('/Sessions/'):
                sends.append((saved['user_id'], path, kw['data']['PositionTicks']))
                return {}
            return {'Id': 'item-1', 'UserData': {'PlaybackPositionTicks': 6000000000, 'Played': False}}

        return SimpleNamespace(budget=lambda _: nullcontext(), request=request)

    hub = EmbyInvalidationHub(tmp_path)
    reporter = EmbySessionReporter(
        tmp_path,
        hub,
        start_worker=False,
        client_loader=lambda sid, gen: _load_emby_client(tmp_path, sid, gen, session_factory=session_factory),
    )
    meta = dict(
        provider='emby',
        source_id=src_a.id,
        source_generation=playing_gen,
        server_id='server-1',
        user_id='userA',
        item_id='item-1',
        media_source_id='media-1',
        play_session_id='session-A',
    )
    common = dict(request_id='c' * 32, duration=3600.0, observed_clock=True, data={'_owned_source': meta})
    try:
        assert reporter.on_playback_event(dict(common, event='AV_START', position=60.0))
        reporter.drain_once(flush_pending=False)

        # Forged random 64-hex generations are strictly rejected.
        assert store.source_session_snapshot(src_a.id, 'f' * 64)[1] is False
        forged_scope = dict(scope, generation='f' * 64)
        assert playback.is_current(forged_scope) is False

        # 60 browse switches (far above old 16 cap): O(1) metadata rows and unbroken playback/reporting!
        for idx in range(60):
            _switch_emby(accounts, store, b if idx % 2 == 0 else a)
        assert playback.is_current(scope) is True
        assert streams.source(scope).id == src_a.id
        meta_rows = store.db.execute("SELECT key, length(value) FROM metadata WHERE key LIKE 'emby_%'").fetchall()
        assert all(length <= 128 for _, length in meta_rows)

        assert reporter.on_playback_event(dict(common, event='PROGRESS', position=180.0, paused=False, trigger='TimeUpdate'))
        reporter.drain_once(flush_pending=False)
        assert reporter.on_playback_event(dict(common, event='TERMINAL', position=600.0, reason='STOP'))
        reporter.drain_once(flush_pending=False)
        assert sends == [
            ('userA', '/Sessions/Playing', 600_000_000),
            ('userA', '/Sessions/Playing/Progress', 1_800_000_000),
            ('userA', '/Sessions/Playing/Stopped', 6_000_000_000),
        ]

        # Logout / removal revokes retained scope immediately and never revives on recreation.
        store.remove(src_a.id)
        assert playback.is_current(scope) is False
    finally:
        reporter.close()
        hub.close()
        store.close()


def test_r3_ui01_setup_rejects_unknown_account_domains(setup_ui, monkeypatch):
    monkeypatch.setattr(setup_ui.module.xbmcgui, 'Dialog', lambda: setup_ui.dialog, raising=False)
    monkeypatch.setattr(sys, 'argv', ['script.bobbi.setup', 'accounts', 'bogus'])
    with pytest.raises(ValueError, match='INVALID_ACCOUNT_DOMAIN'):
        setup_ui.module.main()
    monkeypatch.setattr(sys, 'argv', ['script.bobbi.setup', 'accounts', 'servers', 'extra'])
    with pytest.raises(ValueError, match='INVALID_ACCOUNT_DOMAIN'):
        setup_ui.module.main()


def test_r3_ui01_four_domain_accounts_center_outcomes_and_strict_domain_validation(ui_context, monkeypatch):
    # Verify bobbi_platform has zero reverse imports into plugin.video.bobbi and account_dialog has zero executebuiltin.
    platform_dir = ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform'
    for py_file in platform_dir.glob('*.py'):
        tree = ast.parse(py_file.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith('lib.'), f'{py_file.name} imported plugin module {node.module}'
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith('lib.'), f'{py_file.name} imported plugin module {alias.name}'
    dialog_src = Path(account_dialog.__file__).read_text(encoding='utf-8')
    assert 'executebuiltin' not in dialog_src

    # Unknown domain arguments are rejected directly.
    for bad in ('', 'unknown', 'admin', 'RunPlugin(x)', 123):
        with pytest.raises(ValueError, match='INVALID_ACCOUNT_DOMAIN'):
            cloud_hub.show_accounts(ui_context.dialog, domain=bad)

    # Opening devices domain does NOT auto-create a phone session or run any builtin on open; cancelling is CANCELLED.
    monkeypatch.setattr(cloud_hub, 'status', lambda: dict(authenticated=True, preparation={'state': 'NOT_CONFIGURED'}))
    ui_context.selections = [3, -1, -1]  # Root -> devices -> back -> back
    outcome = cloud_hub.show_accounts(ui_context.dialog)
    assert outcome == cloud_hub.CANCELLED
    assert [m[0] for m in ui_context.shown] == ['账号与来源中心', '设备与手机', '账号与来源中心']
    assert ui_context.builtins == []

    # Navigating to an Emby server from 4-domain Accounts Center -> servers domain exits ALL menus without Container.Refresh!
    src_a = Source(
        'a' * 32,
        '家庭服 A',
        'media_server',
        'http://127.0.0.1:8096',
        password='tok-a',
        metadata=dict(schema=1, provider='emby', user_id='ua', server_id='sa'),
    )
    src_b = Source(
        'b' * 32,
        '家庭服 B',
        'media_server',
        'http://127.0.0.1:8096',
        password='tok-b',
        metadata=dict(schema=1, provider='emby', user_id='ub', server_id='sa'),
    )
    ui_context.store.save(src_a, activate_emby=ui_context.store.emby_binding()[1])
    ui_context.store.save(src_b, activate_emby=ui_context.store.emby_binding()[1])
    ui_context.shown.clear()
    ui_context.builtins.clear()
    ui_context.selections = [1, 2, 0]  # Root -> servers -> 家庭服 A -> 浏览在线片库
    nav_outcome = cloud_hub.show_accounts(ui_context.dialog)
    assert nav_outcome == cloud_hub.NAVIGATED
    assert len(ui_context.shown) == 3
    assert ui_context.builtins == [
        'ActivateWindow(Videos,plugin://plugin.video.bobbi.library/?action=browse&source=' + src_a.id + ',return)'
    ]

    # Removing a server in servers domain returns CHANGED, refreshes list in loop, and fires Container.Refresh once on exit.
    ui_context.shown.clear()
    ui_context.builtins.clear()
    ui_context.selections = [2, 2, -1]  # servers domain -> 家庭服 A -> 移除服务器连接 -> exit servers domain
    ui_context.confirmations = [True]
    chg_outcome = cloud_hub.show_accounts(ui_context.dialog, domain='servers')
    assert chg_outcome == cloud_hub.CHANGED
    assert [s.id for s in ui_context.store.sources()] == [src_b.id]
    assert ui_context.builtins == ['Container.Refresh']


def test_s03_library_root_media_server_filter_and_unknown_kind_rejection(tmp_path, monkeypatch):
    lib_path = ROOT / 'addons/plugin.video.bobbi.library/default.py'
    added_items = []
    ended = []
    builtins = []
    categories = []

    class FakeListItem:
        def __init__(self, label=''):
            self.label = label
            self.label2 = ''
            self.props = {}

        def setLabel2(self, val):
            self.label2 = val

        def setProperty(self, k, v):
            self.props[k] = v

        def setInfo(self, *args):
            pass

        def setContentLookup(self, *args):
            pass

        def setArt(self, *args):
            pass

    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(abortRequested=lambda: False),
        executebuiltin=builtins.append,
        LOGWARNING=2,
        log=lambda *a: None,
    ))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        ListItem=FakeListItem,
        Dialog=lambda: SimpleNamespace(ok=lambda *a: None),
        Window=lambda _: SimpleNamespace(setProperty=lambda *a: None, getProperty=lambda *a: ''),
    ))
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(
        setPluginCategory=lambda h, cat: categories.append(cat),
        setContent=lambda *a: None,
        addDirectoryItems=lambda h, rows, count: added_items.extend(rows),
        endOfDirectory=lambda h, succeeded=True, cacheToDisc=False: ended.append((succeeded, cacheToDisc)),
    ))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(tmp_path)))

    store_path = tmp_path / 'libraries.sqlite3'
    monkeypatch.setattr(library_ui, 'registry', lambda _: Registry(store_path))

    spec = importlib.util.spec_from_file_location('bobbi_library_default_s03', lib_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 1. Zero servers: media_server filter shows only the explicit manage item.
    mod.execute(1, {'action': 'root', 'kind': 'media_server'})
    assert categories[-1] == '媒体服务器'
    assert [row[1].label for row in added_items] == ['管理媒体服务器']
    assert added_items[0][0] == 'plugin://plugin.video.bobbi.library/?action=manage&kind=media_server'

    # Manage route with kind=media_server deep-links to setup accounts servers domain.
    mod.execute(1, {'action': 'manage', 'kind': 'media_server'})
    assert builtins == ['RunScript(script.bobbi.setup,accounts,servers)']

    # 2. Mixed sources (VFS + Catalog + 2 Emby + 1 Jellyfin): filtered root lists ONLY media_server rows!
    reg = Registry(store_path)
    try:
        nas = vfs_source('客厅 NAS', 'smb://nas.local/Movies')
        cat = Source('c' * 32, '直链列表', 'catalog', '',
                     items=(Item(id='1', title='Film', url='https://example.com/1.mkv'),))
        emby_a = Source('1' * 32, 'Emby 主账号', 'media_server', 'http://127.0.0.1:8096',
                        password='tok-1', metadata=dict(schema=1, provider='emby', user_id='u1', server_id='s1'))
        emby_b = Source('2' * 32, 'Emby 家人', 'media_server', 'http://127.0.0.1:8096',
                        password='tok-2', metadata=dict(schema=1, provider='emby', user_id='u2', server_id='s1'))
        jf = Source('3' * 32, 'Jellyfin 书房', 'media_server', 'http://127.0.0.1:8097',
                    password='tok-jf', metadata=dict(schema=1, provider='jellyfin', user_id='ujf', server_id='sjf'))
        reg.save(nas)
        reg.save(cat)
        reg.save(emby_a, activate_emby=reg.emby_binding()[1])
        reg.save(emby_b, activate_emby=reg.emby_binding()[1])
        reg.save(jf)
        active_before = reg.emby_binding()
    finally:
        reg.close()

    added_items.clear()
    mod.execute(1, {'action': 'root', 'kind': 'media_server'})
    labels = [row[1].label for row in added_items]
    assert labels == ['管理媒体服务器', 'Emby 主账号', 'Emby 家人', 'Jellyfin 书房']
    emby_b_item = next(row[1] for row in added_items if row[1].label == 'Emby 家人')
    assert '当前浏览账号' in emby_b_item.label2

    # Unfiltered root keeps all sources + native_pan + personal_catalog.
    added_items.clear()
    mod.execute(1, {'action': 'root'})
    unfiltered_labels = [row[1].label for row in added_items]
    assert '客厅 NAS' in unfiltered_labels and '直链列表' in unfiltered_labels
    assert '个人云盘' in unfiltered_labels and '影视海报库' in unfiltered_labels

    # Unknown kind or unexpected query keys fail explicitly, never falling back to unfiltered root.
    for invalid_params in (
        {'action': 'root', 'kind': 'vfs'},
        {'action': 'root', 'kind': ''},
        {'action': 'root', 'kind': 'unknown'},
        {'action': 'root', 'kind': 'media_server', 'extra': '1'},
        {'action': 'manage', 'kind': 'vfs'},
    ):
        with pytest.raises(LibraryError, match='INVALID_VALUE'):
            mod.execute(1, invalid_params)

    # Confirm emby_binding was never mutated by listing or route generation.
    reg2 = Registry(store_path)
    try:
        assert reg2.emby_binding() == active_before
    finally:
        reg2.close()

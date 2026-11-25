"""Juku 4-domain account convergence: single hub dispatch, Emby active switch, shared QR UI."""
from contextlib import nullcontext
from copy import deepcopy
from functools import partial
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from bobbi_core.account_scope import AccountError, validate_snapshot
from bobbi_platform import (
    account_dialog,
    account_manager,
    ce_glass_boot,
    cloud_hub,
    cloud_ui,
    glass_settings,
    library_ui,
    pan_ui,
    runtime,
    server_ui,
)
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.emby_session import EmbyInvalidationHub, EmbySessionReporter, TICKS_PER_SECOND
from bobbi_platform.host import Host
from bobbi_platform.libraries import Registry
from bobbi_platform.owned_playback import emby_source_scope
from bobbi_platform.pan_accounts import PanAccounts, PanError
from bobbi_platform.pan_http import credentials as pan_credentials
from bobbi_platform.pan_service import PanService
from bobbi_platform.playback_accounts import PlaybackAccounts
from bobbi_platform.server_accounts import Accounts as ServerAccounts
from bobbi_platform.source_streams import SourceStreams


def test_n01a_cloud_hub_single_dispatcher_preserves_progressive_rows_and_ipc_budget(monkeypatch):
    calls = []
    dispatched = []

    def fake_call(action, body, timeout=None):
        calls.append((action, dict(body)))
        return {'authenticated': True, 'preparation': {'state': 'NOT_CONFIGURED'}}

    monkeypatch.setattr(cloud_hub, 'call', fake_call)
    monkeypatch.setattr(cloud_hub.cd2_mounts, 'discover', lambda: ())

    orig_dispatch = cloud_hub._dispatch_action

    def spy_dispatch(action, dialog, value, mounts=()):
        dispatched.append(action)
        if action in ('account', 'native', 'files'):
            return True
        return orig_dispatch(action, dialog, value, mounts)

    monkeypatch.setattr(cloud_hub, '_dispatch_action', spy_dispatch)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: False)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: None))

    seen_menus = []

    class Dialog:
        def __init__(self, picks):
            self.picks = list(picks)

        def select(self, title, rows, **kwargs):
            seen_menus.append((title, list(rows)))
            return self.picks.pop(0)

    # Overview -> Details -> Native multi-pan -> exits cleanly via shared _dispatch_action
    dialog = Dialog([3, 6])
    assert cloud_hub.show(dialog) is True
    assert len(seen_menus) == 2
    assert seen_menus[0][0] == '网盘账号与连接' and len(seen_menus[0][1]) == 6
    assert seen_menus[1][0] == '网盘详细管理' and len(seen_menus[1][1]) == 8
    assert dispatched == ['details', 'native']
    assert calls == [('cloud_status', {}), ('cloud_status', {})]


def test_n01b_emby_multi_account_ui_switch_inflight_playback_isolation_and_removal(tmp_path, monkeypatch):
    def fake_verify_factory(key, values):
        uid = values['token'].split('-')[-1]
        return SimpleNamespace(
            session=SimpleNamespace(budget=lambda _: nullcontext()),
            verify=lambda: ('srv-shared', uid),
        )

    servers = ServerAccounts(tmp_path)
    scope_a0 = servers.register('emby', '家庭成员A', 'http://127.0.0.1:8096', 'tok-ua', client_factory=fake_verify_factory)
    scope_b0 = servers.register('emby', '家庭成员B', 'http://127.0.0.1:8096', 'tok-ub', client_factory=fake_verify_factory)

    host = Host(tmp_path)
    host.accounts = AccountManager(tmp_path / '115-os_linux.json')
    host.pans = PanService(tmp_path, host.accounts, servers=servers, client_factory=fake_verify_factory)
    monkeypatch.setattr(runtime, 'profile', lambda **kwargs: tmp_path / 'runtime.json')
    host.runtime.start()

    pb_accounts = PlaybackAccounts(host.accounts, lambda: host.pans, registry_root=tmp_path)
    streams = SourceStreams(tmp_path, lambda: True)

    reported_sessions = []

    def session_factory(saved):
        def _req(path, **kw):
            reported_sessions.append((saved['user_id'], path, kw.get('data', {}).get('PositionTicks')))
            return {}

        return SimpleNamespace(budget=lambda *_: nullcontext(), request=_req)

    hub = EmbyInvalidationHub(tmp_path)
    reporter = EmbySessionReporter(
        tmp_path,
        hub,
        client_loader=lambda sid, gen: __import__(
            'bobbi_platform.emby_session', fromlist=['_load_emby_client']
        )._load_emby_client(tmp_path, sid, gen, session_factory=session_factory),
        start_worker=False,
    )

    store = Registry(tmp_path / 'libraries.sqlite3')
    try:
        # Initially B is active because B was registered second. Switch active browse to A via server_ui.manage()!
        src_a, rev_a_initial = store.source_snapshot(scope_a0['source_id'])
        src_b, _ = store.source_snapshot(scope_b0['source_id'])

        dialogs = []

        class SwitchDialog:
            def __init__(self, choice, yes=True):
                self.choice = choice
                self.yes = yes
                self.menus = []

            def select(self, heading, options):
                self.menus.append((heading, list(options)))
                return self.choice

            def ok(self, title, body):
                dialogs.append((title, body))

            def yesno(self, title, body):
                return self.yes

        # 1. Switch B -> A through server_ui.manage() choice 3 ("设为当前浏览账号")
        dlg_switch_a = SwitchDialog(3)
        assert server_ui.manage(dlg_switch_a, store, src_a) == server_ui.CHANGED
        assert any('设为当前浏览账号' in opt for opt in dlg_switch_a.menus[0][1])
        active_now, _ = store.emby_binding()
        assert active_now is not None and active_now.id == src_a.id
        assert dialogs[-1][0] == '已切换当前浏览账号'

        # Clicking again when A is already active is idempotent and sends zero mutation IPC
        dialogs.clear()
        dlg_idempotent = SwitchDialog(3)
        assert server_ui.manage(dlg_idempotent, store, src_a) == server_ui.CANCELLED
        assert any('当前浏览账号 · 已启用' in opt for opt in dlg_idempotent.menus[0][1])
        assert dialogs[-1][0] == '当前浏览账号'

        # 2. Start an in-flight Emby playback session on A!
        _, rev_a_playing = store.source_snapshot(src_a.id)
        emby_scope_a = emby_source_scope(
            source_id=src_a.id,
            generation=rev_a_playing,
            server_id='srv-shared',
            user_id='ua',
        )
        assert pb_accounts.is_current(emby_scope_a) is True
        assert streams.source({'source_id': src_a.id, 'generation': rev_a_playing}).id == src_a.id

        meta_a = {
            'provider': 'emby',
            'source_id': src_a.id,
            'source_generation': rev_a_playing,
            'server_id': 'srv-shared',
            'user_id': 'ua',
            'item_id': 'movie-42',
            'media_source_id': 'ms-42',
            'play_session_id': 'ps-inflight-a',
        }
        req_id = 'a' * 32
        assert reporter.on_playback_event({
            'event': 'AV_START',
            'request_id': req_id,
            'position': 120.0,
            'duration': 3600.0,
            'observed_clock': True,
            'data': {'_owned_source': meta_a},
        }) is True
        reporter.drain_once(flush_pending=False)
        assert reported_sessions == [('ua', '/Sessions/Playing', 120 * TICKS_PER_SECOND)]

        # 3. While A is playing, switch active browse from A -> B via server_ui.manage()!
        dialogs.clear()
        src_b_cur = store.get(src_b.id)
        assert server_ui.manage(SwitchDialog(3), store, src_b_cur) == server_ui.CHANGED
        active_after, _ = store.emby_binding()
        assert active_after is not None and active_after.id == src_b.id

        # Generic PanService 'emby' active scope is now B (not A), BUT A's in-flight playback scope,
        # stream Range validator, explicit browse bookmark, and EmbySessionReporter remain bound to A!
        assert servers.snapshot('emby')['source_id'] == src_b.id
        assert pb_accounts.is_current(emby_scope_a) is True
        assert streams.source({'source_id': src_a.id, 'generation': rev_a_playing}).id == src_a.id

        builtins = []
        monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(executebuiltin=builtins.append))
        assert server_ui.browse(SwitchDialog(0), src_a) is True
        assert server_ui.manage(SwitchDialog(0), store, src_a) == server_ui.NAVIGATED
        assert 'source=' + src_a.id in builtins[0]

        # Pause, backward seek, and stop on A's playing session report strictly to 'ua', never 'ub'!
        reporter.on_playback_event({
            'event': 'PROGRESS',
            'request_id': req_id,
            'position': 300.0,
            'duration': 3600.0,
            'paused': True,
            'trigger': 'Pause',
            'observed_clock': True,
            'data': {'_owned_source': meta_a},
        })
        reporter.drain_once(flush_pending=False)
        reporter.on_playback_event({
            'event': 'TERMINAL',
            'request_id': req_id,
            'position': 240.0,
            'duration': 3600.0,
            'reason': 'STOP',
            'observed_clock': True,
            'data': {'_owned_source': meta_a},
        })
        reporter.drain_once(flush_pending=False)
        assert all(u == 'ua' for u, _, _ in reported_sessions)
        progress_calls = [(p, t) for _, p, t in reported_sessions if p.startswith('/Sessions/')]
        assert progress_calls == [
            ('/Sessions/Playing', 120 * TICKS_PER_SECOND),
            ('/Sessions/Playing/Progress', 300 * TICKS_PER_SECOND),
            ('/Sessions/Playing/Stopped', 240 * TICKS_PER_SECOND),
        ]

        # 4. Ambiguous IPC error after Host already committed switch re-reads Registry and confirms!
        orig_call = server_ui.call

        def commit_then_timeout(action, body, timeout=8):
            res = orig_call(action, body, timeout=timeout)
            if action == 'pan_server_activate_emby':
                raise TimeoutError('simulated lost IPC reply after commit')
            return res

        monkeypatch.setattr(server_ui, 'call', commit_then_timeout)
        dialogs.clear()
        assert server_ui.manage(SwitchDialog(3), store, store.get(src_a.id)) == server_ui.CHANGED
        assert store.emby_binding()[0].id == src_a.id
        assert dialogs[-1][0] == '已切换当前浏览账号'
        monkeypatch.setattr(server_ui, 'call', orig_call)

        # 5. Removing active Emby A leaves inactive marker: remaining Emby B is NEVER auto-activated!
        assert server_ui.manage(SwitchDialog(2, yes=True), store, store.get(src_a.id)) == server_ui.CHANGED
        assert [s.id for s in store.sources()] == [src_b.id]
        assert store.emby_binding()[0] is None
        assert not servers.snapshot('emby')['authenticated']
        assert pb_accounts.is_current(emby_scope_a) is False
    finally:
        store.close()
        reporter.close()
        hub.close()
        host.pans.close()
        host.runtime.close()


def test_n01c_shared_login_dialog_and_no_private_cross_imports(tmp_path, monkeypatch):
    import ast

    pan_tree = ast.parse((Path(pan_ui.__file__)).read_text(encoding='utf-8'))
    for node in ast.walk(pan_tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'cloud_ui':
            imported_names = {alias.name for alias in node.names}
            assert '_refresh_account_view' not in imported_names

    events = []

    class Window:
        def __init__(self, *args):
            self.closed = 0
            self.cancelled = False
            self.image = ''
            self.message = ''

        def show(self):
            events.append('show')

        def close(self):
            self.closed += 1
            events.append('close')

        def set_status(self, value):
            self.message = value

        def set_image(self, value):
            self.image = str(value)
            events.append(('image_exists', Path(value).parent.is_dir()))

    monkeypatch.setattr(account_dialog, 'create', lambda image, title='', instruction='': Window())
    monkeypatch.setitem(
        sys.modules,
        'xbmc',
        SimpleNamespace(
            Monitor=lambda: SimpleNamespace(abortRequested=lambda: False, waitForAbort=lambda s: False),
            executebuiltin=lambda cmd: events.append(('builtin', cmd)),
        ),
    )
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(tmp_path)))

    # Exercise pan_ui.login through shared account_dialog.login_dialog + late commit receipt on cancel
    row = {
        'provider': 'quark',
        'account': {'provider': 'quark', 'account_id': '', 'epoch': 0, 'authenticated': False},
        'capabilities': ['qr_login', 'list_files'],
    }
    png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='

    def fake_pan_call(action, body, timeout=28):
        if action == 'pan_login_begin':
            return {'state': 'waiting', 'qr_png': png_b64}
        if action == 'pan_login_poll':
            raise PanError('PAN_QR_CANCELLED')
        if action == 'pan_login_cancel':
            return {'state': 'committed'}
        raise AssertionError(action)

    monkeypatch.setattr(pan_ui, 'call', fake_pan_call)
    dialogs = []
    dlg = SimpleNamespace(ok=lambda *args: dialogs.append(args) or events.append(('ok', args[0])))
    assert pan_ui.login(row, dlg) is False
    # Window closed and temp QR dir removed BEFORE error/late-commit dialogs are shown!
    assert events.index('close') < events.index(('ok', '未确认登录结果'))
    assert ('builtin', 'Container.Refresh') in events
    assert dialogs[-1][0] == '登录已保存'
    assert not list(tmp_path.glob('bobbi-pan-qr-*'))


def test_n01d_validate_snapshot_single_contract_and_ce2185_liquid_glass_guard():
    assert account_manager.validate_snapshot is validate_snapshot
    assert account_manager.AccountError is AccountError
    assert ce_glass_boot.ZIP_JUKU_CONVERGENCE == 2026102185
    assert ce_glass_boot.ZIP_JUKU_CONVERGENCE in ce_glass_boot.OPT_IN_SEQUENCES
    assert ce_glass_boot.PRODUCTS[2026102185] == {
        'skin.bobbi.cinema': '0.1.40',
        'plugin.video.bobbi': '0.1.98',
        'script.module.bobbi.core': '0.1.89',
        'script.module.bobbi.platform': '0.1.99',
    }
    raw_boot = Path(ce_glass_boot.__file__).read_bytes()
    assert hashlib.sha256(raw_boot).hexdigest() == glass_settings.GUARD_HASH
    assert '810db4ef0e4ad787cc450e651d068c0926141050bc9fdb2055cfa99f0caedff6' in glass_settings.OLD_UNITS

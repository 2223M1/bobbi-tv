"""Home presentation uses real unified/server accounts, including empty scopes."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from bobbi_core.library_contract import Source
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanAccounts
from bobbi_platform.pan_115_accounts import Accounts as UnifiedAccounts
from bobbi_platform.server_accounts import Accounts as ServerAccounts


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'addons/plugin.video.bobbi'))
    spec = importlib.util.spec_from_file_location('home_server_scope_test',
        ROOT / 'addons/plugin.video.bobbi/lib/cinema/focus_anchor.py')
    focus = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(focus)
    legacy = AccountManager(tmp_path / 'account.json')
    native = PanAccounts(tmp_path / 'pans.json', {})
    servers = ServerAccounts(tmp_path)
    accounts = UnifiedAccounts(native, legacy, servers)
    props, writes, opens = {}, [], []
    inject = [None]

    def set_property(key, value):
        props[key] = value
        writes.append((key, value))
        if inject[0] is not None:
            inject[0](key, value)

    registry = servers._registry
    def open_registry():
        opens.append(True)
        return registry()
    monkeypatch.setattr(servers, '_registry', open_registry)
    window = SimpleNamespace(getProperty=lambda key: props.get(key, ''), setProperty=set_property)
    host = SimpleNamespace(accounts=legacy, pans=SimpleNamespace(accounts=accounts))
    lifecycle = focus.HomeRailLifecycle(host, window)
    value = SimpleNamespace(lifecycle=lifecycle, servers=servers, accounts=accounts,
        props=props, writes=writes, opens=opens, inject=inject)
    yield value
    inject[0] = None
    lifecycle.close()


def save_server(home, provider='emby'):
    # Local Registry fixture only. No server login, source request or credentials
    # are obtained from the environment.
    store = Registry(home.servers.path)
    try:
        store.save(Source('a' * 32, 'Fixture server', 'media_server', 'http://127.0.0.1:8096',
            password='' if provider == 'plex' else 'fixture-only', metadata=dict(schema=1, provider=provider,
                server_id='fixture-server', user_id='fixture-user')))
    finally:
        store.close()


def remove_server(home):
    store = Registry(home.servers.path)
    try:
        store.remove('a' * 32)
    finally:
        store.close()


@pytest.mark.parametrize('unavailable', ['unregistered', 'plex_binding_missing', 'profile_revoked'])
def test_unchanged_real_empty_server_scopes_do_not_refresh_every_owner_tick(home, unavailable):
    if unavailable == 'plex_binding_missing':
        save_server(home, 'plex')
    elif unavailable == 'profile_revoked':
        save_server(home)
        home.servers.current = lambda: False
    home.lifecycle.tick()
    assert home.lifecycle.dirty is False
    assert all(home.props['Bobbi.Rail.Scope.' + provider] == '' for provider in ('plex', 'jellyfin', 'emby'))
    before = dict(home.props)
    home.writes.clear()
    home.opens.clear()
    for _ in range(50):
        home.lifecycle.tick()
    assert home.props == before
    assert home.writes == home.opens == []


def test_server_login_logout_still_revoke_synchronously_and_settle(home):
    home.lifecycle.tick()
    save_server(home)
    home.servers.snapshot('emby')
    assert home.lifecycle.dirty
    home.lifecycle.tick()
    assert home.props['Bobbi.Rail.Scope.emby'] and home.props['Bobbi.Rail.Account.emby']
    remove_server(home)
    home.servers.snapshot('emby')
    assert home.props['Bobbi.Rail.Scope.emby'] == home.props['Bobbi.Rail.Account.emby'] == ''
    assert home.lifecycle.dirty
    home.lifecycle.tick()
    assert home.lifecycle.dirty is False


def test_authenticated_server_publish_keeps_final_cas_after_snapshot(home, monkeypatch):
    home.lifecycle.tick()
    save_server(home)
    home.servers.snapshot('emby')
    original = home.accounts.run_if_current
    called = []

    def remove_before_cas(expected, operation, authenticated=True):
        if expected['provider'] == 'emby' and expected['authenticated']:
            called.append(True)
            remove_server(home)
        return original(expected, operation, authenticated)

    monkeypatch.setattr(home.accounts, 'run_if_current', remove_before_cas)
    home.lifecycle.tick()
    assert called == [True]
    assert home.props['Bobbi.Rail.Scope.emby'] == home.props['Bobbi.Rail.Account.emby'] == ''
    assert home.lifecycle.dirty  # Retry the new empty scope, never publish stale authority.
    home.lifecycle.tick()
    assert home.lifecycle.dirty is False


def test_login_callback_during_empty_clear_is_kept_for_next_tick(home):
    home.lifecycle.tick()
    fired = []

    def login_during_clear(key, value):
        if key == 'Bobbi.Rail.Scope.emby' and value == '' and not fired:
            fired.append(True)
            save_server(home)
            home.servers.snapshot('emby')  # Actual account notification after captured empty scope.

    home.inject[0] = login_during_clear
    home.lifecycle.dirty = True
    home.lifecycle.tick()
    assert fired == [True]
    assert home.lifecycle.dirty
    # A late empty write can hide a card, but cannot publish old/new authority.
    assert home.props['Bobbi.Rail.Scope.emby'] == home.props['Bobbi.Rail.Account.emby'] == ''
    home.inject[0] = None
    home.lifecycle.tick()
    assert home.lifecycle.dirty is False
    assert home.props['Bobbi.Rail.Scope.emby'] and home.props['Bobbi.Rail.Account.emby']

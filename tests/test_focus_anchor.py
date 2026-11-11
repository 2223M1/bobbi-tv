"""Real scope callback wiring and stable paths used by native Kodi lists.

No test fabricates a Python input interceptor. Native path reidentification is
separately pinned to the inspected Kodi implementation in the T10 receipt.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def focus(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'addons/plugin.video.bobbi'))
    spec = importlib.util.spec_from_file_location('focus_anchor_test',
        ROOT/'addons/plugin.video.bobbi/lib/cinema/focus_anchor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_paths_bind_type_and_id_not_locale_art_or_sort(focus):
    assert focus.public_card('movies', '00042') == 'tmdb:movie:42'
    assert focus.public_target('movies', '42') == focus.public_target('movie', 42)
    assert focus.public_target('movie', 42) != focus.public_target('tv', 42)
    assert all(word not in focus.public_target('tv', 42) for word in ('title=', 'original=', 'fanart=', 'revision='))


def test_resume_card_keeps_exact_version_but_ignores_progress_and_transport(focus):
    row = dict(prepared_resource_id='opaque-source-file-1', _account={'epoch': 1})
    key = focus.resume_key(row)
    assert focus.resume_key(dict(row, progress=80, url='https://signed.invalid/changed', title='new')) == key
    assert focus.resume_key(dict(row, prepared_resource_id='opaque-source-file-2')) != key
    assert focus.resume_key(dict(row, _account={'epoch': 2})) != key
    assert focus.resume_key(dict(title='name', url='https://temporary.invalid', progress=40)) == ''


class Accounts:
    def __init__(self, values, legacy=False):
        self.values, self.legacy = values, legacy
        self.lock, self.listeners = RLock(), []

    def snapshot(self, provider='115'):
        return deepcopy(self.values.get(provider, dict(provider=provider, account_id='', epoch=0, authenticated=False)))

    def subscribe(self, fn):
        self.listeners.append(fn)
        return lambda: self.listeners.remove(fn)

    def change(self, provider, **changes):
        with self.lock:
            previous = self.snapshot(provider)
            self.values[provider] = dict(previous, **changes)
            for fn in tuple(self.listeners):
                fn(previous, self.snapshot(provider))


@pytest.fixture
def lifecycle(focus):
    props = {}
    window = SimpleNamespace(getProperty=lambda key: props.get(key, ''),
        setProperty=lambda key, value: props.update({key: value}))
    legacy = Accounts({'115': dict(account_id='115:'+'a'*64, epoch=1, authenticated=True)}, legacy=True)
    pans = Accounts({'quark': dict(provider='quark', account_id='quark:'+'b'*64, epoch=1, authenticated=True)})
    host = SimpleNamespace(accounts=legacy, pans=SimpleNamespace(accounts=pans))
    controller = focus.HomeRailLifecycle(host, window)
    controller.tick()
    return SimpleNamespace(controller=controller, host=host, legacy=legacy, pans=pans, props=props)


def test_scope_revoked_synchronously_before_next_tick_and_new_epoch_repopulates(lifecycle):
    state = lifecycle
    key = 'Bobi.Rail.Scope.quark'
    old = state.props[key]
    assert old
    state.pans.change('quark', epoch=2)
    assert state.props[key] == ''  # callback, not a ten-second poll
    state.controller.tick()
    assert state.props[key] and state.props[key] != old
    state.pans.change('quark', epoch=3, authenticated=False, account_id='')
    state.controller.tick()
    assert state.props[key] == '' and state.props['Bobi.Rail.Account.quark'] == ''


def test_existing_115_account_changes_and_shutdown_also_revoke(lifecycle):
    state = lifecycle
    assert state.props['Bobi.Rail.Scope.115']
    state.legacy.change('115', epoch=2)
    assert state.props['Bobi.Rail.Scope.115'] == ''
    state.controller.tick()
    state.controller.close()
    assert not state.pans.listeners and not state.legacy.listeners
    assert all(not value for key, value in state.props.items() if '.Scope.' in key or '.Account.' in key)


def test_unchanged_tick_never_refreshes_or_polls_focus(lifecycle):
    before = dict(lifecycle.props)
    for _ in range(50):
        lifecycle.controller.tick()
    assert lifecycle.props == before
    source = (ROOT/'addons/plugin.video.bobbi/lib/cinema/focus_anchor.py').read_text(encoding='utf-8')
    assert 'executebuiltin(' not in source and 'setFocus(' not in source and 'getInfoLabel(' not in source


def test_six_states_are_explicit_provider_receipts(focus):
    from lib.cinema.frontend_contract import RAIL_STATES, rail_properties
    assert RAIL_STATES == {'loading', 'ready', 'empty', 'stale', 'error', 'auth_required'}
    assert rail_properties('error', reason='CATALOG_UNAVAILABLE')['Bobi.Rail.State'] == 'error'
    with pytest.raises(ValueError):
        rail_properties('zero_items')
    with pytest.raises(ValueError):
        rail_properties('error', reason='https://private.invalid')


def test_one_row_revision_does_not_refresh_another(focus):
    props = {'Bobi.Rail.Revision.popular_tv': '8'}
    window = SimpleNamespace(getProperty=lambda key: props.get(key, ''),
        setProperty=lambda key, value: props.update({key: value}))
    focus.bump(window, 'personal_library')
    assert props == {'Bobi.Rail.Revision.popular_tv': '8', 'Bobi.Rail.Revision.personal_library': '1'}
    with pytest.raises(ValueError):
        focus.bump(window, 'Home);PlayMedia(x)')

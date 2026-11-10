"""Actual serialized owner + account store, simulated native receipts only."""
from copy import deepcopy

import pytest

from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_platform.host import Host
from bobbi_platform.pan_accounts import PanError
from test_playback_authority import Native, row, select


def credential(provider):
    return dict(provider=provider, subject='123', access_token='fixture-access',
                refresh_token='fixture-refresh', device_id='fixture-device', expires_at=9999999999)


@pytest.fixture
def personal(tmp_path):
    host = Host(tmp_path)
    host.start()
    pans = host._pans()
    account = pans.accounts.install(credential('xunlei'), pans.accounts.snapshot('xunlei'))
    native = Native()
    owner = PlaybackAuthority(native)
    owner.configure_accounts(host.playback_accounts)
    state = owner.dispatch(dict(operation='snapshot'))
    state = owner.dispatch(dict(operation='select', boot_id=state['boot_id'], epoch=state['epoch'],
        request_id='a'*32, selection_identity='personal-file', account_scope=account))
    args = dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id='a'*32)
    yield host, pans, account, native, owner, args
    host.close()


def bind_and_play(personal):
    host, pans, account, native, owner, args = personal
    assert owner.dispatch(dict(args, operation='bind_file', selection_identity='personal-file',
        file_identity='personal-file|transport', url_sha256='b'*64,
        file_evidence='USER_CONFIRMED_FILE')) == {'bound': True}
    assert owner.dispatch(dict(args, operation='claim_start', route='player_play')) == {'status': 'CLAIMED'}
    native.current = row(args['request_id'], 'personal-file|transport', url_sha256='b'*64)
    owner.refresh()


def test_other_drive_logout_preserves_personal_playback_own_logout_stops_exact_instance(personal):
    host, pans, account, native, owner, args = personal
    bind_and_play(personal)
    other = pans.accounts.install(credential('guangya'), pans.accounts.snapshot('guangya'))
    pans.accounts.logout(other)
    assert not owner.account_changed() and native.commands == []
    pans.accounts.logout(account)
    assert owner.account_changed()
    assert native.commands[-1]['action'] == 'stop'
    assert native.commands[-1]['native_instance'] == native.current['native_instance']
    assert owner.owner.desired['cancelled']


def test_logout_before_bind_rejects_late_personal_result(personal):
    host, pans, account, native, owner, args = personal
    pans.accounts.logout(account)
    with pytest.raises(PanError, match='ACCOUNT_CHANGED'):
        bind_and_play(personal)
    assert not native.commands


def test_late_pan_logout_never_stops_new_external_selection(personal):
    host, pans, account, native, owner, args = personal
    bind_and_play(personal)
    select(owner, 'external-new')
    native.current = row('c'*32, 'external', url_sha256='c'*64)
    before = deepcopy(native.commands)
    pans.accounts.logout(account)
    assert not owner.account_changed() and native.commands == before

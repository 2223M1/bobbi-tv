"""New providers must never weaken or impersonate the existing 115 owner."""
from copy import deepcopy
from functools import partial
import json
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bobbi_platform.account_manager import AccountError, validate_snapshot
from bobbi_platform.pan_accounts import PanAccounts, PanError, empty_scope, scope
from bobbi_platform.pan_http import credentials
from bobbi_platform.pan_service import PanService


def saved(provider='quark', uid='fixture-user', session='fixture-session'):
    return dict(provider=provider, cookies=[dict(name=name, value=value,
        domain='.' + ('quark.cn' if provider == 'quark' else 'uc.cn'), path='/')
        for name, value in [('__uid', uid), ('__pus', session)]])


@pytest.fixture
def accounts(tmp_path):
    return PanAccounts(tmp_path / 'accounts.json', {p: partial(credentials, p) for p in ('quark', 'uc')})


def test_provider_identity_and_epochs_are_independent(accounts):
    quark = accounts.install(saved(), accounts.snapshot('quark'))
    uc = accounts.install(saved('uc'), accounts.snapshot('uc'))
    assert quark['account_id'] != uc['account_id']
    accounts.logout(quark)
    assert accounts.is_current(uc)
    assert not accounts.is_current(quark)
    with pytest.raises(AccountError):
        validate_snapshot(quark)
    with pytest.raises(PanError):
        scope(dict(account_id='', epoch=0, authenticated=False))


def test_tombstones_survive_restart_same_user_never_resurrects_old_scope(accounts):
    first = accounts.install(saved(), accounts.snapshot('quark'))
    logged_out = accounts.logout(first)
    restarted = PanAccounts(accounts.path, accounts.validators)
    assert restarted.snapshot('quark') == logged_out
    last = restarted.install(saved(), logged_out)
    assert last['account_id'] == first['account_id'] and last['epoch'] > first['epoch']
    assert not restarted.is_current(first)


def test_same_account_relogin_revokes_old_login_attempt_but_renew_does_not(accounts):
    events = []
    accounts.subscribe(lambda a, b: events.append((a, b)))
    first = accounts.install(saved(), accounts.snapshot('quark'))
    assert accounts.renew(saved(session='renewed'), first) == first
    assert len(events) == 1
    second = accounts.install(saved(session='login2'), first)
    assert second['epoch'] == first['epoch'] + 1
    with pytest.raises(PanError, match='CHANGED'):
        accounts.install(saved(session='late'), first)
    with pytest.raises(PanError, match='IDENTITY_CHANGED'):
        accounts.renew(saved(uid='other-user'), second)


def test_status_and_returned_credentials_are_copies(accounts):
    result = accounts.install(saved(), accounts.snapshot('quark'))
    result['epoch'] = 99
    current = accounts.snapshot('quark')
    assert current['epoch'] == 1 and 'session' not in json.dumps(current)
    value = accounts.credentials(current)
    value['cookies'][0]['value'] = 'tampered'
    assert accounts.credentials(current)['cookies'][0]['value'] == 'fixture-user'


def test_unknown_adapter_and_cross_provider_credentials_are_rejected(accounts):
    for provider in ('aliyun', 'baidu', '123', '189', '139', 'xunlei', 'guangya'):
        with pytest.raises(PanError, match='ADAPTER_UNAVAILABLE'):
            accounts.install(saved(), accounts.snapshot(provider))
    with pytest.raises(PanError):
        accounts.install(saved(), accounts.snapshot('uc'))
    with pytest.raises(PanError):
        accounts.snapshot('115')


@pytest.mark.parametrize('field,value', [('epoch', True), ('epoch', -1), ('epoch', 2**63),
    ('account_id', 'quark:x'), ('authenticated', 1), ('provider', '../quark')])
def test_malformed_scope_rejected(field, value):
    with pytest.raises(PanError):
        scope(dict(empty_scope('quark'), **{field: value}))


@pytest.mark.parametrize('change', [lambda c: c['cookies'][0].update(domain='.uc.cn'),
    lambda c: c['cookies'][0].update(value='uid\r\nInjected: value'),
    lambda c: c['cookies'].append(dict(c['cookies'][0])),
    lambda c: c['cookies'][0].update(value='x' * 4097),
    lambda c: c['cookies'][0].update(name='__pus')])
def test_credentials_fail_closed(change):
    value = saved()
    change(value)
    with pytest.raises(PanError):
        credentials('quark', value)


def test_atomic_save_failure_does_not_change_memory_or_notify(accounts, monkeypatch):
    import bobbi_platform.pan_accounts as module
    expected = accounts.snapshot('quark')
    observed = []
    accounts.subscribe(lambda *a: observed.append(a))
    def fail(*a):
        raise OSError('fixture')
    monkeypatch.setattr(module, '_write', fail)
    with pytest.raises(OSError):
        accounts.install(saved(), expected)
    assert accounts.snapshot('quark') == expected and not observed


class Flow:
    def __init__(self):
        self.begins = self.polls = 0
        self.before_poll = lambda: None
    def begin(self):
        self.begins += 1
        return 'https://su.quark.cn/fixture-qr'
    def poll(self):
        self.polls += 1
        self.before_poll()
        return 'ready', saved()
    def cancel(self):
        pass


@pytest.fixture
def service(tmp_path, accounts):
    flow = Flow()
    service = PanService(tmp_path, SimpleNamespace(snapshot=lambda:
        dict(account_id='', epoch=0, authenticated=False)), accounts=accounts,
        login_factory={'quark': lambda: flow})
    service.fixture_flow = flow
    return service


def begin(service):
    return service.begin('quark', 'a' * 32, service.accounts.snapshot('quark'))


def test_qr_prepare_commit_and_receipt_retry_are_separate(service):
    initial = service.accounts.snapshot('quark')
    first = begin(service)
    assert service.begin('quark', 'a' * 32, initial) == first
    assert service.fixture_flow.begins == 1
    assert service.poll('quark', 'a' * 32)['state'] == 'ready'
    assert service.accounts.snapshot('quark') == initial
    assert 'fixture-session' not in json.dumps(service.status())
    committed = service.commit('quark', 'a' * 32)
    assert service.commit('quark', 'a' * 32) == committed
    assert service.cancel('quark', 'a' * 32) == committed
    assert committed['account']['epoch'] == 1


def test_cancel_in_flight_discards_confirmed_credentials(service):
    begin(service)
    started, finish = Event(), Event()
    def wait():
        started.set()
        assert finish.wait(2)
    service.fixture_flow.before_poll = wait
    replies = []
    worker = Thread(target=lambda: replies.append(service.poll('quark', 'a' * 32)))
    worker.start()
    assert started.wait(2)
    service.cancel('quark', 'a' * 32)
    finish.set()
    worker.join(2)
    assert not worker.is_alive() and replies[0]['state'] == 'cancelled'
    assert not service.accounts.snapshot('quark')['authenticated']
    with pytest.raises(PanError):
        service.commit('quark', 'a' * 32)


def test_logout_revokes_even_pending_login_of_already_logged_out_provider(service):
    begin(service)
    service.logout(service.accounts.snapshot('quark'))
    assert service.poll('quark', 'a' * 32)['state'] in ('cancelled', 'account_changed')
    assert service.fixture_flow.polls == 0


def test_changed_account_and_closed_host_never_commit_late_qr(service):
    begin(service)
    service.poll('quark', 'a' * 32)
    service.accounts.install(saved(uid='other'), service.accounts.snapshot('quark'))
    with pytest.raises(PanError):
        service.commit('quark', 'a' * 32)
    assert service.accounts.credentials(service.accounts.snapshot('quark'))['cookies'][0]['value'] == 'other'
    service.close()
    with pytest.raises(PanError):
        service.dispatch('pan_status', {})


def test_late_directory_is_not_published_after_logout(service):
    expected = service.accounts.install(saved(), service.accounts.snapshot('quark'))
    def listing(*args, **kwargs):
        service.logout(expected)
        return {'items': [{'name': 'private-folder'}]}
    service.client_factory = lambda *args: SimpleNamespace(list_files=listing)
    with pytest.raises(PanError, match='CHANGED'):
        service.list_files(expected, '0', 1)


def test_refresh_evicts_sibling_pages_but_preserves_other_folders_and_accounts(service):
    expected = service.accounts.install(saved(), service.accounts.snapshot('quark'))
    other = service.accounts.install(saved('uc'), service.accounts.snapshot('uc'))
    calls = []
    def factory(provider, credentials):
        def listing(parent, page, **kwargs):
            calls.append((provider, parent, page))
            return dict(items=[], generation=len(calls))
        return SimpleNamespace(list_files=listing)
    service.client_factory = factory
    service.list_files(expected, '0', 1)
    old_second = service.list_files(expected, '0', 2)
    folder = service.list_files(expected, 'folder', 1)
    uc = service.list_files(other, '0', 2)
    service.list_files(expected, '0', 1, refresh=True)
    assert service.list_files(expected, '0', 2) != old_second
    assert service.list_files(expected, 'folder', 1) == folder
    assert service.list_files(other, '0', 2) == uc
    assert calls == [('quark', '0', 1), ('quark', '0', 2), ('quark', 'folder', 1),
                     ('uc', '0', 2), ('quark', '0', 1), ('quark', '0', 2)]


def test_refresh_during_inflight_page_cannot_repopulate_old_cache(service):
    expected = service.accounts.install(saved(), service.accounts.snapshot('quark'))
    started, finish = Event(), Event()
    def listing(parent, page, **kwargs):
        started.set()
        assert finish.wait(2)
        return dict(items=[], stale=True)
    service.client_factory = lambda *args: SimpleNamespace(list_files=listing)
    replies = []
    thread = Thread(target=lambda: replies.append(service.list_files(expected, '0', 2)))
    thread.start()
    try:
        assert started.wait(1)
        with pytest.raises(PanError, match='BUSY'):
            service.list_files(expected, '0', 1, refresh=True)
    finally:
        finish.set()
        thread.join(2)
    assert not thread.is_alive() and replies == [dict(items=[], stale=True)]
    assert not service.directory_cache


def test_ten_targets_do_not_equal_ten_supported_drivers(service):
    rows = service.status()['providers']
    assert len(rows) == 10
    assert {r['provider'] for r in rows if r['capabilities']} == {'115', 'quark'}
    assert 'share_play' not in next(r for r in rows if r['provider'] == 'quark')['capabilities']


def test_expiry_prunes_receipts_and_bound_attempt_count(service):
    now = [10]
    service.clock = lambda: now[0]
    begin(service)
    with pytest.raises(PanError, match='BUSY'):
        service.begin('quark', 'b' * 32, service.accounts.snapshot('quark'))
    now[0] += 241
    service.begin('quark', 'b' * 32, service.accounts.snapshot('quark'))
    assert len(service.attempts) == 1
    with pytest.raises(PanError, match='EXPIRED'):
        service.commit('quark', 'a' * 32)


def test_network_timeout_is_explicit_retry_until_bounded_qr_deadline(service):
    now = [10]
    service.clock = lambda: now[0]
    begin(service)
    def timeout():
        raise PanError('PAN_NETWORK_ERROR')
    service.fixture_flow.poll = timeout
    value = service.dispatch('pan_login_poll', dict(provider='quark', attempt='a'*32))
    assert value == dict(attempt='a'*32, state='retry', reason='network')
    assert not service.accounts.snapshot('quark')['authenticated']
    now[0] += 181
    assert service.dispatch('pan_login_poll', dict(provider='quark', attempt='a'*32))['state'] == 'cancelled'

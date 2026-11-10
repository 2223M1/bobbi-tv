"""Prefetch and EOF UI permission share the real account generation boundary."""
from copy import deepcopy
from threading import Event
from types import SimpleNamespace as NS

import pytest

from bobbi_platform.account_manager import AccountManager
from bobbi_platform import runtime
from lib.cinema import playback_request
from lib.utils.player import next_source_picker as picker
from test_playback_authority import playing
from test_native_continuation_account_guard import credentials
from test_ce2089_shared_search import shared


@pytest.fixture
def scoped_flow(shared, tmp_path, monkeypatch):
    authority, native, parent = playing()
    manager = AccountManager(tmp_path / 'account.json')
    account = manager.install(credentials(), manager.snapshot())
    authority.configure_accounts(manager)
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    authority.refresh()
    monkeypatch.setattr(playback_request, 'call', authority.dispatch)
    previous = runtime.call
    def local(action, body, **kwargs):
        return manager.snapshot() if action == 'account_status' else previous(action, body, **kwargs)
    monkeypatch.setattr(runtime, 'call', local)
    metadata, shown, notices = [], [], []
    def target(data, cancelled):
        metadata.append(deepcopy(data.get('_account')))
        return None if cancelled() else dict(data, tv_data=dict(season=1, episode=2), autoplay=False)
    monkeypatch.setattr(picker, 'target_episode', target)
    monkeypatch.setattr(shared.search.xbmc, 'Monitor', lambda: NS(abortRequested=lambda: False,
        waitForAbort=lambda seconds: Event().wait(seconds)))
    monkeypatch.setattr(shared.search, 'show_source_select', lambda *a, **kw: shown.append((a, kw)) or False)
    monkeypatch.setattr(shared.search, 'notification', lambda *a, **kw: notices.append(a))
    actor = NS(data=dict(mode='tv', ids={'tmdb_id':123}, tv_data=dict(season=1, episode=1),
        title='Fixture', selection_policy='exact', cinema_continuity=True),
        _owner_context=parent, _native_instance=native.current['native_instance'], _cinema_cancel=Event())
    entries = []
    value = NS(authority=authority, native=native, manager=manager, account=account,
        actor=actor, entries=entries, metadata=metadata, shown=shown, notices=notices, shared=shared)
    yield value
    job = getattr(actor, '_cinema_picker_search', None)
    if job:
        job.cancel()
    for entry in entries:
        picker.release(entry['data'])


def completed(flow):
    job = picker.prefetch(flow.actor)
    assert job.finished.wait(3)
    entry = job.snapshot()
    if entry:
        entry[2].thread.join(3)
        assert not entry[2].thread.is_alive()
    return job


def show(flow):
    entry = flow.entries[0]
    return flow.shared.search.show_next_sources(entry['data'], next_picker=entry['next_picker'])


def test_account_capture_precedes_metadata_and_is_the_eof_reservation_scope(scoped_flow):
    flow = scoped_flow
    job = completed(flow)
    assert job.account_scope() == flow.account
    assert flow.metadata == [flow.account]
    assert picker.queue(flow.actor, flow.entries)
    assert flow.entries[0]['data']['_account'] == flow.account
    show(flow)
    assert len(flow.shown) == 1 and flow.native.commands == []


@pytest.mark.parametrize('mutation', ['switch', 'logout', 'logout-login'])
def test_completed_old_account_prefetch_cannot_be_reserved_under_new_account(scoped_flow, mutation):
    flow = scoped_flow
    job = completed(flow)
    assert job.snapshot() is not None
    if mutation == 'switch': flow.manager.install(credentials('456'), flow.account)
    else:
        out = flow.manager.logout(flow.account)
        if mutation == 'logout-login': flow.manager.install(credentials(), out)
    assert not picker.queue(flow.actor, flow.entries)
    assert flow.entries == flow.shown == []
    assert not flow.authority.owner.terminal['consumed']
    assert flow.native.commands == []


def test_old_status_reply_arriving_after_eof_new_account_reservation_cannot_show(scoped_flow, monkeypatch):
    flow = scoped_flow
    entered, unblock = Event(), Event()
    def slow_status(action, body, **kwargs):
        assert action == 'account_status'
        saved = flow.manager.snapshot()
        entered.set()
        assert unblock.wait(3)
        return saved
    monkeypatch.setattr(runtime, 'call', slow_status)
    job = picker.prefetch(flow.actor)
    assert entered.wait(3) and job.account_scope() is None
    new_account = flow.manager.install(credentials('456'), flow.account)
    try:
        assert picker.queue(flow.actor, flow.entries)  # Never wait on capture at EOF.
        assert flow.entries[0]['data']['_account'] == new_account
    finally:
        unblock.set()
    assert job.finished.wait(3)
    assert job.account_scope() == flow.account
    show(flow)
    assert flow.shown == flow.notices == [] and job.closed.is_set()
    assert flow.native.commands == []


def test_account_switch_after_eof_but_before_delayed_capture_cannot_rebind_permit(scoped_flow, monkeypatch):
    flow = scoped_flow
    entered, unblock = Event(), Event()
    def late_status(action, body, **kwargs):
        assert action == 'account_status'
        entered.set()
        assert unblock.wait(3)
        return flow.manager.snapshot()
    monkeypatch.setattr(runtime, 'call', late_status)
    try:
        assert picker.queue(flow.actor, flow.entries)
        assert entered.wait(3)
        flow.manager.install(credentials('456'), flow.account)
    finally:
        unblock.set()
    job = flow.actor._cinema_picker_search
    assert job.finished.wait(3)
    show(flow)
    assert flow.entries[0]['data']['_account'] == flow.account
    assert flow.shown == flow.notices == []


def test_existing_parent_account_is_never_replaced_by_a_new_capture(scoped_flow):
    flow = scoped_flow
    flow.actor.data['_account'] = deepcopy(flow.account)
    flow.manager.install(credentials('456'), flow.account)
    job = completed(flow)
    assert job.account_scope() is None and job.snapshot() is None
    assert flow.metadata == flow.shared.calls == []
    assert not picker.queue(flow.actor, flow.entries)
    assert flow.entries == flow.shown == []


@pytest.mark.parametrize('failure', ['unavailable', 'malformed', 'signed-out'])
def test_failed_capture_never_reads_metadata_or_displays_old_results(scoped_flow, monkeypatch, failure):
    flow = scoped_flow
    def fail_status(*args, **kwargs):
        if failure == 'unavailable': raise OSError('account transport unavailable')
        if failure == 'malformed': return {'account_id': 'invalid'}
        return {'account_id': '', 'epoch': 2, 'authenticated': False}
    monkeypatch.setattr(runtime, 'call', fail_status)
    job = completed(flow)
    assert job.account_scope() is None and job.snapshot() is None
    assert flow.metadata == flow.shared.calls == []
    assert picker.queue(flow.actor, flow.entries)
    show(flow)
    assert flow.shown == flow.notices == []


@pytest.mark.parametrize('stop', ['cancel', 'parent-stop'])
def test_cancel_during_account_capture_cannot_start_metadata_or_provider_work(scoped_flow, monkeypatch, stop):
    flow = scoped_flow
    entered, unblock = Event(), Event()
    def slow_status(*args, **kwargs):
        entered.set()
        assert unblock.wait(3)
        return flow.account
    monkeypatch.setattr(runtime, 'call', slow_status)
    job = picker.prefetch(flow.actor)
    try:
        assert entered.wait(3)
        if stop == 'cancel': job.cancel()
        else: flow.actor._cinema_cancel.set()
    finally:
        unblock.set()
    assert job.finished.wait(3)
    assert job.account_scope() is None and job.snapshot() is None
    assert flow.metadata == flow.shared.calls == []


def test_same_account_credential_renewal_keeps_prefetch_and_ui_permission(scoped_flow):
    flow = scoped_flow
    job = completed(flow)
    assert flow.manager.install(credentials(suffix='renewed'), flow.account) == flow.account
    assert picker.queue(flow.actor, flow.entries)
    show(flow)
    assert len(flow.shown) == 1 and job.account_scope() == flow.account


def test_account_changes_after_reservation_before_display_suppress_window(scoped_flow):
    flow = scoped_flow
    completed(flow)
    assert picker.queue(flow.actor, flow.entries)
    flow.manager.install(credentials('456'), flow.account)
    show(flow)
    assert flow.shown == flow.notices == [] and flow.native.commands == []


def test_capture_finishing_between_scope_read_and_finished_check_is_rechecked(scoped_flow, monkeypatch):
    flow = scoped_flow
    job = completed(flow)
    assert picker.queue(flow.actor, flow.entries)
    reads = [None, flow.account]
    monkeypatch.setattr(job, 'account_scope', lambda: reads.pop(0) if reads else flow.account)
    show(flow)
    assert len(flow.shown) == 1 and flow.notices == []

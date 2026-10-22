"""A single-axis diagnostic preserves per-call account revocation."""
from threading import Event, Thread
from urllib.parse import urlsplit

import pytest

from test_accounts import credential, logged_in
from test_account_streams import body, stream
from bobbi_core.share_stream import Binding, checked_diagnostic, observation_fields

DIAGNOSTIC = dict(mode='open_range_bound_guard', seconds=60)


def test_bound_guard_mode_is_explicit_and_has_safe_observation_name():
    assert checked_diagnostic(DIAGNOSTIC) == DIAGNOSTIC
    assert observation_fields(dict(diagnostic_mode=DIAGNOSTIC['mode'])) == {
        'diagnostic_mode': DIAGNOSTIC['mode']}


def test_guard_binding_admission_is_once_but_account_comparison_stays_live(tmp_path, monkeypatch):
    manager, scope = logged_in(tmp_path)
    service = stream(manager)
    entry = None
    calls = []
    original = manager.current_guard
    def guard(value):
        calls.append(dict(value))
        return original(value)
    monkeypatch.setattr(manager, 'current_guard', guard)
    try:
        ready = service.register_diagnostic(body(), scope, DIAGNOSTIC)
        same = service.register_diagnostic(body(), scope, DIAGNOSTIC)
        assert ready == same and calls == [scope]
        entry = service.acquire(urlsplit(ready['url']).path)
        def old_path(value):
            pytest.fail('Diagnostic repeats structural validation')
        monkeypatch.setattr(manager, 'is_current', old_path)
        assert entry.cancelled() is False
        service.unsubscribe()  # Even a missing revoke listener cannot preserve authorization.
        current = manager.install(credential(suffix='A2_new'), scope)
        assert entry.cancelled() is False
        manager.logout(current)
        assert entry.cancelled() is True
    finally:
        if entry is not None: service.release(entry)
        service.close()


@pytest.mark.parametrize('diagnostic', [None, dict(mode='open_range', seconds=60),
                                      dict(mode='open_range_microbatch', seconds=60)])
def test_default_and_old_controls_keep_existing_account_checks(tmp_path, monkeypatch, diagnostic):
    manager, scope = logged_in(tmp_path)
    calls = []
    original = manager.is_current
    monkeypatch.setattr(manager, 'is_current', lambda value: (calls.append(value), original(value))[1])
    entry = Binding(body(), lambda *args: '', lambda value: True,
                    account=manager, scope=scope, diagnostic=diagnostic)
    assert entry.cancelled() is False and len(calls) == 1


def test_guard_mode_refuses_unavailable_account_protocol():
    with pytest.raises(ValueError, match='SHARE_DIAGNOSTIC_INVALID'):
        Binding(body(), lambda *args: '', lambda value: True, diagnostic=DIAGNOSTIC)


def test_bound_guard_does_not_publish_a_late_grant_after_switch(tmp_path):
    manager, scope = logged_in(tmp_path)
    entered, finish = Event(), Event()
    failures = []
    def resolve(*args):
        entered.set()
        assert finish.wait(2)
        return 'https://fixture.115cdn.com/video|User-Agent=fixture'
    entry = Binding(body(), resolve, lambda value: True, account=manager,
                    scope=scope, diagnostic=DIAGNOSTIC)
    def run():
        try: entry.grant()
        except Exception as error: failures.append(type(error))
    worker = Thread(target=run)
    worker.start()
    try:
        assert entered.wait(1)
        manager.install(credential('456'), scope)
    finally:
        finish.set()
        worker.join(2)
    assert not worker.is_alive() and failures == [OSError] and entry.address is None

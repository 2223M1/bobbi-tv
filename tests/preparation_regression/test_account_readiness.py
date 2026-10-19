from bobbi_core.account_readiness import AccountReadiness
import pytest


def test_startup_outage_recovers_without_cloud_permission_or_restarting_service():
    now = [0.0]
    gate = AccountReadiness('scope-A', clock=lambda: now[0])
    assert not gate.ready
    assert gate.begin() and not gate.begin()
    failed = gate.complete(error=ConnectionError('private URL must not be reported'))
    assert failed == dict(state='DEPENDENCY_UNAVAILABLE', ready=False,
                          error='ConnectionError', retry_after_seconds=5.0)
    assert not gate.begin()
    now[0] = 5.0
    assert gate.begin()
    assert gate.complete(account='scope-A')['ready']
    assert gate.ready and not gate.begin()


def test_confirmed_other_account_is_sticky_and_never_adopted():
    now = [0.0]
    gate = AccountReadiness('scope-A', clock=lambda: now[0])
    gate.begin()
    assert gate.complete(account='scope-B')['state'] == 'ACCOUNT_MISMATCH'
    now[0] = 99999
    assert not gate.ready and not gate.begin()
    assert gate.expected == 'scope-A'
    with pytest.raises(ValueError):
        gate.complete(account='scope-A')


def test_periodic_health_refresh_does_not_starve_fresh_resolve_and_failed_backoff_is_bounded():
    now = [0.0]
    gate = AccountReadiness('scope-A', clock=lambda: now[0])
    gate.begin()
    gate.complete(account='scope-A')
    now[0] = 60
    # ResolveLane performs its own current account/file/account checks. A
    # periodic health check behind a media probe must not block that lane.
    assert gate.ready and gate.snapshot()['state'] == 'READY'
    assert gate.begin() and gate.ready
    gate.complete(error=TimeoutError())
    assert not gate.ready
    now[0] += 5
    assert gate.begin()
    gate.complete(account='scope-A')
    now[0] += 60
    for delay in (5, 10, 20, 40, 60, 60, 60):
        assert gate.begin()
        result = gate.complete(error=TimeoutError())
        assert not gate.ready
        assert result['retry_after_seconds'] == delay
        now[0] += delay
    assert gate.begin()
    gate.complete(account='scope-A')
    assert gate.failures == 0 and gate.ready


@pytest.mark.parametrize('account', [None, '', 12, False])
def test_missing_account_never_authorizes_startup(account):
    with pytest.raises(ValueError):
        AccountReadiness(account)



"""Stock OSD capability is explicit, never inferred from a failed native read."""
from threading import Thread
import time

import pytest

from bobbi_platform.host import Host


PRESENTATION = dict(operation='playback_presentation', include_owner=True)
STANDARD = dict(available=False, mode='standard', transport='standard', reason='NATIVE_KODI_INTERACTION')


@pytest.mark.parametrize('action', ['playback', 'standard_playback'])
def test_configured_standard_reply_is_read_only_and_never_mints_expected(tmp_path, action):
    host = Host(tmp_path)
    host.accounts = object()
    host.bind_owner(lambda body: pytest.fail('Capability must not invoke the playback owner'))
    result = host.dispatch(action, dict(PRESENTATION))
    assert result == STANDARD and 'expected' not in result
    assert host.calls.empty()


def test_unconfigured_host_cannot_claim_standard_capability(tmp_path):
    host = Host(tmp_path)
    host.accounts = object()
    with pytest.raises(ValueError, match='^NATIVE_OWNER_UNAVAILABLE$'):
        host.dispatch('playback', dict(PRESENTATION))
    assert host.owner is None and host.calls.empty()


@pytest.mark.parametrize('body', [
    dict(operation='playback_presentation'),
    dict(operation='playback_presentation', include_owner=False),
    dict(operation='playback_presentation', include_owner='true'),
    dict(operation='playback_presentation', include_owner=1),
    dict(PRESENTATION, account_scope={'account_id': 'other'}),
    dict(operation='playback_command', include_owner=True),
])
def test_only_exact_owner_capability_query_gets_standard_reply(tmp_path, body):
    host = Host(tmp_path)
    host.accounts = object()
    host.bind_owner(lambda body: None)
    seen = []
    host._owner_request = lambda request: seen.append(request) or {'from_owner': True}
    assert host.dispatch('playback', body) == {'from_owner': True}
    assert seen == [body]


def test_native_read_failure_never_becomes_standard_capability(tmp_path):
    native_calls, results, errors = [], [], []

    def native_rpc(method, body):
        native_calls.append((method, body))
        raise OSError('controlled native outage')

    host = Host(tmp_path, native_rpc=native_rpc)
    host.accounts = object()
    host.bind_owner(lambda body: native_rpc('Player.BobiState', {}))

    def query():
        try:
            results.append(host.dispatch('playback', dict(PRESENTATION)))
        except OSError as error:
            errors.append(error)

    caller = Thread(target=query)
    caller.start()
    try:
        deadline = time.monotonic() + 1
        while host.calls.empty() and time.monotonic() < deadline:
            time.sleep(.001)
        assert not host.calls.empty()
        host.tick()
        caller.join(1)
        assert not caller.is_alive()
        assert not results and len(errors) == 1
        assert str(errors[0]) == 'NATIVE_OWNER_UNAVAILABLE'
        assert native_calls == [('Player.BobiState', {})]
    finally:
        host.close()
        caller.join(1)


def test_standard_capability_still_obeys_profile_fence(tmp_path):
    current = [True]
    host = Host(tmp_path, profile_current=lambda: current[0])
    host.accounts = object()
    host.bind_owner(lambda body: None)
    assert host.dispatch('playback', dict(PRESENTATION)) == STANDARD
    current[0] = False
    with pytest.raises(OSError, match='^PROFILE_CHANGED$'):
        host.dispatch('playback', dict(PRESENTATION))
    current[0] = True
    with pytest.raises(OSError, match='^PROFILE_CHANGED$'):
        host.dispatch('playback', dict(PRESENTATION))

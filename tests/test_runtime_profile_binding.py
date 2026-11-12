"""Existing loopback transport and Host must not follow a changed profile."""
import json
from threading import Event, Thread, get_ident
import time

import pytest

from bobbi_platform import runtime
from bobbi_platform.host import Host


def test_bound_rpc_keeps_original_endpoint_when_default_profile_changes(tmp_path, monkeypatch):
    first = runtime.Runtime(lambda a, b: {'profile': 'A'}, tmp_path/'a'/'runtime.json')
    second = runtime.Runtime(lambda a, b: {'profile': 'B'}, tmp_path/'b'/'runtime.json')
    first.start()
    second.start()
    try:
        bound = runtime.bind_call(first.path)
        monkeypatch.setattr(runtime, 'profile', lambda **kw: second.path)
        assert bound('status', {}) == {'profile': 'A'}
        assert runtime.call('status', {}) == {'profile': 'B'}
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize('change', ['replace', 'remove', 'invalid'])
def test_bound_rpc_revokes_permanently_after_registration_change(tmp_path, change):
    server = runtime.Runtime(lambda a, b: {}, tmp_path/'runtime.json')
    server.start()
    try:
        bound = runtime.bind_call(server.path)
        original = server.path.read_bytes()
        if change == 'remove':
            server.path.unlink()
        else:
            server.path.write_text(json.dumps({'port': server.server.server_port,
                                               'token': 'b'*64}) if change == 'replace' else '{}')
        with pytest.raises(OSError, match='RUNTIME_INSTANCE_CHANGED'):
            bound('status', {})
        server.path.write_bytes(original)
        with pytest.raises(OSError, match='RUNTIME_INSTANCE_CHANGED'):
            bound('status', {})
    finally:
        server.close()


def test_bound_rpc_rejects_reply_after_runtime_replaced_inflight(tmp_path):
    def dispatch(action, body):
        server.path.write_text(json.dumps({'port': server.server.server_port, 'token': 'c'*64}))
        return {'must_not_escape': True}
    server = runtime.Runtime(dispatch, tmp_path/'runtime.json')
    server.start()
    try:
        with pytest.raises(OSError, match='RUNTIME_INSTANCE_CHANGED'):
            runtime.bind_call(server.path)('status', {})
    finally:
        server.close()


@pytest.mark.parametrize('kwargs', [dict(path='relative', expected_token='a'*64),
    dict(path='relative'), dict(expected_token='a'*64), dict(path='relative', expected_token=1)])
def test_bound_call_rejects_incomplete_or_relative_binding(kwargs):
    with pytest.raises(ValueError):
        runtime.call('status', {}, **kwargs)


def test_bind_requires_absolute_path():
    with pytest.raises(ValueError, match='Absolute'):
        runtime.bind_call('runtime.json')


def test_host_profile_switch_revokes_even_after_switching_back(tmp_path):
    current = [True]
    host = Host(tmp_path, profile_current=lambda: current[0])
    host.start()
    try:
        assert host.dispatch('status', {})
        current[0] = False
        with pytest.raises(OSError, match='PROFILE_CHANGED'):
            host.dispatch('status', {})
        current[0] = True
        assert not host.check_profile() and host.stopping.is_set()
        with pytest.raises(OSError, match='PROFILE_CHANGED'):
            host.dispatch('status', {})
    finally:
        host.close()


def test_host_discards_response_if_profile_changes_during_dispatch(tmp_path):
    current = [True]
    host = Host(tmp_path, profile_current=lambda: current[0])
    def dispatch(action, body):
        current[0] = False
        return {'must_not_escape': True}
    host._dispatch = dispatch
    try:
        with pytest.raises(OSError, match='PROFILE_CHANGED'):
            host.dispatch('status', {})
    finally:
        host.close()


def test_concurrent_old_positive_check_cannot_restore_revoked_host(tmp_path):
    entered, release = Event(), Event()
    main_thread = get_ident()
    def current():
        if get_ident() == main_thread:
            return False
        entered.set()
        assert release.wait(1)
        return True
    host = Host(tmp_path, profile_current=current)
    results = []
    worker = Thread(target=lambda: results.append(host.check_profile()))
    worker.start()
    try:
        assert entered.wait(1)
        assert host.check_profile() is False
        release.set()
        worker.join(1)
        assert results == [False] and host.profile_revoked
    finally:
        release.set()
        worker.join(1)
        host.close()


def test_profile_change_does_not_execute_queued_owner_action(tmp_path):
    current, called, errors = [True], [], []
    host = Host(tmp_path, profile_current=lambda: current[0])
    host.start()
    host.bind_owner(lambda body: called.append(body))
    def request():
        try:
            host.dispatch('playback', {'operation': 'snapshot'})
        except (OSError, ValueError) as error:
            errors.append(error)
    caller = Thread(target=request)
    caller.start()
    try:
        deadline = time.monotonic()+1
        while host.calls.empty() and time.monotonic() < deadline:
            time.sleep(.001)
        assert not host.calls.empty()
        current[0] = False
        host.tick()
        host.close()
        caller.join(1)
        assert not caller.is_alive() and errors and not called
    finally:
        host.close()
        caller.join(1)

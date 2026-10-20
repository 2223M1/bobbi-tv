"""Real local HTTP/owner queue; transport unavailability is not user rejection."""
from threading import Thread
import time

import pytest
from bobbi_platform.host import Host
from bobbi_platform import runtime


@pytest.mark.parametrize('cause', ['queue_timeout', 'native_unavailable', 'rejected'])
def test_runtime_preserves_unknown_vs_rejected(tmp_path, monkeypatch, cause):
    host = Host(tmp_path)
    host.start()
    monkeypatch.setattr(runtime, 'profile', lambda **_: tmp_path / 'runtime.json')
    def owner(body):
        if cause == 'native_unavailable':
            raise OSError('sensitive upstream detail must not leave handler')
        raise ValueError('explicit stale request')
    host.bind_owner(owner)
    replies = []
    def invoke():
        try:
            runtime.call('playback', {'operation': 'snapshot'}, timeout=1)
        except Exception as error:
            replies.append(error)
    try:
        worker = Thread(target=invoke)
        worker.start()
        until = time.monotonic() + 1
        while host.calls.empty() and time.monotonic() < until:
            time.sleep(.005)
        if cause != 'queue_timeout':
            host.tick()
        worker.join(2)
        assert len(replies) == 1
        assert isinstance(replies[0], ValueError if cause == 'rejected' else OSError)
        assert 'sensitive' not in str(replies[0])
    finally:
        host.close()

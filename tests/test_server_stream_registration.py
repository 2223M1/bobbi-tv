"""Account notifications must never reenter ShareStream's records lock."""
from threading import Lock, get_ident

import pytest

from bobbi_core.share_stream import ShareStream
from bobbi_platform import pan_stream
from test_media_servers import server


class ObservedLock:
    """Report real same-thread reentry synchronously instead of hanging pytest.

    Accounts._notify catches listener errors, so the counter is checked after
    the production registration returns/rejects. Ordinary locking is unchanged.
    """
    def __init__(self):
        self.lock, self.owner, self.reentries = Lock(), None, 0

    def __enter__(self):
        if self.owner == get_ident():
            self.reentries += 1
            raise RuntimeError('RECORDS_LOCK_REENTERED')
        self.lock.acquire()
        self.owner = get_ident()
        return self

    def __exit__(self, *args):
        self.owner = None
        self.lock.release()


@pytest.mark.parametrize('change', ['settings', 'profile'])
@pytest.mark.parametrize('request_id', ['a' * 32, 'b' * 32], ids=['duplicate', 'new'])
def test_late_server_scope_change_rejects_registration_without_lock_reentry(server, monkeypatch, change, request_id):
    selected = server.pans.list_files(server.expected, 'item:9', 1)['items'][0]
    stream = ShareStream(pan_stream.checked, lambda *args: pytest.fail('Registration must be local'),
        lambda url: True, account=server.pans.accounts, body_check=pan_stream.checked,
        observer=lambda row: None)
    original = stream._register
    try:
        first = pan_stream.body('plex', selected, 'a' * 32)
        stream.register(first, server.expected)
        entry = stream.records[first['request_id']]
        lock = ObservedLock()
        stream.lock = lock

        def change_after_preflight(*args, **kwargs):
            # Registry run_if_current already checked credentials. Settings and
            # profile changes are external to its SQLite publication lock.
            if change == 'settings':
                server.values['token'] = 'changed-fixture-token'
            else:
                server.binding.profile_current = lambda: False
            return original(*args, **kwargs)

        monkeypatch.setattr(stream, '_register', change_after_preflight)
        with pytest.raises(ValueError, match='SHARE_REQUEST_RETARGETED'):
            stream.register(pan_stream.body('plex', selected, request_id), server.expected)
        assert lock.reentries == 0
        assert not stream.records and entry.revoked.is_set()
        # A-B-A cannot revive the old authority after the observed change.
        server.values['token'] = 'fixture-server-secret'
        server.binding.profile_current = lambda: True
        assert not server.accounts.is_current(server.expected)
    finally:
        stream.close()

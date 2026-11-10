"""Only fixed, non-secret pan categories cross the existing local IPC."""
from types import SimpleNamespace

import pytest

from bobbi_platform import runtime
from bobbi_platform.pan_accounts import PanError
from bobbi_platform.pan_http import Session


@pytest.mark.parametrize('action,error,expected', [
    ('pan_list_files', PanError('PAN_NETWORK_ERROR'), 'PAN_NETWORK_ERROR'),
    ('pan_list_files', PanError('PAN_ACCOUNT_CHANGED'), 'PAN_ACCOUNT_CHANGED'),
    ('account_status', PanError('PAN_NETWORK_ERROR'), 'Local service rejected request'),
    ('pan_list_files', PanError('PAN_TOKEN_private-cookie'), 'Local service rejected request'),
    ('pan_list_files', ValueError('PAN_NETWORK_ERROR'), 'Local service rejected request')])
def test_error_taxonomy_is_closed_and_action_scoped(tmp_path, monkeypatch, action, error, expected):
    path = tmp_path/'runtime.json'
    monkeypatch.setattr(runtime, 'profile', lambda **kw: path)
    def dispatch(*a): raise error
    server = runtime.Runtime(dispatch, path)
    server.start()
    try:
        with pytest.raises(ValueError) as caught:
            runtime.call(action, {})
        assert str(caught.value) == expected
    finally:
        server.close()


def test_http_operation_budget_bounds_multiple_hops_and_restores():
    now, waits = [10.0], []
    class Reply:
        status, headers = 200, {'Content-Length': '2'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, size):
            if hasattr(self, 'done'): return b''
            self.done = True
            return b'{}'
    def open(request, timeout):
        waits.append(timeout)
        return Reply()
    session = Session('139', opener=SimpleNamespace(open=open), clock=lambda: now[0])
    url = 'https://yun.139.com/orchestration/auth-rebuild/key/v1.0/getRsaPublicKey'
    with session.budget(16):
        session.request(url, body={})
        now[0] = 25
        session.request(url, body={})
        now[0] = 26
        with pytest.raises(PanError, match='NETWORK_ERROR'):
            session.request(url, body={})
    assert waits == [8, 1] and session.deadline is None

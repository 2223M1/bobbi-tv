import pytest

from bobbi_core.authenticated_cd2 import AuthenticatedCD2
from bobbi_core.cd2 import CD2, CD2Error, field


def client(monkeypatch, operation, status='16'):
    calls, credentials = [], []
    def private():
        value = dict(username='test-user', password='test-only-secret')
        credentials.append(value)
        return value
    def rpc(self, method, payload=b''):
        calls.append(method)
        if method == 'GetToken':
            assert self.token is None
            return [field(1, 1) + field(3, 'test-renewed-token')]
        if self.token != 'test-renewed-token':
            raise CD2Error(status)
        return [b'read-result']
    monkeypatch.setattr(CD2, 'rpc', rpc)
    return AuthenticatedCD2('test-expired', 'http://127.0.0.1:19798/', private, clock=lambda: 100), calls, credentials


def test_expired_read_renews_on_box_and_retries_only_that_read(monkeypatch):
    provider, calls, credentials = client(monkeypatch, 'GetSubFiles')
    assert provider.rpc('GetSubFiles') == [b'read-result']
    assert calls == ['GetSubFiles', 'GetToken', 'GetSubFiles']
    assert credentials == [{}]


def test_expired_mutation_never_replays_after_renewal(monkeypatch):
    provider, calls, _ = client(monkeypatch, 'AddOfflineFiles')
    with pytest.raises(CD2Error):
        provider.rpc('AddOfflineFiles')
    assert calls == ['AddOfflineFiles', 'GetToken']
    assert provider.token == 'test-renewed-token'


@pytest.mark.parametrize('status', ['http-503', 'response-bound-exceeded', 'missing-grpc-status'])
def test_other_failure_never_renews_or_repeats(monkeypatch, status):
    provider, calls, credentials = client(monkeypatch, 'GetSubFiles', status)
    with pytest.raises(CD2Error):
        provider.rpc('GetSubFiles')
    assert calls == ['GetSubFiles'] and credentials == []


def test_rejected_renewal_is_rate_limited(monkeypatch):
    calls = []
    def rpc(self, method, payload=b''):
        calls.append(method)
        raise CD2Error('16')
    monkeypatch.setattr(CD2, 'rpc', rpc)
    provider = AuthenticatedCD2('expired', 'http://127.0.0.1:19798/',
        lambda: dict(username='test', password='test'), clock=lambda: 100)
    for _ in range(2):
        with pytest.raises(CD2Error):
            provider.rpc('GetSubFiles')
    assert calls == ['GetSubFiles', 'GetToken', 'GetSubFiles']



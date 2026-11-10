"""Shared login ownership stays independent of directory/playback readiness.

Protocol tests cover actual adapters separately. These use synthetic grants
to verify the shared Host lifecycle for every non-legacy provider.
"""
from types import SimpleNamespace

import pytest

from bobbi_platform.pan_accounts import PanAccounts
from bobbi_platform.pan_providers import DESCRIPTORS
from bobbi_platform.pan_service import PanService
from bobbi_platform.pan_ui import _failure
from bobbi_platform.pan_accounts import PanError


@pytest.mark.parametrize('provider', sorted(DESCRIPTORS))
def test_authorization_commit_never_constructs_a_directory_or_playback_client(tmp_path, provider):
    calls = []
    grant = dict(provider=provider, subject='synthetic-account')
    def validator(value):
        assert value == grant
        return value['subject'], dict(value)
    accounts = PanAccounts(tmp_path/'accounts.json', {provider: validator})
    class Authorization:
        phase = 'exchange'
        def begin(self):
            calls.append('begin')
            return 'https://fixture.invalid/qr'
        def poll(self):
            calls.append('poll')
            return 'ready', dict(grant)
        def cancel(self):
            calls.append('cancel')
    def forbidden_client(*args):
        pytest.fail('File capabilities must not be a login prerequisite')
    service = PanService(tmp_path, SimpleNamespace(snapshot=lambda: {}), accounts=accounts,
                         login_factory={provider: Authorization}, client_factory=forbidden_client)
    expected = accounts.snapshot(provider)
    attempt = 'a'*32
    assert service.begin(provider, attempt, expected)['state'] == 'waiting'
    assert service.poll(provider, attempt)['state'] == 'ready'
    assert not accounts.path.exists()
    committed = service.commit(provider, attempt)
    assert committed['state'] == 'committed'
    assert accounts.snapshot(provider)['authenticated']
    before = accounts.path.read_bytes(), accounts.path.stat().st_mtime_ns
    assert service.commit(provider, attempt) == committed
    assert (accounts.path.read_bytes(), accounts.path.stat().st_mtime_ns) == before
    assert calls == ['begin', 'poll']


@pytest.mark.parametrize('code', ['PAN_QR_EXCHANGE_FAILED', 'PAN_CREDENTIALS_INVALID',
                                  'PAN_ACCOUNT_ID_INVALID'])
def test_incomplete_grants_have_specific_login_feedback(code):
    message = _failure(PanError(code))
    assert message and '接口暂不可用' not in message
    assert code not in message

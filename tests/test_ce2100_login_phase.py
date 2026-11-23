"""Fixed login stages survive cancellation and IPC without upstream details."""
import io
import json
from types import SimpleNamespace

import pytest

from bobbi_platform import runtime
from bobbi_platform.login_flow import is_retryable
from bobbi_platform.pan_accounts import PanError
from test_ce2096_pan_accounts import accounts, service, begin


@pytest.mark.parametrize('operation,phase', [('begin', 'qr'), ('poll', 'confirm'),
    ('poll', 'exchange'), ('poll', 'identity'), ('poll', 'private-ticket'), ('poll', ['identity'])])
def test_service_captures_only_fixed_stage_before_cancel(service, operation, phase):
    if operation == 'poll':
        begin(service)
    flow = service.fixture_flow
    flow.phase = phase
    flow.cancel = lambda: setattr(flow, 'phase', 'closed')

    def fail():
        raise PanError('PAN_API_REJECTED')

    setattr(flow, operation, fail)
    with pytest.raises(PanError) as caught:
        if operation == 'begin':
            begin(service)
        else:
            service.poll('quark', 'a'*32)
    expected = phase if type(phase) is str and phase in runtime.LOGIN_ERROR_PHASES else None
    assert getattr(caught.value, 'login_phase', None) == expected
    assert flow.phase == 'closed'
    assert service.attempts['quark'].state == 'failed'
    assert not service.accounts.snapshot('quark')['authenticated']


@pytest.mark.parametrize('action,code,phase,error_type,expected', [
    ('pan_login_begin', 'PAN_API_REJECTED', 'qr', PanError, 'qr'),
    ('pan_login_poll', 'PAN_API_REJECTED', 'confirm', PanError, 'confirm'),
    ('pan_login_poll', 'PAN_API_REJECTED', 'exchange', PanError, 'exchange'),
    ('pan_login_poll', 'PAN_API_REJECTED', 'identity', PanError, 'identity'),
    ('pan_login_poll', 'PAN_API_REJECTED', None, PanError, None),
    ('pan_login_poll', 'PAN_API_REJECTED', 'private-ticket', PanError, None),
    ('pan_login_poll', 'PAN_API_REJECTED', ['identity'], PanError, None),
    ('pan_login_poll', 'PAN_PRIVATE_secret', 'identity', PanError, None),
    ('pan_login_poll', 'PAN_CREDENTIALS_INVALID:private-ticket', 'identity', PanError, None),
    ('pan_login_poll', 'PAN_API_REJECTED', 'identity', ValueError, None),
    ('pan_login_commit', 'PAN_API_REJECTED', 'identity', PanError, None),
    ('pan_list_files', 'PAN_API_REJECTED', 'identity', PanError, None),
    ('catalog_scan', 'PAN_API_REJECTED', 'identity', PanError, None),
    ('account_status', 'PAN_API_REJECTED', 'identity', PanError, None),
] + [('pan_login_poll', code, phase, PanError, phase) for code, phase in [
    ('PAN_CREDENTIALS_INVALID', 'identity'), ('PAN_ACCOUNT_ID_INVALID', 'identity'),
    ('PAN_QR_POLL_RETRY', 'confirm'), ('PAN_QR_EXCHANGE_FAILED', 'exchange'),
    ('PAN_QR_STATE_INVALID', 'confirm'), ('PAN_QR_CANCELLED', 'confirm'),
    ('PAN_QR_UNAVAILABLE', 'qr'), ('PAN_QR_IMAGE_INVALID', 'qr'),
    ('PAN_QR_IMAGE_ORIGIN_REJECTED', 'qr'), ('PAN_QR_ORIGIN_REJECTED', 'qr'),
    ('PAN_LOGIN_FAILED', 'exchange'), ('PAN_LOGIN_NOT_READY', 'identity'),
]])
def test_ipc_transmits_stage_only_for_public_login_errors(tmp_path, monkeypatch, action, code, phase,
                                                        error_type, expected):
    path = tmp_path/'runtime.json'
    monkeypatch.setattr(runtime, 'profile', lambda **kw: path)
    error = error_type(code)
    error.login_phase = phase
    error.upstream_body = 'private-ticket'  # Never serialize arbitrary exception fields.
    encoded = []
    original_encode = runtime.encode_message

    def encode(value):
        if value.get('ok') is False:
            encoded.append(dict(value))
        return original_encode(value)

    monkeypatch.setattr(runtime, 'encode_message', encode)

    def dispatch(*args):
        raise error

    server = runtime.Runtime(dispatch, path)
    server.start()
    try:
        with pytest.raises(ValueError) as caught:
            runtime.call(action, {})
        assert getattr(caught.value, 'login_phase', None) == expected
        if expected is not None:
            assert type(caught.value) is PanError and str(caught.value) == code
        if code == 'PAN_QR_POLL_RETRY':
            assert is_retryable(caught.value)  # Survives IPC as a real PanError.
        assert encoded[-1].get('phase') == expected
        assert 'private-ticket' not in json.dumps(encoded)
        assert 'PAN_PRIVATE_secret' not in json.dumps(encoded)
        assert set(encoded[-1]) <= {'ok', 'error', 'code', 'phase'}
    finally:
        server.close()


@pytest.mark.parametrize('action,phase,expected', [
    ('pan_login_begin', 'qr', 'qr'), ('pan_login_poll', 'exchange', 'exchange'),
    ('pan_login_poll', 'private-ticket', None), ('pan_login_poll', ['identity'], None),
    ('pan_login_poll', None, None), ('pan_login_commit', 'identity', None),
    ('pan_list_files', 'identity', None), ('catalog_scan', 'identity', None),
])
def test_client_independently_filters_wire_phase(tmp_path, monkeypatch, action, phase, expected):
    path = tmp_path/'runtime.json'
    path.write_text(json.dumps(dict(port=12345, token='a'*64)))
    monkeypatch.setattr(runtime, 'profile', lambda **kw: path)
    reply = dict(ok=False, error='pan', code='PAN_API_REJECTED')
    if phase is not None:  # Legacy replies do not contain this optional field.
        reply['phase'] = phase
    monkeypatch.setattr(runtime, 'build_opener', lambda *args: SimpleNamespace(
        open=lambda *args, **kwargs: io.BytesIO(json.dumps(reply).encode())))
    with pytest.raises(PanError, match='^PAN_API_REJECTED$') as caught:
        runtime.call(action, {})
    assert getattr(caught.value, 'login_phase', None) == expected

"""Legacy Kodi entry points; capture once per operation, never a core locator."""
from lib.cinema import _shared  # dependency bootstrap
from copy import deepcopy
import time
from bobbi_core import preparation_client as _core
from bobbi_core.preparation_client import SOCKET_PATH, source_intent, advance_intent

_CURRENT_ACCOUNT = object()


def _bound_host(data=None):
    # Snapshot inherited scope before core marks an absent capture as None.
    # One operation owns this closure; failure cannot recapture on its retry.
    expected = ({'_account': deepcopy(data['_account'])}
                if data is not None and '_account' in data else None)
    attempted, session = False, None
    def host_call(action, body, timeout=.3):
        nonlocal attempted, session
        deadline = time.monotonic() + timeout
        if not attempted:
            attempted = True
            from bobbi_platform.prepared_sessions import capture
            session = capture(expected)
        if session is None:
            raise RuntimeError('PREPARATION_ACCOUNT_SCOPE_UNAVAILABLE')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Preparation binding budget expired')
        return session.host_call(action, body, min(timeout, remaining))
    return host_call


def capture_account(data, allow_capture=True, *, host_call=None):
    return _core.capture_account(data, allow_capture,
        host_call=host_call if host_call is not None else _bound_host(data))


def call(method, body, socket_path=SOCKET_PATH, timeout=.3,
         expected_account=_CURRENT_ACCOUNT, *, host_call=None):
    data = None if expected_account is _CURRENT_ACCOUNT else {'_account': expected_account}
    options = {} if expected_account is _CURRENT_ACCOUNT else dict(expected_account=expected_account)
    return _core.call(method, body, socket_path, timeout,
        host_call=host_call if host_call is not None else _bound_host(data), **options)


def resolve_entry(data, snapshot, entry, cancelled=lambda: False, budget=3.0,
                  pending_on_timeout=False, return_verification=False, verification_id=None, *, host_call=None):
    options = dict(budget=budget, pending_on_timeout=pending_on_timeout,
                   return_verification=return_verification, verification_id=verification_id)
    return _core.resolve_entry(data, snapshot, entry, cancelled,
        host_call=host_call if host_call is not None else _bound_host(data), **options)


def prepare_fonts(data, context, cancelled=lambda: False, *, host_call=None):
    return _core.prepare_fonts(data, context, cancelled,
        host_call=host_call if host_call is not None else _bound_host(data))

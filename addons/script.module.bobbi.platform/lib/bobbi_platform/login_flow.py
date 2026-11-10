"""Bounded login presentation flow, without owning accounts or credentials.

Adapters own protocols and cleanup. Only begin/poll run in a worker; rendering,
status updates and the single commit run on the caller's UI thread. Cancellation
after commit was dispatched cannot promise that the account stayed unchanged.
"""
from threading import Event, Thread
import time
from urllib.error import HTTPError

from .cloud115 import CloudError
from .pan_accounts import PanError, PUBLIC_ERRORS


_PHASES = frozenset(('prepare', 'confirm', 'exchange', 'identity', 'commit', 'complete', 'cancelled'))
_FLOW_ERRORS = frozenset(('WAIT_TIMEOUT', 'EXPIRED', 'INVALID_STATE', 'COMMIT_UNCONFIRMED'))
_CLOUD_ERRORS = frozenset((
    'INVALID_ORIGIN', 'UNEXPECTED_REDIRECT', 'INVALID_REPLY', 'NETWORK_ERROR',
    'INVALID_CREDENTIALS', 'UNSAFE_STORAGE', 'QR_UNAVAILABLE', 'QR_FINISHED',
    'QR_EXPIRED', 'QR_CANCELLED', 'QR_POLL_RETRY', 'LOGIN_FAILED',
))
_CANCELLED = object()


class LoginFlowError(RuntimeError):
    """Fixed local mechanism code; never a remote response or exception dump."""
    def __init__(self, code):
        self.code = code if type(code) is str and code in _FLOW_ERRORS else 'INVALID_STATE'
        super().__init__(self.code)


def _pan_code(error):
    # Do not invoke arbitrary __str__/__repr__ even on an unknown PanError.
    return error.args[0] if len(error.args) == 1 and type(error.args[0]) is str else None


def is_retryable(error):
    """Shared network gate. An adapter may narrow this, never broaden it."""
    if isinstance(error, PanError):
        return _pan_code(error) in ('PAN_NETWORK_ERROR', 'PAN_QR_POLL_RETRY')
    if isinstance(error, CloudError):
        return error.code in ('NETWORK_ERROR', 'QR_POLL_RETRY')
    return isinstance(error, OSError) and not isinstance(error, HTTPError)


class LoginRunner:
    """One-shot login attempt; cancellation returns False, failures raise.

    begin is never repeated. Consecutive explicit network poll failures permit
    three calls total (two retries). Structured retry responses use the whole
    attempt deadline. A local worker timeout terminates this runner permanently:
    it must not launch another request while the old worker may still be alive.

    The caller must call adapter.cancel/cleanup in its own finally block and
    reconcile any available commit receipt. A successful return only follows a
    committed acknowledgement, not an old account's authenticated status.
    """
    def __init__(self, window, monitor, clock=time.monotonic, lifetime=180):
        if type(lifetime) not in (int, float) or not 0 < lifetime <= 180:
            raise LoginFlowError('INVALID_STATE')
        self.window, self.monitor, self.clock = window, monitor, clock
        self.lifetime = lifetime
        self.phase, self.commit_sent, self.commit_acknowledged = 'prepare', False, False
        self._used, self._deadline = False, None

    def diagnostic(self, error=None):
        """Only fixed codes and booleans may leave the runner for diagnostics."""
        code = 'NONE' if error is None else 'UNKNOWN'
        if isinstance(error, LoginFlowError) and type(error.code) is str and error.code in _FLOW_ERRORS:
            code = error.code
        elif isinstance(error, PanError):
            candidate = _pan_code(error)
            if candidate in PUBLIC_ERRORS:
                code = candidate
        elif isinstance(error, CloudError) and type(error.code) is str and error.code in _CLOUD_ERRORS:
            code = error.code
        phase = self.phase if type(self.phase) is str and self.phase in _PHASES else 'unknown'
        return dict(phase=phase, code=code, commit_sent=self.commit_sent is True,
                    commit_acknowledged=self.commit_acknowledged is True)

    def _cancelled(self):
        if self.window.cancelled or self.monitor.abortRequested():
            self.phase = 'cancelled'
            return True
        return False

    def _remaining(self):
        remaining = self._deadline - self.clock()
        if remaining <= 0:
            raise LoginFlowError('EXPIRED')
        return remaining

    def _adopt_phase(self, adapter):
        phase = getattr(adapter, 'phase', None)
        if type(phase) is str and phase in _PHASES:
            self.phase = phase

    def _wait(self, operation, maximum):
        if self._cancelled():
            return _CANCELLED
        wait_deadline = self.clock() + min(maximum, self._remaining())
        done, job = Event(), {}

        def work():
            try:
                job['result'] = operation()
            except Exception as error:
                job['error'] = error
            finally:
                done.set()

        Thread(target=work, name='bobbi-login-worker', daemon=True).start()
        while True:
            if self._cancelled():
                return _CANCELLED
            self._remaining()
            remaining = wait_deadline - self.clock()
            if remaining <= 0:
                raise LoginFlowError('WAIT_TIMEOUT')
            ready = done.is_set()
            # Kodi dispatches Python window callbacks only in waitForAbort,
            # not abortRequested/Event.wait. Zero waits indefinitely on this
            # fork. Even an already-ready result must pump queued Back first.
            if self.monitor.waitForAbort(min(.001 if ready else .05, remaining)):
                self.phase = 'cancelled'
                return _CANCELLED
            if self._cancelled():
                return _CANCELLED
            self._remaining()
            remaining = wait_deadline - self.clock()
            if remaining <= 0:
                raise LoginFlowError('WAIT_TIMEOUT')
            if ready:
                if 'error' in job:
                    raise job['error']
                return job['result']
            # A ready result arriving during/after the pump is consumed only
            # next iteration, after another positive callback pump. This tiny
            # wait also yields to workers when a test monitor returns at once.
            done.wait(min(.001, remaining))

    def _pause(self):
        # Short monitor waits keep UI cancellation responsive. The count also
        # permits deterministic Kodi stubs without a real two-second sleep.
        for _ in range(20):
            if self._cancelled():
                return False
            if self.monitor.waitForAbort(min(.1, self._remaining())):
                self.phase = 'cancelled'
                return False
        return not self._cancelled()

    def run(self, adapter, render_qr):
        if self._used:
            raise LoginFlowError('INVALID_STATE')
        self._used = True
        self._deadline = self.clock() + self.lifetime
        if self._cancelled():
            return False
        self.window.set_status('正在准备二维码，可按返回取消。')
        try:
            state = self._wait(adapter.begin, 20)
        except Exception:
            self._adopt_phase(adapter)
            raise
        if state is _CANCELLED:
            return False
        if (type(state) is not dict or state.get('state') != 'waiting'
                or not any(type(state.get(key)) is str and state[key] for key in ('qr', 'qr_png'))):
            raise LoginFlowError('INVALID_STATE')
        if self._cancelled():
            return False
        render_qr(state)
        if self._cancelled():
            return False
        self.phase = 'confirm'
        self.window.set_status('扫码后请在手机确认。可按返回取消。')
        failures = 0
        while self._pause():
            try:
                state = self._wait(adapter.poll, 28)
            except Exception as error:
                self._adopt_phase(adapter)
                gate = getattr(adapter, 'retryable', None)
                if (not is_retryable(error) or gate is not None and not gate(error)):
                    raise
                failures += 1
                if failures >= 3:
                    raise
                self.window.set_status('连接暂不可用，正在重试。可按返回取消。')
                continue
            if state is _CANCELLED:
                return False
            if type(state) is not dict:
                raise LoginFlowError('INVALID_STATE')
            status = state.get('state')
            if status not in ('waiting', 'scanned', 'polling', 'starting', 'retry', 'ready'):
                raise LoginFlowError('INVALID_STATE')
            failures = 0
            phase = state.get('phase')
            if type(phase) is str and phase in ('confirm', 'exchange', 'identity'):
                self.phase = phase
            if status == 'ready':
                if self._cancelled():
                    return False
                self._remaining()
                self.phase, self.commit_sent = 'commit', True
                reply = adapter.commit()
                if type(reply) is not dict or reply.get('state') != 'committed':
                    raise LoginFlowError('COMMIT_UNCONFIRMED')
                self.commit_acknowledged, self.phase = True, 'complete'
                return True
            if status == 'retry':
                self.window.set_status({
                    'confirm': '手机确认结果尚未返回，正在重试。可按返回取消。',
                    'exchange': '正在重试获取登录信息。尚未保存账号。',
                    'identity': '正在重试核对账号。尚未保存登录。',
                }.get(self.phase, '连接超时，正在重试。可按返回取消。'))
            elif status == 'scanned':
                self.window.set_status('已扫码，请在手机上确认登录。可按返回取消。')
            else:
                self.window.set_status('扫码后请在手机确认。可按返回取消。')
        return False

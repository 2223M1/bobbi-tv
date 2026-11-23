"""Request-owned prepared reads, bound to one profile, account and Host.

No registry or late binding: a failed capture is None, and every consumer must
keep that None. Account probes happen outside playback/queue locks. They only
compare identity; uncertainty never submits work or adopts a replacement.
"""
from pathlib import Path
import time

from bobbi_core.account_scope import validate_snapshot
_BOUND_ACCOUNT = object()


class PreparedSession:
    def __init__(self, root, call, account, current):
        self.root = Path(root)
        if not self.root.is_absolute() or not callable(call) or not callable(current):
            raise ValueError('PREPARED_SESSION_BINDING_REQUIRED')
        self._call, self._current = call, current
        self._scope = validate_snapshot(account)
        self._revoked = False
        self.index_path = self.root / 'bobi-prepared.json'

    @property
    def account(self):
        return dict(self._scope)

    def _profile(self):
        if self._revoked:
            raise RuntimeError('PREPARED_SESSION_REVOKED')
        try:
            if self._current() is not True:
                raise RuntimeError('PREPARED_SESSION_REVOKED')
        except (OSError, RuntimeError, ValueError, TypeError):
            self._revoked = True
            raise RuntimeError('PREPARED_SESSION_REVOKED') from None

    def _account(self, timeout=.1):
        self._profile()
        try:
            scope = validate_snapshot(self._call('account_status', {}, timeout=timeout))
            self._profile()
            if scope != self.account:
                raise RuntimeError('PREPARED_SESSION_REVOKED')
            return dict(scope)
        except (OSError, RuntimeError, ValueError, TypeError):
            self._revoked = True
            raise RuntimeError('PREPARED_SESSION_REVOKED') from None

    def account_current(self, scope):
        try:
            return validate_snapshot(scope) == self._account()
        except (OSError, RuntimeError, ValueError, TypeError):
            return False

    def host_call(self, action, body, timeout=.3):
        if type(timeout) not in (int, float) or not 0 < timeout <= .3:
            raise ValueError('Bounded prepared session timeout required')
        deadline = time.monotonic() + timeout
        account = self._account(min(.1, timeout / 3))
        if action == 'account_status':
            return account
        if action == 'preparation' and body.get('account') != account:
            raise ValueError('PREPARATION_ACCOUNT_CHANGED')
        remaining = min(timeout, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError('Prepared session account budget expired')
        value = self._call(action, body, timeout=remaining)
        self._profile()
        return value

    def owner_call(self, body, timeout=.3):
        return self.host_call('playback', body, timeout)

    def call(self, method, body, timeout=.3, expected_account=_BOUND_ACCOUNT):
        from bobbi_core.preparation_client import call
        account = self.account if expected_account is _BOUND_ACCOUNT else expected_account
        return call(method, body, timeout=timeout, expected_account=account, host_call=self.host_call)

    def capture_account(self, data, allow_capture=True):
        from bobbi_core.preparation_client import capture_account
        scope = capture_account(data, allow_capture, host_call=self.host_call)
        if not self.account_current(scope):
            raise RuntimeError('PREPARATION_ACCOUNT_CHANGED')
        return scope

    def load_index(self):
        from bobbi_core.prepared_index import load
        self._profile()
        # Parse under the captured path, then make one fresh account check.
        # The pure callback compares publication scope; it performs no IO.
        result = load(self.index_path, account_current=lambda scope: scope == self.account)
        self._account()
        return result

    def generation(self):
        from bobbi_core.prepared_index import read_generation
        self._profile()
        result = read_generation(self.index_path)
        self._account()
        return result

    def resolve_entry(self, data, snapshot, entry, cancelled=lambda: False, **options):
        from bobbi_core.preparation_client import resolve_entry
        self.capture_account(data)
        result = resolve_entry(data, snapshot, entry, cancelled, host_call=self.host_call, **options)
        return result if self.account_current(data['_account']) and not cancelled() else None

    def prepare_fonts(self, data, context, cancelled=lambda: False):
        from bobbi_core.preparation_client import prepare_fonts
        return prepare_fonts(data, context, cancelled, host_call=self.host_call)

    def verified_entry(self, data, category, intent, cancelled=lambda: False, **options):
        from bobbi_core.prepared_retry import verified_entry
        return verified_entry(data, category, intent, cancelled, owner_call=self.owner_call,
            index_loader=self.load_index, resolver=self.resolve_entry,
            account_current=self.account_current, **options)

    def direct_snapshot(self):
        from bobbi_core.direct_cloud_client import snapshot
        self._profile()
        result = snapshot(path=self.root / 'bobi-direct.json', account_current=lambda scope: scope == self.account)
        self._account()
        return result

    def direct_entry(self, data):
        from bobbi_core.direct_cloud_client import entry
        return entry(data, self.direct_snapshot())

    def direct_prepare(self, data):
        from bobbi_core.direct_cloud_client import prepare
        self.capture_account(data, allow_capture=False)
        return prepare(data, host_call=self.host_call)

    def direct_resolve(self, data, cancelled=lambda: False):
        from bobbi_core.direct_cloud_client import resolve
        self.capture_account(data, allow_capture=False)
        result = resolve(data, cancelled, view=self.direct_snapshot(), host_call=self.host_call)
        return result if self.account_current(data['_account']) and not cancelled() else None


def capture(data=None, *, binding=None):
    """Kodi interpreter entry. Call before queuing work, never from a retry."""
    if data is not None and '_account' not in data:
        data['_account'] = None
        expected = None
    elif data is not None:
        try:
            expected = validate_snapshot(data['_account'])
        except (ValueError, TypeError, RuntimeError):
            return None  # Explicit failed capture cannot adopt a later login.
    else:
        expected = None
    try:
        from .paths import ProfileBinding
        from .runtime import bind_call
        binding = ProfileBinding() if binding is None else binding
        binding.require_current()
        call = bind_call(binding.root() / 'runtime.json')
        account = validate_snapshot(call('account_status', {}, timeout=.1))
        binding.require_current()
        if expected is not None and expected != account:
            return None
        session = PreparedSession(binding.root('plugin.video.bobbi'), call, account, binding.is_current)
        if data is not None:
            data['_account'] = dict(account)
        return session
    except (ImportError, OSError, ValueError, TypeError, RuntimeError):
        return None


def from_host(host, account):
    """Resident composition keeps the actual Host, not its current locator."""
    try:
        scope = validate_snapshot(account)
        def current():
            return not host.stopping.is_set() and host.check_profile()
        def call(action, body, timeout=.3):
            return host.dispatch(action, body)
        session = PreparedSession(host.plugin_root, call, scope, current)
        return session if session.account_current(scope) else None
    except (AttributeError, OSError, ValueError, TypeError, RuntimeError):
        return None

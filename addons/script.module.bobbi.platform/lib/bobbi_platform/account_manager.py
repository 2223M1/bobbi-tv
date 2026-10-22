"""One host-owned account generation; credentials never cross status IPC.

Network work captures a scope and credential copy, then checks the same scope
before publishing. Only short local commits may run under the generation lock.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock

from .cloud115 import credentials, CloudError


class AccountError(RuntimeError):
    pass


def validate_snapshot(value, authenticated=False):
    if (not isinstance(value, dict) or set(value) != {'account_id', 'epoch', 'authenticated'}
            or type(value['epoch']) is not int or not 0 <= value['epoch'] < 2**63
            or type(value['authenticated']) is not bool
            or not isinstance(value['account_id'], str)
            or (value['authenticated'] and not re.fullmatch(r'115:[0-9a-f]{64}', value['account_id']))
            or (not value['authenticated'] and value['account_id'])
            or (authenticated and not value['authenticated'])):
        raise AccountError('ACCOUNT_SCOPE_INVALID')
    return dict(value)


def account_id(value):
    # 115 UID suffix contains client/session detail. Renewal of that suffix
    # must not masquerade as another user or discard this user's ready state.
    uid = credentials(value)['cookies']['UID'].split('_', 1)[0]
    if not re.fullmatch(r'[1-9][0-9]{0,31}', uid):
        raise AccountError('ACCOUNT_ID_INVALID')
    return '115:' + hashlib.sha256(('115:' + uid).encode('ascii')).hexdigest()


def _write(path, value):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise AccountError('ACCOUNT_STORAGE_INVALID')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.account-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class AccountManager:
    """Owned by the one Runtime process, not independently constructed in UI."""
    def __init__(self, path):
        self.path = Path(path)
        self.lock = RLock()
        self.listeners = []
        self._credentials = None
        self._scope = dict(account_id='', epoch=0, authenticated=False)
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        if (not self.path.is_file() or self.path.stat().st_size > 16384
                or any(p.is_symlink() for p in (self.path, *self.path.parents))):
            raise AccountError('ACCOUNT_STORAGE_INVALID')
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            scope = value.get('_account')
            if scope is not None:
                scope = validate_snapshot(scope)
                if not scope['authenticated']:
                    if value != {'_account': scope}:
                        raise AccountError('ACCOUNT_STORAGE_INVALID')
                    self._scope = scope
                    return
            checked = credentials(value)
            identity = account_id(checked)
            if scope is None:
                # One-time migration of this installation's existing login,
                # never a private source profile or another account's files.
                scope = dict(account_id=identity, epoch=1, authenticated=True)
                _write(self.path, dict(checked, _account=scope))
            if scope['account_id'] != identity:
                raise AccountError('ACCOUNT_STORAGE_INVALID')
            self._scope, self._credentials = scope, checked
        except (ValueError, TypeError, AttributeError, CloudError):
            raise AccountError('ACCOUNT_STORAGE_INVALID') from None

    def snapshot(self):
        with self.lock:
            return dict(self._scope)

    def is_current(self, expected):
        try:
            expected = validate_snapshot(expected)
        except AccountError:
            return False
        with self.lock:
            return expected == self._scope

    def current_guard(self, expected):
        """Capture validated scope, not a cached authorization decision.

        The private copy cannot be retargeted by mutating the caller's dictionary.
        Every invocation still compares the complete authoritative scope under
        the same generation lock; listener failures cannot keep an old guard live.
        """
        expected = validate_snapshot(expected)
        with self.lock:
            if expected != self._scope:
                raise AccountError('ACCOUNT_CHANGED')

        def current():
            with self.lock:
                return expected == self._scope
        return current

    def require_current(self, expected, authenticated=True):
        expected = validate_snapshot(expected, authenticated=authenticated)
        with self.lock:
            if expected != self._scope:
                raise AccountError('ACCOUNT_CHANGED')
        return expected

    def run_if_current(self, expected, operation, authenticated=True):
        with self.lock:
            self.require_current(expected, authenticated=authenticated)
            return operation()

    def credentials(self, expected):
        with self.lock:
            self.require_current(expected)
            return deepcopy(self._credentials)

    def subscribe(self, listener):
        with self.lock:
            if listener not in self.listeners:
                self.listeners.append(listener)
        def unsubscribe():
            with self.lock:
                if listener in self.listeners:
                    self.listeners.remove(listener)
        return unsubscribe

    def _commit(self, value, scope):
        previous = dict(self._scope)
        _write(self.path, dict(value, _account=scope) if value else {'_account': scope})
        self._credentials, self._scope = value, dict(scope)
        if previous != scope:
            for listener in tuple(self.listeners):
                try:
                    listener(previous, dict(scope))
                except Exception:
                    # A faulty optional observer cannot prevent other streams
                    # being revoked. Each consumer also checks the epoch itself.
                    continue
        return dict(scope)

    def install(self, value, expected):
        value = credentials(value)
        identity = account_id(value)
        with self.lock:
            self.require_current(expected, authenticated=False)
            epoch = self._scope['epoch'] + (identity != self._scope['account_id'])
            scope = validate_snapshot(dict(account_id=identity, epoch=epoch, authenticated=True))
            return self._commit(value, scope)

    def logout(self, expected):
        with self.lock:
            self.require_current(expected, authenticated=False)
            if not self._scope['authenticated']:
                return dict(self._scope)
            scope = validate_snapshot(dict(account_id='', epoch=self._scope['epoch'] + 1, authenticated=False))
            # Tombstone persists generation; deleting the file would let an
            # old A generation become current after logging into A again.
            return self._commit(None, scope)

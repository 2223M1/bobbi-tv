"""Provider-scoped accounts owned by Host; deliberately not a 115 scope migration.

The existing 115 account/playback contract remains closed. New adapters use an
explicit provider field, so their scopes cannot authorize an old 115 operation.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from threading import RLock

from .account_manager import _write


PROVIDERS = (
    ('115', '115'), ('quark', '夸克'), ('uc', 'UC'), ('aliyun', '阿里云盘'),
    ('123', '123 云盘'), ('189', '天翼云盘'), ('139', '中国移动云盘'),
    ('baidu', '百度网盘'), ('xunlei', '迅雷'), ('guangya', '光鸭'),
)
NAMES = dict(PROVIDERS)

# Only these local categories may cross IPC. Never forward an upstream body
# or arbitrary exception text merely because it starts with PAN_.
PUBLIC_ERRORS = frozenset((
    'PAN_NETWORK_ERROR', 'PAN_OPERATION_BUSY', 'PAN_LOGIN_BUSY', 'PAN_SERVICE_CLOSED',
    'PAN_LOGIN_REQUIRED', 'PAN_ACCOUNT_CHANGED', 'PAN_CREDENTIALS_CHANGED',
    'PAN_CREDENTIALS_INVALID', 'PAN_ACCOUNT_ID_INVALID',
    'PAN_QR_EXPIRED', 'PAN_QR_FINISHED', 'PAN_ATTEMPT_EXPIRED', 'PAN_CHALLENGE_REQUIRED',
    'PAN_QR_POLL_RETRY', 'PAN_QR_EXCHANGE_FAILED', 'PAN_QR_STATE_INVALID',
    'PAN_QR_CANCELLED', 'PAN_QR_UNAVAILABLE', 'PAN_QR_IMAGE_INVALID',
    'PAN_QR_IMAGE_ORIGIN_REJECTED', 'PAN_QR_ORIGIN_REJECTED',
    'PAN_LOGIN_FAILED', 'PAN_LOGIN_NOT_READY',
    'PAN_FILE_CHANGED', 'PAN_DIRECTORY_UNAVAILABLE', 'PAN_CRYPTO_UNAVAILABLE',
    'PAN_ROUTE_REJECTED', 'PAN_REPLY_INVALID', 'PAN_API_REJECTED', 'PAN_HTTP_REJECTED',
    'PAN_SELECTION_CANCELLED', 'PAN_PLAY_EXPIRED',
    'PAN_PAGE_EXPIRED', 'PAN_ITEM_TOO_LARGE', 'PAN_OPERATION_CANCELLED',
    'PAN_OPERATION_EXPIRED', 'PAN_BUDGET_EXHAUSTED', 'PAN_RATE_LIMITED', 'PAN_EXPIRY_INVALID',
))


class PanError(ValueError):
    """Only fixed local codes; remote bodies, cookies and URLs are never errors."""


def provider_id(value):
    if type(value) is not str or value not in NAMES or value == '115':
        raise PanError('PAN_PROVIDER_INVALID')
    return value


def scope(value, provider=None, authenticated=False):
    if (type(value) is not dict
            or set(value) != {'provider', 'account_id', 'epoch', 'authenticated'}):
        raise PanError('PAN_SCOPE_INVALID')
    key = provider_id(value['provider'])
    if (provider is not None and key != provider
            or type(value['epoch']) is not int or not 0 <= value['epoch'] < 2**63
            or type(value['authenticated']) is not bool
            or type(value['account_id']) is not str
            or (value['authenticated'] and not re.fullmatch(key + r':[0-9a-f]{64}', value['account_id']))
            or (not value['authenticated'] and value['account_id'])
            or (authenticated and not value['authenticated'])):
        raise PanError('PAN_SCOPE_INVALID')
    return dict(value)


def empty_scope(provider):
    return dict(provider=provider_id(provider), account_id='', epoch=0, authenticated=False)


class PanAccounts:
    """One store and lock; independent persistent generations for each provider.

    Validators return (stable provider subject, normalized credentials). Only
    registered, implemented adapters can install credentials. Status is local
    and says saved, not verified-online. No credentials leave status IPC.
    """
    def __init__(self, path, validators):
        self.path = Path(path)
        self.validators = dict(validators)
        for key in self.validators:
            provider_id(key)
        self.lock, self.listeners = RLock(), []
        self.records = {}
        self._load()

    def _checked(self, provider, credentials):
        validator = self.validators.get(provider_id(provider))
        if validator is None:
            raise PanError('PAN_ADAPTER_UNAVAILABLE')
        subject, checked = validator(deepcopy(credentials))
        if type(subject) is not str or not subject or len(subject) > 256:
            raise PanError('PAN_CREDENTIALS_INVALID')
        identity = provider + ':' + hashlib.sha256((provider + ':' + subject).encode('utf-8')).hexdigest()
        return identity, deepcopy(checked)

    def _load(self):
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise PanError('PAN_STORAGE_INVALID')
        if not self.path.exists():
            return
        if not self.path.is_file() or self.path.stat().st_size > 262144:
            raise PanError('PAN_STORAGE_INVALID')
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if (type(value) is not dict or set(value) != {'version', 'accounts'}
                    or type(value['version']) is not int or value['version'] != 1
                    or type(value['accounts']) is not dict):
                raise ValueError
            records = {}
            for key, row in value['accounts'].items():
                provider_id(key)
                if type(row) is not dict or set(row) != {'scope', 'credentials'}:
                    raise ValueError
                checked_scope = scope(row['scope'], key)
                checked = None
                if checked_scope['authenticated']:
                    identity, checked = self._checked(key, row['credentials'])
                    if identity != checked_scope['account_id']:
                        raise ValueError
                elif row['credentials'] is not None:
                    raise ValueError
                records[key] = dict(scope=checked_scope, credentials=checked)
            self.records = records
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise PanError('PAN_STORAGE_INVALID') from None

    def snapshot(self, provider):
        provider_id(provider)
        with self.lock:
            return dict(self.records.get(provider, {}).get('scope', empty_scope(provider)))

    def require_current(self, expected, authenticated=True):
        expected = scope(expected, authenticated=authenticated)
        with self.lock:
            if expected != self.snapshot(expected['provider']):
                raise PanError('PAN_ACCOUNT_CHANGED')
        return expected

    def is_current(self, expected):
        try:
            self.require_current(expected, authenticated=False)
            return True
        except PanError:
            return False

    def run_if_current(self, expected, operation, authenticated=True):
        with self.lock:
            self.require_current(expected, authenticated)
            return operation()

    def credentials(self, expected):
        with self.lock:
            expected = self.require_current(expected)
            return deepcopy(self.records[expected['provider']]['credentials'])

    def subscribe(self, listener):
        with self.lock:
            self.listeners.append(listener)
        def unsubscribe():
            with self.lock:
                if listener in self.listeners:
                    self.listeners.remove(listener)
        return unsubscribe

    def _commit(self, previous, current, credentials):
        records = dict(self.records)
        records[current['provider']] = dict(scope=dict(current), credentials=deepcopy(credentials))
        _write(self.path, dict(version=1, accounts=records))
        self.records = records
        for listener in tuple(self.listeners) if previous != current else ():
            try:
                listener(dict(previous), dict(current))
            except Exception:
                continue  # Consumers must also check their own captured scope.
        return dict(current)

    def install(self, credentials, expected):
        expected = scope(expected)
        identity, checked = self._checked(expected['provider'], credentials)
        with self.lock:
            self.require_current(expected, authenticated=False)
            # Every explicit login replaces pending work, including same-user
            # logins. A late QR from the old generation must never win.
            current = scope(dict(expected, account_id=identity, authenticated=True,
                                 epoch=expected['epoch'] + 1))
            return self._commit(expected, current, checked)

    def renew(self, credentials, expected, previous=None):
        expected = scope(expected, authenticated=True)
        identity, checked = self._checked(expected['provider'], credentials)
        with self.lock:
            self.require_current(expected)
            if previous is not None and self.records[expected['provider']]['credentials'] != previous:
                raise PanError('PAN_CREDENTIALS_CHANGED')
            if identity != expected['account_id']:
                raise PanError('PAN_RENEW_IDENTITY_CHANGED')
            # Credential-only refresh is not a user/account switch.
            return self._commit(expected, expected, checked)

    def logout(self, expected):
        expected = scope(expected)
        with self.lock:
            self.require_current(expected, authenticated=False)
            # Even an already-logged-out logout revokes pending QR attempts.
            current = scope(dict(expected, account_id='', authenticated=False,
                                 epoch=expected['epoch'] + 1))
            return self._commit(expected, current, None)

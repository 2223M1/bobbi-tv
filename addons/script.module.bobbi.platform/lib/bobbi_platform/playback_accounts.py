"""Playback-only scope routing; 115 credentials/preparation remain unchanged."""
from pathlib import Path
import re

from bobbi_core.library_contract import LibraryError
from .libraries import Registry
from .pan_accounts import PanError, scope


class _RegistrySourceAccounts:
    """Playback scope verification for Registry-backed sources (T4, STRM, Emby source)."""

    def __init__(self, root, current=lambda: True):
        self.path = Path(root) / 'libraries.sqlite3'
        self.current = current

    def _matches(self, expected) -> bool:
        if not self.current() or not self.path.is_file():
            return False
        kind = expected.get('kind')
        source_id = expected.get('source_id')
        generation = expected.get('generation')
        if (
            not isinstance(source_id, str)
            or not re.fullmatch(r'[0-9a-f]{32}', source_id)
            or not isinstance(generation, str)
            or not re.fullmatch(r'[0-9a-f]{64}', generation)
        ):
            return False
        store = Registry(self.path, read_only=True, timeout=0)
        try:
            source, rev = store.source_snapshot(source_id)
        except (LibraryError, OSError, ValueError):
            return False
        finally:
            store.close()
        if rev != generation:
            return False
        if kind == 'library_source':
            return set(expected) == {'kind', 'source_id', 'generation'}
        if kind == 'emby_source':
            return (
                set(expected) == {'kind', 'provider', 'server_id', 'user_id', 'source_id', 'generation'}
                and expected.get('provider') == 'emby'
                and source.kind == 'media_server'
                and source.metadata.get('provider') == 'emby'
                and source.metadata.get('server_id') == expected.get('server_id')
                and source.metadata.get('user_id') == expected.get('user_id')
            )
        return False

    def require_current(self, expected, authenticated=True):
        if not self._matches(expected):
            raise PanError('PAN_ACCOUNT_CHANGED')
        return dict(expected)

    def is_current(self, expected):
        return self._matches(expected)

    def run_if_current(self, expected, operation, authenticated=True):
        self.require_current(expected, authenticated=authenticated)
        result = operation()
        self.require_current(expected, authenticated=authenticated)
        return result


class PlaybackAccounts:
    def __init__(self, legacy, pan_owner, *, registry_root=None, current=lambda: True):
        self.legacy, self.pan_owner = legacy, pan_owner
        self.registry_sources = (
            _RegistrySourceAccounts(registry_root, current=current)
            if registry_root is not None
            else None
        )

    def snapshot(self):
        # Existing account-independent/BT selection behavior remains 115.
        return self.legacy.snapshot()

    def _owner(self, expected):
        if type(expected) is dict and expected.get('kind') in ('library_source', 'emby_source'):
            if self.registry_sources is None:
                raise PanError('PAN_SERVICE_CLOSED')
            return self.registry_sources
        if type(expected) is dict and 'provider' in expected:
            scope(expected, authenticated=True)
            owner = self.pan_owner()
            if owner is None:
                raise PanError('PAN_SERVICE_CLOSED')
            return owner.accounts
        return self.legacy

    def require_current(self, expected, authenticated=True):
        return self._owner(expected).require_current(expected, authenticated=authenticated)

    def is_current(self, expected):
        try:
            return self._owner(expected).is_current(expected)
        except (ValueError, RuntimeError):
            return False

    def run_if_current(self, expected, operation, authenticated=True):
        return self._owner(expected).run_if_current(expected, operation, authenticated=authenticated)

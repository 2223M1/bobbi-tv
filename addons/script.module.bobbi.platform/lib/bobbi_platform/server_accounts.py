"""Registry-backed server authority. No extra credential/account persistence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from bobbi_core.library_contract import Source, LibraryError, server_location, validate_source
from .libraries import Registry
from .pan_accounts import PanError, SERVER_PROVIDERS, empty_scope, scope


class PlexBinding:
    """Startup-captured existing settings; an observed change never revives."""
    def __init__(self, read, current):
        self.read, self.profile_current, self.revoked = read, current, False
        self.saved = deepcopy(read())
        if not self.current():
            raise PanError('PAN_ACCOUNT_CHANGED')

    def __repr__(self):
        return '<Plex startup binding: credentials hidden>'

    def current(self):
        if not self.revoked:
            try:
                self.revoked = self.profile_current() is not True or self.read() != self.saved
            except (OSError, ValueError, RuntimeError):
                self.revoked = True
        return not self.revoked


class Accounts:
    def __init__(self, root, plex=None, current=lambda: True):
        self.path, self.plex, self.current = Path(root) / 'libraries.sqlite3', plex, current
        self.lock, self.listeners, self.observed = RLock(), [], {}
        self.observation_serial, self.observed_versions = 0, {}

    def _registry(self, *, timeout=0):
        # Strong checks retain the actual SQLite CAS, but a busy Registry is
        # unavailable immediately, not a one-second wait on the playback actor.
        return Registry(self.path, timeout=timeout)

    def _source(self, store, provider):
        if provider == 'emby':
            active, _ = store.emby_binding()
            return store.source_snapshot(active.id) if active else (None, None)
        rows = [source for source in store.sources() if source.kind == 'media_server'
                and source.metadata['provider'] == provider]
        if len(rows) > 1:
            raise PanError('PAN_ACCOUNT_ID_INVALID')
        return store.source_snapshot(rows[0].id) if rows else (None, None)

    @staticmethod
    def _scope(source, revision):
        data = source.metadata
        subject = json.dumps([data['server_id'], data['user_id']], separators=(',', ':'))
        account = data['provider'] + ':' + hashlib.sha256(subject.encode('ascii')).hexdigest()
        return scope(dict(provider=data['provider'], account_id=account, authenticated=True, epoch=0,
                          source_id=source.id, generation=revision))

    def _credentials(self, source):
        if not self.current():
            raise PanError('PAN_ACCOUNT_CHANGED')
        data = source.metadata
        saved = dict(provider=data['provider'], location=source.location,
                     server_id=data['server_id'], user_id=data['user_id'])
        if data['provider'] == 'plex':
            if (self.plex is None or not self.plex.current() or
                    server_location(self.plex.saved.get('location', '')) != source.location):
                raise PanError('PAN_CREDENTIALS_CHANGED')
            saved.update(token=self.plex.saved['token'], user_token=self.plex.saved['user_token'])
        else:
            saved['token'] = source.password
        return saved

    def _notify(self, value):
        with self.lock:
            key = value['provider']
            previous = self.observed.get(key)
            self.observed[key] = value
            self.observation_serial += 1
            self.observed_versions[key] = self.observation_serial
            if previous is not None and previous != value:
                for listener in tuple(self.listeners):
                    try:
                        listener(dict(previous), dict(value))
                    except Exception:
                        pass  # Each consumer still checks its captured full scope.
        return value

    def snapshot(self, provider):
        if provider not in dict(SERVER_PROVIDERS):
            raise PanError('PAN_PROVIDER_INVALID')
        store = self._registry()
        try:
            value = self._snapshot(store, provider)
        finally:
            store.close()
        return self._notify(value)

    def _snapshot(self, store, provider):
        try:
            source, revision = self._source(store, provider)
        except PanError:
            return empty_scope(provider)
        except LibraryError as exc:
            if str(exc) == 'SOURCE_NOT_FOUND':
                return empty_scope(provider)
            raise
        if source is None:
            return empty_scope(provider)
        try:
            self._credentials(source)
            return self._scope(source, revision)
        except (PanError, LibraryError):
            return empty_scope(provider)

    def require_current(self, expected, authenticated=True):
        expected = scope(expected, authenticated=authenticated)
        if expected != self.snapshot(expected['provider']):
            raise PanError('PAN_ACCOUNT_CHANGED')
        return expected

    def is_current(self, expected):
        try:
            self.require_current(expected, False)
            return True
        except (ValueError, OSError):
            return False

    def run_if_current(self, expected, operation, authenticated=True):
        expected = self.require_current(expected, authenticated)
        store = self._registry()
        try:
            source, revision = self._source(store, expected['provider'])
            if source is None or self._scope(source, revision) != expected:
                raise PanError('PAN_ACCOUNT_CHANGED')
            def publish():
                self._credentials(source)
                return operation()
            return store.run_if_current(source, revision, publish)
        except LibraryError:
            raise PanError('PAN_ACCOUNT_CHANGED') from None
        finally:
            store.close()

    def credentials(self, expected):
        self.require_current(expected)
        store = self._registry()
        try:
            source, revision = self._source(store, expected['provider'])
            if source is None or self._scope(source, revision) != expected:
                raise PanError('PAN_ACCOUNT_CHANGED')
            return self._credentials(source)
        finally:
            store.close()

    def subscribe(self, listener):
        with self.lock:
            self.listeners.append(listener)
        def unsubscribe():
            with self.lock:
                if listener in self.listeners:
                    self.listeners.remove(listener)
        return unsubscribe

    def poll(self):
        with self.lock:
            versions = dict(self.observed_versions)
            providers = tuple(versions)
        if not providers:
            return
        # One nonblocking, read-only opening for this observation pass. Busy
        # storage is not logout; authoritative operations still recheck their
        # full source/revision through require_current/run_if_current.
        try:
            store = Registry(self.path, read_only=True)
            try:
                values = [self._snapshot(store, provider) for provider in providers]
            finally:
                store.close()
        except (LibraryError, OSError, sqlite3.Error):
            # Observation failure is unknown, not an account-change event.
            # Do not spuriously revoke an unchanged live selection. Explicit
            # controls still fail closed under their fresh strong scope check.
            return False
        for value in values:
            with self.lock:
                provider = value['provider']
                if self.observed_versions.get(provider) == versions[provider]:
                    self._notify(value)
        return True

    def register(self, provider, name, location='', secret='', expected_source=None, client_factory=None,
                 current=lambda: True, publish=lambda write: write(), username=None, password=None):
        if not self.current() or not current():
            raise PanError('PAN_ACCOUNT_CHANGED')
        if provider not in dict(SERVER_PROVIDERS):
            raise PanError('PAN_PROVIDER_INVALID')
        store = self._registry()
        try:
            activate_emby = None
            if provider == 'emby':
                _, activate_emby = store.emby_binding()
                previous, revision = store.source_snapshot(expected_source) if expected_source else (None, None)
                if previous and (previous.kind != 'media_server' or previous.metadata['provider'] != provider):
                    raise PanError('PAN_ACCOUNT_CHANGED')
            else:
                previous, revision = self._source(store, provider)
            if (previous.id if previous else None) != expected_source:
                raise PanError('PAN_ACCOUNT_CHANGED')
            device = None
            if username is not None or password is not None:
                if provider != 'emby' or secret or not username or not isinstance(password, str):
                    raise PanError('PAN_CREDENTIALS_INVALID')
                with store.db:
                    store.db.execute('INSERT OR IGNORE INTO metadata(key,value) VALUES (?,?)',
                                     ('emby_install_device', uuid4().hex))
                    device = store.db.execute('SELECT value FROM metadata WHERE key=?',
                                              ('emby_install_device',)).fetchone()[0]
        finally:
            store.close()
        if provider == 'plex':
            if self.plex is None or not self.plex.current() or location or secret:
                raise PanError('PAN_CREDENTIALS_INVALID')
            saved = dict(self.plex.saved, provider=provider)
        elif device:
            from .server_emby import authenticate
            sid, uid, secret = authenticate(server_location(location), username, password, device)
            saved = dict(provider=provider, location=server_location(location), token=secret,
                         server_id=sid, user_id=uid)
        else:
            saved = dict(provider=provider, location=server_location(location), token=secret)
        if client_factory is None:
            from .pan_providers import descriptor
            client_factory = lambda key, value: descriptor(key).client(value)
        client = client_factory(provider, saved)
        with client.session.budget(24):
            sid, uid = client.verify()
        if device and (sid, uid) != (saved['server_id'], saved['user_id']):
            raise PanError('PAN_ACCOUNT_ID_INVALID')
        if previous is not None and (sid, uid) != (previous.metadata['server_id'], previous.metadata['user_id']):
            raise PanError('PAN_ACCOUNT_ID_INVALID')  # Explicit removal before a different account replaces it.
        source = validate_source(Source(previous.id if previous else uuid4().hex, name, 'media_server',
            server_location(saved['location']), password='' if provider == 'plex' else secret,
            metadata=dict(schema=1, provider=provider, server_id=sid, user_id=uid)))
        if not self.current() or not current() or provider == 'plex' and not self.plex.current():
            raise PanError('PAN_ACCOUNT_CHANGED')
        store = self._registry()
        try:
            if not self.current() or not current():
                raise PanError('PAN_ACCOUNT_CHANGED')
            publish(lambda: store.save(source, expected_snapshot=(previous, revision), activate_emby=activate_emby))
        finally:
            store.close()
        return self.snapshot(provider)

    def activate_emby(self, source_id, generation, expected, *, publish=lambda fn: fn()):
        """Explicit account switch with CAS on both selection and destination."""
        if not self.current():
            raise PanError('PAN_ACCOUNT_CHANGED')
        expected = scope(expected, 'emby', authenticated=False)
        store = self._registry()
        try:
            _, binding = store.emby_binding()
            if self._snapshot(store, 'emby') != expected:
                raise PanError('PAN_ACCOUNT_CHANGED')
            target, revision = store.source_snapshot(source_id)
            if (revision != generation or target.kind != 'media_server' or target.metadata['provider'] != 'emby'
                    or not self.current()):
                raise PanError('PAN_ACCOUNT_CHANGED')
            self._credentials(target)
            publish(lambda: store.save(target, expected_snapshot=(target, revision), activate_emby=binding))
        finally:
            store.close()
        return self.snapshot('emby')

    def logout(self, expected):
        self.require_current(expected)
        store = self._registry()
        try:
            source, revision = self._source(store, expected['provider'])
            def remove():
                store.db.execute('DELETE FROM sources WHERE id=?', (source.id,))
                store.db.execute('DELETE FROM metadata WHERE key=?', ('source_revision:' + source.id,))
                store.db.execute('DELETE FROM metadata WHERE key=?', ('emby_retained_revisions:' + source.id,))
            store.run_if_current(source, expected['generation'], remove)
        finally:
            store.close()
        return self.snapshot(expected['provider'])

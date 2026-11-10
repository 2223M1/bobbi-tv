"""Host-owned native cloud control. No Kodi, network work under account locks,
credentials in status, implicit file transfers, or automatic source selection.
"""
from functools import partial
from collections import OrderedDict
from copy import deepcopy
from contextlib import contextmanager, nullcontext
import re
from threading import Event, Lock, RLock
import time
from uuid import uuid4

from .pan_accounts import PROVIDERS, PanAccounts, PanError, scope
from .pan_http import credentials
from .pan_quark_uc import Client, QuarkLogin, UCLogin
from .pan_baidu import Client as BaiduClient, Login as BaiduLogin
from .pan_aliyun import Client as AliyunClient, Login as AliyunLogin, credentials as aliyun_credentials
from .pan_123 import Client as Cloud123Client, Login as Cloud123Login, credentials as cloud123_credentials
from .pan_device import Login as DeviceLogin, credentials as device_credentials
from .pan_guangya import Client as GuangyaClient
from .pan_xunlei import Client as XunleiClient
from .pan_mobile import Client as MobileClient, Login as MobileLogin, credentials as mobile_credentials
from .pan_tianyi import Client as TianyiClient, Login as TianyiLogin


def _client(provider, saved):
    if provider == 'xunlei':
        return XunleiClient(saved)
    if provider == '189':
        return TianyiClient(saved)
    if provider == '139':
        return MobileClient(saved)
    if provider == 'aliyun':
        return AliyunClient(saved)
    if provider == '123':
        return Cloud123Client(saved)
    if provider == 'guangya':
        return GuangyaClient(saved)
    if provider == 'baidu':
        return BaiduClient(saved)
    return Client(provider, saved)


def _attempt_id(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise PanError('PAN_ATTEMPT_INVALID')
    return value


def _budget(client, seconds):
    budget = getattr(getattr(client, 'session', None), 'budget', None)
    return budget(seconds) if callable(budget) else nullcontext()


class Attempt:
    def __init__(self, attempt_id, expected, flow, now):
        self.id, self.expected, self.flow, self.created = attempt_id, dict(expected), flow, now
        self.lock, self.cancelled = Lock(), Event()
        self.state, self.qr, self.saved, self.result = 'starting', None, None, None

    def view(self):
        value = dict(attempt=self.id, state=self.state)
        if self.state == 'waiting':
            if type(self.qr) is str:
                value['qr'] = self.qr
            else:
                value['qr_png'] = self.qr['png']
        if self.result is not None:
            value['account'] = dict(self.result)
        return value


class PanService:
    def __init__(self, root, legacy, accounts=None, login_factory=None, client_factory=_client,
                 clock=time.monotonic):
        validators = {key: partial(credentials, key) for key in ('quark', 'uc', 'baidu', '189')}
        validators.update(aliyun=aliyun_credentials, **{'123': cloud123_credentials})
        validators['139'] = mobile_credentials
        validators.update({p: partial(device_credentials, p) for p in ('guangya', 'xunlei')})
        self.accounts = accounts if accounts is not None else PanAccounts(root / 'pan-accounts-v1.json', validators)
        self.legacy, self.clock = legacy, clock
        self.login_factory = login_factory if login_factory is not None else {
            'quark': QuarkLogin, 'uc': UCLogin, 'baidu': BaiduLogin,
            'aliyun': AliyunLogin, '123': Cloud123Login, '139': MobileLogin, '189': TianyiLogin,
            'guangya': partial(DeviceLogin, 'guangya'), 'xunlei': partial(DeviceLogin, 'xunlei')}
        self.client_factory, self.lock = client_factory, RLock()
        self.attempts, self.closed = {}, False
        # Serialize credential-bearing IO per provider, not across all drives.
        # Account switches/cancellation never wait for this network lock.
        self.client_locks = {key: Lock() for key, _ in PROVIDERS if key != '115'}
        self.directory_cache = OrderedDict()
        self.directory_revision = 0
        self.streams = None
        self.cancelled_streams = OrderedDict()
        self.play_tickets = OrderedDict()

    def _prune(self):
        for provider, attempt in tuple(self.attempts.items()):
            if self.clock() - attempt.created >= 240:
                attempt.cancelled.set()
                attempt.saved = None
                del self.attempts[provider]

    def status(self):
        rows = []
        for key, label in PROVIDERS:
            account = self.legacy.snapshot() if key == '115' else self.accounts.snapshot(key)
            # Capabilities describe wired operations, never inferred from
            # symbols, a mounted drive, saved cookies or an HTTP status alone.
            capabilities = (['qr_login', 'share_play'] if key == '115' else
                            ['qr_login', 'list_files', 'personal_play'] if key in self.login_factory else [])
            rows.append(dict(provider=key, label=label, account=account,
                capabilities=capabilities, verification='existing' if key == '115' else 'not_device_verified'))
        return dict(providers=rows)

    def _find(self, provider, attempt_id):
        attempt = self.attempts.get(provider)
        if attempt is None or attempt.id != _attempt_id(attempt_id):
            raise PanError('PAN_ATTEMPT_EXPIRED')
        return attempt

    def _live(self, attempt):
        if self.closed or attempt.cancelled.is_set() or self.clock() - attempt.created >= 180:
            attempt.saved, attempt.state = None, 'cancelled'
            return False
        if not self.accounts.is_current(attempt.expected):
            attempt.saved, attempt.state = None, 'account_changed'
            attempt.cancelled.set()
            return False
        return True

    def begin(self, provider, attempt_id, expected):
        expected = scope(expected, provider)
        _attempt_id(attempt_id)
        if provider not in self.login_factory:
            raise PanError('PAN_LOGIN_UNAVAILABLE')
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            self._prune()
            self.accounts.require_current(expected, authenticated=False)
            previous = self.attempts.get(provider)
            if previous is not None:
                if previous.id == attempt_id:
                    if previous.expected != expected:
                        raise PanError('PAN_ATTEMPT_CONFLICT')
                    return previous.view()  # Lost reply does not mint another QR.
                if previous.state in ('starting', 'waiting', 'ready') and self._live(previous):
                    raise PanError('PAN_LOGIN_BUSY')
                previous.cancelled.set()
                previous.saved = None
            attempt = Attempt(attempt_id, expected, self.login_factory[provider](), self.clock())
            self.attempts[provider] = attempt
        with attempt.lock:
            try:
                with _budget(attempt.flow, 16):
                    qr = attempt.flow.begin()
                with self.lock:
                    if self._live(attempt):
                        attempt.qr, attempt.state = qr, 'waiting'
                    else:
                        attempt.flow.cancel()
                    return attempt.view()
            except Exception:
                with self.lock:
                    attempt.state, attempt.saved = 'failed', None
                    attempt.flow.cancel()
                raise

    def poll(self, provider, attempt_id):
        with self.lock:
            self._prune()
            attempt = self._find(provider, attempt_id)
            if attempt.state in ('committed', 'cancelled', 'failed', 'account_changed'):
                return attempt.view()
            if not self._live(attempt) or attempt.state in ('starting', 'ready'):
                return attempt.view()
        if not attempt.lock.acquire(False):
            return dict(attempt=attempt.id, state='polling')
        try:
            with self.lock:
                if not self._live(attempt) or attempt.state != 'waiting':
                    return attempt.view()
            with _budget(attempt.flow, 24):
                state, saved = attempt.flow.poll()
            with self.lock:
                if not self._live(attempt):
                    attempt.flow.cancel()
                    return attempt.view()
                if state == 'ready':
                    # Validate before retaining, but do not persist until the
                    # live UI explicitly commits. Cancel during HTTP is safe.
                    self.accounts._checked(provider, saved)
                    attempt.saved, attempt.state = saved, 'ready'
                elif state != 'waiting':
                    raise PanError('PAN_QR_STATE_INVALID')
                return attempt.view()
        except PanError as error:
            if str(error) not in ('PAN_NETWORK_ERROR', 'PAN_QR_POLL_RETRY'):
                with self.lock:
                    attempt.state, attempt.saved = 'failed', None
                    attempt.flow.cancel()
            raise
        finally:
            attempt.lock.release()

    def commit(self, provider, attempt_id):
        with self.lock:
            self._prune()
            attempt = self._find(provider, attempt_id)
            if attempt.state == 'committed':
                return attempt.view()
            if not self._live(attempt) or attempt.state != 'ready':
                raise PanError('PAN_LOGIN_NOT_READY')
            result = self.accounts.install(attempt.saved, attempt.expected)
            attempt.result, attempt.saved, attempt.state = result, None, 'committed'
            return attempt.view()

    def cancel(self, provider, attempt_id):
        with self.lock:
            attempt = self._find(provider, attempt_id)
            if attempt.state != 'committed':
                attempt.cancelled.set()
                attempt.saved, attempt.state = None, 'cancelled'
            return attempt.view()  # Never claim unchanged if commit already won.

    def logout(self, expected):
        expected = scope(expected)
        with self.lock:
            result = self.accounts.logout(expected)
            attempt = self.attempts.get(expected['provider'])
            if attempt is not None:
                attempt.cancelled.set()
                attempt.saved = None
            return result

    @contextmanager
    def _using_client(self, expected):
        expected = scope(expected, authenticated=True)
        provider = expected['provider']
        if not self.client_locks[provider].acquire(timeout=.1):
            raise PanError('PAN_OPERATION_BUSY')
        try:
            with self.lock:
                if self.closed:
                    raise PanError('PAN_SERVICE_CLOSED')
            saved = self.accounts.credentials(expected)
            client = self.client_factory(provider, saved)
            def publish(current, previous):
                with self.lock:
                    if self.closed:
                        raise PanError('PAN_SERVICE_CLOSED')
                    self.accounts.renew(current, expected, previous=previous)
            with _budget(client, 24):
                renew = getattr(client, 'renew_if_needed', None)
                if renew:
                    renew(publish)
                yield client
                # Cookie rotation is persisted by the same owner/CAS as token
                # renewal; it may never restore a logged-out/switched account.
                if provider in ('quark', 'uc', 'baidu', '189'):
                    export = getattr(getattr(client, 'session', None), 'export', None)
                    if callable(export):
                        current = export(subject=saved.get('subject'), session_key=saved.get('session_key'))
                        if current != saved:
                            publish(current, saved)
            self.accounts.require_current(expected)
        finally:
            self.client_locks[provider].release()

    def list_files(self, expected, parent, page, cursor=None, refresh=False):
        expected = scope(expected, authenticated=True)
        provider = expected['provider']
        if (type(parent) is not str or len(parent) > 4096 or type(page) is not int
                or not 1 <= page <= 10000 or type(refresh) is not bool
                or cursor is not None and (type(cursor) is not str or len(cursor) > 2048)):
            raise PanError('PAN_PAGE_INVALID')
        cache_key = (provider, expected['account_id'], expected['epoch'], parent, page, cursor)
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            self.accounts.require_current(expected)
            if refresh:
                # A new first page invalidates the entire folder's previous
                # page/marker chain, not just the one page being requested.
                self.directory_revision += 1
                for key in tuple(self.directory_cache):
                    if key[:4] == cache_key[:4]:
                        del self.directory_cache[key]
            revision = self.directory_revision
            cached = self.directory_cache.get(cache_key)
            if not refresh and cached is not None and self.clock() - cached[0] < 20:
                self.directory_cache.move_to_end(cache_key)
                return deepcopy(cached[1])
        with self._using_client(expected) as client:
            if cursor is not None and provider not in ('aliyun', '139', 'xunlei'):
                raise PanError('PAN_PAGE_INVALID')
            result = (client.list_files(parent, page, size=10, cursor=cursor or '') if provider in ('aliyun', '139', 'xunlei')
                      else client.list_files(parent, page, size=10))
        # Check after all IO. Never publish a directory read for a logged-out
        # or switched account, even if the HTTP request itself succeeded.
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            def publish_result():
                # A read already in flight when a refresh starts may finish,
                # but must not repopulate the freshly invalidated page cache.
                if revision != self.directory_revision:
                    return result
                self.directory_cache[cache_key] = (self.clock(), deepcopy(result))
                self.directory_cache.move_to_end(cache_key)
                while len(self.directory_cache) > 64:
                    self.directory_cache.popitem(last=False)
                return result
            return self.accounts.run_if_current(expected, publish_result)

    def _resolve_stream(self, body, expected):
        from .pan_stream import address
        if body['provider'] != expected['provider']:
            raise PanError('PAN_SCOPE_INVALID')
        with self._using_client(expected) as client:
            result = address(body, client.resolve_original(body['selected']))
        return result

    def prepare_play(self, expected, selected):
        from .pan_stream import body
        expected = scope(expected, authenticated=True)
        ticket = uuid4().hex
        checked = body(expected['provider'], selected, ticket)
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            self.accounts.require_current(expected)
            # The opaque ticket represents an item actually shown in this
            # account's directory, not an arbitrary locator supplied by a URL.
            prefix = (expected['provider'], expected['account_id'], expected['epoch'])
            if not any(key[:3] == prefix and selected in value['items']
                       for key, (_, value) in self.directory_cache.items()):
                raise PanError('PAN_PLAY_EXPIRED')
            self.play_tickets[ticket] = (self.clock() + 120, expected, checked['selected'])
            while len(self.play_tickets) > 32:
                self.play_tickets.popitem(last=False)
        return dict(ticket=ticket)

    def claim_play(self, ticket):
        _attempt_id(ticket)
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            value = self.play_tickets.pop(ticket, None)
            if value is None or self.clock() >= value[0]:
                raise PanError('PAN_PLAY_EXPIRED')
            self.accounts.require_current(value[1])
            return dict(request_id=ticket, account=deepcopy(value[1]), selected=deepcopy(value[2]))

    def open_stream(self, expected, selected, request):
        from . import pan_stream
        from bobbi_core.share_stream import ShareStream
        expected = scope(expected, authenticated=True)
        body = pan_stream.body(expected['provider'], selected, request)
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            self.accounts.require_current(expected)
            if request in self.cancelled_streams:
                raise PanError('PAN_SELECTION_CANCELLED')
            if self.streams is None:
                self.streams = ShareStream(pan_stream.checked, self._resolve_stream, lambda url: True,
                    account=self.accounts, body_check=pan_stream.checked, header_check=pan_stream.headers,
                    observer=lambda row: None)
            result = self.streams.register(body, account=expected)
            with self.streams.lock:
                entry = self.streams.records[request]
        # Resolve exact metadata/original before publishing the local URL;
        # every later expired-address renewal repeats the same identity check.
        entry.grant()
        with self.lock:
            if self.closed or entry.cancelled() or request in self.cancelled_streams:
                raise PanError('PAN_SELECTION_CANCELLED')
            return self.accounts.run_if_current(expected, lambda: dict(result, account=expected))

    def close_stream(self, expected, request):
        expected = scope(expected, authenticated=True)
        _attempt_id(request)
        with self.lock:
            self.accounts.require_current(expected)
            if self.streams is not None:
                with self.streams.lock:
                    entry = self.streams.records.get(request)
                    if entry is not None and entry.scope != expected:
                        raise PanError('PAN_SCOPE_INVALID')
                    if entry is not None:
                        entry.revoke()
            self.cancelled_streams[request] = self.clock()
            while len(self.cancelled_streams) > 128:
                self.cancelled_streams.popitem(last=False)
            return dict(cancelled=True)

    def dispatch(self, action, body):
        if self.closed or type(body) is not dict:
            raise PanError('PAN_SERVICE_CLOSED')
        fields = set(body)
        if action == 'pan_status' and not body:
            return self.status()
        if action == 'pan_login_begin' and fields == {'provider', 'attempt', 'expected'}:
            return self.begin(body['provider'], body['attempt'], body['expected'])
        if fields == {'provider', 'attempt'}:
            method = {'pan_login_poll': self.poll, 'pan_login_commit': self.commit,
                      'pan_login_cancel': self.cancel}.get(action)
            if method:
                try:
                    return method(body['provider'], body['attempt'])
                except PanError as error:
                    if action != 'pan_login_poll' or str(error) not in ('PAN_NETWORK_ERROR', 'PAN_QR_POLL_RETRY'):
                        raise
                    with self.lock:
                        attempt = self._find(body['provider'], body['attempt'])
                        if not self._live(attempt):
                            return attempt.view()
                        # A bounded HTTP long-poll can time out before the
                        # user scans. Report a retry, never fake "waiting".
                        return dict(attempt=attempt.id, state='retry', reason='network')
        if action == 'pan_logout' and fields == {'expected'}:
            return self.logout(body['expected'])
        if action == 'pan_open_stream' and fields == {'expected', 'selected', 'request_id'}:
            return self.open_stream(body['expected'], body['selected'], body['request_id'])
        if action == 'pan_close_stream' and fields == {'expected', 'request_id'}:
            return self.close_stream(body['expected'], body['request_id'])
        if action == 'pan_prepare_play' and fields == {'expected', 'selected'}:
            return self.prepare_play(body['expected'], body['selected'])
        if action == 'pan_claim_play' and fields == {'ticket'}:
            return self.claim_play(body['ticket'])
        if (action == 'pan_list_files' and {'expected', 'parent', 'page'} <= fields
                and fields <= {'expected', 'parent', 'page', 'cursor', 'refresh'}):
            return self.list_files(body['expected'], body['parent'], body['page'],
                body.get('cursor'), body.get('refresh', False))
        raise PanError('PAN_ACTION_INVALID')

    def close(self):
        with self.lock:
            self.closed = True
            self.directory_cache.clear()
            self.play_tickets.clear()
            for attempt in self.attempts.values():
                attempt.cancelled.set()
                attempt.saved = None
            streams = self.streams
        if streams is not None:
            streams.close()

"""Host-owned native cloud control. No Kodi, network work under account locks,
credentials in status, implicit file transfers, or automatic source selection.
"""
from collections import OrderedDict
from copy import deepcopy
from contextlib import contextmanager, nullcontext
import re
from threading import Event, Lock, RLock
import time
from uuid import uuid4

from .pan_accounts import PROVIDERS, PanAccounts, PanError, scope
from .pan_providers import DESCRIPTORS, descriptor
from .pan_request_policy import Operation, Cooldowns
from .runtime import encode_message, MAX_MESSAGE_BYTES, LOGIN_ERROR_PHASES

DIRECTORY_REPLY_BYTES = MAX_MESSAGE_BYTES - 512
DIRECTORY_CACHE_BYTES = 2 * 1024 * 1024
DIRECTORY_TTL = 20


def _client(provider, saved):
    return descriptor(provider).client(saved)


def _attempt_id(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise PanError('PAN_ATTEMPT_INVALID')
    return value


def _budget(client, seconds):
    budget = getattr(getattr(client, 'session', None), 'budget', None)
    return budget(seconds) if callable(budget) else nullcontext()


def _capture_login_phase(error, flow):
    phase = getattr(flow, 'phase', None)
    if isinstance(error, PanError) and type(phase) is str and phase in LOGIN_ERROR_PHASES:
        error.login_phase = phase  # Capture before cancel() clears the live stage.


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
        validators = {key: value.validator for key, value in DESCRIPTORS.items()}
        self.accounts = accounts if accounts is not None else PanAccounts(root / 'pan-accounts-v1.json', validators)
        self.legacy, self.clock = legacy, clock
        self.login_factory = login_factory if login_factory is not None else {
            key: value.login for key, value in DESCRIPTORS.items()}
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
        self.play_file_refs = {}
        self.cancelled_attempts = OrderedDict()
        self.directory_pages = OrderedDict()
        self.operations, self.operation_receipts = {}, OrderedDict()
        self.cooldowns = Cooldowns(self.clock)
        self.accounts.subscribe(self._account_changed)

    def _account_changed(self, previous, current):
        # PanAccounts invokes listeners under its own lock. Never invert the
        # service->account lock order here; scope gates revoke cache publication.
        for operation in tuple(self.operations.values()):
            if operation.expected == previous:
                operation.cancelled.set()

    def _require_operation_current(self, expected):
        if self.closed:
            raise PanError('PAN_SERVICE_CLOSED')
        return self.accounts.require_current(expected)

    def _prune(self):
        for cache in (self.cancelled_attempts, self.operation_receipts):
            for key, value in tuple(cache.items()):
                if self.clock() - value[0] >= 240:
                    del cache[key]
            while len(cache) > 128:
                cache.popitem(last=False)
        for key, value in tuple(self.directory_pages.items()):
            if self.clock() - value[0] >= DIRECTORY_TTL:
                del self.directory_pages[key]
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
                **(dict(capabilities=capabilities, verification='existing') if key == '115' else
                   dict(descriptor(key).public(), capabilities=capabilities))))
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

    def _login_operation(self, attempt, seconds):
        operation = Operation(attempt.expected, attempt.id, 'login', clock=self.clock, seconds=seconds,
            current=lambda value: self.accounts.require_current(value, authenticated=False), cooldowns=self.cooldowns)
        operation.cancelled = attempt.cancelled
        session = getattr(attempt.flow, 'session', None)
        if session is not None and hasattr(session, 'operation'):
            session.operation = operation
        return operation

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
            if (provider, attempt_id) in self.cancelled_attempts:
                return dict(attempt=attempt_id, state='cancelled')
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
                self._login_operation(attempt, 16).check()
                with _budget(attempt.flow, 16):
                    qr = attempt.flow.begin()
                with self.lock:
                    if self._live(attempt):
                        attempt.qr, attempt.state = qr, 'waiting'
                    else:
                        attempt.flow.cancel()
                    return attempt.view()
            except Exception as error:
                _capture_login_phase(error, attempt.flow)
                with self.lock:
                    attempt.state, attempt.saved = ('cancelled' if attempt.cancelled.is_set() else 'failed'), None
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
            self._login_operation(attempt, 24).check()
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
            _capture_login_phase(error, attempt.flow)
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
            descriptor(provider)
            _attempt_id(attempt_id)
            self._prune()
            attempt = self.attempts.get(provider)
            if attempt is None or attempt.id != attempt_id:
                self.cancelled_attempts[(provider, attempt_id)] = (self.clock(), None)
                self._prune()
                return dict(attempt=attempt_id, state='cancel_requested')
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
    def _using_client(self, expected, operation=None):
        expected = scope(expected, authenticated=True)
        provider = expected['provider']
        if operation is not None:
            operation.check()
        if not self.client_locks[provider].acquire(timeout=.1):
            if operation is not None:
                operation.check()
            raise PanError('PAN_OPERATION_BUSY')
        try:
            with self.lock:
                if self.closed:
                    raise PanError('PAN_SERVICE_CLOSED')
            saved = self.accounts.credentials(expected)
            client = self.client_factory(provider, saved)
            session = getattr(client, 'session', None)
            if session is not None and hasattr(session, 'operation'):
                session.operation = operation
            def publish(current, previous):
                with self.lock:
                    if self.closed:
                        raise PanError('PAN_SERVICE_CLOSED')
                    self.accounts.renew(current, expected, previous=previous)
            with _budget(client, 24):
                renew = getattr(client, 'renew_if_needed', None)
                if renew:
                    with operation.maintenance() if operation is not None else nullcontext():
                        renew(publish)
                if operation is not None:
                    operation.check()
                # Cookie rotation is persisted by the same owner/CAS as token
                # renewal; it may never restore a logged-out/switched account.
                try:
                    yield client
                finally:
                    if descriptor(provider).cookie_rotation:
                        export = getattr(session, 'export', None)
                        if callable(export):
                            current = export(subject=saved.get('subject'), session_key=saved.get('session_key'))
                            if current != saved:
                                publish(current, saved)
            self.accounts.require_current(expected)
            if operation is not None:
                operation.check()
        finally:
            self.client_locks[provider].release()

    @contextmanager
    def scan_operation(self, expected, operation_id=None, *, max_pages=32, max_items=2000,
                       max_requests=96, seconds=90, kind='scan'):
        expected = scope(expected, authenticated=True)
        operation_id = operation_id or uuid4().hex
        operation = Operation(expected, operation_id, kind, clock=self.clock, seconds=seconds,
                              max_pages=max_pages, max_items=max_items, max_requests=max_requests,
                              current=self._require_operation_current, cooldowns=self.cooldowns)
        with self.lock:
            self._prune()
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            if operation_id in self.operations or operation_id in self.operation_receipts:
                raise PanError('PAN_OPERATION_EXPIRED')
            if len(self.operations) >= 32:
                raise PanError('PAN_OPERATION_BUSY')
            self.operations[operation_id] = operation
        try:
            operation.check()
            yield operation
        finally:
            with self.lock:
                self.operations.pop(operation_id, None)
                self.operation_receipts[operation_id] = (self.clock(), expected)
                self._prune()

    def cancel_operation(self, expected, operation_id):
        expected = scope(expected, authenticated=True)
        _attempt_id(operation_id)
        with self.lock:
            self.accounts.require_current(expected)
            operation = self.operations.get(operation_id)
            if operation is not None:
                if operation.expected != expected:
                    raise PanError('PAN_SCOPE_INVALID')
                operation.cancelled.set()
            else:
                self.operation_receipts[operation_id] = (self.clock(), expected)
                self._prune()
        return dict(cancelled=True)

    def list_for_scan(self, expected, parent, page=1, cursor=None, *, operation, size=20):
        expected = scope(expected, authenticated=True)
        if (operation.expected != expected or type(size) is not int or not 1 <= size <= 20
                or type(parent) is not str or len(parent) > 4096 or type(page) is not int
                or not 1 <= page <= 10000 or cursor is not None and
                (type(cursor) is not str or len(cursor) > 2048)):
            raise PanError('PAN_PAGE_INVALID')
        operation.check()
        # Do not make an additional remote call once the page budget is spent.
        if operation.pages >= operation.max_pages:
            raise PanError('PAN_BUDGET_EXHAUSTED')
        with self._using_client(expected, operation) as client:
            if descriptor(expected['provider']).pagination == 'cursor':
                result = client.list_files(parent, page, size=size, cursor=cursor or '')
            else:
                if cursor is not None:
                    raise PanError('PAN_PAGE_INVALID')
                result = client.list_files(parent, page, size=size)
        operation.consume_page(len(result['items']))
        return result

    def _slice_directory(self, result, key, revision, snapshot=None, offset=0):
        if len(encode_message(dict(ok=True, result=result))) <= DIRECTORY_REPLY_BYTES and not snapshot:
            return deepcopy(result)
        snapshot = snapshot or uuid4().hex
        items = result.get('items')
        if type(items) is not list:
            raise PanError('PAN_REPLY_INVALID')
        if len(encode_message(result)) > DIRECTORY_CACHE_BYTES:
            raise PanError('PAN_ITEM_TOO_LARGE')
        reply = dict(result, items=[], upstream_has_more=bool(result.get('has_more')))
        for index in range(offset, len(items)):
            candidate = dict(reply, items=reply['items'] + [items[index]])
            if index + 1 < len(items):
                candidate.update(has_more=True, continuation=snapshot + '.' + str(index + 1))
                candidate.pop('next_cursor', None)
            else:
                candidate.pop('continuation', None)
                candidate['has_more'] = bool(result.get('has_more'))
                if 'next_cursor' in result:
                    candidate['next_cursor'] = result['next_cursor']
            if len(encode_message(dict(ok=True, result=candidate))) > DIRECTORY_REPLY_BYTES:
                if not reply['items']:
                    raise PanError('PAN_ITEM_TOO_LARGE')
                break
            reply = candidate
        if not reply['items'] or len(encode_message(dict(ok=True, result=reply))) > DIRECTORY_REPLY_BYTES:
            raise PanError('PAN_ITEM_TOO_LARGE')
        created = self.directory_pages[snapshot][0] if snapshot in self.directory_pages else self.clock()
        self.directory_pages[snapshot] = (created, key, revision, deepcopy(result))
        while (len(self.directory_pages) > 64 or
               sum(len(encode_message(v[3])) for v in self.directory_pages.values()) > DIRECTORY_CACHE_BYTES):
            self.directory_pages.popitem(last=False)
        return reply

    def list_files(self, expected, parent, page, cursor=None, refresh=False, continuation=None,
                   operation_id=None, operation=None):
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
            self._prune()
            if operation is not None:
                if operation.expected != expected:
                    raise PanError('PAN_SCOPE_INVALID')
                operation.check()
            if operation_id is not None:
                _attempt_id(operation_id)
                if operation_id in self.operation_receipts:
                    raise PanError('PAN_OPERATION_EXPIRED')
            if continuation is not None:
                if refresh or type(continuation) is not str or not re.fullmatch(r'[0-9a-f]{32}\.[0-9]{1,5}', continuation):
                    raise PanError('PAN_PAGE_EXPIRED')
                snapshot, offset = continuation.split('.')
                value = self.directory_pages.get(snapshot)
                if (value is None or value[1] != cache_key or value[2] != self.directory_revision
                        or not 0 < int(offset) < len(value[3]['items'])):
                    raise PanError('PAN_PAGE_EXPIRED')
                return self._slice_directory(value[3], cache_key, value[2], snapshot, int(offset))
            if refresh:
                # A new first page invalidates the entire folder's previous
                # page/marker chain, not just the one page being requested.
                self.directory_revision += 1
                self.directory_pages.clear()
                for key in tuple(self.directory_cache):
                    if key[:4] == cache_key[:4]:
                        del self.directory_cache[key]
            revision = self.directory_revision
            cached = self.directory_cache.get(cache_key)
            if not refresh and cached is not None and self.clock() - cached[0] < 20:
                self.directory_cache.move_to_end(cache_key)
                return self._slice_directory(cached[1], cache_key, revision)
        context = (nullcontext(operation) if operation is not None else
                   self.scan_operation(expected, operation_id, kind='directory', seconds=24,
                                       max_pages=1, max_items=100, max_requests=16))
        with context as active_operation:
            result = self.list_for_scan(expected, parent, page, cursor, operation=active_operation, size=10)
        # Check after all IO. Never publish a directory read for a logged-out
        # or switched account, even if the HTTP request itself succeeded.
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            def publish_result():
                active_operation.check()
                # A read already in flight when a refresh starts may finish,
                # but must not repopulate the freshly invalidated page cache.
                if revision != self.directory_revision:
                    raise PanError('PAN_PAGE_EXPIRED')
                reply = self._slice_directory(result, cache_key, revision)
                self.directory_cache[cache_key] = (self.clock(), deepcopy(result))
                self.directory_cache.move_to_end(cache_key)
                while (len(self.directory_cache) > 64 or
                       sum(len(encode_message(v[1])) for v in self.directory_cache.values()) > DIRECTORY_CACHE_BYTES):
                    self.directory_cache.popitem(last=False)
                return reply
            return self.accounts.run_if_current(expected, publish_result)

    def _resolve_stream(self, body, expected):
        from .pan_stream import address
        if body['provider'] != expected['provider']:
            raise PanError('PAN_SCOPE_INVALID')
        with self._using_client(expected) as client:
            result = address(body, client.resolve_original(body['selected']))
        return result

    def prepare_play(self, expected, selected, request_id=None):
        from .pan_stream import body
        expected = scope(expected, authenticated=True)
        ticket = _attempt_id(request_id) if request_id is not None else uuid4().hex
        checked = body(expected['provider'], selected, ticket)
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            self.accounts.require_current(expected)
            if ticket in self.cancelled_streams:
                raise PanError('PAN_SELECTION_CANCELLED')
            # The opaque ticket represents an item actually shown in this
            # account's directory, not an arbitrary locator supplied by a URL.
            prefix = (expected['provider'], expected['account_id'], expected['epoch'])
            parent = next((key[3] for key, (_, value) in self.directory_cache.items()
                           if key[:3] == prefix and selected in value['items']), None)
            if parent is None:
                raise PanError('PAN_PLAY_EXPIRED')
            from bobbi_core.file_ref import from_selected
            self.play_file_refs[ticket] = from_selected(expected, selected, parent)
            self.play_tickets[ticket] = (self.clock() + 120, expected, checked['selected'])
            while len(self.play_tickets) > 32:
                expired, _ = self.play_tickets.popitem(last=False)
                self.play_file_refs.pop(expired, None)
        return dict(ticket=ticket)

    def claim_play(self, ticket):
        _attempt_id(ticket)
        with self.lock:
            if self.closed:
                raise PanError('PAN_SERVICE_CLOSED')
            value = self.play_tickets.pop(ticket, None)
            file_ref = self.play_file_refs.pop(ticket, None)
            if value is None or self.clock() >= value[0]:
                raise PanError('PAN_PLAY_EXPIRED')
            self.accounts.require_current(value[1])
            return dict(request_id=ticket, account=deepcopy(value[1]), selected=deepcopy(value[2]), file_ref=file_ref)

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
                        result = dict(attempt=attempt.id, state='retry', reason='network')
                        phase = getattr(attempt.flow, 'phase', None)
                        if phase in ('confirm', 'exchange', 'identity'):
                            result['phase'] = phase  # Fixed enum only, never ticket/exception text.
                        return result
        if action == 'pan_logout' and fields == {'expected'}:
            return self.logout(body['expected'])
        if action == 'pan_cancel_operation' and fields == {'expected', 'operation_id'}:
            return self.cancel_operation(body['expected'], body['operation_id'])
        if action == 'pan_open_stream' and fields == {'expected', 'selected', 'request_id'}:
            return self.open_stream(body['expected'], body['selected'], body['request_id'])
        if action == 'pan_close_stream' and fields == {'expected', 'request_id'}:
            return self.close_stream(body['expected'], body['request_id'])
        if action == 'pan_prepare_play' and fields == {'expected', 'selected'}:
            return self.prepare_play(body['expected'], body['selected'])
        if action == 'pan_claim_play' and fields == {'ticket'}:
            return self.claim_play(body['ticket'])
        if (action == 'pan_list_files' and {'expected', 'parent', 'page'} <= fields
                and fields <= {'expected', 'parent', 'page', 'cursor', 'refresh', 'continuation', 'operation_id'}):
            return self.list_files(body['expected'], body['parent'], body['page'],
                body.get('cursor'), body.get('refresh', False), body.get('continuation'), body.get('operation_id'))
        raise PanError('PAN_ACTION_INVALID')

    def close(self):
        with self.lock:
            self.closed = True
            self.directory_cache.clear()
            self.directory_pages.clear()
            for operation in self.operations.values():
                operation.cancelled.set()
            self.play_tickets.clear()
            self.play_file_refs.clear()
            for attempt in self.attempts.values():
                attempt.cancelled.set()
                attempt.saved = None
            streams = self.streams
        if streams is not None:
            streams.close()

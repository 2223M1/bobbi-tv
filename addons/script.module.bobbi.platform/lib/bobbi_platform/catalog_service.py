"""One opt-in directory scanner, owned and drained by the existing Host."""
from collections import deque, OrderedDict
from threading import Event, Lock, Thread

from bobbi_core.media_library_index import MediaIndex, TERMINAL, identifier
from .libraries import Registry
from .scan_sources import NativePort

# A 10k tree fits without whole-tree materialization. Current adapters cap
# provider pages at 20, independent of the interactive UI's 10 item window.
MAX_DEPTH = 12
MAX_ITEMS = 12000
MAX_DIRECTORIES = 1024
MAX_PAGES = 1200
MAX_REQUESTS = 2400
MAX_SECONDS = 1800
SCAN_WINDOW = 20


class CatalogService:
    def __init__(self, root, pans, playing=lambda: False):
        self.root, self.pans, self.playing = root, pans, playing
        self.index = MediaIndex(root / 'media-index.sqlite3')
        try:
            self.index.recover()
            self._reconcile_sources()
        except BaseException:
            self.index.close()
            raise
        self.lock, self.stop = Lock(), Event()
        self.worker = self.operation = self.task = None
        self.cancel_event = Event()
        self.max_queue = 0
        self.play_lock, self.play_receipts = Lock(), OrderedDict()
        from .mounted_catalog import MountedCatalog
        self.mounted = MountedCatalog(self)

    def _registry(self):
        return Registry(self.root / 'libraries.sqlite3')

    def _reconcile_sources(self):
        # A crash between the Registry removal and index projection is repaired
        # on next service opening. FileRefs, mappings and history are retained.
        store = self._registry()
        try:
            self.index.retain_sources([row['id'] for row in store.directories()] +
                [source.id for source in store.sources() if source.kind == 'vfs'])
        finally:
            store.close()

    def _source(self, source_id, expected):
        store = self._registry()
        try:
            source = store.directory(source_id)
        finally:
            store.close()
        if (source['provider'], source['account_id']) != (expected['provider'], expected['account_id']):
            raise ValueError('CATALOG_ACCOUNT_MISMATCH')
        return source

    def _guard(self, expected):
        if self.stop.is_set():
            raise ValueError('CATALOG_SERVICE_CLOSED')
        return self.pans.accounts.require_current(expected)

    def scope(self, expected):
        """Validate only the local edit scope, never manufacture a permit."""
        if type(expected) is dict and expected.get('reference_kind') == 'mounted_path':
            self.mounted.live()
            scope = self.mounted.port.scope(identifier(expected.get('source_id')))
            if scope['namespace'] != expected.get('namespace'):
                raise ValueError('CATALOG_AUTHORITY_CHANGED')
            return scope
        return self._guard(expected)

    def run_in_scope(self, expected, operation):
        expected = self.scope(expected)
        if expected.get('reference_kind') == 'mounted_path':
            with self.lock:
                self.scope(expected)
                return operation()
        return self.pans.accounts.run_if_current(expected, operation)

    def _play_source(self, expected, object_id):
        self._guard(expected)
        store = self._registry()
        try:
            permitted = {row['id'] for row in store.directories() if
                         (row['provider'], row['account_id']) ==
                         (expected['provider'], expected['account_id'])}
        finally:
            store.close()
        if not permitted.intersection(self.index.file_sources(object_id)):
            raise ValueError('CATALOG_SOURCE_UNAVAILABLE')

    def prepare_play(self, expected, object_id, request_id, intent):
        """Only an explicit opaque selection can start bounded revalidation."""
        from .pan_accounts import PanError
        from .pan_history import prepare_file_play
        identifier(object_id, 64)
        identifier(request_id)
        if intent != 'play':
            raise ValueError('CATALOG_ACTION_INVALID')
        # One indexed intent in flight, not a second player/transport owner.
        # Repeated confirmation returns the same one-use ticket, including
        # after it was claimed; it must never remint a consumed ticket.
        with self.play_lock:
            expected = self._guard(expected)
            binding = (expected['provider'], expected['account_id'], expected['epoch'], object_id)
            prior = self.play_receipts.get(request_id)
            if prior is not None:
                if prior[0] != binding:
                    raise ValueError('CATALOG_REQUEST_REUSED')
                if prior[1] is not None:
                    self._play_source(expected, object_id)
                    return dict(prior[1])
                raise ValueError('CATALOG_RECHECK_INCOMPLETE')
            self.play_receipts[request_id] = (binding, None)
            while len(self.play_receipts) > 128:
                self.play_receipts.popitem(last=False)
            ref = self.index.trusted_file(expected, object_id)
            self._play_source(expected, object_id)

            def publish(prepare):
                # PanService publishes tickets under service -> account locks.
                # Preserve that order while adding our index/source guard.
                # All directory IO has finished before this local boundary.
                with self.pans.lock, self.lock:
                    self._play_source(expected, object_id)
                    # A simultaneous completed scan must not silently replace
                    # the trusted exact-file evidence while the request waits.
                    from bobbi_core.file_ref import same_file
                    if not same_file(ref, self.index.trusted_file(expected, object_id)):
                        raise PanError('PAN_FILE_CHANGED')
                    return self.pans.accounts.run_if_current(expected, prepare)
            try:
                result = prepare_file_play(self.pans, ref, expected, request_id, publish)
            except PanError as error:
                if str(error) in ('PAN_BUDGET_EXHAUSTED', 'PAN_OPERATION_TIMEOUT', 'PAN_PAGE_EXPIRED'):
                    raise ValueError('CATALOG_RECHECK_INCOMPLETE') from None
                raise
            self.play_receipts[request_id] = (binding, dict(result))
            return result

    def start_scan(self, expected, source_id):
        expected = self._guard(expected)
        with self.lock:
            if self.stop.is_set() or self.worker is not None and self.worker.is_alive():
                raise ValueError('CATALOG_SCAN_BUSY')
            source = self._source(source_id, expected)
            return self._admit(NativePort(self.pans), expected, source_id, source['parent'])

    def start_mounted_scan(self, authority):
        port = self.mounted.port
        port.require(authority)  # Potentially blocking FUSE validation stays outside the owner lock.
        with self.lock:
            self.mounted.live()
            if self.worker is not None and self.worker.is_alive():
                raise ValueError('CATALOG_SCAN_BUSY')
            return self._admit(port, authority, authority['source_id'], '')

    def _admit(self, port, expected, source_id, parent):
        # Called under the sole worker lock; each port supplies its own CAS.
        task = port.publish(expected, lambda: self.index.start(source_id, expected))
        self.task, self.cancel_event, self.max_queue = task, Event(), 1
        try:
            self.worker = Thread(target=self._scan, args=(task, port, parent, expected), name='bobbi-library-scan', daemon=True)
            self.worker.start()
        except Exception:
            self.worker = self.task = None
            self.index.finish(task, 'failed', 'WORKER_START_FAILED')
            raise RuntimeError('CATALOG_WORKER_UNAVAILABLE') from None
        return dict(task_id=task)

    def _scan(self, task, port, root_parent, expected):
        state, reason = 'failed', 'SCAN_UNAVAILABLE'
        try:
            self.index.begin(task)
            with port.scan(expected, task, self.cancel_event, max_pages=MAX_PAGES, max_items=MAX_ITEMS,
                    max_requests=MAX_REQUESTS, seconds=MAX_SECONDS) as operation:
                with self.lock:
                    self.operation = operation
                    if self.stop.is_set() or self.cancel_event.is_set():
                        operation.cancelled.set()
                def commit(write):
                    # The owner lock precedes the native account CAS, as in
                    # admission/removal/play publication. Reversing these
                    # locks lets a scan and a concurrent play wait forever.
                    # Mounted publication checks only local Registry/mountinfo;
                    # full FUSE validation remains outside this lock.
                    with self.lock:
                        if self.stop.is_set() or self.cancel_event.is_set():
                            operation.cancelled.set()
                        port.check(operation, local=True)
                        return port.publish(expected, write)
                pending = deque([(root_parent, 0)])
                visited = {root_parent}
                while pending:
                    port.check(operation, local=True)
                    parent, depth = pending.popleft()
                    page, cursor, seen_cursors, seen_pages = 1, None, set(), set()
                    while True:
                        if self.stop.is_set() or self.cancel_event.is_set():
                            operation.cancelled.set()
                        port.check(operation, local=True)
                        # Yield between requests, more aggressively during
                        # playback; never monopolize a provider's client lock.
                        if self.cancel_event.wait(.05 if self.playing() else .001):
                            operation.cancelled.set()
                        port.check(operation, local=True)
                        result = port.page(operation, expected, parent, page, cursor)
                        port.check(operation)
                        rows = result['items']
                        if type(rows) is not list or len(rows) > SCAN_WINDOW:
                            raise ValueError('SCAN_INVALID_PAGE')
                        signature = result['signature']
                        if signature and signature in seen_pages:
                            raise ValueError('SCAN_PAGE_CYCLE')
                        if signature:
                            seen_pages.add(signature)
                        refs = []
                        for row in rows:
                            if row['directory'] is not None:
                                folder = row['directory']
                                if folder in visited:
                                    continue
                                if depth >= MAX_DEPTH or len(visited) >= MAX_DIRECTORIES:
                                    raise ValueError('SCAN_DIRECTORY_LIMIT')
                                visited.add(folder)
                                pending.append((folder, depth + 1))
                                self.max_queue = max(self.max_queue, len(pending))
                            elif row['reference'] is not None:
                                refs.append(row['reference'])
                        checkpoint = dict(parent=parent, page=page, cursor=cursor,
                            queued=len(pending), depth=depth)
                        port.check(operation, local=True)
                        write_batch = self.index.mounted_batch if port.mounted else self.index.batch
                        commit(lambda: write_batch(task, refs, checkpoint, len(rows)))
                        if result.get('has_more') is not True:
                            break
                        if not rows:
                            raise ValueError('SCAN_INCOMPLETE_PAGE')
                        next_cursor = result.get('next_cursor')
                        if next_cursor is not None:
                            if not next_cursor or next_cursor in seen_cursors:
                                raise ValueError('SCAN_CURSOR_CYCLE')
                            seen_cursors.add(next_cursor)
                            cursor = next_cursor
                        page += 1
                port.check(operation)
                # Account CAS also encloses the absence inference boundary.
                commit(lambda: self.index.finish(task, 'completed'))
                return
        except Exception as error:
            if self.stop.is_set():
                state, reason = 'interrupted', 'SERVICE_STOPPED'
            elif self.cancel_event.is_set():
                state, reason = 'canceled', 'CANCEL_CONFIRMED'
            elif port.revoked(expected):
                state, reason = 'interrupted', 'ACCOUNT_REVOKED'
            else:
                code = str(error)
                reason = code if code in {'SCAN_INVALID_PAGE', 'SCAN_PAGE_CYCLE', 'SCAN_DIRECTORY_LIMIT',
                    'SCAN_CURSOR_CYCLE', 'SCAN_INCOMPLETE_PAGE', 'PAN_BUDGET_EXHAUSTED',
                    'PAN_OPERATION_TIMEOUT', 'PAN_RATE_LIMITED', 'CATALOG_SOURCE_UNAVAILABLE',
                    'CATALOG_AUTHORITY_CHANGED', 'CATALOG_RECHECK_INCOMPLETE', 'CATALOG_SOURCE_UNSUPPORTED'} else 'SCAN_UNAVAILABLE'
            self.index.finish(task, state, reason)
        finally:
            with self.lock:
                self.operation = None

    def dispatch(self, action, body):
        if isinstance(action, str) and action.startswith('catalog_mount_'):
            return self.mounted.dispatch(action, body)
        expected = self._guard(body.get('expected'))
        args = {key: value for key, value in body.items() if key != 'expected'}
        if action == 'catalog_sources' and not args:
            store = self._registry()
            try:
                rows = [row for row in store.directories() if (row['provider'], row['account_id']) ==
                        (expected['provider'], expected['account_id'])]
            finally:
                store.close()
            return self.pans.accounts.run_if_current(expected, lambda: dict(items=[
                dict(id=r['id'], name=r['name']) for r in rows]))
        if action == 'catalog_add' and set(args) == {'name', 'parent'}:
            def add():
                store = self._registry()
                try:
                    row = store.save_directory(args['name'], expected, args['parent'])
                    return dict(source_id=row['id'])
                finally:
                    store.close()
            return self.pans.accounts.run_if_current(expected, add)
        if action == 'catalog_scan' and set(args) == {'source_id'}:
            return self.start_scan(expected, args['source_id'])
        if action == 'catalog_remove' and set(args) == {'source_id'}:
            self._source(args['source_id'], expected)
            with self.lock:
                if self.worker is not None and self.worker.is_alive():
                    raise ValueError('CATALOG_SCAN_BUSY')
                def remove():
                    store = self._registry()
                    try:
                        store.remove_directory(args['source_id'])
                    finally:
                        store.close()
                    self._reconcile_sources()
                    return dict(removed=True)
                return self.pans.accounts.run_if_current(expected, remove)
        if action == 'catalog_cancel' and set(args) == {'task_id'}:
            result = self.pans.accounts.run_if_current(expected, lambda: self.index.cancel(args['task_id'], expected))
            with self.lock:
                if self.task == args['task_id'] and result['state'] not in TERMINAL:
                    self.cancel_event.set()
                    if self.operation is not None:
                        self.operation.cancelled.set()
            return result
        if action == 'catalog_jobs' and set(args) <= {'task', 'offset', 'limit'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.jobs(expected, **args))
        if action == 'catalog_items' and set(args) <= {'source', 'state', 'offset', 'limit'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.items(expected, **args))
        if action == 'catalog_item' and set(args) == {'file_id'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.item(expected, **args))
        if action == 'catalog_query' and set(args) <= {'query', 'cursor', 'limit'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.query(expected, **args))
        if action == 'catalog_receipt' and set(args) == {'request_id'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.receipt(expected, **args))
        if action == 'catalog_group' and 'file_id' in args and set(args) <= {'file_id', 'source_id', 'offset', 'limit', 'projection_revision'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.group(expected, **args))
        if action == 'catalog_prepare_play' and set(args) == {'object_id', 'request_id', 'intent'}:
            return self.prepare_play(expected, **args)
        if action == 'catalog_preview' and set(args) == {'commands'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.preview(expected, args['commands']))
        if action == 'catalog_apply' and set(args) == {'request_id', 'commands'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.apply(expected, **args))
        raise ValueError('CATALOG_ACTION_INVALID')

    def close(self):
        with self.lock:
            self.stop.set()
            self.mounted.close()
            self.cancel_event.set()
            worker, operation = self.worker, self.operation
            if operation is not None:
                operation.cancelled.set()
        if worker is not None:
            worker.join(5)
            if worker.is_alive():
                raise RuntimeError('CATALOG_DRAIN_PENDING')
        if not getattr(self, '_closed', False):
            self.index.close()
            self._closed = True

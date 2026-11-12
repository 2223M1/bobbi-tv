"""CD2 typed lane inside the existing CatalogService/index/worker owner."""
from collections import deque, OrderedDict
from threading import Event, Thread
import time

from bobbi_core import mounted_ref
from bobbi_core.media_library_index import identifier
from .scan_sources import MountedPort


class MountedCatalog:
    def __init__(self, owner, port=None):
        self.owner = owner
        self.port = port or MountedPort(owner.root)
        self.attempts, self.tickets, self.claims = OrderedDict(), OrderedDict(), OrderedDict()
        self.cancelled = OrderedDict()

    def live(self):
        if self.owner.stop.is_set():
            raise ValueError('CATALOG_SERVICE_CLOSED')

    def authority(self, source_id):
        self.live()
        return self.port.describe(identifier(source_id))[1]

    @staticmethod
    def task_namespace(source):
        # Local Registry ownership permits observing/canceling a saved job even
        # when its mount is offline. It is never a file or playback authority.
        if source.kind != 'vfs' or source.username or source.password:
            raise ValueError('CATALOG_SOURCE_UNSUPPORTED')
        return mounted_ref.digest('cd2', source.location)

    def dispatch(self, action, body):
        self.live()
        if action == 'catalog_mount_sources' and not body:
            store = self.owner._registry()
            try:
                sources = store.sources()
            finally:
                store.close()
            # /proc mount evidence is local and bounded. Do not stat a FUSE
            # path merely to expose its saved jobs: a hung mount must not hide
            # the cancellation entry. This flag is only a presentation hint;
            # browse, scan admission and playback still call full describe.
            try:
                mounts = self.port.mounts()
            except (ValueError, OSError):
                mounts = []
            items = []
            for source in sources:
                try:
                    namespace = self.task_namespace(source)
                except (ValueError, OSError):
                    continue
                root = source.location.rstrip('/\\')
                available = any(root == row['path'] or root.startswith(row['path'].rstrip('/') + '/')
                                for row in mounts)
                has_jobs = bool(self.owner.index.mounted_jobs(source.id, namespace, limit=1)['items'])
                if not available and not has_jobs:
                    continue
                items.append(dict(id=source.id, name=source.name, reference_kind='mounted_path',
                                  device_verified=False, available=available, has_jobs=has_jobs))
            return dict(items=items)
        if action == 'catalog_mount_claim' and set(body) == {'ticket'}:
            return self.claim(body['ticket'])
        if action == 'catalog_mount_cancel_play' and set(body) == {'source_id', 'request_id'}:
            identifier(body['source_id'])
            request = identifier(body['request_id'])
            with self.owner.lock:
                prior = self.attempts.get(request)
                if prior and prior[0]['source_id'] != body['source_id']:
                    raise ValueError('CATALOG_REFERENCE_INVALID')
                if prior:
                    prior[2].set()
                self.cancelled[request] = body['source_id']
                while len(self.cancelled) > 128:
                    self.cancelled.popitem(last=False)
                self.tickets.pop(request, None)
                self.claims.pop(request, None)
            return dict(cancelled=True)
        if 'source_id' not in body:
            raise ValueError('CATALOG_ACTION_INVALID')
        args = {key: value for key, value in body.items() if key != 'source_id'}
        if (action == 'catalog_mount_jobs' and set(args) <= {'task', 'offset', 'limit'} or
                action == 'catalog_mount_cancel' and set(args) == {'task_id'}):
            # These operations use the registered source and persisted task
            # binding. They must remain reachable while current mount checks
            # fail, without synthesizing a generation acceptable to playback.
            with self.owner.lock:
                source = self.port.source(identifier(body['source_id']))
                namespace = self.task_namespace(source)
                if action == 'catalog_mount_jobs':
                    return self.owner.index.mounted_jobs(source.id, namespace, **args)
                result = self.owner.index.cancel_mounted(args['task_id'], source.id, namespace)
                if self.owner.task == args['task_id'] and result['state'] in ('queued', 'running'):
                    self.owner.cancel_event.set()
                    if self.owner.operation is not None:
                        self.owner.operation.cancelled.set()
                return result
        authority = self.authority(body['source_id'])
        if action == 'catalog_mount_query' and set(args) <= {'query', 'cursor', 'limit'}:
            result = self.owner.index.query(authority, **args)
            self.port.require(authority)
            self.live()
            return result
        if action == 'catalog_mount_scan' and not args:
            return self.start(authority)
        if action == 'catalog_mount_prepare' and set(args) == {'object_id', 'request_id', 'intent'}:
            return self.prepare(authority, **args)
        if action == 'catalog_mount_verify' and set(args) == {'object_id', 'request_id'}:
            with self.owner.lock:
                record = self.claims.get(identifier(args['request_id']))
            self.verify_record(record, authority, args['object_id'])
            return dict(valid=True)
        raise ValueError('CATALOG_ACTION_INVALID')

    def start(self, authority):
        self.port.require(authority)
        with self.owner.lock:
            self.live()
            if self.owner.worker is not None and self.owner.worker.is_alive():
                raise ValueError('CATALOG_SCAN_BUSY')
            task = self.owner.index.start(authority['source_id'], authority)
            self.owner.task, self.owner.cancel_event = task, Event()
            self.owner.worker = Thread(target=self.scan, args=(task, authority), name='bobbi-library-scan', daemon=True)
            try:
                self.owner.worker.start()
            except Exception:
                self.owner.worker = None
                self.owner.index.finish(task, 'failed', 'WORKER_START_FAILED')
                raise RuntimeError('CATALOG_WORKER_UNAVAILABLE') from None
            return dict(task_id=task)

    def scan(self, task, authority):
        from .catalog_service import MAX_DEPTH, MAX_DIRECTORIES
        try:
            self.owner.index.begin(task)
            with self.port.open_scan(authority, self.owner.cancel_event) as session:
                with self.owner.lock:
                    self.owner.operation = session
                pending = deque([('', 0)])
                directories = 1
                while pending:
                    parent, depth = pending.popleft()
                    while True:
                        self.live()
                        page = session.list_page(parent)
                        refs = []
                        for row in page['items']:
                            if row['directory']:
                                directories += 1
                                if depth >= MAX_DEPTH or directories > MAX_DIRECTORIES:
                                    raise ValueError('SCAN_DIRECTORY_LIMIT')
                                pending.append((row['relative'], depth + 1))
                            elif row['reference'] is not None:
                                refs.append(row['reference'])
                        # Complete source checks may enter a blocking FUSE
                        # stat. Keep them outside the shared task-state lock.
                        session.check()
                        with self.owner.lock:
                            self.live()
                            session.check(validate_authority=False)
                            self.owner.index.mounted_batch(task, refs, dict(parent=parent, page=session.pages), len(page['items']))
                        if not page['has_more']:
                            break
                session.check()
                with self.owner.lock:
                    self.live()
                    session.check(validate_authority=False)
                    self.owner.index.finish(task, 'completed')
        except Exception as error:
            if self.owner.stop.is_set():
                state, reason = 'interrupted', 'SERVICE_STOPPED'
            elif self.owner.cancel_event.is_set():
                state, reason = 'canceled', 'CANCEL_CONFIRMED'
            else:
                state = 'failed'
                reason = str(error) if str(error) in {'CATALOG_SOURCE_UNAVAILABLE', 'CATALOG_AUTHORITY_CHANGED',
                    'CATALOG_RECHECK_INCOMPLETE', 'CATALOG_SOURCE_UNSUPPORTED', 'SCAN_DIRECTORY_LIMIT'} else 'SCAN_UNAVAILABLE'
            self.owner.index.finish(task, state, reason)
        finally:
            with self.owner.lock:
                self.owner.operation = None

    def prepare(self, authority, object_id, request_id, intent):
        identifier(object_id, 64)
        identifier(request_id)
        if intent != 'play':
            raise ValueError('CATALOG_ACTION_INVALID')
        with self.owner.play_lock:
            self.live()
            self.port.require(authority)
            with self.owner.lock:
                if request_id in self.cancelled:
                    raise ValueError('CATALOG_SELECTION_CANCELLED')
                prior = self.attempts.get(request_id)
                if prior:
                    if (prior[0], prior[1]) != (authority, object_id):
                        raise ValueError('CATALOG_REQUEST_REUSED')
                    if prior[2].is_set():
                        raise ValueError('CATALOG_SELECTION_CANCELLED')
                    if not prior[3]:
                        raise ValueError('CATALOG_RECHECK_INCOMPLETE')
                    return dict(ticket=request_id)  # Never remint after claim.
                cancelled = Event()
                self.attempts[request_id] = (authority, object_id, cancelled, False)
                while len(self.attempts) > 128:
                    self.attempts.popitem(last=False)
            reference = self.owner.index.trusted_mounted_file(authority, object_id)
            # Match a bounded, freshly enumerated original directory, then
            # check stat again. No by-ID/stat-only shortcut to a selection.
            with self.port.open_scan(authority, cancelled, seconds=24, max_pages=8, max_items=160) as session:
                selected = None
                while selected is None:
                    self.live()
                    page = session.list_page(reference['parent'])
                    for row in page['items']:
                        current = row.get('reference')
                        if current and current['id'] == object_id:
                            if not mounted_ref.same_observation(reference, current):
                                raise ValueError('CATALOG_FILE_CHANGED')
                            selected = current
                            break
                    if selected is None and not page['has_more']:
                        raise ValueError('CATALOG_FILE_CHANGED')
                self.port.stat_by_reference(authority, selected, session.check)
                session.check()
                with self.owner.lock:
                    self.live()
                    session.check(validate_authority=False)
                    self.tickets[request_id] = (time.monotonic() + 120, authority, selected, cancelled)
                    self.attempts[request_id] = (authority, object_id, cancelled, True)
                    while len(self.tickets) > 32:
                        self.tickets.popitem(last=False)
            return dict(ticket=request_id)

    def verify_record(self, record, authority=None, object_id=None):
        self.live()
        if record is None or time.monotonic() >= record[0] or record[3].is_set():
            raise ValueError('CATALOG_PLAY_EXPIRED')
        if authority is not None and record[1] != authority or object_id is not None and record[2]['id'] != object_id:
            raise ValueError('CATALOG_REFERENCE_INVALID')
        self.port.stat_by_reference(record[1], record[2], self.live)
        if record[3].is_set():
            raise ValueError('CATALOG_SELECTION_CANCELLED')
        return record

    def claim(self, ticket):
        identifier(ticket)
        with self.owner.lock:
            record = self.tickets.pop(ticket, None)
        self.verify_record(record)
        with self.owner.lock:
            self.live()
            self.claims[ticket] = record
            while len(self.claims) > 32:
                self.claims.popitem(last=False)
        reference = record[2]
        return dict(source_id=reference['source_id'], object_id=reference['id'], relative=reference['relative'],
                    title=reference['name'], identity=mounted_ref.digest(reference), resume_supported=False)

    def close(self):
        for authority, object_id, cancelled, completed in self.attempts.values():
            cancelled.set()
        self.tickets.clear()
        self.claims.clear()

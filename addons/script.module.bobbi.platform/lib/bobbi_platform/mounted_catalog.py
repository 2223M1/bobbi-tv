"""CD2 typed lane inside the existing CatalogService/index/worker owner."""
from collections import OrderedDict
from threading import Event
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
        return MountedPort.source_scope(source)['namespace']

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
                has_items = self.owner.index.has_mounted_items(source.id, namespace)
                if not available and not has_jobs and not has_items:
                    continue
                items.append(dict(id=source.id, name=source.name, reference_kind='mounted_path',
                                  device_verified=False, available=available, has_jobs=has_jobs, has_items=has_items))
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
        namespace = args.pop('namespace', None)
        scope = self.port.scope(identifier(body['source_id']))
        if namespace is not None and namespace != scope['namespace']:
            raise ValueError('CATALOG_AUTHORITY_CHANGED')
        if action == 'catalog_mount_scope' and not args:
            return scope
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
        if action == 'catalog_mount_query' and set(args) <= {'query', 'cursor', 'limit'}:
            return self.owner.run_in_scope(scope, lambda: self.owner.index.query(self.port.snapshot(scope), **args))
        index_actions = {
            'catalog_mount_item': ({'file_id'}, self.owner.index.item),
            'catalog_mount_items': ({'source', 'state', 'offset', 'limit'}, self.owner.index.items),
            'catalog_mount_group': ({'file_id', 'source_id', 'offset', 'limit', 'projection_revision'}, self.owner.index.group),
            'catalog_mount_preview': ({'commands'}, self.owner.index.preview),
            'catalog_mount_apply': ({'request_id', 'commands'}, self.owner.index.apply),
            'catalog_mount_receipt': ({'request_id'}, self.owner.index.receipt),
        }
        if action in index_actions:
            fields, method = index_actions[action]
            required = {'catalog_mount_item': {'file_id'}, 'catalog_mount_group': {'file_id'},
                        'catalog_mount_preview': {'commands'}, 'catalog_mount_apply': {'request_id', 'commands'},
                        'catalog_mount_receipt': {'request_id'}}.get(action, set())
            if set(args) <= fields and required <= set(args):
                return self.owner.run_in_scope(scope, lambda: method(scope, **args))
        authority = self.authority(body['source_id'])
        if action == 'catalog_mount_scan' and not args:
            return self.owner.start_mounted_scan(authority)
        if action == 'catalog_mount_prepare' and set(args) == {'object_id', 'request_id', 'intent'}:
            return self.prepare(authority, **args)
        if action == 'catalog_mount_verify' and set(args) == {'object_id', 'request_id'}:
            with self.owner.lock:
                record = self.claims.get(identifier(args['request_id']))
            self.verify_record(record, authority, args['object_id'])
            return dict(valid=True)
        raise ValueError('CATALOG_ACTION_INVALID')

    def prepare(self, authority, object_id, request_id, intent):
        identifier(object_id, 64)
        identifier(request_id)
        if intent not in ('play', 'play_from_start'):
            raise ValueError('CATALOG_ACTION_INVALID')
        with self.owner.play_lock:
            self.live()
            self.port.require(authority)
            with self.owner.lock:
                if request_id in self.cancelled:
                    raise ValueError('CATALOG_SELECTION_CANCELLED')
                prior = self.attempts.get(request_id)
                if prior:
                    if (prior[0], prior[1], prior[4]) != (authority, object_id, intent):
                        raise ValueError('CATALOG_REQUEST_REUSED')
                    if prior[2].is_set():
                        raise ValueError('CATALOG_SELECTION_CANCELLED')
                    if not prior[3]:
                        raise ValueError('CATALOG_RECHECK_INCOMPLETE')
                    return dict(ticket=request_id)  # Never remint after claim.
                cancelled = Event()
                self.attempts[request_id] = (authority, object_id, cancelled, False, intent)
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
                            if intent == 'play' and not mounted_ref.same_observation(reference, current):
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
                    self.port.publish(authority, lambda: None)
                    if intent == 'play_from_start':
                        self.owner.index.observe_mounted(authority, selected)
                    self.tickets[request_id] = (time.monotonic() + 120, authority, selected, cancelled)
                    self.attempts[request_id] = (authority, object_id, cancelled, True, intent)
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
        for authority, object_id, cancelled, completed, intent in self.attempts.values():
            cancelled.set()
        self.tickets.clear()
        self.claims.clear()

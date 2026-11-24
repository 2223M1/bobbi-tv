"""Registered path lanes inside the existing CatalogService/index/worker owner."""
from collections import OrderedDict
from threading import Event
import time

from bobbi_core import typed_ref
from bobbi_core.media_library_index import identifier
from .scan_sources import MountedPort, LocalPort
from .network_sources import NetworkPort


class MountedCatalog:
    def __init__(self, owner, port=None):
        self.owner = owner
        self.port = port or MountedPort(owner.root)
        self.local_port = LocalPort(owner.root)
        self.network_port = NetworkPort(owner.root)
        self.attempts, self.tickets, self.claims = OrderedDict(), OrderedDict(), OrderedDict()
        self.cancelled = OrderedDict()

    def live(self):
        self.owner._live_profile()
        if self.owner.stop.is_set():
            raise ValueError('CATALOG_SERVICE_CLOSED')

    def port_for(self, expected):
        kind = expected.get('reference_kind')
        if kind not in typed_ref.KINDS:
            raise ValueError('CATALOG_SCOPE_INVALID')
        return {'local_path': self.local_port, 'network_path': self.network_port, 'mounted_path': self.port}[kind]

    def authority(self, source_id, kind='mounted_path'):
        self.live()
        return self.port_for(dict(reference_kind=kind)).describe(identifier(source_id))[1]

    @staticmethod
    def task_namespace(source, kind='mounted_path'):
        # Local Registry ownership permits observing/canceling a saved job even
        # when its mount is offline. It is never a file or playback authority.
        port = {'local_path': LocalPort, 'network_path': NetworkPort, 'mounted_path': MountedPort}[kind]
        return port.source_scope(source)['namespace']

    def dispatch(self, action, body):
        self.live()
        kind = next((kind for kind in typed_ref.KINDS if action.startswith(typed_ref.action_prefix(kind))), None)
        port = self.port_for(dict(reference_kind=kind))
        action = 'catalog_mount_' + action[len(typed_ref.action_prefix(kind)):]
        if action == 'catalog_mount_sources' and not body:
            from .catalog_service import source_list
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
                mounts = port.mounts() if kind != 'network_path' else []
            except (ValueError, OSError):
                mounts = []
            items = []
            for source in sources:
                try:
                    scope = port.scope(source.id) if kind == 'network_path' else port.source_snapshot(source, mounts)
                    if kind == 'local_path':
                        # An offline CD2 registration keeps its original lane;
                        # do not reclassify its now-empty mountpoint as local.
                        prior_scope = MountedPort.source_scope(source)
                        prior = self.owner.source_observation(prior_scope, source.id)
                        if prior['indexed_count'] or prior['latest_state'] != 'none':
                            continue
                except (ValueError, OSError):
                    continue
                available = bool(scope['generation']) if kind == 'mounted_path' else None
                observation = self.owner.source_observation(scope, source.id)
                has_jobs = observation['latest_state'] != 'none'
                has_items = bool(observation['indexed_count'])
                if kind == 'mounted_path' and not available and not has_jobs and not has_items:
                    continue
                items.append(dict(id=source.id, name=source.name, reference_kind=kind,
                    experimental=kind == 'network_path',
                    device_verified=False, available=available, has_jobs=has_jobs, has_items=has_items,
                    observation=observation))
            return source_list(items)
        if action == 'catalog_mount_claim' and set(body) == {'ticket'}:
            return self.claim(body['ticket'], kind)
        if action == 'catalog_mount_cancel_play' and set(body) == {'source_id', 'request_id'}:
            identifier(body['source_id'])
            request = identifier(body['request_id'])
            with self.owner.lock:
                prior = self.attempts.get(request)
                if prior and (prior[0]['source_id'] != body['source_id'] or prior[0]['reference_kind'] != kind):
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
        generation = args.pop('generation', None)
        scope = port.scope(identifier(body['source_id']))
        if namespace is not None and namespace != scope['namespace']:
            raise ValueError('CATALOG_AUTHORITY_CHANGED')
        if generation is not None and generation != scope['generation']:
            raise ValueError('CATALOG_AUTHORITY_CHANGED')
        if action == 'catalog_mount_scope' and not args:
            return scope
        if (action == 'catalog_mount_jobs' and set(args) <= {'task', 'offset', 'limit'} or
                action == 'catalog_mount_cancel' and set(args) == {'task_id'}):
            # These operations use the registered source and persisted task
            # binding. They must remain reachable while current mount checks
            # fail, without synthesizing a generation acceptable to playback.
            with self.owner.lock:
                source = port.source(identifier(body['source_id']))
                namespace = self.task_namespace(source, kind)
                if action == 'catalog_mount_jobs':
                    return self.owner.index.mounted_jobs(source.id, namespace, **args)
                result = self.owner.index.cancel_mounted(args['task_id'], source.id, namespace)
                if self.owner.task == args['task_id'] and result['state'] in ('queued', 'running'):
                    self.owner.cancel_event.set()
                    if self.owner.operation is not None:
                        self.owner.operation.cancelled.set()
                return result
        if action == 'catalog_mount_query' and set(args) <= {'query', 'cursor', 'limit'}:
            return self.owner.run_in_scope(scope, lambda: self.owner.query(port.snapshot(scope), **args))
        index_actions = {
            'catalog_mount_holdings': ({'identities'}, self.owner.index.holdings),
            'catalog_mount_parent': ({'parent_id'}, self.owner.index.parent_descriptor),
            'catalog_mount_describe': ({'file_ids'}, self.owner.index.describe_files),
            'catalog_mount_item': ({'file_id'}, self.owner.index.item),
            'catalog_mount_items': ({'source', 'state', 'offset', 'limit'}, self.owner.index.items),
            'catalog_mount_group': ({'file_id', 'source_id', 'offset', 'limit', 'projection_revision'}, self.owner.index.group),
            'catalog_mount_preview': ({'commands'}, self.owner.index.preview),
            'catalog_mount_apply': ({'request_id', 'commands'}, self.owner.index.apply),
            'catalog_mount_receipt': ({'request_id'}, self.owner.index.receipt),
        }
        if action in index_actions:
            fields, method = index_actions[action]
            required = {'catalog_mount_holdings': {'identities'}, 'catalog_mount_parent': {'parent_id'},
                        'catalog_mount_describe': {'file_ids'},
                        'catalog_mount_item': {'file_id'}, 'catalog_mount_group': {'file_id'},
                        'catalog_mount_preview': {'commands'}, 'catalog_mount_apply': {'request_id', 'commands'},
                        'catalog_mount_receipt': {'request_id'}}.get(action, set())
            if set(args) <= fields and required <= set(args):
                return self.owner.run_in_scope(scope, lambda: method(scope, **args))
        authority = self.authority(body['source_id'], kind)
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
        port = self.port_for(authority)
        identifier(object_id, 64)
        identifier(request_id)
        if intent not in ('play', 'play_from_start'):
            raise ValueError('CATALOG_ACTION_INVALID')
        with self.owner.play_lock:
            self.live()
            port.require(authority)
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
            with port.open_scan(authority, cancelled, seconds=24, max_pages=8, max_items=160) as session:
                selected = port.select_reference(authority, reference, session, self.live,
                                                 allow_changed=intent == 'play_from_start')
                session.check()
                with self.owner.lock:
                    self.live()
                    session.check(validate_authority=False)
                    def publish_selection():
                        if intent == 'play_from_start':
                            self.owner.index.observe_mounted(authority, selected)
                        self.tickets[request_id] = (time.monotonic() + 120, authority, selected, cancelled)
                        self.attempts[request_id] = (authority, object_id, cancelled, True, intent)
                        while len(self.tickets) > 32:
                            self.tickets.popitem(last=False)
                    port.publish(authority, publish_selection)
            return dict(ticket=request_id)

    def verify_record(self, record, authority=None, object_id=None):
        self.live()
        if record is None or time.monotonic() >= record[0] or record[3].is_set():
            raise ValueError('CATALOG_PLAY_EXPIRED')
        if authority is not None and record[1] != authority or object_id is not None and record[2]['id'] != object_id:
            raise ValueError('CATALOG_REFERENCE_INVALID')
        self.port_for(record[1]).stat_by_reference(record[1], record[2], self.live)
        if record[3].is_set():
            raise ValueError('CATALOG_SELECTION_CANCELLED')
        return record

    def claim(self, ticket, kind='mounted_path'):
        identifier(ticket)
        with self.owner.lock:
            record = self.tickets.get(ticket)
            if record is not None and record[1]['reference_kind'] != kind:
                raise ValueError('CATALOG_REFERENCE_INVALID')
            record = self.tickets.pop(ticket, None)
        self.verify_record(record)
        with self.owner.lock:
            self.live()
            def publish_claim():
                self.claims[ticket] = record
                while len(self.claims) > 32:
                    self.claims.popitem(last=False)
            self.port_for(record[1]).publish(record[1], publish_claim)
        reference = record[2]
        return dict(source_id=reference['source_id'], object_id=reference['id'], relative=reference['relative'],
                    title=reference['name'], identity=typed_ref.digest(reference), resume_supported=False)

    def close(self):
        for authority, object_id, cancelled, completed, intent in self.attempts.values():
            cancelled.set()
        self.tickets.clear()
        self.claims.clear()

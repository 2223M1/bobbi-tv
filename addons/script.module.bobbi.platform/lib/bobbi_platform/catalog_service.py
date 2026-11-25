"""One opt-in directory scanner, owned and drained by the existing Host."""
from collections import deque, OrderedDict
from threading import Event, Lock, Thread

from bobbi_core.media_library_index import (
    FRONTIER_PROOF_VERSION,
    MediaIndex,
    TERMINAL,
    REPLY_BYTES,
    encode,
    identifier,
)
from bobbi_core.typed_ref import KINDS as PATH_KINDS
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


def source_list(items):
    """Keep all bounded Registry identities; shorten only display names."""
    result = dict(items=items)
    if len(encode(result).encode('utf-8')) <= REPLY_BYTES:
        return result
    result = dict(items=[dict(row, name='') for row in items], truncated=True)
    budget = (REPLY_BYTES - len(encode(result).encode('utf-8'))) // len(items)
    if budget < 3:
        raise ValueError('CATALOG_REPLY_LIMIT')
    for row, original in zip(result['items'], items):
        name = original['name']
        if len(encode(name).encode('utf-8')) - 2 > budget:
            while len(encode(name + '…').encode('utf-8')) - 2 > budget:
                name = name[:-1]
            name += '…'
        row['name'] = name
    return result


class CatalogService:
    def __init__(self, root, pans, playing=lambda: False, file_facts=None, profile_current=lambda: True):
        self.root, self.pans, self.playing = root, pans, playing
        self.profile_current, self.profile_revoked = profile_current, Event()
        self.index = MediaIndex(root / 'media-index.sqlite3', file_facts=file_facts)
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

    def query(self, expected, **args):
        # Names are presentation only. Keep the allowlisted Registry partition
        # local; never attach credentials/locations or read the remote tree.
        store = self._registry()
        try:
            if expected.get('reference_kind') in PATH_KINDS:
                source = store.get(expected['source_id'])
                source_names = {source.id: source.name}
            else:
                source_names = {row['id']: row['name'] for row in store.directories()
                    if (row['provider'], row['account_id']) == (expected['provider'], expected['account_id'])}
        finally:
            store.close()
        return self.index.query(expected, source_names=source_names, **args)

    def source_observation(self, expected, source_id):
        observation = self.index.source_observation(expected, source_id)
        latest = observation.pop('latest_job')
        # Full task identities/reasons/cancellation remain on the existing job
        # routes. Source cards need only this small, consistent summary.
        observation.pop('present_count')
        observation.pop('absent_count')
        observation['latest_state'] = latest['state'] if latest else 'none'
        observation['counts'] = latest['counts'] if latest else dict(pages=0, scanned=0, discovered=0)
        if latest and latest['cancel_requested'] and latest['state'] in ('queued', 'running'):
            observation['latest_state'] = 'cancel_requested'
        return observation

    def _guard(self, expected):
        self._live_profile()
        if self.stop.is_set():
            raise ValueError('CATALOG_SERVICE_CLOSED')
        return self.pans.accounts.require_current(expected)

    def _live_profile(self):
        # Lock-free latch check is safe inside existing publication locks.
        if self.profile_revoked.is_set():
            raise ValueError('CATALOG_PROFILE_CHANGED')

    def _profile(self):
        """Call the composition fence only outside catalog/account locks.

        A revoked instance never follows another root or revives on A/B/A.
        Accepted work may record its terminal state in the captured old DB.
        """
        self._live_profile()
        try:
            current = self.profile_current() is True
        except (OSError, ValueError, RuntimeError):
            current = False
        if not current:
            self.profile_revoked.set()
            self.cancel_event.set()
            raise ValueError('CATALOG_PROFILE_CHANGED')

    def scope(self, expected):
        """Validate only the local edit scope, never manufacture a permit."""
        if type(expected) is dict and expected.get('reference_kind') in PATH_KINDS:
            self.mounted.live()
            scope = self.mounted.port_for(expected).scope(identifier(expected.get('source_id')))
            if (scope['namespace'] != expected.get('namespace') or
                    expected.get('reference_kind') == 'network_path' and scope['generation'] != expected.get('generation')):
                raise ValueError('CATALOG_AUTHORITY_CHANGED')
            return scope
        return self._guard(expected)

    def run_in_scope(self, expected, operation):
        expected = self.scope(expected)
        if expected.get('reference_kind') in PATH_KINDS:
            with self.lock:
                self.scope(expected)
                if expected['reference_kind'] == 'network_path':
                    return self.mounted.port_for(expected).publish(expected, operation)
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
            from .pan_accounts import scope_key
            binding = scope_key(expected) + (object_id,)
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
        self._profile()
        expected = self._guard(expected)
        with self.lock:
            if self.stop.is_set() or self.worker is not None and self.worker.is_alive():
                raise ValueError('CATALOG_SCAN_BUSY')
            source = self._source(source_id, expected)
            return self._admit(NativePort(self.pans), expected, source_id, source['parent'])

    def start_mounted_scan(self, authority):
        self._profile()
        port = self.mounted.port_for(authority)
        port.require(authority)  # Potentially blocking FUSE validation stays outside the owner lock.
        self._profile()
        with self.lock:
            self.mounted.live()
            if self.worker is not None and self.worker.is_alive():
                raise ValueError('CATALOG_SCAN_BUSY')
            return self._admit(port, authority, authority['source_id'], '')

    def _admit(self, port, expected, source_id, parent):
        # Called under the sole worker lock; each port supplies its own CAS.
        self._live_profile()
        task = port.publish(
            expected,
            lambda: (
                self.index.start(source_id, expected)
                if port.mounted
                else self.index.start_resumable(source_id, expected, parent, resumable=True)
            ),
        )
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
            self._profile()
            self.index.begin(task)
            with port.scan(expected, task, self.cancel_event, max_pages=MAX_PAGES, max_items=MAX_ITEMS,
                    max_requests=MAX_REQUESTS, seconds=MAX_SECONDS) as operation:
                def safe(local=False):
                    self._profile()
                    port.check(operation, local=local)
                    self._profile()
                safe(local=True)
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
                    safe(local=True)
                    with self.lock:
                        self._live_profile()
                        if self.stop.is_set() or self.cancel_event.is_set():
                            operation.cancelled.set()
                        port.check(operation, local=True)
                        result = port.publish(expected, write)
                    self._profile()
                    return result
                excluded_versions = False
                if port.mounted:
                    pending = deque([(root_parent, 0)])
                    visited = {root_parent}
                    while pending:
                        safe(local=True)
                        parent, depth = pending.popleft()
                        page, cursor, seen_cursors, seen_pages, seen_entries = 1, None, set(), set(), set()
                        while True:
                            if self.stop.is_set() or self.cancel_event.is_set():
                                operation.cancelled.set()
                            safe(local=True)
                            if self.cancel_event.wait(.05 if self.playing() else .001):
                                operation.cancelled.set()
                            safe(local=True)
                            result = port.page(operation, expected, parent, page, cursor)
                            excluded_versions |= result.get('excluded_versions') is True
                            safe()
                            rows = result['items']
                            if type(rows) is not list or len(rows) > SCAN_WINDOW:
                                raise ValueError('SCAN_INVALID_PAGE')
                            signature = result['signature']
                            if signature is not None:
                                if signature and signature in seen_pages:
                                    raise ValueError('SCAN_PAGE_CYCLE')
                                if seen_entries.intersection(signature):
                                    raise ValueError('SCAN_PAGE_CYCLE')
                                if signature:
                                    seen_pages.add(signature)
                                    seen_entries.update(signature)
                            refs, descriptions = [], {}
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
                                    if 'description' in row:
                                        descriptions[row['reference']['id']] = row['description']
                            checkpoint = dict(parent=parent, page=page, cursor=cursor,
                                queued=len(pending), depth=depth)
                            safe(local=True)
                            commit(lambda: self.index.mounted_batch(task, refs, checkpoint, len(rows)))
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
                else:
                    while True:
                        safe(local=True)
                        peek = self.index.frontier_peek(task)
                        if peek is None or peek['empty']:
                            break
                        node = peek['node']
                        is_leaf = bool(node['leaf'])
                        if is_leaf:
                            leaf_nodes = peek.get('leaf_nodes') or [node]
                            refs, descriptions, pop_seqs, continuations, finished_keys = [], {}, [], [], []
                            scanned_total = 0
                            last_parent, last_page, last_depth = node['node_key'], node['next_page'], node['depth']
                            deferred_err = None

                            def flush_leaves():
                                if not pop_seqs:
                                    return
                                est_q = max(0, peek['queued'] - len(pop_seqs) + len(continuations))
                                cp = dict(parent=last_parent[:256], page=last_page, cursor=None, queued=est_q, depth=last_depth)
                                fstep = dict(
                                    pop_seqs=list(pop_seqs),
                                    pages_delta=len(pop_seqs),
                                    dir_key=last_parent,
                                    is_leaf=True,
                                    declared_total=None,
                                    entry_sigs=[],
                                    new_leaves=[],
                                    new_dirs=[],
                                    dir_count=peek['state']['dir_count'],
                                    partial_latch=False,
                                    continuations=list(continuations),
                                    finished_leaf_keys=list(finished_keys),
                                )
                                commit(
                                    lambda: self.index.frontier_batch(
                                        task,
                                        list(refs),
                                        cp,
                                        scanned_total,
                                        descriptions=dict(descriptions) if descriptions else None,
                                        frontier_step=fstep,
                                    )
                                )
                                refs.clear()
                                descriptions.clear()
                                pop_seqs.clear()
                                continuations.clear()
                                finished_keys.clear()

                            for lnode in leaf_nodes:
                                try:
                                    if self.stop.is_set() or self.cancel_event.is_set():
                                        operation.cancelled.set()
                                    safe(local=True)
                                    if self.playing() and self.cancel_event.wait(.05):
                                        operation.cancelled.set()
                                    safe(local=True)
                                    lparent = lnode['node_key']
                                    lpage = lnode['next_page']
                                    lcursor = lnode['cursor']
                                    lres = port.page(operation, expected, lparent, lpage, lcursor)
                                    excluded_versions |= lres.get('excluded_versions') is True
                                    safe()
                                    lrows = lres['items']
                                    if type(lrows) is not list or len(lrows) > SCAN_WINDOW:
                                        raise ValueError('SCAN_INVALID_PAGE')
                                    lrefs = [r['reference'] for r in lrows if r.get('reference') is not None]
                                    if pop_seqs and (len(refs) + len(lrefs) > 20 or scanned_total + len(lrows) > 20):
                                        safe(local=True)
                                        flush_leaves()
                                        scanned_total = 0
                                    for r in lrows:
                                        if r.get('reference') is not None:
                                            refs.append(r['reference'])
                                            if 'description' in r:
                                                descriptions[r['reference']['id']] = r['description']
                                    pop_seqs.append(lnode['seq'])
                                    scanned_total += len(lrows)
                                    last_parent, last_page, last_depth = lparent, lpage, lnode['depth']
                                    if lres.get('has_more') is True:
                                        if not lrows:
                                            raise ValueError('SCAN_INCOMPLETE_PAGE')
                                        continuations.append(dict(
                                            priority=0,
                                            node_key=lparent,
                                            depth=lnode['depth'],
                                            leaf=1,
                                            next_page=lpage + 1,
                                            cursor=lres.get('next_cursor'),
                                        ))
                                    else:
                                        finished_keys.append(lparent)
                                except Exception as exc:
                                    deferred_err = exc
                                    break
                            if pop_seqs:
                                try:
                                    flush_leaves()
                                except Exception:
                                    if deferred_err is None:
                                        raise
                            if deferred_err is not None:
                                raise deferred_err
                            continue
                        parent = node['node_key']
                        depth = node['depth']
                        page = node['next_page']
                        cursor = node['cursor']
                        if self.stop.is_set() or self.cancel_event.is_set():
                            operation.cancelled.set()
                        safe(local=True)
                        if self.cancel_event.wait(.05 if self.playing() else .001):
                            operation.cancelled.set()
                        safe(local=True)
                        dir_proof = peek.get('dir_proof')
                        def _verify_frontier_page(_v_parent, raw_items, *, page, size, total=None, has_more=False, from_adapter=False):
                            from .pan_accounts import PanError
                            _verify_frontier_page.verified = True
                            if dir_proof is None:
                                return
                            offset = (page - 1) * size
                            sigs = [encode((r.get('file_id'), r.get('directory'))) for r in raw_items]
                            if len(set(sigs)) != len(sigs):
                                raise PanError('PAN_REPLY_INVALID')
                            cross_task = dir_proof['seen_count'] > 0 and dir_proof['proof_task'] not in ('', task)
                            if page == 1:
                                if dir_proof['seen_count'] != 0 or dir_proof['next_offset'] != 0:
                                    raise PanError('PAN_PAGE_EXPIRED')
                                new_seen = len(raw_items)
                            else:
                                if dir_proof['proof_version'] < FRONTIER_PROOF_VERSION or dir_proof['seen_count'] <= 0:
                                    raise PanError('PAN_PAGE_EXPIRED')
                                if dir_proof['expected_total'] is not None and total != dir_proof['expected_total']:
                                    if cross_task:
                                        raise ValueError('SCAN_TOTAL_CHANGED')
                                    raise PanError('PAN_PAGE_EXPIRED')
                                if dir_proof['expected_total'] is None and total is not None:
                                    raise PanError('PAN_PAGE_EXPIRED')
                                if total is not None and offset != dir_proof['next_offset']:
                                    raise PanError('PAN_PAGE_EXPIRED')
                                if self.index.frontier_has_entry_overlap(task, parent, sigs):
                                    if from_adapter:
                                        raise PanError('PAN_PAGE_EXPIRED')
                                    raise ValueError('SCAN_PAGE_CYCLE')
                                new_seen = dir_proof['seen_count'] + len(raw_items)
                            if total is not None and not has_more and new_seen != total:
                                raise PanError('PAN_INCOMPLETE_PAGE')
                        _verify_frontier_page.verified = False
                        result = port.page(operation, expected, parent, page, cursor, frontier_check=_verify_frontier_page)
                        excluded_versions |= result.get('excluded_versions') is True
                        safe()
                        rows = result['items']
                        if type(rows) is not list or len(rows) > SCAN_WINDOW:
                            raise ValueError('SCAN_INVALID_PAGE')
                        declared_total = result.get('declared_total')
                        if (
                            not is_leaf
                            and declared_total is not None
                            and peek['expected_total'] is not None
                            and declared_total != peek['expected_total']
                        ):
                            raise ValueError('SCAN_TOTAL_CHANGED')
                        signature = result['signature']
                        entry_sigs = []
                        if signature is not None:
                            entry_sigs = [encode(item) for item in signature]
                            if self.index.frontier_has_entry_overlap(task, parent, entry_sigs):
                                raise ValueError('SCAN_PAGE_CYCLE')
                        refs, descriptions = [], {}
                        new_leaves, new_dirs = [], []
                        dir_count = peek['state']['dir_count']
                        hit_dir_limit = False
                        seen_new_dirs = set()
                        for row in rows:
                            if row['directory'] is not None:
                                folder = row['directory']
                                if row.get('leaf_container') is True:
                                    # Media item leaves (e.g. Emby item:*) are NOT real directories.
                                    new_leaves.append((folder, depth + 1))
                                else:
                                    if folder in seen_new_dirs or self.index.frontier_known_dir(task, folder):
                                        continue
                                    if depth >= MAX_DEPTH or dir_count >= MAX_DIRECTORIES:
                                        hit_dir_limit = True
                                        continue
                                    seen_new_dirs.add(folder)
                                    dir_count += 1
                                    new_dirs.append((folder, depth + 1))
                            elif row['reference'] is not None:
                                refs.append(row['reference'])
                                if 'description' in row:
                                    descriptions[row['reference']['id']] = row['description']
                        has_more = result.get('has_more') is True
                        next_cursor = None
                        if has_more:
                            if not rows:
                                raise ValueError('SCAN_INCOMPLETE_PAGE')
                            raw_cursor = result.get('next_cursor')
                            if raw_cursor is not None:
                                if not raw_cursor or self.index.frontier_has_cursor(task, parent, raw_cursor):
                                    raise ValueError('SCAN_CURSOR_CYCLE')
                                next_cursor = raw_cursor
                        est_queued = max(0, peek['queued'] - 1 + len(new_leaves) + len(new_dirs) + (1 if has_more else 0))
                        self.max_queue = max(self.max_queue, est_queued)
                        checkpoint = dict(
                            parent=parent[:256],
                            page=page,
                            cursor=(cursor[:256] if isinstance(cursor, str) else None),
                            queued=est_queued,
                            depth=depth,
                        )
                        frontier_step = dict(
                            pop_seq=node['seq'],
                            dir_key=parent,
                            is_leaf=is_leaf,
                            declared_total=declared_total,
                            page_item_count=len(rows),
                            next_offset=(page - 1) * SCAN_WINDOW + len(rows),
                            entry_sigs=entry_sigs,
                            new_leaves=new_leaves,
                            new_dirs=new_dirs,
                            dir_count=dir_count,
                            partial_latch=hit_dir_limit,
                            continuation=(
                                dict(
                                    priority=(0 if is_leaf else 1),
                                    node_key=parent,
                                    depth=depth,
                                    leaf=int(is_leaf),
                                    next_page=page + 1,
                                    cursor=next_cursor,
                                )
                                if has_more
                                else None
                            ),
                        )
                        safe(local=True)
                        commit(
                            lambda: self.index.frontier_batch(
                                task,
                                refs,
                                checkpoint,
                                len(rows),
                                descriptions=descriptions or None,
                                frontier_step=frontier_step,
                            )
                        )
                        if hit_dir_limit:
                            raise ValueError('SCAN_DIRECTORY_LIMIT')
                safe()
                # Account CAS also encloses the absence inference boundary.
                if excluded_versions:
                    # Admitted siblings have already committed. No negative
                    # membership inference from an incomplete version listing.
                    commit(lambda: self.index.finish(task, 'interrupted', 'SERVER_VERSIONS_EXCLUDED'))
                else:
                    commit(lambda: self.index.finish(task, 'completed'))
                return
        except Exception as error:
            if self.profile_revoked.is_set():
                state, reason = 'interrupted', 'PROFILE_CHANGED'
            elif self.stop.is_set():
                state, reason = 'interrupted', 'SERVICE_STOPPED'
            elif self.cancel_event.is_set():
                state, reason = 'canceled', 'CANCEL_CONFIRMED'
            elif port.revoked(expected):
                state, reason = 'interrupted', 'ACCOUNT_REVOKED'
            else:
                code = str(error)
                if code in {'PAN_INCOMPLETE_PAGE', 'PAN_PAGE_EXPIRED', 'SCAN_TOTAL_CHANGED', 'SCAN_DIRECTORY_LIMIT'}:
                    state, reason = 'interrupted', code
                else:
                    reason = code if code in {'SCAN_INVALID_PAGE', 'SCAN_PAGE_CYCLE', 'SCAN_DIRECTORY_LIMIT',
                        'SCAN_CURSOR_CYCLE', 'SCAN_INCOMPLETE_PAGE', 'SCAN_FRONTIER_LIMIT', 'PAN_BUDGET_EXHAUSTED',
                        'PAN_OPERATION_TIMEOUT', 'PAN_RATE_LIMITED', 'CATALOG_SOURCE_UNAVAILABLE',
                        'CATALOG_AUTHORITY_CHANGED', 'CATALOG_RECHECK_INCOMPLETE', 'CATALOG_SOURCE_UNSUPPORTED',
                        'CATALOG_NETWORK_INCOMPLETE', 'CATALOG_NETWORK_METADATA_REQUIRED'} else 'SCAN_UNAVAILABLE'
            self.index.finish(task, state, reason)
        finally:
            with self.lock:
                self.operation = None

    def dispatch(self, action, body):
        self._profile()
        if isinstance(action, str) and action.startswith(('catalog_mount_', 'catalog_local_', 'catalog_network_')):
            return self.mounted.dispatch(action, body)
        expected = self._guard(body.get('expected'))
        args = {key: value for key, value in body.items() if key != 'expected'}
        descriptors = {
            'catalog_holdings': ({'identities'}, self.index.holdings),
            'catalog_parent': ({'parent_id'}, self.index.parent_descriptor),
            'catalog_describe': ({'file_ids'}, self.index.describe_files),
        }
        if action in descriptors:
            fields, method = descriptors[action]
            if set(args) != fields:
                raise ValueError('CATALOG_ACTION_INVALID')
            return self.pans.accounts.run_if_current(expected, lambda: method(expected, **args))
        if action == 'catalog_manual_records' and set(args) <= {'file_ids', 'offset', 'limit', 'projection_revision'}:
            return self.pans.accounts.run_if_current(expected, lambda: self.index.manual_records(expected, **args))
        if action == 'catalog_sources' and not args:
            store = self._registry()
            try:
                rows = [row for row in store.directories() if (row['provider'], row['account_id']) ==
                        (expected['provider'], expected['account_id'])]
            finally:
                store.close()
            return self.pans.accounts.run_if_current(expected, lambda: source_list([
                dict(id=r['id'], name=r['name'], observation=self.source_observation(expected, r['id']))
                for r in rows]))
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
            return self.pans.accounts.run_if_current(expected, lambda: self.query(expected, **args))
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

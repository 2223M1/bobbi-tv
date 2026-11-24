"""Experimental SMB/NFS/WebDAV port for the existing catalog worker.

Kodi owns transport/authentication. Cancellation surrounds bounded directory
requests; it cannot interrupt a blocked Kodi VFS call. No second scanner or DB.
"""
from contextlib import contextmanager
from threading import Event
from urllib.parse import unquote, urlsplit

from bobbi_core import network_ref, typed_ref
from bobbi_core.library_contract import SCHEMES, VIDEO_EXTENSIONS, MAX_DIRECTORY_ITEMS, joined_path
from .libraries import Registry
from .scan_sources import MountedPort


def network_listing(result, path, maximum=MAX_DIRECTORY_ITEMS):
    """Strict sibling enumeration; presentation native_listing is not proof.

    Its missing-limit fallback, metadata date truncation and name deduplication
    are deliberately unavailable here. Unsupported files still consume budget.
    """
    if type(result) is not dict or type(result.get('files')) is not list:
        raise ValueError('CATALOG_NETWORK_INCOMPLETE')
    rows, limits = result['files'], result.get('limits')
    if (type(limits) is not dict or not {'start', 'end', 'total'} <= set(limits) or
            any(type(limits[k]) is not int for k in ('start', 'end', 'total')) or
            limits['start'] != 0 or limits['end'] != len(rows) or limits['total'] != len(rows) or
            not 0 <= len(rows) <= min(maximum, MAX_DIRECTORY_ITEMS)):
        raise ValueError('CATALOG_NETWORK_INCOMPLETE')
    prefix, names, items = path.rstrip('/') + '/', set(), []
    for row in rows:
        if type(row) is not dict or row.get('filetype') not in ('file', 'directory'):
            raise ValueError('CATALOG_NETWORK_INCOMPLETE')
        target = row.get('file')
        if type(target) is not str or len(target) > 16384 or not target.startswith(prefix):
            raise ValueError('CATALOG_NETWORK_INCOMPLETE')
        tail = target[len(prefix):]
        folder = row['filetype'] == 'directory'
        if folder and tail.endswith('/'):
            tail = tail[:-1]
        try:
            name = unquote(tail, errors='strict')
            typed_ref.relative(name)
        except (ValueError, UnicodeError):
            raise ValueError('CATALOG_NETWORK_INCOMPLETE') from None
        if '/' in name or name in names:
            raise ValueError('CATALOG_NETWORK_INCOMPLETE')
        names.add(name)
        info = None
        if not folder and any(name.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
            info = network_ref.metadata(row.get('size'), row.get('lastmodified'))
        items.append(dict(name=name, directory=folder, metadata=info))
    return items


def kodi_directory(path, maximum):
    from .kodi import rpc
    return rpc('Files.GetDirectory', dict(directory=path, media='files',
        properties=['size', 'lastmodified'], limits=dict(start=0, end=maximum + 1)))


class NetworkPort(MountedPort):
    capabilities = dict(reference_kind='network_path', identity_policy='registry_root_relative_path',
        enumeration=True, stat=False, metadata_recheck=True, cancellation='between_io',
        completeness='explicit_native_limits', replay_cursor=False, authority='registry_revision',
        experimental=True, device_verified=False, strong_content_identity=False, exact_resume=False)

    def __init__(self, root, fetch=kodi_directory, **kwargs):
        super().__init__(root, **kwargs)
        self.fetch = fetch

    @staticmethod
    def source_scope(source):
        if source.kind != 'vfs' or urlsplit(source.location).scheme not in SCHEMES:
            raise ValueError('CATALOG_SOURCE_UNSUPPORTED')
        return dict(reference_kind='network_path', source_id=source.id,
                    namespace=typed_ref.digest('network', source.location), generation='')

    def describe(self, source_id):
        store = Registry(self.root / 'libraries.sqlite3')
        try:
            source, revision = store.source_snapshot(source_id)
            return source, dict(self.source_scope(source), generation=revision)
        except ValueError as error:
            if str(error) == 'CATALOG_SOURCE_UNSUPPORTED':
                raise
            raise ValueError('CATALOG_SOURCE_UNAVAILABLE') from None
        finally:
            store.close()

    def scope(self, source_id):
        return self.describe(source_id)[1]

    def snapshot(self, expected):
        current = self.scope(expected['source_id'])
        if current != expected:
            raise ValueError('CATALOG_AUTHORITY_CHANGED')
        return current

    def publish(self, expected, write):
        source = self.require(expected)
        store = Registry(self.root / 'libraries.sqlite3')
        try:
            return store.run_if_current(source, expected['generation'], write)
        finally:
            store.close()

    def listing(self, authority, parent, maximum, check):
        typed_ref.relative(parent, empty=True)
        check()
        source = self.require(authority)
        path = joined_path(source, parent)
        try:
            result = self.fetch(path, min(maximum, MAX_DIRECTORY_ITEMS))
        except Exception:
            # Upstream exceptions can include URLs/credentials. Fixed codes only.
            raise ValueError('CATALOG_SOURCE_UNAVAILABLE') from None
        check()
        self.require(authority)
        return network_listing(result, path, maximum)

    @contextmanager
    def open_scan(self, authority, cancel=None, seconds=1800, max_pages=1200, max_items=12000):
        session = NetworkSession(self, authority, cancel or Event(), seconds, max_pages, max_items)
        try:
            session.check()
            yield session
        finally:
            session.close()

    def select_reference(self, authority, reference, session, live, allow_changed=False):
        def check():
            live()
            session.check()
        return self._lookup(authority, reference, check, allow_changed)

    def stat_by_reference(self, authority, reference, check=lambda: None):
        return self._lookup(authority, reference, check, allow_changed=False)

    def _lookup(self, authority, reference, check, allow_changed):
        reference = network_ref.validate(reference)
        if (reference['source_id'], reference['namespace']) != (authority['source_id'], authority['namespace']):
            raise ValueError('CATALOG_REFERENCE_INVALID')
        # Kodi supplies sibling metadata in the directory response. Validate
        # completeness/uniqueness for the entire bounded response before matching.
        for row in self.listing(authority, reference['parent'], MAX_DIRECTORY_ITEMS, check):
            if row['name'] == reference['name'] and row['metadata'] is not None:
                current = network_ref.observed(authority, reference['relative'], row['metadata'])
                if allow_changed or network_ref.same_observation(reference, current):
                    return current
                break
        raise ValueError('CATALOG_FILE_CHANGED')


class NetworkSession:
    def __init__(self, port, authority, cancelled, seconds, max_pages, max_items):
        self.port, self.authority, self.cancelled = port, dict(authority), cancelled
        self.deadline = port.clock() + seconds
        self.max_pages, self.max_items = max_pages, max_items
        self.pages = self.items = 0
        self.rows = self.parent = None
        self.offset = 0

    def check(self, validate_authority=True):
        if self.cancelled.is_set():
            raise ValueError('CATALOG_SCAN_STOPPED')
        if self.port.clock() >= self.deadline:
            raise ValueError('CATALOG_RECHECK_INCOMPLETE')
        if validate_authority:
            self.port.require(self.authority)

    def list_page(self, parent):
        self.check()
        if self.pages >= self.max_pages or self.items >= self.max_items:
            raise ValueError('CATALOG_RECHECK_INCOMPLETE')
        if self.rows is None:
            self.rows = self.port.listing(self.authority, parent, self.max_items - self.items, self.check)
            self.parent, self.offset = parent, 0
        elif parent != self.parent:
            raise ValueError('CATALOG_QUERY_INVALID')
        rows = []
        for row in self.rows[self.offset:self.offset + 20]:
            child = parent + '/' + row['name'] if parent else row['name']
            rows.append(dict(directory=row['directory'], relative=child,
                reference=network_ref.observed(self.authority, child, row['metadata'])
                    if row['metadata'] is not None else None))
        self.offset += len(rows)
        self.items += len(rows)
        complete = self.offset == len(self.rows)
        if complete:
            self.close()
        self.check()
        self.pages += 1
        return dict(items=rows, has_more=not complete)

    def close(self):
        self.rows = self.parent = None
        self.offset = 0

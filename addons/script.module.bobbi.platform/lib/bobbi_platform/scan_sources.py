"""One static CD2 mounted-path port, using existing Registry/mount evidence.

Not an SMB/NFS/WebDAV driver or a second login service. Cancellation/deadline
checks surround filesystem calls; Python cannot preempt a blocked FUSE syscall.
No stat evidence is promoted to a cryptographic identity or resume guarantee.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat
from threading import Event
import time

from bobbi_core import mounted_ref
from bobbi_core.file_ref import from_selected
from . import cd2_mounts
from .libraries import Registry, joined_path, VIDEO_EXTENSIONS, MAX_DIRECTORY_ITEMS
from .pan_providers import descriptor


def native_path(value):
    """Match existing local_listing on CE builds using an ASCII FS codec."""
    value = os.fspath(value)
    return value.encode('utf-8') if os.name == 'posix' and isinstance(value, str) else value


def mount_records():
    """Mount IDs + kernel boot ID distinguish detach/re-attach at one path."""
    try:
        with Path('/proc/self/mountinfo').open(encoding='utf-8') as stream:
            raw = stream.read(cd2_mounts.MAX_BYTES + 1)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
        if not re.fullmatch('[0-9a-f-]{36}', boot):
            return ()
        allowed = set(cd2_mounts.parse_mounts(raw))
        result = []
        for line in raw.splitlines():
            before, _, after = line.partition(' - ')
            fields = before.split()
            if len(fields) < 6:
                continue
            path = re.sub(r'\\(040|011|012|134)', lambda m: chr(int(m.group(1), 8)), fields[4])
            if path in allowed:
                result.append(dict(path=path, generation=mounted_ref.digest(boot, before, after)))
        return tuple(result)
    except (OSError, UnicodeError, ValueError):
        return ()


class NativePort:
    """Source-specific account CAS and native pagination proof, no traversal."""
    mounted = False

    def __init__(self, pans):
        self.pans = pans

    def scan(self, expected, task, cancel, **budget):
        return self.pans.scan_operation(expected, task, **budget)

    def check(self, operation, local=False):
        operation.check()

    def publish(self, expected, write):
        return self.pans.accounts.run_if_current(expected, write)

    def revoked(self, expected):
        return not self.pans.accounts.is_current(expected)

    def page(self, operation, expected, parent, page, cursor):
        result = self.pans.list_for_scan(expected, parent, page, cursor, operation=operation, size=20)
        rows = result['items']
        if type(rows) is not list or len(rows) > 20:
            raise ValueError('SCAN_INVALID_PAGE')
        entries = []
        for row in rows:
            if row.get('directory') is True:
                entries.append(dict(directory=row[descriptor(expected['provider']).parent_field], reference=None))
            else:
                reference = (from_selected(expected, row, parent)
                    if any(row.get('name', '').lower().endswith(ext) for ext in VIDEO_EXTENSIONS) else None)
                entries.append(dict(directory=None, reference=reference))
        return dict(items=entries, signature=tuple((r.get('file_id'), r.get('directory')) for r in rows),
                    has_more=result.get('has_more') is True, next_cursor=result.get('next_cursor'))


class MountedPort:
    mounted = True
    capabilities = dict(reference_kind='mounted_path', identity_policy='registry_root_relative_path',
        enumeration=True, stat=True, cancellation='between_io', completeness='closed_directory_iterators',
        replay_cursor=False, authority='existing_cd2_mount', device_verified=False,
        strong_content_identity=False, exact_resume=False)

    def __init__(self, root, mounts=mount_records, clock=time.monotonic):
        self.root, self.mounts, self.clock = Path(root), mounts, clock

    def source(self, source_id):
        store = Registry(self.root / 'libraries.sqlite3')
        try:
            return store.get(source_id)
        finally:
            store.close()

    def scope(self, source_id):
        """Local descriptor permission; no FUSE call or playback authority."""
        return self.source_scope(self.source(source_id))

    @staticmethod
    def source_scope(source):
        if (source.kind != 'vfs' or source.username or source.password or
                not (source.location.startswith('/') or re.match(r'^[A-Za-z]:[/\\]', source.location))):
            raise ValueError('CATALOG_SOURCE_UNSUPPORTED')
        return dict(reference_kind='mounted_path', source_id=source.id,
                    namespace=mounted_ref.digest('cd2', source.location), generation='')

    def snapshot(self, expected):
        source = self.source(expected['source_id'])
        current = self.source_scope(source)
        if current['namespace'] != expected['namespace']:
            raise ValueError('CATALOG_AUTHORITY_CHANGED')
        root = source.location.rstrip('/\\')
        mounts = [row for row in self.mounts() if root == row['path'] or root.startswith(row['path'].rstrip('/') + '/')]
        if mounts:
            mount = max(mounts, key=lambda row: len(row['path']))
            current['generation'] = mounted_ref.digest(current['namespace'], mount['generation'])
        return current

    def publish(self, expected, write):
        current = self.snapshot(expected)
        if expected.get('generation') and current != expected:
            raise ValueError('CATALOG_AUTHORITY_CHANGED')
        return write()

    def revoked(self, expected):
        return False  # Mount failures keep their explicit source error code.

    def check(self, operation, local=False):
        operation.check(validate_authority=not local)

    def page(self, operation, expected, parent, page, cursor):
        result = operation.list_page(parent)
        return dict(items=[dict(directory=row['relative'] if row['directory'] else None,
                    reference=row.get('reference')) for row in result['items']],
                    # A closed iterator, not repeated filenames, proves paging.
                    signature=None, has_more=result['has_more'], next_cursor=None)

    def scan(self, expected, task, cancel, **budget):
        return self.open_scan(expected, cancel, seconds=budget['seconds'],
                              max_pages=budget['max_pages'], max_items=budget['max_items'])

    def describe(self, source_id):
        source = self.source(source_id)
        scope = self.source_scope(source)
        root = source.location.rstrip('/\\')
        # Only kernel-observed CD2 local mounts qualify. A similarly named
        # folder, credential URL or ordinary registered NAS does not.
        mounts = [row for row in self.mounts() if root == row['path'] or root.startswith(row['path'].rstrip('/') + '/')]
        if not mounts:
            raise ValueError('CATALOG_SOURCE_UNAVAILABLE')
        mount = max(mounts, key=lambda row: len(row['path']))
        path = native_path(root)
        if os.path.islink(path) or not os.path.isdir(path):
            raise ValueError('CATALOG_SOURCE_UNAVAILABLE')
        if os.path.realpath(path) != os.path.abspath(path):
            raise ValueError('CATALOG_SOURCE_UNSUPPORTED')
        namespace = scope['namespace']
        authority = dict(reference_kind='mounted_path', source_id=source.id, namespace=namespace,
                         generation=mounted_ref.digest(namespace, mount['generation']))
        return source, authority

    def require(self, authority):
        source, current = self.describe(authority['source_id'])
        if current != authority:
            raise ValueError('CATALOG_AUTHORITY_CHANGED')
        return source

    def path(self, source, relative):
        mounted_ref.relative(relative, empty=True)
        target = native_path(joined_path(source, relative))
        root = os.path.realpath(native_path(source.location))
        # Reject symlinks at every level, including links which happen to point
        # back inside the root. Path-only identities have no symlink contract.
        probe = native_path(source.location)
        for part in relative.split('/') if relative else ():
            probe = os.path.join(probe, native_path(part))
            if os.path.islink(probe):
                raise ValueError('CATALOG_SOURCE_UNSUPPORTED')
        resolved = os.path.realpath(target)
        try:
            if os.path.commonpath((root, resolved)) != root:
                raise ValueError
        except ValueError:
            raise ValueError('CATALOG_REFERENCE_INVALID') from None
        return target

    @contextmanager
    def open_scan(self, authority, cancel=None, seconds=1800, max_pages=1200, max_items=12000):
        session = MountedSession(self, authority, cancel or Event(), seconds, max_pages, max_items)
        try:
            session.check()
            yield session
        finally:
            session.close()

    def stat_by_reference(self, authority, reference, check=lambda: None):
        reference = mounted_ref.validate(reference)
        check()
        source = self.require(authority)
        if (reference['source_id'], reference['namespace']) != (authority['source_id'], authority['namespace']):
            raise ValueError('CATALOG_REFERENCE_INVALID')
        path = self.path(source, reference['relative'])
        info = os.stat(path, follow_symlinks=False)
        check()
        self.require(authority)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('CATALOG_FILE_CHANGED')
        current = mounted_ref.observed(authority, reference['relative'], info)
        if not mounted_ref.same_observation(reference, current):
            raise ValueError('CATALOG_FILE_CHANGED')
        return current


class MountedSession:
    def __init__(self, port, authority, cancelled, seconds, max_pages, max_items):
        self.port, self.authority, self.cancelled = port, authority, cancelled
        self.deadline = port.clock() + seconds
        self.max_pages, self.max_items = max_pages, max_items
        self.pages = self.items = 0
        self.iterator = self.parent = None
        self.directory_count = 0

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
        if self.iterator is None:
            source = self.port.require(self.authority)
            self.iterator = os.scandir(self.port.path(source, parent))
            self.parent, self.directory_count = parent, 0
        elif self.parent != parent:
            raise ValueError('CATALOG_QUERY_INVALID')
        rows, complete = [], False
        for _ in range(20):
            self.check(False)
            entry = next(self.iterator, None)
            if entry is None:
                complete = True
                self.close()
                break
            self.directory_count += 1
            self.items += 1
            if self.directory_count > MAX_DIRECTORY_ITEMS or self.items > self.max_items:
                raise ValueError('CATALOG_RECHECK_INCOMPLETE')
            name = entry.name.decode('utf-8') if isinstance(entry.name, bytes) else entry.name
            child = parent + '/' + name if parent else name
            mounted_ref.relative(child)
            if entry.is_symlink():
                raise ValueError('CATALOG_SOURCE_UNSUPPORTED')
            # Windows DirEntry.stat reports zero inode/device in CPython;
            # os.stat supplies the actual attributes used by the recheck.
            # CE's native scandir attributes already have the same semantics.
            info = (os.stat(entry.path, follow_symlinks=False) if os.name == 'nt'
                    else entry.stat(follow_symlinks=False))
            if stat.S_ISDIR(info.st_mode):
                rows.append(dict(directory=True, relative=child))
            elif stat.S_ISREG(info.st_mode) and any(name.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                rows.append(dict(directory=False, reference=mounted_ref.observed(self.authority, child, info)))
            else:
                rows.append(dict(directory=False, reference=None))
        self.check()
        self.pages += 1
        return dict(items=rows, has_more=not complete)

    def close(self):
        if self.iterator is not None:
            self.iterator.close()
            self.iterator = None

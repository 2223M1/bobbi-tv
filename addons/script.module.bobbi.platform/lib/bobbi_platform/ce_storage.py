"""CE install capacity and explicit cleanup; current rollback stays protected."""
from contextlib import ExitStack, closing
from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import zipfile

from .updates import UpdateError, _Lock, _safe_path, archive_rows, MAX_MANIFEST, MAX_BACKUP_RECEIPT
from .upstream_addons import UPSTREAM_COMPONENTS, plan_dependencies


def tr(key, **kwargs):
    from .bootstrap_i18n import tr as _bootstrap_tr
    return _bootstrap_tr(key, **kwargs)

RESERVE = 16*1024**2
SCAN_FILES = 100000
SCAN_BYTES = 8*1024**3
# Simultaneous old/new receipts, journal/state temporaries and transaction dirs.
CONTROL_BYTES = 2*MAX_BACKUP_RECEIPT + 4*MAX_MANIFEST
CONTROL_INODES = 32


class SpaceRequired(UpdateError):
    def __init__(self, report):
        super().__init__('INSTALLATION_SPACE_REQUIRED')
        self.space = report


def allocation_unit(path):
    return filesystem(path)['unit']


def _existing_directory(path):
    path = _safe_path(path)
    while not path.exists():
        path = path.parent
    if not path.is_dir():
        path = path.parent
    return path


def filesystem(path):
    """Observe an existing ancestor without creating a future destination."""
    path = _existing_directory(path)
    info = path.stat()
    if os.name == 'nt':
        import ctypes
        sectors, size, free, total = (ctypes.c_ulong() for _ in range(4))
        if not ctypes.windll.kernel32.GetDiskFreeSpaceW(str(path.anchor),
                ctypes.byref(sectors), ctypes.byref(size), ctypes.byref(free), ctypes.byref(total)):
            raise OSError('STORAGE_STAT_UNAVAILABLE')
        unit, available, inodes = sectors.value*size.value, shutil.disk_usage(path).free, None
    else:
        value = os.statvfs(path)
        unit, available, inodes = value.f_frsize, value.f_bavail*value.f_frsize, value.f_favail
        if type(inodes) is not int or inodes < 0:
            raise OSError('STORAGE_INODES_UNAVAILABLE')
    if not 512 <= unit <= 1024*1024 or available < 0:
        raise OSError('STORAGE_STAT_INVALID')
    return dict(device=info.st_dev, unit=unit, free_bytes=available, free_inodes=inodes)


def component_layout(data, item):
    """A bounded component only, using exactly the extraction layout contract."""
    folders, sizes = set(), []
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise UpdateError('Invalid component archive') from error
    with archive:
        for row in archive_rows(archive, item):
            path = PurePosixPath(row.filename)
            folders.update(parent.as_posix() for parent in path.parents if str(parent) != '.')
            if row.is_dir():
                folders.add(path.as_posix())
            else:
                sizes.append(row.file_size)
    return dict(id=item['id'], files=sizes, directories=len(folders))


def bundle_layout(signed):
    return [component_layout(signed.read(row['file'], row['size']), row)
            for row in signed.manifest['components']]


def bundle_manifests(signed):
    """Read verified addon.xml bytes per component without extracting to disk."""
    manifests = {}
    for row in signed.manifest['components']:
        data = signed.read(row['file'], row['size'])
        with zipfile.ZipFile(BytesIO(data)) as archive:
            archive_rows(archive, row)
            target = row['id'] + '/addon.xml'
            if target in archive.namelist():
                manifests[row['id']] = archive.read(target)
    return manifests


def tree_allocation(path, unit, budget=None, required=False):
    """Complete bounded copy allocation, including implicit directory inodes."""
    budget = budget if budget is not None else [SCAN_FILES, SCAN_BYTES]
    total, inodes, logical, stack, device = 0, 0, 0, [Path(path)], None
    while stack:
        item = _safe_path(stack.pop())
        try:
            info = item.lstat()
        except FileNotFoundError:
            if required or inodes:
                raise UpdateError('STORAGE_TREE_CHANGED')
            return dict(bytes=0, inodes=0, logical=0)
        budget[0] -= 1
        if budget[0] < 0 or (device is not None and device != info.st_dev):
            raise UpdateError('STORAGE_SCAN_INCOMPLETE')
        device = info.st_dev
        inodes += 1
        if stat.S_ISDIR(info.st_mode):
            total += unit
            with os.scandir(item) as entries:
                for entry in entries:
                    if len(stack) >= budget[0]:
                        raise UpdateError('STORAGE_SCAN_INCOMPLETE')
                    stack.append(Path(entry.path))
        elif stat.S_ISREG(info.st_mode):
            logical += info.st_size
            budget[1] -= info.st_size
            if budget[1] < 0:
                raise UpdateError('STORAGE_SCAN_INCOMPLETE')
            total += ((info.st_size+unit-1)//unit)*unit
        else:
            raise UpdateError('STORAGE_SCAN_INCOMPLETE')
    return dict(bytes=total, inodes=inodes, logical=logical)


def sqlite_size(path):
    """Read the WAL-visible snapshot, never checkpoint or create a database."""
    path = _safe_path(path)
    if not path.is_file():
        raise UpdateError('STORAGE_DATABASE_UNAVAILABLE')
    wal, shm = Path(str(path)+'-wal'), Path(str(path)+'-shm')
    for side in (wal, shm):
        _safe_path(side)
    # SQLite's read-only WAL connection can create SHM if it is absent.
    if wal.exists() and wal.stat().st_size and not shm.is_file():
        raise UpdateError('STORAGE_DATABASE_SNAPSHOT_UNAVAILABLE')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        pages = db.execute('PRAGMA page_count').fetchone()[0]
        size = db.execute('PRAGMA page_size').fetchone()[0]
    if type(pages) is not int or pages <= 0 or size not in (512,1024,2048,4096,8192,16384,32768,65536):
        raise UpdateError('STORAGE_DATABASE_SIZE_INVALID')
    return pages*size


class SpaceBudget:
    """One metadata-only estimator, grouped by actual destination filesystem."""
    def __init__(self, phase):
        self.phase, self.filesystems, self.parts = phase, {}, []

    def volume(self, path):
        path = _existing_directory(path)
        key = path.stat().st_dev
        if key not in self.filesystems:
            observed = filesystem(path)
            self.filesystems[key] = dict(observed, required_bytes=RESERVE, required_inodes=16)
        return self.filesystems[key]

    def add(self, path, label, size, inodes=1, allocated=False):
        if type(size) is not int or size < 0 or type(inodes) is not int or inodes < 0:
            raise UpdateError('STORAGE_ESTIMATE_INCOMPLETE')
        volume = self.volume(path)
        unit = volume['unit']
        size = size if allocated else ((size+unit-1)//unit)*unit
        volume['required_bytes'] += size
        volume['required_inodes'] += inodes
        self.parts.append(dict(kind=label, bytes=size, inodes=inodes, device=volume['device']))
        return size

    def tree(self, source, destination, label, required=False, budget=None):
        value = tree_allocation(source, self.volume(destination)['unit'], budget, required)
        self.add(destination, label, value['bytes'], value['inodes'], allocated=True)
        return value

    def layout(self, rows, destination, label):
        unit = self.volume(destination)['unit']
        size, count = 0, 0
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'id','files','directories'}
                    or not isinstance(row['files'], list) or type(row['directories']) is not int
                    or row['directories'] < 1 or any(type(n) is not int or n < 0 for n in row['files'])):
                raise UpdateError('STORAGE_LAYOUT_INVALID')
            size += sum(((n+unit-1)//unit)*unit for n in row['files']) + row['directories']*unit
            count += len(row['files']) + row['directories']
        self.add(destination, label, size, count, allocated=True)
        return size

    def report(self):
        rows = list(self.filesystems.values())
        return dict(schema=2, phase=self.phase, complete=True, parts=list(self.parts),
            filesystems=rows, required_bytes=sum(r['required_bytes'] for r in rows),
            free_bytes=sum(r['free_bytes'] for r in rows),
            fits=bool(rows) and all(r['free_bytes'] >= r['required_bytes'] and
                (r['free_inodes'] is None or r['free_inodes'] >= r['required_inodes']) for r in rows))


def program_budget(addons, work, managed, layout=(), *, phase='before-stage', retain=True):
    budget = SpaceBudget(phase)
    if budget.volume(addons)['device'] != budget.volume(work)['device']:
        raise UpdateError('Staging and addons must share a filesystem')
    budget.layout(layout, work, 'stage')
    budget.add(work, 'transaction-metadata', CONTROL_BYTES, CONTROL_INODES)
    # Forward replacement uses rename. This is headroom for the *explicit*
    # rollback's full copy, not a second charge for the existing live trees.
    if retain:
        scan = [SCAN_FILES, SCAN_BYTES]
        for name in sorted(managed):
            budget.tree(Path(addons)/name, work, 'rollback-copy', budget=scan)
    return budget


def footprint(path, budget=None, device=None):
    """Bounded metadata-only observation; incomplete totals are lower bounds."""
    budget = budget if budget is not None else [SCAN_FILES, SCAN_BYTES]
    total, complete, stack = 0, True, [Path(path)]
    while stack:
        item = stack.pop()
        if budget[0] <= 0 or budget[1] < 0:
            return total, False
        try:
            item = _safe_path(item)
            info = item.lstat()
            budget[0] -= 1
            if device is None:
                device = info.st_dev
            elif info.st_dev != device:
                complete = False
                continue
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(item) as entries:
                    for entry in entries:
                        if len(stack) >= budget[0]:
                            complete = False
                            break
                        stack.append(Path(entry.path))
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
                budget[1] -= info.st_size
            else:
                complete = False
        except FileNotFoundError:
            continue
        except (OSError, UpdateError):
            complete = False
    return total, complete


def install_plan(signed, addons, work, state, managed):
    """Extra allocation, not compressed-size multipliers or existing-file copies."""
    layout = bundle_layout(signed)
    manifests = bundle_manifests(signed)
    dep_plan = plan_dependencies(
        addons,
        None,
        managed=managed,
        candidate_manifests=manifests,
        strict_roots=True,
    )
    seedable_ids = set(dep_plan['seedable']) & set(UPSTREAM_COMPONENTS)
    # Kodi-local Installer restores with rename, unlike UpdateEngine.rollback.
    # It needs metadata headroom but no additional program-copy allocation.
    capacity = program_budget(addons, work, managed, layout, retain=False)
    seed = capacity.layout([row for row in layout if row['id'] in seedable_ids], addons, 'dependencies')
    report = capacity.report()
    unit = report['filesystems'][0]['unit']
    stage = sum(row['bytes'] for row in report['parts'] if row['kind'] == 'stage')
    rollback = sum(row['bytes'] for row in report['parts'] if row['kind'] == 'rollback-copy')
    budget = [SCAN_FILES, SCAN_BYTES]
    device = Path(work).stat().st_dev
    old_sizes = [footprint(Path(addons)/name, budget, device) for name in sorted(managed)]
    backup, backup_complete = footprint(Path(work)/state['tx']/'backup', budget, device) if state else (0, True)
    complete = backup_complete and all(row[1] for row in old_sizes)
    return dict(report, sequence=signed.manifest['sequence'],
        archive_bytes=signed.path.stat().st_size, archive_already_present=True,
        component_zip_bytes=sum(row['size'] for row in signed.manifest['components']),
        expanded_bytes=sum(sum(row['files']) for row in layout), stage_bytes=stage, dependency_copy_bytes=seed,
        current_program_bytes=sum(row[0] for row in old_sizes), retained_backup_bytes=backup,
        existing_sizes_complete=complete, rollback_copy_bytes=rollback, metadata_bytes=CONTROL_BYTES,
        backup_extra_bytes=0, allocation_unit=unit, reserve_bytes=RESERVE,
        fits=report['fits'] and complete, external_dependency_space_unknown=True)


def require_space(report):
    if not report.get('fits') or report.get('complete') is False:
        raise SpaceRequired(report)


def plan_text(plan, *, locale=None, host=None):
    def mib(value): return (value+1024**2-1)//1024**2
    text = tr(
        'storage_plan_main',
        locale=locale,
        host=host,
        archive=mib(plan['archive_bytes']),
        stage=mib(plan['stage_bytes']),
        seed=mib(plan['dependency_copy_bytes']),
        current=mib(plan['current_program_bytes']),
        backup=mib(plan['retained_backup_bytes']),
        rollback=mib(plan.get('rollback_copy_bytes', 0)),
        metadata=mib(plan.get('metadata_bytes', 0)),
        reserve=mib(plan['reserve_bytes']),
        required=mib(plan['required_bytes']),
        free=mib(plan['free_bytes']),
    )
    if not plan['existing_sizes_complete']:
        text += tr('storage_plan_incomplete', locale=locale, host=host)
    return text + tr('storage_plan_footer', locale=locale, host=host)


def _identity(path, root):
    path = _safe_path(path)
    if root not in path.parents:
        raise UpdateError('STORAGE_PLAN_CHANGED')
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_dev != root.stat().st_dev:
        raise UpdateError('ONLINE_CACHE_PATH_INVALID')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class Maintenance:
    """Locks span preview/confirmation/delete. Handoff archives are never owned."""
    def __init__(self, installer):
        self.installer = installer
        self.work = _safe_path(installer.work)
        self.stack = ExitStack()
        self.plan = None
        self.entered = False

    def __enter__(self):
        if self.entered:
            raise UpdateError('STORAGE_SESSION_ACTIVE')
        try:
            # Same order as installation then transfer; locks never wait.
            for name in ('installation.lock', '.bobbi-component-download.lock', '.bobbi-online-download.lock'):
                self.stack.enter_context(_Lock(self.work/name))
            state = self.installer._read()
            if state and (state['phase'] not in ('complete', 'restored') or state.get('host_pending')):
                raise UpdateError('INSTALLATION_RECOVERY_REQUIRED')
            self.entered = True
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *_):
        self.plan = None
        self.entered = False
        self.stack.close()

    def _candidates(self):
        folder = _safe_path(self.work/'downloads')
        if not folder.exists():
            return []
        paths = []
        for name in ('online.partial', 'online-resume.json', 'components-absence-v1.json'):
            path = folder/name
            if path.exists() or path.is_symlink(): paths.append(path)
        components = _safe_path(folder/'components-v1')
        if components.exists():
            for count, path in enumerate(components.iterdir(), 1):
                if count > SCAN_FILES:
                    raise UpdateError('ONLINE_COMPONENT_CACHE_LIMIT')
                if path.name == 'transfer.part' or re.fullmatch(r'[a-f0-9]{64}\.zip', path.name):
                    paths.append(path)
                if len(paths) > 260:
                    raise UpdateError('ONLINE_COMPONENT_CACHE_LIMIT')
        return sorted(paths)

    def preview(self):
        if not self.entered:
            raise UpdateError('STORAGE_SESSION_REQUIRED')
        state = self.installer._read()
        rows = [(path, _identity(path, self.work)) for path in self._candidates()]
        budget = [SCAN_FILES, SCAN_BYTES]
        device = self.work.stat().st_dev
        protected, complete, legacy = 0, True, 0
        unknown, unknown_bytes = 0, 0
        retired, retired_bytes, preparations, preparation_bytes = [], 0, [], 0
        from .ce_recovery import retired_transaction, preparation_transaction
        for count, path in enumerate(self.work.iterdir(), 1):
            if count > SCAN_FILES:
                complete = False
                break
            if re.fullmatch('[a-f0-9]{32}', path.name):
                size, known = footprint(path, budget, device)
                receipt = retired_transaction(self.work, path.name, state) if known else None
                preparing = preparation_transaction(self.work, path.name, state, budget) if known and not receipt else None
                if receipt:
                    retired.append((path, receipt))
                    retired_bytes += size
                elif preparing:
                    preparations.append((path, preparing))
                    preparation_bytes += size
                else:
                    protected += size
                    if not state or path.name not in (state['tx'], state.get('previous_tx')):
                        unknown += 1
                        unknown_bytes += size
                complete = complete and known
                if not state or path.name != state['tx']: legacy += 1
        handoff, downloads_complete = footprint(self.work/'downloads', budget, device)
        plan = dict(reclaimable_bytes=sum(identity[2] for _, identity in rows), files=len(rows),
                    free_bytes=shutil.disk_usage(self.work).free,
                    protected_transaction_bytes=protected, protected_sizes_complete=complete,
                    legacy_transactions=legacy, retained_download_bytes=max(0, handoff-sum(identity[2] for _, identity in rows)),
                    retained_download_sizes_complete=downloads_complete,
                    retired_transactions=len(retired), retired_transaction_bytes=retired_bytes,
                    preparation_transactions=len(preparations), preparation_bytes=preparation_bytes,
                    protected_unknown_transactions=unknown, protected_unknown_bytes=unknown_bytes)
        # No caller-supplied filename list can become deletion authority.
        self.plan = (plan, dict(plan), rows, retired, state, preparations)
        return plan

    def clear(self, plan, active=lambda: None):
        if not self.entered or self.plan is None or plan is not self.plan[0] or plan != self.plan[1]:
            raise UpdateError('STORAGE_PLAN_CHANGED')
        rows = self.plan[2]
        active()
        if self.installer._read() != self.plan[4]:
            raise UpdateError('STORAGE_PLAN_CHANGED')
        from .ce_recovery import retired_transaction, preparation_transaction, clear_preparation
        for path, proof in self.plan[5]:
            if preparation_transaction(self.work, path.name, self.installer._read()) != proof:
                raise UpdateError('STORAGE_PLAN_CHANGED')
        for path, receipt in self.plan[3]:
            if retired_transaction(self.work, path.name, self.plan[4]) != receipt:
                raise UpdateError('STORAGE_PLAN_CHANGED')
        current = [(path, _identity(path, self.work)) for path in self._candidates()]
        if current != rows:
            raise UpdateError('STORAGE_PLAN_CHANGED')
        removed, size = 0, 0
        for path, identity in rows:
            active()
            if _identity(path, self.work) != identity:
                raise UpdateError('STORAGE_PLAN_CHANGED')
            path.unlink()  # Exact flat, ordinary files only; no recursive delete.
            removed += 1
            size += identity[2]
        removed_transactions = 0
        for path, receipt in self.plan[3]:
            active()
            if (path.parent != self.work or retired_transaction(self.work, path.name, self.plan[4]) != receipt):
                raise UpdateError('STORAGE_PLAN_CHANGED')
            # Only completed, no-longer-referenced program transactions with
            # exact receipts. A partial cleanup cannot affect the live journal,
            # its previous transaction, recovery packages or user profile.
            shutil.rmtree(_safe_path(path))
            removed_transactions += 1
        size += plan['retired_transaction_bytes'] if removed_transactions else 0
        for path, proof in self.plan[5]:
            active()
            clear_preparation(self.installer, path.name, proof)
        size += plan['preparation_bytes']
        prepared = len(self.plan[5])
        self.plan = None
        return dict(removed_files=removed, removed_bytes=size, removed_transactions=removed_transactions,
                    removed_preparations=prepared)


def show(installer, host, dialog):
    """Use the active skin's existing dialogs, with one explicit delete choice."""
    def active():
        host.check_idle()
        monitor = getattr(host, 'monitor', None)
        if monitor and monitor.abortRequested():
            from .online_updates import Cancelled
            raise Cancelled('ONLINE_CANCELLED')
    active()
    with Maintenance(installer) as storage:
        plan = storage.preview()
        size = (plan['reclaimable_bytes'] + plan['retired_transaction_bytes'] + plan['preparation_bytes'])/(1024**2)
        detail = tr(
            'storage_preview_main',
            host=host,
            free=plan['free_bytes']/1024**2,
            cache=plan['reclaimable_bytes']/1024**2,
            files=plan['files'],
            kept=plan['protected_transaction_bytes']/1024**2,
            retired=plan['retired_transaction_bytes']/1024**2,
            transactions=plan['retired_transactions'],
        )
        detail += tr(
            'storage_preview_prep',
            host=host,
            prep=plan['preparation_bytes']/1024**2,
            count=plan['preparation_transactions'],
        )
        if plan['protected_unknown_transactions']:
            detail += tr('storage_preview_unknown', host=host, unknown=plan['protected_unknown_transactions'])
        if not plan['protected_sizes_complete']:
            detail += tr('storage_preview_incomplete', host=host)
        dialog.textviewer(tr('storage_title', host=host), detail)
        if not plan['files'] and not plan['retired_transactions'] and not plan['preparation_transactions']:
            return
        active()
        if not dialog.yesno(
            tr('storage_confirm_title', host=host),
            tr('storage_confirm_body', host=host, size=size, files=plan['files'],
               tx=plan['retired_transactions'] + plan['preparation_transactions']),
        ):
            return
        active()
        result = storage.clear(plan, active=active)
        dialog.ok(
            tr('storage_done_title', host=host),
            tr('storage_done_body', host=host, removed=result['removed_bytes']/1024**2),
        )

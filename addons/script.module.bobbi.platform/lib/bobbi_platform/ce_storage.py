"""CE install capacity and explicit transport-cache maintenance, never rollback GC."""
from contextlib import ExitStack
from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile

from .updates import UpdateError, _Lock, _safe_path, archive_rows
from .upstream_addons import UPSTREAM_COMPONENTS

RESERVE = 16*1024**2
SCAN_FILES = 100000
SCAN_BYTES = 8*1024**3


class SpaceRequired(UpdateError):
    def __init__(self, report):
        super().__init__('INSTALLATION_SPACE_REQUIRED')
        self.space = report


def allocation_unit(path):
    try:
        size = os.statvfs(path).f_frsize
        if 512 <= size <= 1024*1024:
            return size
    except (AttributeError, OSError):
        pass
    return 4096  # CE uses statvfs; desktop harness has a conservative default.


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
    unit = allocation_unit(work)
    expanded, stage, seed = 0, 0, 0
    for item in signed.manifest['components']:
        folders, size = set(), 0
        with zipfile.ZipFile(BytesIO(signed.read(item['file'], item['size']))) as archive:
            for row in archive_rows(archive, item):
                path = PurePosixPath(row.filename)
                folders.update(parent.as_posix() for parent in path.parents if str(parent) != '.')
                if row.is_dir():
                    folders.add(path.as_posix())
                else:
                    expanded += row.file_size
                    size += ((row.file_size+unit-1)//unit)*unit
        size += len(folders)*unit
        stage += size
        if item['id'] in UPSTREAM_COMPONENTS and not (Path(addons)/item['id']).exists():
            seed += size  # KodiHost copies only missing signed originals.
    budget = [SCAN_FILES, SCAN_BYTES]
    device = Path(work).stat().st_dev
    old_sizes = [footprint(Path(addons)/name, budget, device) for name in sorted(managed)]
    backup, backup_complete = footprint(Path(work)/state['tx']/'backup', budget, device) if state else (0, True)
    free = shutil.disk_usage(work).free
    return dict(schema=1, sequence=signed.manifest['sequence'], phase='before-stage',
        archive_bytes=signed.path.stat().st_size, archive_already_present=True,
        component_zip_bytes=sum(row['size'] for row in signed.manifest['components']),
        expanded_bytes=expanded, stage_bytes=stage, dependency_copy_bytes=seed,
        current_program_bytes=sum(row[0] for row in old_sizes), retained_backup_bytes=backup,
        existing_sizes_complete=backup_complete and all(row[1] for row in old_sizes),
        backup_extra_bytes=0, allocation_unit=unit, reserve_bytes=RESERVE,
        required_bytes=stage+seed+RESERVE, free_bytes=free,
        fits=free >= stage+seed+RESERVE, external_dependency_space_unknown=True)


def require_space(report):
    if not report['fits']:
        raise SpaceRequired(report)


def plan_text(plan):
    def mib(value): return (value+1024**2-1)//1024**2
    text = ('完整包已在本地：{archive} MiB；解压暂存预计 {stage} MiB；缺失原版依赖复制 {seed} MiB。\n'
            '现有程序 {current} MiB；已保留备份 {backup} MiB（均不删除）。\n'
            '同盘移动备份不再复制一份；预留 {reserve} MiB。需新增至少 {required} MiB，可用 {free} MiB。\n'
            'Kodi 另行下载的依赖及其他程序占用未计入保证；安装前会再检查。').format(
                archive=mib(plan['archive_bytes']),stage=mib(plan['stage_bytes']),seed=mib(plan['dependency_copy_bytes']),
                current=mib(plan['current_program_bytes']),backup=mib(plan['retained_backup_bytes']),
                reserve=mib(plan['reserve_bytes']),required=mib(plan['required_bytes']),free=mib(plan['free_bytes']))
    if not plan['existing_sizes_complete']:
        text += '\n现有程序与备份未能完整统计，显示的是已读下限，不影响新增空间估算。'
    return text


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
        for name in ('online.partial', 'online-resume.json'):
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
        for count, path in enumerate(self.work.iterdir(), 1):
            if count > SCAN_FILES:
                complete = False
                break
            if re.fullmatch('[a-f0-9]{32}', path.name):
                size, known = footprint(path, budget, device)
                protected += size
                complete = complete and known
                if not state or path.name != state['tx']: legacy += 1
        handoff, downloads_complete = footprint(self.work/'downloads', budget, device)
        plan = dict(reclaimable_bytes=sum(identity[2] for _, identity in rows), files=len(rows),
                    free_bytes=shutil.disk_usage(self.work).free,
                    protected_transaction_bytes=protected, protected_sizes_complete=complete,
                    legacy_transactions=legacy, retained_download_bytes=max(0, handoff-sum(identity[2] for _, identity in rows)),
                    retained_download_sizes_complete=downloads_complete)
        # No caller-supplied filename list can become deletion authority.
        self.plan = (plan, dict(plan), rows)
        return plan

    def clear(self, plan, active=lambda: None):
        if not self.entered or self.plan is None or plan is not self.plan[0] or plan != self.plan[1]:
            raise UpdateError('STORAGE_PLAN_CHANGED')
        rows = self.plan[2]
        active()
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
        self.plan = None
        return dict(removed_files=removed, removed_bytes=size)


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
        size = plan['reclaimable_bytes']/(1024**2)
        detail = ('可用空间 {free:.1f} MiB；可清理更新下载缓存 {cache:.1f} MiB（{files} 个文件）。\n'
                  '当前事务/回退与旧事务保留 {kept:.1f} MiB；其中 {legacy} 个旧事务不自动删除。\n'
                  '已交付或归属不明的下载文件也保留。这里只清理可重新下载的组件缓存和断点；清理后需重新下载，无法撤销。\n'
                  '不删除程序备份、失败现场、账号、观看记录或媒体。').format(
                      free=plan['free_bytes']/1024**2,cache=size,files=plan['files'],
                      kept=plan['protected_transaction_bytes']/1024**2,legacy=plan['legacy_transactions'])
        if not plan['protected_sizes_complete']:
            detail += '\n部分目录未能完整统计，保留大小是已读下限，仍不会清理它们。'
        dialog.textviewer('存储空间 · 更新缓存与保留范围', detail)
        if not plan['files']:
            return
        active()
        if not dialog.yesno('清理更新下载缓存？',
                '移除 {:.1f} MiB（{} 个文件），之后需要时重新下载。\n'
                '程序备份、账号、观看记录和媒体不变。缓存清理无法撤销。'.format(size, plan['files'])):
            return
        active()
        result = storage.clear(plan, active=active)
        dialog.ok('更新缓存已清理', '已移除 {:.1f} MiB 可重新下载的缓存。程序、备份和账号保持不变。'.format(
            result['removed_bytes']/1024**2))

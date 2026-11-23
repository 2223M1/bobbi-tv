"""Bounded complete signed recovery packages, never account/profile snapshots.

The installation lock owns this store. Restoring still goes through the single
Installer transaction; it is not a second installer or an update downgrade.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import zipfile

from .offline_updates import SignedBundle, MAX_BUNDLE
from .updates import UpdateError, _safe_path, _atomic, _json
from .ce_storage import RESERVE

NAME = re.compile(r'([1-9][0-9]{0,18})-([a-f0-9]{64})\.zip')
KEEP = 3
PREPARATION = 'preparing.json'


def record_preparation(work, tx, sequence):
    """Call under installation.lock, before writing any staged payload."""
    if (not isinstance(tx, str) or not re.fullmatch('[a-f0-9]{32}', tx)
            or type(sequence) is not int or sequence < 1):
        raise UpdateError('PREPARATION_RECEIPT_INVALID')
    root = _safe_path(Path(work) / tx)
    if any(root.iterdir()):
        raise UpdateError('PREPARATION_RECEIPT_INVALID')
    _atomic(root / PREPARATION, dict(schema=1, tx=tx, phase='preparing', sequence=sequence))


def preparation_transaction(work, tx, state, budget=None):
    """Prove an uncommitted staging tree; names or age alone confer no ownership.

    The lock prevents installer races. A bounded identity vector additionally
    detects changed files, links, mounts and directory replacement during UI
    confirmation. Invalid/legacy trees are deliberately protected.
    """
    from .ce_storage import SCAN_FILES, SCAN_BYTES
    if (not re.fullmatch('[a-f0-9]{32}', tx) or state and
            (state.get('phase') not in ('complete', 'restored') or state.get('host_pending')
             or tx in (state.get('tx'), state.get('previous_tx')))):
        return None
    budget = budget if budget is not None else [SCAN_FILES, SCAN_BYTES]
    try:
        work = _safe_path(work)
        root = _safe_path(work / tx)
        receipt = _safe_path(root / PREPARATION)
        info = receipt.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_dev != work.stat().st_dev or info.st_size > 4096):
            return None
        value = _json(receipt.read_bytes())
        names = set()
        for child in root.iterdir():
            names.add(child.name)
            if len(names) > 4:
                return None
            if child.name != PREPARATION and not stat.S_ISDIR(child.lstat().st_mode):
                return None
        if (not isinstance(value, dict) or set(value) != {'schema', 'tx', 'phase', 'sequence'}
                or type(value['schema']) is not int or value['schema'] != 1
                or value['tx'] != tx or value['phase'] != 'preparing'
                or type(value['sequence']) is not int or value['sequence'] < 1
                or names - {PREPARATION, 'stage', 'validator', 'backup'}):
            return None
        backup = root / 'backup'
        if backup.exists() and (not backup.is_dir() or any(backup.iterdir())):
            return None
        device, rows, stack = work.stat().st_dev, {}, [root]
        while stack:
            path = _safe_path(stack.pop())
            info = path.lstat()
            budget[0] -= 1
            isdir = stat.S_ISDIR(info.st_mode)
            if (budget[0] < 0 or info.st_dev != device or not
                    (isdir or stat.S_ISREG(info.st_mode) and info.st_nlink == 1)):
                return None
            if not isdir:
                budget[1] -= info.st_size
                if budget[1] < 0:
                    return None
            rows[path.relative_to(root).as_posix()] = (
                info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if isdir:
                with os.scandir(path) as entries:
                    for entry in entries:
                        if len(stack) >= budget[0]:
                            return None
                        stack.append(Path(entry.path))
        return dict(receipt=value, entries=rows)
    except (OSError, ValueError, UpdateError):
        return None


def clear_preparation(installer, tx, proof):
    """Re-read journal even when its atomic write raised after replacement."""
    if not proof or preparation_transaction(installer.work, tx, installer._read()) != proof:
        raise UpdateError('STORAGE_PLAN_CHANGED')
    root = _safe_path(installer.work / tx)
    # Payload first; retain the receipt until cleanup completes so a crash can
    # retry. Never traverse an uninspected recursive tree with rmtree.
    names = sorted((name for name in proof['entries'] if name not in ('.', PREPARATION)),
                   key=lambda name: (name.count('/'), name), reverse=True)
    for name in names:
        path = _safe_path(root / name)
        info = path.lstat()
        expected = proof['entries'][name]
        if (info.st_dev, info.st_ino, info.st_mode) != expected[:3]:
            raise UpdateError('STORAGE_PLAN_CHANGED')
        if stat.S_ISDIR(info.st_mode):
            path.rmdir()  # Unknown late children fail closed.
        else:
            if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != expected[3:]:
                raise UpdateError('STORAGE_PLAN_CHANGED')
            path.unlink()
    if {p.name for p in root.iterdir()} != {PREPARATION}:
        raise UpdateError('STORAGE_PLAN_CHANGED')
    (root / PREPARATION).unlink()
    root.rmdir()


def clear_preparations(installer):
    """Startup/retry cleanup; caller holds installation.lock. Unknowns remain."""
    from .ce_storage import SCAN_FILES, SCAN_BYTES
    budget, removed = [SCAN_FILES, SCAN_BYTES], 0
    for count, path in enumerate(installer.work.iterdir(), 1):
        if count > SCAN_FILES or budget[0] <= 0 or budget[1] < 0:
            break
        proof = preparation_transaction(installer.work, path.name, installer._read(), budget)
        if proof:
            clear_preparation(installer, path.name, proof)
            removed += 1
    return removed


def record_transaction(installer, state):
    """Receipts only for transactions this installer completed, never adoption."""
    from .ce_installer import program_tree
    root = _safe_path(installer.work / state['tx'])
    # A crash after journal publication may have left the preparation receipt.
    # The completed journal owns this tx; it is never preparation garbage now.
    preparing = _safe_path(root / PREPARATION)
    if preparing.exists():
        preparing.unlink()
    names = {path.name for path in root.iterdir()}
    if names - {'backup', 'stage', 'validator', 'abandoned', 'complete.json'}:
        raise UpdateError('RECOVERY_TRANSACTION_UNKNOWN')
    trees = {name: program_tree(root / name) for name in sorted(names - {'complete.json'})}
    _atomic(root / 'complete.json', dict(schema=1, tx=state['tx'], sequence=state['sequence'], trees=trees))


def retired_transaction(work, tx, state):
    """No receipt, changed tree, current, previous or pending state => protected."""
    from .ce_installer import program_tree
    if (not state or state.get('phase') != 'complete' or state.get('host_pending')
            or tx in (state['tx'], state.get('previous_tx')) or not re.fullmatch('[a-f0-9]{32}', tx)):
        return None
    root = _safe_path(Path(work) / tx)
    receipt = _safe_path(root / 'complete.json')
    try:
        if receipt.stat().st_size > 8192:
            return None
        value = _json(receipt.read_bytes())
        if (not isinstance(value, dict) or set(value) != {'schema', 'tx', 'sequence', 'trees'}
                or value['schema'] != 1 or value['tx'] != tx or type(value['sequence']) is not int
                or value['sequence'] < 1 or value['sequence'] > state.get('high_watermark', 0)
                or not isinstance(value['trees'], dict) or not value['trees']
                or set(value['trees']) - {'backup', 'stage', 'validator', 'abandoned'}
                or {p.name for p in root.iterdir()} != set(value['trees']) | {'complete.json'}):
            return None
        if any(program_tree(root / name) != digest for name, digest in value['trees'].items()):
            return None
        return value
    except (OSError, ValueError, UpdateError):
        return None


class RecoveryStore:
    def __init__(self, work, trust):
        self.root, self.trust = _safe_path(Path(work) / 'recovery-v1'), trust

    def path(self, name):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise UpdateError('RECOVERY_POINT_INVALID')
        path = _safe_path(self.root / name)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= MAX_BUNDLE:
            raise UpdateError('RECOVERY_POINT_INVALID')
        return path

    def inspect(self, name):
        path = self.path(name)
        with SignedBundle(path, self.trust, 'coreelec') as signed:
            manifest = signed.check_all()
            signed.archive.fp.seek(0)
            digest = hashlib.sha256()
            for block in iter(lambda: signed.archive.fp.read(1024 * 1024), b''):
                digest.update(block)
        if name != '{}-{}.zip'.format(manifest['sequence'], digest.hexdigest()):
            raise UpdateError('RECOVERY_POINT_INVALID')
        return dict(name=name, sequence=manifest['sequence'], size=path.stat().st_size,
                    versions={r['id']: r['version'] for r in manifest['components']})

    def list(self):
        if not self.root.exists():
            return dict(points=[], unavailable=0)
        points, unavailable = [], 0
        for count, path in enumerate(self.root.iterdir(), 1):
            if count > 128:
                raise UpdateError('RECOVERY_STORE_LIMIT')
            if not NAME.fullmatch(path.name):
                continue  # Unknown and interrupted files are never GC authority.
            try:
                points.append(self.inspect(path.name))
            except (OSError, ValueError, UpdateError, zipfile.BadZipFile):
                unavailable += 1
        return dict(points=sorted(points, key=lambda row: (row['sequence'], row['name']), reverse=True),
                    unavailable=unavailable)

    def remember(self, signed, protected=()):
        """Best-effort cache, publish before pruning, preserve current + previous."""
        size = os.fstat(signed.archive.fp.fileno()).st_size
        if not 0 < size <= MAX_BUNDLE:
            raise UpdateError('RECOVERY_POINT_INVALID')
        self.root.mkdir(mode=0o700, exist_ok=True)
        if shutil.disk_usage(self.root).free < size + RESERVE:
            return dict(saved=False, reason='space')
        temporary = _safe_path(self.root / '.pending-package')
        if temporary.exists():
            info = temporary.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise UpdateError('RECOVERY_POINT_INVALID')
            temporary.unlink()  # One reserved, uncommitted copy under the install lock.
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            signed.archive.fp.seek(0)
            digest, copied = hashlib.sha256(), 0
            with os.fdopen(fd, 'wb') as target:
                for block in iter(lambda: signed.archive.fp.read(1024 * 1024), b''):
                    copied += len(block)
                    if copied > size:
                        raise UpdateError('RECOVERY_POINT_INVALID')
                    digest.update(block)
                    target.write(block)
                target.flush()
                os.fsync(target.fileno())
            if copied != size:
                raise UpdateError('RECOVERY_POINT_INVALID')
            with SignedBundle(temporary, self.trust, 'coreelec') as copy:
                if copy.check_all() != signed.manifest:
                    raise UpdateError('RECOVERY_POINT_INVALID')
            name = '{}-{}.zip'.format(signed.manifest['sequence'], digest.hexdigest())
            destination = _safe_path(self.root / name)
            if destination.exists():
                self.inspect(name)  # Do not silently replace a damaged recovery point.
            else:
                os.replace(temporary, destination)
            retained = {name, *protected}
            rows = self.list()['points']
            keep = {row['name'] for row in rows if row['name'] in retained}
            for row in rows:
                if len(keep) >= KEEP: break
                keep.add(row['name'])
            for row in rows:
                if row['name'] not in keep:
                    self.inspect(row['name'])
                    self.path(row['name']).unlink()  # Exact verified, unreferenced package only.
            return dict(saved=True, name=name)
        finally:
            temporary.unlink(missing_ok=True)


def show(installer, host, dialog):
    host.check_idle()
    listing = installer.saved_generations()
    points = listing['points']
    if not points:
        dialog.ok('暂无恢复版本', '空间足够时，更新后会保存最近三个版本。也可返回使用“恢复上一版本”。')
        return False
    rows = ['版本 {} · {:.1f} MiB'.format(row['sequence'], row['size'] / 1024**2) for row in points]
    choice = dialog.select('选择恢复版本', rows)
    if choice < 0:
        return False
    point = points[choice]
    dialog.textviewer('恢复版本说明',
        '将恢复到版本 {}，完成后需重启 Kodi。\n'
        '账号、观看记录和媒体保留，不改第三方插件与音画设置。\n'
        '有 {} 个不可用的恢复包未列出，原文件仍保留。'.format(point['sequence'], listing['unavailable']))
    if not dialog.yesno('恢复这个版本？', '仅恢复程序，个人数据保留。完成后需重启 Kodi。'):
        return False
    host.check_idle()
    installer.restore_saved(point['name'])
    return True

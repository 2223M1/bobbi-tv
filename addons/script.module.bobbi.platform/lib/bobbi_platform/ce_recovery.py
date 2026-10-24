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


def record_transaction(installer, state):
    """Receipts only for transactions this installer completed, never adoption."""
    from .ce_installer import program_tree
    root = _safe_path(installer.work / state['tx'])
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
        dialog.ok('程序恢复点', '尚无保存的完整程序包。更新成功后会尽量保留最近三个版本；原“回退上一次程序安装”仍可单独使用。')
        return False
    rows = ['版本 {} · {:.1f} MiB'.format(row['sequence'], row['size'] / 1024**2) for row in points]
    choice = dialog.select('程序恢复点 · 不回退账号与观看记录', rows)
    if choice < 0:
        return False
    point = points[choice]
    dialog.textviewer('恢复完整程序版本',
        '将整套恢复到版本 {}，保留账号、观看记录、媒体和第三方插件。\n'
        '恢复后需重启 Kodi；原皮肤及音画设置不主动改变。\n'
        '更新版本上限仍保留，旧包不会重新变成新更新。\n'
        '已有 {} 个损坏或不可读取的恢复包未列出，也未删除。'.format(point['sequence'], listing['unavailable']))
    if not dialog.yesno('恢复所选程序版本？', '仅恢复程序，不回退用户数据。完成后需重启 Kodi。'):
        return False
    host.check_idle()
    installer.restore_saved(point['name'])
    return True

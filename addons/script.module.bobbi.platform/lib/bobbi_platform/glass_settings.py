"""Liquid Glass is an explicit skin preference; no installer/startup side effects."""
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from . import ce_glass_boot as boot
from .ce_update_notice import coreelec
from .paths import ProfileBinding

SETTING = 'BobbiLiquidGlassEnabled'
GUARD_HASH = '51cc4c15f7e7d4a99f63181e26ec3f5c79e31d63186d71a0ee8dabff10c4dbd7'
PREVIOUS_HASH = '08576e40aae95c1bc37fc7c5b43ce115a6bd34b42e74ff4e6bee9930a074ee38'
EARLIER_HASH = 'b6ea905c6f5d96731f37bc474f08c423d89d7d35fa0821aaa456d71ee2f376d2'
SNAPSHOT = Path('.local/share/bobbi-glass-optin') / GUARD_HASH / 'ce_glass_boot.py'
DROP = Path('.config/system.d/kodi.service.d/86-bobbi-opt-in-glass.conf')
UNIT = ('# Bobbi TV: user-enabled stock CE optics\n[Service]\n'
        'RuntimeDirectory=bobbi-glass\nRuntimeDirectoryMode=0700\n'
        'ExecStartPre=-/usr/bin/python3 -IB /storage/' + SNAPSHOT.as_posix() +
        ' --stock-opt-in\nEnvironmentFile=-/run/bobbi-glass/loader.env\n').encode('ascii')


PREVIOUS_UNIT = UNIT.replace(GUARD_HASH.encode(), PREVIOUS_HASH.encode())
OLD_UNITS = {digest: UNIT.replace(GUARD_HASH.encode(), digest.encode()) for digest in (PREVIOUS_HASH, EARLIER_HASH)}


def _previous(path):
    return any(_matches(path, unit) for unit in OLD_UNITS.values())


def _ordinary(path):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('GLASS_PATH_CHANGED')
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('GLASS_FILE_CHANGED')


def _matches(path, content):
    _ordinary(path)
    return path.exists() and path.stat().st_size == len(content) and path.read_bytes() == content


def _place(path, content):
    """Publish complete bytes exclusively; a foreign destination is never replaced."""
    _ordinary(path)
    if _matches(path, content):
        return
    if path.exists():
        raise ValueError('GLASS_FILE_CHANGED')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _ordinary(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.link(tmp, path)
    except FileExistsError:
        if not _matches(path, content):
            raise ValueError('GLASS_FILE_CHANGED') from None
    finally:
        tmp.unlink(missing_ok=True)


class HostOptics:
    storage = Path('/storage')
    exe = Path('/usr/lib/kodi/kodi.bin')
    running = Path('/proc/self/exe')

    def __init__(self, master):
        self.master = master
        self.drop = self.storage / DROP
        self.snapshot = self.storage / SNAPSHOT

    def mapped(self):
        # Only trust our exact module in this process, not an old stats file.
        try:
            for line in Path('/proc/self/maps').read_text().splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) != 6 or 'x' not in fields[1]:
                    continue
                path = Path(fields[-1])
                if (path.name == 'libbobbi_liquid_glass.so' and
                        (path.parent == boot.RUNTIME or Path('/storage/.local/share') in path.parents)
                        and boot.sha(path) == boot.REFINED_RENDERER):
                    return True
        except OSError:
            pass
        return False

    def available(self):
        if not self.master or not coreelec():
            return False
        # An administrator's Kodi/renderer remains its own responsibility.
        if not self.exe.is_file() or not self.running.samefile(self.exe) or boot.sha(self.exe) != boot.STOCK_CE213_AMLOGIC_NG:
            return False
        _ordinary(self.drop)
        if self.drop.exists() and not (_matches(self.drop, UNIT) or _previous(self.drop)):
            return False
        for conf in self.drop.parent.glob('*.conf'):
            if conf != self.drop:
                _ordinary(conf)
                if conf.stat().st_size > 32768:
                    return False
                content = conf.read_bytes()
                if any(v in content for v in (b'LD_PRELOAD', b'bobbi-glass', b'EnvironmentFile', b'ExecStart')):
                    return False
        addons = self.storage / '.kodi/addons'
        journal = self.storage / '.kodi/userdata/addon_data/script.bobbi.start/installation.json'
        release = boot._record(journal)
        return (release is not None and release['sequence'] in boot.OPT_IN_SEQUENCES
                and boot.verified_module(self.storage / '.local/share/bobbi-private-updates/state.json',
                                         addons, self.exe, installation=journal) == addons / boot.PACKAGED_FILE)

    def mode(self):
        if not coreelec():
            return 'material'
        if self.available():
            return 'stock'  # Re-arm persistence even after disabling in this same process.
        return 'live' if self.mapped() else 'material'

    def enable(self):
        if not self.available():
            raise ValueError('GLASS_HOST_CHANGED')
        source = Path(boot.__file__)
        _ordinary(source)
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != GUARD_HASH:
            raise ValueError('GLASS_GUARD_CHANGED')
        _place(self.snapshot, data)
        if _previous(self.drop):
            self.drop.unlink()
        _place(self.drop, UNIT)  # Last step; no reload, restart or touch of other units.

    def disable(self):
        if not self.master or not coreelec():
            return
        for digest, unit in ((GUARD_HASH, UNIT), *OLD_UNITS.items()):
            if _matches(self.drop, unit):
                self.drop.unlink()
                snapshot = self.snapshot.parent.parent / digest / self.snapshot.name
                _ordinary(snapshot)
                if snapshot.exists() and boot.sha(snapshot) == digest:
                    snapshot.unlink()
                break


def refresh_owned():
    """Carry forward existing explicit consent after a signed upgrade, never enroll a new user."""
    from .paths import profile_root
    if not coreelec() or profile_root() != Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform'):
        return
    host = HostOptics(True)
    if (_previous(host.drop) and boot.opted_in(host.storage / '.kodi/userdata')
            and host.available()):
        host.enable()


def toggle(dialog, host, enabled, apply, current):
    if not current():
        return
    if enabled():
        # Always allow going back to classic. Never uninstall an external launcher.
        apply(False)
        host.disable()
        return
    mode = host.mode()
    prompt = {'stock': '这台 CoreELEC 支持实时折射。将为 Kodi 添加可撤销的启动项，不更换内核、不自动重启。重启盒子后生效；关闭此开关会移除该启动项。',
              'live': '本机已加载实时渲染器。现在启用液态玻璃？不会修改系统启动项。',
              'material': '当前环境没有可启用的实时渲染器。仅开启皮肤自带的玻璃材质，不修改系统启动项。'}
    if not dialog.yesno('开启液态玻璃？', prompt[mode]):
        return
    if not current() or enabled() or host.mode() != mode:
        return
    if mode == 'stock':
        host.enable()
    if current():
        apply(True)
    elif mode == 'stock':
        host.disable()


def show(dialog):
    import xbmc
    from .paths import profile_root
    binding = ProfileBinding()
    host = HostOptics(profile_root() == Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform'))
    def current():
        return (binding.is_current() and xbmc.getSkinDir() == 'skin.bobbi.cinema'
                and xbmc.getCondVisibility('Window.IsActive(skinsettings)'))
    toggle(dialog, host, lambda: xbmc.getCondVisibility('Skin.HasSetting(' + SETTING + ')'),
           lambda on: xbmc.executebuiltin(('Skin.SetBool(' if on else 'Skin.Reset(') + SETTING + ')', True), current)

"""Liquid Glass is an explicit skin preference; no installer/startup side effects."""
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from . import ce_glass_boot as boot, ce_glass_host as glass_host
from .ce_update_notice import coreelec
from .home_rails_meta import (
    HOME_DEFAULT_VISIBLE_SPACE_KEYS,
    HOME_OPTIONAL_SPACE_KEYS,
    HOME_RAIL_CONTROL_IDS,
    HOME_RAIL_KEYS,
    HOME_RAIL_SPECS,
    HOME_RAIL_TITLES,
    HOME_RAILS,
    HOME_SPACE_KEYS,
    HOME_SPACE_SPECS,
    HOME_SPACE_TITLES,
    HOME_SPACES,
    rail_title,
    space_title,
)
# Existing skins and scripts may still import home preferences from this module.
from .home_preferences import (
    apply_home_rail_prefs, apply_home_space_prefs, manage_home_rails, manage_home_spaces,
    normalize_rail_order, normalize_space_order, read_home_rail_prefs, read_home_space_prefs,
    reset_home_rails, reset_home_spaces, show_home_rails, show_home_spaces,
)
from .paths import ProfileBinding

SETTING = 'BobbiLiquidGlassEnabled'
GUARD_HASH = '45219e670abe3884bbc30c84a89e978ba7ece2298b028500ed4a14207673ea34'
N3R1_HASH = '2dc5b5a1063ea6f4d89348bc8dc2fd8d3fe1ae19f02909dacebe2a8cf4286e90'
CE2185_HASH = '58eb1babf11a506fde4fb7e6bfc7acfaa6c43b3e8bc607deefb0197cdb3af0b3'
PREVIOUS_HASH = '810db4ef0e4ad787cc450e651d068c0926141050bc9fdb2055cfa99f0caedff6'
CE2183_HASH = '51cc4c15f7e7d4a99f63181e26ec3f5c79e31d63186d71a0ee8dabff10c4dbd7'
LEGACY_HASH = '08576e40aae95c1bc37fc7c5b43ce115a6bd34b42e74ff4e6bee9930a074ee38'
EARLIER_HASH = 'b6ea905c6f5d96731f37bc474f08c423d89d7d35fa0821aaa456d71ee2f376d2'
SNAPSHOT = Path('.local/share/bobbi-glass-optin') / GUARD_HASH / 'ce_glass_boot.py'
DROP = Path('.config/system.d/kodi.service.d/86-bobbi-opt-in-glass.conf')
_OPT_IN_TPL = ('# Bobbi TV: user-enabled CE optics\n[Service]\n'
               'RuntimeDirectory=bobbi-glass\nRuntimeDirectoryMode=0700\n'
               'ExecStartPre=-/usr/bin/python3 -IB /storage/.local/share/bobbi-glass-optin/{}/ce_glass_boot.py'
               ' --opt-in\nEnvironmentFile=-/run/bobbi-glass/loader.env\n')
UNIT = _OPT_IN_TPL.format(GUARD_HASH).encode('ascii')
_STOCK_TPL = ('# Bobbi TV: user-enabled stock CE optics\n[Service]\n'
              'RuntimeDirectory=bobbi-glass\nRuntimeDirectoryMode=0700\n'
              'ExecStartPre=-/usr/bin/python3 -IB /storage/.local/share/bobbi-glass-optin/{}/ce_glass_boot.py'
              ' --stock-opt-in\nEnvironmentFile=-/run/bobbi-glass/loader.env\n')
OLD_UNITS = {
    N3R1_HASH: _OPT_IN_TPL.format(N3R1_HASH).encode('ascii'),
    **{d: _STOCK_TPL.format(d).encode('ascii')
       for d in (CE2185_HASH, PREVIOUS_HASH, CE2183_HASH, LEGACY_HASH, EARLIER_HASH)},
}
PREVIOUS_UNIT = OLD_UNITS[CE2185_HASH]


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
    proc_root = Path('/proc')
    lib_dirs = None
    systemctl_runner = None

    def __init__(self, master):
        self.master = master
        self.drop = self.storage / DROP
        self.snapshot = self.storage / SNAPSHOT

    def mapped(self):
        return bool(glass_host._is_renderer_mapped(self.proc_root / 'self/maps', boot.RUNTIME, self.storage))

    def inspect_dropins(self):
        return glass_host.inspect_dropins(self.storage, UNIT, OLD_UNITS)

    def qualify(self):
        addons = self.storage / '.kodi/addons'
        return glass_host.qualify_host_cached(
            self.exe, addons / boot.PACKAGED_FILE, addons=addons,
            lib_dirs=self.lib_dirs, proc_root=self.proc_root,
        )

    def available(self):
        if not self.master or not coreelec() or not self.exe.is_file() or not self.running.samefile(self.exe):
            return False
        if not self.inspect_dropins()['available']:
            return False
        addons = self.storage / '.kodi/addons'
        state = self.storage / '.local/share/bobbi-private-updates/state.json'
        journal = self.storage / '.kodi/userdata/addon_data/script.bobbi.start/installation.json'
        release = boot._release(state, journal)
        if (release is None or not journal.exists() or release.get('phase') != 'complete'
                or (release['sequence'] not in boot.OPT_IN_SEQUENCES
                    and release['sequence'] <= boot.ZIP_JUKU_CONVERGENCE)):
            return False
        with self.exe.open('rb') as handle:
            exe_magic = handle.read(4)
        if self.lib_dirs is not None or exe_magic == b'\x7fELF' or release['sequence'] > boot.ZIP_JUKU_CONVERGENCE:
            if not self.qualify()['ok']:
                return False
        return boot.verified_module(
            state, addons, self.exe, installation=journal,
            lib_dirs=self.lib_dirs, proc_root=self.proc_root,
        ) == addons / boot.PACKAGED_FILE

    def mode(self):
        if not coreelec():
            return 'material'
        return 'stock' if self.available() else ('live' if self.mapped() else 'material')

    def enable(self, *, fault_hook=None):
        if not self.available():
            raise ValueError('GLASS_HOST_CHANGED')
        source = Path(boot.__file__)
        _ordinary(source)
        return glass_host.execute_migration(
            storage=self.storage, snapshot_path=self.snapshot, guard_bytes=source.read_bytes(),
            guard_hash=GUARD_HASH, drop_86_path=self.drop, unit_bytes=UNIT,
            old_units=OLD_UNITS, place_fn=_place,
            systemctl_runner=self.systemctl_runner, fault_hook=fault_hook,
        )

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
                glass_host._bounded_daemon_reload(self.systemctl_runner)
                break

    def runtime_status(self, *, opted_in=None, now=None, pid=None, cjk=None):
        if opted_in is not None:
            user_on = bool(opted_in)
        else:
            user_on = boot.opted_in(self.storage / '.kodi/userdata')
            if not user_on:
                import sys as _sys
                xbmc_mod = _sys.modules.get('xbmc')
                get_cond = getattr(xbmc_mod, 'getCondVisibility', None) if xbmc_mod is not None else None
                get_skin = getattr(xbmc_mod, 'getSkinDir', None) if xbmc_mod is not None else None
                if callable(get_cond) and callable(get_skin) and get_skin() == 'skin.bobbi.cinema':
                    try:
                        user_on = bool(get_cond('Skin.HasSetting(' + SETTING + ')'))
                    except Exception:
                        user_on = False
        if cjk is None:
            from .i18n import current_locale
            use_cjk = current_locale() != 'en_gb'
        else:
            use_cjk = bool(cjk)
        owned_86 = self.drop.exists() and (_matches(self.drop, UNIT) or _previous(self.drop))
        return glass_host.inspect_runtime_status(
            opted_in=user_on, is_coreelec=coreelec(), host_available=self.available(),
            owned_86_present=owned_86, storage=self.storage, runtime_dir=boot.RUNTIME,
            proc_root=self.proc_root, pid=pid, now=now, cjk=use_cjk,
        )


def _is_master_profile():
    from .paths import profile_root
    try:
        return profile_root() == Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform')
    except Exception:
        return False


def sync_runtime_property(host=None, *, opted_in=None):
    """Evaluate 7-state Liquid Glass status and publish Window(Home) properties."""
    from .i18n import current_locale
    use_cjk = current_locale() != 'en_gb'
    active_host = host if host is not None else HostOptics(_is_master_profile())
    try:
        st = (active_host.runtime_status(cjk=use_cjk) if opted_in is None
              else active_host.runtime_status(opted_in=opted_in, cjk=use_cjk))
    except TypeError:
        st = active_host.runtime_status()
    try:
        import xbmcgui
        window = xbmcgui.Window(10000)
        window.setProperty('Bobbi.Glass.State', str(st['state']))
        window.setProperty('Bobbi.Glass.StateLabel', str(st['label']))
    except (ImportError, AttributeError, RuntimeError):
        pass
    return st


def runtime_summary_line(host=None):
    """Return localized single-line Liquid Glass status summary for diagnostics."""
    from .i18n import current_locale
    loc = current_locale()
    active_host = host if host is not None else HostOptics(_is_master_profile())
    try:
        st = active_host.runtime_status(cjk=(loc != 'en_gb'))
    except TypeError:
        st = active_host.runtime_status()
    prefix = 'Liquid Glass · ' if loc == 'en_gb' else '液态玻璃 · '
    return prefix + str(st['label'])


def refresh_owned():
    """Carry forward existing explicit consent after a signed upgrade, never enroll a new user."""
    from .paths import profile_root
    if not coreelec() or profile_root() != Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform'):
        return
    host = HostOptics(True)
    if _previous(host.drop) and boot.opted_in(host.storage / '.kodi/userdata') and host.available():
        host.enable()
    try:
        sync_runtime_property(host)
    except Exception:
        pass


def toggle(dialog, host, enabled, apply, current):
    if not current():
        return
    if enabled():
        apply(False)
        host.disable()
        return
    mode = host.mode()
    if not dialog.yesno(*glass_host.toggle_dialog_copy(mode)):
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
                and xbmc.getCondVisibility('Window.IsActive(skinsettings) | Window.IsActive(settings)'))
    enabled_fn = lambda: xbmc.getCondVisibility('Skin.HasSetting(' + SETTING + ')')
    toggle(dialog, host, enabled_fn,
           lambda on: xbmc.executebuiltin(('Skin.SetBool(' if on else 'Skin.Reset(') + SETTING + ')', True), current)
    try:
        sync_runtime_property(host, opted_in=bool(enabled_fn()))
    except Exception:
        pass

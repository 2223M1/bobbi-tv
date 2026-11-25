"""Liquid Glass is an explicit skin preference; no installer/startup side effects."""
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from . import ce_glass_boot as boot
from .ce_update_notice import coreelec
from .home_rails_meta import (
    HOME_RAIL_CONTROL_IDS,
    HOME_RAIL_KEYS,
    HOME_RAIL_SPECS,
    HOME_RAIL_TITLES,
    HOME_RAILS,
)
from .paths import ProfileBinding

SETTING = 'BobbiLiquidGlassEnabled'
GUARD_HASH = '58eb1babf11a506fde4fb7e6bfc7acfaa6c43b3e8bc607deefb0197cdb3af0b3'
PREVIOUS_HASH = '810db4ef0e4ad787cc450e651d068c0926141050bc9fdb2055cfa99f0caedff6'
CE2183_HASH = '51cc4c15f7e7d4a99f63181e26ec3f5c79e31d63186d71a0ee8dabff10c4dbd7'
LEGACY_HASH = '08576e40aae95c1bc37fc7c5b43ce115a6bd34b42e74ff4e6bee9930a074ee38'
EARLIER_HASH = 'b6ea905c6f5d96731f37bc474f08c423d89d7d35fa0821aaa456d71ee2f376d2'
SNAPSHOT = Path('.local/share/bobbi-glass-optin') / GUARD_HASH / 'ce_glass_boot.py'
DROP = Path('.config/system.d/kodi.service.d/86-bobbi-opt-in-glass.conf')
UNIT = ('# Bobbi TV: user-enabled stock CE optics\n[Service]\n'
        'RuntimeDirectory=bobbi-glass\nRuntimeDirectoryMode=0700\n'
        'ExecStartPre=-/usr/bin/python3 -IB /storage/' + SNAPSHOT.as_posix() +
        ' --stock-opt-in\nEnvironmentFile=-/run/bobbi-glass/loader.env\n').encode('ascii')


PREVIOUS_UNIT = UNIT.replace(GUARD_HASH.encode(), PREVIOUS_HASH.encode())
OLD_UNITS = {digest: UNIT.replace(GUARD_HASH.encode(), digest.encode())
             for digest in (PREVIOUS_HASH, CE2183_HASH, LEGACY_HASH, EARLIER_HASH)}


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


# --- Pure Home rail preference logic (decoupled from HostOptics renderer setup) ---


def _spec_index(rail_specs=HOME_RAIL_SPECS):
    keys = tuple(spec[0] for spec in rail_specs)
    titles = {spec[0]: spec[2] for spec in rail_specs}
    return keys, titles


def normalize_rail_order(raw_slots: list[str] | tuple[str, ...], *, rail_specs=HOME_RAIL_SPECS) -> list[str]:
    """Normalize arbitrary/partial slot values into an exact permutation of declared rail keys."""
    keys, titles = _spec_index(rail_specs)
    seen: list[str] = []
    for key in raw_slots:
        if isinstance(key, str) and key in titles and key not in seen:
            seen.append(key)
    for key in keys:
        if key not in seen:
            seen.append(key)
    return seen


def read_home_rail_prefs(get_bool, get_string, *, rail_specs=HOME_RAIL_SPECS) -> tuple[list[str], set[str]]:
    keys, _ = _spec_index(rail_specs)
    raw_slots = [get_string(f'BobbiRailSlot{slot}') for slot in range(1, len(keys) + 1)]
    order = normalize_rail_order(raw_slots, rail_specs=rail_specs)
    hidden = {key for key in keys if get_bool(f'BobbiHideRail_{key}')}
    return order, hidden


def apply_home_rail_prefs(order: list[str], hidden: set[str], set_bool, set_string, reset_setting,
                          *, rail_specs=HOME_RAIL_SPECS) -> None:
    """Persist validated slot order and hide flags to Skin settings only (zero XML writes)."""
    keys, _ = _spec_index(rail_specs)
    clean_order = normalize_rail_order(order, rail_specs=rail_specs)
    is_default_order = tuple(clean_order) == keys
    for idx, key in enumerate(clean_order, start=1):
        slot_name = f'BobbiRailSlot{idx}'
        if is_default_order:
            reset_setting(slot_name)
        else:
            set_string(slot_name, key)
    for key in keys:
        hide_name = f'BobbiHideRail_{key}'
        if key in hidden:
            set_bool(hide_name, True)
        else:
            reset_setting(hide_name)


def manage_home_rails(dialog, get_bool, get_string, set_bool, set_string, reset_setting,
                      is_current=lambda: True, *, rail_specs=HOME_RAIL_SPECS) -> bool:
    if not is_current():
        return False
    keys, titles = _spec_index(rail_specs)
    order, hidden = read_home_rail_prefs(get_bool, get_string, rail_specs=rail_specs)
    dirty = False
    save_requested = False
    while is_current():
        rows = []
        for idx, key in enumerate(order, start=1):
            state_lbl = '已隐藏' if key in hidden else '显示中'
            rows.append(f'{idx}. {titles[key]}  ·  {state_lbl}')
        rows.append('恢复默认顺序与全部显示')
        rows.append('完成并保存')
        pick = dialog.select('首页栏目显隐与顺序', rows)
        if pick < 0:
            break
        if pick == len(order):
            order = list(keys)
            hidden = set()
            dirty = True
            continue
        if pick == len(order) + 1:
            save_requested = True
            break
        if 0 <= pick < len(order):
            chosen_key = order[pick]
            chosen_title = titles[chosen_key]
            vis_action = '设为显示' if chosen_key in hidden else '设为隐藏'
            ops = [(vis_action, 'toggle')]
            if pick > 0:
                ops.append(('上移一位', 'up'))
            if pick + 1 < len(order):
                ops.append(('下移一位', 'down'))
            ops.append(('返回栏目列表', 'back'))
            sub = dialog.select(chosen_title, [lbl for lbl, _ in ops])
            if 0 <= sub < len(ops):
                op = ops[sub][1]
                if op == 'toggle':
                    if chosen_key in hidden:
                        hidden.discard(chosen_key)
                    else:
                        hidden.add(chosen_key)
                    dirty = True
                elif op == 'up':
                    order[pick - 1], order[pick] = order[pick], order[pick - 1]
                    dirty = True
                elif op == 'down':
                    order[pick + 1], order[pick] = order[pick], order[pick + 1]
                    dirty = True
    if save_requested and dirty and is_current():
        apply_home_rail_prefs(order, hidden, set_bool, set_string, reset_setting, rail_specs=rail_specs)
        return True
    return False


def _kodi_skin_accessors():
    import xbmc
    return (
        lambda name: bool(xbmc.getCondVisibility(f'Skin.HasSetting({name})')),
        lambda name: xbmc.getInfoLabel(f'Skin.String({name})') or '',
        lambda name, on: xbmc.executebuiltin(('Skin.SetBool(' if on else 'Skin.Reset(') + name + ')', True),
        lambda name, val: xbmc.executebuiltin(f'Skin.SetString({name},{val})', True),
        lambda name: xbmc.executebuiltin(f'Skin.Reset({name})', True),
    )


def show_home_rails(dialog):
    import xbmc
    binding = ProfileBinding()
    get_bool, get_string, set_bool, set_string, reset_setting = _kodi_skin_accessors()
    is_current = lambda: binding.is_current() and xbmc.getSkinDir() == 'skin.bobbi.cinema'
    manage_home_rails(dialog, get_bool, get_string, set_bool, set_string, reset_setting, is_current)


def reset_home_rails(dialog=None):
    import xbmc
    binding = ProfileBinding()
    if not binding.is_current() or xbmc.getSkinDir() != 'skin.bobbi.cinema':
        return False
    _, _, set_bool, set_string, reset_setting = _kodi_skin_accessors()
    apply_home_rail_prefs(list(HOME_RAIL_KEYS), set(), set_bool, set_string, reset_setting)
    if dialog is not None and hasattr(dialog, 'notification'):
        dialog.notification('波比 TV', '已恢复首页默认栏目')
    return True

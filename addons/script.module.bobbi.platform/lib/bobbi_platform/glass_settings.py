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
                      is_current=lambda: True, *, rail_specs=HOME_RAIL_SPECS, english: bool = False) -> bool:
    if not is_current():
        return False
    keys, titles = _spec_index(rail_specs)
    use_meta_titles = rail_specs is HOME_RAIL_SPECS
    order, hidden = read_home_rail_prefs(get_bool, get_string, rail_specs=rail_specs)
    dirty = False
    save_requested = False
    while is_current():
        rows = []
        for idx, key in enumerate(order, start=1):
            disp_title = rail_title(key, english=english) if use_meta_titles else titles[key]
            if english:
                state_lbl = 'Hidden' if key in hidden else 'Visible'
            else:
                state_lbl = '已隐藏' if key in hidden else '显示中'
            rows.append(f'{idx}. {disp_title}  ·  {state_lbl}')
        rows.append('Restore Default Order & Show All' if english else '恢复默认顺序与全部显示')
        rows.append('Save & Apply' if english else '完成并保存')
        pick = dialog.select('Home Rails Order & Visibility' if english else '首页栏目显隐与顺序', rows)
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
            chosen_title = rail_title(chosen_key, english=english) if use_meta_titles else titles[chosen_key]
            if english:
                vis_action = 'Show Rail' if chosen_key in hidden else 'Hide Rail'
                ops = [(vis_action, 'toggle')]
                if pick > 0:
                    ops.append(('Move Up', 'up'))
                if pick + 1 < len(order):
                    ops.append(('Move Down', 'down'))
                ops.append(('Back to Rails List', 'back'))
            else:
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
    from .power_menu import is_english_ui
    binding = ProfileBinding()
    get_bool, get_string, set_bool, set_string, reset_setting = _kodi_skin_accessors()
    is_current = lambda: binding.is_current() and xbmc.getSkinDir() == 'skin.bobbi.cinema'
    manage_home_rails(dialog, get_bool, get_string, set_bool, set_string, reset_setting,
                      is_current, english=is_english_ui(xbmc.getInfoLabel))


def reset_home_rails(dialog=None):
    import xbmc
    from .power_menu import is_english_ui
    binding = ProfileBinding()
    if not binding.is_current() or xbmc.getSkinDir() != 'skin.bobbi.cinema':
        return False
    _, _, set_bool, set_string, reset_setting = _kodi_skin_accessors()
    apply_home_rail_prefs(list(HOME_RAIL_KEYS), set(), set_bool, set_string, reset_setting)
    if dialog is not None and hasattr(dialog, 'notification'):
        if is_english_ui(xbmc.getInfoLabel):
            dialog.notification('Bobbi TV', 'Default home rails restored')
        else:
            dialog.notification('波比 TV', '已恢复首页默认栏目')
    return True


# --- Pure Navigation Spaces preference logic (1:1 algebra with Includes_HomeNav.generated.xml) ---


def _space_index(space_specs=HOME_SPACE_SPECS):
    fixed_keys = tuple(spec[0] for spec in space_specs if spec[5])
    opt_keys = tuple(spec[0] for spec in space_specs if not spec[5])
    def_vis = frozenset(spec[0] for spec in space_specs if spec[6])
    titles_zh = {spec[0]: spec[2] for spec in space_specs}
    titles_en = {spec[0]: spec[3] for spec in space_specs}
    return fixed_keys, opt_keys, def_vis, titles_zh, titles_en


def normalize_space_order(raw_slots: list[str] | tuple[str, ...], *, space_specs=HOME_SPACE_SPECS) -> list[str]:
    """Normalize optional space slot strings into ['home', *exact_optional_permutation].

    Matches Includes_HomeNav.generated.xml slot-default + deduplication + fallback algebra 1:1:
    empty or unknown slot s resolves to opt_keys[s - 1] before deduplication and canonical tail fill.
    """
    fixed_keys, opt_keys, _, _, _ = _space_index(space_specs)
    opt_set = set(opt_keys)
    resolved_raw: list[str] = []
    for idx, def_key in enumerate(opt_keys):
        val = raw_slots[idx] if idx < len(raw_slots) else ''
        resolved_raw.append(val if (isinstance(val, str) and val in opt_set) else def_key)
    seen: list[str] = []
    for key in resolved_raw:
        if key not in seen:
            seen.append(key)
    for key in opt_keys:
        if key not in seen:
            seen.append(key)
    return [*fixed_keys, *seen]


def read_home_space_prefs(get_bool, get_string, *, space_specs=HOME_SPACE_SPECS) -> tuple[list[str], set[str]]:
    """Return (full_order_including_fixed_home, visible_space_keys_set)."""
    fixed_keys, opt_keys, def_vis, _, _ = _space_index(space_specs)
    raw_slots = [get_string(f'BobbiSpaceSlot{slot}') for slot in range(1, len(opt_keys) + 1)]
    order = normalize_space_order(raw_slots, space_specs=space_specs)
    visible: set[str] = set(fixed_keys)
    for key in opt_keys:
        if key in def_vis:
            if not get_bool(f'BobbiHideSpace_{key}'):
                visible.add(key)
        else:
            if get_bool(f'BobbiShowSpace_{key}'):
                visible.add(key)
    return order, visible


def apply_home_space_prefs(order: list[str], visible: set[str], set_bool, set_string, reset_setting,
                           *, space_specs=HOME_SPACE_SPECS) -> None:
    """Persist validated optional space slots & hide/show booleans to Skin settings only (zero XML writes)."""
    fixed_keys, opt_keys, def_vis, _, _ = _space_index(space_specs)
    opt_only = [k for k in order if k not in fixed_keys]
    clean_full = normalize_space_order(opt_only, space_specs=space_specs)
    clean_opt = clean_full[len(fixed_keys):]
    is_default_order = tuple(clean_opt) == opt_keys
    for idx, key in enumerate(clean_opt, start=1):
        slot_name = f'BobbiSpaceSlot{idx}'
        if is_default_order:
            reset_setting(slot_name)
        else:
            set_string(slot_name, key)
    for key in opt_keys:
        hide_name = f'BobbiHideSpace_{key}'
        show_name = f'BobbiShowSpace_{key}'
        is_vis = key in visible
        if key in def_vis:
            reset_setting(show_name)
            if is_vis:
                reset_setting(hide_name)
            else:
                set_bool(hide_name, True)
        else:
            reset_setting(hide_name)
            if is_vis:
                set_bool(show_name, True)
            else:
                reset_setting(show_name)


def manage_home_spaces(dialog, get_bool, get_string, set_bool, set_string, reset_setting,
                       is_current=lambda: True, *, space_specs=HOME_SPACE_SPECS, english: bool = False) -> bool:
    if not is_current():
        return False
    fixed_keys, opt_keys, def_vis, titles_zh, titles_en = _space_index(space_specs)
    titles = titles_en if english else titles_zh
    order, visible = read_home_space_prefs(get_bool, get_string, space_specs=space_specs)
    dirty = False
    save_requested = False
    n_fixed = len(fixed_keys)
    while is_current():
        rows = []
        for idx, key in enumerate(order, start=1):
            if key in fixed_keys:
                state_lbl = 'Always Visible (Pinned)' if english else '固定在首位'
            elif english:
                state_lbl = 'Visible' if key in visible else 'Hidden'
            else:
                state_lbl = '显示中' if key in visible else '未启用'
            rows.append(f'{idx}. {titles[key]}  ·  {state_lbl}')
        rows.append('Restore Default Spaces & Order' if english else '恢复默认空间与顺序')
        rows.append('Save & Apply' if english else '完成并保存')
        pick = dialog.select('Manage Navigation Spaces' if english else '导航栏空间管理（增减与排序）', rows)
        if pick < 0:
            break
        if pick == len(order):
            order = [*fixed_keys, *opt_keys]
            visible = set(fixed_keys) | set(def_vis)
            dirty = True
            continue
        if pick == len(order) + 1:
            save_requested = True
            break
        if 0 <= pick < n_fixed:
            if hasattr(dialog, 'ok'):
                if english:
                    dialog.ok('Pinned Space', 'Home is always pinned first so you never lose your primary entry point.')
                else:
                    dialog.ok('固定空间', '“首页”固定在第一位显示，不可隐藏或移动，确保始终可返回主页。')
            continue
        if n_fixed <= pick < len(order):
            chosen_key = order[pick]
            chosen_title = titles[chosen_key]
            is_vis = chosen_key in visible
            if english:
                vis_action = 'Hide from Navigation' if is_vis else 'Add to Navigation'
                ops = [(vis_action, 'toggle')]
                if pick > n_fixed:
                    ops.append(('Move Up', 'up'))
                if pick + 1 < len(order):
                    ops.append(('Move Down', 'down'))
                ops.append(('Back to Spaces List', 'back'))
            else:
                vis_action = '从导航栏隐藏' if is_vis else '添加到导航栏'
                ops = [(vis_action, 'toggle')]
                if pick > n_fixed:
                    ops.append(('上移一位', 'up'))
                if pick + 1 < len(order):
                    ops.append(('下移一位', 'down'))
                ops.append(('返回空间列表', 'back'))
            sub = dialog.select(chosen_title, [lbl for lbl, _ in ops])
            if 0 <= sub < len(ops):
                op = ops[sub][1]
                if op == 'toggle':
                    if is_vis:
                        visible.discard(chosen_key)
                    else:
                        visible.add(chosen_key)
                    dirty = True
                elif op == 'up':
                    order[pick - 1], order[pick] = order[pick], order[pick - 1]
                    dirty = True
                elif op == 'down':
                    order[pick + 1], order[pick] = order[pick], order[pick + 1]
                    dirty = True
    if save_requested and dirty and is_current():
        apply_home_space_prefs(order, visible, set_bool, set_string, reset_setting, space_specs=space_specs)
        return True
    return False


def show_home_spaces(dialog):
    import xbmc
    import xbmcgui
    from .power_menu import is_english_ui
    binding = ProfileBinding()
    get_bool, get_string, set_bool, set_string, reset_setting = _kodi_skin_accessors()
    is_current = lambda: binding.is_current() and xbmc.getSkinDir() == 'skin.bobbi.cinema'
    changed = manage_home_spaces(
        dialog, get_bool, get_string, set_bool, set_string, reset_setting,
        is_current, english=is_english_ui(xbmc.getInfoLabel),
    )
    if changed and is_current():
        _, visible = read_home_space_prefs(get_bool, get_string)
        active_section = (xbmcgui.Window(10000).getProperty('BobbiSection') or '').strip()
        if active_section and active_section not in visible and not xbmc.getCondVisibility('Window.IsActive(home)'):
            xbmcgui.Window(10000).setProperty('BobbiSection', 'home')
            xbmc.executebuiltin('ActivateWindow(Home)')
    return changed


def reset_home_spaces(dialog=None):
    import xbmc
    from .power_menu import is_english_ui
    binding = ProfileBinding()
    if not binding.is_current() or xbmc.getSkinDir() != 'skin.bobbi.cinema':
        return False
    _, _, set_bool, set_string, reset_setting = _kodi_skin_accessors()
    apply_home_space_prefs(
        list(HOME_SPACE_KEYS),
        set(HOME_DEFAULT_VISIBLE_SPACE_KEYS) | {'home'},
        set_bool, set_string, reset_setting,
    )
    if dialog is not None and hasattr(dialog, 'notification'):
        if is_english_ui(xbmc.getInfoLabel):
            dialog.notification('Bobbi TV', 'Default navigation spaces restored')
        else:
            dialog.notification('波比 TV', '已恢复默认导航空间')
    return True

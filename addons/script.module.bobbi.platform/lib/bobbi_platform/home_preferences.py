"""Profile-scoped Kodi home rows and navigation. Never loads the optical renderer."""
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


def _save_current(apply, order, flags, writers, is_current, **specs):
    # Skin settings are Kodi built-ins, not a transaction. Recheck before each
    # write so a profile change during a batch cannot apply the remaining keys to the next profile.
    class ContextChanged(Exception):
        pass
    def bound(writer):
        def write(*args):
            if not is_current():
                raise ContextChanged
            writer(*args)
        return write
    try:
        apply(order, flags, *(bound(w) for w in writers), **specs)
    except ContextChanged:
        return False
    return is_current()


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
        return _save_current(apply_home_rail_prefs, order, hidden, (set_bool, set_string, reset_setting), is_current, rail_specs=rail_specs)
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
    if not _save_current(apply_home_rail_prefs, list(HOME_RAIL_KEYS), set(), (set_bool, set_string, reset_setting),
                         lambda: binding.is_current() and xbmc.getSkinDir() == 'skin.bobbi.cinema'):
        return False
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
        return _save_current(apply_home_space_prefs, order, visible, (set_bool, set_string, reset_setting), is_current, space_specs=space_specs)
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
    if not _save_current(apply_home_space_prefs, list(HOME_SPACE_KEYS), set(HOME_DEFAULT_VISIBLE_SPACE_KEYS) | {'home'},
                         (set_bool, set_string, reset_setting),
                         lambda: binding.is_current() and xbmc.getSkinDir() == 'skin.bobbi.cinema'):
        return False
    if dialog is not None and hasattr(dialog, 'notification'):
        if is_english_ui(xbmc.getInfoLabel):
            dialog.notification('Bobbi TV', 'Default navigation spaces restored')
        else:
            dialog.notification('波比 TV', '已恢复默认导航空间')
    return True

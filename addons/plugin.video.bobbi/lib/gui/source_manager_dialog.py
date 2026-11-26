import os
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon
import xbmcgui

from lib.db.cached import cache
from lib.utils.kodi.settings import get_setting
from lib.utils.kodi.utils import (
    ADDON_PATH,
    clear_cached_settings,
    kodilog,
    set_cached_setting_property,
    translation,
)
from lib.utils.source_manager import (
    BUILTIN_SOURCE_SETTINGS,
    persist_source_selection,
    reconcile_source_selection,
)
from lib.utils.user_sources import (
    DEFAULT_SOURCE_SPECS,
    add_custom_torznab_source,
    enable_all_jackett_indexers,
    load_user_sources,
    remove_custom_torznab_source,
    resolve_profile_root,
    restore_all_defaults,
    set_default_removed,
    toggle_jackett_indexer,
    update_custom_torznab_source,
)

NAVIGATED = "NAVIGATED"
CHANGED = "CHANGED"
CANCELLED = "CANCELLED"


def _is_en() -> bool:
    try:
        from bobbi_platform.i18n import is_english

        return bool(is_english())
    except Exception:
        return False


def _t(po_id, zh_text: str, en_text: str) -> str:
    if po_id is not None:
        try:
            from bobbi_platform.i18n import addon_po_string

            resolved = addon_po_string("plugin.video.bobbi", int(po_id))
            if resolved:
                return resolved
        except Exception:
            pass
    return en_text if _is_en() else zh_text


def _read_setting_str(key: str, default: str = "", profile_root=None) -> str:
    root = resolve_profile_root(profile_root)
    if root is not None:
        xml_path = root / "settings.xml"
        if xml_path.is_file():
            try:
                tree = ET.parse(xml_path).getroot()
                for item in tree.iter("setting"):
                    if item.get("id") == key:
                        return (item.text or "").strip()
            except Exception:
                pass
    try:
        val = xbmcaddon.Addon("plugin.video.bobbi").getSetting(key)
        if val is not None and str(val) != "":
            return str(val).strip()
    except Exception:
        pass
    try:
        val = get_setting(key, default)
        if isinstance(val, bool):
            return "true" if val else "false"
        return str(val if val is not None else default).strip()
    except Exception:
        return default


def _read_setting_bool(key: str, default: bool = True, profile_root=None) -> bool:
    raw = _read_setting_str(key, "", profile_root=profile_root)
    if raw.lower() in ("true", "1"):
        return True
    if raw.lower() in ("false", "0"):
        return False
    try:
        val = get_setting(key, default)
        return bool(val)
    except Exception:
        return default


def _write_setting(key: str, value: str, profile_root=None) -> None:
    str_val = str(value)
    try:
        xbmcaddon.Addon("plugin.video.bobbi").setSetting(key, str_val)
    except Exception:
        pass
    try:
        set_cached_setting_property(key, str_val)
    except Exception:
        try:
            clear_cached_settings()
        except Exception:
            pass
    root = resolve_profile_root(profile_root)
    if root is not None:
        xml_path = root / "settings.xml"
        if xml_path.is_file():
            try:
                tree = ET.parse(xml_path)
                root_el = tree.getroot()
                found = False
                for item in root_el.iter("setting"):
                    if item.get("id") == key:
                        item.text = str_val
                        found = True
                        break
                if not found:
                    el = ET.SubElement(root_el, "setting", {"id": key})
                    el.text = str_val
                tree.write(xml_path, encoding="utf-8", xml_declaration=True)
            except Exception:
                pass


def _get_icon_path(name):
    icon_name = f"{name.lower()}.png"
    media_path = os.path.join(ADDON_PATH, "resources", "media", icon_name)
    if os.path.exists(media_path):
        return media_path
    img_path = os.path.join(ADDON_PATH, "resources", "img", icon_name)
    if os.path.exists(img_path):
        return img_path
    return os.path.join(ADDON_PATH, "icon.png")


def _load_stremio_addons():
    """Import and return the Stremio addon selector, or None on failure."""
    try:
        from lib.clients.stremio.helpers import get_selected_stream_addons

        return get_selected_stream_addons
    except Exception as e:
        kodilog(f"Failed to import get_selected_stream_addons: {e}")
        return None


def _load_nuvio_addons():
    """Import and return the Nuvio-specific addon selector, or None on failure."""
    try:
        from lib.clients.nuvio.helpers import get_selected_stream_addon_records

        return get_selected_stream_addon_records
    except Exception as e:
        kodilog(f"Failed to import Nuvio addon selector: {e}")
        return None


def _add_stremio_sources(items, cache_keys, get_selected_stream_addons):
    """Append enabled Stremio addon entries to items/cache_keys."""
    if get_selected_stream_addons is None:
        return
    try:
        addons = get_selected_stream_addons()
        for addon in addons:
            key = f"Stremio:{addon.key()}"
            addon_name = addon.manifest.name
            addon_icon_path = _get_icon_path(addon_name)
            li_addon = xbmcgui.ListItem(label=addon_name)
            li_addon.setArt({"icon": addon_icon_path})
            items.append(li_addon)
            cache_keys.append(key)
    except Exception as e:
        kodilog(f"Error loading Stremio addons: {e}")


def _add_nuvio_sources(items, cache_keys, get_selected_stream_addons):
    if get_selected_stream_addons is None:
        return
    try:
        for addon in get_selected_stream_addons():
            if not isinstance(addon, dict) or not addon.get("key"):
                continue
            key = f"Nuvio:{addon['key']}"
            addon_name = addon.get("name") or "Nuvio Addon"
            li_addon = xbmcgui.ListItem(label=f"Nuvio: {addon_name}")
            li_addon.setArt({"icon": _get_icon_path(addon_name)})
            items.append(li_addon)
            cache_keys.append(key)
    except Exception as e:
        kodilog(f"Error loading Nuvio addons: {e}")


def _build_source_items():
    """Return (ListItem list, cache key list) for enabled sources."""
    get_selected_stream_addons = _load_stremio_addons()
    get_selected_nuvio_stream_addon_records = _load_nuvio_addons()
    items = []
    cache_keys = []

    for setting_key, display_name in BUILTIN_SOURCE_SETTINGS:
        if not get_setting(setting_key):
            continue

        if setting_key == "external_scraper_enabled":
            module_name = get_setting("external_scraper_module_name")
            if module_name:
                display_name = str(module_name)

        if setting_key == "stremio_enabled":
            _add_stremio_sources(items, cache_keys, get_selected_stream_addons)
            continue

        if setting_key == "nuvio_enabled":
            _add_nuvio_sources(items, cache_keys, get_selected_nuvio_stream_addon_records)
            continue

        icon_path = _get_icon_path(display_name)
        li = xbmcgui.ListItem(label=display_name)
        li.setArt({"icon": icon_path})
        items.append(li)
        cache_keys.append(display_name)

    return items, cache_keys


def _resolve_selection(cache_keys):
    return reconcile_source_selection(cache_keys, cache_backend=cache)


def _persist_selection(selected, cache_keys):
    """Save the user's selection and the set of known source keys."""
    persist_source_selection(selected, cache_keys, cache_backend=cache)


def open_source_manager_dialog():
    items, cache_keys = _build_source_items()
    if not items:
        xbmcgui.Dialog().notification("bobbi TV", translation(90756))
        return

    current_selection = _resolve_selection(cache_keys)
    preselect = [i for i, key in enumerate(cache_keys) if key in current_selection]

    result = xbmcgui.Dialog().multiselect(
        translation(90755),
        items,
        preselect=preselect,
        useDetails=True,
    )

    if result is None:
        return

    selected = [cache_keys[i] for i in result]
    _persist_selection(selected, cache_keys)


def _manage_default_sources(dialog, *, profile_root=None) -> str:
    outcome = CANCELLED
    while True:
        prefs = load_user_sources(profile_root)
        removed = set(prefs.get("removed_defaults") or ())
        options = []
        for source_id, zh_name, en_name, setting_key in DEFAULT_SOURCE_SPECS:
            label_name = en_name if _is_en() else zh_name
            if source_id in removed:
                status = _t(91649, "已移除", "Removed")
            elif setting_key and not _read_setting_bool(setting_key, default=True, profile_root=profile_root):
                status = _t(91650, "未启用", "Disabled")
            else:
                status = _t(91648, "启用中", "Active")
            options.append(f"{label_name} · {status}")
        options.append(_t(91647, "恢复全部默认源", "Restore All Default Sources"))

        choice = dialog.select(
            _t(91642, "默认源管理（启用 / 移除 / 恢复默认源）", "1. Default Sources (Toggle / Remove / Restore)"),
            options,
        )
        if choice < 0 or choice >= len(options):
            return outcome
        if choice == len(DEFAULT_SOURCE_SPECS):
            restore_all_defaults(profile_root=profile_root)
            outcome = CHANGED
            if hasattr(dialog, "notification"):
                dialog.notification("bobbi TV", _t(91656, "已恢复全部默认源", "Default sources restored"))
            continue

        source_id, _, _, setting_key = DEFAULT_SOURCE_SPECS[choice]
        is_currently_removed = source_id in removed
        is_setting_disabled = bool(
            setting_key and not _read_setting_bool(setting_key, default=True, profile_root=profile_root)
        )
        if is_currently_removed or is_setting_disabled:
            set_default_removed(source_id, False, profile_root=profile_root)
            if setting_key:
                _write_setting(setting_key, "true", profile_root=profile_root)
        else:
            set_default_removed(source_id, True, profile_root=profile_root)
            if setting_key:
                _write_setting(setting_key, "false", profile_root=profile_root)
        outcome = CHANGED


def _manage_jackett_subindexers(dialog, *, profile_root=None, discover_fn=None) -> str:
    from lib.clients.jackett import discover_jackett_indexers

    discover = discover_fn or discover_jackett_indexers
    host = _read_setting_str("jackett_host", "", profile_root=profile_root)
    port = _read_setting_str("jackett_port", "9117", profile_root=profile_root)
    apikey = _read_setting_str("jackett_apikey", "", profile_root=profile_root)
    discovered = []
    if host and apikey:
        try:
            discovered = list(discover(host, port, apikey))
        except Exception as exc:
            kodilog(f"Jackett sub-indexer discovery failed: {exc}")

    outcome = CANCELLED
    while True:
        prefs = load_user_sources(profile_root)
        disabled = list(prefs.get("disabled_jackett_indexers") or ())
        disabled_set = set(disabled)

        merged = []
        seen = set()
        for row in discovered:
            idx_id = str(row.get("id") or "").strip()
            if idx_id and idx_id not in seen:
                seen.add(idx_id)
                merged.append((idx_id, str(row.get("title") or idx_id).strip() or idx_id))
        for idx_id in disabled:
            if idx_id not in seen:
                seen.add(idx_id)
                merged.append((idx_id, idx_id))

        options = []
        actions = []
        for idx_id, title in merged:
            state = _t(91650, "已停用", "Disabled") if idx_id in disabled_set else _t(91648, "启用中", "Active")
            display = f"{title} ({idx_id})" if title != idx_id else idx_id
            options.append(f"{display} · {state}")
            actions.append(("toggle", idx_id))

        options.append(_t(None, "手动输入子站点 ID 停用 / 恢复", "Enter Sub-Indexer ID Manually"))
        actions.append(("manual", None))
        if disabled:
            options.append(_t(None, "恢复全部已停用子站点", "Re-enable All Disabled Sub-Indexers"))
            actions.append(("restore_all", None))

        choice = dialog.select(
            _t(91643, "Jackett 子站点管理（按站点开关 / 移除失效源）", "2. Jackett Sub-Indexers (Toggle / Disable Sites)"),
            options,
        )
        if choice < 0 or choice >= len(actions):
            return outcome

        kind, target_id = actions[choice]
        if kind == "toggle":
            toggle_jackett_indexer(target_id, profile_root=profile_root)
            outcome = CHANGED
        elif kind == "manual":
            entered = dialog.input(_t(None, "输入 Jackett 子站点 ID（如 nyaasi / dmhy）", "Enter Jackett Sub-Indexer ID (e.g. nyaasi / dmhy)")).strip()
            if not entered:
                continue
            try:
                toggle_jackett_indexer(entered, profile_root=profile_root)
                outcome = CHANGED
            except ValueError:
                dialog.ok(
                    _t(None, "子站点 ID 格式无效", "Invalid Sub-Indexer ID"),
                    _t(None, "仅支持字母、数字、下划线或连字符。", "Only letters, digits, underscores, and hyphens are allowed."),
                )
        elif kind == "restore_all":
            enable_all_jackett_indexers(profile_root=profile_root)
            outcome = CHANGED


def _configure_indexer_service(dialog, prefix: str, label_name: str, default_port: str, *, profile_root=None) -> bool:
    cur_host = _read_setting_str(f"{prefix}_host", "", profile_root=profile_root)
    cur_port = _read_setting_str(f"{prefix}_port", default_port, profile_root=profile_root)
    cur_key = _read_setting_str(f"{prefix}_apikey", "", profile_root=profile_root)

    host = dialog.input(
        _t(None, f"{label_name} 地址（如 http://192.168.1.10）", f"{label_name} Host URL (e.g. http://192.168.1.10)"),
        cur_host,
    ).strip()
    if not host:
        return False
    port = dialog.input(
        _t(None, f"{label_name} 端口", f"{label_name} Port"),
        cur_port or default_port,
    ).strip()
    apikey = dialog.input(
        _t(None, f"{label_name} API Key", f"{label_name} API Key"),
        cur_key,
    ).strip()
    _write_setting(f"{prefix}_host", host, profile_root=profile_root)
    if port:
        _write_setting(f"{prefix}_port", port, profile_root=profile_root)
    _write_setting(f"{prefix}_apikey", apikey, profile_root=profile_root)
    _write_setting(f"{prefix}_enabled", "true", profile_root=profile_root)
    set_default_removed(prefix, False, profile_root=profile_root)
    return True


def _edit_existing_custom_torznab(dialog, entry: dict, *, profile_root=None) -> bool:
    state_action = (
        _t(None, "停用此自定义源", "Disable Custom Source")
        if entry.get("enabled", True)
        else _t(None, "启用此自定义源", "Enable Custom Source")
    )
    sub = dialog.select(
        entry["name"],
        [
            state_action,
            _t(None, "编辑名称 / 地址 / API Key", "Edit Name / URL / API Key"),
            _t(None, "删除此自定义源", "Delete Custom Source"),
        ],
    )
    if sub == 0:
        update_custom_torznab_source(
            entry["id"],
            enabled=not entry.get("enabled", True),
            profile_root=profile_root,
        )
        return True
    if sub == 1:
        name = dialog.input(_t(None, "自定义源名称", "Custom Source Name"), entry["name"]).strip()
        if not name:
            return False
        url = dialog.input(_t(None, "Torznab 接口地址（http/https）", "Torznab Endpoint URL (http/https)"), entry["url"]).strip()
        if not url:
            return False
        apikey = dialog.input(_t(None, "API Key（可留空）", "API Key (optional)"), entry.get("apikey", "")).strip()
        try:
            update_custom_torznab_source(
                entry["id"],
                name=name,
                url=url,
                apikey=apikey,
                profile_root=profile_root,
            )
            return True
        except ValueError:
            dialog.ok(
                _t(None, "无法保存自定义源", "Could Not Save Custom Source"),
                _t(None, "请填写有效的 HTTP 或 HTTPS Torznab 地址。", "Enter a valid HTTP or HTTPS Torznab URL."),
            )
            return False
    if sub == 2:
        return remove_custom_torznab_source(entry["id"], profile_root=profile_root)
    return False


def _manage_custom_sources(dialog, *, profile_root=None) -> str:
    outcome = CANCELLED
    while True:
        prefs = load_user_sources(profile_root)
        custom_list = list(prefs.get("custom_torznab_sources") or ())
        options = []
        actions = []

        for entry in custom_list:
            state = _t(91648, "启用中", "Active") if entry.get("enabled", True) else _t(91650, "已停用", "Disabled")
            options.append(f"[Torznab] {entry['name']} · {state}")
            actions.append(("custom_entry", entry))

        options.extend(
            [
                _t(91651, "添加自定义 Torznab 源", "Add Custom Torznab Source"),
                _t(91654, "添加自定义 Stremio 插件源 URL", "Add Custom Stremio Addon URL"),
                _t(91655, "移除自定义 Stremio 插件源", "Remove Custom Stremio Addon"),
                _t(91652, "配置 Jackett 地址与 API Key", "Configure Jackett Host & API Key"),
                _t(91653, "配置 Prowlarr 地址与 API Key", "Configure Prowlarr Host & API Key"),
            ]
        )
        actions.extend(
            [
                ("add_torznab", None),
                ("stremio_add", None),
                ("stremio_remove", None),
                ("cfg_jackett", None),
                ("cfg_prowlarr", None),
            ]
        )

        choice = dialog.select(
            _t(91644, "自定义检索源（添加 / 编辑 / 删除 Torznab 或 Stremio 源）", "3. Custom Search Sources (Add / Edit / Delete)"),
            options,
        )
        if choice < 0 or choice >= len(actions):
            return outcome

        kind, payload = actions[choice]
        if kind == "custom_entry":
            if _edit_existing_custom_torznab(dialog, payload, profile_root=profile_root):
                outcome = CHANGED
        elif kind == "add_torznab":
            name = dialog.input(_t(None, "自定义源名称（如 Mikan / 私有站）", "Custom Source Name (e.g. Mikan / Private Tracker)")).strip()
            if not name:
                continue
            url = dialog.input(_t(None, "Torznab 接口地址（http/https）", "Torznab Endpoint URL (http/https)")).strip()
            if not url:
                continue
            apikey = dialog.input(_t(None, "API Key（可留空）", "API Key (optional)")).strip()
            try:
                add_custom_torznab_source(name, url, apikey, profile_root=profile_root)
                outcome = CHANGED
            except ValueError as err:
                msg = (
                    _t(None, "最多支持添加 16 个自定义 Torznab 源。", "Up to 16 custom Torznab sources are supported.")
                    if "MAX_CUSTOM_TORZNAB_REACHED" in str(err)
                    else _t(None, "请填写有效的 HTTP 或 HTTPS Torznab 地址。", "Enter a valid HTTP or HTTPS Torznab URL.")
                )
                dialog.ok(_t(None, "无法添加自定义源", "Could Not Add Custom Source"), msg)
        elif kind == "stremio_add":
            xbmc.executebuiltin("RunPlugin(plugin://plugin.video.bobbi/?action=add_custom_stremio_addon)")
            return NAVIGATED
        elif kind == "stremio_remove":
            xbmc.executebuiltin("RunPlugin(plugin://plugin.video.bobbi/?action=remove_custom_stremio_addon)")
            return NAVIGATED
        elif kind == "cfg_jackett":
            if _configure_indexer_service(dialog, "jackett", "Jackett", "9117", profile_root=profile_root):
                outcome = CHANGED
        elif kind == "cfg_prowlarr":
            if _configure_indexer_service(dialog, "prowlarr", "Prowlarr", "9696", profile_root=profile_root):
                outcome = CHANGED


def _manage_libraries_jump(dialog) -> str:
    choice = dialog.select(
        _t(91645, "片源库与聚合源（片源库网址 / T4 / 媒体服 / 网盘）", "4. Source Libraries & Servers (URL / T4 / Media Server / Cloud)"),
        [
            _t(None, "片源库网址管理", "Source Library URLs"),
            _t(None, "聚合源（T4）与本地网络片库", "T4 Aggregated Sources & Network Libraries"),
            _t(None, "账号与片源中心（网盘 / 媒体服 / 服务）", "Accounts & Sources Center (Cloud / Servers / Services)"),
        ],
    )
    if choice == 0:
        from bobbi_platform import source_libraries, source_library_ui
        from bobbi_platform.libraries import Registry
        from bobbi_platform.paths import profile

        source_store = source_libraries.capture()
        current_src = source_store.current()
        reg = Registry(profile("script.module.bobbi.platform") / "libraries.sqlite3")
        try:
            changed = (
                source_library_ui.manage(dialog, reg, current_src)
                if current_src is not None
                else source_library_ui.add(dialog, reg, source_store=source_store)
            )
            return CHANGED if changed else CANCELLED
        finally:
            reg.close()
    if choice == 1:
        xbmc.executebuiltin('ActivateWindow(Videos,"plugin://plugin.video.bobbi.library/?action=manage",return)')
        return NAVIGATED
    if choice == 2:
        xbmc.executebuiltin("RunScript(script.bobbi.setup,accounts)")
        return NAVIGATED
    return CANCELLED


def open_unified_sources_hub(dialog=None, *, profile_root=None, discover_fn=None) -> str:
    dialog = dialog or xbmcgui.Dialog()
    outcome = CANCELLED
    while True:
        choice = dialog.select(
            _t(91641, "检索源管理中心", "Search Sources Hub"),
            [
                _t(91642, "1. 默认源管理（启用 / 移除 / 恢复默认源）", "1. Default Sources (Toggle / Remove / Restore)"),
                _t(91643, "2. Jackett 子站点管理（按站点开关 / 移除失效源）", "2. Jackett Sub-Indexers (Toggle / Disable Sites)"),
                _t(91644, "3. 自定义检索源（添加 / 编辑 / 删除 Torznab 或 Stremio 源）", "3. Custom Search Sources (Add / Edit / Delete)"),
                _t(91645, "4. 片源库与聚合源（片源库网址 / T4 / 媒体服 / 网盘）", "4. Source Libraries & Servers (URL / T4 / Media Server / Cloud)"),
                _t(91646, "5. 快速多选已启用插件源", "5. Quick Multi-select Active Scrapers"),
            ],
        )
        if choice < 0:
            return outcome
        if choice == 0:
            sub = _manage_default_sources(dialog, profile_root=profile_root)
        elif choice == 1:
            sub = _manage_jackett_subindexers(dialog, profile_root=profile_root, discover_fn=discover_fn)
        elif choice == 2:
            sub = _manage_custom_sources(dialog, profile_root=profile_root)
        elif choice == 3:
            sub = _manage_libraries_jump(dialog)
        elif choice == 4:
            open_source_manager_dialog()
            sub = CHANGED
        else:
            return outcome

        if sub == NAVIGATED:
            return NAVIGATED
        if sub == CHANGED:
            outcome = CHANGED

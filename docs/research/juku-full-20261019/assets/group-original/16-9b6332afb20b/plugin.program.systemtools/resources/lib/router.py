# -*- coding: utf-8 -*-
"""URL Router and Menu Dispatcher for Kodi System Tools.

A skin-independent UI architecture:
Uses Kodi's native detailed selection dialog (`xbmcgui.Dialog().select(useDetails=True)`),
which is rendered directly by Kodi's core C++ engine. This completely decouples the
toolbox UI from any skin's `MyPrograms.xml` media window, guaranteeing reliable,
high-compatibility rendering across all third-party skins and embedded hardware.

Handles both container-backed launches (`handle >= 0`, where the container is safely
closed via `endOfDirectory(succeeded=False)` to prevent spinning indicators) and
container-free launches (`handle < 0`, such as from favourites or skin shortcuts).
"""

import sys
import traceback
import urllib.parse
from typing import Dict, List, Tuple

from .common.kodi_ui import (
    dialog_select_details,
    dialog_textviewer,
    get_addon,
    get_string,
    show_notification,
)
from .common.logger import debug, error, info
from .common.os_detect import get_system_info
from .tools import ToolRegistry

try:
    import xbmcgui
    import xbmcplugin
    _HAS_XBMC = True
except ImportError:
    _HAS_XBMC = False
    xbmcgui = None
    xbmcplugin = None


EXIT_ACTION = "__exit__"
ABOUT_ACTION = "about"


def parse_params(param_string: str) -> Dict[str, str]:
    """Parse query string '?key=val&...' into a dictionary."""
    if not param_string:
        return {}
    if param_string.startswith("?"):
        param_string = param_string[1:]
    parsed = urllib.parse.parse_qs(param_string)
    return {k: v[0] for k, v in parsed.items()}


def close_container(handle: int) -> None:
    """Close a plugin container we are not going to fill with directory items.

    Every plugin directory that received a real handle must be closed with
    endOfDirectory(), otherwise the media window keeps showing its "working"
    spinner forever. succeeded=False tells Kodi the listing is empty on
    purpose and makes the media window step back cleanly.
    """
    if handle is None or handle < 0 or not (_HAS_XBMC and xbmcplugin):
        return
    try:
        xbmcplugin.endOfDirectory(handle, succeeded=False, updateListing=False, cacheToDisc=False)
        info(f"Closed unused container handle {handle} (succeeded=False)")
    except Exception as e:
        debug(f"endOfDirectory({handle}) failed: {e}")


def menu_entries() -> List[Tuple[str, str, str, str]]:
    """Return the toolbox menu as (action, label, description, icon) tuples."""
    entries = []
    for tool_cls in ToolRegistry.get_all():
        entries.append((
            tool_cls.get_id(),
            get_string(tool_cls.get_title_id()),
            get_string(tool_cls.get_description_id()),
            tool_cls.get_icon(),
        ))
    entries.append((
        ABOUT_ACTION,
        get_string(30006, "System Information"),
        get_string(30022, "Add-on, platform and hardware information"),
        "DefaultAddonInfo.png",
    ))
    return entries


def run_tool(action: str) -> None:
    """Dispatch a tool action and report failures instead of dying silently."""
    info(f"Dispatching action '{action}'")
    try:
        if not ToolRegistry.dispatch(action, {}):
            error(f"Unknown action requested: {action}")
            show_notification(
                get_string(30000, "System Tools"),
                get_string(30020, "Unknown Action: %s") % action,
            )
    except Exception as e:
        error(f"Action '{action}' failed: {e}\n{traceback.format_exc()}")
        show_notification(
            get_string(30000, "System Tools"),
            get_string(30023, "Tool failed: %s") % action,
        )


def run_entry(action: str) -> None:
    """Run whatever the user picked in the menu."""
    if action == ABOUT_ACTION:
        show_about_info()
    else:
        run_tool(action)


def show_dialog_menu(reason: str = "") -> None:
    """100% skin-independent UI: a native Kodi select dialog with details."""
    if not (_HAS_XBMC and xbmcgui):
        info(f"Dialog menu unavailable outside Kodi (reason: {reason})")
        return

    entries = menu_entries()
    info(f"Showing native dialog menu: {len(entries)} entries (reason: {reason})")

    while True:
        items = []
        for _action, label, description, icon in entries:
            item = xbmcgui.ListItem(label=label, label2=description)
            try:
                item.setArt({"icon": icon, "thumb": icon})
            except Exception:
                pass
            items.append(item)

        try:
            choice = dialog_select_details(get_string(30000, "System Tools"), items)
        except Exception as e:
            error(f"Failed to open the tool menu dialog: {e}\n{traceback.format_exc()}")
            return

        if choice is None or choice < 0 or choice >= len(entries):
            info("Menu cancelled or closed by user")
            return

        action = entries[choice][0]
        if action == EXIT_ACTION:
            info("Menu closed by user")
            return
        run_entry(action)


def show_main_menu(base_url: str, handle: int) -> None:
    """Root menu: close container if open and present native dialog menu."""
    if not (_HAS_XBMC and xbmcgui):
        print(f"Main menu rendered (handle: {handle})")
        return

    if handle >= 0:
        info(f"Container handle {handle} present - closing it (native dialog menu is the active UI)")
        close_container(handle)
    show_dialog_menu("root menu")


def show_about_info() -> None:
    """Show Addon & Hardware platform diagnostic information."""
    sys_info = get_system_info()
    addon = get_addon()
    version = addon.getAddonInfo("version") if addon else "1.0.6"
    dual_boot_str = get_string(30016, "Yes") if sys_info.dual_boot_supported else get_string(30017, "No")

    info_lines = [
        f"=== {get_string(30000, 'System Tools')} ===",
        f"Version: {version}",
        "Author: Mephis",
        "License: GPL-2.0-or-later",
        "--------------------------------------------------",
        get_string(30012, "Operating System: %s") % sys_info.os_type,
        get_string(30013, "Architecture: %s") % sys_info.arch,
        get_string(30014, "Hardware/SoC: %s") % sys_info.soc,
        get_string(30015, "Dual-Boot Support: %s") % dual_boot_str,
        get_string(30018, "Python Runtime: %s") % sys.version.split()[0],
        "--------------------------------------------------",
        get_string(30019, "Toolbox Features:"),
        f"  1. {get_string(30001, 'CoreELEC System & Version Switcher')}",
        f"  2. {get_string(30700, 'DTB Protection & Management')}",
        f"  3. {get_string(30800, 'Free System RAM')}",
        f"  4. {get_string(30900, 'Kodi Performance Optimizer')}",
        f"  5. {get_string(31000, 'R10/F10 Firmware Advanced Settings')}",
        f"  6. {get_string(30002, 'Network Speed Test')}",
        f"  7. {get_string(30003, 'Disk Benchmark')}",
        f"  8. {get_string(30004, 'Network Configuration')}",
        f"  9. {get_string(31408, 'Remote Control Auto-Adapter')}",
        f"  10. {get_string(30005, 'Clear Kodi Logs')}",
        f"  11. {get_string(31500, 'Daily Auto Reboot')}",
    ]
    dialog_textviewer(get_string(30006, "System Information"), "\n".join(info_lines))


def route(argv: list) -> None:
    """Entry point router."""
    base_url = argv[0] if len(argv) > 0 else ""
    try:
        handle = int(argv[1]) if len(argv) > 1 else -1
    except (TypeError, ValueError):
        handle = -1
    param_string = argv[2] if len(argv) > 2 else ""

    params = parse_params(param_string)
    action = params.get("action", "")

    info(f"Entry: handle={handle} action='{action}' argv={list(argv)!r}")

    if action in ("menu", "dialog", "root"):
        close_container(handle)
        show_dialog_menu(f"requested ?action={action}")
    elif not action:
        show_main_menu(base_url, handle)
    elif action == ABOUT_ACTION:
        show_about_info()
    else:
        run_tool(action)

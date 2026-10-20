# -*- coding: utf-8 -*-
"""Tool: R10/F10 Firmware Advanced Settings.

Provides category-based configuration for custom CoreELEC / Amlogic firmware
advanced settings (ALSA sink, hardware decoding, VC-1, Mali EGL pipeline,
dirty regions, and network timeouts).
"""

import os
import shutil
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from ..common.kodi_ui import (
    dialog_input,
    dialog_ok,
    dialog_select,
    dialog_textviewer,
    dialog_yesno,
    get_string,
    show_notification,
    translate_path,
)
from ..common.logger import debug, error, info
from ..common.system_exec import run_command
from .base_tool import BaseTool, ToolRegistry

try:
    import xbmc
    _HAS_XBMC = True
except ImportError:
    _HAS_XBMC = False
    xbmc = None


DEFAULT_CE_USERDATA = "/storage/.kodi/userdata"


def get_default_userdata_dir() -> str:
    """Detect the active Kodi userdata path."""
    if os.path.isdir(DEFAULT_CE_USERDATA):
        return DEFAULT_CE_USERDATA
    try:
        translated = translate_path("special://userdata/")
        if os.path.isdir(translated):
            return translated
    except Exception:
        pass
    return DEFAULT_CE_USERDATA


CATEGORIES: List[Dict[str, Any]] = [
    {
        "id": "audio",
        "title_id": 31002,
        "desc": "Audio Engine & ALSA Sink",
    },
    {
        "id": "video",
        "title_id": 31003,
        "desc": "Video Player & Hardware Codec",
    },
    {
        "id": "gui",
        "title_id": 31004,
        "desc": "GUI Rendering & Mali EGL Pipeline",
    },
    {
        "id": "videolibrary",
        "title_id": 31005,
        "desc": "Video Library Management",
    },
    {
        "id": "network",
        "title_id": 31006,
        "desc": "LAN Protocols & NFS",
    },
    {
        "id": "database",
        "title_id": 31007,
        "desc": "Remote Database Connect Timeout",
    },
]

SETTINGS_SCHEMA: List[Dict[str, Any]] = [
    # 1. Audio Engine & ALSA Sink
    {
        "id": "pcmsinkbitsmax",
        "category": "audio",
        "section": "audio",
        "tag": "pcmsinkbitsmax",
        "type": "choice",
        "default": "0",
        "title_id": 31030,
        "desc_id": 31031,
        "help_id": 31032,
        "choices": ["0", "16", "24", "32"],
    },
    {
        "id": "sinksettleholdms",
        "category": "audio",
        "section": "audio",
        "tag": "sinksettleholdms",
        "type": "int",
        "default": "0",
        "title_id": 31033,
        "desc_id": 31034,
        "help_id": 31035,
        "range": (0, 2000),
        "unit": "ms",
    },

    # 2. Video Player & Hardware Codec
    {
        "id": "menudomainqueuetimesize",
        "category": "video",
        "section": "video",
        "tag": "menudomainqueuetimesize",
        "type": "float",
        "default": "1.0",
        "title_id": 31040,
        "desc_id": 31041,
        "help_id": 31042,
        "range": (0.0, 16.0),
        "unit": "s",
    },
    {
        "id": "bdboundarydrain",
        "category": "video",
        "section": "video",
        "tag": "bdboundarydrain",
        "type": "bool",
        "default": "true",
        "title_id": 31043,
        "desc_id": 31044,
        "help_id": 31045,
    },
    {
        "id": "subtitleasyncparse",
        "category": "video",
        "section": "video",
        "tag": "subtitleasyncparse",
        "type": "bool",
        "default": "true",
        "title_id": 31046,
        "desc_id": 31047,
        "help_id": 31048,
    },
    {
        "id": "asyncfullscreenosd",
        "category": "video",
        "section": "video",
        "tag": "asyncfullscreenosd",
        "type": "choice",
        "default": "2",
        "title_id": 31049,
        "desc_id": 31050,
        "help_id": 31051,
        "choices": ["0", "1", "2"],
    },
    {
        "id": "asyncvideolayerrender",
        "category": "video",
        "section": "video",
        "tag": "asyncvideolayerrender",
        "type": "bool",
        "default": "true",
        "title_id": 31052,
        "desc_id": 31053,
        "help_id": 31054,
    },
    {
        "id": "seekminimumdistancebeforeeof",
        "category": "video",
        "section": "video",
        "tag": "seekminimumdistancebeforeeof",
        "type": "int",
        "default": "10",
        "title_id": 31055,
        "desc_id": 31056,
        "help_id": 31057,
        "range": (0, 600),
        "unit": "s",
    },
    {
        "id": "dvvsvdbv1",
        "category": "video",
        "section": "video",
        "tag": "dvvsvdbv1",
        "type": "bool",
        "default": "false",
        "title_id": 31058,
        "desc_id": 31059,
        "help_id": 31060,
    },
    {
        "id": "deinterlacedelaycompensation",
        "category": "video",
        "section": "video",
        "tag": "deinterlacedelaycompensation",
        "type": "bool",
        "default": "false",
        "title_id": 31061,
        "desc_id": 31062,
        "help_id": 31063,
    },
    {
        "id": "videoratefieldhold",
        "category": "video",
        "section": "video",
        "tag": "videoratefieldhold",
        "type": "bool",
        "default": "true",
        "title_id": 31064,
        "desc_id": 31065,
        "help_id": 31066,
    },
    {
        "id": "vc1forceframeint",
        "category": "video",
        "section": "video",
        "tag": "vc1forceframeint",
        "type": "bool",
        "default": "true",
        "title_id": 31067,
        "desc_id": 31068,
        "help_id": 31069,
    },
    {
        "id": "vc1dropframe",
        "category": "video",
        "section": "video",
        "tag": "vc1dropframe",
        "type": "bool",
        "default": "true",
        "title_id": 31070,
        "desc_id": 31071,
        "help_id": 31072,
    },
    {
        "id": "vc1repairtimestamps",
        "category": "video",
        "section": "video",
        "tag": "vc1repairtimestamps",
        "type": "bool",
        "default": "true",
        "title_id": 31073,
        "desc_id": 31074,
        "help_id": 31075,
    },

    # 3. GUI Rendering & Mali EGL Pipeline
    {
        "id": "bufferagepartialredraw",
        "category": "gui",
        "section": "gui",
        "tag": "bufferagepartialredraw",
        "type": "choice",
        "default": "1",
        "title_id": 31080,
        "desc_id": 31081,
        "help_id": 31082,
        "choices": ["0", "1"],
    },
    {
        "id": "bufferageafterrenderscope",
        "category": "gui",
        "section": "gui",
        "tag": "bufferageafterrenderscope",
        "type": "bool",
        "default": "true",
        "title_id": 31083,
        "desc_id": 31084,
        "help_id": 31085,
    },
    {
        "id": "maxdirtyregions",
        "category": "gui",
        "section": "gui",
        "tag": "maxdirtyregions",
        "type": "int",
        "default": "4",
        "title_id": 31086,
        "desc_id": 31087,
        "help_id": 31088,
        "range": (0, 64),
    },
    {
        "id": "skipsleepactivewindow",
        "category": "gui",
        "section": "gui",
        "tag": "skipsleepactivewindow",
        "type": "int",
        "default": "250",
        "title_id": 31089,
        "desc_id": 31090,
        "help_id": 31091,
        "range": (0, 2000),
        "unit": "ms",
    },
    {
        "id": "menuidleframeratecap",
        "category": "gui",
        "section": "gui",
        "tag": "menuidleframeratecap",
        "type": "int",
        "default": "0",
        "title_id": 31092,
        "desc_id": 31093,
        "help_id": 31094,
        "range": (0, 60),
        "unit": "FPS",
    },
    {
        "id": "skinhdrfbo",
        "category": "gui",
        "section": "gui",
        "tag": "skinhdrfbo",
        "type": "choice",
        "default": "0",
        "title_id": 31095,
        "desc_id": 31096,
        "help_id": 31097,
        "choices": ["0", "1"],
    },
    {
        "id": "osdguestcomposite",
        "category": "gui",
        "section": "gui",
        "tag": "osdguestcomposite",
        "type": "choice",
        "default": "0",
        "title_id": 31098,
        "desc_id": 31099,
        "help_id": 31100,
        "choices": ["0", "1"],
    },
    {
        "id": "osdtrace",
        "category": "gui",
        "section": "gui",
        "tag": "osdtrace",
        "type": "choice",
        "default": "0",
        "title_id": 31101,
        "desc_id": 31102,
        "help_id": 31103,
        "choices": ["0", "1"],
    },
    {
        "id": "anisotropicfiltering",
        "category": "gui",
        "section": "gui",
        "tag": "anisotropicfiltering",
        "type": "choice",
        "default": "0",
        "title_id": 31104,
        "desc_id": 31105,
        "help_id": 31106,
        "choices": ["0", "2", "4", "8", "16"],
    },
    {
        "id": "fronttobackrendering",
        "category": "gui",
        "section": "gui",
        "tag": "fronttobackrendering",
        "type": "bool",
        "default": "false",
        "title_id": 31107,
        "desc_id": 31108,
        "help_id": 31109,
    },
    {
        "id": "geometryclear",
        "category": "gui",
        "section": "gui",
        "tag": "geometryclear",
        "type": "bool",
        "default": "true",
        "title_id": 31110,
        "desc_id": 31111,
        "help_id": 31112,
    },
    {
        "id": "waitvsyncbeforeswap",
        "category": "gui",
        "section": "gui",
        "tag": "waitvsyncbeforeswap",
        "type": "bool",
        "default": "true",
        "title_id": 31113,
        "desc_id": 31114,
        "help_id": 31115,
    },
    {
        "id": "waitgpubeforeswap",
        "category": "gui",
        "section": "gui",
        "tag": "waitgpubeforeswap",
        "type": "choice",
        "default": "2",
        "title_id": 31116,
        "desc_id": 31117,
        "help_id": 31118,
        "choices": ["0", "1", "2"],
    },
    {
        "id": "srgbhdrcomposite",
        "category": "gui",
        "section": "gui",
        "tag": "srgbhdrcomposite",
        "type": "bool",
        "default": "true",
        "title_id": 31119,
        "desc_id": 31120,
        "help_id": 31121,
    },
    {
        "id": "compositedither",
        "category": "gui",
        "section": "gui",
        "tag": "compositedither",
        "type": "bool",
        "default": "true",
        "title_id": 31122,
        "desc_id": 31123,
        "help_id": 31124,
    },
    {
        "id": "asynctextureupload",
        "category": "gui",
        "section": "gui",
        "tag": "asynctextureupload",
        "type": "bool",
        "default": "true",
        "title_id": 31125,
        "desc_id": 31126,
        "help_id": 31127,
    },
    {
        "id": "mipmapping",
        "category": "gui",
        "section": "gui",
        "tag": "mipmapping",
        "type": "bool",
        "default": "false",
        "title_id": 31128,
        "desc_id": 31129,
        "help_id": 31130,
    },
    {
        "id": "mipmappingsharpen",
        "category": "gui",
        "section": "gui",
        "tag": "mipmappingsharpen",
        "type": "float",
        "default": "0.5",
        "title_id": 31131,
        "desc_id": 31132,
        "help_id": 31133,
        "range": (0.0, 3.0),
    },
    {
        "id": "minifiedmipmapping",
        "category": "gui",
        "section": "gui",
        "tag": "minifiedmipmapping",
        "type": "bool",
        "default": "true",
        "title_id": 31134,
        "desc_id": 31135,
        "help_id": 31136,
    },

    # 4. Video Library Management
    {
        "id": "casesensitivelocalartmatch",
        "category": "videolibrary",
        "section": "videolibrary",
        "tag": "casesensitivelocalartmatch",
        "type": "bool",
        "default": "true",
        "title_id": 31137,
        "desc_id": 31138,
        "help_id": 31139,
    },

    # 5. LAN Protocols & NFS
    {
        "id": "nfstimeout",
        "category": "network",
        "section": "network",
        "tag": "nfstimeout",
        "type": "int",
        "default": "0",
        "title_id": 31140,
        "desc_id": 31141,
        "help_id": 31142,
        "range": (0, 3600),
        "unit": "s",
    },
    {
        "id": "nfsretries",
        "category": "network",
        "section": "network",
        "tag": "nfsretries",
        "type": "int",
        "default": "-1",
        "title_id": 31143,
        "desc_id": 31144,
        "help_id": 31145,
        "range": (-1, 30),
    },

    # 6. Remote Database Connect Timeout (multi-parent mapping)
    {
        "id": "db_connecttimeout",
        "category": "database",
        "section": ["videodatabase", "musicdatabase", "tvdatabase", "epgdatabase"],
        "tag": "connecttimeout",
        "type": "int",
        "default": "5",
        "title_id": 31146,
        "desc_id": 31147,
        "help_id": 31148,
        "range": (1, 60),
        "unit": "s",
    },
]


def get_setting_by_id(setting_id: str) -> Optional[Dict[str, Any]]:
    """Look up setting schema item by its unique ID."""
    for item in SETTINGS_SCHEMA:
        if item["id"] == setting_id:
            return item
    return None


def get_settings_by_category(category_id: str) -> List[Dict[str, Any]]:
    """Retrieve all setting schema items in a given category."""
    return [item for item in SETTINGS_SCHEMA if item["category"] == category_id]


class FirmwareXmlEngine:
    """Non-destructive XML merge and backup manager for advancedsettings.xml."""

    def __init__(self, userdata_path: Optional[str] = None):
        self.userdata_path = userdata_path if userdata_path else get_default_userdata_dir()
        self.xml_path = os.path.join(self.userdata_path, "advancedsettings.xml")
        self.bak_path = f"{self.xml_path}.bak"
        self.not_exist_path = f"{self.xml_path}.not_exist"

    def get_xml_path(self) -> str:
        return self.xml_path

    def has_backup(self) -> bool:
        return os.path.exists(self.bak_path) or os.path.exists(self.not_exist_path)

    def backup_config(self) -> Optional[str]:
        """Create a .bak copy of advancedsettings.xml if it exists, or record .not_exist if absent."""
        if os.path.exists(self.xml_path):
            if not os.path.exists(self.bak_path):
                try:
                    shutil.copy2(self.xml_path, self.bak_path)
                    info(f"Created advancedsettings backup: {self.bak_path}")
                    return self.bak_path
                except Exception as e:
                    error(f"Failed to create backup: {e}")
            if os.path.exists(self.not_exist_path):
                try:
                    os.remove(self.not_exist_path)
                except Exception:
                    pass
        else:
            if not os.path.exists(self.bak_path) and not os.path.exists(self.not_exist_path):
                try:
                    with open(self.not_exist_path, "w", encoding="utf-8") as f:
                        f.write("")
                    info(f"Recorded pre-modification absent state: {self.not_exist_path}")
                    return self.not_exist_path
                except Exception as e:
                    error(f"Failed to write marker {self.not_exist_path}: {e}")
        return None

    def restore_backup(self) -> bool:
        """Restore advancedsettings.xml from .bak backup or revert to absent state."""
        if os.path.exists(self.bak_path):
            try:
                shutil.copy2(self.bak_path, self.xml_path)
                info(f"Restored advancedsettings from: {self.bak_path}")
                return True
            except Exception as e:
                error(f"Failed to restore backup: {e}")
                return False
        elif os.path.exists(self.not_exist_path):
            try:
                if os.path.exists(self.xml_path):
                    os.remove(self.xml_path)
                    info(f"Removed {self.xml_path} to restore pre-modification absent state")
                os.remove(self.not_exist_path)
                return True
            except Exception as e:
                error(f"Failed to restore absent state for {self.xml_path}: {e}")
                return False
        return False

    def _get_tree_and_root(self) -> Tuple[Optional[ET.ElementTree], ET.Element]:
        """Parse existing XML file or initialize a fresh root element."""
        root = None
        tree = None
        if os.path.exists(self.xml_path):
            try:
                tree = ET.parse(self.xml_path)
                root = tree.getroot()
            except Exception as e:
                debug(f"Failed to parse {self.xml_path} ({e}), initializing fresh root.")
                root = None

        if root is None or root.tag != "advancedsettings":
            root = ET.Element("advancedsettings")
            tree = ET.ElementTree(root)
        return tree, root

    def read_setting_value(self, item: Dict[str, Any]) -> Optional[str]:
        """Read the current setting value from advancedsettings.xml."""
        if not os.path.exists(self.xml_path):
            return None

        _, root = self._get_tree_and_root()
        section = item["section"]
        tag = item["tag"]

        sections = section if isinstance(section, list) else [section]
        for s in sections:
            parent = root.find(s)
            if parent is not None:
                val = parent.findtext(tag)
                if val is not None:
                    return val.strip()
        return None

    def write_setting_value(self, item: Dict[str, Any], new_value: str) -> None:
        """Incrementally update or insert setting value, preserving existing nodes."""
        os.makedirs(self.userdata_path, exist_ok=True)
        self.backup_config()

        _, root = self._get_tree_and_root()
        section = item["section"]
        tag = item["tag"]

        sections = section if isinstance(section, list) else [section]
        for s in sections:
            parent = root.find(s)
            if parent is None:
                parent = ET.SubElement(root, s)
            elem = parent.find(tag)
            if elem is None:
                elem = ET.SubElement(parent, tag)
            elem.text = str(new_value)

        try:
            ET.indent(root, space="  ", level=0)
        except AttributeError:
            pass

        tree = ET.ElementTree(root)
        tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)
        info(f"Updated setting {item['id']}={new_value} in {self.xml_path}")

    def get_all_status(self) -> List[Tuple[Dict[str, Any], Optional[str]]]:
        """Return list of (item, current_value) for all schema items."""
        return [(item, self.read_setting_value(item)) for item in SETTINGS_SCHEMA]


@ToolRegistry.register
class FirmwareSettingsTool(BaseTool):
    """Interactive R10/F10 firmware advanced settings manager."""

    id = "firmware_settings"
    title_id = 31000
    description_id = 31001
    icon = "DefaultAddonProgram.png"
    order = 17

    def __init__(self, userdata_path: Optional[str] = None):
        self.engine = FirmwareXmlEngine(userdata_path=userdata_path)
        self.has_changes = False

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(31000, "R10/F10 Firmware Advanced Settings")
        info(f"FirmwareSettingsTool invoked on userdata: {self.engine.userdata_path}")

        while True:
            options = []
            for i, cat in enumerate(CATEGORIES):
                cat_title = get_string(cat["title_id"], cat["desc"])
                items = get_settings_by_category(cat["id"])
                options.append(f"{i + 1}. {cat_title} ({len(items)})")

            status_idx = len(CATEGORIES)
            restore_idx = len(CATEGORIES) + 1
            options.append(f"{status_idx + 1}. {get_string(31009, 'View Status Report')}")
            options.append(f"{restore_idx + 1}. {get_string(31010, 'Restore Configurations from Backup (.bak)')}")

            idx = dialog_select(title, options)
            if idx < 0:
                break
            elif idx < len(CATEGORIES):
                self._show_settings_in_category(CATEGORIES[idx])
            elif idx == status_idx:
                self._show_status_report()
            elif idx == restore_idx:
                self._restore_backup_dialog()

        # Prompt reboot upon exiting if any change was made
        if self.has_changes:
            reboot_msg = get_string(
                31014,
                "Advanced settings have been modified. Kodi restart is required to take effect. Reboot now?",
            )
            if dialog_yesno(title, reboot_msg):
                self._do_restart()

    def _show_settings_in_category(self, category: Dict[str, Any]) -> None:
        cat_title = get_string(category["title_id"], category["desc"])
        items = get_settings_by_category(category["id"])
        if not items:
            return

        while True:
            options = []
            for i, item in enumerate(items):
                val = self.engine.read_setting_value(item)
                if val is None:
                    status_str = get_string(31018, "Not set")
                elif item["type"] == "bool":
                    status_str = get_string(31019, "Enabled") if val.lower() == "true" else get_string(31020, "Disabled")
                else:
                    unit = item.get("unit", "")
                    status_str = f"{val}{unit}" if unit else val

                t_str = get_string(item["title_id"], item["id"])
                d_str = get_string(item["desc_id"], "")
                options.append(f"{i + 1}. [{status_str}] {t_str} - {d_str}")

            idx = dialog_select(cat_title, options)
            if idx < 0:
                break
            self._show_setting_detail(items[idx])

    def _show_setting_detail(self, item: Dict[str, Any]) -> None:
        title = get_string(item["title_id"], item["id"])
        while True:
            val = self.engine.read_setting_value(item)
            if val is None:
                current_display = get_string(31018, "Not set")
            elif item["type"] == "bool":
                current_display = get_string(31019, "Enabled") if val.lower() == "true" else get_string(31020, "Disabled")
            else:
                unit = item.get("unit", "")
                current_display = f"{val}{unit}" if unit else val

            default_display = str(item["default"])
            if item["type"] == "bool":
                default_display = get_string(31019, "Enabled") if default_display.lower() == "true" else get_string(31020, "Disabled")
            elif item.get("unit"):
                default_display = f"{default_display}{item['unit']}"

            header_info = get_string(31017, "Current Value: %s | Recommended: %s") % (current_display, default_display)

            options = [
                f"1. {get_string(31011, 'Modify Value')} [{current_display}]",
                f"2. {get_string(31012, 'Reset to Recommended Default')} [{default_display}]",
                f"3. {get_string(30022, 'View Technical Explanation')}",
            ]

            d_title = f"{title} ({item['tag']})"
            idx = dialog_select(d_title, options)
            if idx < 0:
                break
            elif idx == 0:
                self._edit_setting_value(item, current_val=val)
            elif idx == 1:
                confirm_msg = get_string(31023, "Reset this setting to default value: %s?") % default_display
                if dialog_yesno(d_title, confirm_msg):
                    self.engine.write_setting_value(item, str(item["default"]))
                    self.has_changes = True
                    show_notification(
                        get_string(31000, "R10/F10 Firmware Advanced Settings"),
                        get_string(31013, "Saved: %s = %s") % (item["tag"], item["default"]),
                    )
            elif idx == 2:
                help_text = get_string(item["help_id"], "")
                dialog_textviewer(d_title, f"{header_info}\n\n{help_text}")

    def _edit_setting_value(self, item: Dict[str, Any], current_val: Optional[str]) -> bool:
        t_title = get_string(item["title_id"], item["id"])
        notify_title = get_string(31000, "R10/F10 Firmware Advanced Settings")

        if item["type"] == "bool":
            new_val = "false" if (current_val and current_val.lower() == "true") else "true"
            self.engine.write_setting_value(item, new_val)
            self.has_changes = True
            show_notification(notify_title, get_string(31013, "Saved: %s = %s") % (item["tag"], new_val))
            return True

        elif item["type"] == "choice":
            choices = item["choices"]
            options = []
            for c in choices:
                is_curr = (current_val == c)
                options.append(f"{c} {'*' if is_curr else ''}")

            idx = dialog_select(t_title, options)
            if idx < 0:
                return False
            new_val = choices[idx]
            self.engine.write_setting_value(item, new_val)
            self.has_changes = True
            show_notification(notify_title, get_string(31013, "Saved: %s = %s") % (item["tag"], new_val))
            return True

        elif item["type"] in ("int", "float"):
            min_v, max_v = item.get("range", (0, 999999999))
            unit = item.get("unit", "")
            prompt = get_string(31015, "Enter new value (range: %s - %s %s):") % (min_v, max_v, unit)
            default_input = str(current_val if current_val is not None else item["default"])

            while True:
                entered = dialog_input(prompt, default=default_input)
                if not entered:
                    return False
                try:
                    if item["type"] == "int":
                        val_num = int(entered)
                    else:
                        val_num = float(entered)
                    if val_num < min_v or val_num > max_v:
                        dialog_ok(
                            notify_title,
                            get_string(31016, "Invalid input or value out of range [%s - %s]!") % (min_v, max_v),
                        )
                        continue
                    new_val = str(val_num)
                    self.engine.write_setting_value(item, new_val)
                    self.has_changes = True
                    show_notification(notify_title, get_string(31013, "Saved: %s = %s") % (item["tag"], new_val))
                    return True
                except ValueError:
                    dialog_ok(
                        notify_title,
                        get_string(31016, "Invalid input or value out of range [%s - %s]!") % (min_v, max_v),
                    )
                    continue

        return False

    def _show_status_report(self) -> None:
        title = get_string(31158, "R10/F10 Firmware Settings Overview")
        lines = [f"=== {title} ===", ""]

        for cat in CATEGORIES:
            cat_title = get_string(cat["title_id"], cat["desc"])
            lines.append(f"[{cat_title}]")
            for item in get_settings_by_category(cat["id"]):
                val = self.engine.read_setting_value(item)
                status_str = val if val is not None else get_string(31018, "Not set")
                t_str = get_string(item["title_id"], item["id"])
                lines.append(f"  * {item['tag']} ({t_str}): {status_str} [default: {item['default']}]")
            lines.append("")

        dialog_textviewer(title, "\n".join(lines))

    def _restore_backup_dialog(self) -> None:
        title = get_string(31000, "R10/F10 Firmware Advanced Settings")
        if not self.engine.has_backup():
            dialog_ok(title, get_string(31021, "No backup file found to restore."))
            return

        confirm_msg = get_string(31024, "Are you sure you want to restore all advanced settings from .bak?")
        if not dialog_yesno(title, confirm_msg):
            return

        if self.engine.restore_backup():
            reboot_msg = get_string(31022, "Backup restored successfully! Kodi restart is required. Reboot now?")
            if dialog_yesno(title, reboot_msg):
                self._do_restart()

    def _do_restart(self) -> None:
        run_command("sync")
        if _HAS_XBMC and xbmc:
            try:
                xbmc.restart()
                return
            except Exception:
                pass
        run_command("reboot -f")



# -*- coding: utf-8 -*-
"""Tool: CoreELEC DTB Auto-update Protection and Custom DTB Management.

Prevents custom device tree (dtb.img) from being overwritten during tar system updates
by managing /storage/.config/dtb-autoupdate.conf (ENABLE=no).
Also provides backup and restore for custom dtb.img.
"""

import os
import shutil
from typing import Dict

from ..common.kodi_ui import (
    dialog_ok,
    dialog_select,
    dialog_textviewer,
    dialog_yesno,
    get_string,
    show_notification,
)
from ..common.logger import debug, error, info
from ..common.system_exec import run_command
from .base_tool import BaseTool, ToolRegistry

DEFAULT_CONFIG_DIR = "/storage/.config"
DEFAULT_FLASH_DIR = "/flash"
CONF_FILENAME = "dtb-autoupdate.conf"
CUSTOM_DTB_BACKUP = "custom_dtb.img"


def is_dtb_protected(config_dir: str = DEFAULT_CONFIG_DIR) -> bool:
    """Check if DTB auto-update protection is active (ENABLE=no)."""
    conf_path = os.path.join(config_dir, CONF_FILENAME)
    if os.path.isfile(conf_path):
        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                # Check for ENABLE=no or enable=no
                for line in content.splitlines():
                    clean_line = line.strip().replace(" ", "").upper()
                    if clean_line.startswith("ENABLE=NO"):
                        return True
        except Exception as e:
            debug(f"Error reading {conf_path}: {e}")
    return False


def set_dtb_protection(enabled: bool, config_dir: str = DEFAULT_CONFIG_DIR) -> bool:
    """Set DTB auto-update protection (enabled=True writes ENABLE=no)."""
    os.makedirs(config_dir, exist_ok=True)
    conf_path = os.path.join(config_dir, CONF_FILENAME)
    try:
        with open(conf_path, "w", encoding="utf-8") as f:
            if enabled:
                f.write("ENABLE=no\n")
            else:
                f.write("ENABLE=yes\n")
        info(f"Updated {conf_path} to ENABLE={'no' if enabled else 'yes'}")
        return True
    except Exception as e:
        error(f"Failed to write {conf_path}: {e}")
        return False


@ToolRegistry.register
class DtbTool(BaseTool):
    id = "dtb_tool"
    title_id = 30700
    description_id = 30027
    icon = "DefaultAddonService.png"
    order = 15

    def __init__(self, config_dir: str = DEFAULT_CONFIG_DIR, flash_dir: str = DEFAULT_FLASH_DIR):
        self.config_dir = config_dir
        self.flash_dir = flash_dir
        self.conf_path = os.path.join(config_dir, CONF_FILENAME)
        self.backup_path = os.path.join(config_dir, CUSTOM_DTB_BACKUP)
        self.flash_dtb_path = os.path.join(flash_dir, "dtb.img")

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(30700, "DTB Protection & Management")
        info("DTB tool invoked")

        protected = is_dtb_protected(self.config_dir)
        status_text = (
            get_string(30701, "Current Status: Protected (ENABLE=no)")
            if protected
            else get_string(30702, "Current Status: Unprotected (ENABLE=yes)")
        )

        has_backup = os.path.isfile(self.backup_path)

        options = [
            f"1. {get_string(30704, 'Disable DTB Protection') if protected else get_string(30703, 'Enable DTB Protection')}",
            f"2. {get_string(30705, 'Backup Current DTB (/flash/dtb.img)')}",
        ]
        action_keys = ["toggle", "backup"]

        if has_backup:
            options.append(f"3. {get_string(30706, 'Restore Custom DTB to /flash')}")
            action_keys.append("restore")

        options.append(f"{len(options) + 1}. {get_string(30709, 'Current Model: %s') % self._get_device_model()}")
        action_keys.append("view_info")

        idx = dialog_select(f"{title} - {status_text}", options)
        if idx < 0:
            return

        action = action_keys[idx]
        if action == "toggle":
            self._action_toggle_protection(title, protected)
        elif action == "backup":
            self._action_backup_dtb(title)
        elif action == "restore":
            self._action_restore_dtb(title)
        elif action == "view_info":
            self._action_view_info(title)

    def _action_toggle_protection(self, title: str, currently_protected: bool) -> None:
        new_state = not currently_protected
        success = set_dtb_protection(new_state, self.config_dir)
        if success:
            msg = (
                get_string(30707, "DTB protection enabled successfully.")
                if new_state
                else get_string(30708, "DTB protection disabled.")
            )
            show_notification(title, msg)
        else:
            dialog_ok(title, get_string(30714, "Failed to update DTB protection configuration."))

    def _action_backup_dtb(self, title: str) -> None:
        if not os.path.isfile(self.flash_dtb_path):
            dialog_ok(title, get_string(30715, "Flash DTB not found at %s") % self.flash_dtb_path)
            return

        os.makedirs(self.config_dir, exist_ok=True)
        try:
            shutil.copy2(self.flash_dtb_path, self.backup_path)
            # Auto-enable protection when backing up custom DTB
            set_dtb_protection(True, self.config_dir)
            msg = f"{get_string(30710, 'Custom DTB backed up successfully.')}\n({self.backup_path})\n\n{get_string(30707, 'DTB protection enabled successfully.')}"
            dialog_ok(title, msg)
        except Exception as e:
            error(f"Failed to backup DTB: {e}")
            dialog_ok(title, get_string(30716, "Backup failed: %s") % str(e))

    def _action_restore_dtb(self, title: str) -> None:
        if not os.path.isfile(self.backup_path):
            dialog_ok(title, get_string(30712, "No DTB backup file found."))
            return

        confirm_msg = get_string(30717, "Restore custom DTB backup:\n%s\n-> %s?") % (self.backup_path, self.flash_dtb_path)
        if not dialog_yesno(title, confirm_msg):
            return

        # Mount flash as rw
        run_command(f"mount -o remount,rw {self.flash_dir}")
        try:
            shutil.copy2(self.backup_path, self.flash_dtb_path)
            run_command("sync")
            show_notification(title, get_string(30711, "Custom DTB restored to /flash."))
        except Exception as e:
            error(f"Failed to restore DTB: {e}")
            dialog_ok(title, get_string(30718, "Restore failed: %s") % str(e))
        finally:
            run_command(f"mount -o remount,ro {self.flash_dir}")

    def _action_view_info(self, title: str) -> None:
        model = self._get_device_model()
        protected = is_dtb_protected(self.config_dir)
        prot_status = get_string(30722, "Enabled (Protected)") if protected else get_string(30723, "Disabled (Overwritable)")
        flash_status = get_string(30727, "Exists") if os.path.exists(self.flash_dtb_path) else get_string(30728, "Not Found")
        backup_status = get_string(30727, "Exists") if os.path.exists(self.backup_path) else get_string(30729, "None")
        info_lines = [
            f"=== {get_string(30719, 'Device Tree & Hardware Information')} ===",
            "",
            get_string(30720, "Device Model: %s") % model,
            get_string(30721, "Auto-Update Protection: %s") % prot_status,
            get_string(30724, "Config Path: %s") % self.conf_path,
            get_string(30725, "Flash DTB: %s (%s)") % (self.flash_dtb_path, flash_status),
            get_string(30726, "Custom Backup: %s (%s)") % (self.backup_path, backup_status),
        ]
        dialog_textviewer(title, "\n".join(info_lines))

    def _get_device_model(self) -> str:
        dt_model = "/proc/device-tree/model"
        if os.path.isfile(dt_model):
            try:
                with open(dt_model, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip("\x00\r\n ")
            except Exception:
                pass
        return "CoreELEC Device"

# -*- coding: utf-8 -*-
"""Tool: CoreELEC Remote Control Auto-Adapter and Keymap Switcher."""

import json
import os
import shutil
import time
from typing import Dict, List, Optional

try:
    import ctypes
except ImportError:
    ctypes = None

import xbmc
import xbmcvfs

from ..common.kodi_ui import (
    dialog_ok,
    dialog_select,
    dialog_yesno,
    get_string,
)
from ..common.logger import debug, error, info
from ..common.os_detect import OSType, get_system_info
from ..common.system_exec import run_command
from .base_tool import BaseTool, ToolRegistry

DEFAULT_KEYMAPS_DIR = None
DEFAULT_HWDB_DIR = "/storage/.config/hwdb.d"
DEFAULT_FLASH_DIR = "/flash"
DEFAULT_BACKUP_DIR = "/storage/.remote_backup"
DEFAULT_CONFIG_DIR = "/storage/.config"

KNOWN_HWDB_NAMES = {
    "UgoosUR02.hwdb", "4pro.hwdb", "CMCC.hwdb", "cmcc2.hwdb",
    "dune.hwdb", "huawR22.hwdb", "zidoov10.hwdb", "zidoov12.hwdb",
}


@ToolRegistry.register
class RemoteAdapterTool(BaseTool):
    id = "remote_adapter"
    title_id = 31408
    description_id = 31409
    icon = "DefaultAddonsInput.png"
    order = 25

    REMOTES = [
        {"id": "6bur02remote", "name": "AM6B Plus UR02 (Official)"},
        {"id": "6bur02R1",     "name": "AM6B Plus UR02 (Community R1)"},
        {"id": "zidoov12",     "name": "Zidoo V12 Bluetooth Remote"},
        {"id": "zidoov10",     "name": "Zidoo V10 Mini Bluetooth Remote"},
        {"id": "g20pro",       "name": "G20 Pro Air Mouse Remote"},
        {"id": "dune",         "name": "DUNE Bluetooth Remote"},
        {"id": "huaweir22",    "name": "Huawei R22 Bluetooth Remote"},
        {"id": "CMCC2remote",  "name": "CMCC 2.4G Remote (Special Keymap)"},
        {"id": "mx3remote",    "name": "MX3 2.4G Air Mouse Remote"},
        {"id": "CMBremote",    "name": "CMCC Bluetooth Remote"},
        {"id": "aurora4pro",   "name": "Tencent Aurora 4 Pro Remote"}
    ]

    def __init__(
        self,
        keymaps_dir: Optional[str] = DEFAULT_KEYMAPS_DIR,
        hwdb_dir: str = DEFAULT_HWDB_DIR,
        flash_dir: str = DEFAULT_FLASH_DIR,
        backup_dir: str = DEFAULT_BACKUP_DIR,
        config_dir: str = DEFAULT_CONFIG_DIR,
        remotes_data_dir: Optional[str] = None,
    ):
        if keymaps_dir is not None:
            self.keymaps_dir = keymaps_dir
        else:
            self.keymaps_dir = xbmcvfs.translatePath("special://userdata/keymaps/")

        self.hwdb_dir = hwdb_dir
        self.flash_dir = flash_dir
        self.backup_dir = backup_dir
        self.config_dir = config_dir

        if remotes_data_dir is not None:
            self.remotes_data_dir = remotes_data_dir
        else:
            self.remotes_data_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "data", "remotes")
            )

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(self.title_id, "Remote Control Auto-Adapter")
        info("Remote Adapter Tool invoked")

        sys_info = get_system_info()
        if sys_info.os_type not in (OSType.COREELEC, OSType.LIBREELEC) and not os.path.exists(self.config_dir):
            dialog_ok(title, get_string(31412, "This feature is only supported on CoreELEC systems."))
            return

        menu_items = [f"{i + 1}. {r['name']}" for i, r in enumerate(self.REMOTES)]
        menu_items.append(f"★ {get_string(31411, 'Restore Previous Remote Backup')}")

        factory_conf = os.path.join(self.flash_dir, "remote.conf.factory")
        has_factory = os.path.exists(factory_conf)
        if has_factory:
            menu_items.append(f"★ {get_string(31419, 'Restore Factory IR Remote (remote.conf)')}")

        header = get_string(31410, "Select Remote to Adapt")
        idx = dialog_select(header, menu_items)
        if idx < 0:
            return

        if idx == len(self.REMOTES):
            self._restore_backup(title)
        elif has_factory and idx == len(self.REMOTES) + 1:
            self._restore_factory_conf(title)
        else:
            selected = self.REMOTES[idx]
            confirm_msg = get_string(31413, "About to adapt remote: [%s]\nExisting configuration will be backed up automatically.\nContinue?") % selected['name']
            if dialog_yesno(title, confirm_msg):
                self._apply_config(title, selected)

    def _create_backup(self) -> None:
        """Create a full snapshot of current remote configuration to backup_dir."""
        try:
            if os.path.exists(self.backup_dir):
                shutil.rmtree(self.backup_dir, ignore_errors=True)
            os.makedirs(self.backup_dir, exist_ok=True)

            # 1. Backup keymaps remote_adapter_*.xml
            if os.path.exists(self.keymaps_dir):
                bk_km_dir = os.path.join(self.backup_dir, "keymaps")
                os.makedirs(bk_km_dir, exist_ok=True)
                for f in os.listdir(self.keymaps_dir):
                    if f.startswith("remote_adapter_") and f.endswith(".xml"):
                        shutil.copy2(os.path.join(self.keymaps_dir, f), os.path.join(bk_km_dir, f))

            # 2. Backup remote_adapter hwdb files
            if os.path.exists(self.hwdb_dir):
                bk_hwdb_dir = os.path.join(self.backup_dir, "hwdb.d")
                os.makedirs(bk_hwdb_dir, exist_ok=True)
                for f in os.listdir(self.hwdb_dir):
                    if (f.startswith("remote_adapter_") or f in KNOWN_HWDB_NAMES) and f.endswith(".hwdb"):
                        shutil.copy2(os.path.join(self.hwdb_dir, f), os.path.join(bk_hwdb_dir, f))

            # 3. Backup /flash/remote.conf
            flash_conf = os.path.join(self.flash_dir, "remote.conf")
            had_conf = os.path.exists(flash_conf)
            if had_conf:
                shutil.copy2(flash_conf, os.path.join(self.backup_dir, "remote.conf"))

            meta = {
                "backup_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "had_remote_conf": had_conf,
            }
            with open(os.path.join(self.backup_dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            info(f"Created remote configuration snapshot at {self.backup_dir}")
        except Exception as e:
            error(f"Failed to create remote backup snapshot: {e}")

    def _restore_backup(self, title: str) -> None:
        """Restore previous configuration snapshot from backup_dir."""
        if not os.path.exists(self.backup_dir):
            dialog_ok(title, get_string(31416, "No remote configuration backup found."))
            return

        need_reboot = False
        flash_rw = False
        try:
            # 1. Clean current remote_adapter XMLs and restore backed up ones
            if os.path.exists(self.keymaps_dir):
                for f in os.listdir(self.keymaps_dir):
                    if f.startswith("remote_adapter_") and f.endswith(".xml"):
                        try:
                            os.remove(os.path.join(self.keymaps_dir, f))
                        except Exception:
                            pass

            bk_km_dir = os.path.join(self.backup_dir, "keymaps")
            if os.path.exists(bk_km_dir):
                for f in os.listdir(bk_km_dir):
                    shutil.copy2(os.path.join(bk_km_dir, f), os.path.join(self.keymaps_dir, f))

            # 2. Clean current remote_adapter hwdb files and restore backed up ones
            if os.path.exists(self.hwdb_dir):
                for f in os.listdir(self.hwdb_dir):
                    if (f.startswith("remote_adapter_") or f in KNOWN_HWDB_NAMES) and f.endswith(".hwdb"):
                        try:
                            os.remove(os.path.join(self.hwdb_dir, f))
                            need_reboot = True
                        except Exception:
                            pass

            bk_hwdb_dir = os.path.join(self.backup_dir, "hwdb.d")
            if os.path.exists(bk_hwdb_dir):
                for f in os.listdir(bk_hwdb_dir):
                    shutil.copy2(os.path.join(bk_hwdb_dir, f), os.path.join(self.hwdb_dir, f))
                    need_reboot = True

            # 3. Restore /flash/remote.conf based on meta
            bk_conf = os.path.join(self.backup_dir, "remote.conf")
            flash_conf = os.path.join(self.flash_dir, "remote.conf")

            had_remote_conf = os.path.exists(bk_conf)
            meta_file = os.path.join(self.backup_dir, "meta.json")
            if os.path.exists(meta_file):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        had_remote_conf = json.load(f).get("had_remote_conf", had_remote_conf)
                except Exception:
                    pass

            if had_remote_conf and os.path.exists(bk_conf):
                self._set_flash_writable()
                flash_rw = True
                shutil.copy2(bk_conf, flash_conf)
                need_reboot = True
            elif not had_remote_conf and os.path.exists(flash_conf):
                self._set_flash_writable()
                flash_rw = True
                os.remove(flash_conf)
                need_reboot = True

            info("Restored remote backup configuration successfully")
        except Exception as e:
            error(f"Failed to restore remote backup: {e}")
            fail_msg = get_string(31418, "Failed to apply remote configuration: %s") % str(e)
            dialog_ok(title, fail_msg)
            return
        finally:
            if flash_rw:
                self._set_flash_readonly()

        if need_reboot:
            reboot_prompt = get_string(31417, "Previous remote backup restored successfully! Reboot now?")
            if dialog_yesno(title, reboot_prompt):
                self._do_reboot()
        else:
            xbmc.executebuiltin("action(reloadkeymaps)")
            dialog_ok(title, get_string(31414, "Remote [%s] applied successfully! Keymaps reloaded.") % "Backup")

    def _restore_factory_conf(self, title: str) -> None:
        """Restore original factory remote.conf from .factory backup."""
        factory_conf = os.path.join(self.flash_dir, "remote.conf.factory")
        flash_conf = os.path.join(self.flash_dir, "remote.conf")
        if not os.path.exists(factory_conf):
            dialog_ok(title, get_string(31416, "No remote configuration backup found."))
            return

        self._set_flash_writable()
        try:
            shutil.copy2(factory_conf, flash_conf)
            os.remove(factory_conf)
            info("Restored factory remote.conf successfully")
        finally:
            self._set_flash_readonly()

        reboot_prompt = get_string(31420, "Factory IR remote configuration restored successfully! Reboot now?")
        if dialog_yesno(title, reboot_prompt):
            self._do_reboot()

    def _apply_config(self, title: str, remote_info: dict) -> None:
        source_dir = os.path.join(self.remotes_data_dir, remote_info["id"])
        if not os.path.exists(source_dir):
            dialog_ok(title, get_string(31418, "Failed to apply remote configuration: %s") % f"Directory not found: {source_dir}")
            return

        os.makedirs(self.keymaps_dir, exist_ok=True)
        os.makedirs(self.hwdb_dir, exist_ok=True)

        self._create_backup()

        need_reboot = False
        flash_rw = False
        failed_ops = []

        try:
            files = os.listdir(source_dir)

            # 1. Clean previous remote_adapter_*.xml
            if os.path.exists(self.keymaps_dir):
                for f in os.listdir(self.keymaps_dir):
                    if f.startswith("remote_adapter_") and f.endswith(".xml"):
                        try:
                            os.remove(os.path.join(self.keymaps_dir, f))
                        except Exception:
                            pass

            # 2. Clean previous remote_adapter hwdb files (never touch user custom hwdb)
            if os.path.exists(self.hwdb_dir):
                for f in os.listdir(self.hwdb_dir):
                    if (f.startswith("remote_adapter_") or f in KNOWN_HWDB_NAMES) and f.endswith(".hwdb"):
                        try:
                            os.remove(os.path.join(self.hwdb_dir, f))
                            need_reboot = True
                        except Exception:
                            pass

            # 3. Check for .conf files
            has_new_conf = any(f.endswith(".conf") for f in files)
            flash_conf = os.path.join(self.flash_dir, "remote.conf")
            factory_conf = os.path.join(self.flash_dir, "remote.conf.factory")

            if not has_new_conf and os.path.exists(flash_conf):
                # Protect original factory remote.conf by renaming to .factory instead of deleting
                self._set_flash_writable()
                flash_rw = True
                try:
                    shutil.move(flash_conf, factory_conf)
                    need_reboot = True
                    info(f"Protected original remote.conf -> {factory_conf}")
                except Exception as e:
                    failed_ops.append(f"Protect remote.conf failed: {e}")

            # 4. Copy new files (xml, hwdb, conf)
            for filename in files:
                src_path = os.path.join(source_dir, filename)

                if filename.endswith(".xml"):
                    # Use safe prefix to never overwrite or collide with user keymaps
                    safe_name = filename if filename.startswith("remote_adapter_") else f"remote_adapter_{filename}"
                    dst_path = os.path.join(self.keymaps_dir, safe_name)
                    shutil.copy2(src_path, dst_path)

                elif filename.endswith(".hwdb"):
                    safe_name = filename if filename.startswith("remote_adapter_") else f"remote_adapter_{filename}"
                    dst_path = os.path.join(self.hwdb_dir, safe_name)
                    shutil.copy2(src_path, dst_path)
                    need_reboot = True

                elif filename.endswith(".conf"):
                    if not flash_rw:
                        self._set_flash_writable()
                        flash_rw = True
                    dst_path = os.path.join(self.flash_dir, filename)
                    shutil.copy2(src_path, dst_path)
                    need_reboot = True

            info(f"Applied remote configuration for {remote_info['name']}")
        except Exception as e:
            error(f"Remote adapter failed: {e}")
            failed_ops.append(str(e))
        finally:
            if flash_rw:
                self._set_flash_readonly()

        if failed_ops:
            fail_msg = get_string(31418, "Failed to apply remote configuration: %s") % "\n".join(failed_ops)
            dialog_ok(title, fail_msg)
            return

        if need_reboot:
            reboot_msg = get_string(31415, "Hardware driver changes detected for [%s]. A reboot is required to take effect.\nReboot now?") % remote_info['name']
            if dialog_yesno(title, reboot_msg):
                self._do_reboot()
        else:
            xbmc.executebuiltin("action(reloadkeymaps)")
            success_msg = get_string(31414, "Remote [%s] applied successfully! Keymaps reloaded.") % remote_info['name']
            dialog_ok(title, success_msg)

    def _set_flash_writable(self) -> bool:
        if os.path.exists(self.flash_dir):
            code, _, err = run_command(f"mount -o remount,rw {self.flash_dir}")
            return code == 0
        return True

    def _set_flash_readonly(self) -> None:
        if os.path.exists(self.flash_dir):
            run_command(f"mount -o remount,ro {self.flash_dir}")

    def _do_reboot(self) -> None:
        """Execute safe sync & hardware reboot."""
        info("Syncing filesystems and executing reboot")
        try:
            os.sync()
        except Exception:
            pass
        run_command("sync")

        self._set_flash_readonly()

        try:
            with open("/proc/sys/kernel/sysrq", "w") as f:
                f.write("1\n")
            with open("/proc/sysrq-trigger", "w") as f:
                f.write("s\n")
            time.sleep(0.5)
            with open("/proc/sysrq-trigger", "w") as f:
                f.write("u\n")
            time.sleep(0.5)
            with open("/proc/sysrq-trigger", "w") as f:
                f.write("b\n")
            time.sleep(2)
        except Exception as e:
            debug(f"SysRq reboot failed or not supported: {e}")

        if ctypes is not None:
            try:
                libc = ctypes.CDLL(None)
                if hasattr(libc, "reboot"):
                    if hasattr(libc, "sync"):
                        libc.sync()
                    libc.reboot(0x01234567)
                    time.sleep(2)
            except Exception as e:
                debug(f"libc reboot syscall failed: {e}")

        code, _, _ = run_command("reboot -f")
        if code != 0:
            run_command("reboot")

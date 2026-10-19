# -*- coding: utf-8 -*-
"""Tool: CoreELEC Multi-version Switcher and System Management.

Specially designed for CoreELEC to switch between different versions (.tar packages),
such as different official releases, test versions, and nightly builds.
Unpacks and manages SYSTEM, KERNEL.img, and associated guisettings.xml.
"""

import json
import os
import re
import shutil
import tarfile
import time
from typing import Dict, List, Optional, Tuple

try:
    import ctypes
except ImportError:
    ctypes = None

from ..common.kodi_ui import (
    dialog_browse,
    dialog_input,
    dialog_ok,
    dialog_select,
    dialog_textviewer,
    dialog_yesno,
    get_setting_bool,
    get_string,
    progress_dialog,
    show_notification,
    translate_path,
)
from ..common.logger import debug, error, info
from ..common.os_detect import OSType, get_system_info
from ..common.system_exec import run_command
from ..common.vfs_utils import (
    get_filename_from_path,
    open_tar_archive,
    vfs_delete_file,
    vfs_file_exists,
    vfs_file_size,
)
from .base_tool import BaseTool, ToolRegistry
from .dtb_tool import is_dtb_protected

FLASH_DIR = "/flash"
STORAGE_DIR = "/storage"
VERSIONS_DIR = "/storage/.ce_versions"


def parse_tar_version_info(filename: str) -> Tuple[str, str, str]:
    """Parse CoreELEC update tar filename into (safe_name, display_name, build_time).

    Example:
      Input:  CoreELEC-Amlogic-ng.arm-21.3-Omega_avdvplus_F10_20260922221205.tar
      Output: (
        '21.3-Omega_avdvplus_F10_0922_2212',
        '21.3-Omega_avdvplus_F10 [09-22 22:12]',
        '2026-09-22 22:12:05'
      )
    """
    name = re.sub(r"\.tar$", "", filename)
    name = re.sub(r"^CoreELEC(-Amlogic-[a-zA-Z0-9_.]*)?-", "", name)
    name = re.sub(r"-Generic$", "", name)

    # 14 digits timestamp: YYYYMMDDHHMMSS (e.g. _20260922221205)
    m14 = re.search(r"[_.-](\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$", name)
    if m14:
        base = name[:m14.start()]
        year, month, day, hour, minute, second = m14.groups()
        safe_name = f"{base}_{month}{day}_{hour}{minute}"
        display_name = f"{base} [{month}-{day} {hour}:{minute}]"
        build_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
        return safe_name, display_name, build_time

    # 12 digits timestamp: YYYYMMDDHHMM
    m12 = re.search(r"[_.-](\d{4})(\d{2})(\d{2})(\d{2})(\d{2})$", name)
    if m12:
        base = name[:m12.start()]
        year, month, day, hour, minute = m12.groups()
        safe_name = f"{base}_{month}{day}_{hour}{minute}"
        display_name = f"{base} [{month}-{day} {hour}:{minute}]"
        build_time = f"{year}-{month}-{day} {hour}:{minute}"
        return safe_name, display_name, build_time

    # 8 digits timestamp: YYYYMMDD
    m8 = re.search(r"[_.-](\d{4})(\d{2})(\d{2})$", name)
    if m8:
        base = name[:m8.start()]
        year, month, day = m8.groups()
        safe_name = f"{base}_{year}{month}{day}"
        display_name = f"{base} [{year}-{month}-{day}]"
        build_time = f"{year}-{month}-{day}"
        return safe_name, display_name, build_time

    return name, name, ""


@ToolRegistry.register
class OsSwitcherTool(BaseTool):
    id = "os_switch"
    title_id = 30001
    description_id = 30110
    icon = "DefaultIconWarning.png"
    order = 10

    def __init__(self, flash_dir=FLASH_DIR, versions_dir=None, storage_dir=STORAGE_DIR):
        self.flash_dir = flash_dir
        self.storage_dir = storage_dir
        self.versions_dir = versions_dir if versions_dir is not None else os.path.join(storage_dir, ".ce_versions")
        self.config_dir = os.path.join(storage_dir, ".config")
        self.autostart_script = os.path.join(self.config_dir, "autostart.sh")
        self.switch_target_file = os.path.join(self.config_dir, "ce_switch_target")
        self.gui_settings_current = os.path.join(storage_dir, ".kodi", "userdata", "guisettings.xml")

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(30110, "CoreELEC Version Switcher")
        sys_info = get_system_info()
        info(f"CoreELEC Switcher running on {sys_info}")

        # CoreELEC environment check
        if sys_info.os_type not in (OSType.COREELEC, OSType.LIBREELEC) and not os.path.exists(self.flash_dir):
            diag_msg = f"{get_string(30121, 'This feature is only supported on CoreELEC.')}\n{get_string(30135, 'Continue in simulated/diagnostic mode?')}"
            if not dialog_yesno(title, diag_msg):
                return

        self._ensure_dirs()
        self._setup_autostart_logic()

        active_ver = self._detect_active_version()
        saved_versions = self._get_saved_versions()
        saved_count = len(saved_versions)

        menu_items = [
            f"1. {get_string(30112, 'Switch to Selected Version')} ({saved_count} available)",
            f"2. {get_string(30113, 'Import New Version from .tar')}",
            f"3. {get_string(30114, 'Backup Current System as New Version')}",
            f"4. {get_string(30116, 'Delete Saved Version')}",
        ]
        action_map = ["switch", "import", "backup", "delete"]

        status_header = f"{title} [{get_string(30111, 'Active Version: %s') % active_ver}]"
        idx = dialog_select(status_header, menu_items)
        if idx < 0:
            return

        action = action_map[idx]
        if action == "switch":
            self._action_switch_version(title)
        elif action == "import":
            self._action_import_tar(title)
        elif action == "backup":
            self._action_backup_current(title)
        elif action == "delete":
            self._action_delete_version(title)

    def _ensure_dirs(self) -> None:
        os.makedirs(self.versions_dir, exist_ok=True)
        os.makedirs(self.config_dir, exist_ok=True)

    def _set_flash_writable(self) -> bool:
        """Mount /flash partition as read-write."""
        if not os.path.exists(self.flash_dir):
            return True
        code, out, err = run_command(f"mount -o remount,rw {self.flash_dir}")
        if code != 0:
            error(f"Failed to mount {self.flash_dir} as rw: {err}")
            return False
        return True

    def _set_flash_readonly(self) -> None:
        """Remount /flash back to read-only."""
        if os.path.exists(self.flash_dir):
            run_command(f"mount -o remount,ro {self.flash_dir}")

    def _setup_autostart_logic(self) -> None:
        """Ensure autostart.sh contains hook to restore guisettings.xml before Kodi starts."""
        os.makedirs(self.config_dir, exist_ok=True)
        if not os.path.exists(self.autostart_script):
            with open(self.autostart_script, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n")
            try:
                os.chmod(self.autostart_script, 0o755)
            except Exception:
                pass

        try:
            with open(self.autostart_script, "r", encoding="utf-8") as f:
                content = f.read()

            hook_code = f"""
# >>> CoreELEC Version Switcher Hook >>>
if [ -f "{self.switch_target_file}" ]; then
    TARGET_VER=$(cat "{self.switch_target_file}")
    if [ -f "{self.versions_dir}/$TARGET_VER/guisettings.xml" ]; then
        cp "{self.versions_dir}/$TARGET_VER/guisettings.xml" "{self.gui_settings_current}"
    fi
    rm -f "{self.switch_target_file}"
fi
# <<< CoreELEC Version Switcher Hook <<<
"""
            if "# >>> CoreELEC Version Switcher Hook >>>" not in content:
                with open(self.autostart_script, "a", encoding="utf-8") as f:
                    f.write(hook_code)
                info("Injected version switch hook into autostart.sh")
        except Exception as e:
            error(f"Failed to setup autostart.sh: {e}")

    def _get_saved_versions(self) -> List[Dict[str, str]]:
        """List version metadata dicts in versions_dir."""
        if not os.path.exists(self.versions_dir):
            return []
        versions = []
        for name in sorted(os.listdir(self.versions_dir)):
            vdir = os.path.join(self.versions_dir, name)
            if os.path.isdir(vdir):
                if os.path.exists(os.path.join(vdir, "SYSTEM")) or os.path.exists(os.path.join(vdir, "KERNEL.img")):
                    meta = {
                        "name": name,
                        "display_name": name,
                        "build_time": "",
                        "created_at": "",
                        "tar_file": "",
                    }
                    info_path = os.path.join(vdir, "version.json")
                    if os.path.exists(info_path):
                        try:
                            with open(info_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                meta["display_name"] = data.get("display_name", data.get("name", name))
                                meta["build_time"] = data.get("build_time", "")
                                meta["created_at"] = data.get("created_at", "")
                                meta["tar_file"] = data.get("tar_file", "")
                        except Exception:
                            pass
                    versions.append(meta)
        return versions

    def _detect_active_version(self) -> str:
        """Detect active version by inspecting /flash or version marker."""
        if os.path.exists(self.switch_target_file):
            try:
                with open(self.switch_target_file, "r") as f:
                    return f.read().strip()
            except Exception:
                pass

        for release_path in [os.path.join(self.flash_dir, "os-release"), "/etc/os-release"]:
            if os.path.exists(release_path):
                try:
                    with open(release_path, "r") as f:
                        for line in f:
                            if line.startswith("PRETTY_NAME="):
                                return line.split("=", 1)[1].strip(" \"'\n")
                except Exception:
                    pass
        return "Standard / Unmanaged"

    # ------------------ Action 1: Switch Version ------------------
    def _action_switch_version(self, title: str) -> None:
        versions = self._get_saved_versions()
        if not versions:
            dialog_ok(title, get_string(30125, "No saved versions found. Please import a .tar or backup current system."))
            return

        active_ver = self._detect_active_version()
        options = []
        for v in versions:
            is_active = (v["name"] == active_ver or v["display_name"] == active_ver)
            prefix = "★ [当前运行] " if is_active else "  "
            time_suffix = f" (构建: {v['build_time']})" if v.get("build_time") else ""
            options.append(f"{prefix}{v['display_name']}{time_suffix}")

        idx = dialog_select(get_string(30112, "Switch to Selected Version"), options)
        if idx < 0:
            return

        target = versions[idx]
        target_dir_name = target["name"]
        target_display = target["display_name"]

        confirm_msg = get_string(30124, "Are you sure you want to switch to [%s] and reboot now?") % target_display
        if not dialog_yesno(title, confirm_msg):
            return

        src_vdir = os.path.join(self.versions_dir, target_dir_name)

        if not self._set_flash_writable():
            dialog_ok(title, get_string(30123, "Failed to remount /flash partition as writable."))
            return

        try:
            with progress_dialog(title, get_string(30119, "Writing system files to /flash...")) as dp:
                dp.update(10, "Backing up current guisettings.xml...")
                self._backup_current_guisettings()

                dp.update(25, f"Writing KERNEL for [{target_display}]...")
                self._copy_system_file(src_vdir, self.flash_dir, "KERNEL.img", fallback="KERNEL")

                dp.update(50, f"Writing SYSTEM image for [{target_display}]...")
                self._copy_system_file(src_vdir, self.flash_dir, "SYSTEM")

                dp.update(80, "Writing checksums...")
                for md5_file in ["KERNEL.img.md5", "KERNEL.md5", "SYSTEM.md5"]:
                    self._copy_optional_file(src_vdir, self.flash_dir, md5_file)

                dp.update(90, "Setting configuration markers...")
                os.makedirs(self.config_dir, exist_ok=True)
                with open(self.switch_target_file, "w", encoding="utf-8") as f:
                    f.write(target_dir_name)

                dp.update(100, get_string(30120, "Version switched successfully! Rebooting now..."))
                time.sleep(1)

            self._do_reboot()

        except Exception as e:
            error(f"Switch version failed: {e}")
            dialog_ok(title, f"Switch failed: {e}")
        finally:
            self._set_flash_readonly()

    # ------------------ Action 2: Import from TAR ------------------
    def _action_import_tar(self, title: str) -> None:
        """Import CoreELEC version from .tar update package (local or SMB/NFS share)."""
        update_dir = os.path.join(self.storage_dir, ".update")
        local_tars = []
        if os.path.isdir(update_dir):
            try:
                local_tars = [
                    os.path.join(update_dir, f)
                    for f in os.listdir(update_dir)
                    if f.lower().endswith(".tar") and os.path.isfile(os.path.join(update_dir, f))
                ]
            except Exception:
                pass

        menu_items = []
        actions = []

        for lt in local_tars:
            fname = os.path.basename(lt)
            menu_items.append(f"★ [{get_string(30145, 'Quick Import')}] {fname}")
            actions.append(("quick", lt))

        menu_items.append(get_string(30143, "Browse Files (SMB / NFS / Local / USB)..."))
        actions.append(("browse", None))

        menu_items.append(get_string(30144, "Enter Network / Local Path manually..."))
        actions.append(("input", None))

        idx = dialog_select(get_string(30126, "Select CoreELEC .tar update package"), menu_items)
        if idx < 0:
            return

        action_type, action_val = actions[idx]
        tar_path = ""
        if action_type == "quick":
            tar_path = action_val
        elif action_type == "browse":
            # shares="" exposes both local storage and network shares (SMB, NFS, etc.)
            # default_path="" starts at the root shares list so Windows Network (SMB) and Add network location are visible
            tar_path = dialog_browse(
                1,
                get_string(30126, "Select CoreELEC .tar update package"),
                shares="",
                mask=".tar",
                use_thumbs=False,
                treat_as_folder=False,
                default_path="",
            )
        elif action_type == "input":
            tar_path = dialog_input(get_string(30144, "Enter Network / Local Path manually:"), default="smb://")

        if not tar_path:
            return
        if not vfs_file_exists(tar_path):
            dialog_ok(title, get_string(30140, "Failed to extract tar: %s") % f"File not accessible: {tar_path}")
            return

        base_filename = get_filename_from_path(tar_path)
        safe_name, display_suggested, build_time = parse_tar_version_info(base_filename)

        ver_name = dialog_input(get_string(30117, "Enter Version Name:"), default=display_suggested)
        if not ver_name:
            return

        # Sanitize folder name: replace slashes/colons with dashes/underscores
        dir_name = re.sub(r'[/\\:*?"<>|]', '-', ver_name).strip()

        dest_vdir = os.path.join(self.versions_dir, dir_name)
        os.makedirs(dest_vdir, exist_ok=True)

        extracted_files = []
        try:
            with progress_dialog(title, get_string(30118, "Extracting tar package...")) as dp:
                dp.update(10, f"Inspecting archive: {base_filename}")

                with open_tar_archive(tar_path) as tar:
                    members = tar.getmembers()
                    total_members = len(members)

                    for i, member in enumerate(members):
                        if dp.is_canceled():
                            break

                        base = os.path.basename(member.name)
                        if base in ("KERNEL", "KERNEL.img", "SYSTEM", "KERNEL.md5", "KERNEL.img.md5", "SYSTEM.md5"):
                            target_filename = "KERNEL.img" if base == "KERNEL" else base
                            out_path = os.path.join(dest_vdir, target_filename)

                            dp.update(
                                int(20 + (i / max(1, total_members)) * 70),
                                f"Extracting {base} ({member.size / (1024 * 1024):.1f} MB)..."
                            )

                            with tar.extractfile(member) as src_f, open(out_path, "wb") as dst_f:
                                shutil.copyfileobj(src_f, dst_f)

                            extracted_files.append(target_filename)

            if "SYSTEM" not in extracted_files or not any("KERNEL" in f for f in extracted_files):
                shutil.rmtree(dest_vdir, ignore_errors=True)
                dialog_ok(title, get_string(30122, "KERNEL or SYSTEM file not found in tar package."))
                return

            if os.path.exists(self.gui_settings_current):
                shutil.copy2(self.gui_settings_current, os.path.join(dest_vdir, "guisettings.xml"))

            info_data = {
                "name": dir_name,
                "display_name": ver_name,
                "build_time": build_time,
                "tar_file": base_filename,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "files": extracted_files,
            }
            with open(os.path.join(dest_vdir, "version.json"), "w", encoding="utf-8") as f:
                json.dump(info_data, f, indent=2)

            info(f"Successfully imported version [{ver_name}] into {dest_vdir}")

            # Option to delete the original source .tar file to free up storage space
            tar_size_bytes = vfs_file_size(tar_path)
            tar_size_mb = tar_size_bytes / (1024 * 1024)
            auto_delete = get_setting_bool("auto_delete_tar_after_import", False)
            del_prompt = get_string(30128, "Version [%s] imported successfully!\nDo you want to delete the source .tar package (%s MB) to free up storage?") % (ver_name, f"{tar_size_mb:.1f}")

            if auto_delete or dialog_yesno(title, del_prompt):
                try:
                    if not vfs_delete_file(tar_path):
                        raise OSError("Delete failed (permission denied or read-only share)")
                    info(f"Deleted source tar package: {tar_path} ({tar_size_mb:.1f} MB freed)")
                    show_notification(title, get_string(30129, "Source .tar package deleted (%s MB freed).") % f"{tar_size_mb:.1f}")
                except Exception as e:
                    error(f"Failed to delete source tar {tar_path}: {e}")
                    dialog_ok(title, get_string(30141, "Failed to delete source .tar: %s") % str(e))

            # Ask whether to switch to the imported version immediately
            switch_prompt = get_string(30130, "Do you want to switch to version [%s] and reboot now?") % ver_name
            if dialog_yesno(title, switch_prompt):
                self._switch_to_version_direct(dir_name, title)

        except Exception as e:
            error(f"Import tar failed: {e}")
            shutil.rmtree(dest_vdir, ignore_errors=True)
            dialog_ok(title, get_string(30140, "Failed to extract tar: %s") % str(e))

    # ------------------ Action 3: Backup Current System ------------------
    def _action_backup_current(self, title: str) -> None:
        default_name = f"Backup-{time.strftime('%Y%m%d-%H%M')}"
        name = dialog_input(get_string(30117, "Enter Version Name:"), default=default_name)
        if not name:
            return

        dir_name = re.sub(r'[/\\:*?"<>|]', '-', name).strip()
        dest_vdir = os.path.join(self.versions_dir, dir_name)
        os.makedirs(dest_vdir, exist_ok=True)

        try:
            with progress_dialog(title, get_string(30133, "Backing up current running system...")) as dp:
                dp.update(20, get_string(30136, "Writing KERNEL for [%s]...") % name)
                self._copy_system_file(self.flash_dir, dest_vdir, "KERNEL.img", fallback="KERNEL")

                dp.update(50, get_string(30137, "Writing SYSTEM for [%s]...") % name)
                self._copy_system_file(self.flash_dir, dest_vdir, "SYSTEM")

                dp.update(80, "Backing up guisettings.xml...")
                if os.path.exists(self.gui_settings_current):
                    shutil.copy2(self.gui_settings_current, os.path.join(dest_vdir, "guisettings.xml"))

                for md5_file in ["KERNEL.img.md5", "KERNEL.md5", "SYSTEM.md5"]:
                    self._copy_optional_file(self.flash_dir, dest_vdir, md5_file)

                info_data = {
                    "name": dir_name,
                    "display_name": name,
                    "build_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "Current running /flash backup",
                }
                with open(os.path.join(dest_vdir, "version.json"), "w", encoding="utf-8") as f:
                    json.dump(info_data, f, indent=2)

                dp.update(100, get_string(30120, "Version switched successfully! Rebooting now..."))
                time.sleep(1)

            dialog_ok(title, get_string(30134, "System backup [%s] saved to %s") % (name, dest_vdir))

        except Exception as e:
            error(f"Backup failed: {e}")
            shutil.rmtree(dest_vdir, ignore_errors=True)
            dialog_ok(title, get_string(30142, "Backup failed: %s") % str(e))

    # ------------------ Action 4: Delete Version ------------------
    def _action_delete_version(self, title: str) -> None:
        versions = self._get_saved_versions()
        if not versions:
            dialog_ok(title, get_string(30125, "No saved versions found. Please import a .tar or backup current system."))
            return

        options = [f"{v['display_name']}" + (f" ({v['build_time']})" if v.get('build_time') else "") for v in versions]
        idx = dialog_select(f"{title} - {get_string(30116, 'Delete Saved Version')}", options)
        if idx >= 0:
            target = versions[idx]
            target_name = target["name"]
            target_display = target["display_name"]
            del_msg = get_string(30131, "Are you sure you want to permanently delete saved version [%s]?") % target_display
            if dialog_yesno(title, del_msg):
                vdir = os.path.join(self.versions_dir, target_name)
                shutil.rmtree(vdir, ignore_errors=True)
                show_notification(title, get_string(30132, "Version [%s] deleted.") % target_display)

    # ------------------ Helpers ------------------
    def _switch_to_version_direct(self, target_ver: str, title: str) -> None:
        """Switch to specified version without intermediate dialogs."""
        src_vdir = os.path.join(self.versions_dir, target_ver)
        if not self._set_flash_writable():
            dialog_ok(title, get_string(30123, "Failed to remount /flash partition as writable."))
            return

        try:
            with progress_dialog(title, get_string(30119, "Writing system files to /flash...")) as dp:
                self._backup_current_guisettings()
                dp.update(30, get_string(30136, "Writing KERNEL for [%s]...") % target_ver)
                self._copy_system_file(src_vdir, self.flash_dir, "KERNEL.img", fallback="KERNEL")

                dp.update(60, get_string(30137, "Writing SYSTEM for [%s]...") % target_ver)
                self._copy_system_file(src_vdir, self.flash_dir, "SYSTEM")

                dp.update(80, get_string(30138, "Writing checksums..."))
                for md5_file in ["KERNEL.img.md5", "KERNEL.md5", "SYSTEM.md5"]:
                    self._copy_optional_file(src_vdir, self.flash_dir, md5_file)

                # Check DTB protection before touching dtb.img
                if not is_dtb_protected(self.config_dir):
                    self._copy_optional_file(src_vdir, self.flash_dir, "dtb.img")
                else:
                    info("DTB protection is active (ENABLE=no), skipped overwriting dtb.img in /flash")

                dp.update(90, get_string(30139, "Setting configuration markers..."))
                os.makedirs(self.config_dir, exist_ok=True)
                with open(self.switch_target_file, "w", encoding="utf-8") as f:
                    f.write(target_ver)

                dp.update(100, get_string(30120, "Version switched successfully! Rebooting now..."))
                time.sleep(1)

            self._do_reboot()
        finally:
            self._set_flash_readonly()

    def _copy_system_file(self, src_dir: str, dst_dir: str, filename: str, fallback: str = "") -> None:
        src = os.path.join(src_dir, filename)
        if not os.path.exists(src) and fallback:
            src = os.path.join(src_dir, fallback)
        if not os.path.exists(src):
            raise FileNotFoundError(f"Missing required file: {src}")

        dst = os.path.join(dst_dir, filename)
        shutil.copy2(src, dst)
        info(f"Copied {src} -> {dst}")

    def _copy_optional_file(self, src_dir: str, dst_dir: str, filename: str) -> None:
        src = os.path.join(src_dir, filename)
        if os.path.exists(src):
            dst = os.path.join(dst_dir, filename)
            shutil.copy2(src, dst)

    def _backup_current_guisettings(self) -> None:
        """Back up current guisettings.xml into active version directory if known."""
        active = self._detect_active_version()
        if active and active != "Standard / Unmanaged":
            active_dir = os.path.join(self.versions_dir, active)
            if os.path.isdir(active_dir) and os.path.exists(self.gui_settings_current):
                shutil.copy2(self.gui_settings_current, os.path.join(active_dir, "guisettings.xml"))

    def _do_reboot(self) -> None:
        """Execute clean sync and hardware reboot for version switching."""
        info("Syncing filesystems and executing reboot")
        try:
            os.sync()
        except Exception:
            pass
        run_command("sync")

        # Ensure /flash partition is safely remounted ro before hardware reset
        self._set_flash_readonly()

        # Method 1: Kernel Magic SysRq emergency reboot sequence (Sync -> Remount-RO -> Reboot)
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

        # Method 2: libc direct reboot syscall (LINUX_REBOOT_CMD_RESTART = 0x01234567)
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

        # Method 3: Standard external reboot commands as fallback
        code, _, _ = run_command("reboot -f")
        if code != 0:
            run_command("reboot")

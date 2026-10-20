# -*- coding: utf-8 -*-
"""Tool: Kodi Log Viewer and One-Click Cleaner."""

import glob
import os
import shutil
from typing import Dict, List

from ..common.kodi_ui import (
    dialog_ok,
    dialog_select,
    dialog_textviewer,
    dialog_yesno,
    get_setting_bool,
    get_string,
    show_notification,
    translate_path,
)
from ..common.logger import debug, error, info
from .base_tool import BaseTool, ToolRegistry


@ToolRegistry.register
class LogCleanerTool(BaseTool):
    id = "log_cleaner"
    title_id = 30005
    description_id = 30501
    icon = "DefaultAddonInfo.png"
    order = 50

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(30005, "Clear Kodi Logs")
        info("Initiating Kodi Log Cleaner Tool")

        log_dir = self._get_log_dir()
        log_files = self._find_log_files(log_dir)

        if not log_files:
            dialog_ok(title, get_string(30507, "No log files found."))
            return

        total_size = sum(f["size"] for f in log_files)
        total_size_fmt = self._format_size(total_size)

        options = [
            f"1. {get_string(30502, 'View Kodi Log')}",
            f"2. {get_string(30503, 'Clear Current Log (kodi.log)')}",
            f"3. {get_string(30504, 'Clear All Logs (including old/crash logs)')} [{total_size_fmt}]",
        ]

        action_idx = dialog_select(f"{title} ({total_size_fmt})", options)
        if action_idx == 0:
            self._view_active_log(log_files)
        elif action_idx == 1:
            self._clear_active_log(title, log_files)
        elif action_idx == 2:
            self._clear_all_logs(title, log_files)

    def _get_log_dir(self) -> str:
        """Locate the directory where Kodi stores logs."""
        log_path = translate_path("special://logpath/")
        if not os.path.isdir(log_path):
            home_path = translate_path("special://home/")
            log_path = home_path
        return log_path

    def _find_log_files(self, log_dir: str) -> List[Dict]:
        """Find all Kodi log and crashlog files in the log directory."""
        candidates = ["kodi.log", "kodi.old.log", "spmc.log", "spmc.old.log"]
        results = []

        for name in candidates:
            fpath = os.path.join(log_dir, name)
            if os.path.isfile(fpath):
                results.append({
                    "name": name,
                    "path": fpath,
                    "size": os.path.getsize(fpath),
                    "is_active": name == "kodi.log",
                })

        # Crashlogs
        crash_patterns = [os.path.join(log_dir, "kodi_crashlog*"), os.path.join(log_dir, "*crashlog*.log")]
        for pattern in crash_patterns:
            for cpath in glob.glob(pattern):
                if os.path.isfile(cpath) and not any(r["path"] == cpath for r in results):
                    results.append({
                        "name": os.path.basename(cpath),
                        "path": cpath,
                        "size": os.path.getsize(cpath),
                        "is_active": False,
                    })

        return results

    def _format_size(self, num_bytes: int) -> str:
        if num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.1f} KB"
        else:
            return f"{num_bytes / (1024 * 1024):.2f} MB"

    def _view_active_log(self, log_files: List[Dict], max_lines: int = 300) -> None:
        active = next((f for f in log_files if f["is_active"]), log_files[0] if log_files else None)
        if not active:
            return

        lines = []
        try:
            with open(active["path"], "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            dialog_ok(get_string(30501, "Kodi Log Manager"), get_string(30509, "Failed to read log: %s") % str(e))
            return

        tail_lines = lines[-max_lines:]
        content = "".join(tail_lines)
        header = f"--- {active['name']} (Last {len(tail_lines)} lines, Total size: {self._format_size(active['size'])}) ---\n"
        dialog_textviewer(f"Kodi Log: {active['name']}", header + content)

    def _clear_active_log(self, title: str, log_files: List[Dict]) -> None:
        active = next((f for f in log_files if f["is_active"]), None)
        if not active:
            dialog_ok(title, get_string(30507, "No log files found."))
            return

        confirm_msg = get_string(30505, "Are you sure you want to clear Kodi logs?")
        if not dialog_yesno(title, confirm_msg):
            return

        backup = get_setting_bool("log_backup_before_clear", True)
        if backup:
            try:
                shutil.copy2(active["path"], active["path"] + ".bak")
            except Exception as e:
                debug(f"Log backup failed: {e}")

        freed = active["size"]
        try:
            with open(active["path"], "w", encoding="utf-8") as f:
                f.write("[SystemTools] Log truncated by Kodi System Toolbox.\n")
            msg = get_string(30506, "Logs cleared successfully (%s freed).") % self._format_size(freed)
            show_notification(title, msg)
        except Exception as e:
            error(f"Failed to truncate log {active['path']}: {e}")
            dialog_ok(title, get_string(30510, "Failed to clear log: %s") % str(e))

    def _clear_all_logs(self, title: str, log_files: List[Dict]) -> None:
        confirm_msg = get_string(30505, "Are you sure you want to clear Kodi logs?")
        if not dialog_yesno(title, confirm_msg):
            return

        freed_bytes = 0
        backup = get_setting_bool("log_backup_before_clear", True)

        for f in log_files:
            try:
                if f["is_active"]:
                    if backup:
                        try:
                            shutil.copy2(f["path"], f["path"] + ".bak")
                        except Exception:
                            pass
                    freed_bytes += f["size"]
                    with open(f["path"], "w", encoding="utf-8") as fl:
                        fl.write("[SystemTools] Log truncated by Kodi System Toolbox.\n")
                else:
                    freed_bytes += f["size"]
                    os.remove(f["path"])
            except Exception as e:
                error(f"Failed to remove/truncate {f['path']}: {e}")

        msg = get_string(30506, "Logs cleared successfully (%s freed).") % self._format_size(freed_bytes)
        show_notification(title, msg)

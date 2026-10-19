# -*- coding: utf-8 -*-
"""Tool: CoreELEC Daily Auto Reboot via systemd timers."""

import os
import re
from typing import Dict, Optional

from ..common.kodi_ui import (
    dialog_numeric,
    dialog_ok,
    dialog_select,
    get_string,
)
from ..common.logger import error, info
from ..common.os_detect import OSType, get_system_info
from ..common.system_exec import run_command
from .base_tool import BaseTool, ToolRegistry

DEFAULT_SYSTEMD_DIR = "/storage/.config/system.d"
DEFAULT_CONFIG_DIR = "/storage/.config"


@ToolRegistry.register
class AutoRebootTool(BaseTool):
    id = "auto_reboot"
    title_id = 31500
    description_id = 31501
    icon = "DefaultPower.png"
    order = 35

    def __init__(self, systemd_dir: str = DEFAULT_SYSTEMD_DIR, config_dir: str = DEFAULT_CONFIG_DIR):
        self.systemd_dir = systemd_dir
        self.config_dir = config_dir
        self.service_file = os.path.join(self.systemd_dir, "daily-reboot.service")
        self.timer_file = os.path.join(self.systemd_dir, "daily-reboot.timer")

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(self.title_id, "Daily Auto Reboot")
        info("Auto Reboot Tool invoked")

        sys_info = get_system_info()
        if sys_info.os_type not in (OSType.COREELEC, OSType.LIBREELEC) and not os.path.exists(self.config_dir):
            dialog_ok(title, get_string(31412, "This feature is only supported on CoreELEC systems."))
            return

        current_time = self._get_current_time()
        if current_time:
            status_text = f"[COLOR green]{get_string(31503, 'Enabled (Daily at %s)') % current_time}[/COLOR]"
        else:
            status_text = f"[COLOR gray]{get_string(31504, 'Disabled')}[/COLOR]"

        options = [
            f"1. {get_string(31505, '1. Set / Change Auto Reboot Time')}",
            f"2. {get_string(31506, '2. Disable Daily Auto Reboot')}",
        ]

        header = get_string(31502, "Daily Auto Reboot - Status: %s") % status_text
        idx = dialog_select(header, options)

        if idx == 0:
            self._set_timer(title, current_time)
        elif idx == 1:
            self._disable_timer(title)

    def _get_current_time(self) -> Optional[str]:
        """Parse timer file to extract current scheduled time (HH:MM)."""
        if not os.path.exists(self.timer_file):
            return None
        try:
            with open(self.timer_file, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r"OnCalendar=.*?(\d{1,2}:\d{2})", content)
                if match:
                    time_str = match.group(1)
                    if len(time_str) == 4:
                        time_str = "0" + time_str
                    return time_str
        except Exception as e:
            error(f"Failed to read timer file: {e}")
        return None

    def _set_timer(self, title: str, current_time: Optional[str]) -> None:
        default_time = current_time if current_time else "04:00"
        prompt = get_string(31507, "Set daily auto reboot time:")
        time_str = dialog_numeric(2, prompt, default=default_time)

        if not time_str:
            return

        os.makedirs(self.systemd_dir, exist_ok=True)

        service_content = """[Unit]
Description=Daily Auto Reboot Service
After=network-online.target time-sync.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'UPTIME=$(cut -d. -f1 /proc/uptime); if [ "$UPTIME" -gt 600 ]; then /usr/sbin/reboot; else echo "Uptime too short (<10m), skipping reboot."; fi'
"""

        timer_content = f"""[Unit]
Description=Daily Auto Reboot Timer

[Timer]
OnCalendar=*-*-* {time_str}:00
Persistent=false

[Install]
WantedBy=timers.target
"""
        try:
            with open(self.service_file, "w", encoding="utf-8") as f:
                f.write(service_content)
            with open(self.timer_file, "w", encoding="utf-8") as f:
                f.write(timer_content)

            run_command("systemctl daemon-reload")
            run_command("systemctl enable daily-reboot.timer")
            run_command("systemctl restart daily-reboot.timer")

            success_msg = get_string(31508, "Auto reboot configured! System will reboot daily at %s.") % f"[COLOR yellow]{time_str}[/COLOR]"
            dialog_ok(title, success_msg)
        except Exception as e:
            error(f"Failed to set auto reboot: {e}")
            fail_msg = get_string(31511, "Failed to configure auto reboot: %s") % str(e)
            dialog_ok(title, fail_msg)

    def _disable_timer(self, title: str) -> None:
        if not os.path.exists(self.timer_file):
            dialog_ok(title, get_string(31510, "Daily auto reboot is not enabled currently."))
            return

        try:
            run_command("systemctl stop daily-reboot.timer")
            run_command("systemctl disable daily-reboot.timer")

            if os.path.exists(self.service_file):
                os.remove(self.service_file)
            if os.path.exists(self.timer_file):
                os.remove(self.timer_file)

            run_command("systemctl daemon-reload")
            dialog_ok(title, get_string(31509, "Daily auto reboot disabled successfully."))
        except Exception as e:
            error(f"Failed to disable auto reboot: {e}")
            fail_msg = get_string(31511, "Failed to configure auto reboot: %s") % str(e)
            dialog_ok(title, fail_msg)

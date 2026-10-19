# -*- coding: utf-8 -*-
"""Subprocess execution and system command helpers."""

import subprocess
import sys

from .logger import debug, error, info


def run_command(cmd, timeout=15):
    """Safely run a system shell/binary command and return (returncode, stdout, stderr)."""
    try:
        debug(f"Executing system command: {cmd}")
        process = subprocess.Popen(
            cmd,
            shell=isinstance(cmd, str),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout.strip(), stderr.strip()
    except subprocess.TimeoutExpired:
        process.kill()
        error(f"Command timed out after {timeout}s: {cmd}")
        return -1, "", "Command timed out"
    except Exception as e:
        error(f"Command execution error: {e}")
        return -1, "", str(e)


def execute_reboot(mode="normal"):
    """Trigger system reboot based on requested mode.

    Modes:
      - 'normal': regular reboot
      - 'android': reboot from CoreELEC/LibreELEC to Android
      - 'coreelec': reboot from Android to CoreELEC (reboot update)
      - 'recovery': reboot into recovery mode
      - 'poweroff': shut down the device
    """
    info(f"Initiating system reboot with mode: {mode}")

    # CoreELEC / LibreELEC rebooting to internal Android
    if mode == "android":
        candidates = [
            "/usr/sbin/rebootfromnand",
            "systemctl start reboot-to-android",
            "reboot to-android",
        ]
        for cmd in candidates:
            code, out, err = run_command(cmd)
            if code == 0:
                return True, out

        # Fallback using fw_setenv or u-boot flags if available
        code, _, _ = run_command("reboot -f")
        return code == 0, ""

    elif mode == "coreelec":
        # Android to CoreELEC/Recovery via reboot update
        code, out, err = run_command("reboot update")
        if code != 0:
            code, out, err = run_command("su -c 'reboot update'")
        return code == 0, out

    elif mode == "recovery":
        code, out, err = run_command("reboot recovery")
        if code != 0:
            code, out, err = run_command("su -c 'reboot recovery'")
        return code == 0, out

    elif mode == "poweroff":
        # Try Kodi built-in first
        try:
            import xbmc
            xbmc.shutdown()
            return True, ""
        except Exception:
            code, out, err = run_command("poweroff")
            return code == 0, out

    else:  # normal reboot
        try:
            import xbmc
            xbmc.restart()
            return True, ""
        except Exception:
            code, out, err = run_command("reboot")
            return code == 0, out

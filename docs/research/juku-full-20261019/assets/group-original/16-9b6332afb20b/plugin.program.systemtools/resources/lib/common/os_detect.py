# -*- coding: utf-8 -*-
"""OS and hardware platform detection for Kodi."""

import os
import platform
import sys

from .logger import debug


class OSType:
    COREELEC = "CoreELEC"
    LIBREELEC = "LibreELEC"
    ANDROID = "Android"
    LINUX = "Linux"
    WINDOWS = "Windows"
    DARWIN = "macOS"
    UNKNOWN = "Unknown"


class SystemInfo:
    def __init__(self):
        self.os_type = self._detect_os()
        self.arch = platform.machine()
        self.soc = self._detect_soc()
        self.dual_boot_supported = self._check_dual_boot_support()

    def _detect_os(self):
        # 1. Android check
        if hasattr(sys, "getandroidapilevel") or "ANDROID_STORAGE" in os.environ:
            return OSType.ANDROID

        # 2. /etc/os-release check for CoreELEC / LibreELEC
        os_release = "/etc/os-release"
        if os.path.isfile(os_release):
            try:
                with open(os_release, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()
                    if "coreelec" in content:
                        return OSType.COREELEC
                    elif "libreelec" in content:
                        return OSType.LIBREELEC
            except Exception:
                pass

        # 3. Check /etc/issue or /etc/release
        for fpath in ["/etc/issue", "/etc/release"]:
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        txt = f.read().lower()
                        if "coreelec" in txt:
                            return OSType.COREELEC
                        elif "libreelec" in txt:
                            return OSType.LIBREELEC
                except Exception:
                    pass

        # 4. Standard platform checks
        system = platform.system()
        if system == "Windows":
            return OSType.WINDOWS
        elif system == "Darwin":
            return OSType.DARWIN
        elif system == "Linux":
            return OSType.LINUX

        return OSType.UNKNOWN

    def _detect_soc(self):
        """Attempt to identify SoC (e.g. Amlogic, Rockchip, Allwinner, Raspberry Pi)."""
        soc = "Generic"
        cpuinfo = "/proc/cpuinfo"
        if os.path.isfile(cpuinfo):
            try:
                with open(cpuinfo, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()
                    if "amlogic" in content or "meson" in content:
                        soc = "Amlogic"
                    elif "rockchip" in content or "rk3" in content:
                        soc = "Rockchip"
                    elif "allwinner" in content or "sunxi" in content:
                        soc = "Allwinner"
                    elif "bcm2" in content or "raspberry" in content:
                        soc = "Raspberry Pi"
            except Exception:
                pass

        # Check device tree model
        dt_model = "/proc/device-tree/model"
        if os.path.isfile(dt_model):
            try:
                with open(dt_model, "r", encoding="utf-8", errors="ignore") as f:
                    model = f.read().strip("\x00\r\n ")
                    if model:
                        soc = f"{soc} ({model})"
            except Exception:
                pass

        return soc

    def _check_dual_boot_support(self):
        """Check if dual-boot switching commands/files exist."""
        # CoreELEC / LibreELEC reboot to internal/Android scripts
        reboot_scripts = [
            "/usr/sbin/rebootfromnand",
            "/usr/sbin/reboot-to-android",
            "/system/bin/reboot",
        ]
        for s in reboot_scripts:
            if os.path.isfile(s) and os.access(s, os.X_OK):
                return True

        if self.os_type in (OSType.COREELEC, OSType.LIBREELEC, OSType.ANDROID):
            return True

        return False

    def to_dict(self):
        return {
            "os_type": self.os_type,
            "arch": self.arch,
            "soc": self.soc,
            "dual_boot_supported": self.dual_boot_supported,
        }

    def __str__(self):
        return f"{self.os_type} ({self.arch}, {self.soc})"


_cached_info = None


def get_system_info():
    global _cached_info
    if _cached_info is None:
        _cached_info = SystemInfo()
    return _cached_info

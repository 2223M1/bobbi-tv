# -*- coding: utf-8 -*-
"""Logger utility for System Tools addon.

Safely delegates to Kodi's xbmc.log when running in Kodi,
or standard library logging when running standalone / in unit tests.
"""

import sys

ADDON_ID = "plugin.program.systemtools"

try:
    import xbmc
    _HAS_XBMC = True
    LOG_DEBUG = xbmc.LOGDEBUG
    LOG_INFO = xbmc.LOGINFO
    LOG_WARNING = xbmc.LOGWARNING
    LOG_ERROR = xbmc.LOGERROR
except ImportError:
    _HAS_XBMC = False
    LOG_DEBUG = 0
    LOG_INFO = 1
    LOG_WARNING = 2
    LOG_ERROR = 3


def log(msg, level=LOG_INFO):
    """Log a message with the addon identifier prefix."""
    formatted = f"[{ADDON_ID}] {msg}"
    if _HAS_XBMC:
        xbmc.log(formatted, level=level)
    else:
        sys.stderr.write(f"{formatted}\n")


def debug(msg):
    log(msg, level=LOG_DEBUG)


def info(msg):
    log(msg, level=LOG_INFO)


def warning(msg):
    log(msg, level=LOG_WARNING)


def error(msg):
    log(msg, level=LOG_ERROR)

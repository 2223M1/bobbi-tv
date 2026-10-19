# -*- coding: utf-8 -*-
"""Kodi System Tools Addon Entry Point.

Main entry point for plugin.program.systemtools.
Dispatches commands based on Kodi URL parameters.
"""

import os
import sys

# Ensure addon root and resources/lib are in sys.path
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

LIB_DIR = os.path.join(ADDON_DIR, "resources", "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from resources.lib.router import route

if __name__ == "__main__":
    route(sys.argv)

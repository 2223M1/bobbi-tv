"""Compatibility alias: no duplicate state or implementation."""
from lib.cinema import _shared  # dependency bootstrap
from importlib import import_module as _import_module
import sys as _sys
_sys.modules[__name__] = _import_module('bobbi_core.release_font_loader')

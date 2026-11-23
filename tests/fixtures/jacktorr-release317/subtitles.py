"""Compatibility alias for the one shared same-torrent subtitle implementation."""
from importlib import import_module
import sys

_implementation = import_module('bobbi_core.torrent_subtitles')
# exec_module callers retain the original module object; export the same functions
# there as well. Normal imports alias the implementation, including its globals.
globals().update({name: value for name, value in vars(_implementation).items()
                  if not name.startswith('__')})
sys.modules[__name__] = _implementation

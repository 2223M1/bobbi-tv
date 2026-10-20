"""Add-on string lookup, so every user-visible message lives in the language files.

Kodi resolves add-on strings from ``resources/language/resource.language.<lang>/
strings.po``.  Skin XML can reference the same entries with
``$ADDON[script.voice.inputmethod <id>]``.
"""
import xbmcaddon

ADDON_ID = 'script.voice.inputmethod'

_cache = {}


def text(string_id, *args):
    """Return the localized string, formatting positional arguments if given."""
    value = _cache.get(string_id)
    if value is None:
        value = xbmcaddon.Addon(ADDON_ID).getLocalizedString(string_id)
        _cache[string_id] = value
    return value.format(*args) if args else value

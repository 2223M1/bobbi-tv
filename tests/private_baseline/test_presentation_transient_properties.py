"""Real property helpers keep presentation labels out of persistent storage."""
import ast
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


SOURCE = (Path(__file__).resolve().parents[2]
          / 'addons/plugin.video.bobbi/lib/utils/kodi/utils.py')
PRESENTATION_PROPERTIES = (
    'bobbi_cinema_started',
    'bobbi_cinema_handoff',
    'bobbi_cinema_presentation_status',
)


def load_property_api(window, cache):
    """Load actual property functions; only Kodi/cache IO is supplied by callers.

    Return an object with get_property, set_property, clear_property and the
    production TRANSIENT_PLAYBACK_PROPERTIES. ``window`` is the Window(10000)
    object, not a factory. The loaded functions share their own globals, so a
    test may mutate that namespace for an in-memory negative control.
    """
    functions = {'get_property', 'set_property', 'clear_property'}
    original = ast.parse(SOURCE.read_text(encoding='utf-8'))
    selected = []
    for node in original.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
        elif (isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name)
                      and target.id == 'TRANSIENT_PLAYBACK_PROPERTIES'
                      for target in node.targets)):
            selected.append(node)
    assert len(selected) == len(functions) + 1, 'Production property API changed'

    def home_window(identifier):
        assert identifier == 10000
        return window

    scope = dict(Window=home_window, cache=cache, timedelta=timedelta, Any=Any,
                 xbmc=SimpleNamespace(LOGDEBUG=0), kodilog=lambda *a, **kw: None)
    tree = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(tree, str(SOURCE), 'exec'), scope)
    return SimpleNamespace(**{name: scope[name] for name in
                              functions | {'TRANSIENT_PLAYBACK_PROPERTIES'}})


class MemoryWindow:
    def __init__(self):
        self.values = {}

    def getProperty(self, key):
        return self.values.get(key, '')

    def setProperty(self, key, value):
        self.values[key] = value

    def clearProperty(self, key):
        self.values.pop(key, None)


class RecordingCache:
    def __init__(self):
        self.values, self.calls = {}, []

    def get(self, key):
        self.calls.append(('get', key))
        return self.values.get(key)

    def set(self, key, value, expires):
        self.calls.append(('set', key, value, expires))
        self.values[key] = value

    def delete(self, key):
        self.calls.append(('delete', key))
        self.values.pop(key, None)


@pytest.mark.parametrize('key', PRESENTATION_PROPERTIES)
def test_presentation_labels_set_get_clear_never_touch_persistent_cache(key):
    window, cache = MemoryWindow(), RecordingCache()
    cache.values[key] = 'stale previous session'
    api = load_property_api(window, cache)

    # Empty Window state cannot resurrect an earlier process's cached label.
    assert api.get_property(key) is None
    api.set_property(key, 'current session')
    assert window.getProperty(key) == 'current session'
    assert api.get_property(key) == 'current session'
    api.clear_property(key)
    assert window.getProperty(key) == ''
    assert api.get_property(key) is None
    assert cache.calls == []
    assert cache.values[key] == 'stale previous session'


def test_ordinary_property_preserves_persistent_set_fallback_and_delete():
    window, cache = MemoryWindow(), RecordingCache()
    api = load_property_api(window, cache)
    key = 'ordinary_persistent_setting'
    assert key not in api.TRANSIENT_PLAYBACK_PROPERTIES

    api.set_property(key, 'saved value')
    assert window.getProperty(key) == 'saved value'
    assert cache.calls == [('set', key, 'saved value', timedelta(days=30))]
    assert api.get_property(key) == 'saved value'
    assert len(cache.calls) == 1  # A populated Window does not need a fallback.
    window.clearProperty(key)
    assert api.get_property(key) == 'saved value'
    assert cache.calls[-1] == ('get', key)
    api.clear_property(key)
    assert cache.calls[-1] == ('delete', key)
    assert window.getProperty(key) == '' and key not in cache.values
    assert api.get_property(key) is None
    assert cache.calls[-1] == ('get', key)


@pytest.mark.parametrize('key', PRESENTATION_PROPERTIES)
def test_removing_presentation_exemption_restores_synchronous_cache_write(key):
    window, cache = MemoryWindow(), RecordingCache()
    api = load_property_api(window, cache)
    scope = api.set_property.__globals__
    scope['TRANSIENT_PLAYBACK_PROPERTIES'] = (
        scope['TRANSIENT_PLAYBACK_PROPERTIES'] - frozenset(PRESENTATION_PROPERTIES))

    # Negative control changes only this extracted function namespace. It proves
    # the cache spy observes the real disk-write branch, rather than bypassing it.
    api.set_property(key, 'negative control')
    assert window.getProperty(key) == 'negative control'
    assert cache.calls == [('set', key, 'negative control', timedelta(days=30))]

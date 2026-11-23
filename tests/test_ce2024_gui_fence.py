"""Model Omega GUI dispatch separately from the calling Python interpreter."""
import re
import sys
from types import SimpleNamespace

import pytest
from bobbi_platform import ce_install_ui as ui


@pytest.mark.parametrize('mode', ['normal', 'lost', 'abort', 'late'])
def test_refresh_never_holds_python_lock_waiting_for_gui(monkeypatch, mode):
    props, queued, delivered, clears = {}, [], [], []
    clock = [0.0]
    monkeypatch.setattr(ui.time, 'monotonic', lambda: clock[0])
    def submit(command, wait=False):
        assert wait is False, 'Omega synchronous builtin blocks addon-stop GIL acquisition'
        queued.append(command)
    def release_python_lock(delay):
        clock[0] += delay
        if mode == 'abort':
            return True
        if mode == 'normal':
            while queued:
                command = queued.pop(0)
                delivered.append(command)
                if command.startswith('SetProperty('):
                    key = re.fullmatch(r'SetProperty\(([^,]+),ready,10000\)', command)[1]
                    props[key] = 'ready'
        return False
    def clear(key):
        clears.append(key)
        props.pop(key, None)
    window = SimpleNamespace(getProperty=lambda key: props.get(key, ''), clearProperty=clear)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Window=lambda identifier: window))
    host = ui.KodiHost.__new__(ui.KodiHost)
    host.xbmc = SimpleNamespace(executebuiltin=submit)
    host.monitor = SimpleNamespace(waitForAbort=release_python_lock)
    if mode == 'normal':
        host.refresh()
        assert delivered[0] == 'UpdateLocalAddons'
        assert clock[0] > 0 and len(delivered) == 2
    else:
        with pytest.raises(ui.UpdateError, match='ADDON_REFRESH_'):
            host.refresh()
        assert clock[0] <= 15.1
    assert len(clears) == 1 and not props
    if mode == 'late':
        # A late fence from the previous call cannot complete a new call.
        old = re.fullmatch(r'SetProperty\(([^,]+),ready,10000\)', queued[-1])[1]
        props[old] = 'ready'
        with pytest.raises(ui.UpdateError, match='NOT_CONFIRMED'):
            host.refresh()
        assert clears[-1] != old


def test_dependency_install_does_not_use_blocking_builtin():
    from pathlib import Path
    source = Path(ui.__file__).read_text(encoding='utf-8')
    assert "executebuiltin('InstallAddon(%s)' % name, False)" in source
    assert "executebuiltin('InstallAddon(%s)' % name, True)" not in source

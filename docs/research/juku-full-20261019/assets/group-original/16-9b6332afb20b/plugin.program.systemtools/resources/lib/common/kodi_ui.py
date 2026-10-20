# -*- coding: utf-8 -*-
"""Kodi UI helper wrappers for System Tools addon."""

import os
from contextlib import contextmanager

from .logger import ADDON_ID, log, LOG_ERROR

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcvfs
    _HAS_XBMC = True
except ImportError:
    _HAS_XBMC = False
    xbmc = None
    xbmcaddon = None
    xbmcgui = None
    xbmcvfs = None


_addon_instance = None


def get_addon():
    """Retrieve or cache the xbmcaddon.Addon instance."""
    global _addon_instance
    if _addon_instance is None and _HAS_XBMC:
        _addon_instance = xbmcaddon.Addon(ADDON_ID)
    return _addon_instance


def get_string(string_id, default=""):
    """Retrieve localized string from language strings.po by ID."""
    addon = get_addon()
    if addon:
        try:
            val = addon.getLocalizedString(string_id)
            if val:
                return val
        except Exception as e:
            log(f"Failed to get string {string_id}: {e}", level=LOG_ERROR)
    return default or f"#{string_id}"


def get_setting(setting_id, default=""):
    """Retrieve addon setting value."""
    addon = get_addon()
    if addon:
        return addon.getSetting(setting_id)
    return default


def get_setting_int(setting_id, default=0):
    """Retrieve integer addon setting value."""
    addon = get_addon()
    if addon:
        try:
            return addon.getSettingInt(setting_id)
        except Exception:
            try:
                return int(addon.getSetting(setting_id))
            except Exception:
                pass
    return default


def get_setting_bool(setting_id, default=False):
    """Retrieve boolean addon setting value."""
    addon = get_addon()
    if addon:
        try:
            return addon.getSettingBool(setting_id)
        except Exception:
            val = str(addon.getSetting(setting_id)).lower()
            return val in ("true", "1", "yes")
    return default


def dialog_ok(title, message):
    """Show an alert/info dialog with OK button."""
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        dialog.ok(title, message)
    else:
        print(f"[{title}] {message}")


def dialog_yesno(title, message, yeslabel=None, nolabel=None):
    """Show a confirmation Yes/No dialog. Returns True if confirmed."""
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        kwargs = {}
        if yeslabel:
            kwargs["yeslabel"] = yeslabel
        if nolabel:
            kwargs["nolabel"] = nolabel
        return dialog.yesno(title, message, **kwargs)
    return True


def dialog_select(title, items):
    """Show a single-selection list dialog. Returns selected index (-1 on cancel)."""
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        return dialog.select(title, items)
    return 0 if items else -1


def dialog_select_details(title, items, preselect=-1):
    """Single-selection dialog that renders icons and a second text line.

    ``useDetails=True`` (Kodi 18+) makes the built-in dialog show
    ``ListItem`` label / label2 / art.
    Older Kodi builds that do not support the keyword argument fall back gracefully.
    """
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        try:
            return dialog.select(title, items, preselect=preselect, useDetails=True)
        except TypeError:
            return dialog.select(title, items)
    return 0 if items else -1


def dialog_input(title, default=""):
    """Show text input dialog. Returns entered string (empty on cancel)."""
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        return dialog.input(title, default)
    return default


def dialog_numeric(type_code, heading, default=""):
    """Show numeric or time dialog (type_code: 0=standard, 1=date, 2=time, 3=ip)."""
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        return dialog.numeric(type_code, heading, default)
    return default


def dialog_browse(type_code, heading, shares="", mask="", use_thumbs=False, treat_as_folder=False, default_path=""):
    """Show file / folder browser dialog."""
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        # type_code: 0 = ShowAndGetDirectory, 1 = ShowAndGetFile, 2 = ShowAndGetImage, 3 = ShowAndGetWriteableDirectory
        # shares: "" exposes both local drives and network shares (SMB, NFS, etc.)
        if hasattr(dialog, "browseSingle"):
            return dialog.browseSingle(type_code, heading, shares, mask, use_thumbs, treat_as_folder, default_path)
        return dialog.browse(type_code, heading, shares, mask, use_thumbs, treat_as_folder, default_path)
    return default_path


def dialog_textviewer(title, text):
    """Show a large text viewing dialog."""
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        dialog.textviewer(title, text)
    else:
        print(f"--- {title} ---\n{text}\n-----------------")


def show_notification(title, message, icon="", time_ms=3000):
    """Show Kodi system toast notification."""
    if _HAS_XBMC and xbmcgui:
        dialog = xbmcgui.Dialog()
        dialog.notification(title, message, icon=icon, time=time_ms)
    else:
        print(f"[Notification] {title}: {message}")


@contextmanager
def progress_dialog(heading, message=""):
    """Context manager for xbmcgui.DialogProgress.

    Yields a helper with:
      - update(percent, message=None)
      - is_canceled() -> bool
    """
    if _HAS_XBMC and xbmcgui:
        dp = xbmcgui.DialogProgress()
        dp.create(heading, message)

        class ProgressWrapper:
            def __init__(self, dialog):
                self._dialog = dialog

            def update(self, percent, message=None):
                if message is not None:
                    self._dialog.update(int(percent), message)
                else:
                    self._dialog.update(int(percent))

            def is_canceled(self):
                return self._dialog.iscanceled()

        try:
            yield ProgressWrapper(dp)
        finally:
            dp.close()
    else:
        class DummyProgress:
            def update(self, percent, message=None):
                pass

            def is_canceled(self):
                return False

        yield DummyProgress()


def translate_path(path):
    """Safely translate special:// protocol paths to OS absolute paths."""
    if _HAS_XBMC and xbmcvfs:
        return xbmcvfs.translatePath(path)
    elif _HAS_XBMC and hasattr(xbmc, "translatePath"):
        return xbmc.translatePath(path)
    return os.path.abspath(path)

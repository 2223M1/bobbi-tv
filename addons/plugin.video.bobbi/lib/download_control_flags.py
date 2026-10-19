"""Download stop signals are control state, never an evictable value cache.

Stop and explicit-cancel properties use full destination keys, with no TTL,
slot collisions, cache index or cache generation. Explicit start/resume clears
both; completion removes only the ordinary stop signal. These are control
signals, not another download owner.
"""
import xbmcgui


class DownloadControlFlags:
    _PREFIX = "plugin.video.bobbi.download.stop.v1."
    _CANCEL_PREFIX = "plugin.video.bobbi.download.cancel.v1."

    def __init__(self):
        self._window = xbmcgui.Window(10000)

    def _property_key(self, key):
        # Kodi compares Window property names without case. Full lowercase hex
        # is injective even under that comparison; mixed-case base64 is not.
        return self._PREFIX + key.encode("utf-8").hex()

    def get(self, key):
        return self._window.getProperty(self._property_key(key)) == "true" or self.cancelled(key)

    def cancelled(self, key):
        return self._window.getProperty(self._CANCEL_PREFIX + key.encode("utf-8").hex()) == "true"

    def cancel(self, key):
        # Persist the reason before the generic stop. Metadata and process-local
        # registries may race; neither may turn explicit cancellation into pause.
        self._window.setProperty(self._CANCEL_PREFIX + key.encode("utf-8").hex(), "true")
        self.set(key, True)

    def set(self, key, value):
        if value is True:
            self._window.setProperty(self._property_key(key), "true")
        else:
            # False is an explicit start/resume. Ordinary completion deletes
            # only the generic stop property, never a concurrent cancel reason.
            self._window.clearProperty(self._CANCEL_PREFIX + key.encode("utf-8").hex())
            self.delete(key)

    def delete(self, key):
        self._window.clearProperty(self._property_key(key))

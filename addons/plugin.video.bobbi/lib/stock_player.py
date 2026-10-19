"""Non-owning stock-Kodi adapter; the old native player is not a fallback."""
from threading import Event
from bobbi_platform.kodi import standard_handoff
from bobbi_platform.playback import selected_identity


class JacktookPLayer:
    """Keep importer compatibility, without pretending native receipt support."""
    def __init__(self, on_started=None, on_error=None, cancel_event=None,
                 on_progress=None, on_handoff=None, **kwargs):
        self._cinema_cancel = cancel_event or Event()
        self._resolution_answered = False
        self._handoff_confirmed = False
        self._startup_failure_category = None
        self._cinema_prepare_intent = None
        self.on_error = on_error

    def run(self, data):
        from lib.utils.kodi.utils import ADDON_HANDLE
        if self._cinema_cancel.is_set():
            return
        if data.get('selection_policy') != 'portable_manual':
            raise RuntimeError('请返回 bobbi 手动选择片源；通用版不接管旧的自动播放请求。')
        identity = selected_identity(data.get('url'))
        handle = -1 if data.get('direct_playback_handoff') else int(ADDON_HANDLE)
        handoff = standard_handoff(identity, handle, ready=lambda: not self._cinema_cancel.is_set())
        result = handoff.submit(identity, data)
        self._resolution_answered = result['opened']
        # No on_started/on_handoff callbacks: standard submission is not a
        # scoped AV-start or fullscreen confirmation. Kodi controls playback.

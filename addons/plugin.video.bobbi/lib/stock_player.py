"""Single standard handoff, observed by the resident StandardPlayback service."""
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
        from uuid import uuid4
        from bobbi_platform.runtime import call
        from lib.services.standard_playback import resolve_selected
        data = dict(data)
        request = data.get('request_id') or uuid4().hex
        account = data.get('_account') or call('account_status', {})
        data.update(request_id=request, _account=account, selection_policy='exact')
        call('standard_playback', dict(operation='select', request_id=request, account=account))
        call('standard_playback', dict(operation='subtitle_start', request_id=request, data=data))
        data = resolve_selected(data, self._cinema_cancel.is_set)
        result = call('standard_playback', dict(operation='register', request_id=request, data=data))
        if not result.get('accepted'):
            return
        if result.get('subtitles_path'):
            data['subtitles_path'] = result['subtitles_path']
        identity = selected_identity(data.get('url'))
        handle = -1 if data.get('direct_playback_handoff') else int(ADDON_HANDLE)
        handoff = standard_handoff(identity, handle, ready=lambda: not self._cinema_cancel.is_set()
            and call('standard_playback', dict(operation='current', request_id=request)).get('current') is True)
        result = handoff.submit(identity, data)
        self._resolution_answered = result['opened']
        # No on_started/on_handoff callbacks: standard submission is not a
        # scoped AV-start or fullscreen confirmation. Kodi controls playback.

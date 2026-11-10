"""Manual personal-file entry using the existing native/stock playback owner."""
from threading import Event, Thread
import re
import time

from bobbi_platform.pan_accounts import PanError, scope
from bobbi_platform.pan_stream import body as stream_body
from bobbi_platform.runtime import call


def play(params):
    import xbmc
    import xbmcgui
    from lib.native_support import available
    from lib.player import JacktookPLayer
    from bobbi_core.playback_request import context, data_identity, read_snapshot, select
    from bobbi_core.playback_ipc import call as owner_call
    from bobbi_platform.pan_ui import _failure

    ticket = params.get('ticket')
    if type(ticket) is not str or not re.fullmatch('[0-9a-f]{32}', ticket):
        return
    expected = owner = player = None
    native = False
    cancelled, monitor = Event(), xbmc.Monitor()
    progress = xbmcgui.DialogProgress()
    try:
        claimed = call('pan_claim_play', {'ticket': ticket})
        expected = scope(claimed['account'], authenticated=True)
        selected = claimed['selected']
        selected_body = stream_body(expected['provider'], selected, ticket)
        if claimed['request_id'] != ticket:
            raise PanError('PAN_SELECTION_INVALID')
        data = dict(request_id=ticket, _ui_reserved_request=ticket, _account=expected,
            _pan_file=True, _pan_locator=selected_body['locator'], url=selected_body['locator'],
            title=selected['name'], source_title=selected['name'], size=selected['size'],
            mode='file', ids={}, file_evidence='USER_CONFIRMED_FILE',
            selection_policy='exact', direct_playback_handoff=True)
        native = available()
        if native:
            owner = context(select(read_snapshot(), ticket, data_identity(data), account_scope=expected), ticket)
            data['_selection_context'] = owner
        else:
            call('standard_playback', dict(operation='select', request_id=ticket, account=expected))
        progress.create('正在打开原文件', '核对当前账号和所选文件，可按返回取消。')
        job = {}
        def resolve():
            try:
                job['reply'] = call('pan_open_stream', dict(expected=expected, selected=selected, request_id=ticket), timeout=28)
            except Exception as error:
                job['error'] = error
        worker = Thread(target=resolve, name='bobbi-pan-selected-file', daemon=True)
        worker.start()
        deadline = time.monotonic() + 29
        while worker.is_alive():
            if progress.iscanceled() or monitor.waitForAbort(.1) or time.monotonic() >= deadline:
                cancelled.set()
                return
        worker.join()
        if progress.iscanceled() or monitor.abortRequested():
            cancelled.set()
            return
        if 'error' in job:
            raise job['error']
        reply = job.get('reply', {})
        if (reply.get('state') != 'ready' or reply.get('request_id') != ticket or reply.get('account') != expected
                or reply.get('guid') != selected_body['guid'] or reply.get('media') != selected_body['media']
                or reply.get('bytes') != selected['size'] or type(reply.get('url')) is not str
                or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}/stream/[0-9a-f]{32}/video\.[a-z0-9]+', reply['url'])):
            raise PanError('PAN_REPLY_INVALID')
        data['url'] = reply['url']
        progress.close()
        # Native bind/claim and standard current checks revalidate the reserved
        # selection. Resolution finishing late never selects a fresh request.
        player = JacktookPLayer(cancel_event=cancelled)
        player.run(data)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        progress.close()
        xbmcgui.Dialog().ok('未打开网盘文件', _failure(error))
    finally:
        progress.close()
        if expected is not None and not (player and player._resolution_answered):
            cancelled.set()
            try:
                call('pan_close_stream', dict(expected=expected, request_id=ticket))
            except (OSError, ValueError, RuntimeError):
                pass
            try:
                if native and owner is not None:
                    owner_call(dict(owner, operation='cancel'))
                elif not native:
                    call('standard_playback', dict(operation='cancel', request_id=ticket))
            except (OSError, ValueError, RuntimeError):
                pass  # Scoped cancellation only; never global Stop/playlist changes.

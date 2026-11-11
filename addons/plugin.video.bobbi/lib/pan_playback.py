"""Manual personal-file entry using the existing native/stock playback owner."""
from threading import Event, Thread
import re
import time

from bobbi_platform.pan_accounts import PanError, scope
from bobbi_platform.pan_stream import body as stream_body
from bobbi_platform.runtime import call


def play(params, reservation=None):
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
        if reservation is not None:
            native, owner, expected = available(), reservation['owner'], reservation['account']
        claimed = call('pan_claim_play', {'ticket': ticket})
        expected = scope(claimed['account'], authenticated=True)
        selected = claimed['selected']
        selected_body = stream_body(expected['provider'], selected, ticket)
        if claimed['request_id'] != ticket:
            raise PanError('PAN_SELECTION_INVALID')
        if reservation is not None and reservation['account'] != expected:
            raise PanError('PAN_ACCOUNT_CHANGED')
        from bobbi_core.file_ref import locator, same_file
        file_ref = claimed.get('file_ref')
        stable_locator = locator(file_ref) if file_ref is not None else selected_body['locator']
        if reservation is not None:
            if file_ref is None or (reservation.get('object_id') is not None
                                   and reservation['object_id'] != file_ref['id']):
                raise PanError('PAN_FILE_CHANGED')
            if reservation.get('file_ref') is not None and not same_file(reservation['file_ref'], file_ref):
                raise PanError('PAN_FILE_CHANGED')
        data = dict(request_id=ticket, _ui_reserved_request=ticket, _account=expected,
            _pan_file=True, _pan_locator=stable_locator, url=stable_locator,
            title=selected['name'], source_title=selected['name'], size=selected['size'],
            mode='file', ids={}, file_evidence='USER_CONFIRMED_FILE',
            selection_policy='exact', direct_playback_handoff=True)
        if claimed.get('history') is not None:
            history = claimed['history']
            if (file_ref is None or type(history) is not dict
                    or set(history) != {'generation', 'session_id'}):
                raise PanError('PAN_REPLY_INVALID')
            data['_file_history'] = dict(history, file_ref=file_ref)
        if reservation is not None:
            data['_file_resume_position'] = reservation['position']
        native = available()
        if native:
            owner = (reservation['owner'] if reservation is not None else
                     context(select(read_snapshot(), ticket, data_identity(data), account_scope=expected), ticket))
            data['_selection_context'] = owner
        elif reservation is None:
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


def _prepare_ticket(action, body, request, title):
    """One bounded, cancelable UI wait shared by trusted history and indexed files."""
    import xbmc
    import xbmcgui
    progress, monitor, job = xbmcgui.DialogProgress(), xbmc.Monitor(), {}
    progress.create(title, '核验原账号与文件；可按返回取消。')
    def verify():
        try:
            job['reply'] = call(action, body, timeout=28)
        except Exception as error:
            job['error'] = error
    try:
        worker = Thread(target=verify, name='bobbi-file-verify', daemon=True)
        worker.start()
        deadline = time.monotonic() + 29
        while worker.is_alive():
            if progress.iscanceled() or monitor.waitForAbort(.1) or time.monotonic() >= deadline:
                return False
        worker.join()
        if progress.iscanceled() or monitor.abortRequested():
            return False
        if 'error' in job:
            raise job['error']
        if job.get('reply', {}).get('ticket') != request:
            raise PanError('PAN_REPLY_INVALID')
        return True
    finally:
        progress.close()


def _cancel_prepared(expected, request, native, owner):
    from bobbi_core.playback_ipc import call as owner_call
    if expected is None:
        return
    for action, body in (
        ('pan_cancel_operation', dict(expected=expected, operation_id=request)),
        ('pan_close_stream', dict(expected=expected, request_id=request))):
        try:
            call(action, body)
        except (OSError, ValueError, RuntimeError):
            pass
    try:
        if native and owner is not None:
            owner_call(dict(owner, operation='cancel'))
        elif not native:
            call('standard_playback', dict(operation='cancel', request_id=request))
    except (OSError, ValueError, RuntimeError):
        pass


def resume(params):
    """Reserve user intent before remote verification; routes carry only an ID."""
    import xbmc
    import xbmcgui
    from uuid import uuid4
    from lib.db.file_history import FileHistory
    from lib.native_support import available
    from bobbi_core.file_ref import locator
    from bobbi_core.playback_request import context, data_identity, read_snapshot, select
    from bobbi_platform.pan_ui import _failure

    identifier = params.get('history_id')
    if type(identifier) is not str or not re.fullmatch('[0-9a-f]{64}', identifier):
        return
    request, expected, owner = uuid4().hex, None, None
    handed, native = False, available()
    try:
        record = FileHistory().get(identifier)
        ref = record['file_ref']
        rows = call('pan_status', {})['providers']
        matches = [row for row in rows if row['provider'] == ref['provider']]
        if len(matches) != 1:
            raise PanError('PAN_LOGIN_REQUIRED')
        if matches[0]['account'].get('authenticated') is not True:
            raise PanError('PAN_LOGIN_REQUIRED')
        expected = scope(matches[0]['account'], authenticated=True)
        if expected['account_id'] != ref['account_id']:
            raise PanError('PAN_ACCOUNT_CHANGED')
        if native:
            identity = data_identity(dict(_pan_file=True, _pan_locator=locator(ref), url=locator(ref)))
            owner = context(select(read_snapshot(), request, identity, account_scope=expected), request)
        else:
            call('standard_playback', dict(operation='select', request_id=request, account=expected))
        if not _prepare_ticket('pan_prepare_history_play',
                dict(history_id=identifier, request_id=request), request, '继续观看原文件'):
            return
        reservation = dict(account=expected, owner=owner, file_ref=ref,
            position=0 if params.get('start_over') == 'true' else record['position'])
        play(dict(ticket=request), reservation=reservation)
        handed = True
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        label = ('本地记录暂不可用，请从“我的文件”重新选择。'
                 if str(error).startswith('FILE_HISTORY_') else _failure(error))
        xbmcgui.Dialog().ok('未恢复原文件', label)
    finally:
        if not handed:
            _cancel_prepared(expected, request, native, owner)


def indexed(params):
    """Reserve explicit user intent before IO; the index itself grants no playback right."""
    import xbmcgui
    from uuid import uuid4
    from lib.db.file_history import FileHistory
    from lib.native_support import available
    from lib.utils.views.personal_catalog import account_for
    from bobbi_core.playback_request import context, data_identity, read_snapshot, select
    from bobbi_platform.pan_ui import _failure
    identifier = params.get('object_id')
    if type(identifier) is not str or not re.fullmatch('[0-9a-f]{64}', identifier):
        return
    request, expected, owner = uuid4().hex, None, None
    native, handed = available(), False
    try:
        accounts = [scope(row['account'], authenticated=True) for row in call('pan_status', {})['providers']
                    if row['provider'] != '115' and row['account'].get('authenticated')]
        expected = account_for(params, accounts)
        position, history_ref = 0, None
        try:
            previous = FileHistory().get(identifier)
        except (ValueError, OSError, RuntimeError):
            previous = None
        if previous and previous['position'] > 0 and previous['completion_reason'] != 'NATURAL_EOF':
            choice = xbmcgui.Dialog().select('打开原文件', ['继续上次位置', '从头播放'])
            if choice not in (0, 1):
                return
            if choice == 0:
                position, history_ref = previous['position'], previous['file_ref']
        locator = 'bobbipan://%s/%s' % (expected['provider'], identifier)
        if native:
            identity = data_identity(dict(_pan_file=True, _pan_locator=locator, url=locator))
            owner = context(select(read_snapshot(), request, identity, account_scope=expected), request)
        else:
            call('standard_playback', dict(operation='select', request_id=request, account=expected))
        if not _prepare_ticket('catalog_prepare_play', dict(expected=expected, object_id=identifier,
                request_id=request, intent='play'), request, '正在核验片库原文件'):
            return
        play(dict(ticket=request), reservation=dict(account=expected, owner=owner,
            object_id=identifier, file_ref=history_ref, position=position))
        handed = True
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        labels = {'CATALOG_RECHECK_INCOMPLETE': '有限检查内未能确认原文件，请从“我的文件”回原目录选择。',
                  'CATALOG_SOURCE_UNAVAILABLE': '索引来源暂不可用，原文件与观看记录仍保留。',
                  'PAN_ACCOUNT_CHANGED': '账号已变化，请返回片库重新选择。'}
        xbmcgui.Dialog().ok('未打开片库文件', labels.get(str(error), _failure(error)))
    finally:
        if not handed:
            _cancel_prepared(expected, request, native, owner)

"""Manual personal-file entry using the existing native/stock playback owner."""
from threading import Event, Thread
from hashlib import sha256
import re
import time

from bobbi_platform.pan_accounts import PanError, scope
from bobbi_platform.pan_stream import body as stream_body


_CAPTURE_PLAYBACK = object()


def _entry_transport():
    from bobbi_platform.playback_client import capture_transport
    transport = capture_transport()
    status = transport[2]('status', {}, timeout=.25)
    adapter = status.get('playback_adapter') if type(status) is dict else None
    if adapter not in ('native', 'standard'):
        raise ValueError('PLAYBACK_ADAPTER_UNAVAILABLE')
    return transport, adapter


def _history_record(identifier, binding):
    from lib.db.file_history import FileHistory
    from lib.db.pickle_db import PickleDatabase
    binding.require_current()
    history = FileHistory(PickleDatabase(binding.root('plugin.video.bobbi')))
    result = history.get(identifier)
    binding.require_current()
    return result


def play(params, reservation=None, *, transport=_CAPTURE_PLAYBACK, playback_adapter=None):
    import xbmc
    import xbmcgui
    from lib.player import JacktookPLayer
    from bobbi_core.playback_request import context, data_identity
    from bobbi_platform.pan_ui import _failure

    ticket = params.get('ticket')
    if type(ticket) is not str or not re.fullmatch('[0-9a-f]{32}', ticket):
        return
    expected = owner = player = failure = None
    native = False
    call = None
    cancelled, monitor = Event(), xbmc.Monitor()
    progress = xbmcgui.DialogProgress()
    try:
        if transport is _CAPTURE_PLAYBACK:
            transport, playback_adapter = _entry_transport()
        if transport is None or playback_adapter not in ('native', 'standard'):
            raise ValueError('PLAYBACK_BINDING_UNAVAILABLE')
        binding, playback_client, call = transport
        read_snapshot, select, owner_call = playback_client.read_snapshot, playback_client.select, playback_client.call
        native = playback_adapter == 'native'
        if reservation is not None:
            owner, expected = reservation['owner'], reservation['account']
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
            if reservation['position'] == 0:
                data['_bobbi_start_over'] = True  # Override any Kodi bookmark for this path.
        if file_ref is not None:
            from bobbi_core.server_ref import resumable
            if not resumable(file_ref):
                data['_file_resume_position'] = 0
                data['_bobbi_start_over'] = True
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
            binding.require_current()
            if progress.iscanceled() or monitor.waitForAbort(.1) or time.monotonic() >= deadline:
                cancelled.set()
                return
        worker.join()
        binding.require_current()
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
        options = dict(playback_adapter=playback_adapter, prepared_session=None)
        if native:
            options['history_binding'] = binding
        else:
            options['host_call'] = call
        player = JacktookPLayer(cancel_event=cancelled, playback_client=playback_client, **options)
        player.run(data)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        failure = _failure(error)
    finally:
        progress.close()
        if expected is not None and call is not None and not (player and player._resolution_answered):
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
    # A modal dialog can remain open indefinitely. Retire this selection before
    # waiting for acknowledgement; never leave its stream/owner pending behind it.
    if failure is not None:
        xbmcgui.Dialog().ok('未打开网盘文件', failure)


def _wait_result(action, body, timeout, progress, current, rpc):
    """One bounded IO wait for history, native files and mounted selections."""
    finished, job = Event(), {}
    def verify():
        try:
            job['reply'] = rpc(action, body, timeout=timeout)
        except Exception as error:
            job['error'] = error
        finally:
            finished.set()
    if progress.iscanceled() or not current():
        raise PanError('CATALOG_SELECTION_CANCELLED')
    Thread(target=verify, name='bobbi-file-verify', daemon=True).start()
    deadline = time.monotonic() + timeout + 1
    while not finished.wait(.1):
        if progress.iscanceled() or not current() or time.monotonic() >= deadline:
            raise PanError('CATALOG_SELECTION_CANCELLED')
    if progress.iscanceled() or not current():
        raise PanError('CATALOG_SELECTION_CANCELLED')
    if 'error' in job:
        raise job['error']
    return job.get('reply', {})


def _prepare_ticket(action, body, request, title, rpc, binding):
    import xbmc
    import xbmcgui
    progress, monitor = xbmcgui.DialogProgress(), xbmc.Monitor()
    progress.create(title, '核验原账号与文件；可按返回取消。')
    try:
        reply = _wait_result(action, body, 28, progress,
            lambda: binding.is_current() and not monitor.abortRequested(), rpc)
        if reply.get('ticket') != request:
            raise PanError('PAN_REPLY_INVALID')
        return True
    except PanError as error:
        if str(error) != 'CATALOG_SELECTION_CANCELLED':
            raise
        return False
    finally:
        progress.close()


def _cancel_prepared(expected, request, native, owner, *, playback_client, call):
    owner_call = playback_client.call
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
    from bobbi_core.file_ref import locator
    from bobbi_core.playback_request import context, data_identity
    from bobbi_platform.pan_ui import _failure

    identifier = params.get('history_id')
    if type(identifier) is not str or not re.fullmatch('[0-9a-f]{64}', identifier):
        return
    request, expected, owner = uuid4().hex, None, None
    handed, native, transport = False, False, None
    try:
        transport, adapter = _entry_transport()
        binding, playback_client, call = transport
        read_snapshot, select = playback_client.read_snapshot, playback_client.select
        native = adapter == 'native'
        record = _history_record(identifier, binding)
        ref = record['file_ref']
        from bobbi_core.server_ref import resumable
        start_only = not resumable(ref)
        if start_only and params.get('start_over') != 'true':
            raise PanError('PAN_SERVER_RESUME_UNAVAILABLE')
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
        body = dict(history_id=identifier, request_id=request)
        if start_only:
            body['start_only'] = True
        if not _prepare_ticket('pan_prepare_history_play', body, request,
                '核验后从头播放' if start_only else '继续观看原文件', call, binding):
            return
        # A previously saved Continue Watching URL can outlive completion.
        # Only actual EOF counts: a manual stop near the credits still resumes.
        restart = params.get('start_over') == 'true' or record.get('completion_reason') == 'NATURAL_EOF'
        reservation = dict(account=expected, owner=owner, file_ref=ref,
                           position=0 if restart else record['position'])
        play(dict(ticket=request), reservation=reservation, transport=transport, playback_adapter=adapter)
        handed = True
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        label = ('本地记录暂不可用，请从“我的文件”重新选择。'
                 if str(error).startswith('FILE_HISTORY_') else _failure(error))
        xbmcgui.Dialog().ok('未恢复原文件', label)
        if transport is not None and str(error) not in ('PAN_ACCOUNT_CHANGED', 'PAN_LOGIN_REQUIRED', 'PROFILE_CHANGED',
                              'CATALOG_SELECTION_CANCELLED', 'PAN_SERVER_RESUME_UNAVAILABLE'):
            _offer_history_versions(identifier, transport[2], transport[0].require_current)
    finally:
        if not handed and transport is not None:
            _cancel_prepared(expected, request, native, owner, playback_client=transport[1], call=transport[2])


def _offer_history_versions(identifier, call, current):
    """Recovery is explicit navigation; the failed original history is untouched."""
    import xbmc
    import xbmcgui
    from lib.utils.views.personal_catalog import route, scope_params
    try:
        current()
        rows = call('catalog_history_links', dict(history_ids=[identifier]))['items']
        match = next((row for row in rows if row['entity_id'] == identifier and row.get('parent_entity_id')), None)
        if match and not xbmc.Monitor().abortRequested() and xbmcgui.Dialog().yesno(
                '查看其他文件版本？', '原文件的观看记录仍保留。仅打开版本列表，由你决定是否选择另一文件。'):
            current()
            target = route(action='personal_catalog', view='files', parent_entity_id=match['parent_entity_id'],
                           **scope_params(match['expected']))
            xbmc.executebuiltin('ActivateWindow(Videos,"' + target + '",return)')
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        pass


def indexed(params):
    """Reserve explicit user intent before IO; the index itself grants no playback right."""
    if params.get('source'):
        return mounted(params)
    import xbmcgui
    from uuid import uuid4
    from lib.utils.views.personal_catalog import account_for
    from bobbi_core.playback_request import context, data_identity
    from bobbi_platform.pan_ui import _failure
    identifier = params.get('object_id')
    if type(identifier) is not str or not re.fullmatch('[0-9a-f]{64}', identifier):
        return
    request, expected, owner = uuid4().hex, None, None
    native, handed, transport = False, False, None
    try:
        transport, adapter = _entry_transport()
        binding, playback_client, call = transport
        read_snapshot, select = playback_client.read_snapshot, playback_client.select
        native = adapter == 'native'
        accounts = [scope(row['account'], authenticated=True) for row in call('pan_status', {})['providers']
                    if 'provider' in row['account'] and row['account'].get('authenticated')]
        expected = account_for(params, accounts)
        position, history_ref = 0, None
        try:
            previous = _history_record(identifier, binding)
        except (ValueError, OSError, RuntimeError):
            previous = None
        from bobbi_core.server_ref import resumable
        if (resumable(expected) and previous and previous['position'] > 0
                and previous['completion_reason'] != 'NATURAL_EOF'):
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
                request_id=request, intent='play'), request, '正在核验片库原文件', call, binding):
            return
        play(dict(ticket=request), reservation=dict(account=expected, owner=owner,
            object_id=identifier, file_ref=history_ref, position=position), transport=transport, playback_adapter=adapter)
        handed = True
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        labels = {'CATALOG_RECHECK_INCOMPLETE': '有限检查内未能确认原文件，请从“我的文件”回原目录选择。',
                  'CATALOG_SOURCE_UNAVAILABLE': '索引来源暂不可用，原文件与观看记录仍保留。',
                  'PAN_ACCOUNT_CHANGED': '账号已变化，请返回片库重新选择。'}
        xbmcgui.Dialog().ok('未打开片库文件', labels.get(str(error), _failure(error)))
    finally:
        if not handed and transport is not None:
            _cancel_prepared(expected, request, native, owner, playback_client=transport[1], call=transport[2])


MOUNTED_MESSAGES = {
    'CATALOG_NETWORK_INCOMPLETE': '网络目录未提供完整的直接子项列表，未推断任何删除；请使用原目录浏览。',
    'CATALOG_NETWORK_METADATA_REQUIRED': '网络目录缺少文件大小或精确修改时间，不能核验旧观察；请使用原目录浏览。',
    'CATALOG_CURSOR_STALE': '片库已更新，请返回刷新后继续。',
    'CATALOG_RECHECK_INCOMPLETE': '有限检查内未找到原文件，请回原目录选择。',
    'CATALOG_SOURCE_UNAVAILABLE': '已登记来源或挂载暂不可用，原有索引已保留。',
    'CATALOG_AUTHORITY_CHANGED': '来源配置或挂载已变化，请重新选择；不会继承旧文件进度。',
    'CATALOG_FILE_CHANGED': '原路径的文件或来源观察已变化，请重新扫描后选择。',
    'CATALOG_SOURCE_UNSUPPORTED': '此来源不符合已登记目录的核验条件；本地目录不跟随符号链接。',
    'CATALOG_SCAN_BUSY': '已有扫描正在进行，可在扫描进度中查看或取消。',
}


def _reserve_mounted(request, source_id, object_id, rpc):
    """Reuse the resident selection barrier, never claim native AV ownership."""
    snapshot = rpc('playback', dict(operation='snapshot'), timeout=2)
    if snapshot.get('adapter') == 'standard':
        # A real, possibly unauthenticated Host scope guards this lifecycle.
        # It is not a CD2 credential and no second cloud login is required.
        account = rpc('account_status', {}, timeout=2)
        rpc('playback', dict(operation='select', request_id=request, account=account), timeout=2)
        return dict(adapter='standard', request_id=request)
    identity = 'transport:' + sha256(('mounted:' + source_id + ':' + object_id).encode()).hexdigest()
    selected = rpc('playback', dict(operation='select', boot_id=snapshot['boot_id'],
        epoch=snapshot['epoch'], request_id=request, selection_identity=identity), timeout=2)
    from bobbi_core.playback_request import context
    return dict(context(selected, request), adapter='native')


def _owner_current(selection, rpc):
    snapshot = rpc('playback', dict(operation='snapshot'), timeout=2)
    desired = snapshot.get('desired') or {}
    if desired.get('request_id') != selection['request_id'] or desired.get('cancelled') is not False:
        return False
    if selection['adapter'] == 'standard':
        return snapshot.get('adapter') == 'standard'
    return all(snapshot.get(key) == selection[key] for key in ('boot_id', 'epoch'))


def _cancel_owner(request, rpc):
    # A lost select reply is not retried. Read once to cancel only our own
    # accepted request if present; never cancel a newer owner or global player.
    snapshot = rpc('playback', dict(operation='snapshot'), timeout=2)
    desired = snapshot.get('desired') or {}
    if desired.get('request_id') != request or desired.get('cancelled'):
        return
    body = dict(operation='cancel', request_id=request)
    if snapshot.get('adapter') != 'standard':
        body.update(boot_id=snapshot['boot_id'], epoch=snapshot['epoch'])
    rpc('playback', body, timeout=2)


def mounted(params, handle=None, rpc=None):
    import sys
    from uuid import uuid4
    from lib.utils.views.personal_catalog import mounted_for, _profile_rpc
    handle = int(sys.argv[1]) if handle is None else handle
    supplied_rpc = rpc
    source_id, object_id = params.get('source', ''), params.get('object_id', '')
    import xbmc
    import xbmcgui
    import xbmcplugin
    import xbmcvfs
    from bobbi_platform.library_ui import registry
    from bobbi_platform.libraries import joined_path
    from bobbi_platform.kodi import standard_handoff
    request = uuid4().hex
    window = xbmcgui.Window(10000)
    progress, monitor = xbmcgui.DialogProgress(), xbmc.Monitor()
    handoff = None
    selection_attempted = False
    store = None
    failure = None
    binding = None
    def current():
        if binding is not None:
            binding.require_current()
        return not monitor.abortRequested() and window.getProperty('bobbi.portable_selection') == request
    from bobbi_core.typed_ref import action_prefix, request_scope
    prefix = action_prefix(params.get('reference_kind', 'mounted_path'))
    source_label = {'catalog_local_': '本地目录', 'catalog_network_': '网络目录（实验）'}.get(prefix, 'CD2')
    try:
        if supplied_rpc is None or params.get('reference_kind') == 'network_path':
            binding, rpc = _profile_rpc(supplied_rpc)
        expected = mounted_for(params, rpc)
        if not xbmcgui.Dialog().yesno('选择当前文件并从头播放？',
                '将重新核验当前来源和原文件。旧路径观察与进度仅作历史保留，不继承到当前文件。'):
            return
        window.setProperty('bobbi.portable_selection', request)
        progress.create('正在核验' + source_label + '原文件', '核对当前来源与文件，可按返回取消。')
        selection_attempted = True
        selection = _reserve_mounted(request, source_id, object_id, rpc)
        ticket = _wait_result(prefix + 'prepare', dict(request_scope(expected), object_id=object_id,
            request_id=request, intent='play_from_start'), 28, progress, current, rpc)['ticket']
        if ticket != request or not current() or not _owner_current(selection, rpc):
            raise ValueError('CATALOG_SELECTION_CANCELLED')
        selected = _wait_result(prefix + 'claim', dict(ticket=ticket), 28, progress, current, rpc)
        if (selected['source_id'] != source_id or selected['object_id'] != object_id
                or not current() or not _owner_current(selection, rpc)):
            raise ValueError('CATALOG_SELECTION_CANCELLED')
        store = registry((lambda _: str(binding.root())) if binding is not None else xbmcvfs.translatePath)
        source = store.get(source_id)
        if params.get('reference_kind') == 'network_path':
            source, revision = store.source_snapshot(source_id)
            if revision != expected['generation']:
                raise ValueError('CATALOG_AUTHORITY_CHANGED')
        def same_source():
            return (store.source_snapshot(source_id) == (source, revision) if params.get('reference_kind') == 'network_path'
                    else store.get(source_id) == source)
        url = joined_path(source, selected['relative'])
        def ready():
            if not current() or not _owner_current(selection, rpc) or not same_source():
                return False
            valid = _wait_result(prefix + 'verify', dict(request_scope(expected), object_id=object_id,
                request_id=request), 8, progress, current, rpc)
            return (valid.get('valid') is True and current() and _owner_current(selection, rpc)
                    and same_source() and current() and not progress.iscanceled())
        handoff = standard_handoff(selected['identity'], handle, ready=ready)
        result = handoff.submit(selected['identity'], dict(url=url, title=selected['title'], _mounted_path=True))
        if not result['opened']:
            raise ValueError('CATALOG_SELECTION_CANCELLED')
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        if handoff is None or handoff.state in ('selected', 'cancelled'):
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        failure = str(error)
    finally:
        progress.close()
        if selection_attempted and (handoff is None or handoff.state in ('selected', 'cancelled')):
            for cancel in (
                lambda: rpc(prefix + 'cancel_play', dict(source_id=source_id, request_id=request), timeout=2),
                lambda: _cancel_owner(request, rpc)):
                try:
                    cancel()
                except (ValueError, OSError, RuntimeError, KeyError, TypeError):
                    pass
        if store is not None:
            store.close()
    if failure is not None and failure != 'CATALOG_SELECTION_CANCELLED':
        xbmcgui.Dialog().ok(source_label + '原文件播放', MOUNTED_MESSAGES.get(failure, '本次未确认打开原文件；不会自动换源或重复提交。'))

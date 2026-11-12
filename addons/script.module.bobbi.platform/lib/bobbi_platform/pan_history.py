"""Host-only revalidation of a trusted history record, never a UI FileRef."""
import re

from bobbi_core.file_ref import from_selected, same_file, validate
from .pan_accounts import PanError, scope


def history_summary(service, expected, offset=0, limit=5, history=None, catalog=None):
    """Read-only phone projection of current-account unfinished file history.

    The injected adapter exists for offline tests, not as an IPC argument.
    Reading never reserves a session, resolves a file or refreshes credentials.
    """
    expected = scope(expected, authenticated=True)
    if (type(offset) is not int or not 0 <= offset <= 500
            or type(limit) is not int or not 1 <= limit <= 5):
        raise ValueError('CATALOG_PAGE_INVALID')
    service.accounts.require_current(expected)
    if history is None:
        from lib.db.file_history import FileHistory
        history = FileHistory()
    rows = [row for row in history.rows()
            if (row['file_ref']['provider'], row['file_ref']['account_id']) ==
               (expected['provider'], expected['account_id'])]
    descriptions = {}
    selected = rows[offset:offset + limit]
    if catalog is not None and selected:
        from types import SimpleNamespace
        from .catalog_navigation import history_links
        try:
            descriptions = {row['entity_id']: row for row in history_links(catalog, service,
                [row['id'] for row in selected], history=SimpleNamespace(rows=lambda: selected))['items']}
        except (ValueError, OSError, RuntimeError):
            pass  # Optional local index cannot prevent original-file history.
    def publish():
        if service.closed:
            raise PanError('PAN_SERVICE_CLOSED')
        items = [dict(id=row['id'], name=row['file_ref']['name'][:240],
            position=row['position'], duration=row['duration'], updated_at=row['updated_at'],
            completion_reason=row['completion_reason']) for row in selected]
        for item in items:
            card = descriptions.get(item['id'])
            if card:
                from bobbi_core.catalog_display import file_description
                item.update(work_title=card['work_title'], version_label=card['version_label'],
                    description=file_description(card, item['position'], item['duration']),
                    navigation=dict(view='files', parent_entity_id=card['parent_entity_id']))
        return dict(items=items, next_offset=offset + limit if len(rows) > offset + limit else None)
    return service.accounts.run_if_current(expected, publish)


def prepare_history_play(service, record, request_id):
    ref = validate(record['file_ref'])
    current = service.accounts.snapshot(ref['provider'])
    if current.get('authenticated') is not True:
        raise PanError('PAN_LOGIN_REQUIRED')
    expected = scope(current, authenticated=True)
    return prepare_file_play(service, ref, expected, request_id)


def prepare_file_play(service, ref, expected, request_id, publish=None):
    """Host-trusted reference, explicit account generation, shared admission.

    Callers load references from their authority. No UI-supplied selected/ref
    enters here. Even a future by-ID locator cannot replace real list_files.
    """
    if type(request_id) is not str or not re.fullmatch('[0-9a-f]{32}', request_id):
        raise PanError('PAN_SELECTION_INVALID')
    ref = validate(ref)
    expected = scope(expected, authenticated=True)
    service.accounts.require_current(expected)
    if (expected['provider'], expected['account_id']) != (ref['provider'], ref['account_id']):
        raise PanError('PAN_ACCOUNT_CHANGED')

    def live():
        with service.lock:
            if service.closed or request_id in service.cancelled_streams:
                raise PanError('PAN_SELECTION_CANCELLED')
        service.accounts.require_current(expected)

    live()
    # Shared finite budget across every upstream page, local continuation,
    # authentication check and retry. No filename matching / whole-drive scan.
    with service.scan_operation(expected, request_id, max_pages=8, max_items=160,
                                max_requests=20, seconds=24, kind='scan') as operation:
        page, cursor, continuation = 1, None, None
        for _ in range(64):  # Local IPC subdivisions are bounded separately.
            live()
            operation.check()
            result = service.list_files(expected, ref['parent'], page, cursor=cursor,
                refresh=page == 1 and continuation is None, continuation=continuation,
                operation=operation)
            live()
            for selected in result['items']:
                if selected.get('directory') is not False:
                    continue
                current = from_selected(expected, selected, ref['parent'])
                if current['id'] != ref['id']:
                    continue
                if not same_file(ref, current):
                    raise PanError('PAN_FILE_CHANGED')
                # Existing fresh-directory admission and single-use claim are
                # retained. The history row alone can never mint a ticket.
                operation.check()
                prepare = lambda: service.prepare_play(expected, selected, request_id=request_id)
                return publish(prepare) if publish is not None else prepare()
            continuation = result.get('continuation')
            if continuation:
                continue
            if not result.get('has_more'):
                raise PanError('PAN_FILE_CHANGED')
            page += 1
            cursor = result.get('next_cursor')
        raise PanError('PAN_BUDGET_EXHAUSTED')

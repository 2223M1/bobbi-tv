"""Host-only revalidation of a trusted history record, never a UI FileRef."""
import re

from bobbi_core.file_ref import from_selected, same_file, validate
from .pan_accounts import PanError, scope


def history_summary(service, expected, offset=0, limit=5, history=None):
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
    def publish():
        if service.closed:
            raise PanError('PAN_SERVICE_CLOSED')
        return dict(items=[dict(id=row['id'], name=row['file_ref']['name'][:240],
            position=row['position'], duration=row['duration'], updated_at=row['updated_at'],
            completion_reason=row['completion_reason']) for row in rows[offset:offset + limit]],
            next_offset=offset + limit if len(rows) > offset + limit else None)
    return service.accounts.run_if_current(expected, publish)


def prepare_history_play(service, record, request_id):
    if type(request_id) is not str or not re.fullmatch('[0-9a-f]{32}', request_id):
        raise PanError('PAN_SELECTION_INVALID')
    ref = validate(record['file_ref'])
    current = service.accounts.snapshot(ref['provider'])
    if current.get('authenticated') is not True:
        raise PanError('PAN_LOGIN_REQUIRED')
    expected = scope(current, authenticated=True)
    if expected['account_id'] != ref['account_id']:
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
                return service.prepare_play(expected, selected, request_id=request_id)
            continuation = result.get('continuation')
            if continuation:
                continue
            if not result.get('has_more'):
                raise PanError('PAN_FILE_CHANGED')
            page += 1
            cursor = result.get('next_cursor')
        raise PanError('PAN_BUDGET_EXHAUSTED')

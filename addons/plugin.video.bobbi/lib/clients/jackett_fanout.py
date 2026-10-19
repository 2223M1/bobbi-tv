"""Bounded fan-out with explicit outcomes and a killable process I/O boundary."""
import time

from bobbi_core.search_completion import SearchCompletion, SearchResults
from lib.clients.fanout_diagnostics import new_receipt, observe, transport_tasks
from lib.clients import jackett_http


def _fetch_batch(session, urls, budget=8.0, *, deadline=None, cancelled=None,
                      mode='rss', max_response_bytes=4 * 1024 * 1024, request_timeout=2.0):
    deadline = min(deadline if deadline is not None else float('inf'),
                   time.monotonic() + min(8.0, max(0.0, float(budget))))
    receipt = new_receipt(urls)
    if receipt is not None and cancelled is not None:
        receipt.user_cancel_observability = 'caller_callback'
    cancelled = cancelled or (lambda: False)
    tasks = list(transport_tasks(urls, receipt))
    outcomes = [None] * len(tasks)
    started = set()
    transport_failed = False
    pending_exception = None
    try:
        for ordinal, state, reason, response in jackett_http.iter_events(
                session, [task[1] for task in tasks], deadline, cancelled, mode, max_response_bytes,
                request_timeout=request_timeout):
            row = tasks[ordinal][2]
            if state == 'started':
                started.add(ordinal)
                observe(receipt, 'start', row)
                continue
            if state == 'exception' and isinstance(response, BaseException):
                observe(receipt, 'terminal', row, state, reason)
                pending_exception = pending_exception or response
                continue
            if state not in ('succeeded', 'failed', 'skipped', 'timed_out') or outcomes[ordinal] is not None:
                raise ValueError('Invalid HTTP terminal event')
            outcomes[ordinal] = state, response if state == 'succeeded' else None
            observe(receipt, 'terminal', row, state, reason, getattr(response, 'status_code', None))
    except jackett_http.HTTPBatchError as error:
        transport_failed = str(error)
    except BaseException:
        observe(receipt, 'aborted')
        observe(receipt, 'emit', 'transport_exception')
        raise
    if pending_exception is not None:
        observe(receipt, 'aborted')
        observe(receipt, 'emit', 'transport_exception')
        raise pending_exception
    for ordinal, outcome in enumerate(outcomes):
        if outcome is not None:
            continue
        if cancelled():
            state, reason = 'skipped', 'caller_cancelled'
        elif transport_failed:
            state, reason = 'failed', 'worker_' + transport_failed
        elif ordinal in started:
            state, reason = 'timed_out', 'shared_deadline'
        else:
            state, reason = 'skipped', 'budget_before_start'
        outcomes[ordinal] = state, None
        observe(receipt, 'terminal', tasks[ordinal][2], state, reason)
    counts = {state: sum(outcome == state for outcome, _ in outcomes)
              for state in ('succeeded', 'failed', 'skipped', 'timed_out')}
    result = SearchResults([response for _, response in outcomes if response is not None],
                           SearchCompletion(len(outcomes), **counts))
    observe(receipt, 'bind_responses', outcomes)
    result.fanout_receipt = receipt
    return result


def fetch_independent(session, urls, budget=8.0, *, deadline=None, cancelled=None,
                      mode='rss', max_response_bytes=4 * 1024 * 1024, request_timeout=2.0):
    return _fetch_batch(session, urls, budget, deadline=deadline, cancelled=cancelled,
                        mode=mode, max_response_bytes=max_response_bytes, request_timeout=request_timeout)


def fetch_inventory(session, url, deadline, cancelled):
    return _fetch_batch(session, [url], deadline=deadline, cancelled=cancelled,
                             mode='inventory', max_response_bytes=256 * 1024)

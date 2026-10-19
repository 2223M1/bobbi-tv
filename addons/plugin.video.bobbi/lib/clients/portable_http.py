"""Bounded stock-Kodi HTTP fanout, without an external Python interpreter.

Four OS-locked slots are shared across Kodi interpreters. DNS cannot be killed
portably: a late worker keeps its slot until its session actually closes. The
caller stops publishing at cancellation/deadline and never waits indefinitely
for that worker, so repeated searches cannot create unlimited DNS threads.
"""
import copy
import json
import math
from pathlib import Path
import queue
from threading import Event, Lock, Thread
import time
import xml.etree.ElementTree as ET
import requests

WORKERS = 4
MAX_BATCH_BYTES = 16 * 1024 * 1024
JOIN_SECONDS = .2


def _slot():
    from bobbi_core.runtime_paths import ProfilePath
    from bobbi_core.search_admission import try_acquire
    base = Path(ProfilePath('http-admission'))
    for index in range(WORKERS):
        lease = try_acquire(base / str(index))
        if lease is not None:
            return lease
    return None


def _session(template):
    # requests.Session mutates its cookie jar. Never share or close the
    # provider's mutable session/adapters from worker threads.
    if not isinstance(template, requests.Session):
        return template, False  # Explicit injected transports used by tests.
    result = requests.Session()
    for name in ('headers', 'params', 'proxies', 'hooks'):
        setattr(result, name, copy.deepcopy(getattr(template, name)))
    result.cookies = template.cookies.copy()
    for name in ('auth', 'verify', 'cert', 'trust_env', 'max_redirects'):
        setattr(result, name, getattr(template, name))
    return result, True


def _parse(body, mode, response):
    if mode == 'json':
        json.loads(body)
        return
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise ValueError('xml_declaration')
    root = ET.fromstring(body)
    if mode == 'inventory':
        if root.tag != 'indexers':
            raise ValueError('inventory_structure')
        return
    if root.tag != 'rss' or len(root.findall('channel')) != 1:
        raise ValueError('rss_structure')
    from lib.utils.parsers import xmltodict
    items = (xmltodict.parse(body)['rss']['channel'] or {}).get('item') or []
    items = items if isinstance(items, list) else [items]
    if len(items) > 2000 or len(items) != len(root.findall('channel/item')):
        raise ValueError('rss_items')
    response._am6b_items = items
    response._am6b_parse_failed = False


def iter_events(session, urls, deadline, cancelled, mode, limit, request_timeout=2.0):
    if mode not in ('rss', 'json', 'inventory') or not 0 < limit <= 4 * 1024 * 1024 or len(urls) > 256:
        raise ValueError('Invalid bounded HTTP batch')
    if not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
        raise ValueError('Invalid bounded HTTP deadline')
    if request_timeout is not None and (type(request_timeout) not in (int, float)
            or not math.isfinite(request_timeout) or not 0 < request_timeout <= 8):
        raise ValueError('Invalid bounded HTTP timeout')
    events, stop, byte_lock = queue.Queue(), Event(), Lock()
    used, active, threads, cursor = [0], {}, [], 0

    def stopped():
        return stop.is_set() or cancelled() or time.monotonic() >= deadline

    def fetch(ordinal, url, lease):
        local, owned = None, False
        event = ordinal, 'failed', 'request_or_parse_failed', None
        try:
            if stopped():
                event = ordinal, 'skipped', 'caller_cancelled', None
                return
            events.put((ordinal, 'started', 'request_start', None))
            local, owned = _session(session)
            remaining = deadline - time.monotonic()
            timeout = max(.01, min(remaining, request_timeout or 4.0))
            request_end = min(deadline, time.monotonic() + timeout)
            with local.get(url, timeout=(min(timeout, 2), timeout), stream=True,
                           allow_redirects=False, headers={'Accept-Encoding': 'identity'}) as response:
                if response.status_code != 200:
                    event = ordinal, 'failed', 'http_error', response
                    return
                declared = response.headers.get('Content-Length')
                if declared and (not declared.isdigit() or int(declared) > limit):
                    raise ValueError('oversize')
                body = bytearray()
                for chunk in response.iter_content(16384):
                    if stopped() or time.monotonic() >= request_end:
                        break
                    if len(body) + len(chunk) > limit:
                        raise ValueError('oversize')
                    with byte_lock:
                        if used[0] + len(chunk) > MAX_BATCH_BYTES:
                            raise ValueError('batch_size')
                        used[0] += len(chunk)
                    body.extend(chunk)
                if stopped() or time.monotonic() >= request_end:
                    event = ordinal, 'skipped' if cancelled() or stop.is_set() else 'timed_out', 'shared_deadline', None
                    return
                if declared and response.headers.get('Content-Encoding', 'identity') == 'identity' and len(body) != int(declared):
                    raise ValueError('short_read')
                response._content = bytes(body)
                response._content_consumed = True
                _parse(body, mode, response)
                if not stopped():
                    event = ordinal, 'succeeded', 'http_ok', response
        except requests.Timeout:
            event = ordinal, 'timed_out', 'socket_timeout', None
        except (requests.RequestException, ValueError, ET.ParseError, KeyError, TypeError):
            pass
        except Exception as error:
            event = ordinal, 'failed', 'worker_' + type(error).__name__, None
        finally:
            try:
                if owned:
                    local.close()
            except Exception:
                # Cleanup failure must not print an uncontrolled exception
                # from a daemon thread or prevent releasing its admission.
                pass
            finally:
                # A DNS/socket/close stall retains this cross-interpreter slot.
                lease.release()
                events.put(event)

    try:
        while not stopped():
            while cursor < len(urls) and len(active) < WORKERS and not stopped():
                lease = _slot()
                if lease is None:
                    break
                ordinal = cursor
                cursor += 1
                thread = Thread(target=fetch, args=(ordinal, urls[ordinal], lease),
                                name='BobiHTTP', daemon=True)
                active[ordinal] = thread
                try:
                    thread.start()
                    threads.append(thread)
                except BaseException:
                    active.pop(ordinal)
                    lease.release()
                    raise
            if not active:
                if cursor < len(urls):
                    for ordinal in range(cursor, len(urls)):
                        yield ordinal, 'failed', 'global_io_busy', None
                return
            try:
                event = events.get(timeout=min(.025, max(.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if stopped():
                return
            if event[1] != 'started':
                active.pop(event[0], None)
            yield event
    finally:
        stop.set()
        end = time.monotonic() + JOIN_SECONDS
        for thread in threads:
            thread.join(max(0, end - time.monotonic()))

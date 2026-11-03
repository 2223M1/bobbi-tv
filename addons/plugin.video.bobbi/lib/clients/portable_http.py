"""Bounded stock-Kodi HTTP fanout, without an external Python interpreter.

Four OS-locked slots are shared across Kodi interpreters. DNS cannot be killed
portably: a late worker keeps its slot until its session actually closes. The
caller stops publishing at cancellation/deadline and never waits indefinitely
for that worker, so repeated searches cannot create unlimited DNS threads.
"""
import copy
from hashlib import sha256
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
_DUPLICATE_IO = object()


def _request_key(session, url):
    """Only a digest crosses interpreters; never persist URLs or credentials."""
    try:
        context = {name: getattr(session, name, None) for name in
                   ('headers', 'params', 'proxies', 'auth', 'verify', 'cert', 'trust_env')}
        context['headers'] = dict(context['headers'] or {})
        cookies = getattr(session, 'cookies', ()) or ()
        context['cookies'] = (cookies if isinstance(cookies, dict) else
            sorted((cookie.domain, cookie.path, cookie.name, cookie.value) for cookie in cookies))
        value = json.dumps([url, context], sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    except (ValueError, TypeError, AttributeError):
        # Custom authentication objects cannot be proved equivalent. Do not
        # coalesce them or serialize their repr/implementation details.
        return None
    return sha256(value.encode()).hexdigest()


def _slot(request_key=None):
    from bobbi_core.runtime_paths import ProfilePath
    from bobbi_core.search_admission import try_acquire
    base = Path(ProfilePath('http-admission'))
    dispatch = try_acquire(base / 'dispatch')
    if dispatch is None:
        return None
    available = []
    chosen = None
    try:
        duplicate = False
        for index in range(WORKERS):
            directory = base / str(index)
            lease = try_acquire(directory)
            if lease is not None:
                available.append((directory, lease))
            elif request_key:
                # A crashed worker releases its OS lock. A stale marker on a
                # free slot is ignored, so no TTL or cleanup daemon is needed.
                try:
                    duplicate |= (directory / 'request').read_text(encoding='ascii') == request_key
                except (OSError, UnicodeError):
                    pass  # Older workers still retain their ordinary IO slot.
        if duplicate:
            return _DUPLICATE_IO
        if not available:
            return None
        directory, chosen = available.pop(0)
        try:
            (directory / 'request').write_text(request_key or '', encoding='ascii')
        except BaseException:
            chosen.release()
            raise
        return chosen
    finally:
        for _, lease in available:
            lease.release()
        dispatch.release()


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


def _error_reason(response, stopped, request_end):
    """Static classifications only; never copy the upstream error text to logs."""
    if response.status_code in (401, 403):
        return 'http_access_denied'
    if response.status_code == 429:
        return 'http_rate_limited'
    declared = response.headers.get('Content-Length', '')
    if response.status_code != 400 or not declared.isdigit() or not 0 < int(declared) <= 8192:
        return 'http_error'
    try:
        body = bytearray()
        for chunk in response.iter_content(8192):
            if stopped() or time.monotonic() >= request_end or len(body) + len(chunk) > 8192:
                return 'http_error'
            body.extend(chunk)
        if len(body) != int(declared) or b'<!' in body:
            return 'http_error'
        node = ET.fromstring(body)
        if node.tag != 'error':
            return 'http_error'
        if node.get('code') in ('200', '201', '202', '203'):
            return 'indexer_parameters'
        text = node.get('description', '').casefold()
        if 'challenge detected' in text or 'captcha' in text:
            return 'indexer_challenge'
        if 'connection refused' in text or 'name or service not known' in text:
            return 'indexer_upstream_connect'
        if 'timed out' in text or 'timeout' in text:
            return 'indexer_upstream_timeout'
        return 'indexer_error'
    except (requests.RequestException, ValueError, ET.ParseError, TypeError):
        return 'http_error'


def iter_events(session, urls, deadline, cancelled, mode, limit, request_timeout=2.0):
    if mode not in ('rss', 'json', 'inventory') or not 0 < limit <= 4 * 1024 * 1024 or len(urls) > 256:
        raise ValueError('Invalid bounded HTTP batch')
    if not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
        raise ValueError('Invalid bounded HTTP deadline')
    if request_timeout is not None and (type(request_timeout) not in (int, float)
            or not math.isfinite(request_timeout) or not 0 < request_timeout <= 8):
        raise ValueError('Invalid bounded HTTP timeout')
    events, stop, byte_lock = queue.Queue(), Event(), Lock()
    used, active, threads = [0], {}, []
    pending = list(range(len(urls)))
    request_keys = [_request_key(session, url) for url in urls]

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
                    event = ordinal, 'failed', _error_reason(response, stopped, request_end), response
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

    def refill():
        for ordinal in list(pending):
            if len(active) >= WORKERS or stopped():
                break
            lease = _slot(request_keys[ordinal])
            if lease is _DUPLICATE_IO:
                # An abandoned duplicate must not hold up different queries.
                # It stays queued without occupying another worker/IO slot.
                continue
            if lease is None:
                break  # Global capacity/dispatch contention, not a URL gap.
            pending.remove(ordinal)
            try:
                if stopped():
                    lease.release()
                    break
                thread = Thread(target=fetch, args=(ordinal, urls[ordinal], lease),
                                name='BobiHTTP', daemon=True)
                active[ordinal] = thread
                thread.start()
                threads.append(thread)
            except BaseException:
                active.pop(ordinal, None)
                lease.release()
                raise

    try:
        while not stopped():
            refill()
            if not active:
                if not pending:
                    return
                stop.wait(min(.025, max(.001, deadline - time.monotonic())))
                continue
            try:
                event = events.get(timeout=min(.025, max(.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if stopped():
                return
            refill_error = None
            if event[1] != 'started':
                active.pop(event[0], None)
                try:
                    # Parsing/filtering happens while this generator is
                    # suspended. Reuse the freed IO slot before yielding,
                    # under the same global admission/deadline/cancel bounds.
                    refill()
                except Exception as error:
                    refill_error = error
            if stopped():
                return
            yield event
            if refill_error is not None:
                # A failed replacement cannot swallow the response we already
                # completed; the caller gets it before the transport failure.
                raise refill_error
    finally:
        stop.set()
        end = time.monotonic() + JOIN_SECONDS
        for thread in threads:
            thread.join(max(0, end - time.monotonic()))

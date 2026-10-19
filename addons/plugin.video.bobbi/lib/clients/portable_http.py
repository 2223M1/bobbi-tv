"""Stock Kodi HTTP transport; no subprocess or external Python interpreter.

Sequential requests avoid orphan Kodi interpreter threads on Android. Socket
timeouts and between-chunk deadlines are cooperative, not a hard DNS deadline.
Incomplete results retain the ordinary partial-search receipt and never cache
as a complete search. The native subprocess transport remains for historical
tests only; public builds use this implementation on every platform.
"""
import json
import time
import xml.etree.ElementTree as ET
import requests


def iter_events(session, urls, deadline, cancelled, mode, limit, request_timeout=2.0):
    if mode not in ('rss', 'json', 'inventory') or not 0 < limit <= 4 * 1024 * 1024 or len(urls) > 256:
        raise ValueError('Invalid bounded HTTP batch')
    used = 0
    for ordinal, url in enumerate(urls):
        remaining = deadline - time.monotonic()
        if cancelled() or remaining <= .05:
            return
        yield ordinal, 'started', 'request_start', None
        response = None
        try:
            timeout = max(.05, min(remaining, request_timeout or 4.0))
            with session.get(url, timeout=(min(timeout, 2), timeout), stream=True,
                             allow_redirects=False, headers={'Accept-Encoding': 'identity'}) as response:
                if response.status_code != 200:
                    yield ordinal, 'failed', 'http_error', response
                    continue
                body = bytearray()
                declared = response.headers.get('Content-Length')
                if declared and (not declared.isdigit() or int(declared) > limit):
                    raise ValueError('oversize')
                for chunk in response.iter_content(16384):
                    if cancelled() or time.monotonic() >= deadline:
                        break
                    body.extend(chunk)
                    if len(body) > limit or used + len(body) > 16 * 1024 * 1024:
                        raise ValueError('oversize')
                if cancelled() or time.monotonic() >= deadline:
                    yield ordinal, 'skipped' if cancelled() else 'timed_out', 'shared_deadline', None
                    return
                if declared and response.headers.get('Content-Encoding', 'identity') == 'identity' and len(body) != int(declared):
                    raise ValueError('short_read')
                used += len(body)
                response._content = bytes(body)
                response._content_consumed = True
                if mode == 'rss':
                    from lib.utils.parsers import xmltodict
                    root = ET.fromstring(body)
                    if root.tag != 'rss' or len(root.findall('channel')) != 1:
                        raise ValueError('rss_structure')
                    items = (xmltodict.parse(body)['rss']['channel'] or {}).get('item') or []
                    items = items if isinstance(items, list) else [items]
                    if len(items) > 2000 or len(items) != len(root.findall('channel/item')):
                        raise ValueError('rss_items')
                    response._am6b_items = items
                    response._am6b_parse_failed = False
                elif mode == 'json':
                    json.loads(body)
                elif ET.fromstring(body).tag != 'indexers':
                    raise ValueError('inventory_structure')
                yield ordinal, 'succeeded', 'http_ok', response
        except requests.Timeout:
            yield ordinal, 'timed_out', 'socket_timeout', None
        except (requests.RequestException, ValueError, ET.ParseError, KeyError):
            yield ordinal, 'failed', 'request_or_parse_failed', None

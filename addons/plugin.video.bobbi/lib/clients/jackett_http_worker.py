"""Private stdlib-only HTTP worker. Never import Kodi or run outside its owner."""
import importlib.util
import json
import sys


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command():
    raw = sys.stdin.buffer.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('request_size')
    value = json.loads(raw)
    load(value['lifetime_module'], 'am6b_http_lifetime').protect(value['lifetime'])
    return value


def tls_context(verification):
    import os
    import ssl
    if not isinstance(verification, str) or not verification:
        raise ValueError('tls_configuration')
    return ssl.create_default_context(**{
        'capath' if os.path.isdir(verification) else 'cafile': verification})


def failure(error):
    """Classify bounded exception objects, never interpolate server/error text."""
    import socket
    import ssl
    from urllib.error import URLError
    for _ in range(4):
        if isinstance(error, URLError) and isinstance(error.reason, BaseException):
            error = error.reason
        else:
            break
    if isinstance(error, (socket.timeout, TimeoutError)):
        return 'timed_out', 'request_timeout'
    if isinstance(error, ssl.SSLCertVerificationError):
        return 'failed', 'tls_certificate'
    if isinstance(error, ssl.SSLError):
        return 'failed', 'tls_handshake'
    if isinstance(error, socket.gaierror):
        return 'failed', 'dns_failure'
    if isinstance(error, ConnectionRefusedError):
        return 'failed', 'connection_refused'
    if isinstance(error, (ConnectionResetError, ConnectionAbortedError)):
        return 'failed', 'connection_closed'
    return 'failed', 'request_exception'


def main(value):
    # Protection precedes network imports, DNS, TLS and parsers.
    import base64
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    import time
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request
    import xml.etree.ElementTree as ET
    import zlib

    entries, limit, mode = value['entries'], value['limit'], value['mode']
    if not 0 < len(entries) <= 256 or not 0 < limit <= 4 * 1024 * 1024:
        raise ValueError('request_size')
    parser = load(value['parser'], 'am6b_http_xmltodict') if mode == 'rss' else None
    lock, used = Lock(), [0]

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    def emit(event):
        raw = json.dumps(event, ensure_ascii=True, separators=(',', ':')).encode() + b'\n'
        with lock:
            if used[0] + len(raw) > value['total_limit']:
                raw = json.dumps(dict(ordinal=event['ordinal'], state='failed',
                    reason='batch_size', status=None)).encode() + b'\n'
            used[0] += len(raw)
            sys.stdout.buffer.write(raw)
            sys.stdout.buffer.flush()

    def fetch(pair):
        ordinal, entry = pair
        if time.monotonic() >= value['lifetime']['expires']:
            return
        emit(dict(ordinal=ordinal, state='started', reason='request_start'))
        event = dict(ordinal=ordinal, state='failed', reason='request_exception', status=None)
        try:
            handlers = [ProxyHandler(entry['proxies']), NoRedirect()]
            if urlsplit(entry['url']).scheme == 'https':
                try:
                    context = tls_context(entry.get('verify'))
                except (OSError, ValueError):
                    event['reason'] = 'tls_configuration'
                    return
                handlers.append(HTTPSHandler(context=context))
            opener = build_opener(*handlers)
            headers = dict(entry['headers'], **{'Accept-Encoding': 'identity'})
            request = Request(entry['url'], headers=headers)
            remaining = max(.01, value['lifetime']['expires'] - time.monotonic())
            cap = value['request_timeout']
            timeout = remaining if cap is None else min(cap, remaining)
            try:
                response = opener.open(request, timeout=timeout)
            except HTTPError as error:
                response = error
            with response:
                event['status'] = response.code
                if response.code != 200:
                    event['reason'] = 'http_error'
                    return
                declared = response.headers.get('Content-Length')
                if declared and (not declared.isdigit() or int(declared) > limit):
                    event['reason'] = 'oversize'
                    return
                encoding = response.headers.get('Content-Encoding', 'identity').lower()
                decoder = (zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == 'gzip'
                           else zlib.decompressobj() if encoding == 'deflate' else None)
                if encoding not in ('identity', 'gzip', 'deflate'):
                    event['reason'] = 'unsupported_encoding'
                    return
                body, wire = bytearray(), 0
                while True:
                    chunk = response.read(min(16384, limit - wire + 1))
                    if not chunk:
                        break
                    wire += len(chunk)
                    if wire > limit:
                        event['reason'] = 'oversize'
                        return
                    body.extend(decoder.decompress(chunk, limit - len(body) + 1) if decoder else chunk)
                    if len(body) > limit or (decoder and decoder.unconsumed_tail):
                        event['reason'] = 'oversize'
                        return
                if declared and wire != int(declared):
                    event['reason'] = 'short_read'
                    return
                if decoder and (not decoder.eof or decoder.unused_data):
                    event['reason'] = 'invalid_encoding'
                    return
            event.update(state='succeeded', reason='http_ok')
            if mode == 'rss':
                try:
                    root = ET.fromstring(body)
                    channels = [node for node in root if node.tag.rsplit('}', 1)[-1] == 'channel']
                    if (root.tag != 'rss' or len(channels) != 1 or
                            any(node.tag.rsplit('}', 1)[-1] == 'error' for node in root.iter())):
                        raise ValueError('rss_structure')
                    mapped = parser.parse(body)['rss']['channel'] or {}
                    items = mapped.get('item') or []
                    items = items if isinstance(items, list) else [items]
                    expected = sum(node.tag.rsplit('}', 1)[-1] == 'item' for node in channels[0])
                    if len(items) != expected or len(items) > 2000:
                        raise ValueError('rss_items')
                    event['items'] = items
                except Exception:
                    event['parse_failed'] = True
            else:
                if mode == 'json':
                    json.loads(body)
                elif mode == 'inventory':
                    if ET.fromstring(body).tag != 'indexers':
                        raise ValueError('inventory_structure')
                else:
                    raise ValueError('mode')
                event['body'] = base64.b64encode(body).decode('ascii')
        except Exception as error:
            state, reason = failure(error)
            event.update(state=state, reason=reason)
        finally:
            emit(event)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, enumerate(entries)))


if __name__ == '__main__':
    main(command())

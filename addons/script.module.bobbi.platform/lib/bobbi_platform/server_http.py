"""Bounded explicit-origin server requests. No redirects, URL credentials or cookies."""
from contextlib import contextmanager
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, unquote
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from bobbi_core.library_contract import server_location
from .pan_accounts import PanError

USER_AGENT = 'Bobbi-MediaServer/1'
MAX_REPLY = 2 * 1024 * 1024


def token(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,4096}', value):
        raise PanError('PAN_CREDENTIALS_INVALID')
    return value


def address(base, path):
    base = server_location(base)
    if (type(path) is not str or not path.startswith('/') or path.startswith('//')
            or re.search(r'[\x00-\x20\x7f|\\]', path) or '?' in path or '#' in path
            or any(p in ('.', '..') for p in unquote(path).split('/'))):
        raise PanError('PAN_ROUTE_REJECTED')
    return base + path


def at_origin(base, url):
    try:
        configured, actual = urlsplit(server_location(base)), urlsplit(url)
        return (actual.scheme, actual.netloc) == (configured.scheme, configured.netloc) and (
            not actual.username and not actual.password and not actual.fragment
            and actual.path.startswith(configured.path.rstrip('/') + '/')
            and not re.search(r'[\x00-\x20\x7f|\\]', url)
            and not any(p in ('.', '..') for p in unquote(actual.path).split('/'))
            and not any(word in unquote(actual.query).lower() for word in ('token', 'api_key', 'apikey', 'authorization')))
    except (ValueError, TypeError):
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise PanError('PAN_REDIRECT_REJECTED')


class Session:
    def __init__(self, provider, base, secret, opener=None, clock=time.monotonic):
        if provider not in ('plex', 'jellyfin', 'emby'):
            raise PanError('PAN_PROVIDER_INVALID')
        self.provider, self.base, self.secret = provider, server_location(base), token(secret)
        self.opener = opener or build_opener(ProxyHandler({}), NoRedirect())
        self.clock, self.deadline, self.operation = clock, None, None

    def __repr__(self):
        return '<Server HTTP: credentials hidden>'

    def headers(self):
        if self.provider == 'jellyfin':
            # Modern Jellyfin does not accept the legacy X-Emby-Token by
            # default. Token was validated at construction and is never put in
            # a URL. Requests and exact-original Range use the same origin.
            return {'User-Agent': USER_AGENT, 'Authorization': 'MediaBrowser Token="' + self.secret + '"'}
        key = 'X-Plex-Token' if self.provider == 'plex' else 'X-Emby-Token'
        return {'User-Agent': USER_AGENT, key: self.secret}

    @contextmanager
    def budget(self, seconds):
        previous, self.deadline = self.deadline, self.clock() + seconds
        try:
            yield
        finally:
            self.deadline = previous

    def request(self, path, query=None, data=None, *, method=None, success_statuses=(200,), empty_response=False):
        """One bounded attempt with an explicit response contract.

        Existing JSON reads retain their exact defaults. An empty response
        yields None only when requested; it is not proof of remote progress
        semantics or an invitation to replay an uncertain write.
        """
        method = ('GET' if data is None else 'POST') if method is None else method
        if (type(method) is not str or method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
                or method == 'GET' and data is not None
                or type(success_statuses) is not tuple or not 1 <= len(success_statuses) <= 4
                or any(type(code) is not int or code not in (200, 201, 202, 204) for code in success_statuses)
                or len(set(success_statuses)) != len(success_statuses) or type(empty_response) is not bool
                or 204 in success_statuses and not empty_response):
            raise PanError('PAN_ROUTE_REJECTED')
        url = address(self.base, path)
        if query:
            if any(re.search('token|api.?key|authorization', str(k), re.I) for k in query):
                raise PanError('PAN_ROUTE_REJECTED')
            url += '?' + urlencode(query)
        if not at_origin(self.base, url):
            raise PanError('PAN_ROUTE_REJECTED')
        if self.operation:
            self.operation.consume_request()
        timeout = min(8, self.deadline - self.clock()) if self.deadline else 8
        if self.operation:
            timeout = min(timeout, self.operation.deadline - self.operation.clock())
        if timeout <= 0:
            raise PanError('PAN_BUDGET_EXHAUSTED')
        headers = dict(self.headers(), Accept='application/json', **{'Cache-Control': 'no-store'})
        payload = None if data is None else json.dumps(data, allow_nan=False).encode('utf-8')
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with self.opener.open(Request(url, data=payload, headers=headers, method=method), timeout=timeout) as reply:
                if reply.status not in success_statuses or not at_origin(self.base, reply.geturl()):
                    raise PanError('PAN_HTTP_REJECTED')
                raw = bytearray()
                while True:
                    if self.operation:
                        self.operation.check()
                    if self.deadline and self.clock() >= self.deadline:
                        raise PanError('PAN_BUDGET_EXHAUSTED')
                    chunk = reply.read(min(65536, MAX_REPLY + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_REPLY:
                        raise PanError('PAN_REPLY_INVALID')
            if not raw and empty_response:
                return None
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise PanError('PAN_REPLY_INVALID')
                    value[key] = item
                return value
            def invalid_constant(value):
                raise PanError('PAN_REPLY_INVALID')
            value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
            pending, nodes = [(value, 0)], 0
            while pending:
                node, depth = pending.pop()
                nodes += 1
                if depth > 32 or nodes > 100000:
                    raise PanError('PAN_REPLY_INVALID')
                if type(node) is dict:
                    pending.extend((child, depth + 1) for child in node.values())
                elif type(node) is list:
                    pending.extend((child, depth + 1) for child in node)
            return value
        except HTTPError:
            raise PanError('PAN_HTTP_REJECTED') from None
        except (URLError, OSError):
            raise PanError('PAN_NETWORK_ERROR') from None
        except (ValueError, UnicodeError, RecursionError) as error:
            if isinstance(error, PanError):
                raise
            raise PanError('PAN_REPLY_INVALID') from None

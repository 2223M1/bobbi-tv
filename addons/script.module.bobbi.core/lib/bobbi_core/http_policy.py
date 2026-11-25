"""Shared Stremio/Nuvio protocol, cache, and bounded HTTP safety helpers."""

import hashlib
from contextvars import ContextVar
import ipaddress
import json
import socket
import ssl
import time
from typing import Any, Callable, Mapping, Optional
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
import zlib

MAX_RESOURCE_JSON_BYTES = 1024 * 1024
MIN_CACHE_TTL_SECONDS = 60
MAX_CACHE_TTL_SECONDS = 24 * 60 * 60
MAX_REDIRECTS = 5
ALLOWED_CONTENT_ENCODINGS = frozenset(("", "identity", "gzip", "x-gzip", "deflate"))
_SENSITIVE_REDIRECT_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization", "x-emby-token", "x-plex-token", "x-api-key"}
)
_VALIDATION_CONTEXT = ContextVar('bobbi_http_validation', default=None)


def _close_quietly(response: Any) -> None:
    closer = getattr(response, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            pass


def _origin_tuple(url: str) -> tuple[str, str, int]:
    parts = urlsplit(str(url or ""))
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port or (443 if scheme == "https" else 80)
    return scheme, host, port


def _check_budget(
    deadline: Optional[float],
    cancelled: Optional[Callable[[], bool]],
    clock: Callable[[], float] = time.monotonic,
) -> Optional[float]:
    if cancelled is not None and cancelled():
        raise TimeoutError("HTTP request cancelled")
    if deadline is None:
        return None
    rem = deadline - clock()
    if rem <= 0:
        raise TimeoutError("HTTP deadline exceeded")
    return rem


def _apply_stream_timeout(raw_stream: Any, rem: Optional[float]) -> None:
    if rem is None or raw_stream is None:
        return
    bound = max(0.005, min(rem, 2.0))
    for attr_chain in (("_fp", "fp", "raw", "_sock"), ("_fp", "fp", "_sock"), ("_sock",)):
        obj = raw_stream
        for attr in attr_chain:
            obj = getattr(obj, attr, None)
            if obj is None:
                break
        if obj is not None and hasattr(obj, "settimeout"):
            try:
                obj.settimeout(bound)
            except Exception:
                pass
            break


class _BoundedReply:
    """Give a requests response ownership of one existing bounded HTTP attempt."""

    def __init__(self, reply, connection, attempt):
        self._original_response = reply
        self._connection = connection
        self._attempt = attempt

    def read(self, size=-1, decode_content=False):
        return self._original_response.read(size)

    def read1(self, size=-1, decode_content=False):
        return self._original_response.read1(size)

    def close(self):
        try:
            self._original_response.close()
        finally:
            try:
                self._connection.close()
            finally:
                self._attempt.close()


def _bounded_requests_get(request, url, *, deadline, cancelled, clock, strip_sensitive, vetted_addresses, kwargs):
    """Use the existing transport for real requests GETs; keep injected callables intact.

    A requests socket timeout is an idle timeout, including in response headers
    and chunk framing. Its retry adapter also starts fresh budgets. Request
    preparation stays with requests, while bounded_http owns DNS/TCP/TLS and
    every read under the caller's one deadline. No transport worker is spawned.
    """
    import requests
    from .bounded_http import AttemptHandle, default_tls_context, open_connection

    owner = getattr(request, '__self__', None)
    function = getattr(request, '__func__', request)
    if not (
        isinstance(owner, requests.Session)
        and getattr(function, '__module__', '') == 'requests.sessions'
        and getattr(function, '__name__', '') == 'get'
    ):
        return request(url, allow_redirects=False, **kwargs)

    if kwargs.get('proxies') or owner.proxies:
        raise ValueError('configured addon proxy is unsupported by bounded transport')
    verify = kwargs.get('verify', owner.verify)
    if verify is False:
        raise ValueError('verified TLS is required')
    cert = kwargs.get('cert', owner.cert)
    tls_context = None
    if verify not in (True, None) or cert:
        import os
        tls_context = ssl.create_default_context(
            cafile=verify if verify not in (True, None) and not os.path.isdir(verify) else None,
            capath=verify if verify not in (True, None) and os.path.isdir(verify) else None,
        )
        if cert:
            tls_context.load_cert_chain(*(cert if isinstance(cert, tuple) else (cert,)))

    # Do not consult ambient netrc/proxy settings for a user-entered addon URL.
    with requests.Session() as preparation:
        preparation.trust_env = False
        preparation.headers.update(owner.headers)
        preparation.cookies.update(owner.cookies)
        preparation.auth = owner.auth
        preparation.params = owner.params
        prepared = preparation.prepare_request(requests.Request(
            'GET', url, headers=kwargs.get('headers'), params=kwargs.get('params'),
            cookies=kwargs.get('cookies'), auth=kwargs.get('auth'),
        ))
    if strip_sensitive:
        for name in list(prepared.headers):
            if name.lower() in _SENSITIVE_REDIRECT_HEADERS:
                del prepared.headers[name]
    attempt = AttemptHandle(deadline=deadline, cancelled=cancelled, clock=clock)
    connection = None
    try:
        timeout = kwargs.get('timeout')
        connect_cap = timeout[0] if isinstance(timeout, tuple) else timeout
        connection, target = open_connection(
            prepared.url, attempt, connect_cap=connect_cap,
            ssl_context=tls_context or default_tls_context(),
            **({'resolver': lambda *_args: vetted_addresses} if vetted_addresses else {}),
        )
        connection.request('GET', target, headers=dict(prepared.headers))
        reply = connection.getresponse()
        attempt.check()
        response = requests.Response()
        response.status_code = reply.status
        response.reason = reply.reason
        response.url = prepared.url
        response.request = prepared
        response.headers = requests.structures.CaseInsensitiveDict(reply.getheaders())
        response.raw = _BoundedReply(reply, connection, attempt)
        requests.cookies.extract_cookies_to_jar(owner.cookies, prepared, response.raw)
        return response
    except BaseException:
        if connection is not None:
            connection.close()
        attempt.close()
        raise


def read_bounded_http_body(
    response: Any,
    max_bytes: int = MAX_RESOURCE_JSON_BYTES,
    *,
    deadline: Optional[float] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    clock: Callable[[], float] = time.monotonic,
) -> bytes:
    """Read HTTP response bytes with strict Content-Encoding, deadline, and pre-decompression caps."""
    try:
        _check_budget(deadline, cancelled, clock)
        headers = getattr(response, "headers", None) or {}
        raw_encoding = str(headers.get("Content-Encoding") or "").strip().lower()
        if "," in raw_encoding or raw_encoding not in ALLOWED_CONTENT_ENCODINGS:
            raise ValueError("unsupported content encoding")
        content_length = headers.get("Content-Length")
        if content_length is not None and str(content_length).strip() != "":
            try:
                parsed_len = int(content_length)
            except (TypeError, ValueError):
                raise ValueError("invalid content length") from None
            if parsed_len < 0 or parsed_len > max_bytes:
                raise ValueError("response too large")

        raw_stream = getattr(response, "raw", None)
        if raw_stream is not None and hasattr(raw_stream, "read"):
            decompressor = None
            if raw_encoding in ("gzip", "x-gzip"):
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
            elif raw_encoding == "deflate":
                decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
            out = bytearray()
            wire_seen = 0
            while True:
                rem = _check_budget(deadline, cancelled, clock)
                _apply_stream_timeout(raw_stream, rem)
                read = getattr(raw_stream, 'read1', raw_stream.read)
                try:
                    chunk = read(8192, decode_content=False)
                except TypeError:
                    chunk = read(8192)
                if not chunk:
                    break
                _check_budget(deadline, cancelled, clock)
                wire_seen += len(chunk)
                if wire_seen > max_bytes:
                    raise ValueError("response too large")
                if decompressor is not None:
                    remaining = max_bytes + 1 - len(out)
                    try:
                        decoded = decompressor.decompress(chunk, max(1, remaining))
                    except zlib.error:
                        if raw_encoding == "deflate" and len(out) == 0 and wire_seen == len(chunk):
                            decompressor = zlib.decompressobj()
                            decoded = decompressor.decompress(chunk, max(1, remaining))
                        else:
                            raise ValueError("invalid compressed response") from None
                    out.extend(decoded)
                    if len(out) > max_bytes or decompressor.unconsumed_tail:
                        raise ValueError("response too large")
                else:
                    out.extend(chunk)
                    if len(out) > max_bytes:
                        raise ValueError("response too large")
            if decompressor is not None:
                out.extend(decompressor.flush(max_bytes + 1 - len(out)))
                if len(out) > max_bytes:
                    raise ValueError("response too large")
            _check_budget(deadline, cancelled, clock)
            return bytes(out)

        content = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            _check_budget(deadline, cancelled, clock)
            if not chunk:
                continue
            content.extend(chunk)
            if len(content) > max_bytes:
                raise ValueError("response too large")
        _check_budget(deadline, cancelled, clock)
        return bytes(content)
    except BaseException:
        _close_quietly(response)
        raise


def is_safe_http_url(url: Any, resolve_dns: bool = True) -> bool:
    """Return whether *url* is a public HTTP(S) destination."""
    try:
        parts = urlsplit(str(url or ""))
        if (
            parts.scheme.lower() not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            return False
        try:
            addresses = [str(ipaddress.ip_address(parts.hostname))]
        except ValueError:
            if not resolve_dns:
                return True
            from .bounded_http import AttemptHandle, resolve_addresses
            context = _VALIDATION_CONTEXT.get()
            attempt = context['attempt'] if context else AttemptHandle(deadline=time.monotonic() + 5)
            port = parts.port or (443 if parts.scheme.lower() == 'https' else 80)
            try:
                resolved = resolve_addresses(
                    parts.hostname, port, attempt,
                    resolver=lambda host, port, *_: socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM),
                )
            finally:
                if context is None:
                    attempt.close()
            addresses = [entry[4][0] for entry in resolved]
            if context is not None:
                context['addresses'][parts.hostname] = resolved
        if not addresses:
            return False
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                return False
        return True
    except (OSError, ValueError):
        return False


def is_safe_https_url(url: Any, resolve_dns: bool = True) -> bool:
    """Return whether *url* is a public HTTPS destination."""
    parts = urlsplit(str(url or ""))
    return parts.scheme.lower() == "https" and is_safe_http_url(url, resolve_dns=resolve_dns)


def canonical_https_manifest_url(url: Any) -> str:
    """Normalize an https:// or stremio:// manifest URL, or return empty string."""
    normalized = str(url or "").strip()
    if normalized.startswith("stremio://"):
        normalized = normalized.replace("stremio://", "https://", 1)
    parts = urlsplit(normalized)
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
        or not parts.path.rstrip("/").endswith("/manifest.json")
    ):
        return ""
    return urlunsplit(("https", parts.netloc, parts.path, parts.query, ""))


def configured_addon_url_validator(initial_url: str) -> Callable[[str], bool]:
    """Allow the configured addon origin on hop 0 and require safe non-downgraded hops on redirects."""
    init_parts = urlsplit(str(initial_url or ""))
    init_origin = _origin_tuple(initial_url)

    def _valid(candidate: str) -> bool:
        parts = urlsplit(str(candidate or ""))
        scheme = parts.scheme.lower()
        if (
            scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.fragment
        ):
            return False
        if init_parts.scheme.lower() == "https" and scheme != "https":
            return False
        if _origin_tuple(candidate) == init_origin:
            return True
        return is_safe_http_url(candidate)

    return _valid


def request_with_safe_redirects(
    request: Callable[..., Any],
    url: str,
    validator: Callable[[str], bool],
    *,
    deadline: Optional[float] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    clock: Callable[[], float] = time.monotonic,
    **kwargs: Any,
) -> Any:
    """Request a URL while validating every redirect and closing intermediate responses."""
    target = url
    seen_targets = set()
    base_headers = dict(kwargs.get("headers") or {}) if kwargs.get("headers") is not None else None
    base_timeout = kwargs.get("timeout")
    strip_sensitive = False

    for hop in range(MAX_REDIRECTS + 1):
        rem = _check_budget(deadline, cancelled, clock)
        if target in seen_targets:
            raise ValueError("redirect loop")
        seen_targets.add(target)
        from .bounded_http import AttemptHandle
        validation = {'attempt': AttemptHandle(
            deadline=deadline if deadline is not None else clock() + 5,
            cancelled=cancelled, clock=clock,
        ), 'addresses': {}}
        validation_token = _VALIDATION_CONTEXT.set(validation)
        try:
            valid = validator(target)
        finally:
            _VALIDATION_CONTEXT.reset(validation_token)
            validation['attempt'].close()
        _check_budget(deadline, cancelled, clock)
        if not valid:
            raise ValueError("unsafe request destination")

        call_kwargs = dict(kwargs)
        if rem is not None:
            if isinstance(base_timeout, (int, float)):
                call_kwargs["timeout"] = max(0.005, min(float(base_timeout), rem))
            else:
                call_kwargs["timeout"] = max(0.005, rem)

        if deadline is None:
            response = request(target, allow_redirects=False, **call_kwargs)
        else:
            response = _bounded_requests_get(
                request, target, deadline=deadline, cancelled=cancelled, clock=clock,
                strip_sensitive=strip_sensitive,
                vetted_addresses=validation['addresses'].get(urlsplit(target).hostname),
                kwargs=call_kwargs,
            )
        try:
            _check_budget(deadline, cancelled, clock)
            status = getattr(response, "status_code", None)
            if status not in {301, 302, 303, 307, 308}:
                return response
            location = (getattr(response, "headers", {}) or {}).get("Location")
            if not location:
                return response
            next_target = urljoin(target, location)
        except BaseException:
            _close_quietly(response)
            raise

        # Intermediate 3xx response MUST be closed before following or rejecting next hop (SRC-06).
        _close_quietly(response)

        if hop >= MAX_REDIRECTS:
            raise ValueError("too many redirects")
        if urlsplit(target).scheme.lower() == "https" and urlsplit(next_target).scheme.lower() == "http":
            raise ValueError("unsafe redirect downgrade")
        if base_headers is not None and _origin_tuple(next_target) != _origin_tuple(target):
            base_headers = {
                k: v for k, v in base_headers.items() if k.lower() not in _SENSITIVE_REDIRECT_HEADERS
            }
            kwargs["headers"] = dict(base_headers)
        if _origin_tuple(next_target) != _origin_tuple(target):
            strip_sensitive = True
        target = next_target

    raise ValueError("too many redirects")


def response_json(
    response: Any,
    max_bytes: int = MAX_RESOURCE_JSON_BYTES,
    *,
    deadline: Optional[float] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    clock: Callable[[], float] = time.monotonic,
) -> Any:
    """Decode a bounded JSON response with streaming wire/decoded enforcement and response close."""
    try:
        _check_budget(deadline, cancelled, clock)
        headers = getattr(response, "headers", None) or {}
        content_length = headers.get("Content-Length")
        if content_length is not None and str(content_length).strip() != "":
            try:
                parsed_len = int(content_length)
            except (TypeError, ValueError):
                raise ValueError("JSON response too large") from None
            if parsed_len < 0 or parsed_len > max_bytes:
                raise ValueError("JSON response too large")

        already_buffered = getattr(response, "_content", False)
        has_stream = (
            getattr(response, "raw", None) is not None or hasattr(response, "iter_content")
        ) and already_buffered is False
        if has_stream:
            try:
                raw = read_bounded_http_body(
                    response,
                    max_bytes=max_bytes,
                    deadline=deadline,
                    cancelled=cancelled,
                    clock=clock,
                )
            except ValueError as exc:
                if "too large" in str(exc) or "content length" in str(exc):
                    raise ValueError("JSON response too large") from None
                raise
            return json.loads(raw.decode("utf-8"))

        content = getattr(response, "content", None)
        if isinstance(content, (bytes, bytearray)):
            if len(content) > max_bytes:
                raise ValueError("JSON response too large")
            return json.loads(content.decode("utf-8"))
        return response.json()
    finally:
        _close_quietly(response)


def cache_ttl_seconds(value: Any, default: int) -> int:
    """Clamp a Stremio cacheMaxAge value to the supported cache lifetime."""
    try:
        ttl = int(default if value is None else value)
    except (TypeError, ValueError):
        ttl = int(default)
    if ttl <= 0:
        return 0
    return min(MAX_CACHE_TTL_SECONDS, max(MIN_CACHE_TTL_SECONDS, ttl))


def safe_cache_key(prefix: str, identity: Any) -> str:
    """Build a deterministic cache key without exposing identity values."""
    payload = json.dumps(identity, sort_keys=True, default=str, separators=(",", ":"))
    return "{}:{}".format(prefix, hashlib.sha256(payload.encode("utf-8")).hexdigest())


def build_resource_url(
    base_url: str,
    resource: str,
    resource_type: str,
    resource_id: Any,
    extras: Optional[Mapping[str, Any]] = None,
) -> str:
    """Build an official Stremio HTTP resource route."""
    base, _, base_query = str(base_url or "").partition("?")
    components = [resource, resource_type, resource_id]
    path = "/".join(quote(str(component), safe="") for component in components)
    extra_pairs = []
    for key in sorted(extras or {}, key=lambda value: str(value)):
        value = extras[key]
        if value in (None, ""):
            continue
        extra_pairs.append("{}={}".format(quote(str(key), safe=""), quote(str(value), safe="")))
    if extra_pairs:
        path += "/" + "&".join(extra_pairs)
    url = "{}/{}.json".format(base.rstrip("/"), path)
    if base_query:
        url = f"{url}?{base_query}"
    return url

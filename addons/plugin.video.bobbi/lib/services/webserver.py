"""
Local web server for paired phone management (/manage).

Exposes bounded HTTP transport for PhoneManagement and internal Stremio
custom-addon helpers invoked strictly through paired PhoneManagement scopes.
"""

import ipaddress
import json
import os
import re
import socket
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from lib.api.stremio.addon_manager import build_addon_instance_key
from lib.clients.stremio.constants import (
    STREMIO_ADDONS_CATALOGS_KEY,
    STREMIO_ADDONS_KEY,
    STREMIO_TV_ADDONS_KEY,
    STREMIO_USER_ADDONS,
    decode_selected_ids,
    encode_selected_ids,
)
from bobbi_core.http_policy import read_bounded_http_body
from lib.clients.stremio.protocol import (
    MAX_RESOURCE_JSON_BYTES,
    is_safe_http_url,
    request_with_safe_redirects,
)
from lib.db.cached import cache
from lib.utils.general.utils import USER_AGENT_HEADER
from lib.utils.kodi.utils import kodilog

_CACHE_EXPIRY = timedelta(days=365 * 20)
_WEB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "resources",
    "web",
)


def _get_user_addons():
    """Return list of custom addon dicts from cache."""
    return [a for a in (cache.get(STREMIO_USER_ADDONS) or []) if a.get("transportName") == "custom"]


def _get_selected_ids():
    """Return dict of selected addon IDs per category."""
    result = {}
    for key, label in [
        (STREMIO_ADDONS_KEY, "stream"),
        (STREMIO_ADDONS_CATALOGS_KEY, "catalog"),
        (STREMIO_TV_ADDONS_KEY, "tv"),
    ]:
        result[label] = decode_selected_ids(cache.get(key))
    return result


def _addon_capabilities(manifest):
    """Determine stream/catalog/tv capabilities from a manifest dict."""

    def supports_searchable_stream(prefixes):
        normalized = {str(prefix).rstrip(":") for prefix in (prefixes or []) if prefix}
        return not normalized or bool(normalized.intersection({"tt", "tmdb"}))

    resources = manifest.get("resources", []) if isinstance(manifest, dict) else []
    types = manifest.get("types", []) if isinstance(manifest, dict) else []
    manifest_prefixes = manifest.get("idPrefixes", []) if isinstance(manifest, dict) else []
    is_stream = False
    is_catalog = False
    is_tv = False

    for res in resources:
        if isinstance(res, dict):
            res_name = res.get("name")
            res_types = res.get("types", types)
            res_prefixes = res.get("idPrefixes", manifest_prefixes)

            if res_name == "stream":
                if any(
                    t in res_types for t in ("movie", "series", "anime")
                ) and supports_searchable_stream(res_prefixes):
                    is_stream = True
                if any(t in res_types for t in ("tv", "channel")):
                    is_tv = True
            if res_name == "catalog":
                is_catalog = True

        elif isinstance(res, str):
            if res == "stream":
                if any(
                    t in types for t in ("movie", "series", "anime")
                ) and supports_searchable_stream(manifest_prefixes):
                    is_stream = True
                if any(t in types for t in ("tv", "channel")):
                    is_tv = True
            if res == "catalog":
                is_catalog = True

    return {"stream": is_stream, "catalog": is_catalog, "tv": is_tv}


def _normalize_manifest_url(url):
    normalized = url.strip()
    if not normalized:
        return ""

    if normalized.startswith("stremio://"):
        normalized = normalized.replace("stremio://", "https://", 1)

    parts = urlsplit(normalized)
    path = parts.path or ""
    if not path.endswith("/manifest.json"):
        if path.endswith("/"):
            path = f"{path}manifest.json"
        else:
            path = f"{path}/manifest.json"

    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _is_local_or_private_host(url):
    """Whether the URL host is an IP literal or resolves to a private/loopback address."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return False
    if host == "localhost":
        return True

    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        pass

    try:
        addresses = [entry[4][0] for entry in socket.getaddrinfo(host, None)]
    except (OSError, UnicodeError):
        return False

    if not addresses:
        return False

    return all(_is_local_ip(address) for address in addresses)


def _is_local_ip(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def _safe_url_description(url):
    parts = urlsplit(str(url or ""))
    if parts.scheme and parts.hostname:
        return f"{parts.scheme}://{parts.hostname}/<redacted>"
    return "<redacted URL>"


def _allowed_manifest_url(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or parts.username or parts.password:
        return False
    if parts.scheme == "http":
        return _is_local_or_private_host(url)
    return is_safe_http_url(url) or _is_local_or_private_host(url)


def stremio_logo_status(raw_logo, transport_url=""):
    """Validate manifest logo URL protocol without exposing credentials or executing scripts."""
    if raw_logo is None or raw_logo == "":
        return "", False
    if type(raw_logo) is not str or len(raw_logo) > 1024 or re.search(r'[\x00-\x20\x7f"\'<>\\]', raw_logo):
        return "", True
    raw_parts = urlsplit(raw_logo)
    scheme = raw_parts.scheme.lower()
    if scheme and scheme not in ("http", "https"):
        return "", True
    if not scheme:
        if raw_logo.startswith("//") or not transport_url:
            return "", True
        candidate = urljoin(transport_url, raw_logo)
    else:
        candidate = raw_logo
    parts = urlsplit(candidate)
    if (
        parts.scheme.lower() not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
    ):
        return "", True
    if (
        parts.scheme.lower() == "https"
        and parts.hostname.lower() == "image.tmdb.org"
        and re.fullmatch(r"/[A-Za-z0-9/_.-]{1,240}\.(?:jpg|jpeg|png|webp)", parts.path, re.IGNORECASE)
        and not parts.query
    ):
        return urlunsplit(("https", "image.tmdb.org", parts.path, "", "")), False
    return "", False


def format_stremio_addon(addon, selected=None):
    """Project minimal browser-safe addon metadata without transportUrl secrets."""
    manifest = addon.get("manifest") if isinstance(addon.get("manifest"), dict) else {}
    transport_url = str(addon.get("transportUrl") or "")
    addon_key = str(build_addon_instance_key(addon))
    caps = _addon_capabilities(manifest)
    safe_logo, logo_rejected = stremio_logo_status(manifest.get("logo"), transport_url)
    host = (urlsplit(transport_url).hostname or "")[:255]
    raw_types = manifest.get("types") if isinstance(manifest.get("types"), list) else []
    types = [t for t in raw_types if type(t) is str and len(t) <= 32 and not re.search(r"[\x00-\x1f\x7f]", t)][:8]
    if selected is None:
        sel = dict(caps)
    else:
        sel = {cat: addon_key in selected.get(cat, []) for cat in ("stream", "catalog", "tv")}
    return {
        "id": addon_key[:512],
        "name": str(manifest.get("name") or manifest.get("id") or "Unknown")[:240],
        "description": str(manifest.get("description") or "")[:600],
        "version": str(manifest.get("version") or "")[:64],
        "host": host,
        "logo": safe_logo,
        "logo_rejected": logo_rejected,
        "types": types,
        "capabilities": caps,
        "selected": sel,
    }


def _fetch_manifest(url):
    session = requests.Session()
    session.trust_env = False
    resp = None
    deadline = time.monotonic() + 10.0
    try:
        if not _allowed_manifest_url(url):
            raise ValueError("manifest destination rejected")
        kodilog(f"[WebServer] Fetching Stremio manifest: {_safe_url_description(url)}")
        headers = dict(USER_AGENT_HEADER)
        headers.setdefault("Accept-Encoding", "identity")
        resp = request_with_safe_redirects(
            session.get,
            url,
            validator=_allowed_manifest_url,
            headers=headers,
            timeout=10,
            deadline=deadline,
            stream=True,
        )
        resp.raise_for_status()
        if not _allowed_manifest_url(resp.url):
            raise ValueError("manifest redirect rejected")
        raw = read_bounded_http_body(resp, max_bytes=MAX_RESOURCE_JSON_BYTES, deadline=deadline)
        manifest = json.loads(raw.decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest invalid")
        return resp, manifest, None
    except ValueError as ex:
        return None, None, str(ex) or type(ex).__name__
    except Exception as ex:
        return None, None, type(ex).__name__
    finally:
        if resp is not None and hasattr(resp, "close"):
            resp.close()
        session.close()


def prepare_stremio_addon(url):
    """Fetch and validate a manifest URL without mutating cache."""
    url = (url or "").strip()
    if not url:
        return None, None, "STREMIO_URL_REQUIRED"
    normalized = _normalize_manifest_url(url)
    resp, manifest, error = _fetch_manifest(normalized)
    if error or not resp or not isinstance(manifest, dict):
        kodilog(f"[WebServer] Manifest fetch failed: {error}")
        return None, None, "STREMIO_MANIFEST_UNAVAILABLE"
    if not manifest.get("id") and not manifest.get("name"):
        return None, None, "STREMIO_MANIFEST_INVALID"
    _, logo_rejected = stremio_logo_status(manifest.get("logo"), resp.url)
    if logo_rejected:
        return None, None, "STREMIO_LOGO_REJECTED"
    return resp.url, manifest, None


def commit_stremio_addon(resolved_url, manifest):
    """Persist an already-validated Stremio manifest into current profile cache."""
    addon_key = build_addon_instance_key({"manifest": manifest, "transportUrl": resolved_url})
    user_addons = list(cache.get(STREMIO_USER_ADDONS) or [])
    if any(build_addon_instance_key(a) == addon_key for a in user_addons):
        return None, "STREMIO_ADDON_EXISTS"
    caps = _addon_capabilities(manifest)
    if caps["stream"]:
        _add_to_selection(STREMIO_ADDONS_KEY, addon_key)
    if caps["catalog"]:
        _add_to_selection(STREMIO_ADDONS_CATALOGS_KEY, addon_key)
    if caps["tv"]:
        _add_to_selection(STREMIO_TV_ADDONS_KEY, addon_key)
    custom_addon = {
        "manifest": manifest,
        "transportUrl": resolved_url,
        "transportName": "custom",
    }
    user_addons.append(custom_addon)
    cache.set(STREMIO_USER_ADDONS, user_addons, _CACHE_EXPIRY)
    return custom_addon, None


def list_stremio_addons(*, summary=False):
    selected = _get_selected_ids()
    out = []
    for addon in _get_user_addons():
        item = format_stremio_addon(addon, selected=selected)
        if summary and len(item["description"]) > 160:
            item["description"] = item["description"][:160] + "…"
            item["description_truncated"] = True
        out.append(item)
    return out


def get_stremio_addon(addon_id):
    selected = _get_selected_ids()
    for addon in _get_user_addons():
        if build_addon_instance_key(addon) == addon_id:
            return format_stremio_addon(addon, selected=selected)
    return None


def remove_stremio_addon(addon_id):
    """Remove custom addon by instance key from caches; returns True if removed."""
    user_addons = list(cache.get(STREMIO_USER_ADDONS) or [])
    new_addons = [
        a for a in user_addons
        if not (a.get("transportName") == "custom" and build_addon_instance_key(a) == addon_id)
    ]
    if len(new_addons) == len(user_addons):
        return False
    cache.set(STREMIO_USER_ADDONS, new_addons, _CACHE_EXPIRY)
    for cache_key in (
        STREMIO_ADDONS_KEY,
        STREMIO_ADDONS_CATALOGS_KEY,
        STREMIO_TV_ADDONS_KEY,
    ):
        selected = cache.get(cache_key)
        if selected:
            keys = decode_selected_ids(selected)
            filtered = [k for k in keys if k != addon_id]
            if len(filtered) != len(keys):
                cache.set(cache_key, encode_selected_ids(filtered), _CACHE_EXPIRY)
    return True


def toggle_stremio_addon(addon_id, category, enabled):
    """Toggle category selection for an existing custom addon."""
    if not any(build_addon_instance_key(a) == addon_id for a in _get_user_addons()):
        return False
    key_map = {
        "stream": STREMIO_ADDONS_KEY,
        "catalog": STREMIO_ADDONS_CATALOGS_KEY,
        "tv": STREMIO_TV_ADDONS_KEY,
    }
    cache_key = key_map.get(category)
    if not cache_key:
        return False
    keys = list(decode_selected_ids(cache.get(cache_key)))
    if enabled and addon_id not in keys:
        keys.append(addon_id)
    elif not enabled and addon_id in keys:
        keys.remove(addon_id)
    cache.set(cache_key, encode_selected_ids(keys), _CACHE_EXPIRY)
    return True


def _add_to_selection(cache_key, addon_id):
    keys = list(decode_selected_ids(cache.get(cache_key)))
    if addon_id not in keys:
        keys.append(addon_id)
        cache.set(cache_key, encode_selected_ids(keys), _CACHE_EXPIRY)


class StremioRequestHandler(BaseHTTPRequestHandler):
    """Serves paired PhoneManagement routes only; legacy anonymous CRUD is retired."""

    def log_message(self, format, *args):
        return

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def handle_one_request(self):
        self._management_body_attempted = False
        self._management_body_deadline = time.monotonic() + 3
        return super().handle_one_request()

    def _management_body_length(self):
        from lib.services.phone_management import MAX_BODY
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") is not None or len(lengths) != 1:
            return None
        length = lengths[0]
        if not length.isascii() or not length.isdecimal() or len(length) > 10:
            return None
        length = int(length)
        return length if 0 < length <= MAX_BODY else None

    def _management_read_body(self, length):
        self._management_body_attempted = True
        chunks = []
        remaining = length
        previous_timeout = self.connection.gettimeout()
        try:
            while remaining:
                timeout = self._management_body_deadline - time.monotonic()
                if timeout <= 0:
                    raise TimeoutError("management request deadline")
                self.connection.settimeout(timeout)
                chunk = self.rfile.read1(remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            self.connection.settimeout(previous_timeout)

    def _management_discard_body(self):
        if self._management_body_attempted:
            return
        length = self._management_body_length()
        if length is not None:
            try:
                self._management_read_body(length)
            except OSError:
                pass

    def send_error(self, code, message=None, explain=None):
        if hasattr(self, "headers"):
            self._management_discard_body()
        return super().send_error(code, message, explain)

    def _management_reply(self, value, status=200, cookie=None, content_type="application/json; charset=utf-8"):
        from lib.services.phone_management import encode
        body = value if type(value) is bytes else encode(value)
        self._management_discard_body()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https://image.tmdb.org; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _management(self, post=False):
        from lib.services.phone_management import PhoneError
        manager = getattr(self.server, "phone_management", None)
        if manager is None:
            self._management_reply(dict(error="PAIRING_REQUIRED"), 401)
            return
        try:
            manager.check_origin(self.headers, write=post)
            if not post:
                resource = {
                    "/manage": ("manage.html", "text/html; charset=utf-8"),
                    "/manage.js": ("manage.js", "application/javascript; charset=utf-8"),
                }.get(self.path)
                if resource is None:
                    raise PhoneError("NOT_FOUND", 404)
                with open(os.path.join(_WEB_DIR, resource[0]), "rb") as stream:
                    self._management_reply(stream.read(131072), content_type=resource[1])
                return
            if self.headers.get("Transfer-Encoding") is not None:
                raise PhoneError("INVALID_REQUEST", 400)
            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if self.path == "/manage/api/subtitle-multipart" and ctype == "multipart/form-data":
                handler = self

                class _BoundedMultipartStream:
                    def read(self, n=-1):
                        handler._management_body_attempted = True
                        return handler.rfile.read1(n) if hasattr(handler.rfile, "read1") else handler.rfile.read(n)

                result, cookie = manager.handle_subtitle_multipart(self.headers, _BoundedMultipartStream())
                self._management_reply(result, cookie=cookie)
                return
            if ctype != "application/json":
                raise PhoneError("INVALID_REQUEST", 400)
            length = self._management_body_length()
            if length is None:
                raise PhoneError("REQUEST_TOO_LARGE", 413)
            raw = self._management_read_body(length)
            if len(raw) != length:
                raise PhoneError("INVALID_REQUEST", 400)
            result, cookie = manager.handle(self.path, self.headers, raw)
            self._management_reply(result, cookie=cookie)
        except PhoneError as error:
            self._management_reply(dict(error=str(error)), error.status)
        except (OSError, ValueError, KeyError, TypeError):
            self._management_reply(dict(error="MANAGEMENT_UNAVAILABLE"), 503)

    def do_GET(self):
        if self.path.startswith("/manage"):
            self._management()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith("/manage"):
            self._management(post=True)
        else:
            self.send_error(404)

    def do_DELETE(self):
        self.send_error(404)

    def do_PUT(self):
        self.send_error(404)

    def do_OPTIONS(self):
        self._management_reply(dict(error="ORIGIN_FORBIDDEN"), 403)


class StremioWebServer:
    """Threaded HTTP server requiring an explicit PhoneManagement grant."""

    def __init__(self, port=8081, phone_management=None):
        if phone_management is None:
            raise ValueError("PHONE_MANAGEMENT_REQUIRED")
        self.port = port
        self._server = None
        self._thread = None
        self.phone_management = phone_management

    def start(self):
        if self._server:
            return
        try:
            self._server = HTTPServer(("0.0.0.0", self.port), StremioRequestHandler)
            self.port = self._server.server_port
            self._server.phone_management = self.phone_management
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            kodilog(f"[WebServer] Started paired management server on port {self.port}")
        except Exception as e:
            kodilog(f"[WebServer] Failed to start: {e}")
            self._server = None

    def stop(self):
        if self.phone_management is not None:
            self.phone_management.revoke()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
            kodilog("[WebServer] Stopped")

    @property
    def is_running(self):
        return self._server is not None


def get_local_ip():
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

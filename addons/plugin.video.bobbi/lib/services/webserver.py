"""
Local web server for managing Stremio addon sources from a phone/browser.

Serves a web UI and exposes small JSON endpoints for CRUD operations
on the Stremio custom addons stored in the Kodi addon cache.
"""

import ipaddress
import json
import os
import socket
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit, urlunsplit

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


# ---------------------------------------------------------------------------
# Sync helpers (no xbmcgui imports — safe for HTTP thread)
# ---------------------------------------------------------------------------


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

    resources = manifest.get("resources", [])
    types = manifest.get("types", [])
    manifest_prefixes = manifest.get("idPrefixes", [])
    is_stream = False
    is_catalog = False
    is_tv = False

    for res in resources:
        if isinstance(res, dict):
            res_name = res.get("name")
            res_types = res.get("types", types)
            res_prefixes = res.get("idPrefixes", manifest_prefixes)

            if res_name == "stream":
                # Stremio addon providing streams
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
    return is_safe_http_url(url) or _is_local_or_private_host(url)


def _fetch_manifest(url, initial_url):
    def try_fetch(target_url):
        try:
            if not _allowed_manifest_url(target_url):
                raise ValueError("manifest destination rejected")
            kodilog(f"[WebServer] Fetching Stremio manifest: {_safe_url_description(target_url)}")
            resp = request_with_safe_redirects(
                requests.get,
                target_url,
                validator=_allowed_manifest_url,
                headers=USER_AGENT_HEADER,
                timeout=10,
                stream=True,
            )
            resp.raise_for_status()
            if not _allowed_manifest_url(resp.url):
                raise ValueError("manifest redirect rejected")
            content = bytearray()
            for chunk in resp.iter_content(chunk_size=8192):
                content.extend(chunk)
                if len(content) > MAX_RESOURCE_JSON_BYTES:
                    raise ValueError("manifest too large")
            manifest = json.loads(content.decode("utf-8"))
            return resp, manifest, None
        except ValueError as ex:
            # ValueError here comes from our own validation or JSON decoding;
            # the message is static and safe to surface to the UI.
            return None, None, str(ex) or type(ex).__name__
        except Exception as ex:
            return None, None, type(ex).__name__

    resp, manifest, error = try_fetch(url)

    if (
        error
        and url.startswith("https://")
        and (initial_url.startswith("stremio://") or _is_local_or_private_host(url))
    ):
        http_url = url.replace("https://", "http://", 1)
        kodilog(
            f"[WebServer] HTTPS failed, trying HTTP fallback: {_safe_url_description(http_url)}"
        )
        r2, m2, e2 = try_fetch(http_url)
        if not e2:
            return r2, m2, None

    return resp, manifest, error


def _sync_add_addon(url):
    """Fetch manifest from URL, validate, store in cache.  Returns (addon_dict, error)."""
    url = (url or "").strip()
    if not url:
        return None, "Empty URL provided."

    initial_url = url
    url = _normalize_manifest_url(url)

    resp, manifest, error = _fetch_manifest(url, initial_url)

    if error or not resp or not manifest:
        kodilog(f"[WebServer] Failed to add addon: {error}")
        return None, f"Failed to fetch manifest: {error or 'unknown error'}"

    addon_key = build_addon_instance_key({"manifest": manifest, "transportUrl": resp.url})

    # Check duplicate
    user_addons = list(cache.get(STREMIO_USER_ADDONS) or [])
    if any(build_addon_instance_key(a) == addon_key for a in user_addons):
        return None, "This addon is already added."

    caps = _addon_capabilities(manifest)

    # Auto-select into categories
    if caps["stream"]:
        _add_to_selection(STREMIO_ADDONS_KEY, addon_key)
    if caps["catalog"]:
        _add_to_selection(STREMIO_ADDONS_CATALOGS_KEY, addon_key)
    if caps["tv"]:
        _add_to_selection(STREMIO_TV_ADDONS_KEY, addon_key)

    custom_addon = {
        "manifest": manifest,
        "transportUrl": resp.url,
        "transportName": "custom",
    }
    user_addons.append(custom_addon)
    cache.set(STREMIO_USER_ADDONS, user_addons, _CACHE_EXPIRY)

    return custom_addon, None


def _sync_remove_addon(addon_id):
    """Remove addon by manifest ID from all caches."""
    user_addons = list(cache.get(STREMIO_USER_ADDONS) or [])
    new_addons = [a for a in user_addons if build_addon_instance_key(a) != addon_id]
    cache.set(STREMIO_USER_ADDONS, new_addons, _CACHE_EXPIRY)

    for cache_key in [
        STREMIO_ADDONS_KEY,
        STREMIO_ADDONS_CATALOGS_KEY,
        STREMIO_TV_ADDONS_KEY,
    ]:
        selected = cache.get(cache_key)
        if selected:
            keys = decode_selected_ids(selected)
            keys = [k for k in keys if k != addon_id]
            cache.set(cache_key, encode_selected_ids(keys), _CACHE_EXPIRY)


def _sync_toggle_addon(addon_id, category, enabled):
    """Add or remove addon_id from a selection category."""
    key_map = {
        "stream": STREMIO_ADDONS_KEY,
        "catalog": STREMIO_ADDONS_CATALOGS_KEY,
        "tv": STREMIO_TV_ADDONS_KEY,
    }
    cache_key = key_map.get(category)
    if not cache_key:
        return

    keys = list(decode_selected_ids(cache.get(cache_key)))

    if enabled and addon_id not in keys:
        keys.append(addon_id)
    elif not enabled and addon_id in keys:
        keys.remove(addon_id)

    cache.set(cache_key, encode_selected_ids(keys), _CACHE_EXPIRY)


def _add_to_selection(cache_key, addon_id):
    keys = list(decode_selected_ids(cache.get(cache_key)))
    if addon_id not in keys:
        keys.append(addon_id)
        cache.set(cache_key, encode_selected_ids(keys), _CACHE_EXPIRY)


def _validate_manifest(url):
    """Fetch and validate a manifest URL.  Returns (manifest_dict, error)."""
    url = (url or "").strip()
    if not url:
        return None, "Empty URL"

    initial_url = url
    url = _normalize_manifest_url(url)

    kodilog(f"[WebServer] Validating Stremio manifest: {_safe_url_description(url)}")
    _, manifest, error = _fetch_manifest(url, initial_url)
    if error or not manifest:
        kodilog(f"[WebServer] Manifest validation failed: {error}")
        return None, str(error or "unknown error")

    if not manifest.get("id") and not manifest.get("name"):
        return None, "Manifest missing 'id' and 'name'."
    return manifest, None


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------


class StremioRequestHandler(BaseHTTPRequestHandler):
    """Handles web UI + JSON API requests."""

    def log_message(self, format, *args):
        if self.path.startswith('/manage'):
            return
        kodilog(f"[WebServer] {format % args}")

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def handle_one_request(self):
        self._management_body_attempted = False
        self._management_body_deadline = time.monotonic() + 3
        return super().handle_one_request()

    def _management_body_length(self):
        from lib.services.phone_management import MAX_BODY
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') is not None or len(lengths) != 1:
            return None
        length = lengths[0]
        if not length.isascii() or not length.isdecimal() or len(length) > 10:
            return None
        length = int(length)
        return length if 0 < length <= MAX_BODY else None

    def _management_read_body(self, length):
        # A rejected small request must not leave bytes unread when closing the
        # socket: Windows may otherwise reset it before delivering the reply.
        # Never make a second read after EOF, timeout, or a partially read POST.
        self._management_body_attempted = True
        chunks = []
        remaining = length
        previous_timeout = self.connection.gettimeout()
        try:
            while remaining:
                timeout = self._management_body_deadline - time.monotonic()
                if timeout <= 0:
                    raise TimeoutError('management request deadline')
                self.connection.settimeout(timeout)
                chunk = self.rfile.read1(remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            return b''.join(chunks)
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
                pass  # Preserve the already chosen rejection, without retrying.

    def send_error(self, code, message=None, explain=None):
        if (getattr(self.server, 'phone_management', None) is not None and
                hasattr(self, 'headers')):
            self._management_discard_body()
        return super().send_error(code, message, explain)

    def _management_reply(self, value, status=200, cookie=None, content_type='application/json; charset=utf-8'):
        from lib.services.phone_management import encode
        body = value if type(value) is bytes else encode(value)
        self._management_discard_body()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https://image.tmdb.org; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def _management(self, post=False):
        from lib.services.phone_management import PhoneError
        manager = getattr(self.server, 'phone_management', None)
        if manager is None:
            self.send_error(404)
            return
        try:
            manager.check_origin(self.headers, write=post)
            if not post:
                resource = {'/manage': ('manage.html', 'text/html; charset=utf-8'),
                            '/manage.js': ('manage.js', 'application/javascript; charset=utf-8')}.get(self.path)
                if resource is None:
                    raise PhoneError('NOT_FOUND', 404)
                with open(os.path.join(_WEB_DIR, resource[0]), 'rb') as stream:
                    self._management_reply(stream.read(131072), content_type=resource[1])
                return
            if (self.headers.get('Transfer-Encoding') is not None or
                    self.headers.get('Content-Type', '').split(';')[0] != 'application/json'):
                raise PhoneError('INVALID_REQUEST', 400)
            length = self._management_body_length()
            if length is None:
                raise PhoneError('REQUEST_TOO_LARGE', 413)
            raw = self._management_read_body(length)
            if len(raw) != length:
                raise PhoneError('INVALID_REQUEST', 400)
            result, cookie = manager.handle(self.path, self.headers, raw)
            self._management_reply(result, cookie=cookie)
        except PhoneError as error:
            self._management_reply(dict(error=str(error)), error.status)
        except (OSError, ValueError, KeyError, TypeError):
            self._management_reply(dict(error='MANAGEMENT_UNAVAILABLE'), 503)

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content):
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # --- Routes ---

    def do_GET(self):
        if self.path.startswith('/manage'):
            self._management()
        elif getattr(self.server, 'phone_management', None) is not None:
            self.send_error(404)
        elif self.path == "/" or self.path == "":
            self._serve_index()
        elif self.path == "/api/addons":
            self._api_get_addons()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith('/manage'):
            self._management(post=True)
        elif getattr(self.server, 'phone_management', None) is not None:
            self.send_error(404)
        elif self.path == "/api/addons":
            self._api_add_addon()
        elif self.path == "/api/addons/validate":
            self._api_validate()
        else:
            self.send_error(404)

    def do_DELETE(self):
        if getattr(self.server, 'phone_management', None) is not None:
            self.send_error(404)
            return
        if self.path.startswith("/api/addons/"):
            addon_id = self.path[len("/api/addons/") :]
            self._api_remove_addon(addon_id)
        else:
            self.send_error(404)

    def do_PUT(self):
        if getattr(self.server, 'phone_management', None) is not None:
            self.send_error(404)
            return
        if self.path.startswith("/api/addons/") and self.path.endswith("/toggle"):
            addon_id = self.path[len("/api/addons/") : -len("/toggle")]
            self._api_toggle_addon(addon_id)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        if self.path.startswith('/manage'):
            self._management_reply(dict(error='ORIGIN_FORBIDDEN'), 403)
            return
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # --- Handlers ---

    def _serve_index(self):
        index_path = os.path.join(_WEB_DIR, "index.html")
        try:
            with open(index_path, encoding="utf-8") as f:
                self._send_html(f.read())
        except FileNotFoundError:
            self.send_error(500, "Web UI not found")

    def _api_get_addons(self):
        addons = _get_user_addons()
        selected = _get_selected_ids()
        result = []
        for a in addons:
            manifest = a.get("manifest", {})
            transport_url = a.get("transportUrl", "")
            addon_key = build_addon_instance_key(a)
            caps = _addon_capabilities(manifest)

            logo = manifest.get("logo", "")
            if logo and transport_url and not logo.startswith(("http://", "https://")):
                from urllib.parse import urljoin

                logo = urljoin(transport_url, logo)

            result.append(
                {
                    "id": addon_key,
                    "name": manifest.get("name", "Unknown"),
                    "description": manifest.get("description", ""),
                    "logo": logo,
                    "version": manifest.get("version", ""),
                    "types": manifest.get("types", []),
                    "transportUrl": transport_url,
                    "capabilities": caps,
                    "selected": {
                        "stream": addon_key in selected.get("stream", []),
                        "catalog": addon_key in selected.get("catalog", []),
                        "tv": addon_key in selected.get("tv", []),
                    },
                }
            )
        self._send_json({"addons": result})

    def _api_add_addon(self):
        try:
            data = self._read_body()
        except Exception:
            self._send_json({"error": "Invalid JSON"}, 400)
            return
        url = data.get("url", "").strip()
        if not url:
            self._send_json({"error": "URL is required"}, 400)
            return
        addon, error = _sync_add_addon(url)
        if error or not addon:
            self._send_json({"error": error}, 400)
            return
        manifest = addon.get("manifest", {})
        transport_url = addon.get("transportUrl", "")
        addon_key = build_addon_instance_key(addon)
        caps = _addon_capabilities(manifest)

        logo = manifest.get("logo", "")
        if logo and transport_url and not logo.startswith(("http://", "https://")):
            from urllib.parse import urljoin

            logo = urljoin(transport_url, logo)

        self._send_json(
            {
                "success": True,
                "addon": {
                    "id": addon_key,
                    "name": manifest.get("name", "Unknown"),
                    "description": manifest.get("description", ""),
                    "logo": logo,
                    "version": manifest.get("version", ""),
                    "types": manifest.get("types", []),
                    "transportUrl": addon.get("transportUrl", ""),
                    "capabilities": caps,
                    "selected": caps,
                },
            }
        )

    def _api_remove_addon(self, addon_id):
        from urllib.parse import unquote

        addon_id = unquote(addon_id)
        _sync_remove_addon(addon_id)
        self._send_json({"success": True})

    def _api_toggle_addon(self, addon_id):
        from urllib.parse import unquote

        addon_id = unquote(addon_id)
        try:
            data = self._read_body()
        except Exception:
            self._send_json({"error": "Invalid JSON"}, 400)
            return
        category = data.get("category")
        enabled = data.get("enabled", False)
        if category not in ("stream", "catalog", "tv"):
            self._send_json({"error": "Invalid category"}, 400)
            return
        _sync_toggle_addon(addon_id, category, enabled)
        self._send_json({"success": True})

    def _api_validate(self):
        try:
            data = self._read_body()
        except Exception:
            self._send_json({"error": "Invalid JSON"}, 400)
            return
        url = data.get("url", "").strip()
        if not url:
            self._send_json({"error": "URL is required"}, 400)
            return
        manifest, error = _validate_manifest(url)
        if error:
            self._send_json({"error": error}, 400)
            return
        self._send_json({"valid": True, "manifest": manifest})


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


class StremioWebServer:
    """Threaded HTTP server that starts/stops on demand."""

    def __init__(self, port=8081, phone_management=None):
        self.port = port
        self._server = None
        self._thread = None
        self.phone_management = phone_management

    def start(self):
        if self._server:
            return
        try:
            self._server = HTTPServer(("0.0.0.0", self.port), StremioRequestHandler)
            self._server.phone_management = self.phone_management
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            kodilog(f"[WebServer] Started on port {self.port}")
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

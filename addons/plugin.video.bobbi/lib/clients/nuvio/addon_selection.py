import hashlib
import json
import time
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import requests
import xbmcgui

from bobbi_core.http_policy import (
    canonical_https_manifest_url,
    is_safe_https_url,
    read_bounded_http_body,
    request_with_safe_redirects,
)
from lib.api.nuvio import NuvioClient
from lib.clients.nuvio.constants import (
    NUVIO_ADDONS_KEY,
    NUVIO_USER_ADDONS,
    decode_selected_ids,
    encode_selected_ids,
)
from lib.db.cached import cache
from lib.utils.general.utils import USER_AGENT_HEADER
from lib.utils.kodi.settings import get_int_setting
from lib.utils.kodi.utils import kodilog, translation

MAX_MANIFEST_BYTES = 512 * 1024


def _safe_manifest_url(url):
    return canonical_https_manifest_url(url)


def _fetch_manifest(url, *, cancelled=None):
    manifest_url = _safe_manifest_url(url)
    if not manifest_url or not is_safe_https_url(manifest_url):
        raise ValueError("invalid manifest URL")
    timeout_s = max(1, int(get_int_setting("stremio_timeout") or 10))
    deadline = time.monotonic() + timeout_s
    headers = dict(USER_AGENT_HEADER)
    headers.setdefault("Accept-Encoding", "identity")
    session = requests.Session()
    session.trust_env = False
    response = None
    try:
        response = request_with_safe_redirects(
            session.get,
            manifest_url,
            validator=is_safe_https_url,
            headers=headers,
            timeout=timeout_s,
            deadline=deadline,
            cancelled=cancelled,
            stream=True,
        )
        response.raise_for_status()
        final_url = _safe_manifest_url(response.url)
        if not final_url or not is_safe_https_url(final_url):
            raise ValueError("unsafe redirect")
        raw = read_bounded_http_body(
            response,
            max_bytes=MAX_MANIFEST_BYTES,
            deadline=deadline,
            cancelled=cancelled,
        )
    finally:
        if response is not None and hasattr(response, "close"):
            response.close()
        session.close()
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict) or not (manifest.get("id") or manifest.get("name")):
        raise ValueError("invalid manifest")
    if not isinstance(manifest.get("resources", []), (list, dict, str)):
        raise ValueError("invalid manifest resources")
    return manifest, final_url


def _addon_key(record):
    manifest = record.get("manifest") or {}
    addon_id = manifest.get("id") or record.get("name") or ""
    transport_url = record.get("transportUrl") or ""
    normalized = _safe_manifest_url(transport_url)
    if not normalized:
        return str(addon_id)
    parts = urlsplit(normalized)
    path = parts.path.rstrip("/")
    if path.endswith("/manifest.json"):
        path = path[: -len("/manifest.json")]
    base_url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))
    digest = hashlib.sha256(base_url.encode("utf-8")).hexdigest()[:16]
    return f"{addon_id}|{digest}" if addon_id else digest


def _build_options(records):
    options = []
    for record in records:
        manifest = record["manifest"]
        item = xbmcgui.ListItem(
            label=record.get("nuvioName") or manifest.get("name") or manifest.get("id"),
            label2=manifest.get("description", ""),
        )
        item.setArt({"icon": manifest.get("logo") or "DefaultAddon.png"})
        options.append(item)
    return options


def _show_addon_multiselect(records, selected_ids):
    selected = set(decode_selected_ids(selected_ids))
    preselect = [index for index, record in enumerate(records) if _addon_key(record) in selected]
    indexes = xbmcgui.Dialog().multiselect(
        translation(91019), _build_options(records), preselect=preselect, useDetails=True
    )
    if indexes is None:
        return None
    return [_addon_key(records[index]) for index in indexes]


def _merge_records(existing, imported):
    merged = []
    seen = set()
    for record in list(existing or []) + imported:
        if not isinstance(record, dict) or not isinstance(record.get("manifest"), dict):
            continue
        key = _addon_key(record)
        if key and key not in seen:
            merged.append(record)
            seen.add(key)
    return merged


def nuvio_toggle_addons(params=None, *, cancelled=None):
    """Select enabled Nuvio addon manifests without changing Stremio state."""
    rows = NuvioClient().get_addons()
    if rows is None:
        xbmcgui.Dialog().ok(translation(91018), translation(91022))
        return
    imported = []
    for row in rows:
        if cancelled is not None and cancelled():
            return
        try:
            manifest, manifest_url = _fetch_manifest(row["url"], cancelled=cancelled)
            imported.append(
                {
                    "manifest": manifest,
                    "transportUrl": manifest_url,
                    "transportName": "nuvio",
                    "nuvioName": row.get("name") or "",
                }
            )
        except (requests.RequestException, TimeoutError, ValueError, UnicodeDecodeError):
            kodilog("[NUVIO] skipped unavailable or invalid addon manifest")
    if not imported:
        xbmcgui.Dialog().ok(translation(91018), translation(91021))
        return
    selected = _show_addon_multiselect(imported, cache.get(NUVIO_ADDONS_KEY))
    if selected is None:
        return
    existing = cache.get(NUVIO_USER_ADDONS) or []
    cache.set(NUVIO_USER_ADDONS, _merge_records(existing, imported), timedelta(days=365 * 20))
    cache.set(NUVIO_ADDONS_KEY, encode_selected_ids(selected), timedelta(days=365 * 20))

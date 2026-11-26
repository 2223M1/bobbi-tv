"""User-manageable default & custom search source persistence (schema 1).

Persists user customizations atomically to ``<profile_root>/user_sources.json``.
When ``user_sources.json`` is absent, all helpers return clean empty defaults without
touching disk so existing search/provider behavior remains 100% unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
USER_SOURCES_FILENAME = "user_sources.json"
MAX_USER_SOURCES_BYTES = 65536
MAX_CUSTOM_TORZNAB_SOURCES = 16
MAX_DISABLED_INDEXERS = 64

# (source_id, zh_label, en_label, linked_setting_key_or_None)
DEFAULT_SOURCE_SPECS: Tuple[Tuple[str, str, str, Optional[str]], ...] = (
    ("qqdocs", "115 资源目录", "115 Share Catalog", None),
    ("mdsub", "漫迪字幕组目录", "MDsub Catalog", None),
    ("115-local-index", "115 本地索引", "115 Local Index", None),
    ("animegarden", "AnimeGarden 动漫源", "AnimeGarden Anime RSS", None),
    ("jackett", "Jackett BT 检索", "Jackett Torznab", "jackett_enabled"),
    ("prowlarr", "Prowlarr", "Prowlarr", "prowlarr_enabled"),
    ("stremio", "Stremio", "Stremio", "stremio_enabled"),
    ("nuvio", "Nuvio", "Nuvio", "nuvio_enabled"),
)

VALID_DEFAULT_IDS = frozenset(row[0] for row in DEFAULT_SOURCE_SPECS)
INDEXER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")


def empty_user_sources() -> Dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "removed_defaults": [],
        "disabled_jackett_indexers": [],
        "custom_torznab_sources": [],
    }


def resolve_profile_root(profile_root=None) -> Optional[Path]:
    if profile_root is not None:
        return Path(os.fspath(profile_root))
    try:
        import xbmcaddon
        import xbmcvfs

        raw = xbmcaddon.Addon("plugin.video.bobbi").getAddonInfo("profile")
        if raw:
            translated = xbmcvfs.translatePath(raw)
            if translated and not str(translated).startswith("special://"):
                return Path(translated)
    except Exception:
        pass
    try:
        from lib.utils.kodi.utils import ADDON_PROFILE_PATH

        if ADDON_PROFILE_PATH and not str(ADDON_PROFILE_PATH).startswith("special://"):
            return Path(ADDON_PROFILE_PATH)
    except Exception:
        pass
    return None


def _has_control_chars(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def validate_torznab_url(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("INVALID_TORZNAB_URL")
    cleaned = url.strip()
    if not cleaned or len(cleaned) > 512 or _has_control_chars(cleaned) or any(ch.isspace() for ch in cleaned):
        raise ValueError("INVALID_TORZNAB_URL")
    parts = urlsplit(cleaned)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError("INVALID_TORZNAB_URL")
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise ValueError("INVALID_TORZNAB_URL")
    return cleaned


def _slugify_source_id(name: str, url: str, existing_ids: set) -> str:
    raw = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-_")
    if not raw or not raw[0].isalnum():
        digest = hashlib.sha256(f"{name}\0{url}".encode("utf-8")).hexdigest()[:10]
        raw = f"torznab-{digest}"
    base = raw[:40]
    candidate = base
    suffix = 2
    while candidate in existing_ids or not SOURCE_ID_RE.fullmatch(candidate):
        candidate = f"{base[:40]}-{suffix}"
        suffix += 1
    return candidate


def validate_user_sources_doc(doc: Any) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        raise ValueError("INVALID_USER_SOURCES_DOC")
    schema = doc.get("schema", SCHEMA_VERSION)
    if type(schema) is not int or schema != SCHEMA_VERSION:
        raise ValueError("UNSUPPORTED_USER_SOURCES_SCHEMA")

    raw_removed = doc.get("removed_defaults", [])
    if not isinstance(raw_removed, (list, tuple)):
        raise ValueError("INVALID_REMOVED_DEFAULTS")
    removed_defaults: List[str] = []
    for item in raw_removed:
        if not isinstance(item, str) or item not in VALID_DEFAULT_IDS:
            raise ValueError(f"INVALID_DEFAULT_SOURCE_ID:{item!r}")
        if item not in removed_defaults:
            removed_defaults.append(item)

    raw_disabled = doc.get("disabled_jackett_indexers", [])
    if not isinstance(raw_disabled, (list, tuple)) or len(raw_disabled) > MAX_DISABLED_INDEXERS:
        raise ValueError("INVALID_DISABLED_INDEXERS")
    disabled_indexers: List[str] = []
    for item in raw_disabled:
        if not isinstance(item, str) or not INDEXER_ID_RE.fullmatch(item.strip()):
            raise ValueError(f"INVALID_JACKETT_INDEXER_ID:{item!r}")
        cleaned_id = item.strip()
        if cleaned_id not in disabled_indexers:
            disabled_indexers.append(cleaned_id)

    raw_custom = doc.get("custom_torznab_sources", [])
    if not isinstance(raw_custom, (list, tuple)) or len(raw_custom) > MAX_CUSTOM_TORZNAB_SOURCES:
        raise ValueError("INVALID_CUSTOM_TORZNAB_LIST")
    custom_sources: List[Dict[str, Any]] = []
    seen_ids = set()
    for entry in raw_custom:
        if not isinstance(entry, dict):
            raise ValueError("INVALID_CUSTOM_TORZNAB_ENTRY")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80 or _has_control_chars(name):
            raise ValueError("INVALID_CUSTOM_TORZNAB_NAME")
        clean_name = name.strip()
        clean_url = validate_torznab_url(entry.get("url", ""))
        apikey = entry.get("apikey", "")
        if apikey is None:
            apikey = ""
        if not isinstance(apikey, str) or len(apikey.strip()) > 256 or _has_control_chars(apikey):
            raise ValueError("INVALID_CUSTOM_TORZNAB_APIKEY")
        clean_apikey = apikey.strip()
        enabled = entry.get("enabled", True)
        if type(enabled) is not bool:
            raise ValueError("INVALID_CUSTOM_TORZNAB_ENABLED")
        raw_id = entry.get("id")
        if isinstance(raw_id, str) and SOURCE_ID_RE.fullmatch(raw_id.strip()) and raw_id.strip() not in seen_ids:
            src_id = raw_id.strip()
        elif raw_id is None or raw_id == "":
            src_id = _slugify_source_id(clean_name, clean_url, seen_ids)
        else:
            raise ValueError(f"INVALID_CUSTOM_TORZNAB_ID:{raw_id!r}")
        seen_ids.add(src_id)
        custom_sources.append(
            {
                "id": src_id,
                "name": clean_name,
                "url": clean_url,
                "apikey": clean_apikey,
                "enabled": enabled,
            }
        )

    return {
        "schema": SCHEMA_VERSION,
        "removed_defaults": removed_defaults,
        "disabled_jackett_indexers": disabled_indexers,
        "custom_torznab_sources": custom_sources,
    }


def user_sources_path(profile_root=None) -> Optional[Path]:
    root = resolve_profile_root(profile_root)
    if root is None:
        return None
    return root / USER_SOURCES_FILENAME


def load_user_sources(profile_root=None, *, strict: bool = False) -> Dict[str, Any]:
    target = user_sources_path(profile_root)
    if target is None or not target.exists():
        return empty_user_sources()
    try:
        if target.is_symlink():
            raise ValueError("USER_SOURCES_SYMLINK_REJECTED")
        stat = target.stat()
        if stat.st_size > MAX_USER_SOURCES_BYTES:
            raise ValueError("USER_SOURCES_TOO_LARGE")
        raw = target.read_bytes()
        if len(raw) > MAX_USER_SOURCES_BYTES:
            raise ValueError("USER_SOURCES_TOO_LARGE")
        parsed = json.loads(raw.decode("utf-8"))
        return validate_user_sources_doc(parsed)
    except Exception:
        if strict:
            raise
        return empty_user_sources()


def save_user_sources(doc: Dict[str, Any], profile_root=None) -> Dict[str, Any]:
    validated = validate_user_sources_doc(doc)
    root = resolve_profile_root(profile_root)
    if root is None:
        raise ValueError("USER_SOURCES_PROFILE_UNAVAILABLE")
    if root.exists() and root.is_symlink():
        raise ValueError("USER_SOURCES_SYMLINK_REJECTED")
    root.mkdir(parents=True, exist_ok=True)
    target = root / USER_SOURCES_FILENAME
    if target.exists() and target.is_symlink():
        raise ValueError("USER_SOURCES_SYMLINK_REJECTED")

    payload = (json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(payload) > MAX_USER_SOURCES_BYTES:
        raise ValueError("USER_SOURCES_TOO_LARGE")

    fd, tmp_name = tempfile.mkstemp(prefix=".user_sources.", suffix=".tmp", dir=str(root))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, str(target))
    except Exception:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return validated


def user_sources_digest(profile_root=None) -> str:
    target = user_sources_path(profile_root)
    if target is None or not target.exists() or target.is_symlink():
        return ""
    try:
        raw = target.read_bytes()
        if not raw or len(raw) > MAX_USER_SOURCES_BYTES:
            return ""
        return hashlib.sha256(raw).hexdigest()
    except OSError:
        return ""


def cache_scope_suffix(profile_root=None, *, cache_backend=None) -> str:
    root = profile_root
    if root is None and cache_backend is not None:
        for attr in ("_db_path", "db_path", "_database_path"):
            db_path = getattr(cache_backend, attr, None)
            if isinstance(db_path, (str, os.PathLike)):
                text = os.fspath(db_path)
                if text and text != ":memory:":
                    root = Path(text).parent
                    break
    digest = user_sources_digest(root)
    return f"|user-sources:{digest}" if digest else ""


def is_default_removed(source_id: str, profile_root=None) -> bool:
    doc = load_user_sources(profile_root)
    return source_id in doc["removed_defaults"]


def set_default_removed(source_id: str, removed: bool, profile_root=None) -> Dict[str, Any]:
    if source_id not in VALID_DEFAULT_IDS:
        raise ValueError(f"INVALID_DEFAULT_SOURCE_ID:{source_id!r}")
    doc = load_user_sources(profile_root)
    items = list(doc["removed_defaults"])
    if removed and source_id not in items:
        items.append(source_id)
    elif not removed and source_id in items:
        items.remove(source_id)
    doc["removed_defaults"] = items
    return save_user_sources(doc, profile_root=profile_root)


def toggle_default_source(source_id: str, profile_root=None) -> Tuple[bool, Dict[str, Any]]:
    doc = load_user_sources(profile_root)
    now_removed = source_id not in doc["removed_defaults"]
    saved = set_default_removed(source_id, now_removed, profile_root=profile_root)
    return now_removed, saved


def restore_all_defaults(profile_root=None, *, clear_disabled_indexers: bool = False) -> Dict[str, Any]:
    doc = load_user_sources(profile_root)
    doc["removed_defaults"] = []
    if clear_disabled_indexers:
        doc["disabled_jackett_indexers"] = []
    return save_user_sources(doc, profile_root=profile_root)


def set_jackett_indexer_disabled(indexer_id: str, disabled: bool, profile_root=None) -> Dict[str, Any]:
    cleaned = str(indexer_id or "").strip()
    if not INDEXER_ID_RE.fullmatch(cleaned):
        raise ValueError(f"INVALID_JACKETT_INDEXER_ID:{indexer_id!r}")
    doc = load_user_sources(profile_root)
    items = list(doc["disabled_jackett_indexers"])
    if disabled and cleaned not in items:
        items.append(cleaned)
    elif not disabled and cleaned in items:
        items.remove(cleaned)
    doc["disabled_jackett_indexers"] = items
    return save_user_sources(doc, profile_root=profile_root)


def toggle_jackett_indexer(indexer_id: str, profile_root=None) -> Tuple[bool, Dict[str, Any]]:
    cleaned = str(indexer_id or "").strip()
    doc = load_user_sources(profile_root)
    now_disabled = cleaned not in doc["disabled_jackett_indexers"]
    saved = set_jackett_indexer_disabled(cleaned, now_disabled, profile_root=profile_root)
    return now_disabled, saved


def enable_all_jackett_indexers(profile_root=None) -> Dict[str, Any]:
    doc = load_user_sources(profile_root)
    doc["disabled_jackett_indexers"] = []
    return save_user_sources(doc, profile_root=profile_root)


def add_custom_torznab_source(
    name: str,
    url: str,
    apikey: str = "",
    *,
    enabled: bool = True,
    source_id: Optional[str] = None,
    profile_root=None,
) -> Dict[str, Any]:
    doc = load_user_sources(profile_root)
    existing = list(doc["custom_torznab_sources"])
    if len(existing) >= MAX_CUSTOM_TORZNAB_SOURCES:
        raise ValueError("MAX_CUSTOM_TORZNAB_REACHED")
    seen_ids = {row["id"] for row in existing}
    clean_name = str(name or "").strip()
    clean_url = validate_torznab_url(url)
    clean_id = (
        source_id.strip()
        if isinstance(source_id, str) and source_id.strip()
        else _slugify_source_id(clean_name, clean_url, seen_ids)
    )
    entry = {
        "id": clean_id,
        "name": clean_name,
        "url": clean_url,
        "apikey": str(apikey or "").strip(),
        "enabled": bool(enabled),
    }
    existing.append(entry)
    doc["custom_torznab_sources"] = existing
    saved = save_user_sources(doc, profile_root=profile_root)
    return next(row for row in saved["custom_torznab_sources"] if row["id"] == clean_id)


def update_custom_torznab_source(
    source_id: str,
    *,
    name: Optional[str] = None,
    url: Optional[str] = None,
    apikey: Optional[str] = None,
    enabled: Optional[bool] = None,
    profile_root=None,
) -> Dict[str, Any]:
    doc = load_user_sources(profile_root)
    updated_entry = None
    rows = []
    for row in doc["custom_torznab_sources"]:
        if row["id"] == source_id:
            patched = dict(row)
            if name is not None:
                patched["name"] = str(name).strip()
            if url is not None:
                patched["url"] = validate_torznab_url(url)
            if apikey is not None:
                patched["apikey"] = str(apikey).strip()
            if enabled is not None:
                patched["enabled"] = bool(enabled)
            rows.append(patched)
            updated_entry = patched
        else:
            rows.append(row)
    if updated_entry is None:
        raise KeyError(source_id)
    doc["custom_torznab_sources"] = rows
    saved = save_user_sources(doc, profile_root=profile_root)
    return next(row for row in saved["custom_torznab_sources"] if row["id"] == source_id)


def remove_custom_torznab_source(source_id: str, profile_root=None) -> bool:
    doc = load_user_sources(profile_root)
    before = len(doc["custom_torznab_sources"])
    doc["custom_torznab_sources"] = [row for row in doc["custom_torznab_sources"] if row["id"] != source_id]
    if len(doc["custom_torznab_sources"]) == before:
        return False
    save_user_sources(doc, profile_root=profile_root)
    return True

from datetime import timedelta

from lib.api.tmdbv3api.tmdb import TMDb
from lib.db.cached import cache
from lib.utils.kodi.logging import kodilog


# AM6B_ANIME_TITLE_PROPERTIES_V1
def _am6b_value(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _am6b_translation_title(entry, mode):
    data = _am6b_value(entry, "data", {}) or {}
    key = "title" if mode == "movies" else "name"
    value = _am6b_value(data, key, "")
    return value.strip() if isinstance(value, str) else ""


def _am6b_verified_titles(tmdb_id, mode):
    """Return exact zh-CN and en-US titles; never use original/native/romaji."""
    media = "movie" if mode == "movies" else "tv"
    cache_key = f"am6b_anime_titles_v1|{media}|{tmdb_id}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    result = {"zh": "", "en": ""}
    try:
        payload = TMDb()._request_obj(f"/{media}/{tmdb_id}/translations", add_lang=False)
    except Exception:
        # Provider exceptions can contain authenticated URLs; do not log details.
        kodilog(f"AM6B bilingual title lookup failed for {media} {tmdb_id}")
        return result

    for entry in _am6b_value(payload, "translations", []) or []:
        language = str(_am6b_value(entry, "iso_639_1", "") or "").lower()
        region = str(_am6b_value(entry, "iso_3166_1", "") or "").upper()
        if language == "zh" and region == "CN" and not result["zh"]:
            result["zh"] = _am6b_translation_title(entry, mode)
        elif language == "en" and region == "US" and not result["en"]:
            result["en"] = _am6b_translation_title(entry, mode)

    cache.set(cache_key, result, timedelta(days=30))
    return result


def _am6b_catalog_title(res, mode):
    key = "title" if mode == "movies" else "name"
    value = _am6b_value(res, key, "")
    return value.strip() if isinstance(value, str) else ""


def _am6b_catalog_localized_title(res, mode, requested_language):
    """Accept an explicit locale field while rejecting provider native fallback."""
    title = _am6b_catalog_title(res, mode)
    original_key = "original_title" if mode == "movies" else "original_name"
    original = _am6b_value(res, original_key, "")
    original = original.strip() if isinstance(original, str) else ""
    original_language = str(_am6b_value(res, "original_language", "") or "").lower()
    requested_base = requested_language.split("-", 1)[0].lower()
    if title and original and title == original and original_language != requested_base:
        return ""
    return title


def _am6b_build_catalog_title_map(zh_data, en_data, mode, zh_fallback_data=None):
    zh_results = _am6b_value(zh_data, "results", []) or []
    zh_fallback_results = _am6b_value(zh_fallback_data, "results", []) or []
    en_results = _am6b_value(en_data, "results", []) or []
    zh_by_id = {_am6b_value(item, "id", ""): item for item in zh_results}
    zh_fallback_by_id = {_am6b_value(item, "id", ""): item for item in zh_fallback_results}
    en_by_id = {_am6b_value(item, "id", ""): item for item in en_results}
    title_map = {}
    for tmdb_id in set(zh_by_id) | set(zh_fallback_by_id) | set(en_by_id):
        if not tmdb_id:
            continue
        primary_zh = _am6b_catalog_localized_title(zh_by_id.get(tmdb_id, {}), mode, "zh-CN")
        fallback_zh = _am6b_catalog_localized_title(
            zh_fallback_by_id.get(tmdb_id, {}), mode, "zh-TW"
        )
        title_map[tmdb_id] = {
            "zh": primary_zh or fallback_zh,
            "en": _am6b_catalog_localized_title(en_by_id.get(tmdb_id, {}), mode, "en-US"),
        }
    return title_map


def _am6b_resolve_anime_titles(tmdb_id, mode, catalog_titles=None):
    """Prefer the newest explicit locale values while retaining verified cached gaps."""
    if not tmdb_id or mode not in ("tv", "movies"):
        return {"zh": "", "en": ""}

    media = "movie" if mode == "movies" else "tv"
    cache_key = f"am6b_anime_titles_v1|{media}|{tmdb_id}"
    cached_titles = cache.get(cache_key)
    cached_titles = cached_titles if isinstance(cached_titles, dict) else {}
    cached_pair = {key: cached_titles.get(key) or "" for key in ("zh", "en")}
    catalog_titles = catalog_titles if isinstance(catalog_titles, dict) else {}
    titles = {key: catalog_titles.get(key) or cached_pair.get(key) or "" for key in ("zh", "en")}

    # Catalog locale fields are the newest provider values. Persist only a
    # genuine change so repeated widget renders remain read-only and fast.
    if (titles["zh"] or titles["en"]) and titles != cached_pair:
        cache.set(cache_key, titles, timedelta(days=30))
    return titles


def _am6b_apply_anime_title_properties(list_item, res, mode, catalog_titles=None):
    tmdb_id = _am6b_value(res, "id", "")
    if not tmdb_id or mode not in ("tv", "movies"):
        return

    titles = _am6b_resolve_anime_titles(tmdb_id, mode, catalog_titles)
    original_key = "original_title" if mode == "movies" else "original_name"
    original = _am6b_value(res, original_key, "")
    if titles.get("zh"):
        list_item.setProperty("AM6B.Title.zh", titles["zh"])
    if titles.get("en"):
        list_item.setProperty("AM6B.Title.en", titles["en"])
    if isinstance(original, str) and original.strip():
        list_item.setProperty("AM6B.Title.original", original.strip())
    list_item.setProperty("AM6B.Media.kind", "anime_movie" if mode == "movies" else "anime_series")

import contextlib
import os
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4
from threading import Event

from bobbi_core.http_policy import read_bounded_http_body

import requests
import xbmc
import xbmcgui

from lib.clients.stremio.protocol import (
    build_resource_url,
    is_safe_http_url,
    request_with_safe_redirects,
    response_json,
)
from lib.clients.subtitle.utils import (
    get_language_code,
    language_code_to_name,
    slugify_title,
    subtitle_language_matches,
)
from lib.utils.general.utils import USER_AGENT_HEADER
from lib.utils.kodi.settings import get_int_setting, subtitle_automation_enabled
from lib.utils.kodi.utils import (
    ADDON_PROFILE_PATH,
    get_setting,
    kodilog,
    translation,
)

SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".sub", ".txt"}
DEFAULT_ENDPOINT_TIMEOUT = 10
AUTO_SELECT_ENDPOINT_TIMEOUT = 5
DEFAULT_DOWNLOAD_TIMEOUT = 15
AUTO_SELECT_DOWNLOAD_TIMEOUT = 5
MAX_AUTO_DOWNLOAD_CANDIDATES = 3
MAX_RETRY_DELAY = 5.0
MAX_SUBTITLE_WORKERS = 4
MAX_SUBTITLE_BYTES = 10 * 1024 * 1024
DEFAULT_STREMIO_SUBTITLE_ADDON_URL = "https://opensubtitles-v3.strem.io/"


class SubtitleDownloadStopped(Exception):
    """Cooperative cancellation/deadline, not a provider error notification."""


def _check_download(deadline, cancelled):
    if cancelled is not None and cancelled():
        raise SubtitleDownloadStopped('cancelled')
    if deadline is not None and time.monotonic() >= deadline:
        raise SubtitleDownloadStopped('deadline')


def _wait_for_retry(delay, deadline, cancelled):
    until = min(deadline, time.monotonic() + max(0.0, delay))
    while True:
        _check_download(deadline, cancelled)
        remaining = until - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(.1, remaining))


def safe_subtitle_path_component(value: Any) -> str:
    """Return a filesystem-safe, single component for addon-provided identifiers."""
    component = re.sub(r"[^A-Za-z0-9._-]", "_", str(value or ""))
    return component if component not in ("", ".", "..") else "unknown"


def _redact_subtitle_url(url: Any) -> str:
    """Keep hosts useful for diagnostics without exposing signed URL details."""
    parsed = urlparse(str(url or ""))
    if parsed.scheme and parsed.hostname:
        return f"{parsed.scheme}://{parsed.hostname}/<redacted>"
    return "<redacted URL>"


def _retry_delay(response: Any, attempt: int, retry_delay: float = 1.0) -> float:
    """Return a bounded Retry-After delay, falling back to exponential backoff."""
    retry_after = str((getattr(response, "headers", {}) or {}).get("Retry-After", ""))
    try:
        return min(MAX_RETRY_DELAY, max(0.0, float(retry_after)))
    except (TypeError, ValueError):
        fallback = retry_delay * float(2**attempt)
        return float(min(MAX_RETRY_DELAY, fallback))


def _is_obvious_html_response(content: bytes) -> bool:
    return content.lstrip().lower().startswith((b"<!doctype html", b"<html", b"<head", b"<body"))


class OpenSubtitleStremioClient:
    def __init__(self, notification: Callable[[str], None]):
        self.notification = notification
        self.selection_cancelled = False

    @staticmethod
    def _build_url(
        base_url: str,
        mode: str,
        imdb_id: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build a subtitles endpoint URL from a (possibly trailing-slashed) base.

        Ensures exactly one ``/`` separates the base from ``subtitles/...``,
        regardless of whether the caller passed a trailing slash. ``base_url``
        is expected to come from :func:`build_addon_base_url` (which strips
        the trailing slash) or :func:`normalize_transport_url`.
        """
        resource_id = f"{imdb_id}:{season}:{episode}" if mode == "tv" else imdb_id
        resource_type = "series" if mode == "tv" else "movie"
        return build_resource_url(base_url, "subtitles", resource_type, resource_id, extra_args)

    def _fetch_subtitles_data_for_source(
        self,
        base_url: str,
        mode: str,
        imdb_id: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        timeout: int = DEFAULT_ENDPOINT_TIMEOUT,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        extra_args: Optional[Dict[str, Any]] = None,
        *,
        deadline: Optional[float] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Read one source under one budget across DNS, redirects, body and retries.

        A confirmed empty result is [], while unavailable/invalid responses are
        None. Destination DNS is checked once per actual connection by the
        shared transport, not again for every subtitle record in the response.
        """
        end = time.monotonic() + timeout
        deadline = end if deadline is None else min(deadline, end)
        url = self._build_url(base_url, mode, imdb_id, season, episode, extra_args)
        safe_base_url = _redact_subtitle_url(base_url)
        with requests.Session() as session:
            session.trust_env = False
            session.headers["Accept-Encoding"] = "gzip, deflate"
            for attempt in range(max_retries + 1):
                response = None
                delay = retry_delay
                try:
                    _check_download(deadline, cancelled)
                    response = request_with_safe_redirects(
                        session.get, url, validator=is_safe_http_url,
                        headers=USER_AGENT_HEADER, timeout=timeout, stream=True,
                        deadline=deadline, cancelled=cancelled,
                    )
                    if response.status_code == 200:
                        data = response_json(response, deadline=deadline, cancelled=cancelled)
                        if not isinstance(data, dict) or not isinstance(data.get('subtitles', []), list):
                            return []
                        return [row for row in data.get('subtitles', []) if self._valid_subtitle_record(row)]
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        return None
                    delay = _retry_delay(response, attempt, retry_delay)
                except (SubtitleDownloadStopped, ValueError):
                    return None
                except Exception as error:
                    kodilog(f"[StremioSubs] addon {safe_base_url} failed: {type(error).__name__}",
                            level=xbmc.LOGWARNING)
                finally:
                    if response is not None:
                        with contextlib.suppress(Exception):
                            response.close()
                if attempt < max_retries:
                    try:
                        _wait_for_retry(delay, deadline, cancelled)
                    except SubtitleDownloadStopped:
                        return None
        return None

    @staticmethod
    def _id_prefix(imdb_id: str) -> str:
        """Extract the id prefix used by ``Addon.isSupported``.

        ``tt0111161`` -> ``"tt"`` ; ``kitsu:1`` -> ``"kitsu"``.
        Strips the ``:<suffix>`` if present, then strips trailing digits so
        numeric imdb ids map to their alphabetic prefix.
        """
        if not imdb_id:
            return ""
        head = str(imdb_id).split(":", 1)[0]
        # Strip trailing digits: "tt0111161" -> "tt", "kitsu" -> "kitsu".
        stripped = head.rstrip("0123456789")
        return stripped or head

    @staticmethod
    def _canonical_subtitle_addon_keys(addon_manager: Any) -> set:
        """Return keys for manager entries that point to the integrated source."""
        try:
            from lib.api.stremio.addon_manager import normalize_transport_url

            canonical_url = normalize_transport_url(DEFAULT_STREMIO_SUBTITLE_ADDON_URL)
        except Exception:
            return set()

        keys = set()
        for addon in getattr(addon_manager, "addons", []) or []:
            try:
                if normalize_transport_url(addon.url()) == canonical_url:
                    keys.add(addon.key())
            except Exception:
                continue
        return keys

    @staticmethod
    def _read_selected_subtitle_addon_keys() -> List[str]:
        """Read the persisted subtitle-addon selection without changing it."""
        try:
            raw_selection = str(get_setting("stremio_subtitle_addons", "") or "").strip()
        except Exception:
            raw_selection = ""
        return [key.strip() for key in raw_selection.split(",") if key.strip()]

    def _resolve_runtime_subtitle_sources(
        self,
        selected_keys: List[str],
        addon_manager: Optional[Any],
    ) -> Tuple[Optional[Any], List[Tuple[str, str]]]:
        """Resolve the integrated default and selected custom subtitle sources."""
        live_manager = addon_manager
        if live_manager is None:
            try:
                from lib.clients.stremio.helpers import get_addons

                live_manager = get_addons()
            except Exception:
                live_manager = None

        canonical_keys = self._canonical_subtitle_addon_keys(live_manager)
        integrated_enabled = bool(get_setting("stremio_opensubtitles_enabled", True))
        ordered_sources = []
        if integrated_enabled:
            ordered_sources.append(
                ("integrated-default", DEFAULT_STREMIO_SUBTITLE_ADDON_URL.rstrip("/"))
            )
        seen_keys = set()
        for key in selected_keys:
            if key in canonical_keys or key in seen_keys:
                continue
            seen_keys.add(key)
            ordered_sources.append((key, ""))
        return live_manager, ordered_sources

    def _resolve_compatible_subtitle_sources(
        self,
        ordered_sources: List[Tuple[str, str]],
        addon_manager: Optional[Any],
        mode: str,
        imdb_id: str,
    ) -> List[Tuple[str, str, str]]:
        """Resolve selected sources and discard unavailable or incompatible addons."""
        resolved: List[Tuple[str, str, str]] = []
        id_prefix = self._id_prefix(imdb_id)
        video_type = "series" if mode == "tv" else "movie"
        for source_key, base_url_hint in ordered_sources:
            if base_url_hint:
                resolved.append((source_key, base_url_hint, "OpenSubtitles"))
                continue
            if addon_manager is None:
                kodilog(
                    "[StremioSubs] external lookup skipped: no addons resolved and none selected",
                    level=xbmc.LOGDEBUG,
                )
                break
            try:
                addon = addon_manager.get_addon_by_key(source_key)
            except Exception:
                addon = None
            if addon is None:
                kodilog(
                    "[StremioSubs] selected addon skipped: not installed",
                    level=xbmc.LOGDEBUG,
                )
                continue
            if id_prefix and not addon.isSupported("subtitles", video_type, id_prefix):
                kodilog(
                    f"[StremioSubs] selected addon skipped: idPrefix {id_prefix} not supported",
                    level=xbmc.LOGDEBUG,
                )
                continue
            try:
                base_url = addon.url()
            except Exception:
                base_url = ""
            if not base_url:
                kodilog(
                    "[StremioSubs] selected addon skipped: empty base url",
                    level=xbmc.LOGDEBUG,
                )
                continue
            try:
                source_label = addon.label()
            except Exception:
                source_label = getattr(getattr(addon, "manifest", None), "name", "") or source_key
            resolved.append((source_key, base_url, source_label))
        return resolved

    def _query_and_merge_subtitle_sources(
        self,
        sources: List[Tuple[str, str, str]],
        mode: str,
        imdb_id: str,
        season: Optional[int],
        episode: Optional[int],
        auto_select: bool,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[List[Dict[str, Any]], List[str]]]:
        """Query sources concurrently, then merge their responses in source order."""
        per_call_timeout = get_int_setting("stremio_timeout") or DEFAULT_ENDPOINT_TIMEOUT
        if auto_select:
            per_call_timeout = min(per_call_timeout, AUTO_SELECT_ENDPOINT_TIMEOUT)
        cap_seconds = AUTO_SELECT_ENDPOINT_TIMEOUT if auto_select else None
        start = time.monotonic()
        merged: List[Dict[str, Any]] = []
        merged_source_labels: List[str] = []
        seen_keys: set = set()
        queried = 0
        failed = 0
        sources_with_subs = 0
        dup_count = 0
        dup_key_kind = "url"
        results: Dict[Future, Optional[List[Dict[str, Any]]]] = {}
        futures: List[Tuple[str, str, str, Future]] = []
        executor: Optional[ThreadPoolExecutor] = None
        timed_out = False
        stop_fetch = Event()

        try:
            executor = ThreadPoolExecutor(max_workers=min(MAX_SUBTITLE_WORKERS, len(sources)))
            for source_key, base_url, source_label in sources:
                try:
                    retry_options = {"cancelled": stop_fetch.is_set}
                    if auto_select:
                        retry_options.update(max_retries=0, deadline=start + cap_seconds)
                    if extra_args:
                        retry_options["extra_args"] = extra_args
                    future = executor.submit(
                        self._fetch_subtitles_data_for_source,
                        base_url,
                        mode,
                        imdb_id,
                        season,
                        episode,
                        per_call_timeout,
                        **retry_options,
                    )
                except Exception as error:
                    failed += 1
                    kodilog(
                        f"[StremioSubs] addon dispatch failed: {type(error).__name__}",
                        level=xbmc.LOGWARNING,
                    )
                    continue
                futures.append((source_key, base_url, source_label, future))

            queried = len(futures)
            pending = [future for _, _, _, future in futures]
            if cap_seconds is None:
                done, _ = wait(pending)
            else:
                remaining = max(0.0, cap_seconds - (time.monotonic() - start))
                done, not_done = wait(pending, timeout=remaining)
                timed_out = bool(not_done)
                for future in not_done:
                    future.cancel()

            for future in done:
                try:
                    results[future] = future.result()
                except Exception as error:
                    results[future] = None
                    kodilog(
                        f"[StremioSubs] addon worker failed: {type(error).__name__}",
                        level=xbmc.LOGWARNING,
                    )
        except Exception as error:
            kodilog(
                f"[StremioSubs] external lookup dispatch failed: {type(error).__name__}",
                level=xbmc.LOGWARNING,
            )
        finally:
            stop_fetch.set()
            if executor is not None:
                # Auto-select must return at its shared deadline rather than wait for retries.
                executor.shutdown(wait=not auto_select)

        if timed_out:
            kodilog(
                f"[StremioSubs] autoplay timeout cap reached after "
                f"{round(time.monotonic() - start, 2)}s; using completed responses",
                level=xbmc.LOGINFO,
            )

        for _source_key, _base_url, source_label, future in futures:
            if future not in results:
                continue
            result = results[future]
            if result is None:
                failed += 1
                continue
            if not result:
                kodilog(
                    "[StremioSubs] addon returned 0 subs (200 empty)",
                    level=xbmc.LOGDEBUG,
                )
                continue
            sources_with_subs += 1
            for sub in result:
                if not isinstance(sub, dict):
                    continue
                sub_id = sub.get("id") or sub.get("subId") or ""
                sub_lang = sub.get("lang") or ""
                sub_url = sub.get("url") or ""
                if sub_url:
                    key = sub_url
                    kind = "url"
                elif sub_id:
                    key = f"{sub_id}|{sub_lang}"
                    kind = "sub_id|lang"
                else:
                    key = f"_anon|{id(sub)}"
                    kind = "anon"
                if key in seen_keys:
                    dup_count += 1
                    dup_key_kind = kind
                    continue
                seen_keys.add(key)
                merged.append(sub)
                merged_source_labels.append(source_label)

        if dup_count:
            kodilog(
                f"[StremioSubs] dedup: {dup_count} duplicate(s) removed (key={dup_key_kind})",
                level=xbmc.LOGDEBUG,
            )
        kodilog(
            f"[StremioSubs] external lookup: queried {queried} addon(s), "
            f"{sources_with_subs} returned {len(merged)} subs total, "
            f"{failed} failed",
            level=xbmc.LOGINFO,
        )
        if not merged:
            return None
        return merged, merged_source_labels

    @staticmethod
    def _apply_subtitle_language_or_manual_selection(
        subtitles: List[Dict[str, Any]],
        source_labels: List[str],
        auto_select: bool,
    ) -> List[Dict[str, Any]]:
        """Apply the existing automatic language filter or manual multiselect."""
        try:
            sub_language = get_setting("subtitle_language")
            subtitle_automation = subtitle_automation_enabled()
        except Exception:
            sub_language = None
            subtitle_automation = False
        if auto_select or subtitle_automation:
            target_lang = get_language_code(sub_language) if sub_language else ""
            filtered = [subtitle for subtitle in subtitles if subtitle_language_matches(subtitle.get("lang"), target_lang)]
            if filtered:
                return filtered
            return []

        items = [
            xbmcgui.ListItem(
                label=(
                    f"{translation(90665) % index} — {source_label or 'Stremio subtitle addon'}"
                ),
                label2=language_code_to_name(subtitle.get("lang") or ""),
            )
            for index, (subtitle, source_label) in enumerate(zip(subtitles, source_labels))
        ]
        selected_indices = xbmcgui.Dialog().multiselect(
            translation(90256),
            items,
            useDetails=True,
        )
        if selected_indices is None:
            return []
        return [subtitles[index] for index in selected_indices]

    def get_subtitles(
        self,
        mode: str,
        imdb_id: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        auto_select: bool = False,
        addon_manager: Optional[Any] = None,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Resolve subtitles from all selected Stremio addons (multi-source).

        Flow:
            1. Read ``stremio_subtitle_addons`` (CSV of addon instance keys).
            2. Prepend the canonical OpenSubtitles endpoint at runtime.
            3. Resolve each selected custom key -> live ``Addon`` via ``AddonManager``.
            4. Filter custom addons by ``addon.isSupported("subtitles", type, id_prefix)``.
            5. Query each accepted addon's ``addon.url()`` concurrently; merge
               completed responses in selection order and cap auto-select elapsed time.
            6. Merge + dedup by ``url`` else ``"{sub_id}|{lang}"`` (F4/EC5).
            7. Apply language filter (F8).
        """
        selected_keys = self._read_selected_subtitle_addon_keys()
        live_manager, ordered_sources = self._resolve_runtime_subtitle_sources(
            selected_keys, addon_manager
        )
        if not ordered_sources:
            return None

        resolved = self._resolve_compatible_subtitle_sources(
            ordered_sources, live_manager, mode, imdb_id
        )

        if not resolved:
            kodilog(
                "[StremioSubs] external lookup skipped: no addons resolved and none selected",
                level=xbmc.LOGDEBUG,
            )
            return None
        merged = self._query_and_merge_subtitle_sources(
            resolved, mode, imdb_id, season, episode, auto_select, extra_args
        )
        if merged is None:
            return None
        subtitles, source_labels = merged
        return self._apply_subtitle_language_or_manual_selection(
            subtitles, source_labels, auto_select
        )

    def select_subtitles(
        self,
        subtitles: List[Dict[str, Any]],
        auto_select: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        self.selection_cancelled = False
        kodilog(
            f"[StremioSubs] select_subtitles input: {len(subtitles)} candidate(s), "
            f"auto_select={auto_select}",
            level=xbmc.LOGINFO,
        )
        kept = [s for s in subtitles if s.get("url")]
        kodilog(
            f"[StremioSubs] {len(kept)}/{len(subtitles)} candidate(s) kept after url-filter",
            level=xbmc.LOGDEBUG,
        )
        subtitles = kept
        if not subtitles:
            kodilog(
                "[StremioSubs] select_subtitles: no embedded subtitles with a "
                "downloadable url -> returning None (caller will try endpoint)",
                level=xbmc.LOGINFO,
            )
            return

        sub_language = get_setting("subtitle_language")
        if auto_select or subtitle_automation_enabled():
            target_lang = get_language_code(sub_language)
            filtered = [s for s in subtitles if subtitle_language_matches(s.get("lang"), target_lang)]
            kodilog(
                f"[StremioSubs] auto-download: {len(filtered)}/{len(subtitles)} "
                f"embedded subtitle(s) match configured language '{sub_language}' "
                f"(code={target_lang})",
                level=xbmc.LOGINFO,
            )
            if filtered:
                return filtered
            return []

        items = [
            xbmcgui.ListItem(
                label=f"{translation(90665) % i} — Embedded stream subtitle",
                label2=language_code_to_name(s.get("lang") or ""),
            )
            for i, s in enumerate(subtitles)
        ]

        kodilog(
            f"[StremioSubs] opening multiselect dialog with {len(items)} "
            f"embedded subtitle option(s)",
            level=xbmc.LOGINFO,
        )
        selected_indices = xbmcgui.Dialog().multiselect(
            translation(90256),
            items,
            useDetails=True,
        )
        if selected_indices is None:
            self.selection_cancelled = True
            kodilog(
                "[StremioSubs] user cancelled the embedded subtitle multiselect "
                "dialog -> returning [] (endpoint NOT tried)",
                level=xbmc.LOGINFO,
            )
            return []
        kodilog(
            f"[StremioSubs] user selected {len(selected_indices)} embedded subtitle(s)",
            level=xbmc.LOGINFO,
        )
        return [subtitles[i] for i in selected_indices]

    @staticmethod
    def _valid_subtitle_record(subtitle: Any) -> bool:
        if not isinstance(subtitle, dict):
            return False
        url = subtitle.get("url")
        if not is_safe_http_url(url, resolve_dns=False):
            return False
        lang = subtitle.get("lang")
        subtitle_id = subtitle.get("id") or subtitle.get("subId")
        return (lang is None or isinstance(lang, str)) and (
            subtitle_id is None or isinstance(subtitle_id, (str, int))
        )

    def _get_subtitle_extension(self, url: str) -> str:
        extension = os.path.splitext(urlparse(url).path)[1].lower()
        return extension if extension in SUBTITLE_EXTENSIONS else ".srt"

    def download_subtitles_batch(
        self,
        subtitles: List[Dict[str, Any]],
        imdb_id: str,
        title: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        folder_path: Optional[str] = None,
        auto_select: bool = False,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> List[str]:
        kodilog(
            f"[StremioSubs] download_subtitles_batch: {len(subtitles)} subtitle(s), "
            f"auto_select={auto_select}, timeout="
            f"{AUTO_SELECT_DOWNLOAD_TIMEOUT if auto_select else DEFAULT_DOWNLOAD_TIMEOUT}s",
            level=xbmc.LOGINFO,
        )
        file_paths = []
        timeout = AUTO_SELECT_DOWNLOAD_TIMEOUT if auto_select else DEFAULT_DOWNLOAD_TIMEOUT
        failed = 0
        deadline = time.monotonic() + AUTO_SELECT_DOWNLOAD_TIMEOUT if auto_select else None
        for idx, subtitle in enumerate(subtitles):
            if auto_select and idx >= MAX_AUTO_DOWNLOAD_CANDIDATES:
                break
            try:
                _check_download(deadline, cancelled)
                kodilog(
                    f"[StremioSubs] downloading embedded subtitle #{idx} "
                    f"lang={subtitle.get('lang') or '?'} url="
                    f"{_redact_subtitle_url(subtitle.get('url'))}",
                    level=xbmc.LOGDEBUG,
                )
                options = {'deadline': deadline, 'max_retries': 0} if auto_select else {}
                if cancelled is not None:
                    options['cancelled'] = cancelled
                file_path = self.download_subtitle(
                    subtitle, idx, imdb_id, title, season, episode, folder_path, timeout=timeout, **options
                )
                _check_download(deadline, cancelled)
                if file_path:
                    file_paths.append(file_path)
                    if auto_select:
                        break
                else:
                    failed += 1
            except SubtitleDownloadStopped:
                # Completed local downloads remain candidates, but a revoked
                # request must receive no paths to attach to another playback.
                if cancelled is not None and cancelled():
                    return []
                break
            except Exception as e:
                failed += 1
                kodilog(
                    f"[StremioSubs] failed to download embedded subtitle #{idx}: {type(e).__name__}"
                )
                continue
        kodilog(
            f"[StremioSubs] download_subtitles_batch done: {len(file_paths)} ok, "
            f"{failed} failed of {len(subtitles)}",
            level=xbmc.LOGINFO,
        )
        return file_paths

    def download_subtitle(
        self,
        subtitle: Dict[str, Any],
        index: int,
        imdb_id: str,
        title: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        folder_path: Optional[str] = None,
        timeout: int = DEFAULT_DOWNLOAD_TIMEOUT,
        deadline: Optional[float] = None,
        cancelled: Optional[Callable[[], bool]] = None,
        max_retries: int = 2,
    ) -> Optional[str]:
        _check_download(deadline, cancelled)
        url = subtitle.get("url", "")
        if not self._valid_subtitle_record(subtitle):
            raise ValueError("unsafe subtitle record")
        lang = subtitle.get("lang") or ""
        lang_name = language_code_to_name(lang)
        lang_name = slugify_title(lang_name) or "unknown"
        extension = self._get_subtitle_extension(url)

        title = slugify_title(title)

        if folder_path:
            filename = f"Subtitle No.{index}.{title}.{lang_name}{extension}"
            file_path = os.path.join(folder_path, filename)
        else:
            base_path = os.path.join(
                ADDON_PROFILE_PATH, "Subtitles", safe_subtitle_path_component(imdb_id)
            )
            if season and episode:
                file_path = os.path.join(
                    base_path,
                    str(season),
                    str(episode),
                    f"Subtitle No.{index}.{title}.S{season}E{episode}.{lang_name}{extension}",
                )
            elif season:
                file_path = os.path.join(
                    base_path,
                    str(season),
                    f"Subtitle No.{index}.{title}.S{season}.{lang_name}{extension}",
                )
            else:
                filename = f"Subtitle No.{index}.{title}.{lang_name}{extension}"
                file_path = os.path.join(base_path, filename)

        # Concurrent requests must never truncate or remove each other's part.
        temporary_path = file_path + '.' + uuid4().hex + ".part"
        response = None
        supplied_deadline = deadline
        request_deadline = time.monotonic() + timeout
        if deadline is not None:
            request_deadline = min(request_deadline, deadline)

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with requests.Session() as session:
                session.trust_env = False
                session.headers["Accept-Encoding"] = "gzip, deflate"
                for attempt in range(max_retries + 1):
                    if response is not None:
                        response.close()
                        response = None
                    try:
                        _check_download(request_deadline, cancelled)
                        response = request_with_safe_redirects(
                            session.get, url, validator=is_safe_http_url,
                            stream=True, headers=USER_AGENT_HEADER, timeout=timeout,
                            deadline=request_deadline, cancelled=cancelled,
                        )
                    except SubtitleDownloadStopped:
                        raise
                    except Exception:
                        _check_download(request_deadline, cancelled)
                        if attempt >= max_retries:
                            raise
                        _wait_for_retry(1.0, request_deadline, cancelled)
                        continue
                    if response.status_code == 200:
                        break
                    status = response.status_code
                    delay = _retry_delay(response, attempt)
                    response.close()
                    response = None
                    if attempt >= max_retries:
                        raise ValueError(f"HTTP {status}")
                    _wait_for_retry(delay, request_deadline, cancelled)
                raw = read_bounded_http_body(response, max_bytes=MAX_SUBTITLE_BYTES,
                                            deadline=request_deadline, cancelled=cancelled)
                if not raw:
                    raise ValueError("empty subtitle response")
                if _is_obvious_html_response(raw[:512]):
                    raise ValueError("HTML subtitle response")
                _check_download(request_deadline, cancelled)
                with open(temporary_path, "wb") as file:
                    file.write(raw)
                _check_download(request_deadline, cancelled)
                os.replace(temporary_path, file_path)
                return file_path
        except Exception as error:
            with contextlib.suppress(OSError):
                os.remove(temporary_path)
            # Preserve the existing cooperative signal for a caller's playback
            # deadline/cancellation. A manual per-file timeout need not cancel
            # the remaining user-selected downloads in download_subtitles_batch.
            _check_download(supplied_deadline, cancelled)
            if isinstance(error, SubtitleDownloadStopped):
                error = TimeoutError('subtitle download deadline')
            kodilog(f"Subtitle download error: {type(error).__name__}")
            if supplied_deadline is None:
                self.notification(f"Subtitle download error: {type(error).__name__}")
            raise error
        finally:
            if response is not None:
                with contextlib.suppress(Exception):
                    response.close()

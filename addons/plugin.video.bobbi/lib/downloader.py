import contextlib
import hashlib
import http.client
import json
import os
import re
import ssl
import threading
import time
from typing import Optional
from urllib.parse import parse_qsl, unquote, urlparse
from urllib.request import Request, urlopen

import xbmc
import xbmcgui
import xbmcvfs
from xbmcplugin import (
    addDirectoryItems,
    endOfDirectory,
    setContent,
)

from lib.download_control_flags import DownloadControlFlags
from lib.download_file_io import DownloadBusyError, download_lock, open_download_file, publish_download
from lib.utils.kodi.paths import join_kodi_path
from lib.download_manager import DownloadManager
from lib.gui.custom_progress import CustomProgressDialog
from lib.nav.debrid import resolve_cloud_download_url
from lib.utils.general.utils import set_pluging_category, supported_video_extensions
from lib.utils.kodi.utils import (
    ADDON_HANDLE,
    ADDON_PATH,
    action_url_run,
    apply_section_view,
    build_url,
    bytes_to_human_readable,
    get_setting,
    kodilog,
    notification,
    open_file,
    translatePath,
    translation,
)

# Compatibility name used by the download manager window. These signals are
# non-evictable control state, independent of metadata cache clear/generation.
cancel_flag_cache = DownloadControlFlags()


def handle_download_file(params):
    destination = params.get("destination")
    if not destination:
        kodilog(f"[Downloader] Invalid download destination: {destination}")
        notification("Invalid download destination.")
        return

    xbmcvfs.mkdirs(destination)

    url = params.get("url", "")
    file_name = normalize_file_name(params.get("file_name", ""), url)
    dest_path = join_kodi_path(destination, file_name)
    cancel_key = dest_path
    kodilog(
        f"[Downloader] handle_download_file: file_name={file_name}, dest_path={dest_path}, url_length={len(url)}"
    )

    manager = DownloadManager()
    entry = manager.register(name=file_name, dest_path=dest_path, url=url)
    if entry is None:
        kodilog(f"[Downloader] Download already in progress: {dest_path}")
        notification("Download already in progress.")
        return

    downloader = Downloader(
        url=url,
        destination=destination,
        name=file_name,
        registry_id=dest_path,
    )
    cancel_flag_cache.set(cancel_key, downloader.is_cancelled)
    thread = downloader.run()
    if thread:
        manager.set_thread(dest_path, thread)
        kodilog(f"[Downloader] Download thread started for: {dest_path}")
    else:
        kodilog(f"[Downloader] Failed to start download thread for: {dest_path}")


def download_cloud_file(params):
    url = params.get("url", "")
    filename = params.get("filename", "")
    mode = params.get("mode", "movie")
    debrid_type = params.get("debrid_type", "")

    if not url and debrid_type in ("TB", "Torbox"):
        url = resolve_cloud_download_url(
            {
                "debrid_type": debrid_type,
                "torrent_id": params.get("torrent_id", ""),
                "file_id": params.get("file_id", ""),
            }
        )

    if not url:
        notification("Download link unavailable.")
        return

    dest_data = {
        "title": filename,
        "mode": "movies" if mode in ("movie", "movies") else mode,
    }
    destination = get_destination_path(dest_data)
    if not destination:
        notification("Invalid download destination.")
        return

    file_name = normalize_file_name(filename, url)
    dest_path = join_kodi_path(destination, file_name)

    manager = DownloadManager()
    entry = manager.register(name=file_name, dest_path=dest_path, url=url)
    if entry is None:
        notification("Download already in progress.")
        return

    downloader = Downloader(
        url=url,
        destination=destination,
        name=file_name,
        registry_id=dest_path,
    )
    cancel_flag_cache.set(dest_path, False)
    thread = downloader.run()
    if thread:
        manager.set_thread(dest_path, thread)


def get_destination_path(data):
    download_dir = get_setting("download_dir")
    destination = translatePath(download_dir)

    if not get_setting("organize_downloads", False):
        return destination

    mode = data.get("mode", "")
    if mode == "movies":
        movies_folder = get_setting("download_folder_movies", "Movies")
        destination = join_kodi_path(destination, movies_folder)
    elif mode == "tv":
        tv_data = data.get("tv_data", {})
        show_name = tv_data.get("name") or data.get("title", "")
        season = tv_data.get("season", 1)
        tvshows_folder = get_setting("download_folder_tvshows", "TV Shows")
        destination = join_kodi_path(
            destination,
            tvshows_folder,
            show_name,
            f"Season {int(season):02d}",
        )

    xbmcvfs.mkdirs(destination)
    return destination


def download_video(params):
    data = json.loads(params["data"])
    destination = get_destination_path(data)
    handle_download_file(
        {"destination": destination, "file_name": data["title"], "url": data["url"]}
    )


class ProgressHandler:
    def update(
        self,
        percent: int,
        message: str,
        downloaded_str: str = "",
        size_str: str = "",
        speed_str: str = "",
        eta_str: str = "",
    ):
        pass

    def cancelled(self) -> bool:
        return False

    def close(self):
        pass


class KodiProgressHandler(ProgressHandler):
    def __init__(self, title: str, addon_path: str):
        self.dialog = CustomProgressDialog("custom_progress_dialog.xml", addon_path)
        self.dialog.show_dialog()

    def update(
        self,
        percent: int,
        message: str,
        downloaded_str: str = "",
        size_str: str = "",
        speed_str: str = "",
        eta_str: str = "",
    ):
        self.dialog.update_progress(percent, message, downloaded_str, size_str, speed_str, eta_str)

    def cancelled(self) -> bool:
        return self.dialog.cancelled

    def close(self):
        self.dialog.close()


class Downloader:
    def __init__(
        self,
        url: str,
        destination: str,
        name: str,
        registry_id: Optional[str] = None,
        show_progress: bool = True,
    ):
        self.url = url
        self._source_url = url
        self.destination = destination
        self.name = name
        self.registry_id = registry_id
        self.show_progress = show_progress
        self.headers = {}
        self.file_size = 0
        self.monitor = xbmc.Monitor()
        self.progress_handler = None
        self.is_cancelled = False
        self.dest_path = join_kodi_path(destination, name)
        self.temp_path = self.dest_path + ".part"
        self.meta_path = self.dest_path + ".bobbi.json"
        self._start_time = None
        self._transfer = {}
        self._reason = ""

    def _write_metadata(
        self,
        status: str,
        progress: int = 0,
        size: int = 0,
        downloaded: int = 0,
        speed: int = 0,
        eta: int = 0,
    ):
        try:
            if status == "downloading" and cancel_flag_cache.get(self.dest_path) is True:
                return
            meta = {
                "title": self.name,
                "url": self._source_url,
                "status": status,
                "progress": progress,
                "size": size,
                "downloaded": downloaded,
                "speed": speed,
                "eta": eta,
                "reason": self._reason,
                "transfer": self._transfer,
            }
            with open_file(self.meta_path, "w") as f:
                json.dump(meta, f)
            if status not in ("cancelled", "completed") and cancel_flag_cache.cancelled(self.dest_path):
                # Cancel persists its reason before writing metadata. If it
                # raced this write, repair once after close; both writers now
                # agree on cancelled. Publication already committed is separate.
                meta.update(status="cancelled", reason="cancelled")
                with open_file(self.meta_path, "w") as f:
                    json.dump(meta, f)
        except Exception as e:
            kodilog(f"[Downloader] Failed to write metadata: {e!s}")

    def _update_registry(self, downloaded: int, percent: int):
        if not self.registry_id:
            return
        speed = 0
        eta = 0
        if self._start_time is not None:
            elapsed = time.time() - self._start_time
            if elapsed > 0:
                speed = int(downloaded / elapsed)
            remaining = self.file_size - downloaded
            if speed > 0 and remaining > 0:
                eta = int(remaining / speed)
            else:
                eta = 0
        DownloadManager().update_progress(
            self.registry_id,
            downloaded=downloaded,
            speed=speed,
            eta=eta,
            progress=percent,
            size=self.file_size,
        )

    def _set_registry_status(self, status: str):
        if status != "completed" and cancel_flag_cache.cancelled(self.dest_path):
            status = "cancelled"
        if status == "completed":
            cancel_flag_cache.delete(self.dest_path)
        if not self.registry_id:
            return
        DownloadManager().set_status(self.registry_id, status)

    def _is_cancelled(self):
        if self.progress_handler and self.progress_handler.cancelled():
            return True
        if cancel_flag_cache.get(self.dest_path) is True:
            return True
        if self.registry_id:
            entry = DownloadManager().get_entry(self.registry_id)
            if entry and entry.cancel_flag:
                return True
        return False

    def run(self):
        if not self.url:
            notification("No URL provided for download.")
            return None
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return thread

    def _run(self):
        # Show progress dialog immediately, before network calls
        if self.show_progress:
            self.progress_handler = KodiProgressHandler("Downloading", ADDON_PATH)
            self.progress_handler.update(0, translation(90807))
        else:
            self.progress_handler = ProgressHandler()

        self._prepare_url()
        if not self._validate_url():
            notification("Invalid URL for download.")
            self._set_registry_status("error")
            self.progress_handler.close()
            return
        self._start_download()

    def _prepare_url(self):
        try:
            if "|" in self.url:
                self.headers = dict(parse_qsl(self.url.rsplit("|", 1)[1]))
                self.url = self.url.split("|")[0]
        except Exception as e:
            kodilog(f"[Downloader] Failed to parse headers: {e!s}")

    def _validate_url(self):
        try:
            if not self.headers.get("User-Agent"):
                from lib.utils.general.utils import USER_AGENT_STRING

                self.headers["User-Agent"] = USER_AGENT_STRING

            # The actual transfer response is the sole source of object identity
            # and length. A separate GET leaked a response and could race changes.
            parsed = urlparse(self.url)
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except Exception as e:
            kodilog(f"[Downloader] Validation error: {e!s}")
            return False

    def _start_download(self):
        if self.progress_handler is None:
            if self.show_progress:
                self.progress_handler = KodiProgressHandler("Downloading", ADDON_PATH)
            else:
                self.progress_handler = ProgressHandler()
        try:
            with download_lock(translatePath(self.dest_path)):
                self._transfer_download()
        except DownloadBusyError:
            notification("Download already in progress.")
        except Exception as e:
            self._set_registry_status("error")
            notification(f"Download error: {e!s}")
        finally:
            if self.progress_handler:
                self.progress_handler.close()

    def _stop_reason(self):
        if cancel_flag_cache.cancelled(self.dest_path):
            return "cancelled"
        entry = DownloadManager().get_entry(self.registry_id) if self.registry_id else None
        if entry and entry.status == "cancelled":
            return "cancelled"
        if self._is_cancelled():
            meta = get_download_metadata(self.dest_path)
            return "cancelled" if meta.get("status") == "cancelled" else "paused"
        if self.monitor.abortRequested():
            return "aborted"
        return ""

    def _file_digest(self):
        digest = hashlib.sha256()
        with open_download_file(translatePath(self.temp_path), "rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest

    def _finish_transfer(self, status, reason, downloaded):
        if status != "completed" and cancel_flag_cache.cancelled(self.dest_path):
            status, reason = "cancelled", "cancelled"
        if (status == "paused" and downloaded and not self._transfer.get("complete")
                and (not self._transfer.get("etag") or self._transfer.get("total") is None)):
            # UI offers Resume only for paused. Do not advertise unsafe resume
            # without both a stable validator and a verified total for the prefix.
            status = "error"
        self._reason = reason
        percent = 100 if status == "completed" else min(
            99, int(downloaded * 100 / self.file_size) if self.file_size else 0)
        self._write_metadata(status, percent, size=self.file_size, downloaded=downloaded)
        self._update_registry(downloaded, percent)
        self._set_registry_status(status)

    def _reject_resume(self, meta, message):
        # Preserve the original URL, validator and checkpoint, but remove a
        # misleading Resume affordance when the existing file cannot be trusted.
        meta = dict(meta, status="error", reason="resume_unverified")
        try:
            with open_file(self.meta_path, "w") as file:
                json.dump(meta, file)
        except Exception as exc:
            kodilog(f"[Downloader] Failed to save resume error: {exc!s}")
        raise OSError(message)

    def _transfer_download(self):
        self._transfer = {}
        downloaded, expected = 0, None
        body_eof = False
        digest = hashlib.sha256()
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in ("range", "if-range", "accept-encoding")}
        headers["Accept-Encoding"] = "identity"
        identity = hashlib.sha256(json.dumps(
            [self.url, sorted((key.lower(), value) for key, value in headers.items())],
            separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
        # Refuse collisions before altering existing metadata or bytes. Even a
        # same-size final file is not evidence of this download's identity.
        if xbmcvfs.exists(self.dest_path):
            raise OSError("Destination already exists; choose a different download name")
        if xbmcvfs.exists(self.temp_path):
            meta = get_download_metadata(self.dest_path)
            transfer = meta.get("transfer", {})
            downloaded = xbmcvfs.Stat(self.temp_path).st_size()
            if (transfer.get("version") != 1 or transfer.get("identity") != identity
                    or (downloaded and (transfer.get("total") is None
                        or (not transfer.get("etag") and not transfer.get("complete"))))):
                self._reject_resume(meta, "Cannot verify this partial file for resume; preserved it. "
                                    "Choose another download name or explicitly delete it first")
            digest = self._file_digest()
            if digest.hexdigest() != transfer.get("sha256"):
                self._reject_resume(meta, "Partial file differs from its saved checkpoint; preserved it. "
                                    "Choose another download name or explicitly delete it first")
            if downloaded or transfer.get("complete"):
                self._transfer = dict(transfer)
                self.file_size = expected = transfer["total"]
                if downloaded > expected:
                    raise OSError("Partial file exceeds its verified size; preserved it")
                headers["Range"] = f"bytes={downloaded}-"
                headers["If-Range"] = transfer["etag"]

        self._start_time = time.time()
        try:
            reason = self._stop_reason()
            if reason:
                self._finish_transfer("cancelled" if reason == "cancelled" else "paused",
                                      reason, downloaded)
                return
            if (self._transfer.get("complete") is True and downloaded == expected):
                publish_download(translatePath(self.temp_path), translatePath(self.dest_path))
                self._finish_transfer("completed", "complete", downloaded)
                return
            request = Request(self.url, headers=headers)
            context = ssl.create_default_context()
            # Existing compatibility policy is unchanged in this integrity fix.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            with contextlib.closing(urlopen(request, context=context, timeout=30)) as response:
                get_all = getattr(response.headers, "get_all", None)
                if get_all:
                    for name in ("Content-Length", "Content-Range", "ETag", "Transfer-Encoding", "Content-Encoding"):
                        if len(get_all(name, [])) > 1:
                            raise ValueError("Duplicate download response identity/framing header")
                length = response.headers.get("Content-Length")
                if length is not None and not re.fullmatch(r"[0-9]+", length):
                    raise ValueError("Invalid response length")
                length = int(length) if length is not None else None
                etag = response.headers.get("ETag", "")
                strong_etag = etag if re.fullmatch(r'"[\x21\x23-\x7e\x80-\xff]*"', etag) else ""
                encoding = response.headers.get("Content-Encoding", "identity").lower()
                if encoding != "identity":
                    raise ValueError("Encoded download cannot be verified")
                chunked = getattr(response, "chunked", False) is True
                transfer_encoding = response.headers.get("Transfer-Encoding", "").lower()
                if transfer_encoding and (transfer_encoding != "chunked" or not chunked):
                    raise ValueError("Unsupported download transfer encoding")
                if chunked and length is not None:
                    raise ValueError("Ambiguous response framing")
                if self._transfer:
                    content_range = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)",
                                                response.headers.get("Content-Range", ""))
                    if (response.status != 206 or not content_range
                            or tuple(map(int, content_range.groups())) !=
                            (downloaded, expected - 1, expected)
                            or length != expected - downloaded
                            or strong_etag != self._transfer["etag"]):
                        raise ValueError("Resume response does not match the saved object/range; "
                                         "partial file preserved")
                else:
                    if response.status != 200 or response.headers.get("Content-Range"):
                        raise ValueError("Expected a full download response")
                    if length is None and not chunked:
                        raise ValueError("Unknown download length without complete HTTP chunk framing")
                    expected = length
                    self.file_size = expected or 0
                    self._transfer = dict(version=1, identity=identity, etag=strong_etag,
                                          total=expected, sha256=digest.hexdigest())
                self._reason = ""
                self._write_metadata("downloading", 0, size=self.file_size, downloaded=downloaded)
                self._set_registry_status("downloading")
                with open_download_file(translatePath(self.temp_path), "ab" if "Range" in headers else "wb") as file:
                    while True:
                        reason = self._stop_reason()
                        if reason:
                            break
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            body_eof = True
                        reason = self._stop_reason()
                        if reason or not chunk:
                            break
                        if expected is not None and downloaded + len(chunk) > expected:
                            raise ValueError("Download exceeds its declared size")
                        written = file.write(chunk)
                        if written is not True and written != len(chunk):
                            raise OSError("Incomplete file write")
                        downloaded += len(chunk)
                        digest.update(chunk)
                        self._transfer["sha256"] = digest.hexdigest()
                        percent = min(99, int(downloaded * 100 / expected)) if expected else 0
                        elapsed = max(time.time() - self._start_time, 0.001)
                        speed = int(downloaded / elapsed)
                        eta = int(max(0, self.file_size - downloaded) / speed) if speed else 0
                        self.progress_handler.update(percent, self.name,
                            bytes_to_human_readable(downloaded), f"{percent}%",
                            f"{bytes_to_human_readable(speed)}/s", f"{eta}s" if eta else "")
                        self._write_metadata("downloading", percent, size=self.file_size,
                                             downloaded=downloaded, speed=speed, eta=eta)
                        self._update_registry(downloaded, percent)
                        self.monitor.waitForAbort(0.1)
            # A fully received, closed, verified body remains complete even if
            # a stop arrived at EOF. Preserve that proof for explicit resume;
            # never issue the impossible bytes=total- request for such a file.
            complete_body = ((expected is not None and downloaded == expected)
                             or (expected is None and body_eof))
            if complete_body:
                self.file_size = downloaded
                self._transfer["total"] = downloaded
                if (xbmcvfs.Stat(self.temp_path).st_size() != downloaded
                        or self._file_digest().hexdigest() != digest.hexdigest()):
                    raise OSError("Closed partial file failed size/content verification")
                self._transfer["complete"] = True
            # Both handles are closed before publication. Stops still win, even
            # when they arrived during EOF, close, or local content verification.
            reason = reason or self._stop_reason()
            if reason:
                self.is_cancelled = reason != "aborted"
                self._finish_transfer("cancelled" if reason == "cancelled" else "paused",
                                      reason, downloaded)
                return
            if not complete_body:
                self._finish_transfer("paused" if self._transfer.get("etag") else "error",
                                      "truncated", downloaded)
                notification("Download incomplete; partial file preserved.")
                return
            reason = self._stop_reason()
            if reason:
                self._finish_transfer("cancelled" if reason == "cancelled" else "paused",
                                      reason, downloaded)
                return
            publish_download(translatePath(self.temp_path), translatePath(self.dest_path))
            self._finish_transfer("completed", "complete", downloaded)
            notification(f"Download completed: {self.name}")
        except Exception as exc:
            # HTTPError owns an HTTP response too, despite being raised before
            # entry to the response context manager (for example HTTP 416).
            with contextlib.suppress(Exception):
                exc.close()
            reason = self._stop_reason()
            if reason:
                status = "cancelled" if reason == "cancelled" else "paused"
            elif isinstance(exc, http.client.IncompleteRead):
                reason = "truncated"
                status = "paused" if self._transfer.get("etag") and expected is not None else "error"
            else:
                reason, status = "error", "error"
                if self._transfer.get("complete"):
                    reason, status = "publication_failed", "paused"
            self._finish_transfer(status, reason, downloaded)
            notification(f"Download error (partial file preserved): {exc!s}")


def handle_cancel_download(params, refresh=True):
    file_path = json.loads(params.get("file_path"))
    if file_path:
        final_path = file_path[:-5] if file_path.endswith(".part") else file_path
        cancel_flag_cache.cancel(final_path)
        meta = get_download_metadata(final_path)
        meta["status"] = "cancelled"
        try:
            with open_file(final_path + ".bobbi.json", "w") as file:
                json.dump(meta, file)
        except Exception as exc:
            kodilog(f"[Downloader] Failed to save cancellation: {exc!s}")
        DownloadManager().set_status(final_path, "cancelled")
        if refresh:
            xbmc.executebuiltin("Container.Refresh")
    else:
        notification("No active download found.")


def handle_pause_download(params, refresh=True):
    file_path = json.loads(params.get("file_path"))
    if file_path:
        # Derive final path (strip .part if present)
        final_path = file_path[:-5] if file_path.endswith(".part") else file_path
        cancel_flag_cache.set(final_path, True)
        if cancel_flag_cache.cancelled(final_path):
            return
        meta_path = final_path + ".bobbi.json"
        try:
            if xbmcvfs.exists(meta_path):
                with open_file(meta_path, "r") as f:
                    meta = json.load(f)
                if meta.get("status") == "cancelled":
                    return
                meta["status"] = "paused"
                with open_file(meta_path, "w") as f:
                    json.dump(meta, f)
        except Exception as e:
            kodilog(f"[Downloader] Failed to update pause metadata: {e!s}")
        if refresh:
            xbmc.executebuiltin("Container.Refresh")
    else:
        notification("No active download found.")


def resume_download(params):
    file_path = json.loads(params.get("file_path"))
    if not file_path:
        notification("File not found.")
        return

    # Derive final path (strip .part if present)
    final_path = file_path[:-5] if file_path.endswith(".part") else file_path
    temp_path = final_path + ".part"

    # Must have at least the temp file or the final file
    if not xbmcvfs.exists(temp_path) and not xbmcvfs.exists(final_path):
        notification("File not found.")
        return

    meta_path = final_path + ".bobbi.json"
    try:
        with open_file(meta_path, "r") as f:
            meta = json.load(f)
    except Exception as e:
        kodilog(f"[Downloader] Failed to read metadata for resume: {e!s}")
        notification("No metadata found for resume.")
        return

    if meta.get("status") == "cancelled" or cancel_flag_cache.cancelled(final_path):
        notification("Download was cancelled; start a new download explicitly.")
        return

    manager = DownloadManager()
    entry = manager.register(name=os.path.basename(final_path), dest_path=final_path,
                             url=meta.get("url", ""))
    if entry is None:
        notification("Download already in progress.")
        return
    cancel_flag_cache.set(final_path, False)
    downloader = Downloader(
        url=meta.get("url", ""),
        destination=os.path.dirname(final_path),
        name=os.path.basename(final_path),
        registry_id=final_path,
    )
    thread = downloader.run()
    if thread:
        manager.set_thread(final_path, thread)


def get_download_metadata(path):
    # Derive final path (strip .part if present)
    final_path = path[:-5] if path.endswith(".part") else path
    meta_path = final_path + ".bobbi.json"
    defaults = {"status": "unknown", "progress": 0, "title": ""}
    try:
        if xbmcvfs.exists(meta_path):
            with open_file(meta_path, "r") as f:
                meta = json.load(f)
            defaults.update(meta)
    except Exception:
        pass
    return defaults


def handle_delete_file(params):
    file_path = json.loads(params.get("file_path"))
    if not xbmcvfs.exists(file_path):
        notification("File not found.")
        return
    try:
        xbmcvfs.delete(file_path)
        # Also delete the temp .part file if it exists
        final_path = file_path[:-5] if file_path.endswith(".part") else file_path
        temp_path = final_path + ".part"
        if xbmcvfs.exists(temp_path):
            xbmcvfs.delete(temp_path)
        meta_path = final_path + ".bobbi.json"
        if xbmcvfs.exists(meta_path):
            xbmcvfs.delete(meta_path)
        notification("File Deleted")
        xbmc.executebuiltin("Container.Refresh")
    except Exception as e:
        kodilog(f"Error deleting file: {e!s}")
        notification(f"Failed to delete file: {e!s}")


def _count_active_downloads(directory):
    """Count downloads that are in-progress (downloading or paused) recursively
    across all subdirectories.
    """  # noqa: D205
    count = 0

    with contextlib.suppress(Exception):
        count = _walk_count_active(directory)
    return count


def _walk_count_active(directory):
    """Recursively walk a directory using xbmcvfs and count active downloads."""
    count = 0

    dirs, files = xbmcvfs.listdir(directory)
    for f in files:
        f = f.decode("utf-8") if isinstance(f, bytes) else f
        if f.endswith(".bobbi.json"):
            download_path = join_kodi_path(directory, f.replace(".bobbi.json", ""))
            if download_path.endswith(".part"):
                download_path = download_path[:-5]
            meta = get_download_metadata(download_path)
            status = meta.get("status", "")
            if status in ("downloading", "paused"):
                count += 1
    for d in dirs:
        d = d.decode("utf-8") if isinstance(d, bytes) else d
        count += _walk_count_active(join_kodi_path(directory, d))
    return count


def downloads_viewer(params):
    set_pluging_category(translation(90015))
    download_dir = translatePath(get_setting("download_dir"))
    path = params.get("path", download_dir)
    if not path:
        path = download_dir
    translated_path = translatePath(path)
    item_list = []

    try:
        setContent(ADDON_HANDLE, "files")
        directories, files = xbmcvfs.listdir(translated_path)
        # At root level, count active downloads recursively across all subfolders
        is_root = translated_path.rstrip(os.sep) == download_dir.rstrip(os.sep)
        if is_root:
            active_count = _count_active_downloads(translated_path)
        else:
            active_downloads = [
                f for f in files if is_active_download(join_kodi_path(translated_path, f))
            ]
            active_count = len(active_downloads)

        active_label = f"[COLOR red]{translation(90373)}: {active_count}[/COLOR]"
        active_item = xbmcgui.ListItem(label=active_label)
        active_item.setProperty("IsPlayable", "false")
        active_item.setArt({"icon": join_kodi_path(ADDON_PATH, "resources", "img", "download.png")})
        item_list.append(("", active_item, False))

        for item in directories + files:
            item_path = join_kodi_path(translated_path, item)

            # Skip metadata files
            if item.endswith((".bobbi.json", ".bobbi.lock")):
                continue

            if item in directories:
                list_item = xbmcgui.ListItem(label=item)
                info_tag = list_item.getVideoInfoTag()
                info_tag.setTitle(item)
                info_tag.setMediaType("folder")
                list_item.setProperty("IsPlayable", "false")
                is_folder = True
                # Navigate through the plugin so subdirectories work correctly
                listing_url = build_url("downloads_viewer", path=item_path)
            else:
                # Strip .part for display but keep it for internal path
                display_name = item[:-5] if item.endswith(".part") else item
                meta = get_download_metadata(item_path)
                status = meta.get("status", "unknown")
                progress = meta.get("progress", 0)

                if status == "completed":
                    label = f"[COLOR green][OK][/COLOR] {display_name}"
                elif status == "paused":
                    label = f"[COLOR orange][PAUSED][/COLOR] {display_name} ({progress}%)"
                elif status == "downloading":
                    label = f"[COLOR red][DL][/COLOR] {display_name}"
                else:
                    label = display_name

                list_item = xbmcgui.ListItem(label=label)
                info_tag = list_item.getVideoInfoTag()
                info_tag.setTitle(display_name)
                info_tag.setMediaType("file")

                # Make completed files playable directly via plugin URL
                if status == "completed" and not item.endswith(".part"):
                    play_url = build_url("play_url", url=item_path, name=display_name)
                    list_item.setProperty("IsPlayable", "true")
                    list_item.setPath(play_url)
                else:
                    list_item.setProperty("IsPlayable", "false")

                context_menu = []

                if status == "downloading":
                    context_menu.append(
                        (
                            translation(90777),
                            action_url_run(
                                "handle_pause_download",
                                file_path=json.dumps(item_path),
                            ),
                        )
                    )
                elif status == "paused":
                    context_menu.append(
                        (
                            translation(90778),
                            action_url_run(
                                "resume_download",
                                file_path=json.dumps(item_path),
                            ),
                        )
                    )
                elif is_active_download(item_path):
                    context_menu.append(
                        (
                            translation(90374),
                            action_url_run(
                                "handle_cancel_download",
                                file_path=json.dumps(item_path),
                            ),
                        )
                    )

                if status in ("completed", "paused", "cancelled", "error"):
                    context_menu.append(
                        (
                            translation(90782),
                            action_url_run("handle_delete_file", file_path=json.dumps(item_path)),
                        )
                    )

                list_item.addContextMenuItems(context_menu)
                is_folder = False

                # Use plugin URL for playable completed files so Kodi routes
                # them through play_url for proper resolution
                if status == "completed" and not item.endswith(".part"):
                    listing_url = build_url("play_url", url=item_path, name=display_name)
                else:
                    listing_url = item_path
            item_list.append((listing_url, list_item, is_folder))

        addDirectoryItems(ADDON_HANDLE, item_list)
        endOfDirectory(ADDON_HANDLE)
        apply_section_view("view.downloads", content_type="files")
    except Exception as e:
        notification(f"Error: {e!s}", translation(90662))
        endOfDirectory(ADDON_HANDLE, succeeded=False)


def is_active_download(path):
    if path.endswith((".bobbi.json", ".bobbi.lock")):
        return False
    meta = get_download_metadata(path)
    if meta["status"] == "downloading":
        return True
    if meta["status"] in ("paused", "completed", "cancelled", "error"):
        return False
    cancel_flag = cancel_flag_cache.get(path)
    return cancel_flag is not True


def normalize_file_name(file_name, url=""):
    file_name = (file_name or "").strip()
    valid_extensions = {ext.lower() for ext in supported_video_extensions()}

    base, ext = os.path.splitext(file_name)
    if ext.lower() not in valid_extensions:
        base = file_name
        ext = ""

    if not base and url:
        url_path = unquote(urlparse(url.split("|", 1)[0]).path)
        base = os.path.splitext(os.path.basename(url_path))[0]

    if not ext and url:
        url_path = unquote(urlparse(url.split("|", 1)[0]).path)
        _, url_ext = os.path.splitext(url_path)
        if url_ext.lower() in valid_extensions:
            ext = url_ext

    # Remove invalid characters and dots from base name
    base = re.sub(r'[\\/*?:"<>|.]', "_", base)
    base = re.sub(r"_+", "_", base)
    return f"{base}{ext}"

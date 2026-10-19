# -*- coding: utf-8 -*-
"""Tool: Network Speed Test.

Combines:
1. LAN & Cloud Drive Video Stream Benchmark (SMB/NFS/WebDAV/HTTP/FTP/Local)
   - Chunk-based reading via xbmcvfs with zero memory retention.
   - Connection stabilization period (2s).
   - Real-time Mbps/MB/s, max/min speed, and network stability rate.
   - 4K Blu-ray Remux streaming evaluation.
2. Internet WAN Speed Test (Ping Latency, Download Bandwidth, Upload Bandwidth).
"""

import gc
import os
import socket
import time
import traceback
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

from ..common.kodi_ui import (
    dialog_browse,
    dialog_ok,
    dialog_select,
    dialog_textviewer,
    get_setting,
    get_setting_int,
    get_string,
    progress_dialog,
    show_notification,
)
from ..common.logger import debug, error, info
from .base_tool import BaseTool, ToolRegistry

try:
    import xbmc
    import xbmcgui
    import xbmcvfs
    _HAS_XBMC = True
except ImportError:
    _HAS_XBMC = False
    xbmc = None
    xbmcgui = None
    xbmcvfs = None

# Stream test constants
STREAM_TEST_DURATION = 30          # Maximum duration (seconds)
STREAM_MAX_READ_SIZE = 600 * 1024 * 1024  # Maximum read data (600 MB)
STREAM_BUFFER_SIZE = 1024 * 1024   # 1 MB chunk size
STREAM_MIN_FILE_SIZE = 1024 * 1024 * 1024  # 1 GB file recommendation
STREAM_STABILIZATION_SEC = 2       # 2s initial stabilization period

SUPPORT_PROTOCOLS = [
    "smb://", "nfs://", "webdav://", "dav://",
    "http://", "https://", "ftp://", "ftps://",
    "",  # Local storage path (/storage/..., C:/...)
]

DEFAULT_PING_HOSTS = ["223.5.5.5", "1.1.1.1", "8.8.8.8"]
DEFAULT_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=50000000"
DEFAULT_UPLOAD_URL = "https://speed.cloudflare.com/__up"


@ToolRegistry.register
class NetSpeedtestTool(BaseTool):
    id = "speedtest"
    title_id = 30002
    description_id = 30028
    icon = "DefaultNetwork.png"
    order = 20

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(30002, "Network Speed Test")
        info("Network Speedtest menu invoked")

        options = [
            f"1. {get_string(30210, 'LAN & Cloud Drive Speed Test (SMB/NFS/WebDAV/Local)')}",
            f"2. {get_string(30211, 'Internet WAN Speed Test')}",
        ]

        idx = dialog_select(title, options)
        if idx == 0:
            self._run_stream_speedtest(title)
        elif idx == 1:
            self._run_internet_speedtest(title)

    # ==================== Mode 1: LAN / Cloud Drive Stream Test ====================

    def _run_stream_speedtest(self, title: str) -> None:
        """Benchmark LAN / WebDAV / Cloud Drive streaming throughput using xbmcvfs."""
        info("Starting LAN & Cloud Drive Video Stream Benchmark")

        # Step 1: Select source category
        cat_title = get_string(30221, "Select Speed Test Category")
        category_options = [
            get_string(30222, "Mounted Cloud Drive / LAN Video (SMB/NFS/WebDAV)"),
            get_string(30223, "Local Storage / External Drive Large Video"),
        ]
        cat_idx = dialog_select(cat_title, category_options)
        if cat_idx < 0:
            return

        # Step 2: Select video file
        browse_heading = get_string(30212, "Select video file (>=1GB recommended) for speed test")
        if _HAS_XBMC and xbmcgui and hasattr(xbmcgui.Dialog(), "browseSingle"):
            mask_type = "video" if cat_idx == 0 else ""
            selected_file = xbmcgui.Dialog().browseSingle(1, browse_heading, mask_type, "", False, False, "")
        else:
            selected_file = dialog_browse(1, browse_heading, "files", "", False, False, "")

        if not selected_file:
            show_notification(title, get_string(30224, "No video file selected."))
            return

        # Step 3: Validate file & protocol
        protocol_name = self._get_protocol_name(selected_file)
        if not self._is_supported_protocol(selected_file):
            dialog_ok(title, get_string(30225, "Protocol not supported: %s\nPlease select SMB, NFS, WebDAV, or local file.") % protocol_name)
            return

        file_size = self._get_file_size(selected_file)
        if file_size <= 0:
            dialog_ok(title, get_string(30226, "Cannot open or read test file:\n%s") % selected_file)
            return

        file_size_gb = file_size / (1024 * 1024 * 1024)
        info(f"Target stream test file: [{protocol_name}] {selected_file} ({file_size_gb:.2f} GB)")

        if file_size < STREAM_MIN_FILE_SIZE:
            msg = get_string(30227, "File size is %s GB (less than 1GB recommended).\nDo you want to continue?") % f"{file_size_gb:.2f}"
            if not dialog_ok(title, msg):
                return

        # Step 4: Run the streaming benchmark loop
        total_bytes = 0
        max_speed_mb = 0.0
        min_speed_mb = float("inf")
        start_time = 0.0
        is_test_started = False
        elapsed_time = 0.0

        try:
            dlg_title = get_string(30228, "Streaming speed test in progress")
            wait_msg = f"[{protocol_name}]\n{get_string(30229, 'Waiting for file response, please wait...')}"
            with progress_dialog(dlg_title, wait_msg) as dp:
                f_src = self._open_vfs_file(selected_file)
                if not f_src:
                    dialog_ok(title, get_string(30230, "Cannot open test file. Please check mount and network connection."))
                    return

                try:
                    while True:
                        if dp.is_canceled():
                            info("Stream test cancelled by user")
                            break

                        chunk = self._read_vfs_chunk(f_src, STREAM_BUFFER_SIZE)
                        if not chunk:
                            info("Reached end of file during test")
                            break

                        chunk_len = len(chunk)
                        total_bytes += chunk_len
                        del chunk

                        now = time.time()
                        if not is_test_started:
                            start_time = now
                            is_test_started = True
                            dp.update(0, f"[{protocol_name}]\n{get_string(30213, 'Stabilization period (initial 2s)...')}")

                        if is_test_started:
                            elapsed_time = max(0.001, now - start_time)
                            total_mb = total_bytes / (1024 * 1024)

                            if elapsed_time >= STREAM_TEST_DURATION or total_bytes >= STREAM_MAX_READ_SIZE:
                                break

                            real_speed_mb = total_mb / elapsed_time
                            real_speed_mbps = real_speed_mb * 8.0

                            if elapsed_time > STREAM_STABILIZATION_SEC and real_speed_mb > 0:
                                if real_speed_mb > max_speed_mb:
                                    max_speed_mb = real_speed_mb
                                if real_speed_mb < min_speed_mb:
                                    min_speed_mb = real_speed_mb

                            pct = int(min(99, max(elapsed_time / STREAM_TEST_DURATION, total_bytes / STREAM_MAX_READ_SIZE) * 100))
                            remaining = max(0.0, STREAM_TEST_DURATION - elapsed_time)

                            if elapsed_time <= STREAM_STABILIZATION_SEC:
                                prog_msg = (
                                    f"[{protocol_name}]\n"
                                    f"Speed: {real_speed_mb:.1f} MB/s ({real_speed_mbps:.1f} Mbps)\n"
                                    f"Transferred: {total_mb:.1f} MB | Left: {remaining:.1f}s"
                                )
                            else:
                                min_display = min_speed_mb if min_speed_mb != float("inf") else 0.0
                                prog_msg = (
                                    f"[{protocol_name}]\n"
                                    f"Speed: {real_speed_mb:.1f} MB/s ({real_speed_mbps:.1f} Mbps)\n"
                                    f"Max/Min: {max_speed_mb:.1f} / {min_display:.1f} MB/s\n"
                                    f"Transferred: {total_mb:.1f} MB | Left: {remaining:.1f}s"
                                )
                            dp.update(pct, prog_msg)
                            time.sleep(0.01)

                finally:
                    self._close_vfs_file(f_src)

            self._show_stream_results(title, protocol_name, total_bytes, elapsed_time, max_speed_mb, min_speed_mb)

        except Exception as e:
            error(f"Stream benchmark error: {e}\n{traceback.format_exc()}")
            dialog_ok(title, get_string(30209, "Speed test failed: %s") % str(e))
        finally:
            self._cleanup_memory()

    def _show_stream_results(self, title: str, protocol_name: str, total_bytes: int, elapsed_time: float, max_mb: float, min_mb: float) -> None:
        if total_bytes <= 0 or elapsed_time <= 0:
            dialog_ok(title, get_string(30241, "No valid speed test data collected."))
            return

        total_mb = total_bytes / (1024 * 1024)
        avg_speed_mb = total_mb / elapsed_time
        avg_speed_mbps = avg_speed_mb * 8.0

        min_display = min_mb if min_mb != float("inf") else 0.0
        stability_rate = round((min_display / max_mb) * 100, 1) if max_mb > 0 else 0.0

        # Assess 4K Blu-ray Playback Quality
        if stability_rate > 0 and stability_rate < 70:
            quality_rating = get_string(30219, "Network stability is low (%s%% < 70%%), high jitter detected!") % f"{stability_rate:.1f}"
        elif avg_speed_mb < 12.5:
            quality_rating = get_string(30218, "Speed < 100 Mbps, playing Blu-ray remux will stutter!")
        elif 12.5 <= avg_speed_mb < 25.0:
            quality_rating = get_string(30217, "Meets basic Blu-ray playback, may stutter on peak bitrates.")
        elif 25.0 <= avg_speed_mb < 37.5:
            quality_rating = get_string(30216, "Fully meets 4K Blu-ray full-speed playback requirements!")
        else:
            quality_rating = get_string(30240, "Superb network speed (>300 Mbps), perfectly smooth for any high bitrate Blu-ray!")

        report_lines = [
            f"=== {get_string(30231, 'Stream Speed Test Report')} ===",
            "",
            get_string(30220, "Protocol: %s") % protocol_name,
            get_string(30232, "Actual Test Duration: %s s") % f"{elapsed_time:.1f}",
            get_string(30233, "Total Transferred: %s MB") % f"{total_mb:.1f}",
            "--------------------------------------------------",
            get_string(30234, "Average Speed: %s MB/s (%s Mbps)") % (f"{avg_speed_mb:.2f}", f"{avg_speed_mbps:.1f}"),
            get_string(30235, "Max Speed: %s MB/s") % f"{max_mb:.2f}",
            get_string(30236, "Min Speed: %s MB/s") % f"{min_display:.2f}",
            get_string(30214, "Network Stability: %s%%") % f"{stability_rate:.1f}",
            "--------------------------------------------------",
            get_string(30237, "Blu-ray Playback Rating: %s") % quality_rating,
        ]
        dialog_textviewer(title, "\n".join(report_lines))

    # ==================== Mode 2: Internet WAN Speed Test ====================

    def _run_internet_speedtest(self, title: str) -> None:
        """Measure internet WAN latency, download speed, and upload speed."""
        info("Starting Internet WAN Speed Test")
        custom_url = get_setting("custom_speedtest_url", "").strip()
        download_url = custom_url if custom_url else DEFAULT_DOWNLOAD_URL
        duration_limit = get_setting_int("speedtest_duration", 10)

        with progress_dialog(title, get_string(30201, "Testing latency...")) as dp:
            dp.update(10, get_string(30201, "Testing latency..."))
            latency_ms = self._measure_latency()
            if dp.is_canceled():
                return

            dp.update(25, get_string(30202, "Testing download speed..."))
            dl_mbps, dl_mbs = self._test_download(download_url, duration_limit, dp)
            if dp.is_canceled():
                return

            dp.update(70, get_string(30203, "Testing upload speed..."))
            ul_mbps, ul_mbs = self._test_upload(DEFAULT_UPLOAD_URL, max(5, duration_limit // 2), dp)
            dp.update(100, get_string(30204, "Speed test completed"))

        report_lines = [
            f"=== {get_string(30204, 'Speed test completed')} ===",
            "",
            f"{get_string(30205, 'Latency: %s ms') % (f'{latency_ms:.1f}' if latency_ms is not None else 'N/A')}",
            f"{get_string(30206, 'Download: %s Mbps (%s MB/s)') % (f'{dl_mbps:.2f}', f'{dl_mbs:.2f}')}",
            f"{get_string(30207, 'Upload: %s Mbps (%s MB/s)') % (f'{ul_mbps:.2f}', f'{ul_mbs:.2f}')}",
            "",
            f"Server: {download_url.split('?')[0]}",
        ]
        dialog_textviewer(title, "\n".join(report_lines))

    # ==================== VFS & Protocol Helpers ====================

    def _get_protocol_name(self, file_path: str) -> str:
        if not file_path:
            return get_string(30238, "Unknown Protocol")
        p = file_path.lower()
        if p.startswith("smb://"):
            return "SMB"
        elif p.startswith("nfs://"):
            return "NFS"
        elif p.startswith(("webdav://", "dav://")):
            return "WebDAV"
        elif p.startswith(("http://", "https://")):
            return "HTTP/HTTPS"
        elif p.startswith(("ftp://", "ftps://")):
            return "FTP"
        return get_string(30239, "Local / Mount Path")

    def _is_supported_protocol(self, file_path: str) -> bool:
        if not file_path:
            return False
        p = file_path.lower()
        for proto in SUPPORT_PROTOCOLS:
            if p.startswith(proto):
                return True
        return False

    def _get_file_size(self, file_path: str) -> int:
        if _HAS_XBMC and xbmcvfs:
            try:
                return xbmcvfs.File(file_path).size()
            except Exception:
                pass
        if os.path.exists(file_path):
            try:
                return os.path.getsize(file_path)
            except Exception:
                pass
        return 0

    def _open_vfs_file(self, file_path: str):
        if _HAS_XBMC and xbmcvfs:
            try:
                return xbmcvfs.File(file_path, "r")
            except Exception as e:
                error(f"Failed to open via xbmcvfs: {e}")
        try:
            return open(file_path, "rb")
        except Exception as e:
            error(f"Failed to open via standard open: {e}")
            return None

    def _read_vfs_chunk(self, f_obj, chunk_size: int) -> bytes:
        if hasattr(f_obj, "readBytes"):
            return f_obj.readBytes(chunk_size)
        elif hasattr(f_obj, "read"):
            return f_obj.read(chunk_size)
        return b""

    def _close_vfs_file(self, f_obj) -> None:
        if f_obj:
            try:
                f_obj.close()
            except Exception:
                pass

    def _cleanup_memory(self) -> None:
        """Deep memory cleanup with gc.collect() and Kodi ClearCache."""
        gc.collect()
        if _HAS_XBMC and xbmc:
            try:
                xbmc.executebuiltin("ClearCache")
            except Exception:
                pass

    # ==================== WAN Measurement Helpers ====================

    def _measure_latency(self, count: int = 3) -> float:
        samples = []
        for host in DEFAULT_PING_HOSTS:
            for _ in range(count):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    t0 = time.perf_counter()
                    s.connect((host, 53))
                    samples.append((time.perf_counter() - t0) * 1000.0)
                    s.close()
                except Exception:
                    continue
            if samples:
                break
        return sum(samples) / len(samples) if samples else 0.0

    def _test_download(self, url: str, duration: int, dp) -> Tuple[float, float]:
        total_bytes = 0
        chunk_size = 64 * 1024
        start_time = time.perf_counter()
        last_update = start_time

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Kodi-SystemTools/1.0"})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                while True:
                    if dp.is_canceled():
                        break
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    now = time.perf_counter()
                    elapsed = now - start_time
                    if now - last_update >= 0.3:
                        last_update = now
                        curr_mbps = (total_bytes * 8.0) / (elapsed * 1_000_000.0)
                        pct = min(68, int(25 + (elapsed / duration) * 43))
                        dp.update(pct, f"Download: {curr_mbps:.2f} Mbps - {total_bytes / 1048576:.1f} MB")
                    if elapsed >= duration:
                        break
        except Exception as e:
            error(f"Download speed test error: {e}")

        elapsed = max(0.001, time.perf_counter() - start_time)
        return (total_bytes * 8.0) / (elapsed * 1_000_000.0), total_bytes / (elapsed * 1_048_576.0)

    def _test_upload(self, url: str, duration: int, dp) -> Tuple[float, float]:
        chunk_size = 32 * 1024
        payload = b"\x00" * chunk_size
        total_bytes = 0
        start_time = time.perf_counter()
        last_update = start_time

        try:
            while True:
                if dp.is_canceled():
                    break
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={"User-Agent": "Kodi-SystemTools/1.0", "Content-Type": "application/octet-stream"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=5.0) as resp:
                        resp.read()
                        total_bytes += chunk_size
                except Exception:
                    break
                now = time.perf_counter()
                elapsed = now - start_time
                if now - last_update >= 0.3:
                    last_update = now
                    curr_mbps = (total_bytes * 8.0) / (elapsed * 1_000_000.0)
                    pct = min(98, int(70 + (elapsed / duration) * 28))
                    dp.update(pct, f"Upload: {curr_mbps:.2f} Mbps")
                if elapsed >= duration:
                    break
        except Exception as e:
            error(f"Upload speed test error: {e}")

        elapsed = max(0.001, time.perf_counter() - start_time)
        return (total_bytes * 8.0) / (elapsed * 1_000_000.0), total_bytes / (elapsed * 1_048_576.0)

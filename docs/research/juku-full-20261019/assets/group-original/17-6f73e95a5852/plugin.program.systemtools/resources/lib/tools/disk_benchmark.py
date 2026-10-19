# -*- coding: utf-8 -*-
"""Tool: Disk Storage Benchmark (Sequential & 4K Random Read/Write with IOPS)."""

import json
import mmap
import os
import platform
import random
import shutil
import subprocess
import time
from typing import Dict, Optional, Tuple

from ..common.kodi_ui import (
    dialog_browse,
    dialog_select,
    dialog_textviewer,
    get_setting_int,
    get_string,
    progress_dialog,
    translate_path,
)
from ..common.logger import debug, error, info
from ..common.os_detect import OSType, SystemInfo
from ..common.system_exec import run_command
from .base_tool import BaseTool, ToolRegistry

BENCH_FILENAME = ".kodi_disk_bench.tmp"
O_BINARY = getattr(os, "O_BINARY", 0)


@ToolRegistry.register
class DiskBenchmarkTool(BaseTool):
    id = "disk_bench"
    title_id = 30003
    description_id = 30026
    icon = "DefaultHardDisk.png"
    order = 30

    def __init__(self) -> None:
        super().__init__()
        self.sys_info = SystemInfo()

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(30003, "Disk Benchmark")
        info("Initiating Disk Benchmark Tool")

        # 1. Choose target path
        target_dir = self._select_target_directory(title)
        if not target_dir:
            return

        # 2. Choose test size
        test_size_mb = self._select_test_size(title)
        if not test_size_mb:
            return

        target_filepath = os.path.join(target_dir, BENCH_FILENAME)
        info(f"Disk Benchmark target: {target_filepath}, size: {test_size_mb} MB")

        # Detect fio binary
        fio_engine = self._get_fio_binary()
        engine_name = f"fio {fio_engine[1]}" if fio_engine else "Python (Direct I/O)"
        info(f"Selected benchmark engine: {engine_name}")

        # Run benchmarks with progress dialog
        seq_write_mbs = 0.0
        seq_read_mbs = 0.0
        rand_write_iops, rand_write_mbs = 0.0, 0.0
        rand_read_iops, rand_read_mbs = 0.0, 0.0
        rand_write_lat_ms = 0.0
        rand_read_lat_ms = 0.0

        try:
            with progress_dialog(title, get_string(30303, "Testing Sequential Write...")) as dp:
                # Pre-flush OS pagecache before benchmark starts
                dp.update(2, get_string(30319, "Flushing OS cache to measure true physical read speed..."))
                self._flush_and_evict_cache(target_filepath)
                if dp.is_canceled():
                    return

                # Step 1: Sequential Write
                dp.update(5, get_string(30303, "Testing Sequential Write..."))
                if fio_engine:
                    cmd_w = [
                        fio_engine[0],
                        "--name=seq_write",
                        f"--filename={target_filepath}",
                        "--ioengine=sync",
                        "--direct=1",
                        "--rw=write",
                        "--bs=1m",
                        f"--size={test_size_mb}m",
                        "--output-format=json",
                    ]
                    out = self._run_fio_cmd(cmd_w, dp, 5, 25, f"Seq Write: {test_size_mb} MB")
                    if dp.is_canceled():
                        return
                    if out:
                        seq_write_mbs, _, _ = self._parse_fio_json(out, "write")
                    else:
                        seq_write_mbs = self._test_sequential_write(target_filepath, test_size_mb, dp)
                else:
                    seq_write_mbs = self._test_sequential_write(target_filepath, test_size_mb, dp)
                if dp.is_canceled():
                    return

                # Flush OS pagecache to eliminate cache inflation before sequential read
                dp.update(28, get_string(30319, "Flushing OS cache to measure true physical read speed..."))
                self._flush_and_evict_cache(target_filepath)
                if dp.is_canceled():
                    return

                # Step 2: Sequential Read
                dp.update(30, get_string(30304, "Testing Sequential Read..."))
                if fio_engine:
                    cmd_r = [
                        fio_engine[0],
                        "--name=seq_read",
                        f"--filename={target_filepath}",
                        "--ioengine=sync",
                        "--direct=1",
                        "--rw=read",
                        "--bs=1m",
                        f"--size={test_size_mb}m",
                        "--output-format=json",
                    ]
                    out = self._run_fio_cmd(cmd_r, dp, 30, 50, f"Seq Read: {test_size_mb} MB")
                    if dp.is_canceled():
                        return
                    if out:
                        seq_read_mbs, _, _ = self._parse_fio_json(out, "read")
                    else:
                        seq_read_mbs = self._test_sequential_read(target_filepath, dp)
                else:
                    seq_read_mbs = self._test_sequential_read(target_filepath, dp)
                if dp.is_canceled():
                    return

                # Step 3: 4K Random Write
                dp.update(55, get_string(30305, "Testing 4K Random Write..."))
                if fio_engine:
                    cmd_rw = [
                        fio_engine[0],
                        "--name=rand_write",
                        f"--filename={target_filepath}",
                        "--ioengine=sync",
                        "--direct=1",
                        "--rw=randwrite",
                        "--bs=4k",
                        f"--size={test_size_mb}m",
                        "--runtime=5",
                        "--time_based",
                        "--output-format=json",
                    ]
                    out = self._run_fio_cmd(cmd_rw, dp, 55, 75, "4K Random Write (5s)")
                    if dp.is_canceled():
                        return
                    if out:
                        rand_write_mbs, rand_write_iops, rand_write_lat_ms = self._parse_fio_json(out, "write")
                    else:
                        rand_write_iops, rand_write_mbs = self._test_4k_random_write(target_filepath, test_size_mb, dp)
                else:
                    rand_write_iops, rand_write_mbs = self._test_4k_random_write(target_filepath, test_size_mb, dp)
                if dp.is_canceled():
                    return

                # Flush OS pagecache to eliminate cache inflation before 4K random read
                dp.update(78, get_string(30319, "Flushing OS cache to measure true physical read speed..."))
                self._flush_and_evict_cache(target_filepath)
                if dp.is_canceled():
                    return

                # Step 4: 4K Random Read
                dp.update(80, get_string(30306, "Testing 4K Random Read..."))
                if fio_engine:
                    cmd_rr = [
                        fio_engine[0],
                        "--name=rand_read",
                        f"--filename={target_filepath}",
                        "--ioengine=sync",
                        "--direct=1",
                        "--rw=randread",
                        "--bs=4k",
                        f"--size={test_size_mb}m",
                        "--runtime=5",
                        "--time_based",
                        "--output-format=json",
                    ]
                    out = self._run_fio_cmd(cmd_rr, dp, 80, 100, "4K Random Read (5s)")
                    if dp.is_canceled():
                        return
                    if out:
                        rand_read_mbs, rand_read_iops, rand_read_lat_ms = self._parse_fio_json(out, "read")
                    else:
                        rand_read_iops, rand_read_mbs = self._test_4k_random_read(target_filepath, test_size_mb, dp)
                else:
                    rand_read_iops, rand_read_mbs = self._test_4k_random_read(target_filepath, test_size_mb, dp)
                if dp.is_canceled():
                    return

                dp.update(100, get_string(30307, "Disk benchmark completed"))

        finally:
            # Always ensure temporary benchmark file is cleaned up
            self._cleanup_temp_file(target_filepath)

        # Show Results Report
        report_lines = [
            f"=== {get_string(30308, 'Benchmark Report')} ===",
            "",
            f"{get_string(30320, 'Engine: %s') % engine_name}",
            f"{get_string(30309, 'Target: %s') % target_dir}",
            f"{get_string(30310, 'Size: %s MB') % test_size_mb}",
            "--------------------------------------------------",
            f"{get_string(30311, 'Sequential Write: %s MB/s') % f'{seq_write_mbs:.2f}'}",
            f"{get_string(30312, 'Sequential Read: %s MB/s') % f'{seq_read_mbs:.2f}'}",
            "--------------------------------------------------",
            f"{get_string(30313, '4K Random Write: %s MB/s (%s IOPS)') % (f'{rand_write_mbs:.2f}', f'{rand_write_iops:.0f}')}",
        ]
        if rand_write_lat_ms > 0:
            report_lines.append(f"{get_string(30321, '4K Write Latency (p95): %s ms') % f'{rand_write_lat_ms:.2f}'}")
        report_lines.append(
            f"{get_string(30314, '4K Random Read: %s MB/s (%s IOPS)') % (f'{rand_read_mbs:.2f}', f'{rand_read_iops:.0f}')}"
        )
        if rand_read_lat_ms > 0:
            report_lines.append(f"{get_string(30322, '4K Read Latency (p95): %s ms') % f'{rand_read_lat_ms:.2f}'}")
        report_lines.append("--------------------------------------------------")

        dialog_textviewer(title, "\n".join(report_lines))

    def _find_bundled_fio(self) -> Optional[str]:
        """Locate the bundled static fio binary for aarch64."""
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        res_dir = os.path.dirname(os.path.dirname(cur_dir))
        bundled = os.path.join(res_dir, "bin", "linux_aarch64", "fio")
        if os.path.isfile(bundled):
            return bundled

        try:
            special_path = translate_path(
                "special://home/addons/plugin.program.systemtools/resources/bin/linux_aarch64/fio"
            )
            if os.path.isfile(special_path):
                return special_path
        except Exception:
            pass
        return None

    def _probe_fio(self, fio_path: str) -> Optional[str]:
        """Verify that the fio binary is executable and returns a valid version."""
        try:
            if not os.path.isfile(fio_path):
                return None
            try:
                os.chmod(fio_path, 0o755)
            except OSError:
                pass
            res = subprocess.run(
                [fio_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3,
            )
            if res.returncode == 0:
                ver = res.stdout.decode("utf-8", errors="ignore").strip()
                if "fio" in ver:
                    return ver
        except Exception as e:
            debug(f"Probing fio at {fio_path} failed: {e}")
        return None

    def _get_fio_binary(self) -> Optional[Tuple[str, str]]:
        """Find working fio executable path and version for supported platforms."""
        if self.sys_info.os_type not in (OSType.COREELEC, OSType.LIBREELEC, OSType.LINUX):
            return None

        candidates = []
        bundled = self._find_bundled_fio()
        if bundled:
            candidates.append(bundled)

        # Entware / opt path
        if os.path.isfile("/opt/bin/fio"):
            candidates.append("/opt/bin/fio")

        # System PATH
        which_fio = shutil.which("fio")
        if which_fio and which_fio not in candidates:
            candidates.append(which_fio)

        for cand in candidates:
            ver = self._probe_fio(cand)
            if ver:
                info(f"Using fio benchmark engine: {cand} ({ver})")
                return cand, ver

        debug("No working fio executable found, falling back to pure Python engine")
        return None

    def _parse_fio_json(self, stdout_text: str, mode: str) -> Tuple[float, float, float]:
        """Parse fio JSON output. Returns (bw_mb, iops, lat_ms)."""
        try:
            data = json.loads(stdout_text)
            jobs = data.get("jobs", [])
            if not jobs:
                return 0.0, 0.0, 0.0
            job = jobs[0]
            section = job.get(mode, {})
            bw_bytes = float(section.get("bw_bytes", 0.0))
            bw_mb = bw_bytes / (1024.0 * 1024.0)
            iops = float(section.get("iops", 0.0))
            lat_ns = float(section.get("clat_ns", {}).get("percentile", {}).get("95.000000", 0.0))
            lat_ms = lat_ns / 1_000_000.0
            return bw_mb, iops, lat_ms
        except Exception as e:
            debug(f"Failed to parse fio JSON: {e}")
            return 0.0, 0.0, 0.0

    def _run_fio_cmd(self, cmd: list, dp, start_pct: int, end_pct: int, label: str) -> Optional[str]:
        """Execute fio command with real-time cancellation check and progress display."""
        t0 = time.perf_counter()
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception as e:
            error(f"Failed to execute fio command: {e}")
            return None

        while proc.poll() is None:
            if dp and dp.is_canceled():
                try:
                    proc.terminate()
                    proc.wait(timeout=1)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                return None
            time.sleep(0.1)
            elapsed = time.perf_counter() - t0
            progress = min(end_pct - 1, start_pct + int(elapsed * 4))
            if dp:
                dp.update(progress, label)

        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            error(f"fio returned error code {proc.returncode}: {stderr}")
            return None
        return stdout

    def _select_target_directory(self, title: str) -> Optional[str]:
        """Ask user to select benchmark target path."""
        home_path = translate_path("special://home/")
        temp_path = translate_path("special://temp/")

        options = [
            get_string(30316, "Kodi Home (%s)") % home_path,
            get_string(30317, "Kodi Temp (%s)") % temp_path,
            get_string(30318, "Browse Custom Directory (USB / SD / External)..."),
        ]

        idx = dialog_select(get_string(30301, "Select storage directory to benchmark"), options)
        if idx == 0:
            return home_path
        elif idx == 1:
            return temp_path
        elif idx == 2:
            custom = dialog_browse(3, get_string(30301, "Select storage directory to benchmark"), "files", "", False, False, home_path)
            if custom and os.path.isdir(custom):
                return custom
        return None

    def _select_test_size(self, title: str) -> Optional[int]:
        """Ask user to select test file size."""
        default_size = get_setting_int("disk_bench_size", 128)
        sizes = [64, 128, 256, 512]
        labels = [f"{s} MB" + (" (Default)" if s == default_size else "") for s in sizes]

        idx = dialog_select(get_string(30302, "Select test file size"), labels)
        if idx >= 0:
            return sizes[idx]
        return None

    def _test_sequential_write(self, filepath: str, size_mb: int, dp) -> float:
        """Write test file sequentially in 1MB chunks with direct I/O (matching FIO standard)."""
        block_size = 1024 * 1024  # 1 MB
        total_blocks = size_mb
        random_bytes = bytearray(os.urandom(block_size))

        buf = None
        use_direct = False
        if hasattr(os, "O_DIRECT") and hasattr(mmap, "mmap"):
            try:
                buf = mmap.mmap(-1, block_size)
                buf.write(random_bytes)
                fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_DIRECT | O_BINARY)
                use_direct = True
            except OSError:
                if buf:
                    buf.close()
                    buf = None
                use_direct = False

        if not use_direct:
            fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | O_BINARY)

        write_buf = buf if use_direct else random_bytes
        t0 = time.perf_counter()
        blocks_written = 0
        try:
            for i in range(total_blocks):
                if dp.is_canceled():
                    break
                write_buf[0] = i & 0xFF
                write_buf[1] = (i >> 8) & 0xFF
                write_buf[2] = (i >> 16) & 0xFF
                write_buf[3] = (i >> 24) & 0xFF
                os.write(fd, write_buf)
                blocks_written += 1
                if (i + 1) % 4 == 0:
                    pct = 5 + int(((i + 1) / total_blocks) * 20)
                    dp.update(pct, f"Seq Write: {i + 1}/{total_blocks} MB")
            os.fsync(fd)
        finally:
            os.close(fd)
            if buf:
                buf.close()

        # Ensure filesystem metadata and dirty blocks are committed
        if hasattr(os, "sync"):
            try:
                os.sync()
            except Exception:
                pass
        else:
            run_command("sync")

        elapsed = max(0.001, time.perf_counter() - t0)
        return (blocks_written * block_size / (1024 * 1024)) / elapsed

    def _test_sequential_read(self, filepath: str, dp) -> float:
        """Read test file sequentially in 1MB chunks with kernel readahead hint."""
        block_size = 1024 * 1024
        file_size = os.path.getsize(filepath)
        size_mb = file_size / (1024 * 1024)

        t0 = time.perf_counter()
        fd = os.open(filepath, os.O_RDONLY | O_BINARY)
        if hasattr(os, "posix_fadvise") and hasattr(os, "POSIX_FADV_SEQUENTIAL"):
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_SEQUENTIAL)
            except Exception:
                pass

        bytes_read = 0
        try:
            while bytes_read < file_size:
                if dp.is_canceled():
                    break
                data = os.read(fd, block_size)
                if not data:
                    break
                bytes_read += len(data)
                del data
                pct = 30 + int((bytes_read / file_size) * 20)
                dp.update(pct, f"Seq Read: {bytes_read / (1024 * 1024):.1f}/{size_mb:.1f} MB")
        finally:
            os.close(fd)

        elapsed = max(0.001, time.perf_counter() - t0)
        return (bytes_read / (1024 * 1024)) / elapsed

    def _test_4k_random_write(self, filepath: str, size_mb: int, dp, ops: int = 500) -> Tuple[float, float]:
        """Perform 4KB random writes matching FIO direct=1 standard (Q1T1)."""
        block_size = 4096
        total_blocks = (size_mb * 1024 * 1024) // block_size
        if total_blocks < 1:
            return 0.0, 0.0

        random_data = os.urandom(block_size)
        buf = None
        use_direct = False
        use_fdatasync = False

        if hasattr(os, "O_DIRECT") and hasattr(mmap, "mmap"):
            try:
                buf = mmap.mmap(-1, block_size)
                buf.write(random_data)
                fd = os.open(filepath, os.O_RDWR | os.O_DIRECT | O_BINARY)
                use_direct = True
            except OSError:
                if buf:
                    buf.close()
                    buf = None
                use_direct = False

        if not use_direct:
            flags = os.O_RDWR | O_BINARY
            if hasattr(os, "O_DSYNC"):
                flags |= os.O_DSYNC
            elif hasattr(os, "O_SYNC"):
                flags |= os.O_SYNC
            else:
                use_fdatasync = True
            try:
                fd = os.open(filepath, flags)
            except OSError:
                fd = os.open(filepath, os.O_RDWR | O_BINARY)
                use_fdatasync = True

        write_buf = buf if use_direct else random_data
        t0 = time.perf_counter()
        performed = 0
        sync_fn = getattr(os, "fdatasync", getattr(os, "fsync", None))
        try:
            for i in range(ops):
                if dp.is_canceled():
                    break
                offset = random.randint(0, total_blocks - 1) * block_size
                os.lseek(fd, offset, os.SEEK_SET)
                os.write(fd, write_buf)
                if use_fdatasync and sync_fn:
                    sync_fn(fd)
                performed += 1
                if (i + 1) % 25 == 0:
                    pct = 55 + int(((i + 1) / ops) * 20)
                    dp.update(pct, f"4K Random Write: {i + 1}/{ops} ops")
                # Adaptive time bound for slow media (e.g. cheap USB flash drive / SD card)
                if performed >= 100 and (time.perf_counter() - t0) >= 3.0:
                    break
            os.fsync(fd)
        finally:
            os.close(fd)
            if buf:
                buf.close()

        elapsed = max(0.001, time.perf_counter() - t0)
        iops = performed / elapsed
        mbs = (performed * block_size / (1024 * 1024)) / elapsed
        return iops, mbs

    def _test_4k_random_read(self, filepath: str, size_mb: int, dp, ops: int = 500) -> Tuple[float, float]:
        """Perform 4KB random reads matching FIO direct=1 standard (Q1T1)."""
        block_size = 4096
        total_blocks = (size_mb * 1024 * 1024) // block_size
        if total_blocks < 1:
            return 0.0, 0.0

        buf = None
        use_direct = False

        if hasattr(os, "O_DIRECT") and hasattr(mmap, "mmap") and hasattr(os, "readv"):
            try:
                buf = mmap.mmap(-1, block_size)
                fd = os.open(filepath, os.O_RDONLY | os.O_DIRECT | O_BINARY)
                use_direct = True
            except OSError:
                if buf:
                    buf.close()
                    buf = None
                use_direct = False

        if not use_direct:
            fd = os.open(filepath, os.O_RDONLY | O_BINARY)
            if hasattr(os, "posix_fadvise") and hasattr(os, "POSIX_FADV_RANDOM"):
                try:
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
                except Exception:
                    pass

        t0 = time.perf_counter()
        performed = 0
        try:
            for i in range(ops):
                if dp.is_canceled():
                    break
                offset = random.randint(0, total_blocks - 1) * block_size
                os.lseek(fd, offset, os.SEEK_SET)
                if use_direct:
                    n = os.readv(fd, [buf])
                    if n <= 0:
                        break
                else:
                    data = os.read(fd, block_size)
                    if not data:
                        break
                    del data
                performed += 1
                if (i + 1) % 25 == 0:
                    pct = 80 + int(((i + 1) / ops) * 20)
                    dp.update(pct, f"4K Random Read: {i + 1}/{ops} ops")
                # Adaptive time bound for slow media
                if performed >= 100 and (time.perf_counter() - t0) >= 3.0:
                    break
        finally:
            os.close(fd)
            if buf:
                buf.close()

        elapsed = max(0.001, time.perf_counter() - t0)
        iops = performed / elapsed
        mbs = (performed * block_size / (1024 * 1024)) / elapsed
        return iops, mbs

    def _flush_and_evict_cache(self, filepath: str) -> None:
        """Purge OS PageCache and file blocks to ensure raw hardware read speed."""
        # 1. Sync dirty blocks to physical storage
        if hasattr(os, "sync"):
            try:
                os.sync()
            except Exception:
                run_command("sync")
        else:
            run_command("sync")

        # 2. Tell kernel to drop cached pages of this test file
        if hasattr(os, "posix_fadvise") and hasattr(os, "POSIX_FADV_DONTNEED") and os.path.exists(filepath):
            try:
                fd = os.open(filepath, os.O_RDONLY | O_BINARY)
                try:
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                finally:
                    os.close(fd)
            except Exception as e:
                debug(f"posix_fadvise failed: {e}")

        # 3. Drop system-wide pagecache, dentries and inodes
        drop_path = "/proc/sys/vm/drop_caches"
        if os.path.exists(drop_path):
            try:
                with open(drop_path, "w") as f:
                    f.write("3\n")
                debug("Purged kernel drop_caches=3 for disk benchmark")
            except Exception:
                run_command("sysctl -w vm.drop_caches=3")
                run_command("sh -c 'echo 3 > /proc/sys/vm/drop_caches'")

        time.sleep(0.1)

    def _cleanup_temp_file(self, filepath: str) -> None:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                debug(f"Cleaned up benchmark temp file: {filepath}")
        except Exception as e:
            error(f"Failed to remove benchmark file {filepath}: {e}")

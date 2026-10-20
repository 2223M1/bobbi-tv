# -*- coding: utf-8 -*-
"""Tool: Kodi Performance and Rendering Optimizer.

Optimizes SQLite databases and advancedsettings.xml specifically engineered
for large media libraries (tens of thousands of titles) and Mali GPU hardware:
1. SQLite WAL Mode: Configures PRAGMA journal_mode=WAL and synchronous=NORMAL
   across all media databases to enable non-blocking concurrent reads and writes.
2. AdvancedSettings Tuning:
   - Disables asynchronous texture uploads (<asynctextureupload>false</asynctextureupload>)
     to eliminate multithreaded EGL context contention and blocking glFinish() calls.
   - Disables runtime minified mipmap generation (<minifiedmipmapping>false</minifiedmipmapping>)
     to prevent expensive glGenerateMipmap() calls on the main render thread.
   - Enforces cost-reduction dirty region tracking (<algorithmdirtyregions>2</algorithmdirtyregions>)
     to avoid full-viewport redraws when scrolling posters.
   - Caps thumbnail cache resolution (<imageres>540</imageres>, <fanartres>720</fanartres>)
     to conserve RAM and GPU VRAM.
"""

import glob
import os
import shutil
import sqlite3
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from ..common.kodi_ui import (
    dialog_ok,
    dialog_select,
    dialog_textviewer,
    dialog_yesno,
    get_string,
    progress_dialog,
    show_notification,
    translate_path,
)
from ..common.logger import debug, error, info
from ..common.system_exec import run_command
from .base_tool import BaseTool, ToolRegistry

try:
    import xbmc
    _HAS_XBMC = True
except ImportError:
    _HAS_XBMC = False
    xbmc = None

DEFAULT_CE_USERDATA = "/storage/.kodi/userdata"


def get_default_userdata_dir() -> str:
    """Detect the active Kodi userdata path."""
    if os.path.isdir(DEFAULT_CE_USERDATA):
        return DEFAULT_CE_USERDATA
    try:
        translated = translate_path("special://userdata/")
        if os.path.isdir(translated):
            return translated
    except Exception:
        pass
    return DEFAULT_CE_USERDATA


def update_xml_element(parent: ET.Element, tag: str, text: str) -> None:
    """Helper to update or create a child element with specified text."""
    elem = parent.find(tag)
    if elem is None:
        elem = ET.SubElement(parent, tag)
    elem.text = text


def get_database_files(db_dir: str) -> List[str]:
    """Find all SQLite database files in the Database directory."""
    if not os.path.isdir(db_dir):
        return []
    db_files = glob.glob(os.path.join(db_dir, "*.db"))
    return sorted([f for f in db_files if not f.endswith(".bak")])


def format_size(num_bytes: int) -> str:
    """Format bytes into human-readable string (B, KB, MB, GB)."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


CUSTOM_INDEXES = [
    (
        "files",
        "idx_files_unwatched_recent",
        "CREATE INDEX IF NOT EXISTS idx_files_unwatched_recent ON files (playCount, dateAdded DESC);",
    ),
    (
        "bookmark",
        "idx_bookmark_resume",
        "CREATE INDEX IF NOT EXISTS idx_bookmark_resume ON bookmark (type, timeInSeconds, idFile);",
    ),
    (
        "videoversion",
        "idx_vv_lookup",
        "CREATE INDEX IF NOT EXISTS idx_vv_lookup ON videoversion (idMedia, media_type, itemType, idFile);",
    ),
]

DROP_INDEXES = [
    "idx_art_covering",
    "idx_files_unwatched_recent",
    "idx_bookmark_resume",
    "idx_vv_lookup",
]


def apply_custom_indexes(conn: sqlite3.Connection) -> int:
    """Create high-performance composite indexes if tables exist."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = {row[0] for row in cur.fetchall()}
    created_count = 0

    # Ensure negative-optimization/bloated indexes are cleaned up
    try:
        cur.execute("DROP INDEX IF EXISTS idx_art_covering;")
    except Exception:
        pass

    for table, idx_name, idx_sql in CUSTOM_INDEXES:
        if table in existing_tables:
            try:
                cur.execute(idx_sql)
                created_count += 1
                debug(f"Ensured index {idx_name} on table {table}")
            except Exception as e:
                error(f"Failed to create index {idx_name}: {e}")
    return created_count


def drop_custom_indexes(conn: sqlite3.Connection) -> int:
    """Drop custom performance indexes if they exist (lossless revert)."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
    existing_indexes = {row[0] for row in cur.fetchall()}
    dropped_count = 0

    for idx_name in DROP_INDEXES:
        if idx_name in existing_indexes:
            try:
                cur.execute(f"DROP INDEX IF EXISTS {idx_name};")
                dropped_count += 1
                info(f"Dropped custom index: {idx_name}")
            except Exception as e:
                error(f"Failed to drop index {idx_name}: {e}")
    return dropped_count


def backup_file(file_path: str) -> str:
    """Create a backup copy with .bak extension if not already existing.

    If the original file does not exist, a sentinel (.not_exist) is created
    to record that the file was absent before optimization.
    """
    bak_path = f"{file_path}.bak"
    not_exist_marker = f"{file_path}.not_exist"

    if os.path.exists(file_path):
        if not os.path.exists(bak_path):
            try:
                # Flush WAL data to database file before copying to ensure backup is complete
                if file_path.endswith(".db"):
                    try:
                        conn = sqlite3.connect(file_path, timeout=5.0, isolation_level=None)
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                        conn.close()
                    except Exception as ex:
                        debug(f"Pre-backup checkpoint for {file_path} skipped: {ex}")

                shutil.copy2(file_path, bak_path)
                info(f"Created backup: {bak_path}")
            except Exception as e:
                error(f"Failed to backup {file_path}: {e}")
        if os.path.exists(not_exist_marker):
            try:
                os.remove(not_exist_marker)
            except Exception:
                pass
    else:
        if not os.path.exists(bak_path) and not os.path.exists(not_exist_marker):
            try:
                with open(not_exist_marker, "w", encoding="utf-8") as f:
                    f.write("")
                info(f"Recorded pre-optimization absent state: {not_exist_marker}")
            except Exception as e:
                error(f"Failed to write marker {not_exist_marker}: {e}")

    return bak_path


@ToolRegistry.register
class KodiOptimizerTool(BaseTool):
    id = "kodi_optimizer"
    title_id = 30900
    description_id = 30901
    icon = "DefaultAddonProgram.png"
    order = 16

    def __init__(self, userdata_path: Optional[str] = None):
        self.userdata_path = userdata_path if userdata_path else get_default_userdata_dir()

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(30900, "Kodi Performance Optimizer")
        info(f"Kodi Optimizer invoked on userdata: {self.userdata_path}")

        # Auto-clean any legacy negative-optimization items from previous versions
        cleaned_xml, cleaned_idxs = self.clean_legacy_optimizations()
        if cleaned_xml > 0 or cleaned_idxs > 0:
            info(f"Auto-cleaned legacy items: {cleaned_xml} XML tags, {cleaned_idxs} indexes")

        options = [
            f"1. {get_string(30902, 'Apply All Performance Optimizations')}",
            f"2. {get_string(30930, 'Flush Database WALs (Fast Slimming, No Reboot)')}",
            f"3. {get_string(30903, 'View Current Optimization Status')}",
            f"4. {get_string(30935, 'Revert Custom Indexes (Lossless, Keeps Watch History)')}",
            f"5. {get_string(30904, 'Restore Configurations from Backup (.bak)')}",
        ]

        idx = dialog_select(title, options)
        if idx == 0:
            self._action_apply_optimizations(title)
        elif idx == 1:
            self._action_flush_wal(title)
        elif idx == 2:
            self._action_view_status(title)
        elif idx == 3:
            self._action_revert_indexes(title)
        elif idx == 4:
            self._action_restore_backups(title)

    def _action_revert_indexes(self, title: str) -> None:
        confirm_msg = get_string(
            30937,
            "Are you sure you want to revert all custom indexes? Your library data will remain intact.",
        )
        if not dialog_yesno(title, confirm_msg):
            return

        db_count, dropped_count = self.revert_custom_indexes()
        if dropped_count == 0:
            show_notification(title, get_string(30939, "No custom indexes found to revert."))
        else:
            msg = get_string(30936, "Reverted %d custom indexes across %d databases.") % (dropped_count, db_count)
            show_notification(title, msg)

    def _action_flush_wal(self, title: str) -> None:
        try:
            with progress_dialog(title, get_string(30932, "Flushing database WAL logs...") % "") as dp:
                count, freed = self.flush_wal_databases(dp)
            freed_fmt = format_size(freed)
            msg = get_string(30931, "Flushed %d databases successfully (%s freed).") % (count, freed_fmt)
            show_notification(title, msg)
        except Exception as e:
            error(f"WAL flush failed: {e}")
            dialog_ok(title, f"WAL flush failed: {e}")

    def _action_apply_optimizations(self, title: str) -> None:
        # Prompt user for thumbnail resolution preset
        preset_title = get_string(30921, "Select Thumbnail Quality Preset")
        presets = [
            get_string(30922, "1080p Full HD (Recommended, 1:1 pixel crisp, 720p/1080p)"),
            get_string(30923, "Low VRAM Saver (Fast, for low RAM or huge libraries, 540p/720p)"),
            get_string(30924, "4K Ultra HD (For 4GB RAM devices and 4K UI skins, 1080p/2160p)"),
        ]
        p_idx = dialog_select(preset_title, presets)
        if p_idx < 0:
            return

        if p_idx == 0:
            imageres, fanartres = 720, 1080
        elif p_idx == 1:
            imageres, fanartres = 540, 720
        else:
            imageres, fanartres = 1080, 2160

        os.makedirs(self.userdata_path, exist_ok=True)
        db_dir = os.path.join(self.userdata_path, "Database")
        os.makedirs(db_dir, exist_ok=True)

        try:
            with progress_dialog(title, get_string(30905, "Optimizing SQLite databases...")) as dp:
                # 1. Optimize SQLite databases
                dp.update(10, get_string(30905, "Optimizing SQLite databases..."))
                db_count = self.optimize_databases(dp)

                # 2. Optimize advancedsettings.xml with chosen quality preset
                dp.update(70, get_string(30906, "Optimizing advancedsettings.xml..."))
                self.optimize_advancedsettings(imageres=imageres, fanartres=fanartres)

                dp.update(100, get_string(30926, "Performance optimization completed!"))
                time.sleep(0.5)

            msg = get_string(
                30907,
                "Optimizations applied successfully! Restart Kodi/system to take effect. Reboot now?",
            )
            if dialog_yesno(title, msg):
                self._do_restart()

        except Exception as e:
            error(f"Optimization failed: {e}")
            dialog_ok(title, f"Optimization failed: {e}")

    def _action_view_status(self, title: str) -> None:
        report_text = self.get_status_report()
        dialog_textviewer(get_string(30911, "Optimization Status Report"), report_text)

    def _action_restore_backups(self, title: str) -> None:
        confirm_msg = get_string(
            30919,
            "Are you sure you want to restore all databases and settings from .bak backups?",
        )
        if not dialog_yesno(title, confirm_msg):
            return

        restored_count = self.restore_backups()
        if restored_count == 0:
            dialog_ok(title, get_string(30909, "No backup (.bak) files found to restore."))
            return

        show_notification(title, get_string(30920, "Restored %d files successfully.") % restored_count)
        reboot_msg = get_string(
            30910,
            "Backups restored successfully! Restart Kodi to apply. Reboot now?",
        )
        if dialog_yesno(title, reboot_msg):
            self._do_restart()

    def flush_wal_databases(self, dp=None) -> Tuple[int, int]:
        """Execute PRAGMA wal_checkpoint(TRUNCATE) on all media databases to flush WAL to disk."""
        db_dir = os.path.join(self.userdata_path, "Database")
        db_files = get_database_files(db_dir)

        if not db_files:
            info(f"No SQLite database files found in {db_dir}")
            return 0, 0

        total = len(db_files)
        total_freed = 0
        processed_count = 0

        for i, db_path in enumerate(db_files):
            if dp and dp.is_canceled():
                break

            db_name = os.path.basename(db_path)
            wal_path = f"{db_path}-wal"
            wal_size_before = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

            if dp:
                pct = int((i / max(1, total)) * 100)
                dp.update(pct, get_string(30932, "Flushing %s WAL logs...") % db_name)

            try:
                conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
                cur = conn.cursor()
                cur.execute("PRAGMA busy_timeout = 5000;")
                res = cur.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
                if res and res[0] == 1:
                    cur.execute("PRAGMA wal_checkpoint(PASSIVE);")
                cur.execute("PRAGMA optimize;")
                conn.close()

                wal_size_after = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
                freed = max(0, wal_size_before - wal_size_after)
                total_freed += freed
                processed_count += 1
                info(f"Flushed WAL for {db_name}: freed {freed} bytes (before: {wal_size_before}, after: {wal_size_after})")
            except Exception as e:
                error(f"Failed to flush WAL for {db_name}: {e}")

        return processed_count, total_freed

    def optimize_databases(self, dp=None) -> int:
        """Apply WAL mode, 4K page_size, custom covering indexes, VACUUM, and ANALYZE."""
        db_dir = os.path.join(self.userdata_path, "Database")
        db_files = get_database_files(db_dir)

        if not db_files:
            info(f"No SQLite database files found in {db_dir}")
            return 0

        total = len(db_files)
        info(f"Optimizing {total} SQLite databases in {db_dir}...")

        for i, db_path in enumerate(db_files):
            if dp and dp.is_canceled():
                break

            db_name = os.path.basename(db_path)
            backup_file(db_path)

            if dp:
                pct = int(10 + (i / max(1, total)) * 55)
                dp.update(pct, get_string(30934, "Optimizing %s (Covering indexes, Vacuum & Analyze)...") % db_name)

            try:
                conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
                cur = conn.cursor()
                cur.execute("PRAGMA busy_timeout = 5000;")

                # Align page_size to 4096 if older database has 1024 or 2048.
                # In SQLite, page_size cannot be altered while in WAL mode, so we
                # ensure DELETE mode first if a page_size change is required.
                vacuum_already_done = False
                cur.execute("PRAGMA page_size;")
                res_ps = cur.fetchone()
                if res_ps and res_ps[0] != 4096:
                    try:
                        disk_stat = shutil.disk_usage(os.path.dirname(db_path))
                        db_size = os.path.getsize(db_path)
                        if disk_stat.free >= db_size * 1.5:
                            cur.execute("PRAGMA journal_mode = DELETE;")
                            cur.execute("PRAGMA page_size = 4096;")
                            cur.execute("VACUUM;")
                            vacuum_already_done = True
                            info(f"Aligned page_size to 4096 via VACUUM for {db_name}")
                        else:
                            info(f"Skipped page_size realignment for {db_name}: low free space")
                    except Exception as ex:
                        debug(f"Page size realignment failed for {db_name}: {ex}")

                cur.execute("PRAGMA journal_mode = WAL;")
                cur.execute("PRAGMA synchronous = NORMAL;")

                # Apply custom composite and covering indexes
                apply_custom_indexes(conn)

                # VACUUM safely with disk space pre-check if not already run during page_size change
                if not vacuum_already_done:
                    try:
                        disk_stat = shutil.disk_usage(os.path.dirname(db_path))
                        db_size = os.path.getsize(db_path)
                        if disk_stat.free >= db_size * 1.5:
                            cur.execute("VACUUM;")
                            info(f"VACUUM completed for {db_name}")
                        else:
                            info(f"Skipped VACUUM for {db_name}: disk free ({disk_stat.free}) < 1.5x DB size ({db_size})")
                    except Exception as ex:
                        debug(f"VACUUM check/execution failed for {db_name}: {ex}")

                # Update query planner cost statistics
                cur.execute("ANALYZE;")

                # Flush WAL logs
                cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
                info(f"Optimized {db_name}: WAL mode, covering indexes, VACUUM & ANALYZE completed")
            except Exception as e:
                error(f"Failed to optimize {db_name}: {e}")

        return total

    def revert_custom_indexes(self) -> Tuple[int, int]:
        """Remove custom indexes across all media databases without restoring .bak files.

        Returns (databases_processed, total_indexes_dropped).
        """
        db_dir = os.path.join(self.userdata_path, "Database")
        db_files = get_database_files(db_dir)
        if not db_files:
            return 0, 0

        total_dropped = 0
        db_count = 0

        for db_path in db_files:
            try:
                conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
                dropped = drop_custom_indexes(conn)
                conn.execute("PRAGMA optimize;")
                conn.close()
                if dropped > 0:
                    total_dropped += dropped
                    db_count += 1
            except Exception as e:
                error(f"Failed to revert custom indexes on {os.path.basename(db_path)}: {e}")

        return db_count, total_dropped

    def clean_legacy_optimizations(self) -> Tuple[int, int]:
        """Clean up ineffective/phantom XML tags and negative-optimization indexes from prior versions.

        Returns (cleaned_xml_tags_count, dropped_indexes_count).
        """
        cleaned_xml = 0
        dropped_indexes = 0

        # 1. Clean up legacy XML items in advancedsettings.xml
        as_path = os.path.join(self.userdata_path, "advancedsettings.xml")
        if os.path.exists(as_path):
            try:
                tree = ET.parse(as_path)
                root = tree.getroot()
                xml_changed = False

                # Remove unsupported <blurayisocache>
                iso_elem = root.find("blurayisocache")
                if iso_elem is not None:
                    root.remove(iso_elem)
                    cleaned_xml += 1
                    xml_changed = True

                # Remove invalid <cache_size> and local <connecttimeout> under <videodatabase>
                vdb = root.find("videodatabase")
                if vdb is not None:
                    cs = vdb.find("cache_size")
                    if cs is not None:
                        vdb.remove(cs)
                        cleaned_xml += 1
                        xml_changed = True
                    ct = vdb.find("connecttimeout")
                    if ct is not None and vdb.find("host") is None:
                        vdb.remove(ct)
                        cleaned_xml += 1
                        xml_changed = True
                    if len(vdb) == 0:
                        root.remove(vdb)
                        xml_changed = True

                # Clean up local empty database timeout nodes if no remote host
                for db_tag in ["musicdatabase", "tvdatabase", "epgdatabase"]:
                    elem = root.find(db_tag)
                    if elem is not None and elem.find("host") is None:
                        ct = elem.find("connecttimeout")
                        if ct is not None:
                            elem.remove(ct)
                            cleaned_xml += 1
                            xml_changed = True
                        if len(elem) == 0:
                            root.remove(elem)
                            xml_changed = True

                if xml_changed:
                    backup_file(as_path)
                    try:
                        ET.indent(root, space="  ", level=0)
                    except AttributeError:
                        pass
                    tree.write(as_path, encoding="utf-8", xml_declaration=True)
                    info(f"Cleaned {cleaned_xml} legacy/invalid XML items from advancedsettings.xml")
            except Exception as e:
                error(f"Failed to clean legacy XML settings: {e}")

        # 2. Clean up legacy negative-optimization indexes (idx_art_covering) across all DBs
        db_dir = os.path.join(self.userdata_path, "Database")
        db_files = get_database_files(db_dir)
        for db_path in db_files:
            try:
                conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_art_covering';")
                if cur.fetchone():
                    cur.execute("DROP INDEX IF EXISTS idx_art_covering;")
                    cur.execute("PRAGMA optimize;")
                    dropped_indexes += 1
                    info(f"Cleaned deprecated index idx_art_covering from {os.path.basename(db_path)}")
                conn.close()
            except Exception as e:
                error(f"Failed to clean legacy indexes on {os.path.basename(db_path)}: {e}")

        return cleaned_xml, dropped_indexes

    def optimize_advancedsettings(self, imageres: int = 720, fanartres: int = 1080) -> None:
        """Safely merge Mali GPU and SQLite cache optimizations into advancedsettings.xml."""
        as_path = os.path.join(self.userdata_path, "advancedsettings.xml")
        backup_file(as_path)

        root = None
        if os.path.exists(as_path):
            try:
                tree = ET.parse(as_path)
                root = tree.getroot()
            except Exception as e:
                debug(f"Parsing existing advancedsettings.xml failed ({e}), creating fresh root.")
                root = None

        if root is None or root.tag != "advancedsettings":
            root = ET.Element("advancedsettings")

        # 1. Update <gui> section
        gui_elem = root.find("gui")
        if gui_elem is None:
            gui_elem = ET.SubElement(root, "gui")

        # Disable async texture upload to eliminate multithreaded EGL context contention and driver stalls
        update_xml_element(gui_elem, "asynctextureupload", "false")
        # Disable runtime minified mipmapping to eliminate main-thread glGenerateMipmap() calls
        update_xml_element(gui_elem, "minifiedmipmapping", "false")
        # Enforce dirty region solver algorithm 2: COST_REDUCTION (partial updates)
        update_xml_element(gui_elem, "algorithmdirtyregions", "2")
        update_xml_element(gui_elem, "bufferagepartialredraw", "1")
        update_xml_element(gui_elem, "maxdirtyregions", "4")
        # Cap thumbnail cache sizes to save memory while preserving crisp 1080p UI resolution
        update_xml_element(gui_elem, "imageres", str(imageres))
        update_xml_element(gui_elem, "fanartres", str(fanartres))

        # 2. Clean up phantom / ineffective XML sections if present
        # Clean up <videodatabase><cache_size> or empty <videodatabase> (Kodi hardcodes SQLite cache to 4096; ignores XML cache_size)
        vdb_elem = root.find("videodatabase")
        if vdb_elem is not None:
            elem_cache = vdb_elem.find("cache_size")
            if elem_cache is not None:
                vdb_elem.remove(elem_cache)
            elem_to = vdb_elem.find("connecttimeout")
            # If videodatabase only had connecttimeout and/or cache_size without remote host, remove them for local SQLite
            if elem_to is not None and vdb_elem.find("host") is None:
                vdb_elem.remove(elem_to)
            if len(vdb_elem) == 0:
                root.remove(vdb_elem)

        # Clean up non-existent <blurayisocache> section (unsupported by Kodi)
        iso_elem = root.find("blurayisocache")
        if iso_elem is not None:
            root.remove(iso_elem)

        # Format XML nicely with indentation
        try:
            ET.indent(root, space="  ", level=0)
        except AttributeError:
            pass

        out_tree = ET.ElementTree(root)
        out_tree.write(as_path, encoding="utf-8", xml_declaration=True)
        info(f"Optimized advancedsettings.xml written to {as_path}")

    def get_status_report(self) -> str:
        """Generate formatted diagnostic report of databases and settings."""
        lines = [f"=== {get_string(30911, 'Optimization Status Report')} ===", ""]

        db_dir = os.path.join(self.userdata_path, "Database")
        db_files = get_database_files(db_dir)

        opt_str = get_string(30912, "Optimal (WAL)")
        def_str = get_string(30913, "Default (Lock-Prone)")
        not_set_str = get_string(30917, "Not set")

        lines.append(f"[1] {get_string(30914, 'Databases (%d detected):') % len(db_files)}")
        for db_path in db_files:
            name = os.path.basename(db_path)
            wal_path = f"{db_path}-wal"
            try:
                db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
                wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

                conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode;")
                j_mode = cur.fetchone()[0]
                cur.execute("PRAGMA synchronous;")
                sync_val = cur.fetchone()[0]

                cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
                existing_idxs = {row[0] for row in cur.fetchall()}
                has_custom = any(idx_name in existing_idxs for _, idx_name, _ in CUSTOM_INDEXES)
                has_legacy = "idx_art_covering" in existing_idxs
                idx_tag = f" [{get_string(30938, 'Indexes: Active')}]" if has_custom else ""
                if has_legacy:
                    idx_tag += " [Legacy idx_art_covering (Cleanup Recommended)]"

                cur.execute("PRAGMA freelist_count;")
                res_free = cur.fetchone()
                freelist = res_free[0] if res_free else 0
                free_str = f" | free={freelist}" if freelist > 0 else ""

                conn.close()

                sync_desc = {0: "OFF", 1: "NORMAL", 2: "FULL", 3: "EXTRA"}.get(sync_val, str(sync_val))
                if j_mode.upper() != "WAL":
                    tag = f"[{def_str}]"
                elif wal_size > 16 * 1024 * 1024:
                    tag = f"[{get_string(30933, 'WAL Backlog (Slimming Recommended)')}]"
                else:
                    tag = f"[{opt_str}]"

                db_sz = format_size(db_size)
                wal_sz = format_size(wal_size)
                lines.append(
                    f"  * {name:<20}: DB: {db_sz:<8} | WAL: {wal_sz:<8}{free_str} | "
                    f"journal={j_mode:<5} sync={sync_desc:<7} {tag}{idx_tag}".rstrip()
                )
            except Exception as e:
                lines.append(f"  * {name:<20}: [Error: {e}]")

        lines.append("")
        as_path = os.path.join(self.userdata_path, "advancedsettings.xml")
        lines.append(f"[2] {get_string(30915, 'Rendering & Cache Settings (%s):') % 'advancedsettings.xml'}")

        if not os.path.exists(as_path):
            lines.append(f"  * {get_string(30916, 'File does not exist (using Kodi hardcoded defaults).')}")
        else:
            try:
                tree = ET.parse(as_path)
                root = tree.getroot()
                gui = root.find("gui")
                if gui is not None:
                    async_up = gui.findtext("asynctextureupload", not_set_str)
                    min_mip = gui.findtext("minifiedmipmapping", not_set_str)
                    dirty = gui.findtext("algorithmdirtyregions", not_set_str)
                    imageres = gui.findtext("imageres", not_set_str)
                    fanartres = gui.findtext("fanartres", not_set_str)

                    lines.append(f"  * asynctextureupload    : {async_up:<10} ({get_string(30918, 'Optimal')}: false)")
                    lines.append(f"  * minifiedmipmapping    : {min_mip:<10} ({get_string(30918, 'Optimal')}: false)")
                    lines.append(f"  * algorithmdirtyregions : {dirty:<10} ({get_string(30918, 'Optimal')}: 2)")
                    lines.append(f"  * imageres / fanartres  : {imageres} / {fanartres} ({get_string(30918, 'Optimal')}: 720 / 1080)")

                # Check if any legacy phantom tags exist
                legacy_tags = []
                vdb = root.find("videodatabase")
                if vdb is not None and vdb.find("cache_size") is not None:
                    legacy_tags.append("<cache_size>")
                if root.find("blurayisocache") is not None:
                    legacy_tags.append("<blurayisocache>")
                if legacy_tags:
                    lines.append(f"  * [Notice: Old invalid settings detected: {', '.join(legacy_tags)}. Re-apply optimization to clean.]")
            except Exception as e:
                lines.append(f"  * [Parse Error: {e}]")

        return "\n".join(lines)

    def restore_backups(self) -> int:
        """Restore all databases and advancedsettings.xml from backups."""
        db_dir = os.path.join(self.userdata_path, "Database")
        bak_files = glob.glob(os.path.join(db_dir, "*.db.bak"))

        as_path = os.path.join(self.userdata_path, "advancedsettings.xml")
        as_bak = f"{as_path}.bak"
        as_not_exist = f"{as_path}.not_exist"

        if os.path.exists(as_bak):
            bak_files.append(as_bak)

        if not bak_files and not os.path.exists(as_not_exist):
            return 0

        restored = 0
        for bak in bak_files:
            orig = bak[:-4]
            try:
                # If restoring an SQLite database, remove any orphaned WAL/SHM files
                # to prevent database corruption (mismatched WAL header/salt)
                if orig.endswith(".db"):
                    for extra in [f"{orig}-wal", f"{orig}-shm"]:
                        if os.path.exists(extra):
                            try:
                                os.remove(extra)
                                info(f"Removed orphaned WAL/SHM file: {extra}")
                            except Exception as ex:
                                error(f"Failed to remove orphaned file {extra}: {ex}")

                shutil.copy2(bak, orig)
                info(f"Restored: {orig} from {bak}")
                restored += 1
            except Exception as e:
                error(f"Failed to restore {orig}: {e}")

        # Restore files that were absent prior to optimization
        if os.path.exists(as_not_exist):
            try:
                if os.path.exists(as_path):
                    os.remove(as_path)
                    info(f"Removed {as_path} to restore pre-optimization absent state")
                    restored += 1
                os.remove(as_not_exist)
            except Exception as e:
                error(f"Failed to restore absent state for {as_path}: {e}")

        return restored

    def _do_restart(self) -> None:
        """Restart Kodi or reboot system."""
        run_command("sync")
        if _HAS_XBMC and xbmc:
            try:
                xbmc.restart()
                return
            except Exception:
                pass
        run_command("reboot -f")

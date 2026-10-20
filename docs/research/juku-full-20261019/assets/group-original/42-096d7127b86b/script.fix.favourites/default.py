# -*- coding: utf-8 -*-

import os
import re
import shutil
import glob
import sys
import zipfile
import tempfile
import time
import subprocess
import traceback
import urllib.parse
import xml.etree.ElementTree as ET
import xml.dom.minidom
import fcntl
import atexit
import xbmc
import xbmcvfs
import xbmcgui
import xbmcaddon
from datetime import datetime

LOCK_FILE = '/tmp/script.system_maintenance.lock'
_lock_fd = None

def acquire_single_instance():
    global _lock_fd
    try:
        _lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        atexit.register(lambda: _lock_fd and _lock_fd.close())
    except (IOError, OSError):
        xbmcgui.Dialog().ok("提示", "系统维护工具已在运行中，请勿重复打开")
        sys.exit(0)

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')
ICON_PATH = os.path.join(ADDON_PATH, 'icon.png')

USERDATA_DIR = xbmcvfs.translatePath("special://userdata/")
FAVOURITES_FILE = os.path.join(USERDATA_DIR, "favourites.xml")
SOURCES_FILE = os.path.join(USERDATA_DIR, "sources.xml")

UPDATE_DIR = "/storage/.update"
RESTORE_DIR = "/storage/.restore"

def log(msg):
    xbmc.log("[系统维护工具] " + msg, level=xbmc.LOGINFO)

def show_notification(msg, duration=3000):
    xbmcgui.Dialog().notification("系统维护工具", msg, ICON_PATH, duration)

def get_clean_rules():
    enable_name = ADDON.getSettingBool('enable_name_clean')
    prefixes = []
    suffixes = []
    if enable_name:
        p = ADDON.getSetting('prefixes')
        s = ADDON.getSetting('suffixes')
        prefixes = [line.strip() for line in p.splitlines() if line.strip()]
        suffixes = [line.strip() for line in s.splitlines() if line.strip()]
    return prefixes, suffixes

def clean_name(name, prefixes, suffixes):
    if not name:
        return name
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name

def clean_old_backups(keep=3):
    backup_pattern = FAVOURITES_FILE + ".backup_*"
    backup_files = glob.glob(backup_pattern)
    if len(backup_files) <= keep:
        return
    backup_files.sort()
    for f in backup_files[:-keep]:
        try:
            os.remove(f)
        except:
            pass

def pretty_print_xml(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        dom = xml.dom.minidom.parseString(content)
        pretty = dom.toprettyxml(indent="  ")
        lines = [line for line in pretty.splitlines() if line.strip()]
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    except Exception as e:
        log("美化XML失败: " + str(e))
        return False

def build_preview(root, prefixes, suffixes, enable_path_fix):
    name_changes = []
    path_changes = []
    for fav in root.findall("favourite"):
        old_name = fav.get("name", "")
        new_name = clean_name(old_name, prefixes, suffixes)
        if new_name != old_name:
            name_changes.append((old_name, new_name))
        if enable_path_fix:
            text = fav.text
            if text and text.startswith("ActivateWindow"):
                match = re.search(r'ActivateWindow\(\d+,\s*"([^"]+)"', text)
                if match:
                    old_path = match.group(1)
                    if not old_path.endswith("/all.xml/"):
                        new_path = old_path.rstrip('/') + "/all.xml/"
                        path_changes.append((old_path, new_path))
    return name_changes, path_changes

def apply_changes(root, prefixes, suffixes, enable_path_fix):
    name_count = 0
    path_count = 0
    for fav in root.findall("favourite"):
        old_name = fav.get("name", "")
        new_name = clean_name(old_name, prefixes, suffixes)
        if new_name != old_name:
            fav.set("name", new_name)
            name_count += 1
        if enable_path_fix:
            text = fav.text
            if text and text.startswith("ActivateWindow"):
                match = re.search(r'ActivateWindow\(\d+,\s*"([^"]+)"', text)
                if match:
                    old_path = match.group(1)
                    if not old_path.endswith("/all.xml/"):
                        new_path = old_path.rstrip('/') + "/all.xml/"
                        new_text = text.replace(f'"{old_path}"', f'"{new_path}"')
                        fav.text = new_text
                        path_count += 1
    return name_count, path_count

def fix_favourites():
    if not xbmcvfs.exists(FAVOURITES_FILE):
        show_notification("favourites.xml 不存在", 3000)
        return
    prefixes, suffixes = get_clean_rules()
    enable_path_fix = ADDON.getSettingBool('enable_path_fix')
    try:
        tree = ET.parse(FAVOURITES_FILE)
        root = tree.getroot()
    except:
        show_notification("XML解析失败", 3000)
        return
    name_changes, path_changes = build_preview(root, prefixes, suffixes, enable_path_fix)
    total = len(name_changes) + len(path_changes)
    if total == 0:
        show_notification("没有需要修改的条目", 3000)
        return
    msg = "即将执行以下修改（共 " + str(total) + " 项）：\n\n"
    if name_changes:
        msg += "【名称修改】\n"
        for old, new in name_changes:
            msg += old + "  →  " + new + "\n"
        msg += "\n"
    if path_changes:
        msg += "【路径修改】\n"
        for old, new in path_changes:
            msg += old + "  →  " + new + "\n"
    msg += "\n确认执行吗？"
    if not xbmcgui.Dialog().yesno("系统维护工具 - 预览修改", msg):
        show_notification("已取消修改", 2000)
        return
    backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(FAVOURITES_FILE, backup_path)
        clean_old_backups()
    except:
        show_notification("备份失败，操作取消", 3000)
        return
    name_count, path_count = apply_changes(root, prefixes, suffixes, enable_path_fix)
    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        stats_msg = f"修复路径 {path_count} 个，清理名称 {name_count} 个"
        ask_apply_restart_refresh("收藏夹修复完成", stats_msg)
    except:
        show_notification("写入失败，请检查权限", 3000)

def get_addon_list():
    addons = []
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    addons_dir = os.path.dirname(current_dir)
    special_home = xbmcvfs.translatePath("special://home/")
    special_xbmc = xbmcvfs.translatePath("special://xbmc/")
    candidate_dirs = [addons_dir]
    if os.path.exists(os.path.join(special_home, "addons")):
        candidate_dirs.append(os.path.join(special_home, "addons"))
    if os.path.exists(os.path.join(special_xbmc, "addons")):
        candidate_dirs.append(os.path.join(special_xbmc, "addons"))
    scanned = set()
    for real_path in candidate_dirs:
        if not os.path.exists(real_path):
            continue
        try:
            items = os.listdir(real_path)
            for item in items:
                addon_xml = os.path.join(real_path, item, "addon.xml")
                if not os.path.exists(addon_xml):
                    continue
                try:
                    tree = ET.parse(addon_xml)
                    root = tree.getroot()
                    addon_id = root.get('id', item)
                    if addon_id in scanned:
                        continue
                    scanned.add(addon_id)
                    version = root.get('version', '')
                    name_attr = root.get('name', '')
                    if name_attr:
                        name = name_attr
                    else:
                        name_elem = root.find('extension[@point="xbmc.addon.metadata"]/summary')
                        if name_elem is not None and name_elem.text:
                            name = name_elem.text
                        else:
                            name = addon_id
                    addons.append((addon_id, name, version, os.path.join(real_path, item)))
                except:
                    pass
        except:
            pass
    addons.sort(key=lambda x: x[1].lower())
    return addons

def pack_addon():
    addons = get_addon_list()
    if not addons:
        show_notification("未找到任何已安装插件", 3000)
        return
    dialog = xbmcgui.Dialog()
    items = [f"{name} ({addon_id})" for addon_id, name, version, path in addons]
    selection = dialog.select("选择要打包的插件", items)
    if selection < 0:
        show_notification("已取消选择", 2000)
        return
    selected_id, selected_name, selected_version, selected_path = addons[selection]
    save_dir = dialog.browse(3, "选择保存备份的目录", "files", "", False, True, "")
    if not save_dir:
        show_notification("未选择目录，已取消", 2000)
        return
    if not save_dir.endswith('/'):
        save_dir += '/'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    safe_name = re.sub(r'[\\/*?:"<>|]', '', selected_name).strip()
    if not safe_name or safe_name == selected_id:
        prefix = selected_id
    else:
        prefix = f"{safe_name}_{selected_id}"
    
    if selected_version:
        zip_filename = f"{prefix}_{selected_version}_{timestamp}.zip"
    else:
        zip_filename = f"{prefix}_{timestamp}.zip"
    
    local_temp = tempfile.mkstemp(suffix=".zip")[1]

    file_list = []
    root_len = len(selected_path) + 1
    for dirpath, dirnames, filenames in os.walk(selected_path):
        if '__pycache__' in dirpath:
            continue
        for fname in filenames:
            if fname.endswith('.pyc') or fname.endswith('.pyo'):
                continue
            full_path = os.path.join(dirpath, fname)
            arcname = os.path.join(selected_id, full_path[root_len:])
            file_list.append((full_path, arcname))
    total_files = len(file_list)
    if total_files == 0:
        show_notification("插件目录为空，无法打包", 3000)
        try:
            os.remove(local_temp)
        except:
            pass
        return
    dp = xbmcgui.DialogProgress()
    dp.create("打包插件备份", "正在压缩文件...")
    dp.update(0, "0/" + str(total_files))
    try:
        with zipfile.ZipFile(local_temp, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for idx, (full_path, arcname) in enumerate(file_list, 1):
                if dp.iscanceled():
                    if xbmcgui.Dialog().yesno("确认取消", "确定要取消打包插件吗？"):
                        show_notification("打包已取消", 2000)
                        dp.close()
                        try:
                            os.remove(local_temp)
                        except:
                            pass
                        return
                    else:
                        continue
                with open(full_path, 'rb') as f:
                    zipf.writestr(arcname, f.read())
                if idx % 10 == 0 or idx == total_files:
                    dp.update(int(idx * 100 / total_files), f"{idx}/{total_files}")
                    xbmc.sleep(10)
    except Exception as e:
        show_notification("压缩异常: " + str(e), 3000)
        dp.close()
        try:
            os.remove(local_temp)
        except:
            pass
        return
    dp.update(0, "正在复制到目标目录...")
    dest_path = save_dir + zip_filename
    try:
        if xbmcvfs.copy(local_temp, dest_path):
            dp.update(100, "复制完成")
            dp.close()
            show_notification("打包成功: " + dest_path, 4000)
        else:
            dp.close()
            show_notification("复制失败，请检查权限", 3000)
    except Exception as e:
        dp.close()
        show_notification("复制异常: " + str(e), 3000)
    finally:
        try:
            os.remove(local_temp)
        except:
            pass

def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes:.0f} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024*1024):.1f} MB"
    else:
        return f"{size_bytes / (1024*1024*1024):.2f} GB"

def copy_file_with_progress(src_path, dst_path, title):
    dialog = xbmcgui.Dialog()
    progress = xbmcgui.DialogProgress()
    progress.create(title, "正在复制文件，请稍候...")
    progress.update(0)

    try:
        try:
            stat = xbmcvfs.Stat(src_path)
            total_size = stat.st_size()
        except:
            total_size = 0

        src_file = xbmcvfs.File(src_path, 'rb')
        if not src_file:
            dialog.ok("错误", "无法打开源文件")
            progress.close()
            return False

        dst_file = xbmcvfs.File(dst_path, 'wb')
        if not dst_file:
            src_file.close()
            dialog.ok("错误", "无法创建目标文件")
            progress.close()
            return False

        chunk_size = 1024 * 1024
        copied = 0
        last_update = 0
        update_interval = 10 * 1024 * 1024

        start_time = time.time()
        last_time = start_time
        last_copied = 0
        total_size_str = format_size(total_size) if total_size > 0 else "未知"

        while not progress.iscanceled():
            chunk = src_file.readBytes(chunk_size)
            if not chunk:
                break
            dst_file.write(chunk)
            copied += len(chunk)

            now = time.time()
            if copied - last_update >= update_interval or not chunk:
                last_update = copied
                elapsed = now - last_time
                if elapsed > 0 and copied > last_copied:
                    speed = (copied - last_copied) / elapsed
                    if speed > 1024 * 1024:
                        speed_str = f"{speed / (1024*1024):.1f} MB/s"
                    elif speed > 1024:
                        speed_str = f"{speed / 1024:.1f} KB/s"
                    else:
                        speed_str = f"{speed:.0f} B/s"
                else:
                    speed_str = "计算中..."

                last_time = now
                last_copied = copied

                copied_str = format_size(copied)
                if total_size > 0:
                    percent = int(copied * 100 / total_size)
                    progress.update(percent,
                        f"大小：{total_size_str} / 已完成：{copied_str}  速度：{speed_str}")
                else:
                    progress.update(0,
                        f"已完成：{copied_str}  速度：{speed_str}")

        src_file.close()
        dst_file.close()

        if progress.iscanceled():
            if xbmcvfs.exists(dst_path):
                xbmcvfs.delete(dst_path)
            show_notification("复制已取消", 2000)
            return False

        progress.update(100, "复制完成")
        progress.close()
        return True

    except Exception as e:
        progress.close()
        try:
            with open('/storage/copy_error.log', 'w', encoding='utf-8') as f:
                f.write(traceback.format_exc())
        except:
            with open('/storage/copy_error.log', 'w') as f:
                f.write(repr(e))
        dialog.ok("错误", "复制文件失败，请查看 /storage/copy_error.log 获取详细信息。")
        if xbmcvfs.exists(dst_path):
            xbmcvfs.delete(dst_path)
        return False

def reboot_system():
    subprocess.run(["sync"])
    subprocess.run(["reboot", "-f"])

def reboot_to_android():
    candidates = [
        "/usr/sbin/rebootfromand",
        "/usr/sbin/rebootfromnand",
        "rebootfromand",
        "rebootfromnand"
    ]
    cmd = None
    for c in candidates:
        if os.path.exists(c) or (not c.startswith("/") and subprocess.run(["which", c], capture_output=True).returncode == 0):
            cmd = c
            break
    if cmd is None:
        cmd = "rebootfromand"
    subprocess.run(["sync"])
    try:
        subprocess.run([cmd], check=True)
    except Exception as e:
        xbmcgui.Dialog().ok("错误", f"执行 {cmd} 失败:\n{str(e)}\n请手动执行 {cmd} 测试。")
        return
    xbmc.sleep(500)
    subprocess.run(["reboot", "-f"])

def restart_kodi():
    dialog = xbmcgui.Dialog()
    if dialog.yesno("确认", "确定要结束 Kodi 进程吗？\n系统将自动重启 Kodi 界面。"):
        subprocess.run(["pkill", "-f", "kodi.bin"], check=False)
        xbmc.executebuiltin('Quit')

def ask_apply_restart_refresh(operation_desc, stats_msg=""):
    dialog = xbmcgui.Dialog()
    msg = operation_desc
    if stats_msg:
        msg += "\n" + stats_msg
    options = ["重启Kodi（推荐）", "稍后手动重启"]
    ret = dialog.select(msg, options)
    if ret == 0:
        xbmc.log("[系统维护工具] 用户选择重启Kodi", xbmc.LOGINFO)
        xbmc.executebuiltin('RestartApp')
    elif ret == 1:
        show_notification("请手动重启Kodi以使更改生效", 3000)

def ask_restart():
    ask_apply_restart_refresh("操作完成")

def copy_tar_with_progress(src_path, dst_dir, title, success_msg):
    if not src_path.lower().endswith('.tar'):
        xbmcgui.Dialog().ok("提示", "请选择 .tar 格式的文件")
        return False

    try:
        os.makedirs(dst_dir, exist_ok=True)
    except Exception as e:
        try:
            with open('/storage/copy_error.log', 'w', encoding='utf-8') as f:
                f.write(traceback.format_exc())
        except:
            pass
        xbmcgui.Dialog().ok("错误", "无法创建目标目录，请查看 /storage/copy_error.log")
        return False

    dest_path = os.path.join(dst_dir, os.path.basename(src_path))

    if not copy_file_with_progress(src_path, dest_path, title):
        return False

    if xbmcgui.Dialog().yesno("完成", success_msg + "\n是否立即重启系统？"):
        reboot_system()
    return True

def handle_tar_update():
    dialog = xbmcgui.Dialog()
    file_path = dialog.browse(1, "请选择系统更新包 (.tar 文件)", "files", ".tar|.TAR")
    if not file_path:
        show_notification("未选择文件，已取消", 2000)
        return
    copy_tar_with_progress(file_path, UPDATE_DIR, "复制更新包", "更新包已复制到更新目录。")

def handle_backup_restore():
    dialog = xbmcgui.Dialog()
    file_path = dialog.browse(1, "请选择备份 tar 文件", "files", ".tar|.TAR")
    if not file_path:
        show_notification("未选择文件，已取消", 2000)
        return

    if not file_path.lower().endswith('.tar'):
        dialog.ok("提示", "请选择 .tar 格式的备份文件")
        return

    if not xbmcvfs.exists(file_path):
        dialog.ok("错误", "所选文件不存在或无法访问")
        return

    try:
        stat = xbmcvfs.Stat(file_path)
        if stat.st_size() == 0:
            dialog.ok("错误", "备份文件大小为0，可能已损坏")
            return
    except:
        pass

    try:
        os.makedirs(RESTORE_DIR, exist_ok=True)
    except Exception as e:
        dialog.ok("错误", f"无法创建恢复目录 {RESTORE_DIR}:\n{str(e)}")
        return

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dest_filename = f"{timestamp}.tar"
    dest_path = os.path.join(RESTORE_DIR, dest_filename)

    if xbmcvfs.exists(dest_path):
        if not dialog.yesno("文件已存在", f"恢复目录中已有同名文件 {dest_filename}，是否覆盖？"):
            return

    if not copy_file_with_progress(file_path, dest_path, "复制备份文件"):
        return

    if dialog.yesno("复制完成，恢复文件准备就绪", 
                    f"重启系统后将自动检测并执行恢复。\n"
                    "恢复过程时间取决于文件大小和硬件读写能力。\n\n"
                    "是否立即重启？"):
        reboot_system()
    else:
        dialog.ok("提示", "请重启系统以执行恢复。")

# ================= 备份数据功能 =================
def handle_backup_data():
    dialog = xbmcgui.Dialog()
    target_dir = dialog.browse(3, "请选择备份目标目录", "files")
    if not target_dir:
        show_notification("未选择目录，已取消", 2000)
        return

    test_file = os.path.join(target_dir, ".write_test")
    try:
        f = xbmcvfs.File(test_file, 'w')
        if not f:
            dialog.ok("错误", "目标目录不可写，请选择其他目录。")
            return
        f.write("test")
        f.close()
        xbmcvfs.delete(test_file)
    except:
        dialog.ok("错误", "目标目录不可写，请选择其他目录。")
        return

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"backup_{timestamp}.tar"
    backup_path = os.path.join(target_dir, backup_name)

    log("自动检测 /storage 下的挂载点...")
    mount_excludes = []
    mount_points = []
    try:
        result = subprocess.run(['mount'], capture_output=True, encoding='utf-8', errors='ignore')
        output = result.stdout
        log("mount 原始输出:\n" + output)
        lines = output.splitlines()
        for line in lines:
            parts = line.split()
            if len(parts) >= 3 and parts[1] == 'on':
                mp = parts[2]
                if mp.startswith('/storage/') and mp != '/storage':
                    mp = mp.strip()
                    if mp:
                        mount_excludes.append(mp)
                        mount_points.append(mp)
                        log(f"将排除挂载点: {mp}")
        if not mount_excludes:
            log("未发现 /storage 下的挂载点")
    except Exception as e:
        log("检测挂载点失败: " + str(e))

    if mount_points:
        exclude_msg = "已自动排除以下挂载点：\n" + "\n".join(mount_points)
    else:
        exclude_msg = "未发现挂载点。"

    if not dialog.yesno("确认备份", 
                        f"将备份 /storage 目录到：\n{backup_path}\n"
                        f"备份文件可能较大，请确保目标空间充足。\n"
                        f"{exclude_msg}\n"
                        "建议执行备份前卸载挂载避免执行备份发生错误，确定要继续吗？"):
        show_notification("已取消备份", 2000)
        return

    temp_tar = "/storage/backup_temp.tar"
    if os.path.exists(temp_tar):
        try:
            os.remove(temp_tar)
        except:
            pass

    total_size = 0
    du_cmd = ['du', '-x', '-sb', '/storage']
    log("执行 du 命令: " + " ".join(du_cmd))
    try:
        result = subprocess.run(du_cmd, capture_output=True, encoding='utf-8', errors='ignore')
        log("du stdout: " + result.stdout.strip())
        log("du stderr: " + result.stderr.strip())
        log("du returncode: " + str(result.returncode))
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if parts:
                total_size = int(parts[0])
                log("成功获取总大小: " + str(total_size))
            else:
                log("du 输出为空，无法解析")
        else:
            log("du 返回非零，尝试使用 df 备用方案")
            try:
                df_result = subprocess.run(['df', '-k', '/storage'], capture_output=True, encoding='utf-8', errors='ignore')
                if df_result.returncode == 0:
                    lines = df_result.stdout.strip().splitlines()
                    if len(lines) >= 2:
                        parts = lines[1].split()
                        if len(parts) >= 2:
                            total_kb = int(parts[1])
                            total_size = total_kb * 1024
                            log("使用 df 获取总大小: " + str(total_size))
                        else:
                            log("df 输出列数不足")
                    else:
                        log("df 输出行数不足")
                else:
                    log("df 返回非零")
            except Exception as df_e:
                log("df 备用方案失败: " + str(df_e))
    except Exception as e:
        log("du 命令执行异常: " + str(e))
        try:
            df_result = subprocess.run(['df', '-k', '/storage'], capture_output=True, encoding='utf-8', errors='ignore')
            if df_result.returncode == 0:
                lines = df_result.stdout.strip().splitlines()
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        total_kb = int(parts[1])
                        total_size = total_kb * 1024
                        log("异常后使用 df 获取总大小: " + str(total_size))
        except:
            pass

    if total_size == 0:
        log("警告：未能获取总大小，进度条将只显示运行时间")

    exclude_file = None
    try:
        fd, exclude_file = tempfile.mkstemp(suffix=".exclude", text=True)
        os.close(fd)
        with open(exclude_file, 'w', encoding='utf-8') as f:
            for mp in mount_excludes:
                rel_path = mp.lstrip('/')
                f.write(rel_path + "\n")
        log("排除文件创建成功，内容:")
        with open(exclude_file, 'r', encoding='utf-8') as f:
            log(f.read().strip())
    except Exception as e:
        log("排除文件创建失败: " + str(e))
        if exclude_file and os.path.exists(exclude_file):
            os.remove(exclude_file)
        exclude_file = None

    progress = xbmcgui.DialogProgress()
    progress.create("备份系统", "正在打包数据，请稍候...")
    progress.update(0)

    try:
        exclude_dirs = [
            "--exclude=/storage/.cache",
            "--exclude=/storage/.kodi/temp",
            "--exclude=/storage/.kodi/userdata/Thumbnails",
        ]
        cmd = ['tar', '-cf', temp_tar] + exclude_dirs
        if exclude_file:
            cmd.extend(['--exclude-from', exclude_file])
        else:
            for mp in mount_excludes:
                cmd.extend(['--exclude', mp.lstrip('/')])
        cmd.extend(['-C', '/', 'storage'])
        log("执行 tar 命令: " + " ".join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        start_time = time.time()
        step = 0
        while process.poll() is None:
            if progress.iscanceled():
                if xbmcgui.Dialog().yesno("确认取消", "确定要取消当前备份吗？\n已打包的数据将被删除。"):
                    process.terminate()
                    process.wait()
                    progress.close()
                    show_notification("备份已取消", 2000)
                    if os.path.exists(temp_tar):
                        os.remove(temp_tar)
                    if exclude_file and os.path.exists(exclude_file):
                        os.remove(exclude_file)
                    return
                else:
                    continue
            elapsed = int(time.time() - start_time)
            current_size = 0
            if os.path.exists(temp_tar):
                try:
                    current_size = os.path.getsize(temp_tar)
                except:
                    pass

            if total_size > 0:
                percent = int(current_size * 100 / total_size)
                if percent > 100:
                    percent = 100
                total_str = format_size(total_size)
                current_str = format_size(current_size)
                progress.update(percent, f"大小：{total_str} / 已完成：{current_str}  已运行 {elapsed} 秒")
            else:
                step = (step + 10) % 100
                progress.update(step, f"正在打包数据，请稍候... (已运行 {elapsed} 秒)")
            time.sleep(0.5)
        progress.update(100, "打包完成")
        if process.returncode != 0:
            stderr_output = process.stderr.read().decode('utf-8', errors='ignore')
            log("tar stderr: " + stderr_output)
            if "excluded" in stderr_output.lower() or "file changed" in stderr_output.lower() or stderr_output.strip() == "":
                log("tar 产生非致命警告，忽略")
            else:
                raise Exception(f"tar 返回非零: {process.returncode}, 错误信息: {stderr_output}")

    except Exception as e:
        log("打包异常: " + traceback.format_exc())
        progress.close()
        dialog.ok("错误", f"打包失败，请查看日志获取详细信息。\n错误: {str(e)}")
        if os.path.exists(temp_tar):
            os.remove(temp_tar)
        if exclude_file and os.path.exists(exclude_file):
            os.remove(exclude_file)
        return

    progress.close()
    if exclude_file and os.path.exists(exclude_file):
        os.remove(exclude_file)

    if not copy_file_with_progress(temp_tar, backup_path, "复制备份文件到目标位置"):
        dialog.ok("错误", "复制备份文件到目标目录失败，请检查目标空间。")
        if os.path.exists(temp_tar):
            os.remove(temp_tar)
        return

    if os.path.exists(temp_tar):
        try:
            os.remove(temp_tar)
        except:
            pass

    if dialog.yesno("完成", f"备份已成功保存到：\n{backup_path}\n\n是否立即重启系统？"):
        reboot_system()

# ================= 新增：获取网卡握手速率 =================
def get_network_speed():
    """
    获取当前活动网卡的协商速率（有线 ethtool，无线 iw）
    返回一个字符串，描述网卡名和速率
    """
    try:
        # 1. 获取默认路由对应的网卡
        route = subprocess.check_output(['ip', 'route'], encoding='utf-8', errors='ignore')
        iface = None
        for line in route.splitlines():
            if 'default' in line:
                parts = line.split()
                if len(parts) >= 5:
                    iface = parts[4]  # 通常默认路由的 dev 在第5个字段
                break
        if not iface:
            # 备用：从 /proc/net/route 读取
            try:
                with open('/proc/net/route', 'r') as f:
                    for line in f:
                        if line.strip() and not line.startswith('Iface'):
                            parts = line.split()
                            if parts[1] == '00000000':  # 默认路由
                                iface = parts[0]
                                break
            except:
                pass
        if not iface:
            return "无法识别活动网卡"

        # 2. 尝试 ethtool（有线）
        try:
            output = subprocess.check_output(['ethtool', iface], encoding='utf-8', errors='ignore')
            for line in output.splitlines():
                if 'Speed:' in line:
                    speed = line.split(':')[1].strip()
                    return f"{iface} (有线) 协商速率: {speed}"
        except:
            pass

        # 3. 尝试 iw（无线）
        try:
            output = subprocess.check_output(['iw', 'dev', iface, 'link'], encoding='utf-8', errors='ignore')
            for line in output.splitlines():
                if 'tx bitrate:' in line:
                    speed = line.split(':')[1].strip()
                    return f"{iface} (无线) 发送速率: {speed}"
        except:
            pass

        # 4. 尝试 /sys/class/net 备用
        speed_file = f"/sys/class/net/{iface}/speed"
        if os.path.exists(speed_file):
            with open(speed_file, 'r') as f:
                speed = f.read().strip()
                return f"{iface} 速率: {speed} Mb/s"

        return f"{iface} 速率获取失败，请手动检查"
    except Exception as e:
        return f"获取网卡速率失败: {e}"

def handle_speed_test():
    speed_info = get_network_speed()
    dialog = xbmcgui.Dialog()
    mode_list = ["云盘挂载/内网共享 (SMB/NFS/本地)", "从文本文件读取链接测速 (如 .strm)"]
    mode = dialog.select("请选择测速模式\n" + speed_info, mode_list)
    if mode < 0:
        return

    progress = xbmcgui.DialogProgress()
    target_size = 1024 * 1024 * 1024  
    chunk_size = 256 * 1024          

    if mode == 0:
        file_path = dialog.browse(1, "请选择内网共享中的大文件（用于测速）", "files", "", False, False, "")
        if not file_path:
            show_notification("未选择文件，已取消", 2000)
            return
        
        progress.create("云盘挂载/内网共享 (SMB/NFS)", "正在读取文件，请稍候...")
        progress.update(0)
        
        try:
            stat = xbmcvfs.Stat(file_path)
            total_size = stat.st_size()
            if total_size <= 0:
                dialog.ok("错误", "无法获取文件大小或文件为空")
                progress.close()
                return
            
            read_limit = min(total_size, target_size)
            f = xbmcvfs.File(file_path, 'rb')
            if not f:
                dialog.ok("错误", "无法打开文件，请检查共享是否可访问")
                progress.close()
                return
            
            downloaded = 0
            start_time = time.time()
            last_update_time = start_time
            last_update_downloaded = 0
            max_speed = 0
            min_speed = None
            
            while downloaded < read_limit:
                if progress.iscanceled():
                    break
                remaining = read_limit - downloaded
                current_chunk = min(chunk_size, remaining)
                chunk = f.readBytes(current_chunk)
                if not chunk:
                    break
                
                downloaded += len(chunk)
                now = time.time()
                time_diff = now - last_update_time
                
                if time_diff >= 0.5:
                    speed = (downloaded - last_update_downloaded) / time_diff
                    if speed > max_speed:
                        max_speed = speed
                    if min_speed is None or speed < min_speed:
                        min_speed = speed
                    avg_speed = downloaded / (now - start_time) if (now - start_time) > 0 else 0
                    
                    percent = int(downloaded * 100 / read_limit)
                    progress.update(percent,
                        f"已读取：{downloaded/(1024*1024):.1f} MB / {read_limit/(1024*1024):.1f} MB\n"
                        f"当前速度：{speed/(1024*1024):.2f} MB/s\n"
                        f"平均速度：{avg_speed/(1024*1024):.2f} MB/s")
                    last_update_time = now
                    last_update_downloaded = downloaded
            
            f.close()
            progress.close()
            
            if progress.iscanceled():
                show_notification("测速已取消", 2000)
                return
            
            elapsed = time.time() - start_time
            if elapsed == 0: elapsed = 0.001
            avg_speed = downloaded / elapsed
            if max_speed == 0: max_speed = avg_speed
            if min_speed is None: min_speed = avg_speed
            
            msg = (f"测速模式：云盘挂载/内网共享 (SMB/NFS)\n"
                   f"文件大小：{total_size/(1024*1024):.2f} MB\n"
                   f"实际测速：{downloaded/(1024*1024):.2f} MB\n"
                   f"总耗时：{elapsed:.2f} 秒\n"
                   f"平均速度：{avg_speed/(1024*1024):.2f} MB/s\n"
                   f"最高速度：{max_speed/(1024*1024):.2f} MB/s\n"
                   f"最低速度：{min_speed/(1024*1024):.2f} MB/s\n"
                   f"延迟：N/A (本地读取)")
            dialog.ok("内网测速结果", msg)
            
        except Exception as e:
            progress.close()
            dialog.ok("错误", f"内网测速失败：{str(e)}")
            show_notification("测速失败", 3000)

    else:
        file_path = dialog.browse(1, "请选择包含下载链接的文本文件 (.strm/.txt 等)", "files", ".strm|.txt|.url")
        if not file_path:
            show_notification("未选择文件，已取消", 2000)
            return
        
        url = None
        try:
            with xbmcvfs.File(file_path, 'r') as f:
                content = f.read()
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                if line and (line.startswith('http://') or line.startswith('https://')):
                    url = line
                    break
        except Exception as e:
            dialog.ok("错误", f"读取文件失败：{str(e)}")
            return
        
        if not url:
            dialog.ok("错误", "未能从文件中提取到有效的 HTTP/HTTPS 链接。")
            return
        
        if not dialog.yesno("确认链接", f"将使用以下链接进行测速：\n{url}\n\n是否继续？"):
            show_notification("已取消测速", 2000)
            return
        
        progress.create("直连测速 (HTTP)", "正在连接...")
        progress.update(0)
        
        import urllib.request
        try:
            start_request_time = time.time()
            req = urllib.request.urlopen(url, timeout=60)
            first_byte_time = None
            
            content_length = req.headers.get('Content-Length')
            total_size = int(content_length) if content_length else target_size
            read_limit = min(total_size, target_size)
            
            downloaded = 0
            start_time = time.time()
            last_update_time = start_time
            last_update_downloaded = 0
            max_speed = 0
            min_speed = None
            first_chunk = True
            
            while downloaded < read_limit:
                if progress.iscanceled():
                    break
                chunk = req.read(chunk_size)
                if not chunk:
                    break
                downloaded += len(chunk)
                
                if first_chunk:
                    first_byte_time = time.time()
                    first_chunk = False
                
                now = time.time()
                time_diff = now - last_update_time
                if time_diff >= 0.5:
                    speed = (downloaded - last_update_downloaded) / time_diff
                    if speed > max_speed:
                        max_speed = speed
                    if min_speed is None or speed < min_speed:
                        min_speed = speed
                    avg_speed = downloaded / (now - start_time) if (now - start_time) > 0 else 0
                    
                    percent = int(downloaded * 100 / read_limit)
                    progress.update(percent,
                        f"已下载：{downloaded/(1024*1024):.1f} MB / {read_limit/(1024*1024):.1f} MB\n"
                        f"当前速度：{speed/(1024*1024):.2f} MB/s\n"
                        f"平均速度：{avg_speed/(1024*1024):.2f} MB/s")
                    last_update_time = now
                    last_update_downloaded = downloaded
            
            req.close()
            progress.close()
            
            if progress.iscanceled():
                show_notification("测速已取消", 2000)
                return
            
            elapsed = time.time() - start_time
            if elapsed == 0: elapsed = 0.001
            avg_speed = downloaded / elapsed
            if max_speed == 0: max_speed = avg_speed
            if min_speed is None: min_speed = avg_speed
            
            if first_byte_time:
                latency = (first_byte_time - start_request_time) * 1000
            else:
                latency = -1
            
            msg = (f"测速模式：直连 (HTTP)\n"
                   f"实际测速：{downloaded/(1024*1024):.2f} MB\n"
                   f"总耗时：{elapsed:.2f} 秒\n"
                   f"平均速度：{avg_speed/(1024*1024):.2f} MB/s\n"
                   f"最高速度：{max_speed/(1024*1024):.2f} MB/s\n"
                   f"最低速度：{min_speed/(1024*1024):.2f} MB/s\n"
                   f"延迟：{latency:.0f} ms" if latency >= 0 else "延迟：无法测量")
            dialog.ok("测速结果", msg)
            
        except Exception as e:
            progress.close()
            dialog.ok("错误", f"测速失败：{str(e)}\n请检查链接是否有效")
            show_notification("测速失败", 3000)

def add_mounts_to_favourites():
    """
    从系统挂载表中读取 /storage 下的挂载点（如 U 盘、移动硬盘、NFS/SMB 挂载），
    排除系统内部目录，并添加为收藏夹条目，便于快速访问。
    信任 mount 输出，不再使用 xbmcvfs.exists 检查（因为 fuse 挂载可能返回 False）。
    """
    dialog = xbmcgui.Dialog()
    
    try:
        result = subprocess.run(['mount'], capture_output=True, encoding='utf-8', errors='ignore')
        lines = result.stdout.splitlines()
    except Exception as e:
        dialog.ok("错误", f"执行 mount 命令失败：{str(e)}")
        return

    log("mount 输出行数: " + str(len(lines)))
    for line in lines:
        log("mount line: " + line)

    mount_points = []
    exclude_dirs = [
        '/storage/.kodi',
        '/storage/.cache',
        '/storage/.config',
        '/storage/.ash_history',
        '/storage/.profile',
        '/storage/.ssh',
        '/storage/temp',
        '/storage/backup_temp.tar'
    ]
    
    for line in lines:
        mp = None
        if ' on /storage/' in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == 'on' and i+1 < len(parts) and parts[i+1].startswith('/storage/'):
                    mp = parts[i+1]
                    break
        if mp is None:
            parts = line.split()
            for part in parts:
                if part.startswith('/storage/') and part != '/storage':
                    mp = part
                    break
        if mp is None:
            match = re.search(r'(/storage/[^\s]+)', line)
            if match:
                mp = match.group(1)
        
        if mp is None:
            continue
        
        if mp == '/storage':
            continue
        should_exclude = False
        for ex in exclude_dirs:
            if mp.startswith(ex) or mp == ex:
                should_exclude = True
                break
        if should_exclude:
            continue
        
        mount_points.append(mp)
        log("添加挂载点: " + mp)

    if not mount_points:
        try:
            dirs = xbmcvfs.listdir('/storage')[0]
            for d in dirs:
                full_path = '/storage/' + d
                if full_path not in exclude_dirs and full_path != '/storage':
                    mount_points.append(full_path)
                    log("通过目录扫描添加: " + full_path)
        except Exception as e:
            log("扫描 /storage 目录失败: " + str(e))

    if not mount_points:
        show_notification("未找到任何挂载点或子目录", 3000)
        return

    mount_points = list(set(mount_points))

    preview_msg = "将添加以下挂载点到收藏夹：\n\n"
    for mp in mount_points:
        preview_msg += f"{mp}\n"
    preview_msg += f"\n共 {len(mount_points)} 个挂载点，确认添加？"

    if not dialog.yesno("自动添加挂载点", preview_msg):
        show_notification("已取消操作", 2000)
        return

    if xbmcvfs.exists(FAVOURITES_FILE):
        backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(FAVOURITES_FILE, backup_path)
            clean_old_backups()
        except Exception as e:
            show_notification("备份失败，操作取消: " + str(e), 3000)
            return

    try:
        if xbmcvfs.exists(FAVOURITES_FILE):
            fav_tree = ET.parse(FAVOURITES_FILE)
            fav_root = fav_tree.getroot()
        else:
            fav_root = ET.Element("favourites")
            fav_tree = ET.ElementTree(fav_root)
    except:
        fav_root = ET.Element("favourites")
        fav_tree = ET.ElementTree(fav_root)

    existing_paths = set()
    for fav in fav_root.findall("favourite"):
        text = fav.text
        if text and text.startswith("ActivateWindow"):
            match = re.search(r'ActivateWindow\(\d+,\s*"([^"]+)"', text)
            if match:
                existing_paths.add(match.group(1))

    added = 0
    skipped = 0
    for mp in mount_points:
        if not mp.endswith('/'):
            mp += '/'
        if mp in existing_paths:
            skipped += 1
            continue

        name = os.path.basename(mp.rstrip('/'))
        if not name:
            name = mp

        fav = ET.Element("favourite")
        fav.set("name", name)
        fav.text = f'ActivateWindow(10025,"{mp}",return)'
        fav_root.insert(0, fav)
        added += 1
        existing_paths.add(mp)

    if added == 0:
        show_notification(f"所有挂载点已存在，无新增 (跳过 {skipped} 个)", 3000)
        return

    try:
        fav_tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        show_notification(f"已添加 {added} 个挂载点，跳过 {skipped} 个已存在", 3000)
        ask_apply_restart_refresh("挂载点添加完成")
    except Exception as e:
        show_notification("写入失败: " + str(e), 3000)

def match_covers(lib_names, cover_dir, cover_files):
    """
    通用的封面匹配函数。
    lib_names: list of (原始名称, 清理后名称)
    cover_dir: 封面目录路径（以 / 结尾）
    cover_files: 目录下的图片文件列表
    返回字典 {原始名称: 匹配到的图片文件名}
    """
    cover_matches = {}
    if not cover_files:
        return cover_matches

    pattern = re.compile(r'^EMBY\d*_(.+)_\d{8}_\d{6}\.(?:png|jpg|jpeg|gif)$', re.IGNORECASE)
    extracted_map = {}
    for f in cover_files:
        match = pattern.match(f)
        if match:
            extracted_map[match.group(1)] = f

    for lib_orig, lib_clean in lib_names:
        best_score = 0
        best_file = None
        candidates = [lib_orig, lib_clean]
        for candidate in candidates:
            for extracted, f in extracted_map.items():
                if candidate == extracted or candidate in extracted or extracted in candidate:
                    ratio = min(len(candidate), len(extracted)) / max(len(candidate), len(extracted))
                    if ratio > best_score:
                        best_score = ratio
                        best_file = f
            if best_file and best_score >= 0.6:
                break
        if not best_file:
            for f in cover_files:
                name_no_ext = os.path.splitext(f)[0]
                for candidate in candidates:
                    if candidate == name_no_ext or candidate in name_no_ext or name_no_ext in candidate:
                        ratio = min(len(candidate), len(name_no_ext)) / max(len(candidate), len(name_no_ext))
                        if ratio > best_score:
                            best_score = ratio
                            best_file = f
                if best_file and best_score >= 0.6:
                    break
        if best_file and best_score >= 0.6:
            cover_matches[lib_orig] = best_file

    return cover_matches

def select_emby_libraries_to_add():
    """多选添加常规 Emby 分库（emby_movies_* / emby_tvshows_*）"""
    library_root = xbmcvfs.translatePath("special://userdata/library/video/")
    if not xbmcvfs.exists(library_root):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(library_root)
        all_folders = [d for d in dirs if d.startswith(("emby_movies_", "emby_tvshows_"))]
    except:
        show_notification("读取目录失败，请检查权限", 3000)
        return

    if not all_folders:
        show_notification("未找到任何Emby分库文件夹", 3000)
        return

    prefixes, suffixes = get_clean_rules()
    lib_items = []
    for folder in all_folders:
        if folder.startswith("emby_movies_"):
            lib_type = "movies"
            raw_name = folder[len("emby_movies_"):]
        elif folder.startswith("emby_tvshows_"):
            lib_type = "tvshows"
            raw_name = folder[len("emby_tvshows_"):]
        else:
            continue
        cleaned = clean_name(raw_name, prefixes, suffixes)
        if not cleaned:
            cleaned = raw_name
        display = f"{cleaned} ({lib_type})"
        lib_items.append((folder, raw_name, cleaned, lib_type, display))

    lib_items.sort(key=lambda x: x[4])

    dialog = xbmcgui.Dialog()
    selected_indices = dialog.multiselect("选择要添加的Emby分库", [item[4] for item in lib_items])
    if selected_indices is None or len(selected_indices) == 0:
        show_notification("未选择任何分库", 2000)
        return

    selected_items = [lib_items[i] for i in selected_indices]

    mode_list = ["自动匹配服务端封面", "选择封面目录匹配"]
    mode = dialog.select("请选择封面获取方式", mode_list)
    if mode < 0:
        show_notification("已取消", 2000)
        return

    cover_dir = None
    cover_files = []
    index_icon_map = {}

    if mode == 1:
        cover_dir = dialog.browse(3, "请选择封面图目录", "files", "", False, True, "")
        if cover_dir:
            if not cover_dir.endswith('/'):
                cover_dir += '/'
            try:
                cover_dir = urllib.parse.unquote(cover_dir)
            except:
                pass
            if xbmcvfs.exists(cover_dir):
                try:
                    dirs, files = xbmcvfs.listdir(cover_dir)
                    if files:
                        for f in files:
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                cover_files.append(f)
                    else:
                        local_path = xbmcvfs.translatePath(cover_dir)
                        if local_path and local_path != cover_dir and os.path.exists(local_path):
                            try:
                                for f in os.listdir(local_path):
                                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                        cover_files.append(f)
                            except:
                                pass
                except Exception as e:
                    log("扫描封面图目录失败: " + str(e))
        else:
            show_notification("未选择封面目录，将不设置封面", 2000)
            mode = 0
    else:
        for folder, raw_name, cleaned, lib_type, display in selected_items:
            index_file = os.path.join(library_root, folder, "index.xml")
            if xbmcvfs.exists(index_file):
                try:
                    with xbmcvfs.File(index_file, 'r') as f:
                        content = f.read()
                    root_node = ET.fromstring(content)
                    icon_elem = root_node.find('icon')
                    if icon_elem is not None and icon_elem.text:
                        index_icon_map[raw_name] = icon_elem.text
                except Exception as e:
                    log("读取index.xml失败: " + str(e))

    cover_matches = {}
    if mode == 1 and cover_files:
        lib_names = [(raw_name, cleaned) for folder, raw_name, cleaned, lib_type, display in selected_items]
        cover_matches = match_covers(lib_names, cover_dir, cover_files)

    if xbmcvfs.exists(FAVOURITES_FILE):
        backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(FAVOURITES_FILE, backup_path)
            clean_old_backups()
        except:
            pass

    try:
        if xbmcvfs.exists(FAVOURITES_FILE):
            tree = ET.parse(FAVOURITES_FILE)
            root = tree.getroot()
        else:
            root = ET.Element("favourites")
            tree = ET.ElementTree(root)
    except:
        root = ET.Element("favourites")
        tree = ET.ElementTree(root)

    name_to_fav = {}
    for fav in root.findall("favourite"):
        name = fav.get("name", "")
        if name:
            name_to_fav[name] = fav

    updated = 0
    added = 0

    for folder, raw_name, cleaned, lib_type, display in selected_items:
        path = f"library://video/emby_{lib_type}_{cleaned}/all.xml/"
        thumb = ""
        if mode == 1 and cover_files and raw_name in cover_matches and cover_dir:
            thumb = os.path.join(cover_dir, cover_matches[raw_name])
        elif mode == 0 and raw_name in index_icon_map:
            thumb = index_icon_map[raw_name]

        if cleaned in name_to_fav:
            fav = name_to_fav[cleaned]
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            updated += 1
        else:
            fav = ET.Element("favourite")
            fav.set("name", cleaned)
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            root.append(fav)
            added += 1

    if added == 0 and updated == 0:
        show_notification("没有分库需要添加或更新", 3000)
        return

    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        stats_msg = f"已更新 {updated} 个，新增 {added} 个"
        ask_apply_restart_refresh("选择分库添加完成", stats_msg)
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

def select_dynamic_libraries_to_add():
    """多选添加动态分库（emby_dynamic_movies_* / emby_dynamic_tvshows_*）"""
    library_root = xbmcvfs.translatePath("special://userdata/library/video/")
    if not xbmcvfs.exists(library_root):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(library_root)
        all_folders = [d for d in dirs if d.startswith(("emby_dynamic_movies_", "emby_dynamic_tvshows_"))]
    except:
        show_notification("读取目录失败，请检查权限", 3000)
        return

    if not all_folders:
        show_notification("未找到任何动态分库文件夹", 3000)
        return

    prefixes, suffixes = get_clean_rules()
    lib_items = []
    for folder in all_folders:
        if folder.startswith("emby_dynamic_movies_"):
            lib_type = "movies"
            raw_name = folder[len("emby_dynamic_movies_"):]
        elif folder.startswith("emby_dynamic_tvshows_"):
            lib_type = "tvshows"
            raw_name = folder[len("emby_dynamic_tvshows_"):]
        else:
            continue
        cleaned = clean_name(raw_name, prefixes, suffixes)
        if not cleaned:
            cleaned = raw_name
        display = f"{cleaned} (动态-{lib_type})"
        lib_items.append((folder, raw_name, cleaned, lib_type, display))

    lib_items.sort(key=lambda x: x[4])

    dialog = xbmcgui.Dialog()
    selected_indices = dialog.multiselect("选择要添加的动态分库", [item[4] for item in lib_items])
    if selected_indices is None or len(selected_indices) == 0:
        show_notification("未选择任何动态分库", 2000)
        return

    selected_items = [lib_items[i] for i in selected_indices]

    mode_list = ["自动匹配服务端封面", "选择封面目录匹配"]
    mode = dialog.select("请选择封面获取方式", mode_list)
    if mode < 0:
        show_notification("已取消", 2000)
        return

    cover_dir = None
    cover_files = []
    index_icon_map = {}

    if mode == 1:
        cover_dir = dialog.browse(3, "请选择封面图目录", "files", "", False, True, "")
        if cover_dir:
            if not cover_dir.endswith('/'):
                cover_dir += '/'
            try:
                cover_dir = urllib.parse.unquote(cover_dir)
            except:
                pass
            if xbmcvfs.exists(cover_dir):
                try:
                    dirs, files = xbmcvfs.listdir(cover_dir)
                    if files:
                        for f in files:
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                cover_files.append(f)
                    else:
                        local_path = xbmcvfs.translatePath(cover_dir)
                        if local_path and local_path != cover_dir and os.path.exists(local_path):
                            try:
                                for f in os.listdir(local_path):
                                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                        cover_files.append(f)
                            except:
                                pass
                except Exception as e:
                    log("扫描封面图目录失败: " + str(e))
        else:
            show_notification("未选择封面目录，将不设置封面", 2000)
            mode = 0
    else:
        for folder, raw_name, cleaned, lib_type, display in selected_items:
            index_file = os.path.join(library_root, folder, "index.xml")
            if xbmcvfs.exists(index_file):
                try:
                    with xbmcvfs.File(index_file, 'r') as f:
                        content = f.read()
                    root_node = ET.fromstring(content)
                    icon_elem = root_node.find('icon')
                    if icon_elem is not None and icon_elem.text:
                        index_icon_map[raw_name] = icon_elem.text
                except Exception as e:
                    log("读取index.xml失败: " + str(e))

    cover_matches = {}
    if mode == 1 and cover_files:
        lib_names = [(raw_name, cleaned) for folder, raw_name, cleaned, lib_type, display in selected_items]
        cover_matches = match_covers(lib_names, cover_dir, cover_files)

    if xbmcvfs.exists(FAVOURITES_FILE):
        backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(FAVOURITES_FILE, backup_path)
            clean_old_backups()
        except:
            pass

    try:
        if xbmcvfs.exists(FAVOURITES_FILE):
            tree = ET.parse(FAVOURITES_FILE)
            root = tree.getroot()
        else:
            root = ET.Element("favourites")
            tree = ET.ElementTree(root)
    except:
        root = ET.Element("favourites")
        tree = ET.ElementTree(root)

    name_to_fav = {}
    for fav in root.findall("favourite"):
        name = fav.get("name", "")
        if name:
            name_to_fav[name] = fav

    updated = 0
    added = 0

    for folder, raw_name, cleaned, lib_type, display in selected_items:
        suffix = "movie_movie.xml" if lib_type == "movies" else "series_series.xml"
        path = f"library://video/emby_dynamic_{lib_type}_{cleaned}/{suffix}/"
        thumb = ""
        if mode == 1 and cover_files and raw_name in cover_matches and cover_dir:
            thumb = os.path.join(cover_dir, cover_matches[raw_name])
        elif mode == 0 and raw_name in index_icon_map:
            thumb = index_icon_map[raw_name]

        display_name = f"动态库：{cleaned}"
        if display_name in name_to_fav:
            fav = name_to_fav[display_name]
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            updated += 1
        else:
            fav = ET.Element("favourite")
            fav.set("name", display_name)
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            root.append(fav)
            added += 1

    if added == 0 and updated == 0:
        show_notification("没有动态分库需要添加或更新", 3000)
        return

    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        stats_msg = f"已更新 {updated} 个，新增 {added} 个"
        ask_apply_restart_refresh("选择动态分库添加完成", stats_msg)
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

def add_boxsets_libraries_auto():
    mode_list = ["自动匹配服务端封面", "选择封面目录匹配"]
    dialog = xbmcgui.Dialog()
    mode = dialog.select("请选择封面获取方式", mode_list)
    if mode < 0:
        show_notification("已取消", 2000)
        return
    
    library_root = xbmcvfs.translatePath("special://userdata/library/video/")
    if not xbmcvfs.exists(library_root):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(library_root)
        lib_folders = [d for d in dirs if d.startswith("emby_dynamic_boxsets_")]
    except:
        show_notification("读取目录失败，请检查权限", 3000)
        return

    if not lib_folders:
        show_notification("未找到任何Emby合集分库", 3000)
        return

    if mode == 1:
        cover_dir = dialog.browse(3, "请选择封面图目录", "files", "", False, True, "")
        if cover_dir:
            if not cover_dir.endswith('/'):
                cover_dir += '/'
            try:
                cover_dir = urllib.parse.unquote(cover_dir)
            except:
                pass
        else:
            cover_dir = None
            show_notification("未选择封面图目录，操作已取消", 2000)
            return
    else:
        cover_dir = None

    cover_files = []
    if cover_dir and xbmcvfs.exists(cover_dir):
        try:
            dirs, files = xbmcvfs.listdir(cover_dir)
            if files:
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        cover_files.append(f)
            else:
                local_path = xbmcvfs.translatePath(cover_dir)
                if local_path and local_path != cover_dir and os.path.exists(local_path):
                    try:
                        for f in os.listdir(local_path):
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                cover_files.append(f)
                    except:
                        pass
        except Exception as e:
            log("扫描封面图目录失败: " + str(e))

    index_icon_map = {}
    if mode == 0 or not cover_files:
        for folder in lib_folders:
            index_file = os.path.join(library_root, folder, "index.xml")
            if xbmcvfs.exists(index_file):
                try:
                    with xbmcvfs.File(index_file, 'r') as f:
                        content = f.read()
                    root_node = ET.fromstring(content)
                    icon_elem = root_node.find('icon')
                    if icon_elem is not None and icon_elem.text:
                        lib_name = folder[len("emby_dynamic_boxsets_"):]
                        index_icon_map[lib_name] = icon_elem.text
                except Exception as e:
                    log("读取index.xml失败: " + str(e))

    if xbmcvfs.exists(FAVOURITES_FILE):
        backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(FAVOURITES_FILE, backup_path)
            clean_old_backups()
        except:
            pass

    try:
        if xbmcvfs.exists(FAVOURITES_FILE):
            tree = ET.parse(FAVOURITES_FILE)
            root = tree.getroot()
        else:
            root = ET.Element("favourites")
            tree = ET.ElementTree(root)
    except:
        root = ET.Element("favourites")
        tree = ET.ElementTree(root)

    existing_boxset_names = {}
    for fav in root.findall("favourite"):
        name = fav.get("name", "")
        if name:
            existing_boxset_names[name] = fav

    boxset_favs = []
    other_favs = []
    for fav in root.findall("favourite"):
        text = fav.text
        if text and 'boxset_boxset.xml' in text and 'emby_dynamic_boxsets_' in text:
            boxset_favs.append(fav)
        else:
            other_favs.append(fav)

    for fav in boxset_favs:
        root.remove(fav)

    prefixes, suffixes = get_clean_rules()
    lib_names = []
    for folder in lib_folders:
        lib_name = folder[len("emby_dynamic_boxsets_"):]
        cleaned = clean_name(lib_name, prefixes, suffixes)
        if not cleaned:
            cleaned = lib_name
        lib_names.append((lib_name, cleaned))

    cover_matches = {}
    if cover_files:
        cover_matches = match_covers(lib_names, cover_dir, cover_files)

    updated = 0
    added = 0
    processed_names = set()

    for lib_orig, lib_clean in lib_names:
        display_name = f"合集：{lib_clean}"
        if display_name in processed_names:
            continue
        processed_names.add(display_name)
        path = f"library://video/emby_dynamic_boxsets_{lib_clean}/boxset_boxset.xml/"
        thumb = ""

        if cover_files and lib_orig in cover_matches and cover_dir:
            thumb = os.path.join(cover_dir, cover_matches[lib_orig])
        elif lib_orig in index_icon_map:
            thumb = index_icon_map[lib_orig]

        if display_name in existing_boxset_names:
            fav = existing_boxset_names[display_name]
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            updated += 1
        else:
            fav = ET.Element("favourite")
            fav.set("name", display_name)
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            root.append(fav)
            added += 1

    if added == 0 and updated == 0:
        show_notification("没有需要处理的合集分库", 3000)
        return

    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        stats_msg = f"已更新 {updated} 个，新增 {added} 个"
        ask_apply_restart_refresh("合集分库添加完成", stats_msg)
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

def add_movie_sets_entry():
    """
    在收藏夹中添加一个总入口，指向本地数据库的电影合集列表。
    路径：library://video/movies/sets.xml/
    名称为“本地：电影集”
    封面匹配逻辑与合集分库一致：自动匹配（从Emby合集分库图标提取）或用户选目录匹配。
    """
    dialog = xbmcgui.Dialog()
    
    db_path = xbmcvfs.translatePath("special://database/")
    db_files = glob.glob(os.path.join(db_path, "MyVideos*.db"))
    if not db_files:
        log("未找到 Kodi 视频数据库文件，但可以继续添加收藏夹入口")
    
    mode = dialog.select("请选择封面获取方式", ["自动匹配服务端封面", "选择封面目录匹配"])
    if mode < 0:
        show_notification("已取消", 2000)
        return

    entry_name = "本地：电影集"
    cover_path = None

    if mode == 0: 
        library_root = xbmcvfs.translatePath("special://userdata/library/video/")
        if xbmcvfs.exists(library_root):
            try:
                dirs, files = xbmcvfs.listdir(library_root)
                for d in dirs:
                    if d.startswith("emby_dynamic_boxsets_"):
                        index_file = os.path.join(library_root, d, "index.xml")
                        if xbmcvfs.exists(index_file):
                            try:
                                with xbmcvfs.File(index_file, 'r') as f:
                                    content = f.read()
                                root_node = ET.fromstring(content)
                                icon_elem = root_node.find('icon')
                                if icon_elem is not None and icon_elem.text:
                                    cover_path = icon_elem.text
                                    log(f"从合集分库 {d} 获取封面: {cover_path}")
                                    break
                            except Exception as e:
                                log(f"读取 {index_file} 失败: {str(e)}")
            except Exception as e:
                log(f"扫描合集分库失败: {str(e)}")
        if not cover_path:
            userdata = xbmcvfs.translatePath("special://userdata/")
            icon_dir = os.path.join(userdata, "addon_data", "plugin.service.emby-next-gen", "library_icons")
            if xbmcvfs.exists(icon_dir):
                try:
                    dirs, files = xbmcvfs.listdir(icon_dir)
                    for f in files:
                        if "合集" in f or "collection" in f.lower():
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                cover_path = os.path.join(icon_dir, f)
                                break
                except Exception as e:
                    log(f"扫描 library_icons 失败: {str(e)}")
        if cover_path:
            show_notification("已自动匹配到封面", 2000)
        else:
            show_notification("未匹配到封面，将不设置封面", 2000)
    else:  # 选择目录匹配
        cover_dir = dialog.browse(3, "请选择封面图目录", "files", "", False, True, "")
        if cover_dir:
            if not cover_dir.endswith('/'):
                cover_dir += '/'
            try:
                cover_dir = urllib.parse.unquote(cover_dir)
            except:
                pass
            cover_files = []
            if xbmcvfs.exists(cover_dir):
                try:
                    dirs, files = xbmcvfs.listdir(cover_dir)
                    if files:
                        for f in files:
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                cover_files.append(f)
                    else:
                        local_path = xbmcvfs.translatePath(cover_dir)
                        if local_path and local_path != cover_dir and os.path.exists(local_path):
                            for f in os.listdir(local_path):
                                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                    cover_files.append(f)
                except Exception as e:
                    log("扫描封面图目录失败: " + str(e))
            if cover_files:
                lib_names = [(entry_name, entry_name)]
                cover_matches = match_covers(lib_names, cover_dir, cover_files)
                if cover_matches and entry_name in cover_matches:
                    cover_path = os.path.join(cover_dir, cover_matches[entry_name])
                    show_notification("已匹配到封面", 2000)
                else:
                    show_notification("未匹配到合适的封面图片", 2000)
            else:
                show_notification("所选目录中没有图片文件", 2000)
        else:
            show_notification("未选择封面目录", 2000)

    # 备份并修改 favourites.xml
    if xbmcvfs.exists(FAVOURITES_FILE):
        backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(FAVOURITES_FILE, backup_path)
            clean_old_backups()
        except:
            show_notification("备份失败，操作取消", 3000)
            return

    try:
        if xbmcvfs.exists(FAVOURITES_FILE):
            tree = ET.parse(FAVOURITES_FILE)
            root = tree.getroot()
        else:
            root = ET.Element("favourites")
            tree = ET.ElementTree(root)
    except:
        show_notification("解析 favourites.xml 失败", 3000)
        return

    # 删除旧条目（如果存在）
    for fav in root.findall("favourite"):
        if fav.get("name") == entry_name:
            root.remove(fav)
            break

    # 创建新条目
    fav = ET.Element("favourite")
    fav.set("name", entry_name)
    if cover_path:
        fav.set("thumb", cover_path)
    fav.text = 'ActivateWindow(10025,"library://video/movies/sets.xml/",return)'
    root.append(fav)  # 放在末尾

    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        show_notification(f"已添加 {entry_name} 到收藏夹", 3000)
        ask_apply_restart_refresh("电影合集添加完成")
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

# ================= 分库添加功能（原有） =================
def add_tv_show_inprogress():
    mode_list = ["自动匹配服务端封面", "选择封面目录匹配"]
    dialog = xbmcgui.Dialog()
    mode = dialog.select("请选择封面获取方式", mode_list)
    if mode < 0:
        show_notification("已取消", 2000)
        return
    
    library_root = xbmcvfs.translatePath("special://userdata/library/video/")
    if not xbmcvfs.exists(library_root):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(library_root)
        lib_folders = [d for d in dirs if d.startswith("emby_tvshows_")]
    except:
        show_notification("读取目录失败，请检查权限", 3000)
        return

    if not lib_folders:
        show_notification("未找到任何Emby电视剧分库", 3000)
        return

    if mode == 1:
        cover_dir = dialog.browse(3, "请选择封面图目录", "files", "", False, True, "")
        if cover_dir:
            if not cover_dir.endswith('/'):
                cover_dir += '/'
            try:
                cover_dir = urllib.parse.unquote(cover_dir)
            except:
                pass
        else:
            cover_dir = None
            show_notification("未选择封面图目录，操作已取消", 2000)
            return
    else:
        cover_dir = None

    cover_files = []
    if cover_dir and xbmcvfs.exists(cover_dir):
        try:
            dirs, files = xbmcvfs.listdir(cover_dir)
            if files:
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        cover_files.append(f)
            else:
                local_path = xbmcvfs.translatePath(cover_dir)
                if local_path and local_path != cover_dir and os.path.exists(local_path):
                    try:
                        for f in os.listdir(local_path):
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                cover_files.append(f)
                    except:
                        pass
        except Exception as e:
            log("扫描封面图目录失败: " + str(e))

    index_icon_map = {}
    if mode == 0 or not cover_files:
        for folder in lib_folders:
            index_file = os.path.join(library_root, folder, "index.xml")
            if xbmcvfs.exists(index_file):
                try:
                    with xbmcvfs.File(index_file, 'r') as f:
                        content = f.read()
                    root_node = ET.fromstring(content)
                    icon_elem = root_node.find('icon')
                    if icon_elem is not None and icon_elem.text:
                        lib_name = folder[len("emby_tvshows_"):]
                        index_icon_map[lib_name] = icon_elem.text
                except Exception as e:
                    log("读取index.xml失败: " + str(e))

    if xbmcvfs.exists(FAVOURITES_FILE):
        backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(FAVOURITES_FILE, backup_path)
            clean_old_backups()
        except:
            pass

    try:
        if xbmcvfs.exists(FAVOURITES_FILE):
            tree = ET.parse(FAVOURITES_FILE)
            root = tree.getroot()
        else:
            root = ET.Element("favourites")
            tree = ET.ElementTree(root)
    except:
        root = ET.Element("favourites")
        tree = ET.ElementTree(root)

    existing_entries = {}
    for fav in root.findall("favourite"):
        name = fav.get("name", "")
        if name:
            existing_entries[name] = fav

    prefixes, suffixes = get_clean_rules()

    lib_names = []
    for folder in lib_folders:
        if folder.startswith("emby_tvshows_"):
            lib_name = folder[len("emby_tvshows_"):]
            cleaned = clean_name(lib_name, prefixes, suffixes)
            if not cleaned:
                cleaned = lib_name
            lib_names.append((lib_name, cleaned))

    cover_matches = {}
    if cover_files:
        cover_matches = match_covers(lib_names, cover_dir, cover_files)

    updated = 0
    added = 0
    for lib_orig, lib_clean in lib_names:
        fav_name = f"进行中：{lib_clean}"
        path = f"library://video/emby_tvshows_{lib_clean}/inprogress.xml/"
        thumb = ""

        if cover_files and lib_orig in cover_matches and cover_dir:
            thumb = os.path.join(cover_dir, cover_matches[lib_orig])
        elif lib_orig in index_icon_map:
            thumb = index_icon_map[lib_orig]

        if fav_name in existing_entries:
            fav = existing_entries[fav_name]
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            updated += 1
        else:
            fav = ET.Element("favourite")
            fav.set("name", fav_name)
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            root.insert(0, fav)  # 优先
            added += 1

    if added == 0 and updated == 0:
        show_notification("没有需要处理的电视剧分库", 3000)
        return

    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        stats_msg = f"已更新 {updated} 个，新增 {added} 个"
        ask_apply_restart_refresh("电视剧播放记录添加完成", stats_msg)
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

def add_emby_libraries_auto():
    sort_choice = xbmcgui.Dialog().select("选择分库排序方式", ["电视剧优先", "电影优先"])
    if sort_choice < 0:
        show_notification("已取消操作", 2000)
        return
    tv_first = (sort_choice == 0)
    
    mode_list = ["自动匹配服务端封面", "选择封面目录匹配"]
    dialog = xbmcgui.Dialog()
    mode = dialog.select("请选择封面获取方式", mode_list)
    if mode < 0:
        show_notification("已取消", 2000)
        return
    
    library_root = xbmcvfs.translatePath("special://userdata/library/video/")
    if not xbmcvfs.exists(library_root):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(library_root)
        lib_folders = [d for d in dirs if d.startswith(("emby_movies_", "emby_tvshows_"))]
    except:
        show_notification("读取目录失败，请检查权限", 3000)
        return

    if not lib_folders:
        show_notification("未找到任何Emby分库文件夹", 3000)
        return

    if mode == 1:
        cover_dir = dialog.browse(3, "请选择封面图目录", "files", "", False, True, "")
        if cover_dir:
            if not cover_dir.endswith('/'):
                cover_dir += '/'
            try:
                cover_dir = urllib.parse.unquote(cover_dir)
            except:
                pass
        else:
            cover_dir = None
            show_notification("未选择封面图目录，操作已取消", 2000)
            return
    else:
        cover_dir = None

    cover_files = []
    if cover_dir and xbmcvfs.exists(cover_dir):
        try:
            dirs, files = xbmcvfs.listdir(cover_dir)
            if files:
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        cover_files.append(f)
            else:
                local_path = xbmcvfs.translatePath(cover_dir)
                if local_path and local_path != cover_dir and os.path.exists(local_path):
                    try:
                        for f in os.listdir(local_path):
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                cover_files.append(f)
                    except:
                        pass
        except Exception as e:
            log("扫描封面图目录失败: " + str(e))

    index_icon_map = {}
    if mode == 0 or not cover_files:
        for folder in lib_folders:
            index_file = os.path.join(library_root, folder, "index.xml")
            if xbmcvfs.exists(index_file):
                try:
                    with xbmcvfs.File(index_file, 'r') as f:
                        content = f.read()
                    root_node = ET.fromstring(content)
                    icon_elem = root_node.find('icon')
                    if icon_elem is not None and icon_elem.text:
                        if folder.startswith("emby_movies_"):
                            lib_name = folder[len("emby_movies_"):]
                        elif folder.startswith("emby_tvshows_"):
                            lib_name = folder[len("emby_tvshows_"):]
                        else:
                            continue
                        index_icon_map[lib_name] = icon_elem.text
                except Exception as e:
                    log("读取index.xml失败: " + str(e))

    if xbmcvfs.exists(FAVOURITES_FILE):
        backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(FAVOURITES_FILE, backup_path)
            clean_old_backups()
        except:
            pass

    try:
        if xbmcvfs.exists(FAVOURITES_FILE):
            tree = ET.parse(FAVOURITES_FILE)
            root = tree.getroot()
        else:
            root = ET.Element("favourites")
            tree = ET.ElementTree(root)
    except:
        root = ET.Element("favourites")
        tree = ET.ElementTree(root)

    existing_emby_names = {}
    for fav in root.findall("favourite"):
        name = fav.get("name", "")
        if name:
            existing_emby_names[name] = fav

    # 移除旧的Emby分库条目
    emby_favs = []
    other_favs = []
    for fav in root.findall("favourite"):
        text = fav.text
        if text and '/all.xml/' in text and ('emby_movies_' in text or 'emby_tvshows_' in text):
            emby_favs.append(fav)
        else:
            other_favs.append(fav)

    for fav in emby_favs:
        root.remove(fav)

    prefixes, suffixes = get_clean_rules()

    tv_items = []
    movie_items = []
    for folder in lib_folders:
        if folder.startswith("emby_movies_"):
            lib_name = folder[len("emby_movies_"):]
            folder_type = "movies"
            movie_items.append((folder, lib_name, folder_type))
        elif folder.startswith("emby_tvshows_"):
            lib_name = folder[len("emby_tvshows_"):]
            folder_type = "tvshows"
            tv_items.append((folder, lib_name, folder_type))

    if tv_first:
        first_items = tv_items
        second_items = movie_items
    else:
        first_items = movie_items
        second_items = tv_items

    updated = 0
    added = 0
    processed_names = set()

    for folder, lib_name, folder_type in first_items:
        cleaned = clean_name(lib_name, prefixes, suffixes)
        if not cleaned:
            cleaned = lib_name
        if cleaned in processed_names:
            continue
        processed_names.add(cleaned)
        path = f"library://video/emby_{folder_type}_{cleaned}/all.xml/"
        thumb = ""
        
        cover_matches = {}
        if cover_files:
            cover_matches = match_covers([(lib_name, cleaned)], cover_dir, cover_files)
        if cover_files and lib_name in cover_matches and cover_dir:
            thumb = os.path.join(cover_dir, cover_matches[lib_name])
        elif lib_name in index_icon_map:
            thumb = index_icon_map[lib_name]

        if cleaned in existing_emby_names:
            fav = existing_emby_names[cleaned]
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            updated += 1
        else:
            fav = ET.Element("favourite")
            fav.set("name", cleaned)
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            root.append(fav)
            added += 1

    for folder, lib_name, folder_type in second_items:
        cleaned = clean_name(lib_name, prefixes, suffixes)
        if not cleaned:
            cleaned = lib_name
        if cleaned in processed_names:
            continue
        processed_names.add(cleaned)
        path = f"library://video/emby_{folder_type}_{cleaned}/all.xml/"
        thumb = ""
        
        cover_matches = {}
        if cover_files:
            cover_matches = match_covers([(lib_name, cleaned)], cover_dir, cover_files)
        if cover_files and lib_name in cover_matches and cover_dir:
            thumb = os.path.join(cover_dir, cover_matches[lib_name])
        elif lib_name in index_icon_map:
            thumb = index_icon_map[lib_name]

        if cleaned in existing_emby_names:
            fav = existing_emby_names[cleaned]
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            updated += 1
        else:
            fav = ET.Element("favourite")
            fav.set("name", cleaned)
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            root.append(fav)
            added += 1

    if added == 0 and updated == 0:
        show_notification("没有需要处理的Emby分库", 3000)
        return

    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        stats_msg = f"已更新 {updated} 个，新增 {added} 个"
        ask_apply_restart_refresh("分库添加完成", stats_msg)
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

def add_emby_dynamic_libraries_auto():
    sort_choice = xbmcgui.Dialog().select("选择动态分库排序方式", ["电视剧优先", "电影优先"])
    if sort_choice < 0:
        show_notification("已取消操作", 2000)
        return
    tv_first = (sort_choice == 0)
    
    mode_list = ["自动匹配服务端封面", "选择封面目录匹配"]
    dialog = xbmcgui.Dialog()
    mode = dialog.select("请选择封面获取方式", mode_list)
    if mode < 0:
        show_notification("已取消", 2000)
        return
    
    library_root = xbmcvfs.translatePath("special://userdata/library/video/")
    if not xbmcvfs.exists(library_root):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(library_root)
        lib_folders = [d for d in dirs if d.startswith(("emby_dynamic_movies_", "emby_dynamic_tvshows_"))]
    except:
        show_notification("读取目录失败，请检查权限", 3000)
        return

    if not lib_folders:
        show_notification("未找到任何Emby动态分库文件夹", 3000)
        return

    if mode == 1:
        cover_dir = dialog.browse(3, "请选择封面图目录", "files", "", False, True, "")
        if cover_dir:
            if not cover_dir.endswith('/'):
                cover_dir += '/'
            try:
                cover_dir = urllib.parse.unquote(cover_dir)
            except:
                pass
        else:
            cover_dir = None
            show_notification("未选择封面图目录，操作已取消", 2000)
            return
    else:
        cover_dir = None

    cover_files = []
    if cover_dir and xbmcvfs.exists(cover_dir):
        try:
            dirs, files = xbmcvfs.listdir(cover_dir)
            if files:
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        cover_files.append(f)
            else:
                local_path = xbmcvfs.translatePath(cover_dir)
                if local_path and local_path != cover_dir and os.path.exists(local_path):
                    try:
                        for f in os.listdir(local_path):
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                cover_files.append(f)
                    except:
                        pass
        except Exception as e:
            log("扫描封面图目录失败: " + str(e))

    index_icon_map = {}
    if mode == 0 or not cover_files:
        for folder in lib_folders:
            index_file = os.path.join(library_root, folder, "index.xml")
            if xbmcvfs.exists(index_file):
                try:
                    with xbmcvfs.File(index_file, 'r') as f:
                        content = f.read()
                    root_node = ET.fromstring(content)
                    icon_elem = root_node.find('icon')
                    if icon_elem is not None and icon_elem.text:
                        if folder.startswith("emby_dynamic_movies_"):
                            lib_name = folder[len("emby_dynamic_movies_"):]
                        elif folder.startswith("emby_dynamic_tvshows_"):
                            lib_name = folder[len("emby_dynamic_tvshows_"):]
                        else:
                            continue
                        index_icon_map[lib_name] = icon_elem.text
                except Exception as e:
                    log("读取index.xml失败: " + str(e))

    if xbmcvfs.exists(FAVOURITES_FILE):
        backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(FAVOURITES_FILE, backup_path)
            clean_old_backups()
        except:
            pass

    try:
        if xbmcvfs.exists(FAVOURITES_FILE):
            tree = ET.parse(FAVOURITES_FILE)
            root = tree.getroot()
        else:
            root = ET.Element("favourites")
            tree = ET.ElementTree(root)
    except:
        root = ET.Element("favourites")
        tree = ET.ElementTree(root)

    existing_dynamic_names = {}
    for fav in root.findall("favourite"):
        name = fav.get("name", "")
        if name:
            existing_dynamic_names[name] = fav

    # 移除旧的动态分库条目
    dynamic_favs = []
    other_favs = []
    for fav in root.findall("favourite"):
        text = fav.text
        if text and ('movie_movie.xml' in text or 'series_series.xml' in text) and ('emby_dynamic_movies_' in text or 'emby_dynamic_tvshows_' in text):
            dynamic_favs.append(fav)
        else:
            other_favs.append(fav)

    for fav in dynamic_favs:
        root.remove(fav)

    prefixes, suffixes = get_clean_rules()

    tv_items = []
    movie_items = []
    for folder in lib_folders:
        if folder.startswith("emby_dynamic_movies_"):
            lib_name = folder[len("emby_dynamic_movies_"):]
            folder_type = "movies"
            movie_items.append((folder, lib_name, folder_type))
        elif folder.startswith("emby_dynamic_tvshows_"):
            lib_name = folder[len("emby_dynamic_tvshows_"):]
            folder_type = "tvshows"
            tv_items.append((folder, lib_name, folder_type))

    if tv_first:
        first_items = tv_items
        second_items = movie_items
    else:
        first_items = movie_items
        second_items = tv_items

    updated = 0
    added = 0
    processed_names = set()

    for folder, lib_name, folder_type in first_items:
        cleaned = clean_name(lib_name, prefixes, suffixes)
        if not cleaned:
            cleaned = lib_name
        display_name = f"动态库：{cleaned}"
        if display_name in processed_names:
            continue
        processed_names.add(display_name)
        if folder_type == "movies":
            suffix = "movie_movie.xml"
        else:
            suffix = "series_series.xml"
        path = f"library://video/emby_dynamic_{folder_type}_{cleaned}/{suffix}/"
        thumb = ""
        
        cover_matches = {}
        if cover_files:
            cover_matches = match_covers([(lib_name, cleaned)], cover_dir, cover_files)
        if cover_files and lib_name in cover_matches and cover_dir:
            thumb = os.path.join(cover_dir, cover_matches[lib_name])
        elif lib_name in index_icon_map:
            thumb = index_icon_map[lib_name]

        if display_name in existing_dynamic_names:
            fav = existing_dynamic_names[display_name]
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            updated += 1
        else:
            fav = ET.Element("favourite")
            fav.set("name", display_name)
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            root.append(fav)
            added += 1

    for folder, lib_name, folder_type in second_items:
        cleaned = clean_name(lib_name, prefixes, suffixes)
        if not cleaned:
            cleaned = lib_name
        display_name = f"动态库：{cleaned}"
        if display_name in processed_names:
            continue
        processed_names.add(display_name)
        if folder_type == "movies":
            suffix = "movie_movie.xml"
        else:
            suffix = "series_series.xml"
        path = f"library://video/emby_dynamic_{folder_type}_{cleaned}/{suffix}/"
        thumb = ""
        
        cover_matches = {}
        if cover_files:
            cover_matches = match_covers([(lib_name, cleaned)], cover_dir, cover_files)
        if cover_files and lib_name in cover_matches and cover_dir:
            thumb = os.path.join(cover_dir, cover_matches[lib_name])
        elif lib_name in index_icon_map:
            thumb = index_icon_map[lib_name]

        if display_name in existing_dynamic_names:
            fav = existing_dynamic_names[display_name]
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            updated += 1
        else:
            fav = ET.Element("favourite")
            fav.set("name", display_name)
            if thumb:
                fav.set("thumb", thumb)
            fav.text = f'ActivateWindow(10025,"{path}",return)'
            root.append(fav)
            added += 1

    if added == 0 and updated == 0:
        show_notification("没有需要处理的Emby动态分库", 3000)
        return

    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        stats_msg = f"已更新 {updated} 个，新增 {added} 个"
        ask_apply_restart_refresh("动态分库添加完成", stats_msg)
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

def update_emby_cache():
    userdata = xbmcvfs.translatePath("special://userdata/")
    icon_dir = os.path.join(userdata, "addon_data", "plugin.service.emby-next-gen", "library_icons")
    video_dir = os.path.join(userdata, "library", "video")
    
    deleted = []
    
    try:
        shutil.rmtree(icon_dir)
        deleted.append("图标缓存目录")
    except FileNotFoundError:
        pass
    except Exception as e:
        show_notification("删除图标缓存失败: " + str(e), 3000)
        return
    
    try:
        shutil.rmtree(video_dir)
        deleted.append("库目录")
    except FileNotFoundError:
        pass
    except Exception as e:
        show_notification("删除库目录失败: " + str(e), 3000)
        return
    
    if deleted:
        show_notification("已删除: " + "、".join(deleted), 3000)
        dialog = xbmcgui.Dialog()
        ret = dialog.yesno("更新缓存", "旧缓存已清除。\n重启Kodi后Emby将自动重建缓存并同步数据，如果界面没内容请重载皮肤。\n是否立即重启？")
        if ret:
            xbmc.executebuiltin('RestartApp')
        else:
            show_notification("请手动重启 Kodi 以重新同步", 3000)
    else:
        show_notification("未发现需要清理的缓存目录", 3000)

# ================= 主菜单 =================
def main_menu():
    acquire_single_instance()
    
    dialog = xbmcgui.Dialog()
    options = [
        "自动重建/添加Emby同步分库到收藏夹",
        "自动添加Emby动态分库到收藏夹",
        "选择Emby同步分库添加到收藏夹",
        "选择Emby动态分库添加到收藏夹",
        "添加电视剧分库播放记录到收藏夹",
        "添加Emby动态合集分库到收藏夹",
        "添加本地电影合集到收藏夹",
        "更新Emby分库数据缓存",
        "自动添加挂载点到收藏夹",
        "修改收藏夹Emby分库名称路径",
        "打包插件备份zip文件到指定目录",
        "重启系统",
        "重启到安卓",
        "重启Kodi（仅重启进程）",
        "选择tar更新文件更新系统",
        "选择tar备份文件恢复数据",
        "备份当前系统数据到指定目录",
        "内网/直连（http）测速"
    ]
    choice = dialog.select("系统维护工具 - 请选择操作", options)
    if choice < 0:
        return

    if choice == 0:
        add_emby_libraries_auto()
    elif choice == 2:
        select_emby_libraries_to_add()
    elif choice == 3:
        select_dynamic_libraries_to_add()
    elif choice == 1:
        add_emby_dynamic_libraries_auto()
    elif choice == 4:
        add_tv_show_inprogress()
    elif choice == 5:
        add_boxsets_libraries_auto()
    elif choice == 6:
        add_movie_sets_entry()
    elif choice == 7:
        update_emby_cache()
    elif choice == 8:
        add_mounts_to_favourites()
    elif choice == 9:
        fix_favourites()
    elif choice == 10:
        pack_addon()
    elif choice == 11:
        if dialog.yesno("确认", "确定要重启系统吗？"):
            reboot_system()
        else:
            show_notification("已取消重启", 2000)
    elif choice == 12:
        if dialog.yesno("确认", "确定要重启到安卓系统吗？"):
            reboot_to_android()
        else:
            show_notification("已取消重启", 2000)
    elif choice == 13:
        restart_kodi()
    elif choice == 14:
        handle_tar_update()
    elif choice == 15:
        handle_backup_restore()
    elif choice == 16:
        handle_backup_data()
    elif choice == 17:
        handle_speed_test()

if __name__ == "__main__":
    acquire_single_instance()
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip('"').lower()
        if arg == "fix":
            fix_favourites()
        elif arg == "pack":
            pack_addon()
        else:
            main_menu()
    else:
        main_menu()
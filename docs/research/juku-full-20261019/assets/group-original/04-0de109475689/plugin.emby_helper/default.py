# -*- coding: utf-8 -*-

import os
import re
import shutil
import sys
import glob
import time
import sqlite3
import urllib.parse
import xml.etree.ElementTree as ET
import xml.dom.minidom
import xbmc
import xbmcvfs
import xbmcgui
import xbmcaddon
from datetime import datetime

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')
ICON_PATH = os.path.join(ADDON_PATH, 'icon.png')

USERDATA_DIR = xbmcvfs.translatePath("special://userdata/")
FAVOURITES_FILE = os.path.join(USERDATA_DIR, "favourites.xml")
LIBRARY_ROOT = xbmcvfs.translatePath("special://userdata/library/video/")

PREFIXES = ["EMBY: "]
SUFFIXES = [" (movies)", " (tvshows)"]
ENABLE_PATH_FIX = True

def log(msg):
    xbmc.log("[Emby分库助手] " + msg, level=xbmc.LOGINFO)

def show_notification(msg, duration=3000):
    xbmcgui.Dialog().notification("Emby分库助手", msg, ICON_PATH, duration)

def clean_name(name):
    if not name:
        return name
    for prefix in PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    for suffix in SUFFIXES:
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

def ask_apply_restart_refresh(operation_desc, stats_msg=""):
    dialog = xbmcgui.Dialog()
    msg = operation_desc
    if stats_msg:
        msg += "\n" + stats_msg
    options = ["重启Kodi（推荐）", "稍后手动重启"]
    ret = dialog.select(msg, options)
    if ret == 0:
        xbmc.log("[Emby分库助手] 用户选择重启Kodi", xbmc.LOGINFO)
        xbmc.executebuiltin('RestartApp')
    elif ret == 1:
        show_notification("请手动重启Kodi以使更改生效", 3000)

def match_covers(lib_names, cover_dir, cover_files):
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

def build_preview(root):
    name_changes = []
    path_changes = []
    for fav in root.findall("favourite"):
        old_name = fav.get("name", "")
        new_name = clean_name(old_name)
        if new_name != old_name:
            name_changes.append((old_name, new_name))
        if ENABLE_PATH_FIX:
            text = fav.text
            if text and text.startswith("ActivateWindow"):
                match = re.search(r'ActivateWindow\(\d+,\s*"([^"]+)"', text)
                if match:
                    old_path = match.group(1)
                    if not old_path.endswith("/all.xml/"):
                        new_path = old_path.rstrip('/') + "/all.xml/"
                        path_changes.append((old_path, new_path))
    return name_changes, path_changes

def apply_changes(root):
    name_count = 0
    path_count = 0
    for fav in root.findall("favourite"):
        old_name = fav.get("name", "")
        new_name = clean_name(old_name)
        if new_name != old_name:
            fav.set("name", new_name)
            name_count += 1
        if ENABLE_PATH_FIX:
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
    try:
        tree = ET.parse(FAVOURITES_FILE)
        root = tree.getroot()
    except:
        show_notification("XML解析失败", 3000)
        return
    name_changes, path_changes = build_preview(root)
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
    if not xbmcgui.Dialog().yesno("Emby分库助手 - 预览修改", msg):
        show_notification("已取消修改", 2000)
        return
    backup_path = FAVOURITES_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(FAVOURITES_FILE, backup_path)
        clean_old_backups()
    except:
        show_notification("备份失败，操作取消", 3000)
        return
    name_count, path_count = apply_changes(root)
    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        stats_msg = f"修复路径 {path_count} 个，清理名称 {name_count} 个"
        ask_apply_restart_refresh("收藏夹修复完成", stats_msg)
    except:
        show_notification("写入失败，请检查权限", 3000)

def update_emby_cache():
    userdata = xbmcvfs.translatePath("special://userdata/")
    icon_dir = os.path.join(userdata, "addon_data", "plugin.service.emby-next-gen", "library_icons")
    video_dir = os.path.join(userdata, "library", "video")
    deleted = []
    for path in [icon_dir, video_dir]:
        try:
            shutil.rmtree(path)
            deleted.append(os.path.basename(path))
        except FileNotFoundError:
            pass
        except Exception as e:
            show_notification(f"删除 {os.path.basename(path)} 失败: {str(e)}", 3000)
            return
    if deleted:
        show_notification("已删除: " + "、".join(deleted), 3000)
        if xbmcgui.Dialog().yesno("更新缓存", "旧缓存已清除。\n重启Kodi后Emby将自动重建缓存并同步数据，是否立即重启？"):
            xbmc.executebuiltin('RestartApp')
        else:
            show_notification("请手动重启 Kodi 以重新同步", 3000)
    else:
        show_notification("未发现需要清理的缓存目录", 3000)

def add_tv_show_inprogress():
    mode_list = ["自动匹配服务端封面", "选择封面目录匹配"]
    dialog = xbmcgui.Dialog()
    mode = dialog.select("请选择封面获取方式", mode_list)
    if mode < 0:
        show_notification("已取消", 2000)
        return

    if not xbmcvfs.exists(LIBRARY_ROOT):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(LIBRARY_ROOT)
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
            index_file = os.path.join(LIBRARY_ROOT, folder, "index.xml")
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

    lib_names = []
    for folder in lib_folders:
        if folder.startswith("emby_tvshows_"):
            lib_name = folder[len("emby_tvshows_"):]
            cleaned = clean_name(lib_name)
            if not cleaned:
                cleaned = lib_name
            lib_names.append((lib_name, cleaned))

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
            root.insert(0, fav)
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

def add_boxsets_libraries_auto():
    mode_list = ["自动匹配服务端封面", "选择封面目录匹配"]
    dialog = xbmcgui.Dialog()
    mode = dialog.select("请选择封面获取方式", mode_list)
    if mode < 0:
        show_notification("已取消", 2000)
        return

    if not xbmcvfs.exists(LIBRARY_ROOT):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(LIBRARY_ROOT)
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
            index_file = os.path.join(LIBRARY_ROOT, folder, "index.xml")
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

    lib_names = []
    for folder in lib_folders:
        lib_name = folder[len("emby_dynamic_boxsets_"):]
        cleaned = clean_name(lib_name)
        if not cleaned:
            cleaned = lib_name
        lib_names.append((lib_name, cleaned))

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

    if not xbmcvfs.exists(LIBRARY_ROOT):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(LIBRARY_ROOT)
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
            index_file = os.path.join(LIBRARY_ROOT, folder, "index.xml")
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
        cleaned = clean_name(lib_name)
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
        cleaned = clean_name(lib_name)
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

    if not xbmcvfs.exists(LIBRARY_ROOT):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(LIBRARY_ROOT)
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
            index_file = os.path.join(LIBRARY_ROOT, folder, "index.xml")
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
        cleaned = clean_name(lib_name)
        if not cleaned:
            cleaned = lib_name
        if cleaned in processed_names:
            continue
        processed_names.add(cleaned)
        path = f"library://video/emby_{folder_type}_{cleaned}/all.xml/"
        thumb = ""

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
        cleaned = clean_name(lib_name)
        if not cleaned:
            cleaned = lib_name
        if cleaned in processed_names:
            continue
        processed_names.add(cleaned)
        path = f"library://video/emby_{folder_type}_{cleaned}/all.xml/"
        thumb = ""

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

def select_emby_libraries_to_add():
    if not xbmcvfs.exists(LIBRARY_ROOT):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(LIBRARY_ROOT)
        all_folders = [d for d in dirs if d.startswith(("emby_movies_", "emby_tvshows_"))]
    except:
        show_notification("读取目录失败，请检查权限", 3000)
        return

    if not all_folders:
        show_notification("未找到任何Emby分库文件夹", 3000)
        return

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
        cleaned = clean_name(raw_name)
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
            index_file = os.path.join(LIBRARY_ROOT, folder, "index.xml")
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
        ask_apply_restart_refresh("选择同步分库添加完成", stats_msg)
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

def select_dynamic_libraries_to_add():
    if not xbmcvfs.exists(LIBRARY_ROOT):
        show_notification("未找到库目录，请确认Emby插件已运行并生成分库", 3000)
        return

    try:
        dirs, files = xbmcvfs.listdir(LIBRARY_ROOT)
        all_folders = [d for d in dirs if d.startswith(("emby_dynamic_movies_", "emby_dynamic_tvshows_"))]
    except:
        show_notification("读取目录失败，请检查权限", 3000)
        return

    if not all_folders:
        show_notification("未找到任何动态分库文件夹", 3000)
        return

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
        cleaned = clean_name(raw_name)
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
            index_file = os.path.join(LIBRARY_ROOT, folder, "index.xml")
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

def add_movie_sets_entry():
    dialog = xbmcgui.Dialog()
    db_path = xbmcvfs.translatePath("special://database/")
    db_files = glob.glob(os.path.join(db_path, "MyVideos*.db"))
    if not db_files:
        log("未找到 Kodi 视频数据库文件，但可以继续添加收藏夹")

    mode = dialog.select("请选择封面获取方式", ["自动匹配服务端封面", "选择封面目录匹配"])
    if mode < 0:
        show_notification("已取消", 2000)
        return

    entry_name = "本地：电影集"
    cover_path = None

    if mode == 0:
        if xbmcvfs.exists(LIBRARY_ROOT):
            try:
                dirs, files = xbmcvfs.listdir(LIBRARY_ROOT)
                for d in dirs:
                    if d.startswith("emby_dynamic_boxsets_"):
                        index_file = os.path.join(LIBRARY_ROOT, d, "index.xml")
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
    else:
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

    for fav in root.findall("favourite"):
        if fav.get("name") == entry_name:
            root.remove(fav)
            break

    fav = ET.Element("favourite")
    fav.set("name", entry_name)
    if cover_path:
        fav.set("thumb", cover_path)
    fav.text = 'ActivateWindow(10025,"library://video/movies/sets.xml/",return)'
    root.append(fav)

    try:
        tree.write(FAVOURITES_FILE, encoding="utf-8", xml_declaration=True)
        pretty_print_xml(FAVOURITES_FILE)
        show_notification(f"已添加 {entry_name} 到收藏夹", 3000)
        ask_apply_restart_refresh("电影合集添加完成")
    except Exception as e:
        log("写入失败: " + str(e))
        show_notification("写入失败，请检查权限", 3000)

def main_menu():
    dialog = xbmcgui.Dialog()
    options = [
        "自动重建/添加Emby分库到收藏夹",
        "自动添加Emby动态分库到收藏夹",
        "添加电视剧分库播放记录到收藏夹",
        "选择Emby同步分库添加到收藏夹",
        "选择Emby动态分库添加到收藏夹",
        "添加本地电影合集到收藏夹",
        "添加动态合集分库到收藏夹",
        "更新Emby分库数据缓存",
        "修改收藏夹Emby分库名称路径"
    ]
    choice = dialog.select("Emby分库助手 - 请选择操作", options)
    if choice < 0:
        return

    if choice == 0:
        add_emby_libraries_auto()
    elif choice == 1:
        add_emby_dynamic_libraries_auto()
    elif choice == 2:
        add_tv_show_inprogress()
    elif choice == 3:
        select_emby_libraries_to_add()
    elif choice == 4:
        select_dynamic_libraries_to_add()
    elif choice == 5:
        add_movie_sets_entry()
    elif choice == 6:
        add_boxsets_libraries_auto()
    elif choice == 7:
        update_emby_cache()
    elif choice == 8:
        fix_favourites()

if __name__ == "__main__":
    main_menu()
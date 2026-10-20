# -*- coding: utf-8 -*-
import os
import urllib.parse

# 节点默认配图键 -> resources/images/<key>_thumb.jpg / <key>_fanart.jpg
NODE_IMAGE_DIR = "resources/images"


class DummyBgProgress:
    """Mock/Fallback 进度条，用于单元测试或非 GUI 运行环境"""
    def update(self, percent=0, heading=None, message=None):
        pass
    def close(self):
        pass
    def isFinished(self):
        return True


class VfsAdapter:
    """
    负责将 VFS 目录项目交付给 Kodi UI。
    通过动态 import 规避单元测试环境缺少 xbmc 模块的问题。
    """
    def __init__(self, handle, base_url):
        self.handle = handle
        self.base_url = base_url
        try:
            import xbmc
            import xbmcgui
            import xbmcplugin
            import xbmcvfs
            self.xbmc = xbmc
            self.xbmcgui = xbmcgui
            self.xbmcplugin = xbmcplugin
            self.xbmcvfs = xbmcvfs
        except ImportError:
            self.xbmc = None
            self.xbmcgui = None
            self.xbmcplugin = None
            self.xbmcvfs = None

    def build_url(self, params):
        base = (self.base_url or "").rstrip('/')
        return f"{base}?{urllib.parse.urlencode(params)}"

    # ------------------------------------------------------------------
    # 库视图配图解析：支持节点默认图 + fanart 回退
    # ------------------------------------------------------------------
    def library_view_enabled(self):
        """读取“启用库视图”开关，默认开启。读取失败时按开启处理。"""
        if hasattr(self, "_lib_view_cache"):
            return self._lib_view_cache
        enabled = True
        try:
            import xbmcaddon
            addon = xbmcaddon.Addon()
            setting = addon.getSetting("use_library_view")
            if setting is not None and str(setting).strip() != "":
                enabled = str(setting).strip().lower() in ("true", "1", "yes", "on")
        except Exception:
            try:
                import xbmcaddon
                addon = xbmcaddon.Addon()
                enabled = addon.getSettingBool("use_library_view")
            except Exception:
                enabled = True
        self._lib_view_cache = enabled
        return enabled

    def _addon_root(self):
        """返回插件安装根目录（special:// 的本地路径）。"""
        if not hasattr(self, "_addon_root_cache"):
            root = ""
            try:
                import xbmcaddon
                addon = xbmcaddon.Addon()
                root = addon.getAddonInfo("path")
                if root and self.xbmcvfs:
                    root = self.xbmcvfs.translatePath(root)
            except Exception:
                root = ""
            if not root:
                root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self._addon_root_cache = root.rstrip("/\\")
        return self._addon_root_cache

    def node_image(self, key, kind="thumb"):
        """
        根据节点键返回内置配图绝对路径，缺失时回退到插件默认 icon/fanart。
        kind: 'thumb' | 'fanart'
        """
        root = self._addon_root()
        candidate = os.path.join(root, NODE_IMAGE_DIR, f"{key}_{kind}.jpg")
        if os.path.exists(candidate):
            return candidate
        # 通用兜底
        fallback_key = "root"
        fallback = os.path.join(root, NODE_IMAGE_DIR, f"{fallback_key}_{kind}.jpg")
        if os.path.exists(fallback):
            return fallback
        # 最终回退到插件的官方图标/背景
        if kind == "fanart":
            legacy = os.path.join(root, "resources", "fanart.webp")
        else:
            legacy = os.path.join(root, "resources", "icon.png")
        return legacy if os.path.exists(legacy) else ""

    def node_art(self, key, icon=None, fanart=None):
        """
        组装一个节点的完整 art 字典（thumb/poster/icon/landscape + fanart）。
        显式传入的 icon/fanart 优先级最高，其次才是节点内置图。
        """
        thumb = icon or self.node_image(key, "thumb")
        fan = fanart or self.node_image(key, "fanart")
        art = {}
        if thumb:
            art.update({
                "thumb": thumb,
                "icon": thumb,
                "poster": thumb,
                "landscape": fan or thumb,
                "banner": fan or thumb,
            })
        if fan:
            art["fanart"] = fan
        return art

    def create_list_item(self, label, params, is_folder=True, icon=None, fanart=None, info=None, is_playable=False, pic=None, context_menu=None, art=None, **kwargs):
        url = self.build_url(params)
        if self.xbmcgui:
            try:
                list_item = self.xbmcgui.ListItem(label, offscreen=True)
                list_item.setPath(url)
            except TypeError:
                list_item = self.xbmcgui.ListItem(label, "", url)
            target_art = {}
            if art and isinstance(art, dict):
                target_art.update(art)
            target_pic = pic or icon
            if target_pic:
                target_art.update({
                    'icon': target_pic, 
                    'thumb': target_pic, 
                    'poster': target_pic, 
                })
                # 若尚未指定宽幅图，则退而用海报占位，避免部分皮肤 landscape 视图空白
                target_art.setdefault('landscape', target_pic)
                target_art.setdefault('banner', target_pic)
            if fanart:
                target_art['fanart'] = fanart

            if target_art:
                list_item.setArt(target_art)
            
            # 为可播放项目自动注入简易 info，确保 mediatype="video" 强制唤起内置播放器
            if is_playable and not info:
                info = {"title": label, "mediatype": "video"}
                
            if info:
                resume_time = info.get("resume_time") or info.get("time")
                total_time = info.get("total_time") or info.get("duration")
                if resume_time and float(resume_time) > 0:
                    list_item.setProperty('ResumeTime', str(float(resume_time)))
                if total_time and float(total_time) > 0:
                    list_item.setProperty('TotalTime', str(float(total_time)))
                if info.get("played") or info.get("playcount"):
                    list_item.setProperty('PlayCount', str(info.get("playcount") or 1))

                # 库视图（非播放目录项）同样需要视频信息标签，否则皮肤无法展示简介/类型
                mediatype = info.get("mediatype")
                if not mediatype and is_playable:
                    mediatype = "video"

                if hasattr(list_item, 'getVideoInfoTag'):
                    try:
                        tag = list_item.getVideoInfoTag()
                        t = info.get("title")
                        if t:
                            tag.setTitle(str(t))
                        y = info.get("year")
                        if y and str(y).isdigit():
                            tag.setYear(int(y))
                        p = info.get("plot")
                        if p:
                            tag.setPlot(str(p))
                        g = info.get("genre")
                        if g:
                            tag.setGenres([g] if isinstance(g, str) else list(g))
                        d = info.get("director")
                        if d:
                            tag.setDirectors([d] if isinstance(d, str) else list(d))
                        c = info.get("cast")
                        if c and hasattr(tag, 'setCast'):
                            try:
                                names = c if isinstance(c, (list, tuple)) else [str(c)]
                                if names and hasattr(self.xbmcgui, 'ListItem'):
                                    cast_objs = []
                                    for n in names:
                                        try:
                                            actor = self.xbmcgui.ListItem(str(n))
                                            cast_objs.append(actor)
                                        except Exception:
                                            pass
                                    if cast_objs:
                                        tag.setCast(cast_objs)
                            except Exception:
                                pass
                        if mediatype:
                            tag.setMediaType(str(mediatype))
                        if resume_time and hasattr(tag, 'setResumePoint'):
                            try:
                                tag.setResumePoint(float(resume_time), float(total_time or 0))
                            except Exception:
                                pass
                        if (info.get("played") or info.get("playcount")) and hasattr(tag, 'setPlaycount'):
                            try:
                                tag.setPlaycount(int(info.get("playcount") or 1))
                            except Exception:
                                pass
                    except Exception:
                        list_item.setInfo('video', info)
                else:
                    list_item.setInfo('video', info)
                
            if is_playable:
                list_item.setProperty('IsPlayable', 'true')
                # 显式指定 path 为插件调用 url，解决部分 Kodi 19/20 底层在双击时因 path 为空忽略执行的问题
                list_item.setPath(url)

            if context_menu:
                list_item.addContextMenuItems(context_menu)
                
            return url, list_item, is_folder
        return url, None, is_folder

    def add_directory_item(self, label, params, is_folder=True, icon=None, fanart=None, info=None, is_playable=False, pic=None, context_menu=None, art=None, **kwargs):
        url, list_item, folder = self.create_list_item(
            label, params, is_folder=is_folder, icon=icon, fanart=fanart,
            info=info, is_playable=is_playable, pic=pic, context_menu=context_menu, art=art, **kwargs
        )
        if self.xbmcplugin and list_item:
            self.xbmcplugin.addDirectoryItem(self.handle, url, list_item, isFolder=folder)

    def add_library_item(self, label, params, node_key, plot="", is_folder=True,
                         mediatype=None, icon=None, fanart=None, info=None,
                         context_menu=None, is_playable=False):
        """
        渲染一个「库视图」节点：自动套用内置缩略图/背景图，并注入简介与媒体类型。
        用于主菜单与各二级菜单，使 Kodi 以海报/缩略图+简介的信息流方式展示，
        而非默认的文件列表视图。当“库视图”被关闭时退化为普通目录项。

        mediatype 推导规则（关系到皮肤 widget 能否读到背景图与简介）：
        - 未显式指定时：文件夹 => "movie"，可播放项 => "video"
        - 剧集文件夹请显式传 mediatype="tvshow"
        - 单集/剧集条目请显式传 mediatype="episode"
        使用 "movie"/"tvshow" 而非 "video"，皮肤 widget 才能正确映射
        fanart / plot / poster 等字段，否则背景与简介会读不到。
        """
        if not self.library_view_enabled():
            kw = {"is_folder": is_folder}
            if icon is not None:
                kw["icon"] = icon
            if fanart is not None:
                kw["fanart"] = fanart
            if info is not None:
                kw["info"] = info
            if is_playable:
                kw["is_playable"] = is_playable
            if context_menu is not None:
                kw["context_menu"] = context_menu
            self.add_directory_item(label, params, **kw)
            return
        if not mediatype:
            mediatype = "video" if (not is_folder or is_playable) else "movie"
        art = self.node_art(node_key, icon=icon, fanart=fanart)
        merged_info = {"title": label, "mediatype": mediatype}
        if plot:
            merged_info["plot"] = plot
        if info:
            merged_info.update(info)
        self.add_directory_item(
            label, params,
            is_folder=is_folder,
            info=merged_info,
            art=art,
            context_menu=context_menu,
            is_playable=is_playable,
        )

    def add_directory_items(self, item_tuples):
        """批量添加目录项，提高大量条目时的渲染效率。item_tuples 为 [(url, list_item, is_folder), ...]"""
        if self.xbmcplugin and self.xbmcgui and item_tuples:
            self.xbmcplugin.addDirectoryItems(self.handle, item_tuples, len(item_tuples))

    def create_bg_progress(self, heading, message=""):
        """创建后台进度条 (在屏幕右上角显示)，返回 DialogProgressBG 实例或 DummyBgProgress"""
        if self.xbmcgui and hasattr(self.xbmcgui, 'DialogProgressBG'):
            try:
                dialog = self.xbmcgui.DialogProgressBG()
                dialog.create(heading, message)
                return dialog
            except Exception:
                pass
        return DummyBgProgress()

    def set_content(self, content_type):
        if self.xbmcplugin:
            self.xbmcplugin.setContent(self.handle, content_type)

    def set_library_content(self, content_type="movies"):
        """
        将当前目录标记为媒体库内容，使皮肤以海报墙/缩略图信息流方式渲染。
        content_type 可取 movies / tvshows / videos / files / episodes 等。
        当用户在设置中关闭“库视图”时，退回默认 files 视图。
        """
        if not self.library_view_enabled():
            self.set_content("files")
            return
        self.set_content(content_type)

    def set_resolved_url(self, succeeded, list_item=None, *args, **kwargs):
        if self.xbmcplugin:
            if isinstance(list_item, str) and self.xbmcgui:
                url_str = list_item
                list_item = self.xbmcgui.ListItem(path=url_str)
                list_item.setProperty('IsPlayable', 'true')
                list_item.setPath(url_str)
                if 'art' in kwargs and kwargs['art'] and hasattr(list_item, 'setArt'):
                    list_item.setArt(kwargs['art'])
                if 'info' in kwargs and kwargs['info'] and hasattr(list_item, 'setInfo'):
                    list_item.setInfo('video', kwargs['info'])
            elif list_item is None and self.xbmcgui:
                list_item = self.xbmcgui.ListItem()
            if self.xbmc:
                path = list_item.getPath() if list_item else "None"
                self.xbmc.log(f"=== SET RESOLVED URL CALLED: succeeded={succeeded}, path={path} ===", self.xbmc.LOGINFO)
                if succeeded:
                    try:
                        self.xbmc.executebuiltin("Dialog.Close(all, true)")
                    except Exception as _close_err:
                        self.xbmc.log(f"=== SET RESOLVED URL CLOSE DIALOG ERROR: {_close_err} ===", self.xbmc.LOGWARNING)
            try:
                self.xbmcplugin.setResolvedUrl(self.handle, succeeded, list_item)
            except Exception as e:
                if self.xbmc:
                    self.xbmc.log(f"=== SET RESOLVED URL ERROR: {e} ===", self.xbmc.LOGERROR)

    def end_of_directory(self):
        if self.xbmcplugin:
            self.xbmcplugin.endOfDirectory(self.handle)

    def show_select_dialog(self, heading, choices, default_idx=0) -> int:
        if self.xbmcgui:
            dialog = self.xbmcgui.Dialog()
            return dialog.select(heading, choices, preselect=default_idx)
        return -1

    def show_numeric_dialog(self, heading, default_val="") -> str:
        if self.xbmcgui:
            dialog = self.xbmcgui.Dialog()
            return dialog.numeric(0, heading, default_val)
        return ""

    def show_input_dialog(self, heading, default_val="") -> str:
        if self.xbmcgui:
            dialog = self.xbmcgui.Dialog()
            return dialog.input(heading, default_val)
        return ""

    def update_container(self, params, replace=False):
        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        if self.xbmc:
            cmd = f"Container.Update({url}, replace)" if replace else f"Container.Update({url})"
            self.xbmc.executebuiltin(cmd)

    def refresh_container(self):
        if self.xbmc:
            self.xbmc.executebuiltin("Container.Refresh")

    def get_profile_path(self) -> str:
        if self.xbmcvfs:
            profile_path = self.xbmcvfs.translatePath("special://profile/addon_data/plugin.video.juku/")
            if not os.path.exists(profile_path):
                try:
                    os.makedirs(profile_path)
                except Exception:
                    pass
            return profile_path
        else:
            import tempfile
            temp_dir = os.path.join(tempfile.gettempdir(), 'plugin.video.juku')
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            return temp_dir

    def log(self, msg, level="info"):
        if self.xbmc:
            log_level = self.xbmc.LOGINFO
            if level == "warning":
                log_level = self.xbmc.LOGWARNING
            elif level == "error":
                log_level = self.xbmc.LOGERROR
            self.xbmc.log(f"[VfsRouter] {msg}", log_level)
        else:
            print(f"[{level.upper()}] [VfsRouter] {msg}")

    def show_keyboard_input(self, default_val="", heading="", hidden=False) -> str:
        if self.xbmc:
            import xbmc
            keyboard = xbmc.Keyboard(default_val, heading, hidden)
            keyboard.doModal()
            if keyboard.isConfirmed():
                return keyboard.getText()
            return None
        return ""

    def show_multiselect_dialog(self, heading, choices, preselect=None) -> list:
        if self.xbmcgui:
            dialog = self.xbmcgui.Dialog()
            return dialog.multiselect(heading, choices, preselect=preselect)
        return []

    def show_yes_no_dialog(self, heading, message) -> bool:
        if self.xbmcgui:
            dialog = self.xbmcgui.Dialog()
            return dialog.yesno(heading, message)
        return True

    def show_notification(self, heading, message, is_error=False):
        if self.xbmcgui:
            dialog = self.xbmcgui.Dialog()
            icon = "error" if is_error else "info"
            dialog.notification(heading, message, icon, 3000)
        else:
            print(f"[Notification] {heading}: {message}")

    def execute_builtin(self, function_str):
        if self.xbmc:
            self.xbmc.executebuiltin(function_str)


# -*- coding: utf-8 -*-
"""
主菜单配置管理器
负责管理 Kodi 插件顶级主菜单的显示/隐藏状态、排序位置，
支持通过 Kodi 原生设置 (settings.xml) 与可视化交互弹窗双向同步配置。
"""

import os
import json

# 官方默认顶级主菜单清单定义
# 包含 17 大核心业务菜单：节点键、显示名称、简介、路由参数、是否目录、媒体类型与默认序号
DEFAULT_ROOT_NODES = [
    {
        "key": "connect_phone",
        "name": "连接手机",
        "plot": "用手机扫码连接电视，支持局域网内置网页 (IP:17654) 或 PWA 跨屏推送与进度漫游。可在设置中切换连接方式。",
        "params": {"action": "connect_phone"},
        "is_folder": False,
        "mediatype": "movie",
        "default_order": 1,
    },
    {
        "key": "recommend",
        "name": "最近热门",
        "plot": "全网热播聚合，基于你口味的智能推荐，永远有下一部好看的。",
        "params": {"action": "recommend"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 2,
    },
    {
        "key": "private_libraries",
        "name": "我的私有库",
        "plot": "你的私人影音收藏，支持海报墙浏览、Excel 导入与智能同步。",
        "params": {"action": "private_libraries"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 3,
    },
    {
        "key": "shared_libraries",
        "name": "共享媒体库",
        "plot": "发现别人分享的优质媒体库，输入分享码即可一键导入本地。",
        "params": {"action": "shared_libraries"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 4,
    },
    {
        "key": "my_pans",
        "name": "我的网盘",
        "plot": "天翼云、阿里云盘、夸克、115 等多网盘统一管理，免登直连。",
        "params": {"action": "my_pans_menu"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 5,
    },
    {
        "key": "search",
        "name": "视频搜索",
        "plot": "聚合全网资源，输入关键词秒级匹配影片、剧集与网盘链接。",
        "params": {"action": "search_menu"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 6,
    },
    {
        "key": "history",
        "name": "播放记录",
        "plot": "跨屏续播与本地历史汇总，上次看到哪一集，一打开就知道。",
        "params": {"action": "history"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 7,
    },
    {
        "key": "share_square",
        "name": "分享广场",
        "plot": "看看大家都在收藏什么，热门片单与优质共享库一网打尽。",
        "params": {"action": "share_square"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 8,
    },
    {
        "key": "push",
        "name": "推送记录",
        "plot": "手机推送到电视的历史记录，随时回看与继续播放。",
        "params": {"action": "push_menu"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 9,
    },
    {
        "key": "pansou",
        "name": "盘搜",
        "plot": "搜索全网网盘资源，聚合多个搜索源，冷门好片也能找到。",
        "params": {"action": "pansou_menu"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 10,
    },
    {
        "key": "playlists",
        "name": "专题片单",
        "plot": "编辑精选主题合辑，周星驰、追光动画、奈飞原创等一键直达。",
        "params": {"action": "playlists"},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 11,
    },
    {
        "key": "category_movie",
        "name": "电影",
        "plot": "院线大片、豆瓣高分与经典老片，按年份/地区/类型自由筛选。",
        "params": {"action": "category", "typeId": 1, "page": 1},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 12,
    },
    {
        "key": "category_tv",
        "name": "剧集",
        "plot": "热播剧场全集连播，断点续播、自动连播，追剧更轻松。",
        "params": {"action": "category", "typeId": 2, "page": 1},
        "is_folder": True,
        "mediatype": "tvshow",
        "default_order": 13,
    },
    {
        "key": "category_anime",
        "name": "动漫",
        "plot": "国漫日漫全季收藏，新番同步更新，一次看个够。",
        "params": {"action": "category", "typeId": 3, "page": 1},
        "is_folder": True,
        "mediatype": "tvshow",
        "default_order": 14,
    },
    {
        "key": "category_variety",
        "name": "综艺",
        "plot": "真人秀、脱口秀、音综竞演，下饭解压的最佳陪伴。",
        "params": {"action": "category", "typeId": 4, "page": 1},
        "is_folder": True,
        "mediatype": "tvshow",
        "default_order": 15,
    },
    {
        "key": "category_doc",
        "name": "纪录",
        "plot": "人文历史与自然地理纪录片，看见真实世界的广阔与深刻。",
        "params": {"action": "category", "typeId": 5, "page": 1},
        "is_folder": True,
        "mediatype": "movie",
        "default_order": 16,
    },
    {
        "key": "category_short",
        "name": "短剧",
        "plot": "爽点密集、节奏飞快，一两分钟一集，追更根本停不下来。",
        "params": {"action": "category", "typeId": 7, "page": 1},
        "is_folder": True,
        "mediatype": "tvshow",
        "default_order": 17,
    },
]


class MenuConfigManager:
    """主菜单配置管理器"""

    def __init__(self, addon=None):
        self._addon = addon

    def _get_addon(self):
        if self._addon is not None:
            return self._addon
        try:
            import xbmcaddon
            return xbmcaddon.Addon()
        except Exception:
            return None

    def get_menu_items(self, include_hidden=False):
        """
        获取经过用户设置排序与过滤的主菜单项列表。
        按配置的 order（升序）与默认 order 排序。
        include_hidden: 是否包含已隐藏的项（管理界面需要，主界面只取可见项）
        """
        addon = self._get_addon()
        items = []

        for raw in DEFAULT_ROOT_NODES:
            key = raw["key"]
            item = dict(raw)
            visible = True
            order = raw["default_order"]

            if addon is not None:
                try:
                    show_val = addon.getSetting(f"menu_show_{key}")
                    if show_val is not None:
                        val_str = str(show_val).strip().lower()
                        if val_str in ("false", "0", "no", "off"):
                            visible = False
                        elif val_str in ("true", "1", "yes", "on"):
                            visible = True
                except Exception:
                    pass

                try:
                    order_val = addon.getSetting(f"menu_order_{key}")
                    if order_val is not None:
                        order = int(str(order_val).strip())
                except Exception:
                    pass

            item["visible"] = visible
            item["order"] = order
            items.append(item)

        # 排序：优先按用户配置 order，同权重按默认 default_order
        items.sort(key=lambda x: (x["order"], x["default_order"]))

        if not include_hidden:
            items = [it for it in items if it["visible"]]

        return items

    def save_menu_items(self, items):
        """
        将菜单列表的可见性与顺序同步持久化到 Kodi 设置中
        """
        addon = self._get_addon()
        if not addon:
            return

        for idx, it in enumerate(items, 1):
            key = it["key"]
            visible = it.get("visible", True)
            order = it.get("order", idx)
            try:
                addon.setSetting(f"menu_show_{key}", "true" if visible else "false")
                addon.setSetting(f"menu_order_{key}", str(order))
            except Exception:
                pass

    def hide_menu_item(self, key):
        """快速隐藏某一个菜单项"""
        addon = self._get_addon()
        if addon:
            try:
                addon.setSetting(f"menu_show_{key}", "false")
                return True
            except Exception:
                pass
        return False

    def reset_to_default(self):
        """恢复所有主菜单为官方默认顺序与全部显示"""
        addon = self._get_addon()
        if addon:
            for it in DEFAULT_ROOT_NODES:
                key = it["key"]
                order = it["default_order"]
                try:
                    addon.setSetting(f"menu_show_{key}", "true")
                    addon.setSetting(f"menu_order_{key}", str(order))
                except Exception:
                    pass
            return True
        return False

    def show_manage_entry_at_bottom(self):
        """是否在主菜单末尾显示‘主菜单设置’入口"""
        addon = self._get_addon()
        if addon:
            try:
                val = addon.getSetting("menu_show_root_manage_entry")
                if val is not None and str(val).strip() != "":
                    return str(val).strip().lower() in ("true", "1", "yes", "on")
            except Exception:
                pass
        return False

    def run_interactive_manager(self, adapter):
        """
        遥控器可视化主菜单排序与显示管理交互弹窗
        """
        current_items = self.get_menu_items(include_hidden=True)
        for idx, it in enumerate(current_items, 1):
            it["order"] = idx

        changed = False

        while True:
            choices = [
                "[保存并返回]",
                "[恢复默认排序与全部显示]",
            ]
            for idx, it in enumerate(current_items, 1):
                status_tag = "[显示]" if it["visible"] else "[已隐藏]"
                choices.append(f"{idx:02d}. {status_tag} {it['name']}")

            sel = adapter.show_select_dialog("主菜单排序与显示设置 (点击条目调整)", choices)
            if sel < 0 or sel == 0:
                if changed:
                    self.save_menu_items(current_items)
                    adapter.show_notification("主菜单设置", "主菜单排序与显示已更新")
                    adapter.refresh_container()
                break

            if sel == 1:
                confirm = adapter.show_yes_no_dialog("恢复默认设置", "确定要将所有菜单恢复为默认排序和全部显示吗？")
                if confirm:
                    self.reset_to_default()
                    current_items = self.get_menu_items(include_hidden=True)
                    for idx, it in enumerate(current_items, 1):
                        it["order"] = idx
                    changed = False
                    adapter.show_notification("主菜单设置", "已恢复默认排序与全部显示")
                    adapter.refresh_container()
                continue

            item_idx = sel - 2
            if item_idx < 0 or item_idx >= len(current_items):
                continue

            target_item = current_items[item_idx]
            current_status = "显示" if target_item["visible"] else "已隐藏"
            toggle_action_label = "设为 [已隐藏]" if target_item["visible"] else "设为 [显示]"

            sub_choices = [
                f"切换状态 (当前: {current_status} -> {toggle_action_label})",
                "上移一位",
                "下移一位",
                "置顶 (移至第一位)",
                "置底 (移至最后一位)",
                f"指定位置序号 (1-{len(current_items)})",
                "返回上一级",
            ]
            sub_sel = adapter.show_select_dialog(
                f"设置菜单: {target_item['name']} (当前第 {item_idx + 1} 位)",
                sub_choices
            )

            if sub_sel == 0:
                target_item["visible"] = not target_item["visible"]
                changed = True
            elif sub_sel == 1:
                if item_idx > 0:
                    current_items[item_idx], current_items[item_idx - 1] = current_items[item_idx - 1], current_items[item_idx]
                    for idx, it in enumerate(current_items, 1):
                        it["order"] = idx
                    changed = True
                else:
                    adapter.show_notification("主菜单设置", "已经是第一位了")
            elif sub_sel == 2:
                if item_idx < len(current_items) - 1:
                    current_items[item_idx], current_items[item_idx + 1] = current_items[item_idx + 1], current_items[item_idx]
                    for idx, it in enumerate(current_items, 1):
                        it["order"] = idx
                    changed = True
                else:
                    adapter.show_notification("主菜单设置", "已经是最后一位了")
            elif sub_sel == 3:
                if item_idx > 0:
                    popped = current_items.pop(item_idx)
                    current_items.insert(0, popped)
                    for idx, it in enumerate(current_items, 1):
                        it["order"] = idx
                    changed = True
            elif sub_sel == 4:
                if item_idx < len(current_items) - 1:
                    popped = current_items.pop(item_idx)
                    current_items.append(popped)
                    for idx, it in enumerate(current_items, 1):
                        it["order"] = idx
                    changed = True
            elif sub_sel == 5:
                new_pos_str = adapter.show_numeric_dialog(f"输入新序号 (1-{len(current_items)})", str(item_idx + 1))
                try:
                    new_pos = int(new_pos_str)
                    if 1 <= new_pos <= len(current_items):
                        popped = current_items.pop(item_idx)
                        current_items.insert(new_pos - 1, popped)
                        for idx, it in enumerate(current_items, 1):
                            it["order"] = idx
                        changed = True
                    elif new_pos_str:
                        adapter.show_notification("主菜单设置", "输入的序号超出范围", is_error=True)
                except (ValueError, TypeError):
                    pass
            elif sub_sel == 6 or sub_sel < 0:
                continue

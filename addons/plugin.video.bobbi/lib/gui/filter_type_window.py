import xbmcgui

from lib.gui.base_window import BaseWindow


class FilterTypeWindow(BaseWindow):
    def __init__(self, xml_file, location):
        super().__init__(xml_file, location, None)
        self.selected_type = None

    def onInit(self):
        self.list_control = self.getControl(2000)
        self.list_control.reset()

        chinese_subtitle_item = xbmcgui.ListItem(
            label="仅看标注中文字幕的片源"
        )
        chinese_subtitle_item.setProperty("type", "chinese_subtitles")
        self.list_control.addItem(chinese_subtitle_item)

        quality_item = xbmcgui.ListItem(label="清晰度")
        quality_item.setProperty("type", "quality")
        self.list_control.addItem(quality_item)

        if getattr(self, "allow_release_groups", True):
            provider_item = xbmcgui.ListItem(label="压制组")
            provider_item.setProperty("type", "provider")
            self.list_control.addItem(provider_item)

        source_item = xbmcgui.ListItem(label="来源站点")
        source_item.setProperty("type", "indexer")
        self.list_control.addItem(source_item)

        language_item = xbmcgui.ListItem(label="语言")
        language_item.setProperty("type", "language")
        self.list_control.addItem(language_item)

        if getattr(self, "allow_release_groups", True):
            release_group_item = xbmcgui.ListItem(label="精确匹配压制组")
            release_group_item.setProperty("type", "release_group")
            self.list_control.addItem(release_group_item)

        torrents_item = xbmcgui.ListItem(label="仅看 BT 片源")
        torrents_item.setProperty("type", "only_torrents")
        self.list_control.addItem(torrents_item)

        debrid_item = xbmcgui.ListItem(label="仅看解限服务片源")
        debrid_item.setProperty("type", "only_debrid")
        self.list_control.addItem(debrid_item)

        reset_item = xbmcgui.ListItem(label="清除筛选，显示全部")
        reset_item.setProperty("type", "reset")
        self.list_control.addItem(reset_item)

        self.set_default_focus(self.list_control, 2000, control_list_reset=True)

    def handle_action(self, action_id, control_id=None):
        if action_id == 7:  # Select
            selected_item = self.list_control.getSelectedItem()
            if selected_item:
                self.selected_type = selected_item.getProperty("type")
            self.close()
        elif action_id in (2, 9, 10, 13, 92):  # Back/Escape
            self.close()

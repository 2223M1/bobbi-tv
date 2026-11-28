import xbmcgui

from lib.gui.base_window import BaseWindow


class FilterWindow(BaseWindow):
    def __init__(self, xml_file, location, filter):
        super().__init__(xml_file, location, None)
        self.filter = filter
        self.selected_filter = None
        self.selected_position = None

    def onInit(self):
        self.list_control = self.getControl(2000)
        self.list_control.reset()

        active = getattr(self, 'active_position', None)
        for i, q in enumerate(self.filter):
            item = xbmcgui.ListItem(label=('✓  ' if i == active else '') + q)
            self.list_control.addItem(item)

        if active is not None and 0 <= active < len(self.filter):
            self.list_control.selectItem(active)
            self.setFocus(self.list_control)
        else:
            self.set_default_focus(self.list_control, 2000, control_list_reset=True)

    def handle_action(self, action_id, control_id=None):
        if action_id == 7:  # Select
            pos = self.list_control.getSelectedPosition()
            if 0 <= pos < len(self.filter):
                self.selected_position = pos
                self.selected_filter = self.filter[pos]
            self.close()
        elif action_id in (2, 9, 10, 13, 92):  # Back/Escape
            self.close()

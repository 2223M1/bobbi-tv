"""A bounded, instance-local terminal prompt; never opens another video itself."""
from threading import Event, Thread
from time import monotonic
import xbmc
import xbmcaddon
import xbmcgui


class TerminalActions(xbmcgui.WindowXMLDialog):
    def configure(self, current, episode, ended):
        self.current, self.episode, self.ended = current, episode, ended
        self.choice, self.done = None, Event()

    def onInit(self):
        self.getControl(100).setLabel('本集已结束 · 下一集需手动选择' if self.ended
                                     else '播放未正常结束 · 已保留续看进度')
        self.getControl(9002).setVisible(self.episode)
        self.setFocusId(9003)  # No default action ever starts media or searches.
        Thread(target=self.watch, name='bobbi-terminal-menu', daemon=True).start()

    def watch(self):
        deadline = monotonic() + 20
        monitor = xbmc.Monitor()
        while not self.done.wait(.2) and not monitor.abortRequested():
            if monotonic() >= deadline or not self.current():
                self.close()  # This exact window instance, not Dialog.Close(all).
                return

    def onClick(self, control_id):
        if control_id in (9001, 9002) and self.current():
            self.choice = 'sources' if control_id == 9001 else 'episodes'
        self.close()

    def onAction(self, action):
        if action.getId() in (9, 10, 13, 92):
            self.close()

    def close(self):
        self.done.set()
        super().close()


def choose(current, episode, ended):
    if not current():
        return None
    window = TerminalActions('terminal-actions.xml', xbmcaddon.Addon('plugin.video.bobbi').getAddonInfo('path'),
                              'Default', '1080i')
    window.configure(current, episode, ended)
    window.doModal()
    return window.choice if current() else None

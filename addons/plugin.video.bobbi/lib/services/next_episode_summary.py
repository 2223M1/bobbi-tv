"""One read-only OSD projection; no worker, timer, search or playback action."""
from copy import deepcopy
from bobbi_core.next_episode_summary import label


class Display:
    def __init__(self, adapter):
        self.adapter, self.previous, self.revision = adapter, None, 0

    def publish(self, value):
        try:
            self._publish(value)
        except Exception:
            # A partial property write/clear is dirty even when the next value
            # returns to the previously committed summary. Force full repair.
            self.previous = False
            return

    def _publish(self, value):
        import xbmcgui
        window = xbmcgui.Window(10000)
        if value == self.previous and (value is None or window.getProperty('Bobi.Next.Adapter') == self.adapter):
            return
        if value is None:
            if window.getProperty('Bobi.Next.Adapter') == self.adapter:
                for key in ('Label', 'State', 'Revision', 'Adapter'):
                    window.clearProperty('Bobi.Next.' + key)
            self.previous = None
            return
        caption = label(value)
        # Window properties intentionally contain no owner IDs, account refs,
        # URLs or action tokens. The complete envelope remains process-local.
        window.setProperty('Bobi.Next.Adapter', self.adapter)
        window.setProperty('Bobi.Next.State', value['state'])
        window.setProperty('Bobi.Next.Label', caption)
        window.setProperty('Bobi.Next.Revision', str(self.revision + 1))
        self.previous = deepcopy(value)
        self.revision += 1

    def clear(self):
        self.previous = False
        self.publish(None)

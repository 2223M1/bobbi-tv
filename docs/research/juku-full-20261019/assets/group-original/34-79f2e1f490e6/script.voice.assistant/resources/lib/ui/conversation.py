"""Remote-selectable choices and verified media posters in a central dialog."""
import queue
import threading
import time

import xbmc
import xbmcgui
from ..recording_ui import BACK
from ..voice_binding import current_codes, is_voice_key
from .transcript import message_rows, message_lines, message_page


class ConversationWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.events = queue.Queue()
        self.voice_keys = set()
        self.ready = threading.Event()
        self.cancelled = threading.Event()
        self.choices = []
        self.history = []
        self.rows = []
        self.busy = False
        self.recording = False
        self.accepting_input = False
        self.task_active = False
        self.question_token = ''
        self.question_secret = False
        self.task_stop = threading.Event()
        self.finish_requested = threading.Event()
        self.last_status = None
        self.activity_sink = None
        self.last_activity = None
        self.items = []
        # Each item is one whole message/choice. The native list is a clipped
        # line viewport: a block occupies as many lines as its text needs.
        self.display_items = []
        self.display_rows = []
        self.block_starts = []
        self._selected_block = None
        self._line_selected = 0
        self._line_block = -1
        self._chat_entry_line = None
        self._rendered = 0
        self._window_id = None
        self._closed = False
        self._recover_after = 0
        self._focus = 400
        self._focus_dirty = True
        self._selected = 0
        self._select_dirty = False
        self._render_state = None
        super().__init__(*args, **kwargs)

    def onInit(self):
        self.voice_keys = current_codes()
        # ReloadSkin destroys Kodi controls, but the worker and this model survive.
        self._window_id = xbmcgui.getCurrentWindowDialogId()
        self.getControl(500).reset()
        self._rendered = 0
        self._render_state = None
        self._focus_dirty = self._select_dirty = True
        self.ready.set()
        self.refresh(reopen=False)

    def close(self):
        self._closed = True
        super().close()

    def refresh(self, reopen=True):
        """Rebuild a lost view without cancelling or replaying the agent turn."""
        if self._closed or self.cancelled.is_set():
            return
        try:
            if (reopen and self._window_id is not None and
                    not xbmc.getCondVisibility('Window.IsVisible(%d)' % self._window_id)):
                if time.monotonic() >= self._recover_after:
                    self._recover_after = time.monotonic() + 1
                    self.show()
                return
            control = self.getControl(500)
            if control.size() != self._rendered:
                control.reset()
                self._rendered = 0
                self._render_state = None
                self._select_dirty = True
            while self._rendered < len(self.display_items):
                control.addItem(self.display_items[self._rendered])
                self._rendered += 1
            if self._select_dirty and self.items:
                line = self._line_selected if self._line_block == self._selected else self.block_starts[self._selected]
                control.selectItem(line)
                self._select_dirty = False
            elif self.items and self._window_id == xbmcgui.getCurrentWindowDialogId():
                selected = xbmc.getInfoLabel('Container(500).CurrentItem')
                if selected.isdigit():
                    index = max(0, int(selected) - 1)
                    if index < len(self.display_rows):
                        self._selected = self.display_rows[index]
                        self._line_selected, self._line_block = index, self._selected
            if self._selected_block != self._selected:
                self.setProperty('VoiceAssistant.SelectedBlock', str(self._selected))
                self._selected_block = self._selected
            state = (self.last_status, self.busy, self.recording, self.accepting_input, self.task_active, self.question_token)
            if state != self._render_state:
                # Window properties and queued list messages survive skin reload.
                # Kodi Control wrappers cache native pointers; do not dereference
                # them with setEnabled, button.setLabel, scroll or getSelectedPosition.
                title, text = self.last_status or ('', '')
                self.setProperty('VoiceAssistant.Status', title)
                self.setProperty('VoiceAssistant.Detail', message_rows(text)[-1])
                label = ('说完了，提交（OK）' if self.recording else '回答问题（语音键）' if self.question_token else '补充要求（语音键）' if self.accepting_input else '正在处理，请稍候…') if self.busy else '继续说话（语音键）'
                self.setProperty('VoiceAssistant.VoiceLabel', label)
                self.setProperty('VoiceAssistant.TaskActive', 'true' if self.task_active else 'false')
                self.setProperty('VoiceAssistant.Busy', 'true' if self.busy and not self.accepting_input else 'false')
                self._render_state = state
            if self._focus_dirty:
                self.setFocusId(self._focus)
                self._focus_dirty = False
            else:
                for identifier in (500, 400, 401, 402, 403):
                    if xbmc.getCondVisibility('Control.HasFocus(%d)' % identifier):
                        self._focus = identifier
                        break
        except RuntimeError:
            # Kodi temporarily removes controls during ReloadSkin. Keep all data
            # in Python and retry from the UI loop once the skin is ready again.
            self._rendered = 0
            self._render_state = None
            self._select_dirty = self._focus_dirty = True

    def show_question(self, token, question):
        self.question_token, self.question_secret = token, bool(question.get('isSecret'))
        first = len(self.rows)
        for option in question.get('options') or []:
            self._add_block(option['label'], 'choice', option.get('description', ''),
                            {'question': token, 'text': option['label']})
        self._selected, self._select_dirty = first, first < len(self.rows)
        self._focus = 500 if first < len(self.rows) else 401 if self.question_secret else 400
        self._focus_dirty = True
        self.refresh()

    def clear_question(self):
        self.question_token = ''
        self.question_secret = False
        self._focus, self._focus_dirty = 400, True
        self.refresh()

    def onClick(self, identifier):
        if identifier == 500:
            selected = xbmc.getInfoLabel('Container(500).CurrentItem')
            index = int(selected) - 1 if selected.isdigit() else -1
            logical = self.display_rows[index] if 0 <= index < len(self.display_rows) else -1
            row = self.rows[logical] if 0 <= logical < len(self.rows) else None
            if row and 'question' in row:
                if row['question'] == self.question_token and not self.recording:
                    self.events.put(('answer', dict(row)))
                return
        if identifier == 403:
            if self.task_active:
                self.task_stop.set()
                self.status('正在停止任务…')
            return
        if self.busy:
            if identifier == 400 and self.recording:
                self.finish_requested.set()
            elif identifier == 402:
                self.cancelled.set()
            elif self.accepting_input and not self.recording and identifier in (400, 401):
                self.events.put(('voice' if identifier == 400 else 'keyboard', ''))
            return
        if identifier == 500:
            selected = xbmc.getInfoLabel('Container(500).CurrentItem')
            index = int(selected) - 1 if selected.isdigit() else -1
            logical = self.display_rows[index] if 0 <= index < len(self.display_rows) else -1
            if 0 <= logical < len(self.rows) and self.rows[logical] is not None:
                row = self.rows[logical]
                text = row['value']
                if row.get('kind') in ('movie', 'episode', 'tvshow', 'channel'):
                    prefix = ('请查询这部电视剧的剧集供我选择：' if row['kind'] == 'tvshow' else
                              '请播放我选择的直播频道：' if row['kind'] == 'channel' else '请播放我选择的影视：')
                    text = prefix + row['title']
                    text += '\n用户选择的已查询项目：kind={}，id={}。'.format(row['kind'], row['id'])
                self.events.put(('media', dict(row)) if (row.get('kind') in ('movie', 'episode', 'channel')
                                or row.get('kind') == 'tvshow' and (row.get('_command_resume') or row.get('_command_tvshow')))
                                else ('text', text))
        elif identifier == 400:
            self.events.put(('voice', ''))
        elif identifier == 401:
            self.events.put(('keyboard', ''))
        elif identifier == 402:
            self.cancelled.set()

    def onAction(self, action):
        identifier = action.getId()
        # Some controller keymaps bind F5 to Back in generic Python dialogs.
        # Honor the learned voice key here; Bluetooth owns opening the mic,
        # while USB uses the existing voice-input event path.
        if is_voice_key(action, self.voice_keys):
            if not self.recording:
                self.events.put(('voice', ''))
            return
        if identifier in BACK:
            self.cancelled.set()
        elif identifier in (3, 4) and xbmc.getCondVisibility('Control.HasFocus(500)'):
            # Native Up/Down moved one visual tile before this callback. Resolve
            # that movement as a whole-message/page step, not a hidden line stop.
            selected = xbmc.getInfoLabel('Container(500).CurrentItem')
            position = xbmc.getInfoLabel('Container(500).Position')
            index = int(selected) - 1 if selected.isdigit() else -1
            if 0 <= index < len(self.display_rows):
                direction = 1 if identifier == 4 else -1
                entering = index == self._chat_entry_line
                self._chat_entry_line = None
                origin = max(0, min(len(self.display_rows) - 1, index - direction))
                block = len(self.items) - 1 if entering else self.display_rows[origin]
                top = index - int(position) if position.isdigit() else index
                target = message_page(self.block_starts, len(self.display_rows), block, top, direction, entering)
                if target is None:
                    self.setFocusId(400)
                else:
                    first, last = target
                    # Select both bounds to ensure the entire short message (or
                    # page of a long one) is brought into the native viewport.
                    control = self.getControl(500)
                    for line in ((first, last) if direction > 0 else (last, first)):
                        control.selectItem(line)

    def onFocus(self, identifier):
        if identifier == 500:
            selected = xbmc.getInfoLabel('Container(500).CurrentItem')
            self._chat_entry_line = int(selected) - 1 if selected.isdigit() else None
        else:
            self._chat_entry_line = None

    def present(self, value):
        self.append_message('assistant', value['message'])
        self.idle()
        self.choices = value['choices']
        first_choice = len(self.rows)
        for row in self.choices:
            art = row.get('art') or {}
            poster = art.get('poster') or art.get('tvshow.poster') or row.get('thumbnail', '')
            self._add_block(row['label'], 'choice', str(row.get('year', '')) or row['value'][:72],
                            dict(row), poster)
        if self.choices:
            self._selected = first_choice
            self._select_dirty = True
        self._focus = 500 if self.choices else 400
        self._focus_dirty = True
        self.refresh()

    def append_message(self, role, text):
        if not text:
            return
        self.history.append((role, text))
        self._append_text('我' if role == 'user' else 'AI', text, role)

    def _append_text(self, label, text, role='activity'):
        self._add_block(label, role, text)
        self._selected = len(self.rows) - 1
        # Follow the end of new text even while focus stays on the buttons.
        # Selecting the block header only reveals its first line; the native
        # list has no reason to scroll the remaining body into view.
        self._line_selected = len(self.display_items) - 2  # Exclude trailing gap.
        self._line_block = self._selected
        self._select_dirty = True
        self.refresh()

    def _add_block(self, label, role, body, row=None, poster=''):
        block = len(self.items)
        item = xbmcgui.ListItem(label=label)
        item.setProperty('kind', 'choice' if role == 'choice' else 'message')
        item.setProperty('role', role)
        item.setProperty('body', body)
        item.setArt({'thumb': poster, 'poster': poster})
        self.items.append(item)
        self.rows.append(row)
        self.block_starts.append(len(self.display_items))
        if role == 'choice':
            lines = [('choice0', label), ('choice1', body), ('choice2', 'OK 选择')]
        else:
            lines = [('header', label)] + [('body', line) for line in message_lines(body, width=60 if role == 'user' else 84)]
        lines.append(('gap', ''))
        for part, text in lines:
            visual = xbmcgui.ListItem(label=text if part == 'header' else '')
            for key, value in (('block', str(block)), ('role', role), ('part', part),
                               ('body', text), ('kind', 'choice' if role == 'choice' else 'message')):
                visual.setProperty(key, value)
            visual.setArt({'thumb': poster, 'poster': poster})
            self.display_items.append(visual)
            self.display_rows.append(block)

    def activity(self, message):
        if not message or message == self.last_activity:
            return
        self.last_activity = message
        self._append_text('工作过程', message)
        if self.activity_sink:
            self.activity_sink(message)

    def restore(self, rounds):
        # Replace the visible session, including choices and work messages.
        self.history.clear(); self.rows.clear(); self.items.clear()
        self.display_items.clear(); self.display_rows.clear(); self.block_starts.clear()
        self.choices = []
        self.last_activity = self.last_status = None
        self._rendered = -1
        self._selected_block = None
        self._line_selected, self._line_block = 0, -1
        self._selected = 0
        self._focus = 400
        self._focus_dirty = self._select_dirty = True
        self.refresh()
        for row in rounds:
            self.append_message('user', row['user'])
            if isinstance(row.get('events'), list):
                for entry in row['events']:
                    if entry.get('role') in ('user', 'assistant'):
                        self.append_message(entry['role'], entry['text'])
                    elif entry.get('role') == 'activity':
                        self._append_text('工作过程', entry['text'])
            else:
                for message in row.get('activity', []):
                    if isinstance(message, str):
                        self._append_text('工作过程', message)
            answer = row.get('answer')
            if isinstance(answer, dict) and isinstance(answer.get('message'), str):
                self.present(answer)
            else:
                self._append_text('工作过程', '上次处理已中断。')

    def status(self, title, text=''):
        self.last_status = (title, text)
        self.refresh()

    def idle(self):
        self.busy = self.recording = False
        self.finish_requested.clear()
        self.status('上下浏览对话和推荐 · OK 选择推荐 · 语音键继续说话')


class ConversationProgress:
    """Capture/agent progress within the existing conversation, never a new dialog."""
    def __init__(self, window):
        self.window = window
        self.finish_requested = window.finish_requested
        self.embedded = True

    def create(self, title, message):
        self.window.busy = True
        self.finish_requested.clear()
        self.window._focus = 400
        self.window._focus_dirty = True
        self.window.status(title, message)

    def set_recording(self, enabled):
        self.window.recording = bool(enabled) and not self.finish_requested.is_set()
        self.window.refresh()

    def update(self, percent, message):
        title, _, text = message.partition('\n')
        self.window.status(title, text)

    def activity(self, message):
        self.window.activity(message)

    def iscanceled(self):
        return self.window.cancelled.is_set() or self.window.task_stop.is_set()

    def task_stopped(self):
        return self.window.task_stop.is_set() and not self.window.cancelled.is_set()

    def close(self):
        # The conversation owns window lifetime; keep transcript and focus intact.
        self.window.idle()

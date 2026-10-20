"""Collect a supplement on the UI thread while the agent worker keeps running."""
import queue
import xbmcgui
from ..inputs.registry import claim, pending
from .conversation import ConversationProgress


class LiveInput:
    def __init__(self, addon, profile, values, window, home, monitor, capture, cancel_speech=lambda: None):
        self.cancel_speech = cancel_speech
        self.addon, self.profile, self.values = addon, profile, values
        self.window, self.home, self.monitor, self.capture = window, home, monitor, capture

    def poll(self, drain):
        source = self.values['voice_input']
        token = pending(self.home, source) if source != 'usb' else ''
        usb = self.home.getProperty('VoiceAssistant.USBRecordRequested')
        try:
            action, value = self.window.events.get_nowait()
        except queue.Empty:
            action, value = '', ''
        if action in ('keyboard', 'text', 'answer') or token or (source == 'usb' and (usb or action == 'voice')):
            self.cancel_speech()
        if action == 'keyboard':
            title = '回答 Codex 的问题' if self.window.question_token else '补充当前任务'
            options = {'option': xbmcgui.ALPHANUM_HIDE_INPUT} if self.window.question_secret else {}
            return xbmcgui.Dialog().input(title, **options).strip()
        if action in ('text', 'answer'):
            return value
        if not (token or (source == 'usb' and (usb or action == 'voice'))):
            if action == 'voice':
                self.window.status('请轻按遥控器的语音键补充要求')
            return None
        self.home.clearProperty('VoiceAssistant.USBRecordRequested')
        self.window.accepting_input = False
        try:
            with claim(self.profile, source, self.home, self.monitor, token or None) as factory:
                if factory is not False:
                    if self.window.question_secret:
                        self.window.activity('此问题请用隐藏文字输入回答。')
                        return None
                    return self.capture(self.addon, self.profile, factory, self.values,
                                        progress=ConversationProgress(self.window), tick=drain)
        except Exception as error:
            self.window.activity('补充语音识别失败，请重试：' + str(error))
        finally:
            self.window.accepting_input = True
            self.window.busy = True
            self.home.setProperty('VoiceAssistant.State', 'thinking')
            self.window.refresh()

"""Best-effort speech IPC: speech failures must never fail the agent turn."""
from ..data_paths import data_path
import json
from pathlib import Path
import secrets
import socket


class Speech:
    def __init__(self, profile, values):
        self.path = str(data_path(Path(profile), 'speech/control.sock'))
        self.values = values
        self.enabled = values.get('tts_enabled') == 'on'
        self.token = secrets.token_hex(16)
        self.count = 0
        self.final_count = 0
        self.available = False
        if self.enabled:
            self.available = self.send('begin')

    def restart(self):
        self.stop()
        self.token = secrets.token_hex(16)
        self.count = 0
        self.final_count = 0
        self.available = self.send('begin') if self.enabled else False

    def send(self, op, **extra):
        if not self.enabled: return False
        try:
            data = (json.dumps(dict(op=op, token=self.token, **extra), ensure_ascii=False) + '\n').encode()
            if len(data) > 32768: return False
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(.25); connection.connect(self.path); connection.sendall(data)
                return b'"ok":true' in connection.recv(100)
        except (OSError, ValueError, TypeError):
            return False

    def say(self, row, kind='final'):
        if kind != 'final':
            from .text import commentary_allowed
            if self.values.get('tts_scope') != 'all' or not commentary_allowed(row.get('text', '')): return
        if self.available and self.send('say', row=row):
            self.count += 1
            if kind == 'final': self.final_count += 1

    def finish(self, fallback=''):
        if self.available:
            if not self.final_count and fallback:
                from .text import chunks
                for text in chunks(fallback): self.say({'text': text, 'pronunciations': []})
            self.send('finish')

    def stop(self):
        if self.available: self.send('stop')
        self.available = False

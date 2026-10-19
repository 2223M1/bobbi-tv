"""Turn-scoped client; closing a completed stream keeps model weights resident."""
import json
from pathlib import Path
from ..data_paths import data_path
import select
import socket
import struct
import time
from .text import display_text


class Recognizer:
    def __init__(self, profile, model, cancelled=lambda: False):
        self.cancelled = cancelled
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.buffer = bytearray()
        self.finished = False
        self.is_endpoint = False
        try:
            self.socket.settimeout(2)
            self.socket.connect(str(data_path(profile, 'asr/control.sock')))
            self.socket.sendall((json.dumps({'model': model}) + '\n').encode())
            self.ready = self.read(125)
        except BaseException:
            self.close(); raise

    def read(self, timeout=95):
        deadline = time.monotonic() + timeout
        while True:
            if self.cancelled(): raise InterruptedError('识别已取消。')
            if b'\n' in self.buffer:
                line, _, self.buffer = self.buffer.partition(b'\n')
                value = json.loads(line)
                if value.get('error'): raise ValueError(value['error'])
                return value
            if time.monotonic() >= deadline: raise ValueError('本地识别超时。')
            if select.select([self.socket], [], [], .05)[0]:
                data = self.socket.recv(8192)
                if not data: raise ValueError('本地识别服务已断开。')
                self.buffer.extend(data)
                if len(self.buffer) > 128 * 1024: raise ValueError('识别响应过长。')

    def exchange(self, pcm):
        self.socket.sendall(struct.pack('<I', len(pcm)) + pcm)
        result = self.read()
        return display_text(result['result']['text'])

    def accept(self, pcm):
        if self.finished or len(pcm) % 2 or len(pcm) > 32000:
            raise ValueError('识别音频格式无效。')
        return self.exchange(pcm) if pcm else ''

    def finish(self):
        if self.finished: raise ValueError('识别已经结束。')
        self.finished = True
        return self.exchange(b'')

    def close(self):
        self.socket.close()

    def __enter__(self): return self
    def __exit__(self, *unused): self.close()

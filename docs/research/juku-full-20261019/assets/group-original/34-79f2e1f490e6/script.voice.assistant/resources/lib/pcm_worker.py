"""Streaming PCM upload and final sentence result, with bounded cancellation."""
import json
import os
from pathlib import Path
import select
import shutil
import struct
import subprocess
import time
import signal

class PcmWorkerRecognizer:
    def __init__(self, addon_root, worker, config, label, timeout=20,
                 cancelled=lambda: False, process_factory=subprocess.Popen, own_group=False):
        self.label, self.own_group = label, own_group
        self.cancelled = cancelled
        self.timeout = max(5, min(60, int(timeout)))
        self.process = None
        self.buffer = bytearray()
        self.ready = self.final = False
        self.text = self.log_id = ''
        self.audio_bytes = 0
        self.finished = False
        python = shutil.which('python3')
        if not python:
            raise RuntimeError('系统没有 python3，无法连接{}。'.format(self.label))
        try:
            self.process = process_factory([python, '-X', 'utf8', '-u',
                str(Path(addon_root) / 'resources/lib' / worker)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, start_new_session=own_group)
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
            self._send(json.dumps(config).encode('utf-8') + b'\n')
            self._wait(lambda: self.ready)
        except BaseException:
            self.close()
            raise

    def _check(self):
        if self.cancelled():
            raise InterruptedError('已取消{}识别。'.format(self.label))

    def _poll(self):
        self._check()
        while select.select([self.process.stdout], [], [], 0)[0]:
            chunk = os.read(self.process.stdout.fileno(), 8192)
            if not chunk:
                if not self.final:
                    raise RuntimeError('{}识别进程提前结束。'.format(self.label))
                break
            self.buffer.extend(chunk)
            if len(self.buffer) > 65536:
                raise RuntimeError('{}识别进程返回的数据过大。'.format(self.label))
            while b'\n' in self.buffer:
                line, _, remainder = self.buffer.partition(b'\n')
                self.buffer = bytearray(remainder)
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeError):
                    raise RuntimeError('{}识别进程返回格式无效。'.format(self.label)) from None
                if not isinstance(value, dict):
                    raise RuntimeError('{}识别进程返回格式无效。'.format(self.label))
                kind = value.get('type')
                if kind == 'error':
                    raise RuntimeError(value['error'])
                if kind == 'ready':
                    self.ready = True
                    self.log_id = value.get('log_id', '')
                elif kind == 'result':
                    self.text = value.get('text', '')
                    if not isinstance(self.text, str) or len(self.text) > 4000:
                        raise RuntimeError('{}识别文字无效。'.format(self.label))
                    self.final = bool(value.get('last'))
        if self.process.poll() is not None and not self.final:
            raise RuntimeError('{}识别进程提前结束。'.format(self.label))

    def _send(self, data):
        deadline, offset = time.monotonic() + self.timeout, 0
        while offset < len(data):
            self._poll()
            if time.monotonic() >= deadline:
                raise RuntimeError('{}上传超时，请检查网络。'.format(self.label))
            readable, writable, _ = select.select([self.process.stdout], [self.process.stdin], [], .05)
            if readable:
                self._poll()
            if writable:
                try:
                    offset += os.write(self.process.stdin.fileno(), data[offset:])
                except BlockingIOError:
                    continue
                except BrokenPipeError:
                    self._poll()
                    raise RuntimeError('{}上传连接已关闭。'.format(self.label)) from None

    def _wait(self, complete):
        deadline = time.monotonic() + self.timeout
        while not complete():
            self._poll()
            if complete():
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('{}识别超时，请稍后再试。'.format(self.label))
            select.select([self.process.stdout], [], [], .05)
        self._check()

    def accept(self, pcm):
        self._check()
        if self.finished or len(pcm) % 2 or len(pcm) > 6400:
            raise ValueError('{}音频输入无效。'.format(self.label))
        self.audio_bytes += len(pcm)
        if self.audio_bytes > 30 * 32000:
            raise ValueError('{}单次录音不能超过 30 秒。'.format(self.label))
        if pcm and not self.final:
            self._send(struct.pack('>I', len(pcm)) + pcm)
        self._poll()
        return ''  # Sentence mode publishes its final result after capture.

    def finish(self):
        self.finished = True
        if not self.final:
            self._send(struct.pack('>I', 0))
        self._wait(lambda: self.final)
        return self.text

    def transcribe(self, pcm, cancelled=lambda: False, update=lambda *args: None):
        for offset in range(0, len(pcm), 3200):
            if cancelled():
                raise InterruptedError('已取消{}识别。'.format(self.label))
            self.accept(pcm[offset:offset + 3200])
            update(min(100, int((offset + 3200) * 100 / max(1, len(pcm)))))
        return self.finish()

    def close(self):
        if self.process is not None:
            if self.own_group:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=2)
            self.process.stdin.close()
            self.process.stdout.close()
            self.process = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

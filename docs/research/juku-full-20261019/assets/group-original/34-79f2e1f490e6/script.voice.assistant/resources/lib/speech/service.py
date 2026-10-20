"""Service-owned synthesis queue and direct audio output, isolated from microphone input."""
from ..data_paths import data_path
from collections import deque
import json
from pathlib import Path
import queue
import socketserver
import threading
import tempfile
import time
from .engine import Engine
from .text import chunks, encode
from ..dependencies.catalog import preload_delay, installed


class Stream:
    def __init__(self, token, directory):
        self.token = token
        self.audio = tempfile.TemporaryFile(dir=directory)
        self.condition = threading.Condition()
        self.size = 0
        self.cancelled = threading.Event()
        self.ready = threading.Event()
        self.finished = False
        self.started = False
        self.created = time.monotonic()
        self.first_audio_seconds = None

    def put(self, data):
        with self.condition:
            if self.cancelled.is_set(): return
            if data is None:
                self.finished = True
            else:
                self.audio.seek(self.size); self.audio.write(data); self.audio.flush()
                self.size += len(data)
                if self.first_audio_seconds is None:
                    self.first_audio_seconds = time.monotonic() - self.created
                self.ready.set()
            self.condition.notify_all()

    def read(self, offset, timeout=None):
        with self.condition:
            while offset >= self.size and not self.finished and not self.cancelled.is_set():
                self.condition.wait(.2 if timeout is None else timeout)
                if timeout is not None and offset >= self.size and not self.finished and not self.cancelled.is_set():
                    return None
            if self.cancelled.is_set() or offset >= self.size: return b''
            self.audio.seek(offset)
            return self.audio.read(min(16384, self.size - offset))

    def close(self):
        with self.condition:
            self.cancelled.set(); self.condition.notify_all(); self.audio.close()


class Service:
    def __init__(self, root, profile, output, media_active, log=lambda message: None):
        self.root, self.profile = Path(root), Path(profile)
        self.engine = Engine(root, profile)
        self.preload_at = time.monotonic() + preload_delay()
        self.output, self.media_active, self.log = output, media_active, log
        self.values = {}
        self.current = None
        self.commands = queue.Queue(256)
        self.jobs = deque()
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.closed = threading.Event()
        self.enabled = False
        self.error = ''
        self.retry_after = 0
        service = self

        class Control(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(.5)
                line = self.rfile.readline(32769)
                if len(line) > 32768: return
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict): return
                    service.commands.put_nowait(value)
                    self.wfile.write(b'{"ok":true}\n')
                except (ValueError, queue.Full, OSError):
                    return

        class Unix(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        directory = data_path(Path(profile), 'speech')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700); directory.chmod(0o700)
        self.path = directory / 'control.sock'
        self.path.unlink(missing_ok=True)
        self.control = Unix(str(self.path), Control); self.path.chmod(0o600)
        self.threads = [threading.Thread(target=self.control.serve_forever, kwargs={'poll_interval':.1}, daemon=True)]
        self.worker = threading.Thread(target=self.work, name='matcha-speech', daemon=True)
        for thread in self.threads: thread.start()
        self.worker.start()

    def stop(self, reason='requested'):
        stream = self.current
        if stream:
            self.log('朗读结束：' + reason + ', pcm_bytes=' + str(stream.size))
            stream.close()
        self.output.stop()
        with self.lock:
            self.jobs.clear()
        self.current = None
        self.wake.set()

    def tick(self, values, recording=False):
        enabled = values.get('tts_enabled') == 'on'
        self.values = dict(values)
        if enabled != self.enabled:
            self.enabled = enabled
            self.stop()
            if not enabled: self.engine.close()
            self.wake.set()
        if recording: self.stop('microphone')
        for _ in range(128):
            try: request = self.commands.get_nowait()
            except queue.Empty: break
            token = request.get('token')
            if not isinstance(token, str) or len(token) != 32: continue
            op = request.get('op')
            if op == 'begin':
                self.stop()
                if self.enabled and not recording and not self.media_active():
                    self.current = Stream(token, self.path.parent)
                    self.log('朗读会话已接收')
                else:
                    self.log('朗读会话未启动：' + ('disabled' if not self.enabled else
                             'microphone' if recording else 'media'))
            elif self.current and token == self.current.token:
                if op == 'stop': self.stop()
                elif op in ('say', 'finish'):
                    with self.lock:
                        if op == 'finish' or len(self.jobs) < 128:
                            self.jobs.append((self.current, request.get('row') if op == 'say' else None, dict(values)))
                    self.wake.set()
        stream = self.current
        if not stream: return
        if stream.cancelled.is_set():
            self.stop(); return
        if self.media_active():
            self.stop('media'); return
        try:
            if stream.started:
                result = self.output.poll(relative_volume=values.get('tts_volume', 50))
                if result:
                    if result != 'ended': self.log('直接音频输出失败：' + result)
                    self.stop(result)
            elif stream.ready.is_set():
                self.output.start(stream, lead_in=float(values.get('tts_lead_in', '1.0')), rate=self.engine.rate,
                                  relative_volume=values.get('tts_volume', 50))
                stream.started = time.monotonic()
                self.log('开始直接朗读：' + self.output.device)
            elif stream.finished:
                self.stop('empty')
            elif time.monotonic() - stream.created > 180:
                self.stop('timeout')
        except Exception as error:
            self.log('直接音频输出失败：' + str(error))
            self.stop('output_error')

    def work(self):
        while not self.closed.is_set():
            self.wake.wait(.1); self.wake.clear()
            if not self.enabled or time.monotonic() < self.retry_after: continue
            if not all(installed(self.root, self.profile, name)
                       for name in ('onnx-runtime', 'matcha-bilingual')):
                continue
            if time.monotonic() < self.preload_at and self.current is None:
                continue
            stream = None
            try:
                self.engine.start()  # Warm once, even before the first response.
                if not self.enabled:
                    self.engine.close(); continue
                with self.lock:
                    job = self.jobs.popleft() if self.jobs else None
                if not job: continue
                stream, row, values = job
                if stream.cancelled.is_set(): continue
                if row is None:
                    stream.put(None); continue
                if not isinstance(row, dict): continue
                text = encode(row, self.engine.mapping, values.get('tts_ai_pronunciation') == 'on')
                pause = round(float(values.get('tts_pause', '1.0')) * 100)
                for part in chunks(text):
                    if stream.cancelled.is_set() or self.closed.is_set(): break
                    pcm = self.engine.synthesize(part, pause)
                    if not stream.cancelled.is_set(): stream.put(pcm)
                self.wake.set()
            except Exception as error:
                if not self.enabled or self.closed.is_set():
                    self.engine.close(); continue
                self.error = type(error).__name__
                self.log('语音合成暂不可用：' + self.error)
                if stream: stream.cancelled.set()
                self.engine.close()
                self.retry_after = time.monotonic() + 10

    def close(self):
        self.closed.set(); self.enabled = False
        self.stop(); self.engine.close(); self.wake.set()
        self.worker.join(timeout=3)
        self.control.shutdown(); self.control.server_close()
        self.path.unlink(missing_ok=True)

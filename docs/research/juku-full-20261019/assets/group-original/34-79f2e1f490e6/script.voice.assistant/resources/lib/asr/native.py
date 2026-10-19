"""Framed PCM protocol to the persistent, isolated sherpa-onnx worker."""
import json
import os
import select
import struct
import subprocess
import time
from ..dependencies.catalog import catalog, native_command, require
from .text import display_text


def command(root, profile, model_id):
    model = catalog(str(root))['asr_models'][model_id]
    directory = require(root, profile, model['component'])
    networks = [str(directory / name) for name in model['networks']]
    networks += [''] * (3 - len(networks))
    method = 'modified_beam_search' if model['family'] == 'zipformer' else 'greedy_search'
    return native_command(root, profile, 'asr-worker') + [model['family'], *networks,
        str(directory / 'tokens.txt'), str(model['threads']), method, '']


class Native:
    def __init__(self, arguments, cancelled=lambda: False, *, decoding=None):
        self.cancelled = cancelled
        self.buffer = bytearray()
        environment = dict(os.environ, LC_ALL='C', LANG='C')
        for key in ('VOICE_ASR_MAX_ACTIVE_PATHS', 'VOICE_ASR_HOTWORDS_SCORE'):
            environment.pop(key, None)
        if decoding is not None:
            environment['VOICE_ASR_MAX_ACTIVE_PATHS'] = str(decoding['max_active_paths'])
            environment['VOICE_ASR_HOTWORDS_SCORE'] = str(decoding['hotwords_score'])
        self.process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0, start_new_session=True,
            env=environment)
        try:
            self.ready = self.read(120)
            if not self.ready.get('ready'):
                raise ValueError('语音模型未能加载。')
        except BaseException:
            self.close(); raise

    def read(self, timeout=90):
        deadline = time.monotonic() + timeout
        while True:
            if self.cancelled():
                raise InterruptedError('识别已取消。')
            if b'\n' in self.buffer:
                line, _, self.buffer = self.buffer.partition(b'\n')
                return json.loads(line)
            if time.monotonic() >= deadline:
                raise ValueError('本地识别超时。')
            if select.select([self.process.stdout], [], [], .05)[0]:
                data = os.read(self.process.stdout.fileno(), 8192)
                if not data:
                    raise ValueError('本地识别进程已退出。')
                self.buffer.extend(data)
                if len(self.buffer) > 128 * 1024:
                    raise ValueError('本地识别响应无效。')

    def exchange(self, data=b'', reset=False):
        payload = memoryview(struct.pack('<I', 0xffffffff if reset else len(data)) + data)
        deadline = time.monotonic() + 10
        while payload:
            if self.cancelled():
                raise InterruptedError('识别已取消。')
            if time.monotonic() >= deadline:
                raise ValueError('本地识别音频写入超时。')
            if select.select([], [self.process.stdin], [], .05)[1]:
                count = os.write(self.process.stdin.fileno(), payload[:8192])
                if not count: raise ValueError('本地识别音频写入失败。')
                payload = payload[count:]
        return self.read()

    def close(self):
        process = self.process
        if process.poll() is None:
            try: process.terminate()
            except ProcessLookupError: pass
            try: process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=2)
        for source in (process.stdin, process.stdout):
            if source: source.close()

"""A single resident ARM64 worker; Kodi's ARM32 interpreter never loads ONNX."""
from ..data_paths import data_path
import hashlib
import os
from pathlib import Path
import select
import struct
import subprocess
import threading
import time
from .text import phoneme_map
from ..dependencies.catalog import require, native_command


class Engine:
    def __init__(self, root, profile):
        self.root, self.profile = Path(root), Path(profile)
        self.process = None
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.rate = 16000
        self.mapping = {}

    def start(self):
        if self.process and self.process.poll() is None:
            return
        model = require(self.root, self.profile, 'matcha-bilingual')
        tokens = (model / 'tokens.txt').read_text(encoding='utf-8')
        self.mapping = phoneme_map(tokens)
        data = (model / 'lexicon.txt').read_text(encoding='utf-8')
        data += '\n' + '\n'.join(char + ' ' + phone for phone, char in self.mapping.items()) + '\n'
        directory = data_path(self.profile, 'speech')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        lexicon = directory / 'phoneme-transport.txt'
        digest = hashlib.sha256(data.encode()).hexdigest()
        if not lexicon.exists() or hashlib.sha256(lexicon.read_bytes()).hexdigest() != digest:
            temporary = lexicon.with_suffix('.tmp')
            temporary.write_text(data, encoding='utf-8'); temporary.chmod(0o600); temporary.replace(lexicon)
        command = native_command(self.root, self.profile, 'matcha-worker') + [
                   str(model / 'model.onnx'), str(model / 'vocos.onnx'), str(lexicon), str(model / 'tokens.txt'),
                   ','.join(str(model / name) for name in ('phone.fst','date.fst','number.fst')), '4',
                   str(model / 'espeak-ng-data')]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=dict(os.environ, LC_ALL='C', LANG='C'), start_new_session=True)
        try:
            self.rate = struct.unpack('<I', self._read(4, 45))[0]
            if self.rate != 16000:
                raise RuntimeError('Matcha 采样率不匹配。')
            self.ready.set()
        except Exception:
            self.close(); raise

    def _read(self, count, timeout=30):
        process = self.process
        if not process:
            raise InterruptedError('语音合成已关闭。')
        deadline = time.monotonic() + timeout
        output = bytearray()
        while len(output) < count:
            if self.process is not process or time.monotonic() > deadline:
                raise RuntimeError('Matcha 合成超时或已取消。')
            readable, _, _ = select.select([process.stdout], [], [], .1)
            if readable:
                data = os.read(process.stdout.fileno(), min(65536, count - len(output)))
                if not data:
                    raise RuntimeError('Matcha 合成进程已退出。')
                output.extend(data)
        return bytes(output)

    def synthesize(self, text, pause):
        with self.lock:
            self.start()
            payload = text.encode('utf-8')
            if not 0 < len(payload) <= 8192:
                raise ValueError('朗读片段过长。')
            self.process.stdin.write(struct.pack('<II', len(payload), pause) + payload)
            self.process.stdin.flush()
            size = struct.unpack('<I', self._read(4))[0]
            if not 0 < size <= self.rate * 2 * 60 or size % 2:
                self.close(); raise RuntimeError('Matcha 音频数据无效。')
            return self._read(size)

    def close(self):
        self.ready.clear()
        process, self.process = self.process, None
        if process:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=.3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()

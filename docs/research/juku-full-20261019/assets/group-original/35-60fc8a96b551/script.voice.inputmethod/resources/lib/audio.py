"""16 kHz mono S16_LE capture through CoreELEC's existing libasound."""
from array import array
import ctypes
import errno
import math
from pathlib import Path
import re
import sys
import time

RATE = 16000
CHUNK_FRAMES = 1600


class AudioError(RuntimeError):
    pass


def usb_capture_devices(proc=Path('/proc/asound')):
    """Use card IDs, never assume the USB dongle remains card number 1."""
    devices = []
    for card in sorted(proc.glob('card[0-9]*')):
        if not (card / 'usbid').exists() and not (card / 'stream0').exists():
            continue
        try:
            identifier = (card / 'id').read_text().strip()
        except OSError:
            continue
        for pcm in sorted(card.glob('pcm*c')):
            match = re.fullmatch(r'pcm(\d+)c', pcm.name)
            if match:
                devices.append('plughw:CARD={},DEV={}'.format(identifier, match.group(1)))
    return devices


class AlsaCapture:
    def __init__(self, device):
        self.device = device
        self.handle = ctypes.c_void_p()
        try:
            self.lib = ctypes.CDLL('libasound.so.2')
        except OSError as exc:
            raise AudioError('无法加载系统录音库 libasound.so.2：{}'.format(exc)) from exc
        signatures = {
            'snd_pcm_open': ([ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            'snd_pcm_set_params': ([ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_uint], ctypes.c_int),
            'snd_pcm_readi': ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong], ctypes.c_long),
            'snd_pcm_prepare': ([ctypes.c_void_p], ctypes.c_int),
            'snd_pcm_start': ([ctypes.c_void_p], ctypes.c_int),
            'snd_pcm_close': ([ctypes.c_void_p], ctypes.c_int),
            'snd_strerror': ([ctypes.c_int], ctypes.c_char_p),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        # CAPTURE=1, NONBLOCK=1; S16_LE=2, RW_INTERLEAVED=3.
        self._check(self.lib.snd_pcm_open(ctypes.byref(self.handle), device.encode(), 1, 1))
        try:
            self._check(self.lib.snd_pcm_set_params(self.handle, 2, 3, 1, RATE, 1, 200000))
            # set_params defaults to a start threshold equal to the entire
            # buffer. Our smaller nonblocking reads must start capture explicitly.
            self._check(self.lib.snd_pcm_start(self.handle))
        except Exception:
            self.close()
            raise
        self.buffer = ctypes.create_string_buffer(CHUNK_FRAMES * 2)

    def _check(self, result):
        if result < 0:
            reason = self.lib.snd_strerror(result).decode('utf-8', 'replace')
            raise AudioError('麦克风 {}：{}'.format(self.device, reason))
        return result

    def read(self):
        frames = self.lib.snd_pcm_readi(self.handle, self.buffer, CHUNK_FRAMES)
        if frames == -errno.EAGAIN:
            return b''
        if frames == -errno.EPIPE:
            self._check(self.lib.snd_pcm_prepare(self.handle))
            self._check(self.lib.snd_pcm_start(self.handle))
            return b''
        self._check(frames)
        return self.buffer.raw[:frames * 2]

    def close(self):
        if self.handle:
            self.lib.snd_pcm_close(self.handle)
            self.handle = ctypes.c_void_p()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


def open_microphone(configured=''):
    devices = [configured] if configured else usb_capture_devices()
    if not devices:
        raise AudioError('没有找到 USB 麦克风。请连接遥控器的 USB 接收器，或在插件设置中指定 ALSA 录音设备。蓝牙按键连接本身不代表麦克风可用。')
    failures = []
    for device in devices:
        try:
            return AlsaCapture(device)
        except AudioError as exc:
            failures.append(str(exc))
    raise AudioError('\n'.join(failures))


def rms(pcm, centered=False):
    samples = array('h')
    samples.frombytes(pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    if not samples:
        return 0.0
    energy = sum(value * value for value in samples) / len(samples)
    if centered:
        energy -= (sum(samples) / len(samples)) ** 2
    return math.sqrt(max(0.0, energy))


class SpeechGate:
    """Ignore brief clicks; stop after speech followed by configurable silence."""
    def __init__(self, threshold=200, silence_seconds=1.0, start_timeout=6.0, max_seconds=10.0,
                 startup_seconds=0.0, recognizer_endpoint=False, adaptive_noise=False):
        self.threshold = threshold
        self.silence_seconds = silence_seconds
        self.start_timeout = start_timeout
        self.max_seconds = max_seconds
        self.startup_seconds = max(0.0, startup_seconds)
        self.recognizer_endpoint = recognizer_endpoint
        self.adaptive_noise = adaptive_noise
        self.noise_levels = []
        self.effective_threshold = threshold
        self.elapsed = 0.0
        self.active = 0.0
        self.quiet = 0.0
        self.speech = False

    def feed(self, pcm):
        duration = len(pcm) / (RATE * 2)
        # UR02 can have a large DC offset. Measure AC energy for its cloud
        # stop decision only; preserve the exact original PCM for recognition.
        level = rms(pcm, centered=self.adaptive_noise)
        self.elapsed += duration
        if self.elapsed <= self.startup_seconds:
            if self.adaptive_noise:
                self.noise_levels.append(level)
                floor = sorted(self.noise_levels)[len(self.noise_levels) // 2]
                self.effective_threshold = max(self.threshold, min(1200.0, floor * 1.8))
            # Some Bluetooth microphones produce a sustained transient when
            # opening. It must not count as speech followed by silence. The
            # caller still queues every PCM sample for recognition.
            self.active = self.quiet = 0.0
            return level, self.elapsed >= self.max_seconds
        if level >= self.effective_threshold:
            self.active += duration
            self.quiet = 0.0
            if self.active >= 0.15:
                self.speech = True
        else:
            self.quiet += duration
            # USB packets are often only 10 ms long. Brief low-energy gaps
            # within a syllable must not reset all accumulated speech evidence.
            if self.quiet >= 0.12:
                self.active = 0.0
        done = (self.elapsed >= self.max_seconds or
                (not self.recognizer_endpoint and self.speech and self.quiet >= self.silence_seconds) or
                (not self.speech and self.elapsed >= self.start_timeout))
        return level, done


def record(source, gate, cancelled=lambda: False, update=lambda *args: None,
           on_audio=lambda *args: None, finished=lambda: False):
    chunks = []
    total_bytes = 0
    start = last_data = time.monotonic()
    deadline = start + gate.max_seconds + 2.0
    key_controlled = getattr(source, 'key_controlled', False)
    while time.monotonic() < deadline:
        if cancelled():
            return b''
        if finished():
            break
        pcm = source.read()
        now = time.monotonic()
        if not pcm:
            if getattr(source, 'eof', False):
                break
            # Some remote dongles stop sending USB packets when the voice key
            # is released, rather than supplying zero-filled silence. Preserve
            # the captured phrase and treat that gap as end-of-speech.
            if not key_controlled and gate.speech and now - last_data >= gate.silence_seconds:
                break
            if not gate.speech and now - start >= gate.start_timeout:
                break
            update(0.0, now - start, gate.speech)
            time.sleep(0.01)
            continue
        last_data = now
        # Bound allocation even if a source supplies oversized chunks.
        remaining = max(0, int(gate.max_seconds * RATE * 2) - total_bytes)
        pcm = pcm[:remaining - remaining % 2]
        chunks.append(pcm)
        total_bytes += len(pcm)
        level, done = gate.feed(pcm)
        if key_controlled:
            # CMCC release explicitly ends the stream; pauses while the key is
            # held must not cut a phrase or stop its microphone prematurely.
            done = gate.elapsed >= gate.max_seconds
        on_audio(pcm, gate.speech)
        update(level, gate.elapsed, gate.speech)
        if done or total_bytes >= int(gate.max_seconds * RATE * 2) or (not key_controlled and not gate.speech and now - start >= gate.start_timeout):
            break
    return b''.join(chunks) if gate.speech and not cancelled() else b''

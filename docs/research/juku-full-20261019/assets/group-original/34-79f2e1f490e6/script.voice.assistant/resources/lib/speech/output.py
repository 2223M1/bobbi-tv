"""Stream PCM to Kodi's selected ALSA device without using its media player."""
from array import array
from functools import lru_cache
import json
import math
import os
import random
import select
import subprocess
import sys
import tempfile
import threading
import time


def alsa_device(setting):
    if not isinstance(setting, str) or not setting.startswith('ALSA:'):
        raise ValueError('直接朗读需要 Kodi 使用 ALSA 音频输出。')
    # Kodi appends a display name after |; the part before it is the PCM name.
    device = setting[5:].split('|', 1)[0]
    if not device or len(device) > 512 or any(ord(c) < 32 for c in device):
        raise ValueError('Kodi 音频输出设备无效。')
    # plug converts Matcha's 22.05 kHz mono PCM to the selected device format.
    return 'plug:{SLAVE=' + json.dumps(device, ensure_ascii=False) + '}'


def scale_pcm(data, gain):
    if gain >= 1: return data
    if gain <= 0: return b'\0' * len(data)
    samples = array('h')
    samples.frombytes(data)
    if sys.byteorder != 'little': samples.byteswap()
    for index, value in enumerate(samples): samples[index] = round(value * gain)
    if sys.byteorder != 'little': samples.byteswap()
    return samples.tobytes()


def kodi_volume_gain(volume, muted=False):
    """Match Kodi AEUtil::PercentToGain/GainToScale's 60 dB volume range."""
    percent = max(0, min(100, float(volume)))
    if muted or percent <= 0:
        return 0.0
    gain = 10 ** ((percent / 100 - 1) * 3)
    return 1.0 if gain >= .99 else gain


def wake_noise(seconds=1.0, rate=22050):
    """Kodi-style low-level Gaussian noise as mono S16LE."""
    return _wake_noise(round(rate * seconds))


@lru_cache(maxsize=8)
def _wake_noise(frames):
    # ActiveAESink::GenerateNoise uses a normalized standard deviation of 1e-5
    # (about -100 dBFS), not a low-frequency tone. Quantize only at the end so
    # sub-LSB floating-point samples do not all become zero by truncation.
    rng = random.Random()
    samples = array('h', (round(rng.gauss(0, 32768 * 0.00001)) for _ in range(frames)))
    if sys.byteorder != 'little': samples.byteswap()
    return samples.tobytes()


class AlsaOutput:
    def __init__(self, rpc, suspend, resume):
        self.rpc, self.suspend, self.resume = rpc, suspend, resume
        self.process = None
        self.thread = None
        self.stream = None
        self.stderr = None
        self.configuration = None
        self.suspended = False
        self.cancelled = threading.Event()
        self.done = threading.Event()
        self.error = ''
        self.device = ''
        self.gain = 1
        self.relative_volume = 50
        self.lead_in = 1.0
        self.rate = 22050
        self.next_volume = 0
        self.bytes_written = 0
        self.open_retries = 0
        self.process_lock = threading.Lock()

    def volume(self, relative_volume=None):
        if relative_volume is not None:
            percent = float(relative_volume)
            if not math.isfinite(percent) or not 0 <= percent <= 100:
                raise ValueError('播报相对音量必须在 0 到 100 之间。')
            self.relative_volume = percent
        values = self.rpc('Application.GetProperties', {'properties': ['volume', 'muted']})
        self.gain = kodi_volume_gain(values['volume'], values['muted']) * self.relative_volume / 100
        self.next_volume = time.monotonic() + .25

    def start(self, stream, lead_in=1.0, rate=22050, relative_volume=50):
        self.stop()
        if rate not in (16000, 22050):
            raise ValueError('朗读采样率无效。')
        self.rate = rate
        self.lead_in = float(lead_in)
        if not 0 <= self.lead_in <= 5:
            raise ValueError('音频唤醒时长必须在 0 到 5 秒之间。')
        self.device = alsa_device(self.rpc('Settings.GetSettingValue',
            {'setting': 'audiooutput.audiodevice'})['value'])
        self.volume(relative_volume)
        self.cancelled.clear(); self.done.clear()
        self.error = ''; self.bytes_written = 0
        self.open_retries = 0
        self.stream = stream
        try:
            # The Amlogic PCM accepts mono even when the HDMI receiver stays
            # silent. Convert explicitly to TV-compatible stereo at 48 kHz.
            # This configuration is private to aplay, not a system ALSA change.
            base = os.environ.get('ALSA_CONFIG_PATH') or '/usr/share/alsa/alsa.conf'
            if any(c in base for c in '\r\n<>'):
                raise ValueError('ALSA 配置路径无效。')
            config = ('<' + base + '>\npcm.!voice_assistant {\n'
                      ' type plug\n slave { pcm ' + json.dumps(self.device, ensure_ascii=False) +
                      ' rate 48000 channels 2 format S16_LE }\n route_policy duplicate\n}\n')
            self.configuration = tempfile.TemporaryFile()
            self.configuration.write(config.encode('utf-8')); self.configuration.flush()
            # Always balance this, including a failed suspend/open/spawn.
            self.suspended = True
            self.suspend()
            self.stderr = tempfile.TemporaryFile()
            self.spawn()
            self.thread = threading.Thread(target=self.feed, name='speech-alsa', daemon=True)
            self.thread.start()
        except Exception:
            self.stop()
            raise

    def spawn(self):
        with self.process_lock:
            if self.cancelled.is_set(): return
            self.stderr.seek(0); self.stderr.truncate()
            config_fd = self.configuration.fileno()
            self.process = subprocess.Popen(['aplay', '-q', '-D', 'voice_assistant',
                '-t', 'raw', '-f', 'S16_LE', '-r', str(self.rate), '-c', '1',
                '--buffer-time=100000', '--period-time=25000'],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.stderr,
                bufsize=0, start_new_session=True, pass_fds=(config_fd,),
                env=dict(os.environ, LC_ALL='C', ALSA_CONFIG_PATH='/proc/self/fd/' + str(config_fd)))
            os.set_blocking(self.process.stdin.fileno(), False)

    def transfer(self, process, stream):
        # Like Kodi's sink keepalive, use a fixed, extremely low noise floor;
        # scaling it again after S16 quantization would erase it at low volume.
        # Respect mute/zero volume and cancellation even during the preamble.
        noise = wake_noise(self.lead_in, self.rate)
        block = round(self.rate / 10) * 2
        for start in range(0, len(noise), block):
            if self.cancelled.is_set(): return
            chunk = noise[start:start + block]
            self.write_pcm(process, chunk if self.gain > 0 else b'\0' * len(chunk))
        offset = 0
        while not self.cancelled.is_set():
            if process.poll() is not None: raise RuntimeError(self.failure())
            data = stream.read(offset, timeout=.2)
            if data is None: continue
            if not data: break
            offset += len(data)
            self.write_pcm(process, scale_pcm(data, self.gain))
        if not self.cancelled.is_set():
            process.stdin.close()
            if process.wait(timeout=5): raise RuntimeError(self.failure())

    def write_pcm(self, process, data):
        data = memoryview(data)
        deadline = time.monotonic() + 5
        while data and not self.cancelled.is_set():
            if process.poll() is not None: raise RuntimeError(self.failure())
            if time.monotonic() > deadline: raise TimeoutError('ALSA 写入超时。')
            if not select.select([], [process.stdin], [], .05)[1]: continue
            try: count = os.write(process.stdin.fileno(), data)
            except BlockingIOError: continue
            data = data[count:]
            self.bytes_written += count
            deadline = time.monotonic() + 5

    def feed(self):
        stream = self.stream
        deadline = time.monotonic() + 2
        try:
            while not self.cancelled.is_set():
                process = self.process
                try:
                    self.transfer(process, stream)
                    break
                except Exception:
                    # Kodi's suspend request is asynchronous. EBUSY occurs
                    # before aplay reads PCM, so retrying from offset 0 is safe.
                    if self.cancelled.is_set(): break
                    detail = self.failure()
                    if 'Device or resource busy' not in detail or time.monotonic() >= deadline:
                        raise
                    process.wait(timeout=.2); process.stdin.close()
                    if self.cancelled.wait(.05): break
                    self.open_retries += 1
                    self.bytes_written = 0
                    self.spawn()
        except Exception as error:
            if not self.cancelled.is_set(): self.error = type(error).__name__ + ': ' + str(error)
        finally:
            self.done.set()

    def failure(self):
        if self.stderr:
            self.stderr.seek(0)
            detail = self.stderr.read(1024).decode('utf-8', errors='replace').strip()
            if detail: return 'ALSA 输出失败：' + detail
        return 'ALSA 输出进程提前退出。'

    def poll(self, relative_volume=None):
        if self.done.is_set(): return self.error or 'ended'
        if (time.monotonic() >= self.next_volume
                or relative_volume is not None and relative_volume != self.relative_volume):
            self.volume(relative_volume)
        return None

    def stop(self):
        self.cancelled.set()
        if self.stream: self.stream.close()
        with self.process_lock:
            process = self.process
        try:
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=.3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=1)
            if self.thread: self.thread.join(timeout=1)
            if process and process.stdin: process.stdin.close()
            if self.stderr: self.stderr.close()
            if self.configuration: self.configuration.close()
        finally:
            self.process = self.thread = self.stream = None
            self.stderr = None
            self.configuration = None
            if self.suspended:
                self.suspended = False
                self.resume()

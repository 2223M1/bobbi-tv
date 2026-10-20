"""XiaoPai tap-to-speak using its separate Bluetooth microphone control UUID."""
import json
from pathlib import Path
import subprocess

from .audio import AudioError
from .bluez_gatt import characteristics
from .cmcc_audio import message
from .cmcc_service import Controller
from .nanosic_audio import AUDIO_OUT_UUID, MIC_START, MIC_STOP, NAME, WnvcDecoder
from .nanosic_frames import NanosicFrames

DOWN = bytes.fromhex('0100003e0000000000')
UP = bytes.fromhex('010000000000000000')


def find_remote(sysfs=Path('/sys/class/hidraw')):
    for path in sorted(sysfs.glob('hidraw*')):
        try:
            info = dict(line.split('=', 1) for line in
                        (path / 'device/uevent').read_text().splitlines() if '=' in line)
        except OSError:
            continue
        if info.get('HID_NAME') in ('XiaoPaiRC_173', 'XiaoPaiRC_173S'):
            return '/dev/' + path.name
    return None


class GattMicrophone:
    def __init__(self, address):
        prefix = '/org/bluez/hci0/dev_' + address.replace(':', '_').upper() + '/'
        try:
            result = subprocess.run(['busctl', '--system', '--json=short', 'call', 'org.bluez', '/',
                'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects'],
                capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired as error:
            raise OSError('蓝牙音频通道查询超时。') from error
        if result.returncode or not result.stdout.strip():
            # Some BlueZ object databases cannot be rendered by busctl's JSON
            # formatter. Enumerating just this device's UUIDs remains usable.
            self.path = characteristics(address, {AUDIO_OUT_UUID})[AUDIO_OUT_UUID]
            return
        objects = json.loads(result.stdout)['data'][0]
        self.path = next((path for path, interfaces in objects.items()
            if path.startswith(prefix) and
            interfaces.get('org.bluez.GattCharacteristic1', {}).get('UUID', {}).get('data', '').lower()
            == AUDIO_OUT_UUID), None)
        if not self.path:
            raise OSError('没有找到极光遥控器的蓝牙音频控制通道。')

    def write(self, enabled):
        payload = MIC_START if enabled else MIC_STOP
        try:
            reply = subprocess.run(['busctl', '--system', '--timeout=2', 'call', 'org.bluez',
                self.path, 'org.bluez.GattCharacteristic1', 'WriteValue', 'aya{sv}',
                str(len(payload)), *map(str, payload), '1', 'type', 's', 'request'],
                capture_output=True, text=True, timeout=3)
        except subprocess.TimeoutExpired as error:
            raise OSError('极光遥控器开闭麦命令超时。') from error
        if reply.returncode:
            raise OSError(reply.stderr.strip() or '极光遥控器开闭麦失败。')


class NanosicController(Controller):
    def __init__(self, profile, root, launch, log=lambda text: None,
                 decoder_factory=None, microphone=None, **options):
        super().__init__(profile, root, launch, log,
            decoder_factory=decoder_factory or (lambda: WnvcDecoder(root)),
            name=NAME, frame_factory=NanosicFrames, socket_name='nanosic.sock',
            source='nanosic', supports_toggle=False, **options)
        self.microphone = microphone
        self.reopen_at = None
        self.cooldown_until = 0
        self.decode_errors = self.consecutive_errors = 0

    def attach(self, device):
        info = dict(line.split('=', 1) for line in
                    (Path('/sys/class/hidraw') / Path(device).name / 'device/uevent')
                    .read_text().splitlines() if '=' in line)
        self.microphone = GattMicrophone(info['HID_UNIQ'])
        super().attach(device)

    def _output(self, enabled):
        # Pressing physically opens the microphone already. In tap mode the
        # host opens it again after the physical release's stop has arrived.
        if not enabled and self.microphone is not None:
            self.microphone.write(False)

    def _reset_decoder(self):
        current = self.session
        if current and current.recording:
            current.decoder.close()
            current.decoder = self.decoder_factory()
            self.consecutive_errors = 0

    def on_report(self, data, maximum=10):
        current = self.session
        if data[:1] == b'\x2b':
            control = data[1:].rstrip(b'\0 ')
            if control == b'nanosic voice start':
                if current is None:
                    if self.clock() < self.cooldown_until:
                        return
                    self.decode_errors = self.consecutive_errors = 0
                    self.begin_capture(maximum)
                    current = self.session
                elif current.recording:
                    self._reset_decoder()
                if current and current.recording:
                    current.frames.feed(data)
                else:
                    self._output(False)
                return
            if control == b'nanosic voice stop':
                if current and current.recording:
                    current.frames.feed(data)
                    if current.key_controlled:
                        self.end_capture()
                    else:
                        self.reopen_at = self.clock() + 0.05
                return
            if current and current.recording and self.clock() - current.started < current.maximum:
                event = current.frames.feed(data)
                if event and event[0] == 'frame':
                    try:
                        pcm = current.decoder.decode(event[1])
                    except AudioError:
                        # A reset/transition may yield one corrupt startup
                        # frame. Drop it, with a bound on sustained failures.
                        self.decode_errors += 1
                        self.consecutive_errors += 1
                        if self.consecutive_errors >= 5:
                            self.end_capture('极光遥控器音频持续解码失败，请重新按语音键。')
                        return
                    self.consecutive_errors = 0
                    if current.decoded * 640 + len(pcm) > int(current.maximum * 32000):
                        self.end_capture()
                        return
                    current.outgoing.extend(message(b'A', pcm))
                    current.decoded += 1
                    current.last_audio = self.clock()
        elif data == DOWN:
            self.pressed = True  # F5 opens the UI; it never toggles this lease.
        elif data == UP and self.pressed:
            self.pressed = False
            if current and current.recording:
                if current.key_controlled:
                    self.end_capture()
                else:
                    self.reopen_at = self.clock() + 0.05

    def tick(self, maximum=10, timeout=0.05):
        if self.reopen_at is not None and self.clock() >= self.reopen_at:
            self.reopen_at = None
            current = self.session
            if current and current.recording and self.clock() - current.started < current.maximum:
                try:
                    self._reset_decoder()
                    current.frames._discard()
                    current.frames.active = True
                    self.microphone.write(True)
                except (OSError, AudioError) as error:
                    self.end_capture(str(error))
        super().tick(maximum, timeout)

    def end_capture(self, error=''):
        self.reopen_at = None
        self.cooldown_until = self.clock() + 0.5
        super().end_capture(error)

    def extra_statistics(self):
        return {'bluetooth_decode_errors': self.decode_errors,
                'bluetooth_remote': NAME}

    def detach(self, reason='极光遥控器蓝牙连接已断开。'):
        super().detach(reason)
        self.microphone = None

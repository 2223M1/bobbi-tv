"""UR02 ATVV owner; physical/ATVV voice events share one bounded capture lease."""
from pathlib import Path
import hashlib

from .audio import AudioError
from .bluez_gatt import GattBus, characteristics
from .cmcc_audio import message
from .cmcc_service import Controller
from .ur02_audio import (NAME, TX, RX, CTL, GET_CAPS, MIC_OPEN, MIC_CLOSE,
                         AudioFrames, ImaDecoder, capabilities)


def find_remote(sysfs=Path('/sys/class/hidraw')):
    for path in sorted(sysfs.glob('hidraw*')):
        try:
            info = dict(line.split('=', 1) for line in
                        (path / 'device/uevent').read_text().splitlines() if '=' in line)
        except OSError:
            continue
        if info.get('HID_NAME') in ('UR01', 'UR02'):
            return '/dev/' + path.name
    return None


class Ur02Controller(Controller):
    remote_name = NAME
    socket_name = 'ur02.sock'
    input_source = 'ur02'

    def __init__(self, profile, root, launch, log=lambda text: None, bus=None,
                 decoder_factory=None, **options):
        super().__init__(profile, root, launch, log, decoder_factory=decoder_factory or ImaDecoder,
            name=self.remote_name, frame_factory=AudioFrames, socket_name=self.socket_name,
            source=self.input_source, **options)
        self.bus = bus
        self.paths = {}
        self.caps = None
        self.last_query = -10
        self.last_trigger = -10
        self.trigger_channel = None
        self.audio_started = False
        self.audio_packets = 0
        self.syncs = 0
        self.stream_id = 0
        self.pre_start_packets = 0
        self.audio_starts = 0

    def attach(self, device):
        info = dict(line.split('=', 1) for line in
                    (Path('/sys/class/hidraw') / Path(device).name / 'device/uevent')
                    .read_text().splitlines() if '=' in line)
        paths = characteristics(info['HID_UNIQ'], {TX, RX, CTL})
        bus = GattBus(info['HID_UNIQ'])
        try:
            bus.subscribe(paths[CTL]); bus.subscribe(paths[RX])
            self.bus, self.paths = bus, paths
            super().attach(device)
            self.status = 'negotiating'
            self.query()
        except Exception:
            self.detach()
            bus.close()
            raise

    def query(self):
        if self.bus is not None and self.clock() - self.last_query >= 1:
            self.last_query = self.clock()
            self.bus.write(self.paths[TX], GET_CAPS)

    def _output(self, enabled):
        if self.bus is None:
            raise OSError(self.name + ' 蓝牙语音已断开。')
        if enabled:
            self.audio_started = False
            self.audio_packets = self.syncs = 0
            self.pre_start_packets = self.audio_starts = 0
            self.stream_id = 0
            current = self.session
            current.frames = AudioFrames(self.caps['frame_bytes'])
            current.pcm_pending = bytearray()
            current.decoded_bytes = 0
            current.encoded_hash = hashlib.sha256()
            current.pcm_hash = hashlib.sha256()
        self.bus.write(self.paths[TX], MIC_OPEN if enabled else MIC_CLOSE)

    def trigger(self, channel, maximum):
        now = self.clock()
        if self.caps is None:
            self.query()
            return
        # UR02 sends both START_SEARCH and a Consumer Voice Command report.
        # They can arrive in either order through BlueZ and the kernel.
        if channel != self.trigger_channel and now - self.last_trigger < 0.3:
            return
        self.last_trigger, self.trigger_channel = now, channel
        if self.session and self.session.recording:
            self.end_capture()
        else:
            self.begin_capture(maximum)

    def on_report(self, data, maximum=10):
        if data[:1] != b'\x02' or len(data) != 6:
            return
        down = int.from_bytes(data[1:3], 'little') == 0xcf
        if down and not self.pressed:
            self.pressed = True
            self.trigger('hid', maximum)
        elif not any(data[1:]):
            self.pressed = False  # UR02 reports immediate release, even held.
        elif self.caps is None:
            self.query()  # Direction keys wake a sleeping newly connected remote.

    def on_gatt(self, path, data, maximum=10):
        if not data:
            return
        current = self.session
        if path == self.paths.get(CTL):
            if data[0] == 0x0b:
                self.caps = capabilities(data)
                self.status = 'recording' if current and current.recording else 'ready'
            elif data[0] == 8:
                self.trigger('ctl', maximum)
            elif data[0] == 4 and len(data) >= 4:
                if current and current.recording:
                    if data[2] != 2:
                        self.end_capture(self.name + ' 返回了未协商的语音编码。')
                        return
                    current.frames.reset()
                    current.decoder.reset()
                    self.stream_id = data[3]
                    self.audio_started = True
                    self.audio_starts += 1
                    current.last_audio = self.clock()
                else:
                    self._output(False)
            elif data[0] == 0 and current and current.recording:
                if len(data) < 2 or data[1] != 4:  # Upcoming AudioStart is a transition.
                    self.end_capture()
            elif data[0] == 0x0a and len(data) >= 7 and current and current.recording:
                if data[1] != 2:
                    self.end_capture(self.name + ' 音频同步编码无效。')
                    return
                current.frames.reset()
                current.decoder.reset(int.from_bytes(data[4:6], 'big', signed=True), data[6])
                self.syncs += 1
            elif data[0] == 0x0c and current and current.recording:
                self.end_capture(self.name + ' 拒绝了开麦命令：' + data.hex())
        elif path == self.paths.get(RX) and current and current.recording:
            if not self.audio_started:
                self.pre_start_packets += 1
                return
            if self.clock() - current.started >= current.maximum:
                self.end_capture()
                return
            self.audio_packets += 1
            current.last_audio = self.clock()
            frame = current.frames.feed(data)
            if frame is None:
                return
            pcm = current.decoder.decode(frame)
            current.encoded_hash.update(frame)
            current.pcm_hash.update(pcm)
            available = max(0, int(current.maximum * 32000) - current.decoded_bytes)
            pcm = pcm[:available - available % 2]
            current.decoded_bytes += len(pcm)
            current.decoded += 1
            current.pcm_pending.extend(pcm)
            while len(current.pcm_pending) >= 640:
                current.outgoing.extend(message(b'A', bytes(current.pcm_pending[:640])))
                del current.pcm_pending[:640]
            if not available or current.decoded_bytes >= int(current.maximum * 32000):
                self.end_capture()

    def extra_readers(self):
        return [self.bus.fd] if self.bus is not None else []

    def tick(self, maximum=10, timeout=0.01):
        try:
            if self.bus:
                for path, value in self.bus.poll():
                    self.on_gatt(path, value, maximum)
            super().tick(maximum, timeout)
            if self.bus:
                for path, value in self.bus.poll():
                    self.on_gatt(path, value, maximum)
        except (OSError, AudioError) as error:
            self.error = str(error)
            self.log(self.error)
            self.detach(self.error)

    def end_capture(self, error=''):
        current = self.session
        if current and current.recording:
            pending = getattr(current, 'pcm_pending', bytearray())
            if pending:
                current.outgoing.extend(message(b'A', bytes(pending)))
                pending.clear()
            self.audio_started = False
        super().end_capture(error)

    def extra_statistics(self):
        encoded = getattr(self.session, 'encoded_hash', None)
        pcm = getattr(self.session, 'pcm_hash', None)
        return {'bluetooth_remote': self.name, 'bluetooth_audio_packets': self.audio_packets,
                'bluetooth_codec': 'IMA/DVI ADPCM 16kHz', 'bluetooth_protocol': 'ATVV 1.0',
                'bluetooth_audio_syncs': self.syncs, 'bluetooth_audio_starts': self.audio_starts,
                'bluetooth_pre_start_packets': self.pre_start_packets,
                'bluetooth_encoded_sha256': encoded.hexdigest() if encoded else '',
                'bluetooth_pcm_sha256': pcm.hexdigest() if pcm else '',
                'bluetooth_native_decoder': bool(getattr(self.session.decoder, 'native', False))}

    def detach(self, reason=None):
        super().detach(reason or self.name + ' 蓝牙语音已断开。')
        if self.bus:
            self.bus.close()
            self.bus = None
        self.caps = None
        self.paths = {}

"""Read-only R22 owner: physical key starts audio, release ends the stream."""
import os
from pathlib import Path

from .cmcc_audio import message
from .cmcc_service import Controller
from .r22_audio import Frames, MsbcDecoder, NAME

DOWN = bytes.fromhex('0100003e0000000000')
UP = bytes.fromhex('010000000000000000')


def find_remote(sysfs=Path('/sys/class/hidraw')):
    for path in sorted(sysfs.glob('hidraw*')):
        try:
            info = dict(line.split('=', 1) for line in (path / 'device/uevent').read_text(encoding='utf-8', errors='replace').splitlines() if '=' in line)
        except OSError:
            continue
        if info.get('HID_NAME') == NAME and info.get('HID_ID', '').upper() == '0005:00000416:00000300':
            return '/dev/' + path.name
    return None


class R22Controller(Controller):
    def __init__(self, profile, root, launch, log=lambda text: None, decoder_factory=None, **options):
        options.pop('activation', None)
        super().__init__(profile, root, launch, log,
            decoder_factory=decoder_factory or (lambda: MsbcDecoder(root)),
            name=NAME, frame_factory=Frames, socket_name='r22.sock', source='r22',
            supports_toggle=False, activation='hold', **options)
        self.decode_errors = 0

    def attach(self, device):
        if self.hid is None:
            self.hid = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
            self.device = device
            self.pressed = False
            self.status, self.error = 'ready', ''

    def _output(self, enabled):
        # No host microphone command is verified. OK/cancel/timeout ends the
        # host capture; the remote itself stops transmitting on physical release.
        pass

    def on_report(self, data, maximum=30):
        start = len(data) == 21 and data[:4] == b'\xfb\x07\x03\x01'
        stop = len(data) == 21 and data[:4] == b'\xfb\x07\x03\x00'
        if data == DOWN or start:
            if not self.pressed:
                self.pressed = True
                self.decode_errors = 0
                self.begin_capture(maximum)
            return
        if data == UP:
            if self.pressed:
                self.pressed = False
                self.end_capture()
            return
        if stop:
            self.end_capture()
            # Keep the physical-key latch until release: a cancelled client or
            # repeated F5/start report must not reopen an utterance still held.
            return
        current = self.session
        if not current or not current.recording or data[:1] != b'\xfb':
            return
        frames = current.frames.feed(data)
        if frames is None:
            self.decode_errors += 1
            if self.decode_errors >= 5:
                self.end_capture('R22 音频帧持续无效，请松开后重新按语音键。')
            return
        try:
            pcm = current.decoder.decode(frames)
            if current.decoded * 480 + len(pcm) > int(current.maximum * 32000):
                self.end_capture()
                return
            current.outgoing.extend(message(b'A', pcm))
            current.decoded += 1
            current.last_audio = self.clock()
            self.decode_errors = 0
        except Exception as error:
            self.end_capture(str(error))

    def extra_statistics(self):
        return {'bluetooth_codec': 'mSBC', 'bluetooth_sample_rate': 16000,
                'bluetooth_msbc_frames': self.session.decoded * 2}

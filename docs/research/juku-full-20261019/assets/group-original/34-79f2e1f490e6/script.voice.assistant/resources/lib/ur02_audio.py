"""UR02 ATVV v1.0 negotiation, bounded fragments and IMA/DVI ADPCM audio."""
from array import array
import sys

from .audio import AudioError
from .cmcc_audio import CmccClient

try:
    import audioop as _audioop
except ImportError:
    _audioop = None

NAME = 'UR02'
TX, RX, CTL = ('ab5e000' + suffix + '-5a21-4f05-bc7d-af01f617b664' for suffix in ('2', '3', '4'))
GET_CAPS = bytes.fromhex('0a0100000300')
MIC_OPEN, MIC_CLOSE = bytes.fromhex('0c00'), bytes.fromhex('0dff')

# Standard IMA/DVI quantizer tables, independent of any vendor firmware.
STEPS = (7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37,
    41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190,
    209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749,
    3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630,
    9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767)
INDICES = (-1, -1, -1, -1, 2, 4, 6, 8)


def capabilities(data):
    if len(data) < 7 or data[0] != 0x0b or data[1:3] != b'\x01\x00':
        raise AudioError('UR02 未返回已支持的 ATVV 1.0 语音协议。')
    if not data[3] & 2:
        raise AudioError('当前 UR02 固件不支持已验证的 16kHz 语音编码。')
    size = int.from_bytes(data[5:7], 'big')
    if not 1 <= size <= 1024:
        raise AudioError('UR02 返回的音频帧长度无效。')
    return {'version': '1.0', 'codecs': data[3], 'model': data[4], 'frame_bytes': size}


class ImaDecoder:
    def __init__(self, native=True):
        self.native = bool(native and _audioop is not None)
        self.state = (0, 0)
        self.closed = False

    def reset(self, predictor=0, index=0):
        if not -32768 <= predictor <= 32767 or not 0 <= index <= 88:
            raise AudioError('UR02 音频同步状态无效。')
        self.state = (predictor, index)

    def decode(self, data):
        if self.closed or not data or len(data) > 1024:
            raise AudioError('UR02 音频编码块无效。')
        if self.native:
            pcm, self.state = _audioop.adpcm2lin(data, 2, self.state)
            return pcm
        predictor, index = self.state
        samples = array('h')
        for byte in data:
            for code in (byte >> 4, byte & 15):
                step = STEPS[index]
                delta = ((step >> 3) + ((step >> 2) if code & 1 else 0) +
                         ((step >> 1) if code & 2 else 0) + (step if code & 4 else 0))
                predictor = max(-32768, min(32767, predictor + (-delta if code & 8 else delta)))
                index = max(0, min(88, index + INDICES[code & 7]))
                samples.append(predictor)
        self.state = (predictor, index)
        if sys.byteorder != 'little':
            samples.byteswap()
        return samples.tobytes()

    def close(self):
        self.closed = True


class AudioFrames:
    def __init__(self, size=128, fragment_bytes=20):
        self.size, self.fragment_bytes = size, fragment_bytes
        self.partial = bytearray()
        self.discarded = 0

    def feed(self, data):
        if not data or len(data) > self.size:
            raise AudioError('UR02 音频通知长度无效。')
        self.partial.extend(data)
        if len(self.partial) == self.size:
            frame = bytes(self.partial)
            self.partial.clear()
            return frame
        if len(self.partial) > self.size or len(data) < self.fragment_bytes:
            self.discarded += 1
            self.partial.clear()
            raise AudioError('UR02 音频分片不完整，请重新按语音键。')
        return None

    def reset(self):
        if self.partial:
            self.discarded += 1
        self.partial.clear()


class Ur02Client(CmccClient):
    def __init__(self, profile, token):
        super().__init__(profile, token, socket_name='ur02.sock')

"""Verified R22 BLE HID H2/mSBC framing and private PCM transport."""
import ctypes as C

from .audio import AudioError
from .cmcc_audio import CmccClient
from .native_libs import library

NAME = 'R22-IBLV2'
SEQUENCE = (0x08, 0x38, 0xc8, 0xf8)


class Frames:
    def __init__(self):
        self.expected = None
        self.discarded = 0

    def feed(self, report):
        if len(report) != 121 or report[0] != 0xfb:
            self.discarded += 2
            return None
        frames = [report[offset:offset + 60] for offset in (1, 61)]
        if any(f[0] != 1 or f[1] not in SEQUENCE or f[2:5] != b'\xad\0\0' or f[59] != 0 for f in frames):
            self.discarded += 2
            return None
        for frame in frames:
            sequence = SEQUENCE.index(frame[1])
            if self.expected is not None:
                self.discarded += (sequence - self.expected) % 4
            self.expected = (sequence + 1) % 4
        return b''.join(frame[2:59] for frame in frames)


class MsbcDecoder:
    def __init__(self, addon_root):
        self.handle = None
        path = library(addon_root, 'r22', ('libr22-msbc-ffmpeg63.so',
                                            'libr22-msbc-ffmpeg62.so'))
        try:
            self.lib = C.CDLL(str(path))
            self.lib.r22_decoder_create.restype = C.c_void_p
            self.lib.r22_decoder_destroy.argtypes = [C.c_void_p]
            self.lib.r22_decoder_destroy.restype = None
            self.lib.r22_decoder_decode.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_void_p, C.c_int]
            self.lib.r22_decoder_decode.restype = C.c_int
            self.handle = self.lib.r22_decoder_create()
        except OSError as error:
            raise AudioError('当前系统无法加载 R22 音频解码器：{}。'
                             '该解码器调用系统自带的 FFmpeg（{} 位用户态）。'
                             .format(error, C.sizeof(C.c_void_p) * 8)) from error
        if not self.handle:
            raise AudioError('当前系统的 FFmpeg 没有可用的 mSBC 解码器。')
        self.output = C.create_string_buffer(240)

    def decode(self, frames):
        if not self.handle or len(frames) != 114:
            raise AudioError('R22 音频帧无效。')
        pcm = []
        for offset in (0, 57):
            source = C.create_string_buffer(frames[offset:offset + 57])
            size = self.lib.r22_decoder_decode(self.handle, source, 57, self.output, 240)
            if size != 240:
                raise AudioError('R22 音频解码失败：{}'.format(size))
            pcm.append(self.output.raw)
        return b''.join(pcm)

    def close(self):
        if self.handle:
            self.lib.r22_decoder_destroy(self.handle)
            self.handle = None


class R22Client(CmccClient):
    def __init__(self, profile, token):
        super().__init__(profile, token, socket_name='r22.sock')

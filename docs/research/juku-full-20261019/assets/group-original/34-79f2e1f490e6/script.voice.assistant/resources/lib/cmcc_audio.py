"""Verified CMCC HID framing, Siren decoder and local PCM transport."""
import ctypes as C

from .errors import AudioError
from .inputs.pcm import Client as CmccClient, CmccMicrophone, HEADER, MAX_MESSAGE, message
from .native_platform import decoder_path

NAME = 'CMCC_Voice_Remote'


def input_source(preference, enabled, connected, nanosic_enabled=True, nanosic_connected=False,
                 ur02_enabled=True, ur02_connected=False):
    if preference == 'ur02':
        return 'ur02'
    if preference == 'nanosic':
        return 'nanosic'
    if preference == 'cmcc':
        return 'cmcc'
    if preference != 'usb' and ur02_enabled and ur02_connected:
        return 'ur02'
    if preference != 'usb' and nanosic_enabled and nanosic_connected:
        return 'nanosic'
    return 'cmcc' if preference != 'usb' and enabled and connected else 'usb'


class Frames:
    def __init__(self):
        self.sequence = None
        self.parts = []
        self.discarded = 0

    def feed(self, report):
        if len(report) != 21 or report[0] != 0xfc:
            return None
        sequence = int.from_bytes(report[1:3], 'little')
        fragment = report[3]
        if fragment == 0:
            if self.parts:
                self.discarded += 1
            self.sequence, self.parts = sequence, [report[5:21]]
        elif sequence == self.sequence and fragment == len(self.parts) and fragment < 3:
            self.parts.append(report[5:21])
        else:
            self.discarded += 1
            self.sequence, self.parts = None, []
        if len(self.parts) == 3:
            frame = b''.join(self.parts)[:40]
            self.sequence, self.parts = None, []
            return frame
        return None


class SirenDecoder:
    def __init__(self, addon_root):
        self.handle = None
        path = decoder_path(addon_root, 'cmcc', 'libcmcc-siren-ffmpeg')
        try:
            self.lib = C.CDLL(str(path))
            self.lib.cmcc_decoder_create.restype = C.c_void_p
            self.lib.cmcc_decoder_destroy.argtypes = [C.c_void_p]
            self.lib.cmcc_decoder_destroy.restype = None
            self.lib.cmcc_decoder_decode.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_void_p, C.c_int]
            self.lib.cmcc_decoder_decode.restype = C.c_int
            self.handle = self.lib.cmcc_decoder_create()
        except OSError as error:
            raise AudioError('当前系统无法加载 CMCC 蓝牙音频解码器，请安装匹配系统的插件包。') from error
        if not self.handle:
            raise AudioError('当前系统没有兼容的 Siren 蓝牙音频解码器。')
        self.output = C.create_string_buffer(640)

    def decode(self, frame):
        if len(frame) != 40:
            raise AudioError('蓝牙音频帧长度不正确。')
        source = C.create_string_buffer(frame)
        size = self.lib.cmcc_decoder_decode(self.handle, source, 40, self.output, 640)
        if size != 640:
            raise AudioError('蓝牙音频解码失败：{}'.format(size))
        return self.output.raw[:size]

    def close(self):
        if self.handle:
            self.lib.cmcc_decoder_destroy(self.handle)
            self.handle = None

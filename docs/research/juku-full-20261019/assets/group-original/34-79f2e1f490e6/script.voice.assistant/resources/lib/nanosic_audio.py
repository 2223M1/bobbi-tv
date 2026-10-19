"""XiaoPai's verified WNVC decoder and private PCM client."""
import ctypes as C
from pathlib import Path

from .audio import AudioError
from .cmcc_audio import CmccClient
from .native_platform import decoder_path

NAME = 'XiaoPaiRC_173'
AUDIO_OUT_UUID = '5f74756f-6f69-6475-6163-69736f6e616e'
MIC_START = bytes.fromhex('5a0100ffffff0000')
MIC_STOP = bytes.fromhex('5a0000ffffff0000')


class WnvcDecoder:
    def __init__(self, addon_root):
        self.handle = None
        path = decoder_path(addon_root, 'nanosic', 'libnanosic-wnvc-avutil', 'avutil')
        try:
            self.lib = C.CDLL(str(path))
            self.lib.nanosic_decoder_create.restype = C.c_void_p
            self.lib.nanosic_decoder_destroy.argtypes = [C.c_void_p]
            self.lib.nanosic_decoder_destroy.restype = None
            self.lib.nanosic_decoder_decode.argtypes = [C.c_void_p, C.c_void_p, C.c_int,
                                                        C.c_void_p, C.c_int]
            self.lib.nanosic_decoder_decode.restype = C.c_int
            self.handle = self.lib.nanosic_decoder_create()
        except OSError as error:
            raise AudioError('无法加载极光遥控器音频解码器，请安装匹配系统的插件包。') from error
        if not self.handle:
            raise AudioError('当前系统没有兼容的极光遥控器音频解码器。')
        self.output = C.create_string_buffer(640)

    def decode(self, frame):
        if len(frame) != 60 or not self.handle:
            raise AudioError('极光遥控器音频帧不正确。')
        size = self.lib.nanosic_decoder_decode(self.handle, frame, len(frame), self.output, 640)
        if size != 640:
            raise AudioError('极光遥控器音频解码失败：{}'.format(size))
        return self.output.raw[:size]

    def close(self):
        if self.handle:
            self.lib.nanosic_decoder_destroy(self.handle)
            self.handle = None


class NanosicClient(CmccClient):
    def __init__(self, profile, token):
        super().__init__(profile, token, socket_name='nanosic.sock')

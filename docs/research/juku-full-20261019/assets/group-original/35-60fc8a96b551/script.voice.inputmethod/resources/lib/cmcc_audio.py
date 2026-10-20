"""Verified CMCC HID framing, Siren decoder and local PCM transport."""
import ctypes as C
import json
from pathlib import Path
import select
import socket
import struct
import time

from .audio import AudioError
from .native_libs import library

NAME = 'CMCC_Voice_Remote'
HEADER = struct.Struct('!cI')
MAX_MESSAGE = 8192


def input_source(preference, enabled, connected, nanosic_enabled=True, nanosic_connected=False,
                 ur02_enabled=True, ur02_connected=False, b25_enabled=True, b25_connected=False,
                 r22_enabled=True, r22_connected=False):
    if preference == 'ur02':
        return 'ur02'
    if preference == 'nanosic':
        return 'nanosic'
    if preference == 'cmcc':
        return 'cmcc'
    if preference == 'b25':
        return 'b25'
    if preference == 'r22':
        return 'r22'
    if preference != 'usb' and b25_enabled and b25_connected:
        return 'b25'
    if preference != 'usb' and r22_enabled and r22_connected:
        return 'r22'
    if preference != 'usb' and ur02_enabled and ur02_connected:
        return 'ur02'
    if preference != 'usb' and nanosic_enabled and nanosic_connected:
        return 'nanosic'
    return 'cmcc' if preference != 'usb' and enabled and connected else 'usb'


def message(kind, payload=b''):
    return HEADER.pack(kind, len(payload)) + payload


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
        # One name per user space: the aarch64 build links the system FFmpeg 9
        # (libavcodec.so.63) that CoreELEC 22 ships, the armv7l build the
        # FFmpeg 8 (libavcodec.so.62) of CoreELEC 21.  Only one exists in the
        # directory chosen by native_libs, so the order is documentation.
        path = library(addon_root, 'cmcc', ('libcmcc-siren-ffmpeg63.so',
                                            'libcmcc-siren-ffmpeg62.so'))
        try:
            self.lib = C.CDLL(str(path))
            self.lib.cmcc_decoder_create.restype = C.c_void_p
            self.lib.cmcc_decoder_destroy.argtypes = [C.c_void_p]
            self.lib.cmcc_decoder_destroy.restype = None
            self.lib.cmcc_decoder_decode.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_void_p, C.c_int]
            self.lib.cmcc_decoder_decode.restype = C.c_int
            self.handle = self.lib.cmcc_decoder_create()
        except OSError as error:
            raise AudioError('当前系统无法加载 CMCC 蓝牙音频解码器：{}。'
                             '该解码器调用系统自带的 FFmpeg（{} 位用户态）。'
                             .format(error, C.sizeof(C.c_void_p) * 8)) from error
        if not self.handle:
            raise AudioError('当前系统的 FFmpeg 没有可用的 Siren 解码器。')
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


class CmccClient:
    """Keep the server's capture lease through ASR, AI and the result dialog.

    Closing the microphone stops recording; closing this client releases the
    lease. The server holds capture.lock so legacy F5 cannot open USB capture.
    """
    def __init__(self, profile, token, socket_name='cmcc.sock'):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.buffer = bytearray()
        self.finished = False
        self.statistics = {}
        try:
            self.socket.settimeout(2)
            self.socket.connect(str(Path(profile) / socket_name))
            self.socket.sendall(('HELLO ' + token + '\n').encode('ascii'))
            self.socket.setblocking(False)
            reply = self._receive(2)
            if reply is None or reply[0] != b'R':
                raise AudioError('这次蓝牙录音已结束，请重新按语音键。')
            metadata = json.loads(reply[1])
            self.device = metadata['device']
            self.key_controlled = metadata.get('key_controlled', True)
            self.input_source = metadata.get('source', 'cmcc')
            self.supports_toggle = metadata.get('supports_toggle', True)
        except (OSError, ValueError, KeyError) as error:
            self.close()
            raise AudioError('无法连接蓝牙录音服务，请重新按语音键。') from error
        except Exception:
            self.close()
            raise

    def _receive(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            if len(self.buffer) >= HEADER.size:
                kind, size = HEADER.unpack_from(self.buffer)
                if size > MAX_MESSAGE:
                    raise AudioError('蓝牙录音服务消息长度不正确。')
                if len(self.buffer) >= HEADER.size + size:
                    payload = bytes(self.buffer[HEADER.size:HEADER.size + size])
                    del self.buffer[:HEADER.size + size]
                    return kind, payload
            remaining = max(0, deadline - time.monotonic())
            readable, _, _ = select.select([self.socket], [], [], remaining)
            if not readable:
                return None
            data = self.socket.recv(4096)
            if not data:
                raise AudioError('蓝牙录音服务已停止。')
            self.buffer.extend(data)

    def read(self):
        if self.finished:
            return b''
        reply = self._receive(0.05)
        if reply is None:
            return b''
        kind, payload = reply
        if kind == b'A' and 0 < len(payload) <= 640 and len(payload) % 2 == 0:
            return payload
        if kind == b'F':
            self.statistics = json.loads(payload)
            self.finished = True
            return b''
        if kind == b'E':
            raise AudioError(payload.decode('utf-8', 'replace'))
        raise AudioError('蓝牙录音服务返回了无效音频。')

    def stop_capture(self):
        if self.socket is None:
            return
        try:
            self.socket.settimeout(0.2)
            self.socket.sendall(b'STOP\n')
            self.socket.setblocking(False)
            # Silence/return can stop tap mode before the server sends F.
            # Drain to its bounded acknowledgement to collect statistics and
            # ensure FB00 was sent while keeping the result-dialog lease.
            deadline = time.monotonic() + 0.5
            while not self.finished and time.monotonic() < deadline:
                self.read()
        except OSError:
            self.close()
        except (AudioError, ValueError):
            self.close()

    def microphone(self, unused_device=''):
        return CmccMicrophone(self)

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


class CmccMicrophone:
    def __init__(self, client):
        self.client = client
        self.device = client.device
        self.key_controlled = client.key_controlled

    @property
    def eof(self):
        return self.client.finished

    @property
    def statistics(self):
        return self.client.statistics

    def read(self):
        return self.client.read()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.client.stop_capture()

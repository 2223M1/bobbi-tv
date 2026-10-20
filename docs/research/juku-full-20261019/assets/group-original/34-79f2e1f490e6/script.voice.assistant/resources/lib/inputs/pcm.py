"""Shared local PCM socket transport; no Bluetooth/native decoder imports."""
import json
from ..data_paths import data_path
import select
import socket
import struct
import time

from ..errors import AudioError

HEADER = struct.Struct('!cI')
MAX_MESSAGE = 8192


def message(kind, payload=b''):
    return HEADER.pack(kind, len(payload)) + payload


class Client:
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
            self.socket.connect(str(data_path(profile, socket_name)))
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

"""One HID owner, bounded in-memory PCM and a private local assistant lease."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import select
import socket
import time

from .cmcc_audio import Frames, NAME, SirenDecoder, message


def find_remote(sysfs=Path('/sys/class/hidraw')):
    for path in sorted(sysfs.glob('hidraw*')):
        try:
            info = dict(line.split('=', 1) for line in (path / 'device/uevent').read_text(encoding='utf-8', errors='replace').splitlines() if '=' in line)
        except OSError:
            continue
        if info.get('HID_NAME') == NAME and info.get('HID_ID', '').upper() == '0005:00000416:00000300':
            return '/dev/' + path.name
    return None


class Session:
    def __init__(self, lock, decoder, device, maximum, now, key_controlled):
        self.lock, self.decoder = lock, decoder
        self.token = secrets.token_hex(16)
        self.started = self.last_audio = now
        self.maximum = maximum
        self.device = device
        self.recording = True
        self.key_controlled = key_controlled
        self.peer = None
        self.frames = Frames()
        self.decoded = 0
        self.outgoing = bytearray()
        self.ended = None


class Controller:
    def __init__(self, profile, root, launch, log=lambda text: None,
                 decoder_factory=None, clock=time.monotonic, activation='tap',
                 name=NAME, frame_factory=Frames, socket_name='cmcc.sock',
                 source='cmcc', supports_toggle=True):
        self.profile, self.root = Path(profile), root
        self.launch, self.log, self.clock = launch, log, clock
        self.decoder_factory = decoder_factory or (lambda: SirenDecoder(root))
        self.hid = None
        self.device = None
        self.listener = None
        self.peers = {}
        self.session = None
        self.pressed = False
        self.status = 'disconnected'
        self.error = ''
        self.activation = activation
        self.name, self.frame_factory = name, frame_factory
        self.source, self.supports_toggle = source, supports_toggle
        self.path = self.profile / socket_name

    def open(self):
        self.profile.mkdir(parents=True, exist_ok=True)
        # Caller holds cmcc-service.lock before removing a stale socket.
        self.path.unlink(missing_ok=True)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.listener.listen(2)
        self.listener.setblocking(False)

    def attach(self, device):
        if self.hid is None:
            self.hid = os.open(device, os.O_RDWR | os.O_NONBLOCK)
            self.device = device
            self.pressed = False
            self.status, self.error = 'ready', ''

    def detach(self, reason='蓝牙遥控器连接已断开。'):
        if self.session and self.session.recording:
            self.end_capture(reason)
        if self.hid is not None:
            os.close(self.hid)
            self.hid = None
        self.device = None
        self.pressed = False
        self.status = 'disconnected'

    def _output(self, enabled):
        if self.hid is None:
            raise OSError('CMCC remote disconnected')
        if os.write(self.hid, bytes((0xfb, int(enabled)))) != 2:
            raise OSError('Incomplete CMCC HID output report')

    def begin_capture(self, maximum):
        if self.session is not None:
            return
        lock = (self.profile / 'capture.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            return  # Existing USB capture, AI work or result dialog owns it.
        decoder = None
        try:
            decoder = self.decoder_factory()
            self.session = Session(lock, decoder, self.name + ' (Bluetooth)', maximum, self.clock(),
                                   key_controlled=self.activation == 'hold')
            self.session.frames = self.frame_factory()
            # Publish the pending session before FB01 generates F5. Only that
            # normal F5 opens the UI; the service itself never starts a script.
            self.launch(self.session.token)
            self.status = 'recording'
            self._output(True)
        except Exception as error:
            self.error = str(error)
            self.log(self.error)
            if self.session:
                self.release()
            else:
                if decoder:
                    decoder.close()
                lock.close()
            self.status = 'error'

    def on_report(self, data, maximum=10):
        if len(data) >= 4 and data[:3] == b'\xf8\x82\x03':
            if data[3] == 1 and not self.pressed:
                self.pressed = True
                if self.session and self.session.recording and not self.session.key_controlled:
                    self.end_capture()  # A second tap ends this recording.
                else:
                    self.begin_capture(maximum)
            elif data[3] == 0:
                self.pressed = False
                if self.session and self.session.key_controlled:
                    self.end_capture()
        elif self.session and self.session.recording and data[:1] == b'\xfc':
            current = self.session
            frame = current.frames.feed(data)
            if frame is not None:
                try:
                    pcm = current.decoder.decode(frame)
                    if current.decoded * 640 + len(pcm) > int(current.maximum * 32000):
                        self.end_capture()
                        return
                    current.outgoing.extend(message(b'A', pcm))
                    current.decoded += 1
                    current.last_audio = self.clock()
                except Exception as error:
                    self.end_capture(str(error))

    def end_capture(self, error=''):
        current = self.session
        if current is None or not current.recording:
            return
        current.recording = False
        current.ended = self.clock()
        try:
            self._output(False)
        except OSError as failure:
            self.log(str(failure))
        current.decoder.close()
        stats = {'bluetooth_frames': current.decoded,
                 'bluetooth_discarded_fragments': current.frames.discarded,
                 'bluetooth_capture_seconds': round(current.ended - current.started, 3)}
        stats.update(self.extra_statistics())
        current.outgoing.extend(message(b'E', error.encode('utf-8')[:4096]) if error else
                                message(b'F', json.dumps(stats).encode()))
        self.status = 'ready' if self.hid is not None else 'disconnected'

    def extra_statistics(self):
        return {}

    def extra_readers(self):
        return []

    def release(self):
        current = self.session
        if current is None:
            return
        self.end_capture()
        if current.peer is not None:
            self.peers.pop(current.peer, None)
            current.peer.close()
        current.lock.close()
        self.session = None

    def _drop_peer(self, peer):
        if self.session and self.session.peer is peer:
            self.release()  # Client cancellation/crash also stops the microphone.
        else:
            self.peers.pop(peer, None)
            peer.close()

    def _receive_peer(self, peer):
        state = self.peers[peer]
        data = peer.recv(128)
        if not data:
            self._drop_peer(peer)
            return
        state['buffer'].extend(data)
        if len(state['buffer']) > 128:
            self._drop_peer(peer)
            return
        while b'\n' in state['buffer']:
            raw, _, remaining = state['buffer'].partition(b'\n')
            state['buffer'] = bytearray(remaining)
            current = self.session
            if not state['claimed']:
                expected = ('HELLO ' + current.token).encode() if current else b''
                if current is None or current.peer is not None or not secrets.compare_digest(raw, expected):
                    self._drop_peer(peer)
                    return
                current.peer = peer
                state['claimed'] = True
                current.outgoing[:0] = message(b'R', json.dumps({'device': current.device,
                    'key_controlled': current.key_controlled, 'source': self.source,
                    'supports_toggle': self.supports_toggle}).encode())
            elif raw == b'STOP':
                self.end_capture()
            else:
                self._drop_peer(peer)
                return

    def tick(self, maximum=10, timeout=0.05):
        now = self.clock()
        current = self.session
        if current:
            if current.recording and now - current.started >= current.maximum:
                self.end_capture()
            elif current.recording and now - current.last_audio >= 2:
                self.end_capture('蓝牙语音数据已中断，请重新按语音键。')
            if current.peer is None and now - current.started >= 5:
                self.release()  # Kodi failed to attach; do not hold a stale lock.
        for peer, state in list(self.peers.items()):
            if not state['claimed'] and now - state['started'] >= 2:
                self._drop_peer(peer)
        readers = list(self.peers)
        if self.listener is not None:
            readers.append(self.listener)
        if self.hid is not None:
            readers.append(self.hid)
        readers.extend(self.extra_readers())
        writers = ([self.session.peer] if self.session and self.session.peer is not None and
                   self.session.outgoing else [])
        readable, writable, _ = select.select(readers, writers, [], timeout)
        # HID first: drain audio/control before a peer disconnect frees its lease.
        if self.hid is not None and self.hid in readable:
            try:
                for unused in range(64):
                    data = os.read(self.hid, 4096)
                    if not data:
                        self.detach()
                        break
                    self.on_report(data, maximum)
            except BlockingIOError:
                pass
            except OSError:
                self.detach()
        for peer in readable:
            if peer is self.listener:
                connection, _ = self.listener.accept()
                connection.setblocking(False)
                if len(self.peers) >= 2:
                    connection.close()
                else:
                    self.peers[connection] = {'buffer': bytearray(), 'claimed': False, 'started': now}
            elif peer in self.peers:
                try:
                    self._receive_peer(peer)
                except OSError:
                    self._drop_peer(peer)
        for peer in writable:
            if self.session and self.session.peer is peer:
                try:
                    size = peer.send(self.session.outgoing)
                    del self.session.outgoing[:size]
                except BlockingIOError:
                    pass
                except OSError:
                    self._drop_peer(peer)

    def close(self):
        self.release()
        self.detach()
        for peer in list(self.peers):
            self._drop_peer(peer)
        if self.listener is not None:
            self.listener.close()
            self.listener = None
            self.path.unlink(missing_ok=True)

"""One nonblocking subtitle IPC read on the existing playback-service tick.

No worker threads, cloud operations or native mutation. A ready response is
still revalidated by PlaybackAuthority and Kodi against the actual instance.
"""
import errno
import json
import socket
import time
from copy import deepcopy

from bobbi_core.preparation_client import SOCKET_PATH


class SubtitleLookup:
    def __init__(self, factory=None, clock=time.monotonic):
        self.factory = factory or (lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
        self.clock = clock
        self.connection = None
        self.key = None
        self.result = None
        self.deadline = self.completed = 0
        self.outgoing = b''
        self.incoming = bytearray()

    def close(self):
        if self.connection is not None:
            self.connection.close()
        self.connection = None

    def _finish(self, result):
        self.close()
        self.result = result
        self.completed = self.clock()

    def request(self, receipt):
        fields = ('native_instance', 'request_id', 'file_identity', 'url_sha256',
                  'subtitle_intent', 'subtitle_auto_intent')
        key = json.dumps({k: receipt.get(k) for k in fields}, sort_keys=True)
        self.tick()
        if self.key == key:
            if self.result is not None:
                result = self.result
                fresh = self.clock() - self.completed < 30
                self.key = self.result = None
                if fresh:
                    return deepcopy(result)
            elif self.connection is not None:
                return {'state': 'pending'}
        self.close()  # A different request/track intent invalidates old results.
        raw = json.dumps({'method': 'subtitle', 'body': receipt}, separators=(',', ':')).encode() + b'\n'
        if len(raw) > 16384:
            raise ValueError('Subtitle lookup byte budget')
        self.key, self.result = key, None
        self.deadline = self.clock() + 0.3
        self.incoming, self.outgoing = bytearray(), raw
        try:
            self.connection = self.factory()
            self.connection.setblocking(False)
            code = self.connection.connect_ex(SOCKET_PATH)
            if code not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                raise OSError('Subtitle IPC connect unavailable')
        except OSError:
            self._finish({'state': 'unavailable', 'reason': 'SUBTITLE_IPC_UNAVAILABLE'})
        return {'state': 'pending'}

    def tick(self):
        if self.connection is None:
            return
        if self.clock() >= self.deadline:
            self._finish({'state': 'unavailable', 'reason': 'SUBTITLE_IPC_TIMEOUT'})
            return
        try:
            if self.outgoing:
                sent = self.connection.send(self.outgoing)
                if not sent:
                    raise ConnectionError('Subtitle IPC closed during write')
                self.outgoing = self.outgoing[sent:]
                return
            chunk = self.connection.recv(min(4096, 16385 - len(self.incoming)))
            if not chunk:
                raise ConnectionError('Subtitle IPC closed during read')
            self.incoming.extend(chunk)
            if len(self.incoming) > 16384:
                raise ValueError('Subtitle IPC response byte budget')
            if b'\n' not in self.incoming:
                return
            line, extra = bytes(self.incoming).split(b'\n', 1)
            if extra:
                raise ValueError('One subtitle response required')
            result = json.loads(line)
            if not isinstance(result, dict) or result.get('ok') is not True:
                raise ValueError('Subtitle IPC rejected')
            self._finish(result)
        except (BlockingIOError, InterruptedError):
            return  # No waiting in the serialized playback actor.
        except (OSError, ValueError, TypeError):
            self._finish({'state': 'unavailable', 'reason': 'SUBTITLE_IPC_REJECTED'})

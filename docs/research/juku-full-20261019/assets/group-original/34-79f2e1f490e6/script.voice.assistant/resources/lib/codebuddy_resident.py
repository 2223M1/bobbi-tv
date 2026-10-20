"""One official prewarm process; hand its private pipes to a conversation.

Only the service owns/kills native processes. SCM_RIGHTS transfers duplicate
pipe descriptors to the UI interpreter, without a TCP listener or pipe proxy.
Closing the conversation/cancelling a task releases the lease and replenishes
the standby. A leased process is never recycled into an unrelated conversation.
"""
from .data_paths import data_path
import array
from collections import deque
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import threading
import time
from types import SimpleNamespace
import uuid

from .codebuddy_protocol import Connection, command, configured_proxy
from .codebuddy_regions import account_busy, auth_revision, selected_model, work_path
from .dependencies.catalog import preload_delay

MAX_REQUEST = 65536


def address(profile):
    path = str(data_path(Path(profile), 'codebuddy.sock'))
    return path if len(os.fsencode(path)) < 104 else '/tmp/voice-buddy-' + hashlib.sha256(path.encode()).hexdigest()[:24] + '.sock'


def base_command(args):
    args = list(args)
    if '--resume' in args:
        index = args.index('--resume')
        if index != len(args) - 2:
            raise ValueError('Invalid CodeBuddy resume arguments')
        del args[index:]
    return args


def fingerprint(args, profile, proxy, region):
    value = [base_command(args), proxy, region, auth_revision(profile, region)]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def receive_line(peer, cancelled=lambda: False, timeout=60, initial=b''):
    end, data = time.monotonic() + timeout, bytearray(initial)
    while time.monotonic() < end:
        if cancelled():
            raise InterruptedError('已取消 CodeBuddy。')
        if b'\n' in data:
            return json.loads(data.partition(b'\n')[0])
        if select.select([peer], [], [], .1)[0]:
            block = peer.recv(4096)
            if not block:
                raise OSError('CodeBuddy local connection closed')
            data.extend(block)
            if len(data) > MAX_REQUEST:
                raise ValueError('CodeBuddy local request too large')
    raise TimeoutError('CodeBuddy local connection timed out')


class WarmConnection(Connection):
    def __init__(self, args, profile, cancelled=lambda: False, timeout=60, proxy='', region='external'):
        self.reset(cancelled, timeout)
        self.buffer, self.pending = bytearray(), deque()
        self.sequence, self.initialized = 0, None
        self.peer = socket.socket(socket.AF_UNIX)
        descriptors = array.array('i')
        try:
            self.peer.settimeout(.5)
            self.peer.connect(address(profile))
            self.peer.sendall((json.dumps({'args': args, 'signature': fingerprint(args, profile, proxy, region)}) + '\n').encode())
            self.peer.setblocking(True)
            end = time.monotonic() + max(5, timeout)
            while not select.select([self.peer], [], [], .1)[0]:
                if cancelled():
                    raise InterruptedError('已取消 CodeBuddy。')
                if time.monotonic() >= end:
                    raise TimeoutError('CodeBuddy prewarm timed out')
            data, ancillary, flags, _ = self.peer.recvmsg(MAX_REQUEST, socket.CMSG_SPACE(2 * descriptors.itemsize))
            for level, kind, value in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    descriptors.frombytes(value[:len(value) - len(value) % descriptors.itemsize])
            info = receive_line(self.peer, cancelled, max(1, end - time.monotonic()), initial=data)
            if not info.get('ok') or len(descriptors) != 2 or flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC):
                raise OSError('CodeBuddy standby unavailable')
            for fd in descriptors:
                os.set_inheritable(fd, False)
            self.process = SimpleNamespace(pid=info['pid'], stdin=os.fdopen(descriptors[0], 'wb', buffering=0),
                                           stdout=os.fdopen(descriptors[1], 'rb', buffering=0))
            descriptors = array.array('i')
        except BaseException:
            for fd in descriptors:
                os.close(fd)
            self.peer.close()
            raise

    def alive(self):
        return self.peer.fileno() >= 0 and not select.select([self.peer], [], [], 0)[0]

    def close(self):
        self.pump = self.control = None
        if self.peer.fileno() < 0:
            return
        self.process.stdin.close()
        self.process.stdout.close()
        try:
            self.peer.sendall(b'close\n')
            self.peer.shutdown(socket.SHUT_WR)
            # The owner acknowledges only after all native descendants exit.
            receive_line(self.peer, timeout=3)
        except (OSError, ValueError, TimeoutError):
            pass
        finally:
            self.peer.close()


def connection_factory(root, profile):
    def connect(args, target, cancelled=lambda: False, timeout=60, proxy='', region='external'):
        try:
            return WarmConnection(args, target, cancelled, timeout, proxy, region)
        except InterruptedError:
            raise
        except (OSError, ValueError, TimeoutError):
            # No user message has been sent, so cold fallback cannot repeat work.
            return Connection(args, target, cancelled, timeout, proxy, region)
    return connect


class Resident:
    def __init__(self, root, profile, log=lambda message: None):
        self.root, self.profile, self.log = Path(root), Path(profile), log
        self.values, self.status = {}, {'state': 'off'}
        self.stopped = threading.Event()
        self.preload_at = time.monotonic() + preload_delay()
        self.connection = None
        self.signature = self.prewarm_socket = None
        self.lease = (data_path(self.profile, 'codebuddy-owner.lock')).open('a')
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lease.close()
            self.thread = None
            return
        self.server = socket.socket(socket.AF_UNIX)
        try:
            Path(address(profile)).unlink(missing_ok=True)
            self.server.bind(address(profile))
            os.chmod(address(profile), 0o600)
            self.server.listen(1)
            self.server.settimeout(.1)
        except BaseException:
            self.server.close()
            self.lease.close()
            raise
        self.thread = threading.Thread(target=self._run, name='CodeBuddy-prewarm', daemon=True)
        self.thread.start()

    def tick(self, values):
        # The service's Bluetooth/audio loop must never wait for native startup.
        self.values = dict(values)

    def _configuration(self):
        values = self.values
        if values.get('agent_backend') != 'codebuddy':
            return None
        if account_busy(self.profile):
            return None
        args = command(self.root, self.profile, selected_model(values), values.get('permission_level') == 'full')
        proxy, region = configured_proxy(values), values.get('codebuddy_region', 'external')
        return args, proxy, region, fingerprint(args, self.profile, proxy, region)

    def _stop(self):
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.prewarm_socket:
            self.prewarm_socket.unlink(missing_ok=True)
        self.signature = self.prewarm_socket = None
        self.status = {'state': 'off'}

    def _start(self, config):
        args, proxy, region, signature = config
        identity = uuid.uuid4().hex
        # This short-lived, mode-0600 IPC endpoint is cleaned on activation/exit.
        self.prewarm_socket = Path('/tmp/codebuddy-prewarm-' + identity + '.sock')
        # The headless SDK must be selected during cold initialization. Starting
        # with just --prewarm and adding stream-json flags on activation breaks
        # saved-session replay. Model/tool restrictions also belong up front.
        self.connection = Connection(args + ['--prewarm', '--prewarm-id', identity],
                                     self.profile, timeout=60, proxy=proxy, region=region)
        self.signature = signature
        self.status = {'state': 'warming', 'pid': self.connection.process.pid}
        self.started_at = time.monotonic()

    def _ready(self):
        if self.connection.process.poll() is not None:
            raise OSError('CodeBuddy standby exited')
        if not self.prewarm_socket.exists():
            if time.monotonic() - self.started_at > 120:
                raise TimeoutError('CodeBuddy standby startup timed out')
            return False
        self.status = dict(self.status, state='ready')
        return True

    def _activate(self, peer, request):
        config = self._configuration()
        if not config or request.get('signature') != config[3] or base_command(request.get('args', [])) != config[0]:
            peer.sendall(b'{"ok":false}\n')
            return
        if self.signature != config[3]:
            self._stop()
        if self.connection is None:
            self._start(config)
        while not self.stopped.is_set() and not self._ready():
            if select.select([peer], [], [], .1)[0] and not peer.recv(1, socket.MSG_PEEK):
                self._stop()
                return
        if self.stopped.is_set():
            return
        extra = request['args'][len(config[0]):]  # Only this window's --resume.
        with socket.socket(socket.AF_UNIX) as control:
            control.settimeout(5)
            control.connect(str(self.prewarm_socket))
            control.sendall((json.dumps({'cmd': 'activate', 'args': extra,
                                        'cwd': str(work_path(self.profile, config[2]))}) + '\n').encode())
            if not receive_line(control, self.stopped.is_set, timeout=5).get('ok'):
                raise OSError('CodeBuddy activation failed')
        fds = array.array('i', [self.connection.process.stdin.fileno(), self.connection.process.stdout.fileno()])
        peer.sendmsg([(json.dumps({'ok': True, 'pid': self.connection.process.pid}) + '\n').encode()],
                     [(socket.SOL_SOCKET, socket.SCM_RIGHTS, fds)])
        self.status = dict(self.status, state='active')
        try:
            while not self.stopped.is_set():
                if self.connection.process.poll() is not None:
                    break
                if select.select([peer], [], [], .1)[0]:
                    peer.recv(4096)
                    break
        finally:
            self._stop()
            try:
                peer.sendall(b'{"closed":true}\n')
            except OSError:
                pass

    def _run(self):
        next_check = retry_at = 0
        try:
            while not self.stopped.is_set():
                try:
                    now = time.monotonic()
                    if now >= next_check:
                        next_check = now + 1
                        config = self._configuration()
                        if not config or self.signature not in (None, config[3]):
                            self._stop()
                        if config and self.connection is None and now >= max(self.preload_at, retry_at):
                            self._start(config)
                        if self.connection:
                            self._ready()
                    try:
                        peer, _ = self.server.accept()
                    except socket.timeout:
                        continue
                    with peer:
                        peer.settimeout(.5)
                        self._activate(peer, receive_line(peer, self.stopped.is_set, timeout=2))
                except InterruptedError:
                    break
                except Exception as error:
                    self._stop()
                    self.status = {'state': 'error'}
                    if time.monotonic() >= retry_at:
                        self.log('CodeBuddy 预热暂不可用：' + type(error).__name__)
                    retry_at = time.monotonic() + 30
        finally:
            self._stop()
            self.server.close()
            Path(address(self.profile)).unlink(missing_ok=True)
            self.lease.close()

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=6)

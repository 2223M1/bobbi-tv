"""Kodi-owned native Codex daemon, using its private Unix WebSocket transport."""
from ..data_paths import data_path
from collections import deque
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time

from ..codex_agent import Connection, launch_command, private_codex_home, process_environment
from ..configuration.credentials import load_key
from ..storage import read_json, write_json
from .errors import AgentError
from .permissions import Permissions, restricted_catalog
from ..dependencies.catalog import codex_binary, preload_delay
from ..proxy import configured_proxy

MAX_MESSAGE = 50 * 1024 * 1024


def process_tree(parent):
    """Track descendants even when a terminal creates its own session/group."""
    processes = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            processes[int(path.parent.name)] = (int(fields[1]), fields[19])
        except (OSError, ValueError, IndexError):continue
    owned = {parent}
    while True:
        found = {pid for pid, (ppid, _) in processes.items() if ppid in owned}
        if found <= owned:break
        owned.update(found)
    return {pid: processes[pid][1] for pid in owned if pid in processes}


def signal_processes(processes, sig):
    for pid, started in processes.items():
        try:
            fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
            if fields[19] == started:os.kill(pid, sig)
        except (OSError, ValueError, IndexError):pass


def fingerprint(command, key, cwd, home, proxy):
    value = [command, hashlib.sha256(key.encode()).hexdigest(), str(cwd), str(home), proxy]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def websocket_module(root):
    vendor = str(Path(root) / 'resources/vendor')
    if vendor not in sys.path:sys.path.insert(0, vendor)
    import websocket
    return websocket


class Resident:
    """Owned and ticked by the existing Kodi startup service, never a turn UI."""
    def __init__(self, root, profile):
        self.root, self.profile = Path(root), Path(profile)
        self.process = None
        self.nonce = None
        self.signature = None
        self.next_start = 0
        self.next_check = 0
        self.auth_stamp = None
        self.preload_at = time.monotonic() + preload_delay()
        self.socket_path = data_path(self.profile, 'codex.sock')
        self.state_path = data_path(self.profile, 'codex-resident.json')
        self.stop_path = data_path(self.profile, 'codex-resident-stop.json')
        self.lease = (data_path(self.profile, 'codex-resident.lock')).open('a')

    def _stop(self):
        if self.process is not None:
            descendants = process_tree(self.process.pid)
            signal_processes(descendants, signal.SIGTERM)
            try:os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:pass
            try:self.process.wait(timeout=.7)
            except subprocess.TimeoutExpired:
                pass
            # Native terminal children may have independent process groups.
            # Verify start times before killing, so recycled PIDs are untouched.
            signal_processes(descendants, signal.SIGKILL)
            try:os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:pass
            self.process.wait(timeout=1)
        self.process = None
        self.state_path.unlink(missing_ok=True)
        self.socket_path.unlink(missing_ok=True)

    def tick(self, values):
        requested = read_json(self.stop_path, {}) or {}
        if requested:
            self.stop_path.unlink(missing_ok=True)
            if requested.get('nonce') == self.nonce:
                self._stop()
        if self.process is not None and self.process.poll() is not None:
            self._stop()
            self.next_start = time.monotonic() + 3
        if time.monotonic() < self.next_check:return
        self.next_check = time.monotonic() + 1
        try:fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:return
        try:
            if values.get('agent_backend') != 'codex':
                self._stop()
                return
            if time.monotonic() < self.preload_at and self.process is None:
                return
            if time.monotonic() < self.next_start:return
            subscription = values['codex_provider'] == 'chatgpt'
            key = '' if subscription else load_key(self.profile, values['agent_key_file'])
            model = values['codex_chatgpt_model'] if subscription else values['agent_model']
            effort = values['codex_chatgpt_effort'] if subscription else values['agent_effort']
            permissions = Permissions(values['permission_level'], values['approval_strategy'])
            catalog = '' if permissions.native else restricted_catalog(self.root, self.profile, model,
                                                                       standard_api=not subscription)
            binary = codex_binary(self.root, self.profile)
            home = private_codex_home(self.profile)
            work = data_path(self.profile, 'codex-work');work.mkdir(parents=True, exist_ok=True)
            command = launch_command(binary, values['agent_base_url'] if not subscription else '',
                model, values['agent_timeout'], 'chatgpt' if subscription else 'deepseek', permissions, effort, catalog,
                api_code_mode=values.get('agent_code_mode', 'off') == 'on')
            proxy = configured_proxy(values)
            signature = fingerprint(command, key, work, home, proxy)
            auth = home / 'auth.json'
            auth_stamp = auth.stat().st_mtime_ns if auth.exists() else None
            if self.process is not None and (signature != self.signature or auth_stamp != self.auth_stamp):self._stop()
            if self.process is None:
                self.socket_path.unlink(missing_ok=True)
                self.state_path.unlink(missing_ok=True)
                binary.chmod(0o755)
                host = binary.with_name('codex-code-mode-host')
                if host.is_file():host.chmod(0o755)
                command[command.index('--listen') + 1] = 'unix://' + str(self.socket_path)
                self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, cwd=work, env=process_environment(key, home, proxy),
                    start_new_session=True)
                self.signature, self.nonce = signature, secrets.token_hex(16)
                self.auth_stamp = auth_stamp
            if self.socket_path.exists() and not self.state_path.exists():
                self.socket_path.chmod(0o600)
                write_json(self.state_path, {'signature': self.signature, 'nonce': self.nonce, 'pid': self.process.pid})
        except (OSError, ValueError):
            self.next_start = time.monotonic() + 5
        finally:fcntl.flock(self.lease, fcntl.LOCK_UN)

    def close(self):
        self._stop()
        self.lease.close()


class ResidentConnection(Connection):
    def __init__(self, root, profile, command, key, cwd, cancelled, timeout, codex_home=None, proxy=''):
        self.profile = Path(profile)
        self.lease = (data_path(self.profile, 'codex-resident.lock')).open('a')
        self.socket = None
        self.completed_turn = None
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.state = read_json(data_path(self.profile, 'codex-resident.json'), {}) or {}
            if self.state.get('signature') != fingerprint(command, key, cwd, codex_home, proxy):
                raise OSError('Resident configuration unavailable')
            self.ws_module = websocket_module(root)
            raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                raw.settimeout(1)
                raw.connect(str(data_path(self.profile, 'codex.sock')))
                self.socket = self.ws_module.create_connection('ws://localhost', socket=raw,
                    timeout=1, suppress_origin=True)
            except Exception:
                raw.close()
                raise
            self.socket.settimeout(.1)
        except Exception:
            if self.socket:self.socket.close()
            self.lease.close()
            raise
        self.cancelled, self.timeout = cancelled, timeout
        self.deadline = time.monotonic() + max(60, timeout * 5)
        self.pending, self.sequence = deque(), 0
        self.pump = None
        self.waiting_user = lambda: False

    def send(self, message):
        try:self.socket.send(json.dumps(message, ensure_ascii=False))
        except (OSError, self.ws_module.WebSocketException):
            raise AgentError('Codex 常驻连接已断开，请重新提交任务。') from None

    def read(self):
        deadline = min(self.deadline, time.monotonic() + self.timeout)
        previous = time.monotonic()
        while True:
            now = time.monotonic()
            if self.waiting_user():
                deadline += now - previous
                self.deadline += now - previous
            previous = now
            if now >= deadline:raise AgentError('Codex 请求超时，请稍后重试。')
            if self.cancelled():raise InterruptedError('已取消 Codex。')
            if self.pump:self.pump()
            try:data = self.socket.recv()
            except self.ws_module.WebSocketTimeoutException:continue
            except (OSError, self.ws_module.WebSocketException):
                raise AgentError('Codex 常驻连接已断开，请重新提交任务。') from None
            if not data:raise AgentError('Codex 常驻进程已结束，请重新提交任务。')
            if len(data.encode('utf-8') if isinstance(data, str) else data) > MAX_MESSAGE:
                raise AgentError('Codex 返回内容过长。')
            try:
                message = json.loads(data)
                if not isinstance(message, dict):raise ValueError()
            except (ValueError, UnicodeError):raise AgentError('Codex 返回了无效消息。') from None
            if message.get('method') == 'turn/completed':
                params = message.get('params', {})
                turn = params.get('turn', {})
                if turn.get('status') == 'completed':
                    self.completed_turn = (params.get('threadId'), turn.get('id'))
            return message

    def close(self, thread_id=None, turn_id=None):
        self.pump = None
        self.waiting_user = lambda: False
        try:
            healthy = self.completed_turn == (thread_id, turn_id) and thread_id is not None
            if healthy:
                self.cancelled = lambda: False
                self.timeout = 2
                self.deadline = time.monotonic() + 2
                try:self.request('thread/unsubscribe', {'threadId': thread_id})
                except (AgentError, OSError):healthy = False
            if not healthy:
                # The owner kills the native process tree before reuse.
                # This also handles cancellation while a terminal is still busy.
                write_json(data_path(self.profile, 'codex-resident-stop.json'), {'nonce': self.state['nonce']})
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    state = read_json(data_path(self.profile, 'codex-resident.json'), {}) or {}
                    if state.get('nonce') != self.state['nonce']:break
                    time.sleep(.05)
        finally:
            if self.socket:self.socket.close(timeout=.1)
            self.lease.close()


def connection_factory(root, profile):
    def connect(*args):
        try:return ResidentConnection(root, profile, *args)
        except (OSError, ValueError, websocket_module(root).WebSocketException):
            # Only fall back before any task was submitted; never replay work.
            return Connection(*args)
    return connect

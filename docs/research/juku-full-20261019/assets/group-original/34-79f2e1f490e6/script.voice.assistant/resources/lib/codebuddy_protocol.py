"""CodeBuddy's SDK NDJSON transport, without a Node.js or Python SDK dependency."""
from collections import deque
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import time

from .intelligence.errors import AgentError
from .codebuddy_regions import home_path, work_path, validate_region


def environment(profile, proxy='', region='external'):
    home = home_path(profile, region)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    home.chmod(0o700)
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith(('CODEBUDDY_', 'ANTHROPIC_')):
            env.pop(name)
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / 'config'), XDG_CACHE_HOME=str(home / 'cache'),
               XDG_DATA_HOME=str(home / 'data'), CODEBUDDY_CONFIG_DIR=str(home), CODEBUDDY_INTERNET_ENVIRONMENT=region,
               CODEBUDDY_CODE_ENTRYPOINT='sdk-py', DISABLE_AUTOUPDATER='1',
               CODEBUDDY_DISABLE_AUTO_MEMORY='1', CODEBUDDY_CODE_DISABLE_BACKGROUND_TASKS='1')
    if proxy:
        env.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, http_proxy=proxy, https_proxy=proxy,
                   NO_PROXY='localhost,127.0.0.1,::1', no_proxy='localhost,127.0.0.1,::1')
    return env


def command(root, profile, model='', native=False, resume='', binary=None):
    if binary is None:
        from .dependencies.catalog import require
        binary = require(root, profile, 'codebuddy') / 'codebuddy-headless'
        bridge = Path(root) / 'resources/native/linux_aarch64/bridge/lib'
        (bridge / 'ld-linux-aarch64.so.1').chmod(0o755)
        launcher = [str(bridge / 'ld-linux-aarch64.so.1'), '--library-path', str(bridge), str(binary)]
    else:
        launcher = [str(binary)]
    Path(binary).chmod(0o755)
    args = launcher + ['--input-format=stream-json', '--output-format=stream-json', '--verbose',
        '--include-partial-messages', '--replay-user-messages', '--setting-sources', 'none',
        '--strict-mcp-config', '--permission-mode', 'default']
    if not native:
        args += ['--tools', 'AskUserQuestion']
    if model:
        args += ['--model', model]
    if resume:
        args += ['--resume', resume]
    return args


def response(identifier, value=None, error=None):
    result = {'subtype': 'error' if error is not None else 'success', 'request_id': identifier}
    result['error' if error is not None else 'response'] = error if error is not None else (value or {})
    return {'type': 'control_response', 'response': result}


class Connection:
    reusable = True

    def __init__(self, command, profile, cancelled=lambda: False, timeout=60, proxy='', region='external'):
        validate_region(region)
        self.reset(cancelled, timeout)
        self.buffer, self.pending = bytearray(), deque()
        self.sequence, self.pump, self.control = 0, None, None
        work = work_path(profile, region)
        work.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=work, env=environment(profile, proxy, region), bufsize=0,
            start_new_session=True)

    def reset(self, cancelled, timeout):
        """Each turn has its own cancellation event and timeout budget."""
        self.cancelled, self.timeout = cancelled, max(5, timeout)
        self.deadline = time.monotonic() + max(300, self.timeout * 5)
        self.pump = self.control = None

    def alive(self):
        return self.process.poll() is None

    def send(self, value):
        try:
            data = (json.dumps(value, ensure_ascii=False) + '\n').encode()
            view = memoryview(data)
            while view:
                count = self.process.stdin.write(view)
                if not count:
                    raise OSError()
                view = view[count:]
            self.process.stdin.flush()
        except OSError:
            raise AgentError('CodeBuddy 进程已结束。') from None

    def read(self):
        deadline = min(self.deadline, time.monotonic() + self.timeout)
        while time.monotonic() < deadline:
            if self.cancelled():
                raise InterruptedError('已取消 CodeBuddy。')
            if self.pump:
                self.pump()
            if b'\n' in self.buffer:
                line, _, rest = self.buffer.partition(b'\n')
                self.buffer[:] = rest
                if not line:
                    continue
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError()
                    return value
                except (ValueError, UnicodeError):
                    raise AgentError('CodeBuddy 返回了无效消息。') from None
            if select.select([self.process.stdout], [], [], .1)[0]:
                block = os.read(self.process.stdout.fileno(), 65536)
                if not block:
                    raise AgentError('CodeBuddy 进程已结束，请检查组件和网络。')
                self.buffer.extend(block)
                if len(self.buffer) > 50 * 1024 * 1024:
                    raise AgentError('CodeBuddy 返回内容过长。')
        raise AgentError('CodeBuddy 请求超时，请检查网络或稍后重试。')

    def request(self, request):
        self.sequence += 1
        identifier = 'assistant-' + str(self.sequence)
        self.send({'type': 'control_request', 'request_id': identifier, 'request': request})
        while True:
            value = self.read()
            result = value.get('response', {})
            if value.get('type') == 'control_response' and result.get('request_id') == identifier:
                if result.get('subtype') == 'error':
                    raise AgentError('CodeBuddy 协议请求失败。')
                return result.get('response') or {}
            if value.get('type') == 'control_request' and self.control:
                self.control(value)
            else:
                self.pending.append(value)

    def event(self):
        return self.pending.popleft() if self.pending else self.read()

    def close(self):
        self.pump = None
        if self.process.poll() is None:
            try:
                self.send({'type': 'control_request', 'request_id': 'stop', 'request': {'subtype': 'interrupt'}})
            except AgentError:
                pass
            # Include detached descendants, and verify start times before signalling.
            from .intelligence.resident import process_tree, signal_processes
            descendants = process_tree(self.process.pid)
            signal_processes(descendants, signal.SIGTERM)
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=.7)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
            signal_processes(descendants, signal.SIGKILL)
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()


def configured_proxy(values):
    from .proxy import configured_proxy as compose
    try:
        return compose({name.replace('codebuddy_', 'codex_', 1): value for name, value in values.items()
                        if name.startswith('codebuddy_proxy')})
    except ValueError as error:
        raise ValueError(str(error).replace('Codex', 'CodeBuddy')) from None

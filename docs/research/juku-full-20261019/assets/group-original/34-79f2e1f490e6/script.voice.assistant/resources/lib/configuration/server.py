"""Authenticated LAN configuration; Kodi settings are applied by the service thread."""
from ..data_paths import data_path
from concurrent.futures import ThreadPoolExecutor
import copy
import fcntl
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import secrets
import threading
import time
from urllib.parse import urlsplit, parse_qs
import wave
from contextlib import contextmanager, ExitStack


@contextmanager
def idle_operation(profile):
    with (data_path(Path(profile), 'conversation.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('请先结束当前对话，再配置或测试。') from None
        yield


@contextmanager
def idle_input(profile):
    with ExitStack() as stack:
        for name in ('conversation.lock', 'capture.lock', 'invocation.lock'):
            lock = stack.enter_context((data_path(profile, name)).open('a'))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('请先关闭当前弹窗后再修改输入设备或绑定按键。') from None
        yield

from ..settings import FIELDS, Settings, validate, web_schema
from ..storage import write_json
from ..version import VERSION
from ..proxy import configured_proxy
from ..codebuddy_regions import REGIONS, validate_region


SESSION_TTL = 30 * 60


class Configuration:
    def __init__(self, root, profile, addon, rpc, builtin=lambda value: None, port=8767, dependencies=None, settings_open=lambda: False):
        self.root, self.profile, self.addon = Path(root), Path(profile), addon
        self.rpc, self.builtin = rpc, builtin
        self.settings = Settings(addon)
        self.settings_open = settings_open
        self.owns_dependencies = dependencies is None
        if dependencies is None:
            from ..dependencies.service import Manager
            dependencies = Manager(root, profile)
        self.dependencies = dependencies
        self.dependencies.update(self.settings.values())
        self.queue = queue.Queue()
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.job_stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='assistant-config')
        self.token = secrets.token_urlsafe(32)
        self.expires = 0
        self.pin = ''
        self.pair_attempts = {}
        self.last_settings_check = 0
        self.logout_pending = False
        self.input_changed = False
        self.snapshot = {'settings': self.settings.values(), 'schema': web_schema(), 'logged_in': False,
                         'models': [], 'codebuddy_accounts': {region: {'logged_in': False, 'models': [], 'credits': None, 'checked': False}
                                                             for region in REGIONS}, 'jobs': {},
                         'version': VERSION, 'keys': {}}
        self.http = ThreadingHTTPServer(('0.0.0.0', port), self.handler())
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self.http.serve_forever, name='assistant-web', daemon=True)
        self.thread.start()
        self.refresh_keys()
        from ..dependencies.catalog import installed
        self.codex_ready = installed(root, profile, 'codex')
        self.codebuddy_ready = installed(root, profile, 'codebuddy')

    def activate(self):
        self.pin = str(secrets.randbelow(1000000)).zfill(6)
        self.pair_attempts.clear()
        self.expires = time.monotonic() + SESSION_TTL
        if self.codebuddy_ready and self.settings.get('agent_backend') == 'codebuddy':
            try: self.job('codebuddy-account')
            except ValueError: pass
        elif self.codex_ready:
            try: self.job('account')
            except ValueError: pass
        return self.token

    def authenticated(self, supplied):
        return time.monotonic() < self.expires and hmac.compare_digest(supplied or '', self.token)

    def state(self):
        with self.lock:
            value = copy.deepcopy(self.snapshot)
        value['dependencies'] = self.dependencies.state(value['settings'])
        value['codebuddy_ready'] = self.codebuddy_ready
        account = value['codebuddy_accounts'][value['settings']['codebuddy_region']]
        value.update(codebuddy_logged_in=account['logged_in'], codebuddy_models=account['models'])
        from ..voice_binding import binding_status
        value['binding'] = binding_status(self.profile)
        value['secret_configured'] = {}
        for name, field in FIELDS.items():
            if field.secret:
                value['secret_configured'][name] = bool(value['settings'].get(name))
                value['settings'][name] = ''
        return value

    def refresh_keys(self):
        with self.lock:
            self.snapshot['keys'] = {'doubao': (self.profile / 'doubao-api-key.txt').is_file(),
                                      'codex': (self.profile / 'codex-api-key.txt').is_file()}

    def dependency_selection(self, payload):
        """Preview/download a web draft without saving or enabling its modules."""
        changes = payload.get('settings', {})
        allowed = {'recognition_engine', 'onnx_model', 'agent_backend', 'tts_enabled'}
        if not isinstance(changes, dict) or set(changes) - allowed:
            raise ValueError('组件选择无效。')
        with self.lock:
            values = dict(self.snapshot['settings'])
        values.update({name: validate(name, value) for name, value in changes.items()})
        return values

    def pump(self):
        """Called by the Kodi service main thread; handlers never touch xbmcaddon."""
        from ..dependencies.catalog import installed
        ready = installed(self.root, self.profile, 'codex')
        if ready and not self.codex_ready:
            try:
                self.job('account')
                self.codex_ready = True
            except ValueError:
                pass
        ready = installed(self.root, self.profile, 'codebuddy')
        if ready and not self.codebuddy_ready:
            try:
                self.job('codebuddy-account')
                self.codebuddy_ready = True
            except ValueError:
                pass
        if self.logout_pending:
            try:
                with idle_operation(self.profile):
                    if self.settings.values()['recognition_engine'] == 'codex':
                        self.settings.apply({'recognition_engine': 'off'}, logged_in=False)
                    self.logout_pending = False
            except ValueError:
                pass
        if not self.settings_open() and time.monotonic() - self.last_settings_check >= 1:
            with self.lock:
                self.snapshot['settings'] = self.settings.values()
            self.dependencies.update(self.snapshot['settings'])
            self.last_settings_check = time.monotonic()
        for unused in range(10):
            try:
                action, payload, event, result = self.queue.get_nowait()
            except queue.Empty:
                return
            try:
                if action == 'activate':
                    result['token'] = self.activate()
                elif action == 'config':
                    with idle_operation(self.profile):
                        result.update(self.save_config(payload))
                elif action == 'input':
                    with idle_input(self.profile):
                        changes = payload.get('settings')
                        if not isinstance(changes, dict) or not changes or any(
                                name not in FIELDS or FIELDS[name].section != 'input' for name in changes):
                            raise ValueError('音频输入设置无效。')
                        result.update(self.save_config({'settings': changes}))
                        self.input_changed = True
                elif action == 'bind':
                    if self.settings_open():
                        raise ValueError('请先关闭 Kodi 插件设置窗口，再绑定按键。')
                    from ..voice_binding import begin_binding
                    with idle_input(self.profile):
                        identifier = begin_binding(self.profile)
                    self.builtin('RunScript(script.voice.assistant,--bind-voice-key,--bind-request=' + identifier + ')')
                    result.update(ok=True)
                else:
                    raise ValueError('未知配置操作。')
            except ValueError as error:
                result['error'] = str(error)
            except Exception:
                result['error'] = '无法保存设置，请重试。'
            finally:
                event.set()

    def save_config(self, payload):
        if self.settings_open():
            raise ValueError('请先保存或关闭 Kodi 插件设置窗口，再保存网页设置。')
        from ..doubao_config import validate_key, save_key as save_doubao
        from .credentials import save_key as save_codex
        changes, keys = payload.get('settings', {}), payload.get('keys', {})
        if not isinstance(keys, dict) or set(keys) - {'doubao', 'codex'}:
            raise ValueError('凭据类型无效。')
        validated_keys = {name: validate_key(value) for name, value in keys.items() if value}
        changes = dict(changes)
        if 'doubao' in validated_keys:
            changes['doubao_key_file'] = str(self.profile / 'doubao-api-key.txt')
        if 'codex' in validated_keys:
            changes['agent_key_file'] = str(self.profile / 'codex-api-key.txt')
        state = self.state()
        self.settings.validate_changes(changes, state['logged_in'], state['models'])
        for name, key in validated_keys.items():
            (save_doubao if name == 'doubao' else save_codex)(self.profile, key)
        values = self.settings.apply(changes, state['logged_in'], state['models'])
        self.dependencies.update(values)
        self.dependencies.web_saved = True
        with self.lock:
            self.snapshot['settings'] = values
        self.refresh_keys()
        if 'codex' in validated_keys:
            (data_path(self.profile, 'conversation.json')).unlink(missing_ok=True)
        return {'ok': True, 'dependencies': self.dependencies.state(values)}

    def request(self, action, payload):
        event, result = threading.Event(), {}
        self.queue.put((action, payload, event, result))
        if not event.wait(5):
            raise ValueError('配置服务忙，请稍后重试。')
        if result.get('error'):
            raise ValueError(result['error'])
        return result

    def job(self, kind, region=None):
        if kind not in ('account', 'models', 'login', 'logout', 'doubao', 'codex',
                        'codebuddy-account', 'codebuddy-login', 'codebuddy-logout', 'codebuddy-test'):
            raise ValueError('未知测试或账号操作。')
        with self.lock:
            values = dict(self.snapshot['settings'])
            if kind.startswith('codebuddy-'):
                region = validate_region(region if region is not None else values['codebuddy_region'])
                values['codebuddy_region'] = region
            elif region is not None:
                raise ValueError('此操作不支持选择 CodeBuddy 区域。')
            if any(v.get('state') == 'running' for v in self.snapshot['jobs'].values()):
                raise ValueError('请先等待当前测试或登录结束。')
            identifier = secrets.token_hex(12)
            self.snapshot['jobs'] = {identifier: {'state': 'running', 'kind': kind}}
            if region is not None:
                self.snapshot['jobs'][identifier]['region'] = region
            cancelled_event = threading.Event()
            self.job_stop = cancelled_event

        def cancelled():
            return self.stop.is_set() or cancelled_event.is_set()

        def work():
            result = {}
            began = time.monotonic()
            try:
                with idle_operation(self.profile), (data_path(self.profile, 'capture.lock')).open('a') as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        raise ValueError('请先结束当前语音，再运行配置或测试。') from None
                    if kind in ('account', 'models', 'login', 'logout'):
                        from ..codex_account import CodexAccount
                        with CodexAccount(self.root, self.profile, cancelled,
                                          proxy=configured_proxy(values)) as account:
                            def show(challenge):
                                with self.lock:
                                    self.snapshot['jobs'][identifier].update(url=challenge['url'], code=challenge['code'])
                            status = account.login(show) if kind == 'login' else (
                                account.logout() if kind == 'logout' else account.status())
                            models = account.models() if status['logged_in'] else []
                            models = [{k: m[k] for k in ('model', 'displayName', 'defaultReasoningEffort',
                                'supportedReasoningEfforts', 'isDefault') if k in m} for m in models]
                        with self.lock:
                            self.snapshot.update(logged_in=status['logged_in'], models=models)
                        if kind in ('login', 'logout'):
                            (data_path(self.profile, 'conversation.json')).unlink(missing_ok=True)
                        if kind == 'logout':
                            self.logout_pending = True
                        result = {'logged_in': status['logged_in'], 'models': len(models)}
                    elif kind in ('codebuddy-account', 'codebuddy-login', 'codebuddy-logout'):
                        from ..codebuddy_account import CodeBuddyAccount
                        from ..codebuddy_protocol import configured_proxy as buddy_proxy
                        with CodeBuddyAccount(self.root, self.profile, cancelled,
                                              proxy=buddy_proxy(values), region=region) as account:
                            def show_buddy(challenge):
                                with self.lock:
                                    self.snapshot['jobs'][identifier].update(url=challenge['url'])
                            status = account.login(show_buddy) if kind == 'codebuddy-login' else (
                                account.logout() if kind == 'codebuddy-logout' else account.status())
                        if kind == 'codebuddy-login' and status['logged_in']:
                            # The login process's initial model list predates authorization.
                            with CodeBuddyAccount(self.root, self.profile, cancelled,
                                                  proxy=buddy_proxy(values), region=region) as account:
                                status = account.status()
                        with self.lock:
                            self.snapshot['codebuddy_accounts'][region] = dict(status, checked=True)
                            active = self.snapshot['settings']
                            invalidate = active['agent_backend'] == 'codebuddy' and active['codebuddy_region'] == region
                        if kind != 'codebuddy-account' and invalidate:
                            (data_path(self.profile, 'conversation.json')).unlink(missing_ok=True)
                        result = {'logged_in': status['logged_in'], 'models': len(status['models'])}
                    elif kind == 'doubao':
                        from ..doubao_recognizer import DoubaoRecognizer
                        with wave.open(str(self.root / 'resources/config/asr-test.wav'), 'rb') as source:
                            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                                raise ValueError('测试音频格式不正确。')
                            pcm = source.readframes(source.getnframes())
                        with DoubaoRecognizer(self.root, self.profile, values['doubao_resource_id'],
                            values['doubao_timeout'], cancelled, key_file=values['doubao_key_file']) as engine:
                            for offset in range(0, len(pcm), 3200):
                                engine.accept(pcm[offset:offset + 3200])
                            result = {'text': engine.finish(), 'expected': '甚至出现交易几乎停滞的情况。'}
                    else:
                        from ..intelligence.runtime import create_agent
                        # Tests use only a fixed public instruction, no production history/tools/commands.
                        test_values = dict(values, permission_level='media', approval_strategy='request',
                            codebuddy_approval_strategy='request',
                            agent_backend='codebuddy' if kind == 'codebuddy-test' else 'codex')
                        agent, tools = create_agent(self.root, self.profile, test_values, self.rpc)
                        tools.definitions = lambda: []
                        outcome = agent.run('这是配置连接测试。不要执行工具，只回复“连接正常”。', cancelled=cancelled)
                        from ..intelligence.presentation import parse
                        result = {'reply': parse(outcome['reply'], tools)['message']}
                result.update(state='done', kind=kind, elapsed_seconds=round(time.monotonic() - began, 3))
            except InterruptedError:
                result = {'state': 'cancelled', 'kind': kind}
            except Exception as error:
                if kind in ('account', 'models', 'login', 'logout'):
                    from ..codex_account import login_error
                    message = login_error(error)
                else:
                    message = str(error) if isinstance(error, (ValueError, RuntimeError)) else '测试失败，请检查网络和配置。'
                result = {'state': 'error', 'kind': kind, 'error': message[:600]}
            with self.lock:
                if region is not None:
                    result['region'] = region
                self.snapshot['jobs'][identifier] = result

        self.pool.submit(work)
        return {'job': identifier}

    def cancel_job(self):
        self.job_stop.set()
        return {'ok': True}

    def handler(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value, content_type='application/json; charset=utf-8'):
                data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Frame-Options', 'DENY')
                self.end_headers()
                self.wfile.write(data)

            def valid_origin(self):
                host = self.headers.get('Host', '')
                try:
                    parsed = urlsplit('http://' + host)
                    import ipaddress
                    valid_host = parsed.hostname in ('localhost',) or ipaddress.ip_address(parsed.hostname).is_private
                except (ValueError, TypeError):
                    valid_host = False
                origin = self.headers.get('Origin')
                return valid_host and (not origin or origin == 'http://' + host)

            def valid_request(self):
                supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
                return self.valid_origin() and owner.authenticated(supplied)

            def do_GET(self):
                if self.path in ('/', '/index.html'):
                    return self.reply(200, (owner.root / 'resources/web/index.html').read_bytes(), 'text/html; charset=utf-8')
                if not self.valid_request():
                    return self.reply(401, {'error': '配置入口已关闭或过期，请重新扫码。'})
                if self.path == '/api/state':
                    return self.reply(200, owner.state())
                self.reply(404, {'error': '页面不存在。'})

            def do_POST(self):
                pairing = self.path == '/api/pair'
                if not self.valid_origin() or (not pairing and not self.valid_request()):
                    return self.reply(401, {'error': '配置入口已关闭或过期，请重新扫码。'})
                try:
                    if urlsplit(self.path).path == '/api/dependencies/upload':
                        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                        if set(query) != {'filename'} or len(query['filename']) != 1:
                            raise ValueError('依赖文件名无效。')
                        if (self.headers.get('Content-Type', '').split(';')[0] != 'application/octet-stream'
                                or self.headers.get('Transfer-Encoding')):
                            raise ValueError('上传数据格式无效。')
                        length = int(self.headers.get('Content-Length', '0'))
                        self.connection.settimeout(10)
                        result = owner.dependencies.upload(query['filename'][0], length, self.rfile)
                        with owner.lock:
                            owner.expires = time.monotonic() + SESSION_TTL
                        return self.reply(200, result)
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 32768 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                        raise ValueError('配置数据无效。')
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict):
                        raise ValueError('配置数据无效。')
                    if pairing:
                        address = self.client_address[0]
                        with owner.lock:
                            attempts = owner.pair_attempts.get(address, 0) + 1
                            owner.pair_attempts[address] = attempts
                            code = payload.get('code', '')
                            if (attempts > 5 or not isinstance(code, str) or len(code) != 6 or
                                not code.isascii() or not hmac.compare_digest(code, owner.pin) or
                                time.monotonic() >= owner.expires):
                                raise ValueError('配置码错误或已过期，请重新打开电视上的扫码配置。')
                        value = {'token': owner.token}
                    elif self.path == '/api/config':
                        value = owner.request('config', payload)
                    elif self.path == '/api/input':
                        value = owner.request('input', payload)
                    elif self.path == '/api/input/bind':
                        value = owner.request('bind', payload)
                    elif self.path == '/api/dependencies/preview':
                        value = owner.dependencies.state(owner.dependency_selection(payload))
                    elif self.path == '/api/dependencies/download':
                        selection = owner.dependency_selection(payload)
                        owner.dependencies.start(selection)
                        value = owner.dependencies.state(selection)
                    elif self.path == '/api/dependencies/cancel':
                        owner.dependencies.cancel()
                        value = {'ok': True}
                    elif self.path == '/api/job/cancel':
                        value = owner.cancel_job()
                    elif self.path.startswith('/api/job/'):
                        if set(payload) - {'region'}:
                            raise ValueError('账号操作参数无效。')
                        value = owner.job(self.path[len('/api/job/'):], **payload)
                    else:
                        return self.reply(404, {'error': '操作不存在。'})
                    if self.path in ('/api/config', '/api/input'):
                        with owner.lock:
                            owner.expires = time.monotonic() + SESSION_TTL
                    self.reply(200, value)
                except (ValueError, TypeError, InterruptedError, TimeoutError) as error:
                    self.reply(400, {'error': str(error)[:400]})
                except Exception:
                    self.reply(500, {'error': '配置服务暂时不可用。'})
        return Handler

    def close(self):
        self.stop.set()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=1)
        self.pool.shutdown(wait=True)
        if self.owns_dependencies:
            self.dependencies.close()

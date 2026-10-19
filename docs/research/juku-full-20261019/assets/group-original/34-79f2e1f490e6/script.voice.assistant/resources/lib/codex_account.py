"""Managed ChatGPT device-code login using the official Codex app-server."""
from .data_paths import data_path
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from .intelligence.errors import AgentError
from .codex_agent import Connection, launch_command, private_codex_home, validate_proxy
from .version import VERSION


def device_challenge(value):
    if not isinstance(value, dict) or value.get('type') != 'chatgptDeviceCode':
        raise AgentError('当前 Codex 未返回设备码登录，请检查版本。')
    url, code = value.get('verificationUrl', ''), value.get('userCode', '')
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == 'https' and parsed.hostname == 'auth.openai.com'
                 and parsed.path.rstrip('/') == '/codex/device'
                 and parsed.port in (None, 443) and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment)
    except (ValueError, TypeError):
        valid = False
    if not valid or not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9-]{4,32}', code):
        raise AgentError('Codex 登录地址或设备码无效，请重试。')
    login_id = value.get('loginId')
    if not isinstance(login_id, str) or not 1 <= len(login_id) <= 100:
        raise AgentError('Codex 登录会话无效，请重试。')
    return {'login_id': login_id, 'url': url, 'code': code}


def account_summary(value):
    account = value.get('account') if isinstance(value, dict) else None
    if not isinstance(account, dict) or account.get('type') != 'chatgpt':
        return {'logged_in': False, 'email': '', 'plan': ''}
    email, plan = account.get('email'), account.get('planType')
    return {'logged_in': True, 'email': email[:320] if isinstance(email, str) else '',
            'plan': plan[:40] if isinstance(plan, str) else ''}


def login_error(error):
    message = str(error).lower()
    if '403' in message or 'unsupported_country' in message:
        return 'OpenAI 登录服务拒绝了连接。请检查盒子的网络和账号访问条件。'
    if 'device' in message and ('disabled' in message or 'not enabled' in message):
        return '请先在账号安全设置或工作区权限中启用 Codex 设备码登录，然后重试。'
    if '超时' in message or 'timed out' in message or 'timeout' in message:
        return '登录等待超时，请重新扫码登录。'
    if isinstance(error, AgentError) and message.startswith(('codex 登录', '当前 codex', '未安装 codex',
                                                            '设备码登录', '登录已完成')):
        return str(error)
    return 'Codex 登录未完成。请检查网络、设备码登录设置，或重新扫码。'


class CodexAccount:
    def __init__(self, root, profile, cancelled=lambda: False, timeout=30,
                 binary=None, connection_factory=Connection, proxy=''):
        self.root, self.profile = Path(root), Path(profile)
        if binary:
            self.binary = Path(binary)
        else:
            from .dependencies.catalog import codex_binary
            self.binary = codex_binary(root, profile)
        self.cancelled, self.timeout = cancelled, timeout
        self.connection_factory = connection_factory
        self.proxy = validate_proxy(proxy)
        self.connection = None
        self.login_id = None

    def __enter__(self):
        if not self.binary.is_file():
            raise AgentError('未安装 Codex，请在设置中下载所需组件。')
        self.binary.chmod(0o755)
        home = private_codex_home(self.profile)
        work = data_path(self.profile, 'codex-work')
        work.mkdir(parents=True, exist_ok=True)
        self.connection = self.connection_factory(
            launch_command(self.binary, '', '', self.timeout, 'chatgpt'),
            '', work, self.cancelled, self.timeout, home, self.proxy)
        try:
            self.connection.request('initialize', {
                'clientInfo': {'name': 'coreelec_voice_assistant',
                               'title': 'CoreELEC Voice Assistant', 'version': VERSION},
                'capabilities': {'experimentalApi': True}})
            self.connection.send({'method': 'initialized'})
            return self
        except Exception:
            self.connection.close()
            raise

    def status(self):
        return account_summary(self.connection.request('account/read', {'refreshToken': False}))

    def models(self):
        models, cursor = [], None
        while True:
            params = {'limit': 50, 'includeHidden': False}
            if cursor:
                params['cursor'] = cursor
            value = self.connection.request('model/list', params)
            models.extend(value.get('data', []))
            cursor = value.get('nextCursor')
            if not cursor or len(models) >= 200:
                return models

    def login(self, show_code, wait_seconds=600):
        value = self.connection.request('account/login/start', {'type': 'chatgptDeviceCode'})
        # Retain the attempt ID even if validation fails, so close cancels it.
        if isinstance(value, dict) and isinstance(value.get('loginId'), str):
            self.login_id = value['loginId']
        challenge = device_challenge(value)
        wait_seconds = max(1, min(900, wait_seconds))
        show_code(challenge)
        self.connection.timeout = wait_seconds
        self.connection.deadline = time.monotonic() + wait_seconds
        while True:
            if self.cancelled():
                raise InterruptedError('已取消 Codex 登录。')
            event = self.connection.event()
            params = event.get('params', {})
            if (event.get('method') == 'account/login/completed'
                    and params.get('loginId') == self.login_id):
                if not params.get('success'):
                    raise AgentError('设备码登录未完成或已过期。请重试，并确认账号已允许 Codex 设备码登录。')
                self.login_id = None
                self.connection.timeout = self.timeout
                self.connection.deadline = time.monotonic() + max(60, self.timeout * 5)
                account = self.status()
                if not account['logged_in']:
                    raise AgentError('登录已完成，但尚未读取到 Codex 账号，请重试查看登录状态。')
                auth = private_codex_home(self.profile) / 'auth.json'
                if auth.is_file():
                    auth.chmod(0o600)
                return account

    def logout(self):
        self.connection.request('account/logout', {})
        return self.status()

    def close(self):
        if self.connection is not None:
            if self.login_id:
                try:
                    self.connection.sequence += 1
                    self.connection.send({'id': self.connection.sequence, 'method': 'account/login/cancel',
                                          'params': {'loginId': self.login_id}})
                except (AgentError, OSError):
                    pass
            self.connection.close()
            self.connection = None

    def __exit__(self, *args):
        self.close()

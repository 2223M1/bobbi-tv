"""CodeBuddy login isolated by region within the addon's private data directory."""
from .data_paths import data_path
from pathlib import Path
import fcntl
from urllib.parse import urlsplit

from .codebuddy_protocol import Connection, command, response
from .intelligence.errors import AgentError
from .codebuddy_regions import home_path, validate_region, invalidate_auth


class CodeBuddyAccount:
    def __init__(self, root, profile, cancelled=lambda: False, proxy='', binary=None, region='external'):
        self.profile = Path(profile)
        self.proxy, self.cancelled = proxy, cancelled
        self.region = validate_region(region)
        self.profile.mkdir(parents=True, exist_ok=True)
        self.lock = (data_path(self.profile, 'codebuddy-account.lock')).open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.connection = Connection(command(root, profile, binary=binary), profile, cancelled, 30, proxy, region)
        except BaseException:
            self.lock.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            self.connection.close()
            home = home_path(self.profile, self.region)
            if home.exists():
                for path in home.rglob('*'):
                    if not path.is_symlink():
                        path.chmod(0o700 if path.is_dir() else 0o600)
        finally:
            self.lock.close()

    def initialize(self):
        return self.connection.request({'subtype': 'initialize', 'environment': self.region,
                                        'hasPrompt': False})

    @staticmethod
    def public(value):
        account = value.get('account') or {}
        return {'logged_in': bool(account.get('userId') and account.get('token')),
                'models': [{'model': item['id'], 'displayName': item.get('name') or item['id']}
                           for item in value.get('models', []) if isinstance(item.get('id'), str)]}

    def status(self):
        from .codebuddy_metadata import credits, model_prices, multiplier
        initialized = self.initialize()
        result = self.public(initialized)
        result['credits'] = None
        if result['logged_in']:
            account = initialized.get('account') or {}
            prices = model_prices(self.profile, self.region, account)
            original = {item['id']: item for item in initialized.get('models', [])
                        if isinstance(item, dict) and isinstance(item.get('id'), str)}
            for item in result['models']:
                rate = multiplier(original[item['model']].get('credits'))
                item['multiplier'] = rate if rate is not None else prices.get(item['model'])
            default = initialized.get('currentModelId')
            if isinstance(default, str):
                result['default_model'] = default
            result['credits'] = credits(account, self.region, self.proxy, self.cancelled)
        return result

    def logout(self):
        self.connection.request({'subtype': 'logout', 'environment': self.region})
        invalidate_auth(self.profile, self.region)
        return {'logged_in': False, 'models': [], 'credits': None}

    def login(self, show):
        initialized = self.initialize()
        if self.public(initialized)['logged_in']:
            return self.public(initialized)
        self.connection.timeout = 300
        self.connection.send({'type': 'control_request', 'request_id': 'login',
            'request': {'subtype': 'authenticate', 'environment': self.region, 'methodId': self.region}})
        while True:
            value = self.connection.event()
            if value.get('type') == 'control_response':
                result = value.get('response') or {}
                if result.get('request_id') == 'login' and result.get('subtype') == 'error':
                    raise AgentError('CodeBuddy 登录失败，请检查网络或重试。')
            if value.get('type') != 'control_request':
                continue
            request = value.get('request') or {}
            identifier = value.get('request_id')
            if request.get('subtype') == 'auth_url_callback':
                url = (request.get('authState') or {}).get('authUrl', '')
                parsed = urlsplit(url)
                if parsed.scheme != 'https' or not parsed.hostname or not any(
                        parsed.hostname == host or parsed.hostname.endswith('.' + host)
                        for host in ('codebuddy.ai', 'codebuddy.cn', 'tencent.com')):
                    raise AgentError('CodeBuddy 返回了无法验证的登录地址。')
                show({'url': url, 'code': ''})
                self.connection.send(response(identifier, {'received': True}))
            elif request.get('subtype') == 'auth_result_callback':
                self.connection.send(response(identifier, {'handled': True}))
                if not request.get('success') or not (request.get('userinfo') or {}).get('userId'):
                    raise AgentError('CodeBuddy 登录未完成，请重试。')
                invalidate_auth(self.profile, self.region)
                return {'logged_in': True, 'models': self.public(initialized)['models']}

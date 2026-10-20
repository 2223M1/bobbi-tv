"""Independent implementation of the IDE's sentence dictation HTTP protocol.

The endpoint is observed in the installed client, not a documented stable API.
Only the plugin's managed native account supplies credentials. No IDE storage,
language, hotwords, conversation, or audio processing is involved.
"""
import base64
import io
import json
import secrets
import socket
import urllib.error
import urllib.request
import wave

from .codex_account import CodexAccount
from .codex_agent import Connection, validate_proxy
from .http_proxy import AuthenticatedProxyHandler

ENDPOINT = 'https://chatgpt.com/backend-api/transcribe'
MAX_PCM = 30 * 32000
MAX_RESPONSE = 65536
# Match the installed extension used for the on-device identity comparison.
DICTATION_ORIGINATOR = 'codex_vscode'
DICTATION_CLIENT = {'name': 'VS Code', 'title': 'Codex Extension', 'version': '26.1007.21434'}


class DictationError(RuntimeError):
    """Only static messages from this module may cross the worker boundary."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DictationConnection(Connection):
    """Use the extension's identity only for the dictation auth subprocess."""
    def __init__(self, command, *args):
        self.user_agent = DICTATION_ORIGINATOR
        # Child-only environment; retain the worker's process group so cancelling
        # recognition also stops native authentication. Agent/login are unchanged.
        super().__init__(['env', 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE=' + DICTATION_ORIGINATOR] + command,
                         *args, start_new_session=False)

    def request(self, method, params):
        if method == 'initialize':
            params = dict(params, clientInfo=dict(DICTATION_CLIENT))
        result = super().request(method, params)
        if method == 'initialize':
            self.user_agent = result.get('userAgent') or DICTATION_ORIGINATOR
        return result


def authorization(status, user_agent=DICTATION_ORIGINATOR):
    if not isinstance(status, dict):
        raise DictationError('无法读取 Codex 登录状态，请重新登录。')
    token = status.get('authToken')
    if (status.get('authMethod') not in ('chatgpt', 'chatgptAuthTokens')
            or not isinstance(token, str) or not token):
        raise DictationError('请在插件设置 → 智能体 → 登录 Codex 中完成登录。')
    try:
        if len(token) > 32768 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError()
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError()
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
        identity = claims['https://api.openai.com/auth']['chatgpt_account_id']
        if (not isinstance(identity, str) or not 1 <= len(identity) <= 200
                or any(ord(c) < 33 or ord(c) > 126 for c in identity)):
            raise ValueError()
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise DictationError('Codex 登录凭据无效，请重新登录。') from None
    if (not isinstance(user_agent, str) or not 1 <= len(user_agent) <= 1024
            or any(ord(c) < 32 or ord(c) > 126 for c in user_agent)):
        raise DictationError('订阅听写客户端标识无效，请更新插件。')
    return {'Authorization': 'Bearer ' + token, 'ChatGPT-Account-Id': identity,
            'originator': DICTATION_ORIGINATOR, 'User-Agent': user_agent}


def managed_headers(root, profile, timeout, proxy='', refresh=False):
    try:
        with CodexAccount(root, profile, timeout=timeout, proxy=proxy,
                          connection_factory=DictationConnection) as account:
            status = account.connection.request('getAuthStatus',
                                               {'includeToken': True, 'refreshToken': refresh})
            return authorization(status, account.connection.user_agent)
    except DictationError:
        raise
    except Exception:
        # Native errors may contain response bodies. Never echo those to Kodi.
        raise DictationError('无法获取 Codex 订阅登录状态，请检查网络或重新登录。') from None


def multipart_pcm(pcm):
    if not pcm or len(pcm) % 2 or len(pcm) > MAX_PCM:
        raise DictationError('订阅听写音频无效，单次最多 30 秒。')
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(pcm)
    boundary = '----coreelec-dictation-' + secrets.token_hex(16)
    body = (('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="voice.wav"\r\n'
             'Content-Type: audio/wav\r\n\r\n').encode('ascii') + audio.getvalue()
            + ('\r\n--' + boundary + '--\r\n').encode('ascii'))
    return body, 'multipart/form-data; boundary=' + boundary


def transcribe(pcm, headers, refresh_headers, timeout=30, proxy='', opener=None):
    body, content_type = multipart_pcm(pcm)
    proxy = validate_proxy(proxy)
    if opener is None:
        handlers = [NoRedirect()]
        if proxy:
            handlers.append(AuthenticatedProxyHandler({'http': proxy, 'https': proxy}))
        opener = urllib.request.build_opener(*handlers)
    identity = headers.get('ChatGPT-Account-Id')
    for attempt in range(2):
        request = urllib.request.Request(ENDPOINT, data=body,
            headers=dict(headers, **{'Content-Type': content_type}), method='POST')
        try:
            with opener.open(request, timeout=timeout) as response:
                data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise DictationError('订阅听写返回内容过长。')
            try:
                result = json.loads(data)
            except (ValueError, UnicodeError):
                raise DictationError('订阅听写返回格式无效，请稍后重试。') from None
            text = result.get('text') if isinstance(result, dict) else None
            if not isinstance(text, str) or len(text) > 4000:
                raise DictationError('订阅听写返回文字无效，请稍后重试。')
            return text.strip()
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code == 401 and attempt == 0:
                headers = refresh_headers()
                if headers.get('ChatGPT-Account-Id') != identity:
                    raise DictationError('Codex 登录账号已改变，请重新录音。')
                continue
            messages = {400: '订阅听写请求被拒绝，请更新插件后重试。',
                        401: 'Codex 登录已过期，请重新扫码登录 Codex。',
                        403: '订阅听写访问被拒绝，请检查盒子网络或账号权限。',
                        429: '订阅听写请求过于频繁，请稍后重试。'}
            raise DictationError(messages.get(code, '订阅听写服务暂时不可用，请稍后重试。')) from None
        except (TimeoutError, socket.timeout):
            raise DictationError('订阅听写请求超时，请稍后重试。') from None
        except (urllib.error.URLError, OSError):
            raise DictationError('无法连接订阅听写，请检查盒子网络或 Codex 代理设置。') from None

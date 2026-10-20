"""Private plaintext API credentials; no Kodi dependency."""
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit


DEFAULT_URL = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-flash'


def validate_url(value):
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    local = parsed.hostname in ('localhost', '127.0.0.1', '::1')
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and local)) or not parsed.hostname:
        raise ValueError('AI 接口地址必须使用 HTTPS；本机测试可使用 HTTP。')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('AI 接口地址不能包含账号、密码或查询参数。')
    return value


def read_key_file(path):
    text = Path(path).read_text(encoding='utf-8-sig').strip()
    match = re.search(r'\bsk-[A-Za-z0-9_-]{16,}\b', text)
    if match:
        return match.group()
    if text and len(text) <= 512 and not any(char.isspace() or ord(char) < 33 or ord(char) > 126 for char in text):
        return text
    raise ValueError('API Key 文件应只包含一个有效的 Key。')


def save_key(profile, key):
    from ..storage import atomic_write
    key = key.strip()
    if not key or len(key) > 512 or any(char.isspace() or ord(char) < 33 or ord(char) > 126 for char in key):
        raise ValueError('API Key 不能为空，也不能包含空白字符。')
    path = Path(profile) / 'codex-api-key.txt'
    atomic_write(path, key + '\n')
    path.chmod(0o600)


def load_key(profile, key_file=''):
    try:
        path = Path(key_file) if key_file else Path(profile) / 'codex-api-key.txt'
        return read_key_file(path)
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('请配置 API Key：在插件设置 → Codex 智能体选择 Key 文件，或在扫码配置网页填写 Key。') from None


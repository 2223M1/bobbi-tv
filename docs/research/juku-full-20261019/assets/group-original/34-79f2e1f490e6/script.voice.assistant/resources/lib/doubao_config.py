"""Private Doubao ASR credentials, separate from the AI Agent's credentials."""
import json
from pathlib import Path

from .storage import atomic_write

DEFAULT_RESOURCE = 'volc.seedasr.sauc.duration'
RESOURCES = (DEFAULT_RESOURCE, 'volc.seedasr.sauc.concurrent',
             'volc.bigasr.sauc.duration', 'volc.bigasr.sauc.concurrent')


def validate_key(value):
    if not isinstance(value, str):
        raise ValueError('豆包 API Key 格式无效。')
    value = value.strip()
    if not value or len(value) > 512 or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError('豆包 API Key 不能为空，也不能包含空白或控制字符。')
    return value


def read_key_file(path):
    value = Path(path).read_text(encoding='utf-8-sig').strip()
    if value.startswith('{'):
        try:
            value = json.loads(value)['api_key']
        except (ValueError, KeyError, TypeError):
            raise ValueError('豆包凭据文件需包含 api_key。') from None
    return validate_key(value)


def save_key(profile, value):
    path = Path(profile) / 'doubao-api-key.txt'
    atomic_write(path, validate_key(value) + '\n')
    path.chmod(0o600)


def load_key(profile, key_file=''):
    try:
        path = Path(key_file) if key_file else Path(profile) / 'doubao-api-key.txt'
        return read_key_file(path)
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('请配置 API Key：在插件设置 → 语音转文字选择 Key 文件，或在扫码配置网页填写豆包 Key。') from None


def validate_resource(value):
    if value not in RESOURCES:
        raise ValueError('豆包识别资源类型无效。')
    return value

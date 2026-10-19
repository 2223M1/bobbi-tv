"""Shared HTTP proxy configuration for native Codex and Python dictation."""
from urllib.parse import quote, unquote, urlsplit


def validate_proxy(value, allow_credentials=True):
    value = (value or '').strip()
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        valid = (len(value) <= 10000 and not any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in value)
                 and parsed.scheme in ('http', 'https') and parsed.hostname
                 and parsed.port != 0 and parsed.path in ('', '/')
                 and not parsed.query and not parsed.fragment)
        if parsed.username is not None or parsed.password is not None:
            user = unquote(parsed.username or '', errors='strict')
            password = unquote(parsed.password or '', errors='strict')
            valid = (valid and allow_credentials and bool(user) and parsed.password is not None
                     and ':' not in user and not any(ord(c) < 32 or ord(c) == 127 for c in user + password))
    except (ValueError, TypeError, UnicodeError):
        valid = False
    if not valid:
        raise ValueError('Codex 代理地址应为 http://地址:端口；用户名和密码请填写到单独的设置项。')
    return value


def configured_proxy(values):
    """Compose credentials only at the runtime boundary, never into saved URLs."""
    address = validate_proxy(values.get('codex_proxy', ''), allow_credentials=False)
    if not address:
        return ''
    user = values.get('codex_proxy_username', '')
    password = values.get('codex_proxy_password', '')
    if not user:
        if password:
            raise ValueError('填写 Codex 代理密码时也需要填写代理用户名。')
        return address
    parsed = urlsplit(address)
    result = parsed._replace(netloc=quote(user, safe='') + ':' + quote(password, safe='') + '@' + parsed.netloc).geturl()
    return validate_proxy(result)



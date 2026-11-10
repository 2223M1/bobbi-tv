"""Personal-file admission into the existing bounded Range stream engine.

This is not a catalog locator or inferred TMDb identity. Only an explicitly
selected file may be registered. Credentials remain inside the Host resolver.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlencode

from .pan_accounts import PanError, provider_id
from .pan_tokens import original_url, text, number

CDN = {
    'quark': ('quark.cn',), 'uc': ('uc.cn',), 'baidu': ('baidupcs.com', 'd.pcs.baidu.com'),
    'aliyun': ('alipan.com', 'aliyundrive.com', 'aliyunpds.com'),
    '123': ('123pan.cn', '123pan.com', '123684.com', '123865.com'),
    'guangya': ('guangyapan.com', 'aliyuncs.com'),
    'xunlei': ('xunlei.com',),
    '189': ('189.cn', 'ctyun.cn', 'ctyunapi.cn'), '139': ('139.com', 'caiyun.feixin.10086.cn'),
}
REFERER = {'quark': 'https://pan.quark.cn/', 'uc': 'https://drive.uc.cn/', 'baidu': 'https://pan.baidu.com/',
           'aliyun': 'https://www.alipan.com/', '123': 'https://yun.123pan.cn/'}
EXTENSIONS = frozenset(('mkv', 'mp4', 'm4v', 'avi', 'ts', 'm2ts', 'webm', 'mov'))


def body(provider, selected, request):
    provider_id(provider)
    if provider not in CDN or type(selected) is not dict or selected.get('directory') is not False:
        raise PanError('PAN_SELECTION_INVALID')
    title, size = text(selected.get('name')), number(selected.get('size'), 1)
    if (re.search(r'[/\\]', title) or title.rsplit('.', 1)[-1].lower() not in EXTENSIONS
            or size > 512 * 1024**3 or type(request) is not str or not re.fullmatch('[0-9a-f]{32}', request)):
        raise PanError('PAN_SELECTION_INVALID')
    try:
        canonical = json.dumps(selected, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError):
        raise PanError('PAN_SELECTION_INVALID') from None
    if len(canonical) > 10000:
        raise PanError('PAN_SELECTION_INVALID')
    digest = hashlib.sha256((provider + ':' + canonical).encode('ascii')).hexdigest()
    return dict(request_id=request, locator='bobbipan://' + provider + '/' + digest,
                guid='pan:' + digest, media='file:' + digest, title=title, size=size,
                provider=provider, selected=deepcopy(selected))


def checked(value):
    if type(value) is not dict or set(value) != {'request_id', 'locator', 'guid', 'media', 'title', 'size', 'provider', 'selected'}:
        raise PanError('PAN_SELECTION_INVALID')
    expected = body(value['provider'], value['selected'], value['request_id'])
    if expected != value:
        raise PanError('PAN_SELECTION_INVALID')
    return expected


def headers(value, url, values):
    provider = value['provider']
    original_url(url, CDN[provider])
    if (type(values) is not dict or not {'User-Agent'} <= set(values) <= {'User-Agent', 'Referer', 'Cookie'}
            or any(type(v) is not str or not v or len(v) > 16384 or not v.isascii()
                   or re.search(r'[\x00-\x1f\x7f]', v) for v in values.values())):
        return False
    if 'Referer' in values and values['Referer'] != REFERER.get(provider):
        return False
    # Cookie-backed adapters supply only CookieJar's exact-domain projection.
    # Token adapters never place Authorization or other secrets on a CDN.
    if 'Cookie' in values and provider not in ('quark', 'uc', 'baidu'):
        return False
    return True


def address(value, resolved):
    if (type(resolved) is not dict or set(resolved) != {'url', 'size', 'original', 'headers'}
            or resolved['original'] is not True or type(resolved['size']) is not int
            or resolved['size'] != value['size'] or type(resolved['headers']) is not dict):
        raise PanError('PAN_FILE_CHANGED')
    # Empty Cookie is normal for a different CDN domain and must stay absent.
    h = {k: v for k, v in resolved['headers'].items() if k != 'Cookie' or v}
    if not headers(value, resolved['url'], h):
        raise PanError('PAN_DOWNLOAD_ORIGIN_REJECTED')
    return resolved['url'] + '|' + urlencode(h)

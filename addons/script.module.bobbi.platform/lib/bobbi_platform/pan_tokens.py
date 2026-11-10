"""Small strict primitives shared by independently implemented token adapters."""
from copy import deepcopy
import re
from urllib.parse import urlsplit

from .pan_accounts import PanError


def text(value, limit=1024):
    if (type(value) is not str or not 0 < len(value) <= limit
            or re.search(r'[\x00-\x1f\x7f]', value)):
        raise PanError('PAN_REPLY_INVALID')
    return value


def token(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,8192}', value):
        raise PanError('PAN_CREDENTIALS_INVALID')
    return value


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise PanError('PAN_FILE_ID_INVALID')
    return value


def number(value, minimum=0):
    if type(value) is not int or not minimum <= value < 2**63:
        raise PanError('PAN_REPLY_INVALID')
    return value


def decimal(value):
    if type(value) is int:
        value = str(number(value))
    if type(value) is not str or not re.fullmatch(r'0|[1-9][0-9]{0,19}', value):
        raise PanError('PAN_FILE_ID_INVALID')
    if int(value) >= 2**63:
        raise PanError('PAN_FILE_ID_INVALID')
    return value


def saved(provider, value, fields):
    if type(value) is not dict or set(value) != fields or value.get('provider') != provider:
        raise PanError('PAN_CREDENTIALS_INVALID')
    identifier(value.get('subject'))
    token(value.get('access_token'))
    return deepcopy(value)


def page_number(page, size):
    if type(page) is not int or not 1 <= page <= 10000 or type(size) is not int or not 1 <= size <= 20:
        raise PanError('PAN_PAGE_INVALID')


def listing(rows, total, page, size, convert):
    if type(rows) is not list or len(rows) > size:
        raise PanError('PAN_REPLY_INVALID')
    number(total)
    items = [convert(row) for row in rows]
    if len({r['file_id'] for r in items}) != len(items):
        raise PanError('PAN_REPLY_INVALID')
    more = page * size < total
    if more and not rows:
        raise PanError('PAN_REPLY_INVALID')
    return dict(items=items, page=page, has_more=more)


def original_url(value, domains):
    text(value, 16384)
    try:
        url = urlsplit(value)
        if (url.scheme != 'https' or url.username or url.password or url.fragment
                or url.port not in (None, 443) or not url.hostname
                or not any(url.hostname == d or url.hostname.endswith('.' + d) for d in domains)):
            raise ValueError
    except ValueError:
        raise PanError('PAN_DOWNLOAD_ORIGIN_REJECTED') from None
    return value

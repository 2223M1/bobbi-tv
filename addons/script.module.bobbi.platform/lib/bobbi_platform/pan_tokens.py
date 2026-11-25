"""Small strict primitives shared by independently implemented token adapters."""
from copy import deepcopy
import re
import time
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


def parse_download_expiry(explicit_value=None, url='', *, now=None):
    """Parse explicit UTC expiry timestamp or signed query epoch without fabricating fixed TTLs (REV-08)."""
    from datetime import datetime, timezone
    import math
    from urllib.parse import parse_qsl
    cur = time.time() if now is None else float(now)

    def _valid_epoch(ts):
        if type(ts) not in (int, float) or type(ts) is bool or not math.isfinite(ts):
            return None
        val = float(ts)
        if 1_000_000_000_000 <= val <= 9_999_999_999_999:
            val /= 1000.0
        if cur + 20.0 < val <= cur + 7 * 86400:
            return val
        return None

    if explicit_value is not None:
        if type(explicit_value) in (int, float) and type(explicit_value) is not bool:
            hit = _valid_epoch(explicit_value)
            if hit is not None:
                return hit
        elif isinstance(explicit_value, str):
            s = explicit_value.strip()
            if re.fullmatch(r'[1-9][0-9]{9,12}', s):
                hit = _valid_epoch(int(s))
                if hit is not None:
                    return hit
            if s.endswith('Z') or '+' in s[10:] or '-' in s[10:]:
                iso = s[:-1] + '+00:00' if s.endswith('Z') else s
                try:
                    dt = datetime.fromisoformat(iso)
                    if dt.tzinfo is not None:
                        hit = _valid_epoch(dt.astimezone(timezone.utc).timestamp())
                        if hit is not None:
                            return hit
                except ValueError:
                    pass

    if isinstance(url, str) and '?' in url:
        try:
            q = dict(parse_qsl(urlsplit(url).query, max_num_fields=64))
        except ValueError:
            q = {}
        for key in ('Expires', 'expires', 'x-oss-expires', 'X-Amz-Expires-Epoch', 'e', 't'):
            raw_v = q.get(key)
            if isinstance(raw_v, str) and re.fullmatch(r'[1-9][0-9]{9,12}', raw_v):
                hit = _valid_epoch(int(raw_v))
                if hit is not None:
                    return hit
    return None


def scan_page_proof(session, parent, items, *, page, size, total=None, has_more=False):
    offset = (page - 1) * size
    ids = {item['file_id'] for item in items}
    if len(ids) != len(items):
        raise PanError('PAN_REPLY_INVALID')
    if total is not None:
        if offset > total:
            raise PanError('PAN_REPLY_INVALID')
        if not has_more and page == 1 and len(items) != total:
            raise PanError('PAN_INCOMPLETE_PAGE')
    operation = getattr(session, 'operation', None) if session is not None else None
    if operation is None or getattr(operation, 'kind', None) != 'scan' or parent is None:
        return
    operation._last_scan_page_meta = dict(
        parent=parent,
        page=page,
        size=size,
        declared_total=total,
        has_more=bool(has_more),
        count=len(items),
    )
    verifier = getattr(operation, 'frontier_verifier', None)
    if callable(verifier):
        verifier(parent, items, page=page, size=size, total=total, has_more=has_more, from_adapter=True)
        return
    # Adapter-only scan invocations without MediaIndex frontier keep only a single-directory
    # within-call check, never a cross-directory or cross-run authority.
    window = getattr(operation, '_single_dir_window', None)
    if page == 1:
        if window is not None and window[0] == parent:
            raise PanError('PAN_PAGE_EXPIRED')
        count = len(items)
    else:
        if window is None or window[0] != parent:
            raise PanError('PAN_PAGE_EXPIRED')
        _, prev_total, following, seen = window
        if total != prev_total or (total is not None and offset != following) or seen.intersection(ids):
            raise PanError('PAN_PAGE_EXPIRED')
        ids = seen | ids
        count = following + len(items)
    if len(ids) > 12000:
        raise PanError('PAN_BUDGET_EXHAUSTED')
    if total is not None and not has_more and (count != total or len(ids) != total):
        raise PanError('PAN_INCOMPLETE_PAGE')
    operation._single_dir_window = (parent, total, count, ids) if has_more else None


def listing(rows, total, page, size, convert, *, has_total=True, session=None, parent=None):
    if type(rows) is not list or len(rows) > size:
        raise PanError('PAN_REPLY_INVALID')
    number(total)
    offset = (page - 1) * size
    if has_total and offset > total:
        raise PanError('PAN_REPLY_INVALID')
    items = [convert(row) for row in rows]
    if len({r['file_id'] for r in items}) != len(items):
        raise PanError('PAN_REPLY_INVALID')
    more = page * size < total
    if more and not rows:
        raise PanError('PAN_REPLY_INVALID')
    if has_total and len(items) != min(size, total - offset):
        raise PanError('PAN_INCOMPLETE_PAGE')
    scan_page_proof(session, parent, items, page=page, size=size,
                    total=total if has_total else None, has_more=more)
    result = dict(items=items, page=page, has_more=more)
    if has_total and getattr(getattr(session, 'operation', None), 'kind', None) == 'scan':
        result['declared_total'] = total
    return result


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

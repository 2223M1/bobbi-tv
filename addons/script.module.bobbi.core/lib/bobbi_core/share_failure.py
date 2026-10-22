"""Closed share-failure value contracts; no owner, cache, or network work."""
import hashlib
import json
import math
import re

PERMANENT = frozenset(('share_revoked', 'identity_changed'))
TUPLE_FIELDS = ('locator', 'guid', 'title', 'size', 'media')
MAX_PROOFS = 128


def tuple_hash(selected):
    return hashlib.sha256(json.dumps([selected[key] for key in TUPLE_FIELDS],
        ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()


def failure_value(error):
    # Do not infer a typed failure from exception names, text, or server bodies.
    from bobbi_catalog.api import ShareError
    if not isinstance(error, ShareError):
        return None
    value = dict(code=error.code if error.code in ShareError.CODES else 'invalid_response',
        http_status=error.http_status if type(error.http_status) is int and 100 <= error.http_status <= 599 else None,
        api_code=error.api_code if type(error.api_code) is int and 0 <= error.api_code <= 9999999999 else None,
        invalidation_failed=getattr(error, 'invalidation_failed', False) is True)
    proof = getattr(error, 'checked_proof', None)
    if (type(proof) is dict and set(proof) == {'checked_at', 'checked_account'}
            and type(proof['checked_at']) in (int, float) and math.isfinite(proof['checked_at'])
            and proof['checked_at'] > 0 and type(proof['checked_account']) is str
            and re.fullmatch('[0-9a-f]{64}', proof['checked_account'])):
        value['checked_proof'] = dict(proof)
    return value


def failure_error(value):
    from bobbi_catalog.api import ShareError
    error = ShareError(value['code'], value['http_status'], value['api_code'])
    error.invalidation_failed = value['invalidation_failed']
    if 'checked_proof' in value:
        error.checked_proof = dict(value['checked_proof'])
    return error


def proofs(value):
    if type(value) is not list or not 1 <= len(value) <= MAX_PROOFS:
        raise ValueError('SHARE_PROOFS_INVALID')
    result = {}
    for item in value:
        if (type(item) is not dict or set(item) != {'tuple_sha256', 'checked_at'}
                or type(item['tuple_sha256']) is not str
                or not re.fullmatch('[0-9a-f]{64}', item['tuple_sha256'])
                or item['tuple_sha256'] in result
                or type(item['checked_at']) not in (int, float)
                or not math.isfinite(item['checked_at']) or item['checked_at'] <= 0):
            raise ValueError('SHARE_PROOFS_INVALID')
        result[item['tuple_sha256']] = item['checked_at']
    return result


def message(code):
    return {
        'login_required': '115 登录已失效，请重新授权自己的网盘账号。',
        'share_unavailable': '这个分享暂时无法访问，请选择其他来源或稍后重试。',
        'share_revoked': '这个分享已被取消，请选择其他来源。',
        'identity_changed': '分享文件已变化，请刷新片源后重新选择。',
        'refresh_required': '请刷新片源后重新选择 115 分享文件。',
        'network': '115 分享网络暂时不可用，请稍后重试或选择其他片源。',
        'network_timeout': '115 分享请求超时，请稍后重试或选择其他片源。',
        'deadline': '115 分享请求超时，请稍后重试或选择其他片源。',
    }.get(code, '115 分享暂时无法播放，请重试或选择其他片源。')


def presentation_receipt(player, window_context, request_id):
    """Fresh PRE_AV observation only; deliberately grants no control rights."""
    try:
        receipt = player._read_startup_failure()
        original = player._owner_context
        prior = player._startup_failure_receipt
        if (type(receipt) is not dict or type(original) is not dict or type(prior) is not dict
                or type(window_context) is not dict or receipt != prior
                or receipt.get('request_id') != request_id
                or any(receipt.get(key) != original.get(key) for key in ('boot_id', 'epoch', 'request_id'))
                or any(receipt.get(key) != window_context.get(key) for key in ('boot_id', 'epoch', 'request_id'))
                or (original.get('file_identity') and receipt.get('file_identity') != original['file_identity'])
                or (window_context.get('file_identity') and receipt.get('file_identity') != window_context['file_identity'])
                or not receipt.get('file_identity') or not receipt.get('native_instance')):
            return None
        return receipt
    except (AttributeError, OSError, RuntimeError, ValueError, TypeError):
        return None


def read_failure(source, item, receipt):
    """One closed host query tied to the selected card and frozen account."""
    from bobbi_platform.runtime import call
    from bobbi_catalog.identity import media_key
    from bobbi_catalog.api import ShareError
    try:
        if (type(receipt) is not dict or set(receipt) != {'boot_id', 'epoch', 'request_id',
                'file_identity', 'native_instance', 'url_sha256'} or not item.get('_account')):
            return None
        tv = item.get('tv_data') or {}
        selected = dict(locator=source.url, guid=source.guid, title=source.title, size=source.size,
            media=media_key((item.get('ids') or {}).get('tmdb_id'), item.get('mode'),
                            tv.get('season'), tv.get('episode')))
        result = call('share_failure', dict(account=item['_account'], owner=receipt, selected=selected), timeout=.3)
        if (type(result) is not dict or set(result) != {'matched', 'account', 'owner', 'tuple_sha256', 'failure'}
                or result['matched'] is not True or result['account'] != item['_account']
                or result['owner'] != receipt or result['tuple_sha256'] != tuple_hash(selected)):
            return None
        value = result['failure']
        if (type(value) is not dict or set(value) != {'code', 'http_status', 'api_code', 'invalidation_failed'}
                or type(value['code']) is not str or value['code'] not in ShareError.CODES
                or type(value['invalidation_failed']) is not bool
                or (value['http_status'] is not None and (type(value['http_status']) is not int or not 100 <= value['http_status'] <= 599))
                or (value['api_code'] is not None and (type(value['api_code']) is not int or not 0 <= value['api_code'] <= 9999999999))):
            return None
        return value
    except (AttributeError, ImportError, OSError, RuntimeError, ValueError, TypeError, KeyError):
        return None

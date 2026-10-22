"""Closed share-failure value contracts; no owner, cache, or network work."""
import hashlib
import json
import math
import re
import time
import sqlite3

PERMANENT = frozenset(('share_revoked', 'identity_changed'))
TUPLE_FIELDS = ('locator', 'guid', 'title', 'size', 'media')
MAX_PROOFS = 128


def account_scope(client=None, include_signed_out=False, timeout=.2):
    if client is not None:
        scope = getattr(client, 'account_scope', None)
    else:
        try:
            from bobbi_platform.runtime import call
            scope = call('account_status', {}, timeout=timeout)
        except (ImportError, OSError, ValueError, RuntimeError):
            return None
    if (type(scope) is dict
            and (scope.get('authenticated') is True and type(scope.get('account_id')) is str and scope['account_id']
                 or include_signed_out and scope.get('authenticated') is False and scope.get('account_id') == '')
            and type(scope.get('epoch')) is int and scope['epoch'] >= 0):
        return scope
    return None


def _scope_key(scope):
    return hashlib.sha256(json.dumps([scope['account_id'], scope['epoch']],
        separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def record_result(db, selected, scope, started, code=''):
    """One bounded overlay in the existing catalog DB, never a playback gate.

    Keep success ordering receipts too: an older in-flight failure may not
    overwrite a newer successful explicit retry. No account credentials/URLs.
    """
    if not scope or code and code not in PERMANENT:
        return
    db.execute('CREATE TABLE IF NOT EXISTS share_outcomes ('
        'account TEXT, tuple_key TEXT, started REAL, expires REAL, code TEXT, PRIMARY KEY(account,tuple_key))')
    with db:
        db.execute('DELETE FROM share_outcomes WHERE expires < ?', (time.time(),))
        db.execute('INSERT INTO share_outcomes VALUES(?,?,?,?,?) ON CONFLICT(account,tuple_key) DO UPDATE SET '
            'started=excluded.started, expires=excluded.expires, code=excluded.code '
            'WHERE excluded.started > share_outcomes.started',
            (_scope_key(scope), tuple_hash(selected), started, time.time()+21600, code))
        db.execute('DELETE FROM share_outcomes WHERE rowid IN '
            '(SELECT rowid FROM share_outcomes ORDER BY started DESC LIMIT -1 OFFSET 1024)')


def known_result(db, selected, scope):
    if not scope:
        return ''
    try:
        row = db.execute('SELECT code FROM share_outcomes WHERE account=? AND tuple_key=? AND expires>?',
            (_scope_key(scope), tuple_hash(selected), time.time())).fetchone()
        return row[0] if row and row[0] in PERMANENT else ''
    except sqlite3.OperationalError:
        return ''  # Legacy database or optional metadata busy, not a new failure.


def card_state(db, selected, scope):
    """Ordered display observation, not a playback grant or a stored account.

    An observed empty value can clear an older failure. Unavailable reads have
    no authority to clear anything; late observations cannot undo newer ones.
    """
    if not scope:
        return {}
    observed = time.perf_counter_ns()
    try:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='share_outcomes' AND type='table'").fetchone()
        row = db.execute('SELECT code FROM share_outcomes WHERE account=? AND tuple_key=? AND expires>?',
            (_scope_key(scope), tuple_hash(selected), time.time())).fetchone() if exists else None
    except sqlite3.Error:
        return {}
    return dict(account=_scope_key(scope), epoch=scope['epoch'], tuple=tuple_hash(selected),
                observed=observed, code=row[0] if row and row[0] in PERMANENT else '')


def valid_card_state(value):
    return (type(value) is dict and set(value) == {'account', 'epoch', 'tuple', 'observed', 'code'}
        and all(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]) for key in ('account', 'tuple'))
        and type(value['epoch']) is int and value['epoch'] >= 0
        and type(value['observed']) in (int, float) and math.isfinite(value['observed']) and value['observed'] > 0
        and type(value['code']) is str and value['code'] in PERMANENT | {''})


def resolution_state(selected, scope, code, observed):
    """Display-only receipt from the resolver's frozen account, never live IPC."""
    if (type(scope) is not dict or scope.get('authenticated') is not True
            or type(scope.get('account_id')) is not str or not scope['account_id']
            or type(scope.get('epoch')) is not int or scope['epoch'] < 0
            or code not in PERMANENT):
        return {}
    return dict(account=_scope_key(scope), epoch=scope['epoch'], tuple=tuple_hash(selected),
                observed=observed, code=code)


def card_tuple(card, media):
    return dict(locator=card['url'], guid=card['guid'], title=card['title'], size=card['size'], media=media)


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
    state = getattr(error, 'share_state', None)
    if valid_card_state(state) and state['code'] == value['code']:
        value['share_state'] = dict(state)
    return value


def failure_error(value):
    from bobbi_catalog.api import ShareError
    error = ShareError(value['code'], value['http_status'], value['api_code'])
    error.invalidation_failed = value['invalidation_failed']
    if 'checked_proof' in value:
        error.checked_proof = dict(value['checked_proof'])
    if valid_card_state(value.get('share_state')):
        error.share_state = dict(value['share_state'])
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
        if (type(value) is not dict or set(value) not in (
                {'code', 'http_status', 'api_code', 'invalidation_failed'},
                {'code', 'http_status', 'api_code', 'invalidation_failed', 'share_state'})
                or type(value['code']) is not str or value['code'] not in ShareError.CODES
                or type(value['invalidation_failed']) is not bool
                or (value['http_status'] is not None and (type(value['http_status']) is not int or not 100 <= value['http_status'] <= 599))
                or (value['api_code'] is not None and (type(value['api_code']) is not int or not 0 <= value['api_code'] <= 9999999999))):
            return None
        if 'share_state' in value:
            state = value['share_state']
            if (not valid_card_state(state) or state['tuple'] != tuple_hash(selected)
                    or state['account'] != _scope_key(item['_account'])
                    or state['epoch'] != item['_account']['epoch'] or state['code'] != value['code']):
                return None
        return value
    except (AttributeError, ImportError, OSError, RuntimeError, ValueError, TypeError, KeyError):
        return None

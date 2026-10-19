"""Read-only CodeBuddy credits and account-scoped model pricing metadata."""
import base64
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

from .codebuddy_regions import home_path, validate_region

ORIGINS = {'internal': 'https://copilot.tencent.com', 'external': 'https://www.codebuddy.ai'}
SUMMARY_PATH = '/billing/meter/get-user-resource-summary'
MAX_RESPONSE = 2 * 1024 * 1024
RATE = re.compile(r'\s*(?:[xX×]\s*)?(\d+(?:\.\d+)?)(?:\s*(?:credits?|倍))?\s*', re.I)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def decimal_text(value):
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def multiplier(value):
    if isinstance(value, str):
        match = RATE.fullmatch(value)
        if not match:
            return None
        value = match.group(1)
    value = number(value)
    return decimal_text(value) if value is not None else None


def model_prices(profile, region, account):
    """Use the CLI's last-good cloud config for this exact logged-in account.

    initialize deliberately projects models down to {id, name}. Its matching
    cloud config retains `credits` (e.g. x0.06 credits), scoped by userId.
    No authentication cache, agent prompt or other account's data is returned.
    """
    uid = account.get('userId')
    if not isinstance(uid, str) or not uid:
        return {}
    filename = 'entry_' + hashlib.md5(b'cloud_product_config_cache').hexdigest() + '.info'
    path = home_path(profile, region) / 'local_storage' / filename
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            return {}
        entries = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(entries, list):
            return {}
        for entry in reversed(entries):
            if not isinstance(entry, dict) or entry.get('userId') != uid:
                continue
            data = entry.get('data') or {}
            models = data.get('models', []) if isinstance(data, dict) else []
            return {item['id']: multiplier(item.get('credits')) for item in models
                    if isinstance(item, dict) and isinstance(item.get('id'), str)}
    except (OSError, ValueError, TypeError):
        pass
    return {}


def summary(value):
    """Match the official page: sum remaining credit capacities, not totals."""
    if not isinstance(value, dict) or value.get('code') not in (0, 200):
        raise ValueError('积分服务返回错误。')
    data = value.get('data')
    if not isinstance(data, dict):
        raise ValueError('积分服务返回格式无效。')
    remaining = number(data.get('TotalCredits'))
    if remaining is None:
        packages = data.get('Packages')
        if not isinstance(packages, list):
            raise ValueError('积分服务没有返回余额。')
        remaining = Decimal(0)
        for item in packages:
            if not isinstance(item, dict):
                raise ValueError('积分包格式无效。')
            if str(item.get('CapacityUnit', '')).lower() not in ('credit', 'credits'):
                continue
            amount = number(item.get('CycleRemainCapacity'))
            if amount is None:
                raise ValueError('积分包没有返回有效余额。')
            remaining += amount
    result = {'remaining': decimal_text(remaining), 'updated_at': int(time.time())}
    plan = data.get('SubscriptionPackageName')
    if isinstance(plan, str):
        result['plan'] = plan[:100]
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        # Account credentials must only reach the selected official origin.
        return None


def credits(account, region, proxy='', cancelled=lambda: False):
    region = validate_region(region)
    if cancelled():
        raise InterruptedError('已取消积分查询。')
    uid, token = account.get('userId'), account.get('token')
    if not isinstance(uid, str) or not uid or not isinstance(token, str) or not token:
        return None
    userinfo = {'uin': uid, 'token_source': region}
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
               'X-User-Id': uid, 'X-Auth-Method': region, 'X-Product': 'CodeBuddy',
               'X-Userinfo': base64.b64encode(json.dumps(userinfo).encode()).decode(),
               'User-Agent': 'CodeBuddy-VoiceAssistant'}
    enterprise = account.get('enterpriseId')
    if isinstance(enterprise, str) and enterprise:
        headers['X-Enterprise-Id'] = enterprise
        userinfo['owner_uin'] = enterprise
        headers['X-Userinfo'] = base64.b64encode(json.dumps(userinfo).encode()).decode()
    request = Request(ORIGINS[region] + SUMMARY_PATH, data=b'{}', headers=headers)
    opener = build_opener(ProxyHandler({'http': proxy, 'https': proxy} if proxy else {}), NoRedirect())
    try:
        with opener.open(request, timeout=12) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if cancelled():
            raise InterruptedError('已取消积分查询。')
        if len(raw) > MAX_RESPONSE:
            raise ValueError('积分服务返回内容过长。')
        return summary(json.loads(raw))
    except HTTPError as error:
        return {'error': '积分查询失败（HTTP {}），请稍后刷新。'.format(error.code)}
    except InterruptedError:
        raise
    except (URLError, OSError, ValueError):
        # Never expose response bodies/URLs/proxy credentials in web errors.
        return {'error': '积分暂时无法查询，请检查网络后刷新。'}

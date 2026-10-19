# -*- coding:utf-8 -*-
"""Bilibili WBI signing (img_key + sub_key → w_rid).

B 站 2023 起对部分 API（WBI 搜索、用户空间等）强制要求 wts + w_rid 签名，
签名算法见 https://socialsisteryi.github.io/bilibili-API-collect/docs/misc/sign/wbi.html
"""
import time
from functools import reduce
from hashlib import md5
from urllib.parse import urlencode

from core import plugin, xbmc

# 字符顺序打乱表，由 B 站前端逆向得到
mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

_WBI_ESCAPE = str.maketrans('', '', "!'()*")


def getMixinKey(orig: str) -> str:
    """对 imgKey 和 subKey 进行字符顺序打乱编码，得到 mixin_key"""
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]


def encWbi(params: dict, img_key: str, sub_key: str) -> dict:
    """为请求参数加 wts + w_rid 字段，返回新 dict（不修改原 dict）。

    img_key 或 sub_key 为 None 时直接返回原 params（不签名），让
    B 站返回 460/-352，由调用方决定如何提示重新登录。
    """
    if not img_key or not sub_key:
        return params
    mixin_key = getMixinKey(img_key + sub_key)
    signed = {**params, 'wts': round(time.time())}
    signed = dict(sorted(signed.items()))
    signed = {k: str(v).translate(_WBI_ESCAPE) for k, v in signed.items()}
    query = urlencode(signed)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()
    signed['w_rid'] = wbi_sign
    return signed


@plugin.cached(TTL=30)
def getWbiKeys():
    """获取最新的 img_key 和 sub_key，缓存 30 分钟。

    返回 (img_key, sub_key)；API 失败时返回 None，encWbi 会跳过签名
    让 B 站返回明确的 460/-352 错误，而不是用错误的 fallback key
    生成无效签名（调用方还要再做一次失败 round-trip）。
    """
    # 函数内 import 避免 api.wbi ↔ api.http 在 import 时循环
    from api.http import get_api_data
    try:
        data = get_api_data('/x/web-interface/nav')
        img_url = data['data']['wbi_img']['img_url']
        sub_url = data['data']['wbi_img']['sub_url']
        img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
        return img_key, sub_key
    except (KeyError, TypeError, IndexError):
        xbmc.log('[api.wbi] getWbiKeys failed (login required?)', xbmc.LOGWARNING)
        return None

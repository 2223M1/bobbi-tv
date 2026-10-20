# -*- coding:utf-8 -*-
"""认证 / 缓存清理路由：QR 登录、Cookie 登录、退出、缓存清理。"""
import os
import time

import requests

from core import plugin, xbmc, xbmcvfs, xbmcgui
from utils import (
    get_temp_path, remove_dir, notify, notify_error,
)
from api import get_cookie, clear_cookie_cache, get_api_data


@plugin.route('/remove_cache_files/')
def remove_cache_files():
    addon_id = 'plugin.video.bili'
    try:
        path = xbmc.translatePath(f'special://temp/{addon_id}').decode('utf-8')
    except (AttributeError, UnicodeDecodeError):
        path = xbmc.translatePath(f'special://temp/{addon_id}')

    remove_dir(path)
    if not os.path.isdir(path):
        xbmcgui.Dialog().ok('提示', '清除成功')
        return
    xbmcgui.Dialog().ok('提示', '清除失败')


@plugin.route('/check_login/')
def check_login():
    if not get_cookie():
        xbmcgui.Dialog().ok('提示', '账号未登录')
        return
    res = get_api_data('/x/web-interface/nav/stat', raw=True)
    if res['code'] == 0:
        xbmcgui.Dialog().ok('提示', '登录成功')
    elif res['code'] == -101:
        xbmcgui.Dialog().ok('提示', '账号未登录')
    else:
        xbmcgui.Dialog().ok('提示', res.get('message', '未知错误'))


@plugin.route('/load_cookie_file/')
def load_cookie_file():
    """从文件读 cookie 并保存到插件 storage。

    按顺序查找以下路径，第一个存在的用：
      1. special://profile/addon_data/plugin.video.bili/cookie.txt  （标准数据目录）
      2. special://home/addons/plugin.video.bili/cookie.txt          （addons 目录）
    """
    candidate_paths = [
        xbmc.translatePath('special://profile/addon_data/plugin.video.bili/cookie.txt'),
        xbmc.translatePath('special://home/addons/plugin.video.bili/cookie.txt'),
    ]
    file_path = None
    for p in candidate_paths:
        if xbmcvfs.exists(p):
            file_path = p
            break
    if not file_path:
        xbmcgui.Dialog().ok(
            'Cookie 文件未找到',
            '请把 cookie 字符串保存到以下任一文件:\n\n' +
            '\n'.join(candidate_paths),
        )
        return

    try:
        with xbmcvfs.File(file_path, 'r') as f:
            content = f.read()
        cookie = content.strip()
        if not cookie:
            xbmcgui.Dialog().ok('错误', 'cookie.txt 是空的')
            return
        account = plugin.get_storage('account')
        account['cookie'] = cookie
        clear_cookie_cache()
        plugin.clear_function_cache()
        xbmc.log(
            '[load_cookie_file] loaded from %s, cookie len=%d' % (file_path, len(cookie)),
            xbmc.LOGINFO,
        )
        xbmcgui.Dialog().ok(
            '成功',
            '已从文件加载 cookie\n来源: %s\n长度: %d 字节\n\n点任意视频测试' % (
                file_path, len(cookie),
            ),
        )
    except Exception as e:
        xbmc.log('[load_cookie_file] error: %s' % e, xbmc.LOGERROR)
        xbmcgui.Dialog().ok('错误', '读取失败: %s' % e)


@plugin.route('/logout/')
def logout():
    account = plugin.get_storage('account')
    account['cookie'] = ''
    clear_cookie_cache()
    plugin.clear_function_cache()
    xbmcgui.Dialog().ok('提示', '退出成功')


@plugin.route('/cookie_login/')
def cookie_login():
    keyboard = xbmc.Keyboard('', '请输入 Cookie')
    keyboard.doModal()
    if not keyboard.isConfirmed():
        return
    cookie = keyboard.getText().strip()
    if not cookie:
        return
    account = plugin.get_storage('account')
    account['cookie'] = cookie
    clear_cookie_cache()
    plugin.clear_function_cache()
    xbmcgui.Dialog().ok('提示', 'Cookie 设置成功')


@plugin.route('/qrcode_login/')
def qrcode_login():
    temp_path = get_temp_path()
    if not temp_path:
        notify('提示', '无法创建文件夹')
        return
    temp_path = os.path.join(temp_path, 'login.png')
    try:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/59.0.3071.115 Safari/537.36'
            ),
        }
        res = requests.get(
            'https://passport.bilibili.com/x/passport-login/web/qrcode/generate',
            headers=headers, timeout=10,
        ).json()
    except Exception:
        notify('提示', '二维码获取失败')
        return
    if res['code'] != 0:
        notify_error(res)
        return

    login_path = res['data']['url']
    key = res['data']['qrcode_key']
    try:
        import qrcode
    except Exception as e:
        xbmc.log('[plugin.video.bili] qrcode import failed: %s' % str(e), xbmc.LOGERROR)
        notify('提示', '缺少依赖：请安装 script.module.qrcode 插件')
        return
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=20,
    )
    qr.add_data(login_path)
    qr.make(fit=True)
    img = qr.make_image()
    img.save(temp_path)
    xbmc.executebuiltin('ShowPicture(%s)' % temp_path)
    _polling_login_status(key)


def _polling_login_status(key):
    session = requests.Session()
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/59.0.3071.115 Safari/537.36'
        ),
    }
    for _ in range(50):
        try:
            response = session.get(
                f'https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={key}',
                headers=headers, timeout=10,
            )
            check_result = response.json()
        except Exception:
            time.sleep(3)
            continue
        if check_result['code'] != 0:
            xbmc.executebuiltin('Action(Back)')
            return
        if check_result['data']['code'] == 0:
            account = plugin.get_storage('account')
            cookies = '; '.join(
                cookie.name + '=' + cookie.value for cookie in session.cookies
            )
            account['cookie'] = cookies
            clear_cookie_cache()
            plugin.clear_function_cache()
            xbmcgui.Dialog().ok('提示', '登录成功')
            xbmc.executebuiltin('Action(Back)')
            return
        if check_result['data']['code'] == 86038:
            notify('提示', '二维码已失效')
            xbmc.executebuiltin('Action(Back)')
            return
        time.sleep(3)
    xbmc.executebuiltin('Action(Back)')

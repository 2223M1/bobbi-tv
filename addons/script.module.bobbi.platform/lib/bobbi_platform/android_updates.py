"""APK delivery; Android remains the only install/signature/data transaction owner."""
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import tempfile
import time
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

from .online_transport import CancellableHTTPSHandler
from .updates import UpdateError, _json

FEEDS = ('https://gitee.com/M12223/bobbi-tv-updates/raw/master/repository/android.json',
         'https://raw.githubusercontent.com/2223M1/bobbi-tv/main/repository/android.json')
MAX_APK = 512 * 1024**2


class Cancelled(UpdateError):
    pass


def allowed_apk(url):
    if not isinstance(url, str):
        return False
    p = urlsplit(url)
    return p.scheme == 'https' and p.netloc == 'github.com' and not p.query and not p.fragment and bool(
        re.fullmatch(r'/2223M1/bobbi-tv/releases/download/android[0-9]+/BobbiTV-[0-9]+-android-(arm64-v8a|armeabi-v7a)\.apk', p.path))


def parse_feed(raw, abi, current):
    value = _json(raw)
    if (not isinstance(value, dict) or set(value) != {'schema', 'releases'} or
            type(value['schema']) is not int or value['schema'] != 1 or
            not isinstance(value['releases'], list) or len(value['releases']) > 20):
        raise UpdateError('ANDROID_FEED_INVALID')
    offers = []
    seen = set()
    for offer in value['releases']:
        if (not isinstance(offer, dict) or set(offer) != {'version_code', 'abi', 'url', 'size', 'sha256'} or
                type(offer['version_code']) is not int or not 1 <= offer['version_code'] <= 2100000000 or
                offer['abi'] not in ('arm64-v8a', 'armeabi-v7a') or not allowed_apk(offer['url']) or
                not offer['url'].endswith('-android-'+offer['abi']+'.apk') or
                type(offer['size']) is not int or not 20*1024**2 <= offer['size'] <= MAX_APK or
                not isinstance(offer['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', offer['sha256'])):
            raise UpdateError('ANDROID_FEED_INVALID')
        identity = offer['abi'], offer['version_code']
        if identity in seen:
            raise UpdateError('ANDROID_FEED_DUPLICATE')
        seen.add(identity)
        if offer['abi'] == abi and offer['version_code'] > current:
            offers.append(offer)
    return max(offers, key=lambda item: item['version_code']) if offers else None


def transfer(url, maximum, consume, cancelled, progress=lambda _: None, expected=None):
    deadline = time.monotonic() + 600
    def active():
        if cancelled():
            raise Cancelled('ANDROID_UPDATE_CANCELLED')
        if time.monotonic() >= deadline:
            raise UpdateError('ANDROID_UPDATE_TIMEOUT')
    class Redirects(HTTPRedirectHandler):
        count = 0
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            self.count += 1
            p = urlsplit(newurl)
            good = (p.scheme == 'https' and not p.fragment and not p.username and not p.password and
                ((p.netloc in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com') and allowed_apk(url)) or
                 (p.netloc == 'raw.giteeusercontent.com' and url == FEEDS[0] and
                  p.path == '/M12223/bobbi-tv-updates/raw/master/repository/android.json')))
            if fp is not None:
                fp.close()
            if self.count > 3 or not good:
                raise UpdateError('ANDROID_UPDATE_REDIRECT')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    if url not in FEEDS and not allowed_apk(url):
        raise UpdateError('ANDROID_UPDATE_URL')
    opener = build_opener(ProxyHandler({}), CancellableHTTPSHandler(active, ssl.create_default_context()), Redirects())
    active()
    try:
        response = opener.open(Request(url, headers={'User-Agent': 'BobbiTV-Android', 'Accept-Encoding': 'identity'}), timeout=5)
    except HTTPError as error:
        error.close()
        raise UpdateError('ANDROID_UPDATE_HTTP') from None
    with response:
        if response.status != 200 or response.headers.get('Content-Encoding', 'identity') != 'identity':
            raise UpdateError('ANDROID_UPDATE_RESPONSE')
        length = response.headers.get('Content-Length')
        if length is not None:
            if not length.isdigit() or int(length) > maximum or (expected is not None and int(length) != expected):
                raise UpdateError('ANDROID_UPDATE_LENGTH')
            length = int(length)
        total = 0
        while True:
            active()
            block = response.read1(min(128*1024, maximum-total+1))
            active()
            if not block:
                break
            total += len(block)
            if total > maximum:
                raise UpdateError('ANDROID_UPDATE_LIMIT')
            consume(block)
            progress(int(total*100/(expected or length)) if (expected or length) else 0)
        if (length is not None and total != length) or (expected is not None and total != expected):
            raise UpdateError('ANDROID_UPDATE_SHORT_READ')


def latest(abi, current, cancelled=lambda: False):
    if abi not in ('arm64-v8a', 'armeabi-v7a') or type(current) is not int:
        raise UpdateError('ANDROID_HOST_INFO')
    offers, valid, last_error = [], False, None
    for url in FEEDS:
        blocks = []
        try:
            transfer(url, 32768, blocks.append, cancelled)
            offer = parse_feed(b''.join(blocks), abi, current)
            valid = True
            if offer:
                offers.append(offer)
        except Cancelled:
            raise
        except (OSError, ValueError, UpdateError) as error:
            last_error = error
    if not valid:
        raise last_error or UpdateError('ANDROID_UPDATE_UNAVAILABLE')
    return max(offers, key=lambda row: row['version_code']) if offers else None


def stage(directory, writer):
    """Only a complete APK replaces the install candidate; never touch app data."""
    directory = Path(directory)
    if not directory.is_absolute() or directory.name != 'bobbi-update' or directory.is_symlink():
        raise UpdateError('ANDROID_UPDATE_DIRECTORY')
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='apk-', suffix='.partial', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        target = directory/'update.apk'
        if target.is_symlink():
            raise UpdateError('ANDROID_UPDATE_PATH')
        os.replace(name, target)
        return target
    finally:
        if os.path.exists(name):
            os.unlink(name)


def download(offer, directory, cancelled=lambda: False, progress=lambda _: None):
    parse_feed(json.dumps({'schema': 1, 'releases': [offer]}), offer['abi'], 0)
    def write(stream):
        digest = hashlib.sha256()
        def consume(block):
            digest.update(block)
            stream.write(block)
        transfer(offer['url'], MAX_APK, consume, cancelled, progress, offer['size'])
        if digest.hexdigest() != offer['sha256']:
            raise UpdateError('ANDROID_UPDATE_INCOMPLETE')
    return stage(directory, write)


def install_from_ui(dialog, online=False):
    import xbmc
    import xbmcgui
    import xbmcvfs
    from .android_engine import request
    progress = xbmcgui.DialogProgress()
    try:
        if xbmc.Player().isPlaying():
            dialog.ok('请先停止播放', '停止影片后再更新程序。')
            return False
        info = request('info')
        if info['state'] != 'READY':
            raise UpdateError('ANDROID_HOST_UNAVAILABLE')
        progress.create('更新波比 TV', '正在检查安装包')
        cancelled = lambda: progress.iscanceled() or xbmc.Monitor().abortRequested()
        if online:
            offer = latest(info['abi'], info['version_code'], cancelled)
            if offer is None:
                progress.close()
                dialog.ok('暂无更新', '当前渠道没有更新的 Android 安装包。')
                return False
            target = download(offer, info['update_directory'], cancelled, progress.update)
        else:
            progress.close()
            chosen = dialog.browseSingle(1, '选择 Android APK', 'files', '.apk')
            if not chosen:
                return False
            progress.create('准备更新', '正在复制安装包')
            def copy(stream):
                source = xbmcvfs.File(chosen)
                total = 0
                try:
                    while True:
                        if cancelled():
                            raise Cancelled('ANDROID_UPDATE_CANCELLED')
                        block = bytes(source.readBytes(128*1024))
                        if not block:
                            break
                        total += len(block)
                        if total > MAX_APK:
                            raise UpdateError('ANDROID_UPDATE_LIMIT')
                        stream.write(block)
                    if total < 20*1024**2:
                        raise UpdateError('ANDROID_UPDATE_INCOMPLETE')
                finally:
                    source.close()
            target = stage(info['update_directory'], copy)
        progress.close()
        if cancelled() or xbmc.Player().isPlaying():
            return False
        state = request('install', str(target))['state']
        if state == 'PERMISSION_REQUIRED':
            dialog.ok('允许安装更新', '请在系统页面允许波比 TV 安装应用，然后返回重试。')
        elif state == 'REQUESTED':
            dialog.ok('请确认安装', '接下来由 Android 完成更新。账号和观看记录会保留。')
            return True
        else:
            dialog.ok('安装未开始', '请使用同一签名、版本更新的 Android APK；不要卸载或清除数据。')
    except Cancelled:
        pass
    except (OSError, ValueError, RuntimeError):
        dialog.ok('更新未完成', '可以稍后重试，或下载 Android APK 后选择本地安装。原版本和数据未改动。')
    finally:
        progress.close()
    return False

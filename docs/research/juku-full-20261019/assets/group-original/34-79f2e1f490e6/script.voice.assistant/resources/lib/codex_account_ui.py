"""TV QR/device-code login; network work stays outside Kodi's UI thread."""
from .data_paths import data_path
import os
from pathlib import Path
import queue
import secrets
import struct
import threading
import time
import zlib

import xbmc
import xbmcgui
import xbmcvfs

from .intelligence.errors import AgentError
from .codex_account import CodexAccount, login_error
from .qrcodegen import QrCode
from .settings import get_proxy

BACK = (9, 10, 92, 216, 247, 257)


def qr_png(url, destination):
    qr = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
    width = 420
    scale = min(10, width // (qr.get_size() + 8))
    inset = (width - qr.get_size() * scale) // 2
    pixels = bytearray()
    for y in range(width):
        pixels.append(0)
        for x in range(width):
            pixels.append(0 if qr.get_module((x - inset) // scale, (y - inset) // scale) else 255)

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', width, width, 8, 0, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(pixels), 9)) + chunk(b'IEND', b'')
    with Path(destination).open('wb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(png)




class LoginWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.stopped = kwargs.pop('stopped')
        self.ready = threading.Event()
        super().__init__(*args, **kwargs)

    def onInit(self):
        self.setFocusId(400)
        self.ready.set()

    def onAction(self, action):
        if action.getId() in BACK:
            self.stopped.set()
            self.close()

    def onClick(self, identifier):
        if identifier == 400:
            self.stopped.set()
            self.close()


def login(addon, profile, account_factory=CodexAccount):
    root = Path(xbmcvfs.translatePath(addon.getAddonInfo('path')))
    profile = Path(profile)
    qr_path = data_path(profile, 'codex-login-' + secrets.token_hex(12) + '.png')
    stop, done = threading.Event(), threading.Event()
    monitor, updates = xbmc.Monitor(), queue.Queue()
    shared = {}
    window = LoginWindow('CodexLogin.xml', str(root), 'Default', '1080i', stopped=stop)
    worker = None
    try:
        def cancelled():
            return stop.is_set() or monitor.abortRequested()

        def show_code(challenge):
            qr_png(challenge['url'], qr_path)
            updates.put(challenge)

        def work():
            try:
                with account_factory(root, profile, cancelled,
                                     proxy=get_proxy(addon)) as account:
                    shared['account'] = account.login(show_code)
            except InterruptedError:
                shared['cancelled'] = True
            except Exception as error:
                shared['error'] = login_error(error)
            finally:
                done.set()

        window.show()
        worker = threading.Thread(target=work, name='codex-device-login')
        worker.start()
        deadline = None
        while not done.is_set() and not cancelled():
            if window.ready.is_set():
                try:
                    challenge = updates.get_nowait()
                except queue.Empty:
                    pass
                else:
                    window.getControl(301).setImage(str(qr_path))
                    window.getControl(302).setText('用手机相机或浏览器扫码。\n在 OpenAI 官方页面登录 Codex，\n然后输入下方设备验证码。')
                    window.getControl(303).setLabel(challenge['code'])
                    deadline = time.monotonic() + 600
                if deadline:
                    seconds = max(0, int(deadline - time.monotonic()))
                    window.getControl(304).setLabel('等待手机授权 · 本窗口剩余 {}:{:02d}'.format(seconds // 60, seconds % 60))
            monitor.waitForAbort(.1)
        was_cancelled = cancelled() or shared.get('cancelled')
        stop.set()
        worker.join()
        window.close()
        if was_cancelled:
            return {'state': 'cancelled'}
        if shared.get('error'):
            xbmcgui.Dialog().ok('Codex 登录未完成', shared['error'])
            return {'state': 'error', 'error': shared['error']}
        account = shared['account']
        text = 'Codex 已登录' + ('（{}）'.format(account['plan'].upper()) if account['plan'] else '')
        if account['email']:
            text += '\n' + account['email']
        text += '\n可在“智能体”选择订阅登录方式和模型。'
        xbmcgui.Dialog().ok('登录成功', text)
        return {'state': 'done', 'logged_in': True, 'plan': account['plan']}
    finally:
        stop.set()
        if worker is not None and worker.is_alive():
            worker.join()
        window.close()
        qr_path.unlink(missing_ok=True)


def account_action(addon, profile, logout=False, account_factory=CodexAccount):
    root = Path(xbmcvfs.translatePath(addon.getAddonInfo('path')))
    stop, done, monitor = threading.Event(), threading.Event(), xbmc.Monitor()
    shared = {}
    progress = xbmcgui.DialogProgress()

    def work():
        try:
            with account_factory(root, profile, lambda: stop.is_set() or monitor.abortRequested(),
                                 proxy=get_proxy(addon)) as account:
                shared['account'] = account.logout() if logout else account.status()
        except InterruptedError:
            shared['cancelled'] = True
        except Exception as error:
            shared['error'] = login_error(error)
        finally:
            done.set()

    progress.create('Codex 订阅', '正在退出登录…' if logout else '正在读取账号…')
    worker = threading.Thread(target=work, name='codex-account-status')
    worker.start()
    try:
        while not done.is_set():
            if monitor.abortRequested() or progress.iscanceled():
                stop.set()
                break
            monitor.waitForAbort(.1)
        worker.join()
        progress.close()
        if stop.is_set() or shared.get('cancelled') or monitor.abortRequested():
            return
        if shared.get('error'):
            xbmcgui.Dialog().ok('Codex 账号', shared['error'])
        else:
            account = shared['account']
            text = '已退出 Codex 登录。' if logout else ('Codex 已登录' if account['logged_in'] else 'Codex 未登录。')
            if account['logged_in']:
                text += '\n' + account['email'] + '\n订阅：' + (account['plan'].upper() or '未知')
            xbmcgui.Dialog().ok('Codex 账号', text)
    finally:
        stop.set()
        if worker.is_alive():
            worker.join()
        progress.close()

"""QR rendered locally; no login material sent to third-party QR services."""
import tempfile
from pathlib import Path
from .cloud115 import Login, CloudError
from .environment import private_path
from .account_manager import validate_snapshot
from .runtime import call


def _refresh_account_view():
    # The account route refreshes the current directory after committing a
    # login/logout. This is not a skin reload or a playback stop/restart.
    import xbmc
    try:
        xbmc.executebuiltin('Container.Refresh')
    except RuntimeError:
        pass  # A UI refresh failure must not misreport a committed login.


def login():
    import xbmc
    import xbmcgui
    import xbmcvfs
    from ._vendor import segno
    dialog = xbmcgui.Dialog()
    path = private_path(xbmcvfs.translatePath, '115-os_linux.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        expected = validate_snapshot(call('account_status', {}))
    except (ValueError, OSError, RuntimeError):
        dialog.ok('115 账号服务尚未就绪', '请等待影院后台启动后重试。没有修改已有登录。')
        return False
    if expected['authenticated']:
        choice = dialog.select('115 账号 · 已登录', ['扫码切换 / 重新登录（取消保留当前账号）', '退出登录'])
        if choice < 0:
            return False
        if choice == 1:
            if not dialog.yesno('退出 115', '撤销此账号的播放连接与待处理任务。不会删除或转存网盘文件。继续吗？'):
                return False
            try:
                call('account_logout', {'expected': expected})
            except (ValueError, OSError, RuntimeError):
                dialog.ok('账号状态已变化', '请重新打开账号管理确认当前状态。本次不重试退出操作。')
                return False
            _refresh_account_view()
            dialog.ok('已退出本机 115', '本机登录与旧播放连接已撤销，网盘文件未修改。')
            return True

    from .account_dialog import create
    flow, window = Login(), None
    monitor = xbmc.Monitor()
    with tempfile.TemporaryDirectory(prefix='bobbi-qr-', dir=str(path.parent)) as directory:
        image = Path(directory) / 'login.png'
        try:
            qr = flow.begin()
            segno.make(qr, micro=False).save(str(image), scale=10, border=4)
            window = create(image)
            window.show()
            failures = 0
            while not monitor.abortRequested() and not window.cancelled:
                if monitor.waitForAbort(2):
                    break
                try:
                    state, value = flow.poll()
                    failures = 0
                except CloudError as error:
                    if error.code in ('NETWORK_ERROR', 'QR_POLL_RETRY') and failures < 3:
                        failures += 1
                        window.set_status('连接暂时中断，正在重试；可取消')
                        continue
                    raise
                if state == 'confirmed':
                    if not window.cancelled and not monitor.abortRequested():
                        call('account_install', {'credentials': value, 'expected': expected})
                        window.close()
                        _refresh_account_view()
                        dialog.ok('115 登录已保存', '账号仅保存在这台设备，未转存或删除网盘文件。')
                        return True
                    break
                if state == 'scanned':
                    window.set_status('已扫描，请在手机上确认登录')
        except (CloudError, OSError, ValueError, RuntimeError):
            if window is not None:
                window.close()
            # An IPC timeout can follow a successful atomic save. Never claim
            # unchanged state or repeat the account exchange in that case.
            dialog.ok('本次登录未确认', '二维码可能已过期、账号已切换或后台暂时不可用。请重新打开账号管理确认；本次不重复提交。')
        finally:
            flow.cancel()
            if window is not None:
                window.close()
    return False

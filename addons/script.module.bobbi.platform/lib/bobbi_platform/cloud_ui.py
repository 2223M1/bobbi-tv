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
        dialog.ok('115 暂时无法登录', '请稍等片刻再试，已有账号保留。')
        return False
    if expected['authenticated']:
        choice = dialog.select('115 账号', ['扫码切换或重新登录', '退出登录'])
        if choice < 0:
            return False
        if choice == 1:
            if not dialog.yesno('退出 115？', '将停止此账号的播放和待处理任务，网盘文件保留。'):
                return False
            try:
                call('account_logout', {'expected': expected})
            except (ValueError, OSError, RuntimeError):
                dialog.ok('未确认退出结果', '请重新打开账号管理查看当前状态。')
                return False
            _refresh_account_view()
            dialog.ok('已退出 115', '本机登录已移除，网盘文件保留。')
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
                        window.set_status('连接中断，正在重试。可按返回取消。')
                        continue
                    raise
                if state == 'confirmed':
                    if not window.cancelled and not monitor.abortRequested():
                        call('account_install', {'credentials': value, 'expected': expected})
                        window.close()
                        _refresh_account_view()
                        dialog.ok('115 登录成功', '已保存到这台设备，可以返回选片。')
                        return True
                    break
                if state == 'scanned':
                    window.set_status('已扫码，请在手机上确认登录')
        except (CloudError, OSError, ValueError, RuntimeError) as error:
            if window is not None:
                window.close()
            # An IPC timeout can follow a successful atomic save. Never claim
            # unchanged state or repeat the account exchange in that case.
            if isinstance(error, CloudError) and error.code in ('QR_EXPIRED', 'QR_CANCELLED'):
                dialog.ok('二维码已过期' if error.code == 'QR_EXPIRED' else '已取消登录',
                          '请重新扫码，当前账号保留。')
            else:
                dialog.ok('未确认登录结果', '请重新打开账号管理查看状态。若仍未登录，请重新扫码。')
        finally:
            flow.cancel()
            if window is not None:
                window.close()
    return False

"""QR rendered locally; no login material sent to third-party QR services."""
import tempfile
from pathlib import Path
from threading import Event, Lock
from .cloud115 import Login, CloudError
from .environment import private_path
from .account_manager import validate_snapshot
from .runtime import call


class _LoginAdapter:
    """115 protocol stays separate; only the account owner can persist it."""
    def __init__(self, flow, expected):
        self.flow, self.expected = flow, expected
        self.cancelled, self.lock, self._saved = Event(), Lock(), None

    @property
    def phase(self):
        return getattr(self.flow, 'phase', 'confirm')

    def begin(self):
        qr = self.flow.begin()
        if self.cancelled.is_set():
            self.flow.cancel()  # A late begin must not revive an abandoned token.
            return dict(state='cancelled')
        return dict(state='waiting', qr=qr)

    def poll(self):
        state, value = self.flow.poll()
        with self.lock:
            if self.cancelled.is_set():
                return dict(state='cancelled')
            if state == 'confirmed':
                self._saved = value
                return dict(state='ready')  # Credentials never enter the runner/UI result.
        if state not in ('waiting', 'scanned'):
            raise CloudError('INVALID_REPLY')
        return dict(state=state)

    def retryable(self, error):
        # The protocol claims its one-use exchange before sending it. A lost
        # exchange reply must not be replaced by another poll or exchange.
        return not getattr(self.flow, 'terminal', False)

    def commit(self):
        with self.lock:
            if self.cancelled.is_set() or self._saved is None:
                raise CloudError('QR_FINISHED')
            value = self._saved
        reply = call('account_install', dict(credentials=value, expected=self.expected))
        validate_snapshot(reply, authenticated=True)
        return dict(state='committed')

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            self._saved = None
        self.flow.cancel()


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
    dialog = xbmcgui.Dialog()
    path = private_path(xbmcvfs.translatePath, '115-os_linux.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        expected = validate_snapshot(call('account_status', {}))
    except (ValueError, OSError, RuntimeError):
        dialog.ok('115 暂时无法登录', '请稍等片刻再试，已有账号保留。')
        return False
    if expected['authenticated']:
        choice = dialog.select('115 分享播放', ['扫码切换或重新登录', '退出登录'])
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

    from .account_dialog import create, render_qr, failure_details, safe_close
    from .login_flow import LoginRunner, LoginFlowError
    adapter, window, runner = _LoginAdapter(Login(), expected), None, None
    monitor = xbmc.Monitor()
    with tempfile.TemporaryDirectory(prefix='bobbi-qr-', dir=str(path.parent)) as directory:
        image = Path(directory) / 'login.png'
        try:
            window = create('')
            window.message = '正在准备二维码，可按返回取消。'
            window.show()
            runner = LoginRunner(window, monitor)
            if runner.run(adapter, lambda state: render_qr(window, image, state)):
                safe_close(window)
                _refresh_account_view()
                dialog.ok('115 登录成功', '已保存到这台设备，可以返回选片。')
                return True
        except Exception as error:
            safe_close(window)
            # An IPC timeout can follow a successful atomic save. Never claim
            # unchanged state or repeat the account exchange in that case.
            code = error.code if isinstance(error, (CloudError, LoginFlowError)) else ''
            if code in ('QR_EXPIRED', 'QR_CANCELLED', 'EXPIRED'):
                dialog.ok('已取消登录' if code == 'QR_CANCELLED' else '二维码已过期',
                          '请重新扫码，当前账号保留。')
            else:
                detail = failure_details(runner, error, '115') if runner is not None else '登录界面暂不可用。'
                dialog.ok('未确认登录结果', detail + '\n请重新打开账号管理查看状态。')
        finally:
            adapter.cancel()
            safe_close(window)
    return False

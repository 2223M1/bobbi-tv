"""QR rendered locally; no login material sent to third-party QR services."""
import tempfile
from pathlib import Path
from .cloud115 import Login, CloudError, save, load
from .environment import private_path


def login():
    import xbmc
    import xbmcgui
    import xbmcvfs
    from ._vendor import segno
    dialog = xbmcgui.Dialog()
    path = private_path(xbmcvfs.translatePath, '115-os_linux.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = load(path)
    except CloudError:
        previous = path.exists()  # Allow explicit repair without deleting old state first.
    if previous and not dialog.yesno('115 已保存登录', '重新扫码会替换本机 115 登录。取消或失败仍保留原账号。继续吗？'):
        return False

    class QRWindow(xbmcgui.WindowDialog):
        cancelled = False

        def onAction(self, action):
            if action.getId() in (9, 10, 13, 92, 216):
                self.cancelled = True
                self.close()

    flow, window = Login(), QRWindow()
    monitor = xbmc.Monitor()
    with tempfile.TemporaryDirectory(prefix='bobbi-qr-', dir=str(path.parent)) as directory:
        image = Path(directory) / 'login.png'
        try:
            qr = flow.begin()
            segno.make(qr, micro=False).save(str(image), scale=10, border=4)
            # Controls use the established cinema palette and active skin fonts.
            window.setCoordinateResolution(5)
            background = xbmcgui.ControlImage(0, 0, 1280, 720, 'white.png', colorDiffuse='FA0A0B0E')
            cinema = xbmc.getSkinDir() == 'skin.bobbi.cinema'
            title = xbmcgui.ControlLabel(100, 36, 1080, 60, '用 115 生活 App 扫码登录', font='Display44' if cinema else 'font24', textColor='FFF5F3EF', alignment=2)
            picture = xbmcgui.ControlImage(430, 120, 420, 420, str(image))
            status = xbmcgui.ControlLabel(100, 570, 1080, 60, '请扫描二维码并在手机确认；按返回取消', font='Label30' if cinema else 'font20', textColor='FFB4B2AD', alignment=2)
            window.addControls([background, title, picture, status])
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
                        status.setLabel('连接暂时中断，正在重试；按返回取消')
                        continue
                    raise
                if state == 'confirmed':
                    if not window.cancelled and not monitor.abortRequested():
                        save(path, value)
                        window.close()
                        dialog.ok('115 登录已保存', '账号仅保存在这台设备，未转存或删除网盘文件。')
                        return True
                    break
                if state == 'scanned':
                    status.setLabel('已扫描，请在手机上确认登录')
        except (CloudError, OSError, ValueError):
            window.close()
            dialog.ok('本次登录未完成', '二维码可能已过期或网络暂时不可用，请重新扫码。原有登录未更改。')
        finally:
            flow.cancel()
            window.close()
    return False

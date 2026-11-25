"""Shared login presentation; protocols and account authority stay separate."""
from contextlib import contextmanager


def _tr(msg_id, zh_text, en_text):
    from .i18n import tr
    return tr(msg_id, zh_text, en_text)


def safe_close(window):
    """A dismissed Kodi control must not change an acknowledged login outcome."""
    if window is not None:
        try:
            window.close()
        except RuntimeError:
            pass  # Kodi may already have disposed this window's controls.


@contextmanager
def login_dialog(root, prefix, title=None, instruction=None, monitor=None):
    """Single QR window and temporary image lifecycle; protocols and commits stay with callers."""
    from pathlib import Path
    import tempfile
    import xbmc
    from .login_flow import LoginRunner
    if title is None:
        title = _tr(32000, '登录 115 分享播放', 'Sign in to 115 Share Playback')
    if instruction is None:
        instruction = _tr(32001, '用「115 生活」App 扫码', 'Scan with the 115 Life app')
    Path(root).mkdir(parents=True, exist_ok=True)
    monitor = monitor or xbmc.Monitor()
    with tempfile.TemporaryDirectory(prefix=prefix, dir=str(root)) as directory:
        image = Path(directory) / 'login.png'
        window = None
        try:
            window = create('', title, instruction)
            window.message = _tr(32002, '正在准备二维码，可按返回取消。', 'Preparing QR code; press Back to cancel.')
            window.show()
            runner = LoginRunner(window, monitor)
            yield window, runner, image
        finally:
            safe_close(window)


def render_qr(window, image, state):
    """Only the UI thread writes the temporary image and touches Kodi controls."""
    import base64
    from .pan_accounts import PanError
    from .qr import write_png
    if type(state.get('qr')) is str:
        write_png(state['qr'], image, scale=10, border=4, micro=False)
    elif type(state.get('qr_png')) is str and len(state['qr_png']) <= 10924:
        raw = base64.b64decode(state['qr_png'], validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) > 8192:
            raise PanError('PAN_QR_IMAGE_INVALID')
        image.write_bytes(raw)
    else:
        raise PanError('PAN_QR_UNAVAILABLE')
    window.set_image(image)


def failure_details(runner, error, provider):
    """Fixed local categories only; never log exception text or credentials."""
    from .pan_accounts import NAMES
    value = runner.diagnostic(error)
    provider = provider if provider in NAMES else 'unknown'
    phase_map = {
        'prepare': (32005, '准备二维码', 'Preparing QR code'),
        'confirm': (32006, '等待手机确认', 'Waiting for phone confirmation'),
        'exchange': (32007, '获取登录信息', 'Fetching sign-in token'),
        'identity': (32008, '核验登录信息', 'Verifying account identity'),
        'commit': (32009, '保存登录', 'Saving sign-in'),
        'complete': (32010, '完成', 'Completed'),
        'cancelled': (32011, '取消', 'Cancelled'),
    }
    phase = _tr(*phase_map.get(value['phase'], (32012, '登录', 'Sign-in')))
    receipt = (
        _tr(32013, '已收到保存回执', 'Save receipt confirmed')
        if value['commit_acknowledged']
        else _tr(32014, '保存回执待确认', 'Save receipt pending')
        if value['commit_sent']
        else _tr(32015, '尚未提交保存', 'Not submitted for save yet')
    )
    try:
        import xbmc
        xbmc.log('[Bobbi login] provider=%s phase=%s code=%s commit_sent=%s commit_ack=%s' %
            (provider, value['phase'], value['code'], value['commit_sent'], value['commit_acknowledged']),
            xbmc.LOGWARNING)
    except (ImportError, AttributeError, RuntimeError):
        pass
    return _tr(32016, '%s（%s）；%s。', '%s (%s); %s.') % (phase, value['code'], receipt)


def create(image, title=None, instruction=None):
    import xbmc
    import xbmcaddon
    import xbmcgui
    resolved_title = _tr(32000, '登录 115 分享播放', 'Sign in to 115 Share Playback') if title is None else title
    resolved_instruction = _tr(32001, '用「115 生活」App 扫码', 'Scan with the 115 Life app') if instruction is None else instruction

    class AccountQR(xbmcgui.WindowXMLDialog):
        def onInit(self):
            cinema = xbmc.getSkinDir() == 'skin.bobbi.cinema'
            self.getControl(100).setLabel(resolved_title, font='Head40' if cinema else 'font24')
            self.getControl(102).setLabel(resolved_instruction, font='Head34' if cinema else 'font24')
            # Kodi may deliver onInit after the asynchronous QR request has
            # already published its image. Never restore the initial blank.
            self.getControl(101).setImage(self.image)
            self.getControl(103).setLabel(self.message, font='Body26' if cinema else 'font20')
            self.getControl(9001).setLabel(_tr(32003, '取消', 'Cancel'), font='Button28' if cinema else 'font20')
            self.setFocusId(9001)

        def set_status(self, value):
            self.message = value
            try:
                self.getControl(103).setLabel(value)
            except RuntimeError:
                pass  # onInit applies the saved state when controls exist.

        def set_image(self, value):
            self.image = str(value)
            try:
                self.getControl(101).setImage(self.image)
            except RuntimeError:
                pass

        def onClick(self, control_id):
            if control_id == 9001:
                self.cancelled = True
                self.close()

        def onAction(self, action):
            if action.getId() in (9, 10, 13, 92, 216):
                self.cancelled = True
                self.close()

    window = AccountQR('account-login.xml',
        xbmcaddon.Addon('script.module.bobbi.platform').getAddonInfo('path'), 'Default', '1080i')
    window.cancelled = False
    window.image = str(image)
    window.message = _tr(32004, '扫码后在手机确认。取消会保留当前账号。', 'Confirm on your phone after scanning. Cancelling keeps the current account.')
    return window

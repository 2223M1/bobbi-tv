"""Shared login presentation; protocols and account authority stay separate."""


def safe_close(window):
    """A dismissed Kodi control must not change an acknowledged login outcome."""
    if window is not None:
        try:
            window.close()
        except RuntimeError:
            pass  # Kodi may already have disposed this window's controls.


def render_qr(window, image, state):
    """Only the UI thread writes the temporary image and touches Kodi controls."""
    import base64
    from ._vendor import segno
    from .pan_accounts import PanError
    if type(state.get('qr')) is str:
        segno.make(state['qr'], micro=False).save(str(image), scale=10, border=4)
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
    phase = {'prepare': '准备二维码', 'confirm': '等待手机确认', 'exchange': '获取登录信息',
             'identity': '核验登录信息', 'commit': '保存登录', 'complete': '完成',
             'cancelled': '取消'}.get(value['phase'], '登录')
    receipt = ('已收到保存回执' if value['commit_acknowledged'] else
               '保存回执待确认' if value['commit_sent'] else '尚未提交保存')
    try:
        import xbmc
        xbmc.log('[Bobbi login] provider=%s phase=%s code=%s commit_sent=%s commit_ack=%s' %
            (provider, value['phase'], value['code'], value['commit_sent'], value['commit_acknowledged']),
            xbmc.LOGWARNING)
    except (ImportError, AttributeError, RuntimeError):
        pass
    return '%s（%s）；%s。' % (phase, value['code'], receipt)


def create(image, title='登录 115 分享播放', instruction='用「115 生活」App 扫码'):
    import xbmc
    import xbmcaddon
    import xbmcgui

    class AccountQR(xbmcgui.WindowXMLDialog):
        def onInit(self):
            cinema = xbmc.getSkinDir() == 'skin.bobbi.cinema'
            self.getControl(100).setLabel(title, font='Head40' if cinema else 'font24')
            self.getControl(102).setLabel(instruction, font='Head34' if cinema else 'font24')
            # Kodi may deliver onInit after the asynchronous QR request has
            # already published its image. Never restore the initial blank.
            self.getControl(101).setImage(self.image)
            self.getControl(103).setLabel(self.message, font='Body26' if cinema else 'font20')
            self.getControl(9001).setLabel('取消', font='Button28' if cinema else 'font20')
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
    window.message = '扫码后在手机确认。取消会保留当前账号。'
    return window

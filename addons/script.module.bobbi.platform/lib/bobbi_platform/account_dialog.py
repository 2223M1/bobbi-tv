"""Presentation only; QR lifecycle and account authority stay in cloud_ui."""


def create(image):
    import xbmc
    import xbmcaddon
    import xbmcgui

    class AccountQR(xbmcgui.WindowXMLDialog):
        def onInit(self):
            cinema = xbmc.getSkinDir() == 'skin.bobbi.cinema'
            self.getControl(100).setLabel('登录 115 网盘', font='Head40' if cinema else 'font24')
            self.getControl(101).setImage(str(image))
            self.getControl(102).setLabel('用「115 生活」App 扫码', font='Head34' if cinema else 'font24')
            self.getControl(103).setLabel(self.message, font='Body26' if cinema else 'font20')
            self.getControl(9001).setLabel('取消', font='Button28' if cinema else 'font20')
            self.setFocusId(9001)

        def set_status(self, value):
            self.message = value
            self.getControl(103).setLabel(value)

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
    window.message = '扫码后在手机确认。取消会保留当前账号。'
    return window

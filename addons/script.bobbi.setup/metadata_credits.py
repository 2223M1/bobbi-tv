"""Official attribution, loaded only when its user-facing page is opened."""
import xbmcgui
from bobbi_core.project_metadata import tmdb_key, ATTRIBUTION


class MetadataCredits(xbmcgui.WindowXMLDialog):
    def onInit(self):
        self.getControl(100).setText(
            ('已提供波比 TV 专用个人非商业应用配置，无需申请或登录 TMDb。'
             if tmdb_key() else '缺少维护者应用配置，请安装完整私人发行包。')
            + '\n\n' + ATTRIBUTION + '\n\nhttps://www.themoviedb.org')

    def onClick(self, control_id):
        if control_id == 9001:
            self.close()

    def onAction(self, action):
        if action.getId() in (9, 10, 92):
            self.close()

"""Android package maintenance never enters the CoreELEC ZIP transaction."""


def show_updates(dialog):
    import xbmc
    if xbmc.Player().isPlaying():
        dialog.ok('请先停止播放', '停止影片后再更新程序。')
        return False
    choice = dialog.select('更新与恢复', [
        '管理 Kodi 依赖', '管理已安装插件', 'Android 安装与更新说明',
        '检查 Android 更新', '从本地 APK 更新'])
    if choice < 0:
        return False
    if choice == 2:
        dialog.ok('更新 Android 影院',
                  '下载适合设备架构的波比 TV APK，直接覆盖安装，账号与观看记录会保留。\n'
                  '请勿使用 CoreELEC ZIP 包，也不要卸载应用或清除数据。')
        return False
    if choice in (3, 4):
        from .android_updates import install_from_ui
        return install_from_ui(dialog, online=choice == 3)
    if choice not in (0, 1):
        return False
    dialog.ok('Kodi 插件管理',
              '下一页可管理插件和依赖。波比影院请使用整包更新，勿用其他插件覆盖其组件。')
    if xbmc.Player().isPlaying():
        dialog.ok('当前正在播放', '已取消打开更新页，请看完后再操作。')
        return False
    target = 'addons://dependencies/' if choice == 0 else 'addons://user/all/'
    xbmc.executebuiltin('ActivateWindow(addonbrowser,%s,return)' % target)
    return True


def start(online=False, storage=False):
    import xbmc
    import xbmcgui
    if online or storage:
        return show_updates(xbmcgui.Dialog())
    xbmc.executebuiltin('RunScript(script.bobbi.setup)')
    return True

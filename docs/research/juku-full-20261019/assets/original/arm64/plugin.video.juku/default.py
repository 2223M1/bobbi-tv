# -*- coding: utf-8 -*-
import sys
import os
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

# 将 resources/lib 追加至运行期路径
project_root = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(project_root, 'resources', 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

try:
    from api_client import ApiClient
    from vfs_adapter import VfsAdapter
    from router import VfsRouter
    from daemon import ensure_daemon_started
except ImportError as e:
    xbmcgui.Dialog().ok("导入错误", "无法加载插件依赖模块: {}".format(str(e)))
    sys.exit(1)

def main():
    try:
        # 保证后台 Go 守护进程就绪
        ensure_daemon_started()

        addon = xbmcaddon.Addon()
        
        # 保证配置落入用户插件 profile 沙盒中以确保安全隔离
        profile_dir = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
        if not os.path.exists(profile_dir):
            os.makedirs(profile_dir)
        # 初始化 API 客户端
        api_client = ApiClient()

        # 获得 Kodi 提供的上下文参数
        base_url = sys.argv[0]
        handle = int(sys.argv[1])
        query_string = sys.argv[2] if len(sys.argv) > 2 else ""

        # 执行 VFS 渲染及路由派发
        adapter = VfsAdapter(handle, base_url)
        router = VfsRouter(adapter, api_client)
        router.route(query_string)
    except Exception as e:
        xbmc.log("MvPlugin Error: {}".format(str(e)), xbmc.LOGERROR)
        xbmcgui.Dialog().notification("插件出错", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

if __name__ == '__main__':
    main()

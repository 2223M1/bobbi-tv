# -*- coding:utf-8 -*-
"""B站插件入口 — Kodi 每次导航时启动全新进程，生成目录列表后立即退出。

v0.4.0-v0.6.x 在每个 CPythonInvoker 进程里起 daemon 线程服务静态 MPD，
作为 service.py 不启动时的 fallback。v0.7.0 删除该 fallback：
service.py 是 54321 的唯一 listener（live m3u8 端点必须长跑进程持续
listen，addon.py 短进程退出时 daemon 线程会随进程死亡）。如果
service.py 没启动，整个插件就会 broken —— 这是统一行为，便于排障。
"""
import atexit

import xbmc

from core import plugin

# 导入 routes 模块以注册所有路由（@plugin.route 装饰器在导入时自动注册）
import routes  # noqa: F401

# atexit 兜底：Kodi 进程退出时关掉所有 live danmaku 子线程，释放 socket。
# 新 CPythonInvoker 进程里 _instances 是空的，但本进程内的实例会被正常清理。
def _atexit_cleanup():
    try:
        mod = __import__('live.danmaku', fromlist=['stop_all_live_danmaku'])
        mod.stop_all_live_danmaku()
        # 释放所有 lock 文件（这些 lock 是本进程创建的，进程退时清掉）
        bp_mod = __import__('utils', fromlist=['get_temp_path'])
        bp = bp_mod.get_temp_path()
        if bp:
            import os as _os
            import glob as _glob
            for lock in _glob.glob(_os.path.join(bp, 'danmaku_*.lock')):
                try:
                    with open(lock, 'r', encoding='utf-8') as f:
                        first = f.read().split('\n', 1)[0]
                    if first == str(_os.getpid()):
                        _os.remove(lock)
                except Exception:
                    pass
    except Exception:
        pass

atexit.register(_atexit_cleanup)


# 注意：Kodi 每次导航都是全新 Python 进程，内存缓存不跨进程共享。
# clear_function_cache() 在新鲜进程中为 no-op，此处不调用。
# 缓存的持久化部分由 login/logout 路由负责刷新。

if __name__ == '__main__':
    plugin.run()

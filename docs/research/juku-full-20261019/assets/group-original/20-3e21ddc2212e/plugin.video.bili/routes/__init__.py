# -*- coding:utf-8 -*-
"""Kodi URL 路由处理：按功能拆分子模块。

addon.py 只需 `import routes`，本 __init__ 会触发所有子模块的 @plugin.route()
装饰器注册。路由模块之间通过 routes._helpers 共享辅助函数。
"""
# 触发每个子模块的 @plugin.route 装饰器注册
from . import auth       # noqa: F401
from . import menu       # noqa: F401
from . import popular    # noqa: F401
from . import user       # noqa: F401
from . import collections  # noqa: F401
from . import search     # noqa: F401
from . import home       # noqa: F401
from . import video      # noqa: F401
from . import live       # noqa: F401

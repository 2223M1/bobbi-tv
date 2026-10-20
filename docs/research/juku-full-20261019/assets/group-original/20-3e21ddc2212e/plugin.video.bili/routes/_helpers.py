# -*- coding:utf-8 -*-
"""路由共享的小工具函数（在多个 routes/*.py 里复用）。"""
from core import plugin
from utils import tag


def append_next_page(videos: list, route_name: str, **kwargs):
    """统一添加"下一页"条目，减少 15+ 处重复的 dict 构造。"""
    videos.append({
        'label': tag('下一页', 'yellow'),
        'path': plugin.url_for(route_name, **kwargs),
    })


def up_context_menu(uname: str, mid) -> list:
    """统一构造"转到UP"上下文菜单。"""
    return [(f"转到UP: {uname}", f"Container.Update({plugin.url_for('user', id=mid)})")]


def live_status_label(status, uname: str, title: str, sep: str = ' - ') -> str:
    """统一构造直播状态标签。"""
    if status == 1:
        return tag('【直播中】', 'red') + uname + sep + title
    return tag('【未直播】', 'grey') + uname + sep + title


def format_up_plot(uname: str, mid, roomid: str = '', extra: str = '') -> str:
    """统一构造 UP 主信息 plot 行。"""
    plot = f"UP: {uname}\tID: {mid}"
    if roomid:
        plot += f"\n房间号: {roomid}"
    plot += "\n\n"
    if extra:
        plot += extra
    return plot

# -*- coding:utf-8 -*-
"""菜单管理：首页目录项、上下移、恢复默认顺序。"""
from core import plugin, xbmc, xbmcgui
from utils import getSetting, install_adaptive, is_dash_capable, localize
from api import get_uid


# 进程内一次性: 用户回答过一次"是否安装 inputstream.adaptive"后不再弹同一个 yesno
# (Container.Refresh / 返回首页都会重新跑 index())。
_adaptive_prompt_shown = False


def _categories() -> list:
    """所有可选的一级菜单（id 对应 strings.po，path 指向对应路由）。"""
    uid = get_uid()
    return [
        {'name': 'home',            'id': 30101, 'path': plugin.url_for('home', page=1)},
        {'name': 'dynamic_list',    'id': 30102, 'path': plugin.url_for('dynamic_list')},
        {'name': 'ranking_list',    'id': 30103, 'path': plugin.url_for('ranking_list')},
        {'name': 'popular_weekly',  'id': 30114, 'path': plugin.url_for('popular_weekly')},
        {'name': 'popular_history', 'id': 30115, 'path': plugin.url_for('popular_history')},
        {'name': 'live_areas',      'id': 30104, 'path': plugin.url_for('live_areas', level=1, id=0)},
        {'name': 'followingLive',  'id': 30105, 'path': plugin.url_for('following_live', page=1)},
        {'name': 'my_collection',   'id': 30106, 'path': plugin.url_for('my_collection')},
        {'name': 'web_dynamic',     'id': 30107, 'path': plugin.url_for('web_dynamic', page=1, offset=0)},
        {'name': 'followings',      'id': 30108, 'path': plugin.url_for('followings', id=uid, page=1)},
        {'name': 'followers',       'id': 30109, 'path': plugin.url_for('followers', id=uid, page=1)},
        {'name': 'watchlater',      'id': 30110, 'path': plugin.url_for('watchlater')},
        {'name': 'history',         'id': 30111, 'path': plugin.url_for('history', time=0)},
        {'name': 'space_videos',    'id': 30112, 'path': plugin.url_for('space_videos', id=uid, page=1)},
        {'name': 'my',              'id': 30117, 'path': plugin.url_for('user', id=uid)},
        {'name': 'search_list',     'id': 30113, 'path': plugin.url_for('search_list')},
        {'name': 'open_settings',   'id': 30116, 'path': plugin.url_for('open_settings')},
    ]


def _update_categories() -> list:
    """读 storage 里的用户排序，与默认列表合并后回写。"""
    data = plugin.get_storage('data')
    sorted_categories = data.get('categories')
    if not sorted_categories:
        return _categories()
    categories = _categories()
    kv = {category['id']: category for category in categories}
    visited, new_categories = [], []
    for category in sorted_categories:
        if category['id'] in kv:
            visited.append(category['id'])
            new_categories.append(kv[category['id']])
    for cid in kv:
        if cid not in visited:
            new_categories.append(kv[cid])
    data['categories'] = new_categories
    return new_categories


@plugin.route('/')
def index():
    items = []
    categories = _update_categories()

    for category in categories:
        if getSetting('function.' + category['name']) == 'true':
            context_menu = [
                ('上移菜单项', 'RunPlugin(%s)' % plugin.url_for('move_up', name=category['name'])),
                ('下移菜单项', 'RunPlugin(%s)' % plugin.url_for('move_down', name=category['name'])),
                ('恢复默认菜单顺序', 'RunPlugin(%s)' % plugin.url_for('default_menus')),
            ]
            items.append({
                'label': localize(category['id']),
                'path': category['path'],
                'context_menu': context_menu,
            })

    # v0.6.0: 缺失时引导安装。点播能力差异见 utils.is_dash_capable 注释。
    global _adaptive_prompt_shown
    if not _adaptive_prompt_shown and not is_dash_capable():
        _adaptive_prompt_shown = True
        if xbmcgui.Dialog().yesno(
            '安装插件',
            '安装 inputstream.adaptive 后可播放 1080P+ / 杜比视界 / 杜比全景声 / Hi-Res FLAC。\n'
            '未安装时最高 720P。是否现在安装？',
            '取消', '确认',
        ):
            install_adaptive()

    return items


@plugin.route('/move_up/<name>/')
def move_up(name):
    data = plugin.get_storage('data')
    categories = data['categories']
    idx = next((i for i, item in enumerate(categories) if item['name'] == name), None)
    if idx is not None and idx > 0:
        categories[idx], categories[idx-1] = categories[idx-1], categories[idx]
    xbmc.executebuiltin('Container.Refresh')


@plugin.route('/move_down/<name>/')
def move_down(name):
    data = plugin.get_storage('data')
    categories = data['categories']
    idx = next((i for i, item in enumerate(categories) if item['name'] == name), None)
    if idx is not None and idx < len(categories) - 1:
        categories[idx], categories[idx+1] = categories[idx+1], categories[idx]
    xbmc.executebuiltin('Container.Refresh')


@plugin.route('/default_menus/')
def default_menus():
    data = plugin.get_storage('data')
    data['categories'] = _categories()
    xbmc.executebuiltin('Container.Refresh')


@plugin.route('/open_settings/')
def open_settings():
    plugin.open_settings()

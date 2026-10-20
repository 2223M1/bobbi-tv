# -*- coding:utf-8 -*-
"""搜索：关键字/分类/历史/删除。"""
from core import plugin, xbmc
from utils import tag, clear_text, convert_number
from api import get_api_data, getWbiKeys, encWbi
from playback import get_video_item
from ._helpers import append_next_page, up_context_menu, live_status_label


_SEARCH_TYPES = {
    'all':           '综合搜索',
    'video':         '视频搜索',
    'media_bangumi': '番剧搜索',
    'media_ft':      '影视搜索',
    'live':          '直播搜索',
    'bili_user':     '用户搜索',
}


@plugin.route('/search_list/')
def search_list():
    items = []
    for key, label in _SEARCH_TYPES.items():
        items.append({
            'label': label,
            'path': plugin.url_for('search', type=key, page=1),
        })
    items.append({
        'label': '清除搜索历史',
        'path': plugin.url_for('clear_search_history'),
    })
    data = plugin.get_storage('data')
    search_history = data.get('search_history', [])
    for item in search_history:
        context_menu = [
            ('删除该搜索历史',
             f"RunPlugin({plugin.url_for('delete_keyword', type=item['type'], keyword=item['keyword'])})"),
        ]
        items.append({
            'label': f"[B]{tag(item['keyword'], 'pink')}[/B]{tag('(' + _SEARCH_TYPES[item['type']] + ')', 'grey')}",
            'path': plugin.url_for('search_by_keyword', type=item['type'], keyword=item['keyword'], page=1),
            'context_menu': context_menu,
        })
    return items


@plugin.route('/delete_keyword/<type>/<keyword>/')
def delete_keyword(type, keyword):
    data = plugin.get_storage('data')
    search_history = data['search_history']
    for item in search_history:
        if item['keyword'] == keyword and item['type'] == type:
            search_history.remove(item)
            xbmc.executebuiltin('Container.Refresh')
            return


def _add_keyword(type, keyword):
    """把搜索关键字插入 history 头部，已存在则移到头部。"""
    data = plugin.get_storage('data')
    if 'search_history' not in data:
        data['search_history'] = []
    search_history = data['search_history']
    for item in search_history:
        if item['type'] == type and item['keyword'] == keyword:
            search_history.remove(item)
            search_history.insert(0, item)
            return
    search_history.insert(0, {'type': type, 'keyword': keyword})


@plugin.route('/clear_search_history/')
def clear_search_history():
    data = plugin.get_storage('data')
    if 'search_history' in data:
        data['search_history'] = []
        xbmc.executebuiltin('Container.Refresh')


def _get_search_list(items: list) -> list:
    videos = []
    for item in items:
        if item['type'] == 'video':
            item['title'] = clear_text(item['title'])
            video = get_video_item(item)
        elif item['type'] in ('media_bangumi', 'media_ft'):
            cv_type = '声优' if item['type'] == 'media_bangumi' else '出演'
            plot = f"{tag(clear_text(item['title']), 'pink')} {item['index_show']}\n\n"
            plot += f"地区: {item['areas']}\n"
            plot += cv_type + ': ' + clear_text(item['cv']).replace('\n', '/') + '\n'
            plot += item['staff'] + '\n\n'
            plot += item['desc']
            video = {
                'label': tag('【' + item['season_type_name'] + '】', 'pink') + clear_text(item['title']),
                'path': plugin.url_for('bangumi', type='season_id', id=item['season_id']),
                'icon': item['cover'],
                'thumbnail': item['cover'],
                'info': {'plot': plot},
            }
        elif item['type'] == 'bili_user':
            plot = f"UP: {item['uname']}\tLV{item['level']}\n"
            plot += f"ID: {item['mid']}\n"
            plot += f"粉丝: {convert_number(item['fans'])}\n\n"
            plot += f"签名: {item['usign']}\n"
            video = {
                'label': f"{tag('【用户】')}{item['uname']}",
                'path': plugin.url_for('user', id=item['mid']),
                'icon': item['upic'],
                'thumbnail': item['upic'],
                'info': {'plot': plot},
            }
        else:
            continue
        videos.append(video)
    return videos


def _build_live_search_item(item: dict, has_title: bool = True) -> dict:
    """构造直播搜索结果项；has_title 表示 item 是否有 title 字段。"""
    uname = clear_text(item['uname'])
    plot = f"UP: {uname}\tID: {item['uid']}\n房间号: {item['roomid']}\n\n"
    context_menu = up_context_menu(uname, item['uid'])
    if has_title:
        title = clear_text(item['title'])
        title_display = item['title'].replace(
            '<em class="keyword">', '[COLOR pink]'
        ).replace('</em>', '[/COLOR]')
        if item['live_status'] == 1:
            label = live_status_label(1, item['uname'], title_display)
        else:
            label = live_status_label(0, item['uname'], title_display)
    else:
        title = uname
        name_display = item['uname'].replace(
            '<em class="keyword">', '[COLOR pink]'
        ).replace('</em>', '[/COLOR]')
        if item['live_status'] == 1:
            label = live_status_label(1, '', name_display, sep='')
        else:
            label = live_status_label(0, '', name_display, sep='')
    return {
        'label': label,
        'path': plugin.url_for('live', id=item['roomid']),
        'is_playable': True,
        'icon': item['uface'],
        'thumbnail': item['uface'],
        'context_menu': context_menu,
        'info': {
            'mediatype': 'video',
            'title': title,
            'plot': plot,
        },
        'info_type': 'video',
    }


@plugin.route('/search/<type>/<page>/')
def search(type, page):
    videos = []
    keyboard = xbmc.Keyboard('', '请输入搜索内容')
    keyboard.doModal()
    if not keyboard.isConfirmed():
        return videos
    keyword = keyboard.getText()
    if not keyword.strip():
        return videos
    _add_keyword(type, keyword)
    return search_by_keyword(type, keyword, page)


@plugin.route('/search_by_keyword/<type>/<keyword>/<page>/')
def search_by_keyword(type, keyword, page):
    videos = []
    data = {
        'page': page, 'page_size': 50, 'platform': 'pc', 'keyword': keyword,
    }
    if type == 'all':
        url = '/x/web-interface/wbi/search/all/v2'
    else:
        url = '/x/web-interface/wbi/search/type'
        data['search_type'] = type

    # 搜索类 API 强制要求 WBI 签名
    img_key, sub_key = getWbiKeys()
    data = encWbi(data, img_key, sub_key)
    res = get_api_data(url, data)
    if res['code'] != 0:
        return videos
    if 'result' not in res['data']:
        return videos
    items = res['data']['result']
    if type == 'all':
        for result in items:
            if result['result_type'] in ('video', 'media_bangumi', 'media_ft', 'bili_user'):
                videos.extend(_get_search_list(result['data']))
    else:
        if type == 'live':
            for item in res['data']['result']['live_user']:
                videos.append(_build_live_search_item(item, has_title=False))
            for item in res['data']['result']['live_room']:
                videos.append(_build_live_search_item(item, has_title=True))
        else:
            videos.extend(_get_search_list(items))
    if res['data']['page'] < res['data']['numPages']:
        append_next_page(videos, 'search_by_keyword', type=type, keyword=keyword, page=int(page) + 1)
    return videos

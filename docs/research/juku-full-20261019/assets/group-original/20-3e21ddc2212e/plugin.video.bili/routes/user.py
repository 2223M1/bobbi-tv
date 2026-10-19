# -*- coding:utf-8 -*-
"""用户空间：投稿、关注、粉丝、个人信息。"""
from core import plugin
from utils import tag, notify, notify_error
from api import get_uid, get_api_data, getWbiKeys, encWbi
from playback import get_video_item
from ._helpers import append_next_page, up_context_menu, live_status_label


@plugin.route('/space_videos/<id>/<page>/')
def space_videos(id, page):
    videos = []
    if id == '0':
        notify('提示', '未登录')
        return videos
    ps = 50
    img_key, sub_key = getWbiKeys()
    data = encWbi(
        params={
            'mid': id, 'ps': ps, 'pn': page,
            'order': 'pubdate', 'tid': 0, 'keyword': '', 'platform': 'web',
        },
        img_key=img_key, sub_key=sub_key,
    )
    res = get_api_data('/x/space/wbi/arc/search', data)
    if res['code'] != 0:
        notify_error(res)
        return videos
    for item in res['data']['list']['vlist']:
        video = get_video_item(item)
        if video:
            videos.append(video)
    if int(page) * ps < res['data']['page']['count']:
        append_next_page(videos, 'space_videos', id=id, page=int(page) + 1)
    return videos


def _relation_list(api_path, route_name, id, page):
    users = []
    if id == '0':
        notify('提示', '未登录')
        return users
    ps = 50
    data = {
        'vmid': id, 'ps': ps, 'pn': page,
        'order': 'desc', 'order_type': 'attention',
    }
    res = get_api_data(api_path, data)
    if res['code'] != 0:
        notify_error(res)
        return users
    for item in res['data']['list']:
        if item['vip']['vipType'] == 0:
            uname = item['uname']
        else:
            uname = tag(item['uname'], 'pink')
        plot = f"UP: {item['uname']}\tID: {item['mid']}\n\n"
        if item['official_verify']['desc']:
            plot += tag(item['official_verify']['desc'], 'orange') + '\n'
        plot += '\n'
        if item['sign']:
            plot += f"签名: {item['sign']}"
        users.append({
            'label': uname,
            'path': plugin.url_for('user', id=item['mid']),
            'icon': item['face'],
            'thumbnail': item['face'],
            'info': {'plot': plot},
        })
    if int(page) * 50 < res['data']['total']:
        append_next_page(users, route_name, id=id, page=int(page) + 1)
    return users


@plugin.route('/followings/<id>/<page>/')
def followings(id, page):
    return _relation_list('/x/relation/followings', 'followings', id, page)


@plugin.route('/followers/<id>/<page>/')
def followers(id, page):
    return _relation_list('/x/relation/followers', 'followers', id, page)


@plugin.route('/user/<id>/')
def user(id):
    return [
        {'label': '投稿的视频',   'path': plugin.url_for('space_videos', id=id, page=1)},
        {'label': '直播间',       'path': plugin.url_for('user_live_room', uid=id)},
        {'label': '合集和列表',   'path': plugin.url_for('seasons_series', uid=id, page=1)},
        {'label': '关注列表',     'path': plugin.url_for('followings', id=id, page=1)},
        {'label': '粉丝列表',     'path': plugin.url_for('followers', id=get_uid(), page=1)},
        {'label': 'TA的订阅',     'path': plugin.url_for('his_subscription', id=id)},
    ]


@plugin.route('/user_live_room/<uid>/')
def user_live_room(uid):
    res = get_api_data('/x/space/wbi/acc/info', {'mid': uid})
    if res['code'] != 0:
        return []
    item = res['data']
    if not item['live_room']:
        notify('提示', '直播间不存在')
        return []
    plot = (
        f"UP: {item['name']}\tID: {item['mid']}\n"
        f"房间号: {item['live_room']['roomid']}\n"
        f"{item['live_room']['watched_show']['text_large']}"
    )
    label = live_status_label(
        item['live_room']['liveStatus'],
        item['name'], item['live_room']['title'],
    )
    context_menu = up_context_menu(item['name'], item['mid'])
    return [{
        'label': label,
        'path': plugin.url_for('live', id=item['live_room']['roomid']),
        'is_playable': True,
        'icon': item["live_room"]["cover"],
        'thumbnail': item["live_room"]["cover"],
        'context_menu': context_menu,
        'info': {
            'mediatype': 'video',
            'title': item['live_room']['title'],
            'plot': plot,
        },
    }]

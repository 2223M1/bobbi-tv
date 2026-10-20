# -*- coding:utf-8 -*-
"""收藏夹、稍后再看、历史记录。"""
from core import plugin
from utils import (
    tag, format_stat, notify, notify_error,
)
from api import get_uid, get_api_data
from playback import get_video_item
from ._helpers import append_next_page, up_context_menu, live_status_label


# ── 合集 / 系列 / 追番追剧 ───────────────────────────────────────────

@plugin.route('/seasons_series/<uid>/<page>/')
def seasons_series(uid, page):
    collections = []
    ps = 20
    data = {'mid': uid, 'page_num': page, 'page_size': ps}
    res = get_api_data('/x/polymer/web-space/seasons_series_list', data)
    if res['code'] != 0:
        notify_error(res)
        return collections
    for item in res['data']['items_lists']['seasons_list']:
        collections.append({
            'label': item['meta']['name'],
            'path': plugin.url_for(
                'seasons_and_series_detail',
                uid=uid, id=item['meta']['season_id'], type='season', page=1,
            ),
            'icon': item['meta']['cover'],
            'thumbnail': item['meta']['cover'],
        })
    for item in res['data']['items_lists']['series_list']:
        collections.append({
            'label': item['meta']['name'],
            'path': plugin.url_for(
                'seasons_and_series_detail',
                uid=uid, id=item['meta']['series_id'], type='series', page=1,
            ),
            'icon': item['meta']['cover'],
            'thumbnail': item['meta']['cover'],
        })
    page_info = res['data']['items_lists']['page']
    if page_info['page_num'] * page_info['page_size'] < page_info['total']:
        append_next_page(collections, 'seasons_series', uid=uid, page=int(page) + 1)
    return collections


@plugin.route('/seasons_and_series_detail/<uid>/<id>/<type>/<page>/')
def seasons_and_series_detail(id, uid, type, page):
    videos = []
    ps = 100
    if type == 'season':
        url = '/x/polymer/space/seasons_archives_list'
        data = {
            'mid': uid, 'season_id': id, 'sort_reverse': False,
            'page_size': ps, 'page_num': page,
        }
    else:
        url = '/x/series/archives'
        data = {
            'mid': uid, 'series_id': id, 'sort': 'desc',
            'ps': ps, 'pn': page,
        }
    res = get_api_data(url, data)
    if res['code'] != 0:
        return videos
    for item in res['data']['archives']:
        video = get_video_item(item)
        if video:
            videos.append(video)
    page_info = res['data']['page']
    if type == 'season':
        if page_info['page_num'] * page_info['page_size'] < page_info['total']:
            append_next_page(
                videos, 'seasons_and_series_detail',
                uid=uid, id=id, type=type, page=int(page) + 1,
            )
    else:
        if page_info['num'] * page_info['size'] < page_info['total']:
            append_next_page(
                videos, 'seasons_and_series_detail',
                uid=uid, id=id, type=type, page=int(page) + 1,
            )
    return videos


@plugin.route('/his_subscription/<id>/')
def his_subscription(id):
    return [
        {'label': '追番', 'path': plugin.url_for('fav_series', uid=id, type=1)},
        {'label': '追剧', 'path': plugin.url_for('fav_series', uid=id, type=2)},
    ]


# ── 我的收藏 / 追番 / 追剧 ───────────────────────────────────────────

@plugin.route('/my_collection/')
def my_collection():
    uid = get_uid()
    if uid == '0':
        notify('提示', '未登录')
        return []
    return [
        {'label': '我的收藏夹', 'path': plugin.url_for('favlist_list', uid=uid)},
        {'label': '追番',       'path': plugin.url_for('fav_series', uid=uid, type=1)},
        {'label': '追剧',       'path': plugin.url_for('fav_series', uid=uid, type=2)},
    ]


@plugin.route('/fav_series/<uid>/<type>/')
def fav_series(uid, type):
    videos = []
    if uid == '0':
        return videos
    res = get_api_data('/x/space/bangumi/follow/list', {'vmid': uid, 'type': type})
    if res['code'] != 0:
        return videos
    for item in res['data']['list']:
        label = item['title']
        if item['season_type_name']:
            label = tag('【' + item['season_type_name'] + '】', 'pink') + label
        plot = f"{tag(item['title'], 'pink')}\t{item['new_ep']['index_show']}\n"
        if item['publish']['release_date_show']:
            plot += f"发行时间: {item['publish']['release_date_show']}\n"
        if item['styles']:
            plot += f"类型: {tag(' '.join(item['styles']), 'blue')}\n"
        if item['areas']:
            plot += f"地区: {' '.join(area['name'] for area in item['areas'])}\n"
        state = format_stat(item)
        if state:
            plot += f"{state[:-3]}\n"
        plot += f"\n{item['summary']}"
        videos.append({
            'label': label,
            'path': plugin.url_for('bangumi', type='season_id', id=item['season_id']),
            'icon': item['cover'],
            'thumbnail': item['cover'],
            'info': {'plot': plot},
        })
    return videos


@plugin.route('/favlist_list/<uid>/')
def favlist_list(uid):
    videos = []
    if uid == '0':
        return videos
    res = get_api_data('/x/v3/fav/folder/created/list-all', {'up_mid': uid})
    if res['code'] != 0:
        return videos
    for item in res['data']['list']:
        videos.append({
            'label': item['title'],
            'path': plugin.url_for('favlist', id=item['id'], page=1),
        })
    return videos


@plugin.route('/favlist/<id>/<page>/')
def favlist(id, page):
    videos = []
    data = {
        'media_id': id, 'ps': 20, 'pn': page,
        'keyword': '', 'order': 'mtime', 'tid': '0',
    }
    res = get_api_data('/x/v3/fav/resource/list', data)
    if res['code'] != 0:
        return videos
    for item in res['data']['medias']:
        video = get_video_item(item)
        if video:
            videos.append(video)
    if res['data']['has_more']:
        append_next_page(videos, 'favlist', id=id, page=int(page) + 1)
    return videos


# ── 稍后再看 / 历史 ─────────────────────────────────────────────────

@plugin.route('/watchlater/')
def watchlater():
    videos = []
    res = get_api_data('/x/v2/history/toview')
    if res['code'] != 0:
        notify_error(res)
        return videos
    for item in res['data']['list']:
        video = get_video_item(item)
        if video:
            videos.append(video)
    return videos


@plugin.route('/history/<time>/')
def history(time):
    videos = []
    res = get_api_data('/x/web-interface/history/cursor', {'view_at': time, 'ps': 20}, raw=True)
    if res['code'] != 0:
        notify_error(res)
        return videos
    for item in res['data']['list']:
        if item['videos'] >= 1:
            video = get_video_item(item)
            if not video:
                continue
        else:
            if item['history']['business'] == 'live':
                label = live_status_label(
                    item['live_status'],
                    item['author_name'], item['title'],
                )
                context_menu = up_context_menu(item['author_name'], item['author_mid'])
                video = {
                    'label': label,
                    'path': plugin.url_for('live', id=item['kid']),
                    'is_playable': True,
                    'icon': item['cover'],
                    'thumbnail': item['cover'],
                    'context_menu': context_menu,
                    'info': {
                        'mediatype': 'video',
                        'title': item['title'],
                    },
                    'info_type': 'video',
                }
            elif item['history']['business'] == 'pgc':
                if item['badge']:
                    label = tag('【' + item['badge'] + '】', 'pink') + item['title']
                else:
                    label = item['title']
                if 'show_title' in item and item['show_title']:
                    label += '\n' + tag(item['show_title'], 'grey')
                video = {
                    'label': label,
                    'path': plugin.url_for(
                        'bangumi', type='ep_id', id=item['history']['epid'],
                    ),
                    'icon': item['cover'],
                    'thumbnail': item['cover'],
                    'info_type': 'video',
                }
            else:
                continue
        videos.append(video)
    append_next_page(videos, 'history', time=res['data']['cursor']['view_at'])
    return videos

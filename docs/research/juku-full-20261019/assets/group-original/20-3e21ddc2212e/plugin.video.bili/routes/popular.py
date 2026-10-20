# -*- coding:utf-8 -*-
"""热门 / 排行榜 / 每周必看。"""
from core import plugin
from utils import notify_error
from api import get_api_data
from playback import get_video_item


@plugin.route('/popular_history/')
def popular_history():
    videos = []
    res = get_api_data('/x/web-interface/popular/precious')
    if res['code'] != 0:
        return videos
    for item in res['data']['list']:
        video = get_video_item(item)
        if video:
            videos.append(video)
    return videos


@plugin.route('/popular_weekly/')
def popular_weekly():
    categories = []
    res = get_api_data('/x/web-interface/popular/series/list')
    if res['code'] != 0:
        return categories
    for item in res['data']['list']:
        categories.append({
            'label': f"{item['name']} {item['subject']}",
            'path': plugin.url_for('weekly', number=item['number']),
        })
    return categories


@plugin.route('/weekly/<number>/')
def weekly(number):
    videos = []
    res = get_api_data('/x/web-interface/popular/series/one', {'number': number})
    if res['code'] != 0:
        return videos
    for item in res['data']['list']:
        video = get_video_item(item)
        if video:
            videos.append(video)
    return videos


@plugin.route('/ranking_list/')
def ranking_list():
    rankings = [
        ['全站', 0], ['国创相关', 168], ['动画', 1], ['音乐', 3],
        ['舞蹈', 129], ['游戏', 4], ['知识', 36], ['科技', 188],
        ['运动', 234], ['汽车', 223], ['生活', 160], ['美食', 211],
        ['动物圈', 217], ['鬼畜', 119], ['时尚', 155], ['娱乐', 5],
        ['影视', 181],
    ]
    return [{
        'label': r[0],
        'path': plugin.url_for('ranking', id=r[1]),
    } for r in rankings]


@plugin.route('/ranking/<id>/')
def ranking(id):
    res = get_api_data('/x/web-interface/ranking/v2', {'rid': id})
    videos = []
    if res['code'] != 0:
        return videos
    for item in res['data']['list']:
        video = get_video_item(item)
        if video:
            videos.append(video)
    return videos


@plugin.route('/related_videos/<id>/')
def related_videos(id):
    videos = []
    res = get_api_data('/x/web-interface/archive/related', {'bvid': id})
    if res['code'] != 0:
        notify_error(res)
        return videos
    for item in res['data']:
        video = get_video_item(item)
        if video:
            videos.append(video)
    return videos

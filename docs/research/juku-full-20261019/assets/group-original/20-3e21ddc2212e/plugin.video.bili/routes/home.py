# -*- coding:utf-8 -*-
"""首页推荐 / 分区动态 / Web 动态。"""
import json

from core import plugin
from utils import tag
from api import get_api_data
from playback import get_video_item, parse_plot
from ._helpers import (
    append_next_page, up_context_menu, live_status_label,
)


# B 站动态分区（静态快照；如需更新请同步 B 站 API）
_DYNAMIC_REGIONS = [
    ['番剧', 13], ['- 连载动画', 33], ['- 完结动画', 32], ['- 资讯', 51], ['- 官方延伸', 152],
    ['电影', 23], ['国创', 167], ['- 国产动画', 153], ['- 国产原创相关', 168],
    ['- 布袋戏', 169], ['- 动态漫·广播剧', 195], ['- 资讯', 51],
    ['电视剧', 11], ['纪录片', 177], ['动画', 1], ['- MAD·AMV', 24],
    ['- MMD·3D', 25], ['- 短片·手书·配音', 47], ['- 手办·模玩', 210],
    ['- 特摄', 86], ['- 动漫杂谈', 253], ['- 综合', 27],
    ['游戏', 4], ['- 单机游戏', 17], ['- 电子竞技', 171], ['- 手机游戏', 172],
    ['- 网络游戏', 65], ['- 桌游棋牌', 173], ['- GMV', 121], ['- 音游', 136],
    ['- Mugen', 19],
    ['鬼畜', 119], ['- 鬼畜调教', 22], ['- 音MAD', 26], ['- 人力VOCALOID', 126],
    ['- 鬼畜剧场', 216], ['- 教程演示', 127],
    ['音乐', 3], ['- 原创音乐', 28], ['- 翻唱', 31], ['- 演奏', 59],
    ['- VOCALOID·UTAU', 30], ['- 音乐现场', 29], ['- MV', 193], ['- 乐评盘点', 243],
    ['- 音乐教学', 244], ['- 音乐综合', 130],
    ['舞蹈', 129], ['- 宅舞', 20], ['- 街舞', 198], ['- 明星舞蹈', 199],
    ['- 中国舞', 200], ['- 舞蹈综合', 154], ['- 舞蹈教程', 156],
    ['影视', 181], ['- 影视杂谈', 182], ['- 影视剪辑', 183], ['- 小剧场', 85],
    ['- 预告·资讯', 184],
    ['娱乐', 5], ['- 综艺', 71], ['- 娱乐杂谈', 241], ['- 粉丝创作', 242],
    ['- 明星综合', 137],
    ['知识', 36], ['- 科学科普', 201], ['- 社科·法律·心理', 124],
    ['- 人文历史', 228], ['- 财经商业', 207], ['- 校园学习', 208],
    ['- 职业职场', 209], ['- 设计·创意', 229], ['- 野生技能协会', 122],
    ['科技', 188], ['- 数码', 95], ['- 软件应用', 230], ['- 计算机技术', 231],
    ['- 科工机械', 232],
    ['资讯', 51], ['- 热点', 203], ['- 环球', 204], ['- 社会', 205], ['- 综合', 27],
    ['美食', 211], ['- 美食制作', 76], ['- 美食侦探', 212], ['- 美食测评', 213],
    ['- 田园美食', 214], ['- 美食记录', 215],
    ['生活', 160], ['- 搞笑', 138], ['- 亲子', 254], ['- 出行', 250],
    ['- 三农', 251], ['- 家居房产', 239], ['- 手工', 161], ['- 绘画', 162],
    ['- 日常', 21],
    ['汽车', 223], ['- 赛车', 245], ['- 改装玩车', 246], ['- 新能源车', 246],
    ['- 房车', 248], ['- 摩托车', 240], ['- 购车攻略', 227], ['- 汽车生活', 176],
    ['时尚', 155], ['- 美妆护肤', 157], ['- 仿妆cos', 252], ['- 穿搭', 158],
    ['- 时尚潮流', 159],
    ['运动', 234], ['- 篮球', 235], ['- 足球', 249], ['- 健身', 164],
    ['- 竞技体育', 236], ['- 运动文化', 237], ['- 运动综合', 238],
    ['动物圈', 217], ['- 喵星人', 218], ['- 汪星人', 219], ['- 小宠异宠', 222],
    ['- 野生动物', 221], ['- 动物二创', 220], ['- 动物综合', 75],
    ['搞笑', 138], ['单机游戏', 17],
]


@plugin.route('/home/<page>/')
def home(page):
    videos = []
    page = int(page)
    data = {
        'y_num': 3, 'fresh_type': 4, 'feed_version': 'V8',
        'fresh_idx_1h': page, 'fetch_row': 3 * page + 1,
        'fresh_idx': page, 'brush': page, 'homepage_ver': 1,
        'ps': 12, 'last_y_num': 4, 'outside_trigger': '',
    }
    res = get_api_data('/x/web-interface/index/top/feed/rcmd', data)
    if res['code'] != 0:
        return videos

    for item in res['data']['item']:
        if not item['bvid']:
            continue
        if 'live.bilibili.com' in item['uri']:
            label = live_status_label(
                item['room_info']['live_status'],
                item['owner']['name'], item['title'],
            )
            plot = (
                f"UP: {item['owner']['name']}\tID: {item['owner']['mid']}\n"
                f"房间号: {item['room_info']['room_id']}\n"
                f"{item['watched_show']['text_large']}\n"
                f"分区: {item['area']['area_name']}"
            )
            context_menu = up_context_menu(item['owner']['name'], item['owner']['mid'])
            video = {
                'label': label,
                'path': plugin.url_for('live', id=item['url'].split('/')[-1]),
                'is_playable': True,
                'icon': item['pic'],
                'thumbnail': item['pic'],
                'context_menu': context_menu,
                'info': {'plot': plot},
            }
        else:
            video = get_video_item(item)
            if not video:
                continue
        videos.append(video)
    append_next_page(videos, 'home', page=page + 1)
    return videos


@plugin.route('/dynamic_list/')
def dynamic_list():
    items = []
    for d in _DYNAMIC_REGIONS:
        if d[0].startswith('- '):
            continue
        items.append({
            'label': d[0],
            'path': plugin.url_for('dynamic', id=d[1], page=1),
        })
    return items


@plugin.route('/dynamic/<id>/<page>/')
def dynamic(id, page):
    videos = []
    ps = 50
    res = get_api_data('/x/web-interface/dynamic/region', {'pn': page, 'ps': ps, 'rid': id})
    if res['code'] != 0:
        return videos
    for item in res['data']['archives']:
        if 'redirect_url' in item and 'www.bilibili.com/bangumi/play' in item['redirect_url']:
            plot = parse_plot(item)
            bangumi_id = item['redirect_url'].split('/')[-1].split('?')[0]
            if bangumi_id.startswith('ep'):
                kind = 'ep_id'
            else:
                kind = 'season_id'
            bangumi_id = bangumi_id[2:]
            video = {
                'label': tag('【' + item['tname'] + '】', 'pink') + item['title'],
                'path': plugin.url_for('bangumi', type=kind, id=bangumi_id),
                'icon': item['pic'],
                'thumbnail': item['pic'],
                'info': {'plot': plot},
                'info_type': 'video',
            }
        else:
            video = get_video_item(item)
            if not video:
                continue
        videos.append(video)
    if int(page) * ps < res['data']['page']['count']:
        append_next_page(videos, 'dynamic', id=id, page=int(page) + 1)
    return videos


@plugin.route('/web_dynamic/<page>/<offset>/')
def web_dynamic(page, offset):
    videos = []
    data = {'timezone_offset': -480, 'type': 'all', 'page': page}
    if page != '1':
        data['offset'] = offset
    res = get_api_data('/x/polymer/web-dynamic/v1/feed/all', data)
    if res['code'] != 0:
        return videos
    items = res['data']['items']
    offset = res['data']['offset']
    for d in items:
        major = d['modules']['module_dynamic']['major']
        if not major:
            continue
        author = d['modules']['module_author']['name']
        mid = d['modules']['module_author']['mid']
        if 'archive' in major:
            item = major['archive']
            if not item:
                # B 站偶发返回 archive=null（原动态被删/草稿/聚合源已下架）
                continue
            item['author'] = author
            item['mid'] = mid
            video = get_video_item(item)
        elif 'live_rcmd' in major:
            live_rcmd = major['live_rcmd']
            if not live_rcmd or not live_rcmd.get('content'):
                continue
            content = live_rcmd['content']
            item = json.loads(content)
            label = live_status_label(
                item['live_play_info']['live_status'],
                author, item['live_play_info']['title'],
            )
            plot = (
                f"UP: {author}\tID: {mid}\n"
                f"房间号: {item['live_play_info']['room_id']}\n"
                f"{item['live_play_info']['watched_show']['text_large']}\n"
                f"分区: {tag(item['live_play_info']['parent_area_name'], 'blue')} "
                f"{tag(item['live_play_info']['area_name'], 'blue')}"
            )
            context_menu = up_context_menu(author, mid)
            video = {
                'label': label,
                'path': plugin.url_for('live', id=item['live_play_info']['room_id']),
                'is_playable': True,
                'icon': item['live_play_info']['cover'],
                'thumbnail': item['live_play_info']['cover'],
                'context_menu': context_menu,
                'info': {
                    'mediatype': 'video',
                    'title': item['live_play_info']['title'],
                    'plot': plot,
                },
                'info_type': 'video',
            }
        else:
            continue
        videos.append(video)
    if res['data']['has_more']:
        append_next_page(videos, 'web_dynamic', page=int(page) + 1, offset=offset)
    return videos

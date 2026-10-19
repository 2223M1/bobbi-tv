# -*- coding:utf-8 -*-
"""视频列表项构建：dict → Kodi ListItem 字段的转换；plot 文本生成。"""
from core import plugin
from utils import (
    tag, parts_tag, timestamp_to_date, format_stat, parse_duration,
)


def _flat_get(item: dict, *keys, default=None):
    """从 item 中按优先级取第一个存在的扁平字段值。"""
    for key in keys:
        if key in item:
            return item[key]
    return default


def _extract_uname_mid(item: dict):
    """从各 API 格式中提取 UP 主名称和 mid。"""
    for container in ('upper', 'owner'):
        if container in item:
            return item[container].get('name', ''), item[container].get('mid', 0)
    uname = _flat_get(item, 'author', 'author_name', default='')
    mid = _flat_get(item, 'mid', 'uid', 'author_mid', default=0)
    return uname, mid


def get_video_item(item: dict):
    """B 站 API 返回的 item dict → 喂给 _dict_to_li 的 listitem dict。

    单 P / 多 P / 鉴权失败（attr != 0）三种情况分支处理。
    """
    if item.get('attr', 0) != 0:
        return

    # 多 P 标记
    multi_key = ''
    for key in ('videos', 'page', 'count'):
        if key in item and isinstance(item[key], int):
            multi_key = key
            break

    uname, mid = _extract_uname_mid(item)
    pic = _flat_get(item, 'pic', 'cover', 'face', default='')
    bvid = _flat_get(item, 'bvid', default='')
    if not bvid and 'history' in item:
        bvid = item['history'].get('bvid', '')
    title = _flat_get(item, 'title', default='')
    cid = _flat_get(item, 'cid', default=0)
    if not cid:
        if 'ugc' in item:
            cid = item['ugc'].get('first_cid', 0)
        elif 'history' in item:
            cid = item['history'].get('cid', 0)

    # 时长提取
    duration = 0
    for key in ('duration', 'length'):
        if key in item:
            val = item[key]
            duration = val if isinstance(val, int) else parse_duration(val)
            break
    else:
        if 'duration_text' in item:
            duration = parse_duration(item['duration_text'])

    plot = parse_plot(item)
    if uname:
        label = f"{uname} - {title}"
    else:
        label = title
    context_menu = []
    if uname and mid:
        context_menu.append(
            (f"转到UP: {uname}", f"Container.Update({plugin.url_for('user', id=mid)})")
        )
    context_menu.append(
        ("查看推荐视频", f"Container.Update({plugin.url_for('related_videos', id=bvid)})")
    )
    if (not multi_key) or item[multi_key] == 1:
        context_menu.append(
            ("仅播放音频",
             f"PlayMedia({plugin.url_for('video', id=bvid, cid=cid, ispgc='false', audio_only='true', title=title)})")
        )
        video = {
            'label': label,
            'path': plugin.url_for('video', id=bvid, cid=cid, ispgc='false', audio_only='false', title=title),
            'is_playable': True,
            'icon': pic,
            'thumbnail': pic,
            'context_menu': context_menu,
            'info': {
                'mediatype': 'video',
                'title': title,
                'duration': duration,
                'plot': plot,
            },
            'info_type': 'video',
        }
    elif item[multi_key] > 1:
        video = {
            'label': parts_tag(item[multi_key]) + label,
            'path': plugin.url_for('videopages', id=bvid),
            'icon': pic,
            'thumbnail': pic,
            'context_menu': context_menu,
            'info': {'plot': plot},
        }
    else:
        return
    return video


def parse_plot(item: dict) -> str:
    """构造 Kodi 列表项的 plot 字段（hover 时显示的多行文本）。"""
    plot = ''
    if 'upper' in item:
        plot += f"UP: {item['upper']['name']}\tID: {item['upper']['mid']}\n"
    elif 'owner' in item:
        plot += f"UP: {item['owner']['name']}\tID: {item['owner']['mid']}\n"
    elif 'author' in item:
        plot += f"UP: {item['author']}"
        if 'mid' in item:
            plot += f'\tID: {item["mid"]}'
        plot += '\n'

    if 'bvid' in item:
        plot += f"{item['bvid']}\n"

    if 'pubdate' in item:
        plot += f"{timestamp_to_date(item['pubdate'])}\n"

    if 'copyright' in item and item.get('copyright') in (1, '1', True):
        plot += '未经作者授权禁止转载\n'

    state = format_stat(item)
    if state:
        plot += f"{state[:-3]}\n"
    plot += '\n'

    if 'achievement' in item and item['achievement']:
        plot += f"{tag(item['achievement'], 'orange')}\n\n"
    if 'rcmd_reason' in item and isinstance(item['rcmd_reason'], str) and item['rcmd_reason']:
        plot += f"推荐理由：{item['rcmd_reason']}\n\n"
    if 'desc' in item and item['desc']:
        plot += f"简介: {item['desc']}"
    elif 'description' in item and item['description']:
        plot += f"简介: {item['description']}"
    return plot

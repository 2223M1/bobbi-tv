# -*- coding:utf-8 -*-
"""直播：分区、关注、播放。"""
from urllib.parse import urlencode

from core import plugin, xbmc, xbmcgui
from utils import getSetting, notify, notify_error
from api import fetch_url, get_uid, get_cookie
from live import start_live_danmaku
from playback import choose_live_resolution
from ._helpers import (
    append_next_page, up_context_menu, live_status_label, format_up_plot, tag,
)


# B 站直播分区（静态快照；如需更新请同步 B 站 API）
_LIVE_AREAS = {
    '2': {
        'id': '2', 'name': '网游',
        'list': [
            {'id': '86', 'name': '英雄联盟'}, {'id': '92', 'name': 'DOTA2'},
            {'id': '89', 'name': 'CS:GO'}, {'id': '240', 'name': 'APEX英雄'},
            {'id': '666', 'name': '永劫无间'}, {'id': '88', 'name': '穿越火线'},
            {'id': '87', 'name': '守望先锋'}, {'id': '80', 'name': '吃鸡行动'},
            {'id': '252', 'name': '逃离塔科夫'}, {'id': '695', 'name': '传奇'},
            {'id': '78', 'name': 'DNF'}, {'id': '575', 'name': '生死狙击2'},
            {'id': '599', 'name': '洛奇英雄传'}, {'id': '102', 'name': '最终幻想14'},
            {'id': '249', 'name': '星际战甲'}, {'id': '710', 'name': '梦三国'},
            {'id': '690', 'name': '英魂之刃'}, {'id': '82', 'name': '剑网3'},
            {'id': '691', 'name': '铁甲雄兵'}, {'id': '300', 'name': '封印者'},
            {'id': '653', 'name': '新天龙八部'}, {'id': '667', 'name': '赛尔号'},
            {'id': '668', 'name': '造梦西游'}, {'id': '669', 'name': '洛克王国'},
            {'id': '670', 'name': '问道'}, {'id': '654', 'name': '诛仙世界'},
            {'id': '652', 'name': '大话西游'}, {'id': '683', 'name': '奇迹MU'},
            {'id': '684', 'name': '永恒之塔'}, {'id': '685', 'name': 'QQ三国'},
            {'id': '677', 'name': '人间地狱'}, {'id': '329', 'name': 'VALORANT'},
            {'id': '686', 'name': '彩虹岛'}, {'id': '663', 'name': '洛奇'},
            {'id': '664', 'name': '跑跑卡丁车'}, {'id': '658', 'name': '星际公民'},
            {'id': '659', 'name': 'Squad战术小队'}, {'id': '629', 'name': '反恐精英Online'},
            {'id': '648', 'name': '风暴奇侠'}, {'id': '642', 'name': '装甲战争'},
            {'id': '590', 'name': '失落的方舟'}, {'id': '639', 'name': '阿尔比恩'},
            {'id': '600', 'name': '猎杀对决'}, {'id': '472', 'name': 'CFHD '},
            {'id': '650', 'name': '骑士精神2'}, {'id': '680', 'name': '超击突破'},
            {'id': '634', 'name': '武装突袭'}, {'id': '84', 'name': '300英雄'},
            {'id': '91', 'name': '炉石传说'}, {'id': '499', 'name': '剑网3缘起'},
            {'id': '649', 'name': '街头篮球'}, {'id': '601', 'name': '综合射击'},
            {'id': '505', 'name': '剑灵'}, {'id': '651', 'name': '艾尔之光'},
            {'id': '632', 'name': '黑色沙漠'}, {'id': '596', 'name': ' 天涯明月刀'},
            {'id': '519', 'name': '超激斗梦境'}, {'id': '574', 'name': '冒险岛'},
            {'id': '487', 'name': '逆战'}, {'id': '181', 'name': '魔兽争霸3'},
            {'id': '610', 'name': 'QQ飞车'}, {'id': '83', 'name': '魔兽世界'},
            {'id': '388', 'name': 'FIFA ONLINE 4'}, {'id': '581', 'name': 'NBA2KOL2'},
            {'id': '318', 'name': '使命召唤:战区'}, {'id': '656', 'name': 'VRChat'},
            {'id': '115', 'name': '坦克世界'}, {'id': '248', 'name': '战舰世界'},
            {'id': '316', 'name': '战争雷霆'}, {'id': '383', 'name': '战意'},
            {'id': '114', 'name': '风暴英雄'}, {'id': '93', 'name': '星际争霸2'},
            {'id': '239', 'name': '刀塔自走棋'}, {'id': '164', 'name': '堡垒之夜'},
            {'id': '251', 'name': '枪神纪'}, {'id': '81', 'name': '三国杀'},
            {'id': '112', 'name': '龙之谷'}, {'id': '173', 'name': '古剑奇谭OL'},
            {'id': '176', 'name': '幻想全明星'}, {'id': '288', 'name': '怀旧网游'},
            {'id': '298', 'name': '新游前瞻'}, {'id': '331', 'name': '星战前夜：晨曦'},
            {'id': '350', 'name': '梦幻西游端游'}, {'id': '551', 'name': '流放之路'},
            {'id': '633', 'name': 'FPS沙盒'}, {'id': '459', 'name': '永恒轮回'},
            {'id': '607', 'name': '激战2'}, {'id': '107', 'name': '其他网游'},
        ],
    },
    '3': {
        'id': '3', 'name': '手游',
        'list': [
            {'id': '35', 'name': '王者荣耀'}, {'id': '256', 'name': '和平精英'},
            {'id': '395', 'name': 'LOL手游'}, {'id': '321', 'name': '原神'},
            {'id': '163', 'name': '第五人格'}, {'id': '255', 'name': '明日方舟'},
            {'id': '474', 'name': '哈利波特：魔法觉醒 '}, {'id': '550', 'name': '幻塔'},
            {'id': '514', 'name': '金铲铲之战'}, {'id': '506', 'name': 'APEX手游'},
            {'id': '598', 'name': '深空之眼'}, {'id': '675', 'name': '无期迷途'},
            {'id': '687', 'name': '光遇'}, {'id': '717', 'name': '跃迁旅人'},
            {'id': '725', 'name': '环形战争'}, {'id': '689', 'name': '香肠派对'},
            {'id': '645', 'name': '猫之城'}, {'id': '644', 'name': '玛娜希斯回响'},
            {'id': '386', 'name': '使命召唤手游'}, {'id': '615', 'name': '黑色沙漠手游'},
            {'id': '40', 'name': '崩坏3'}, {'id': '407', 'name': '游戏王：决斗链接'},
            {'id': '303', 'name': '游戏王'}, {'id': '724', 'name': 'JJ斗地主'},
            {'id': '571', 'name': '蛋仔派对'}, {'id': '36', 'name': '阴阳师'},
            {'id': '719', 'name': '欢乐斗地主'}, {'id': '718', 'name': '空之要塞：启航'},
            {'id': '292', 'name': '火影忍者手游'}, {'id': '37', 'name': 'Fate/GO'},
            {'id': '354', 'name': '综合棋牌'}, {'id': '154', 'name': 'QQ飞车手游'},
            {'id': '140', 'name': '决战！平安京'}, {'id': '41', 'name': '狼人杀'},
            {'id': '352', 'name': '三国杀移动版'}, {'id': '113', 'name': '碧蓝航线'},
            {'id': '156', 'name': '影之诗'}, {'id': '189', 'name': '明日之后'},
            {'id': '50', 'name': '部落冲突: 皇室战争'}, {'id': '661', 'name': '奥比岛手游'},
            {'id': '704', 'name': '盾之勇者成名录：浪潮'}, {'id': '214', 'name': '雀姬'},
            {'id': '330', 'name': ' 公主连结Re:Dive'}, {'id': '343', 'name': 'DNF手游'},
            {'id': '641', 'name': 'FIFA足球世界'}, {'id': '258', 'name': 'BanG Dream'},
            {'id': '469', 'name': '荒野乱斗'}, {'id': '333', 'name': 'CF手游'},
            {'id': '293', 'name': '战双帕弥什'}, {'id': '389', 'name': '天涯明月刀手游'},
            {'id': '42', 'name': '解密游戏'}, {'id': '576', 'name': '恋爱养成游戏'},
            {'id': '492', 'name': '暗黑破坏神：不朽'}, {'id': '502', 'name': '暗区突围'},
            {'id': '265', 'name': '跑跑卡丁车手游'}, {'id': '212', 'name': '非人学园'},
            {'id': '286', 'name': '百闻牌'}, {'id': '269', 'name': '猫和老鼠手游'},
            {'id': '442', 'name': '坎公骑冠剑'}, {'id': '203', 'name': '忍者必须死3'},
            {'id': '342', 'name': '梦幻西游手游'}, {'id': '504', 'name': '航海王热血航线'},
            {'id': '39', 'name': ' 少女前线'}, {'id': '688', 'name': '300大作战'},
            {'id': '525', 'name': '少女前线：云图计划'}, {'id': '478', 'name': '漫威超级战争'},
            {'id': '464', 'name': '摩尔庄园手游'}, {'id': '493', 'name': '宝可梦大集结'},
            {'id': '473', 'name': '小动物之星'}, {'id': '448', 'name': '天地劫：幽城再临'},
            {'id': '511', 'name': '漫威对决'}, {'id': '538', 'name': ' 东方归言录'},
            {'id': '178', 'name': '梦幻模拟战'}, {'id': '643', 'name': '时空猎人3'},
            {'id': '613', 'name': '重返帝国'}, {'id': '679', 'name': '休闲小游戏'},
            {'id': '98', 'name': '其他手游'}, {'id': '274', 'name': '新游评测'},
        ],
    },
    '6': {
        'id': '6', 'name': '单机游戏',
        'list': [
            {'id': '236', 'name': '主机游戏'}, {'id': '579', 'name': '战神'},
            {'id': '216', 'name': '我的世界'}, {'id': '726', 'name': '大多数'},
            {'id': '283', 'name': '独立游戏'}, {'id': '237', 'name': '怀旧游戏'},
            {'id': '460', 'name': '弹幕互动玩法'}, {'id': '722', 'name': '互动派对'},
            {'id': '276', 'name': '恐怖游戏'}, {'id': '693', 'name': '红色警戒2'},
            {'id': '570', 'name': '策略游戏'}, {'id': '723', 'name': '战锤40K:暗潮'},
            {'id': '707', 'name': '禁闭求生'}, {'id': '694', 'name': '斯普拉遁3'},
            {'id': '700', 'name': '卧龙：苍天陨落'}, {'id': '282', 'name': '使命召唤19'},
            {'id': '665', 'name': '异度神剑'}, {'id': '555', 'name': '艾尔登法环'},
            {'id': '636', 'name': '聚会游戏'}, {'id': '716', 'name': '哥谭骑士'},
            {'id': '277', 'name': '命运2'}, {'id': '630', 'name': '沙石镇时光'},
            {'id': '591', 'name': 'Dread Hunger'}, {'id': '721', 'name': '生化危机'},
            {'id': '714', 'name': '失落迷城：群星的诅咒'}, {'id': '597', 'name': '战地风云'},
            {'id': '720', 'name': '宝可梦集换式卡牌游戏'}, {'id': '612', 'name': '幽灵线：东京'},
            {'id': '357', 'name': '糖豆人'}, {'id': '586', 'name': '消逝的光芒2'},
            {'id': '245', 'name': '只狼'}, {'id': '578', 'name': '怪物猎人'},
            {'id': '218', 'name': ' 饥荒'}, {'id': '228', 'name': '精灵宝可梦'},
            {'id': '708', 'name': 'FIFA23'}, {'id': '582', 'name': '暖雪'},
            {'id': '594', 'name': '全面战争：战锤3'}, {'id': '580', 'name': '彩虹六号：异种'},
            {'id': '302', 'name': 'FORZA 极限竞速'}, {'id': '362', 'name': 'NBA2K'},
            {'id': '548', 'name': '帝国时代4'}, {'id': '559', 'name': '光环：无限'},
            {'id': '537', 'name': '孤岛惊魂6'}, {'id': '309', 'name': '植物大战僵尸'},
            {'id': '540', 'name': '仙剑奇侠传七'}, {'id': '223', 'name': '灵魂筹码'},
            {'id': '433', 'name': '格斗游戏'}, {'id': '226', 'name': '荒野大镖客2'},
            {'id': '426', 'name': '重生细胞'}, {'id': '227', 'name': '刺客信条'},
            {'id': '387', 'name': '恐鬼症'}, {'id': '219', 'name': '以撒'},
            {'id': '446', 'name': '双人成行'}, {'id': '295', 'name': '方舟'},
            {'id': '313', 'name': '仁王2'}, {'id': '244', 'name': '鬼泣5'},
            {'id': '727', 'name': '黑白莫比乌斯岁月的代价'}, {'id': '364', 'name': '枪火重生'},
            {'id': '341', 'name': '盗贼之海'}, {'id': '507', 'name': '胡闹厨房'},
            {'id': '500', 'name': '体育游戏'}, {'id': '439', 'name': '恐惧之间'},
            {'id': '308', 'name': '塞尔达'}, {'id': '261', 'name': '马力欧制造2'},
            {'id': '243', 'name': '全境封锁2'}, {'id': '326', 'name': '骑马与砍杀'},
            {'id': '270', 'name': '人类一败涂地'}, {'id': '424', 'name': '鬼谷八荒'},
            {'id': '273', 'name': '无主之地3'}, {'id': '220', 'name': '辐射76'},
            {'id': '257', 'name': '全面战争'}, {'id': '463', 'name': '亿万僵尸'},
            {'id': '535', 'name': '暗黑破坏神2'}, {'id': '583', 'name': '文字游戏'},
            {'id': '592', 'name': '恋爱模拟游戏'}, {'id': '593', 'name': '泰拉瑞亚'},
            {'id': '441', 'name': '雨中冒险2'}, {'id': '678', 'name': '游戏速通'},
            {'id': '681', 'name': '摔角城大乱斗'}, {'id': '692', 'name': '勇敢的哈克'},
            {'id': '698', 'name': ' 审判系列'}, {'id': '728', 'name': '蜀山：初章'},
            {'id': '235', 'name': '其他单机'},
        ],
    },
    '1': {
        'id': '1', 'name': '娱乐',
        'list': [
            {'id': '21', 'name': '视频唱见'}, {'id': '530', 'name': '萌宅领域'},
            {'id': '145', 'name': '视频聊天'}, {'id': '207', 'name': '舞见'},
            {'id': '706', 'name': '情感'}, {'id': '123', 'name': '户外'},
            {'id': '399', 'name': '日常'},
        ],
    },
    '5': {
        'id': '5', 'name': '电台',
        'list': [
            {'id': '190', 'name': '唱见电台'}, {'id': '192', 'name': '聊天电台'},
            {'id': '193', 'name': '配音'},
        ],
    },
    '9': {
        'id': '9', 'name': '虚拟主播',
        'list': [
            {'id': '371', 'name': '虚拟主播'}, {'id': '697', 'name': '3D虚拟主播'},
        ],
    },
    '10': {
        'id': '10', 'name': '生活',
        'list': [
            {'id': '646', 'name': '生活分享'}, {'id': '628', 'name': '运动'},
            {'id': '624', 'name': '搞笑'}, {'id': '627', 'name': '手工绘画'},
            {'id': '369', 'name': '萌宠'}, {'id': '367', 'name': '美食'},
            {'id': '378', 'name': '时尚'}, {'id': '33', 'name': '影音馆'},
        ],
    },
    '11': {
        'id': '11', 'name': '知识',
        'list': [
            {'id': '376', 'name': '社科法律心理'}, {'id': '702', 'name': '人文历史'},
            {'id': '372', 'name': '校园学习'}, {'id': '377', 'name': '职场·技能'},
            {'id': '375', 'name': ' 科技'}, {'id': '701', 'name': '科学科普'},
        ],
    },
    '13': {
        'id': '13', 'name': '赛事',
        'list': [
            {'id': '561', 'name': '游戏赛事'}, {'id': '562', 'name': '体育赛事'},
            {'id': '563', 'name': '赛事综合'},
        ],
    },
}


@plugin.route('/live_areas/<level>/<id>/')
def live_areas(level, id):
    areas = _LIVE_AREAS
    if level == '1':
        return [{
            'label': areas[a]['name'],
            'path': plugin.url_for('live_areas', level=2, id=a),
        } for a in areas]

    childran_areas = areas[id]['list']
    items = [{
        'label': areas[id]['name'],
        'path': plugin.url_for('live_area', pid=id, id=0, page=1),
    }]
    items.extend([{
        'label': a['name'],
        'path': plugin.url_for('live_area', pid=id, id=a['id'], page=1),
    } for a in childran_areas])
    return items


@plugin.route('/live_area/<pid>/<id>/<page>/')
def live_area(pid, id, page):
    lives = []
    page_size = 30
    data = {
        'platform': 'web', 'parent_area_id': pid, 'area_id': id,
        'page': page, 'page_size': page_size,
    }
    res = fetch_url(
        'https://api.live.bilibili.com/room/v3/area/getRoomList?' + urlencode(data)
    )
    if res['code'] != 0:
        return lives
    for item in res['data']['list']:
        plot = format_up_plot(item['uname'], item['uid'], item['roomid'])
        if item['verify']['desc']:
            plot += tag(item['verify']['desc'], 'orange') + '\n\n'
        plot += item['title']
        context_menu = up_context_menu(item['uname'], item['uid'])
        lives.append({
            'label': item['uname'] + ' - ' + item['title'],
            'path': plugin.url_for('live', id=item['roomid']),
            'is_playable': True,
            'icon': item['cover'],
            'thumbnail': item['cover'],
            'context_menu': context_menu,
            'info': {
                'mediatype': 'video',
                'title': item['title'],
                'plot': plot,
            },
            'info_type': 'video',
        })
    if page_size * int(page) < res['data']['count']:
        append_next_page(lives, 'live_area', pid=pid, id=id, page=int(page) + 1)
    return lives


@plugin.route('/following_live/<page>/')
def following_live(page):
    page = int(page)
    items = []
    if get_uid() == '0':
        notify('提示', '未登录')
        return items
    res = fetch_url(
        f'https://api.live.bilibili.com/xlive/web-ucenter/user/following'
        f'?page={page}&page_size=10&platform=web'
    )
    if res['code'] != 0:
        notify_error(res)
        return items
    for live in res['data']['list']:
        # B 站关注 API 可能返回 room_id（真实房间号）和 roomid（短号），优先 room_id
        room_id = live.get('room_id', live.get('roomid', 0))
        label = live_status_label(
            live['live_status'], live['uname'], live['title'], sep=' - ',
        )
        context_menu = up_context_menu(live['uname'], live['uid'])
        items.append({
            'label': label,
            'path': plugin.url_for('live', id=room_id),
            'is_playable': True if live['live_status'] == 1 else False,
            'icon': live['face'],
            'thumbnail': live['face'],
            'context_menu': context_menu,
            'info': {
                'mediatype': 'video',
                'title': live['title'],
                'plot': (
                    f"UP: {live['uname']}\tID: {live['uid']}\n"
                    f"房间号: {room_id}\n\n{live['title']}"
                ),
            },
            'info_type': 'video',
        })
    if page < res['data']['totalPage']:
        append_next_page(items, 'following_live', page=page + 1)
    return items


def _fetch(room_id, stream_qn, fmt_filter, protocol='0,1'):
    """调一次 getRoomPlayInfo，返回 streams 数组；失败返回 None。

    模块级函数，service.py daemon 线程（live_refresh_daemon）也调用。
    3 步 fallback（qn=user → qn=80 → protocol=0）在 live() route 内编排。
    """
    params = (
        'room_id={}&no_playurl=0&mask=1&qn={}&platform=web'
        '&protocol={}&format={}&codec=0,1,2'
        '&dolby=5&ptype=8&panorama=1'
    ).format(room_id, stream_qn, protocol, fmt_filter)
    r = fetch_url(
        'https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo?' + params
    )
    if r['code'] != 0 or not r.get('data', {}).get('playurl_info'):
        xbmc.log(
            '[live] _fetch room=%s qn=%s fmt=%s proto=%s -> empty (code=%s)' % (
                room_id, stream_qn, fmt_filter, protocol, r.get('code'),
            ),
            xbmc.LOGDEBUG,
        )
        return None
    return r['data']['playurl_info']['playurl']['stream']


def fetch_live_m3u8_url(room_id, qn=10000):
    """复用 live() 的 3 步 fallback 策略拉取 m3u8 URL。

    返回 m3u8 URL 字符串；非 m3u8 路径（m4s/flv）或失败返回 None。
    service.py daemon 线程（live_refresh_daemon）也调用。

    判断 m3u8 的依据是 format_name == 'ts' (HLS)，不是 URL 末尾 .m3u8
    —— B 站 base_url 字段有时候不带 .m3u8 后缀（实测）。
    """
    streams = _fetch(room_id, qn, '1')
    if not streams:
        streams = _fetch(room_id, 80, '0,1,2')
    if not streams:
        return None

    best = choose_live_resolution(streams)
    if not best:
        return None

    # 非 m3u8（HLS）路径 —— 只有 FLV 是真的非 HLS 单文件流。
    # ts / fmp4 都是 HLS 容器（实测 fmp4 也含 /index.m3u8 URL）。
    if best.get('format_name') == 'flv':
        return None

    # master_url 优先；回退 urls[0]
    master_url = best.get('master_url', '') or ''
    if master_url:
        return master_url

    urls = best.get('urls', []) or []
    return urls[0] if urls else None


@plugin.route('/live/<id>/')
def live(id):
    """Fetch a live stream and hand it to Kodi ffmpeg demuxer.

    Performance vs API rate-limit tradeoff:
      The naive ladder is 5 QN levels × 2 format filters × 1
      protocol, sequential. On a slow network this hits ~10 s
      (the user observed exactly that). Concurrency would shave
      it to ~1 s BUT would issue 5 simultaneous
      getRoomPlayInfo calls per click, which B 站 rate-limits
      aggressively (412 / -101 are common after bursts).

      Compromise: 2 sequential attempts only.
        1) qn=user_setting (usually 蓝光). One HTTP call. 99%
           success path. ~500 ms.
        2) qn=80 (标清). One HTTP call, only if (1) failed.
           Fallback for rate-limited or low-spec servers. ~500 ms.

      Worst case 1 s, best case 500 ms. No concurrent calls
      to avoid B 站 风控.
    """
    qn = getSetting('live_resolution')

    # ── Step 1: user's setting QN + format=1 (fmp4 preferred) ──
    streams = _fetch(id, qn, '1')
    # ── Step 2: fallback to qn=80 (标清) format=0,1,2 ──
    if not streams:
        streams = _fetch(id, 80, '0,1,2')
    if not streams:
        xbmc.log('[live] no playurl for room_id=%s' % id, xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            'plugin.video.bili', '无法获取直播流 (room_id=%s)' % id,
            xbmcgui.NOTIFICATION_ERROR, 3000,
        )
        return

    best = choose_live_resolution(streams)
    if not best:
        xbmc.log('[live] no codec room_id=%s' % id, xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            'plugin.video.bili', '该房间无可用编码 (room_id=%s)' % id,
            xbmcgui.NOTIFICATION_ERROR, 3000,
        )
        return

    master_url = best.get('master_url') or ''
    urls = best.get('urls') or []
    fmt_name = best.get('format_name', '')
    codec_name = best.get('codec_name', '')

    # 优先 master_url (m3u8 from http_hls)；回退 urls[0] (raw m4s)
    chosen = master_url or (urls[0] if urls else '')
    if not chosen:
        xbmc.log('[live] no url room_id=%s' % id, xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            'plugin.video.bili', '直播流 URL 为空 (room_id=%s)' % id,
            xbmcgui.NOTIFICATION_ERROR, 3000,
        )
        return

    xbmc.log(
        '[live] %s/%s room_id=%s master=%s url=%s' % (
            fmt_name, codec_name, id,
            'yes' if master_url else 'no',
            chosen[:80],
        ),
        xbmc.LOGDEBUG,
    )

    # ── 直播弹幕 ──
    live_ass = None
    if getSetting('enable_live_danmaku') == 'true':
        from api import get_uid, get_cookie
        uid = get_uid()
        cookie = get_cookie()
        live_ass, _ = start_live_danmaku(id, uid, cookie)

    # ── 输出路径: m3u8 走本地 HTTP 转发（service.py 54321） ──
    # 流程：
    #   1. 把 room_id + m3u8_url 写到 storage 'live_refresh_state'
    #      service.py m3u8 转发端点每次收到 ffmpeg 请求时从 storage 读
    #      m3u8_url 并实时 fetch CDN → ffmpeg 拿到的 manifest 永远 fresh。
    #   2. ffmpeg pipe 喂 http://127.0.0.1:54321/live-m3u8/<id>
    #      ffmpeg HLS demuxer 每 4 秒 refresh playlist 时访问本地端点
    #      → service.py 实时拉 CDN 拿当前 sliding window
    #      → 含新签名 .m4s URL → ffmpeg 持续拉新 segment → 不间断
    #
    # 关键：service.py 不是返回静态文件，而是**每次请求都 fetch CDN**。
    # 因此 ffmpeg 的 4s refresh 行为与"直拉 CDN"完全一致 —— sliding
    # window 永远 fresh，无 EOF / 无 60 分钟 TRID 过期。
    #
    # 非 m3u8 路径（flv 单文件流）走老 ffmpeg pipe 直接喂 CDN URL。
    # B 站 m3u8（HLS）路径的可靠标识：format_name ∈ {'ts', 'fmp4'}。
    # 只有 fmt_name == 'flv' 才是真的 FLV 单文件流（非 HLS）。
    is_m3u8 = fmt_name != 'flv'
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ffmpeg_hdr = 'Referer=https://www.bilibili.com&User-Agent=%s&Origin=https://www.bilibili.com' % ua

    if is_m3u8:
        # 写 storage: service.py m3u8 转发端点读这个 state。必须用
        # write_storage（直写 disk）而不是 get_storage（进程内 cache）：
        # service.py 是另一个进程实例，内存 cache 跨进程不可见。
        plugin.write_storage('live_refresh_state', {
            id: {'m3u8_url': chosen},  # service.py 每次来拉时 fetch CDN 这 URL
        })

        # ── 喂本地 URL 给 ffmpeg pipe ──
        # headers 给 ffmpeg 拉 .m4s 时用（CDN 校验 .m4s URL 的签名需要 Referer）
        live_url = (
            'http://127.0.0.1:54321/live-m3u8/%s'
            '|%s&reconnect=1&reconnect_streamed=1&reconnect_delay_max=5'
        ) % (id, ffmpeg_hdr)
    else:
        # m4s / flv / unknown：直接喂 CDN URL（inputstream.adaptive 不支持单文件 m4s）
        live_url = (
            '%s|%s&reconnect=1&reconnect_streamed=1&reconnect_delay_max=5'
        ) % (chosen, ffmpeg_hdr)

    item = {
        'path': live_url,
        'is_playable': True,
        'is_live': True,
    }
    xbmc.log(
        '[live] %s/%s room_id=%s path=%s' % (
            fmt_name, codec_name, id,
            'local-m3u8' if is_m3u8 else 'ffmpeg-pipe',
        ),
        xbmc.LOGINFO,
    )

    plugin.set_resolved_url(item, subtitles=live_ass)

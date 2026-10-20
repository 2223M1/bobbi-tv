# -*- coding:utf-8 -*-
"""plugin.video.bili 内部弹幕 → ASS 字幕转换工具。

历史来源: 改编自 StarBrilliant 的 Danmaku2ASS (GPL3) 项目
  https://github.com/m13253/danmaku2ass

本插件只用到 B 站场景，因此删除了 Niconico / Acfun / Tudou / MioMio
等其它站点解析逻辑；v0.5.0 重构：保留通用 ASS 写入路径 + 9 字段
(timeline, ts, no, text, pos, color, size, height, width) tuple 契约。

外部调用方:
  - playback/ass.py  : ReadComments, Danmaku2ASS
  - live/danmaku.py  : ProcessComments, CalculateLength
"""
import json
import math
import random
import re
import sys
import xml.dom.minidom
from functools import lru_cache

import xbmc


# ═══════════════════════════════════════════════════════════════════════
# 格式探测：只支持 B 站 v1 弹幕（xml version="1.0" encoding="UTF-8"）
# ═══════════════════════════════════════════════════════════════════════

def ProbeCommentFormat(f):
    """根据 XML 头判断是否为 B 站弹幕。返回 'Bilibili' 或 None。"""
    tmp = f.read(1)
    if tmp == '<':
        tmp = f.read(1)
        if tmp == '?':
            tmp = f.read(38)
            if tmp == 'xml version="1.0" encoding="UTF-8"?><i':
                return 'Bilibili'
    return None


#
# ReadCommentsBilibili 协议
#
# 输入:  f: 输入文件对象, fontsize: 默认字号
# 输出:  yield 9-字段 tuple
#   (timeline, timestamp, no, comment, pos, color, size, height, width)
#     timeline: 弹幕出现时间（秒）
#     timestamp: 弹幕提交时间（UNIX 秒，未启用）
#     no:       1, 2, 3, ... 序列号
#     comment:  弹幕内容
#     pos:      0=滚动, 1=底部居中, 2=顶部居中, 3=反向滚动, 7=定位弹幕
#     color:    0xRRGGBB
#     size:     字号 (px)
#     height:   估算高度 (px) = (comment.count('\n')+1) * size
#     width:    估算宽度 (px) = CalculateLength(comment) * size
#


def ReadCommentsBilibili(f, fontsize):
    dom = xml.dom.minidom.parse(f)
    comment_element = dom.getElementsByTagName('d')
    for i, comment in enumerate(comment_element):
        try:
            p = str(comment.getAttribute('p')).split(',')
            assert len(p) >= 5
            assert p[1] in ('1', '4', '5', '6', '7', '8')
            if comment.childNodes.length > 0:
                if p[1] in ('1', '4', '5', '6'):
                    c = str(comment.childNodes[0].wholeText).replace('/n', '\n')
                    size = int(p[2]) * fontsize / 25.0
                    yield (float(p[0]), int(p[4]), i, c, {'1': 0, '4': 2, '5': 1, '6': 3}[p[1]], int(p[3]), size, (c.count('\n') + 1) * size, CalculateLength(c) * size)
                elif p[1] == '7':  # positioned
                    c = str(comment.childNodes[0].wholeText)
                    yield (float(p[0]), int(p[4]), i, c, 'bilipos', int(p[3]), int(p[2]), 0, 0)
                elif p[1] == '8':
                    pass  # scripted, ignore
        except (AssertionError, AttributeError, IndexError, TypeError, ValueError):
            xbmc.log('[danmaku2ass] invalid comment: %s' % comment.toxml(), xbmc.LOGWARNING)
            continue



# 格式名 → 解析器映射 (v0.5.0 简化：只保留 B 站 v1, 模块私有)
_CommentFormatMap = {
    'Bilibili': ReadCommentsBilibili,
}


# ═══════════════════════════════════════════════════════════════════════
# ASS 输出：头部 / 单条弹幕 / 定位弹幕
# ═══════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def GetZoomFactor(SourceSize, TargetSize):
    """计算源/目标尺寸缩放因子。结果: (scale, dx, dy), NewX = f*x+dx。"""
    try:
        SourceAspect = SourceSize[0] / SourceSize[1]
        TargetAspect = TargetSize[0] / TargetSize[1]
        if TargetAspect < SourceAspect:  # narrower
            ScaleFactor = TargetSize[0] / SourceSize[0]
            return (ScaleFactor, 0, (TargetSize[1] - TargetSize[0] / SourceAspect) / 2)
        elif TargetAspect > SourceAspect:  # wider
            ScaleFactor = TargetSize[1] / SourceSize[1]
            return (ScaleFactor, (TargetSize[0] - TargetSize[1] * SourceAspect) / 2, 0)
        else:
            return (TargetSize[0] / SourceSize[0], 0, 0)
    except ZeroDivisionError:
        return (1, 0, 0)


# Flash FOV → ASS 旋转：参考 jabbany/CommentCoreLibrary
# Result: (transX, transY, rotX, rotY, rotZ, scaleX, scaleY)
def ConvertFlashRotation(rotY, rotZ, X, Y, width, height):
    def WrapAngle(deg):
        return 180 - ((180 - deg) % 360)
    rotY = WrapAngle(rotY)
    rotZ = WrapAngle(rotZ)
    if rotY in (90, -90):
        rotY -= 1
    if rotY == 0 or rotZ == 0:
        outX = 0
        outY = -rotY
        outZ = -rotZ
        rotY *= math.pi / 180.0
        rotZ *= math.pi / 180.0
    else:
        rotY *= math.pi / 180.0
        rotZ *= math.pi / 180.0
        outY = math.atan2(-math.sin(rotY) * math.cos(rotZ), math.cos(rotY)) * 180 / math.pi
        outZ = math.atan2(-math.cos(rotY) * math.sin(rotZ), math.cos(rotZ)) * 180 / math.pi
        outX = math.asin(math.sin(rotY) * math.sin(rotZ)) * 180 / math.pi
    trX = (X * math.cos(rotZ) + Y * math.sin(rotZ)) / math.cos(rotY) + (1 - math.cos(rotZ) / math.cos(rotY)) * width / 2 - math.sin(rotZ) / math.cos(rotY) * height / 2
    trY = Y * math.cos(rotZ) - X * math.sin(rotZ) + math.sin(rotZ) * width / 2 + (1 - math.cos(rotZ)) * height / 2
    trZ = (trX - width / 2) * math.sin(rotY)
    FOV = width * math.tan(2 * math.pi / 9.0) / 2
    try:
        scaleXY = FOV / (FOV + trZ)
    except ZeroDivisionError:
        xbmc.log('[danmaku2ass] rotation behind camera: trZ=%.0f' % trZ, xbmc.LOGERROR)
        scaleXY = 1
    trX = (trX - width / 2) * scaleXY + width / 2
    trY = (trY - height / 2) * scaleXY + height / 2
    if scaleXY < 0:
        scaleXY = -scaleXY
        outX += 180
        outY += 180
        xbmc.log('[danmaku2ass] rotation behind camera: trZ=%.0f < FOV=%.0f' % (trZ, FOV), xbmc.LOGERROR)
    return (trX, trY, WrapAngle(outX), WrapAngle(outY), WrapAngle(outZ), scaleXY * 100, scaleXY * 100)


def WriteCommentBilibiliPositioned(f, c, width, height, styleid):
    """B 站定位弹幕 (pos=7)：含旋转 / 缩放 / 透明度动画。"""
    BiliPlayerSize = (672, 438)  # 2014 player
    ZoomFactor = GetZoomFactor(BiliPlayerSize, (width, height))

    def GetPosition(InputPos, isHeight):
        isHeight = int(isHeight)
        if isinstance(InputPos, int):
            return ZoomFactor[0] * InputPos + ZoomFactor[isHeight + 1]
        elif isinstance(InputPos, float):
            if InputPos > 1:
                return ZoomFactor[0] * InputPos + ZoomFactor[isHeight + 1]
            else:
                return BiliPlayerSize[isHeight] * ZoomFactor[0] * InputPos + ZoomFactor[isHeight + 1]
        else:
            try:
                InputPos = int(InputPos)
            except ValueError:
                InputPos = float(InputPos)
            return GetPosition(InputPos, isHeight)

    try:
        comment_args = safe_list(json.loads(c[3]))
        text = ASSEscape(str(comment_args[4]).replace('/n', '\n'))
        from_x = comment_args.get(0, 0)
        from_y = comment_args.get(1, 0)
        to_x = comment_args.get(7, from_x)
        to_y = comment_args.get(8, from_y)
        from_x = GetPosition(from_x, False)
        from_y = GetPosition(from_y, True)
        to_x = GetPosition(to_x, False)
        to_y = GetPosition(to_y, True)
        alpha = safe_list(str(comment_args.get(2, '1')).split('-'))
        from_alpha = float(alpha.get(0, 1))
        to_alpha = float(alpha.get(1, from_alpha))
        from_alpha = 255 - round(from_alpha * 255)
        to_alpha = 255 - round(to_alpha * 255)
        rotate_z = int(comment_args.get(5, 0))
        rotate_y = int(comment_args.get(6, 0))
        lifetime = float(comment_args.get(3, 4500))
        duration = int(comment_args.get(9, lifetime * 1000))
        delay = int(comment_args.get(10, 0))
        fontface = comment_args.get(12)
        isborder = comment_args.get(11, 'true')
        from_rotarg = ConvertFlashRotation(rotate_y, rotate_z, from_x, from_y, width, height)
        to_rotarg = ConvertFlashRotation(rotate_y, rotate_z, to_x, to_y, width, height)
        styles = [r'\org(%d, %d)' % (width / 2, height / 2)]
        if from_rotarg[0:2] == to_rotarg[0:2]:
            styles.append('\\pos(%.0f, %.0f)' % (from_rotarg[0:2]))
        else:
            styles.append('\\move(%.0f, %.0f, %.0f, %.0f, %.0f, %.0f)' % (from_rotarg[0:2] + to_rotarg[0:2] + (delay, delay + duration)))
        styles.append('\\frx%.0f\\fry%.0f\\frz%.0f\\fscx%.0f\\fscy%.0f' % (from_rotarg[2:7]))
        if (from_x, from_y) != (to_x, to_y):
            styles.append('\\t(%d, %d, ' % (delay, delay + duration))
            styles.append('\\frx%.0f\\fry%.0f\\frz%.0f\\fscx%.0f\\fscy%.0f' % (to_rotarg[2:7]))
            styles.append(')')
        if fontface:
            styles.append('\\fn%s' % ASSEscape(fontface))
        styles.append('\\fs%.0f' % (c[6] * ZoomFactor[0]))
        if c[5] != 0xffffff:
            styles.append('\\c&H%s&' % ConvertColor(c[5]))
            if c[5] == 0x000000:
                styles.append('\\3c&HFFFFFF&')
        if from_alpha == to_alpha:
            styles.append('\\alpha&H%02X' % from_alpha)
        elif (from_alpha, to_alpha) == (255, 0):
            styles.append('\\fad(%.0f,0)' % (lifetime * 1000))
        elif (from_alpha, to_alpha) == (0, 255):
            styles.append('\\fad(0, %.0f)' % (lifetime * 1000))
        else:
            styles.append('\\fade(%(from_alpha)d, %(to_alpha)d, %(to_alpha)d, 0, %(end_time).0f, %(end_time).0f, %(end_time).0f)' % {'from_alpha': from_alpha, 'to_alpha': to_alpha, 'end_time': lifetime * 1000})
        if isborder == 'false':
            styles.append('\\bord0')
        f.write('Dialogue: -1,%(start)s,%(end)s,%(styleid)s,,0,0,0,,{%(styles)s}%(text)s\n' % {'start': ConvertTimestamp(c[0]), 'end': ConvertTimestamp(c[0] + lifetime), 'styles': ''.join(styles), 'text': text, 'styleid': styleid})
    except (IndexError, ValueError):
        try:
            data = c[3]
        except IndexError:
            data = repr(c)
        xbmc.log('[danmaku2ass] invalid positioned comment: %r' % data, xbmc.LOGWARNING)


def ProcessComments(comments, f, width, height, bottomReserved, fontface, fontsize, alpha, duration_marquee, duration_still, filters_regex, reduced, progress_callback):
    """主入口：把 9 字段 tuple 列表渲染成 ASS 字幕。"""
    styleid = 'Danmaku2ASS_%04x' % random.randint(0, 0xffff)
    WriteASSHead(f, width, height, fontface, fontsize, alpha, styleid)
    rows = [[None] * (height - bottomReserved + 1) for i in range(4)]
    for idx, i in enumerate(comments):
        if progress_callback and idx % 1000 == 0:
            progress_callback(idx, len(comments))
        if isinstance(i[4], int):
            skip = False
            for filter_regex in filters_regex:
                if filter_regex and filter_regex.search(i[3]):
                    skip = True
                    break
            if skip:
                continue
            row = 0
            rowmax = height - bottomReserved - i[7]
            while row <= rowmax:
                freerows = TestFreeRows(rows, i, row, width, height, bottomReserved, duration_marquee, duration_still)
                if freerows >= i[7]:
                    MarkCommentRow(rows, i, row)
                    WriteComment(f, i, row, width, height, bottomReserved, fontsize, duration_marquee, duration_still, styleid)
                    break
                else:
                    row += freerows or 1
            else:
                if not reduced:
                    row = FindAlternativeRow(rows, i, height, bottomReserved)
                    MarkCommentRow(rows, i, row)
                    WriteComment(f, i, row, width, height, bottomReserved, fontsize, duration_marquee, duration_still, styleid)
        elif i[4] == 'bilipos':
            WriteCommentBilibiliPositioned(f, i, width, height, styleid)
        else:
            xbmc.log('[danmaku2ass] invalid pos: %r' % i[3], xbmc.LOGWARNING)
    if progress_callback:
        progress_callback(len(comments), len(comments))


def TestFreeRows(rows, c, row, width, height, bottomReserved, duration_marquee, duration_still):
    res = 0
    rowmax = height - bottomReserved
    targetRow = None
    c_pos = c[4]
    c_h = c[7]
    c_t = c[0]
    if c_pos in (1, 2):
        row_list = rows[c_pos]
        while row < rowmax and res < c_h:
            if targetRow != row_list[row]:
                targetRow = row_list[row]
                if targetRow and targetRow[0] + duration_still > c_t:
                    break
            row += 1
            res += 1
    else:
        try:
            # thresholdTime: 屏幕上当前正在滚出的弹幕刚好到达右边缘的时间戳。
            # 用来判断同行的下一条滚动弹幕是否还有空间。
            thresholdTime = c_t - duration_marquee * (1.0 - float(width) / (c[8] + width))
        except ZeroDivisionError:
            thresholdTime = c_t - duration_marquee
        row_list = rows[c_pos]
        while row < rowmax and res < c_h:
            if targetRow != row_list[row]:
                targetRow = row_list[row]
                try:
                    if targetRow and (targetRow[0] > thresholdTime or targetRow[0] + targetRow[8] * duration_marquee / (targetRow[8] + width) > c_t):
                        break
                except ZeroDivisionError:
                    pass
            row += 1
            res += 1
    return res


def FindAlternativeRow(rows, c, height, bottomReserved):
    res = 0
    for row in range(height - bottomReserved - math.ceil(c[7])):
        if not rows[c[4]][row]:
            return row
        elif rows[c[4]][row][0] < rows[c[4]][res][0]:
            res = row
    return res


def MarkCommentRow(rows, c, row):
    try:
        for i in range(row, row + math.ceil(c[7])):
            rows[c[4]][i] = c
    except IndexError:
        pass


def WriteASSHead(f, width, height, fontface, fontsize, alpha, styleid):
    f.write(
        '''[Script Info]
; Script generated by Danmaku2ASS (adapted for plugin.video.bili)
ScriptType: v4.00+
PlayResX: %(width)d
PlayResY: %(height)d
Aspect Ratio: %(width)d:%(height)d
Collisions: Normal
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: %(styleid)s, %(fontface)s, %(fontsize).0f, &H%(alpha)02XFFFFFF, &H%(alpha)02XFFFFFF, &H%(alpha)02X000000, &H%(alpha)02X000000, 0, 0, 0, 0, 100, 100, 0.00, 0.00, 1, %(outline).0f, 0, 7, 0, 0, 0, 0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
''' % {'width': width, 'height': height, 'fontface': fontface, 'fontsize': fontsize, 'alpha': 255 - round(alpha * 255), 'outline': max(fontsize / 25.0, 1), 'styleid': styleid}
    )


def WriteComment(f, c, row, width, height, bottomReserved, fontsize, duration_marquee, duration_still, styleid):
    text = ASSEscape(c[3])
    c_pos = c[4]
    c_t = c[0]
    styles = []
    if c_pos == 1:
        styles.append('\\an8\\pos(%(halfwidth)d, %(row)d)' % {'halfwidth': width / 2, 'row': row})
        duration = duration_still
    elif c_pos == 2:
        styles.append('\\an2\\pos(%(halfwidth)d, %(row)d)' % {'halfwidth': width / 2, 'row': ConvertType2(row, height, bottomReserved)})
        duration = duration_still
    elif c_pos == 3:
        styles.append('\\move(%(neglen)d, %(row)d, %(width)d, %(row)d)' % {'width': width, 'row': row, 'neglen': -math.ceil(c[8])})
        duration = duration_marquee
    else:
        styles.append('\\move(%(width)d, %(row)d, %(neglen)d, %(row)d)' % {'width': width, 'row': row, 'neglen': -math.ceil(c[8])})
        duration = duration_marquee
    c_fs = c[6]
    if not (-1 < c_fs - fontsize < 1):
        styles.append('\\fs%.0f' % c_fs)
    c_color = c[5]
    if c_color != 0xffffff:
        styles.append('\\c&H%s&' % ConvertColor(c_color))
        if c_color == 0x000000:
            styles.append('\\3c&HFFFFFF&')
    f.write('Dialogue: 2,%(start)s,%(end)s,%(styleid)s,,0000,0000,0000,,{%(styles)s}%(text)s\n' % {'start': ConvertTimestamp(c_t), 'end': ConvertTimestamp(c_t + duration), 'styles': ''.join(styles), 'text': text, 'styleid': styleid})


# ═══════════════════════════════════════════════════════════════════════
# 文本 / 颜色 / 时间 工具
# ═══════════════════════════════════════════════════════════════════════

def _ReplaceLeadingSpace(s):
    """前后空格替换为零宽空格，避免 libass 裁剪。"""
    if len(s) == 0:
        return s
    if s[0] in (' ', '\t'):
        s = '​' + s
    if s[-1] in (' ', '\t'):
        s = s + '​'
    return s


def ASSEscape(s):
    # `or ' '` 兜底空白行：libass 会丢空行导致前后两行粘连
    return '\\N'.join((_ReplaceLeadingSpace(i) or ' ' for i in str(s).replace('\\', '\\​').replace('{', '\\{').replace('}', '\\}').split('\n')))


def CalculateLength(s):
    """估算字符串宽度（按字符数）。不精确但够用。"""
    return max(map(len, s.split('\n')))


def ConvertTimestamp(timestamp):
    """秒数 → ASS 时间格式 H:MM:SS.cs，支持负数。"""
    if timestamp < 0:
        return '-' + ConvertTimestamp(-timestamp)
    cs = round(timestamp * 100)
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    c = cs % 100
    return '%d:%02d:%02d.%02d' % (h, m, s, c)


def _ClipByte(x):
    if x > 255:
        return 255
    if x < 0:
        return 0
    return round(x)


# BT.601 → BT.709 转换矩阵常量（预乘）
_C709_R = (0.00956384088080656, 0.03217254540203729, 0.95826361371715607)
_C709_G = (-0.10493933142075390, 1.17231478191855154, -0.06737545049779757)
_C709_B = (0.91348912373987645, 0.07858536372532510, 0.00792551253479842)

# 颜色写入上限缓存 (B 站弹幕颜色种类通常 <50, 256 足够, 不实现 LRU 淘汰)
_color_cache = {0x000000: '000000', 0xffffff: 'FFFFFF'}


def ConvertColor(RGB, width=1280, height=576):
    """0xRRGGBB → ASS BGR 颜色串。低分辨率跳过 BT.709 转换。"""
    if RGB in _color_cache:
        return _color_cache[RGB]
    R = (RGB >> 16) & 0xff
    G = (RGB >> 8) & 0xff
    B = RGB & 0xff
    if width < 1280 and height < 576:
        result = '%02X%02X%02X' % (B, G, R)
    else:  # VobSub always uses BT.601 colorspace, convert to BT.709
        result = '%02X%02X%02X' % (
            _ClipByte(R * _C709_R[0] + G * _C709_R[1] + B * _C709_R[2]),
            _ClipByte(R * _C709_G[0] + G * _C709_G[1] + B * _C709_G[2]),
            _ClipByte(R * _C709_B[0] + G * _C709_B[1] + B * _C709_B[2])
        )
    if len(_color_cache) < 256:
        _color_cache[RGB] = result
    return result


def ConvertType2(row, height, bottomReserved):
    """顶部弹幕（pos=2）的 Y 坐标：距顶部多少像素。"""
    return height - bottomReserved - row


def ConvertToFile(filename_or_file, *args, **kwargs):
    """输入可以是文件名（str/bytes）或已打开的文件对象；返回文件对象。"""
    if isinstance(filename_or_file, bytes):
        filename_or_file = filename_or_file.decode('utf-8', 'replace')
    if isinstance(filename_or_file, str):
        return open(filename_or_file, *args, **kwargs)
    else:
        return filename_or_file


# ═══════════════════════════════════════════════════════════════════════
# 顶层 API（被外部 playback/ass.py / live/danmaku.py 调用）
# ═══════════════════════════════════════════════════════════════════════

class safe_list(list):
    """list + .get(idx, default) 失败回退。定位弹幕解析需要。"""
    def get(self, index, default=None):
        try:
            return self[index]
        except IndexError:
            return default


def Danmaku2ASS(input_files, input_format, output_file, stage_width, stage_height,
                reserve_blank=0, font_face='sans-serif', font_size=25.0,
                text_opacity=1.0, duration_marquee=5.0, duration_still=5.0,
                comment_filter=None, comment_filters_file=None,
                is_reduce_comments=False, progress_callback=None, comments=None):
    """VOD 弹幕主入口。input_format='autodetect' 时自动探测。"""
    comment_filters = [comment_filter]
    if comment_filters_file:
        with open(comment_filters_file, 'r') as f:
            d = f.readlines()
            comment_filters.extend([i.strip() for i in d])
    filters_regex = []
    for comment_filter in comment_filters:
        try:
            if comment_filter:
                filters_regex.append(re.compile(comment_filter))
        except re.error:
            raise ValueError('Invalid regular expression: %s' % comment_filter)
    fo = None
    if comments is None:
        comments = ReadComments(input_files, input_format, font_size)
    try:
        if output_file:
            fo = ConvertToFile(output_file, 'w', encoding='utf-8-sig', errors='replace', newline='\n')
        else:
            fo = sys.stdout
        ProcessComments(comments, fo, stage_width, stage_height, reserve_blank, font_face, font_size, text_opacity, duration_marquee, duration_still, filters_regex, is_reduce_comments, progress_callback)
    finally:
        if output_file and fo != output_file:
            fo.close()


def ReadComments(input_files, input_format, font_size=25.0, progress_callback=None):
    """读取弹幕文件并返回 9 字段 tuple 列表。autodetect 时调用 ProbeCommentFormat。"""
    if isinstance(input_files, bytes):
        input_files = input_files.decode('utf-8', 'replace')
    if isinstance(input_files, str):
        input_files = [input_files]
    else:
        input_files = list(input_files)
    import io
    comments = []
    for idx, i in enumerate(input_files):
        if progress_callback:
            progress_callback(idx, len(input_files))
        with ConvertToFile(i, 'r', encoding='utf-8', errors='replace') as f:
            s = f.read()
            str_io = io.StringIO(s)
            if input_format == 'autodetect':
                CommentProcessor = GetCommentProcessor(str_io)
                if not CommentProcessor:
                    raise ValueError('Failed to detect comment file format: %s' % i)
            else:
                CommentProcessor = _CommentFormatMap.get(input_format)
                if not CommentProcessor:
                    raise ValueError('Unknown comment file format: %s' % input_format)
            # ProbeCommentFormat 读 1+1+38 字节到 EOF；rebind 重新从 0 读，
            # 不依赖下游 processor 支持 seek(0) 或多份 StringIO
            str_io = io.StringIO(s)
            comments.extend(CommentProcessor(str_io, font_size))
    if progress_callback:
        progress_callback(len(input_files), len(input_files))
    comments.sort()
    return comments


def GetCommentProcessor(input_file):
    return _CommentFormatMap.get(ProbeCommentFormat(input_file))

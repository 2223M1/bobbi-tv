# -*- coding: utf-8 -*-
import os
import json
import time
import re
import urllib.parse

def kodi_jsonrpc(method, params=None):
    """通过 Kodi 原生 JSON-RPC 内部接口执行系统级调用"""
    try:
        import xbmc
    except ImportError:
        return None
    if not hasattr(xbmc, "executeJSONRPC"):
        return None

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": 1
    }
    if params:
        payload["params"] = params
    try:
        raw_res = xbmc.executeJSONRPC(json.dumps(payload))
        if raw_res:
            return json.loads(raw_res)
    except Exception:
        pass
    return None

def safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def format_file_size(bytes_val):
    try:
        val = float(bytes_val)
    except (ValueError, TypeError):
        return ""
    if val <= 0:
        return ""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if val < 1024.0 or unit == 'TB':
            if unit in ['B', 'KB']:
                return f"{int(val)} {unit}"
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"

YEAR_REGEX = re.compile(r'(?:\b|[._\(\[\{])((?:19|20)\d{2})(?:\b|[._\)\]\}])')
DATE_REGEX = re.compile(r'(?:19|20)\d{2}[-_.]?\d{2}[-_.]?\d{2}')

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.ts', '.m2ts', '.m4v', '.rmvb', '.vob', '.iso', '.mpg', '.mpeg', '.3gp', '.asf', '.ogv'}
AUDIO_EXTS = {'.mp3', '.flac', '.wav', '.ape', '.dts', '.m4a', '.aac', '.ogg', '.wma', '.opus', '.alac', '.aiff', '.dsf', '.dff', '.ac3', '.pcm', '.mid', '.midi', '.mka'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.tiff'}

def parse_episode_number(raw_name):
    """从文件名或集数标签中精确提取集数数字，避免将年份(如2026)、分辨率、日期或影片序号误识别为集数"""
    if not raw_name:
        return 0

    raw = str(raw_name).strip()
    if not raw:
        return 0

    # 0. 去除视频常见扩展名
    base_name, ext = os.path.splitext(raw)
    if ext.lower() in VIDEO_EXTS or (ext.startswith('.') and len(ext) <= 5):
        clean_target = base_name.strip()
    else:
        clean_target = raw

    # 1. 优先匹配明确的中文集数标签: 第XX集 / 第XX话 / 第XX期 / 第XX回
    m = re.search(r'第\s*(\d{1,4})\s*[集话話期回]', clean_target)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    # 2. 匹配标准季集标签: S01E02 / S1E2 / E02 / EP02 / EP2 / Episode 02
    m = re.search(r'(?:^|[^a-zA-Z0-9])(?:S\d{1,2})?\s*[-_.]?\s*E(\d{1,4})(?:[^a-zA-Z0-9]|$)', clean_target, re.IGNORECASE)
    if m:
        try:
            num = int(m.group(1))
            if num > 0:
                return num
        except ValueError:
            pass

    m = re.search(r'(?:^|[^a-zA-Z0-9])EP\s*(\d{1,4})(?:[^a-zA-Z0-9]|$)', clean_target, re.IGNORECASE)
    if m:
        try:
            num = int(m.group(1))
            if num > 0:
                return num
        except ValueError:
            pass

    m = re.search(r'(?:^|[^a-zA-Z0-9])(?:Season\s*\d+\s*)?Episode\s*(\d{1,4})(?:[^a-zA-Z0-9]|$)', clean_target, re.IGNORECASE)
    if m:
        try:
            num = int(m.group(1))
            if num > 0:
                return num
        except ValueError:
            pass

    # 3. 动漫/压制组常见格式: " - 01", " - 01v2", " - 108"
    m = re.search(r'\s+-\s+(\d{1,3})(?:v\d+)?(?:\s|\[|\.|\(|_|$)', clean_target)
    if m:
        try:
            num = int(m.group(1))
            if 1 <= num <= 999 and num not in {240, 360, 480, 576, 720}:
                return num
        except ValueError:
            pass

    # 4. 括号包裹的纯数字: [01], 【01】, (01)
    m = re.search(r'(?:\[|【|\()(\d{1,3})(?:v\d+)?(?:\]|】|\))', clean_target)
    if m:
        try:
            num = int(m.group(1))
            if 1 <= num <= 999 and num not in {240, 360, 480, 576, 720}:
                return num
        except ValueError:
            pass

    # 5. 开头即为集数前缀: "01 - 标题", "01.标题", "01_标题"
    m = re.match(r'^(\d{1,3})(?:v\d+)?\s*[-_.\s]\s*\S+', clean_target)
    if m:
        try:
            num = int(m.group(1))
            if 1 <= num <= 999 and num not in {240, 360, 480, 576, 720, 264, 265}:
                return num
        except ValueError:
            pass

    # 6. 纯数字字符串 (如 HLS 选集列表中的 "01", "1", "12", "100" 或 文件名 "01.mp4", "1.mkv")
    if clean_target.isdigit():
        try:
            num = int(clean_target)
            # 过滤年份 (1900-2099)、分辨率、编码
            if 1900 <= num <= 2099:
                return 0
            if num in {240, 360, 480, 576, 720, 1080, 2160, 4320, 264, 265}:
                return 0
            if 1 <= num <= 1899:
                return num
        except ValueError:
            pass

    # 7. 分隔符包裹的 2 位数字集号 (如 "片名.01.mp4", "片名_01.mkv", "片名.01.1080p")
    # 严格要求前后为 . _ - 空格 或行尾，且两位数 01-99
    # 同时排除日期 (如 2026-08-27, 20260827, 2026.01.15)
    if not DATE_REGEX.search(clean_target) and not re.match(r'^(?:19|20)\d{2}[-_.]\d{2}$', clean_target):
        for m in re.finditer(r'(?:[._\s\-])(\d{2})(?:[._\s\-]|$)', clean_target):
            start_pos = m.start(1)
            end_pos = m.end(1)
            # 检查是否命中 4 位年份内部
            is_year_part = False
            for ym in YEAR_REGEX.finditer(clean_target):
                if ym.start(1) <= start_pos and end_pos <= ym.end(1):
                    is_year_part = True
                    break
            if not is_year_part:
                try:
                    num = int(m.group(1))
                    if 1 <= num <= 99:
                        return num
                except ValueError:
                    pass

    return 0

def parse_season_number(raw_name):
    """从文件名、剧集标签或备注中提取季数数字，如 S01, S2, 第2季, Season 1 等"""
    if not raw_name:
        return 0
    raw = str(raw_name).strip()
    if not raw:
        return 0

    # 1. 匹配中文第N季
    m = re.search(r'第\s*(\d{1,2})\s*季', raw)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    # 2. 匹配标准季集标签: S01E02 / S1E2 / S02
    m = re.search(r'(?:^|[^a-zA-Z0-9])S(\d{1,2})(?:[^a-zA-Z0-9]|$)', raw, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    # 3. 匹配 Season 01
    m = re.search(r'(?:^|[^a-zA-Z0-9])Season\s*(\d{1,2})(?:[^a-zA-Z0-9]|$)', raw, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    return 0

def build_play_display_title(vod_title="", season_number=None, episode_number=None, episode_title="", remark="", fallback_title="", is_tv=False, type_id=None):
    """
    统一格式化播放时呈现给用户的视频标题：
    - 剧集：片名：季数集数（备注） 如 "繁花：第1季第1集（4K 原盘）" 或无备注时 "繁花：第1季第1集"
    - 电影：片名：（备注） 或 "片名"
    返回: (display_title, s_num, e_num, is_tv_item)
    """
    vod_title = (vod_title or "").strip()
    remark = (remark or "").strip()
    episode_title = (episode_title or "").strip()
    fallback_title = (fallback_title or "").strip()

    is_explicit_movie = (str(type_id) in ("1", "movie")) or (is_tv is False and str(type_id) != "2")

    # 1. 解析季号与集号
    s_val = None
    if season_number is not None and str(season_number).strip() != "":
        try:
            s_val = int(season_number)
        except (ValueError, TypeError):
            s_val = None

    e_val = None
    if episode_number is not None and str(episode_number).strip() != "":
        try:
            e_val = int(episode_number)
        except (ValueError, TypeError):
            e_val = None

    # 判定是否属于剧集分集项：如果显式声明为电影，则绝不判定为剧集，也不从标题/备注提取集号
    if is_explicit_movie:
        is_tv_item = False
        s_val = None
        e_val = None
    else:
        # 如果没有显式指定集号，尝试从 fallback_title / remark 解析
        if e_val is None or e_val <= 0:
            parsed_e = parse_episode_number(fallback_title) or parse_episode_number(remark)
            if parsed_e > 0:
                e_val = parsed_e

        if s_val is None:
            parsed_s = parse_season_number(fallback_title) or parse_season_number(remark)
            if parsed_s > 0:
                s_val = parsed_s

        is_tv_item = bool(is_tv or (e_val is not None and e_val > 0) or (s_val is not None and s_val > 1) or (s_val == 0) or episode_title)

    s_num = s_val if (s_val is not None and s_val >= 0) else 1
    e_num = e_val if (e_val is not None and e_val > 0) else 1

    if is_tv_item:
        ep_text = f"第{s_num}季第{e_num}集"
        clean_ep_t = episode_title
        if clean_ep_t and (clean_ep_t.replace(" ", "") in (f"第{e_num}集", f"第{e_num}话", f"E{e_num}", f"EP{e_num}", f"Episode{e_num}", f"episode{e_num}")):
            clean_ep_t = ""

        ep_part = f"{ep_text} {clean_ep_t}" if clean_ep_t else ep_text

        # 过滤 remark 中与 ep_part / ep_text 重复的内容（如备注写了 "第1集" 或 "EP01"）
        clean_remark = remark
        if clean_remark:
            if clean_remark.replace(" ", "") in (ep_text, f"第{e_num}集", f"第{e_num}话", f"E{e_num}", f"EP{e_num}", f"Episode{e_num}", f"episode{e_num}"):
                clean_remark = ""
            elif clean_ep_t and clean_remark == clean_ep_t:
                clean_remark = ""

        # 组装格式：片名：季数集数（备注）
        if vod_title:
            if clean_remark:
                display_title = f"{vod_title}：{ep_part}（{clean_remark}）"
            else:
                display_title = f"{vod_title}：{ep_part}"
        else:
            if clean_remark:
                display_title = f"{ep_part}（{clean_remark}）"
            else:
                display_title = ep_part
    else:
        # 非剧集 (电影)
        # 清洗掉可能混入片名的假 SxxExx 后缀
        clean_vod_title = re.sub(r'\s+S\d+E\d+.*$', '', vod_title).strip()
        content_tag = remark or fallback_title
        if content_tag:
            clean_tag = re.sub(r'\s+S\d+E\d+.*$', '', content_tag).strip()
            if clean_tag == clean_vod_title or content_tag == vod_title or content_tag == clean_vod_title:
                content_tag = ""

        if clean_vod_title:
            if content_tag:
                display_title = f"{clean_vod_title}：（{content_tag}）"
            else:
                display_title = clean_vod_title
        else:
            display_title = content_tag or ""

        s_num = 0
        e_num = 0

    return display_title, s_num, e_num, is_tv_item

def get_file_category(file_name):
    ext = os.path.splitext(file_name)[1].lower()
    if ext in VIDEO_EXTS:
        return "video", ext
    elif ext in AUDIO_EXTS:
        return "audio", ext
    elif ext in IMAGE_EXTS:
        return "image", ext
    return "other", ext

def should_mark_pan_link_invalid(err_msg):
    if not err_msg:
        return False
    normalized = err_msg.replace('：', ':')
    is_explicitly_invalid = (
        ("分享" in normalized and ("已失效" in normalized or "无可播放文件" in normalized or "文件不存在" in normalized or "已被原作者删除" in normalized))
        or "外链不存在" in normalized
        or "文件不存在" in normalized
        or "已被原作者删除" in normalized
        or "取消分享" in normalized
        or "被分享者取消" in normalized
    )
    is_share_token_error = "分享 token 失败: HTTP 404" in normalized or "分享 token 失败: HTTP 403" in normalized
    return is_explicitly_invalid or is_share_token_error


# ------------------------------------------------------------------------------
# 1. 标签本地 TTL 缓存管理器 (TagsCacheManager)
# ------------------------------------------------------------------------------
class TagsCacheManager:
    """处理视频标签的本地持久化与 TTL 缓存机制"""
    def __init__(self, cache_dir, ttl=3600):
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "tags_cache.json")
        self.ttl = ttl

    def get_cached_tags(self):
        """读取未过期的标签缓存"""
        if not os.path.exists(self.cache_file):
            return None
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if time.time() - data.get("timestamp", 0) < self.ttl:
                return data.get("tags")
        except Exception:
            pass
        return None

    def save_tags(self, tags):
        """将标签写入本地文件"""
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception:
                pass
        try:
            data = {
                "timestamp": time.time(),
                "tags": tags
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ------------------------------------------------------------------------------
# 1.5 播放历史记录管理器 (HistoryManager)
# ------------------------------------------------------------------------------
class HistoryManager:
    """管理视频的播放历史记录"""
    def __init__(self, cache_dir, max_items=50):
        self.cache_dir = cache_dir
        self.history_file = os.path.join(cache_dir, "play_history.json")
        self.max_items = max_items

    def load_history(self):
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_history(self, history):
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception:
                pass
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_record(self, record):
        """
        添加一条播放记录。如果已存在相同的记录（通过相同播放参数判定），则将其移动到最前。
        """
        history = self.load_history()
        new_history = []
        
        def is_same(r1, r2):
            p1 = r1.get("play_params") or {}
            p2 = r2.get("play_params") or {}
            a1 = p1.get("action")
            a2 = p2.get("action")
            if a1 != a2:
                return False
            if a1 == "play_hls":
                return p1.get("url") == p2.get("url")
            elif a1 == "pan_play":
                return p1.get("url") == p2.get("url") and p1.get("file_id") == p2.get("file_id")
            elif a1 == "line_episodes":
                return p1.get("id") == p2.get("id") and p1.get("line") == p2.get("line")
            elif a1 == "list_files":
                return p1.get("url") == p2.get("url")
            elif a1 == "play_private_link":
                if p1.get("movie_id") and p2.get("movie_id") and p1.get("movie_id") == p2.get("movie_id"):
                    return (p1.get("season_number") == p2.get("season_number") and p1.get("episode_number") == p2.get("episode_number"))
                return p1.get("url") == p2.get("url")
            elif a1 in ("cloud_down_play", "cloud_down_task_play"):
                return p1.get("url") == p2.get("url") or (p1.get("hash") and p1.get("hash") == p2.get("hash"))
            return False

        for item in history:
            if not is_same(item, record):
                new_history.append(item)
                
        new_history.insert(0, record)
        new_history = new_history[:self.max_items]
        self.save_history(new_history)

    def clear_history(self):
        self.save_history([])


# ------------------------------------------------------------------------------
# 1.6 搜索历史记录管理器 (SearchHistoryManager)
# ------------------------------------------------------------------------------
class SearchHistoryManager:
    """管理搜索历史记录"""
    def __init__(self, cache_dir, max_items=20):
        self.cache_dir = cache_dir
        self.history_file = os.path.join(cache_dir, "search_history.json")
        self.max_items = max_items

    def load_history(self):
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                res = json.load(f)
                if isinstance(res, list):
                    return res
                return []
        except Exception:
            return []

    def save_history(self, history):
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception:
                pass
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_query(self, query):
        """
        添加一条搜索关键词。去重并置顶。
        """
        if not query:
            return
        query = query.strip()
        if not query:
            return
        history = self.load_history()
        # 去重
        if query in history:
            try:
                history.remove(query)
            except Exception:
                pass
        # 置顶
        history.insert(0, query)
        history = history[:self.max_items]
        self.save_history(history)

    def clear_history(self):
        """清除所有搜索记录"""
        self.save_history([])


# ------------------------------------------------------------------------------
# 1.7 推送历史记录管理器 (PushHistoryManager)
# ------------------------------------------------------------------------------
class PushHistoryManager:
    """管理推送网盘链接的历史记录"""
    def __init__(self, cache_dir, max_items=50):
        self.cache_dir = cache_dir
        self.history_file = os.path.join(cache_dir, "push_history.json")
        self.max_items = max_items

    def load_history(self):
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                res = json.load(f)
                if isinstance(res, list):
                    return res
                return []
        except Exception:
            return []

    def save_history(self, history):
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception:
                pass
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_record(self, record):
        """
        添加一条推送记录。如果已存在相同的 URL，则将其移动到最前。
        """
        if not record or not record.get("url"):
            return
        history = self.load_history()
        new_history = []
        url = record.get("url").strip()
        
        for item in history:
            if item.get("url", "").strip() != url:
                new_history.append(item)
                
        new_history.insert(0, record)
        new_history = new_history[:self.max_items]
        self.save_history(new_history)

    def clear_history(self):
        self.save_history([])


# ------------------------------------------------------------------------------
# 2. 筛选项常量定义
# ------------------------------------------------------------------------------
YEARS = ["全部"] + [str(y) for y in range(2026, 2006, -1)] + ["更早"]
YEAR_VALUES = [None] + [str(y) for y in range(2026, 2006, -1)] + ["earlier"]

AREAS = ["全部", "大陆", "香港", "台湾", "美国", "西班牙", "法国", "英国", "日本", "韩国", "泰国", "德国", "印度", "意大利", "加拿大", "其它"]
AREA_VALUES = [None if a == "全部" else a for a in AREAS]

GENRES = ["全部", "剧情", "喜剧", "惊悚", "动作", "犯罪", "爱情", "恐怖", "悬疑", "纪录", "冒险", "奇幻", "家庭", "科幻", "动画", "历史", "电视电影", "科幻玄幻", "音乐", "动作冒险", "战争", "西部", "真人秀", "战争政治", "古装"]
GENRE_VALUES = [None if g == "全部" else g for g in GENRES]


# cloudid 或 provider key → 网盘名称映射
CLOUD_PROVIDER_NAMES = {
    "1": "阿里云盘", "ALIYUN": "阿里云盘", "aliyun": "阿里云盘",
    "2": "夸克网盘", "QUARK": "夸克网盘", "quark": "夸克网盘",
    "3": "UC网盘", "UC": "UC网盘", "uc": "UC网盘",
    "4": "百度网盘", "BAIDU": "百度网盘", "baidu": "百度网盘",
    "5": "迅雷网盘", "XUNLEI": "迅雷网盘", "xunlei": "迅雷网盘",
    "6": "123云盘", "CLOUD123": "123云盘", "cloud123": "123云盘",
    "7": "115网盘", "CLOUD115": "115网盘", "cloud115": "115网盘",
    "8": "移动云盘", "CHINA_MOBILE": "移动云盘", "china_mobile": "移动云盘",
    "9": "天翼云盘", "CHINA_TELECOM": "天翼云盘", "china_telecom": "天翼云盘",
    "11": "光鸭云盘", "GUANGYA": "光鸭云盘", "guangya": "光鸭云盘",
    "magnet": "磁力链接", "MAGNET": "磁力链接",
    "ed2k": "ED2K", "ED2K": "ED2K",
}

# cloudid 或 provider key → Go daemon provider key
CLOUD_PROVIDER_KEYS = {
    "1": "ALIYUN", "ALIYUN": "ALIYUN", "aliyun": "ALIYUN", "阿里云盘": "ALIYUN", "阿里网盘": "ALIYUN", "阿里": "ALIYUN",
    "2": "QUARK", "QUARK": "QUARK", "quark": "QUARK", "夸克网盘": "QUARK", "夸克": "QUARK",
    "3": "UC", "UC": "UC", "uc": "UC", "UC网盘": "UC",
    "4": "BAIDU", "BAIDU": "BAIDU", "baidu": "BAIDU", "百度网盘": "BAIDU", "百度": "BAIDU",
    "5": "XUNLEI", "XUNLEI": "XUNLEI", "xunlei": "XUNLEI", "迅雷网盘": "XUNLEI", "迅雷云盘": "XUNLEI", "迅雷": "XUNLEI",
    "6": "CLOUD123", "CLOUD123": "CLOUD123", "cloud123": "CLOUD123", "123云盘": "CLOUD123", "123网盘": "CLOUD123",
    "7": "CLOUD115", "CLOUD115": "CLOUD115", "cloud115": "CLOUD115", "115网盘": "CLOUD115", "115云盘": "CLOUD115", "115": "CLOUD115",
    "8": "CHINA_MOBILE", "CHINA_MOBILE": "CHINA_MOBILE", "china_mobile": "CHINA_MOBILE", "移动云盘": "CHINA_MOBILE", "中国移动": "CHINA_MOBILE",
    "9": "CHINA_TELECOM", "CHINA_TELECOM": "CHINA_TELECOM", "china_telecom": "CHINA_TELECOM", "天翼云盘": "CHINA_TELECOM", "中国电信": "CHINA_TELECOM",
    "11": "GUANGYA", "GUANGYA": "GUANGYA", "guangya": "GUANGYA", "光鸭云盘": "GUANGYA", "光鸭": "GUANGYA",
}

PAN_ALIAS_TO_ID = {
    "7": "7", "115": "7", "cloud115": "7", "CLOUD115": "7",
    "4": "4", "bd": "4", "baidu": "4", "BAIDU": "4",
    "2": "2", "qk": "2", "quark": "2", "QUARK": "2",
    "3": "3", "uc": "3", "UC": "3",
    "11": "11", "gy": "11", "guangya": "11", "GUANGYA": "11",
    "6": "6", "123": "6", "cloud123": "6", "CLOUD123": "6",
    "9": "9", "ty": "9", "china_telecom": "9", "CHINA_TELECOM": "9",
    "8": "8", "yd": "8", "china_mobile": "8", "CHINA_MOBILE": "8",
    "5": "5", "xl": "5", "xunlei": "5", "XUNLEI": "5",
    "1": "1", "ali": "1", "aliyun": "1", "ALIYUN": "1",
    "10": "10"
}

def sort_pan_keys(pan_keys, pan_order=None):
    """根据 pan_order 权重序列对 pan_keys 进行重新排序"""
    if not isinstance(pan_order, list):
        pan_order = ["7", "4", "2", "3", "11", "6", "9", "8", "5", "1", "10"]
    def get_order_idx(k):
        cloud_id = PAN_ALIAS_TO_ID.get(str(k), str(k))
        try:
            return pan_order.index(cloud_id)
        except (ValueError, AttributeError):
            return 999
    return sorted(list(pan_keys), key=get_order_idx)

def detect_cloud_provider_key(provider="", url="", err_msg=""):
    """多级智能推导网盘 provider 英文 KEY (ALIYUN, QUARK, UC, BAIDU, XUNLEI, CLOUD123, CLOUD115 等)"""
    p_str = str(provider or "").strip()
    if p_str in CLOUD_PROVIDER_KEYS:
        return CLOUD_PROVIDER_KEYS[p_str]

    u = (url or "").lower()
    if "115.com" in u or "115cdn.com" in u or "anxia.com" in u:
        return "CLOUD115"
    if "quark.cn" in u:
        return "QUARK"
    if "pan.baidu.com" in u:
        return "BAIDU"
    if "alipan.com" in u or "aliyundrive.com" in u:
        return "ALIYUN"
    if "disk.uc.cn" in u or "drive.uc.cn" in u:
        return "UC"
    if "xunlei.com" in u:
        return "XUNLEI"
    if "123pan.com" in u or "123684.com" in u or "123865.com" in u or "123278.com" in u:
        return "CLOUD123"
    if "yun.139.com" in u or "caiyun.139.com" in u:
        return "CHINA_MOBILE"
    if "cloud.189.cn" in u or "content.21cn.com" in u:
        return "CHINA_TELECOM"
    if "guangyapan.com" in u:
        return "GUANGYA"

    # 从错误信息反推
    msg = str(err_msg or "")
    if "115" in msg:
        return "CLOUD115"
    if "百度" in msg:
        return "BAIDU"
    if "夸克" in msg:
        return "QUARK"
    if "UC" in msg or "uc" in msg:
        return "UC"
    if "阿里" in msg:
        return "ALIYUN"
    if "迅雷" in msg:
        return "XUNLEI"
    if "123" in msg:
        return "CLOUD123"
    if "移动" in msg:
        return "CHINA_MOBILE"
    if "天翼" in msg:
        return "CHINA_TELECOM"
    if "光鸭" in msg:
        return "GUANGYA"

    return ""


CLOUD_SHARE_PREFIXES = {
    "1": "https://www.alipan.com/s/",
    "2": "https://pan.quark.cn/s/",
    "3": "https://drive.uc.cn/s/",
    "4": "https://pan.baidu.com/s/",
    "5": "https://pan.xunlei.com/s/",
    "6": "https://www.123pan.com/s/",
    "7": "https://115.com/s/",
    "8": "https://caiyun.139.com/m/i?",
    "9": "https://cloud.189.cn/t/",
    "11": "https://www.guangyapan.com/s/",
    
    "ALIYUN": "https://www.alipan.com/s/",
    "QUARK": "https://pan.quark.cn/s/",
    "UC": "https://drive.uc.cn/s/",
    "BAIDU": "https://pan.baidu.com/s/",
    "XUNLEI": "https://pan.xunlei.com/s/",
    "CLOUD123": "https://www.123pan.com/s/",
    "CLOUD115": "https://115.com/s/",
    "CHINA_MOBILE": "https://caiyun.139.com/m/i?",
    "CHINA_TELECOM": "https://cloud.189.cn/t/",
    "GUANGYA": "https://www.guangyapan.com/s/",
}

def get_pic_url(item):
    if not item:
        return ""
    if isinstance(item, str):
        pic = item.strip()
    elif isinstance(item, dict):
        pic = item.get("pic") or item.get("cover_url") or item.get("coverUrl") or item.get("sourceCoverUrl") or item.get("cover") or item.get("pic_url") or ""
    else:
        return ""
    if not pic:
        return ""
    pic = pic.strip()
    if pic.startswith("http://") or pic.startswith("https://") or pic.startswith("data:image/"):
        return proxied_image_url(pic)
    if pic.startswith("/api/") or pic.startswith("/posters/"):
        return f"http://127.0.0.1:17654{pic}"
    if pic.startswith("/"):
        return proxied_image_url(f"https://image.tmdb.org/t/p/original{pic}")
    return pic

def proxied_image_url(raw_url):
    if not raw_url:
        return ""
    if "image.tmdb.org" in raw_url and "127.0.0.1:17654/api/image/proxy" not in raw_url:
        import urllib.parse
        return f"http://127.0.0.1:17654/api/image/proxy?url={urllib.parse.quote(raw_url, safe='')}"
    return raw_url

def get_backdrop_url(item):
    if not item:
        return ""
    if isinstance(item, str):
        bg = item.strip()
    elif isinstance(item, dict):
        bg = item.get("backdrop_url") or item.get("backdropPath") or item.get("backdrop_path") or item.get("fanart") or item.get("backdrop") or ""
    else:
        return ""
    if not bg:
        return ""
    bg = bg.strip()
    if bg.startswith("http://") or bg.startswith("https://") or bg.startswith("data:image/"):
        return proxied_image_url(bg)
    if bg.startswith("/api/") or bg.startswith("/posters/"):
        return f"http://127.0.0.1:17654{bg}"
    if not bg.startswith("/"):
        bg = "/" + bg
    return proxied_image_url(f"https://image.tmdb.org/t/p/original{bg}")

def to_share_url(raw_url, pan_name):
    if not raw_url:
        return ""
    raw_url = raw_url.strip()
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    prefix = CLOUD_SHARE_PREFIXES.get(str(pan_name))
    if prefix:
        if pan_name in ["8", "CHINA_MOBILE"] and raw_url.startswith("cid="):
            raw_url = raw_url[4:]
        return prefix + raw_url
    return raw_url

def is_single_file_url(raw_url):
    """判断网盘链接是否明确指向了单个文件 (包含 #fid=, ?fid=, &fid=, file_id=, target_id= 等)"""
    if not raw_url:
        return False
    return bool(re.search(r'(?:[#?&/](?:fid|file_id|target_id)=([^&#\s]+))', raw_url, re.I))

def extract_file_id_from_url(raw_url):
    """从网盘链接中提取单文件 ID (支持包含 Base64 编码、+/= 填充的复杂文件ID)"""
    if not raw_url:
        return ""
    m = re.search(r'(?:[#?&/](?:fid|file_id|target_id)=([^&#\s]+))', raw_url, re.I)
    return urllib.parse.unquote(m.group(1)) if m else ""


# ------------------------------------------------------------------------------
# 3. 核心 VFS 路由分发器 (VfsRouter)
# ------------------------------------------------------------------------------
class VfsRouter:
    """
    核心 VFS 路由分发器，控制目录跳转逻辑与数据流渲染。
    支持分类即时筛选（Container.Update）、网盘多视频懒加载以及全自动外挂字幕匹配和扫码登录 Dialog 整合。
    """
    def __init__(self, adapter, api_client):
        self.adapter = adapter
        self.api_client = api_client

    def route(self, query_string):
        params = dict(urllib.parse.parse_qsl(query_string.lstrip('?')))
        action = params.get('action', 'root')

        if action == 'root':
            self.show_root_menu()
        elif action == 'home':
            self.show_home_menu()
        elif action == 'home_list':
            self.show_home_list(params.get('type'))
        elif action == 'recommend':
            self.show_recommend()
        elif action == 'playlists':
            self.show_playlists()
        elif action == 'playlist_category':
            self.show_playlist_category(params.get('slug'))
        elif action == 'playlist_detail':
            self.show_playlist_detail(params.get('slug'))
        elif action == 'search_menu':
            self.show_search_menu()
        elif action == 'new_search':
            self.start_new_search()
        elif action == 'clear_search':
            self.clear_search_history()
        elif action == 'search':
            self.show_search_results(params.get('q'), int(params.get('page', 1)))
        elif action == 'voice_command':
            self.handle_voice_command(params)
        elif action == 'local_candidates':
            self.show_local_candidates(params)
        elif action == 'play_kodi_item':
            self.play_kodi_item(params)
        elif action == 'category':
            self.show_category(params)
        elif action == 'select_filter':
            self.handle_filter_selection(params)
        elif action == 'detail':
            self.show_video_detail(params.get('id'))
        elif action == 'hls_lines':
            self.show_hls_lines(params)
        elif action == 'line_episodes':
            self.show_line_episodes(params)
        elif action == 'play_hls':
            self.play_hls(params)
        elif action == 'play_all_lines':
            self.play_all_lines(params)
        elif action == 'pan_sources':
            self.show_pan_sources(params)
        elif action == 'cloud_down_sources':
            self.show_cloud_down_sources(params)
        elif action == 'cloud_down_play':
            self.play_cloud_down_item(params)
        elif action == 'cloud_down_tasks':
            self.show_cloud_down_tasks(params)
        elif action == 'cloud_down_task_play':
            self.play_cloud_down_task(params)
        elif action == 'cloud_down_task_menu':
            self.handle_cloud_down_task_menu(params)
        elif action == 'delete_cloud_down_task':
            self.handle_delete_cloud_down_task(params)
        elif action == 'cloud_down_dir_files':
            self.show_cloud_down_dir_files(params)
        elif action == 'cloud_files':
            self.show_cloud_files(params)
        elif action == 'list_files':
            self.show_pan_files(params)
        elif action == 'pan_play':
            self.play_pan_file(params)
        elif action == 'fast_pan_play':
            self.play_fast_pan_file(params)
        elif action == 'play_all_pan_files':
            self.play_all_pan_files(params)
        elif action == 'history':
            self.show_history()
        elif action == 'clear_history':
            self.clear_history()
        elif action == 'my_pans_menu':
            self.show_my_pans_menu()
        elif action == 'pan_detail_menu':
            self.show_pan_detail_menu(params.get('provider'))
        elif action == 'pan_logout':
            self.handle_pan_logout(params.get('provider'))
        elif action == 'pan_concurrency':
            self.handle_pan_concurrency(params.get('provider'))
        elif action == 'pan_chunk_size':
            self.handle_pan_chunk_size(params.get('provider'))
        elif action == 'pan_qps':
            self.handle_pan_qps(params.get('provider'))
        elif action == 'pan115_save_dir':
            self.handle_pan115_save_dir()
        elif action == 'pan_toggle_auto_delete':
            self.handle_pan_toggle_auto_delete(params.get('provider'), params.get('value'))
        elif action == 'pan_toggle_all_auto_delete':
            self.handle_pan_toggle_all_auto_delete(params.get('target'))
        elif action == 'list_user_pan_files':
            self.list_user_pan_files(params)
        elif action == 'play_user_pan':
            self.play_user_pan(params)
        elif action == 'unsupported_file':
            return
        elif action == 'ignore':
            return
        elif action == 'qr_login':
            self.start_qr_login(params.get('provider'))
        elif action == 'manual_login':
            self.start_manual_login(params.get('provider'))
        elif action == 'push_menu':
            self.show_push_menu()
        elif action == 'connect_phone':
            self.start_push_dialog()
        elif action == 'new_push':
            self.start_push_dialog()
        elif action == 'clear_push_history':
            self.clear_push_history()
        elif action == 'pansou_menu':
            self.show_pansou_menu()
        elif action == 'pansou_search':
            self.show_pansou_results(params.get('q'))
        elif action == 'pansou_settings':
            self.show_pansou_settings_page(params)
        elif action == 'pansou_settings_save':
            self.save_pansou_settings(params)
        elif action == 'share_square':
            self.show_share_square(params)
        elif action == 'share_favorites':
            self.show_share_favorites(params)
        elif action in ['share_detail', 'show_share_detail']:
            self.show_share_detail(params)
        elif action == 'share_toggle_favorite':
            self.handle_share_toggle_favorite(params)
        elif action == 'private_libraries':
            self.show_private_libraries()
        elif action == 'my_favorites':
            self.show_my_favorites(params)
        elif action == 'toggle_favorite':
            self.handle_toggle_favorite(params)
        elif action == 'private_library_movies':
            self.show_private_library_movies(params)
        elif action == 'private_movie_links':
            self.show_private_movie_links(params)
        elif action in ('play_private_link', 'private_play_link'):
            self.play_private_link(params)
        elif action == 'sync_private_library':
            self.handle_sync_private_library(params)
        elif action == 'detach_private_library':
            self.handle_detach_private_library(params)
        elif action == 'copy_private_movie':
            self.handle_copy_private_movie(params)
        elif action == 'refresh_private_library_movies':
            self.adapter.execute_builtin("Container.Refresh")
        elif action == 'export_strm_library':
            self.handle_export_strm_library(params)
        elif action == 'private_library_poster_setting':
            self.handle_private_library_poster_setting(params)
        elif action in ('shared_libraries', 'public_shared_libraries'):
            self.show_shared_libraries(params)
        elif action == 'input_import_share_code':
            self.handle_input_import_share_code()
        elif action == 'import_shared_library':
            self.handle_import_shared_library(params)
        else:
            self.show_root_menu()

    def show_root_menu(self):
        """渲染顶级主菜单 (库视图：缩略图 + 背景 + 简介)"""
        self.adapter.set_library_content("videos")

        # 结构: (节点键, 显示名, 简介, 参数, 是否目录, mediatype)
        # mediatype 说明：剧集类（剧集/动漫/综艺/短剧）用 "tvshow"，其余用 "movie"。
        # 皮肤 widget 依赖 "movie"/"tvshow" 才能读到 fanart/plot/poster；
        # 若用 "video" 会导致小部件里背景与简介读取不到。
        nodes = [
            ("connect_phone", "连接手机", "用手机扫码绑定设备，实现手机推送到电视、跨屏进度漫游。", {"action": "connect_phone"}, False, "movie"),
            ("recommend", "最近热门", "全网热播聚合，基于你口味的智能推荐，永远有下一部好看的。", {"action": "recommend"}, True, "movie"),
            ("private_libraries", "我的私有库", "你的私人影音收藏，支持海报墙浏览、Excel 导入与智能同步。", {"action": "private_libraries"}, True, "movie"),
            ("shared_libraries", "共享媒体库", "发现别人分享的优质媒体库，输入分享码即可一键导入本地。", {"action": "shared_libraries"}, True, "movie"),
            ("my_pans", "我的网盘", "天翼云、阿里云盘、夸克、115 等多网盘统一管理，免登直连。", {"action": "my_pans_menu"}, True, "movie"),
            ("search", "视频搜索", "聚合全网资源，输入关键词秒级匹配影片、剧集与网盘链接。", {"action": "search_menu"}, True, "movie"),
            ("history", "播放记录", "跨屏续播与本地历史汇总，上次看到哪一集，一打开就知道。", {"action": "history"}, True, "movie"),
            ("share_square", "分享广场", "看看大家都在收藏什么，热门片单与优质共享库一网打尽。", {"action": "share_square"}, True, "movie"),
            ("push", "推送记录", "手机推送到电视的历史记录，随时回看与继续播放。", {"action": "push_menu"}, True, "movie"),
            ("pansou", "盘搜", "搜索全网网盘资源，聚合多个搜索源，冷门好片也能找到。", {"action": "pansou_menu"}, True, "movie"),
            ("playlists", "专题片单", "编辑精选主题合辑，周星驰、追光动画、奈飞原创等一键直达。", {"action": "playlists"}, True, "movie"),
            ("category_movie", "电影", "院线大片、豆瓣高分与经典老片，按年份/地区/类型自由筛选。", {"action": "category", "typeId": 1, "page": 1}, True, "movie"),
            ("category_tv", "剧集", "热播剧场全集连播，断点续播、自动连播，追剧更轻松。", {"action": "category", "typeId": 2, "page": 1}, True, "tvshow"),
            ("category_anime", "动漫", "国漫日漫全季收藏，新番同步更新，一次看个够。", {"action": "category", "typeId": 3, "page": 1}, True, "tvshow"),
            ("category_variety", "综艺", "真人秀、脱口秀、音综竞演，下饭解压的最佳陪伴。", {"action": "category", "typeId": 4, "page": 1}, True, "tvshow"),
            ("category_doc", "纪录", "人文历史与自然地理纪录片，看见真实世界的广阔与深刻。", {"action": "category", "typeId": 5, "page": 1}, True, "movie"),
            ("category_short", "短剧", "爽点密集、节奏飞快，一两分钟一集，追更根本停不下来。", {"action": "category", "typeId": 7, "page": 1}, True, "tvshow"),
        ]
        for key, name, plot, params, is_folder, mediatype in nodes:
            self.adapter.add_library_item(name, params, key, plot=plot, is_folder=is_folder,
                                          mediatype=mediatype)

        self.adapter.end_of_directory()

    def show_home_menu(self):
        """首页二级菜单版块分类 (库视图)"""
        self.adapter.set_library_content("videos")
        # 结构: (节点键, 显示名, 简介, 参数, mediatype)
        # 剧集类版块使用 "tvshow"，电影类版块使用 "movie"，以便皮肤 widget 正确读取背景与简介。
        nodes = [
            ("recommend", "个性化推荐", "根据你的观看习惯定制推荐，越用越懂你。", {"action": "recommend"}, "movie"),
            ("playlists", "精选轮播", "编辑精选的轮播内容，打开就有惊喜。", {"action": "home_list", "type": "banner"}, "movie"),
            ("category_movie", "热播电影", "正在热映与近期高分电影聚合。", {"action": "home_list", "type": "movie"}, "movie"),
            ("category_tv", "热播剧集", "当下最火的剧集，一集接一集停不下来。", {"action": "home_list", "type": "tv"}, "tvshow"),
            ("category_anime", "热播动漫", "新番与热门动画同步更新。", {"action": "home_list", "type": "anime"}, "tvshow"),
            ("category_variety", "热播综艺", "正在热播的综艺节目精选。", {"action": "home_list", "type": "variety"}, "tvshow"),
            ("category_doc", "热播纪录", "口碑纪录片精选合集。", {"action": "home_list", "type": "documentary"}, "movie"),
            ("category_short", "热播短剧", "爽感十足的短剧精选。", {"action": "home_list", "type": "short"}, "tvshow"),
        ]
        for key, name, plot, params, mediatype in nodes:
            self.adapter.add_library_item(name, params, key, plot=plot, is_folder=True,
                                          mediatype=mediatype)
        self.adapter.end_of_directory()

    def show_home_list(self, section_type):
        """渲染首页具体频道视频列表 (库视图)"""
        self.adapter.set_library_content("videos")
        data = self.api_client.get_home_data()
        field_map = {
            "banner": "bannerVideos",
            "movie": "movieVideos",
            "tv": "tvVideos",
            "anime": "animeVideos",
            "variety": "varietyVideos",
            "documentary": "documentaryVideos",
            "short": "shortVideos"
        }
        field = field_map.get(section_type, "movieVideos")
        videos = data.get(field) or []
        # 剧集形态的版块使用 tvshow，其余按 default_mediatype 推导（电影/纪录等为 movie）
        list_mediatype = "tvshow" if section_type in ("tv", "anime", "variety", "short") else "movie"
        for v in videos:
            self._render_video_item(v, default_mediatype=list_mediatype)
        self.adapter.end_of_directory()

    def show_recommend(self):
        """渲染个性化推荐 (库视图)"""
        self.adapter.set_library_content("videos")
        videos = self.api_client.get_recommendations()
        for v in videos:
            self._render_video_item(v, default_mediatype="movie")
        self.adapter.end_of_directory()

    def show_playlists(self):
        """渲染片单分类 (库视图)"""
        self.adapter.set_library_content("videos")
        categories = self.api_client.get_playlist_categories()
        for cat in categories:
            name = cat.get("name")
            desc = cat.get("description") or cat.get("intro") or f"精选「{name}」主题片单，发现更多好内容。"
            self.adapter.add_library_item(
                name,
                {"action": "playlist_category", "slug": cat.get("slug")},
                "playlists",
                plot=desc,
                is_folder=True,
                icon=get_pic_url(cat.get("coverUrl") or cat.get("cover_url") or ""),
            )
        self.adapter.end_of_directory()

    def show_playlist_category(self, slug):
        """渲染特定分类下的主题片单列表 (库视图)"""
        self.adapter.set_library_content("videos")
        categories = self.api_client.get_playlist_categories()
        matched = next((cat for cat in categories if cat.get("slug") == slug), None)
        if matched:
            for pl in matched.get("playlists", []):
                title = pl.get("title")
                count = pl.get("itemCount")
                label = f"{title} ({count}部)" if count is not None else title
                plot = pl.get("description") or pl.get("intro") or f"共 {count or '多'} 部影片的主题片单，点击查看完整内容。"
                self.adapter.add_library_item(
                    label,
                    {"action": "playlist_detail", "slug": pl.get("slug")},
                    "playlists",
                    plot=plot,
                    is_folder=True,
                    icon=get_pic_url(pl.get("coverUrl")),
                )
        self.adapter.end_of_directory()

    def show_playlist_detail(self, slug):
        """渲染具体片单内的视频项 (库视图)"""
        self.adapter.set_library_content("videos")
        detail = self.api_client.get_playlist_detail(slug)
        items = detail.get("items", [])
        for item in items:
            vod_info_id = item.get("vodInfoId")
            if vod_info_id:
                director = item.get('director') or '未知'
                starring = item.get('starring') or '未知'
                plot = f"导演: {director}\n主演: {starring}"
                info = {
                    "plot": plot,
                    "title": item.get("title"),
                    "genre": item.get("type") or item.get("genre"),
                    "year": item.get("year"),
                }
                if item.get("remark"):
                    info["plot"] = f"{plot}\n{item.get('remark')}"
                self.adapter.add_directory_item(
                    item.get("title"),
                    {"action": "detail", "id": vod_info_id},
                    is_folder=True,
                    icon=get_pic_url(item.get("coverUrl") or item.get("sourceCoverUrl")),
                    fanart=get_backdrop_url(item),
                    info=info,
                    art={
                        "thumb": get_pic_url(item.get("coverUrl") or item.get("sourceCoverUrl")),
                        "poster": get_pic_url(item.get("coverUrl") or item.get("sourceCoverUrl")),
                        "icon": get_pic_url(item.get("coverUrl") or item.get("sourceCoverUrl")),
                        "fanart": get_backdrop_url(item),
                    }
                )
        self.adapter.end_of_directory()

    def show_search_menu(self):
        """渲染搜索主菜单 (库视图)"""
        self.adapter.set_library_content("videos")
        self.adapter.add_library_item(
            "新建搜索...",
            {"action": "new_search"},
            "search_menu",
            plot="输入关键词，聚合搜索全网影视资源与网盘链接。",
            is_folder=False,
        )

        # 加载并渲染历史搜索记录
        profile_dir = self.adapter.get_profile_path()
        history_mgr = SearchHistoryManager(profile_dir)
        history = history_mgr.load_history()

        if history:
            self.adapter.add_library_item(
                "清除搜索历史记录",
                {"action": "clear_search"},
                "search_menu",
                plot="一键清空全部搜索历史。",
                is_folder=False,
            )
            for q in history:
                self.adapter.add_library_item(
                    f"历史: {q}",
                    {"action": "search", "q": q, "page": 1},
                    "search_menu",
                    plot=f"重新搜索「{q}」并查看最新结果。",
                    is_folder=True,
                )

        self.adapter.end_of_directory()

    def clear_search_history(self):
        """清除搜索记录"""
        profile_dir = self.adapter.get_profile_path()
        history_mgr = SearchHistoryManager(profile_dir)
        history_mgr.clear_history()
        self.adapter.show_notification("搜索历史", "已清除搜索记录")
        self.adapter.refresh_container()

    def handle_voice_command(self, params):
        """处理外部遥控器/麦克风/按键直调的语音控制指令 (支持播控、关键词映射与三级搜片起播)"""
        query = (params.get("query") or params.get("q") or "").strip()
        if not query:
            # 遥控器实体按键未带参数时，调出 Kodi 键盘/输入法供输入或听写
            if getattr(self.adapter, "xbmc", None):
                keyboard = self.adapter.xbmc.Keyboard("", "语音 / 文字搜片指令 (例如: 播放庆余年)")
                keyboard.doModal()
                if keyboard.isConfirmed():
                    query = keyboard.getText().strip()
            elif getattr(self.adapter, "xbmcgui", None):
                d = self.adapter.xbmcgui.Dialog()
                query = d.input("语音 / 文字搜片指令 (例如: 播放庆余年)", type=self.adapter.xbmcgui.INPUT_ALPHANUM).strip()

        if not query:
            return

        try:
            res = self.api_client.send_voice_command(query)
            if res and res.get("success"):
                msg = res.get("message") or res.get("tts") or f"已执行: {query}"
                self.adapter.show_notification("语音指令", self._clean_title(msg))
            else:
                err = (res and res.get("error")) or "未能识别该指令"
                self.adapter.show_notification("语音指令", self._clean_title(err), is_error=True)
        except Exception as e:
            self.adapter.show_notification("语音指令", "请求服务失败", is_error=True)

    def start_new_search(self):
        """新建搜索交互输入"""
        if self.adapter.xbmc:
            keyboard = self.adapter.xbmc.Keyboard("", "请输入搜索关键字")
            keyboard.doModal()
            if keyboard.isConfirmed():
                query = keyboard.getText()
                if query:
                    search_params = {"action": "search", "q": query, "page": 1}
                    self.adapter.update_container(search_params, replace=False)

    def show_search_results(self, query, page=1):
        """请求并渲染搜索结果及分页 (库视图)"""
        self.adapter.set_library_content("videos")
        if page == 1 and query:
            profile_dir = self.adapter.get_profile_path()
            history_mgr = SearchHistoryManager(profile_dir)
            history_mgr.add_query(query)

        data = self.api_client.search_videos(query, page=page)
        videos = data.get("items") or []
        pagination = data.get("pagination") or {}

        for v in videos:
            # 搜索结果混杂电影与剧集，交由 _render_video_item 依接口字段自动判定；
            # 判定不出时按 movie 兜底（皮肤 widget 需要 movie/tvshow 才能读到背景与简介）。
            self._render_video_item(v, default_mediatype="movie")

        current_page = pagination.get("page", 1)
        total_pages = pagination.get("totalPages", 1)
        if current_page < total_pages:
            self.adapter.add_library_item(
                "下一页 >>",
                {"action": "search", "q": query, "page": current_page + 1},
                "search_menu",
                plot=f"继续浏览「{query}」的第 {current_page + 1} 页结果。",
                is_folder=True,
            )
        self.adapter.end_of_directory()

    def show_local_candidates(self, params):
        """展示本地库多候选匹配条目供用户遥控器选择 (库视图)"""
        self.adapter.set_library_content("movies")
        title = self._clean_title(params.get('title', '搜索候选'))
        raw_data = params.get('data', '[]')

        candidates = []
        try:
            candidates = json.loads(raw_data)
        except Exception as e:
            self.adapter.log(f"解析本地候选条目失败: {e}", "warning")

        if not candidates:
            self.adapter.add_directory_item(
                "未找到候选影片",
                {"action": "ignore"},
                is_folder=False
            )
            self.adapter.end_of_directory()
            return

        for item in candidates:
            c_type = item.get("type", "")
            c_id = item.get("id")
            c_title = self._clean_title(item.get("title", ""))
            c_year = str(item.get("year") or "").strip()
            c_cover = item.get("cover") or ""
            c_backdrop = item.get("backdrop") or ""
            c_plot = item.get("plot") or ""
            c_resume = float(item.get("resume_seconds") or 0.0)

            tag = ""
            if c_type == "kodi_movie":
                tag = "[本地电影]"
            elif c_type == "kodi_tvshow":
                tag = "[本地剧集]"
            elif c_type == "private_movie":
                tag = "[私有电影]"
            elif c_type == "private_tvshow":
                tag = "[私有剧集]"

            display_title = c_title
            if c_year:
                display_title += f" ({c_year})"
            if tag:
                display_title += f" {tag}"

            if c_resume > 0:
                rm, rs = divmod(int(c_resume), 60)
                if rm >= 60:
                    rh, rm = divmod(rm, 60)
                    t_str = f"{rh:02d}:{rm:02d}:{rs:02d}"
                else:
                    t_str = f"{rm:02d}:{rs:02d}"
                display_title += f" [看至 {t_str}]"

            if c_type in ("kodi_movie", "kodi_tvshow"):
                route_params = {
                    "action": "play_kodi_item",
                    "item_type": "movie" if c_type == "kodi_movie" else "tvshow",
                    "id": c_id,
                    "title": c_title,
                }
                self.adapter.add_library_item(
                    display_title,
                    route_params,
                    node_key="recommend",
                    plot=c_plot or f"来自 Kodi 原生媒体库的《{c_title}》，点击立即起播。",
                    is_folder=False,
                    icon=c_cover,
                    fanart=c_backdrop,
                    mediatype="movie" if c_type == "kodi_movie" else "tvshow",
                )
            elif c_type in ("private_movie", "private_tvshow"):
                route_params = {
                    "action": "private_movie_links",
                    "movie_id": c_id,
                    "title": c_title,
                    "year": c_year,
                    "is_tv": "1" if c_type == "private_tvshow" else "0"
                }
                self.adapter.add_library_item(
                    display_title,
                    route_params,
                    node_key="private_libraries",
                    plot=c_plot or f"来自私有媒体库的《{c_title}》，点击查看选集与播放源。",
                    is_folder=True,
                    icon=c_cover,
                    fanart=c_backdrop,
                    mediatype="movie" if c_type == "private_movie" else "tvshow",
                )

        self.adapter.end_of_directory()

    def play_kodi_item(self, params):
        """播放 Kodi 本地视频库条目 (电影直接播放，剧集智能定位断点分集)"""
        item_type = params.get("item_type", "movie")
        raw_id = params.get("id")
        try:
            item_id = int(raw_id)
        except (ValueError, TypeError):
            item_id = raw_id

        if item_type == "movie":
            kodi_jsonrpc("Player.Open", {
                "item": {"movieid": item_id},
                "options": {"resume": True}
            })
            return

        if item_type == "tvshow":
            ep_res = kodi_jsonrpc("VideoLibrary.GetEpisodes", {
                "tvshowid": item_id,
                "properties": ["episode", "season", "file", "resume", "playcount", "lastplayed"]
            })
            selected_ep_id = None
            if ep_res and isinstance(ep_res, dict) and "result" in ep_res:
                episodes = ep_res["result"].get("episodes") or []
                for ep in episodes:
                    resume_info = ep.get("resume") or {}
                    if resume_info.get("position", 0) > 0:
                        selected_ep_id = ep.get("episodeid")
                        break
                if not selected_ep_id and episodes:
                    played_eps = [ep for ep in episodes if ep.get("lastplayed") or ep.get("playcount", 0) > 0]
                    if played_eps:
                        played_eps.sort(key=lambda x: str(x.get("lastplayed", "")), reverse=True)
                        most_recent = played_eps[0]
                        next_ep_num = most_recent.get("episode", 0) + 1
                        for ep in episodes:
                            if ep.get("episode") == next_ep_num:
                                selected_ep_id = ep.get("episodeid")
                                break
                        if not selected_ep_id:
                            selected_ep_id = most_recent.get("episodeid")
                if not selected_ep_id and episodes:
                    selected_ep_id = episodes[0].get("episodeid")

            if selected_ep_id:
                kodi_jsonrpc("Player.Open", {
                    "item": {"episodeid": selected_ep_id},
                    "options": {"resume": True}
                })
            else:
                self.adapter.execute_builtin(f'ActivateWindow(Videos, "videodb://tvshows/titles/{item_id}/")')

    # --------------------------------------------------------------------------
    # 4. 分类即时筛选功能整合
    # --------------------------------------------------------------------------
    def fetch_tags(self):
        """获取视频标签，优先使用 TTL 缓存"""
        profile_dir = self.adapter.get_profile_path()
        cache_manager = TagsCacheManager(profile_dir)
        cached = cache_manager.get_cached_tags()
        if cached is not None:
            return cached

        tags = []
        try:
            tags = self.api_client.get_tags()
        except Exception as e:
            self.adapter.log(f"获取标签列表失败: {str(e)}", "warning")

        if tags:
            cache_manager.save_tags(tags)
        return tags

    def show_category(self, params):
        """渲染分类视频目录并固定在第一页头部展示控制筛选项与筛选结果数量 (库视图)"""
        self.adapter.set_library_content("videos")
        type_id = int(params.get('typeId', 1))
        year = params.get('year') or None
        area = params.get('area') or None
        tag_id = int(params.get('tagId', 0))
        genre = params.get('genre') or None
        page = int(params.get('page', 1))

        # 1. 优先获取数据，以取得 pagination.total 数量
        data = self.api_client.get_category_videos(type_id, year, area, tag_id, page, page_size=22, genre=genre)
        videos = data.get("items") or []
        pagination = data.get("pagination") or {}
        total = pagination.get("total", 0)

        # 2. 如果是第一页，在最前面固定展示筛选条件
        if page == 1:
            # 2.1 标签匹配处理，计算当前选中 tag_label
            tags = self.fetch_tags()
            tag_label = "全部"
            if tag_id > 0:
                for t in tags:
                     tid = t.get("tagId") or t.get("id")
                     if tid is not None and safe_int(tid) == tag_id:
                         tag_label = t.get("tagName") or t.get("name")
                         break

            year_label = year if year else "全部"
            area_label = area if area else "全部"
            genre_label = genre if genre else "全部"

            # 2.3 年份、地区、类型、标签各自的筛选控制按钮 (年份->地区->类型->标签)
            self.adapter.add_library_item(
                f"年份: {year_label} (点击修改)",
                {"action": "select_filter", "typeId": type_id, "filter_type": "year", "year": year or "", "area": area or "", "tagId": tag_id, "genre": genre or ""},
                "filter",
                plot="按出品年份筛选影片，选择任意年份查看该年片单。",
                is_folder=False,
            )
            self.adapter.add_library_item(
                f"地区: {area_label} (点击修改)",
                {"action": "select_filter", "typeId": type_id, "filter_type": "area", "year": year or "", "area": area or "", "tagId": tag_id, "genre": genre or ""},
                "filter",
                plot="按国家和地区筛选影片，快速定位想看的语种与风格。",
                is_folder=False,
            )
            self.adapter.add_library_item(
                f"类型: {genre_label} (点击修改)",
                {"action": "select_filter", "typeId": type_id, "filter_type": "genre", "year": year or "", "area": area or "", "tagId": tag_id, "genre": genre or ""},
                "filter",
                plot="按影片类型筛选，喜剧、动作、科幻、悬疑随心切换。",
                is_folder=False,
            )
            self.adapter.add_library_item(
                f"标签: {tag_label} (点击修改)",
                {"action": "select_filter", "typeId": type_id, "filter_type": "tag", "year": year or "", "area": area or "", "tagId": tag_id, "genre": genre or ""},
                "filter",
                plot="按平台标签筛选，快速锁定特定来源与题材的影片。",
                is_folder=False,
            )

            # 2.4 重置筛选按钮
            if year or area or tag_id > 0 or genre:
                self.adapter.add_library_item(
                    "重置当前所有筛选条件",
                    {"action": "category", "typeId": type_id, "page": 1},
                    "filter",
                    plot="清除全部筛选条件，重新浏览完整片库。",
                    is_folder=True,
                )

            self.adapter.add_library_item(
                "返回主页",
                {"action": "root"},
                "root",
                plot="回到巨库首页，浏览其他版块。",
                is_folder=True,
            )

        # 3. 追加常规视频列表
        # typeId: 1=电影 2=剧集 3=动漫 4=综艺 5=纪录 7=短剧
        # 除电影(1)与纪录(5)外，其余分类均为剧集形态，使用 tvshow 便于皮肤 widget 读取背景与简介。
        list_mediatype = "movie" if type_id in (1, 5) else "tvshow"
        for v in videos:
            self._render_video_item(v, default_mediatype=list_mediatype)

        # 4. 分页处理
        current_page = pagination.get("page", 1)
        total_pages = pagination.get("totalPages", 1)
        if current_page < total_pages:
            self.adapter.add_library_item(
                "下一页 >>",
                {"action": "category", "typeId": type_id, "year": year or "", "area": area or "", "tagId": tag_id, "genre": genre or "", "page": current_page + 1},
                "category_movie" if type_id == 1 else "category_tv",
                plot=f"继续浏览第 {current_page + 1} 页内容。",
                is_folder=True,
            )
        self.adapter.end_of_directory()

    def handle_filter_selection(self, params):
        """处理点击控制筛选项时的对话框选择和 Container 重定向"""
        type_id = int(params.get('typeId', 1))
        filter_type = params.get('filter_type')
        current_year = params.get('year') or None
        current_area = params.get('area') or None
        current_tag_id = int(params.get('tagId', 0))
        current_genre = params.get('genre') or None

        new_year = current_year
        new_area = current_area
        new_tag_id = current_tag_id
        new_genre = current_genre

        if filter_type == 'genre':
            default_idx = GENRES.index(current_genre) if current_genre in GENRES else 0
            idx = self.adapter.show_select_dialog("选择类型", GENRES, default_idx)
            if idx >= 0:
                new_genre = GENRE_VALUES[idx]

        elif filter_type == 'year':
            default_idx = YEARS.index(current_year) if current_year in YEARS else 0
            idx = self.adapter.show_select_dialog("选择年份", YEARS, default_idx)
            if idx >= 0:
                new_year = YEAR_VALUES[idx]

        elif filter_type == 'area':
            default_idx = AREAS.index(current_area) if current_area in AREAS else 0
            idx = self.adapter.show_select_dialog("选择地区", AREAS, default_idx)
            if idx >= 0:
                new_area = AREA_VALUES[idx]

        elif filter_type == 'tag':
            tags = self.fetch_tags()
            tags_display = ["全部"] + [(t.get("tagName") or t.get("name") or "") for t in tags]
            tags_values = [0] + [safe_int(t.get("tagId") or t.get("id")) for t in tags]

            default_idx = 0
            if current_tag_id > 0 and current_tag_id in tags_values:
                default_idx = tags_values.index(current_tag_id)

            idx = self.adapter.show_select_dialog("选择标签", tags_display, default_idx)
            if idx >= 0:
                new_tag_id = tags_values[idx]

        new_params = {
            "action": "category",
            "typeId": type_id,
            "year": new_year or "",
            "area": new_area or "",
            "tagId": new_tag_id,
            "genre": new_genre or "",
            "page": 1
        }
        self.adapter.update_container(new_params, replace=True)

    # --------------------------------------------------------------------------
    # 5. 网盘剧集多文件懒加载与播放整合
    # --------------------------------------------------------------------------
    def show_video_detail(self, video_id):
        """渲染播放源类型分组菜单（类似 Android 端的 HLS/网盘分组）(库视图)"""
        self.adapter.set_library_content("videos")
        detail = self.api_client.get_video_detail(video_id)
        if not detail:
            self.adapter.end_of_directory()
            return

        play_list_by_line = detail.get("playListByLine") or {}
        pan_list = detail.get("panList") or {}
        vod_title = detail.get("title") or ""
        pic = get_pic_url(detail)
        fanart = get_backdrop_url(detail)
        type_id = detail.get("typeId") or detail.get("type_id")
        # 详情页播放源分组的媒体类型：剧集形态用 tvshow，电影用 movie，
        # 便于皮肤 widget 正确映射 fanart/plot/poster。
        detail_mediatype = "tvshow" if str(type_id) in ("2", "3", "4", "7") else "movie"
        video_plot = detail.get("content") or detail.get("summary") or ""

        # HLS 源分组
        lib_enabled = self.adapter.library_view_enabled() if hasattr(self.adapter, "library_view_enabled") else True
        if play_list_by_line:
            total_lines = len(play_list_by_line)
            hls_kw = {"is_folder": True, "pic": pic, "fanart": fanart}
            if lib_enabled:
                hls_kw["info"] = {"title": f"{vod_title} · HLS", "plot": video_plot or f"在线 HLS 播放源，共 {total_lines} 条线路。", "mediatype": detail_mediatype}
                if pic:
                    hls_kw["art"] = {"poster": pic, "thumb": pic, "icon": pic, "fanart": fanart, "landscape": fanart or pic}
            self.adapter.add_directory_item(
                f"HLS ({total_lines})",
                {"action": "hls_lines", "id": video_id, "vod_title": vod_title, "type_id": type_id, "pic": pic, "fanart": fanart},
                **hls_kw
            )

        status_data = self.api_client.get_pan_status() or {}
        pan_order = self.api_client.get_pan_order()
        if not isinstance(pan_order, list):
            pan_order = ["7", "4", "2", "3", "11", "6", "9", "8", "5", "1", "10"]

        def get_sort_key(item):
            pan_key, _ = item
            cloud_id = PAN_ALIAS_TO_ID.get(str(pan_key), str(pan_key))
            try:
                order_idx = pan_order.index(cloud_id)
            except Exception:
                order_idx = 999
            return order_idx

        sorted_pan_list = sorted(pan_list.items(), key=get_sort_key)

        # 网盘源按 provider 分组
        for pan_key, items in sorted_pan_list:
            count = len(items)
            display_name = CLOUD_PROVIDER_NAMES.get(str(pan_key), f"网盘{pan_key}")
            p_status = status_data.get(str(pan_key)) or {}
            logged_in = p_status.get("logged_in", False)
            login_hint = "已登录，可直接播放" if logged_in else "未登录，播放时可能需要扫码授权"
            pan_kw = {"is_folder": True, "pic": pic, "fanart": fanart}
            if lib_enabled:
                pan_kw["info"] = {"title": f"{vod_title} · {display_name}", "plot": f"{display_name} 资源共 {count} 条，{login_hint}。", "mediatype": detail_mediatype}
                if pic:
                    pan_kw["art"] = {"poster": pic, "thumb": pic, "icon": pic, "fanart": fanart, "landscape": fanart or pic}
            self.adapter.add_directory_item(
                f"{display_name} ({count})",
                {"action": "pan_sources", "id": video_id, "pan_name": pan_key, "vod_title": vod_title, "type_id": type_id, "pic": pic, "fanart": fanart},
                **pan_kw
            )
        # 磁力和ED2K链接 (ed2k/magnet 离线秒播) 源分组
        down_list = detail.get("downList") or []
        if down_list:
            total_downs = len(down_list)
            down_kw = {"is_folder": True, "pic": pic, "fanart": fanart}
            if lib_enabled:
                down_kw["info"] = {"title": f"{vod_title} · 磁力/ED2K", "plot": f"磁力与电驴资源共 {total_downs} 条，可用云端离线下载后秒播。", "mediatype": detail_mediatype}
                if pic:
                    down_kw["art"] = {"poster": pic, "thumb": pic, "icon": pic, "fanart": fanart, "landscape": fanart or pic}
            self.adapter.add_directory_item(
                f"磁力和ED2K链接 ({total_downs})",
                {"action": "cloud_down_sources", "id": video_id, "vod_title": vod_title, "type_id": type_id, "pic": pic, "fanart": fanart},
                **down_kw
            )

        if not play_list_by_line and not pan_list and not down_list:
            self.adapter.add_directory_item("暂无播放源", {"action": "root"}, is_folder=False)

        self.adapter.end_of_directory()

    def show_hls_lines(self, params):
        """渲染 HLS 线路列表"""
        video_id = params.get("id")
        vod_title = params.get("vod_title") or ""
        type_id = params.get("type_id")
        detail = self.api_client.get_video_detail(video_id)
        if not detail:
            self.adapter.end_of_directory()
            return

        pic = params.get("pic") or get_pic_url(detail)
        fanart = params.get("fanart") or get_backdrop_url(detail)

        if not type_id and detail:
            type_id = detail.get("typeId") or detail.get("type_id")

        play_list_by_line = detail.get("playListByLine") or {}
        for line_name, items in play_list_by_line.items():
            display_line_name = line_name
            if not display_line_name.startswith("线路"):
                display_line_name = f"线路{display_line_name}"
            label = f"{display_line_name} (共 {len(items)} 集)"
            self.adapter.add_directory_item(
                label,
                {"action": "line_episodes", "id": video_id, "line": line_name, "vod_title": vod_title or detail.get("title") or "", "type_id": type_id, "pic": pic, "fanart": fanart},
                is_folder=True,
                pic=pic,
                fanart=fanart
            )
        self.adapter.end_of_directory()

    def show_pan_sources(self, params):
        """渲染某个网盘 provider 下的分享链接列表"""
        video_id = params.get("id")
        pan_name = params.get("pan_name")
        vod_title = params.get("vod_title") or ""
        type_id = params.get("type_id")
        detail = self.api_client.get_video_detail(video_id)
        if not detail:
            self.adapter.end_of_directory()
            return

        pic = params.get("pic") or get_pic_url(detail)
        fanart = params.get("fanart") or get_backdrop_url(detail)

        if not type_id and detail:
            type_id = detail.get("typeId") or detail.get("type_id")

        pan_list = detail.get("panList") or {}
        items = pan_list.get(pan_name) or []

        for idx, item in enumerate(items):
            share_url = to_share_url(item.get("url"), pan_name)
            code = item.get("code") or ""
            remark = item.get("remark") or ""
            label = f"链接{idx+1}{remark}"
            self.adapter.add_directory_item(
                label,
                {
                    "action": "list_files", 
                    "url": share_url, 
                    "code": code, 
                    "pan_name": pan_name,
                    "vod_title": vod_title or detail.get("title") or "",
                    "vod_id": video_id,
                    "link_id": item.get("id"),
                    "link_idx": idx + 1,
                    "type_id": type_id,
                    "pic": pic,
                    "fanart": fanart
                },
                is_folder=True,
                pic=pic,
                fanart=fanart
            )
        self.adapter.end_of_directory()

    def show_cloud_down_sources(self, params):
        """渲染影片详情下的 downList 离线下载资源列表"""
        video_id = params.get("id") or params.get("vod_id")
        vod_title = params.get("vod_title") or ""
        type_id = params.get("type_id")
        detail = self.api_client.get_video_detail(video_id)
        if not detail:
            self.adapter.end_of_directory()
            return

        pic = params.get("pic") or get_pic_url(detail)
        fanart = params.get("fanart") or get_backdrop_url(detail)
        if not type_id:
            type_id = detail.get("typeId") or detail.get("type_id")

        down_list = detail.get("downList") or []
        if not down_list:
            self.adapter.add_directory_item("暂无可用云下载资源", {"action": "root"}, is_folder=False)
            self.adapter.end_of_directory()
            return

        # 0. 顶部放置任务列表快捷入口
        self.adapter.add_directory_item(
            "[查看 115 云下载任务列表]",
            {"action": "cloud_down_tasks", "vod_title": vod_title, "vod_id": video_id, "type_id": type_id, "pic": pic, "fanart": fanart},
            is_folder=True,
            pic=pic,
            fanart=fanart
        )

        is_tv_series = safe_int(type_id, 0) == 2
        for idx, item in enumerate(down_list):
            raw_url = item.get("url") or ""
            item_title = item.get("title") or f"资源{idx+1}"
            quality = item.get("quality") or ""
            size_mb = item.get("size") or 0
            size_bytes = 0
            try:
                size_bytes = int(float(size_mb) * 1024 * 1024)
            except Exception:
                pass
            size_label = format_file_size(size_bytes)

            tag_parts = []
            if quality:
                tag_parts.append(f"[{quality}]")
            if size_label:
                tag_parts.append(f"[{size_label}]")
            tag_str = "".join(tag_parts)

            display_name = f"{tag_str} {item_title}" if tag_str else item_title

            self.adapter.add_directory_item(
                display_name,
                {
                    "action": "cloud_down_play",
                    "url": raw_url,
                    "title": item_title,
                    "vod_title": vod_title or detail.get("title") or "",
                    "vod_id": video_id,
                    "type_id": type_id,
                    "pic": pic,
                    "fanart": fanart
                },
                is_folder=is_tv_series,
                is_playable=not is_tv_series,
                pic=pic,
                fanart=fanart
            )
        self.adapter.end_of_directory()

    def _check_login_and_prompt(self, provider, err_msg):
        """检查错误信息是否指示网盘登录失效，若是则弹窗引导用户重新登录"""
        if not err_msg:
            return False
        s = str(err_msg).lower()
        if "登录" in s or "401" in s or "unauthorized" in s or "expired" in s or "token" in s or "超时" in s:
            p_name = CLOUD_PROVIDER_NAMES.get(provider, provider)
            confirm = self.adapter.show_yes_no_dialog(
                f"{p_name} 登录失效",
                f"{p_name} 登录已过期或在其他设备登录。\n是否立即重新扫码登录？"
            )
            if confirm:
                self.start_qr_login(provider)
            return True
        return False

    def play_cloud_down_item(self, params):
        """处理云下载资源点击：检查登录 -> 进度条秒下/轮询 -> 播放或展开选集"""
        url = params.get("url") or ""
        title = params.get("title") or ""
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        type_id = params.get("type_id")
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""

        if not url:
            self.adapter.show_notification("云下载", "下载链接为空", is_error=True)
            return

        # 1. 检查 115 登录状态
        status_data = self.api_client.get_pan_status() or {}
        status_115 = status_data.get("CLOUD115") or {}
        is_logged_in = bool(status_115.get("logged_in") or status_115.get("is_logged_in"))
        if not is_logged_in:
            confirm = self.adapter.show_yes_no_dialog(
                "115 登录提示",
                "云下载播放需要登录 115 网盘。\n是否立即进行扫码登录？"
            )
            if confirm:
                success = self.start_qr_login("CLOUD115")
                if not success:
                    self.adapter.set_resolved_url(False, None)
                    return
            else:
                self.adapter.set_resolved_url(False, None)
                return

        self.adapter.log(f"[CloudDown] 触发云下载: title={title}, vod={vod_title}, url={url[:60]}...", "info")

        # 2. 弹出进度条并提交离线任务
        progress = None
        if self.adapter.xbmcgui:
            try:
                progress = self.adapter.xbmcgui.DialogProgress()
                progress.create("115 云下载", "正在云端匹配与秒下载...")
                progress.update(10, "正在提交 115 离线下载任务...")
            except Exception:
                progress = None

        res = None
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                res = self.api_client.add_115_offline_task(url, title=title, vod_title=vod_title, vod_id=vod_id)
                self.adapter.log(f"[CloudDown] 提交离线任务返回: status={res.get('status')}, cached={res.get('cached')}, hash={res.get('info_hash')}", "info")
                break
            except Exception as ex:
                ex_str = str(ex)
                self.adapter.log(f"[CloudDown] 提交离线任务异常 (attempt {attempt+1}): {ex_str}", "error")
                # 检查是否属于登录失效且为首次尝试
                is_login_err = any(k in ex_str.lower() for k in ["登录", "401", "unauthorized", "expired", "token", "超时", "10010", "10004"])
                if is_login_err and attempt == 0:
                    if progress:
                        try:
                            progress.close()
                        except Exception:
                            pass
                    confirm = self.adapter.show_yes_no_dialog(
                        "115 登录失效",
                        "115 网盘登录已过期。\n是否立即重新扫码登录？"
                    )
                    if confirm:
                        success = self.start_qr_login("CLOUD115")
                        if success:
                            self.adapter.show_notification("扫码登录", "115 登录成功，正在重新提交任务...")
                            time.sleep(0.3)
                            if self.adapter.xbmcgui:
                                try:
                                    progress = self.adapter.xbmcgui.DialogProgress()
                                    progress.create("115 云下载", "正在云端匹配与秒下载...")
                                    progress.update(10, "正在重新提交 115 离线下载任务...")
                                except Exception:
                                    progress = None
                            continue
                    self.adapter.set_resolved_url(False, None)
                    return
                else:
                    if progress:
                        try:
                            progress.close()
                        except Exception:
                            pass
                    self.adapter.show_notification("云下载失败", ex_str, is_error=True)
                    self.adapter.set_resolved_url(False, None)
                    return

        if not res:
            if progress:
                try:
                    progress.close()
                except Exception:
                    pass
            self.adapter.set_resolved_url(False, None)
            return

        # 3. 如果命中有效缓存或秒下载完成
        if res.get("status") == 2 or res.get("cached"):
            self.adapter.log(f"[CloudDown] 命中秒播: file_id={res.get('file_id')}, pick_code={res.get('pick_code')}", "info")
            if progress:
                try:
                    progress.update(100, "云下载完成，正在解析播放...")
                    time.sleep(0.3)
                    progress.close()
                except Exception:
                    pass
            self._handle_completed_cloud_down(res, params)
            return

        # 4. 未秒完成，进入轮询等待（延长至 2 分钟，用户可随时点取消转入后台）
        task_hash = res.get("info_hash") or ""
        max_poll_count = 120
        is_completed = False
        final_res = None

        for i in range(max_poll_count):
            if progress:
                try:
                    if progress.iscanceled():
                        progress.close()
                        self.adapter.log("[CloudDown] 用户取消前台等待，转入后台下载", "info")
                        self.adapter.show_notification("115 云下载", "任务已转入后台下载，可在【云下载任务列表】中查看")
                        self.adapter.set_resolved_url(False, None)
                        return
                except Exception:
                    pass

            time.sleep(1.0)

            try:
                st = self.api_client.get_115_offline_status(info_hash=task_hash, download_url=url)
                if st.get("status") == 2:
                    is_completed = True
                    final_res = st
                    self.adapter.log(f"[CloudDown] 轮询第 {i+1} 秒检测到下载完成", "info")
                    break
                else:
                    if progress:
                        p_val = safe_int(st.get("display_percent") or st.get("percent_done"), 0)
                        rate = safe_int(st.get("rate_download"), 0)
                        speed_str = format_file_size(rate) + "/s" if rate > 0 else ""
                        status_txt = st.get("status_text") or "正在云端下载"
                        msg = f"{status_txt}... {p_val}%" + (f" ({speed_str})" if speed_str else "")
                        estimated_pct = min(95, int(15 + (float(i) / max_poll_count) * 80))
                        progress.update(max(p_val, estimated_pct), msg)
            except Exception as ex:
                self.adapter.log(f"[CloudDown] 轮询任务状态报错: {str(ex)}", "warning")

        if progress:
            try:
                progress.close()
            except Exception:
                pass

        if is_completed and final_res:
            self._handle_completed_cloud_down(final_res, params)
        else:
            self.adapter.log("[CloudDown] 前台等待超时，转入后台下载", "info")
            self.adapter.show_notification("115 云下载", "该资源未命中秒传，正在后台下载中。请稍后在【云下载任务列表】中查看")
            self.adapter.set_resolved_url(False, None)

    def _handle_completed_cloud_down(self, res, params):
        """处理已完成的离线成果：多文件选集 或 单文件起播"""
        is_dir = bool(res.get("is_dir"))
        sub_files = res.get("sub_files") or []
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        type_id = params.get("type_id")
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""
        self.adapter.log(f"[CloudDown] 处理完成离线项: is_dir={is_dir}, sub_files_count={len(sub_files)}", "info")

        # 如果是多视频目录且包含超过 1 个视频文件，直接进入分集选集列表
        if is_dir and len(sub_files) > 1:
            dir_params = {
                "action": "cloud_down_dir_files",
                "file_id": res.get("file_id") or "",
                "vod_title": vod_title,
                "vod_id": vod_id,
                "type_id": type_id,
                "pic": pic,
                "fanart": fanart
            }
            if safe_int(type_id, 0) == 2:
                self.show_cloud_down_dir_files(dir_params)
            else:
                self.adapter.set_resolved_url(False, None)
                self.adapter.update_container(dir_params)
            return

        # 单视频文件直接播放
        target_file_id = res.get("file_id") or ""
        target_pick_code = res.get("pick_code") or ""
        target_file_name = res.get("file_name") or params.get("title") or ""
        if len(sub_files) == 1:
            target_file_id = sub_files[0].get("file_id") or target_file_id
            target_pick_code = sub_files[0].get("pick_code") or target_pick_code
            target_file_name = sub_files[0].get("file_name") or target_file_name

        play_url = res.get("play_url")
        headers = res.get("headers") or {}

        if not play_url and (target_file_id or target_pick_code):
            try:
                play_res = self.api_client.resolve_115_offline_play(file_id=target_file_id, pick_code=target_pick_code)
                play_url = play_res.get("play_url")
                headers = play_res.get("headers") or {}
            except Exception as e:
                self.adapter.log(f"[CloudDown] resolve_115_offline_play 异常: {str(e)}", "error")

        if not play_url and (target_pick_code or target_file_id):
            try:
                play_res = self.api_client.resolve_user_play("CLOUD115", file_id=(target_pick_code or target_file_id), file_name=target_file_name)
                play_url = play_res.get("play_url")
                headers = play_res.get("headers") or {}
            except Exception as e:
                self.adapter.log(f"[CloudDown] resolve_user_play 异常: {str(e)}", "error")

        if not play_url:
            self.adapter.show_notification("播放失败", "未解析到播放直链", is_error=True)
            self.adapter.set_resolved_url(False, None)
            return

        if headers:
            header_parts = []
            for k, v in headers.items():
                header_parts.append(f"{k}={urllib.parse.quote(v, safe='')}")
            play_url = f"{play_url}|{'&'.join(header_parts)}"

        ext_title = params.get("display_title") or params.get("title") or ""
        s_param = params.get("season_number")
        e_param = params.get("episode_number")
        ep_t_param = params.get("episode_title") or ""
        rem_param = params.get("remark") or ""
        is_tv_param = (params.get("is_tv") == "1")

        type_id_param = params.get("type_id")
        if type_id_param == "1":
            is_tv_param = False

        if ext_title and not (type_id_param == "1") and ("：" in ext_title or (s_param and e_param)):
            display_title = ext_title
            s_num = int(s_param) if (s_param and str(s_param).isdigit()) else 1
            e_num = int(e_param) if (e_param and str(e_param).isdigit()) else parse_episode_number(target_file_name)
            is_tv_item = bool(is_tv_param or e_num > 0)
        else:
            display_title, s_num, e_num, is_tv_item = build_play_display_title(
                vod_title=vod_title,
                season_number=s_param,
                episode_number=e_param,
                episode_title=ep_t_param,
                remark=rem_param,
                fallback_title=target_file_name or ext_title,
                is_tv=is_tv_param,
                type_id=type_id_param
            )

        if self.adapter.xbmcgui:
            list_item = self.adapter.xbmcgui.ListItem(label=display_title, path=play_url)
            list_item.setProperty('IsPlayable', 'true')
            art = {}
            if pic:
                art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
            if fanart:
                art['fanart'] = fanart
            if art:
                list_item.setArt(art)

            info = {
                "tvshowtitle": (vod_title or display_title) if is_tv_item else "",
                "title": display_title,
                "mediatype": "episode" if is_tv_item else "movie"
            }
            if is_tv_item and e_num > 0:
                info["episode"] = e_num
                info["season"] = s_num
            resume_time = params.get("resume_time")
            if resume_time and float(resume_time) > 0:
                r_sec = float(resume_time)
                info["resume_time"] = r_sec
                list_item.setProperty('ResumeTime', str(r_sec))
                list_item.setProperty('StartOffset', str(r_sec))
            list_item.setInfo('video', info)

            # 写入播放历史
            if vod_title:
                try:
                    profile_dir = self.adapter.get_profile_path()
                    history_mgr = HistoryManager(profile_dir)
                    play_params = {
                        "action": "cloud_down_play",
                        "url": params.get("url"),
                        "title": display_title,
                        "vod_title": vod_title,
                        "vod_id": vod_id
                    }
                    item_history_name = f"第{s_num}季第{e_num}集" + (f"（{rem_param}）" if rem_param else "") if is_tv_item else (rem_param or target_file_name or params.get("title"))
                    record = {
                        "vod_title": vod_title,
                        "vod_id": vod_id,
                        "item_name": item_history_name,
                        "timestamp": time.time(),
                        "url": self.adapter.build_url(play_params),
                        "pic": pic,
                        "fanart": fanart,
                        "type_id": type_id or (2 if is_tv_item else 1)
                    }
                    history_mgr.add_record(record)
                except Exception as ex:
                    self.adapter.log(f"[CloudDown] 写入播放历史失败: {ex}", "warning")

            self._mark_playback_started(movie_id=params.get("movie_id"), vod_id=vod_id)
            self.adapter.set_resolved_url(True, list_item)

    def show_cloud_down_tasks(self, params):
        """渲染 115 离线下载任务列表（支持分页、删除管理、已完成点击直接播放或展开目录）"""
        status_data = self.api_client.get_pan_status() or {}
        status_115 = status_data.get("CLOUD115") or {}
        is_logged_in = bool(status_115.get("logged_in") or status_115.get("is_logged_in"))

        if not is_logged_in:
            self.adapter.add_directory_item(
                "请先登录 115 网盘",
                {"action": "qr_login", "provider": "CLOUD115"},
                is_folder=False
            )
            self.adapter.end_of_directory()
            return

        page = safe_int(params.get("page"), 1)
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""

        try:
            tasks_data = self.api_client.get_115_offline_tasks(page=page)
        except Exception as ex:
            if not self._check_login_and_prompt("CLOUD115", str(ex)):
                self.adapter.show_notification("获取任务列表失败", str(ex), is_error=True)
            self.adapter.end_of_directory()
            return

        tasks = tasks_data.get("tasks") or []
        if not tasks:
            self.adapter.add_directory_item("暂无云下载任务", {"action": "root"}, is_folder=False)
            self.adapter.end_of_directory()
            return

        for t in tasks:
            t_vod_title = t.get("vod_title") or ""
            t_vod_id = t.get("vod_id") or ""
            t_name = t.get("name") or t.get("url") or "未知任务"

            # 仅当任务自身具备由插件记录的片名时，才在文件名前展示片名
            if t_vod_title and not t_name.startswith(t_vod_title):
                display_name = f"{t_vod_title}：（{t_name}）"
            else:
                display_name = t_name

            t_size_str = format_file_size(t.get("size"))
            t_status = t.get("status")
            t_percent = safe_int(t.get("display_percent") or t.get("percent_done"), 0)
            t_file_id = t.get("file_id") or ""
            t_pick_code = t.get("pick_code") or ""
            t_hash = t.get("info_hash") or ""

            context_menu = [
                ("删除此云下载任务", f"RunPlugin({self.adapter.base_url}?action=delete_cloud_down_task&hash={t_hash})"),
                ("删除任务及源文件", f"RunPlugin({self.adapter.base_url}?action=delete_cloud_down_task&hash={t_hash}&delete_files=1)")
            ]

            if t_status == 2:
                # 已完成
                size_tag = f"[{t_size_str}] " if t_size_str else ""
                cat, ext = get_file_category(t_name)
                del_path = t.get("del_path") or ""
                is_dir_task = bool(t.get("is_dir")) or del_path.endswith("/") or (cat != "video")

                encoded_title = urllib.parse.quote(t_vod_title or display_name)
                browse_url = f"{self.adapter.base_url}?action=cloud_down_dir_files&file_id={t_file_id}&vod_title={encoded_title}"
                task_context_menu = [
                    ("浏览分集/文件列表", f"Container.Update({browse_url})")
                ] + context_menu

                if is_dir_task:
                    label = f"[已完成] [目录] {size_tag}{display_name}"
                    self.adapter.add_directory_item(
                        label,
                        {
                            "action": "cloud_down_dir_files",
                            "file_id": t_file_id,
                            "vod_title": t_vod_title or display_name,
                            "vod_id": t_vod_id,
                            "pic": pic,
                            "fanart": fanart
                        },
                        is_folder=True,
                        is_playable=False,
                        pic=pic,
                        fanart=fanart,
                        context_menu=task_context_menu
                    )
                else:
                    label = f"[已完成] {size_tag}{display_name}"
                    self.adapter.add_directory_item(
                        label,
                        {
                            "action": "cloud_down_task_play",
                            "file_id": t_file_id,
                            "pick_code": t_pick_code,
                            "title": display_name,
                            "vod_title": t_vod_title,
                            "vod_id": t_vod_id,
                            "pic": pic,
                            "fanart": fanart
                        },
                        is_folder=False,
                        is_playable=True,
                        pic=pic,
                        fanart=fanart,
                        context_menu=task_context_menu
                    )
            elif t_status == 0 or t_status == 1:
                # 下载中 / 等待中
                rate = safe_int(t.get("rate_download"), 0)
                speed_str = f" | {format_file_size(rate)}/s" if rate > 0 else ""
                size_tag = f"[{t_size_str}] " if t_size_str else ""
                status_txt = t.get("status_text") or "下载中"
                label = f"[{status_txt} {t_percent}%{speed_str}] {size_tag}{display_name}"
                self.adapter.add_directory_item(
                    label,
                    {
                        "action": "cloud_down_task_menu",
                        "hash": t_hash,
                        "name": display_name,
                        "percent": t_percent,
                        "status_text": status_txt
                    },
                    is_folder=False,
                    pic=pic,
                    fanart=fanart,
                    context_menu=context_menu
                )
            else:
                # 失败
                label = f"[下载失败] {display_name}"
                self.adapter.add_directory_item(
                    label,
                    {
                        "action": "cloud_down_task_menu",
                        "hash": t_hash,
                        "name": display_name,
                        "status_text": "下载失败"
                    },
                    is_folder=False,
                    pic=pic,
                    fanart=fanart,
                    context_menu=context_menu
                )

        page_count = safe_int(tasks_data.get("page_count"), 1)
        if page_count > page:
            self.adapter.add_directory_item(
                f"下一页 (第 {page + 1} / {page_count} 页)",
                {"action": "cloud_down_tasks", "page": page + 1, "vod_title": vod_title, "vod_id": vod_id, "pic": pic, "fanart": fanart},
                is_folder=True,
                pic=pic,
                fanart=fanart
            )

        self.adapter.end_of_directory()

    def play_cloud_down_task(self, params):
        """播放任务列表中已完成的项目（多集展开选集，单集直接播放）"""
        file_id = params.get("file_id") or ""
        pick_code = params.get("pick_code") or ""
        title = params.get("title") or ""
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""

        try:
            res = self.api_client.resolve_115_offline_play(file_id=file_id, pick_code=pick_code)
        except Exception as e:
            if not self._check_login_and_prompt("CLOUD115", str(e)):
                self.adapter.show_notification("解析失败", str(e), is_error=True)
            self.adapter.set_resolved_url(False, None)
            return

        is_dir = bool(res.get("is_dir"))
        sub_files = res.get("sub_files") or []

        if is_dir and len(sub_files) > 1:
            self.adapter.set_resolved_url(False, None)
            dir_params = {
                "action": "cloud_down_dir_files",
                "file_id": file_id,
                "vod_title": vod_title or title,
                "vod_id": vod_id,
                "pic": pic,
                "fanart": fanart
            }
            self.adapter.update_container(dir_params)
            return

        play_url = res.get("play_url")
        headers = res.get("headers") or {}
        target_file_name = res.get("file_name") or title

        if not play_url:
            target_file_id = sub_files[0].get("file_id") if (len(sub_files) == 1 and sub_files[0].get("file_id")) else file_id
            if len(sub_files) == 1:
                target_file_name = sub_files[0].get("file_name") or target_file_name

            try:
                play_res = self.api_client.resolve_user_play("CLOUD115", file_id=target_file_id, file_name=target_file_name)
                play_url = play_res.get("play_url")
                headers = play_res.get("headers") or {}
            except Exception as e:
                if not self._check_login_and_prompt("CLOUD115", str(e)):
                    self.adapter.show_notification("播放解析失败", str(e), is_error=True)
                self.adapter.set_resolved_url(False, None)
                return

        if not play_url:
            self.adapter.show_notification("播放失败", "未解析到播放直链", is_error=True)
            self.adapter.set_resolved_url(False, None)
            return

        if headers:
            header_parts = []
            for k, v in headers.items():
                header_parts.append(f"{k}={urllib.parse.quote(v, safe='')}")
            play_url = f"{play_url}|{'&'.join(header_parts)}"

        ep_num = parse_episode_number(target_file_name)
        display_title = title or target_file_name
        if vod_title:
            if ep_num > 0:
                display_title = f"{vod_title} 第{ep_num:02d}集"
            elif vod_title not in display_title:
                display_title = f"{vod_title} {display_title}"

        if self.adapter.xbmcgui:
            list_item = self.adapter.xbmcgui.ListItem(label=display_title, path=play_url)
            list_item.setProperty('IsPlayable', 'true')
            art = {}
            if pic:
                art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
            if fanart:
                art['fanart'] = fanart
            if art:
                list_item.setArt(art)

            info = {
                "tvshowtitle": vod_title or display_title,
                "title": display_title,
                "mediatype": "episode" if ep_num > 0 else "video"
            }
            if ep_num > 0:
                info["episode"] = ep_num
            list_item.setInfo('video', info)
            self._mark_playback_started(movie_id=params.get("movie_id"), vod_id=vod_id)
            self.adapter.set_resolved_url(True, list_item)

    def handle_cloud_down_task_menu(self, params):
        """点击未完成或失败的离线任务时弹出操作菜单"""
        t_hash = params.get("hash") or ""
        t_name = params.get("name") or "云下载任务"
        status_text = params.get("status_text") or ""
        percent = params.get("percent", 0)

        options = [
            f"状态: {status_text} ({percent}%)",
            "刷新任务列表",
            "删除此云下载任务",
            "删除任务及已下载文件"
        ]

        choice = self.adapter.show_select_dialog(t_name, options)
        if choice == 1:
            self.adapter.update_container({"action": "cloud_down_tasks"}, replace=True)
        elif choice == 2:
            self.api_client.delete_115_offline_tasks(t_hash, delete_files=False)
            self.adapter.show_notification("云下载", "已删除任务")
            self.adapter.update_container({"action": "cloud_down_tasks"}, replace=True)
        elif choice == 3:
            self.api_client.delete_115_offline_tasks(t_hash, delete_files=True)
            self.adapter.show_notification("云下载", "已删除任务及文件")
            self.adapter.update_container({"action": "cloud_down_tasks"}, replace=True)

    def handle_delete_cloud_down_task(self, params):
        """通过上下文菜单直接删除云下载任务"""
        t_hash = params.get("hash") or ""
        delete_files = params.get("delete_files") == "1"
        if not t_hash:
            return
        try:
            self.api_client.delete_115_offline_tasks(t_hash, delete_files=delete_files)
            self.adapter.show_notification("云下载", "已删除任务")
            self.adapter.update_container({"action": "cloud_down_tasks"}, replace=True)
        except Exception as e:
            self.adapter.show_notification("删除失败", str(e), is_error=True)

    def show_cloud_down_dir_files(self, params):
        """渲染离线多视频文件夹下的视频分集选集列表"""
        file_id = params.get("file_id") or ""
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        type_id = params.get("type_id")
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""

        if not file_id:
            self.adapter.end_of_directory()
            return

        # 递归扫描所有子目录下的视频分集
        video_files = []
        def _scan_dir(cid, depth=0):
            if depth > 4:
                return
            try:
                sub_res = self.api_client.get_user_files("CLOUD115", parent_file_id=cid)
                sub_items = sub_res.get("files") or []
                for item in sub_items:
                    if item.get("is_folder"):
                        _scan_dir(item.get("file_id"), depth + 1)
                    else:
                        cat, _ = get_file_category(item.get("file_name", ""))
                        if cat == "video" or safe_int(item.get("size"), 0) > 20 * 1024 * 1024:
                            video_files.append(item)
            except Exception as e:
                if not self._check_login_and_prompt("CLOUD115", str(e)):
                    self.adapter.log(f"[CloudDown] 递归获取子目录失败({cid}): {e}", "warning")

        _scan_dir(file_id, 0)

        if not video_files:
            self.adapter.add_directory_item("目录下无可用视频分集", {"action": "root"}, is_folder=False)
            self.adapter.end_of_directory()
            return

        def _sort_key(item):
            fn = item.get("file_name", "")
            ep = parse_episode_number(fn)
            return (ep if ep > 0 else 999999, fn)
        video_files.sort(key=_sort_key)

        self.adapter.set_content("episodes")

        for f in video_files:
            f_id = f.get("file_id") or ""
            f_name = f.get("file_name") or ""
            f_size = format_file_size(f.get("size"))
            ep_num = parse_episode_number(f_name)

            if vod_title:
                if ep_num > 0:
                    formatted_name = f"{vod_title} 第{ep_num:02d}集"
                elif vod_title not in f_name:
                    formatted_name = f"{vod_title} {f_name}"
                else:
                    formatted_name = f_name
            else:
                formatted_name = f_name

            display_name = f"[{f_size}] {formatted_name}" if f_size else formatted_name

            info = {
                "tvshowtitle": vod_title or formatted_name,
                "title": formatted_name,
                "mediatype": "episode" if ep_num > 0 else "video"
            }
            if ep_num > 0:
                info["episode"] = ep_num

            self.adapter.add_directory_item(
                display_name,
                {
                    "action": "play_user_pan",
                    "provider": "CLOUD115",
                    "file_id": f_id,
                    "file_name": f_name,
                    "title": formatted_name,
                    "vod_title": vod_title,
                    "vod_id": vod_id,
                    "type_id": type_id,
                    "pic": pic,
                    "fanart": fanart
                },
                is_folder=False,
                is_playable=True,
                pic=pic,
                fanart=fanart,
                info=info
            )

        self.adapter.end_of_directory()

    def show_cloud_files(self, params):
        """渲染 cloud_files 表中的视频文件列表（用于 115 秒传播放）"""
        video_id = params.get("id") or params.get("vod_id")
        cloudid = params.get("cloudid", "7")
        vod_title = params.get("vod_title") or ""
        type_id = params.get("type_id")
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""

        detail = None
        if not vod_title or not pic:
            detail = self.api_client.get_video_detail(video_id)
            if detail:
                if not vod_title:
                    vod_title = detail.get("title") or ""
                if not pic:
                    pic = get_pic_url(detail)
                if not fanart:
                    fanart = get_backdrop_url(detail)
                if not type_id:
                    type_id = detail.get("typeId") or detail.get("type_id")

        status_data = self.api_client.get_pan_status() or {}
        status_115 = status_data.get("CLOUD115") or {}
        is_logged_in = bool(status_115.get("logged_in") or status_115.get("is_logged_in"))
        if not is_logged_in:
            self.adapter.add_directory_item(
                "请先登录 115 网盘（用于秒传保存与播放）",
                {"action": "qr_login", "provider": "CLOUD115"},
                is_folder=False
            )
            self.adapter.end_of_directory()
            return

        files = self.api_client.get_cloud_files(video_id, cloudid=cloudid)
        if not files:
            self.adapter.add_directory_item("暂无可用秒传视频文件", {"action": "root"}, is_folder=False)
            self.adapter.end_of_directory()
            return

        self.adapter.set_content("episodes")

        for f in files:
            file_name = f.get("file_name") or ""
            file_size = f.get("size") or 0
            sha = f.get("sha") or ""
            size_label = format_file_size(file_size)
            ep_num = parse_episode_number(file_name)

            if vod_title:
                formatted_name = f"{vod_title}：（{file_name}）"
            else:
                formatted_name = file_name

            display_name = f"[{size_label}]{formatted_name}" if size_label else formatted_name

            info = {
                "tvshowtitle": vod_title or file_name,
                "title": formatted_name,
                "mediatype": "episode" if ep_num > 0 else "video"
            }
            if ep_num > 0:
                info["episode"] = ep_num

            self.adapter.add_directory_item(
                display_name,
                {
                    "action": "fast_pan_play",
                    "provider": "CLOUD115",
                    "file_name": file_name,
                    "file_size": file_size,
                    "sha": sha,
                    "title": formatted_name,
                    "vod_title": vod_title,
                    "vod_id": video_id,
                    "cloudid": cloudid,
                    "type_id": type_id,
                    "pic": pic,
                    "fanart": fanart
                },
                is_folder=False,
                is_playable=True,
                pic=pic,
                fanart=fanart,
                info=info
            )

        self.adapter.end_of_directory()

    def play_fast_pan_file(self, params):
        """通过 115 秒传方式导入并播放视频"""
        provider = params.get("provider", "CLOUD115")
        file_name = params.get("file_name") or ""
        file_size = safe_int(params.get("file_size"), 0)
        sha = params.get("sha") or ""
        title = params.get("title") or file_name
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""

        if not sha:
            self.adapter.show_notification("播放失败", "该文件缺少 SHA-1 秒传指纹", is_error=True)
            return

        try:
            res = self.api_client.resolve_fast_play(provider, file_name, file_size, sha)
        except Exception as e:
            err_msg = str(e)
            if "请先登录" in err_msg or "未登录" in err_msg:
                confirm = self.adapter.show_yes_no_dialog(
                    "登录提示",
                    "秒传播放需要登录 115 网盘。\n是否立即进行扫码登录？"
                )
                if confirm:
                    success = self.start_qr_login("CLOUD115")
                    if success:
                        self.adapter.show_notification("扫码登录", "115 登录成功，正在重新秒传播放...")
                        try:
                            res = self.api_client.resolve_fast_play(provider, file_name, file_size, sha)
                        except Exception as e2:
                            self.adapter.show_notification("秒传失败", str(e2), is_error=True)
                            return
                    else:
                        return
                else:
                    return
            else:
                self.adapter.show_notification("秒传失败", err_msg, is_error=True)
                return

        play_url = res.get("play_url")
        headers = res.get("headers") or {}

        if not play_url:
            self.adapter.log("未解析到秒传播放直链", "error")
            return

        if headers:
            header_parts = []
            for k, v in headers.items():
                header_parts.append(f"{k}={urllib.parse.quote(v, safe='')}")
            play_url = f"{play_url}|{'&'.join(header_parts)}"

        ep_num = parse_episode_number(file_name)
        if vod_title:
            if ep_num > 0:
                display_title = f"{vod_title} 第{ep_num:02d}集"
            elif vod_title not in title:
                display_title = f"{vod_title} {title}"
            else:
                display_title = title
        else:
            display_title = title

        if self.adapter.xbmcgui and self.adapter.xbmcplugin:
            list_item = self.adapter.xbmcgui.ListItem(label=display_title, path=play_url)
            list_item.setProperty('IsPlayable', 'true')

            art = {}
            if pic:
                art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
            if fanart:
                art['fanart'] = fanart
            if art:
                list_item.setArt(art)

            info = {
                "tvshowtitle": vod_title or display_title,
                "title": display_title,
                "mediatype": "episode" if ep_num > 0 else "video"
            }
            if ep_num > 0:
                info["episode"] = ep_num
            list_item.setInfo('video', info)

            self.adapter.set_resolved_url(True, list_item)

            # 保存播放历史
            if vod_title:
                try:
                    profile_dir = self.adapter.get_profile_path()
                    history_mgr = HistoryManager(profile_dir)
                    type_id = params.get("type_id")
                    is_folder = False
                    play_params = {
                        "action": "fast_pan_play",
                        "provider": provider,
                        "file_name": file_name,
                        "file_size": file_size,
                        "sha": sha,
                        "vod_title": vod_title,
                        "vod_id": vod_id
                    }

                    if type_id is not None and str(type_id) != "1":
                        is_folder = True
                        play_params = {
                            "action": "cloud_files",
                            "id": vod_id,
                            "cloudid": params.get("cloudid", "7"),
                            "vod_title": vod_title,
                            "type_id": type_id
                        }

                    record = {
                        "vod_title": vod_title,
                        "vod_id": vod_id,
                        "item_name": file_name or title,
                        "timestamp": time.time(),
                        "is_folder": is_folder,
                        "play_params": play_params
                    }
                    history_mgr.add_record(record)
                except Exception as ex:
                    self.adapter.log(f"保存秒传播放历史失败: {str(ex)}", "warning")

            if self.adapter.xbmc:
                try:
                    self.adapter.xbmc.executebuiltin("Dialog.Close(all, true)")
                except Exception:
                    pass
            self.adapter.xbmcplugin.setResolvedUrl(self.adapter.handle, True, list_item)
        else:
            self.adapter.log(f"Fast Pan Play URL: {play_url}")

    def show_line_episodes(self, params):
        """渲染某条线路下的剧集列表"""
        video_id = params.get("id")
        line_name = params.get("line")
        vod_title = params.get("vod_title") or ""
        type_id = params.get("type_id")
        detail = self.api_client.get_video_detail(video_id)
        if not detail:
            self.adapter.end_of_directory()
            return

        pic = params.get("pic") or get_pic_url(detail)
        fanart = params.get("fanart") or get_backdrop_url(detail)

        if not vod_title and detail:
            vod_title = detail.get("title") or ""

        if not type_id and detail:
            type_id = detail.get("typeId") or detail.get("type_id")

        self.adapter.set_content("episodes")

        play_list_by_line = detail.get("playListByLine") or {}
        episodes = play_list_by_line.get(line_name) or []

        for ep in episodes:
            raw_ep_name = ep.get("name") or f"第 {ep.get('episode', '?')} 集"
            ep_url = ep.get("url") or ""
            ep_num = parse_episode_number(raw_ep_name)
            
            if vod_title:
                if ep_num > 0:
                    full_title = f"{vod_title} 第{ep_num:02d}集"
                elif vod_title not in raw_ep_name:
                    full_title = f"{vod_title} {raw_ep_name}"
                else:
                    full_title = raw_ep_name
            else:
                full_title = raw_ep_name

            info = {
                "tvshowtitle": vod_title or full_title,
                "title": full_title,
                "mediatype": "episode" if ep_num > 0 else "video"
            }
            if ep_num > 0:
                info["episode"] = ep_num

            if ep_url:
                self.adapter.add_directory_item(
                    full_title,
                    {
                        "action": "play_hls", 
                        "url": ep_url, 
                        "title": full_title,
                        "vod_title": vod_title,
                        "vod_id": video_id,
                        "line": line_name,
                        "type_id": type_id,
                        "pic": pic
                    },
                    is_folder=False,
                    is_playable=True,
                    pic=pic,
                    info=info
                )

        if not episodes:
            self.adapter.add_directory_item("暂无可播放剧集", {"action": "root"}, is_folder=False)

        self.adapter.end_of_directory()

    def play_hls(self, params):
        """播放 HLS 线路的视频"""
        play_url = params.get("url") or ""
        title = params.get("title") or ""
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""
        line_name = params.get("line")
        type_id = params.get("type_id")

        if not play_url:
            self.adapter.log("HLS 播放地址为空", "error")
            return

        # 尝试为多集剧集自动填充完整播放列表
        if vod_id and line_name and self.adapter.xbmc and self.adapter.xbmcgui:
            try:
                playlist = self.adapter.xbmc.PlayList(self.adapter.xbmc.PLAYLIST_VIDEO)
                is_from_playlist = params.get("from_playlist") == "1"
                if is_from_playlist:
                    # 已经在连续播放列表中（Kodi 连播或切下一集），跳过播放列表重建，避免破坏内部播放指针
                    pass
                else:
                    detail = self.api_client.get_video_detail(vod_id)
                    if detail:
                        play_list_by_line = detail.get("playListByLine") or {}
                        episodes = play_list_by_line.get(line_name) or []
                        if len(episodes) > 1:
                            # 查找当前播放集在剧集列表中的位置
                            curr_idx = -1
                            for idx, ep in enumerate(episodes):
                                if (ep.get("url") or "") == play_url:
                                    curr_idx = idx
                                    break

                            # 从当前集开始向后构建播放列表：第 0 项为当前集，后续为未播集数
                            # 确保首次起播时，Kodi 连播下一集永远顺位播放
                            start_idx = curr_idx if curr_idx >= 0 else 0
                            remaining_episodes = episodes[start_idx:]

                            playlist.clear()
                            for idx, ep in enumerate(remaining_episodes):
                                raw_ep_name = ep.get("name") or f"第 {ep.get('episode', '?')} 集"
                                ep_url = ep.get("url") or ""
                                if not ep_url:
                                    continue

                                ep_num = parse_episode_number(raw_ep_name)
                                if vod_title:
                                    if ep_num > 0:
                                        full_title = f"{vod_title} 第{ep_num:02d}集"
                                    elif vod_title not in raw_ep_name:
                                        full_title = f"{vod_title} {raw_ep_name}"
                                    else:
                                        full_title = raw_ep_name
                                else:
                                    full_title = raw_ep_name

                                if idx == 0:
                                    target_path = play_url
                                else:
                                    target_path = f"{self.adapter.base_url}?{urllib.parse.urlencode({'action': 'play_hls', 'url': ep_url, 'title': full_title, 'vod_title': vod_title, 'vod_id': vod_id, 'line': line_name, 'type_id': type_id, 'pic': pic, 'fanart': fanart, 'from_playlist': '1'})}"

                                list_item = self.adapter.xbmcgui.ListItem(label=full_title, path=target_path)
                                list_item.setProperty('IsPlayable', 'true')
                                art = {}
                                if pic:
                                    art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
                                if fanart:
                                    art['fanart'] = fanart
                                if art:
                                    list_item.setArt(art)

                                info = {
                                    "tvshowtitle": vod_title or full_title,
                                    "title": full_title,
                                    "mediatype": "episode" if ep_num > 0 else "video"
                                }
                                if ep_num > 0:
                                    info["episode"] = ep_num
                                list_item.setInfo('video', info)

                                playlist.add(target_path, list_item)
            except Exception as ex:
                self.adapter.log(f"自动构建 HLS 播放列表失败: {str(ex)}", "warning")

        if self.adapter.xbmcgui and self.adapter.xbmcplugin:
            ep_num = parse_episode_number(title)
            if vod_title:
                if ep_num > 0:
                    display_title = f"{vod_title} 第{ep_num:02d}集"
                elif vod_title not in title:
                    display_title = f"{vod_title} {title}"
                else:
                    display_title = title
            else:
                display_title = title

            list_item = self.adapter.xbmcgui.ListItem(label=display_title, path=play_url)
            list_item.setProperty('IsPlayable', 'true')

            art = {}
            if pic:
                art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
            if fanart:
                art['fanart'] = fanart
            if art:
                list_item.setArt(art)

            info = {
                "tvshowtitle": vod_title or display_title,
                "title": display_title,
                "mediatype": "episode" if ep_num > 0 else "video"
            }
            if ep_num > 0:
                info["episode"] = ep_num
            resume_time = params.get("resume_time")
            if resume_time and float(resume_time) > 0:
                r_sec = float(resume_time)
                info["resume_time"] = r_sec
                list_item.setProperty('ResumeTime', str(r_sec))
                list_item.setProperty('StartOffset', str(r_sec))
            list_item.setInfo('video', info)

            self.adapter.set_resolved_url(True, list_item)

            # 写入播放历史
            if vod_title:
                try:
                    profile_dir = self.adapter.get_profile_path()
                    history_mgr = HistoryManager(profile_dir)
                    type_id = params.get("type_id")
                    line_name = params.get("line")
                    is_folder = False
                    play_params = {
                        "action": "play_hls",
                        "url": play_url,
                        "title": title,
                        "vod_title": vod_title,
                        "vod_id": vod_id
                    }
                    
                    if type_id is not None and str(type_id) != "1" and line_name:
                        is_folder = True
                        play_params = {
                            "action": "line_episodes",
                            "id": vod_id,
                            "line": line_name,
                            "vod_title": vod_title,
                            "type_id": type_id
                        }

                    record = {
                        "vod_title": vod_title,
                        "vod_id": vod_id,
                        "item_name": title,
                        "timestamp": time.time(),
                        "is_folder": is_folder,
                        "play_params": play_params
                    }
                    history_mgr.add_record(record)
                except Exception as e:
                    self.adapter.log(f"保存HLS播放历史失败: {str(e)}", "warning")

            if self.adapter.xbmc:
                try:
                    self.adapter.xbmc.executebuiltin("Dialog.Close(all, true)")
                except Exception:
                    pass
            self.adapter.xbmcplugin.setResolvedUrl(self.adapter.handle, True, list_item)
        else:
            self.adapter.log(f"HLS Play URL: {play_url}")

    def play_all_lines(self, params):
        """将 HLS 线路全集写入 Kodi 播放列表并顺序播放"""
        video_id = params.get("id")
        line_name = params.get("line")
        vod_title = params.get("vod_title") or ""
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""
        type_id = params.get("type_id")
        detail = self.api_client.get_video_detail(video_id)
        if not detail:
            return

        if not pic:
            pic = get_pic_url(detail)

        if not fanart:
            fanart = get_backdrop_url(detail)

        if not vod_title:
            vod_title = detail.get("title") or ""

        play_list_by_line = detail.get("playListByLine") or {}
        episodes = play_list_by_line.get(line_name) or []

        if self.adapter.xbmcgui and self.adapter.xbmc:
            playlist = self.adapter.xbmc.PlayList(self.adapter.xbmc.PLAYLIST_VIDEO)
            playlist.clear()

            for ep in episodes:
                raw_ep_name = ep.get("name") or f"第 {ep.get('episode', '?')} 集"
                ep_url = ep.get("url") or ""
                if not ep_url:
                    continue

                ep_num = parse_episode_number(raw_ep_name)
                if vod_title:
                    if ep_num > 0:
                        full_title = f"{vod_title} 第{ep_num:02d}集"
                    elif vod_title not in raw_ep_name:
                        full_title = f"{vod_title} {raw_ep_name}"
                    else:
                        full_title = raw_ep_name
                else:
                    full_title = raw_ep_name

                item_url = f"{self.adapter.base_url}?{urllib.parse.urlencode({'action': 'play_hls', 'url': ep_url, 'title': full_title, 'vod_title': vod_title, 'vod_id': video_id, 'line': line_name, 'type_id': type_id, 'pic': pic, 'fanart': fanart, 'from_playlist': '1'})}"

                list_item = self.adapter.xbmcgui.ListItem(label=full_title, path=item_url)
                list_item.setProperty('IsPlayable', 'true')
                art = {}
                if pic:
                    art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
                if fanart:
                    art['fanart'] = fanart
                if art:
                    list_item.setArt(art)

                info = {
                    "tvshowtitle": vod_title or full_title,
                    "title": full_title,
                    "mediatype": "episode" if ep_num > 0 else "video"
                }
                if ep_num > 0:
                    info["episode"] = ep_num
                list_item.setInfo('video', info)

                playlist.add(item_url, list_item)

            self.adapter.xbmc.Player().play(playlist)

    def show_pan_files(self, params, progress=None):
        """渲染电视剧网盘文件夹下的集数子目录列表，未登录时提示扫码登录"""
        pan_name = params.get("pan_name") or ""
        share_url = to_share_url(params.get("url"), pan_name)
        params["url"] = share_url
        code = params.get("code") or ""
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        movie_id = params.get("movie_id") or ""
        link_id = params.get("link_id")
        type_id = params.get("type_id")
        season_param = params.get("season_number")
        is_tv_param = (params.get("is_tv") == "1") or (str(type_id) == "2")
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""
        link_idx = safe_int(params.get("link_idx"), 1)
        page = safe_int(params.get("page"), 1)
        page_size = safe_int(params.get("page_size"), 50)

        def get_next_link():
            safe_vod_id = str(safe_int(vod_id)) if vod_id else ""
            self.adapter.log(f"[get_next_link] 开始匹配. vod_id_raw={vod_id}, safe_vod_id={safe_vod_id}, pan_name={pan_name}, link_id={link_id}", "info")
            if safe_vod_id and pan_name and link_id:
                try:
                    detail = self.api_client.get_video_detail(safe_vod_id)
                    self.adapter.log(f"[get_next_link] API详情请求完毕. 结果存在={bool(detail)}", "info")
                    if detail:
                        pan_list = detail.get("panList") or {}
                        items = []
                        for k, v in pan_list.items():
                            if str(k) == str(pan_name):
                                items = v
                                break
                        self.adapter.log(f"[get_next_link] 匹配到网盘 items 长度={len(items)}", "info")
                        current_idx = -1
                        for idx, item in enumerate(items):
                            if str(item.get("id")) == str(link_id):
                                current_idx = idx
                                break
                        if current_idx != -1:
                            if current_idx < len(items) - 1:
                                next_item = items[current_idx + 1]
                                self.adapter.log(f"[get_next_link] 成功找到下一个链接 (基于当前索引+1): id={next_item.get('id')}", "info")
                                return next_item
                            else:
                                self.adapter.log(f"[get_next_link] 当前已经是列表最后一项", "info")
                        else:
                            # 没找到，说明当前链接可能已被后端过滤，直接尝试当前剩余列表的第一项
                            if items:
                                next_item = items[0]
                                self.adapter.log(f"[get_next_link] 链接已失效被过滤，自动尝试当前剩余的第一个链接: id={next_item.get('id')}", "info")
                                return next_item
                            else:
                                self.adapter.log(f"[get_next_link] 列表已空", "info")
                except Exception as ex:
                    self.adapter.log(f"查找下一个网盘链接失败: {str(ex)}", "warning")
            else:
                self.adapter.log(f"[get_next_link] 参数缺失，跳过匹配", "warning")
            return None

        try:
            files_data = self.api_client.list_pan_files(share_url, code, page=page, page_size=page_size)
            files = files_data.get("files") or []
            total = safe_int(files_data.get("total"), 0)
            total_page = safe_int(files_data.get("total_page"), 1)
            has_more = bool(files_data.get("has_more", False))

            if not files:
                if link_id:
                    self.api_client.mark_pan_link_invalid(link_id, "无可播放文件")
                
                next_link = get_next_link()
                if next_link:
                    next_link_idx = link_idx + 1
                    msg = f"当前链接已失效，自动尝试备用链接: 链接{next_link_idx}"
                    if not progress and self.adapter.xbmcgui:
                        try:
                            progress = self.adapter.xbmcgui.DialogProgress()
                            progress.create("失效链接自愈", msg)
                        except Exception:
                            progress = None
                    elif progress:
                        try:
                            progress.update(50, msg)
                        except Exception:
                            pass
                    else:
                        self.adapter.show_notification("链接失效", msg)

                    new_params = params.copy()
                    new_params["url"] = next_link.get("url") or ""
                    new_params["code"] = next_link.get("code") or ""
                    new_params["link_id"] = next_link.get("id")
                    new_params["link_idx"] = next_link_idx
                    return self.show_pan_files(new_params, progress=progress)

                if progress:
                    try:
                        progress.close()
                    except Exception:
                        pass
                self.adapter.add_directory_item(
                    "无可播放文件 (已自动上报失效)",
                    {"action": "root"},
                    is_folder=False
                )
                self.adapter.end_of_directory()
                return
        except Exception as e:
            err_msg = str(e)
            is_login_needed = "请先登录" in err_msg or "未登录" in err_msg
            
            # 如果是链接失效，直接提示“该链接已失效（已自动上报失效）”并返回
            if not is_login_needed and should_mark_pan_link_invalid(err_msg):
                if link_id:
                    self.api_client.mark_pan_link_invalid(link_id, err_msg)
                
                next_link = get_next_link()
                if next_link:
                    next_link_idx = link_idx + 1
                    msg = f"当前网盘链接已失效，自动尝试备用链接: 链接{next_link_idx}"
                    if not progress and self.adapter.xbmcgui:
                        try:
                            progress = self.adapter.xbmcgui.DialogProgress()
                            progress.create("失效链接自愈", msg)
                        except Exception:
                            progress = None
                    elif progress:
                        try:
                            progress.update(50, msg)
                        except Exception:
                            pass
                    else:
                        self.adapter.show_notification("链接失效", msg)

                    new_params = params.copy()
                    new_params["url"] = next_link.get("url") or ""
                    new_params["code"] = next_link.get("code") or ""
                    new_params["link_id"] = next_link.get("id")
                    new_params["link_idx"] = next_link_idx
                    return self.show_pan_files(new_params, progress=progress)

                if progress:
                    try:
                        progress.close()
                    except Exception:
                        pass
                self.adapter.add_directory_item(
                    "该链接已失效（已自动上报失效）",
                    {"action": "root"},
                    is_folder=False
                )
                self.adapter.end_of_directory()
                return

            # 请求失败（未登录 / token 过期），提示用户登录
            provider_display = CLOUD_PROVIDER_NAMES.get(str(pan_name), f"网盘{pan_name}")
            provider_key = CLOUD_PROVIDER_KEYS.get(str(pan_name))

            if progress:
                try:
                    progress.close()
                except Exception:
                    pass

            self.adapter.add_directory_item(
                f"请先登录{provider_display}",
                {"action": "root"},
                is_folder=False
            )
            self.adapter.add_directory_item(
                f"错误原因: {err_msg} (URL: {share_url})",
                {"action": "root"},
                is_folder=False
            )
            if provider_key:
                self.adapter.add_directory_item(
                    f"点击扫码登录{provider_display}",
                    {"action": "qr_login", "provider": provider_key},
                    is_folder=False
                )
            self.adapter.end_of_directory()
            return

        self.adapter.set_content("episodes")

        if page > 1:
            prev_params = params.copy()
            prev_params["page"] = page - 1
            prev_title = f"上一页 (第 {page - 1}/{total_page} 页)" if total_page > 1 else f"上一页 (第 {page - 1} 页)"
            self.adapter.add_directory_item(
                prev_title,
                prev_params,
                is_folder=True
            )

        # 预查分集播放断点与已看状态
        target_mid = movie_id or vod_id
        batch_status_map = {}
        if target_mid and files:
            ep_query_ids = []
            for f in files:
                f_name = f.get("file_name")
                e_n = parse_episode_number(f_name)
                s_n = parse_season_number(f_name) or safe_int(season_param, 1)
                if e_n > 0:
                    ep_query_ids.append(f"ep_{target_mid}_{s_n}_{e_n}")
            if ep_query_ids:
                try:
                    res_map = self.api_client.get_batch_playback_status(ep_query_ids)
                    if isinstance(res_map, dict):
                        batch_status_map = res_map
                except Exception:
                    pass

        for f in files:
            file_name = f.get("file_name")
            size_label = f.get("size_label")
            ep_num = parse_episode_number(file_name)
            s_num = parse_season_number(file_name) or safe_int(season_param, 1)
            is_file_tv = is_tv_param or (ep_num > 0)
            
            if vod_title:
                formatted_name = f"{vod_title}：（{file_name}）"
            else:
                formatted_name = file_name

            ep_id = f"ep_{target_mid}_{s_num}_{ep_num}" if (target_mid and ep_num > 0) else ""
            ep_status = batch_status_map.get(ep_id) or {}
            ep_resume = float(ep_status.get("resume_seconds") or 0.0)
            ep_played = bool(ep_status.get("played"))

            progress_tag = ""
            if ep_played:
                progress_tag = " [已看]"
            elif ep_resume > 0:
                rm, rs = divmod(int(ep_resume), 60)
                if rm >= 60:
                    rh, rm = divmod(rm, 60)
                    t_str = f"{rh:02d}:{rm:02d}:{rs:02d}"
                else:
                    t_str = f"{rm:02d}:{rs:02d}"
                pct = int(ep_status.get("percentage") or 0)
                if pct > 0:
                    progress_tag = f" [已播 {t_str} · {pct}%]"
                else:
                    progress_tag = f" [已播 {t_str}]"

            display_name = f"[{size_label}]{formatted_name}{progress_tag}" if size_label else f"{formatted_name}{progress_tag}"

            info = {
                "tvshowtitle": vod_title or file_name,
                "title": formatted_name,
                "mediatype": "episode" if ep_num > 0 else "video"
            }
            if ep_num > 0:
                info["episode"] = ep_num
            if ep_resume > 0:
                info["resume_time"] = ep_resume
            if ep_played:
                info["played"] = True
                info["playcount"] = 1

            item_params = {
                "action": "pan_play", 
                "url": share_url, 
                "code": code, 
                "file_id": f.get("file_id"), 
                "pan_name": pan_name,
                "file_name": file_name,
                "title": formatted_name,
                "vod_title": vod_title,
                "vod_id": vod_id,
                "link_id": link_id,
                "link_idx": link_idx,
                "type_id": type_id,
                "pic": pic,
                "fanart": fanart
            }
            f_size = f.get("size") or f.get("file_size") or 0
            if f_size:
                item_params["file_size"] = f_size

            self.adapter.add_directory_item(
                display_name,
                item_params,
                is_folder=False,
                is_playable=True,
                pic=pic,
                fanart=fanart,
                info=info
            )

        if has_more or (total_page > 1 and page < total_page):
            next_params = params.copy()
            next_params["page"] = page + 1
            next_title = f"下一页 (第 {page + 1}/{total_page} 页)" if total_page > 1 else f"下一页 (第 {page + 1} 页)"
            self.adapter.add_directory_item(
                next_title,
                next_params,
                is_folder=True
            )

        if progress:
            try:
                progress.close()
            except Exception:
                pass
        self.adapter.end_of_directory()

    def play_all_pan_files(self, params):
        """将网盘全集文件写入 Kodi 播放列表并自动顺序播放"""
        pan_name = params.get("pan_name") or ""
        share_url = to_share_url(params.get("url"), pan_name)
        code = params.get("code") or ""
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        link_id = params.get("link_id")
        type_id = params.get("type_id")
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""
        link_idx = safe_int(params.get("link_idx"), 1)

        try:
            files_data = self.api_client.list_pan_files(share_url, code)
            files = files_data.get("files") or []
        except Exception:
            files = []

        if not files:
            self.adapter.show_notification("网盘播放", "无可播放文件", is_error=True)
            return

        if self.adapter.xbmcgui and self.adapter.xbmc:
            playlist = self.adapter.xbmc.PlayList(self.adapter.xbmc.PLAYLIST_VIDEO)
            playlist.clear()

            for f in files:
                file_name = f.get("file_name")
                ep_num = parse_episode_number(file_name)

                if vod_title:
                    formatted_name = f"{vod_title}：（{file_name}）"
                else:
                    formatted_name = file_name

                pan_play_params = {
                    'action': 'pan_play',
                    'url': share_url,
                    'code': code,
                    'file_id': f.get('file_id'),
                    'pan_name': pan_name,
                    'file_name': file_name,
                    'file_size': f.get('size') or f.get('file_size') or 0,
                    'title': formatted_name,
                    'vod_title': vod_title,
                    'vod_id': vod_id,
                    'movie_id': params.get('movie_id') or vod_id,
                    'link_id': link_id,
                    'link_idx': link_idx,
                    'type_id': type_id,
                    'pic': pic,
                    'fanart': fanart,
                    'from_playlist': '1'
                }
                if ep_num > 0 or params.get('is_tv') == '1' or str(type_id) == '2':
                    pan_play_params['is_tv'] = '1'
                    pan_play_params['season_number'] = params.get('season_number') or '1'
                    if ep_num > 0:
                        pan_play_params['episode_number'] = str(ep_num)
                item_url = f"{self.adapter.base_url}?{urllib.parse.urlencode(pan_play_params)}"

                list_item = self.adapter.xbmcgui.ListItem(label=formatted_name, path=item_url)
                list_item.setProperty('IsPlayable', 'true')
                art = {}
                if pic:
                    art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
                if fanart:
                    art['fanart'] = fanart
                if art:
                    list_item.setArt(art)

                info = {
                    "tvshowtitle": vod_title or formatted_name,
                    "title": formatted_name,
                    "mediatype": "episode" if ep_num > 0 else "video"
                }
                if ep_num > 0:
                    info["episode"] = ep_num
                list_item.setInfo('video', info)

                playlist.add(item_url, list_item)

            self.adapter.xbmc.Player().play(playlist)

    def play_pan_file(self, params):
        """点击集数进行播放直链和外挂字幕解析渲染"""
        pan_name = params.get("pan_name") or ""
        share_url = to_share_url(params.get("url"), pan_name)
        provider_key = detect_cloud_provider_key(pan_name, share_url)
        code = params.get("code") or ""
        file_id = params.get("file_id") or ""
        vod_title = params.get("vod_title") or ""
        vod_id = params.get("vod_id") or ""
        file_name = params.get("file_name") or ""
        title = params.get("title") or file_name
        pic = params.get("pic") or ""
        fanart = params.get("fanart") or ""
        file_size = params.get("file_size") or params.get("size") or 0
        try:
            file_size = int(file_size)
        except (ValueError, TypeError):
            file_size = 0

        resolve_kwargs = {"file_name": file_name}
        if file_size > 0:
            resolve_kwargs["file_size"] = file_size

        try:
            res = self.api_client.resolve_play(share_url, code, file_id, **resolve_kwargs)
        except Exception as e:
            err_msg = str(e)
            if "请先登录" in err_msg or "未登录" in err_msg:
                if not provider_key or provider_key not in CLOUD_PROVIDER_NAMES:
                    provider_key = detect_cloud_provider_key(provider_key, share_url, err_msg)
                display_name = CLOUD_PROVIDER_NAMES.get(provider_key, provider_key)
                if not display_name:
                    display_name = "网盘"
                confirm = self.adapter.show_yes_no_dialog(
                    "登录提示",
                    f"播放此视频需要登录 {display_name}。\n是否立即进行扫码登录？"
                )
                if confirm:
                    success = self.start_qr_login(provider_key)
                    if success:
                        self.adapter.show_notification("扫码登录", f"{display_name} 登录成功，正在重新解析播放...")
                        try:
                            res = self.api_client.resolve_play(share_url, code, file_id, **resolve_kwargs)
                        except Exception as e2:
                            err_msg2 = str(e2)
                            self.adapter.show_notification("播放失败", err_msg2, is_error=True)
                            link_id = params.get("link_id")
                            if link_id and should_mark_pan_link_invalid(err_msg2):
                                self.api_client.mark_pan_link_invalid(link_id, err_msg2)
                            self.adapter.set_resolved_url(False, None)
                            return
                    else:
                        self.adapter.set_resolved_url(False, None)
                        return
                else:
                    self.adapter.set_resolved_url(False, None)
                    return
            else:
                self.adapter.show_notification("播放失败", err_msg, is_error=True)
                link_id = params.get("link_id")
                if link_id and should_mark_pan_link_invalid(err_msg):
                    self.api_client.mark_pan_link_invalid(link_id, err_msg)
                self.adapter.set_resolved_url(False, None)
                return

        play_url = res.get("play_url")
        headers = res.get("headers") or {}
        subtitles = res.get("subtitles") or []
        res_file_name = res.get("file_name") or ""
        if res_file_name:
            _, ext_check = get_file_category(file_name)
            if not ext_check:
                file_name = res_file_name

        if not play_url:
            self.adapter.log("未解析到可播放直链", "error")
            self.adapter.set_resolved_url(False, None)
            return

        # 转换为 Kodi 专有格式 URL：play_url | Headers
        if headers:
            header_parts = []
            for k, v in headers.items():
                header_parts.append(f"{k}={urllib.parse.quote(v, safe='')}")
            play_url = f"{play_url}|{'&'.join(header_parts)}"

        display_title_param = params.get("display_title")
        season_number_param = params.get("season_number")
        episode_number_param = params.get("episode_number")
        episode_title_param = params.get("episode_title") or ""
        remark_param = params.get("remark") or ""
        type_id_param = params.get("type_id")
        is_tv_param = (params.get("is_tv") == "1")
        if type_id_param == "1":
            is_tv_param = False

        display_title, s_num, e_num, is_tv_item = build_play_display_title(
            vod_title=vod_title,
            season_number=season_number_param,
            episode_number=episode_number_param,
            episode_title=episode_title_param,
            remark=remark_param,
            fallback_title=file_name or title,
            is_tv=is_tv_param,
            type_id=type_id_param
        )
        if display_title_param:
            display_title = display_title_param

        # 尝试为网盘多集剧集自动填充完整播放列表
        if share_url and file_id and self.adapter.xbmc and self.adapter.xbmcgui:
            try:
                playlist = self.adapter.xbmc.PlayList(self.adapter.xbmc.PLAYLIST_VIDEO)
                is_from_playlist = params.get("from_playlist") == "1"
                is_from_push = params.get("from_push") == "1"
                type_id_val = safe_int(params.get("type_id"), 0)
                is_single_movie = not is_tv_item and (type_id_val == 1 or params.get("single_file") == "1")

                if is_from_playlist:
                    # 已经在连续播放列表中（Kodi 连播或切下一集），跳过播放列表重建，避免破坏内部播放指针导致跳集
                    pass
                elif is_single_movie or (is_from_push and not is_tv_item):
                    # 电影单片、单文件或非电视剧推送播放：只维护单项 Playlist，避免多余的 list_pan_files 请求
                    playlist.clear()
                    list_item = self.adapter.xbmcgui.ListItem(label=display_title, path=play_url)
                    list_item.setProperty('IsPlayable', 'true')
                    list_item.setPath(play_url)
                    art = {}
                    if pic:
                        art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
                    if fanart:
                        art['fanart'] = fanart
                    if art:
                        list_item.setArt(art)
                    info = {
                        "tvshowtitle": (vod_title or display_title) if is_tv_item else "",
                        "title": display_title,
                        "mediatype": "episode" if is_tv_item else "movie"
                    }
                    if is_tv_item:
                        info["episode"] = e_num
                        info["season"] = s_num
                    list_item.setInfo('video', info)
                    playlist.add(play_url, list_item)
                else:
                    files_data = self.api_client.list_pan_files(share_url, code)
                    files = files_data.get("files") or []
                    if len(files) > 1:
                        # 查找当前播放文件在网盘文件列表中的位置
                        curr_idx = -1
                        for idx, f in enumerate(files):
                            if f.get("file_id") == file_id:
                                curr_idx = idx
                                break

                        # 从当前集开始向后构建播放列表：第 0 项为当前集，后续为未播集数
                        # 确保首次起播时，Kodi 连播下一集永远顺位播放，绝不跳回前序已播集
                        start_idx = curr_idx if curr_idx >= 0 else 0
                        remaining_files = files[start_idx:]

                        playlist.clear()
                        link_id = params.get("link_id")
                        link_idx = safe_int(params.get("link_idx"), 1)
                        type_id = params.get("type_id")

                        for idx, f in enumerate(remaining_files):
                            curr_file_id = f.get("file_id")
                            file_name_item = f.get("file_name")
                            ep_num = parse_episode_number(file_name_item)

                            if vod_title:
                                formatted_name = f"{vod_title}：（{file_name_item}）"
                            else:
                                formatted_name = file_name_item

                            if idx == 0 and curr_file_id == file_id:
                                target_path = play_url
                            else:
                                item_s_num = parse_season_number(file_name_item) or s_num
                                target_path = f"{self.adapter.base_url}?{urllib.parse.urlencode({'action': 'pan_play', 'url': share_url, 'code': code, 'file_id': curr_file_id, 'pan_name': pan_name, 'file_name': file_name_item, 'file_size': f.get('size') or f.get('file_size') or 0, 'title': formatted_name, 'vod_title': vod_title, 'vod_id': vod_id, 'movie_id': params.get('movie_id') or vod_id, 'link_id': link_id, 'link_idx': link_idx, 'type_id': type_id, 'is_tv': '1' if is_tv_item else '0', 'season_number': item_s_num if is_tv_item else '', 'episode_number': ep_num if (is_tv_item and ep_num > 0) else '', 'pic': pic, 'fanart': fanart, 'from_playlist': '1'})}"

                            list_item = self.adapter.xbmcgui.ListItem(label=formatted_name, path=target_path)
                            list_item.setProperty('IsPlayable', 'true')
                            art = {}
                            if pic:
                                art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
                            if fanart:
                                art['fanart'] = fanart
                            if art:
                                list_item.setArt(art)

                            info = {
                                "tvshowtitle": (vod_title or formatted_name) if is_tv_item else "",
                                "title": formatted_name,
                                "mediatype": "episode" if (is_tv_item and ep_num > 0) else "movie"
                            }
                            if is_tv_item and ep_num > 0:
                                info["episode"] = ep_num
                            list_item.setInfo('video', info)

                            playlist.add(target_path, list_item)
            except Exception as ex:
                self.adapter.log(f"自动构建网盘播放列表失败: {str(ex)}", "warning")

        if self.adapter.xbmcgui and self.adapter.xbmcplugin:
            list_item = self.adapter.xbmcgui.ListItem(label=display_title, path=play_url)
            list_item.setProperty('IsPlayable', 'true')

            art = {}
            if pic:
                art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
            if fanart:
                art['fanart'] = fanart
            if art:
                list_item.setArt(art)

            cat, _ = get_file_category(file_name or title)
            if cat == "audio":
                info = {
                    "title": display_title,
                    "artist": vod_title or display_title
                }
                list_item.setInfo('music', info)
            else:
                info = {
                    "tvshowtitle": (vod_title or display_title) if is_tv_item else "",
                    "title": display_title,
                    "mediatype": "episode" if is_tv_item else "movie"
                }
                if is_tv_item:
                    info["episode"] = e_num
                    info["season"] = s_num
                resume_time = params.get("resume_time")
                if resume_time and float(resume_time) > 0:
                    r_sec = float(resume_time)
                    info["resume_time"] = r_sec
                    list_item.setProperty('ResumeTime', str(r_sec))
                    list_item.setProperty('StartOffset', str(r_sec))
                list_item.setInfo('video', info)

            # 注入外挂字幕
            sub_urls = []
            for sub in subtitles:
                if sub.get("url"):
                    sub_urls.append(sub.get("url"))
            if sub_urls:
                list_item.setSubtitles(sub_urls)

            self._mark_playback_started(
                movie_id=params.get("movie_id"),
                vod_id=vod_id,
                season_number=s_num if is_tv_item else None,
                episode_number=e_num if is_tv_item else None,
                is_tv=is_tv_item,
                link_id=params.get("link_id")
            )
            self.adapter.set_resolved_url(True, list_item)

            # 保存播放历史
            if vod_title:
                try:
                    profile_dir = self.adapter.get_profile_path()
                    history_mgr = HistoryManager(profile_dir)
                    type_id = params.get("type_id")
                    is_folder = False
                    play_params = {
                        "action": "pan_play",
                        "url": params.get("url"),
                        "code": code,
                        "file_id": file_id,
                        "pan_name": pan_name,
                        "file_name": file_name,
                        "file_size": file_size,
                        "vod_title": vod_title,
                        "vod_id": vod_id
                    }
                    if is_tv_item:
                        play_params["season_number"] = s_num
                        play_params["episode_number"] = e_num
                        play_params["is_tv"] = "1"
                        if remark_param:
                            play_params["remark"] = remark_param

                    if type_id is not None and str(type_id) != "1":
                        is_folder = True
                        play_params = {
                            "action": "list_files",
                            "url": params.get("url"),
                            "code": code,
                            "pan_name": pan_name,
                            "vod_title": vod_title,
                            "vod_id": vod_id,
                            "link_id": params.get("link_id"),
                            "link_idx": params.get("link_idx"),
                            "type_id": type_id
                        }

                    item_history_name = file_name
                    if is_tv_item:
                        item_history_name = f"第{s_num}季第{e_num}集" + (f"（{remark_param}）" if remark_param else (f"（{file_name}）" if file_name and file_name != f"第{s_num}季第{e_num}集" else ""))
                    elif remark_param:
                        item_history_name = remark_param

                    record = {
                        "vod_title": vod_title,
                        "vod_id": vod_id,
                        "item_name": item_history_name,
                        "timestamp": time.time(),
                        "is_folder": is_folder,
                        "play_params": play_params
                    }
                    history_mgr.add_record(record)
                except Exception as e:
                    self.adapter.log(f"保存网盘播放历史失败: {str(e)}", "warning")

            if self.adapter.xbmc:
                try:
                    self.adapter.xbmc.executebuiltin("Dialog.Close(all, true)")
                except Exception:
                    pass
            self.adapter.xbmcplugin.setResolvedUrl(self.adapter.handle, True, list_item)
        else:
            self.adapter.log(f"Play URL: {play_url}, Subs: {subtitles}")

    # --------------------------------------------------------------------------
    # 6. 网盘扫码登录界面浮层与状态查询
    # --------------------------------------------------------------------------
    def show_my_pans_menu(self):
        """渲染‘我的网盘’主菜单 (库视图)"""
        self.adapter.set_library_content("videos")
        status_data = self.api_client.get_pan_status() or {}
        pan_order = self.api_client.get_pan_order()
        
        # 保持有序展示
        default_providers = ["ALIYUN", "QUARK", "UC", "BAIDU", "XUNLEI", "CLOUD123", "CLOUD115", "CHINA_MOBILE", "CHINA_TELECOM", "GUANGYA"]
        providers_order = sort_pan_keys(default_providers, pan_order)
        
        # 1. 自动删除转存文件总开关/一键切换项
        all_auto_del = all(status_data.get(k, {}).get("auto_delete", True) for k in providers_order)
        all_target_val = "false" if all_auto_del else "true"
        all_del_label = f"[全部网盘] 自动删除转存文件: {'全部开启' if all_auto_del else '部分或全部关闭'} (点击一键{'关闭' if all_auto_del else '开启'})"
        self.adapter.add_library_item(
            all_del_label,
            {"action": "pan_toggle_all_auto_delete", "target": all_target_val},
            "my_pans_menu",
            plot="一键切换所有网盘的“播放后自动删除转存文件”策略，节省网盘空间。",
            is_folder=False,
            mediatype="video",
        )
        
        for p_key in providers_order:
            default_concurrency = 8
            if p_key == "ALIYUN":
                default_concurrency = 32
            elif p_key == "XUNLEI":
                default_concurrency = 4
            elif p_key == "CLOUD115":
                default_concurrency = 1
                
            p_status = status_data.get(p_key) or {"logged_in": False, "concurrency": default_concurrency, "auto_delete": True}
            logged_in = p_status.get("logged_in", False)
            concurrency = p_status.get("concurrency", default_concurrency)
            auto_delete = p_status.get("auto_delete", True)
            is_vip = p_status.get("is_vip", False)
            if p_key == "CLOUD115":
                concurrency = 1
            
            display_name = CLOUD_PROVIDER_NAMES.get(p_key, p_key)
            if logged_in:
                if p_key in ["ALIYUN", "QUARK", "UC"]:
                    status_text = "[已登录-VIP]" if is_vip else "[已登录-普通]"
                else:
                    status_text = "[已登录]"
            else:
                status_text = "[未登录]"
            auto_del_text = "[自动删:开]" if auto_delete else "[自动删:关]"
            label = f"{status_text} {display_name} (并发数: {concurrency}) {auto_del_text}"

            if logged_in:
                plot = f"{display_name} 已登录，可浏览个人盘文件并直接播放。并发 {concurrency}，自动删除转存：{'开启' if auto_delete else '关闭'}。"
            else:
                plot = f"{display_name} 尚未登录，点击进入后可扫码或手工登录，登录后即可免转存直接播放。"
            
            toggle_target = "false" if auto_delete else "true"
            toggle_text = "关闭自动删除转存" if auto_delete else "开启自动删除转存"
            context_menu = [
                (toggle_text, f"RunPlugin({self.adapter.base_url}?action=pan_toggle_auto_delete&provider={p_key}&value={toggle_target})")
            ]
            self.adapter.add_library_item(
                label,
                {"action": "pan_detail_menu", "provider": p_key},
                "my_pans",
                plot=plot,
                is_folder=True,
                context_menu=context_menu,
                mediatype="movie",
            )
        self.adapter.end_of_directory()

    def show_pan_detail_menu(self, provider):
        """渲染单个网盘的详情操作菜单 (库视图)"""
        self.adapter.set_library_content("videos")
        status_data = self.api_client.get_pan_status() or {}
        default_concurrency = 8
        if provider == "ALIYUN":
            default_concurrency = 32
        elif provider == "XUNLEI":
            default_concurrency = 4
        elif provider == "CLOUD115":
            default_concurrency = 1
            
        p_status = status_data.get(provider) or {"logged_in": False, "concurrency": default_concurrency, "chunk_size": 0, "auto_delete": True}
        logged_in = p_status.get("logged_in", False)
        concurrency = p_status.get("concurrency", default_concurrency)
        chunk_size = p_status.get("chunk_size", 0)
        auto_delete = p_status.get("auto_delete", True)
        is_vip = p_status.get("is_vip", False)
        if provider == "CLOUD115":
            concurrency = 1
        
        display_name = CLOUD_PROVIDER_NAMES.get(provider, provider)
        
        # 0. 浏览个人网盘入口
        if logged_in:
            self.adapter.add_library_item(
                "浏览个人盘文件 (根目录)",
                {"action": "list_user_pan_files", "provider": provider, "parent_file_id": "root"},
                "my_pans",
                plot=f"浏览你的 {display_name} 个人盘根目录，可直接选片播放。",
                is_folder=True,
                mediatype="movie",
            )
            if provider == "CLOUD115":
                self.adapter.add_library_item(
                    "[查看 115 云下载任务列表]",
                    {"action": "cloud_down_tasks"},
                    "my_pans",
                    plot="查看与播放 115 云下载任务中已完成的文件。",
                    is_folder=True,
                    mediatype="movie",
                )

        # 1. 状态展示项
        if logged_in:
            if provider in ["ALIYUN", "QUARK", "UC"]:
                status_label = f"当前状态: 已登录 ({'会员账号' if is_vip else '普通账号'})"
            else:
                status_label = "当前状态: 已登录"
        else:
            status_label = "当前状态: 未登录"
        self.adapter.add_library_item(
            status_label, {"action": "my_pans_menu"}, "login",
            plot=f"{display_name} 当前登录状态。",
            is_folder=True, mediatype="movie",
        )
        
        # 2. 修改并发数项
        if provider == "CLOUD115":
            concurrency_label = f"并发连接数: {concurrency} (防风控，不可修改)"
        else:
            concurrency_label = f"并发连接数: {concurrency} (点击修改)"
        self.adapter.add_library_item(
            concurrency_label,
            {"action": "pan_concurrency", "provider": provider},
            "settings",
            plot="调整同时下载的分片连接数，数值越高速度越快，但过高可能触发网盘风控。",
            is_folder=False, mediatype="video",
        )
        
        # 3. 修改分片连接大小项
        if chunk_size <= 0:
            chunk_size_label = "分片连接大小: 自动 (自适应) (点击修改)"
        elif chunk_size % (1024 * 1024) == 0:
            chunk_size_label = f"分片连接大小: {chunk_size // (1024 * 1024)} MB (点击修改)"
        elif chunk_size % 1024 == 0:
            chunk_size_label = f"分片连接大小: {chunk_size // 1024} KB (点击修改)"
        else:
            chunk_size_label = f"分片连接大小: {chunk_size} 字节 (点击修改)"
        self.adapter.add_library_item(
            chunk_size_label,
            {"action": "pan_chunk_size", "provider": provider},
            "settings",
            plot="调整每个下载分片的大小，影响解析与缓冲表现，一般保持自动即可。",
            is_folder=False, mediatype="video",
        )

        # 3.5 修改请求间隔 (QPS) 项
        default_qps = 1.0 if provider == "CLOUD115" else 0.0
        qps_val = p_status.get("qps", default_qps)
        if qps_val <= 0:
            qps_label = "请求间隔(QPS): 全速无休眠 (点击修改)"
        else:
            qps_label = f"请求间隔(QPS): {qps_val} 秒/次 (点击修改)"
        self.adapter.add_library_item(
            qps_label,
            {"action": "pan_qps", "provider": provider},
            "settings",
            plot="限制接口请求频率，适当放慢可降低被网盘限流或风控的概率。",
            is_folder=False, mediatype="video",
        )

        # 4. 自动删除转存文件开关项
        auto_del_state = "开启" if auto_delete else "关闭"
        toggle_val = "false" if auto_delete else "true"
        auto_del_label = f"自动删除转存文件: {auto_del_state} (点击切换)"
        self.adapter.add_library_item(
            auto_del_label,
            {"action": "pan_toggle_auto_delete", "provider": provider, "value": toggle_val},
            "settings",
            plot="播放时若需转存文件，播放结束后自动删除，避免占用网盘空间。",
            is_folder=False, mediatype="video",
        )

        # 115 专属云下载保存目录项
        if provider == "CLOUD115":
            save_dir = p_status.get("save_dir") or ""
            if not save_dir:
                try:
                    save_dir = self.api_client.get_115_save_dir()
                except Exception:
                    save_dir = "云下载"
            if not save_dir:
                save_dir = "云下载"
            self.adapter.add_library_item(
                f"云下载保存目录: {save_dir} (点击修改)",
                {"action": "pan115_save_dir"},
                "settings",
                plot="指定 115 云下载任务的默认保存目录。",
                is_folder=False, mediatype="video",
            )
        
        # 5. 登录 / 退出登录项
        if logged_in:
            self.adapter.add_library_item(
                "退出登录",
                {"action": "pan_logout", "provider": provider},
                "login",
                plot=f"退出 {display_name} 的当前账号登录状态。",
                is_folder=False, mediatype="video",
            )
        else:
            SUPPORTED_QR = ["ALIYUN", "QUARK", "UC", "BAIDU", "XUNLEI", "CLOUD123", "CLOUD115", "CHINA_MOBILE", "CHINA_TELECOM", "GUANGYA"]
            if provider in SUPPORTED_QR:
                self.adapter.add_library_item(
                    "扫码登录",
                    {"action": "qr_login", "provider": provider},
                    "login",
                    plot=f"用手机 {display_name} App 扫码，快速完成授权登录。",
                    is_folder=False, mediatype="video",
                )
                self.adapter.add_library_item(
                    "网页手工输入登录",
                    {"action": "manual_login", "provider": provider},
                    "login",
                    plot="通过网页跳转后手工输入授权信息完成登录。",
                    is_folder=False, mediatype="video",
                )
            else:
                self.adapter.add_library_item(
                    "此网盘暂不支持在 Kodi 扫码，请使用 Android TV 客户端登录同步",
                    {"action": "pan_detail_menu", "provider": provider},
                    "login",
                    plot="该网盘暂不支持在 Kodi 内扫码登录，请改用 Android TV 客户端登录后同步。",
                    is_folder=False, mediatype="video",
                )
                
        self.adapter.end_of_directory()

    def handle_pan_logout(self, provider):
        """处理退出登录逻辑"""
        display_name = CLOUD_PROVIDER_NAMES.get(provider, provider)
        confirm = self.adapter.show_yes_no_dialog("退出登录", f"确认退出 {display_name} 的登录状态吗？")
        if confirm:
            res = self.api_client.logout_pan(provider)
            if res.get("success"):
                self.adapter.show_notification("我的网盘", f"{display_name} 退出登录成功")
                self.adapter.refresh_container()
            else:
                self.adapter.show_notification("我的网盘", f"退出登录失败: {res.get('error', '未知错误')}", is_error=True)

    def handle_pan_concurrency(self, provider):
        """处理修改网盘并发数逻辑"""
        if provider == "CLOUD115":
            self.adapter.show_notification("我的网盘", "115网盘已限制为单链接，不可修改")
            return
            
        display_name = CLOUD_PROVIDER_NAMES.get(provider, provider)
        concurrency_options = ["1", "2", "4", "8", "12", "16", "24", "32", "64", "128", "256"]
        default_concurrency = 8
        if provider == "ALIYUN":
            default_concurrency = 32
        elif provider == "XUNLEI":
            default_concurrency = 4
        elif provider == "CLOUD115":
            default_concurrency = 1
            
        status_data = self.api_client.get_pan_status() or {}
        current_concurrency = str((status_data.get(provider) or {}).get("concurrency", default_concurrency))
        
        default_idx = 2
        if current_concurrency in concurrency_options:
            default_idx = concurrency_options.index(current_concurrency)
            
        idx = self.adapter.show_select_dialog(f"设置 {display_name} 的并发连接数", concurrency_options, default_idx)
        if idx >= 0:
            val = int(concurrency_options[idx])
            res = self.api_client.set_pan_concurrency(provider, val)
            if res.get("success"):
                self.adapter.show_notification("我的网盘", f"{display_name} 并发连接数已设置为 {val}")
                self.adapter.refresh_container()
            else:
                self.adapter.show_notification("我的网盘", f"修改并发数失败: {res.get('error', '未知错误')}", is_error=True)

    def handle_pan_chunk_size(self, provider):
        """处理修改网盘分片大小逻辑"""
        display_name = CLOUD_PROVIDER_NAMES.get(provider, provider)
        options = ["自动 (自适应)", "手动设置 (KB)", "手动设置 (MB)"]
        
        idx = self.adapter.show_select_dialog(f"设置 {display_name} 的分片连接大小", options, 0)
        if idx < 0:
            return
            
        if idx == 0:
            res = self.api_client.set_pan_chunk_size(provider, 0)
            if res.get("success"):
                self.adapter.show_notification("我的网盘", f"{display_name} 分片大小已设置为 自动")
                self.adapter.refresh_container()
            else:
                self.adapter.show_notification("我的网盘", f"设置失败: {res.get('error', '未知错误')}", is_error=True)
        elif idx == 1:
            status_data = self.api_client.get_pan_status() or {}
            curr_size = (status_data.get(provider) or {}).get("chunk_size", 0)
            default_kb = ""
            if curr_size > 0 and curr_size % 1024 == 0:
                default_kb = str(curr_size // 1024)
            val_str = self.adapter.show_numeric_dialog(f"输入分片大小(KB) [128 - 4096]", default_kb)
            if not val_str:
                return
            try:
                val = int(val_str)
                if val < 128 or val > 4096:
                    self.adapter.show_notification("输入越界", "KB模式分片限制在 128 ~ 4096 之间", is_error=True)
                    return
                bytes_val = val * 1024
                res = self.api_client.set_pan_chunk_size(provider, bytes_val)
                if res.get("success"):
                    self.adapter.show_notification("我的网盘", f"{display_name} 分片大小已设置为 {val} KB")
                    self.adapter.refresh_container()
                else:
                    self.adapter.show_notification("我的网盘", f"设置失败: {res.get('error', '未知错误')}", is_error=True)
            except ValueError:
                self.adapter.show_notification("输入错误", "请输入有效的正整数", is_error=True)
        elif idx == 2:
            status_data = self.api_client.get_pan_status() or {}
            curr_size = (status_data.get(provider) or {}).get("chunk_size", 0)
            default_mb = ""
            if curr_size > 0 and curr_size % (1024 * 1024) == 0:
                default_mb = str(curr_size // (1024 * 1024))
            val_str = self.adapter.show_numeric_dialog(f"输入分片大小(MB) [1 - 64]", default_mb)
            if not val_str:
                return
            try:
                val = int(val_str)
                if val < 1 or val > 64:
                    self.adapter.show_notification("输入越界", "MB模式分片限制在 1 ~ 64 之间", is_error=True)
                    return
                bytes_val = val * 1024 * 1024
                res = self.api_client.set_pan_chunk_size(provider, bytes_val)
                if res.get("success"):
                    self.adapter.show_notification("我的网盘", f"{display_name} 分片大小已设置为 {val} MB")
                    self.adapter.refresh_container()
                else:
                    self.adapter.show_notification("我的网盘", f"设置失败: {res.get('error', '未知错误')}", is_error=True)
            except ValueError:
                self.adapter.show_notification("输入错误", "请输入有效的正整数", is_error=True)

    def handle_pan_qps(self, provider):
        """处理修改网盘请求间隔(QPS)防风控逻辑"""
        display_name = CLOUD_PROVIDER_NAMES.get(provider, provider)
        qps_options = [
            ("全速无休眠 (0.0 秒)", 0.0),
            ("温和限速 (0.5 秒)", 0.5),
            ("推荐防风控 (1.0 秒)", 1.0),
            ("稳健限速 (1.5 秒)", 1.5),
            ("慢速防封 (2.0 秒)", 2.0),
            ("超慢速 (3.0 秒)", 3.0),
            ("自定义输入秒数...", -1.0)
        ]
        labels = [opt[0] for opt in qps_options]

        status_data = self.api_client.get_pan_status() or {}
        default_qps = 1.0 if provider == "CLOUD115" else 0.0
        current_qps = (status_data.get(provider) or {}).get("qps", default_qps)

        default_idx = 0
        for i, opt in enumerate(qps_options):
            if opt[1] >= 0 and abs(opt[1] - current_qps) < 0.01:
                default_idx = i
                break

        idx = self.adapter.show_select_dialog(f"设置 {display_name} 每次请求间隔 (QPS)", labels, default_idx)
        if idx < 0:
            return

        selected_val = qps_options[idx][1]
        if selected_val < 0:
            # 自定义输入
            input_val = self.adapter.show_input_dialog(f"输入请求间隔秒数 (如 0.8 或 2.5)", str(current_qps))
            if not input_val:
                return
            try:
                selected_val = float(input_val.strip())
                if selected_val < 0 or selected_val > 60:
                    self.adapter.show_notification("输入越界", "请求间隔秒数范围为 0 ~ 60 秒", is_error=True)
                    return
            except ValueError:
                self.adapter.show_notification("输入错误", "请输入有效的数字", is_error=True)
                return

        res = self.api_client.set_pan_qps(provider, selected_val)
        if res.get("success"):
            tip = "全速无休眠" if selected_val <= 0 else f"{selected_val} 秒/次"
            self.adapter.show_notification("我的网盘", f"{display_name} 请求间隔已设置为 {tip}")
            self.adapter.refresh_container()
        else:
            self.adapter.show_notification("我的网盘", f"设置失败: {res.get('error', '未知错误')}", is_error=True)

    def handle_pan115_save_dir(self):
        """处理修改 115 云下载保存目录逻辑"""
        curr_dir = "云下载"
        try:
            status_data = self.api_client.get_pan_status() or {}
            curr_dir = (status_data.get("CLOUD115") or {}).get("save_dir") or ""
            if not curr_dir:
                curr_dir = self.api_client.get_115_save_dir() or "云下载"
        except Exception:
            curr_dir = "云下载"

        options = [
            f"手动输入保存目录 (当前: {curr_dir})",
            "恢复默认保存目录 (云下载)"
        ]
        choice = self.adapter.show_select_dialog("115 云下载保存目录设置", options, 0)
        if choice < 0:
            return

        if choice == 1:
            new_dir = "云下载"
        else:
            input_val = self.adapter.show_keyboard_input(curr_dir, "请输入保存目录名称 (留空恢复为'云下载')")
            if input_val is None:
                return
            new_dir = input_val.strip() or "云下载"

        res = self.api_client.set_115_save_dir(new_dir)
        if res.get("success"):
            self.adapter.show_notification("我的网盘", f"115 云下载保存目录已设置为: {new_dir}")
            self.adapter.refresh_container()
        else:
            self.adapter.show_notification("我的网盘", f"设置失败: {res.get('error', '未知错误')}", is_error=True)

    def handle_pan_toggle_auto_delete(self, provider, value=None):
        """切换单个网盘的自动删除转存文件开关"""
        if not provider:
            return
        status_data = self.api_client.get_pan_status() or {}
        cur_status = (status_data.get(provider) or {}).get("auto_delete", True)
        if value is None or value == "":
            new_val = not cur_status
        else:
            new_val = (value == "true" or value is True or value == "1")
        
        display_name = CLOUD_PROVIDER_NAMES.get(provider, provider)
        res = self.api_client.set_pan_auto_delete(provider, new_val)
        if res and res.get("success"):
            state_str = "开启" if new_val else "关闭"
            self.adapter.show_notification("我的网盘", f"{display_name} 自动删除转存已{state_str}")
            self.adapter.refresh_container()
        else:
            err = res.get("error") if isinstance(res, dict) else "请求失败"
            self.adapter.show_notification("我的网盘", f"设置失败: {err}", is_error=True)

    def handle_pan_toggle_all_auto_delete(self, target=None):
        """一键切换所有网盘的自动删除转存文件开关"""
        status_data = self.api_client.get_pan_status() or {}
        default_providers = ["ALIYUN", "QUARK", "UC", "BAIDU", "XUNLEI", "CLOUD123", "CLOUD115", "CHINA_MOBILE", "CHINA_TELECOM", "GUANGYA"]
        if target is None or target == "":
            all_auto_del = all((status_data.get(k) or {}).get("auto_delete", True) for k in default_providers)
            new_val = not all_auto_del
        else:
            new_val = (target == "true" or target is True or target == "1")
        
        res = self.api_client.set_pan_auto_delete("ALL", new_val)
        if res and res.get("success"):
            state_str = "开启" if new_val else "关闭"
            self.adapter.show_notification("我的网盘", f"全部网盘自动删除转存已{state_str}")
            self.adapter.refresh_container()
        else:
            err = res.get("error") if isinstance(res, dict) else "请求失败"
            self.adapter.show_notification("我的网盘", f"设置失败: {err}", is_error=True)

    def list_user_pan_files(self, params):
        """渲染个人网盘的文件和文件夹列表"""
        provider = params.get("provider") or ""
        parent_file_id = params.get("parent_file_id") or ""
        dir_name = params.get("dir_name") or CLOUD_PROVIDER_NAMES.get(provider, provider)

        try:
            res_data = self.api_client.get_user_files(provider, parent_file_id)
            files = res_data.get("files") or []

            if not files:
                self.adapter.add_directory_item("(空文件夹)", {"action": "root"}, is_folder=False)
                self.adapter.end_of_directory()
                return

            self.adapter.set_content("episodes")

            for file in files:
                file_id = file.get("file_id") or ""
                file_name = file.get("file_name") or ""
                is_folder = file.get("is_folder", False)
                size_label = file.get("size_label") or ""

                if is_folder:
                    label = f"[目录] {file_name}"
                    self.adapter.add_directory_item(
                        label,
                        {
                            "action": "list_user_pan_files",
                            "provider": provider,
                            "parent_file_id": file_id,
                            "dir_name": file_name,
                        },
                        is_folder=True
                    )
                else:
                    cat, ext = get_file_category(file_name)
                    if cat in ["video", "audio", "image"]:
                        tag = "[视频]" if cat == "video" else ("[音频]" if cat == "audio" else "[图片]")
                        label = f"{tag} {file_name}"
                        if size_label:
                            label += f" [{size_label}]"

                        ep_num = parse_episode_number(file_name) if cat == "video" else 0
                        info = {
                            "tvshowtitle": file_name,
                            "title": file_name,
                            "mediatype": "episode" if ep_num > 0 else ("song" if cat == "audio" else "video")
                        }
                        if ep_num > 0:
                            info["episode"] = ep_num

                        self.adapter.add_directory_item(
                            label,
                            {
                                "action": "play_user_pan",
                                "provider": provider,
                                "file_id": file_id,
                                "file_name": file_name,
                                "vod_title": file_name,
                            },
                            is_folder=False,
                            is_playable=True,
                            info=info
                        )
                    else:
                        label = f"[文件] {file_name}"
                        if size_label:
                            label += f" [{size_label}]"

                        self.adapter.add_directory_item(
                            label,
                            {
                                "action": "unsupported_file",
                                "file_name": file_name,
                                "ext": ext,
                            },
                            is_folder=False,
                            is_playable=False
                        )

            self.adapter.end_of_directory()
        except Exception as e:
            err_msg = str(e)
            self.adapter.show_notification(f"浏览{CLOUD_PROVIDER_NAMES.get(provider, provider)}失败", err_msg, is_error=True)
            self.adapter.add_directory_item(f"获取列表失败: {err_msg}", {"action": "root"}, is_folder=False)
            self.adapter.end_of_directory()

    def handle_unsupported_file(self, params):
        """处理点击非媒体格式文件的提示"""
        file_name = params.get("file_name") or "文件"
        ext = params.get("ext") or ""
        self.adapter.show_notification("无法播放", f"{file_name}\n为非媒体格式 ({ext})，无法播放", is_error=True)

    def play_user_pan(self, params):
        """处理个人盘文件解析与播放"""
        self.adapter.log(f"=== PLAY USER PAN TRIGGERED: {params} ===")
        provider = params.get("provider") or ""
        file_id = params.get("file_id") or ""
        file_name = params.get("file_name") or ""
        vod_title = params.get("vod_title") or file_name

        try:
            res = self.api_client.resolve_user_play(provider, file_id, file_name)
            play_url = res.get("play_url")
            if not play_url:
                raise Exception("未获取到播放链接")

            headers = res.get("headers") or {}
            if headers:
                header_parts = []
                for k, v in headers.items():
                    header_parts.append(f"{k}={urllib.parse.quote(v, safe='')}")
                play_url = f"{play_url}|{'&'.join(header_parts)}"

            if vod_title:
                try:
                    profile_dir = self.adapter.get_profile_path()
                    history_mgr = HistoryManager(profile_dir)
                    history_record = {
                        "title": vod_title,
                        "play_params": {
                            "action": "play_user_pan",
                            "provider": provider,
                            "file_id": file_id,
                            "url": play_url
                        },
                        "time": int(time.time())
                    }
                    history_mgr.add_record(history_record)
                except Exception as ex:
                    self.adapter.log(f"保存个人盘播放历史失败: {str(ex)}", "warning")

            list_item = self.adapter.xbmcgui.ListItem(label=vod_title, path=play_url)
            list_item.setProperty('IsPlayable', 'true')
            list_item.setPath(play_url)
            
            cat, _ = get_file_category(file_name or vod_title)
            if cat == "audio":
                info = {
                    "title": vod_title,
                    "artist": vod_title
                }
                list_item.setInfo('music', info)
            else:
                info = {
                    "tvshowtitle": vod_title,
                    "title": vod_title,
                    "mediatype": "episode" if params.get("is_tv") == "1" else "movie"
                }
                list_item.setInfo('video', info)

            self.adapter.set_resolved_url(True, list_item)
        except Exception as e:
            err_msg = str(e)
            self.adapter.log(f"=== PLAY USER PAN ERROR: {err_msg} ===", "error")
            self.adapter.show_notification("播放失败", err_msg, is_error=True)
            self.adapter.set_resolved_url(False, None)

    def start_qr_login(self, provider):
        """弹出扫码登录浮层对话框"""
        try:
            provider = detect_cloud_provider_key(provider)
            if not provider:
                self.adapter.show_notification("扫码登录", "未知网盘类型，无法启动扫码", is_error=True)
                return False
            client_type = None
            client_type_name = ""
            if provider in ("CLOUD115", "115", "7", "115网盘"):
                types_list = [
                    {"key": "alipaymini", "name": "支付宝小程序", "label": "支付宝小程序 [推荐，最不易与常用设备互踢]"},
                    {"key": "wechatmini", "name": "微信小程序", "label": "微信小程序"},
                    {"key": "115android", "name": "Android 客户端", "label": "Android 客户端"},
                    {"key": "115ios", "name": "iOS 客户端", "label": "iOS 客户端"},
                    {"key": "115ipad", "name": "iPad 平板端", "label": "iPad 平板端"},
                    {"key": "tv", "name": "电视端", "label": "电视端 (115 TV 大屏)"},
                    {"key": "web", "name": "网页端", "label": "网页端"},
                ]
                cur_pref = self.api_client.get_115_client_type()
                default_idx = 0
                for i, item in enumerate(types_list):
                    if item["key"] == cur_pref:
                        default_idx = i
                        break
                choices = [item["label"] for item in types_list]
                idx = self.adapter.show_select_dialog("选择 115 扫码端类型", choices, default_idx)
                if idx < 0:
                    return False
                chosen = types_list[idx]
                client_type = chosen["key"]
                client_type_name = chosen["name"]
                self.api_client.set_115_client_type(client_type)

            from qrcode_dialog import QrCodeLoginDialog
            if client_type:
                dialog = QrCodeLoginDialog(provider, self.api_client, client_type=client_type, client_type_name=client_type_name)
            else:
                dialog = QrCodeLoginDialog(provider, self.api_client)
            success = dialog.start()
            if success:
                import time
                time.sleep(0.3)
                self.adapter.refresh_container()
            return success
        except Exception as e:
            self.adapter.log(f"启动扫码登录失败: {str(e)}", "error")
            return False

    def start_manual_login(self, provider):
        """弹出网页手工输入登录浮层对话框"""
        try:
            provider = CLOUD_PROVIDER_KEYS.get(str(provider).strip(), provider)
            from qrcode_dialog import QrCodeLoginDialog
            dialog = QrCodeLoginDialog(provider, self.api_client, manual_mode=True)
            success = dialog.start()
            if success:
                import time
                time.sleep(0.3)
                self.adapter.refresh_container()
            return success
        except Exception as e:
            self.adapter.log(f"启动网页手工输入登录失败: {str(e)}", "error")
            return False

    # --------------------------------------------------------------------------
    # 辅助方法
    # --------------------------------------------------------------------------
    def _render_video_item(self, v, default_mediatype="movie"):
        """
        渲染单个影片/剧集条目。
        default_mediatype: 当接口未给出可判定类型时使用的媒体类型。
        优先依据接口字段自动判定：命中的剧集形态用 "tvshow"，否则用传入的 default_mediatype。
        mediatype 必须是 "movie"/"tvshow"，皮肤 widget 才能读到 fanart/plot/poster；
        使用 "video" 会导致小部件中背景与简介读取不到。
        """
        title = v.get("title")
        remark = v.get("remark")
        label = f"{title} [{remark}]" if remark else title
        pic = get_pic_url(v)
        fanart = get_backdrop_url(v)

        # 判定是否为剧集形态：type_id == 2 / is_series / 存在集数信息
        raw_type = v.get("type_id", v.get("typeId"))
        if raw_type is None:
            raw_type = v.get("type")
        is_tv_item = False
        if isinstance(raw_type, str) and raw_type.strip() in ("2", "tv", "tvshow", "series", "anime", "variety", "short"):
            is_tv_item = True
        elif raw_type in (2,):
            is_tv_item = True
        if v.get("is_series") or v.get("is_tv") or v.get("series_id") or v.get("tv_id"):
            is_tv_item = True
        if v.get("episode_number") or v.get("episode") or v.get("total_episode") or v.get("total_episodes"):
            is_tv_item = True
        if v.get("season_number"):
            is_tv_item = True
        mediatype = "tvshow" if is_tv_item else (default_mediatype or "movie")

        info = {
            "title": title,
            "plot": v.get("content") or v.get("summary") or "",
            "year": v.get("year"),
            "genre": v.get("tags"),
            "director": v.get("director"),
            "cast": [cast.strip() for cast in (v.get("starring") or "").split(",") if cast.strip()],
            "mediatype": mediatype,
        }
        if mediatype == "tvshow":
            info["tvshowtitle"] = title
        art = {}
        if pic:
            art.update({"thumb": pic, "poster": pic, "icon": pic})
        if fanart:
            art["fanart"] = fanart
        art.setdefault("landscape", fanart or pic)
        self.adapter.add_directory_item(
            label,
            {"action": "detail", "id": v.get("id")},
            is_folder=True,
            icon=pic,
            pic=pic,
            fanart=fanart,
            info=info,
            art=art if art else None
        )

    # --------------------------------------------------------------------------
    # 播放历史记录交互方法
    # --------------------------------------------------------------------------
    def show_history(self):
        """显示跨屏双向漫游与本地的播放历史记录 (含 Emby/爆米花漫游) (库视图)"""
        self.adapter.set_library_content("videos")
        profile_dir = self.adapter.get_profile_path()
        history_mgr = HistoryManager(profile_dir)
        local_records = history_mgr.load_history() or []

        # 1. 拉取 Emby / 爆米花跨屏漫游历史
        roaming_items = []
        try:
            res = self.api_client.get_playback_history(limit=50)
            if isinstance(res, list):
                roaming_items = res
        except Exception as ex:
            self.adapter.log(f"[History] 拉取跨屏漫游历史失败: {ex}", "warning")

        # 2. 智能合并去重 (以 movie_id + season + episode 或 url 为唯一键)
        merged_map = {}
        order_keys = []

        base_url_clean = (self.adapter.base_url or "").rstrip('/')

        # 先放入漫游记录
        for r_item in roaming_items:
            m_id = r_item.get("movie_id") or ""
            is_series = bool(r_item.get("is_series"))
            s_num = r_item.get("season_number") or 1
            e_num = r_item.get("episode_number") or 1

            if is_series and m_id:
                dedup_key = f"series_{m_id}_{s_num}_{e_num}"
            elif m_id:
                dedup_key = f"movie_{m_id}"
            else:
                dedup_key = r_item.get("item_id") or r_item.get("url") or ""

            if not dedup_key:
                continue

            merged_map[dedup_key] = {
                "source": "roaming",
                "data": r_item,
                "timestamp": r_item.get("updated_at") or 0
            }
            order_keys.append(dedup_key)

        # 再合并本地记录
        for loc in local_records:
            p_params = loc.get("play_params") or {}
            m_id = p_params.get("movie_id") or loc.get("vod_id") or ""
            is_tv = (p_params.get("is_tv") == "1") or (loc.get("type_id") == 2)
            s_num = p_params.get("season_number")
            e_num = p_params.get("episode_number")
            url = p_params.get("url") or loc.get("url") or ""

            if (is_tv or e_num) and m_id:
                s_val = int(s_num) if (s_num is not None and str(s_num).isdigit()) else 1
                e_val = int(e_num) if (e_num is not None and str(e_num).isdigit()) else 1
                dedup_key = f"series_{m_id}_{s_val}_{e_val}"
            elif m_id:
                dedup_key = f"movie_{m_id}"
            elif url:
                dedup_key = f"url_{url}"
            else:
                dedup_key = f"title_{loc.get('vod_title', '')}_{loc.get('item_name', '')}"

            ts = loc.get("timestamp") or 0

            if dedup_key in merged_map:
                # 已存在漫游记录，若本地时间更新，补全本地信息并更新时间戳
                existing = merged_map[dedup_key]
                if ts > existing["timestamp"]:
                    existing["local_data"] = loc
                    existing["timestamp"] = ts
                else:
                    existing["local_data"] = loc
            else:
                merged_map[dedup_key] = {
                    "source": "local",
                    "data": loc,
                    "timestamp": ts
                }
                order_keys.append(dedup_key)

        # 3. 按时间戳降序排序
        sorted_keys = sorted(order_keys, key=lambda k: merged_map[k]["timestamp"], reverse=True)

        # 4. 顶部展示“清空播放记录”
        if sorted_keys:
            self.adapter.add_library_item(
                "清空播放记录",
                {"action": "clear_history"},
                "history",
                plot="一键清空全部本地播放历史记录（不影响云端漫游记录）。",
                is_folder=False,
            )

        for key in sorted_keys:
            entry = merged_map[key]
            src = entry["source"]

            if src == "roaming":
                r_item = entry["data"]
                local_data = entry.get("local_data") or {}

                vod_title = self._clean_title(r_item.get("title") or "未知片名")
                is_series = bool(r_item.get("is_series"))
                s_num = r_item.get("season_number") or 1
                e_num = r_item.get("episode_number") or 1
                item_title = self._clean_title(r_item.get("item_title") or "")
                resume_sec = float(r_item.get("resume_seconds") or 0.0)
                total_sec = float(r_item.get("total_seconds") or 0.0)
                percentage = int(r_item.get("percentage") or 0)
                played = bool(r_item.get("played"))

                provider_display = self._get_provider_display_name(r_item.get("provider", ""), r_item.get("url", ""))
                tag = f"[{provider_display}]"

                if is_series:
                    ep_text = f"第{s_num}季第{e_num}集"
                    if item_title and item_title not in (ep_text, f"第{e_num}集", f"第{e_num}话", f"EP{e_num}"):
                        name_part = f"{vod_title} - {ep_text} {item_title}"
                    else:
                        name_part = f"{vod_title} - {ep_text}"
                else:
                    name_part = vod_title

                prog_tag = ""
                if played:
                    prog_tag = " [已看]"
                elif resume_sec > 0:
                    rm, rs = divmod(int(resume_sec), 60)
                    if rm >= 60:
                        rh, rm = divmod(rm, 60)
                        t_str = f"{rh:02d}:{rm:02d}:{rs:02d}"
                    else:
                        t_str = f"{rm:02d}:{rs:02d}"
                    if percentage > 0:
                        prog_tag = f" [已播 {t_str} · {percentage}%]"
                    else:
                        prog_tag = f" [已播 {t_str}]"

                label = f"{tag} {name_part}{prog_tag}"

                cover = get_pic_url(r_item.get("cover_url", ""))
                fanart = get_backdrop_url(r_item.get("backdrop_url", ""))
                art = {}
                if cover:
                    art.update({'icon': cover, 'thumb': cover, 'poster': cover})
                if fanart:
                    art['fanart'] = fanart
                art.setdefault('landscape', fanart or cover)

                info = {
                    "title": self._clean_title(label),
                    "tvshowtitle": vod_title if is_series else "",
                    "mediatype": "episode" if is_series else "movie"
                }
                if is_series:
                    info["season"] = s_num
                    info["episode"] = e_num
                if resume_sec > 0:
                    info["resume_time"] = resume_sec
                if total_sec > 0:
                    info["total_time"] = total_sec
                if played:
                    info["played"] = True
                    info["playcount"] = 1

                # 优先使用本地完整的播放参数，否则自动构建起播参数
                play_params = local_data.get("play_params")
                is_folder = local_data.get("is_folder", False)

                if not play_params:
                    url = r_item.get("url") or ""
                    m_id = r_item.get("movie_id") or ""
                    link_id = r_item.get("link_id") or ""
                    link_type = r_item.get("link_type") or "pan"
                    provider_key = r_item.get("provider") or ""
                    password = r_item.get("password") or ""
                    remark = r_item.get("remark") or ""

                    if url:
                        play_params = {
                            "action": "play_private_link",
                            "movie_id": m_id,
                            "link_id": link_id,
                            "link_type": link_type,
                            "provider": provider_key,
                            "url": url,
                            "password": password,
                            "remark": remark,
                            "vod_title": vod_title,
                            "vod_id": m_id,
                            "season_number": s_num if is_series else "",
                            "episode_number": e_num if is_series else "",
                            "episode_title": item_title if is_series else "",
                            "is_tv": "1" if is_series else "0",
                            "pic": cover,
                            "fanart": fanart
                        }
                        if resume_sec > 0:
                            play_params["resume_time"] = resume_sec
                        is_folder = False
                    else:
                        play_params = {
                            "action": "private_movie_links",
                            "movie_id": m_id,
                            "title": vod_title,
                            "pic": cover,
                            "fanart": fanart,
                            "vod_id": m_id
                        }
                        is_folder = True

                context_menu = []
                m_id = r_item.get("movie_id")
                if m_id:
                    context_menu.append(
                        ("查看分集/播放源", f"Container.Update({base_url_clean}?action=private_movie_links&movie_id={m_id}&title={urllib.parse.quote(vod_title)}&pic={urllib.parse.quote(cover)}&fanart={urllib.parse.quote(fanart)}&vod_id={m_id})")
                    )

                self.adapter.add_directory_item(
                    self._clean_title(label),
                    play_params,
                    is_folder=is_folder,
                    is_playable=not is_folder,
                    info=info,
                    art=art if art else None,
                    context_menu=context_menu if context_menu else None
                )

            else:
                # 纯本地播放记录
                rec = entry["data"]
                vod_title = self._clean_title(rec.get("vod_title") or "")
                item_name = self._clean_title(rec.get("item_name") or "")
                label = f"{vod_title} - {item_name}" if (vod_title and item_name) else (vod_title or item_name or "播放记录")
                play_params = rec.get("play_params") or {}
                is_folder = rec.get("is_folder", False)

                art = {}
                if rec.get("pic"):
                    art.update({"icon": rec["pic"], "thumb": rec["pic"], "poster": rec["pic"]})
                if rec.get("fanart"):
                    art["fanart"] = rec["fanart"]
                art.setdefault("landscape", rec.get("fanart") or rec.get("pic"))

                info = {
                    "title": self._clean_title(label),
                    "tvshowtitle": vod_title,
                    "mediatype": "movie"
                }

                self.adapter.add_directory_item(
                    self._clean_title(label),
                    play_params,
                    is_folder=is_folder,
                    is_playable=not is_folder,
                    info=info,
                    art=art if art else None
                )

        if not sorted_keys:
            self.adapter.add_library_item(
                "暂无播放记录", {"action": "root"}, "history",
                plot="还没有播放记录，去首页挑一部开始观看吧。",
                is_folder=False,
            )

        self.adapter.end_of_directory()

    def clear_history(self):
        """清空所有本地与跨屏漫游播放历史"""
        confirm = self.adapter.show_yes_no_dialog("清空历史", "确认清空所有播放记录（含跨屏漫游历史）吗？")
        if confirm:
            profile_dir = self.adapter.get_profile_path()
            history_mgr = HistoryManager(profile_dir)
            history_mgr.clear_history()
            try:
                self.api_client.clear_playback_history()
            except Exception as ex:
                self.adapter.log(f"[History] 清空跨屏漫游历史失败: {ex}", "warning")
            self.adapter.show_notification("播放记录", "播放历史已成功清空")
            self.adapter.refresh_container()

    # --------------------------------------------------------------------------
    # 网页推送分享播放逻辑
    # --------------------------------------------------------------------------
    def show_push_menu(self):
        """显示推送主菜单与推送历史记录 (库视图)"""
        self.adapter.set_library_content("videos")
        self.adapter.add_library_item(
            "新增推送...", {"action": "new_push"}, "push",
            plot="生成推送二维码，用手机扫码把网页上的片子直接推送到电视播放。",
            is_folder=False, mediatype="video",
        )

        profile_dir = self.adapter.get_profile_path()
        push_mgr = PushHistoryManager(profile_dir)
        records = push_mgr.load_history()

        if records:
            self.adapter.add_library_item(
                "清理历史记录", {"action": "clear_push_history"}, "push",
                plot="清空全部推送历史记录。",
                is_folder=False, mediatype="video",
            )

        for rec in records:
            url = rec.get("url")
            code = rec.get("code") or ""
            title = rec.get("title") or url
            pan_name = rec.get("pan_name") or ""
            provider_display = CLOUD_PROVIDER_NAMES.get(pan_name, pan_name or "未知网盘")
            
            label = f"[{provider_display}] {title}"
            is_cloud_down = pan_name in ["magnet", "ed2k"] or (url and (url.startswith("magnet:") or url.startswith("ed2k://")))
            if is_cloud_down:
                self.adapter.add_library_item(
                    label,
                    {
                        "action": "cloud_down_play",
                        "url": url,
                        "title": title,
                        "vod_title": title
                    },
                    "push",
                    plot=f"磁力/电驴资源推送记录，来源：{provider_display}。",
                    is_folder=False, mediatype="video",
                )
            else:
                self.adapter.add_library_item(
                    label,
                    {
                        "action": "list_files",
                        "url": url,
                        "code": code,
                        "pan_name": pan_name,
                        "vod_title": title
                    },
                    "push",
                    plot=f"网盘分享链推送记录，来源：{provider_display}。",
                    is_folder=True, mediatype="movie",
                )

        if not records:
            self.adapter.add_library_item(
                "暂无推送历史记录", {"action": "push_menu"}, "push",
                plot="还没有推送记录，点击“新增推送”生成二维码开始推送。",
                is_folder=False, mediatype="video",
            )

        self.adapter.end_of_directory()

    def start_push_dialog(self):
        """启动网页推送的 QR 浮层对话框"""
        try:
            from qrcode_dialog import PushQrDialog
            dialog = PushQrDialog(self.api_client)
            dialog.start()
            # 推送成功后可能由背景服务直接拉起播放，也可能在此手动刷新容器
            self.adapter.refresh_container()
            return True
        except Exception as e:
            self.adapter.log(f"启动推送浮层失败: {str(e)}", "error")
            return False

    def clear_push_history(self):
        """清理所有网页推送历史记录"""
        confirm = self.adapter.show_yes_no_dialog("清空历史", "确认清空所有推送历史记录吗？")
        if confirm:
            profile_dir = self.adapter.get_profile_path()
            push_mgr = PushHistoryManager(profile_dir)
            push_mgr.clear_history()
            self.adapter.show_notification("推送历史", "推送历史记录已清空")
            self.adapter.refresh_container()

    def _guess_provider_key(self, url):
        lower = url.lower()
        if "aliyundrive" in lower or "alipan" in lower:
            return "ALIYUN"
        if "quark.cn" in lower:
            return "QUARK"
        if "uc.cn" in lower:
            return "UC"
        if "baidu.com" in lower:
            return "BAIDU"
        if "xunlei" in lower:
            return "XUNLEI"
        if "123pan" in lower or "123684" in lower or "123865" in lower or "123278" in lower:
            return "CLOUD123"
        if "115" in lower:
            return "CLOUD115"
        if "139.com" in lower:
            return "CHINA_MOBILE"
        if "189.cn" in lower or "content.21cn.com" in lower:
            return "CHINA_TELECOM"
        if "guangyapan" in lower:
            return "GUANGYA"
        return ""

    def _clean_title(self, text):
        """清洗标题中的高位 Emoji (码点 > 0xFFFF) 与 Dingbats/符号图标 (0x2600-0x27BF, 0x2B00-0x2BFF)"""
        if not text:
            return ""
        cleaned = "".join(
            c for c in text
            if not (
                0x2600 <= ord(c) <= 0x27BF or
                0x2B00 <= ord(c) <= 0x2BFF or
                0x1F000 <= ord(c) <= 0x1FFFF or
                ord(c) > 0xFFFF or
                ord(c) in (0xFE0F, 0xFE0E)
            )
        )
        return cleaned.strip()

    def show_pansou_menu(self):
        """渲染盘搜二级菜单 (库视图)"""
        self.adapter.set_library_content("videos")
        self.adapter.add_library_item(
            "新增搜索", {"action": "pansou_search"}, "pansou",
            plot="输入关键词，聚合搜索多个网盘的公开资源链接。",
            is_folder=True, mediatype="movie",
        )
        self.adapter.add_library_item(
            "设置", {"action": "pansou_settings"}, "settings",
            plot="配置盘搜服务器地址、账号密码以及需要搜索的网盘范围。",
            is_folder=True, mediatype="movie",
        )
        self.adapter.end_of_directory()

    def show_pansou_results(self, query):
        """显示盘搜搜索结果 (库视图)"""
        self.adapter.set_library_content("videos")
        keyword = query
        if not keyword:
            keyword = self.adapter.show_keyboard_input("", "请输入盘搜关键词")
            if not keyword:
                self.adapter.end_of_directory()
                return
            keyword = keyword.strip()

        try:
            res = self.api_client.search_pansou(keyword)
            merged_by_type = res.get("merged_by_type") or {}
            
            pan_name_mapping = {
                "aliyun": "阿里云盘",
                "quark": "夸克网盘",
                "uc": "UC网盘",
                "baidu": "百度网盘",
                "xunlei": "迅雷网盘",
                "123": "123云盘",
                "115": "115网盘",
                "mobile": "移动云盘",
                "tianyi": "天翼云盘",
                "guangya": "光鸭云盘",
                "magnet": "磁力链接",
                "ed2k": "电驴链接"
            }

            has_items = False
            for pan_type, items in merged_by_type.items():
                if not items:
                    continue
                pan_label = pan_name_mapping.get(pan_type.lower(), pan_type)
                for item in items:
                    note = item.get("note") or ""
                    cleaned_note = self._clean_title(note)
                    title = f"[{pan_label}] {cleaned_note}"
                    share_url = item.get("url") or ""
                    code = item.get("password") or ""
                    
                    is_cloud_down = (
                        pan_type.lower() in ("magnet", "ed2k") or
                        (share_url and (share_url.startswith("magnet:") or share_url.startswith("ed2k://")))
                    )
                    if is_cloud_down:
                        self.adapter.add_library_item(
                            title,
                            {
                                "action": "cloud_down_play",
                                "url": share_url,
                                "title": cleaned_note,
                                "vod_title": cleaned_note,
                                "vod_id": "pansou"
                            },
                            "pansou",
                            plot=f"磁力/电驴资源，来源：{pan_label}。点击进入云下载任务。",
                            is_folder=False, mediatype="video",
                            is_playable=True,
                        )
                    else:
                        pan_provider_key = self._guess_provider_key(share_url)
                        self.adapter.add_library_item(
                            title,
                            {
                                "action": "list_files",
                                "url": share_url,
                                "code": code,
                                "pan_name": pan_provider_key,
                                "vod_title": cleaned_note,
                                "vod_id": "pansou"
                            },
                            "pansou",
                            plot=f"网盘分享链接，来源：{pan_label}。点击浏览文件并播放。",
                            is_folder=True, mediatype="movie",
                        )
                    has_items = True
            
            if not has_items:
                self.adapter.show_notification("盘搜", "未找到任何相关资源")
            
            self.adapter.end_of_directory()
        except Exception as e:
            self.adapter.show_notification("盘搜", f"搜索出错: {str(e)}", is_error=True)
            self.adapter.end_of_directory()

    def show_pansou_settings_page(self, params):
        """显示盘搜设置列表页 (库视图)"""
        self.adapter.set_library_content("videos")
        if "addr" not in params:
            config = self.api_client.get_pansou_config()
            addr = config.get("addr") or "https://so.252035.xyz"
            username = config.get("username") or ""
            password = config.get("password") or ""
            pan_types = ",".join(config.get("pan_types") or [])
        else:
            addr = params.get("addr") or "https://so.252035.xyz"
            username = params.get("username") or ""
            password = params.get("password") or ""
            pan_types = params.get("pan_types") or ""

        edit_field = params.get("edit_field")
        if edit_field == "addr":
            new_val = self.adapter.show_keyboard_input(addr, "设置盘搜服务器地址")
            if new_val is not None:
                new_val = new_val.strip()
                addr = new_val if new_val else "https://so.252035.xyz"

        elif edit_field == "username":
            new_val = self.adapter.show_keyboard_input(username, "设置账号 (可选)")
            if new_val is not None:
                username = new_val.strip()

        elif edit_field == "password":
            new_val = self.adapter.show_keyboard_input(password, "设置密码 (可选)", hidden=True)
            if new_val is not None:
                password = new_val.strip()

        elif edit_field == "pan_types":
            ALL_PANS_KODI = [
                ("aliyun", "阿里云盘"),
                ("quark", "夸克网盘"),
                ("uc", "UC网盘"),
                ("baidu", "百度网盘"),
                ("xunlei", "迅雷网盘"),
                ("123", "123云盘"),
                ("115", "115网盘"),
                ("mobile", "移动云盘"),
                ("tianyi", "天翼云盘"),
                ("guangya", "光鸭云盘"),
                ("magnet", "磁力链接"),
                ("ed2k", "电驴链接")
            ]
            current_selected = [p for p in pan_types.split(",") if p]
            preselect = []
            options = [item[1] for item in ALL_PANS_KODI]
            for idx, item in enumerate(ALL_PANS_KODI):
                if len(current_selected) == 0 or item[0] in current_selected:
                    preselect.append(idx)

            selected_indices = self.adapter.show_multiselect_dialog("选择需要搜索的网盘 (默认全选)", options, preselect=preselect)
            if selected_indices is not None and len(selected_indices) > 0:
                selected_pans = [ALL_PANS_KODI[idx][0] for idx in selected_indices]
                pan_types = ",".join(selected_pans)

        display_pass = "******" if password else "未设置"
        selected_pans = [p for p in pan_types.split(",") if p]
        display_pans = f"已选择 {len(selected_pans)} 个网盘" if selected_pans else "全选"

        common_params = {
            "addr": addr,
            "username": username,
            "password": password,
            "pan_types": pan_types
        }

        addr_params = common_params.copy()
        addr_params.update({"action": "pansou_settings", "edit_field": "addr"})
        self.adapter.add_library_item(f"盘搜地址：{addr}", addr_params, "settings",
                                      plot="盘搜服务的接口地址，默认使用公共节点。", is_folder=True, mediatype="movie")

        user_params = common_params.copy()
        user_params.update({"action": "pansou_settings", "edit_field": "username"})
        self.adapter.add_library_item(f"账号：{username or '未设置'}", user_params, "settings",
                                      plot="部分盘搜服务需要登录账号，选填。", is_folder=True, mediatype="movie")

        pass_params = common_params.copy()
        pass_params.update({"action": "pansou_settings", "edit_field": "password"})
        self.adapter.add_library_item(f"密码：{display_pass}", pass_params, "settings",
                                      plot="与账号配套的密码，选填。", is_folder=True, mediatype="movie")

        pans_params = common_params.copy()
        pans_params.update({"action": "pansou_settings", "edit_field": "pan_types"})
        self.adapter.add_library_item(f"搜索网盘：{display_pans}", pans_params, "settings",
                                      plot="选择需要参与搜索的网盘类型，默认全选。", is_folder=True, mediatype="movie")

        save_params = common_params.copy()
        save_params.update({"action": "pansou_settings_save"})
        self.adapter.add_library_item(">> [ 保存并应用设置 ]", save_params, "settings",
                                      plot="保存以上配置并立即生效。", is_folder=True, mediatype="movie")

        self.adapter.end_of_directory()

    def save_pansou_settings(self, params):
        """保存盘搜配置"""
        addr = params.get("addr") or "https://so.252035.xyz"
        username = params.get("username") or ""
        password = params.get("password") or ""
        pan_types = params.get("pan_types") or ""

        pan_types_list = [p for p in pan_types.split(",") if p]
        if not pan_types_list:
            pan_types_list = ["aliyun", "quark", "uc", "baidu", "xunlei", "123", "115", "mobile", "tianyi", "guangya", "magnet", "ed2k"]

        try:
            self.api_client.save_pansou_config(addr, username, password, pan_types_list)
            self.adapter.show_notification("设置", "盘搜配置保存成功")
            self.adapter.update_container({"action": "pansou_menu"}, replace=True)
        except Exception as e:
            self.adapter.show_notification("设置", f"保存失败: {str(e)}", is_error=True)

        self.adapter.end_of_directory()

    def show_share_square(self, params):
        """渲染分享广场页面 (库视图)"""
        self.adapter.set_library_content("videos")
        page = safe_int(params.get("page"), 1)
        page_size = 100
        res = self.api_client.get_shares(page=page, page_size=page_size)
        shares_list = res.get("list") or []
        total = res.get("total") or 0
        page_size = res.get("pageSize") or page_size

        # 顶部固定: 我的收藏
        self.adapter.add_library_item(
            "[我的收藏]", {"action": "share_favorites"}, "favorites",
            plot="查看你在分享广场收藏的分享内容。",
            is_folder=True, mediatype="movie",
        )

        pan_label_mapping = {
            "ALIYUN": "阿里云盘", "QUARK": "夸克网盘", "UC": "UC网盘",
            "BAIDU": "百度网盘", "XUNLEI": "迅雷网盘", "CLOUD123": "123云盘",
            "CLOUD115": "115网盘", "CHINA_MOBILE": "移动云盘",
            "CHINA_TELECOM": "天翼云盘", "GUANGYA": "光鸭云盘"
        }

        for s in shares_list:
            s_id = s.get("id")
            s_url = s.get("url")
            s_title = self._clean_title(s.get("title") or "")
            s_sharer = self._clean_title(s.get("sharer") or "匿名")
            s_pan_type = s.get("panType")
            s_pwd = s.get("pwd") or ""
            s_created_at = (s.get("createdAt") or "")[:10]
            is_fav = s.get("isFavorited", False)

            pan_name = pan_label_mapping.get(s_pan_type, s_pan_type)
            fav_prefix = "[已收藏] " if is_fav else ""
            display_title = f"{fav_prefix}[{pan_name}] {s_title} (分享者: {s_sharer} | {s_created_at})"

            self.adapter.add_library_item(
                display_title,
                {
                    "action": "share_detail",
                    "share_id": s_id,
                    "url": s_url,
                    "title": s_title,
                    "sharer": s_sharer,
                    "pan_name": s_pan_type,
                    "code": s_pwd,
                    "is_favorited": "1" if is_fav else "0"
                },
                "share_square",
                plot=f"分享者：{s_sharer}｜网盘：{pan_name}｜分享时间：{s_created_at or '未知'}。点击查看文件列表。",
                is_folder=True, mediatype="movie",
            )

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
        if page < total_pages:
            self.adapter.add_library_item(
                f"下一页 (第 {page + 1} / {total_pages} 页)",
                {"action": "share_square", "page": page + 1},
                "share_square",
                plot=f"查看分享广场第 {page + 1} 页。",
                is_folder=True, mediatype="movie",
            )
        if page > 1:
            self.adapter.add_library_item(
                f"上一页 (第 {page - 1} / {total_pages} 页)",
                {"action": "share_square", "page": page - 1},
                "share_square",
                plot=f"返回分享广场第 {page - 1} 页。",
                is_folder=True, mediatype="movie",
            )

        self.adapter.end_of_directory()

    def show_share_favorites(self, params):
        """渲染我的收藏列表页面 (库视图)"""
        self.adapter.set_library_content("videos")
        page = safe_int(params.get("page"), 1)
        page_size = 100
        res = self.api_client.get_share_favorites(page=page, page_size=page_size)
        shares_list = res.get("list") or []
        total = res.get("total") or 0
        page_size = res.get("pageSize") or page_size

        pan_label_mapping = {
            "ALIYUN": "阿里云盘", "QUARK": "夸克网盘", "UC": "UC网盘",
            "BAIDU": "百度网盘", "XUNLEI": "迅雷网盘", "CLOUD123": "123云盘",
            "CLOUD115": "115网盘", "CHINA_MOBILE": "移动云盘",
            "CHINA_TELECOM": "天翼云盘", "GUANGYA": "光鸭云盘"
        }

        if not shares_list:
            self.adapter.add_library_item(
                "暂无收藏的分享", {"action": "share_square"}, "favorites",
                plot="还没有收藏任何分享，去分享广场逛逛吧。",
                is_folder=False, mediatype="video",
            )

        for s in shares_list:
            s_id = s.get("id")
            s_url = s.get("url")
            s_title = self._clean_title(s.get("title") or "")
            s_sharer = self._clean_title(s.get("sharer") or "匿名")
            s_pan_type = s.get("panType")
            s_pwd = s.get("pwd") or ""
            s_created_at = (s.get("createdAt") or "")[:10]

            pan_name = pan_label_mapping.get(s_pan_type, s_pan_type)
            display_title = f"[已收藏] [{pan_name}] {s_title} (分享者: {s_sharer} | {s_created_at})"

            self.adapter.add_library_item(
                display_title,
                {
                    "action": "share_detail",
                    "share_id": s_id,
                    "url": s_url,
                    "title": s_title,
                    "sharer": s_sharer,
                    "pan_name": s_pan_type,
                    "code": s_pwd,
                    "is_favorited": "1"
                },
                "favorites",
                plot=f"分享者：{s_sharer}｜网盘：{pan_name}｜分享时间：{s_created_at or '未知'}。点击查看文件列表。",
                is_folder=True, mediatype="movie",
            )

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
        if page < total_pages:
            self.adapter.add_library_item(
                f"下一页 (第 {page + 1} / {total_pages} 页)",
                {"action": "share_favorites", "page": page + 1},
                "favorites",
                plot=f"查看收藏列表第 {page + 1} 页。",
                is_folder=True, mediatype="movie",
            )
        if page > 1:
            self.adapter.add_library_item(
                f"上一页 (第 {page - 1} / {total_pages} 页)",
                {"action": "share_favorites", "page": page - 1},
                "favorites",
                plot=f"返回收藏列表第 {page - 1} 页。",
                is_folder=True, mediatype="movie",
            )

        self.adapter.end_of_directory()

    def show_share_detail(self, params):
        """点入分享后的详情与网盘目录树 (支持按层级下钻与分页)"""
        share_id = params.get("share_id") or ""
        is_fav = params.get("is_favorited") == "1"
        s_title = self._clean_title(params.get("title") or "")
        raw_url = params.get("url") or ""
        s_pwd = params.get("code") or ""
        pan_name = params.get("pan_name") or ""
        parent_file_id = params.get("parent_file_id") or ""
        page = safe_int(params.get("page"), 1)
        page_size = safe_int(params.get("page_size"), 50)

        # 使用 to_share_url 自动还原为带完整域名的标准 share_url
        share_url = to_share_url(raw_url, pan_name)

        # 仅在根层级 (parent_file_id 为空) 且第 1 页时展示顶部“收藏/取消收藏”按钮
        if not parent_file_id and page == 1:
            if is_fav:
                self.adapter.add_directory_item(
                    "[取消收藏]",
                    {"action": "share_toggle_favorite", "share_id": share_id, "op": "unfavorite"},
                    is_folder=False
                )
            else:
                self.adapter.add_directory_item(
                    "[收藏本分享]",
                    {"action": "share_toggle_favorite", "share_id": share_id, "op": "favorite"},
                    is_folder=False
                )

        try:
            # 调取分享专用的单层列表 (flat=0)
            res_data = self.api_client.list_pan_files(share_url, s_pwd, parent_file_id=parent_file_id, flat="0", page=page, page_size=page_size)
            files = res_data.get("files") or []
            total = safe_int(res_data.get("total"), 0)
            total_page = safe_int(res_data.get("total_page"), 1)
            has_more = bool(res_data.get("has_more", False))

            if not files:
                self.adapter.add_directory_item("(无可播放文件)", {"action": "root"}, is_folder=False)
                self.adapter.end_of_directory()
                return

            self.adapter.set_content("episodes")

            if page > 1:
                prev_params = params.copy()
                prev_params["page"] = page - 1
                prev_title = f"上一页 (第 {page - 1}/{total_page} 页)" if total_page > 1 else f"上一页 (第 {page - 1} 页)"
                self.adapter.add_directory_item(
                    prev_title,
                    prev_params,
                    is_folder=True
                )

            for file in files:
                file_id = file.get("file_id") or ""
                file_name = self._clean_title(file.get("file_name") or "")
                is_folder = file.get("is_folder", False)
                size_label = file.get("size_label") or ""

                if is_folder:
                    label = f"[目录] {file_name}"
                    self.adapter.add_directory_item(
                        label,
                        {
                            "action": "share_detail",
                            "share_id": share_id,
                            "is_favorited": "1" if is_fav else "0",
                            "title": s_title,
                            "url": share_url,
                            "code": s_pwd,
                            "pan_name": pan_name,
                            "parent_file_id": file_id,
                        },
                        is_folder=True
                    )
                else:
                    cat, ext = get_file_category(file_name)
                    if cat in ["video", "audio"]:
                        label = file_name
                        if size_label:
                            label += f" [{size_label}]"

                        ep_num = parse_episode_number(file_name) if cat == "video" else 0
                        info = {
                            "tvshowtitle": s_title or file_name,
                            "title": file_name,
                            "mediatype": "episode" if ep_num > 0 else ("song" if cat == "audio" else "video")
                        }
                        if ep_num > 0:
                            info["episode"] = ep_num

                        play_params = {
                            "action": "pan_play",
                            "url": share_url,
                            "code": s_pwd,
                            "file_id": file_id,
                            "pan_name": pan_name,
                            "file_name": file_name,
                            "title": file_name,
                            "vod_title": s_title,
                            "vod_id": f"share_{share_id}",
                            "from_share": "1",
                            "single_file": "1"
                        }

                        self.adapter.add_directory_item(
                            label,
                            play_params,
                            is_folder=False,
                            is_playable=True,
                            info=info
                        )
                    else:
                        tag = "[字幕]" if cat == "subtitle" else ("[文档]" if cat == "document" else ("[压缩包]" if cat == "archive" else ("[图片]" if cat == "image" else "[文件]")))
                        plain_label = f"{tag} {file_name}"
                        if size_label:
                            plain_label += f" [{size_label}]"
                        label = f"[COLOR grey]{plain_label}[/COLOR]"
                        self.adapter.add_directory_item(
                            label,
                            {
                                "action": "ignore"
                            },
                            is_folder=False
                        )

            if has_more or (total_page > 1 and page < total_page):
                next_params = params.copy()
                next_params["page"] = page + 1
                next_title = f"下一页 (第 {page + 1}/{total_page} 页)" if total_page > 1 else f"下一页 (第 {page + 1} 页)"
                self.adapter.add_directory_item(
                    next_title,
                    next_params,
                    is_folder=True
                )

            self.adapter.end_of_directory()

        except Exception as e:
            err_msg = str(e)
            if "请先登录" in err_msg or "未登录" in err_msg:
                provider_key = CLOUD_PROVIDER_KEYS.get(str(pan_name), pan_name)
                display_name = CLOUD_PROVIDER_NAMES.get(provider_key, provider_key)
                confirm = self.adapter.show_yes_no_dialog(
                    "登录提示",
                    f"查看此分享内容需要登录 {display_name}。\n是否立即进行扫码登录？"
                )
                if confirm:
                    success = self.start_qr_login(provider_key)
                    if success:
                        self.show_share_detail(params)
                        return
            self.adapter.show_notification("网盘解析错误", err_msg, is_error=True)
            self.adapter.end_of_directory()

    def handle_share_toggle_favorite(self, params):
        """处理收藏/取消收藏动作"""
        share_id = params.get("share_id")
        op = params.get("op")
        try:
            if op == "favorite":
                res = self.api_client.favorite_share(share_id)
                if res and res.get("code") == "SUCCESS":
                    self.adapter.show_notification("分享广场", "收藏成功")
                else:
                    self.adapter.show_notification("分享广场", f"收藏失败: {res.get('error', '未知错误')}", is_error=True)
            else:
                res = self.api_client.unfavorite_share(share_id)
                if res and res.get("code") == "SUCCESS":
                    self.adapter.show_notification("分享广场", "已取消收藏")
                else:
                    self.adapter.show_notification("分享广场", f"操作失败: {res.get('error', '未知错误')}", is_error=True)
            self.adapter.refresh_container()
        except Exception as e:
            self.adapter.show_notification("分享广场", f"操作失败: {str(e)}", is_error=True)

    # -------------------------------------------------------------
    # 私有媒体库与共享媒体库 VFS 目录树
    # -------------------------------------------------------------

    def show_private_libraries(self):
        """展示所有私有媒体库 (库视图)"""
        self.adapter.set_library_content("videos")
        try:
            libs = self.api_client.get_private_libraries()

            self.adapter.add_library_item(
                "导入共享媒体库 (输入 6 位分享码)",
                {"action": "input_import_share_code"},
                "shared_libraries",
                plot="输入 6 位分享码，一键把别人的公开媒体库导入到本地。",
                is_folder=False
            )
            self.adapter.add_library_item(
                "我的收藏",
                {"action": "my_favorites"},
                "favorites",
                plot="查看你收藏的影片，跨库汇总，随时回看。",
                is_folder=True
            )

            if not libs:
                self.adapter.add_library_item(
                    "暂无私有库 (请通过手机/电脑扫码打开 Web 管理台创建)",
                    {"action": "ignore"},
                    "private_libraries",
                    plot="还没有创建媒体库，可扫码进入 Web 管理台新建。",
                    is_folder=False
                )
                self.adapter.end_of_directory()
                return

            for lib in libs:
                lib_id = lib.get("id")
                name = self._clean_title(lib.get("name", "未命名媒体库"))
                cover = get_pic_url(lib.get("cover_url", ""))
                share_type = safe_int(lib.get("share_type"), 0)
                item_count = safe_int(lib.get("item_count"), 0)
                creator = self._clean_title(lib.get("creator_name", "我"))

                share_code = lib.get("share_code")
                type_tag = "[自建]"
                if share_type == 2:
                    type_tag = "[持续更新]"
                elif share_type == 1:
                    type_tag = "[快照]"
                elif share_code:
                    type_tag = "[自建·已发布]"

                title = f"{type_tag} {name} ({item_count} 部影片)"
                if share_type == 2:
                    title += f" [作者: {creator}]"

                plot = f"共 {item_count} 部影片。"
                if share_type == 2:
                    plot += f" 持续更新型订阅库，作者：{creator}。"
                elif share_type == 1:
                    plot += " 一次性快照库，导入后内容固定。"
                else:
                    plot += " 自建媒体库，可自由增删影片与播放源。"
                if share_code:
                    plot += f" 分享码：{share_code}。"

                context_menu = [
                    (
                        "海报墙同步设置",
                        f"RunPlugin({self.adapter.build_url({'action': 'private_library_poster_setting', 'library_id': lib_id, 'library_name': name})})"
                    )
                ]
                if share_type == 2:
                    context_menu.append((
                        "转为自建媒体库 (解除订阅)",
                        f"RunPlugin({self.adapter.build_url({'action': 'detach_private_library', 'library_id': lib_id, 'library_name': name})})"
                    ))

                lib_enabled = self.adapter.library_view_enabled() if hasattr(self.adapter, "library_view_enabled") else True
                lib_kw = {"is_folder": True, "context_menu": context_menu}
                if lib_enabled:
                    lib_art = {"icon": cover, "poster": cover, "thumb": cover} if cover else {"icon": self.adapter.node_image("private_libraries", "thumb"), "poster": self.adapter.node_image("private_libraries", "thumb"), "thumb": self.adapter.node_image("private_libraries", "thumb")}
                    lib_art["fanart"] = self.adapter.node_image("private_libraries", "fanart")
                    lib_art["landscape"] = lib_art["fanart"]
                    lib_kw["info"] = {"title": name, "plot": plot, "mediatype": "movie"}
                    lib_kw["art"] = lib_art
                else:
                    lib_kw["art"] = {"icon": cover, "poster": cover, "thumb": cover} if cover else None

                self.adapter.add_directory_item(
                    self._clean_title(title),
                    {
                        "action": "private_library_movies",
                        "library_id": lib_id,
                        "library_name": name,
                        "share_type": share_type
                    },
                    **lib_kw
                )

            self.adapter.end_of_directory()
        except Exception as e:
            self.adapter.show_notification("私有媒体库", f"读取失败: {str(e)}", is_error=True)
            self.adapter.end_of_directory()

    def show_private_library_movies(self, params):
        """展示私有库内的影片列表 (支持高效分页与上下页导航，默认每页 30 部以保障电视端极致秒开)"""
        import time
        t_start = time.time()
        library_id = params.get("library_id")
        lib_name = params.get("library_name", "媒体库")
        share_type = safe_int(params.get("share_type"), 0)
        page = safe_int(params.get("page"), 1)
        page_size = safe_int(params.get("page_size"), 100)

        self.adapter.log(f"[PERF] >>> show_private_library_movies: lib={library_id}, page={page}, page_size={page_size}")

        self.adapter.set_library_content("movies")

        try:
            # 1. 顶部常驻项 (仅在第 1 页展示顶部控制台，避免翻页后被杂项挤占空间)
            if page == 1:
                cur_poster_mode = safe_int(params.get("poster_mode"), -1)
                if cur_poster_mode < 0:
                    lib_info = self.api_client.get_private_library(library_id)
                    cur_poster_mode = safe_int(lib_info.get("poster_mode"), 0)
                mode_text = "完整海报墙" if cur_poster_mode == 2 else ("极速海报墙" if cur_poster_mode == 1 else "未启用")
                self.adapter.add_library_item(
                    f"[海报墙: {mode_text}] 点击更改设置 / 立即同步",
                    {
                        "action": "private_library_poster_setting",
                        "library_id": library_id,
                        "library_name": lib_name
                    },
                    "settings",
                    plot="调整本媒体库的海报墙模式（完整/极速），并可立即触发一次同步。",
                    is_folder=False,
                    mediatype="movie",
                )

                # 如果是持续更新型订阅库，提供手动增量同步入口
                if share_type == 2:
                    self.adapter.add_library_item(
                        "检查并同步最新影片与链接",
                        {"action": "sync_private_library", "library_id": library_id},
                        "settings",
                        plot="从云端检查该订阅库是否有新增影片或失效链接，并增量同步到本地。",
                        is_folder=False,
                        mediatype="movie",
                    )
                    self.adapter.add_library_item(
                        "转为自建媒体库 (解除订阅)",
                        {
                            "action": "detach_private_library",
                            "library_id": library_id,
                            "library_name": lib_name
                        },
                        "settings",
                        plot="解除订阅关系，将其转为普通自建媒体库，后续不再自动更新。",
                        is_folder=False,
                        mediatype="movie",
                    )

                # 刷新影片列表
                self.adapter.add_library_item(
                    "刷新影片列表",
                    {
                        "action": "refresh_private_library_movies",
                        "library_id": library_id,
                        "library_name": lib_name,
                        "share_type": share_type
                    },
                    "settings",
                    plot="重新从本地数据库读取影片列表并刷新当前页面。",
                    is_folder=False,
                    mediatype="movie",
                )

            # 2. 上一页导航 (翻页后置顶)
            if page > 1:
                prev_params = {
                    "action": "private_library_movies",
                    "library_id": library_id,
                    "library_name": lib_name,
                    "share_type": share_type,
                    "page": page - 1
                }
                if "page_size" in params:
                    prev_params["page_size"] = page_size
                self.adapter.add_library_item(
                    f"上一页 (第 {page - 1} 页)", prev_params,
                    "private_libraries",
                    plot=f"返回第 {page - 1} 页继续浏览。",
                    is_folder=True,
                    mediatype="movie",
                )

            t_before_fetch = time.time()
            paged_res = self.api_client.get_private_library_movies_paged(library_id, page=page, page_size=page_size)
            t_after_fetch = time.time()
            self.adapter.log(f"[PERF] 1. 数据接口响应: 耗时 {(t_after_fetch - t_before_fetch)*1000:.1f}ms")

            if isinstance(paged_res, dict) and "items" in paged_res and paged_res["items"]:
                movies = paged_res.get("items") or []
                total = paged_res.get("total") or len(movies)
            else:
                # 兼容旧调用或未指定 items 结构的环境
                raw = self.api_client.get_private_library_movies(library_id)
                if isinstance(raw, dict) and "items" in raw:
                    movies = raw.get("items") or []
                    total = raw.get("total") or len(movies)
                elif isinstance(raw, list) and raw:
                    movies = raw
                    total = len(movies)
                else:
                    movies = paged_res.get("items") if isinstance(paged_res, dict) else []
                    total = paged_res.get("total", 0) if isinstance(paged_res, dict) else 0

            if not movies and page == 1:
                self.adapter.add_library_item(
                    "库内暂无影片 (可通过 Web 管理端搜索添加或 Excel 导入)",
                    {"action": "ignore"},
                    "private_libraries",
                    plot="这个媒体库还是空的，可以在 Web 管理台搜索添加影片，或用 Excel 批量导入。",
                    is_folder=False,
                    mediatype="movie",
                )
                self.adapter.end_of_directory()
                return

            t_before_render = time.time()
            base_url_clean = (self.adapter.base_url or "").rstrip('/')
            for m in movies:
                self._render_private_movie_item(m, base_url_clean=base_url_clean)

            t_after_render = time.time()
            self.adapter.log(f"[PERF] 2. 构造条目耗时: {(t_after_render - t_before_render)*1000:.1f}ms (渲染 {len(movies)} 部影片)")

            # 3. 下一页导航
            if total > page * page_size:
                next_params = {
                    "action": "private_library_movies",
                    "library_id": library_id,
                    "library_name": lib_name,
                    "share_type": share_type,
                    "page": page + 1
                }
                if "page_size" in params:
                    next_params["page_size"] = page_size
                self.adapter.add_library_item(
                    f"下一页 (第 {page + 1} 页)", next_params,
                    "private_libraries",
                    plot=f"继续浏览第 {page + 1} 页影片。",
                    is_folder=True,
                    mediatype="movie",
                )

            self.adapter.end_of_directory()
            t_finish = time.time()
            self.adapter.log(f"[PERF] <<< show_private_library_movies 完成: 总耗时 {(t_finish - t_start)*1000:.1f}ms")
        except Exception as e:
            self.adapter.show_notification("私有媒体库", f"读取影片失败: {str(e)}", is_error=True)
            self.adapter.end_of_directory()

    def _mark_playback_started(self, movie_id=None, vod_id=None, season_number=None, episode_number=None, is_tv=False, link_id=None):
        """记录当前起播的影片/分集 ID，供后台 service 监听并向 Go 后端与 Emby 上报播放进度"""
        try:
            m_id = str(movie_id or "").strip()
            v_id = str(vod_id or "").strip()
            l_id = str(link_id or "").strip()

            # 核心拦截：非私有库播放的视频(没有movie_id，只有vod_id)，不要上报进度给 Emby
            # 只有具备显式 movie_id、link_id 或 vod_id 以 mov_ / ep_mov_ 开头时才被视为私有库项目
            base_id = ""
            if m_id:
                base_id = m_id
            elif v_id.startswith("mov_") or v_id.startswith("ep_mov_"):
                base_id = v_id
            elif l_id:
                base_id = v_id if v_id else l_id

            if not base_id:
                # 非私有库视频起播：显式清除旧窗口属性，避免上一部私有库视频残留
                if self.adapter.xbmcgui:
                    try:
                        self.adapter.xbmcgui.Window(10000).clearProperty("mv_current_movie_id")
                    except Exception:
                        pass
                self.adapter.log(f"[Playback] Skip marking playback for non-private video (vod_id='{v_id}', no movie_id)", "debug")
                return

            s_val = None
            if season_number is not None and str(season_number).strip() != "":
                try:
                    s_val = int(season_number)
                except (ValueError, TypeError):
                    pass

            e_val = None
            if episode_number is not None and str(episode_number).strip() != "":
                try:
                    e_val = int(episode_number)
                except (ValueError, TypeError):
                    pass

            if base_id.startswith("ep_"):
                target_id = base_id
            elif is_tv and e_val is not None and e_val > 0:
                s_num = s_val if (s_val is not None and s_val >= 0) else 1
                e_num = e_val
                target_id = f"ep_{base_id}_{s_num}_{e_num}"
            else:
                target_id = base_id

            if target_id and self.adapter.xbmcgui:
                curr_prop = self.adapter.xbmcgui.Window(10000).getProperty("mv_current_movie_id")
                # 防退化保护：仅在同为剧集上下文时，若现有属性已是精细分集 ID (ep_...)，且本次传入的只是粗粒度剧集总ID，跳过覆盖
                if curr_prop and curr_prop.startswith("ep_") and not target_id.startswith("ep_") and is_tv:
                    self.adapter.log(f"[Playback] Retain fine-grained target_id '{curr_prop}', skip coarse-grained overwrite '{target_id}'", "info")
                    return
                self.adapter.xbmcgui.Window(10000).setProperty("mv_current_movie_id", target_id)
                self.adapter.log(f"[Playback] Marked current playing target_id: {target_id}", "info")
        except Exception as ex:
            self.adapter.log(f"[Playback] Failed to mark playback target: {ex}", "warning")

    def _render_private_movie_item(self, m, base_url_clean=None, is_favorite_page=False):
        """渲染单个私有库影片卡片（支持单链接直达、选集树、断点续播注入及右键收藏菜单）"""
        if not base_url_clean:
            base_url_clean = (self.adapter.base_url or "").rstrip('/')

        movie_id = m.get("id")
        title = self._clean_title(m.get("title", "未命名影片"))
        year = m.get("year", "")
        cover = get_pic_url(m.get("cover_url", ""))
        backdrop = get_backdrop_url(m.get("backdrop_url", ""))
        summary = m.get("summary", "")
        genres = m.get("genres", "")
        directors = m.get("directors", "")
        vod_id = m.get("vod_id", movie_id)
        links = m.get("links", [])
        link_count = len(links)
        is_explicit_movie = (m.get("type_id") == 1)
        is_tv = (m.get("type_id") == 2)
        season_set = set()
        ep_set = set()
        has_multi_season_or_ep = False
        for lk in links:
            s_raw = lk.get("season_number")
            s_num = s_raw if (s_raw is not None and s_raw >= 0) else 1
            e_raw = lk.get("episode_number")
            e_num = e_raw if (e_raw is not None and e_raw > 0) else 1
            if (s_raw is not None and s_raw > 1) or (e_raw is not None and e_raw > 1) or (s_raw == 0 and e_raw is not None and e_raw > 0):
                has_multi_season_or_ep = True
            season_set.add(s_num)
            ep_set.add((s_num, e_num))

        if not is_explicit_movie and (has_multi_season_or_ep or len(season_set) > 1 or len(ep_set) > 1):
            is_tv = True

        total_seasons = len(season_set) if links else 0
        total_episodes = len(ep_set) if links else 0

        display_title = f"{title}"
        if year:
            display_title += f" ({year})"
        if is_tv:
            if total_seasons > 0 and total_episodes > 0:
                display_title += f" [全 {total_seasons} 季全 {total_episodes} 集]"
            else:
                display_title += f" [剧集·{link_count} 源]"
        elif link_count > 1:
            display_title += f" [{link_count} 源]"

        # 获取播放状态与断点进度 (安全防御 Mock 与异常)
        pb_status = {}
        try:
            res = self.api_client.get_playback_status(movie_id)
            if isinstance(res, dict):
                pb_status = res
        except Exception:
            pass

        resume_sec = 0.0
        if "resume_seconds" in pb_status and isinstance(pb_status["resume_seconds"], (int, float)):
            resume_sec = float(pb_status["resume_seconds"])
        is_fav = is_favorite_page or (pb_status.get("is_favorite") is True)

        if is_tv and pb_status.get("recent_episode"):
            r_ep = pb_status.get("recent_episode")
            r_sec = pb_status.get("resume_seconds") or 0.0
            if pb_status.get("played"):
                display_title += f" [已看第{r_ep}集]"
            elif r_sec > 0:
                rm, rs = divmod(int(r_sec), 60)
                if rm >= 60:
                    rh, rm = divmod(rm, 60)
                    t_str = f"{rh:02d}:{rm:02d}:{rs:02d}"
                else:
                    t_str = f"{rm:02d}:{rs:02d}"
                display_title += f" [看至第{r_ep}集 {t_str}]"

        has_user_pan = bool(m.get("has_user_pan")) or any(l.get("link_type") == "user_pan" or (l.get("url") or "").startswith("user_pan://") for l in links)
        if has_user_pan:
            display_title += " [个人盘]"

        lib_enabled = self.adapter.library_view_enabled() if hasattr(self.adapter, "library_view_enabled") else True
        info = {
            "title": title,
            "plot": summary,
            "year": int(year) if str(year).isdigit() else None,
            "genre": genres,
            "director": directors
        }
        if lib_enabled:
            info["mediatype"] = "tvshow" if is_tv else "movie"
        if resume_sec > 0:
            info["resume_time"] = resume_sec
        if "total_seconds" in pb_status and isinstance(pb_status["total_seconds"], (int, float)) and pb_status["total_seconds"] > 0:
            info["total_time"] = float(pb_status["total_seconds"])
        if pb_status.get("played") is True:
            info["played"] = True
            info["playcount"] = 1

        if m.get("actors"):
            info["cast"] = [a.strip() for a in re.split(r"[,/，、]", str(m["actors"])) if a.strip()]
        art = {}
        if cover:
            art["poster"] = cover
            art["thumb"] = cover
            art["icon"] = cover
        if backdrop:
            art["fanart"] = backdrop
        if lib_enabled:
            art.setdefault("landscape", backdrop or cover)

        fav_label = "取消收藏" if is_fav else "加入收藏"
        fav_context = (fav_label, f"RunPlugin({base_url_clean}?action=toggle_favorite&movie_id={movie_id})")
        copy_context = ("复制到自建媒体库", f"RunPlugin({base_url_clean}?action=copy_private_movie&movie_id={movie_id}&title={urllib.parse.quote(title)})")

        # 仅有 1 条链接且非电视剧时，直接直达播放或展开网盘选集，避免多层点击
        if link_count == 1 and not is_tv:
            s_link = links[0]
            s_link_id = s_link.get("id")
            s_link_type = s_link.get("link_type", "pan")
            s_provider = s_link.get("provider", "")
            s_url = s_link.get("url", "")
            s_password = s_link.get("password", "")
            s_remark = self._clean_title(s_link.get("remark", "").strip())

            is_pan = (s_link_type == "pan") or any(p in s_url.lower() for p in [
                "quark.cn", "alipan.com", "aliyundrive.com", "115.com",
                "pan.baidu.com", "pan.xunlei.com", "disk.uc.cn",
                "123pan.com", "123684.com", "123865.com",
                "yun.139.com", "cloud.189.cn", "content.21cn.com", "guangyapan.com"
            ])

            context_menu = [
                ("查看/管理所有播放源", f"Container.Update({base_url_clean}?action=private_movie_links&movie_id={movie_id}&title={urllib.parse.quote(title)}&pic={urllib.parse.quote(cover)}&fanart={urllib.parse.quote(backdrop)}&vod_id={vod_id})"),
                copy_context
            ]
            if is_favorite_page:
                context_menu.append(fav_context)

            s_pan_key = CLOUD_PROVIDER_KEYS.get(str(s_provider or "").strip(), s_provider)
            if is_pan and not is_single_file_url(s_url):
                self.adapter.add_directory_item(
                    self._clean_title(display_title),
                    {
                        "action": "list_files",
                        "url": s_url,
                        "code": s_password,
                        "pan_name": s_pan_key,
                        "vod_title": title,
                        "vod_id": vod_id,
                        "pic": cover,
                        "fanart": backdrop
                    },
                    is_folder=True,
                    info=info,
                    art=art,
                    context_menu=context_menu
                )
            else:
                single_play_params = {
                    "action": "play_private_link",
                    "link_id": s_link_id,
                    "link_type": s_link_type,
                    "provider": s_provider,
                    "url": s_url,
                    "password": s_password,
                    "remark": s_remark,
                    "vod_title": title,
                    "vod_id": vod_id,
                    "pic": cover,
                    "fanart": backdrop
                }
                if s_link.get("file_id"):
                    single_play_params["file_id"] = s_link["file_id"]
                if s_link.get("file_name"):
                    single_play_params["file_name"] = s_link["file_name"]
                if s_link.get("file_size"):
                    single_play_params["file_size"] = s_link["file_size"]

                self.adapter.add_directory_item(
                    self._clean_title(display_title),
                    single_play_params,
                    is_folder=False,
                    is_playable=True,
                    info=info,
                    art=art,
                    context_menu=context_menu
                )
        else:
            multi_params = {
                "action": "private_movie_links",
                "movie_id": movie_id,
                "title": title,
                "pic": cover,
                "fanart": backdrop,
                "vod_id": vod_id,
                "year": year
            }
            m_context = [copy_context]
            if is_favorite_page:
                m_context.append(fav_context)
            self.adapter.add_directory_item(
                self._clean_title(display_title),
                multi_params,
                is_folder=True,
                info=info,
                art=art,
                context_menu=m_context
            )

    def show_my_favorites(self, params):
        """渲染我的收藏影片列表 (库视图)"""
        self.adapter.set_library_content("movies")
        library_id = params.get("library_id") if params else None
        fav_movies = self.api_client.get_user_favorites(library_id=library_id)
        if not fav_movies:
            self.adapter.add_library_item(
                "暂无收藏影片 (可在私有库影片菜单中右键加入收藏)",
                {"action": "ignore"},
                "favorites",
                plot="还没有收藏任何影片，在私有库影片上右键即可加入收藏。",
                is_folder=False, mediatype="movie",
            )
            self.adapter.end_of_directory()
            return

        base_url_clean = (self.adapter.base_url or "").rstrip('/')
        for m in fav_movies:
            self._render_private_movie_item(m, base_url_clean=base_url_clean, is_favorite_page=True)

        self.adapter.end_of_directory()

    def handle_toggle_favorite(self, params):
        """切换私有库影片的收藏状态"""
        movie_id = params.get("movie_id")
        if not movie_id:
            return
        res = self.api_client.toggle_user_favorite(movie_id)
        is_fav = res.get("is_favorite", False)
        msg = "已加入收藏" if is_fav else "已从收藏中移除"
        self.adapter.show_notification("个人收藏", msg)
        self.adapter.refresh_container()

    def _get_provider_display_name(self, provider, url=""):
        """将 provider 数字ID或英文KEY或URL映射为标准中文网盘名"""
        p_str = str(provider or "").strip()
        if p_str in CLOUD_PROVIDER_NAMES:
            return CLOUD_PROVIDER_NAMES[p_str]

        prov_key = detect_cloud_provider_key(provider, url)
        if prov_key and prov_key in CLOUD_PROVIDER_NAMES:
            return CLOUD_PROVIDER_NAMES[prov_key]

        return p_str if p_str else "网盘"

    def show_private_movie_links(self, params):
        """展示影片下的所有播放链接"""
        movie_id = params.get("movie_id")
        title = self._clean_title(params.get("title", "未知片名"))
        pic = get_pic_url(params.get("pic", ""))
        fanart = get_backdrop_url(params.get("fanart", ""))
        vod_id = params.get("vod_id", movie_id)
        year = params.get("year", "")

        try:
            links = self.api_client.get_private_movie_links(movie_id)
            if not links:
                self.adapter.add_directory_item(
                    "该影片暂无播放链接 (可通过 Web 端添加)",
                    {"action": "ignore"},
                    is_folder=False
                )
                self.adapter.end_of_directory()
                return

            # 1. 智能判定当前链接集合是否属于电视剧/剧集
            is_explicit_movie = (params.get("is_tv") == "0") or (str(params.get("type_id")) == "1")
            is_tv = (params.get("is_tv") == "1") or (str(params.get("type_id")) == "2")
            if not is_tv and not is_explicit_movie:
                for lk in links:
                    s_chk = lk.get("season_number")
                    e_chk = lk.get("episode_number")
                    t_chk = (lk.get("episode_title") or "").strip()
                    if (s_chk is not None and s_chk > 1) or (e_chk is not None and e_chk > 1) or (s_chk == 0 and e_chk is not None and e_chk > 0) or t_chk:
                        is_tv = True
                        break
                if not is_tv and len(links) > 1:
                    distinct_se = set((lk.get("season_number", 1), lk.get("episode_number", 1)) for lk in links)
                    if len(distinct_se) > 1:
                        is_tv = True

            # 批量预查所有分集/链接的播放进度与断点
            batch_status_map = {}
            if movie_id:
                ep_ids_to_query = []
                for lk in links:
                    sn = lk.get("season_number")
                    sn_val = sn if (sn is not None and sn >= 0) else 1
                    en = lk.get("episode_number")
                    en_val = en if (en is not None and en > 0) else 1
                    ep_ids_to_query.append(f"ep_{movie_id}_{sn_val}_{en_val}")
                ep_ids_to_query.append(movie_id)
                try:
                    res_map = self.api_client.get_batch_playback_status(ep_ids_to_query)
                    if isinstance(res_map, dict):
                        batch_status_map = res_map
                except Exception:
                    pass

            for idx, l in enumerate(links, 1):
                link_id = l.get("id")
                link_type = l.get("link_type", "pan")
                provider = l.get("provider", "")
                url = l.get("url", "")
                password = l.get("password", "")
                remark = self._clean_title(l.get("remark", "").strip())

                p_display = self._get_provider_display_name(provider, url)
                tag = f"[{p_display}]"
                if link_type == "user_pan" or url.startswith("user_pan://"):
                    p_clean = p_display.replace("[", "").replace("]", "").replace("网盘", "").replace("云盘", "")
                    tag = f"[个人{p_clean}]"
                elif link_type == "magnet":
                    tag = "[磁力]"
                elif link_type == "ed2k":
                    tag = "[电驴]"
                elif link_type == "http":
                    tag = "[直链]"

                ep_prefix = ""
                s_raw = l.get("season_number")
                s_num = s_raw if (s_raw is not None and s_raw >= 0) else 1
                e_raw = l.get("episode_number")
                e_num = e_raw if (e_raw is not None and e_raw > 0) else 1
                ep_title = self._clean_title(l.get("episode_title", "").strip())
                is_item_tv = bool(is_tv or (e_raw is not None and e_raw > 0) or (s_raw is not None and s_raw > 1) or (s_raw == 0) or ep_title)

                # 只要当前为剧集，或者链接显式包含分季/分集/单集标题信息，统一添加 [第N季第N集] 标识（第一项也完整添加）
                if is_item_tv:
                    ep_text = f"第{s_num}季第{e_num}集"
                    clean_ep_t = ep_title
                    if clean_ep_t and (clean_ep_t.replace(" ", "") in (f"第{e_num}集", f"第{e_num}话", f"E{e_num}", f"EP{e_num}", f"Episode{e_num}", f"episode{e_num}")):
                        clean_ep_t = ""
                    if clean_ep_t:
                        ep_prefix = f"[{ep_text} {clean_ep_t}] "
                    else:
                        ep_prefix = f"[{ep_text}] "

                ep_id = f"ep_{movie_id}_{s_num}_{e_num}"
                ep_status = batch_status_map.get(ep_id) or batch_status_map.get(movie_id) or {}
                ep_resume = float(ep_status.get("resume_seconds") or 0.0)
                ep_played = bool(ep_status.get("played"))

                progress_tag = ""
                if ep_played:
                    progress_tag = " [已看]"
                elif ep_resume > 0:
                    rm, rs = divmod(int(ep_resume), 60)
                    if rm >= 60:
                        rh, rm = divmod(rm, 60)
                        t_str = f"{rh:02d}:{rm:02d}:{rs:02d}"
                    else:
                        t_str = f"{rm:02d}:{rs:02d}"
                    pct = int(ep_status.get("percentage") or 0)
                    if pct > 0:
                        progress_tag = f" [已播 {t_str} · {pct}%]"
                    else:
                        progress_tag = f" [已播 {t_str}]"

                link_title = f"{idx}. {ep_prefix}{tag} {remark if remark else url}{progress_tag}"

                link_info = {
                    "title": self._clean_title(link_title),
                    "tvshowtitle": title if is_item_tv else "",
                    "mediatype": "episode" if is_item_tv else "video"
                }
                if is_item_tv:
                    link_info["season"] = s_num
                    link_info["episode"] = e_num
                if ep_resume > 0:
                    link_info["resume_time"] = ep_resume
                if ep_played:
                    link_info["played"] = True
                    link_info["playcount"] = 1

                is_pan = (link_type == "pan") or any(p in url.lower() for p in [
                    "quark.cn", "alipan.com", "aliyundrive.com", "115.com",
                    "pan.baidu.com", "pan.xunlei.com", "disk.uc.cn",
                    "123pan.com", "123684.com", "123865.com",
                    "yun.139.com", "cloud.189.cn", "content.21cn.com", "guangyapan.com"
                ])

                pan_key = CLOUD_PROVIDER_KEYS.get(str(provider or "").strip(), provider)

                if is_pan and not is_single_file_url(url):
                    # 网盘分享链接作为目录展示文件/集数选集列表
                    item_params = {
                        "action": "list_files",
                        "url": url,
                        "code": password,
                        "pan_name": pan_key,
                        "vod_title": title,
                        "vod_id": vod_id,
                        "pic": pic,
                        "fanart": fanart
                    }
                    if is_item_tv:
                        item_params["season_number"] = s_num
                        item_params["episode_number"] = e_num
                        item_params["is_tv"] = "1"
                        if ep_title:
                            item_params["episode_title"] = ep_title
                        if remark:
                            item_params["remark"] = remark
                    item_kwargs = {
                        "is_folder": True,
                        "art": {"icon": pic, "poster": pic, "fanart": fanart} if pic else None
                    }
                    if ep_resume > 0 or ep_played:
                        item_kwargs["info"] = link_info
                    self.adapter.add_directory_item(
                        self._clean_title(link_title),
                        item_params,
                        **item_kwargs
                    )
                else:
                    # 磁力/ED2K/直链作为可播放项目
                    play_params = {
                        "action": "play_private_link",
                        "link_id": link_id,
                        "link_type": link_type,
                        "provider": provider,
                        "url": url,
                        "password": password,
                        "remark": remark,
                        "vod_title": title,
                        "vod_id": vod_id,
                        "pic": pic,
                        "fanart": fanart
                    }
                    if ep_resume > 0:
                        play_params["resume_time"] = ep_resume
                    if l.get("file_id"):
                        play_params["file_id"] = l["file_id"]
                    if l.get("file_name"):
                        play_params["file_name"] = l["file_name"]
                    if l.get("file_size"):
                        play_params["file_size"] = l["file_size"]
                    if is_item_tv:
                        play_params["season_number"] = s_num
                        play_params["episode_number"] = e_num
                        if ep_title:
                            play_params["episode_title"] = ep_title
                        play_params["is_tv"] = "1"
                    play_kwargs = {
                        "is_folder": False,
                        "is_playable": True,
                        "art": {"icon": pic, "poster": pic, "fanart": fanart} if pic else None
                    }
                    if ep_resume > 0 or ep_played:
                        play_kwargs["info"] = link_info
                    self.adapter.add_directory_item(
                        self._clean_title(link_title),
                        play_params,
                        **play_kwargs
                    )

            self.adapter.end_of_directory()
        except Exception as e:
            self.adapter.show_notification("私有媒体库", f"读取链接失败: {str(e)}", is_error=True)
            self.adapter.end_of_directory()

    def play_private_link(self, params):
        """统一分发播放私有库链接"""
        raw_type = params.get("link_type") or params.get("type") or ""
        provider = params.get("provider", "")
        url = params.get("url", "")
        password = params.get("password") or params.get("code") or ""
        vod_title = params.get("vod_title", "")
        vod_id = params.get("vod_id", "")
        remark = params.get("remark", "")
        pic = params.get("pic", "")
        fanart = params.get("fanart", "")
        season_number = params.get("season_number")
        episode_number = params.get("episode_number")
        episode_title = params.get("episode_title", "")
        type_id_param = params.get("type_id")
        is_tv = (params.get("is_tv") == "1")
        if type_id_param == "1":
            is_tv = False

        if not url:
            self.adapter.show_notification("播放失败", "链接为空", is_error=True)
            self.adapter.set_resolved_url(False, None)
            return

        display_title, s_num, e_num, is_tv_item = build_play_display_title(
            vod_title=vod_title,
            season_number=season_number,
            episode_number=episode_number,
            episode_title=episode_title,
            remark=remark,
            fallback_title=remark or vod_title,
            is_tv=is_tv,
            type_id=type_id_param
        )

        # 尝试为私有库多集电视剧构建自动连播播放列表 (从当前集开始向后排入)
        is_from_playlist = params.get("from_playlist") == "1"
        movie_id_val = params.get("movie_id")
        if is_tv_item and movie_id_val and not is_from_playlist and self.adapter.xbmc and self.adapter.xbmcgui:
            try:
                m_links = self.api_client.get_private_movie_links(movie_id_val)
                if m_links and len(m_links) > 1:
                    valid_links = [l for l in m_links if isinstance(l, dict) and (l.get("url") or l.get("file_id"))]
                    valid_links.sort(key=lambda x: (int(x.get("season_number") or 1), int(x.get("episode_number") or 1)))

                    curr_idx = -1
                    curr_link_id = params.get("link_id")
                    for idx, l in enumerate(valid_links):
                        if curr_link_id and l.get("id") == curr_link_id:
                            curr_idx = idx
                            break
                        if l.get("url") == url:
                            curr_idx = idx
                            break
                        if int(l.get("season_number") or 1) == s_num and int(l.get("episode_number") or 1) == e_num:
                            curr_idx = idx
                            break

                    if curr_idx >= 0 and curr_idx < len(valid_links) - 1:
                        playlist = self.adapter.xbmc.PlayList(self.adapter.xbmc.PLAYLIST_VIDEO)
                        for l in valid_links[curr_idx + 1:]:
                            next_s = int(l.get("season_number") or 1)
                            next_e = int(l.get("episode_number") or 1)
                            next_title = f"{vod_title} 第{next_e:02d}集" if vod_title else (l.get("remark") or f"第{next_e}集")
                            next_params = {
                                "action": "play_private_link",
                                "link_id": l.get("id", ""),
                                "link_type": l.get("link_type", ""),
                                "provider": l.get("provider", ""),
                                "url": l.get("url", ""),
                                "password": l.get("password", ""),
                                "vod_title": vod_title,
                                "vod_id": vod_id,
                                "movie_id": movie_id_val,
                                "remark": l.get("remark", ""),
                                "season_number": str(next_s),
                                "episode_number": str(next_e),
                                "is_tv": "1",
                                "type_id": "2",
                                "pic": pic,
                                "fanart": fanart,
                                "from_playlist": "1"
                            }
                            next_url = f"{self.adapter.base_url}?{urllib.parse.urlencode(next_params)}"
                            next_item = self.adapter.xbmcgui.ListItem(label=next_title, path=next_url)
                            next_item.setProperty('IsPlayable', 'true')
                            next_item.setInfo('video', {
                                "tvshowtitle": vod_title,
                                "title": next_title,
                                "mediatype": "episode",
                                "season": next_s,
                                "episode": next_e
                            })
                            playlist.add(next_url, next_item)
            except Exception as pl_err:
                self.adapter.log(f"私有库分集自动构建播放列表失败: {pl_err}", "warning")

        try:
            url_lower = url.lower().strip()

            # 1. 磁力与 ED2K 链接优先拦截 (基于 115 离线秒播)
            if url_lower.startswith("ed2k://") or url_lower.startswith("magnet:?") or raw_type in ["magnet", "ed2k"]:
                cloud_params = {
                    "url": url,
                    "title": display_title,
                    "display_title": display_title,
                    "vod_title": vod_title,
                    "vod_id": vod_id,
                    "movie_id": params.get("movie_id", ""),
                    "remark": remark,
                    "season_number": s_num if is_tv_item else "",
                    "episode_number": e_num if is_tv_item else "",
                    "episode_title": episode_title,
                    "is_tv": "1" if is_tv_item else "0",
                    "type_id": type_id_param or ("2" if is_tv_item else "1"),
                    "pic": pic,
                    "fanart": fanart
                }
                self._mark_playback_started(
                    movie_id=params.get("movie_id"),
                    vod_id=vod_id,
                    season_number=s_num if is_tv_item else "",
                    episode_number=e_num if is_tv_item else "",
                    is_tv=is_tv_item,
                    link_id=params.get("link_id")
                )
                self.play_cloud_down_item(cloud_params)
                return

            # 2. 个人网盘文件直播 (user_pan)
            if raw_type == "user_pan" or url_lower.startswith("user_pan://"):
                target_p = provider or ""
                target_fid = params.get("file_id") or ""
                if url_lower.startswith("user_pan://"):
                    raw_path = url[len("user_pan://"):].strip()
                    parts = raw_path.split("/", 1)
                    if len(parts) == 2:
                        if not target_p:
                            target_p = parts[0]
                        if not target_fid:
                            target_fid = parts[1]
                if not target_p:
                    target_p = params.get("provider") or ""

                file_name_val = params.get("file_name") or remark or vod_title or ""
                self.adapter.log(f"[play_private_link] 解析个人盘文件: provider={target_p}, fid={target_fid}, name={file_name_val}")
                res = self.api_client.resolve_user_play(target_p, target_fid, file_name_val)
                play_url = res.get("play_url")
                if not play_url:
                    raise Exception(res.get("error") or "未获取到个人网盘播放链接")

                headers = res.get("headers") or {}
                if headers:
                    header_parts = [f"{k}={urllib.parse.quote(v, safe='')}" for k, v in headers.items()]
                    play_url = f"{play_url}|{'&'.join(header_parts)}"

                # 记录播放开始状态
                self._mark_playback_started(
                    movie_id=params.get("movie_id"),
                    vod_id=vod_id,
                    season_number=s_num if is_tv_item else "",
                    episode_number=e_num if is_tv_item else "",
                    is_tv=is_tv_item,
                    link_id=params.get("link_id")
                )
                if vod_title:
                    try:
                        profile_dir = self.adapter.get_profile_path()
                        history_mgr = HistoryManager(profile_dir)
                        history_record = {
                            "title": vod_title,
                            "play_params": {
                                "action": "play_private_link",
                                "link_id": params.get("link_id", ""),
                                "link_type": "user_pan",
                                "provider": target_p,
                                "file_id": target_fid,
                                "url": url,
                                "vod_title": vod_title,
                                "vod_id": vod_id,
                                "movie_id": params.get("movie_id", ""),
                                "remark": remark,
                                "file_name": file_name_val,
                                "pic": pic,
                                "fanart": fanart
                            }
                        }
                        if is_tv_item:
                            history_record["episode_name"] = display_title
                            history_record["play_params"]["season_number"] = s_num
                            history_record["play_params"]["episode_number"] = e_num
                            if episode_title:
                                history_record["play_params"]["episode_title"] = episode_title
                        history_mgr.add_record(history_record)
                    except Exception as h_err:
                        self.adapter.log(f"记录个人盘播放历史失败: {str(h_err)}", "warning")

                list_item = self.adapter.xbmcgui.ListItem(label=display_title, path=play_url)
                list_item.setProperty('IsPlayable', 'true')
                list_item.setPath(play_url)
                art = {}
                if pic:
                    art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
                if fanart:
                    art['fanart'] = fanart
                if art:
                    list_item.setArt(art)

                item_info = {
                    "title": display_title,
                    "tvshowtitle": vod_title if is_tv_item else "",
                    "mediatype": "episode" if is_tv_item else "video"
                }
                if is_tv_item:
                    item_info["season"] = s_num
                    item_info["episode"] = e_num
                if params.get("resume_time"):
                    try:
                        item_info["resume_time"] = float(params["resume_time"])
                    except Exception:
                        pass
                list_item.setInfo('video', item_info)
                self.adapter.set_resolved_url(True, list_item)
                return

            # 3. 网盘分享链接识别
            is_pan = (raw_type == "pan") or any(p in url_lower for p in [
                "quark.cn", "alipan.com", "aliyundrive.com", "115.com", "115cdn.com", "anxia.com",
                "pan.baidu.com", "pan.xunlei.com", "disk.uc.cn", "drive.uc.cn",
                "123pan.com", "123684.com", "123865.com", "123278.com",
                "yun.139.com", "caiyun.139.com", "cloud.189.cn", "content.21cn.com", "guangyapan.com"
            ])

            if is_pan:
                if not provider:
                    provider = detect_cloud_provider_key(provider, url)
                fid = extract_file_id_from_url(url)
                file_name_val = params.get("file_name") or remark or ""
                file_size_val = params.get("file_size") or params.get("size") or 0
                pan_params = {
                    "url": url,
                    "code": password,
                    "pan_name": provider,
                    "vod_title": vod_title,
                    "vod_id": vod_id,
                    "movie_id": params.get("movie_id", ""),
                    "file_name": file_name_val,
                    "title": display_title,
                    "display_title": display_title,
                    "remark": remark,
                    "season_number": s_num if is_tv_item else "",
                    "episode_number": e_num if is_tv_item else "",
                    "episode_title": episode_title,
                    "is_tv": "1" if is_tv_item else "0",
                    "type_id": type_id_param or ("2" if is_tv_item else "1"),
                    "pic": pic,
                    "fanart": fanart,
                    "single_file": "1"
                }
                if file_size_val:
                    pan_params["file_size"] = file_size_val
                if fid:
                    pan_params["file_id"] = fid
                self._mark_playback_started(
                    movie_id=params.get("movie_id"),
                    vod_id=vod_id,
                    season_number=s_num if is_tv_item else "",
                    episode_number=e_num if is_tv_item else "",
                    is_tv=is_tv_item,
                    link_id=params.get("link_id")
                )
                self.play_pan_file(pan_params)
                return

            # 3. HTTP / HTTPS 直链
            if url.startswith("http://") or url.startswith("https://"):
                if self.adapter.xbmcgui and self.adapter.xbmcplugin:
                    list_item = self.adapter.xbmcgui.ListItem(label=display_title, path=url)
                    list_item.setProperty('IsPlayable', 'true')
                    list_item.setPath(url)
                    art = {}
                    if pic:
                        art.update({'icon': pic, 'thumb': pic, 'poster': pic, 'landscape': pic, 'banner': pic})
                    if fanart:
                        art['fanart'] = fanart
                    if art:
                        list_item.setArt(art)
                    info = {
                        "tvshowtitle": (vod_title or display_title) if is_tv_item else "",
                        "title": display_title,
                        "mediatype": "episode" if is_tv_item else "movie"
                    }
                    if is_tv_item:
                        info["episode"] = e_num
                        info["season"] = s_num
                    resume_time = params.get("resume_time")
                    if resume_time and float(resume_time) > 0:
                        r_sec = float(resume_time)
                        info["resume_time"] = r_sec
                        list_item.setProperty('ResumeTime', str(r_sec))
                        list_item.setProperty('StartOffset', str(r_sec))
                    list_item.setInfo('video', info)
                    self._mark_playback_started(
                        movie_id=params.get("movie_id"),
                        vod_id=vod_id,
                        season_number=s_num if is_tv_item else "",
                        episode_number=e_num if is_tv_item else "",
                        is_tv=is_tv_item,
                        link_id=params.get("link_id")
                    )
                    self.adapter.set_resolved_url(True, list_item)

                if vod_title:
                    try:
                        profile_dir = self.adapter.get_profile_path()
                        history_mgr = HistoryManager(profile_dir)
                        item_display_name = f"第{s_num}季第{e_num}集" + (f"（{remark}）" if remark else "") if is_tv_item else (remark or vod_title)
                        play_params = {
                            "action": "play_private_link",
                            "url": url,
                            "vod_title": vod_title,
                            "vod_id": vod_id,
                            "movie_id": params.get("movie_id", ""),
                            "remark": remark,
                            "season_number": s_num if is_tv_item else "",
                            "episode_number": e_num if is_tv_item else "",
                            "episode_title": episode_title,
                            "is_tv": "1" if is_tv_item else "0",
                            "file_size": params.get("file_size", 0),
                            "pic": pic
                        }
                        record = {
                            "vod_title": vod_title,
                            "vod_id": vod_id,
                            "item_name": item_display_name,
                            "timestamp": time.time(),
                            "is_folder": False,
                            "play_params": play_params
                        }
                        history_mgr.add_record(record)
                    except Exception:
                        pass
                return

            self.adapter.show_notification("播放提示", "不支持的链接协议", is_error=True)
            self.adapter.set_resolved_url(False, None)
        except Exception as e:
            self.adapter.show_notification("播放异常", str(e), is_error=True)
            self.adapter.set_resolved_url(False, None)

    def handle_sync_private_library(self, params):
        """手动触发私有库增量同步"""
        library_id = params.get("library_id")
        if not library_id:
            return
        res = self.api_client.sync_private_library(library_id)
        if res and res.get("success"):
            data = res.get("data", {})
            if data.get("hasUpdates"):
                self.adapter.show_notification("增量同步", "已成功同步并拉取最新影片/链接！")
            else:
                self.adapter.show_notification("增量同步", "当前媒体库已是最新版本")
            self.adapter.refresh_container()
        else:
            msg = res.get("message", "未知错误") if res else "网络请求失败"
            if "下架" in msg or "不存在" in msg or "失效" in msg:
                self.adapter.show_notification("共享媒体库", "该分享已被作者取消，本地已自动保留为独立副本")
            else:
                self.adapter.show_notification("增量同步", f"同步失败: {msg}", is_error=True)
            self.adapter.refresh_container()

    def handle_detach_private_library(self, params):
        """处理解除订阅并转为自建媒体库"""
        library_id = params.get("library_id")
        lib_name = params.get("library_name", "媒体库")
        if not library_id:
            return

        confirmed = False
        if self.adapter.xbmcgui:
            dialog = self.adapter.xbmcgui.Dialog()
            confirmed = dialog.yesno(
                "转为自建媒体库",
                f"确定要将【{lib_name}】转为自建媒体库吗？\n\n• 转为自建库后将解除与原作者的订阅关系，后续不再接收增量更新；\n• 解除后您可自由编辑、添加影片与管理播放源。"
            )
        else:
            confirmed = True

        if not confirmed:
            return

        res = self.api_client.detach_private_library(library_id)
        if res and res.get("success"):
            self.adapter.show_notification("转为自建库", f"已成功将【{lib_name}】转为自建媒体库")
            self.adapter.refresh_container()
        else:
            msg = res.get("message", "未知错误") if res else "网络请求失败"
            self.adapter.show_notification("转为自建库", f"操作失败: {msg}", is_error=True)

    def handle_copy_private_movie(self, params):
        """处理复制影片到自建媒体库"""
        movie_id = params.get("movie_id")
        title = params.get("title", "影片")
        if not movie_id:
            return

        # 获取所有自建媒体库 (排除 share_type == 2 和 id == 'all')
        libs = self.api_client.get_private_libraries() or []
        writable_libs = [l for l in libs if l.get("id") != "all" and safe_int(l.get("share_type"), 0) != 2]
        if not writable_libs:
            self.adapter.show_notification("复制影片", "暂无可用自建媒体库，请先创建自建媒体库", is_error=True)
            return

        target_lib = None
        if self.adapter.xbmcgui and len(writable_libs) > 1:
            dialog = self.adapter.xbmcgui.Dialog()
            lib_names = [f"{l.get('name', '未命名')} ({l.get('item_count', 0)}部)" for l in writable_libs]
            idx = dialog.select(f"复制【{title}】到自建媒体库", lib_names)
            if idx < 0:
                return
            target_lib = writable_libs[idx]
        elif writable_libs:
            target_lib = writable_libs[0]

        if not target_lib:
            return

        target_lib_id = target_lib.get("id")
        target_lib_name = target_lib.get("name", "自建库")

        res = self.api_client.copy_private_movies(movie_id, target_lib_id, copy_links=True)
        if res and res.get("success"):
            self.adapter.show_notification("复制影片", f"已成功复制到【{target_lib_name}】")
        else:
            msg = res.get("message", "未知错误") if res else "网络请求失败"
            self.adapter.show_notification("复制影片", f"复制失败: {msg}", is_error=True)

    def handle_export_strm_library(self, params):
        """导出私有库为本地 STRM / NFO 媒体库并触发 Kodi 扫描入库"""
        library_id = params.get("library_id")
        lib_name = params.get("library_name", "私有媒体库")
        if not library_id:
            return

        self.adapter.show_notification(lib_name, "正在导出 STRM 与 NFO 元数据...")
        res = self.api_client.export_private_library_strm(library_id)

        if res and res.get("success"):
            exported_movies = res.get("exported_movies", 0)
            exported_strms = res.get("exported_strms", 0)
            target_dir = res.get("target_dir", "")

            # 触发 Kodi 官方局部媒体库扫描 UpdateLibrary
            if target_dir:
                try:
                    self.adapter.execute_builtin(f'UpdateLibrary(video, "{target_dir}")')
                except Exception:
                    pass

            self.adapter.show_notification(
                lib_name,
                f"已成功导出 {exported_movies} 部影片 ({exported_strms} 个版本)，正在扫描海报墙！"
            )
        else:
            err = res.get("error") or res.get("message") or "导出失败"
            self.adapter.show_notification(lib_name, f"导出失败: {err}", is_error=True)

    def handle_private_library_poster_setting(self, params):
        """处理私有媒体库海报墙设置与同步交互"""
        library_id = params.get("library_id")
        lib_name = params.get("library_name") or "私有媒体库"
        if not library_id:
            return

        lib_info = self.api_client.get_private_library(library_id)
        if lib_info and lib_info.get("name"):
            lib_name = lib_info.get("name")
        current_mode = safe_int(lib_info.get("poster_mode"), 0)

        # 选项列表
        tag_full = " [当前已启用]" if current_mode == 2 else ""
        tag_fast = " [当前已启用]" if current_mode == 1 else ""
        tag_off = " [当前状态]" if current_mode == 0 else ""

        options = [
            f"完整海报墙 (TMDB深度刮削/演职员/精美海报){tag_full}",
            f"极速海报墙 (轻量元数据/秒级导出){tag_fast}",
            f"关闭海报墙 (清空本地STRM并从Kodi资料库移除){tag_off}",
        ]
        if current_mode > 0:
            options.append("立即重新全量同步海报墙")

        dialog = None
        try:
            import xbmcgui
            dialog = xbmcgui.Dialog()
        except Exception:
            pass

        if not dialog:
            return

        sel = dialog.select(f"【{lib_name}】海报墙同步设置", options)
        if sel < 0:
            return

        if sel == 0:
            # 完整海报墙
            if current_mode == 2:
                if dialog.yesno("海报墙同步", f"【{lib_name}】当前已是完整海报墙模式。\n是否立即重新全量同步？"):
                    self.api_client.trigger_private_library_poster_sync(library_id)
                    self._monitor_poster_sync_progress(library_id, lib_name)
                return
            res = self.api_client.update_private_library_poster_mode(library_id, 2)
            if res and res.get("success"):
                self._monitor_poster_sync_progress(library_id, lib_name)
            else:
                err = res.get("error") or res.get("message") or "设置失败"
                self.adapter.show_notification(lib_name, f"设置失败: {err}", is_error=True)
        elif sel == 1:
            # 极速海报墙
            if current_mode == 1:
                if dialog.yesno("海报墙同步", f"【{lib_name}】当前已是极速海报墙模式。\n是否立即重新全量同步？"):
                    self.api_client.trigger_private_library_poster_sync(library_id)
                    self._monitor_poster_sync_progress(library_id, lib_name)
                return
            res = self.api_client.update_private_library_poster_mode(library_id, 1)
            if res and res.get("success"):
                self._monitor_poster_sync_progress(library_id, lib_name)
            else:
                err = res.get("error") or res.get("message") or "设置失败"
                self.adapter.show_notification(lib_name, f"设置失败: {err}", is_error=True)
        elif sel == 2:
            # 关闭海报墙
            if current_mode == 0:
                dialog.ok("提示", f"【{lib_name}】海报墙当前已处于关闭状态。")
                return
            if not dialog.yesno("确认关闭海报墙", f"确认关闭【{lib_name}】的海报墙吗？\n将清空本地 STRM 物理目录并从 Kodi 资料库中移除所有对应影片。"):
                return
            res = self.api_client.update_private_library_poster_mode(library_id, 0)
            if res and res.get("success"):
                self.adapter.show_notification(lib_name, "已关闭海报墙并清理 Kodi 资料库")
                self.adapter.refresh_container()
            else:
                err = res.get("error") or res.get("message") or "关闭失败"
                self.adapter.show_notification(lib_name, f"关闭失败: {err}", is_error=True)
        elif sel == 3:
            # 立即重新全量同步
            res = self.api_client.trigger_private_library_poster_sync(library_id)
            if res and res.get("success"):
                self._monitor_poster_sync_progress(library_id, lib_name)
            else:
                err = res.get("error") or res.get("message") or "同步失败"
                self.adapter.show_notification(lib_name, f"同步失败: {err}", is_error=True)

    def _monitor_poster_sync_progress(self, library_id, lib_name):
        """在 Kodi 右上角通过 DialogProgressBG 实时展示同步刮削进度"""
        pDialog = None
        heading = f"海报墙同步: {lib_name}"
        try:
            import xbmcgui
            pDialog = xbmcgui.DialogProgressBG()
            pDialog.create(heading, "正在准备海报墙元数据...")
        except Exception:
            self.adapter.show_notification(lib_name, "海报墙后台同步已启动...")

        import time
        import xbmc
        monitor = xbmc.Monitor()
        max_duration = 600
        start_time = time.time()
        last_pct = 0

        try:
            # 稍作等待给后台协程启动留时间
            if monitor.waitForAbort(0.6):
                if pDialog:
                    pDialog.close()
                return

            while not monitor.abortRequested() and (time.time() - start_time < max_duration):
                status_data = self.api_client.get_private_library_poster_status(library_id)
                status = status_data.get("status", "idle")
                current = safe_int(status_data.get("current"), 0)
                total = safe_int(status_data.get("total"), 0)
                title = status_data.get("current_title", "")

                if status == "syncing":
                    if total > 0:
                        pct = int((current / float(total)) * 90.0)
                    else:
                        pct = min(last_pct + 5, 80)
                    last_pct = max(last_pct, pct)
                    msg = f"正在刮削 ({current}/{total} {last_pct}%) - 《{title}》" if title else f"正在刮削生成 ({current}/{total})..."
                    if pDialog:
                        pDialog.update(last_pct, heading, msg)
                elif status == "completed":
                    if pDialog:
                        pDialog.update(95, heading, "正在扫描 Kodi 视频库与海报入库...")
                    monitor.waitForAbort(2.0)
                    if pDialog:
                        pDialog.update(100, heading, f"同步完成！共 {total} 部影视已入库")
                    monitor.waitForAbort(1.2)
                    break
                elif status == "failed":
                    err = status_data.get("error", "同步失败")
                    if pDialog:
                        pDialog.update(100, heading, f"同步失败: {err}")
                    monitor.waitForAbort(2.0)
                    break
                elif status == "idle" and (time.time() - start_time > 3.0):
                    if pDialog:
                        pDialog.update(100, heading, "海报墙已是最新状态")
                    monitor.waitForAbort(1.0)
                    break

                if monitor.waitForAbort(0.6):
                    break
        except Exception as e:
            xbmc.log(f"[PosterSyncMonitor] 进度监控异常: {e}", xbmc.LOGERROR)
        finally:
            if pDialog:
                try:
                    pDialog.close()
                except Exception:
                    pass

        self.adapter.show_notification(lib_name, "海报墙同步已就绪")
        self.adapter.refresh_container()

    def show_shared_libraries(self, params=None):
        """展示共享媒体库大厅 (库视图)：第一行固定‘输入分享码导入媒体库’，下方直接展示公共共享媒体库列表（支持分页）"""
        self.adapter.set_library_content("videos")
        if params is None:
            params = {}
        page = safe_int(params.get("page"), 1)
        page_size = 100
        lib_enabled = self.adapter.library_view_enabled() if hasattr(self.adapter, "library_view_enabled") else True

        # 1. 第一行固定项：输入分享码导入媒体库
        self.adapter.add_library_item(
            "输入分享码导入媒体库",
            {"action": "input_import_share_code"},
            "shared_libraries",
            plot="输入 6 位分享码，把公开的共享媒体库一键导入到本地私有库。",
            is_folder=False, mediatype="video",
        )

        try:
            res = self.api_client.get_public_shared_libraries(page=page, page_size=page_size) or {}
            items = res.get("items", [])
            raw_total = res.get("total")
            if raw_total is None and isinstance(res.get("pagination"), dict):
                raw_total = res.get("pagination", {}).get("total")
            total = safe_int(raw_total, 0)

            # 上一页（在翻页后排在第一项固定入口之后）
            if page > 1:
                prev_params = {"action": "shared_libraries", "page": page - 1}
                self.adapter.add_library_item(
                    f"上一页 (第 {page - 1} 页)", prev_params, "shared_libraries",
                    plot=f"返回共享媒体库大厅第 {page - 1} 页。",
                    is_folder=True, mediatype="movie",
                )

            local_libs = self.api_client.get_private_libraries() or []
            local_code_set = set()
            for l in local_libs:
                c = (l.get("share_code") or "").strip().upper()
                if c:
                    local_code_set.add(c)

            if not items and page == 1:
                self.adapter.add_library_item(
                    "暂无公开发布的共享媒体库", {"action": "ignore"}, "shared_libraries",
                    plot="当前没有公开的共享媒体库，稍后再来看看。",
                    is_folder=False, mediatype="video",
                )
            else:
                for item in items:
                    share_code = item.get("shareCode") or item.get("share_code")
                    name = self._clean_title(item.get("name", "共享媒体库"))
                    cover = item.get("coverUrl") or item.get("cover_url", "")
                    creator = self._clean_title(item.get("creatorName") or item.get("creator_name", "匿名作者"))
                    movie_count = item.get("itemCount") if item.get("itemCount") is not None else (item.get("item_count") if item.get("item_count") is not None else item.get("movieCount", 0))
                    share_type = safe_int(item.get("shareType") or item.get("share_type"), 1)

                    clean_code = (share_code or "").strip().upper()
                    is_imported = clean_code and (clean_code in local_code_set)
                    imported_tag = "[已导入] " if is_imported else ""

                    type_str = "[持续更新]" if share_type == 2 else "[快照]"
                    title = f"{imported_tag}{type_str} {name} ({movie_count}部) · 作者: {creator} [码: {share_code}]"

                    plot = f"作者：{creator}｜收录 {movie_count} 部影片｜{'持续更新型订阅' if share_type == 2 else '一次性快照'}。"
                    if share_code:
                        plot += f" 分享码：{share_code}。"
                    if is_imported:
                        plot += " 你已导入过该媒体库。"

                    shared_kw = {"is_folder": False}
                    if lib_enabled:
                        lib_art = {"icon": get_pic_url(cover), "poster": get_pic_url(cover), "thumb": get_pic_url(cover)} if cover else {
                            "icon": self.adapter.node_image("shared_libraries", "thumb"),
                            "poster": self.adapter.node_image("shared_libraries", "thumb"),
                            "thumb": self.adapter.node_image("shared_libraries", "thumb"),
                        }
                        lib_art["fanart"] = self.adapter.node_image("shared_libraries", "fanart")
                        lib_art["landscape"] = lib_art["fanart"]
                        shared_kw["info"] = {"title": name, "plot": plot, "mediatype": "movie"}
                        shared_kw["art"] = lib_art
                    else:
                        shared_kw["art"] = {"icon": cover, "poster": cover, "thumb": cover} if cover else None

                    self.adapter.add_directory_item(
                        self._clean_title(title),
                        {
                            "action": "import_shared_library",
                            "share_code": share_code,
                            "name": name,
                            "creator": creator,
                            "movie_count": movie_count,
                            "share_type": share_type
                        },
                        **shared_kw
                    )

            if total > page * page_size:
                next_params = {"action": "shared_libraries", "page": page + 1}
                self.adapter.add_library_item(
                    f"下一页 (第 {page + 1} 页)", next_params, "shared_libraries",
                    plot=f"查看共享媒体库大厅第 {page + 1} 页。",
                    is_folder=True, mediatype="movie",
                )

            self.adapter.end_of_directory()
        except Exception as e:
            self.adapter.show_notification("共享媒体库", f"加载失败: {str(e)}", is_error=True)
            self.adapter.end_of_directory()

    def show_public_shared_libraries(self, params):
        """兼容保留公共共享媒体库大厅接口"""
        return self.show_shared_libraries(params)

    def handle_input_import_share_code(self):
        """弹出输入框输入分享码并导入"""
        code = self.adapter.show_keyboard_input("", "请输入 6 位媒体库分享码 (例如: A8X9KM)")
        if not code or not code.strip():
            return

        code = code.strip().upper()

        # 0. 优先本地快速查重：如果本地已存在该分享码的媒体库，提示并阻止重复导入
        local_libs = self.api_client.get_private_libraries() or []
        for lib in local_libs:
            existing_code = (lib.get("share_code") or "").strip().upper()
            if existing_code and existing_code == code:
                lib_name = self._clean_title(lib.get("name", "共享媒体库"))
                go_now = self.adapter.show_yes_no_dialog(
                    "媒体库已存在",
                    f"您已经导入过该媒体库【{lib_name}】(分享码: {code})，无需重复导入。\n\n是否立即前往该媒体库？"
                )
                if go_now:
                    self.adapter.update_container({
                        "action": "private_library_movies",
                        "library_id": lib.get("id"),
                        "library_name": lib_name,
                        "share_type": lib.get("share_type", 1)
                    })
                return

        # 1. 优先调用轻量预览接口 (毫秒级响应摘要，避免确认前下载数十兆数据)
        preview_res = self.api_client.get_shared_library_preview(code)
        if not preview_res:
            self.adapter.show_notification("共享媒体库", "未找到该分享码对应的媒体库", is_error=True)
            return

        lib_name = self._clean_title(preview_res.get("name", "共享媒体库"))
        creator = self._clean_title(preview_res.get("creatorName", "匿名作者"))
        item_count = preview_res.get("itemCount", 0)
        link_count = preview_res.get("linkCount", 0)
        share_type = preview_res.get("shareType", 1)
        share_type_str = "持续更新订阅" if share_type == 2 else "一次性快照"

        msg_lines = [
            f"媒体库名称: {lib_name}",
            f"创作者: {creator}",
            f"影片数量: {item_count} 部",
        ]
        if link_count > 0:
            msg_lines.append(f"包含资源: {link_count} 条播放链接")
        msg_lines.append(f"共享模式: {share_type_str}")
        msg_lines.append("\n是否确认导入到您的本地私有库？")

        confirm = self.adapter.show_yes_no_dialog(
            "确认导入共享媒体库",
            "\n".join(msg_lines)
        )
        if not confirm:
            return

        # 2. 用户确认后，唤起右上角后台进度条并拉取全量快照入库
        pDialog = self.adapter.create_bg_progress("导入共享媒体库", f"正在拉取【{lib_name}】云端快照...")
        pDialog.update(15, message="正在从云端下载媒体库快照...")

        detail_res = self.api_client.get_shared_library_detail(code)
        if not detail_res:
            pDialog.close()
            self.adapter.show_notification("导入失败", "获取共享库全量快照失败", is_error=True)
            return

        pDialog.update(60, message="快照下载完毕，正在写入本地私有数据库...")
        import_res = self.api_client.import_private_snapshot(detail_res)
        pDialog.update(100, message="媒体库导入完成！")
        pDialog.close()

        if import_res and import_res.get("success"):
            new_lib = import_res.get("data") or {}
            new_lib_id = new_lib.get("id") or ""
            actual_share_type = new_lib.get("share_type", share_type)

            # 提示并询问是否立即直达新媒体库
            go_now = self.adapter.show_yes_no_dialog(
                "导入成功",
                f"媒体库【{lib_name}】已成功加入私有库！\n\n是否立即前往该媒体库？"
            )
            if go_now and new_lib_id:
                self.adapter.update_container({
                    "action": "private_library_movies",
                    "library_id": new_lib_id,
                    "library_name": lib_name,
                    "share_type": actual_share_type
                })
            else:
                import time
                time.sleep(0.2)
                self.adapter.refresh_container()
        else:
            self.adapter.show_notification("导入失败", import_res.get("message", "未知错误"), is_error=True)

    def handle_import_shared_library(self, params):
        """从公共大厅点击导入"""
        share_code = (params.get("share_code") or "").strip().upper()
        name = self._clean_title(params.get("name", "共享媒体库"))
        creator = self._clean_title(params.get("creator", "作者"))
        movie_count = params.get("movie_count", 0)

        # 0. 优先本地快速查重：如果本地已存在该分享码的媒体库，提示并阻止重复导入
        local_libs = self.api_client.get_private_libraries() or []
        for lib in local_libs:
            existing_code = (lib.get("share_code") or "").strip().upper()
            if share_code and existing_code and existing_code == share_code:
                lib_name = self._clean_title(lib.get("name", name))
                go_now = self.adapter.show_yes_no_dialog(
                    "媒体库已存在",
                    f"您已经导入过该媒体库【{lib_name}】(分享码: {share_code})，无需重复导入。\n\n是否立即前往该媒体库？"
                )
                if go_now:
                    self.adapter.update_container({
                        "action": "private_library_movies",
                        "library_id": lib.get("id"),
                        "library_name": lib_name,
                        "share_type": lib.get("share_type", 1)
                    })
                return

        confirm = self.adapter.show_yes_no_dialog(
            "导入共享媒体库",
            f"媒体库: {name}\n作者: {creator}\n影片数: {movie_count} 部\n分享码: {share_code}\n\n是否立即导入并保存到我的私有库？"
        )
        if not confirm:
            return

        # 唤起右上角后台进度条
        pDialog = self.adapter.create_bg_progress("导入共享媒体库", f"正在拉取【{name}】云端快照...")
        pDialog.update(15, message="正在从云端下载媒体库快照...")

        detail_res = self.api_client.get_shared_library_detail(share_code)
        if not detail_res:
            pDialog.close()
            self.adapter.show_notification("导入失败", "获取共享库快照失败", is_error=True)
            return

        pDialog.update(60, message="快照下载完毕，正在写入本地私有数据库...")
        import_res = self.api_client.import_private_snapshot(detail_res)
        pDialog.update(100, message="媒体库导入完成！")
        pDialog.close()

        if import_res and import_res.get("success"):
            new_lib = import_res.get("data") or {}
            new_lib_id = new_lib.get("id") or ""
            actual_share_type = new_lib.get("share_type", safe_int(params.get("share_type"), 1))

            go_now = self.adapter.show_yes_no_dialog(
                "导入成功",
                f"【{name}】已成功加入私有库！\n\n是否立即前往该媒体库？"
            )
            if go_now and new_lib_id:
                self.adapter.update_container({
                    "action": "private_library_movies",
                    "library_id": new_lib_id,
                    "library_name": name,
                    "share_type": actual_share_type
                })
            else:
                import time
                time.sleep(0.2)
                self.adapter.refresh_container()
        else:
            self.adapter.show_notification("导入失败", import_res.get("message", "未知错误"), is_error=True)



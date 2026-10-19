# -*- coding: utf-8 -*-
import urllib.request
import urllib.parse
import urllib.error
import json
import time

# 绕过系统代理：为防止用户系统代理设置导致访问本地回环 127.0.0.1 失败，
# 全局为 urllib.request 注册一个无代理（Empty ProxyHandler）的 opener。
try:
    _no_proxy_handler = urllib.request.ProxyHandler({})
    _no_proxy_opener = urllib.request.build_opener(_no_proxy_handler)
    urllib.request.install_opener(_no_proxy_opener)
except Exception:
    pass

def get_kodi_user_agent():
    """获取 Kodi 原生真实的 User-Agent 字符串"""
    try:
        import xbmc
        ua = xbmc.getUserAgent()
        if ua and ua.strip():
            return ua.replace('\r', '').replace('\n', '').strip()
    except Exception:
        pass
    return "Kodi/21.0 (X11; Linux aarch64)"

class ApiClient:
    """
    对接本地 Go 服务反向代理主站的 Python 封装，使用 urllib 代替 requests。
    """
    def __init__(self, session=None):
        # 无参构造时，默认 base_url 为本地 Go 服务反代理路由，daemon_url 为本地守护进程根路径
        self.base_url = "http://127.0.0.1:17654/api/mv"
        self.daemon_url = "http://127.0.0.1:17654"
        self.user_agent = get_kodi_user_agent()

    def _request_json(self, url, params=None, timeout=15, headers=None):
        if params:
            # 过滤掉 None 值，避免 urlencode 处理成 'None' 字符串
            filtered_params = {k: v for k, v in params.items() if v is not None}
            query_string = urllib.parse.urlencode(filtered_params)
            if '?' in url:
                url = f"{url}&{query_string}"
            else:
                url = f"{url}?{query_string}"
        
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)

        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read().decode('utf-8')
                return json.loads(data)
        except Exception as e:
            err_msg = str(e)
            # 尝试解析 HTTPError 的响应体以获取后端具体错误
            if isinstance(e, urllib.error.HTTPError):
                try:
                    body = e.read().decode('utf-8')
                    err_data = json.loads(body)
                    if err_data.get("error"):
                        err_msg = err_data["error"]
                except Exception:
                    pass

            try:
                import xbmc
                xbmc.log(f"MvPlugin ApiClient request error on {url}: {err_msg}", 3) # LOGERROR
            except ImportError:
                print(f"MvPlugin ApiClient request error on {url}: {err_msg}")
            raise Exception(err_msg)

    def get_home_data(self):
        """获取首页板块数据 (getHomeData)"""
        url = f"{self.base_url}/videos/getHomeData"
        try:
            res_json = self._request_json(url, timeout=15)
            if res_json.get("success"):
                return res_json.get("data") or {}
        except Exception:
            pass
        return {}

    def get_recommendations(self):
        """获取个性化推荐"""
        url = f"{self.base_url}/videos/recommend"
        try:
            res_json = self._request_json(url, timeout=15)
            if res_json.get("success"):
                return res_json.get("data") or []
        except Exception:
            pass
        return []

    def get_playlist_categories(self):
        """获取所有片单分类"""
        url = f"{self.base_url}/lists/categories"
        try:
            res_json = self._request_json(url, timeout=15)
            if res_json.get("success"):
                return res_json.get("data") or []
        except Exception:
            pass
        return []

    def get_playlist_detail(self, slug):
        """获取片单详情"""
        url = f"{self.base_url}/lists/{urllib.parse.quote(slug)}"
        try:
            res_json = self._request_json(url, timeout=15)
            if res_json.get("success"):
                return res_json.get("data") or {}
        except Exception:
            pass
        return {}

    def search_videos(self, query, page=1, page_size=20):
        """关键字搜索视频"""
        url = f"{self.base_url}/videos/search"
        params = {"q": query, "page": page, "pageSize": page_size}
        try:
            res_json = self._request_json(url, params=params, timeout=15)
            if res_json.get("success"):
                return res_json.get("data") or {}
        except Exception:
            pass
        return {"items": [], "pagination": {"page": 1, "pageSize": page_size, "total": 0, "totalPages": 1}}

    def get_video_detail(self, video_id):
        """获取视频详情"""
        url = f"{self.base_url}/videos/{int(video_id)}"
        try:
            res_json = self._request_json(url, timeout=15)
            if res_json.get("success"):
                return res_json.get("data") or {}
        except Exception:
            pass
        return {}

    def get_tags(self):
        """获取视频标签 (getTags)"""
        url = f"{self.base_url}/videos/tags"
        try:
            res_json = self._request_json(url, timeout=15)
            if res_json.get("success"):
                return res_json.get("data") or []
        except Exception:
            pass
        return []

    def get_category_videos(self, type_id, year=None, area=None, tag_id=0, page=1, page_size=20, genre=None):
        """分类筛选视频 list"""
        url = f"{self.base_url}/videos"
        params = {"typeId": type_id, "page": page, "pageSize": page_size}
        if year:
            params["year"] = year
        if area:
            params["area"] = area
        if tag_id > 0:
            params["tagId"] = tag_id
        if genre:
            params["genre"] = genre
        try:
            res_json = self._request_json(url, params=params, timeout=15)
            if res_json.get("success"):
                return res_json.get("data") or {}
        except Exception:
            pass
        return {"items": [], "pagination": {"page": 1, "pageSize": page_size, "total": 0, "totalPages": 1}}

    # ========================== 对接本地 Go Daemon 服务 ==========================

    _pan_files_memory_cache = {}
    _PAN_CACHE_TTL = 7200  # 2小时缓存

    @classmethod
    def clear_pan_files_cache(cls):
        """清空网盘文件列表内存缓存"""
        cls._pan_files_memory_cache.clear()

    def list_pan_files(self, share_url, code="", parent_file_id="", flat="", page=1, page_size=50, no_cache=False):
        """获取网盘文件列表（支持 Python 内存缓存加速，避免播放退出时重复请求）"""
        cache_key = f"{share_url}|{code}|{parent_file_id}|{flat}|{page}|{page_size}"
        now = time.time()
        if not no_cache and cache_key in self._pan_files_memory_cache:
            exp, cached_data = self._pan_files_memory_cache[cache_key]
            if now < exp and cached_data:
                return cached_data

        url = f"{self.daemon_url}/api/list"
        params = {"share_url": share_url, "code": code}
        if parent_file_id:
            params["parent_file_id"] = parent_file_id
        if flat:
            params["flat"] = flat
        if page:
            params["page"] = page
        if page_size:
            params["page_size"] = page_size
        if no_cache:
            params["no_cache"] = "1"
        res = self._request_json(url, params=params, timeout=10)
        if res and isinstance(res, dict) and res.get("files"):
            if len(self._pan_files_memory_cache) > 100:
                oldest_key = min(self._pan_files_memory_cache.keys(), key=lambda k: self._pan_files_memory_cache[k][0])
                self._pan_files_memory_cache.pop(oldest_key, None)
            self._pan_files_memory_cache[cache_key] = (now + self._PAN_CACHE_TTL, res)
        return res

    def get_cloud_files(self, video_id, cloudid=7, vod_url_id=None):
        """获取视频在 cloud_files 表中的文件元数据列表（用于 115 秒传等）"""
        url = f"{self.base_url}/videos/{int(video_id)}/cloud-files"
        params = {}
        if cloudid is not None:
            params["cloudid"] = cloudid
        if vod_url_id is not None:
            params["vod_url_id"] = vod_url_id
        try:
            res_json = self._request_json(url, params=params, timeout=10)
            if res_json.get("success"):
                return res_json.get("data") or []
        except Exception:
            pass
        return []

    def resolve_play(self, share_url, code="", file_id="", file_name="", file_size=0, user_agent=None):
        """获取视频播放直链和字幕"""
        url = f"{self.daemon_url}/api/play"
        ua = user_agent or self.user_agent
        params = {"share_url": share_url, "code": code, "file_id": file_id, "file_name": file_name, "user_agent": ua}
        if file_size:
            params["file_size"] = file_size
        return self._request_json(url, params=params, timeout=30)

    def resolve_fast_play(self, provider, file_name, file_size, sha, user_agent=None):
        """向本地 Go 守护进程发起秒传导入并解析直链"""
        url = f"{self.daemon_url}/api/fast_play"
        ua = user_agent or self.user_agent
        params = {
            "provider": provider,
            "file_name": file_name,
            "file_size": file_size,
            "sha": sha,
            "user_agent": ua
        }
        return self._request_json(url, params=params, timeout=30)

    def get_qrcode(self, provider, client_type=None):
        """开始扫码登录，获取二维码"""
        url = f"{self.daemon_url}/api/qrcode"
        params = {"provider": provider}
        if client_type:
            params["client_type"] = client_type
        return self._request_json(url, params=params, timeout=10)

    def get_115_client_type(self):
        """获取 115 扫码端偏好类型"""
        url = f"{self.daemon_url}/api/pan/115/client_type"
        try:
            res = self._request_json(url, timeout=10)
            if res and res.get("success"):
                return res.get("client_type", "alipaymini")
        except Exception:
            pass
        return "alipaymini"

    def set_115_client_type(self, client_type):
        """设置 115 扫码端偏好类型"""
        url = f"{self.daemon_url}/api/pan/115/client_type"
        try:
            return self._post_json(url, {"client_type": client_type}, timeout=10)
        except Exception as e:
            return {"error": str(e)}

    def get_115_save_dir(self):
        """获取 115 云下载保存目录"""
        url = f"{self.daemon_url}/api/pan/115/save_dir"
        try:
            res = self._request_json(url, timeout=10)
            if res and res.get("success"):
                return res.get("save_dir", "云下载")
        except Exception:
            pass
        return "云下载"

    def set_115_save_dir(self, save_dir):
        """设置 115 云下载保存目录"""
        url = f"{self.daemon_url}/api/pan/115/save_dir"
        try:
            return self._post_json(url, {"save_dir": save_dir}, timeout=10)
        except Exception as e:
            return {"error": str(e)}

    def get_manual_login_info(self, provider):
        """获取手工输入登录所需的网页URL与二维码"""
        url = f"{self.daemon_url}/api/manual_input/url"
        params = {"provider": provider}
        return self._request_json(url, params=params, timeout=10)

    def check_qrcode_status(self, provider, key):
        """检查扫码状态（115网盘长轮询保持约 15~25 秒，超时设为 35 秒以防客户端提前中断）"""
        url = f"{self.daemon_url}/api/qrcode/status"
        params = {"provider": provider, "key": key}
        try:
            return self._request_json(url, params=params, timeout=35)
        except Exception:
            return {"status": "pending"}

    def get_pan_status(self):
        """获取所有网盘的登录状态与并发数"""
        url = f"{self.daemon_url}/api/pan/status"
        try:
            return self._request_json(url, timeout=10)
        except Exception:
            return {}

    def logout_pan(self, provider):
        """退出某网盘登录"""
        url = f"{self.daemon_url}/api/pan/logout"
        try:
            return self._request_json(url, params={"provider": provider}, timeout=10)
        except Exception:
            return {"error": "request failed"}

    def set_pan_concurrency(self, provider, value):
        """设置某网盘的并发数"""
        url = f"{self.daemon_url}/api/pan/concurrency"
        try:
            return self._request_json(url, params={"provider": provider, "value": value}, timeout=10)
        except Exception:
            return {"error": "request failed"}

    def set_pan_chunk_size(self, provider, value):
        """设置某网盘的分片大小（字节数）"""
        url = f"{self.daemon_url}/api/pan/chunk_size"
        try:
            return self._request_json(url, params={"provider": provider, "value": value}, timeout=10)
        except Exception:
            return {"error": "request failed"}

    def set_pan_auto_delete(self, provider, value):
        """设置网盘是否自动删除转存文件 (value 为布尔值或 'true'/'false')"""
        url = f"{self.daemon_url}/api/pan/auto_delete"
        val_str = "true" if value is True or value == "true" else "false"
        try:
            return self._request_json(url, params={"provider": provider, "value": val_str}, timeout=10)
        except Exception:
            return {"error": "request failed"}

    def set_pan_qps(self, provider, value):
        """设置网盘每次请求间隔 (QPS/秒)"""
        url = f"{self.daemon_url}/api/pan/qps"
        try:
            return self._request_json(url, params={"provider": provider, "value": value}, timeout=10)
        except Exception:
            return {"error": "request failed"}

    def get_pan_qps(self, provider=None):
        """获取网盘每次请求间隔 (QPS/秒)"""
        url = f"{self.daemon_url}/api/pan/qps"
        params = {}
        if provider:
            params["provider"] = provider
        try:
            return self._request_json(url, params=params, timeout=5)
        except Exception:
            return {"error": "request failed"}

    def get_pan_order(self):
        """获取网盘排序规则"""
        url = f"{self.daemon_url}/api/pan/order"
        try:
            res = self._request_json(url, timeout=5)
            if isinstance(res, dict) and res.get("success") and isinstance(res.get("order"), list):
                return res.get("order")
        except Exception:
            pass
        return ["7", "4", "2", "3", "11", "6", "9", "8", "5", "1", "10"]

    def get_push_url_info(self):
        """获取网页推送所需的网页URL与二维码"""
        url = f"{self.daemon_url}/api/push/url"
        return self._request_json(url, timeout=10)

    def poll_pushed_link(self):
        """轮询是否有新的网页推送播放请求"""
        url = f"{self.daemon_url}/api/push/poll"
        try:
            return self._request_json(url, timeout=3)
        except Exception:
            return {"has_new": False}

    def _post_json(self, url, body_data, timeout=15, headers=None):
        try:
            data = json.dumps(body_data).encode('utf-8')
            req_headers = {'Content-Type': 'application/json', 'User-Agent': self.user_agent}
            if headers:
                req_headers.update(headers)
            req = urllib.request.Request(
                url, 
                data=data, 
                headers=req_headers
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_data = response.read().decode('utf-8')
                return json.loads(res_data)
        except Exception as e:
            err_msg = str(e)
            if isinstance(e, urllib.error.HTTPError):
                try:
                    body = e.read().decode('utf-8')
                    err_data = json.loads(body)
                    if err_data.get("error"):
                        err_msg = err_data["error"]
                except Exception:
                    pass
            try:
                import xbmc
                xbmc.log(f"MvPlugin ApiClient POST error on {url}: {err_msg}", 3) # LOGERROR
            except ImportError:
                print(f"MvPlugin ApiClient POST error on {url}: {err_msg}")
            raise Exception(err_msg)

    def send_voice_command(self, query):
        """向本地守护进程发送语音控制指令 (支持播控、关键词映射与三级搜片起播)"""
        url = f"{self.daemon_url}/api/voice/command"
        return self._post_json(url, {"query": query}, timeout=10)

    def mark_pan_link_invalid(self, link_id, reason):
        """上报失效的网盘分享链接"""
        url = f"{self.base_url}/videos/pan-links/{int(link_id)}/invalid"
        body = {"invalidReason": reason}
        try:
            return self._post_json(url, body, timeout=10)
        except Exception:
            pass
        return None

    def get_pansou_config(self):
        """获取盘搜设置"""
        url = f"{self.daemon_url}/api/pansou/config"
        try:
            return self._request_json(url, timeout=10)
        except Exception:
            return {}

    def save_pansou_config(self, addr, username, password, pan_types):
        """保存盘搜设置"""
        url = f"{self.daemon_url}/api/pansou/config"
        body = {
            "addr": addr,
            "username": username,
            "password": password,
            "pan_types": pan_types
        }
        return self._post_json(url, body, timeout=10)

    def search_pansou(self, kw):
        """发起盘搜搜索"""
        url = f"{self.daemon_url}/api/pansou/search"
        return self._request_json(url, params={"kw": kw}, timeout=20)

    def get_user_files(self, provider, parent_file_id="", token=None):
        """获取个人网盘某文件夹下的文件与子目录列表"""
        url = f"{self.daemon_url}/api/user_files"
        params = {
            "provider": provider,
            "parent_file_id": parent_file_id,
        }
        if token:
            params["token"] = token
        return self._request_json(url, params=params, timeout=15)

    def resolve_user_play(self, provider, file_id, file_name="", file_size=0, token=None, user_agent=None):
        """获取个人网盘视频文件的播放直链/本地代理包装地址"""
        url = f"{self.daemon_url}/api/user_play"
        ua = user_agent or self.user_agent
        params = {
            "provider": provider,
            "file_id": file_id,
            "file_name": file_name,
            "user_agent": ua,
        }
        if file_size:
            params["file_size"] = file_size
        if token:
            params["token"] = token
        return self._request_json(url, params=params, timeout=15)

    def get_shares(self, page=1, page_size=100, keyword=None):
        """获取分享广场列表"""
        url = f"{self.base_url}/shares"
        params = {"page": page, "pageSize": page_size}
        if keyword:
            params["keyword"] = keyword
        try:
            res = self._request_json(url, params=params, timeout=10)
            if res.get("code") == "SUCCESS":
                return res.get("data") or {}
        except Exception:
            pass
        return {"list": [], "total": 0, "page": page, "pageSize": page_size}

    def get_share_favorites(self, page=1, page_size=100):
        """获取当前设备的收藏分享列表"""
        url = f"{self.base_url}/shares/favorites"
        params = {"page": page, "pageSize": page_size}
        try:
            res = self._request_json(url, params=params, timeout=10)
            if res.get("code") == "SUCCESS":
                return res.get("data") or {}
        except Exception:
            pass
        return {"list": [], "total": 0, "page": page, "pageSize": page_size}

    def add_share(self, share_url, title, sharer="匿名", pwd=None):
        """新增分享"""
        url = f"{self.base_url}/shares"
        body = {
            "url": share_url,
            "title": title,
            "sharer": sharer,
            "pwd": pwd
        }
        return self._post_json(url, body, timeout=10)

    def favorite_share(self, share_id):
        """收藏分享"""
        url = f"{self.base_url}/shares/{int(share_id)}/favorite"
        return self._post_json(url, {}, timeout=10)

    def unfavorite_share(self, share_id):
        """取消收藏分享"""
        url = f"{self.base_url}/shares/{int(share_id)}/unfavorite"
        return self._post_json(url, {}, timeout=10)

    def add_115_offline_task(self, download_url, title="", vod_title="", vod_id="", save_cid="", token=None, user_agent=None):
        """提交 115 离线下载任务（优先读取本地缓存）"""
        url = f"{self.daemon_url}/api/115/offline/add"
        ua = user_agent or self.user_agent
        params = {
            "url": download_url,
            "title": title,
            "vod_title": vod_title,
            "vod_id": str(vod_id) if vod_id else "",
            "save_cid": save_cid,
            "user_agent": ua,
        }
        if token:
            params["token"] = token
        return self._request_json(url, params=params, timeout=15)

    def get_115_offline_status(self, info_hash="", download_url="", token=None):
        """查询 115 离线任务状态"""
        url = f"{self.daemon_url}/api/115/offline/status"
        params = {}
        if info_hash:
            params["info_hash"] = info_hash
        if download_url:
            params["url"] = download_url
        if token:
            params["token"] = token
        return self._request_json(url, params=params, timeout=10)

    def get_115_offline_tasks(self, page=1, token=None):
        """获取 115 离线任务列表"""
        url = f"{self.daemon_url}/api/115/offline/tasks"
        params = {"page": page}
        if token:
            params["token"] = token
        return self._request_json(url, params=params, timeout=15)

    def delete_115_offline_tasks(self, hashes, delete_files=False, token=None):
        """删除 115 离线任务"""
        url = f"{self.daemon_url}/api/115/offline/delete"
        if isinstance(hashes, list):
            hashes_str = ",".join(hashes)
        else:
            hashes_str = str(hashes)
        params = {
            "hashes": hashes_str,
            "delete_files": "1" if delete_files else "0"
        }
        if token:
            params["token"] = token
        return self._request_json(url, params=params, timeout=10)

    def resolve_115_offline_play(self, file_id="", pick_code="", token=None, user_agent=None):
        """解析已完成 115 离线任务为直链或多文件目录"""
        url = f"{self.daemon_url}/api/115/offline/resolve"
        ua = user_agent or self.user_agent
        params = {"user_agent": ua}
        if file_id:
            params["file_id"] = file_id
        if pick_code:
            params["pick_code"] = pick_code
        if token:
            params["token"] = token
        return self._request_json(url, params=params, timeout=15)

    # ------------------ 私有媒体库 API ------------------

    def get_private_libraries(self):
        """获取所有本地私有媒体库"""
        url = f"{self.daemon_url}/api/private/libraries"
        try:
            res = self._request_json(url, timeout=10)
            if res.get("success"):
                return res.get("data") or []
        except Exception:
            pass
        return []

    def get_private_library_movies(self, library_id):
        """获取指定私有库内的所有影片"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}/movies"
        try:
            res = self._request_json(url, timeout=15)
            if res.get("success"):
                data = res.get("data")
                if isinstance(data, dict):
                    return data.get("items") or []
                return data or []
        except Exception:
            pass
        return []

    def get_private_library_movies_paged(self, library_id, page=1, page_size=100, keyword=None, type_id=None):
        """分页获取私有库内的影片列表 (返回包含 items 与 total 的分页结构)"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}/movies"
        params = {"page": page, "page_size": page_size}
        if keyword:
            params["keyword"] = keyword
        if type_id is not None:
            params["type_id"] = type_id
        try:
            res = self._request_json(url, params=params, timeout=15)
            if res.get("success"):
                return res.get("data") or {"items": [], "total": 0, "page": page, "pageSize": page_size}
        except Exception:
            pass
        return {"items": [], "total": 0, "page": page, "pageSize": page_size}

    def get_private_movie_links(self, movie_id):
        """获取影片下的所有播放链接"""
        url = f"{self.daemon_url}/api/private/movies/{movie_id}/links"
        try:
            res = self._request_json(url, timeout=10)
            if res.get("success"):
                return res.get("data") or []
        except Exception:
            pass
        return []

    def get_shared_library_preview(self, share_code):
        """获取共享媒体库轻量级预览摘要 (名称、作者、总影片数、总链接数等)"""
        url = f"{self.base_url}/shared-libraries/preview/{urllib.parse.quote(share_code)}"
        try:
            res = self._request_json(url, timeout=10)
            if res.get("success"):
                return res.get("data") or {}
        except Exception:
            pass
        return {}

    def get_shared_library_detail(self, share_code):
        """查询远端共享媒体库全量详情快照"""
        url = f"{self.base_url}/shared-libraries/detail/{urllib.parse.quote(share_code)}"
        try:
            res = self._request_json(url, timeout=60)
            if res.get("success"):
                return res.get("data") or {}
        except Exception:
            pass
        return {}

    def get_public_shared_libraries(self, page=1, page_size=100, keyword=""):
        """获取云端公共共享媒体库大厅列表"""
        url = f"{self.base_url}/shared-libraries/public"
        params = {"page": page, "pageSize": page_size}
        if keyword:
            params["q"] = keyword
        try:
            res = self._request_json(url, params=params, timeout=15)
            if res.get("success"):
                return res.get("data") or {"items": []}
        except Exception:
            pass
        return {"items": []}

    def import_private_snapshot(self, snapshot_data):
        """导入共享快照至本地私有库"""
        url = f"{self.daemon_url}/api/private/import_snapshot"
        req = urllib.request.Request(
            url,
            data=json.dumps(snapshot_data).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as he:
            try:
                body = json.loads(he.read().decode('utf-8'))
                return {"success": False, "message": body.get("message") or str(he)}
            except Exception:
                return {"success": False, "message": str(he)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def sync_private_library(self, library_id):
        """执行本地私有库增量同步"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}/sync"
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            return {"success": False, "message": str(e)}

    def detach_private_library(self, library_id):
        """解除持续更新型订阅媒体库关联并转为自建媒体库"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}/detach"
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            return {"success": False, "message": str(e)}

    def copy_private_movies(self, movie_ids, target_library_id, copy_links=True):
        """复制影片到目标媒体库"""
        url = f"{self.daemon_url}/api/private/movies/copy"
        if isinstance(movie_ids, str):
            movie_ids = [movie_ids]
        payload = {
            "movie_ids": movie_ids,
            "target_library_id": target_library_id,
            "copy_links": copy_links
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            return {"success": False, "message": str(e)}

    def export_private_library_strm(self, library_id, target_dir=""):
        """导出私有库为本地 STRM 与 NFO 媒体库"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}/export_strm"
        payload = {}
        if target_dir:
            payload["target_dir"] = target_dir
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "JukuKodiPlugin"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            xbmc.log(f"[ApiClient] 导出 STRM 异常: {e}", xbmc.LOGERROR)
            return {"success": False, "error": str(e)}

    def get_private_library(self, library_id):
        """获取单个私有媒体库详情"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JukuKodiPlugin"})
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("success"):
                    return res.get("data") or {}
        except Exception as e:
            xbmc.log(f"[ApiClient] 获取私有媒体库详情异常: {e}", xbmc.LOGERROR)
        return {}

    def update_private_library_poster_mode(self, library_id, poster_mode):
        """更新私有媒体库的海报墙模式 (0:不启用, 1:极速, 2:完整)"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}"
        payload = {"poster_mode": poster_mode}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "JukuKodiPlugin"},
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            xbmc.log(f"[ApiClient] 更新媒体库海报墙模式异常: {e}", xbmc.LOGERROR)
            return {"success": False, "error": str(e)}

    def trigger_private_library_poster_sync(self, library_id):
        """强制触发私有库海报墙全量重新同步"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}/export_strm"
        try:
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={"Content-Type": "application/json", "User-Agent": "JukuKodiPlugin"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            xbmc.log(f"[ApiClient] 触发海报墙全量同步异常: {e}", xbmc.LOGERROR)
            return {"success": False, "error": str(e)}

    def get_private_library_poster_status(self, library_id):
        """查询媒体库海报墙同步进度状态"""
        url = f"{self.daemon_url}/api/private/libraries/{library_id}/poster_status"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JukuKodiPlugin"})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            return {"status": "idle", "error": str(e)}

    def get_playback_status(self, item_id, user_id=None):
        """获取影片播放进度断点、已看及收藏状态"""
        url = f"{self.daemon_url}/api/playback/status?item_id={urllib.parse.quote(str(item_id))}"
        if user_id:
            url += f"&user_id={urllib.parse.quote(str(user_id))}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JukuKodiPlugin"})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return {"playback_ticks": 0, "resume_seconds": 0, "played": False, "is_favorite": False}

    def report_playback_progress(self, item_id, position_seconds, total_seconds=0, is_stopped=True, user_id=None):
        """上报影片播放断点与进度"""
        url = f"{self.daemon_url}/api/playback/report"
        payload = {
            "item_id": str(item_id),
            "position_seconds": float(position_seconds),
            "total_seconds": float(total_seconds),
            "is_stopped": bool(is_stopped)
        }
        if user_id:
            payload["user_id"] = str(user_id)
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "JukuKodiPlugin"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_playback_history(self, user_id=None, limit=50):
        """获取跨屏双向漫游的播放历史记录 (含电影与电视剧单集)"""
        url = f"{self.daemon_url}/api/playback/history?limit={limit}"
        if user_id:
            url += f"&user_id={urllib.parse.quote(str(user_id))}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JukuKodiPlugin"})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("items", [])
        except Exception:
            return []

    def clear_playback_history(self, user_id=None):
        """清空跨屏双向漫游的播放历史进度 (保留收藏)"""
        url = f"{self.daemon_url}/api/playback/clear"
        payload = {}
        if user_id:
            payload["user_id"] = str(user_id)
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "JukuKodiPlugin"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_batch_playback_status(self, item_ids, user_id=None):
        """批量获取多个 item 的播放断点与已看状态"""
        if not item_ids:
            return {}
        url = f"{self.daemon_url}/api/playback/batch-status"
        payload = {"item_ids": item_ids}
        if user_id:
            payload["user_id"] = str(user_id)
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "JukuKodiPlugin"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("items", {})
        except Exception:
            return {}

    def get_user_favorites(self, user_id=None, library_id=None, limit=100):
        """获取用户收藏的影片列表"""
        url = f"{self.daemon_url}/api/user/favorites?limit={limit}"
        if user_id:
            url += f"&user_id={urllib.parse.quote(str(user_id))}"
        if library_id:
            url += f"&library_id={urllib.parse.quote(str(library_id))}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JukuKodiPlugin"})
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode("utf-8"))
                return res.get("items") or []
        except Exception:
            return []

    def toggle_user_favorite(self, item_id, is_favorite=None, user_id=None):
        """切换或设置用户收藏状态"""
        url = f"{self.daemon_url}/api/user/favorite/toggle"
        payload = {
            "item_id": str(item_id)
        }
        if is_favorite is not None:
            payload["is_favorite"] = bool(is_favorite)
        if user_id:
            payload["user_id"] = str(user_id)
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "JukuKodiPlugin"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            return {"success": False, "error": str(e)}



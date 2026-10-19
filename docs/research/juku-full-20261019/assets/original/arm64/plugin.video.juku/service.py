# -*- coding: utf-8 -*-
import sys
import os
import time
import urllib.parse
import re
import xbmc
import xbmcgui
import xbmcvfs
import threading
import sqlite3

# 将 resources/lib 追加至运行期路径
project_root = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(project_root, 'resources', 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

from daemon import ensure_daemon_started, stop_daemon
from api_client import ApiClient
from router import PushHistoryManager, parse_episode_number, parse_season_number

class MvServiceMonitor(xbmc.Monitor):
    def __init__(self):
        super(MvServiceMonitor, self).__init__()
        self.settings_changed_flag = False
        self._last_ws_enabled = False
        try:
            import xbmcaddon
            addon = xbmcaddon.Addon()
            ws_val = addon.getSetting("enable_websocket")
            self._last_ws_enabled = str(ws_val).strip().lower() in ("true", "1", "yes", "on") if ws_val else False
        except Exception:
            pass

    def onAbortRequested(self):
        xbmc.log("MvPlugin Service: Abort requested, stopping daemon", xbmc.LOGINFO)
        stop_daemon()

    def onSettingsChanged(self):
        xbmc.log("MvPlugin Service: onSettingsChanged event received", xbmc.LOGINFO)
        self.settings_changed_flag = True

    def handle_settings_changed(self):
        try:
            import xbmcaddon
            import xbmcgui
            addon = xbmcaddon.Addon()
            phone_mode = "local"
            mode_val = addon.getSetting("phone_connect_mode")
            if mode_val and str(mode_val).strip().lower() in ("local", "pwa"):
                phone_mode = str(mode_val).strip().lower()

            ws_val = addon.getSetting("enable_websocket")
            current_ws = str(ws_val).strip().lower() in ("true", "1", "yes", "on") if ws_val else False

            # 约束检查：关闭后如果将手机连接方式改为PWA网站 (公网信令/跨网络)则提示用户需先开启websocket功能用于配对
            if phone_mode == "pwa" and not current_ws:
                xbmc.log("MvPlugin Service: PWA mode requires WebSocket. Reverting to local mode and alerting user.", xbmc.LOGWARNING)
                addon.setSetting("phone_connect_mode", "local")
                dialog = xbmcgui.Dialog()
                dialog.ok("连接手机", "需先开启websocket功能用于配对。")
                phone_mode = "local"

            # 如果 WebSocket 开关状态发生变化，热重启守护进程使参数生效
            if current_ws != self._last_ws_enabled:
                xbmc.log(f"MvPlugin Service: WebSocket setting changed from {self._last_ws_enabled} to {current_ws}. Restarting daemon...", xbmc.LOGINFO)
                self._last_ws_enabled = current_ws
                from daemon import restart_daemon
                restart_daemon()
        except Exception as e:
            xbmc.log(f"MvPlugin Service: Error handling settings change: {e}", xbmc.LOGERROR)


_last_primary_user = None
_last_primary_user_ts = 0

def get_primary_user_id():
    """获取当前 Kodi 绑定的 Emby 主账号 ID，优先从本地守护程序获取当前设定的主账号，兜底 settings 与 admin"""
    global _last_primary_user, _last_primary_user_ts
    now = time.time()
    if _last_primary_user and (now - _last_primary_user_ts < 30):
        return _last_primary_user

    # 优先从本地守护进程获取最新设定的主账号
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://127.0.0.1:17654/api/private/emby/config")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and data.get("success") and data.get("data"):
                p_user = data["data"].get("primary_user") or data["data"].get("username")
                if p_user and p_user.strip():
                    _last_primary_user = p_user.strip()
                    _last_primary_user_ts = now
                    return _last_primary_user
    except Exception:
        pass

    try:
        import xbmcaddon
        addon = xbmcaddon.Addon()
        user = addon.getSetting("primary_emby_user")
        if user and user.strip():
            _last_primary_user = user.strip()
            _last_primary_user_ts = now
            return _last_primary_user
    except Exception:
        pass

    return "admin"


def is_private_library_item_id(item_id):
    """判断是否为合法的私有库电影或剧集分集 ID (电影必须以 mov_ 开头，分集必须以 ep_mov_ 开头)"""
    if not item_id:
        return False
    cid = str(item_id).strip()
    if cid.startswith("mov_"):
        return True
    if cid.startswith("ep_"):
        if cid.startswith("ep_mov_"):
            return True
        parts = cid.split("_")
        # 兼容例如 ep_mov_xxx_1_1 或格式为 ep_{movieId}_{s}_{e}
        if len(parts) >= 4:
            mid = "_".join(parts[1:-2])
            if mid.startswith("mov_"):
                return True
    return False


class MvPlaybackTracker(xbmc.Player):
    """监听 Kodi 播放生命周期事件，自动将断点进度与完成度双向同步至 Go 后端与 Emby (支持原生海报墙 STRM 自动识别)"""
    def __init__(self, api_client):
        super(MvPlaybackTracker, self).__init__()
        self.api_client = api_client
        self.current_movie_id = None
        self.playing_file = None
        self.last_position = 0.0
        self.last_total = 0.0
        self.last_report_time = 0.0
        self.is_tracking = False

    def _extract_target_id_from_file(self, file_path):
        if not file_path:
            return None
        try:
            target_url = str(file_path).strip()
            # 若播放的是本地 STRM 文件，读取其首行提取 plugin:// 真实播放参数
            if target_url.endswith(".strm") and os.path.exists(target_url):
                with open(target_url, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("plugin://"):
                            target_url = line
                            break

            if "plugin://plugin.video.juku" in target_url:
                parsed = urllib.parse.urlparse(target_url)
                params = dict(urllib.parse.parse_qsl(parsed.query))
                m_id = (params.get("movie_id") or "").strip()
                v_id = (params.get("vod_id") or "").strip()
                # 严格非私有库拦截：只有具备显式 movie_id 或 vod_id 且以 mov_ / ep_mov_ 开头才属于私有库
                movie_id = ""
                if m_id and (m_id.startswith("mov_") or m_id.startswith("ep_mov_")):
                    movie_id = m_id
                elif v_id and (v_id.startswith("mov_") or v_id.startswith("ep_mov_")):
                    movie_id = v_id
                if not movie_id:
                    return None
                s_num = params.get("season_number")
                e_num = params.get("episode_number")
                if not e_num:
                    name_candidate = params.get("file_name") or params.get("title") or ""
                    parsed_e = parse_episode_number(name_candidate)
                    if parsed_e > 0:
                        e_num = str(parsed_e)
                        if not s_num:
                            s_num = str(parse_season_number(name_candidate) or 1)
                type_id_str = str(params.get("type_id") or "")
                is_tv_str = str(params.get("is_tv") or "")
                if type_id_str == "1" or is_tv_str == "0":
                    is_tv = False
                elif type_id_str == "2" or is_tv_str == "1":
                    is_tv = True
                else:
                    is_tv = False

                if is_tv and e_num and str(e_num).isdigit() and int(e_num) > 0:
                    s_val = int(s_num) if (s_num is not None and str(s_num).isdigit() and int(s_num) >= 0) else 1
                    e_val = int(e_num)
                    clean_mid = movie_id.strip()
                    if clean_mid.startswith("ep_"):
                        return clean_mid
                    return f"ep_{clean_mid}_{s_val}_{e_val}"
                elif movie_id:
                    return movie_id
        except Exception as ex:
            xbmc.log(f"MvPlugin Service: Failed to extract target_id from file '{file_path}': {ex}", xbmc.LOGDEBUG if hasattr(xbmc, 'LOGDEBUG') else xbmc.LOGINFO)
        return None

    def onPlayBackStarted(self):
        try:
            self.current_movie_id = xbmcgui.Window(10000).getProperty("mv_current_movie_id")
            self.playing_file = None
            try:
                self.playing_file = self.getPlayingFile()
            except Exception:
                pass

            if not self.current_movie_id and self.playing_file:
                target_id = self._extract_target_id_from_file(self.playing_file)
                if target_id and is_private_library_item_id(target_id):
                    self.current_movie_id = target_id
                    xbmcgui.Window(10000).setProperty("mv_current_movie_id", target_id)

            # 严格私有库合法性校验：非私有库播放时，彻底停止进度追踪，零开销休眠
            if not is_private_library_item_id(self.current_movie_id):
                self.current_movie_id = None
                self.is_tracking = False
                try:
                    xbmcgui.Window(10000).clearProperty("mv_current_movie_id")
                except Exception:
                    pass
                xbmc.log(f"MvPlugin Service: Non-private playback started, progress tracking disabled (file={self.playing_file})", xbmc.LOGDEBUG if hasattr(xbmc, 'LOGDEBUG') else xbmc.LOGINFO)
            else:
                self.last_position = 0.0
                self.last_total = 0.0
                self.last_report_time = time.time()
                self.is_tracking = True
                xbmc.log(f"MvPlugin Service: Playback started for private movie_id={self.current_movie_id} (file={self.playing_file})", xbmc.LOGINFO)

            # 蓝光原盘 (ISO/BDMV) 安全延时 Seek 兜底守护
            if self.playing_file and is_disc_item(self.playing_file):
                if has_skin_iso_resume_handler():
                    xbmc.log("MvPlugin Service: Detected custom skin ISO resume handler, plugin will yield to avoid double-seek conflict", xbmc.LOGINFO)
                else:
                    self._launch_disc_seek_guard(self.playing_file)
        except Exception:
            self.current_movie_id = None
            self.is_tracking = False

    def _launch_disc_seek_guard(self, playing_file):
        """
        在无特制皮肤脚本的普通环境下，为原盘提供平稳的起播后 Seek 兜底保障。
        等待音视频解码器与全局时间轴完全就绪后，再平稳跳转，杜绝黑屏卡死与时间超限被忽略。
        """
        try:
            db_path = find_latest_video_db()
            if not db_path or not os.path.exists(db_path):
                return
            base_name = os.path.basename(playing_file)
            conn = sqlite3.connect(db_path, timeout=5)
            cur = conn.cursor()
            cur.execute("""
                SELECT b.timeInSeconds 
                FROM bookmark b 
                JOIN files f ON b.idFile = f.idFile 
                WHERE (f.strFilename = ? OR f.strFilename LIKE ?) 
                  AND b.type = 1 AND b.timeInSeconds > 30 
                ORDER BY b.idBookmark DESC LIMIT 1
            """, (base_name, f"%{base_name}%"))
            row = cur.fetchone()
            conn.close()
            if not row or not row[0]:
                return
            target_sec = float(row[0])

            def _seek_worker():
                for _ in range(30):
                    time.sleep(0.2)
                    if not self.isPlaying():
                        return
                    tot = 0.0
                    cur_t = 0.0
                    try:
                        tot = float(self.getTotalTime())
                        cur_t = float(self.getTime())
                    except Exception:
                        pass
                    if tot > 300.0 and cur_t < 10.0:
                        time.sleep(0.8)
                        if not self.isPlaying():
                            return
                        self.seekTime(target_sec)
                        xbmc.log(f"MvPlugin Service: DiscSeekGuard smoothly seeked to {target_sec:.1f}s", xbmc.LOGINFO)
                        try:
                            hhmmss = time.strftime('%H:%M:%S', time.gmtime(target_sec))
                            xbmcgui.Dialog().notification("漫游续播", f"已为你自动跳转至 {hhmmss}", xbmcgui.NOTIFICATION_INFO, 3000)
                        except Exception:
                            pass
                        break

            t = threading.Thread(target=_seek_worker, daemon=True)
            t.start()
        except Exception as e:
            xbmc.log(f"MvPlugin Service: Failed to launch disc seek guard: {e}", xbmc.LOGDEBUG if hasattr(xbmc, 'LOGDEBUG') else xbmc.LOGINFO)

    def onPlayBackPaused(self):
        if not self.is_tracking or not self.current_movie_id:
            return
        cur_pos = self.last_position
        tot_pos = self.last_total
        try:
            cur_pos = float(self.getTime())
            tot_pos = float(self.getTotalTime())
        except Exception:
            pass
        self._report_progress(is_stopped=False, position=cur_pos, total=tot_pos)

    def onPlayBackStopped(self):
        if not self.is_tracking or not self.current_movie_id:
            self.is_tracking = False
            self.current_movie_id = None
            self.last_position = 0.0
            return
        cur_pos = self.last_position
        tot_pos = self.last_total
        try:
            if self.isPlaying():
                cur_pos = float(self.getTime())
                tot_pos = float(self.getTotalTime())
        except Exception:
            pass
        self._report_progress(is_stopped=True, position=cur_pos, total=tot_pos)
        self.is_tracking = False
        self.last_position = 0.0

    def onPlayBackEnded(self):
        if not self.is_tracking or not self.current_movie_id:
            self.is_tracking = False
            self.current_movie_id = None
            self.last_position = 0.0
            return
        cur_pos = self.last_position
        tot_pos = self.last_total
        try:
            if self.isPlaying():
                cur_pos = float(self.getTime())
                tot_pos = float(self.getTotalTime())
        except Exception:
            pass
        self._report_progress(is_stopped=True, position=cur_pos, total=tot_pos)
        self.is_tracking = False
        self.last_position = 0.0

    def tick(self):
        """主服务循环中定期采样播放进度并按周期发送心跳上报"""
        # 非私有库播放或未处于跟踪状态时，极速短路退出，彻底零上报、零时间轴采样开销
        if not self.is_tracking or not self.current_movie_id:
            return

        try:
            if self.isPlaying():
                try:
                    pos = float(self.getTime())
                    if pos > 0:
                        self.last_position = pos
                except Exception:
                    pass

                try:
                    tot = float(self.getTotalTime())
                    if tot > 0:
                        self.last_total = tot
                except Exception:
                    pass

                now = time.time()
                # 播放过程中每 10 秒向 Go 后端与 Emby 上报一次心跳断点
                if now - self.last_report_time >= 10.0 and self.last_position > 0:
                    self._report_progress(is_stopped=False, position=self.last_position, total=self.last_total)
                    self.last_report_time = now
            elif self.last_position > 0:
                # 兜底：检测到播放器已退出 playing 状态但 onPlayBackStopped 尚未触发或已过
                self._report_progress(is_stopped=True, position=self.last_position, total=self.last_total)
                self.is_tracking = False
                self.last_position = 0.0
        except Exception:
            pass

    def _report_progress(self, is_stopped=True, position=None, total=None):
        try:
            movie_id = self.current_movie_id or xbmcgui.Window(10000).getProperty("mv_current_movie_id")
            if not movie_id and self.playing_file:
                movie_id = self._extract_target_id_from_file(self.playing_file)
            if not movie_id:
                return

            # 核心拦截：非私有库播放的视频(没有movie_id，只有vod_id)，严禁向 Emby 上报进度
            # 私有库 ID 必须以 mov_ 或 ep_mov_ 开头
            if not is_private_library_item_id(movie_id):
                xbmc.log(f"MvPlugin Service: Skip reporting progress for non-private library item: {movie_id}", xbmc.LOGDEBUG if hasattr(xbmc, 'LOGDEBUG') else xbmc.LOGINFO)
                if is_stopped:
                    try:
                        xbmcgui.Window(10000).clearProperty("mv_current_movie_id")
                    except Exception:
                        pass
                    self.current_movie_id = None
                    self.playing_file = None
                    self.is_tracking = False
                return

            # 剧集分集自动补全探测：仅当播放器处于电视剧上下文时 (VideoPlayer.TVShowTitle 存在)，才补全为 ep_{movie_id}_{s}_{e}
            # 电影（Movie）绝不拼接 ep_，严防将电影片名数字误判为电视剧集号
            if movie_id and not movie_id.startswith("ep_"):
                try:
                    tv_show_title = xbmc.getInfoLabel('VideoPlayer.TVShowTitle') or ""
                    if tv_show_title:
                        ep_str = xbmc.getInfoLabel('VideoPlayer.Episode')
                        if ep_str and ep_str.isdigit() and int(ep_str) > 0:
                            s_str = xbmc.getInfoLabel('VideoPlayer.Season')
                            s_val = int(s_str) if (s_str and s_str.isdigit() and int(s_str) >= 0) else 1
                            movie_id = f"ep_{movie_id}_{s_val}_{int(ep_str)}"
                except Exception:
                    pass

            cur_time = position if (position is not None and position > 0) else 0.0
            total_time = total if (total is not None and total > 0) else 0.0
            if cur_time <= 0:
                try:
                    cur_time = float(self.getTime())
                    total_time = float(self.getTotalTime())
                except Exception:
                    cur_time = self.last_position
                    total_time = self.last_total

            if cur_time > 0:
                primary_user = get_primary_user_id()
                xbmc.log(f"MvPlugin Service: Reporting playback progress for movie_id={movie_id} user={primary_user}: {cur_time:.1f}/{total_time:.1f}s (stopped={is_stopped})", xbmc.LOGINFO)
                self.api_client.report_playback_progress(movie_id, cur_time, total_time, is_stopped=is_stopped, user_id=primary_user)
                try:
                    clean_id_str = str(movie_id).strip()
                    _recent_local_playbacks[clean_id_str] = time.time()
                    if clean_id_str.startswith("ep_"):
                        parts = clean_id_str.split("_")
                        if len(parts) >= 3:
                            parent_mid = f"mov_{parts[2]}" if parts[1] == "mov" else parts[1]
                            _recent_local_playbacks[parent_mid] = time.time()
                except Exception:
                    pass

            if is_stopped:
                try:
                    xbmcgui.Window(10000).clearProperty("mv_current_movie_id")
                except Exception:
                    pass
                self.current_movie_id = None
                self.playing_file = None
        except Exception as e:
            xbmc.log(f"MvPlugin Service: Error reporting playback: {e}", xbmc.LOGWARNING)



def kodi_jsonrpc(method, params=None):
    """通过 Kodi 原生 JSON-RPC 内部接口执行系统级调用"""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": 1
    }
    if params:
        payload["params"] = params
    try:
        import json as json_mod
        raw_res = xbmc.executeJSONRPC(json_mod.dumps(payload))
        if raw_res:
            return json_mod.loads(raw_res)
    except Exception as e:
        xbmc.log(f"MvPlugin Service JSON-RPC error ({method}): {e}", xbmc.LOGDEBUG if hasattr(xbmc, 'LOGDEBUG') else xbmc.LOGINFO)
    return None


_synced_roaming_records = {}  # 内存缓存：item_id -> dict(updated_at, resume_sec)
_recent_local_playbacks = {}  # 内存记录本机刚刚上报过的 movie_id -> 上报时间戳 (防回旋镖自残)


def is_matching_movie_or_episode(candidate_file, target_movie_id, target_year=None, target_tmdb_id=0, target_title="", is_series=False, target_season=1, target_episode=1):
    """
    严格校验候选文件/STRM是否与目标影视(movie_id, year, tmdb_id, season, episode)完全一致。
    杜绝同名影视/翻拍剧跨年代相互覆盖断点与播放进度串扰。
    """
    if not candidate_file:
        return False

    file_str = str(candidate_file).strip()
    target_mid = str(target_movie_id or "").strip()
    target_yr = str(target_year or "").strip()
    target_tmdb = str(target_tmdb_id or "0").strip()

    # 1. STRM 文件内容深度检测（最高置信度与权威防线）
    if file_str.endswith(".strm") and os.path.isfile(file_str):
        try:
            with open(file_str, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline().strip()
                if first_line.startswith("plugin://plugin.video.juku"):
                    parsed = urllib.parse.urlparse(first_line)
                    q = dict(urllib.parse.parse_qsl(parsed.query))
                    strm_mid = (q.get("movie_id") or "").strip()
                    strm_vid = (q.get("vod_id") or "").strip()
                    strm_id = strm_mid if strm_mid else (strm_vid if (strm_vid.startswith("mov_") or strm_vid.startswith("ep_mov_")) else "")

                    # 若 STRM 明确包含 movie_id
                    if strm_id and target_mid:
                        if strm_id != target_mid:
                            # 明确属于另一个影片（例如不同年代同名片或不同私有库副本）
                            return False
                        # movie_id 匹配，若是剧集，继续核对季集
                        if is_series:
                            try:
                                strm_s = int(q.get("season_number") or 1)
                                strm_e = int(q.get("episode_number") or 1)
                                return (strm_s == int(target_season) and strm_e == int(target_episode))
                            except Exception:
                                return False
                        return True
        except Exception:
            pass

    # 2. 检查路径是否包含 movie_id
    if target_mid and target_mid in file_str:
        if not is_series:
            return True

    # 检查路径中是否包含其他不同的 mov_xxxx ID
    other_mid = re.findall(r'mov_[a-f0-9]{12}', file_str)
    if other_mid and target_mid:
        if any(m != target_mid for m in other_mid):
            return False

    # 3. 检查 TMDB ID 标签 (例如目录名中的 {tmdbid-3926})
    if target_tmdb and target_tmdb != "0":
        m_tmdb = re.search(r'\{tmdbid-(\d+)\}', file_str, re.IGNORECASE)
        if m_tmdb:
            file_tmdb = m_tmdb.group(1).strip()
            if file_tmdb != target_tmdb:
                return False
            if not is_series:
                return True

    # 4. 年份 (Year) 比对与防串扰排除
    if target_yr and target_yr.isdigit() and len(target_yr) == 4:
        found_years = re.findall(r'[\(\[\._\-\s](19\d\d|20\d\d)[\)\]\._\-\s]', file_str)
        if found_years:
            if all(y != target_yr for y in found_years):
                return False

    # 5. 电视剧季集核对 (TVShow)
    if is_series:
        try:
            tgt_s = int(target_season)
            tgt_e = int(target_episode)
            found_eps = re.findall(r'[Ss](\d{1,2})[Ee](\d{1,3})', file_str)
            if found_eps:
                matches_ep = any(int(s) == tgt_s and int(e) == tgt_e for s, e in found_eps)
                if not matches_ep:
                    return False
            else:
                if f"Season {tgt_s}" not in file_str and f"Season {tgt_s:02d}" not in file_str:
                    return False
        except Exception:
            return False

    return True


def is_disc_item(file_path):
    """
    判断文件路径或 STRM 指向的目标是否为光盘镜像/原盘 (ISO/BDMV)
    光盘镜像续播依赖 Kodi 原生的 playerState (<libbluraystate>) 恢复播放列表，
    Kodi 的 JSON-RPC 接口不提供 playerState 写入能力，
    若强行通过 JSON-RPC 更新其断点会将 playerState 覆盖为空字符串，
    导致下次续播反序列化失败崩溃 (Failed to deserialize Bluray state)。
    """
    if not file_path:
        return False
    lower_path = str(file_path).lower()
    if ".iso" in lower_path or ".bdmv" in lower_path:
        return True
    if lower_path.endswith(".strm"):
        try:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(1024).lower()
                    if ".iso" in content or ".bdmv" in content:
                        return True
        except Exception:
            pass
    return False


def find_latest_video_db():
    """查找 Kodi 当前使用的最新 MyVideos 系列 SQLite 数据库绝对路径"""
    try:
        if not hasattr(xbmcvfs, 'translatePath'):
            return None
        db_dir = xbmcvfs.translatePath("special://database/")
        if not os.path.exists(db_dir):
            return None
        db_files = []
        for fn in os.listdir(db_dir):
            if fn.startswith("MyVideos") and fn.endswith(".db"):
                try:
                    ver = int(fn[8:-3])
                    db_files.append((ver, os.path.join(db_dir, fn)))
                except Exception:
                    continue
        if db_files:
            db_files.sort(reverse=True, key=lambda x: x[0])
            return db_files[0][1]
    except Exception as e:
        xbmc.log(f"MvPlugin Service: find_latest_video_db error: {e}", xbmc.LOGDEBUG if hasattr(xbmc, 'LOGDEBUG') else xbmc.LOGINFO)
    return None


def has_skin_iso_resume_handler():
    """
    检测当前 Kodi 皮肤是否自带 ISO 原盘断点续播脚本 (如 skin.confluence.minsk 的 resumeplay.py)。
    若皮肤自带此能力，插件自身必须主动退让，绝不重复触发内部 Seek，严防产生 Double Seek 冲突。
    """
    try:
        # 1. 检查当前皮肤目录下是否存在 resumeplay.py
        if hasattr(xbmcvfs, 'exists') and xbmcvfs.exists("special://skin/scripts/resumeplay.py"):
            return True
        # 2. 检查皮肤专有运行时标记
        resumeselect = xbmc.getInfoLabel("Skin.String(resumeselect)").strip()
        if resumeselect in ["1", "true", "True"]:
            return True
        # 3. 检查当前皮肤目录名
        skin_id = (xbmc.getSkinDir() or "").lower()
        if "minsk" in skin_id:
            return True
    except Exception:
        pass
    return False


def get_existing_disc_player_state(candidate_path):
    """获取原盘在 Kodi 数据库中现存的合法 playerState XML，以便更新断点后精准还原正片 playlistId"""
    if not candidate_path or not is_disc_item(candidate_path):
        return None
    db_path = find_latest_video_db()
    if not db_path or not os.path.exists(db_path):
        return None
    base_name = os.path.basename(candidate_path)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        cur.execute("""
            SELECT b.playerState 
            FROM bookmark b 
            JOIN files f ON b.idFile = f.idFile 
            WHERE (f.strFilename = ? OR f.strFilename LIKE ?) 
              AND b.playerState IS NOT NULL AND b.playerState != ''
            ORDER BY b.idBookmark DESC LIMIT 1
        """, (base_name, f"%{base_name}%"))
        row = cur.fetchone()
        conn.close()
        if row and row[0] and row[0].strip():
            return row[0].strip()
    except Exception:
        pass
    return None


def ensure_disc_player_state(candidate_path, orig_player_state=None):
    """
    针对蓝光原盘 (ISO/BDMV)，Kodi 原生断点恢复强依赖 bookmark.playerState (<libbluraystate>) XML。
    若通过 JSON-RPC 写入断点后 playerState 为空，用户在原生皮肤下选择“继续播放”会抛出反序列化异常直接崩溃。
    本函数在断点写入后，优先将原有正片 playlist 状态还原，若无原有记录则补全默认 XML，
    确保 Kodi 原生反序列化通过，完美恢复断点播放。
    """
    if not candidate_path or not is_disc_item(candidate_path):
        return False

    db_path = find_latest_video_db()
    if not db_path or not os.path.exists(db_path):
        return False

    base_name = os.path.basename(candidate_path)
    target_xml = orig_player_state if (orig_player_state and orig_player_state.strip()) else '<libbluraystate version="1">\n    <playlistId>1</playlistId>\n</libbluraystate>'

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT idFile FROM files WHERE strFilename = ? OR strFilename LIKE ? LIMIT 5", (base_name, f"%{base_name}%"))
        rows = cur.fetchall()
        updated = False
        for row in rows:
            fid = row[0]
            cur.execute("UPDATE bookmark SET playerState = ? WHERE idFile = ? AND (playerState IS NULL OR playerState = '' OR playerState != ?)", (target_xml, fid, target_xml))
            if cur.rowcount > 0:
                updated = True
        conn.commit()
        conn.close()
        if updated:
            xbmc.log(f"MvPlugin Service: Successfully ensured disc playerState for '{base_name}'", xbmc.LOGINFO)
        return updated
    except Exception as ex:
        xbmc.log(f"MvPlugin Service: Failed to ensure disc playerState: {ex}", xbmc.LOGDEBUG if hasattr(xbmc, 'LOGDEBUG') else xbmc.LOGINFO)
        return False


def sync_emby_progress_to_kodi_library(api_client, profile_dir=None):
    """
    将 Emby 主账号的漫游播放断点增量反写进 Kodi 原生媒体库与 STRM 文件
    使爆米花上的观看历史直接在 Kodi 首页官方海报墙【继续观看 (In Progress)】展示
    严格依据 movie_id, 年份与 TMDB ID 隔离同名影视，绝不跨年代相互覆盖断点
    """
    if xbmc.Player().isPlaying():
        xbmc.log("MvPlugin Service: [Roaming Sync] Playback in progress, skipping library sync to prevent disruption", xbmc.LOGINFO)
        return False

    primary_user = get_primary_user_id()
    try:
        history_items = api_client.get_playback_history(user_id=primary_user, limit=30)
        if not history_items or not isinstance(history_items, list):
            return True

        has_any_update = False
        global _synced_roaming_records, _recent_local_playbacks

        for h in history_items:
            item_id = h.get("item_id")
            if not item_id:
                continue

            updated_at = h.get("updated_at") or 0
            resume_sec = float(h.get("resume_seconds") or 0.0)
            total_sec = float(h.get("total_seconds") or 0.0)
            played = bool(h.get("played"))

            cached = _synced_roaming_records.get(item_id)
            if cached and cached.get("updated_at") == updated_at and cached.get("resume_sec") == resume_sec:
                continue

            target_movie_id = (h.get("movie_id") or "").strip()
            if not target_movie_id:
                clean_it = str(item_id).strip()
                if clean_it.startswith("mov_"):
                    target_movie_id = clean_it
                elif clean_it.startswith("ep_"):
                    parts = clean_it.split("_")
                    if len(parts) >= 3:
                        target_movie_id = f"mov_{parts[2]}" if parts[1] == "mov" else f"{parts[1]}"

            title = str(h.get("title") or "").strip()
            target_year = str(h.get("year") or "").strip()
            try:
                target_tmdb_id = int(h.get("tmdb_id") or 0)
            except Exception:
                target_tmdb_id = 0

            is_series = bool(h.get("is_series"))
            s_num = h.get("season_number") or 1
            e_num = h.get("episode_number") or 1

            updated_kodi = False
            last_checked_local_pos = 0.0

            # 1. 尝试通过 Kodi 原生 VideoLibrary 查找已入库影视并更新断点
            if not is_series:
                # 电影
                res = kodi_jsonrpc("VideoLibrary.GetMovies", {
                    "filter": {"field": "title", "operator": "is", "value": title},
                    "properties": ["file", "resume", "playcount", "year", "uniqueid"]
                })
                movies = ((res or {}).get("result") or {}).get("movies") or []
                for m in movies:
                    # 1.1 年份校验 (不同年份同名电影坚决不更新)
                    m_year = str(m.get("year") or "").strip()
                    if target_year and m_year and m_year != "0" and m_year != target_year:
                        continue

                    # 1.2 TMDB ID 校验
                    m_uniqueids = m.get("uniqueid") or {}
                    m_tmdb = str(m_uniqueids.get("tmdb") or "").strip()
                    if target_tmdb_id and m_tmdb and m_tmdb != "0" and m_tmdb != str(target_tmdb_id):
                        continue

                    # 1.3 文件/STRM 内容严格匹配校验
                    m_file = m.get("file") or ""
                    if not is_matching_movie_or_episode(
                        candidate_file=m_file,
                        target_movie_id=target_movie_id,
                        target_year=target_year,
                        target_tmdb_id=target_tmdb_id,
                        target_title=title,
                        is_series=False
                    ):
                        continue

                    # 原盘断点保护：ISO/BDMV 若写入后 playerState 为空会导致 Kodi 原始皮肤反序列化崩溃
                    # 写入后立即调用 ensure_disc_player_state 还原正片 playlist，兼顾海报墙进度与原生断点起播
                    is_disc = is_disc_item(m_file)
                    orig_disc_state = None
                    if is_disc and m_file:
                        orig_disc_state = get_existing_disc_player_state(m_file)

                    # 防回旋镖与防倒流保护：
                    # 1. 检查本地数据库已有的 resume 状态
                    m_resume = m.get("resume") or {}
                    local_pos = float(m_resume.get("position") or 0.0)
                    last_checked_local_pos = local_pos
                    if local_pos > 0 and (local_pos >= resume_sec or abs(local_pos - resume_sec) <= 15.0):
                        continue
                    # 2. 检查是否为本机最近 10 分钟内刚播放上报过的条目：
                    # 仅当远程进度未实质性超前本地（没有超过 15 秒）时，才作为本地自身回旋镖屏蔽；
                    # 若远程进度显著领先本地（用户在外部设备继续观看了），坚决放行漫游同步！
                    if local_pos > 0 and target_movie_id and target_movie_id in _recent_local_playbacks:
                        if resume_sec <= local_pos + 15.0:
                            continue

                    m_id = m.get("movieid")
                    kodi_jsonrpc("VideoLibrary.SetMovieDetails", {
                        "movieid": m_id,
                        "resume": {"position": resume_sec, "total": total_sec},
                        "playcount": 1 if played else 0
                    })
                    if m_file:
                        kodi_jsonrpc("Files.SetFileDetails", {
                            "file": m_file,
                            "media": "video",
                            "resume": {"position": resume_sec, "total": total_sec},
                            "playcount": 1 if played else 0
                        })
                    if is_disc and m_file:
                        ensure_disc_player_state(m_file, orig_player_state=orig_disc_state)
                    updated_kodi = True
            else:
                # 电视剧
                res = kodi_jsonrpc("VideoLibrary.GetTVShows", {
                    "filter": {"field": "title", "operator": "is", "value": title},
                    "properties": ["title", "year", "uniqueid"]
                })
                tvshows = ((res or {}).get("result") or {}).get("tvshows") or []
                for tv in tvshows:
                    # 1.1 电视剧年份校验
                    tv_year = str(tv.get("year") or "").strip()
                    if target_year and tv_year and tv_year != "0" and tv_year != target_year:
                        continue

                    # 1.2 电视剧 TMDB ID 校验
                    tv_uniqueids = tv.get("uniqueid") or {}
                    tv_tmdb = str(tv_uniqueids.get("tmdb") or "").strip()
                    if target_tmdb_id and tv_tmdb and tv_tmdb != "0" and tv_tmdb != str(target_tmdb_id):
                        continue

                    tv_id = tv.get("tvshowid")
                    ep_res = kodi_jsonrpc("VideoLibrary.GetEpisodes", {
                        "tvshowid": tv_id,
                        "season": s_num,
                        "properties": ["episode", "season", "file", "resume", "playcount"]
                    })
                    episodes = ((ep_res or {}).get("result") or {}).get("episodes") or []
                    for ep in episodes:
                        if ep.get("episode") == e_num:
                            ep_file = ep.get("file") or ""
                            if not is_matching_movie_or_episode(
                                candidate_file=ep_file,
                                target_movie_id=target_movie_id,
                                target_year=target_year,
                                target_tmdb_id=target_tmdb_id,
                                target_title=title,
                                is_series=True,
                                target_season=s_num,
                                target_episode=e_num
                            ):
                                continue

                            is_disc = is_disc_item(ep_file)
                            orig_disc_state = None
                            if is_disc and ep_file:
                                orig_disc_state = get_existing_disc_player_state(ep_file)

                            # 防回旋镖与防倒流保护：
                            ep_resume = ep.get("resume") or {}
                            local_pos = float(ep_resume.get("position") or 0.0)
                            last_checked_local_pos = local_pos
                            if local_pos > 0 and (local_pos >= resume_sec or abs(local_pos - resume_sec) <= 15.0):
                                continue
                            if local_pos > 0 and target_movie_id and target_movie_id in _recent_local_playbacks:
                                if resume_sec <= local_pos + 15.0:
                                    continue

                            ep_id = ep.get("episodeid")
                            kodi_jsonrpc("VideoLibrary.SetEpisodeDetails", {
                                "episodeid": ep_id,
                                "resume": {"position": resume_sec, "total": total_sec},
                                "playcount": 1 if played else 0
                            })
                            if ep_file:
                                kodi_jsonrpc("Files.SetFileDetails", {
                                    "file": ep_file,
                                    "media": "video",
                                    "resume": {"position": resume_sec, "total": total_sec},
                                    "playcount": 1 if played else 0
                                })
                            if is_disc and ep_file:
                                ensure_disc_player_state(ep_file, orig_player_state=orig_disc_state)
                            updated_kodi = True

            # 2. 尝试从本地 STRM / library 目录反向匹配文件路径并直接注入 Files.SetFileDetails
            if profile_dir and not updated_kodi:
                year_str = target_year
                title_with_year = f"{title} ({year_str})" if year_str else title
                strm_candidates = []
                if not is_series:
                    strm_candidates.append(os.path.join(profile_dir, "strm", "movies", title_with_year, f"{title_with_year}.strm"))
                    strm_candidates.append(os.path.join(profile_dir, "library", "movies", title_with_year, f"{title_with_year}.strm"))
                    if not year_str:
                        strm_candidates.append(os.path.join(profile_dir, "strm", "movies", title, f"{title}.strm"))
                        strm_candidates.append(os.path.join(profile_dir, "library", "movies", title, f"{title}.strm"))
                else:
                    strm_candidates.append(os.path.join(profile_dir, "strm", "tv", title_with_year, f"Season {s_num}", f"{title}.S{s_num:02d}E{e_num:02d}.strm"))
                    if not year_str:
                        strm_candidates.append(os.path.join(profile_dir, "strm", "tv", title, f"Season {s_num}", f"{title}.S{s_num:02d}E{e_num:02d}.strm"))
                    # 动态探测 library/ 目录下的 TVShows 剧集
                    tv_strm_name = f".S{s_num:02d}E{e_num:02d}.strm"
                    season_dir_name = f"Season {s_num:02d}"
                    lib_base = os.path.join(profile_dir, "library")
                    if os.path.isdir(lib_base):
                        try:
                            for root, _, files in os.walk(lib_base):
                                if (f"Season {s_num}" in root or season_dir_name in root) and title in root:
                                    if year_str and f"({year_str})" not in root and f".{year_str}." not in root:
                                        continue
                                    for f in files:
                                        if f.endswith(tv_strm_name) or f.endswith(f".S{s_num}E{e_num}.strm"):
                                            strm_candidates.append(os.path.join(root, f))
                        except Exception:
                            pass

                for p in set(strm_candidates):
                    is_disc_p = is_disc_item(p)
                    if os.path.exists(p):
                        if not is_matching_movie_or_episode(
                            candidate_file=p,
                            target_movie_id=target_movie_id,
                            target_year=target_year,
                            target_tmdb_id=target_tmdb_id,
                            target_title=title,
                            is_series=is_series,
                            target_season=s_num,
                            target_episode=e_num
                        ):
                            continue

                        orig_disc_state = None
                        if is_disc_p:
                            orig_disc_state = get_existing_disc_player_state(p)

                        if target_movie_id and target_movie_id in _recent_local_playbacks:
                            file_info = kodi_jsonrpc("Files.GetFileDetails", {"file": p, "media": "video", "properties": ["resume"]})
                            cur_p_pos = float(((file_info or {}).get("result") or {}).get("resume", {}).get("position") or 0.0)
                            if cur_p_pos > 0 and resume_sec <= cur_p_pos + 15.0:
                                continue

                        kodi_jsonrpc("Files.SetFileDetails", {
                            "file": p,
                            "media": "video",
                            "resume": {"position": resume_sec, "total": total_sec},
                            "playcount": 1 if played else 0
                        })
                        if is_disc_p:
                            ensure_disc_player_state(p, orig_player_state=orig_disc_state)
                        updated_kodi = True

            if updated_kodi:
                _synced_roaming_records[item_id] = {
                    "updated_at": updated_at,
                    "resume_sec": resume_sec
                }
                has_any_update = True
                xbmc.log(f"MvPlugin Service: [Roaming Sync] Synced progress for '{title}' (ep={e_num if is_series else 0}, pos={resume_sec:.1f}s) into Kodi library", xbmc.LOGINFO)
            elif last_checked_local_pos > 0 and (last_checked_local_pos >= resume_sec or abs(last_checked_local_pos - resume_sec) <= 15.0):
                # 本地进度已与远程一致或领先本地，无需在后续周期重复检查
                _synced_roaming_records[item_id] = {
                    "updated_at": updated_at,
                    "resume_sec": resume_sec
                }

        if has_any_update:
            xbmc.executebuiltin("Container.Refresh")
        return True
    except Exception as ex:
        xbmc.log(f"MvPlugin Service: [Roaming Sync] Error syncing to Kodi library: {ex}", xbmc.LOGWARNING)
        return False


def clean_title_text(text):
    """清洗标题中的高位 Emoji (码点 > 0xFFFF) 与 Dingbats/符号图标"""
    if not text:
        return ""
    cleaned = "".join(
        c for c in str(text)
        if not (
            0x2600 <= ord(c) <= 0x27BF or
            0x2B00 <= ord(c) <= 0x2BFF or
            0x1F000 <= ord(c) <= 0x1FFFF or
            ord(c) > 0xFFFF or
            ord(c) in (0xFE0F, 0xFE0E)
        )
    )
    return cleaned.strip()


def show_update_notification(heading, message):
    """在 Kodi 右上角弹出优雅的非阻塞气泡通知"""
    try:
        import xbmcaddon
        dialog = xbmcgui.Dialog()
        icon = xbmcgui.NOTIFICATION_INFO
        try:
            addon = xbmcaddon.Addon()
            addon_icon = addon.getAddonInfo('icon')
            if addon_icon:
                icon = addon_icon
        except Exception:
            pass
        dialog.notification(heading, message, icon, 5000)
    except Exception as ex:
        xbmc.log(f"MvPlugin Service: Failed to show notification: {ex}", xbmc.LOGWARNING)


def check_and_update_subscription_libraries(api_client):
    """
    后台静默检查持续更新型订阅媒体库并在有更新时自动同步与气泡提醒
    若正在播放视频，严禁触发以避免画面闪烁或打扰观影
    """
    if xbmc.Player().isPlaying():
        xbmc.log("MvPlugin Service: [Timer Task] Playback in progress, postponing subscription libraries check", xbmc.LOGINFO)
        return False

    xbmc.log("MvPlugin Service: [Timer Task] Checking subscription libraries for updates...", xbmc.LOGINFO)
    try:
        res = api_client.get_private_libraries()
        if isinstance(res, list):
            libraries = res
        elif isinstance(res, dict):
            libraries = res.get("data") or [] if res.get("success") else []
        else:
            libraries = []

        sub_libs = [lib for lib in libraries if isinstance(lib, dict) and lib.get("share_type") == 2 and lib.get("share_code")]
        if not sub_libs:
            xbmc.log("MvPlugin Service: [Timer Task] No subscription libraries found", xbmc.LOGINFO)
            return True

        has_any_update = False
        for lib in sub_libs:
            lib_id = lib.get("id")
            lib_name = lib.get("name", "未命名媒体库")
            clean_lib_name = clean_title_text(lib_name) or "订阅媒体库"
            sync_res = api_client.sync_private_library(lib_id)
            if sync_res and isinstance(sync_res, dict) and sync_res.get("success"):
                data = sync_res.get("data") or {}
                if isinstance(data, dict) and data.get("hasUpdates"):
                    has_any_update = True
                    current_ver = data.get('currentVersion', '')
                    xbmc.log(f"MvPlugin Service: [Timer Task] Subscription library '{lib_name}' updated successfully (version {current_ver})", xbmc.LOGINFO)

                    # 提取更新的影片片名以组织友好提示
                    changed_movies = data.get("changedMovies") or data.get("changed_movies") or []
                    active_titles = []
                    for m in changed_movies:
                        if isinstance(m, dict):
                            is_del = m.get("isDeleted") or m.get("is_deleted") or False
                            t = m.get("title")
                            if not is_del and t and str(t).strip():
                                ct = clean_title_text(str(t).strip())
                                if ct and ct not in active_titles:
                                    active_titles.append(ct)

                    if clean_lib_name.endswith("库"):
                        lib_label = f"“{clean_lib_name}”"
                    else:
                        lib_label = f"“{clean_lib_name}”订阅库"

                    if active_titles:
                        if len(active_titles) == 1:
                            detail_str = f"“{active_titles[0]}”等新内容"
                        elif len(active_titles) == 2:
                            detail_str = f"“{active_titles[0]}”、“{active_titles[1]}”等新内容"
                        else:
                            detail_str = f"“{active_titles[0]}”、“{active_titles[1]}”等 {len(active_titles)} 部新内容"
                        notify_msg = f"{lib_label}更新了{detail_str}"
                    else:
                        notify_msg = f"{lib_label}已同步更新最新影视资源"

                    show_update_notification("订阅媒体库更新", notify_msg)
                else:
                    xbmc.log(f"MvPlugin Service: [Timer Task] Subscription library '{lib_name}' is already up-to-date", xbmc.LOGINFO)
            else:
                msg = sync_res.get("message", "") if isinstance(sync_res, dict) else "unknown error"
                xbmc.log(f"MvPlugin Service: [Timer Task] Subscription library '{lib_name}' sync result: {msg}", xbmc.LOGWARNING)

        if has_any_update:
            # 自动刷新当前打开的列表页面（若用户恰好停留在该媒体库界面）
            xbmc.executebuiltin("Container.Refresh")
        return True
    except Exception as e:
        xbmc.log(f"MvPlugin Service: [Timer Task] Error checking subscription libraries: {e}", xbmc.LOGWARNING)
        return False


def check_addon_repo_updates():
    """
    后台静默执行 Kodi 内建命令 UpdateAddonRepos 检查插件更新
    若正在播放视频，严禁触发以避免画面闪烁或掉帧卡顿
    """
    if xbmc.Player().isPlaying():
        xbmc.log("MvPlugin Service: [Timer Task] Playback in progress, skipping UpdateAddonRepos", xbmc.LOGINFO)
        return False

    xbmc.log("MvPlugin Service: [Timer Task] Executing UpdateAddonRepos to check for addon updates...", xbmc.LOGINFO)
    try:
        xbmc.executebuiltin("UpdateAddonRepos")
        return True
    except Exception as e:
        xbmc.log(f"MvPlugin Service: [Timer Task] Error executing UpdateAddonRepos: {e}", xbmc.LOGWARNING)
        return False


def process_pushed_item(item, api_client, push_mgr):
    """处理轮询到的单条推送项目（指令、网盘链接或磁力/ED2K链接）"""
    if not item:
        return None

    cmd = item.get("cmd")
    if cmd:
        xbmc.log(f"MvPlugin Service: Pushed command detected! cmd={cmd}", xbmc.LOGINFO)
        cmd_to_run = cmd.strip()
        # 兼容 Action 类指令：若命令不含参数括号且属于常见 Kodi Action（如 PlayerProcessInfo、ContextMenu 等），
        # 自动包装为 Action(...) 交付 executebuiltin，避免内建函数解析器因找不到 built-in 而静默丢弃
        if "(" not in cmd_to_run:
            action_names = {
                "playerprocessinfo", "showosd", "osd", "codecinfo", "audionextlanguage",
                "nextsubtitle", "fullscreen", "contextmenu", "info", "fastforward", "rewind",
                "playpause", "stepforward", "stepback", "bigstepforward", "bigstepback"
            }
            if cmd_to_run.lower() in action_names:
                cmd_to_run = f"Action({cmd_to_run})"
        xbmc.executebuiltin(cmd_to_run)
        return cmd_to_run

    # 在执行任何远程推送播放或跳转（非控制指令）前，先强制关闭后台可能挂起的所有模态对话框
    # 防止因残留模态弹窗（如插件信息 DialogAddonInfo、设置弹窗等）导致 ActivateWindow 被拒绝并引发停止播放时黑屏死锁
    try:
        xbmc.executebuiltin("Dialog.Close(all, true)")
    except Exception as _dialog_err:
        xbmc.log(f"MvPlugin Service: Failed to force close modal dialogs: {_dialog_err}", xbmc.LOGWARNING)

    url = item.get("url")
    code = item.get("code") or ""
    title = item.get("title") or ""
    pan_name = item.get("pan_name") or ""
    pic = item.get("pic") or item.get("coverUrl") or ""
    fanart = item.get("backdropPath") or item.get("backdrop_path") or item.get("fanart") or ""
    vod_id = item.get("vod_id") or item.get("id") or ""

    xbmc.log(f"MvPlugin Service: Pushed link detected! url={url}, title={title}, pic={pic}, fanart={fanart}, vod_id={vod_id}", xbmc.LOGINFO)
    
    # 写入推送历史记录
    if push_mgr:
        record = {
            "url": url,
            "code": code,
            "title": title,
            "pan_name": pan_name,
            "timestamp": int(time.time())
        }
        push_mgr.add_record(record)

    vod_title = item.get("vod_title")
    if not vod_title:
        vod_title = re.sub(r'\s+S\d+E\d+.*$', '', title).strip() if title else ""

    movie_id = item.get("movie_id") or ""
    type_id = item.get("type_id")
    is_tv = item.get("is_tv")
    season_number = item.get("season_number")
    episode_number = item.get("episode_number")
    episode_title = item.get("episode_title") or ""
    remark = item.get("remark") or ""
    file_name = item.get("file_name") or title or ""
    resume = bool(item.get("resume"))
    resume_seconds = float(item.get("resume_seconds") or 0.0)

    is_cloud_down = pan_name in ["magnet", "ed2k"] or (url and (url.startswith("magnet:") or url.startswith("ed2k://")))
    is_user_pan = (item.get("link_type") == "user_pan") or (url and url.startswith("user_pan://"))
    if is_user_pan:
        user_p = pan_name or item.get("provider") or ""
        user_fid = item.get("file_id") or ""
        if url and url.startswith("user_pan://"):
            raw_path = url[len("user_pan://"):].strip()
            parts = raw_path.split("/", 1)
            if len(parts) == 2:
                if not user_p:
                    user_p = parts[0]
                if not user_fid:
                    user_fid = parts[1]
        user_params = {
            "action": "play_user_pan",
            "provider": user_p,
            "file_id": user_fid,
            "file_name": file_name,
            "vod_title": vod_title or title or file_name,
            "title": title or file_name,
            "pic": pic,
            "fanart": fanart,
            "vod_id": str(vod_id),
            "from_push": "1"
        }
        if movie_id:
            user_params["movie_id"] = str(movie_id)
        if type_id is not None:
            user_params["type_id"] = str(type_id)
        if is_tv is not None:
            user_params["is_tv"] = str(is_tv)
        if season_number is not None:
            user_params["season_number"] = str(season_number)
        if episode_number is not None:
            user_params["episode_number"] = str(episode_number)
        if episode_title:
            user_params["episode_title"] = episode_title
        if remark:
            user_params["remark"] = remark
        if resume_seconds > 0:
            user_params["resume_time"] = str(resume_seconds)
        if resume:
            user_params["resume"] = "1"

        play_cmd_extra = ",,,,resume" if (resume or resume_seconds > 0) else ""
        cmd_to_run = f'PlayMedia("plugin://plugin.video.juku/?{urllib.parse.urlencode(user_params)}"{play_cmd_extra})'
    elif is_cloud_down:
        down_title = title or ("磁力链接" if (pan_name == "magnet" or (url and url.startswith("magnet:"))) else "ED2K链接")
        cloud_params = {
            "action": "cloud_down_play",
            "url": url,
            "title": down_title,
            "vod_title": vod_title or down_title,
            "pic": pic,
            "fanart": fanart,
            "vod_id": str(vod_id),
            "from_push": "1"
        }
        if movie_id:
            cloud_params["movie_id"] = str(movie_id)
        if type_id is not None:
            cloud_params["type_id"] = str(type_id)
        if is_tv is not None:
            cloud_params["is_tv"] = str(is_tv)
        if season_number is not None:
            cloud_params["season_number"] = str(season_number)
        if episode_number is not None:
            cloud_params["episode_number"] = str(episode_number)
        if episode_title:
            cloud_params["episode_title"] = episode_title
        if remark:
            cloud_params["remark"] = remark
        if resume_seconds > 0:
            cloud_params["resume_time"] = str(resume_seconds)
        if resume:
            cloud_params["resume"] = "1"

        play_cmd_extra = ",,,,resume" if (resume or resume_seconds > 0) else ""
        cmd_to_run = f'PlayMedia("plugin://plugin.video.juku/?{urllib.parse.urlencode(cloud_params)}"{play_cmd_extra})'
    else:
        # 优先检测 URL 是否明确包含单文件 ID (#fid=... 或 ?fid=...)
        single_fid = ""
        m_fid = re.search(r'(?:[#?&/](?:fid|file_id|target_id)=([^&#\s]+))', url or "", re.I)
        if m_fid:
            single_fid = urllib.parse.unquote(m_fid.group(1))

        if single_fid:
            # 明确为单视频直接起播，避免后台冗余递归扫描
            file_name = item.get("file_name") or title
            pan_params = {
                "action": "pan_play",
                "url": url,
                "code": code,
                "file_id": single_fid,
                "pan_name": pan_name,
                "file_name": file_name,
                "vod_title": vod_title or file_name,
                "title": title or file_name,
                "pic": pic,
                "fanart": fanart,
                "vod_id": str(vod_id),
                "from_share": "1",
                "from_push": "1",
                "single_file": "1"
            }
            if movie_id:
                pan_params["movie_id"] = str(movie_id)
            if type_id is not None:
                pan_params["type_id"] = str(type_id)
            if is_tv is not None:
                pan_params["is_tv"] = str(is_tv)
            if season_number is not None:
                pan_params["season_number"] = str(season_number)
            if episode_number is not None:
                pan_params["episode_number"] = str(episode_number)
            if episode_title:
                pan_params["episode_title"] = episode_title
            if remark:
                pan_params["remark"] = remark
            if resume_seconds > 0:
                pan_params["resume_time"] = str(resume_seconds)
            if resume:
                pan_params["resume"] = "1"

            play_cmd_extra = ",,,,resume" if (resume or resume_seconds > 0) else ""
            cmd_to_run = f'PlayMedia("plugin://plugin.video.juku/?{urllib.parse.urlencode(pan_params)}"{play_cmd_extra})'
        else:
            # 全量网盘目录分享在后台获取文件列表
            files = []
            try:
                files_data = api_client.list_pan_files(url, code)
                files = files_data.get("files") or []
            except Exception as list_err:
                xbmc.log(f"MvPlugin Service: failed to list files in background: {list_err}", xbmc.LOGWARNING)

            # 如果只有一个视频文件，则使用 PlayMedia 播放，否则使用 ActivateWindow 打开文件目录列表
            if len(files) == 1:
                f = files[0]
                file_name = f.get("file_name") or title
                pan_params = {
                    "action": "pan_play",
                    "url": url,
                    "code": code,
                    "file_id": f.get("file_id") or "",
                    "pan_name": pan_name,
                    "file_name": file_name,
                    "vod_title": vod_title or file_name,
                    "title": title or file_name,
                    "pic": pic,
                    "fanart": fanart,
                    "vod_id": str(vod_id),
                    "from_share": "1",
                    "from_push": "1",
                    "single_file": "1"
                }
                if movie_id:
                    pan_params["movie_id"] = str(movie_id)
                if type_id is not None:
                    pan_params["type_id"] = str(type_id)
                if is_tv is not None:
                    pan_params["is_tv"] = str(is_tv)
                if season_number is not None:
                    pan_params["season_number"] = str(season_number)
                if episode_number is not None:
                    pan_params["episode_number"] = str(episode_number)
                if episode_title:
                    pan_params["episode_title"] = episode_title
                if remark:
                    pan_params["remark"] = remark
                if resume_seconds > 0:
                    pan_params["resume_time"] = str(resume_seconds)
                if resume:
                    pan_params["resume"] = "1"

                play_cmd_extra = ",,,,resume" if (resume or resume_seconds > 0) else ""
                cmd_to_run = f'PlayMedia("plugin://plugin.video.juku/?{urllib.parse.urlencode(pan_params)}"{play_cmd_extra})'
            else:
                # 拼装 list_files 目录展示页面
                cmd_to_run = 'ActivateWindow(Videos, "plugin://plugin.video.juku/?action=list_files&url={}&code={}&pan_name={}&vod_title={}&pic={}&fanart={}&vod_id={}")'.format(
                    urllib.parse.quote(url),
                    urllib.parse.quote(code),
                    urllib.parse.quote(pan_name),
                    urllib.parse.quote(vod_title or title),
                    urllib.parse.quote(pic),
                    urllib.parse.quote(fanart),
                    urllib.parse.quote(str(vod_id))
                )
    
    xbmc.log(f"MvPlugin Service: Triggering push playback cmd: {cmd_to_run}", xbmc.LOGINFO)
    xbmc.executebuiltin(cmd_to_run)
    return cmd_to_run


def main():
    xbmc.log("MvPlugin Service: Starting background daemon", xbmc.LOGINFO)
    ensure_daemon_started()

    # 诊断本地联通性
    xbmc.log("MvPlugin Service: Diagnosing connection to 127.0.0.1:17654", xbmc.LOGINFO)
    import urllib.request
    import json
    try:
        req = urllib.request.Request("http://127.0.0.1:17654/api/pan/status")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode('utf-8')
            res = json.loads(data)
            xbmc.log(f"MvPlugin Service Connection Test (status): SUCCESS, response: {res}", xbmc.LOGINFO)
            
        # 测试设备注册与主站 API 转发
        xbmc.log("MvPlugin Service: Testing API forwarding to getHomeData", xbmc.LOGINFO)
        req_api = urllib.request.Request("http://127.0.0.1:17654/api/mv/videos/getHomeData")
        with urllib.request.urlopen(req_api, timeout=10) as response_api:
            data_api = response_api.read().decode('utf-8')
            res_api = json.loads(data_api)
            xbmc.log(f"MvPlugin Service Connection Test (api): SUCCESS, response: {res_api}", xbmc.LOGINFO)
    except Exception as e:
        xbmc.log(f"MvPlugin Service Connection Test: FAILED: {e}", xbmc.LOGERROR)

    # 初始化 API 客户端和推送历史记录管理器
    api_client = ApiClient()
    playback_tracker = MvPlaybackTracker(api_client)
    
    import xbmcaddon
    import xbmcvfs
    addon = xbmcaddon.Addon()
    profile_dir = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
    push_mgr = PushHistoryManager(profile_dir)

    # 后台定时任务参数：开机/启动后 15 秒首次执行，之后每隔 1 小时 (3600 秒) 静默执行
    start_time = time.time()
    INITIAL_DELAY = 15
    PERIODIC_INTERVAL = 3600
    next_task_time = start_time + INITIAL_DELAY

    # 漫游播放进度同步参数：开机/启动后 5 秒首次执行，之后每隔 30 秒静默增量同步
    ROAMING_INITIAL_DELAY = 5
    ROAMING_SYNC_INTERVAL = 30
    next_roaming_time = start_time + ROAMING_INITIAL_DELAY

    monitor = MvServiceMonitor()
    # 循环等待退出信号与网页推送轮询
    while not monitor.abortRequested():
        # 响应插件设置变更事件（在主线程中安全弹窗并热重启守护进程）
        if monitor.settings_changed_flag:
            monitor.settings_changed_flag = False
            monitor.handle_settings_changed()

        # 0. 播放器状态心跳跟踪：定期采样时间戳并在播放期间/停止时确保断点百分之百落库
        playback_tracker.tick()

        # 自愈重启机制：主动检测 daemon 端口 17654，如果未运行则重新拉起
        from daemon import is_port_in_use
        daemon_ok = is_port_in_use(17654)
        if not daemon_ok:
            xbmc.log("MvPlugin Service: Detect daemon is down (port 17654 not in use). Restarting...", xbmc.LOGWARNING)
            try:
                daemon_ok = ensure_daemon_started()
            except Exception as ree:
                xbmc.log(f"MvPlugin Service self-healing failed to restart daemon: {ree}", xbmc.LOGWARNING)
                daemon_ok = False

        # 后台定时任务调度检查 (开机/启动后 15 秒及每隔 1 小时执行)
        now = time.time()
        if now >= next_task_time:
            # 避让播放状态：若用户正在看片，严禁执行后台仓库更新与弹窗刷新，推迟 5 分钟重试
            if xbmc.Player().isPlaying():
                xbmc.log("MvPlugin Service: Playback in progress, postponing timer tasks by 5 minutes", xbmc.LOGINFO)
                next_task_time = now + 300
            else:
                # 任务2: 静默执行 UpdateAddonRepos 检查插件更新
                check_addon_repo_updates()

                # 任务1: 静默检查并增量更新订阅型共享媒体库
                if daemon_ok:
                    check_and_update_subscription_libraries(api_client)
                    next_task_time = now + PERIODIC_INTERVAL
                else:
                    # 若 daemon 尚未就绪，推迟 5 秒重试，避免跳过整整 1 小时
                    xbmc.log("MvPlugin Service: Daemon not ready for subscription library check, retrying in 5s", xbmc.LOGINFO)
                    next_task_time = now + 5

        # 任务3: 静默同步 Emby 主账号漫游播放历史至 Kodi 资料库与 STRM 文件
        if daemon_ok and now >= next_roaming_time:
            if xbmc.Player().isPlaying():
                next_roaming_time = now + 10
            else:
                sync_emby_progress_to_kodi_library(api_client, profile_dir=profile_dir)
                next_roaming_time = now + ROAMING_SYNC_INTERVAL

        # 仅在守护进程端口可用时才进行轮询，避免在 daemon 启动中或异常时疯狂抛出 Connection refused
        if daemon_ok:
            try:
                res = api_client.poll_pushed_link()
                if res and res.get("has_new"):
                    process_pushed_item(res.get("item"), api_client, push_mgr)
            except Exception as e:
                xbmc.log(f"MvPlugin Service polling error: {str(e)}", xbmc.LOGDEBUG if hasattr(xbmc, 'LOGDEBUG') else xbmc.LOGINFO)

        if monitor.waitForAbort(1):
            break

    xbmc.log("MvPlugin Service: Exiting service loop", xbmc.LOGINFO)
    stop_daemon()

if __name__ == '__main__':
    main()

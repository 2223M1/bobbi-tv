# -*- coding: utf-8 -*-
"""
service.ysp.live - ysp-live 央视频直播网关后台服务

把上游 ysp-live v9.0（纯 Python 标准库实现）作为 Kodi service 插件常驻运行，
并自动把 PVR IPTV Simple Client 指向本机网关 —— 插件装完即可看电视。

设计要点：
  1. 程序本体随插件分发（resources/bin/ysp-live.py），不依赖系统里已有副本
  2. 用系统 Python 解释器以子进程方式运行，日志落到插件 profile 目录
  3. 仿照 service.litepan 的保活模式：进程退出即重新拉起（带退避）
  4. 启动前检测端口占用，避免与 systemd 版 ysp-live 等服务冲突
  5. 网关就绪后自动配置 pvr.iptvsimple 的 M3U 地址并触发重载
  6. 设置变更后自动重启以生效
"""

import os
import shutil
import socket
import subprocess
import sys
import threading
import time

import xbmc
import xbmcaddon
import xbmcvfs

ADDON_ID = 'service.ysp.live'

# 候选 Python 解释器（按顺序探测，第一个可用者胜出）。
#
# 关键坑：Kodi 里 sys.executable **不是** Python 解释器：
#   - Windows : sys.executable == kodi.exe
#   - macOS   : sys.executable == Kodi.app 里的可执行文件
#   - Linux   : sys.executable == kodi.bin / kodi
# 如果直接拿它去跑脚本，等于又启动一次 Kodi（立刻退出，code=0），
# 表现为无限重启循环。因此 sys.executable 只能作为**最后**的兜底，
# 且必须先确认它确实是一个 Python。
PYTHON_CANDIDATES = [
    # Linux / CoreELEC / LibreELEC
    '/usr/bin/python3',
    '/usr/local/bin/python3',
    '/usr/bin/python',
    # macOS（Homebrew / 系统）
    '/opt/homebrew/bin/python3',
    '/usr/local/bin/python3',
]

# Windows 常见安装位置（含 py launcher）
WINDOWS_CANDIDATES = [
    r'C:\Python313\python.exe',
    r'C:\Python312\python.exe',
    r'C:\Python311\python.exe',
    r'C:\Python310\python.exe',
    r'C:\Python39\python.exe',
]


def _looks_like_python(path):
    """确认给定可执行文件是 Python 而不是 Kodi 本身。

    判据：文件名里含 python，或用 `-c` 跑一句最小代码能成功。
    """
    if not path or not os.path.exists(path):
        return False
    base = os.path.basename(path).lower()
    if base.startswith('kodi'):
        return False
    if 'python' in base:
        return True
    # 名字不像 python（例如某些打包环境），实测一下
    try:
        import subprocess as _sp
        r = _sp.run([path, '-c', 'import sys;print(sys.version_info[0])'],
                    stdout=_sp.PIPE, stderr=_sp.PIPE, timeout=10)
        return r.returncode == 0 and b'3' in r.stdout
    except Exception:
        return False


def _find_python():
    """返回一个可用的 Python 3 解释器；找不到返回 None。"""
    cands = list(PYTHON_CANDIDATES)

    if os.name == 'nt':
        # Windows：常见安装路径 + PATH 上的 python + py launcher
        cands = list(WINDOWS_CANDIDATES) + cands
        for name in ('python.exe', 'python3.exe'):
            p = shutil.which(name)
            if p:
                cands.append(p)
        # py launcher 能自动挑一个已安装版本
        py_launcher = shutil.which('py.exe') or shutil.which('py')
        if py_launcher:
            cands.append(py_launcher)

    # 环境变量显式指定优先
    env_py = os.environ.get('YSP_PYTHON')
    if env_py:
        cands.insert(0, env_py)

    for p in cands:
        if _looks_like_python(p):
            return p

    # 最后才考虑 sys.executable，且必须真的是 Python
    if _looks_like_python(sys.executable):
        return sys.executable

    return None

DEFAULT_PORT = 8767
DEFAULT_LINKS_PER_DEVICE = 4
CHECK_INTERVAL = 5          # 保活轮询间隔（秒）
MAX_BACKOFF = 120           # 崩溃重启最大退避（秒）
HEALTH_TIMEOUT = 1.5
READY_TIMEOUT = 90          # 等待网关就绪的上限（秒）
PVR_RECHECK_INTERVAL = 600  # 定期复查 PVR 配置的间隔（秒）


class YspLiveService(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.addon = xbmcaddon.Addon(ADDON_ID)
        self.addon_dir = xbmcvfs.translatePath(self.addon.getAddonInfo('path'))
        self.profile_dir = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        self.process = None
        self._logf = None
        self.backoff = CHECK_INTERVAL
        self._last_port_warn = 0.0
        self._pvr_done = False
        # 进程内模式（Android 无系统 Python 时使用）
        self.inprocess = False
        self.server = None
        self.inproc_thread = None
        # 是否首次运行（需要完整初始化）；None=未判定
        self._first_run = None

        # 让 resources/lib 里的模块可被导入
        lib = os.path.join(self.addon_dir, 'resources', 'lib')
        if lib not in sys.path:
            sys.path.insert(0, lib)

    # ------------------------------------------------------------ 日志
    def log(self, msg, level=xbmc.LOGINFO):
        xbmc.log('[ysp-live] %s' % msg, level)

    # ------------------------------------------------------------ 配置
    def _int_setting(self, key, default):
        try:
            raw = self.addon.getSetting(key)
            if raw is None or str(raw).strip() == '':
                return default
            return int(float(raw))
        except Exception:
            return default

    def _bool_setting(self, key, default=True):
        try:
            raw = self.addon.getSetting(key)
            if raw is None or str(raw).strip() == '':
                return default
            return str(raw).lower() in ('true', '1', 'yes')
        except Exception:
            return default

    def get_port(self):
        port = self._int_setting('port', DEFAULT_PORT)
        if port < 1 or port > 65535:
            self.log('端口设置无效 (%s)，回退到 %d' % (port, DEFAULT_PORT),
                     xbmc.LOGWARNING)
            port = DEFAULT_PORT
        return port

    def get_script(self):
        for rel in (os.path.join('resources', 'bin', 'ysp-live.py'),
                    'ysp-live.py'):
            p = os.path.join(self.addon_dir, rel)
            if os.path.exists(p):
                return p
        return None

    def get_python(self):
        return _find_python()

    def get_log_path(self):
        return os.path.join(self.profile_dir, 'ysp-live.log')

    def get_data_dir(self):
        return os.path.join(self.profile_dir, 'data')

    # ------------------------------------------------------------ 端口/就绪
    def _port_responds(self, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(HEALTH_TIMEOUT)
        try:
            s.connect(('127.0.0.1', port))
            return True
        except Exception:
            return False
        finally:
            s.close()

    def _warn_port_busy(self, port):
        now = time.time()
        if now - self._last_port_warn < 60:
            return
        self._last_port_warn = now
        self.log('端口 %d 已被占用：可能已有另一个 ysp-live 实例在运行'
                 '（例如 systemd 版服务）。请先停用它，否则本插件无法启动。'
                 % port, xbmc.LOGERROR)

    def _wait_ready(self, port, timeout=READY_TIMEOUT):
        """等待网关开始监听端口。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.abortRequested():
                return False
            if self._port_responds(port):
                return True
            if self.process and self.process.poll() is not None:
                return False
            if self.waitForAbort(1):
                return False
        return False

    # ------------------------------------------------------------ PVR 自动配置
    def configure_pvr(self, port):
        """把 PVR IPTV Simple Client 指向本机网关（幂等）。

        无论是否发生改动都要置位 _pvr_done，否则主循环会每 5 秒重试一次、
        把日志刷满。配置成功后只在设置变更或网关重启时才需要再配。
        """
        if not self._bool_setting('auto_config_pvr', True):
            self.log('已关闭 PVR 自动配置，跳过')
            self._pvr_done = True
            return
        try:
            import pvr_config
        except Exception as e:
            self.log('无法导入 pvr_config: %s' % e, xbmc.LOGERROR)
            return

        try:
            changed, msg = pvr_config.configure(port=port, log=self.log)
            if changed:
                self.log('PVR 配置: %s' % msg)
            else:
                self.log('PVR 配置: %s' % msg, xbmc.LOGDEBUG)
            # 配好（或本来就对）就置位，避免主循环反复重试
            self._pvr_done = True
        except Exception as e:
            self.log('PVR 自动配置失败: %s' % e, xbmc.LOGERROR)

    # ------------------------------------------------------------ 进程管理
    def _is_android(self):
        """判断是否在 Android 上跑（Android 通常没有系统 Python 可执行文件）。"""
        try:
            if 'ANDROID_ROOT' in os.environ or 'ANDROID_DATA' in os.environ:
                return True
            # platform 模块在 Kodi 内置 Python 里可能不可用，用 sys.platform 兜底
            if hasattr(sys, 'getandroidapilevel'):
                return True
        except Exception:
            pass
        return False

    def start_inprocess(self):
        """在 Kodi 内置 Python 里直接运行网关（Android 必需）。

        Android 上没有系统 Python 可执行文件，无法用子进程方式启动网关。
        网关是纯标准库实现，可以直接 import 并在线程里跑。
        """
        port = self.get_port()
        data_dir = self.get_data_dir()
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception as e:
            self.log('创建数据目录失败: %s' % e, xbmc.LOGWARNING)

        # 把网关脚本所在目录加入模块搜索路径
        bindir = os.path.join(self.addon_dir, 'resources', 'bin')
        if bindir not in sys.path:
            sys.path.insert(0, bindir)

        # 文件名是 ysp-live.py（含连字符），不能用普通 import，
        # 必须用 importlib 按路径加载。
        script = self.get_script()
        if not script:
            self.log('找不到 ysp-live.py，插件包可能不完整', xbmc.LOGERROR)
            return False
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                'ysp_live_gateway', script)
            if spec is None or spec.loader is None:
                self.log('无法构造网关模块 spec', xbmc.LOGERROR)
                return False
            ysp_live = importlib.util.module_from_spec(spec)
            sys.modules['ysp_live_gateway'] = ysp_live
            spec.loader.exec_module(ysp_live)
        except Exception as e:
            self.log('导入网关模块失败: %s' % e, xbmc.LOGERROR)
            return False

        try:
            no_4k = not self._bool_setting('enable_device_protocol', True)
            only_4k = self._bool_setting('only_4k', False)
            links = self._int_setting('links_per_device',
                                      DEFAULT_LINKS_PER_DEVICE)
            srv, _r = ysp_live.build_server(
                port=port, bind='0.0.0.0', data_dir=data_dir,
                no_4k=no_4k, only_4k=only_4k, links_per_device=links,
                startup_warmup=self._needs_first_run_init())
        except Exception as e:
            self.log('构建网关失败: %s' % e, xbmc.LOGERROR)
            return False

        self.server = srv
        self.inprocess = True

        def _serve():
            try:
                srv.serve_forever()
            except Exception as e:
                self.log('网关服务异常结束: %s' % e, xbmc.LOGERROR)

        self.inproc_thread = threading.Thread(
            target=_serve, name='ysp-gateway', daemon=True)
        self.inproc_thread.start()
        self.log('网关已在 Kodi 内置 Python 中启动 (端口 %d)' % port)
        return True

    def start_process(self):
        # Android（或找不到外部 Python）时，改为在进程内运行
        if self._is_android() or not self.get_python():
            return self.start_inprocess()

        port = self.get_port()
        script = self.get_script()
        python = self.get_python()

        if not script:
            self.log('找不到 ysp-live.py，插件包可能不完整', xbmc.LOGERROR)
            return False

        if self._port_responds(port):
            self._warn_port_busy(port)
            return False

        data_dir = self.get_data_dir()
        log_path = self.get_log_path()
        for d in (self.profile_dir, data_dir):
            try:
                os.makedirs(d, exist_ok=True)
            except Exception as e:
                self.log('创建目录 %s 失败: %s' % (d, e), xbmc.LOGWARNING)

        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['TZ'] = 'Asia/Shanghai'
        env['YSP_DATA_DIR'] = data_dir
        env['YSP_LINKS_PER_DEVICE'] = str(
            self._int_setting('links_per_device', DEFAULT_LINKS_PER_DEVICE))

        cmd = [python, script, str(port), '--data-dir', data_dir]
        if self._bool_setting('only_4k', False):
            cmd.append('--only-4k')
        if not self._bool_setting('enable_device_protocol', True):
            cmd.append('--no-4k')
        # 插件环境没有 Node.js，显式关闭 WASM 兜底引擎，省去无用探测
        cmd.append('--no-engine')
        # 首次安装（或无有效缓存）时才做设备初始化预热；
        # 之后启动只拉起服务，频道链接由按需获取 + 后台刷新维护。
        if not self._needs_first_run_init():
            cmd.append('--no-startup-warmup')

        self.log('启动: %s (端口 %d)' % (' '.join(cmd), port))

        try:
            self._logf = open(log_path, 'ab', buffering=0)
            popen_kwargs = dict(
                cwd=data_dir, env=env,
                stdout=self._logf, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL)
            # Windows：优先用 pythonw.exe（无控制台窗口），
            # 否则用 CREATE_NO_WINDOW 标志隐藏窗口，避免每次开 Kodi 弹出黑框。
            if os.name == 'nt':
                pythonw = self._find_pythonw(python)
                if pythonw:
                    cmd[0] = pythonw
                    self.log('使用 pythonw 启动（无控制台窗口）: %s' % pythonw)
                else:
                    popen_kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW
            self.process = subprocess.Popen(cmd, **popen_kwargs)
            self.log('已启动 (pid=%s)，日志: %s' % (self.process.pid, log_path))
            return True
        except Exception as e:
            self.log('启动失败: %s' % e, xbmc.LOGERROR)
            self.process = None
            return False

    def _find_pythonw(self, python_exe):
        """找到与 python.exe 同目录的 pythonw.exe（无控制台窗口版本）。"""
        if not python_exe:
            return None
        try:
            d = os.path.dirname(python_exe)
            cand = os.path.join(d, 'pythonw.exe')
            if os.path.exists(cand):
                return cand
        except Exception:
            pass
        return None

    def _needs_first_run_init(self):
        """判断是否需要「首次安装」级别的初始化（设备注册 + 全量预热）。

        用一个独立标记文件 .initialized 记录是否已完成首次初始化，
        比依赖网关内部文件更可靠（那些文件不一定会生成）。

        - 标记文件不存在 -> 首次安装，做完整初始化（设备注册 + 预热）
        - 标记文件存在   -> 日常启动，只拉起服务，频道链接按需获取
        - 设置项 force_warmup_on_start 打开 -> 每次都强制预热

        结果缓存在 self._first_run，保证一次启动内判定一致
        （该方法会在构建命令和启动时各调用一次）。
        """
        if getattr(self, '_first_run', None) is not None:
            return self._first_run

        # 允许显式强制（设置项）
        if self._bool_setting('force_warmup_on_start', False):
            self._first_run = True
            return True

        data_dir = self.get_data_dir()
        marker = os.path.join(data_dir, '.initialized')
        if os.path.exists(marker):
            self._first_run = False
            return False

        # 首次：写入标记，后续启动不再预热
        self._first_run = True
        try:
            os.makedirs(data_dir, exist_ok=True)
            with open(marker, 'w') as f:
                f.write('initialized')
            self.log('首次安装：本次做完整初始化（设备注册 + 预热），之后启动将跳过')
        except Exception as e:
            self.log('写入初始化标记失败: %s（下次仍会预热）' % e,
                     xbmc.LOGWARNING)
        return True

    def stop_process(self):
        # 进程内模式：关闭 HTTP 服务
        if getattr(self, 'inprocess', False) and getattr(self, 'server', None):
            self.log('正在停止网关服务...')
            try:
                self.server.shutdown()
            except Exception as e:
                self.log('关闭服务时出错: %s' % e, xbmc.LOGWARNING)
            try:
                self.server.server_close()
            except Exception:
                pass
            self.server = None
            self.inprocess = False
            self.log('网关服务已停止')
            return

        proc = self.process
        if proc and proc.poll() is None:
            self.log('正在停止后台服务...')
            try:
                proc.terminate()
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.log('未响应 terminate，强制结束', xbmc.LOGWARNING)
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
            except Exception as e:
                self.log('停止时出错: %s' % e, xbmc.LOGWARNING)
            self.log('后台服务已停止')
        try:
            if self._logf:
                self._logf.close()
                self._logf = None
        except Exception:
            pass
        self.process = None

    # ------------------------------------------------------------ 事件
    def onSettingsChanged(self):
        self.log('设置已变更，重启服务以应用')
        self.stop_process()
        time.sleep(1)
        self.backoff = CHECK_INTERVAL
        self._pvr_done = False
        # 重新判定是否首次运行（force_warmup_on_start 可能刚被打开）
        self._first_run = None
        self.start_process()
        port = self.get_port()
        if self._wait_ready(port):
            self.configure_pvr(port)

    # ------------------------------------------------------------ 主循环
    def run(self):
        port = self.get_port()
        self.log('服务启动，端口 %d' % port)
        started = self.start_process()

        # 首次配置
        if started and self._wait_ready(port):
            self.configure_pvr(port)
        elif started:
            self.log('等待网关就绪超时，稍后重试 PVR 配置', xbmc.LOGWARNING)

        # 定期复查（用户可能在 Kodi 里手动改了 PVR 设置，或 PVR 被重置）。
        # 间隔取 PVR_RECHECK_INTERVAL，避免每 5 秒刷日志。
        next_pvr_check = time.time() + PVR_RECHECK_INTERVAL

        while not self.waitForAbort(CHECK_INTERVAL):
            proc = self.process
            if getattr(self, 'inprocess', False):
                # 进程内模式：检查服务线程是否还活着
                th = getattr(self, 'inproc_thread', None)
                if th is not None and not th.is_alive():
                    self.log('网关线程已退出，%d 秒后重启' % self.backoff,
                             xbmc.LOGWARNING)
                    self.stop_process()
                    waited = 0
                    while waited < self.backoff and not self.waitForAbort(1):
                        waited += 1
                    if self.abortRequested():
                        break
                    if self.start_process() and self._wait_ready(
                            self.get_port()):
                        self.configure_pvr(self.get_port())
                    self.backoff = min(self.backoff * 2, MAX_BACKOFF)
                else:
                    self.backoff = CHECK_INTERVAL
                    if not self._pvr_done and self._port_responds(
                            self.get_port()):
                        self.configure_pvr(self.get_port())
                        next_pvr_check = time.time() + PVR_RECHECK_INTERVAL
                    elif time.time() >= next_pvr_check:
                        next_pvr_check = time.time() + PVR_RECHECK_INTERVAL
                        if self._port_responds(self.get_port()):
                            self.configure_pvr(self.get_port())
            elif proc is not None and proc.poll() is not None:
                self.log('检测到进程退出 (code=%s)，%d 秒后重启'
                         % (proc.returncode, self.backoff), xbmc.LOGWARNING)
                self.stop_process()
                waited = 0
                while waited < self.backoff and not self.waitForAbort(1):
                    waited += 1
                if self.abortRequested():
                    break
                if self._port_responds(self.get_port()):
                    self._warn_port_busy(self.get_port())
                    continue
                if self.start_process() and self._wait_ready(self.get_port()):
                    self.configure_pvr(self.get_port())
                self.backoff = min(self.backoff * 2, MAX_BACKOFF)
                next_pvr_check = time.time() + PVR_RECHECK_INTERVAL
            elif proc is not None:
                self.backoff = CHECK_INTERVAL
                # 网关在跑但 PVR 还没配好（例如 Kodi 启动时 PVR 尚未就绪）
                if not self._pvr_done and self._port_responds(self.get_port()):
                    self.configure_pvr(self.get_port())
                    next_pvr_check = time.time() + PVR_RECHECK_INTERVAL
                elif time.time() >= next_pvr_check:
                    next_pvr_check = time.time() + PVR_RECHECK_INTERVAL
                    if self._port_responds(self.get_port()):
                        self.configure_pvr(self.get_port())

        self.stop_process()
        self.log('服务已退出')


if __name__ == '__main__':
    YspLiveService().run()

# -*- coding: utf-8 -*-
import os
import sys
import platform
import subprocess
import socket
import time
import atexit

try:
    import xbmc
    import xbmcaddon
    import xbmcvfs
except ImportError:
    # 兼容单元测试环境
    class MockXbmc:
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3
        def log(self, msg, level=1):
            print(f"[{level}] {msg}")
    xbmc = MockXbmc()
    
    class MockAddon:
        def getAddonInfo(self, info_id):
            if info_id == 'path':
                return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            elif info_id == 'profile':
                return os.path.expanduser("~/.kodi/userdata/addon_data/plugin.video.juku")
            return ""
    
    class MockXbmcAddon:
        def Addon(self):
            return MockAddon()
    xbmcaddon = MockXbmcAddon()
    
    class MockXbmcVfs:
        def translatePath(self, path):
            return path
    xbmcvfs = MockXbmcVfs()

_daemon_process = None

def is_port_in_use(port=17654):
    """检测指定端口是否被占用"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(('127.0.0.1', port))
        s.close()
        return True
    except Exception:
        return False

def get_binary_path():
    """识别当前系统的 CPU 架构并返回对应的守护进程二进制文件路径"""
    try:
        addon = xbmcaddon.Addon()
        addon_dir = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    except Exception:
        addon_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if hasattr(addon_dir, 'mock_calls') or not isinstance(addon_dir, str):
        addon_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    system = platform.system().lower()
    machine = platform.machine().lower()
    uname_machine = ""
    if hasattr(os, 'uname'):
        try:
            uname_machine = os.uname().machine.lower()
        except Exception:
            pass

    bin_dir = os.path.join(addon_dir, 'bin')
    candidates = []

    if 'linux' in system or 'android' in system or sys.platform.startswith('linux') or sys.platform.startswith('android'):
        if 'x86_64' in machine or 'amd64' in machine or 'x86_64' in uname_machine:
            candidates = ['daemon-linux-amd64']
        elif 'arm64' in uname_machine or 'aarch64' in uname_machine or 'arm64' in machine or 'aarch64' in machine:
            candidates = ['daemon-linux-arm64', 'daemon-linux-armv7']
        elif 'arm' in machine or 'aarch32' in machine:
            candidates = ['daemon-linux-armv7', 'daemon-linux-arm64']
        else:
            candidates = ['daemon-linux-arm64', 'daemon-linux-armv7', 'daemon-linux-amd64']

    elif 'darwin' in system or sys.platform.startswith('darwin'):
        if 'arm64' in machine or 'aarch64' in machine or 'arm64' in uname_machine or 'aarch64' in uname_machine:
            candidates = ['daemon-darwin-arm64', 'daemon-darwin-amd64']
        elif 'x86_64' in machine or 'amd64' in machine or 'x86_64' in uname_machine:
            candidates = ['daemon-darwin-amd64', 'daemon-darwin-arm64']
        else:
            candidates = ['daemon-darwin-arm64', 'daemon-darwin-amd64']

    elif 'windows' in system or sys.platform.startswith('win'):
        if 'x86_64' in machine or 'amd64' in machine:
            candidates = ['daemon-windows-amd64.exe', 'daemon-windows-arm64.exe']
        elif 'arm64' in machine or 'aarch64' in machine:
            candidates = ['daemon-windows-arm64.exe', 'daemon-windows-amd64.exe']
        else:
            candidates = ['daemon-windows-amd64.exe', 'daemon-windows-arm64.exe']

    if not candidates:
        xbmc.log(f"MvPlugin Daemon: Unsupported platform/architecture: {system}/{machine}/{uname_machine}", xbmc.LOGWARNING)
        return None

    # 1. 优先按 candidates 匹配实际存在的文件
    for name in candidates:
        full_path = os.path.join(bin_dir, name)
        if os.path.isfile(full_path):
            return full_path

    # 2. 如果 candidates 推导的文件都不存在（例如单精简包裁切过，或架构识别偏移），
    # 查找 bin 目录下是否存在唯一的 daemon-* 可执行二进制进行 Fallback
    if os.path.isdir(bin_dir):
        existing_daemons = [
            f for f in os.listdir(bin_dir)
            if f.startswith('daemon-') and not f.endswith('.pem') and not f.endswith('.json')
        ]
        if len(existing_daemons) == 1:
            fallback_name = existing_daemons[0]
            fallback_path = os.path.join(bin_dir, fallback_name)
            xbmc.log(
                f"MvPlugin Daemon: Preferred binaries {candidates} not found in {bin_dir}, "
                f"falling back to existing single binary: {fallback_name}",
                xbmc.LOGWARNING
            )
            return fallback_path

    xbmc.log(f"MvPlugin Daemon: Daemon binary not found in {bin_dir} for candidates {candidates}", xbmc.LOGERROR)
    return os.path.join(bin_dir, candidates[0])

def get_effective_profile_dir():
    """获取插件有效的数据存储目录，并自动对齐真实活跃主库路径"""
    try:
        addon = xbmcaddon.Addon()
        profile_dir = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
    except Exception:
        profile_dir = os.path.expanduser("~/.kodi/userdata/addon_data/plugin.video.juku")

    if hasattr(profile_dir, 'mock_calls') or not isinstance(profile_dir, str):
        profile_dir = os.path.expanduser("~/.kodi/userdata/addon_data/plugin.video.juku")

    dot_kodi_dir = os.path.expanduser("~/.kodi/userdata/addon_data/plugin.video.juku")
    if os.path.normpath(profile_dir) != os.path.normpath(dot_kodi_dir) and os.path.exists(os.path.join(dot_kodi_dir, "juku.db")):
        dot_db = os.path.join(dot_kodi_dir, "juku.db")
        prof_db = os.path.join(profile_dir, "juku.db")
        if not os.path.exists(prof_db) or os.path.getsize(dot_db) > os.path.getsize(prof_db):
            profile_dir = dot_kodi_dir

    try:
        if not os.path.exists(profile_dir):
            os.makedirs(profile_dir, exist_ok=True)
    except Exception:
        pass

    return profile_dir

def get_tokens_file_path():
    """获取 tokens.json 存储的绝对路径"""
    profile_dir = get_effective_profile_dir()
    return os.path.join(profile_dir, 'tokens.json')

def get_pid_file_path():
    """获取 daemon.pid 存储的绝对路径"""
    profile_dir = get_effective_profile_dir()
    return os.path.join(profile_dir, 'daemon.pid')

def write_pid_file(pid):
    """写入守护进程 PID 到文件"""
    try:
        with open(get_pid_file_path(), 'w') as f:
            f.write(str(pid))
    except Exception as e:
        xbmc.log(f"MvPlugin Daemon: Failed to write PID file: {e}", xbmc.LOGWARNING)

def clean_pid_file():
    """删除 PID 文件"""
    try:
        pid_file = get_pid_file_path()
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except Exception:
        pass

def ensure_daemon_started():
    """确保后台守护进程运行"""
    global _daemon_process

    # 1. 检测端口是否已被占用
    if is_port_in_use(17654):
        xbmc.log("MvPlugin Daemon: Daemon port 17654 already in use. No need to start new one.", xbmc.LOGINFO)
        return True

    # 获取 profile_dir 用于锁目录
    profile_dir = get_effective_profile_dir()
    lock_dir = os.path.join(profile_dir, 'daemon_start.lock')

    # === 僵尸锁（Stale Lock）探测与清理机制 ===
    # 若锁目录已存在超过 5.0 秒，判定为前次进程崩溃或硬中断遗留的孤儿锁，强制回收
    if os.path.exists(lock_dir):
        try:
            lock_mtime = os.path.getmtime(lock_dir)
            lock_age = time.time() - lock_mtime
            if lock_age > 5.0:
                xbmc.log(f"MvPlugin Daemon: Stale start lock detected (age: {lock_age:.1f}s), breaking stale lock...", xbmc.LOGWARNING)
                try:
                    os.rmdir(lock_dir)
                except OSError:
                    import shutil
                    shutil.rmtree(lock_dir, ignore_errors=True)
        except Exception as e:
            xbmc.log(f"MvPlugin Daemon: Error inspecting lock directory: {e}", xbmc.LOGWARNING)

    # 尝试获取锁，如果已被占用，等待最多 3 秒
    lock_acquired = False
    start_lock_time = time.time()
    while time.time() - start_lock_time < 3.0:
        try:
            os.makedirs(lock_dir, exist_ok=False)
            lock_acquired = True
            break
        except OSError:
            # 锁已存在，等待并重试
            time.sleep(0.1)

    if not lock_acquired:
        # 如果等待 3 秒后依然没有获取到锁，再次检查端口状态
        if is_port_in_use(17654):
            xbmc.log("MvPlugin Daemon: Daemon already started by another instance during lock wait.", xbmc.LOGINFO)
            return True

        # 端口未在使用且锁仍然卡死，说明锁持有者在等待期内死掉了，强制打破僵局清除锁
        xbmc.log("MvPlugin Daemon: Failed to acquire start lock after 3s and daemon port 17654 is down. Forcibly releasing lock...", xbmc.LOGWARNING)
        try:
            os.rmdir(lock_dir)
        except OSError:
            import shutil
            shutil.rmtree(lock_dir, ignore_errors=True)
        return False

    try:
        # 获取锁后再次检测，以防在等待锁的过程中已被另一实例启动
        if is_port_in_use(17654):
            xbmc.log("MvPlugin Daemon: Daemon port 17654 already in use after acquiring lock.", xbmc.LOGINFO)
            return True

        # 2. 识别系统并寻找二进制文件路径
        binary_path = get_binary_path()
        if not binary_path:
            xbmc.log("MvPlugin Daemon: Cannot start daemon, platform or CPU architecture not supported.", xbmc.LOGWARNING)
            return False

        if not os.path.exists(binary_path):
            xbmc.log(f"MvPlugin Daemon: Daemon binary not found at: {binary_path}", xbmc.LOGERROR)
            return False

        # === Android 平台特殊处理（绕过外部存储 noexec 限制） ===
        is_android = False
        try:
            if xbmc.getCondVisibility('System.Platform.Android'):
                is_android = True
        except Exception:
            pass
        if not is_android:
            system = platform.system().lower()
            if 'android' in system or sys.platform.startswith('android'):
                is_android = True

        if is_android:
            try:
                # 获取 Android 内部私有可执行的 cache 目录（绕过外部存储 noexec 限制）
                package_name = 'org.xbmc.kodi'
                try:
                    with open('/proc/self/cmdline', 'r') as f:
                        cmdline = f.read()
                    parts = cmdline.split('\x00')
                    if parts and parts[0] and '.' in parts[0]:
                        package_name = parts[0].strip()
                except Exception:
                    pass
                
                temp_dir = f'/data/data/{package_name}/cache'
                try:
                    if not os.path.exists(temp_dir):
                        os.makedirs(temp_dir, exist_ok=True)
                except Exception:
                    # Fallback: 如果 /data/data/包名/cache 无法创建或写入，退回到 special://temp
                    temp_dir = xbmcvfs.translatePath('special://temp')
                
                dest_binary_path = os.path.join(temp_dir, os.path.basename(binary_path))
                
                # 仅当文件不存在或大小不一致时才拷贝，优化写入
                if not os.path.exists(dest_binary_path) or os.path.getsize(dest_binary_path) != os.path.getsize(binary_path):
                    xbmc.log(f"MvPlugin Daemon: Copying binary to Android private directory: {dest_binary_path}", xbmc.LOGINFO)
                    import shutil
                    shutil.copy2(binary_path, dest_binary_path)
                
                binary_path = dest_binary_path
            except Exception as e:
                xbmc.log(f"MvPlugin Daemon: Failed to prepare executable binary on Android: {e}", xbmc.LOGWARNING)

        # 确保可执行权限
        try:
            os.chmod(binary_path, 0o755)
        except Exception as e:
            xbmc.log(f"MvPlugin Daemon: Failed to chmod +x for daemon binary: {e}", xbmc.LOGWARNING)

        tokens_file = get_tokens_file_path()

        # 3. 启动后台进程
        cmd = [binary_path, '-tokens-file', tokens_file]
        xbmc.log(f"MvPlugin Daemon: Starting daemon command: {' '.join(cmd)}", xbmc.LOGINFO)
        try:
            # 重定向输出到 daemon.log 以便调试排错
            log_file_path = os.path.join(os.path.dirname(tokens_file), 'daemon.log')
            try:
                log_file = open(log_file_path, 'a', encoding='utf-8')
                log_file.write(f"\n--- Daemon start at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                log_file.flush()
            except Exception:
                log_file = subprocess.DEVNULL

            # 继承当前环境变量，并额外注入 Python 检测到的系统代理，以供 Go 后端连接外网使用
            env = os.environ.copy()
            try:
                import urllib.request
                proxies = urllib.request.getproxies()
                if 'http' in proxies:
                    env['HTTP_PROXY'] = proxies['http']
                    env['http_proxy'] = proxies['http']
                if 'https' in proxies:
                    env['HTTPS_PROXY'] = proxies['https']
                    env['https_proxy'] = proxies['https']
                # 本地回环接口不走代理，防止环流
                env['NO_PROXY'] = '127.0.0.1,localhost'
                env['no_proxy'] = '127.0.0.1,localhost'
            except Exception as pe:
                xbmc.log(f"MvPlugin Daemon: Failed to get system proxies: {pe}", xbmc.LOGWARNING)

            # 使用 subprocess.Popen 启动
            popen_kwargs = {
                'stdout': log_file,
                'stderr': log_file,
                'env': env,
            }

            if sys.platform.startswith('win') or platform.system().lower() == 'windows':
                # Windows 下隐藏黑色命令行窗口
                try:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    popen_kwargs['startupinfo'] = startupinfo
                except Exception:
                    pass
                popen_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            else:
                popen_kwargs['close_fds'] = True

            _daemon_process = subprocess.Popen(
                cmd,
                **popen_kwargs
            )
            
            # 将进程 PID 写入文件
            write_pid_file(_daemon_process.pid)
            
        except Exception as e:
            xbmc.log(f"MvPlugin Daemon: Failed to execute daemon binary: {e}", xbmc.LOGERROR)
            clean_pid_file()
            return False

        # 4. 端口健康检查（轮询尝试连接直到成功，设置 20 秒超时）
        start_time = time.time()
        while time.time() - start_time < 20.0:
            if _daemon_process.poll() is not None:
                xbmc.log(f"MvPlugin Daemon: Daemon exited prematurely with code {_daemon_process.returncode}", xbmc.LOGERROR)
                _daemon_process = None
                clean_pid_file()
                return False

            if is_port_in_use(17654):
                xbmc.log("MvPlugin Daemon: Daemon started and verified successfully on port 17654.", xbmc.LOGINFO)
                return True
            time.sleep(0.1)

        xbmc.log("MvPlugin Daemon: Timeout waiting for daemon to start.", xbmc.LOGERROR)
        stop_daemon()
        return False
    finally:
        # 释放目录锁
        try:
            if os.path.exists(lock_dir):
                try:
                    os.rmdir(lock_dir)
                except OSError:
                    import shutil
                    shutil.rmtree(lock_dir, ignore_errors=True)
        except Exception:
            pass

def stop_daemon():
    """优雅关闭守护进程"""
    global _daemon_process
    
    # 优先采用当前解释器实例内持有的 _daemon_process 句柄
    if _daemon_process is not None:
        xbmc.log("MvPlugin Daemon: Stopping daemon process via process handle...", xbmc.LOGINFO)
        try:
            _daemon_process.terminate()
            # 轮询 2 秒等待退出
            for _ in range(20):
                if _daemon_process.poll() is not None:
                    break
                time.sleep(0.1)
            else:
                xbmc.log("MvPlugin Daemon: Process did not terminate, killing it...", xbmc.LOGWARNING)
                _daemon_process.kill()
                _daemon_process.wait()
        except Exception as e:
            xbmc.log(f"MvPlugin Daemon: Error stopping daemon via handle: {e}", xbmc.LOGERROR)
        finally:
            _daemon_process = None
            clean_pid_file()
        return

    # 若没有句柄，尝试从 pid 文件中读取并跨进程杀死该 daemon
    pid_file = get_pid_file_path()
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            xbmc.log(f"MvPlugin Daemon: Stopping daemon process via PID file (PID: {pid})...", xbmc.LOGINFO)
            
            import signal
            # 尝试发送 SIGTERM 信号
            try:
                os.kill(pid, signal.SIGTERM)
                # 轮询 2 秒等待端口释放
                for _ in range(20):
                    if not is_port_in_use(17654):
                        break
                    time.sleep(0.1)
                else:
                    xbmc.log(f"MvPlugin Daemon: Process PID {pid} did not terminate, sending SIGKILL...", xbmc.LOGWARNING)
                    os.kill(pid, signal.SIGKILL)
            except OSError as oe:
                # 进程可能已经退出，或者没有控制权限
                xbmc.log(f"MvPlugin Daemon: OS error signalling PID {pid}: {oe}", xbmc.LOGWARNING)
        except Exception as e:
            xbmc.log(f"MvPlugin Daemon: Error stopping daemon via PID file: {e}", xbmc.LOGERROR)
        finally:
            clean_pid_file()

# 注册 atexit 钩子以防止孤儿/僵尸进程
# 只有当主启动脚本是 service.py 时才在 atexit 自动清理，防止临时脚本退出时误杀守护进程
main_file = os.path.basename(sys.argv[0])
if main_file == 'service.py':
    atexit.register(stop_daemon)

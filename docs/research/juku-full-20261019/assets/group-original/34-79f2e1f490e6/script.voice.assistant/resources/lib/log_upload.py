"""Use the same latest-log uploader as CoreELEC Settings -> Submit Log."""
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import time

COMMAND = '/usr/bin/pastekodi'
MAX_OUTPUT = 64 * 1024


def upload(cancelled=lambda: False, timeout=90):
    if cancelled():
        raise InterruptedError('已取消上传日志。')
    if not Path(COMMAND).is_file() or not os.access(COMMAND, os.X_OK):
        raise ValueError('当前系统没有 CoreELEC 日志上传程序 pastekodi。')
    try:
        process = subprocess.Popen([COMMAND], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        raise ValueError('无法启动 CoreELEC 日志上传程序。') from None
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancelled():
                raise InterruptedError('已停止日志上传；若服务端已接收，已上传的内容不会自动撤回。')
            if time.monotonic() >= deadline:
                raise ValueError('日志上传超时，未取得短网址，请检查网络。')
            readable, _, _ = select.select([process.stdout], [], [], .1)
            if not readable:
                continue
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > MAX_OUTPUT:
                raise ValueError('日志上传程序返回异常，未取得有效短网址。')
        while process.poll() is None:
            if cancelled():
                raise InterruptedError('已停止等待日志上传结果。')
            if time.monotonic() >= deadline:
                raise ValueError('日志上传超时，未取得短网址，请检查网络。')
            time.sleep(.05)
        code = process.returncode
        if cancelled():
            raise InterruptedError('已停止等待日志上传结果。')
        if code != 0:
            raise ValueError('日志上传失败，未取得短网址，请检查网络后重试。')
        for word in output.decode('utf-8', errors='replace').split():
            # The official service also returns versioned paths, e.g. /2/rkwl.
            if re.fullmatch(r'https?://paste\.coreelec\.org/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*', word):
                return {'uploaded': True, 'url': word,
                        'scope': '最新 Kodi 日志、系统日志及相关 CE 配置（与 CE 设置提交日志一致）'}
        # Never echo failed upload output: it may contain local log text.
        raise ValueError('日志服务没有返回有效短网址，不能确认上传成功。')
    finally:
        # pastekodi launches a shell pipeline and curl; stop the whole owned
        # process group so cancellation cannot leave an uploader running.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=.3)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()

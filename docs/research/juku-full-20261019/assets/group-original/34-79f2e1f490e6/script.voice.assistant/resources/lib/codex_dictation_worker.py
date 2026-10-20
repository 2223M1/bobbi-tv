"""Keep subscription auth and HTTPS out of Kodi's Python interpreter."""
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from resources.lib.codex_dictation import DictationError, MAX_PCM, managed_headers, transcribe


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def read_exact(source, size):
    data = bytearray()
    while len(data) < size:
        chunk = source.read(size - len(data))
        if not chunk:
            raise DictationError('订阅听写音频连接已关闭。')
        data.extend(chunk)
    return bytes(data)


def main():
    source = sys.stdin.buffer
    config = json.loads(source.readline(8193))
    profile = config['profile']
    if not isinstance(profile, str) or not profile or len(profile) > 4096:
        raise DictationError('订阅听写配置无效。')
    timeout = max(5, min(60, int(config.get('timeout', 30))))
    proxy = config.get('proxy', '')
    def get_headers(refresh=False):
        return managed_headers(ROOT, profile, timeout, proxy, refresh)
    headers = get_headers()
    emit({'type': 'ready'})
    pcm = bytearray()
    while True:
        size = struct.unpack('>I', read_exact(source, 4))[0]
        if size == 0:
            break
        if size > 6400 or size % 2 or len(pcm) + size > MAX_PCM:
            raise DictationError('订阅听写音频输入无效。')
        pcm.extend(read_exact(source, size))
    text = transcribe(bytes(pcm), headers, lambda: get_headers(True), timeout, proxy)
    emit({'type': 'result', 'last': True, 'text': text})


if __name__ == '__main__':
    try:
        main()
    except DictationError as error:
        emit({'type': 'error', 'error': str(error)})
        sys.exit(1)
    except Exception:
        emit({'type': 'error', 'error': '订阅听写进程失败，请检查网络、登录状态和插件版本。'})
        sys.exit(1)

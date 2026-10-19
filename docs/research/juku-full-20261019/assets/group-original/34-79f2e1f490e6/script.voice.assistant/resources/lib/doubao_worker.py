"""Isolated TLS/WebSocket worker. Credentials and PCM arrive over a private pipe."""
import json
from pathlib import Path
import struct
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'resources/vendor'))

from resources.lib.doubao_config import validate_key, validate_resource
from resources.lib.doubao_protocol import URL, full_request, audio_request, parse_response
import websocket


def main():
    connection, reader = None, None
    ended = threading.Event()
    output_lock = threading.Lock()
    secret = ''

    def emit(value):
        line = json.dumps(value, ensure_ascii=False)
        if secret:
            line = line.replace(secret, '[已隐藏]')
        with output_lock:
            print(line, flush=True)

    def exact(size):
        result = bytearray()
        while len(result) < size:
            chunk = sys.stdin.buffer.read(size - len(result))
            if not chunk:
                raise InterruptedError('调用方已结束豆包识别。')
            result.extend(chunk)
        return bytes(result)

    try:
        raw = sys.stdin.buffer.readline(4097)
        if len(raw) > 4096 or not raw.endswith(b'\n'):
            raise ValueError('豆包请求配置无效。')
        config = json.loads(raw)
        secret = validate_key(config['api_key'])
        resource = validate_resource(config['resource_id'])
        timeout = max(5, min(60, int(config['timeout'])))
        request_id = config['request_id']
        headers = {'X-Api-Key': secret, 'X-Api-Resource-Id': resource,
                   'X-Api-Request-Id': request_id, 'X-Api-Connect-Id': request_id,
                   'X-Api-Sequence': '-1'}
        connection = websocket.create_connection(URL, header=headers, timeout=timeout,
                                                  enable_multithread=True, redirect_limit=0)
        log_id = connection.getheaders().get('x-tt-logid', '')
        connection.send_binary(full_request())

        def receive():
            try:
                while not ended.is_set():
                    response = parse_response(connection.recv())
                    emit(dict(type='result', **response))
                    if response['last']:
                        ended.set()
            except RuntimeError as error:
                emit({'type': 'error', 'error': str(error)})
                ended.set()
            except Exception:
                if not ended.is_set():
                    emit({'type': 'error', 'error': '豆包连接中断、超时或返回格式无效。'})
                ended.set()

        reader = threading.Thread(target=receive, name='doubao-responses', daemon=True)
        reader.start()
        emit({'type': 'ready', 'log_id': log_id})
        sequence, total, pending = 2, 0, bytearray()
        while not ended.is_set():
            size = struct.unpack('>I', exact(4))[0]
            if size == 0:
                connection.send_binary(audio_request(sequence, bytes(pending), last=True))
                if not ended.wait(timeout):
                    raise TimeoutError()
                break
            if size % 2 or not 0 < size <= 6400:
                raise ValueError('豆包音频输入无效。')
            total += size
            if total > 30 * 32000:
                raise ValueError('豆包单次录音不能超过 30 秒。')
            pending.extend(exact(size))
            # Keep one final segment so the negative packet carries real PCM.
            while len(pending) > 6400:
                connection.send_binary(audio_request(sequence, bytes(pending[:6400])))
                del pending[:6400]
                sequence += 1
    except websocket.WebSocketBadStatusException as error:
        status = error.status_code
        message = {401: '豆包 API Key 无效或已失效。', 403: '豆包 Key 无权限，请检查服务开通和资源类型。',
                   429: '豆包服务限流，请稍后再试。'}.get(status, '豆包连接失败，请检查网络与服务配置。')
        emit({'type': 'error', 'error': message + ' (HTTP {})'.format(status)})
    except InterruptedError:
        pass
    except Exception:
        emit({'type': 'error', 'error': '豆包连接失败或超时，请检查网络、API Key 和资源类型。'})
    finally:
        ended.set()
        if connection:
            connection.shutdown()
        if reader:
            reader.join(timeout=.5)


if __name__ == '__main__':
    main()

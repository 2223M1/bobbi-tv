"""Bounded local playback IPC, independent of cloud preparation availability."""
import json
import socket
import time

SOCKET_PATH = None  # Default transport is the device-local portable host.
MAX_FRAME = 16384


def call(message, path=SOCKET_PATH, timeout=0.3):
    if not isinstance(message, dict) or not 0 < timeout <= 0.3:
        raise ValueError('Bounded object request required')
    if path is None:
        from bobbi_platform.runtime import call as host_call
        return host_call('playback', message, timeout=timeout)
    if not hasattr(socket, 'AF_UNIX'):
        raise OSError('Local Unix playback socket is unavailable on this runtime')
    payload = json.dumps(message, separators=(',', ':'), ensure_ascii=False).encode('utf-8') + b'\n'
    if len(payload) > MAX_FRAME:
        raise ValueError('Playback request exceeds frame budget')
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(path)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Playback service connection budget expired')
        connection.settimeout(remaining)
        connection.sendall(payload)
        data = bytearray()
        while b'\n' not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Playback service response budget expired')
            connection.settimeout(remaining)
            chunk = connection.recv(min(4096, MAX_FRAME + 1 - len(data)))
            if not chunk:
                raise OSError('Playback service closed without response')
            data.extend(chunk)
            if len(data) > MAX_FRAME:
                raise ValueError('Playback response exceeds frame budget')
    line, trailing = bytes(data).split(b'\n', 1)
    if trailing:
        raise ValueError('One response per request required')
    response = json.loads(line)
    if not isinstance(response, dict) or response.get('ok') is not True:
        raise RuntimeError('播放控制服务未接受本次请求')
    return response['result']

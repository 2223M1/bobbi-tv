"""Volcengine SAUC v3 binary framing; no language, hotwords or context."""
import gzip
import json
import struct
import zlib

URL = 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream'
MAX_RESPONSE = 1024 * 1024


def request_body():
    return {'user': {'uid': 'kodi-voice-assistant'},
            'audio': {'format': 'pcm', 'codec': 'raw', 'rate': 16000, 'bits': 16, 'channel': 1},
            'request': {'model_name': 'bigmodel', 'enable_itn': True, 'enable_punc': True,
                        'enable_ddc': False, 'result_type': 'full'}}


def packet(message_type, sequence, payload, last=False):
    compressed = gzip.compress(payload)
    header = bytes((0x11, (message_type << 4) | (3 if last else 1), 0x11, 0))
    return header + struct.pack('>iI', -sequence if last else sequence, len(compressed)) + compressed


def full_request():
    return packet(1, 1, json.dumps(request_body(), ensure_ascii=False).encode('utf-8'))


def audio_request(sequence, pcm, last=False):
    if len(pcm) % 2 or len(pcm) > 6400:
        raise ValueError('豆包音频包必须为不超过 200ms 的完整 S16_LE 音频。')
    return packet(2, sequence, pcm, last)


def parse_response(data):
    if not isinstance(data, bytes) or not 8 <= len(data) <= MAX_RESPONSE or data[0] >> 4 != 1:
        raise ValueError('豆包返回的二进制消息无效。')
    size, message_type, flags = (data[0] & 15) * 4, data[1] >> 4, data[1] & 15
    serialization, compression = data[2] >> 4, data[2] & 15
    if not 4 <= size <= len(data) or message_type not in (9, 15) or flags & ~7:
        raise ValueError('豆包返回的消息类型无效。')
    position, sequence, event, code = size, 0, 0, 0

    def integer(signed=False):
        nonlocal position
        if position + 4 > len(data):
            raise ValueError('豆包返回的消息不完整。')
        value = int.from_bytes(data[position:position + 4], 'big', signed=signed)
        position += 4
        return value

    if flags & 1:
        sequence = integer(True)
    if flags & 4:
        event = integer(True)
    if message_type == 15:
        code = integer()
    length = integer()
    if length != len(data) - position:
        raise ValueError('豆包返回的数据长度不匹配。')
    payload = data[position:]
    if compression == 1:
        decoder = zlib.decompressobj(31)
        payload = decoder.decompress(payload, MAX_RESPONSE + 1)
        if len(payload) > MAX_RESPONSE or not decoder.eof or decoder.unused_data:
            raise ValueError('豆包返回的解压数据无效或过大。')
    elif compression != 0:
        raise ValueError('豆包返回的压缩格式无效。')
    if serialization != 1:
        raise ValueError('豆包返回的序列化格式无效。')
    value = json.loads(payload) if payload else {}
    if not isinstance(value, dict):
        raise ValueError('豆包返回的识别数据无效。')
    if message_type == 15 or value.get('code', 0) not in (0, 20000000):
        # Server error descriptions may echo request data or credentials.
        raise RuntimeError('豆包识别服务返回错误（{}）。'.format(code or value.get('code', '未知')))
    result = value.get('result', {})
    if isinstance(result, list):
        text = ''.join(x.get('text', '') for x in result if isinstance(x, dict))
    elif isinstance(result, dict):
        text = result.get('text', '')
    else:
        raise ValueError('豆包识别结果格式无效。')
    if not isinstance(text, str) or len(text) > 16000:
        raise ValueError('豆包识别文字无效或过长。')
    return {'last': bool(flags & 2), 'sequence': sequence, 'event': event, 'text': text.strip()}

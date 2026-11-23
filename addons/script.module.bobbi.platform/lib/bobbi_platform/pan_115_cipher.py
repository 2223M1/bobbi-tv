"""115 wire codec, adapted for Kodi Python from p115rsacipher.

Upstream author: ChenyangGao <https://chenyanggao.github.io>
Source: p115client commit 856e4f8f09ce034534bd458f06d3dee4474a1698,
modules/p115rsacipher/p115rsacipher/__init__.py. See licenses/p115rsacipher.txt.
At this revision the module LICENSE is GPLv3 but pyproject declares MIT;
licenses/p115rsacipher-pyproject.txt preserves that conflicting metadata.
Applicability and distribution clearance are unresolved, not an MIT grant.
Bobbi changes (2026-11-13): explicit byte order / older-Python syntax, bounded
inputs, strict base64/block validation and local-only error codes.
The public protocol constants below are not account or application credentials.
This deterministic legacy wire encoding is not a general encryption facility.
"""
from base64 import b64decode, b64encode
from binascii import Error

from .pan_accounts import PanError

_TABLE = bytes.fromhex(
    'f0e569aebfdcbf8a1a45e8be7da673b8de8fe7c445da86c49b648b146ab4f1aa'
    '3801359e26692c86006b4fa5363462a62a966818f24afdbd6b978f4d8f8913b76c8e'
    '93ed0e0d483ed72f88d8fefe7e8650954fd1eb832634db667b9c7e9d7a8132eab633'
    'de3aa95934663baaba816048b9d5819cf86c8477ff5478265fbee81e369f34805c45'
    '2c9b76d51b8fccc3b8f5')
_MODULUS = int(
    '8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b860213'
    '6477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3'
    'bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1'
    'eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683', 16)
_EXPONENT = 65537
_SHORT = bytes.fromhex('8da5a58d')
_LONG = bytes.fromhex('7806ad4c33865d184c013f46')


def _xor(data, key):
    result = bytearray()
    head = len(data) % 4
    result.extend(a ^ b for a, b in zip(data[:head], key))
    for offset in range(head, len(data), len(key)):
        result.extend(a ^ b for a, b in zip(data[offset:offset + len(key)], key))
    return bytes(result)


def encrypt(data):
    if type(data) is str:
        data = data.encode('utf-8')
    if type(data) is not bytes or not 0 < len(data) <= 4096:
        raise PanError('PAN_REPLY_INVALID')
    payload = bytes(16) + _xor(_xor(data, _SHORT)[::-1], _LONG)
    result = bytearray()
    for offset in range(0, len(payload), 117):
        chunk = payload[offset:offset + 117]
        padded = b'\x00' + b'\x02' * (126 - len(chunk)) + b'\x00' + chunk
        result.extend(pow(int.from_bytes(padded, 'big'), _EXPONENT, _MODULUS).to_bytes(128, 'big'))
    return b64encode(result).decode('ascii')


def decrypt(value):
    try:
        if type(value) is not str or not 0 < len(value) <= 16384:
            raise ValueError
        wire = b64decode(value, validate=True)
        if not wire or len(wire) % 128:
            raise ValueError
        decoded = bytearray()
        for offset in range(0, len(wire), 128):
            block = int.from_bytes(wire[offset:offset + 128], 'big')
            if block >= _MODULUS:
                raise ValueError
            padded = pow(block, _EXPONENT, _MODULUS).to_bytes(128, 'big')
            split = padded.index(0, 2)
            if padded[0] != 0 or padded[1] not in (1, 2) or split < 10:
                raise ValueError
            decoded.extend(padded[split + 1:])
        if len(decoded) <= 16:
            raise ValueError
        key = bytes(_TABLE[132 - i * 12] ^ ((decoded[i] + _TABLE[i * 12]) & 255)
                    for i in range(12))
        return _xor(_xor(decoded[16:], key)[::-1], _SHORT)
    except (ValueError, TypeError, Error, OverflowError, IndexError):
        raise PanError('PAN_REPLY_INVALID') from None

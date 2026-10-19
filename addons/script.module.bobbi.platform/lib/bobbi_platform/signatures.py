"""Strict RSA-3072/SHA-256 PKCS#1 v1.5 public verification (RFC 8017).

Only verifies detached release manifests with a pinned offline-generated public
key. Private key operations use cryptography in the maintainer tooling, never
this module. No downloaded trust key or algorithm negotiation.
"""
import base64
import hashlib
import hmac
import re

DIGEST_INFO_SHA256 = bytes.fromhex('3031300d060960864801650304020105000420')
MODULUS_BYTES = 384
MAX_MANIFEST = 1024 * 1024


def verify(payload, signature, key):
    try:
        if (not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_MANIFEST
                or not isinstance(signature, str) or not isinstance(key, dict)
                or set(key) != {'algorithm', 'n', 'e'}
                or key['algorithm'] != 'RSA3072-SHA256' or key['e'] != 65537
                or type(key['e']) is not int or not isinstance(key['n'], str)
                or not re.fullmatch('[0-9a-f]{768}', key['n'])):
            return False
        n = int(key['n'], 16)
        if n.bit_length() != 3072 or n % 2 == 0:
            return False
        raw = base64.b64decode(signature, validate=True)
        if len(raw) != MODULUS_BYTES:
            return False
        number = int.from_bytes(raw, 'big')
        if number >= n:
            return False
        encoded = pow(number, key['e'], n).to_bytes(MODULUS_BYTES, 'big')
        digest = DIGEST_INFO_SHA256 + hashlib.sha256(payload).digest()
        expected = b'\x00\x01' + b'\xff' * (MODULUS_BYTES - len(digest) - 3) + b'\x00' + digest
        return hmac.compare_digest(encoded, expected)
    except (ValueError, TypeError, OverflowError):
        return False

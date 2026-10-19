import base64
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from bobbi_platform.signatures import verify


@pytest.fixture(scope='module')
def proof():
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_numbers()
    key = {'algorithm': 'RSA3072-SHA256', 'n': format(public.n, 'x'), 'e': public.e}
    payload = b'{"sequence":1,"channel":"preview"}'
    signature = base64.b64encode(private.sign(payload, padding.PKCS1v15(), hashes.SHA256())).decode()
    return payload, signature, key


def test_verified_against_cryptography(proof):
    assert verify(*proof)


def test_changed_manifest_or_signature_rejected(proof):
    data, signature, key = proof
    assert not verify(data + b' ', signature, key)
    assert not verify(data, base64.b64encode(b'\0' * 384).decode(), key)
    assert not verify(data, signature[:-1], key)


@pytest.mark.parametrize('field,value', [('e', 3), ('n', 'ab' * 384),
    ('algorithm', 'none'), ('e', True), ('n', '00' * 384)])
def test_no_algorithm_or_key_downgrade(proof, field, value):
    data, signature, key = proof
    assert not verify(data, signature, dict(key, **{field: value}))


def test_oversized_payload_fails_closed(proof):
    _, signature, key = proof
    assert not verify(b'a' * (1024 * 1024 + 1), signature, key)

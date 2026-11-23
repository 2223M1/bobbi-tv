"""115 login HTTP framing: real http.client parser with an in-memory socket."""
from functools import partial
from http.client import HTTPResponse
from io import BytesIO
import json
from types import SimpleNamespace

import pytest

from bobbi_platform.cloud115 import request, CloudError, Login
from bobbi_platform import cloud115


class Socket:
    def __init__(self, wire):
        self.wire = wire

    def makefile(self, *args, **kwargs):
        return BytesIO(self.wire)


def opener(body, length=None, chunked=False):
    headers = b'Transfer-Encoding: chunked\r\n' if chunked else (
        b'' if length is None else ('Content-Length: %s\r\n' % length).encode())
    response = HTTPResponse(Socket(b'HTTP/1.1 200 OK\r\n' + headers + b'\r\n' + body))
    response.begin()
    return SimpleNamespace(open=lambda *args, **kwargs: response)


TOKEN = dict(state=1, data=dict(uid='fixture', sign='fixture-sign', time=123,
    qrcode='https://115.com/scan/fixture'))
RAW = json.dumps(TOKEN).encode()


def test_valid_json_prefix_of_short_http_body_cannot_publish_qr():
    flow = Login(partial(request, opener=opener(RAW, len(RAW) + 19)))
    with pytest.raises(CloudError, match='INVALID_REPLY'):
        flow.begin()
    assert flow.token is None


@pytest.mark.parametrize('length', [str(2*1024*1024+1), 'invalid', '-1'])
def test_invalid_or_oversize_declared_reply_is_rejected(length):
    with pytest.raises(CloudError, match='INVALID_REPLY'):
        request('https://qrcodeapi.115.com/test', opener=opener(RAW, length))


def test_truncated_chunk_encoding_is_classified_not_leaked():
    body = ('%x\r\n' % (len(RAW) + 10)).encode() + RAW
    with pytest.raises(CloudError, match='INVALID_REPLY'):
        request('https://qrcodeapi.115.com/test', opener=opener(body, chunked=True))


@pytest.mark.parametrize('length', [None, len(RAW)])
def test_complete_bounded_reply_retains_compatibility(length):
    assert request('https://qrcodeapi.115.com/test', opener=opener(RAW, length)) == TOKEN


def test_complete_chunked_reply_is_supported():
    body = ('%x\r\n' % len(RAW)).encode() + RAW + b'\r\n0\r\n\r\n'
    assert request('https://qrcodeapi.115.com/test', opener=opener(body, chunked=True)) == TOKEN


def test_unframed_reply_still_has_a_byte_bound():
    with pytest.raises(CloudError, match='INVALID_REPLY'):
        request('https://qrcodeapi.115.com/test', opener=opener(b' ' * (cloud115.MAX_REPLY + 1)))


def test_malformed_json_and_network_errors_keep_distinct_fixed_categories():
    with pytest.raises(CloudError, match='INVALID_REPLY'):
        request('https://qrcodeapi.115.com/test', opener=opener(b'{invalid'))
    def offline(*args, **kwargs):
        raise OSError('fixture error with transport details')
    with pytest.raises(CloudError, match='^NETWORK_ERROR$'):
        request('https://qrcodeapi.115.com/test', opener=SimpleNamespace(open=offline))


def test_slow_reply_has_a_total_deadline_not_only_per_read_timeout(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(cloud115.time, 'monotonic', lambda: clock[0])
    class Response:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            pytest.fail('read1 must be preferred over read(n)')
        def read1(self, limit):
            clock[0] += 5.
            return b' '
    with pytest.raises(CloudError, match='^NETWORK_ERROR$'):
        request('https://qrcodeapi.115.com/test', opener=SimpleNamespace(open=lambda *a, **k: Response()))
    assert clock[0] == 10.

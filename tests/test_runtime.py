import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest
from bobbi_platform import runtime


def test_lifecycle_and_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / 'runtime.json'
    monkeypatch.setattr(runtime, 'profile', lambda **kw: path)
    server = runtime.Runtime(lambda action, body: {'action': action, 'body': body}, path)
    server.start()
    try:
        assert runtime.call('status', {}) == {'action': 'status', 'body': {}}
        with pytest.raises(HTTPError):
            urlopen(Request('http://127.0.0.1:%d/control' % server.server.server_port, data=b'{}'), timeout=2)
        with pytest.raises(ValueError):
            runtime.call('status', {'large': 'x' * 20000})
    finally:
        server.close()
        server.close()
    assert not path.exists()


def test_close_without_start_and_new_owner(tmp_path):
    path = tmp_path / 'runtime.json'
    server = runtime.Runtime(lambda *_: None, path)
    path.write_text(json.dumps({'token': 'new-owner'}))
    server.close()
    assert path.exists()
    with pytest.raises(RuntimeError):
        server.start()


def test_bounded_response(tmp_path, monkeypatch):
    path = tmp_path / 'runtime.json'
    monkeypatch.setattr(runtime, 'profile', lambda **kw: path)
    server = runtime.Runtime(lambda *_: 'x' * 20000, path)
    server.start()
    try:
        with pytest.raises(ValueError):
            runtime.call('large', {})
    finally:
        server.close()

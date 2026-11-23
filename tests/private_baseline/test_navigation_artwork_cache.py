from types import SimpleNamespace
import requests


def test_optional_artwork_network_failure_is_not_a_day_long_success(monkeypatch):
    from lib.api.fanart import fanart
    from lib.utils.general import utils
    saved, calls = {}, []
    def get(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise requests.ConnectionError('offline')
        return SimpleNamespace(json=lambda: {'tvposter': [
            {'url': 'https://assets.fanart.tv/example.jpg', 'lang': 'en', 'likes': '1'}]})
    monkeypatch.setattr(fanart.session, 'get', get)
    monkeypatch.setattr(fanart, 'get_setting', lambda *a: '')
    monkeypatch.setattr(utils, 'get_fanart', fanart.get_fanart)
    monkeypatch.setattr(utils, 'get_setting', lambda *a: 18)
    monkeypatch.setattr(utils, 'is_cache_enabled', lambda: True)
    monkeypatch.setattr(utils, 'get_cache_expiration', lambda: 24)
    monkeypatch.setattr(utils, 'cache', SimpleNamespace(get=lambda key: saved.get(key),
        set=lambda key, data, expires: saved.__setitem__(key, data)))
    assert utils.get_fanart_details(tvdb_id=42)['fanart_added'] is False
    assert saved == {}
    assert utils.get_fanart_details(tvdb_id=42)['fanart_added'] is True
    assert len(calls) == 2
    assert utils.get_fanart_details(tvdb_id=42)['fanart_added'] is True
    assert len(calls) == 2


def test_old_failed_artwork_cache_is_not_reused(monkeypatch):
    from lib.utils.general import utils
    monkeypatch.setattr(utils, 'cache', SimpleNamespace(get=lambda key: {'fanart_added': False}))
    assert utils.get_fanart_details(tvdb_id=42, cached_only=True) == {}

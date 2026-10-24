"""Actual catalogue projections share only their short-lived artwork endpoint."""
from copy import deepcopy
import json
from unittest.mock import MagicMock

import pytest


class Item:
    def __init__(self, label=''):
        self.label, self.art, self.properties = label, {}, {}
        self.tag = MagicMock()

    def getVideoInfoTag(self): return self.tag
    def setArt(self, art): self.art.update(art)
    def setProperty(self, key, value): self.properties[key] = value
    def getProperty(self, key): return self.properties.get(key, '')
    def setLabel(self, label): self.label = label
    def setLabel2(self, label): self.label2 = label
    def setContentLookup(self, value): pass


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    from bobbi_core import image_cache as images
    from bobbi_platform import paths
    calls = []
    real = images._configuration
    monkeypatch.setattr(paths, 'profile', lambda: tmp_path)
    monkeypatch.setattr(images, '_configuration', lambda path: (calls.append(path), real(path))[1])
    monkeypatch.setattr(images, 'fetch', lambda *a, **kw: pytest.fail('No presentation HTTP'))
    def publish(port=12345):
        (tmp_path / 'image-runtime.json').write_text(json.dumps(dict(port=port, token='a' * 64)))
    publish()
    return calls, publish


@pytest.mark.parametrize('mode', ['tv', 'movies'])
def test_catalogue_page_reuses_endpoint_and_next_page_reloads(endpoint, monkeypatch, mode):
    from lib.clients.tmdb import anime_fast_catalog as catalog, frontend_metadata as front, season_cards
    from lib.db.cached import cache
    calls, publish = endpoint
    monkeypatch.setattr(catalog.xbmcgui, 'ListItem', Item)
    monkeypatch.setattr(front, '_record', lambda key: dict(refresh_after=1e20, data=dict(
        poster_path='/detail.jpg', backdrop_path='/detail-bg.jpg')))
    monkeypatch.setattr(cache, 'get', lambda key: None)
    monkeypatch.setattr(front, 'flush', lambda: None)
    monkeypatch.setattr(season_cards, 'enqueue_directory', lambda rows: None)
    monkeypatch.setattr(season_cards, 'cached_view', lambda identifier: dict(
        season=2, poster_path='/season.jpg', air_date='2025-01-01'))
    pages = []
    monkeypatch.setattr(catalog.xbmcplugin, 'addDirectoryItems', lambda handle, rows: pages.append(rows))
    data = dict(total_pages=3, results=[dict(id=n + 1, name='动画', title='电影',
        original_name='Example', original_title='Example', poster_path='/series.jpg',
        backdrop_path='/background.jpg') for n in range(20)])
    original = deepcopy(data)
    def render():
        catalog._render_directory(data, lambda row: catalog._catalog_item(row, mode, {}),
                                  '作品', 'tvshows' if mode == 'tv' else 'movies',
                                  next_action='am6b_streaming_catalog')
    render()
    assert len(calls) == 1, 'configuration reads for 20 cards: {}'.format(len(calls))
    publish(23456)
    render()
    assert len(calls) == 2
    assert data == original
    for index, port in enumerate((12345, 23456)):
        rows = pages[index]
        assert len(rows) == 21
        assert rows[-1][1].properties['Bobi.NextPage'] == 'true'
        for url, item, folder in rows[:-1]:
            assert folder == (mode == 'tv')
            assert 'am6b_open_streaming_item' in url
            assert item.art['poster'].endswith('/w342/' + ('season.jpg' if mode == 'tv' else 'detail.jpg'))
            assert item.art['fanart'].endswith('/w1280/detail-bg.jpg')
            assert all(value.startswith('http://127.0.0.1:{}/'.format(port)) for value in item.art.values())


def test_generic_card_reuses_endpoint_without_changing_art_fields(endpoint, monkeypatch):
    from lib.utils.general import utils
    calls, publish = endpoint
    monkeypatch.setattr(utils, 'get_setting_fresh', lambda *a: '2')
    data = dict(poster_path='/poster.jpg', backdrop_path='/bg.jpg', images=dict(logos=[dict(file_path='/logo.png')]))
    item = Item()
    utils.set_listitem_artwork(item, data, {})
    assert len(calls) == 1, 'configuration reads for one generic card: {}'.format(len(calls))
    assert len(item.art) == 11
    assert item.art['poster'] == item.art['icon']
    assert item.art['fanart'] == item.art['tvshow.landscape']
    assert item.art['clearlogo'].endswith('/original/logo.png')
    before = dict(item.art)
    publish(23456)
    utils.set_listitem_artwork(item, data, {})
    assert len(calls) == 2
    assert item.art == {key: value.replace(':12345/', ':23456/') for key, value in before.items()}

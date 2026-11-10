"""Title history is local-first; optional metadata cannot change its routes."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest

from lib.clients.tmdb import frontend_metadata as metadata
from lib.utils.views import last_titles as history


class Item:
    def __init__(self, label):
        self.label, self.label2 = label, ''
        self.art, self.properties, self.menu = {}, {}, []
        self.tag = Mock()

    def getVideoInfoTag(self): return self.tag
    def setLabel(self, value): self.label = value
    def setLabel2(self, value): self.label2 = value
    def setArt(self, value): self.art.update(value)
    def setProperty(self, key, value): self.properties[key] = value
    def addContextMenuItems(self, value): self.menu.extend(value)


def record(number, mode='movies', **extra):
    return dict(timestamp='Mon, {:02d} Nov 2026 01:00 PM'.format(number), mode=mode,
                ids=dict(tmdb_id=str(100 + number), imdb_id='tt{:07d}'.format(number)), **extra)


@pytest.fixture
def page(monkeypatch):
    rows, directory, events = {}, [], []
    from lib.db.cached import cache
    from lib.clients.tmdb.utils import utils
    monkeypatch.setattr(history, 'pickle_db', SimpleNamespace(get_key=lambda key: rows))
    monkeypatch.setattr(history, 'make_list_item', lambda label: Item(label))
    monkeypatch.setattr(history, 'build_url', lambda action, **kwargs: action + '?' + json.dumps(kwargs, sort_keys=True))
    monkeypatch.setattr(history, 'add_directory_items_batch', lambda items: (directory.extend(items), events.append('items')))
    monkeypatch.setattr(history, 'end_of_directory', lambda: events.append('end'))
    monkeypatch.setattr(history, 'apply_section_view', lambda view: events.append(view))
    monkeypatch.setattr(history, 'set_pluging_category', lambda value: None)
    monkeypatch.setattr(history, 'translation', lambda value: str(value))
    monkeypatch.setattr(history, 'kodilog', lambda message: events.append(message))
    monkeypatch.setattr(cache, 'get', lambda key: None)
    monkeypatch.setattr(metadata, '_pending', {})
    monkeypatch.setattr(metadata, '_record', lambda key: {})
    monkeypatch.setattr(metadata, 'flush', lambda: events.append('flush'))
    monkeypatch.setattr(metadata, '_fetch', lambda *args: pytest.fail('foreground metadata HTTP'))
    monkeypatch.setattr(utils, 'tmdb_get', lambda *args: pytest.fail('foreground tmdb_get'))
    return SimpleNamespace(rows=rows, directory=directory, events=events)


def route(entry):
    action, args = entry[0].split('?', 1)
    return action, json.loads(args)


def test_missing_cache_keeps_all_local_titles_timestamps_and_exact_routes(page):
    page.rows.update({'Original movie': record(1), 'Original show': record(2, 'tv')})
    before = deepcopy(page.rows)
    history.show_last_titles(None)
    assert [item.label for _, item, _ in page.directory] == [
        'Clear Titles', 'Original show — ' + before['Original show']['timestamp'],
        'Original movie — ' + before['Original movie']['timestamp']]
    assert route(page.directory[1]) == ('show_seasons_details', dict(ids=before['Original show']['ids'], mode='tv'))
    assert route(page.directory[2]) == ('search', dict(ids=before['Original movie']['ids'], mode='movies', query='Original movie'))
    assert page.directory[1][2] is True and page.directory[2][2] is False
    assert page.directory[2][1].properties['IsPlayable'] == 'true'
    assert page.rows == before
    assert set(metadata._pending) == {'tv:102', 'movie:101'}
    assert page.events[-3:] == ['end', 'view.history', 'flush']


def test_cached_metadata_enriches_display_without_replacing_history_label_or_route(page, monkeypatch):
    page.rows['Local exact title'] = record(1)
    monkeypatch.setattr(metadata, '_record', lambda key: dict(refresh_after=10**12, data=dict(
        title='缓存中文标题', original_title='Original English', overview='Cached plot',
        poster_path='/poster.jpg', release_date='2020-02-03',
        translations=dict(translations=[dict(iso_639_1='zh', iso_3166_1='CN', data=dict(title='缓存中文标题')),
                                       dict(iso_639_1='en', iso_3166_1='US', data=dict(title='Cached English'))]))))
    monkeypatch.setattr(metadata, 'image_url', lambda path, size: 'cached:' + path if path else '')
    history.show_last_titles({})
    entry = page.directory[1]
    assert entry[1].label == 'Local exact title — ' + page.rows['Local exact title']['timestamp']
    assert entry[1].properties['Bobi.Title.zh'] == '缓存中文标题'
    assert entry[1].art['poster'] == 'cached:/poster.jpg'
    entry[1].tag.setPlot.assert_called_with('Cached plot')
    assert route(entry)[1]['query'] == 'Local exact title'
    assert route(entry)[1]['ids'] == page.rows['Local exact title']['ids']
    assert metadata._pending == {}


@pytest.mark.parametrize('failure', [OSError, ValueError, RuntimeError, TypeError])
def test_metadata_failure_never_hides_history_or_loses_local_label(page, monkeypatch, failure):
    page.rows.update({'Movie': record(1), 'Show': record(2, 'tv')})
    def broken(item, *args):
        item.setLabel('partial cached title')
        raise failure('optional display unavailable')
    monkeypatch.setattr(metadata, 'apply', broken)
    history.show_last_titles({})
    assert len(page.directory) == 3
    assert [item.label.split(' — ')[0] for _, item, _ in page.directory[1:]] == ['Show', 'Movie']
    assert route(page.directory[1])[0] == 'show_seasons_details'
    assert route(page.directory[2])[0] == 'search'
    assert page.events[-1] == 'flush'


def test_tg_route_payload_and_unknown_mode_policy_remain_unchanged(page, monkeypatch):
    payload = dict(id='tg-title', sources=[dict(key='source', opaque='original')])
    page.rows.update({'Telegram': record(1, 'tg_latest', tg_data=payload),
                      'Unsupported': record(2, 'anime')})
    monkeypatch.setattr(metadata, 'apply', lambda *args: pytest.fail('unsupported metadata mode'))
    before = deepcopy(page.rows)
    history.show_last_titles({})
    assert len(page.directory) == 2
    assert route(page.directory[1]) == ('list_jackgram_title_sources', dict(data=json.dumps(payload)))
    assert page.directory[1][2] is True and page.rows == before
    assert page.directory[1][1].label == 'Telegram — ' + before['Telegram']['timestamp']


@pytest.mark.parametrize('number', [0, 1, 10, 11, 23])
def test_existing_page_boundaries_order_and_management_items_are_preserved(page, number):
    page.rows.update({'Title {}'.format(i): record(i) for i in range(1, number + 1)})
    original = deepcopy(page.rows)
    page_number = 1 if number <= 11 else 2
    expected = sorted(list(reversed(list(original.items())))[(page_number - 1) * 10:page_number * 10],
                      key=history.parse_time, reverse=True)
    history.show_last_titles({'page': page_number})
    assert route(page.directory[0]) == ('clear_history', {'type': 'lth'})
    next_page = page_number * 10 < number
    entries = page.directory[1:-1] if next_page else page.directory[1:]
    assert [entry[1].label for entry in entries] == [title + ' — ' + data['timestamp'] for title, data in expected]
    for entry, (title, data) in zip(entries, expected):
        assert route(entry) == ('search', dict(mode='movies', query=title, ids=data['ids']))
        assert entry[1].menu == [('Delete from history', 'RunPlugin(' + history.build_url('delete_last_title_entry', title=title) + ')')]
    if next_page:
        assert route(page.directory[-1]) == ('titles_history', {'page': page_number + 1})
        assert page.directory[-1][1].properties['Bobi.NextPage'] == 'true'
    assert page.rows == original

"""Public details share cards/routes and never publish an obsolete completion."""
import json
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit
import xml.etree.ElementTree as ET

import pytest

from lib.gui import extras_window as extras
from lib.clients.tmdb import people_client as people
from lib.api.tmdbv3api.as_obj import AsObj
from test_detail_relationship_navigation import Item, page  # shared real card fixture


class ListControl:
    def __init__(self, writes):
        self.items, self.writes = [], writes

    def reset(self):
        self.items.clear()
        self.writes.append('reset')

    def addItem(self, item):
        self.items.append(item)
        self.writes.append('add')

    def getSelectedItem(self):
        return self.items[0]

    def setLabel(self, label):
        self.writes.append(('label', label))


@pytest.fixture
def window(monkeypatch):
    state = SimpleNamespace(properties={}, writes=[], jobs=[], commands=[])
    controls = {}
    def control(self, identifier):
        return controls.setdefault(identifier, ListControl(state.writes))
    def prop(self, key, value):
        state.properties[key] = value
        state.writes.append((key, value))
    monkeypatch.setattr(extras.BaseWindow, 'setProperty', prop)
    monkeypatch.setattr(extras.ExtrasWindow, 'getControl', control)
    monkeypatch.setattr(extras.ExtrasWindow, 'getControlList', control)
    monkeypatch.setattr(extras.threading, 'Thread', lambda target, args, **kw:
        SimpleNamespace(start=lambda: state.jobs.append((target, args))))
    monkeypatch.setattr(extras, 'execute_builtin', state.commands.append)
    monkeypatch.setattr(extras, 'get_fanart', lambda *a: {})
    monkeypatch.setattr(extras, 'kodilog', lambda *a: None)
    value = extras.ExtrasWindow('extras.xml', '', item_information=dict(
        tmdb_id='42', media_type='movie', title='中文 A&B + (C)', imdb_id='tt42'))
    value.onInit()
    state.value, state.controls = value, controls
    state.writes.clear()
    return state


@pytest.mark.parametrize('reopen', [False, True])
def test_details_late_completion_cannot_write_properties_controls_or_shared_data(window, monkeypatch, reopen):
    started, released = Event(), Event()
    def fetch(*args, **kwargs):
        started.set()
        assert released.wait(3)
        return AsObj(dict(id=42, overview='late', vote_average=9, imdb_id='tt99'))
    monkeypatch.setattr(extras, 'relationship_request', fetch)
    old_ready = window.value._details_ready
    job, args = window.jobs[0]
    worker = Thread(target=job, args=args)
    worker.start()
    try:
        assert started.wait(2)
        window.value.close()
        if reopen:
            window.value.onInit()
        window.writes.clear()
        released.set()
        worker.join(3)
        assert not worker.is_alive()
        assert window.writes == []
        assert window.value._tmdb_data is None
        assert window.value.imdb_id == 'tt42'
        assert old_ready.is_set()
        if reopen:
            assert not window.value._details_ready.is_set()
    finally:
        released.set()
        worker.join(3)


@pytest.mark.parametrize('panel', ['text', 'media', 'cast'])
def test_late_list_render_never_resets_the_current_list(window, monkeypatch, panel):
    value = window.value
    old_generation, old_ready = value._generation, value._details_ready
    value.close()
    value.onInit()
    window.writes.clear()
    monkeypatch.setattr(extras, 'relationship_request', lambda *a, **kw:
        AsObj(dict(cast=[dict(id=1, name='late')])) )
    monkeypatch.setattr(extras, 'relationship_person', lambda *a: ('route', Item('late'), True))
    def render():
        if panel == 'text':
            value._populate_text_panel(value.reviews_list_id, ['late'], 'count')
        elif panel == 'media':
            value.populate_media_list(value.similar_list_id, [dict(id=1, title='late')], 'count')
        else:
            value.fetch_cast()
    worker = Thread(target=value._run_worker, args=(old_generation, old_ready, render))
    worker.start(); worker.join(3)
    assert window.writes == []


@pytest.mark.parametrize('data', [dict(id=42), RuntimeError('transport cancelled')])
def test_bounded_request_checks_window_cancellation_before_and_after_io(page, data):
    cancelled = [True]
    with pytest.raises(InterruptedError):
        people.relationship_request('movie_details', 42, cancelled=lambda: cancelled[0])
    assert page.calls == []
    cancelled[0] = False
    page.data = data
    page.during_fetch = lambda: cancelled.__setitem__(0, True)
    with pytest.raises(InterruptedError):
        people.relationship_request('movie_details', 42, cancelled=lambda: cancelled[0])
    assert len(page.calls) == 1


def test_dialog_uses_bounded_summary_cards_and_one_owned_batch(window, page):
    window.value.populate_media_list(2051, AsObj(dict(results=[
        dict(id=i+1, title='中文 A&B', media_type='movie') for i in range(30)])), 'count')
    items = window.controls[2051].items
    assert len(items) == 20
    assert window.properties['count'] == '(20)'
    assert len(page.local_calls) == 1 and len(page.local_calls[0]['identities']) == 20
    assert all(item.properties['IsPlayable'] == 'false' for item in items)
    assert len({item.properties['Bobbi.CardKey'] for item in items}) == 20
    assert not page.calls


def test_closed_dialog_does_not_request_owned_status(window, page):
    window.value.close()
    window.value.populate_media_list(2051, [dict(id=1, title='old')], 'count')
    assert page.local_calls == [] and window.writes == []


def test_cast_reuses_the_primary_details_payload_without_a_second_request(window, page):
    calls = []
    details = AsObj(dict(id=42, credits=dict(cast=[dict(id=7, name='演员')])))
    window.value._request = lambda path, params: calls.append((path, params)) or details
    window.value.fetch_details_and_artwork()
    window.value.fetch_cast()
    assert len(calls) == 1 and calls[0][0] == 'movie_details'
    assert set(calls[0][1]['append_to_response'].split(',')) == {'credits', 'videos', 'external_ids'}
    assert len(window.controls[2050].items) == 1


def test_collection_cards_are_bounded_and_wrong_identity_is_ignored(window, page, monkeypatch):
    class MoreItem(Item):
        def getProperty(self, key): return self.properties.get(key, '')
    monkeypatch.setattr(extras.xbmcgui, 'ListItem', MoreItem)
    window.value._tmdb_data = AsObj(dict(belongs_to_collection=dict(id=9, name='系列')))
    window.value._request = lambda *a: AsObj(dict(id=9, parts=[dict(id=i+1, title='电影') for i in range(30)]))
    window.value._populate_collection()
    assert len(window.controls[2064].items) == 20
    assert len(page.local_calls) == 1 and len(page.local_calls[0]['identities']) == 19
    more = window.controls[2064].items[-1]
    assert 'handle_collection_details' in more.properties['browse_url']
    assert 'collection_id=9' in more.properties['browse_url']
    window.writes.clear()
    page.local_calls.clear()
    window.value._request = lambda *a: AsObj(dict(id=999, parts=[dict(id=99, title='错误')]))
    window.value._populate_collection()
    assert len(window.controls[2064].items) == 20 and not page.local_calls
    assert 'reset' not in window.writes
    window.controls[2064].items = [more]
    window.value._handle_click(2064)
    assert window.commands == ['ActivateWindow(Videos,%s,return)' % more.properties['browse_url']]


@pytest.mark.parametrize('tv_data', [{}, {'season': 2}, {'episode': 3}, {'season': -1, 'episode': 1}, 'broken'])
def test_tv_without_an_exact_episode_opens_seasons_not_default_s1e1(window, tv_data):
    window.value.media_type = 'tv'
    window.value.item_information['tv_data'] = tv_data
    window.value._handle_click(10)
    command = window.commands[0]
    assert command.startswith('ActivateWindow(Videos,')
    params = dict(parse_qsl(urlsplit(command.removeprefix('ActivateWindow(Videos,').removesuffix(',return)')).query))
    assert params['action'] == 'show_seasons_details'
    assert json.loads(params['ids']) == dict(tmdb_id='42', imdb_id='tt42')
    assert 'tv_data' not in params


def test_explicit_tv_episode_keeps_existing_search_context_and_encoded_title(window):
    value = window.value
    value.media_type = 'tv'
    value.item_information['tv_data'] = dict(season=0, episode=3, name='A&B')
    value._handle_click(10)
    command = window.commands[0]
    params = dict(parse_qsl(urlsplit(command.removeprefix('PlayMedia(').removesuffix(')')).query))
    assert params['action'] == 'search' and params['query'] == value.title
    assert json.loads(params['tv_data']) == dict(season=0, episode=3, name='A&B')


def test_related_work_route_encodes_title_and_cast_reuses_existing_directory(window):
    class Selected:
        def __init__(self, data): self.data = data
        def getProperty(self, key): return self.data.get(key, '')
    value = window.value
    window.controls[value.similar_list_id].items = [Selected(dict(id='52', media_type='tv', name=value.title))]
    value._handle_click(value.similar_list_id)
    command = window.commands.pop()
    params = dict(parse_qsl(urlsplit(command.removeprefix('RunPlugin(').removesuffix(')')).query))
    assert params == dict(action='extras', id='52', media_type='tv', title=value.title)
    value.onInit()
    window.controls[value.cast_list_id].items = [Selected(dict(id='7'))]
    value._handle_click(value.cast_list_id)
    assert 'handle_tmdb_person_details' in window.commands[0]
    assert 'person_id=7' in window.commands[0]


def test_old_person_entry_and_summary_cards_do_not_fetch_person_details(page, monkeypatch):
    from lib.utils.kodi import utils
    commands, rows = [], []
    monkeypatch.setattr(utils, 'execute_builtin', commands.append)
    monkeypatch.setattr(people, 'add_kodi_dir_item', lambda **kw: rows.append(kw))
    people.PeopleClient.show_people_details(dict(id=7, name='人物'), 'movies')
    people.PeopleClient.handle_tmdb_person_info(dict(person_id='7', mode='movies'))
    assert page.calls == [] and rows[0]['is_folder']
    assert 'handle_tmdb_person_details' in rows[0]['url'] and 'handle_tmdb_person_details' in commands[0]


def test_no_second_recommendation_page_or_dead_ai_focus_target(window):
    assert not hasattr(window.value, 'fetch_ai_similar')
    skin = Path(extras.__file__).resolve().parents[2] / 'resources/skins/Default/1080i/extras.xml'
    tree = ET.parse(skin)
    assert not tree.findall('.//*[@id="2053"]')
    assert not any(node.text == '2053' for node in tree.iter())

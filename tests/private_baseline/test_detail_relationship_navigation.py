"""Existing People/Collections routes: one bounded fetch, canonical lazy cards."""
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit
from unittest.mock import Mock

import pytest

from lib.clients.tmdb import people_client as people, collections, anime_fast_catalog as catalog
from lib.clients.tmdb import frontend_metadata as front, season_cards


class Item:
    def __init__(self, label=''):
        self.label, self.properties, self.art, self.tag = label, {}, {}, Mock()
    def setProperty(self, key, value): self.properties[key] = value
    def setArt(self, value): self.art.update(value)
    def getVideoInfoTag(self): return self.tag
    def setLabel(self, value): self.label = value
    def setLabel2(self, value): self.label2 = value
    def setContentLookup(self, value): pass


def params(url): return dict(parse_qsl(urlsplit(url).query))


@pytest.fixture
def page(monkeypatch):
    import xbmc
    from lib.db.cached import cache
    state = SimpleNamespace(rows=[], calls=[], local_calls=[], ended=[], data=None, aborted=False, during_fetch=lambda: None)
    from bobbi_platform import runtime
    def local(action, body):
        assert action == 'catalog_public_holdings' and set(body) == {'identities'}
        assert len(body['identities']) <= 20
        state.local_calls.append(body)
        return dict(state='unknown', items=[])
    monkeypatch.setattr(runtime, 'call', local)
    def fetch(path, value):
        state.calls.append((path, value))
        state.during_fetch()
        if isinstance(state.data, Exception): raise state.data
        return state.data
    monkeypatch.setattr(people, 'tmdb_get', fetch)
    monkeypatch.setattr(people, 'make_list_item', Item)
    monkeypatch.setattr(catalog.xbmcgui, 'ListItem', Item)
    monkeypatch.setattr(front, 'apply', lambda *a, **kw: None)
    monkeypatch.setattr(season_cards, 'apply', lambda *a, **kw: None)
    monkeypatch.setattr(cache, 'get', lambda *a, **kw: None)
    monkeypatch.setattr(people, 'tmdb_image_url', lambda path, size: '' if not path else 'https://image.tmdb.org/t/p/'+size+path)
    monkeypatch.setattr(people, 'add_directory_items_batch', state.rows.extend)
    monkeypatch.setattr(people, 'end_of_directory', lambda **kw: state.ended.append(kw))
    monkeypatch.setattr(collections, 'end_of_directory', lambda **kw: state.ended.append(kw))
    monkeypatch.setattr(people, 'apply_section_view', lambda *a, **kw: None)
    monkeypatch.setattr(people, 'set_pluging_category', lambda *a: None)
    monkeypatch.setattr(people, 'set_content_type', lambda *a: None)
    monkeypatch.setattr(xbmc, 'Monitor', lambda: SimpleNamespace(abortRequested=lambda: state.aborted))
    return state


def test_work_relationships_use_explicit_collection_cast_and_director_ids(page):
    page.data = dict(id=42, belongs_to_collection=dict(id=9, name='系列'), credits=dict(
        cast=[dict(id=1, name='同名'), dict(id=2, name='同名')],
        crew=[dict(id=3, name='导演', job='Director'), dict(id=4, name='制片', job='Producer')]))
    people.PeopleClient.relationships(dict(id='42', kind='movie'))
    assert len(page.calls) == 1 and page.calls[0][0] == 'movie_details'
    assert len(page.rows) == 4
    assert params(page.rows[0][0]) == dict(action='handle_collection_details', collection_id='9')
    assert [params(url).get('person_id') for url, _, _ in page.rows[1:]] == ['3', '1', '2']
    assert [params(url)['role'] for url, _, _ in page.rows[1:]] == ['director', 'cast', 'cast']
    assert len({item.properties['Bobi.CardKey'] for _, item, _ in page.rows}) == 4
    assert all(folder for _, _, folder in page.rows)


@pytest.mark.parametrize('mode,expected', [('multi', 20), ('movies', 20), ('tv', 1)])
def test_people_credits_are_paginated_without_per_card_details_or_source_queries(page, mode, expected):
    page.data = dict(id=7, cast=[dict(id=n+1, title='电影', media_type='movie', release_date='2020-01-01')
        for n in range(25)] + [dict(id=1, name='电视剧', media_type='tv', first_air_date='2021-01-01')])
    people.PeopleClient.handle_tmdb_person_details(dict(person_id=7, mode=mode))
    assert page.calls == [('person_credits', 7)]
    work = [(url, item, folder) for url, item, folder in page.rows if item.properties.get('Bobi.NextPage') != 'true']
    assert len(work) == expected
    assert all(params(url)['action'] == 'am6b_open_streaming_item' for url, _, _ in work)
    assert all(item.properties['IsPlayable'] == 'false' for _, item, _ in work)
    assert len(page.local_calls) == 1 and len(page.local_calls[0]['identities']) == expected
    if mode != 'tv':
        assert params(page.rows[-1][0])['page'] == '2'


def test_director_works_do_not_include_producer_or_acting_credits(page):
    page.data = dict(id=8, cast=[dict(id=1, title='主演', media_type='movie')], crew=[
        dict(id=2, title='执导', media_type='movie', job='Director'),
        dict(id=3, title='制片', media_type='movie', job='Producer')])
    people.PeopleClient.handle_tmdb_person_details(dict(person_id=8, mode='multi', role='director'))
    assert len(page.rows) == 1 and params(page.rows[0][0])['id'] == '2'


def test_collection_keeps_distinct_explicit_members_and_never_fetches_movie_details(page):
    page.data = dict(id=9, parts=[dict(id=1, title='同名'), dict(id=2, title='同名')])
    collections.TmdbCollections.add_collection_details(dict(collection_id=9))
    assert page.calls == [('collection_details', 9)]
    assert [params(row[0])['id'] for row in page.rows] == ['2', '1']
    assert all(item.properties['IsPlayable'] == 'false' for _, item, _ in page.rows)


@pytest.mark.parametrize('collection', [False, True])
def test_second_page_keeps_identity_and_renders_only_remaining_summary_cards(page, collection):
    credits = [dict(id=n+1, title='电影', media_type='movie', job='Director') for n in range(25)]
    if collection:
        page.data = dict(id=9, parts=credits)
        collections.TmdbCollections.add_collection_details(dict(collection_id=9, page=2))
        assert page.calls == [('collection_details', 9)]
    else:
        page.data = dict(id=8, crew=credits)
        people.PeopleClient.handle_tmdb_person_details(dict(person_id=8, mode='multi', role='director', page=2))
        assert page.calls == [('person_credits', 8)]
    assert [params(url)['id'] for url, _, _ in page.rows] == ['5', '4', '3', '2', '1']
    assert all(params(url)['action'] == 'am6b_open_streaming_item' for url, _, _ in page.rows)
    # Movie cards keep the existing action route; only TV cards are folders.
    assert all(not folder and item.properties['IsPlayable'] == 'false' for _, item, folder in page.rows)


@pytest.mark.parametrize('data', [None, OSError('offline'), {'id': 999, 'parts': []}])
def test_failure_or_mismatched_id_is_an_isolated_retry_directory(page, data):
    page.data = data
    collections.TmdbCollections.add_collection_details(dict(collection_id=9))
    assert len(page.rows) == 1
    assert page.rows[0][1].properties['Bobi.Rail.State'] == 'error'
    assert params(page.rows[0][0])['collection_id'] == '9'
    assert len(page.ended) == 1


def test_cancelled_request_cannot_publish_a_late_relationship_or_focus(page):
    page.data = dict(id=9, parts=[dict(id=1, title='Old')])
    page.during_fetch = lambda: setattr(page, 'aborted', True)
    collections.TmdbCollections.add_collection_details(dict(collection_id=9))
    assert not page.rows and page.ended == [dict(cache=False)]


def test_missing_picture_and_empty_results_remain_navigable(page):
    page.data = dict(id=42, credits=dict(cast=[dict(id=3, name='无图人物')]))
    people.PeopleClient.relationships(dict(id=42, kind='tv'))
    assert page.rows[0][1].art == {} and params(page.rows[0][0])['person_id'] == '3'
    page.rows.clear()
    page.data = dict(id=42, credits={})
    people.PeopleClient.relationships(dict(id=42, kind='tv'))
    assert page.rows[0][1].properties['Bobi.Rail.State'] == 'empty'


@pytest.mark.parametrize('value', ['-1', 'name', None, True, '0'])
def test_invalid_relationship_identity_starts_no_metadata_work(page, value):
    people.PeopleClient.relationships(dict(id=value, kind='movie'))
    assert not page.calls and not page.rows and page.ended

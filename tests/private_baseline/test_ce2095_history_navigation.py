"""Local display history never becomes a playback request or a catalog identity."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lib.utils.views import continue_watching as continuing
from lib.utils.views import shows


class Item:
    def __init__(self, label=''):
        self.label, self.properties, self.menu, self.art = label, {}, [], {}
        self.tag = Mock()
        self.tag.getPlayCount.return_value = 0
    def getVideoInfoTag(self): return self.tag
    def getProperty(self, key): return self.properties.get(key, '')
    def setProperty(self, key, value): self.properties[key] = value
    def setLabel(self, value): self.label = value
    def setLabel2(self, value): self.label2 = value
    def setArt(self, value): self.art.update(value)
    def addContextMenuItems(self, value): self.menu.extend(value)


def watched(episode=1, season=1, identifier=42, minute=1, **extra):
    return dict(title='作品', mode='tv', ids={'tmdb_id': identifier},
                tv_data={'season': season, 'episode': episode, 'name': 'Title'},
                timestamp='Mon, 09 Nov 2026 01:{:02d} PM'.format(minute),
                progress=35, completed=False, **extra)


@pytest.fixture
def page(monkeypatch):
    from lib.api import simkl
    from lib.db import pickle_db
    from lib.clients.tmdb import frontend_metadata as metadata
    from bobbi_platform import runtime
    state = SimpleNamespace(history={}, reads=0, calls=0, rows=[], failed=False, link_calls=[], links=[],
                            account=dict(account_id='115:' + 'a' * 64, epoch=2, authenticated=True))
    class Database:
        def get_key_checked(self, key):
            assert key == 'jt:lfh'
            state.reads += 1
            if state.failed:
                raise OSError('history unavailable')
            return deepcopy(state.history)
    def account_status(action, body, **kwargs):
        if action == 'catalog_history_links':
            state.link_calls.append(deepcopy(body))
            assert set(body) == {'history_ids'} and len(body['history_ids']) <= 20
            return dict(items=deepcopy(state.links))
        assert action == 'account_status' and body == {} and kwargs['timeout'] == .1
        state.calls += 1
        if isinstance(state.account, Exception):
            raise state.account
        return deepcopy(state.account)
    monkeypatch.setattr(pickle_db, 'PickleDatabase', Database)
    monkeypatch.setattr(continuing, 'PickleDatabase', Database)
    monkeypatch.setattr(runtime, 'call', account_status)
    monkeypatch.setattr(simkl, 'is_simkl_authenticated', lambda: False)
    monkeypatch.setattr(metadata, 'apply', lambda *a, **k: None)
    monkeypatch.setattr(metadata, 'episode_projection', lambda *a: None)
    monkeypatch.setattr(shows, 'get_fanart_details', lambda **k: {})
    monkeypatch.setattr(shows, 'set_media_infoTag', lambda *a, **k: None)
    monkeypatch.setattr(shows, 'add_tmdb_episode_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(shows, 'is_trakt_auth', lambda: False)
    monkeypatch.setattr(shows, 'add_simkl_history_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(shows, 'add_nuvio_history_context_menu', lambda *a, **k: [])
    monkeypatch.setattr(shows, 'execute_thread_pool_collection',
                        lambda rows, function, *args: [function(row, *args) for row in rows])
    for module in (shows, continuing):
        monkeypatch.setattr(module, 'make_list_item', Item)
        monkeypatch.setattr(module, 'build_url', lambda action, **kw: action + '?' + json.dumps(kw, sort_keys=True))
        monkeypatch.setattr(module, 'add_directory_items_batch', state.rows.extend)
        monkeypatch.setattr(module, 'end_of_directory', lambda **kw: None)
        monkeypatch.setattr(module, 'apply_section_view', lambda *a, **kw: None)
    monkeypatch.setattr(continuing, 'set_pluging_category', lambda *a: None)
    monkeypatch.setattr(continuing, 'setContent', lambda *a: None)
    monkeypatch.setattr(continuing, 'translation', str)
    return state


def test_continue_card_adds_public_work_route_without_changing_default_actions(page):
    data = watched()
    data.update(_account=page.account, _owner={'private': 'owner'}, request_id='old-request',
                direct_cloud_key='old-cloud', file_id='private-file', path='private-path')
    page.history['saved'] = data
    before = deepcopy(data)
    continuing.show_continue_watching({})
    url, item, folder = page.rows[0]
    assert not folder and item.properties['IsPlayable'] == 'false'
    action, params = url.split('?', 1)
    assert action == 'play_media'
    assert json.loads(params) == dict(data=json.dumps(before), continue_watching='true')
    label, command = item.menu[2]
    assert label == '查看全剧分集'
    assert command.startswith('ActivateWindow(Videos,show_tmdb_item?') and command.endswith(',return)')
    browse = json.loads(command.split('?', 1)[1][:-len(',return)')])
    assert browse == dict(id=42, mode='tv', media_type='tv', title='作品')
    assert [entry[0] for entry in item.menu[:2]] == ['从头播放', '选择其他片源']
    assert page.history['saved'] == before and page.calls == 0
    assert not item.tag.setResumePoint.called


def test_file_and_title_history_share_snapshot_preview_and_only_opaque_file_routes(page, monkeypatch):
    from bobbi_core.file_ref import from_selected
    from lib.db.file_history import KEY
    from datetime import datetime
    account = dict(provider='quark', account_id='quark:' + 'd' * 64, epoch=1, authenticated=True)
    ref = from_selected(account, dict(file_id='private-file', name='私人视频.mkv', size=100, directory=False), 'private-parent')
    record = dict(version=1, id=ref['id'], file_ref=ref, position=97., duration=100.,
        completion_reason='ERROR', updated_at=datetime(2026, 11, 10).timestamp(),
        generation=1, sequence=2, session_id='e' * 32)
    page.history['title'] = watched()
    class Database:
        def get_keys_checked(self, keys):
            page.reads += 1
            assert keys == ('jt:lfh', KEY)
            return {'jt:lfh': deepcopy(page.history), KEY: {ref['id']: deepcopy(record)}}
    monkeypatch.setattr(continuing, 'PickleDatabase', Database)
    continuing.show_continue_watching({})
    assert len(page.rows) == 2 and page.reads == 1 and page.calls == 0
    assert page.link_calls == [dict(history_ids=[ref['id']])]
    url, item, folder = page.rows[0]
    assert json.loads(url.split('?', 1)[1]) == {'history_id': ref['id']}
    assert url.startswith('pan_history_play?') and not folder
    assert item.properties['PercentPlayed'] == '97' and item.properties['Bobi.File.State'] == 'verification_required'
    assert 'private-file' not in url + str(item.menu) and 'private-parent' not in url + str(item.menu)
    assert not item.tag.setResumePoint.called
    page.rows.clear()
    continuing.show_continue_watching({'resume_preview': 'true'})
    assert len(page.rows) == 1 and page.rows[0][0] == url and page.reads == 2


def test_history_version_link_uses_current_scope_and_keeps_original_resume(page):
    from bobbi_core.file_ref import from_selected
    from urllib.parse import parse_qsl, urlsplit
    expected = dict(provider='quark', account_id='quark:' + 'd'*64, epoch=7, authenticated=True)
    ref = from_selected(expected, dict(file_id='original', name='原始文件.mkv', size=100, directory=False), 'private')
    record = dict(version=1, id=ref['id'], file_ref=ref, position=18., duration=100.,
        completion_reason='STOP', updated_at=1, generation=1, sequence=1, session_id='a'*32)
    link = dict(entity_id=ref['id'], parent_entity_id='f'*64, expected=expected,
                work_title='已确认作品', version_label='导演剪辑', file_size=100)
    target, item, folder = continuing._file_item(record, link)
    assert json.loads(target.split('?', 1)[1]) == {'history_id': ref['id']}
    navigation = dict(parse_qsl(urlsplit(item.properties['Bobi.Catalog.Variants']).query))
    assert navigation['view'] == 'files' and navigation['parent_entity_id'] == 'f'*64
    assert navigation['provider'] == 'quark' and 'file_ref' not in navigation
    assert '人工备注' in item.label2 and '上次播放此文件' in item.label2
    assert any(label == '查看此作品的文件版本' for label, _ in item.menu)


@pytest.mark.parametrize('change', [dict(ids={}), dict(ids={'tmdb_id': 0}),
    dict(ids={'tmdb_id': True}), dict(tv_data={}), dict(tv_data={'season': 1, 'episode': 0}),
    dict(mode='movies'), dict(mode='unknown'), dict(ids=[]), dict(tv_data=[])])
def test_full_series_action_requires_explicit_valid_television_identity(page, change):
    data = watched()
    data.update(change)
    assert continuing._series_browse_context(data) == []


def test_anime_history_returns_to_canonical_work_not_displayed_production_season(page):
    data = watched(episode=25)
    data.update(mode='anime', display_order=dict(season=2, episode=1))
    command = continuing._series_browse_context(data)[0][1]
    assert 'show_tmdb_item?' in command and 'season' not in command and 'episode' not in command
    assert '"id": 42' in command


def test_one_snapshot_deduplicates_before_filtering_and_never_infers_completion(page):
    page.history = {
        'old': watched(minute=1),
        'new': dict(watched(minute=2), completed=True, progress=100),
        'error': dict(watched(episode=2), progress=97, terminal_reason='ERROR'),
        'legacy': dict(watched(episode=3), progress=100),
        'reset-old': watched(episode=4),
        'reset-new': dict(watched(episode=4, minute=2), progress=0),
        'other': watched(identifier=99),
        'missing': dict(watched(), ids={}),
    }
    page.history['legacy'].pop('completed')
    original = deepcopy(page.history)
    assert shows._local_episode_progress({'tmdb_id': 42}) == {
        (1, 1): (True, 0), (1, 2): (False, 97), (1, 3): (False, 99)}
    assert page.reads == 1 and page.calls == 0 and page.history == original


def test_equal_timestamps_latest_inserted_source_wins_and_specials_are_distinct(page):
    page.history = {'first': watched(), 'last': dict(watched(), progress=50),
                    'special': watched(season=0)}
    assert shows._local_episode_progress({'tmdb_id': 42}) == {
        (1, 1): (False, 50), (0, 1): (False, 35)}


@pytest.mark.parametrize('latest', [0, -1, None, 'invalid', float('nan'), float('inf'), 101])
def test_latest_zero_or_invalid_progress_never_resurrects_older_progress(page, latest):
    page.history = {'old': watched(), 'new': dict(watched(minute=2), progress=latest)}
    assert shows._local_episode_progress({'tmdb_id': 42}) == {}


def test_account_snapshot_is_once_and_history_uses_stable_user_not_stale_authority(page):
    current = page.account
    old = dict(current, epoch=1)
    another = dict(current, account_id='115:' + 'b' * 64)
    page.history = {'same': watched(_account=old), 'other': watched(episode=2, _account=another),
        'bad': watched(episode=3, _account=None),
        'unscoped-cloud': watched(episode=4, direct_cloud_key='private'),
        'public': watched(episode=5), 'unscoped115': watched(episode=6, indexer='115')}
    assert shows._local_episode_progress({'tmdb_id': 42}) == {(1, 1): (False, 35), (1, 5): (False, 35)}
    assert page.calls == page.reads == 1


@pytest.mark.parametrize('account', [OSError('offline'), {}, None,
    dict(account_id='', epoch=3, authenticated=False),
    dict(account_id='115:' + 'b' * 64, epoch=3, authenticated=True)])
def test_unavailable_logout_or_other_account_cannot_show_private_progress(page, account):
    page.history = {'private': watched(_account=page.account), 'public': watched(episode=2)}
    page.account = account
    assert shows._local_episode_progress({'tmdb_id': 42}) == {(1, 2): (False, 35)}


def test_new_profile_snapshot_and_account_switch_never_reuse_previous_projection(page):
    page.history = {'old': watched(_account=page.account)}
    assert shows._local_episode_progress({'tmdb_id': 42}) == {(1, 1): (False, 35)}
    page.account = dict(page.account, account_id='115:' + 'c' * 64, epoch=3)
    assert shows._local_episode_progress({'tmdb_id': 42}) == {}
    page.history = {'new-profile': watched(episode=7)}
    assert shows._local_episode_progress({'tmdb_id': 42}) == {(1, 7): (False, 35)}
    assert page.reads == 3 and page.calls == 2


def test_optional_corrupt_history_and_malformed_entries_do_not_drop_directory(page):
    page.failed = True
    assert shows._local_episode_progress({'tmdb_id': 42}) == {}
    page.failed = False
    page.history = {'none': None, 'ids': dict(watched(), ids=[]), 'tv': dict(watched(), tv_data=[]),
                    'nan': dict(watched(), progress=float('nan')), 'good': watched(episode=2)}
    assert shows._local_episode_progress({'tmdb_id': 42}) == {(1, 2): (False, 35)}


def test_remote_indicators_are_preserved_without_extra_remote_requests(page, monkeypatch):
    from lib.api import simkl
    monkeypatch.setattr(simkl, 'is_simkl_authenticated', lambda: True)
    page.history['local'] = watched()
    assert shows._local_episode_progress({'tmdb_id': 42}) == {} and page.reads == 0
    watched_item = Item()
    watched_item.tag.getPlayCount.return_value = 1
    shows._apply_local_episode_progress(watched_item, (False, 35))
    assert watched_item.properties == {} and not watched_item.tag.setPlaycount.called
    progress_item = Item()
    progress_item.properties['PercentPlayed'] = '60'
    shows._apply_local_episode_progress(progress_item, (True, 0))
    assert progress_item.properties == {'PercentPlayed': '60'}
    assert not progress_item.tag.setPlaycount.called


def test_real_normal_directory_batches_history_once_and_keeps_all_search_payloads(page):
    page.history = {'one': watched(), 'two': dict(watched(episode=2), completed=True)}
    episodes = [dict(episode_number=n, season_number=1, name='第{}集'.format(n),
                     air_date='2020-01-01') for n in range(1, 101)]
    assert shows.show_episode_info('作品', 1, {'tmdb_id': 42}, 'tv', 'tv',
        prepared_pages={'zh-CN': {'episodes': episodes}}) == 100
    assert page.reads == 1 and page.calls == 0
    for number, (url, item, folder) in enumerate(page.rows, 1):
        action, params = url.split('?', 1)
        query = json.loads(params)
        assert action == 'search' and not folder
        assert query['ids'] == {'tmdb_id': 42}
        assert query['tv_data']['season'] == 1 and query['tv_data']['episode'] == number
        assert not item.tag.setResumePoint.called
    assert page.rows[0][1].properties['PercentPlayed'] == '35'
    page.rows[1][1].tag.setPlaycount.assert_called_once_with(1)
    assert 'PercentPlayed' not in page.rows[2][1].properties


def test_collapsed_anime_directory_matches_catalog_coordinates_and_reads_once(page, monkeypatch):
    from lib.clients.tmdb import episode_order
    from lib.utils.kodi import utils
    from lib.utils.general import utils as general
    page.history = {'catalog': watched(episode=25), 'display-collision': dict(watched(season=2), progress=70)}
    order = dict(digest='verified-order', seasons=[dict(season=2, episodes=[
        dict(episode_id=n, catalog_season=1, catalog_episode=n, season=2, episode=n-24,
             name='第{}话'.format(n), air_date='2020-01-01') for n in (25, 26)])])
    monkeypatch.setattr(episode_order, 'get_order', lambda *a: order)
    monkeypatch.setattr(utils, 'add_directory_items_batch', page.rows.extend)
    monkeypatch.setattr(utils, 'end_of_directory', lambda **k: None)
    monkeypatch.setattr(utils, 'apply_section_view', lambda *a, **k: None)
    monkeypatch.setattr(general, 'set_content_type', lambda *a: None)
    episode_order.show_order_episodes(dict(ids=json.dumps({'tmdb_id': 42}), season='2',
        digest='verified-order', tv_name='作品'))
    assert len(page.rows) == 2 and page.reads == 1
    first = page.rows[0]
    assert first[1].properties['PercentPlayed'] == '35'
    assert first[1].properties['Bobi.CatalogEpisode'] == '1x25'
    first[1].tag.setSeason.assert_called_with(2)
    first[1].tag.setEpisode.assert_called_with(1)
    query = json.loads(first[0].split('?', 1)[1])
    assert query['tv_data']['season'] == 1 and query['tv_data']['episode'] == 25
    assert 'PercentPlayed' not in page.rows[1][1].properties
    assert all(not item.tag.setResumePoint.called for _, item, _ in page.rows)

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.next_episode_summary import project, checked, label
from test_standard_session import actor, begin
from test_standard_product import product, selected, handoff


def episode(number=1, **kw):
    return dict(mode='tv', ids={'tmdb_id': 123}, tv_data={'season': 0, 'episode': number},
                selection_policy='exact', **kw)


def test_provisional_bt_and_unresolved_cloud_never_promise_ready():
    for fields in ({'_next_transport': 'bt'}, {'_next_recheck': True}, {'_catalog_next': True}):
        value = project(episode(), episode(2, prepared_version_key='a'*64, **fields))
        assert value['state'] == 'preparing' and '播放前仍需检查' in label(value)
        assert value['next_media_ref'] == 'tmdb:tv:123:s0:e2'


def test_current_manual_file_mapping_does_not_grant_continuation():
    current = episode(file_evidence='USER_CONFIRMED_FILE')
    assert project(current, episode(2, _next_cloud_verified=True, prepared_version_key='a'*64))['state'] == 'unavailable'


def test_absence_error_and_selection_are_not_complete():
    assert project(episode())['state'] == 'unavailable'
    assert project(episode(), failed=True)['state'] == 'error'
    assert project(episode(), selection=episode(2))['state'] == 'needs_selection'
    assert project(episode(), preparing=True)['state'] == 'preparing'


def test_projection_drops_all_source_and_secret_fields():
    current = episode(url='https://secret.example/file', title='private filename', token='SECRET')
    value = project(current, episode(2, prepared_version_key='a'*64, _next_cloud_verified=True))
    assert value['state'] == 'ready'
    assert all(secret not in str(value) for secret in ('secret.example', 'private filename', 'SECRET'))
    with pytest.raises(ValueError):
        checked(dict(value, url='https://injected.example'))


@pytest.mark.parametrize('invalidate', ['stop', 'account', 'replacement', 'close'])
def test_real_standard_session_clears_summary_without_consuming_next(actor, invalidate):
    data = begin(actor)
    data.update(episode())
    actor.owner.current['data'] = deepcopy(data)
    actor.owner.observe(data['request_id'], data['url'], 10, 100)
    actor.owner.current['next_data'] = episode(2, _next_transport='bt', prepared_version_key='a'*64)
    value = actor.owner.next_summary()
    assert value['state'] == 'preparing' and value['adapter'] == 'standard'
    assert value['allowed_actions'] == [] and not actor.opened
    if invalidate == 'stop': actor.owner.terminal(data['request_id'], 'STOPPED')
    if invalidate == 'account': actor.account['epoch'] += 1
    if invalidate == 'replacement': begin(actor, 'b'*32)
    if invalidate == 'close': actor.owner.close()
    assert actor.owner.next_summary() is None and not actor.opened


def test_real_standard_display_changes_once_and_clears_on_callback(product):
    product.actor.session.next_loader = None
    data = selected(product)
    data['ids'] = {'tmdb_id': 123}
    handoff(product, data)
    product.actor.session.current['next_data'] = episode(2, prepared_version_key='a'*64, _next_transport='bt')
    product.actor.tick()
    assert '播放前仍需检查' in product.state.props['Bobi.Next.Label']
    revision = product.state.props['Bobi.Next.Revision']
    product.state.position += 1
    product.actor.tick()
    assert product.state.props['Bobi.Next.Revision'] == revision
    assert len(product.state.opened) == 1 and product.state.subtitles == []
    product.state.playing = False
    product.actor.player.onPlayBackStopped()
    product.actor.tick()
    assert not any(key.startswith('Bobi.Next.') for key in product.state.props)
    assert len(product.state.opened) == 1


def test_optional_display_failure_does_not_break_player_and_retries(product, monkeypatch):
    product.actor.session.next_loader = None
    data = selected(product)
    data['ids'] = {'tmdb_id': 123}
    handoff(product, data)
    product.actor.session.current['next_data'] = episode(2, prepared_version_key='a'*64, _next_transport='bt')
    window = sys.modules['xbmcgui'].Window
    def fail(_):
        raise RuntimeError('Window temporarily unavailable')
    monkeypatch.setattr(sys.modules['xbmcgui'], 'Window', fail)
    product.actor.tick()
    assert len(product.state.opened) == 1 and product.actor.session.current['state'] == 'playing'
    monkeypatch.setattr(sys.modules['xbmcgui'], 'Window', window)
    product.actor.tick()
    assert product.state.props['Bobi.Next.State'] == 'preparing'
    assert len(product.state.opened) == 1


def test_partial_clear_keeps_owner_marker_until_all_old_properties_are_removed(product, monkeypatch):
    display = product.actor.next_display
    display.publish(project(episode(), preparing=True))
    window = sys.modules['xbmcgui'].Window(10000)
    original = window.clearProperty
    failed = []
    def clear(key):
        if key == 'Bobi.Next.Label' and not failed:
            failed.append(key)
            raise RuntimeError('Temporary property failure')
        original(key)
    monkeypatch.setattr(window, 'clearProperty', clear)
    display.publish(None)
    assert product.state.props['Bobi.Next.Adapter'] == 'standard'
    display.publish(None)
    assert not any(key.startswith('Bobi.Next.') for key in product.state.props)


def test_partial_write_is_repaired_even_when_true_state_returns_to_previous_value(product, monkeypatch):
    display = product.actor.next_display
    old = project(episode(), preparing=True)
    display.publish(old)
    window = sys.modules['xbmcgui'].Window(10000)
    original = window.setProperty
    failed = []
    def write(key, value):
        if key == 'Bobi.Next.Label' and not failed:
            failed.append(key)
            raise RuntimeError('Temporary property failure')
        original(key, value)
    monkeypatch.setattr(window, 'setProperty', write)
    display.publish(project(episode(), failed=True))
    assert product.state.props['Bobi.Next.State'] == 'error'
    display.publish(old)
    assert product.state.props['Bobi.Next.State'] == 'preparing'
    assert product.state.props['Bobi.Next.Label'] == label(old)

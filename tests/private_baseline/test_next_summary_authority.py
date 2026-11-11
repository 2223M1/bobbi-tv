"""The actual native actor admits presentation, not continuation or controls."""
from copy import deepcopy
import pytest
from test_playback_authority import playing, select
from bobbi_core.next_episode_summary import project


def message(authority, native, args):
    current = dict(mode='tv', ids={'tmdb_id': 1}, tv_data={'season': 1, 'episode': 1}, selection_policy='exact')
    return dict(args, operation='next_summary', native_instance=native.current['native_instance'],
                summary=project(current, preparing=True))


def test_native_summary_does_not_issue_player_or_gui_commands():
    authority, native, args = playing()
    before = authority.owner.snapshot()
    native.commands.clear()
    native.gui_commands.clear()
    assert authority.dispatch(message(authority, native, args)) == {'accepted': True}
    result = authority.next_summary_snapshot()
    assert result['state'] == 'preparing' and result['allowed_actions'] == []
    assert result['owner_identity']['native_instance'] == native.current['native_instance']
    assert authority.owner.snapshot() == before and not native.commands and not native.gui_commands


@pytest.mark.parametrize('change', ['stop', 'replacement', 'instance', 'manual', 'boot'])
def test_late_summary_cannot_revive_previous_playback(change):
    authority, native, args = playing()
    pending = message(authority, native, args)
    assert authority.dispatch(pending)['accepted']
    if change == 'stop':
        native.current.update(phase='TERMINAL', reason='STOP', sequence=2)
        authority.refresh()
    elif change == 'replacement':
        select(authority, 'release-b')
    elif change == 'instance':
        native.current['native_instance'] = '00000000-0000-4000-8000-000000000000'
        authority.refresh()
    elif change == 'manual':
        authority.owner.desired['file_evidence'] = 'USER_CONFIRMED_FILE'
    else:
        authority.owner.boot_id = 'new-boot'
    assert authority.dispatch(pending)['accepted'] is False
    if change != 'manual':
        assert authority.next_summary_snapshot() is None


def test_account_epoch_invalidates_summary_even_without_callback():
    authority, native, args = playing()
    scope = {'account_id': 'opaque', 'epoch': 1}
    from types import SimpleNamespace
    authority.configure_accounts(SimpleNamespace(is_current=lambda value: value == scope,
        run_if_current=lambda value, fn: fn() if value == scope else (_ for _ in ()).throw(ValueError('STALE'))))
    authority.selection_account = deepcopy(scope)
    assert authority.dispatch(message(authority, native, args))['accepted']
    scope['epoch'] += 1
    assert authority.next_summary_snapshot() is None
    with pytest.raises(ValueError):
        authority.dispatch(message(authority, native, args))


def test_native_projection_only_reports_actual_discovery_work(monkeypatch):
    from threading import Event
    from types import SimpleNamespace, MethodType
    from test_transport_recovery_native import methods
    from lib.utils.player.discovery_gate import DiscoveryGate
    from lib.cinema import playback_request
    sent = []
    monkeypatch.setattr(playback_request, 'call', lambda body: sent.append(body) or {'accepted': True})
    actor = SimpleNamespace(data=dict(mode='tv', ids={'tmdb_id': 1},
        tv_data={'season': 1, 'episode': 1}, selection_policy='exact', cinema_continuity=True),
        _cinema_cancel=Event(), _native_instance='native', _owner_context={},
        _cinema_next_data=None, _cinema_next_status=None, _cinema_discovery=DiscoveryGate())
    publish = MethodType(methods({'publish_next_summary'}, {})['publish_next_summary'], actor)
    publish()
    assert sent[-1]['summary']['state'] == 'unavailable'
    token = actor._cinema_discovery.begin(0)
    publish()
    assert sent[-1]['summary']['state'] == 'preparing'
    actor._cinema_discovery.finish(token, False, 0, lambda: None)
    publish()
    assert sent[-1]['summary']['state'] == 'unavailable'
    # Invalidated old work is not current preparation, even before it exits.
    actor._cinema_discovery.begin(10)
    actor._cinema_discovery.wake('new-generation')
    publish()
    assert sent[-1]['summary']['state'] == 'unavailable'
    actor._cinema_next_status = 'DIRECT_CLOUD_PREPARING'
    publish()
    assert sent[-1]['summary']['state'] == 'preparing'

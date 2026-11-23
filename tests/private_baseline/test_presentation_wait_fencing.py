"""Local retirement polling never replaces the authoritative control fences."""
from types import MethodType

import pytest

from test_playback_authority import select
from test_presentation_handoff_recovery import scene


@pytest.mark.parametrize('change', [
    'cancel', 'replacement', 'back', 'native_replacement', 'account_epoch', 'binding_lost', 'reused_window',
])
def test_changed_owner_or_intent_during_local_wait_never_grants_fullscreen(scene, change):
    class Accounts:
        current = dict(account_id='115:' + '1' * 64, epoch=1, authenticated=True)

        def is_current(self, expected):
            return expected == self.current

        def run_if_current(self, expected, operation):
            if not self.is_current(expected):
                raise RuntimeError('ACCOUNT_CHANGED')
            return operation()

    accounts = Accounts()
    scene.authority.configure_accounts(accounts)
    scene.authority.selection_account = dict(accounts.current)
    scene.resolver._owns_selection = MethodType(type(scene.resolver)._owns_selection, scene.resolver)
    scene.resolver.close_windows = lambda: None  # Native GUI close retires asynchronously.
    scene.player._media_started = True
    gui = scene.resolver.handle_playback_started.__func__.__globals__['xbmc']
    waits = []

    def wait(milliseconds):
        scene.clock[0] += milliseconds / 1000
        waits.append(milliseconds)
        if len(waits) != 1:
            return
        if change != 'reused_window':
            scene.visible.clear()
        if change == 'cancel':
            scene.resolver.cancel_event.set()
        elif change == 'replacement':
            select(scene.authority, ident='replacement-during-retirement')
        elif change == 'back':
            scene.native.gui['gui_user_intent'] += 1
        elif change == 'native_replacement':
            scene.native.epoch += 1
            scene.native.current.update(native_instance='other-video', request_id='', file_identity='external', sequence=1)
        elif change == 'account_epoch':
            accounts.current = dict(accounts.current, epoch=2)
        elif change == 'binding_lost':
            # The fixed client still has to cross its fresh binding guard at
            # close_window. A failed guard cannot fall back to a cached lease.
            scene.faults['close_window'] = dict(remaining=-1, lost_ack=False)
        elif change == 'reused_window':
            gui.getInfoLabel = lambda value: 'another-window-token'
            scene.native.loading_window = lambda dialog, expected: dict(
                visible=True, matching=False, modal=False, active_window=10000)

    gui.sleep = wait
    assert scene.player.handle_playback_start() is True
    assert waits
    assert not scene.native.gui_commands and not scene.native.commands
    assert not getattr(scene.player, '_handoff_confirmed', False)
    # No repeat ownership RPC is hidden inside the local 25 ms wait loop.
    before_release = []
    for call in scene.calls:
        if call['operation'] == 'close_window':
            break
        before_release.append(call['operation'])
    if change in ('back', 'native_replacement', 'account_epoch', 'binding_lost', 'replacement'):
        assert before_release == ['snapshot', 'begin_window_close']
    if change == 'reused_window':
        assert len(waits) == 20
        assert not any(call['operation'] == 'close_window' for call in scene.calls)


def test_expired_presentation_records_request_local_result_without_touching_new_global_labels(scene):
    player = scene.player
    player._media_started = player._start_notified = True
    player._presentation_deadline = scene.clock[0]
    player._presentation_attempts = 1
    player._presentation_next_at = 0
    player.on_presentation_deferred = lambda: None
    scene.properties.update(bobbi_cinema_handoff='new-request-handoff',
                            bobbi_cinema_presentation_status='new-request-status')
    before = list(scene.calls)
    assert player.handle_playback_start() is True
    assert player._presentation_result == dict(request_id=scene.args['request_id'],
        native_instance=scene.native.current['native_instance'], phase='DEFERRED',
        stage='MEDIA_OBSERVATION', reason='BUDGET_EXHAUSTED')
    assert scene.properties['bobbi_cinema_handoff'] == 'new-request-handoff'
    assert scene.properties['bobbi_cinema_presentation_status'] == 'new-request-status'
    assert scene.calls == before
    assert not scene.native.gui_commands and not scene.native.commands

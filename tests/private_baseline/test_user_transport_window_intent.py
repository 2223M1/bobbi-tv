"""Production lease revocation with a native user-intent claimant simulation."""
from copy import deepcopy

import pytest

from test_user_transport_presentation import transport
from test_playback_presentation import scene, submit


@pytest.mark.parametrize('action', ['user_pause', 'user_resume'])
def test_explicit_already_satisfied_user_action_revokes_auto_window_pause_lease(transport, action):
    owner, native, args = transport
    # Establish the fixture's complete native protocol fields as one real event.
    native.current['sequence'] += 1
    owner.refresh()
    state = native.state
    token = 'a' * 32
    native.state = lambda: dict(state(), windows=[dict(token=token, role='audio',
        request_id=args['request_id'], native_instance=native.current['native_instance'])])
    owner.refresh()
    assert native.commands[-1]['action'] == 'pause' and owner.owner.pause is not None
    if action == 'user_pause':
        native.current.update(paused=True, sequence=native.current['sequence'] + 1)
        owner.refresh()
    # Pause is already true, or resume is already false while the automatic
    # pause request is still unconfirmed. Both explicit intents must win.
    assert native.current['paused'] == (action == 'user_pause')
    original_intent = native.current['user_intent']
    original_sequence = native.current['sequence']
    native.commands.clear()
    control = native.control
    def claim(command):
        result = control(command)
        if command['action'] in ('user_pause', 'user_resume'):
            native.current['user_intent'] += 1
        return result
    native.control = claim
    result, command = submit(transport, action, {})
    assert result['status'] == 'queued'
    assert native.current['user_intent'] == original_intent + 1
    assert native.current['sequence'] == original_sequence
    assert owner.event('xbmc', 'Player.OnBobiControl', dict(native.commands[-1], status='applied'))
    owner.refresh()
    assert owner.owner.pause is None
    native.state = state
    before = deepcopy(native.commands)
    owner.refresh()
    assert native.commands == before
    assert [row['action'] for row in native.commands] == [action]
    assert owner.dispatch(dict(operation='playback_receipt', expected=command['expected'],
        command_id=command['command_id']))['status'] == 'applied'

"""New receipt evidence crosses only the existing exact owner authority."""
from copy import deepcopy
from uuid import uuid4

import pytest
from test_playback_authority import playing, select
from bobbi_core import playback_request
from bobbi_core.playback_completion import terminal_end


@pytest.mark.parametrize('change', ['none','stop','error','account_cancel','replace','foreign'])
def test_authority_retains_only_matching_immutable_completion(monkeypatch, change):
    authority, native, args = playing()
    instance = native.current['native_instance']
    end = deepcopy(native.current)
    observation = dict(schema=1,position_ms=99960,duration_ms=100000,age_us=20000,valid=True)
    end.update(phase='TERMINAL',reason='NATURAL_EOF',sequence=end['sequence']+1,
               completion_observation=observation)
    if change in ('stop','error'): end['reason'] = change.upper()
    if change == 'account_cancel': authority.owner.cancel(args['boot_id'],args['epoch'],args['request_id'])
    if change == 'replace': select(authority,'other')
    if change == 'foreign': end['file_identity'] = 'different-file'
    native.current = end
    accepted = authority.event('xbmc','Player.OnBobiState',end)
    assert accepted is (change != 'foreign')
    monkeypatch.setattr(playback_request,'call',lambda body:authority.owner.snapshot())
    result = playback_request.terminal_state(args,instance)
    if change == 'foreign':
        assert result is None
    elif change == 'replace':
        assert result == {'reason':'SUPERSEDED'}
    else:
        expected = {'account_cancel':'CANCEL','stop':'STOP','error':'ERROR'}.get(change,'NATURAL_EOF')
        assert result == dict(reason=expected,completion_observation=observation)
        end['completion_observation']['position_ms'] = 0
        assert authority.owner.terminal['completion_observation']['position_ms'] == 99960


def test_generic_notifications_and_arbitrary_payload_never_supply_completion():
    authority,native,args = playing()
    end = dict(native.current,phase='TERMINAL',reason='NATURAL_EOF',sequence=2,
        completion_observation=dict(schema=1,position_ms=100000,duration_ms=100000,age_us=0,valid=True))
    assert not authority.event('untrusted','Player.OnBobiState',end)
    assert not authority.event('xbmc','Player.OnPlay',end)
    assert authority.owner.terminal is None


def test_new_observation_preserves_one_use_continuation_after_native_destruction(monkeypatch):
    authority,native,args = playing()
    instance = native.current['native_instance']
    native.current.update(phase='TERMINAL',reason='NATURAL_EOF',sequence=2,
        completion_observation=dict(schema=1,position_ms=99960,duration_ms=100000,age_us=10000,valid=True))
    assert authority.event('xbmc','Player.OnBobiState',deepcopy(native.current))
    monkeypatch.setattr(playback_request,'call',lambda _:authority.owner.snapshot())
    terminal = playback_request.terminal_state(args,instance)
    assert terminal_end(terminal,68,100,1,2)  # monitor missed the final second at 32x
    native.current = None
    grant = authority.dispatch(dict(args,operation='authorize_next',native_instance=instance,
                                    selection_identity='same-release-next'))
    assert grant['authorized']
    command = dict(args,operation='reserve_child',token=grant['token'],child_request_id=uuid4().hex,
                   selection_identity='same-release-next')
    result = authority.dispatch(command)
    assert result['desired']['request_id']==command['child_request_id']
    with pytest.raises(RuntimeError):
        authority.dispatch(command)

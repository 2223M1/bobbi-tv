"""An observed terminal target and this workflow's Stop confirmation differ."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_ce2039_diagnostic_stop_receipt import kodi, owned_record


@pytest.mark.parametrize('before',[True,False])
@pytest.mark.parametrize('reason',['STOP','NATURAL_EOF','READ_ERROR','ERROR','',None])
def test_terminal_reason_is_preserved_but_only_post_command_stop_is_confirmed(before,reason):
    record=owned_record();calls=[]
    row=dict(request_id=record['request_id'],native_instance=record['native_instance'],file_identity=record['file_identity'],
             phase='TERMINAL' if before else 'AV_STARTED',reason=reason,sequence=2,user_intent=3)
    authority=dict(boot_id='boot',epoch=4,desired=dict(request_id=record['request_id'],cancelled=False))
    def rpc(method,params=None):
        calls.append(method)
        return {'queued':True} if method=='Player.BobiControl' else {'playback':dict(row,phase='TERMINAL')}
    runtime=SimpleNamespace(view=lambda:deepcopy((authority,dict(selection_epoch=8,playback=row),[{'playerid':1}])),
                            save=lambda value:None,rpc=rpc)
    runtime.stop=lambda record:kodi.Runtime.stop(runtime,record)
    result=kodi.capture_stop_result(runtime,record)
    assert result['reason']==reason and result['target_terminal'] is True
    assert result['stop_issued'] is (not before)
    assert result['confirmed'] is (not before and reason=='STOP')
    assert record['stop_state']==('confirmed' if result['confirmed'] else 'unconfirmed')
    assert calls.count('Player.BobiControl')==(0 if before else 1)


@pytest.mark.parametrize('change',['request_id','native_instance','file_identity','user_intent'])
def test_changed_post_command_scope_or_user_action_never_confirms_our_stop(change):
    record=owned_record();calls=[]
    row=dict(request_id=record['request_id'],native_instance=record['native_instance'],file_identity=record['file_identity'],
             phase='AV_STARTED',sequence=2,user_intent=3)
    after=dict(row,phase='TERMINAL',reason='STOP')
    after[change]=4 if change=='user_intent' else 'different'
    authority=dict(boot_id='boot',epoch=4,desired=dict(request_id=record['request_id'],cancelled=False))
    def rpc(method,params=None):
        calls.append(method)
        return {'queued':True} if method=='Player.BobiControl' else {'playback':after}
    runtime=SimpleNamespace(view=lambda:deepcopy((authority,dict(selection_epoch=8,playback=row),[{'playerid':1}])),
                            save=lambda value:None,rpc=rpc)
    runtime.stop=lambda record:kodi.Runtime.stop(runtime,record)
    result=kodi.capture_stop_result(runtime,record)
    assert result['confirmed'] is False and record['stop_state']=='unconfirmed'
    assert result['target_terminal'] is (True if change=='user_intent' else None)
    assert calls==['Player.BobiControl','Player.BobiState']

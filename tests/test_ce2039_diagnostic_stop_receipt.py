"""Receipt-only stop reconciliation; no native/player/device actions are real."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from test_ce_115_direct_start import kodi, shared, REQUEST, INSTANCE


def owned_record():
    return dict(run_id='a'*32, request_id=REQUEST, native_instance=INSTANCE, file_identity='exact',
        owner_context=dict(boot_id='boot',epoch=4,request_id=REQUEST))


def real_stop_runtime(monkeypatch,mode):
    row=dict(phase='AV_STARTED',native_instance=INSTANCE,request_id=REQUEST,
             file_identity='exact',user_intent=2,sequence=9)
    authority=dict(boot_id='boot',epoch=4,desired=dict(request_id=REQUEST,cancelled=False))
    native=dict(selection_epoch=12,playback=row)
    calls=[];saved=[];clock=[0.]
    monkeypatch.setattr(kodi.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(kodi.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    if mode=='already_terminal':row.update(phase='TERMINAL',reason='STOP')
    def rpc(method,params=None):
        calls.append((method,params))
        if method=='Player.BobiControl':
            if mode=='exception':raise TimeoutError('private lost ACK')
            return {'queued':False} if mode=='rejected' else {'queued':True}
        assert method=='Player.BobiState'
        if mode=='confirmed':return dict(playback=dict(row,phase='TERMINAL',reason='STOP'))
        if mode=='replacement':return dict(playback=dict(row,native_instance='other'))
        if mode=='observation_exception':raise OSError('private observation error')
        return native
    runtime=SimpleNamespace(view=lambda:(authority,native,[{'playerid':1}]),rpc=rpc,
        save=lambda value:saved.append(deepcopy(value)))
    runtime.stop=lambda record:kodi.Runtime.stop(runtime,record)
    return runtime,calls,saved


@pytest.mark.parametrize('mode',['confirmed','already_terminal','rejected','unknown','replacement',
                                 'exception','observation_exception'])
def test_real_stop_outcome_sets_both_fields_without_extra_stop(monkeypatch,mode):
    runtime,calls,saved=real_stop_runtime(monkeypatch,mode)
    record=owned_record()
    # A prior top-level value is never a control input, nor a retry invitation.
    record.update(stop_state='confirmed',stop={'confirmed':True,'reason':'old'})
    if mode in ('rejected','exception','observation_exception'):
        with pytest.raises((shared.DiagnosticError,TimeoutError,OSError)):
            kodi.capture_stop_result(runtime,record)
    else:kodi.capture_stop_result(runtime,record)
    confirmed=mode=='confirmed'
    assert record['stop_state']==('confirmed' if confirmed else 'unconfirmed')
    assert record['stop']['confirmed'] is confirmed
    stops=[call for call in calls if call[0]=='Player.BobiControl']
    assert len(stops)==(0 if mode=='already_terminal' else 1)
    if mode=='already_terminal':
        assert record['stop']['target_terminal'] is True and record['stop']['stop_issued'] is False
        assert record['stop']['reason']=='STOP'
    if mode!='already_terminal':
        assert saved[0]['stop_state']=='unconfirmed' and saved[0]['stop']['confirmed'] is False
    assert 'old' not in json.dumps(record) and 'private' not in json.dumps(record)


@pytest.mark.parametrize('outcome',[{'confirmed':True,'reason':'STOP'}, {'confirmed':False}, {},
                                   {'confirmed':1}, {'confirmed':'true'}, TimeoutError('private')])
def test_runner_final_receipt_matches_outcome_and_never_retries(monkeypatch,outcome):
    saved=[];stop_calls=[]
    class Runtime:
        def __init__(self,directory):pass
        def save(self,value):saved.append(deepcopy(value))
        def abort_requested(self):return False
        def settings(self):return {'unchanged':True}
        def user_state(self):return {'unchanged':True}
        def native_identity(self):return {'sha256':'1'*64}
        def stop(self,record):
            stop_calls.append(deepcopy(record))
            if isinstance(outcome,Exception):raise outcome
            return deepcopy(outcome)
        def cancel_pending(self,record):pytest.fail('No cleanup replay after an opened diagnostic')
    def start(runtime,expected,target,record):record.update(owned_record(),play_issued_at=1.)
    monkeypatch.setattr(kodi,'Runtime',Runtime)
    monkeypatch.setattr(kodi,'perform_start',start)
    monkeypatch.setattr(kodi.time,'monotonic',lambda:100.)
    kodi.kodi_entry(dict(run_id='a'*32,request_id=REQUEST,inspection={},target={},duration=10),'unused')
    final=saved[-1]
    confirmed=isinstance(outcome,dict) and outcome.get('confirmed') is True
    assert final['stop_state']==('confirmed' if confirmed else 'unconfirmed')
    assert final['stop']['confirmed'] is confirmed
    assert final['state']==('completed' if confirmed else 'unconfirmed' if isinstance(outcome,Exception)
                            else 'stop_unconfirmed')
    assert len(stop_calls)==1 and stop_calls[0]['stop']==dict(confirmed=False,target_terminal=None,stop_issued=None)
    assert 'SESSION_ACTIVATED' not in json.dumps(saved) and 'private' not in json.dumps(saved)


@pytest.mark.parametrize('outcome',[{'confirmed':True,'reason':'STOP'},{'confirmed':False},
                                  shared.DiagnosticError('OTHER_INSTANCE'),TimeoutError('private')])
def test_standalone_receipt_matches_outcome_without_mutating_original(tmp_path,monkeypatch,outcome):
    original=owned_record();original.update(stop_state='confirmed',stop={'confirmed':True,'reason':'old'})
    source=tmp_path/'result.json';source.write_text(json.dumps(original),encoding='utf-8')
    original_bytes=source.read_bytes();calls=[]
    def stop(runtime,record):
        calls.append(deepcopy(record))
        if isinstance(outcome,Exception):raise outcome
        return deepcopy(outcome)
    monkeypatch.setattr(kodi.Runtime,'stop',stop)
    parameters=dict(owned_record(),command_id='b'*32)
    result=kodi.standalone_stop(parameters,str(tmp_path))
    confirmed=isinstance(outcome,dict) and outcome.get('confirmed') is True
    assert result['stop_state']==('confirmed' if confirmed else 'unconfirmed')
    assert result['state']==('stopped' if confirmed else 'unconfirmed')
    assert result['stop']['confirmed'] is confirmed and len(calls)==1
    assert source.read_bytes()==original_bytes
    assert json.loads((tmp_path/('stop-'+'b'*32+'.json')).read_text())==result
    assert 'private' not in json.dumps(result) and 'old' not in json.dumps(result)

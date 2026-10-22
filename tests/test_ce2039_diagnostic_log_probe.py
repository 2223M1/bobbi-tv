"""Receipt-scoped log extraction only; fake local files/journal, no device IO."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'addons/script.module.bobbi.core/lib'))
import ce_playback_log_probe as probe

REQUEST='a'*32
INSTANCE='11111111-2222-3333-4444-555555555555'
TRANSPORT='b'*64


def receipt():
    return dict(schema=1,operation='start',run_id='c'*32,request_id=REQUEST,native_instance=INSTANCE,
        tool_revision=5,route='sharestream-open-range',state='completed',diagnostic_only=True,
        product_proof=False,retry_allowed=False,open_call_returned=True,url_sha256=TRANSPORT,
        transport_diagnostic={'mode':'open_range','seconds':60},
        file_identity='transport:'+'d'*64+'|diagnostic:'+'e'*64+'|transport:'+TRANSPORT,
        owner_context=dict(boot_id='f'*32,epoch=2,request_id=REQUEST),
        samples=[dict(phase='AV_STARTED',native=dict(request_id=REQUEST,native_instance=INSTANCE,phase='AV_STARTED'))],
        stop={'confirmed':True,'reason':'STOP'},stop_state='unconfirmed')


def scope_for(tmp_path,value=None,request=REQUEST):
    path=tmp_path/'receipt.json';path.write_text(json.dumps(receipt() if value is None else value),encoding='utf-8')
    return probe.diagnostic_scope(path,request)


def test_full_old_receipt_is_accepted_without_rewriting_historical_stop_field(tmp_path):
    value=receipt();scope=scope_for(tmp_path,value)
    assert scope['transport_sha256']==TRANSPORT and scope['request_id']==REQUEST
    assert scope['request_sha256']==hashlib.sha256(REQUEST.encode()).hexdigest()[:16]
    assert scope['diagnostic_only'] is True and scope['product_proof'] is False
    assert json.loads((tmp_path/'receipt.json').read_text())==value
    assert 'owner_context' not in scope and 'stop_state' not in scope


def test_v6_microbatch_scope_is_explicit_and_cannot_masquerade_as_old_revision(tmp_path):
    value=receipt();value.update(route='sharestream-open-range-microbatch',tool_revision=6)
    value['transport_diagnostic']={'mode':'open_range_microbatch','seconds':60}
    assert scope_for(tmp_path,value)['route']=='sharestream-open-range-microbatch'
    value['tool_revision']=5
    with pytest.raises(ValueError,match='DIAGNOSTIC_RECEIPT_INVALID'):scope_for(tmp_path,value)


def test_v7_bound_guard_scope_is_explicit_and_never_accepted_as_v6(tmp_path):
    value=receipt();value.update(route='sharestream-open-range-bound-guard',tool_revision=7)
    value['transport_diagnostic']={'mode':'open_range_bound_guard','seconds':60}
    assert scope_for(tmp_path,value)['route']=='sharestream-open-range-bound-guard'
    value['tool_revision']=6
    with pytest.raises(ValueError,match='DIAGNOSTIC_RECEIPT_INVALID'):scope_for(tmp_path,value)


@pytest.mark.parametrize('change',['request','native','product','diagnostic','launch_stub','hash',
    'file_binding','owner','sample_request','sample_native','no_native_samples','route','revision','opened','retry','mode'])
def test_incomplete_or_mismatched_receipt_cannot_bypass_normal_session_requirement(tmp_path,change):
    value=receipt();request=REQUEST
    if change=='request':request='0'*32
    elif change=='native':value.pop('native_instance')
    elif change=='product':value['product_proof']=True
    elif change=='diagnostic':value['diagnostic_only']=False
    elif change=='launch_stub':value=dict(operation='start',state='launched',request_id=REQUEST)
    elif change=='hash':value['url_sha256']='0'*64
    elif change=='file_binding':value['file_identity']='private-url'
    elif change=='owner':value['owner_context']['request_id']='0'*32
    elif change=='sample_request':value['samples'][0]['native']['request_id']='0'*32
    elif change=='sample_native':value['samples'][0]['native']['native_instance']='other'
    elif change=='no_native_samples':value['samples']=[{'phase':None}]
    elif change=='route':value['route']='ordinary'
    elif change=='revision':value['tool_revision']=True
    elif change=='opened':value['open_call_returned']=False
    elif change=='retry':value['retry_allowed']=True
    elif change=='mode':value['transport_diagnostic']['mode']='open_range_microbatch'
    with pytest.raises(ValueError,match='DIAGNOSTIC_RECEIPT_INVALID'):
        scope_for(tmp_path,value,request)


def execute_remote(tmp_path,monkeypatch,lines,journal='',scope=None):
    import pathlib
    storage=tmp_path/'storage';(storage/'temp').mkdir(parents=True)
    (storage/'temp/kodi.log').write_text('\n'.join(lines),encoding='utf-8')
    (storage/'temp/kodi_crashlog-private-account').touch()
    actual=pathlib.Path
    monkeypatch.setattr(pathlib,'Path',lambda value:storage if str(value)=='/storage/.kodi' else actual(value))
    calls=[];printed=[]
    def journal_read(command,**kwargs):
        calls.append(command)
        assert command[:3]==['journalctl','-u','kodi.service']
        return journal.encode()
    monkeypatch.setattr(subprocess,'check_output',journal_read)
    previous=list(sys.path)
    try:
        exec(compile(probe.REMOTE,'actual-log-extractor','exec'),
            dict(REQUEST=REQUEST,LOG_NAME='kodi.log',DIAGNOSTIC=scope,print=printed.append))
    finally:sys.path[:]=previous
    return json.loads(printed[-1]),calls


def observation(**kwargs):
    return dict(event='share_read',transport=TRANSPORT,request='8'*16,phase='begin',http=1,**kwargs)


def test_default_path_still_requires_real_session_marker(tmp_path,monkeypatch):
    with pytest.raises(AssertionError,match='REQUEST_NOT_IN_CURRENT_LOG'):
        execute_remote(tmp_path,monkeypatch,[REQUEST+' AV_STARTED'])


def test_default_with_real_marker_keeps_ordinary_behavior(tmp_path,monkeypatch):
    value,_=execute_remote(tmp_path,monkeypatch,['[bobbi] '+REQUEST+' SESSION_ACTIVATED',
        '[bobbi] '+json.dumps(observation()),'VideoPlayer opening https://private.invalid/file'])
    assert value['diagnostic_scope'] is None and value['share_observations'][0]['transport']==TRANSPORT
    assert any('SESSION_ACTIVATED' in row for row in value['lines'])
    assert 'https://' not in json.dumps(value)


def test_diagnostic_extracts_only_exact_scope_and_no_free_text_or_account(tmp_path,monkeypatch):
    scope=scope_for(tmp_path)
    matching=observation(url='https://secret.invalid/',account='private-account')
    unrelated=dict(matching,transport='0'*64)
    request_only=dict(event='share_read',request=scope['request_sha256'],phase='end')
    conflict=dict(request_only,transport='0'*64)
    lines=['VideoPlayer unrelated private-account https://secret.invalid/',
        REQUEST+' AV_STARTED account=private-account https://secret.invalid/',
        '0'+REQUEST+'0 WARNING private-account',
        '[bobbi] '+json.dumps(matching),'[bobbi] '+json.dumps(unrelated),
        '[bobbi] '+json.dumps(conflict)]
    value,calls=execute_remote(tmp_path,monkeypatch,lines,json.dumps(request_only),scope)
    assert len(calls)==1 and value['diagnostic_scope']==scope
    assert len(value['share_observations'])==2
    assert all(row.get('transport') in (None,TRANSPORT) for row in value['share_observations'])
    assert all(row['event']=='scoped_log_marker' for row in value['lines'])
    assert any(row['markers']==['AV_STARTED'] for row in value['lines'])
    encoded=json.dumps(value)
    assert 'private-account' not in encoded and 'https://' not in encoded and 'secret.invalid' not in encoded
    assert 'SESSION_ACTIVATED' not in encoded


def test_diagnostic_without_any_exact_log_evidence_fails_instead_of_claiming_session(tmp_path,monkeypatch):
    scope=scope_for(tmp_path)
    with pytest.raises(AssertionError,match='REQUEST_NOT_IN_DIAGNOSTIC_LOG'):
        execute_remote(tmp_path,monkeypatch,['VideoPlayer unrelated'],scope=scope)


def test_actual_ce2039_receipt_is_bound_and_read_only():
    path=Path('D:/AM6B-Project/ce2029-results-20261021/ce2039-gattaca-open-range-result1.json')
    before=path.read_bytes();value=json.loads(before)
    scope=probe.diagnostic_scope(path,value['request_id'])
    assert scope['native_instance']==value['native_instance'] and scope['transport_sha256']==value['url_sha256']
    assert path.read_bytes()==before


@pytest.mark.parametrize('failed',[False,True])
def test_cli_uses_existing_private_raw_capture_and_preserves_earlier_failed_probe(tmp_path,monkeypatch,failed):
    workspace=tmp_path/'repo';(workspace/'review-evidence').mkdir(parents=True)
    old=workspace/'review-evidence/ce-playback-log-123.json';old.write_text('{"old":"failed"}')
    value=receipt();value['private_extra']='private-account-or-url'
    receipt_path=tmp_path/'diagnostic.json';receipt_path.write_text(json.dumps(value))
    raw=b'private-account-or-url raw remains in external evidence only'
    retained=tmp_path/'private-raw';calls=[];closed=[]
    class SFTP:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stat(self,path):return SimpleNamespace(st_size=len(raw))
        def open(self,path,mode):
            assert path in ('/storage/.kodi/temp/kodi.log','/storage/.kodi/temp/kodi.old.log')
            assert mode=='rb'
            return io.BytesIO(raw)
    client=SimpleNamespace(open_sftp=lambda:SFTP(),close=lambda:closed.append(True))
    def readonly(connection,code,**kwargs):
        assert connection is client and kwargs['deadline_seconds']==20
        assert b'private-account-or-url' not in code
        compile(code,'diagnostic-probe','exec');calls.append(code)
        return (1 if failed else 0),dict(lines=[],share_observations=[],crashes=[]),failed
    module=SimpleNamespace(connect=lambda:(client,SimpleNamespace(readonly=readonly)))
    spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
    monkeypatch.setattr(probe.importlib.util,'spec_from_file_location',lambda *args:spec)
    monkeypatch.setattr(probe.importlib.util,'module_from_spec',lambda spec:module)
    monkeypatch.setattr(probe,'ROOT',workspace)
    monkeypatch.setattr(probe.time,'time_ns',lambda:123)
    monkeypatch.setattr(sys,'argv',['probe','--transport-source',str(tmp_path),'--request',REQUEST,
        '--diagnostic-receipt',str(receipt_path),'--retain-raw',str(retained),'--brief'])
    if failed:
        with pytest.raises(RuntimeError,match='log probe failed'):probe.main()
    else:probe.main()
    assert len(calls)==1 and closed==[True]
    assert (retained/'kodi.log').read_bytes()==raw and (retained/'kodi.old.log').read_bytes()==raw
    assert old.read_text()=='{"old":"failed"}'
    new=workspace/'review-evidence/ce-playback-log-diagnostic-123.json'
    assert new.is_file() and 'private-account-or-url' not in new.read_text()


def test_cli_rejects_launch_stub_before_loading_transport_or_connecting(tmp_path,monkeypatch):
    path=tmp_path/'stub.json';path.write_text(json.dumps(dict(operation='start',request_id=REQUEST,state='launched')))
    monkeypatch.setattr(sys,'argv',['probe','--transport-source',str(tmp_path),'--request',REQUEST,
                                   '--diagnostic-receipt',str(path)])
    monkeypatch.setattr(probe.importlib.util,'spec_from_file_location',
                        lambda *args:pytest.fail('Invalid receipt must fail before transport load'))
    with pytest.raises(ValueError,match='DIAGNOSTIC_RECEIPT_INVALID'):probe.main()

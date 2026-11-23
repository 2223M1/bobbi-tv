"""Offline collection contracts for 65-second observations; no device calls."""
import ast
import json
import sys
from types import SimpleNamespace

import pytest

from test_ce2039_diagnostic_log_probe import execute_remote, REQUEST, TRANSPORT, probe
from test_ce_log_evidence_bound import bounded
from test_ce_trial_metrics import metrics


def window(index=1, phase='window'):
    return dict(event='share_read', phase=phase, timing_scope='block_cumulative',
        observation_begin_us=100_000_000, monotonic_us=(100+index*5)*1_000_000,
        run='1'*16, http=4, transport=TRANSPORT, request='2'*16, file='3'*64,
        gate=5, start=117, end=200_000_000, offset=index*1_000_000,
        bytes=index*1_000_000, delivered=index*1_000_000, stage='write',
        wait_ms=index*100, fetch_ms=index*4000, write_ms=index*900,
        wall_ms=index*5000, cancel='none', method='GET', role='unknown')


def metric_definitions():
    namespace={}
    nodes=[node for node in ast.parse(metrics.REMOTE).body
           if isinstance(node,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef))]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-metric-definitions','exec'),namespace)
    return namespace


def test_log_probe_preserves_new_window_fields_through_existing_safe_schema(tmp_path,monkeypatch):
    rows=[window(index) for index in range(1,14)]+[window(14,'end')]
    value,_=execute_remote(tmp_path,monkeypatch,['[bobbi] '+REQUEST+' SESSION_ACTIVATED']+
        ['[bobbi] '+json.dumps(dict(row,url='https://secret.invalid',account='private')) for row in rows])
    assert value['share_observations']==rows
    assert 'secret' not in json.dumps(value['share_observations'])
    assert 'private' not in json.dumps(value['lines'])  # No raw duplicate bypasses the structured filter.


def test_ordinary_transport_scope_is_exact_and_not_a_playback_request_hash(tmp_path,monkeypatch):
    monkeypatch.setattr(probe,'REMOTE','TRANSPORT_SHA256='+repr(TRANSPORT)+'\n'+probe.REMOTE)
    wanted=window()
    unrelated=dict(wanted,transport='0'*64,request='2'*16)
    hash_only={key:value for key,value in wanted.items() if key!='transport'}
    value,_=execute_remote(tmp_path,monkeypatch,['[bobbi] '+REQUEST+' SESSION_ACTIVATED']+
        ['[bobbi] '+json.dumps(row) for row in (unrelated,wanted,hash_only)],journal=json.dumps(unrelated))
    assert value['share_observations']==[wanted]
    assert value['transport_sha256']==TRANSPORT and value['transport_scope_matched'] is True
    assert '0'*64 not in json.dumps(value)


def test_empty_exact_transport_scope_is_reported_not_fallback_matched(tmp_path,monkeypatch):
    monkeypatch.setattr(probe,'REMOTE',"TRANSPORT_SHA256='"+'0'*64+"'\n"+probe.REMOTE)
    value,_=execute_remote(tmp_path,monkeypatch,['[bobbi] '+REQUEST+' SESSION_ACTIVATED',
                                               '[bobbi] '+json.dumps(window())])
    assert value['share_observations']==[] and value['transport_scope_matched'] is False


def test_bound_retains_every_window_and_terminal_despite_large_unrelated_middle():
    rows=[window(index) for index in range(1,14)]+[window(14,'end')]
    noisy=[dict(event='share_read',phase='fetch_end',http=index,len=index,extra='x'*1000)
           for index in range(300)]
    raw=bounded()(dict(lines=['START']+['字幕'*300]*300+['END'],
                       share_observations=[noisy[0]]+noisy[1:150]+rows+noisy[150:]))
    value=json.loads(raw)
    assert len(raw.encode())<=120*1024
    assert all(row in value['share_observations'] for row in rows)
    assert value['truncation']['protected_observations_complete'] is True


def test_protected_overflow_returns_explicit_incomplete_partial_with_counts():
    rows=[dict(window(index),http=index) for index in range(1,250)]
    raw=bounded()(dict(lines=[],share_observations=rows),limit=3000)
    value=json.loads(raw)
    assert len(raw.encode())<=3000
    counts=value['truncation']
    assert counts['protected_observations_complete'] is False
    assert counts['protected_observations_dropped']>0
    assert counts['protected_observations_original']==249
    assert len(value['share_observations'])+counts['protected_observations_dropped']==249
    assert value['share_observations'][0]==rows[0] and value['share_observations'][-1]==rows[-1]


def test_unprotected_endpoints_are_removed_before_any_protected_window():
    rows=[window(1),window(13),window(14,'end')]
    raw=bounded()(dict(lines=['first'*200,'last'*200],share_observations=list(rows)),limit=3000)
    value=json.loads(raw)
    assert len(raw.encode())<=3000
    assert value['share_observations']==rows
    assert value['truncation']['dropped']['lines']>0
    assert value['truncation']['protected_observations_dropped']==0
    assert value['truncation']['protected_observations_complete'] is True


def test_metrics_keep_all_window_fields_and_reject_sensitive_values():
    trace=metric_definitions()['trace_line']
    original=window()
    row=trace(('prefix '+json.dumps(dict(original,url='https://secret.invalid',account='private'))).encode())
    assert row=={key:value for key,value in original.items() if key!='event'}
    invalid=dict(original,observation_begin_us=True,bytes=-1,transport='https://secret.invalid',
                 request='z'*16,timing_scope='private',stage='private')
    safe=trace(json.dumps(invalid).encode())
    assert not {'observation_begin_us','bytes','transport','request','timing_scope','stage'} & safe.keys()
    assert 'private' not in json.dumps(safe) and 'secret' not in json.dumps(safe)


def test_metrics_export_windows_without_summing_cumulative_counts():
    scope=metric_definitions()
    rows=[scope['trace_line'](json.dumps(window(index)).encode()) for index in range(1,14)]
    rows.append(scope['trace_line'](json.dumps(window(14,'end')).encode()))
    result=scope['trace_summary'](SimpleNamespace(events=rows,gaps=0,missing=0),70)
    series=result['block_cumulative_observations']
    assert series['rows']==rows and series['complete'] is True
    assert series['dropped']==0 and series['original_count']==14
    assert 'not sum' in series['qualification']
    assert result['fetch_end_bytes_observed']==0
    assert result['completed_response_delivered_bytes_observed']==14_000_000


def test_metrics_series_and_total_receipt_are_bounded_and_loss_is_explicit():
    scope=metric_definitions()
    rows=[{key:value for key,value in dict(window(index),http=index).items() if key!='event'}
          for index in range(1,1001)]
    trace=scope['trace_summary'](SimpleNamespace(events=rows,gaps=0,missing=0),70)
    series=trace['block_cumulative_observations']
    assert len(json.dumps(series['rows']).encode())<=32*1024
    assert series['complete'] is False and series['dropped']>0
    assert series['original_count']==len(series['rows'])+series['dropped']
    result=dict(trace=trace,errors=[],samples=[dict(monotonic=index,text='x'*2000) for index in range(61)])
    raw=scope['bounded_metrics'](result)
    retained=json.loads(raw)
    assert len(raw.encode())<=120*1024
    assert retained['errors']
    assert retained['samples'][0]['monotonic']==0 and retained['samples'][-1]['monotonic']==60
    assert retained['truncation']['samples_dropped']>0
    from ce_playback_trial import result_exit_code
    assert result_exit_code(retained,operation='metrics')==1


@pytest.mark.parametrize('result,reason', [
    (dict(lines=[],share_observations=[window()],truncation={'protected_observations_complete':False,
          'protected_observations_dropped':2}),'incomplete protected evidence'),
    (dict(lines=[],share_observations=[],transport_scope_matched=False),'transport scope not observed')])
def test_cli_saves_partial_evidence_and_counts_before_failure(tmp_path,monkeypatch,result,reason):
    root=tmp_path/'repo';(root/'review-evidence').mkdir(parents=True)
    received=[]
    client=SimpleNamespace(close=lambda:None)
    def readonly(connection,code,**kwargs):
        assert b"TRANSPORT_SHA256='"+TRANSPORT.encode()+b"'" in code
        received.append(True)
        return 0,result,False
    module=SimpleNamespace(connect=lambda:(client,SimpleNamespace(readonly=readonly)))
    spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
    monkeypatch.setattr(probe.importlib.util,'spec_from_file_location',lambda *args:spec)
    monkeypatch.setattr(probe.importlib.util,'module_from_spec',lambda spec:module)
    monkeypatch.setattr(probe,'ROOT',root)
    monkeypatch.setattr(sys,'argv',['probe','--transport-source',str(tmp_path),'--request',REQUEST,
                                  '--transport-sha256',TRANSPORT,'--brief'])
    with pytest.raises(RuntimeError,match=reason):probe.main()
    artifacts=list((root/'review-evidence').glob('ce-playback-log-*.json'))
    assert received==[True] and len(artifacts)==1
    assert json.loads(artifacts[0].read_text())==result


def test_cli_rejects_url_instead_of_hash_before_connecting(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'argv',['probe','--transport-source',str(tmp_path),'--request',REQUEST,
                                  '--transport-sha256','https://private.invalid'])
    monkeypatch.setattr(probe.importlib.util,'spec_from_file_location',
                        lambda *args:pytest.fail('Must reject before loading transport'))
    with pytest.raises(ValueError,match='TRANSPORT_SHA256_INVALID'):probe.main()

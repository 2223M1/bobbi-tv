"""Post-fix invariants, using retained real dual-layer decoder text."""
from copy import deepcopy
import json
from pathlib import Path
import re

from test_ce_trace_signal_diagnostics import functions

ROOT=Path(__file__).resolve().parents[1]


def real_text():
    return json.loads((ROOT/'review-evidence/ce-new-work-grand_budapest-observe-1792551462588057300.json').read_text(encoding='utf-8'))['result']['decoder']


def test_real_channels_survive_both_orders_without_summing_layers():
    ns=functions()
    raw=real_text();blocks=re.findall(r'(?ms)^vdec channel \d+ statistics:.*?(?=^vdec channel \d+ statistics:|\Z)',raw)
    first=ns['decoder_snapshot'](raw,1,2)
    reverse=ns['decoder_snapshot'](''.join(reversed(blocks)),1,2)
    assert first['channels']==reverse['channels']
    assert len(first['channels'])==2 and first['primary_channel']==reverse['primary_channel']==0
    assert first['channels'][0]['counters']['drop count']==8
    assert first['channels'][1]['counters']['drop count']==0
    assert first['raw']==raw and first['sha256']!=reverse['sha256']


def test_interval_identity_reset_and_cumulative_counts():
    ns=functions();snapshot=ns['decoder_snapshot'](real_text(),1,1.1)
    a=dict(native=dict(native_instance=1,request_id='a'),decoder=snapshot)
    b=deepcopy(a);b['decoder'].update(read_started=2,read_completed=2.1)
    b['decoder']['channels'][0]['counters']['frame count']+=24
    b['decoder']['channels'][1]['counters']['frame count']+=24
    intervals=ns['decoder_intervals'](a,b)
    assert [r['delta']['drop count'] for r in intervals]==[0,0] # old eight are not new errors
    assert ns['decoder_frame_pair'](a,b)==(1755,1779) # never 3510 -> 3558
    b['decoder']['channels'][0]['counters']['frame count']=1
    assert ns['decoder_intervals'](a,b)[0]['delta'] is None
    assert ns['decoder_frame_pair'](a,b)==(None,None)
    b['native']['request_id']='new'
    assert ns['decoder_intervals'](a,b)==[]


def test_missing_or_duplicate_identity_cannot_prove_continuity():
    ns=functions()
    assert ns['decoder_snapshot']('frame count: 24',1,2)['identity_known'] is False
    assert ns['decoder_snapshot'](real_text()+real_text(),1,2)['identity_known'] is False
    a=dict(native=dict(native_instance=1,request_id='a'),decoder=ns['decoder_snapshot'](real_text(),1,2))
    b=deepcopy(a);b['decoder'].update(read_started=3,read_completed=4)
    b['decoder']['channels'][0]['device']='changed'
    assert ns['decoder_frame_pair'](a,b)==(None,None)

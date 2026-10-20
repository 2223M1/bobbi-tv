"""Attended maintenance controls on a named trial, never production automation.

The owner authorized these interactive playback checks. Standard Kodi seek and
subtitle controls have no expected-instance parameter: before/after checks are
recorded, not presented as atomic protection. Never use this as an auto-resume
or background-control implementation. Abort if another playback is observed.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import json,pathlib,time,urllib.request
record=json.loads(pathlib.Path(RECORD).read_text())
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3) as response:value=json.load(response)
 assert 'error' not in value,'RPC_ERROR'
 return value['result']
def snapshot():
 native=rpc('Player.BobiState')
 row=native.get('playback') or {}
 active=rpc('Player.GetActivePlayers')
 data={'at':time.monotonic(),'native':row,'players':active}
 if active:
  data['properties']=rpc('Player.GetProperties',{'playerid':1,'properties':['time','totaltime','speed','subtitleenabled','currentsubtitle']})
 return data
def own(value):
 row=value['native']
 assert row.get('phase')=='AV_STARTED','TRIAL_NOT_PLAYING'
 assert row.get('request_id')==record.get('request_id') and row.get('native_instance')==record.get('native_instance'),'TRIAL_REPLACED'
def seconds(v):return v['hours']*3600+v['minutes']*60+v['seconds']+v['milliseconds']/1000
before=snapshot();own(before)
out=dict(operation=OP,before=before,atomic_instance_control=False,operator_test=True)
if OP in ('seek-tail','seek-middle'):
 if OP=='seek-tail':assert record['test']['kind']=='tv','EPISODE_TEST_ONLY'
 length=seconds(before['properties']['totaltime'])
 assert 120<length<10800,'DURATION_SCOPE'
 target=int(length)-25 if OP=='seek-tail' else int(length/2)
 own(snapshot())
 out['command_result']=rpc('Player.Seek',{'playerid':1,'value':{'time':{'hours':target//3600,'minutes':(target%3600)//60,'seconds':target%60,'milliseconds':0}}})
 out['target_seconds']=target
elif OP in ('subtitle-off','subtitle-on'):
 own(snapshot())
 out['command_result']=rpc('Player.SetSubtitle',{'playerid':1,'subtitle':'off' if OP=='subtitle-off' else 'on'})
else:raise AssertionError('OPERATOR_SCOPE')
out['observations']=[]
for index in range(6):
 time.sleep(2)
 value=snapshot();out['observations'].append(value)
 if value['native'].get('native_instance')!=record.get('native_instance'):break
out['same_instance_after']=all(v['native'].get('native_instance')==record.get('native_instance') for v in out['observations'])
if OP in ('subtitle-off','subtitle-on'):
 expected=OP=='subtitle-on'
 out['observed_intent_preserved']=out['same_instance_after'] and all(v.get('properties',{}).get('subtitleenabled') is expected for v in out['observations'])
print(json.dumps(out,ensure_ascii=False))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('work',choices=('coherence','odd_taxi','tokyo_godfathers','flip_flappers','haibane_renmei'))
    parser.add_argument('operation',choices=('seek-tail','seek-middle','subtitle-off','subtitle-on'))
    parser.add_argument('--attempt',type=int,choices=range(1,11),required=True)
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--brief',action='store_true')
    args=parser.parse_args()
    name='trial-'+args.work+('' if args.attempt==1 else '-'+str(args.attempt))+'.json'
    record='/storage/.local/share/bobbi-private-trials/20261020/'+name
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('operator_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client,wire=module.connect()
    try:
        script = 'RECORD='+repr(record)+'\nOP='+repr(args.operation)+'\n'+REMOTE
        wrapped = ('import json,traceback\ntry:\n exec(compile('+repr(script)+',"ce-operator-trial","exec"))\n'
                   'except Exception as error:\n print(json.dumps(dict(error=type(error).__name__,reason=str(error) if isinstance(error,AssertionError) else "OPERATOR_ERROR",frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])))\n')
        code,result,diagnostic=wire.readonly(client,wrapped.encode(),deadline_seconds=25)
    finally:client.close()
    path=ROOT/'review-evidence'/('ce-operator-'+args.work+'-'+args.operation+'-'+str(time.time_ns())+'.json')
    path.write_text(json.dumps(dict(result=result,exit_code=code,diagnostic_present=bool(diagnostic)),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shown = result
    if args.brief:
        shown = {key: result[key] for key in ('operation','error','reason','frames','target_seconds','command_result',
            'same_instance_after','observed_intent_preserved','atomic_instance_control') if key in result}
        shown['last'] = (result.get('observations') or [None])[-1]
    print(json.dumps(dict(evidence=str(path),result=shown),ensure_ascii=False))
    if code or diagnostic or result.get('error'):raise RuntimeError('OPERATOR_TEST_UNCONFIRMED')


if __name__=='__main__':main()

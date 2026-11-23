"""Temporary native video/cache diagnostics, with exact prior-setting restore."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

REMOTE = r'''
import json,pathlib,time,urllib.request
def rpc(method,params=None):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=4) as f:r=json.load(f)
 if 'error' in r:raise RuntimeError('RPC_FAILED')
 return r['result']
keys=('debug.showloginfo','debug.extralogging','debug.setextraloglevel')
def read():return {k:rpc('Settings.GetSettingValue',{'setting':k})['value'] for k in keys}
def write(values):
 for key,value in values.items():
  if rpc('Settings.SetSettingValue',{'setting':key,'value':value}) is not True:raise RuntimeError('SETTING_REJECTED')
current=read()
record=pathlib.Path('/storage/.local/share/bobbi-private-trials/20261020/startup-logging-'+STAMP+'.json')
result=dict(mode=MODE,before=current,timestamp=time.time())
if MODE!='status':
 if rpc('Player.GetActivePlayers'):raise RuntimeError('IDLE_REQUIRED')
 if MODE=='on':
  if not isinstance(current[keys[2]],list) or not all(type(v) is int for v in current[keys[2]]):raise RuntimeError('SETTING_SCHEMA')
  expected={keys[0]:True,keys[1]:True,keys[2]:sorted(set(current[keys[2]])|{2048,32768,262144})}
  record.parent.mkdir(parents=True,exist_ok=True)
  with record.open('x') as f:json.dump(dict(before=current,expected=expected),f)
  try:
   write(expected)
   if read()!=expected:raise RuntimeError('SETTING_READBACK')
  except Exception:
   write(current)
   raise
 else:
  saved=json.loads(record.read_text())
  if current!=saved['expected']:raise RuntimeError('DIAGNOSTICS_CHANGED_EXTERNALLY')
  write(saved['before'])
  if read()!=saved['before']:raise RuntimeError('RESTORE_READBACK')
  result['restored']=True
 result['after']=read()
print(json.dumps(result))
'''

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('status','on','off'))
    p.add_argument('--stamp',required=True)
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not a.stamp.isdecimal() or len(a.stamp)!=14 or a.output.exists():p.error('Exact new receipt and timestamp required')
    transport.REMOTE='MODE='+repr(a.mode)+'\nSTAMP='+repr(a.stamp)+'\n'+REMOTE
    transport.run(a.transport_source,a.output)

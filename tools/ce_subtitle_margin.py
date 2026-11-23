"""Attended, reversible one-setting readability adjustment; no program changes."""
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
TRANSPORT=Path('D:/AM6B-Project/AM6B-review-ui-anirss-20261018')
REMOTE=r'''
import json,pathlib,time,urllib.request
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as response:result=json.load(response)
 assert 'error' not in result,'RPC_FAILED'
 return result['result']
assert rpc('Player.GetActivePlayers')==[],'PLAYBACK_ACTIVE'
names=['subtitles.marginvertical','subtitles.align','subtitles.overridefonts','subtitles.overridestyles','subtitles.overrideass','subtitles.fontsize','subtitles.colorpick','subtitles.pgsverticalmode']
def values():return {name:rpc('Settings.GetSettingValue',dict(setting=name))['value'] for name in names}
before=values()
assert abs(before['subtitles.marginvertical']-4.95)<.001,'SETTING_CHANGED'
path=pathlib.Path('/storage/.local/share/bobbi-private-trials/20261020')/('subtitle-margin-'+str(time.time_ns())+'.json')
record=dict(before=before,setting='subtitles.marginvertical',target=7.5,state='BACKED_UP')
with path.open('x') as stream:json.dump(record,stream,indent=2)
assert rpc('Player.GetActivePlayers')==[],'PLAYBACK_STARTED'
assert rpc('Settings.SetSettingValue',dict(setting='subtitles.marginvertical',value=7.5)) is True,'SET_FAILED'
after=values()
assert all(after[k]==before[k] for k in names if k!='subtitles.marginvertical'),'UNRELATED_SETTING_CHANGED'
assert after['subtitles.marginvertical']==7.5,'SET_NOT_APPLIED'
record.update(after=after,state='APPLIED',scope='ADAPTED_TEXT_MARGIN_NOT_ASS_POSITION_OVERRIDE',physical_screen_verified=False)
path.write_text(json.dumps(record,indent=2))
print(json.dumps(dict(record=record,backup=str(path)),ensure_ascii=False))
'''
sys.path.insert(0,str(TRANSPORT/'ui-redesign/runtime/ssh-python'))
spec=importlib.util.spec_from_file_location('margin_transport',TRANSPORT/'ui-redesign/tools/device_transport.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
client,wire=transport.connect()
try:code,result,diagnostic=wire.readonly(client,REMOTE.encode(),deadline_seconds=20)
finally:client.close()
path=ROOT/'review-evidence/ce-20261020'/('subtitle-margin-'+str(time.time_ns())+'.json')
path.write_text(json.dumps(dict(result=result,exit_code=code,diagnostic_present=bool(diagnostic)),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(evidence=str(path),result=result),ensure_ascii=False))
if code or diagnostic:raise SystemExit(1)

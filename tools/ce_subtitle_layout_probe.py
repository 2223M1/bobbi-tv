"""Read subtitle layout/view/calibration only; never print account settings."""
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
TRANSPORT=Path('D:/AM6B-Project/AM6B-review-ui-anirss-20261018')
REMOTE=r'''
import json,pathlib,urllib.request,xml.etree.ElementTree as ET
root=pathlib.Path('/storage/.kodi/userdata')
def rpc(method,params=None):
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as response:result=json.load(response)
 return result.get('result',dict(error=result.get('error')))
document=ET.parse(root/'guisettings.xml').getroot()
settings={n.get('id'):n.text for n in document.findall('setting') if n.get('id','').startswith('subtitles.') or n.get('id') in ('videoplayer.stretch43','videoscreen.screenmode','videoscreen.resolution','videoscreen.screen')}
settings={k:v for k,v in settings.items() if not any(s in k for s in ('path','custom','directory'))}
out=dict(settings=settings,calibrations=[ET.tostring(n,encoding='unicode') for n in document.findall('./resolutions/resolution')],
 active=rpc('Player.GetActivePlayers'),view=rpc('Player.GetViewMode'),
 labels=rpc('XBMC.GetInfoLabels',dict(labels=['System.ScreenResolution','VideoPlayer.VideoResolution','VideoPlayer.StereoMode'])))
if out['active']:
 out['item']=rpc('Player.GetItem',dict(playerid=1,properties=['title','showtitle','season','episode']))
 out['streams']=rpc('Player.GetProperties',dict(playerid=1,properties=['currentvideostream','currentsubtitle','subtitleenabled']))
out['video_defaults']=[ET.tostring(n,encoding='unicode') for n in document.findall('defaultvideosettings')]
print(json.dumps(out,ensure_ascii=False))
'''
sys.path.insert(0,str(TRANSPORT/'ui-redesign/runtime/ssh-python'))
spec=importlib.util.spec_from_file_location('layout_probe_transport',TRANSPORT/'ui-redesign/tools/device_transport.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
client,wire=transport.connect()
try:code,result,diagnostic=wire.readonly(client,REMOTE.encode(),deadline_seconds=20)
finally:client.close()
path=ROOT/'review-evidence/ce-20261020'/('subtitle-layout-'+str(time.time_ns())+'.json')
path.write_text(json.dumps(dict(result=result,exit_code=code,diagnostic_present=bool(diagnostic)),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(evidence=str(path),result=result),ensure_ascii=False))
if code or diagnostic:raise SystemExit(1)

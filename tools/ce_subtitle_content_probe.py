"""Read only the observed small subtitle, never video bytes or a cloud task."""
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = Path('D:/AM6B-Project/AM6B-review-ui-anirss-20261018')
REMOTE = r'''
import hashlib,json,re,sys,urllib.request,urllib.parse,pathlib,sqlite3,subprocess
sys.dont_write_bytecode=True
sys.path.insert(0,'/storage/.kodi/addons/script.module.bobbi.core/lib')
sys.path.extend(str(p) for p in pathlib.Path('/storage/.kodi/addons').glob('script.module.*/lib') if p.is_dir())
from bobbi_core.torrent_subtitles import matching_chinese_sidecars
from bobbi_core.subtitle_cues import parse,_seconds
from bobbi_core.fonts import subtitle_text
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
root=pathlib.Path('/storage/.kodi/userdata/addon_data')
runtime=json.loads((root/'script.module.bobbi.platform/runtime.json').read_text())
request=urllib.request.Request('http://127.0.0.1:%d/control'%runtime['port'],json.dumps(dict(action='account_status',body={})).encode(),{'Authorization':'Bearer '+runtime['token'],'Content-Type':'application/json'})
with opener.open(request,timeout=3) as response:scope=json.load(response)['result']
assert scope['authenticated'] and scope['account_id'].startswith('115:')
state=root/'plugin.video.bobbi/preparation'/(scope['account_id'][4:]+'-'+str(scope['epoch']))
from bobbi_core.metadata_cache import MetadataCache
from bobbi_core.preparation_host import configuration,_private
from bobbi_core.authenticated_cd2 import AuthenticatedCD2
from bobbi_core.cloud_mapping import map_torrent_file
from bobbi_core.cloud_qualifier import CloudQualifier
metadata=MetadataCache(state/'torrent-file-metadata').load('12733bd6fadad8406d4cad55606e8734aefa0ef7')
assert metadata.get('hash')=='12733bd6fadad8406d4cad55606e8734aefa0ef7','TORRENT_CHANGED'
files=metadata['file_stats'];media=[f for f in files if f['id']==3]
assert len(media)==1 and media[0]['length']==411570230 and media[0]['path'].endswith(' - 01 [WebRip 1920x1080 HEVC-yuv420p10 AAC].mkv'),'FILE_CHANGED'
choices=matching_chinese_sidecars(media[0]['path'],files)
assert len(choices)==1,'SUBTITLE_AMBIGUOUS'
chosen=choices[0]
assert chosen['id']==1 and chosen['length']==417001,'SUBTITLE_CHANGED'
with sqlite3.connect((state/'resources.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 rows=db.execute('SELECT DISTINCT t.destination,t.payload FROM tasks t JOIN prepared_bindings b ON b.task=t.id WHERE t.source_hash=?',(metadata['hash'],)).fetchall()
 bindings=db.execute('SELECT r.payload FROM subtitle_revisions r JOIN subtitle_current c ON c.revision=r.seq JOIN subtitle_preparation s ON s.video_key=c.video_key JOIN prepared_bindings b ON b.resource=s.resource WHERE b.media_id=?',('tmdb:tv:68272:s1:e1',)).fetchall()
 font_bindings=[json.loads(r[0]).get('font_result') for r in bindings]
assert len(rows)==1,'TASK_AMBIGUOUS'
config=configuration(root/'script.module.bobbi.platform/preparation.json')
provider=AuthenticatedCD2(_private(config['cd2_token_file']),config['cd2_endpoint']+'/clouddrive.CloudDriveFileSrv/',lambda:json.loads(_private(config['cd2_login_file'])))
task=rows[0];observation=json.loads(task['payload'])['provider_observation']
observations=[r for r in provider.offline_tasks(task['destination']) if r['info_hash']==metadata['hash']]
assert len(observations)==1 and observations[0]['status']==2
assert all(observations[0][k]==observation[k] for k in ('file_id','parent_id'))
item=map_torrent_file(provider,task['destination'],observations[0],chosen)
qualifier=CloudQualifier(config['ffprobe'],config['cd2_endpoint'],config['download_capability'])
url=qualifier.download_url(provider,item)
with provider.session.get(url,stream=True,timeout=(3,8)) as response:
 response.raise_for_status();raw=response.raw.read(chosen['length']+1)
assert len(raw)==chosen['length'],'SUBTITLE_LENGTH'
out=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),selected_subtitle_id=1)
out['font_bindings']=[dict(status=b.get('status'),missing=b.get('missing'),selected_count=len(b.get('selected',[]))) for b in font_bindings if b]
try:out['cue_count']=len(parse(raw,'.ass'))
except ValueError as e:out['parse_error']=str(e)
text=subtitle_text(raw);bad=[];zero=0;reverse=0
for line in text.splitlines():
 if not line.casefold().startswith('dialogue:'):continue
 values=line.split(':',1)[1].split(',',9)
 try:
  first,last=_seconds(values[1],True),_seconds(values[2],True)
  if first==last:zero+=1
  if first>last:reverse+=1
  if first>=last and len(bad)<8:bad.append(dict(start=values[1],end=values[2],text_length=len(values[-1]),drawing=bool(re.search(r'\\p[1-9]',values[-1]))))
 except (ValueError,IndexError):bad.append(dict(timestamp_invalid=True))
out.update(zero_duration_events=zero,reversed_events=reverse,sample_invalid_events=bad[:8])
if config.get('font_tool'):
 result=subprocess.run([config['font_tool'],'i'],capture_output=True,timeout=5)
 out['font_helper_rar_formats']=[line.strip() for line in result.stdout.decode(errors='replace').splitlines() if re.search(r'\bRar[0-9]*\b',line)]
if PROBE_FONTS:
 import tempfile
 from bobbi_core.release_font_loader import ReleaseFontLoader
 fonts=[f for f in files if f['id']==40]
 assert len(fonts)==1 and fonts[0]['length']==47296835 and fonts[0]['path'].endswith('fonts(必装字体).rar')
 work=pathlib.Path(tempfile.mkdtemp(prefix='font-rar-',dir='/storage/.local/share/bobbi-private-trials/20261020'))
 def idle():
  req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method='Player.GetActivePlayers')).encode(),{'Content-Type':'application/json'})
  with opener.open(req,timeout=2) as response:return json.load(response).get('result')==[]
 loader=ReleaseFontLoader(provider,qualifier,work,config['font_tool'],idle)
 asset=map_torrent_file(provider,task['destination'],observations[0],fonts[0])
 target=work/'fonts.rar';sha=loader._download(asset,target)
 out['rar_trial']=dict(bytes=target.stat().st_size,sha256=sha,workspace=str(work))
 try:
  decoded=loader._decode(target,sha,work/'decoded')
  out['rar_trial'].update(decoded_fonts=len(decoded),font_bytes=sum(f['bytes'] for f in decoded))
 except ValueError:
  report=work/'decoded/result.json';listing=work/'decoded/listing.stdout'
  out['rar_trial']['decoder_rejected']=True
  if report.is_file():out['rar_trial']['report']=json.loads(report.read_text())
  if listing.is_file():out['rar_trial']['listing_sample']=listing.read_text()[:8000]
print(json.dumps(out,ensure_ascii=False))
'''

sys.path.insert(0, str(TRANSPORT/'ui-redesign/runtime/ssh-python'))
spec = importlib.util.spec_from_file_location('subtitle_probe_transport', TRANSPORT/'ui-redesign/tools/device_transport.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
client, wire = module.connect()
try:
    wrapped = 'import json,traceback\ntry:\n exec(compile('+repr(REMOTE)+',"subtitle-content-probe","exec"))\nexcept Exception as e:\n print(json.dumps(dict(error=type(e).__name__,reason=str(e) if isinstance(e,AssertionError) else "PROBE_ERROR",frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(e.__traceback__)])))\n'
    code, result, diagnostic = wire.readonly(client, ('PROBE_FONTS='+repr('--fonts' in sys.argv)+'\n'+wrapped).encode(), deadline_seconds=100 if '--fonts' in sys.argv else 25)
finally:
    client.close()
path = ROOT/'review-evidence/ce-20261020'/('subtitle-content-'+str(time.time_ns())+'.json')
path.write_text(json.dumps(dict(result=result,exit_code=code,diagnostic_present=bool(diagnostic)),indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(evidence=str(path),result=result),ensure_ascii=False))
if code or diagnostic or result.get('error') or result.get('rar_trial',{}).get('decoder_rejected'):
    raise SystemExit(1)

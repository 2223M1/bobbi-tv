"""Bounded read-only diagnostics from the installed backend and subtitle logs."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import json,pathlib,re,sys,time
sys.dont_write_bytecode=True
for addon in ('plugin.video.bobbi.torrent','script.module.bobbi.core','script.module.requests','script.module.urllib3','script.module.chardet','script.module.certifi','script.module.idna'):
 sys.path.insert(0,'/storage/.kodi/addons/'+addon+'/lib')
from bobbi_torrent.backend import Backend,load_config
from bobbi_torrent.resolver import metadata_files
out={'time':time.time(),'readonly':True}
backend=Backend(load_config('/storage/.kodi/userdata/addon_data/plugin.video.bobbi.torrent/backend.json'))
try:
 raw=backend.request('GET','/echo',time.monotonic()+4,lambda:None)
 out['backend_version']=raw.decode('ascii','replace')[:64]
 raw=backend.request('POST','/torrents',time.monotonic()+5,lambda:None,body={'action':'list'})
 rows=json.loads(raw)
 out['torrent_states']=[]
 for row in (rows if isinstance(rows,list) else [rows])[:40]:
  if not isinstance(row,dict):continue
  value={k:row[k] for k in ('hash','name','title','stat','stat_string','loaded_size','download_speed','active_peers','total_peers') if k in row}
  fs=metadata_files(row)
  value['metadata_files']=len(fs) if fs is not None else None
  out['torrent_states'].append(value)
except Exception as e:out['backend_error']=getattr(e,'code',type(e).__name__)
finally:backend.close()
out['log_events']=[]
for name in ('kodi.old.log','kodi.log'):
 p=pathlib.Path('/storage/.kodi/temp')/name
 if not p.is_file():continue
 with p.open('rb') as f:
  f.seek(max(0,p.stat().st_size-2*1024*1024));lines=f.read().decode('utf-8','replace').splitlines()
 for line in lines:
  if 'subtitles297]' in line or 'subtitles283]' in line or '[BOBBI-TORRENT]' in line or '[bobbi-torrent]' in line:
   # Fixed diagnostics only; avoid serializing URLs or arbitrary response bodies.
   if re.search(r'https?://|magnet:|Cookie|Authorization',line,re.I):continue
   out['log_events'].append(dict(log=name,text=line[:700]))
out['log_events']=out['log_events'][-100:]
out['subtitle_cache']=[]
base=pathlib.Path('/storage/.kodi/userdata/addon_data/plugin.video.bobbi/subtitle-cache283')
if base.is_dir():
 import hashlib
 for query in ('Ping Pong the Animation S01E01','Ping Pong the Animation S01','Ping Pong the Animation'):
  p=base/('search-'+hashlib.sha256(query.encode()).hexdigest()+'.json')
  if p.is_file():
   value=json.loads(p.read_text());rows=value.get('rows',[])
   out['subtitle_cache'].append(dict(query=query,age=time.time()-value.get('time',0),count=len(rows),
    rows=[{k:r.get(k) for k in ('id','native_name','videoname','lang','subtype')} for r in rows[:15] if isinstance(r,dict)]))
if SUBTITLE_DETAIL:
 from bobbi_core.subtitle_candidates import AssrtCandidates,rank
 provider=AssrtCandidates(None,base,token_file=base.parent/'assrt-token')
 out['subtitle_details']=[]
 deadline=time.monotonic()+15
 for ident in (668245,319658):
  try:
   rows=provider.api('detail',{'id':ident},deadline,lambda:False)
   out['subtitle_details'].append(dict(id=ident,details=[dict(
    title=r.get('title'),native_name=r.get('native_name'),videoname=r.get('videoname'),
    filenames=[f.get('f') for f in r.get('filelist',[]) if isinstance(f,dict)]) for r in rows if isinstance(r,dict)]))
  except Exception as e:out['subtitle_details'].append(dict(id=ident,error=type(e).__name__,code=str(e) if re.fullmatch('[A-Z_0-9]{1,80}',str(e)) else None))
print(json.dumps(out))
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--transport-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--subtitle-detail',action='store_true');a=p.parse_args()
    sys.path.insert(0,str(a.transport_source/'ui-redesign/runtime/ssh-python'))
    s=importlib.util.spec_from_file_location('diag_wire',a.transport_source/'ui-redesign/tools/device_transport.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    c,w=m.connect()
    try:rc,result,diag=w.readonly(c,('SUBTITLE_DETAIL='+repr(a.subtitle_detail)+'\n'+REMOTE).encode(),deadline_seconds=30)
    finally:c.close()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(transport_exit=rc,diagnostic_present=bool(diag),result=result),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(output=str(a.output),subtitle_details=result.get('subtitle_details'),backend_error=result.get('backend_error')),ensure_ascii=False));return int(bool(rc or diag))


if __name__=='__main__':raise SystemExit(main())

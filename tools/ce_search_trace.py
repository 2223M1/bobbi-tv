"""Enable/collect a 15-minute selected-hash trace; no search or media IO here."""
import argparse
from pathlib import Path
import re
import probe_ce_candidate as transport

REMOTE = r'''
import json,pathlib,time
root=pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.core')
marker=root/'search-trace.json'
if MODE=='enable':
 root.mkdir(exist_ok=True,parents=True)
 if marker.exists():
  old=json.loads(marker.read_text())
  assert old.get('expires',0)<time.time(),'TRACE_ALREADY_ACTIVE'
 assert not marker.is_symlink()
 marker.write_text(json.dumps(dict(expires=time.time()+900,hashes=HASHES)))
 result=dict(enabled=True,expires_in_seconds=900,hashes=HASHES)
elif MODE=='disable':
 assert not marker.is_symlink()
 if marker.exists():marker.unlink()
 result=dict(enabled=False,trace_files_preserved=True)
else:
 result=dict(traces=[],fanout=[])
 for path in sorted(root.glob('search-trace-*.jsonl'),key=lambda p:p.stat().st_mtime)[-8:]:
  if path.is_symlink() or path.stat().st_size>256*1024:continue
  result['traces'].append(dict(file=path.name,records=[json.loads(line) for line in path.read_text().splitlines()]))
 log=pathlib.Path('/storage/.kodi/temp/kodi.log')
 with log.open('rb') as stream:
  stream.seek(max(0,log.stat().st_size-2*1024*1024))
  for line in stream.read().decode('utf-8','replace').splitlines():
   for prefix in ('FANOUT-OWNER ','FANOUT-TERMINAL '):
    if prefix in line:
     try:value=json.loads(line.split(prefix,1)[1])
     except ValueError:continue
     result['fanout'].append(dict(event=prefix.strip(),value=value))
 result['fanout']=result['fanout'][-40:]
print(json.dumps(result))
'''

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=('enable','collect','disable'))
    p.add_argument('--transport-source', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--hash', action='append', default=[], dest='hashes')
    a = p.parse_args()
    if a.mode == 'enable' and (not 1 <= len(a.hashes) <= 4 or any(not re.fullmatch('[a-f0-9]{40}', h) for h in a.hashes)):
        p.error('One to four exact info hashes required')
    if a.output.exists(): raise FileExistsError('Preserve prior evidence')
    transport.REMOTE = 'MODE='+repr(a.mode)+'\nHASHES='+repr(a.hashes)+'\n'+REMOTE
    transport.run(a.transport_source, a.output)

"""Read the active native overlay, not firmware or account state."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import hashlib,json,pathlib,subprocess,re
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
paths=subprocess.check_output(['systemctl','show','kodi.service','--property=DropInPaths','--value']).decode().split()
out={'dropins':{},'files':{},'running':[]}
for item in paths:
 p=pathlib.Path(item)
 if not p.is_file():continue
 data=p.read_text()
 lines=[line for line in data.splitlines() if line.startswith(('BindReadOnlyPaths=','ExecStart=','[Service]'))]
 out['dropins'][item]={'sha256':sha(p),'lines':lines}
 for name in re.findall(r'/storage/[^\s:]+', '\n'.join(lines)):
  q=pathlib.Path(name)
  if q.is_file():
   row={'sha256':sha(q),'bytes':q.stat().st_size}
   if q.suffix=='.py':row['source']=q.read_text()
   out['files'][name]=row
for pid in subprocess.check_output(['pidof','kodi.bin']).decode().split():
 out['running'].append({'pid':pid,'sha256':sha(pathlib.Path('/proc')/pid/'exe')})
print(json.dumps(out))
'''

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--transport-source',type=Path,required=True)
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args()
 if args.output.exists():raise FileExistsError(args.output)
 transport.run(args.transport_source,args.output)

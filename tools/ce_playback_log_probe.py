"""Read bounded playback diagnostics without exporting URLs or credentials."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib,json,pathlib,re,subprocess,time,sys
sys.path.insert(0,'/storage/.kodi/addons/script.module.bobbi.core/lib')
from bobbi_core.share_stream import observation_fields
root=pathlib.Path('/storage/.kodi')
lines=(root/'temp/kodi.log').read_text(errors='replace').splitlines()
starts=[i for i,line in enumerate(lines) if REQUEST in line and 'SESSION_ACTIVATED' in line]
assert starts, 'REQUEST_NOT_IN_CURRENT_LOG'
lines=lines[max(0,starts[-1]-5):]
markers=('CINEMA-', 'BOBBI-', '[bobbi]', 'VideoPlayer', 'CVideoPlayer',
         'CDVDAudio', 'CDVDClock', 'CAML', 'Font', 'font', 'SUBTITLE', 'subtitle',
         'libass', 'Curl', 'curl', 'ERROR', 'WARNING')
out=[]
observations=[]
for line in lines:
    if '[bobbi] {' in line:
        try:
            value=json.loads(line.split('[bobbi] ',1)[1])
            if value.get('event')=='share_read':
                observations.append(dict(event='share_read',**observation_fields(value)))
        except ValueError:pass
    if not any(m in line for m in markers): continue
    if any(m in line.lower() for m in ('cookie','token','password','authorization','bearer','api_key','apikey')): continue
    line=re.sub(r'(?:https?://|plugin://|magnet:\?)\S+', '<transport>', line)
    out.append(line[:1000])
journal=subprocess.check_output(['journalctl','-u','kodi.service','--since','-30 minutes','-o','cat','--no-pager'],timeout=8).decode(errors='replace')
for line in journal.splitlines():
    start=line.find('{"event": "share_read"')
    if start<0: start=line.find('{"at":')
    if start<0: continue
    try: value=json.loads(line[start:])
    except ValueError: continue
    if value.get('event')=='share_read': observations.append(dict(event='share_read',**observation_fields(value)))
print(json.dumps({'timestamp':time.time(),'request':REQUEST,'lines':out[-450:],
                  'share_observations':observations[-250:],
                  'crashes':[p.name for p in (root/'temp').glob('kodi_crashlog*')][-8:]},ensure_ascii=False))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--brief',action='store_true')
    args=parser.parse_args()
    if len(args.request)!=32 or any(c not in '0123456789abcdef' for c in args.request):
        raise ValueError('request must be a request ID')
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('ce_log_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client,wire=transport.connect()
    try:
        rc,result,diagnostic=wire.readonly(client,('REQUEST='+repr(args.request)+'\n'+REMOTE).encode(),deadline_seconds=20)
    finally: client.close()
    output=ROOT/'review-evidence'/('ce-playback-log-'+str(time.time_ns())+'.json')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shown = result
    if args.brief:
        shown = dict(request=args.request, lines=len(result.get('lines',[])),
                     share_observations=len(result.get('share_observations',[])),crashes=result.get('crashes'))
    print(json.dumps(dict(evidence=str(output),result=shown),ensure_ascii=False))
    if rc or diagnostic: raise RuntimeError('log probe failed')


if __name__=='__main__': main()

"""Real Kodi directory RPC/ordinary navigation, never native borrowed controls."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlsplit

REMOTE = r'''
import json,subprocess,time,urllib.request,urllib.parse
def rpc(method,params=None,timeout=30):
 q=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=timeout) as f:r=json.load(f)
 if 'error' in r:raise RuntimeError('RPC_'+str(r['error'].get('code')))
 return r['result']
if rpc('Player.GetActivePlayers'):raise RuntimeError('PLAYBACK_ACTIVE')
began=time.monotonic()
if MODE=='directory':
 raw=rpc('Files.GetDirectory',dict(directory=URL,media='video',properties=['title','season','episode','year']))
 rows=[]
 for row in raw.get('files',[]):
  path=row.get('file','');p=urllib.parse.urlsplit(path)
  if p.scheme!='plugin' or p.netloc!='plugin.video.bobbi':continue
  fields=urllib.parse.parse_qs(p.query)
  safe={key:values[0] for key,values in fields.items() if len(values)==1 and key in ('action','id','ids','mode','media_type','title','query','tv_name','tv_data','season','force_select')}
  rows.append(dict(label=row.get('label'),title=row.get('title'),filetype=row.get('filetype'),season=row.get('season'),episode=row.get('episode'),year=row.get('year'),route=safe))
 result=dict(rows=rows,limits=raw.get('limits'))
elif MODE=='open':
 rpc('GUI.ActivateWindow',dict(window='videos',parameters=[URL,'return']))
 time.sleep(.4);result={}
elif MODE=='back':
 rpc('Input.Back');time.sleep(.4);result={}
elif MODE=='home':
 rpc('GUI.ActivateWindow',dict(window='home'));time.sleep(.4);result={}
else:result={}
result['elapsed_seconds']=round(time.monotonic()-began,3)
result['gui']=rpc('GUI.GetProperties',{'properties':['currentwindow','currentcontrol']})
labels=['Container.NumItems','Container.FolderName','ListItem.Label','ListItem.DBType','ListItem.Season','ListItem.Episode']
labels+=['Container(50).ListItemAbsolute(%d).Label'%i for i in range(45)]
result['labels']={k:v for k,v in rpc('XBMC.GetInfoLabels',{'labels':labels}).items() if v}
print(json.dumps(result,ensure_ascii=False))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('directory', 'open', 'view', 'back', 'home'))
    parser.add_argument('--url')
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode in ('directory', 'open'):
        parts = urlsplit(args.url or '')
        fields = parse_qs(parts.query)
        if (parts.scheme != 'plugin' or parts.netloc != 'plugin.video.bobbi'
                or fields.get('action') not in (['handle_tmdb_search'], ['show_tmdb_item'],
                    ['show_episodes_details'], ['bobi_related_movies'])):
            parser.error('Catalogue route required')
        if fields.get('action') == ['show_tmdb_item'] and fields.get('mode') != ['tv']:
            parser.error('TV directory only; film selection is a separate attended action')
    if args.output.exists():
        parser.error('Keep prior evidence')
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('navigation_wire', args.transport_source / 'ui-redesign/tools/device_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client, wire = module.connect()
    try:
        code = 'MODE=' + repr(args.mode) + '\nURL=' + repr(args.url) + '\n' + REMOTE
        rc, result, diag = wire.readonly(client, code.encode(), deadline_seconds=40)
    finally:
        client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(mode=args.mode, timestamp=time.time(), exit=rc,
        diagnostic=bool(diag), result=result), ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {key: value for key, value in result.items() if key != 'rows'}
    if 'rows' in result:
        summary['row_count'] = len(result['rows'])
        summary['sample'] = [dict(label=row['label'], title=row['title'], route=row['route'])
                             for row in result['rows'][:6]]
    print(json.dumps(dict(evidence=str(args.output), result=summary), ensure_ascii=False))
    return int(bool(rc or diag))


if __name__ == '__main__':
    raise SystemExit(main())

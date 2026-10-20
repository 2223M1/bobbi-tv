"""Preserve recent terminal evidence without restarting Kodi or exporting secrets."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import json,pathlib,re,time,pickle
root=pathlib.Path('/storage/.kodi/temp')
records={}
for name in ('kodi.old.log','kodi.log'):
    path=root/name
    if not path.exists(): continue
    lines=path.read_text(errors='replace').splitlines()
    starts=[i for i,line in enumerate(lines) if 'SESSION_ACTIVATED' in line]
    start=max(0,starts[-8]-8) if len(starts)>=8 else 0
    out=[]
    for line in lines[start:]:
        if not any(m in line for m in ('CINEMA-', 'BOBBI-', '[bobbi]', 'VideoPlayer',
            'CVideoPlayer', 'CDVDAudio', 'CDVDClock', 'CAML', 'ERROR', 'WARNING')): continue
        if any(m in line.lower() for m in ('cookie','token','password','authorization','bearer','api_key','apikey')): continue
        line=re.sub(r'(?:https?://|plugin://|magnet:\?)\S+', '<transport>', line)
        out.append(line[:1500])
    records[name]={'bytes':path.stat().st_size,'lines':out[-3500:]}
class SafeHistory(pickle.Unpickler):
    def find_class(self,*args): raise ValueError('Non-primitive history')
history=[]
path=pathlib.Path('/storage/.kodi/userdata/addon_data/plugin.video.bobbi/database.pickle')
if path.exists() and path.stat().st_size<64*1024**2:
    with path.open('rb') as stream: database=SafeHistory(stream).load()
    for value in database.get('jt:lfh',{}).values():
        if not isinstance(value,dict): continue
        if value.get('request_id') in ('f767be7a21c14258b07a76967ae19991','82c64939e5e041fcb0f36dfe7367a4d0'):
            history.append({k:value[k] for k in ('request_id','title','source_title','ids','tv_data','mode',
                'terminal_reason','completed','current_time','total_time','cinema_continuity','is_torrent',
                'prepared_version_key','info_hash') if k in value})
print(json.dumps({'timestamp':time.time(),'logs':records,'history':history},ensure_ascii=False))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('ce_recent_transport',
        args.transport_source / 'ui-redesign/tools/device_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client, wire = transport.connect()
    try:
        rc, result, diagnostic = wire.readonly(client, REMOTE.encode(), deadline_seconds=30)
    finally:
        client.close()
    output = ROOT / 'review-evidence' / ('ce-recent-terminal-' + str(time.time_ns()) + '.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'evidence': str(output), 'exit_code': rc,
        'lines': {k: len(v['lines']) for k, v in result.get('logs', {}).items()}}))
    return 1 if rc or diagnostic else 0


if __name__ == '__main__':
    raise SystemExit(main())

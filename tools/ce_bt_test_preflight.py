"""Read existing BT test capabilities without changing rates or starting media."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import json,pathlib,shutil,subprocess,sys,time
sys.dont_write_bytecode=True
sys.path.insert(0,'/storage/.kodi/addons/plugin.video.bobbi.torrent/lib')
sys.path.insert(0,'/storage/.kodi/addons/script.module.requests/lib')
sys.path.insert(0,'/storage/.kodi/addons/script.module.urllib3/lib')
sys.path.insert(0,'/storage/.kodi/addons/script.module.certifi/lib')
sys.path.insert(0,'/storage/.kodi/addons/script.module.chardet/lib')
sys.path.insert(0,'/storage/.kodi/addons/script.module.idna/lib')
from bobbi_torrent.backend import load_config,Backend
backend=Backend(load_config('/storage/.kodi/userdata/addon_data/plugin.video.bobbi.torrent/backend.json'))
try:
 version=backend.request('GET','/echo',time.monotonic()+4,lambda:None).decode('ascii').strip()
 settings=backend.document(backend.request('POST','/settings',time.monotonic()+4,lambda:None,body={'action':'get'}))
 raw=backend.request('POST','/torrents',time.monotonic()+4,lambda:None,body={'action':'list'})
 rows=json.loads(raw)
 out=dict(mode='read_only',version=version,tc_available=bool(shutil.which('tc')),
  settings={key:settings.get(key) for key in ('DownloadRateLimit','UploadRateLimit','CacheSize','PreloadCache','ReaderReadAHead','ResponsiveMode')},
  torrent_count=len(rows) if isinstance(rows,list) else None)
 if shutil.which('tc'):
  result=subprocess.run(['tc','qdisc','show','dev','lo'],capture_output=True,timeout=3)
  out['loopback_qdisc']=result.stdout.decode('ascii','replace').splitlines() if result.returncode==0 else None
 print(json.dumps(out))
finally:backend.close()
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('A new output path is required')
    transport.run(args.transport_source, args.output)

"""Read only installation generation metadata; no journal repair or override."""
import argparse
from pathlib import Path
import probe_ce_candidate as transport

transport.REMOTE = r'''
import json,pathlib
out={}
for name,path in (
 ('legacy','/storage/.local/share/bobbi-private-updates/state.json'),
 ('entry','/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json'),
 ('native','/storage/.local/share/bobbi-native/2026102035/receipt.json')):
 p=pathlib.Path(path)
 row=dict(exists=p.is_file())
 if p.is_file():
  value=json.loads(p.read_text())
  row['fields']=sorted(value)
  row.update({k:value[k] for k in ('schema','sequence','high_watermark','phase','host_pending','state','tx') if k in value})
 out[name]=row
print(json.dumps(out))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('A new output path is required')
    transport.run(args.transport_source, args.output)

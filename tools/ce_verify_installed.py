"""Read-only signed-input/live-file correspondence; never reads user profiles."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib,json,pathlib,zipfile
from io import BytesIO
root=pathlib.Path('/storage/.kodi/addons')
bundle=root/'script.bobbi.start/resources/complete.bobbi-update.zip'
if hashlib.sha256(bundle.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('EMBEDDED_PAYLOAD_MISMATCH')
with zipfile.ZipFile(bundle) as signed:
 manifest=json.loads(signed.read('release.json'))
 rows=[]
 for component in manifest['components']:
  if component['id'] not in OWNED:continue
  with zipfile.ZipFile(BytesIO(signed.read(component['file']))) as archive:
   for name in archive.namelist():
    if '..' in name.split('/') or '\\' in name or ':' in name:raise RuntimeError('UNEXPECTED_PATH')
    path=root/name
    expected=hashlib.sha256(archive.read(name)).hexdigest()
    actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    rows.append(dict(path=name,expected=expected,actual=actual,matched=actual==expected))
print(json.dumps(dict(sequence=manifest['sequence'],files=len(rows),matched=all(r['matched'] for r in rows),mismatches=[r for r in rows if not r['matched']],scope='Owned program files; original dependencies and user data not overwritten or compared')))
'''


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--transport-source',type=Path,required=True)
    p.add_argument('--bundle',type=Path,required=True)
    a=p.parse_args()
    sys.path.insert(0,str(ROOT/'addons/script.module.bobbi.platform/lib'))
    from bobbi_platform.offline_updates import SignedBundle,load_trust
    from bobbi_platform.upstream_addons import OWNED_COMPONENTS
    with SignedBundle(a.bundle,load_trust(),'coreelec') as signed:
        sequence=signed.check_all()['sequence']
    sys.path.insert(0,str(a.transport_source/'ui-redesign/runtime/ssh-python'))
    s=importlib.util.spec_from_file_location('verify_wire',a.transport_source/'ui-redesign/tools/device_transport.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    c,w=m.connect()
    try:
        code='EXPECTED='+repr(hashlib.sha256(a.bundle.read_bytes()).hexdigest())+'\nOWNED='+repr(sorted(OWNED_COMPONENTS))+'\n'+REMOTE
        rc,value,diag=w.readonly(c,code.encode(),deadline_seconds=30)
    finally:c.close()
    out=ROOT/'review-evidence/ce2023'/('installed-files-'+str(time.time_ns())+'.json')
    result=dict(transport_exit=rc,diagnostic_present=bool(diag),expected_sequence=sequence,result=value)
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(out),**result)))
    return int(bool(rc or diag or not value.get('matched') or value.get('sequence')!=sequence))


if __name__=='__main__':raise SystemExit(main())

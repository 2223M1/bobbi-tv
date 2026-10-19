"""Read-only migration prerequisites; never copies accounts into build outputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import hashlib, json, pathlib, subprocess, sys, types, sqlite3, xml.etree.ElementTree as ET
root = pathlib.Path('/storage/.kodi')
out = {'mode':'readonly','services':{},'profiles':{},'addons':{},'preparation':{}}
database=sorted((root/'userdata/Database').glob('Addons*.db'))[-1]
db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
try:
    out['addon_database']={'name':database.name,'installed_columns':db.execute('PRAGMA table_info(installed)').fetchall()}
finally: db.close()
for name in ('kodi','bobitv-preparation.service'):
    out['services'][name] = {key:subprocess.check_output(['systemctl','show',name,'--property='+key,'--value'],timeout=4).decode().strip() for key in ('ActiveState','MainPID','UnitFileState')}
for path in sorted((root/'addons').glob('*/addon.xml')):
    addon=ET.parse(path).getroot()
    name=addon.get('id','')
    if any(word in name for word in ('bobbi','bobi','am6b','jacktook','cryptodome','jacktorr','catalog','mdsub')):
        out['addons'][name] = {'version':addon.get('version'),'xml_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
for path in sorted((root/'userdata/addon_data').iterdir()):
    if path.is_dir() and any(word in path.name for word in ('bobbi','bobi','am6b','jacktook','catalog','mdsub')):
        out['profiles'][path.name]=sorted(p.name for p in path.iterdir() if p.is_file())[:100]
config_path=pathlib.Path('/storage/.local/share/bobitv/preparation-runtime/r3-20260922/config.json')
if config_path.is_file():
    config=json.loads(config_path.read_text())
    out['preparation']['keys']=sorted(config)
    for key in ('cd2_endpoint','cd2_token_file','cd2_login_file','destination','ffprobe','font_tool','font_native_directory','download_capability','torrserver_endpoint','snapshot_path','tmdb_api_key_file','state_directory','python_library_directory'):
        if key in config: out['preparation'][key]=config[key]
    state=pathlib.Path(config['state_directory'])
    ledger=state/'resources.sqlite'
    if ledger.is_file():
        db=sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True)
        try:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            out['preparation']['tables']=sorted(tables)
            out['preparation']['schema_version']=db.execute('PRAGMA user_version').fetchone()[0]
            out['preparation']['foreign_key_errors']=len(db.execute('PRAGMA foreign_key_check').fetchall())
            out['preparation']['ledger_counts']={name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('tasks','prepared_bindings','resources','font_objects','subtitle_current','direct_jobs','preparation_intents') if name in tables}
            out['preparation']['states']={name:dict(db.execute('SELECT state,COUNT(*) FROM '+name+' GROUP BY state').fetchall()) for name in ('tasks','direct_jobs','preparation_intents') if name in tables}
        finally: db.close()
    direct=state/'direct.sqlite3'
    if direct.is_file():
        db=sqlite3.connect(direct.as_uri()+'?mode=ro',uri=True)
        try:
            out['preparation']['direct_states']=dict(db.execute('SELECT state,COUNT(*) FROM direct_jobs GROUP BY state').fetchall())
        finally: db.close()
    out['preparation']['state_children']=[dict(name=p.name,directory=p.is_dir(),bytes=p.stat().st_size if p.is_file() else None) for p in state.iterdir()][:100]
    try:
        sys.path.insert(0,config['python_library_directory'])
        m=types.ModuleType('migration_cd2')
        exec(CD2_SOURCE,m.__dict__)
        client=m.CD2(pathlib.Path(config['cd2_token_file']).read_text().strip(),config['cd2_endpoint'].rstrip('/')+'/clouddrive.CloudDriveFileSrv/')
        try:
            identity=client.provider_identity()
            out['preparation']['cd2_uid_available']=True
            out['preparation']['legacy_scope_matches']=identity['legacy_scope']==config['account']
            out['preparation']['cd2_runtime']=client.runtime_info()
            sessions=[]
            folders=list((root/'userdata/addon_data').iterdir())+[pathlib.Path('/storage/.local/share/am6b-qqdocs-private')]
            for folder in folders:
                if folder.is_dir() and any(x in folder.name for x in ('am6b','bobbi','catalog')):
                    for credential in folder.glob('*linux*.json'):
                        if credential.stat().st_size>16384: continue
                        value=json.loads(credential.read_text())
                        if isinstance(value.get('cookies'),dict):
                            uid=value['cookies'].get('UID','').split('_',1)[0]
                            digest='115:'+hashlib.sha256(('115:'+uid).encode()).hexdigest()
                            sessions.append(dict(profile=folder.name,file=credential.name,uid_matches_cd2=digest==identity['account_id'],app=value.get('app')))
            out['preparation']['sessions']=sessions
        finally: client.session.close()
    except Exception as error:
        out['preparation']['provider_probe_error']=type(error).__name__
print(json.dumps(out))
'''


def run(source, output):
    sys.path.insert(0,str(source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('migration_transport',source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cd2=(ROOT/'addons/script.module.bobbi.core/lib/bobbi_core/cd2.py').read_text(encoding='utf-8')
    client,wire=module.connect()
    try:
        code,result,diagnostic=wire.readonly(client,('CD2_SOURCE='+repr(cd2)+'\n'+REMOTE).encode(),deadline_seconds=55)
        if code or diagnostic: raise RuntimeError('Read-only migration probe failed')
    finally: client.close()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'review-evidence/ce-migration-preflight.json')
    args=parser.parse_args()
    run(args.transport_source,args.output)

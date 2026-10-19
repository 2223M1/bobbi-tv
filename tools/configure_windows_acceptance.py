"""Reuse the owner's existing session for isolated LOCAL acceptance, never builds.

No new QR login, refresh or logout is issued. Secrets remain in memory until
the active Windows host commits its own account; metadata goes only to the
explicit stopped test profile under ignored native/build.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

def host_call(config,action,body):
    request=urllib.request.Request('http://127.0.0.1:%d/control'%config['port'],
        json.dumps(dict(action=action,body=body)).encode(),
        {'Authorization':'Bearer '+config['token'],'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=4) as response:
        result=json.load(response)
    if result.get('ok') is not True:raise RuntimeError('LOCAL_ACCOUNT_REJECTED')
    return result['result']

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--mode',choices=('metadata','account'),required=True)
    parser.add_argument('--report',type=Path,help='Distinct acceptance evidence, never a credential file')
    args=parser.parse_args()
    target_report=args.report or ROOT/'review-evidence'/('windows-local-'+args.mode+'-acceptance.json')
    if args.report and target_report.exists():
        raise ValueError('ACCEPTANCE_REPORT_ALREADY_EXISTS')
    profile=args.profile.absolute()
    if any(p.is_symlink() for p in (profile,*profile.parents)):
        raise ValueError('TEST_PROFILE_SYMLINK')
    if (ROOT/'native/build').resolve() not in profile.resolve().parents:
        raise ValueError('IGNORED_TEST_PROFILE_REQUIRED')
    runtime=profile/'userdata/addon_data/script.module.bobbi.platform/runtime.json'
    if any(p.is_symlink() for p in (runtime,*runtime.parents)):
        raise ValueError('TEST_RUNTIME_SYMLINK')
    if args.mode=='metadata' and runtime.exists():
        raise ValueError('STOP_HOST_BEFORE_METADATA')
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('local_acceptance_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client,_=transport.connect()
    try:
        with client.open_sftp() as channel:
            name=('/storage/.local/share/bobitv/preparation-private/tmdb-key' if args.mode=='metadata'
                else '/storage/.local/share/am6b-qqdocs-private/115-os_linux.json')
            with channel.open(name,'rb') as source:raw=source.read(16385)
        if len(raw)>16384:raise ValueError('LOCAL_CREDENTIAL_SIZE')
    finally:client.close()
    if args.mode=='metadata':
        value=raw.decode().strip()
        if not value or len(value)>1024:raise ValueError('METADATA_CONFIGURATION_INVALID')
        target=profile/'userdata/addon_data/plugin.video.bobbi/settings.xml'
        if any(p.is_symlink() for p in (target,*target.parents)):
            raise ValueError('TEST_SETTINGS_SYMLINK')
        target.parent.mkdir(parents=True,exist_ok=True)
        tree=ET.parse(target) if target.is_file() else ET.ElementTree(ET.Element('settings',{'version':'2'}))
        for key,content in (('tmdb_api_key',value),('auto_play','false')):
            node=tree.getroot().find("setting[@id='%s']"%key)
            if node is None:node=ET.SubElement(tree.getroot(),'setting',{'id':key})
            node.text=content
            node.attrib.pop('default',None)
        tree.write(target,encoding='utf-8',xml_declaration=True)
        target.chmod(0o600)
        result=dict(configured=True,dedicated_distributable_app=False,local_only=True)
    else:
        config=json.loads(runtime.read_text(encoding='utf-8'))
        before=host_call(config,'account_status',{})
        if before.get('authenticated'):raise ValueError('TEST_ACCOUNT_ALREADY_SET_NO_REPLACE')
        value=json.loads(raw)
        # Never retry installation on uncertain transport completion.
        after=host_call(config,'account_install',dict(credentials=value,expected=before))
        if not after.get('authenticated'):raise ValueError('TEST_ACCOUNT_NOT_INSTALLED')
        result=dict(authenticated=True,epoch=after['epoch'],new_login_performed=False,
                    local_only=True,source='owner-existing-CE-session')
    result['test_installation']=profile.parent.name
    print(json.dumps(result))
    target_report.parent.mkdir(parents=True,exist_ok=True)
    target_report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    try:main()
    except Exception as error:
        # Never stringify a network exception containing a request URL/secret.
        print(json.dumps(dict(ok=False,error=type(error).__name__,retry_automatically=False)))
        raise SystemExit(1)

"""Bounded CE status/identity evidence; no account or transport URL output."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import json,pathlib,time,urllib.request,urllib.parse,subprocess,xml.etree.ElementTree as ET
root=pathlib.Path('/storage/.kodi')
def rpc(method,params=None):
    request=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode(),{'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as response:
        result=json.load(response)
    return result.get('result',{'rpc_error':result.get('error',{}).get('code')})
out={'mode':MODE,'timestamp':time.time()}
if MODE=='metadata':
    import sys
    sys.path.insert(0,str(root/'addons/script.module.bobbi.core/lib'))
    from bobbi_core.project_metadata import tmdb_key
    key=tmdb_key()
    out['project_config_present']=bool(key)
    out['configuration_source']='bobbi-project-only'
    query=urllib.parse.urlencode(dict(api_key=key,query='A Separation',primary_release_year=2011,language='en-US'))
    began=time.monotonic()
    try:
        if not key: raise ValueError('PROJECT_CONFIG_MISSING')
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('https://api.themoviedb.org/3/search/movie?'+query,timeout=8) as response:
            data=json.load(response)
            out['http']=response.status
        out['results']=[{k:r.get(k) for k in ('id','title','original_title','release_date')} for r in data.get('results',[])[:10]]
        out['configured_proxy']=False
    except Exception as error: out['error']=type(error).__name__
    out['seconds']=time.monotonic()-began
    out['routing_limit']='No explicit proxy; router/ISP transparent routing is not established by this probe.'
else:
    out['players']=rpc('Player.GetActivePlayers')
    out['gui']=rpc('GUI.GetProperties',{'properties':['currentwindow','currentcontrol','skin']})
    out['application']=rpc('Application.GetProperties',{'properties':['version','name']})
    out['native']=rpc('Player.BobiState')
    out['services']={name:subprocess.check_output(['systemctl','show',name,'--property=ActiveState','--value']).decode().strip() for name in ('kodi.service','bobitv-preparation.service')}
    out['programs']={}
    for name in ('plugin.video.bobbi','plugin.video.bobbi.torrent','plugin.video.jacktorr',
                 'script.module.bobbi.core','script.module.bobbi.platform'):
        path=root/'addons'/name/'addon.xml'
        out['programs'][name]=ET.parse(path).getroot().get('version') if path.is_file() else None
    path=pathlib.Path('/storage/.local/share/bobbi-private-updates/state.json')
    if path.is_file():
        value=json.loads(path.read_text())
        out['program_generation']={k:value.get(k) for k in ('sequence','versions')}
    legacy=root/'userdata/addon_data/plugin.video.jacktorr/settings.xml'
    out['torrent_connection']={'legacy_exists':legacy.is_file()}
    if legacy.is_file():
        values={n.get('id'):n.get('value',n.text or '') for n in ET.parse(legacy).getroot()}
        import ipaddress
        host=values.get('service_host','')
        try: local=host=='localhost' or ipaddress.ip_address(host.strip('[]')).is_loopback
        except ValueError:local=False
        out['torrent_connection'].update(legacy_loopback=local,
            legacy_fields=sorted(k for k in values if k in ('service_host','service_port','ssl_connection',
                'service_login','service_password','metadata_timeout','buffer_timeout')),
            legacy_auth_present=bool(values.get('service_login') or values.get('service_password')))
    backend=root/'userdata/addon_data/plugin.video.bobbi.torrent/backend.json'
    out['torrent_connection']['new_config_exists']=backend.is_file()
    if backend.is_file():
        value=json.loads(backend.read_text())
        out['torrent_connection'].update(schema=value.get('schema'),auth_present=bool(value.get('auth')),
            metadata_seconds=value.get('metadata_seconds'),buffering_seconds=value.get('buffering_seconds'))
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8090/echo',timeout=2) as response:
            value=response.read(64).decode('ascii')
        out['torrent_connection']['existing_engine']=value if value in ('MatriX.144.1','MatriX.147') else 'OTHER'
    except Exception as error:out['torrent_connection']['engine_error']=type(error).__name__
    for name in ('runtime-paths.json','preparation-first-failure.json','bobi-prepared.json','bobi-direct.json'):
        path=root/'userdata/addon_data/plugin.video.bobbi'/name
        if path.is_file():
            value=json.loads(path.read_text())
            if name in ('runtime-paths.json','preparation-first-failure.json'): out[name]=value
            else: out[name]={'schema':value.get('schema',value.get('schema_version')),
                'entry_count':len(value.get('entries',value.get('resources',value.get('titles',[])))),
                'source_count':sum(len(title.get('sources',[])) for title in value.get('titles',[])),
                'account_scoped':bool(value.get('account_scope')),'account_epoch':value.get('account_scope',{}).get('epoch')}
    path=root/'userdata/addon_data/script.module.bobbi.platform/runtime.json'
    if path.is_file():
        value=json.loads(path.read_text())
        host_scope=None
        for action in ('account_status','status','preparation'):
            body={}
            if action=='preparation':
                if not host_scope or not host_scope.get('authenticated'):
                    out['preparation_ping']={'state':'NO_ACCOUNT'}
                    continue
                import sys
                sys.path.insert(0,str(root/'addons/script.module.bobbi.core/lib'))
                from bobbi_core.capabilities import IPC_PROTOCOL
                body=dict(method='ping',body={},protocol=IPC_PROTOCOL,account=host_scope)
            req=urllib.request.Request('http://127.0.0.1:%d/control'%value['port'],json.dumps(dict(action=action,body=body)).encode(),{'Authorization':'Bearer '+value['token'],'Content-Type':'application/json'})
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=2) as response: data=json.load(response)
                result=data.get('result',{})
                if action=='account_status':
                    host_scope=result
                    out['host_account_status']={k:result.get(k) for k in ('authenticated','epoch')}
                    identity=(out.get('native',{}).get('playback') or {}).get('file_identity','')
                    import re,sqlite3
                    match=re.match(r'prepared:([0-9a-f]{64})(?:\||$)',identity)
                    if (match or SOURCE_HASH) and result.get('authenticated') and str(result.get('account_id','')).startswith('115:'):
                        state=root/'userdata/addon_data/plugin.video.bobbi/preparation'/(result['account_id'][4:]+'-'+str(result['epoch']))/'resources.sqlite'
                        out['current_prepared_database_present']=state.is_file()
                        if state.is_file():
                            with sqlite3.connect(state.resolve().as_uri()+'?mode=ro',uri=True,timeout=.2) as db:
                                if SOURCE_HASH:
                                    rows=db.execute('SELECT b.media_id,s.state,s.attempts,s.detail FROM prepared_bindings b JOIN tasks t ON t.id=b.task LEFT JOIN subtitle_preparation s ON s.resource=b.resource WHERE t.source_hash=? ORDER BY b.media_id LIMIT 32',(SOURCE_HASH,)).fetchall()
                                    out['trial_subtitle_tasks']=[dict(media_id=r[0],state=r[1],attempts=r[2],reason=json.loads(r[3] or '{}').get('reason'),stage=json.loads(r[3] or '{}').get('stage'),matcher_policy=json.loads(r[3] or '{}').get('matcher_policy')) for r in rows]
                                    fonts=db.execute('SELECT b.media_id,f.state,f.attempts,f.detail FROM prepared_bindings b JOIN tasks t ON t.id=b.task JOIN subtitle_font_preparation f ON f.resource=b.resource WHERE t.source_hash=? ORDER BY b.media_id LIMIT 32',(SOURCE_HASH,)).fetchall()
                                    out['trial_subtitle_fonts']=[dict(media_id=r[0],state=r[1],attempts=r[2],reason=json.loads(r[3] or '{}').get('reason'),font_count=len(json.loads(r[3] or '{}').get('font_hashes',[]))) for r in fonts]
                                row=db.execute('SELECT s.state,s.attempts,s.detail FROM subtitle_preparation s JOIN prepared_playback_protection p ON p.resource=s.resource WHERE p.request=?',
                                    (out['native']['playback']['request_id'],)).fetchone() if match else None
                                if row:
                                    detail=json.loads(row[2])
                                    out['current_prepared_subtitle']={'state':row[0],'attempts':row[1],
                                        'reason':detail.get('reason'),'matcher_policy':detail.get('matcher_policy'),
                                        'font_activation_current_request':detail.get('font_activation',{}).get('request_id')==out['native']['playback']['request_id'],
                                        'font_activation_count':len(detail.get('font_activation',{}).get('font_hashes',[])),
                                        'font_inputs_complete':detail.get('font_activation',{}).get('inputs_complete'),
                                        'missing_font_count':detail.get('font_activation',{}).get('missing_count'),
                                        'subtitle_sha256':detail.get('subtitle_sha256')}
                elif action=='preparation':
                    out['preparation_ping']={k:result.get(k) for k in ('ok','state','component')}
                    out['preparation_ping']['current_account']=result.get('account')==host_scope
                else:
                    out['host_status']={k:result.get(k) for k in ('ready','version','native_owner','preparation','shares')}
            except Exception as error:out['host_'+action]={'error':type(error).__name__}
    log=(root/'temp/kodi.log').read_text(errors='replace').splitlines()[-1800:]
    out['bobbi_stages']=[line.split('[bobbi]',1)[1][:180] for line in log if '[bobbi]' in line and not any(word in line.lower() for word in ('http','token','cookie','password','apikey','api_key'))][-40:]
    import re
    out['cinema_stages']=[]
    for line in log:
        marker=re.search(r'\[(?:CINEMA-[A-Z0-9_-]+|BOBBI-(?:TERMINAL|TORRENT)|TORRSERVER[A-Z0-9_-]*)\]',line)
        if marker and not any(word in line.lower() for word in
                ('http','magnet:','token','cookie','password','apikey','api_key','authorization','bearer')):
            out['cinema_stages'].append(line[marker.start():][:360])
    out['cinema_stages']=out['cinema_stages'][-45:]
    out['python_failures']=[line.strip()[:260] for line in log if 'Error Type:' in line or 'Error Contents:' in line and not any(word in line.lower() for word in ('http','token','cookie','password','apikey','api_key'))][-20:]
print(json.dumps(out,ensure_ascii=False))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--mode',choices=('health','metadata'),default='health')
    parser.add_argument('--source-hash', help='Optional exact trial torrent for read-only subtitle preparation status')
    parser.add_argument('--report',type=Path,help='Keep a distinct immutable acceptance checkpoint')
    args=parser.parse_args()
    import re
    if args.source_hash and not re.fullmatch('[0-9a-f]{40}',args.source_hash):
        parser.error('Normalized torrent info hash required')
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('ce_probe_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client,wire=transport.connect()
    try:
        rc,result,diagnostic=wire.readonly(client,('MODE='+repr(args.mode)+'\nSOURCE_HASH='+repr(args.source_hash)+'\n'+REMOTE).encode(),deadline_seconds=30)
    finally:client.close()
    output=args.report or ROOT/'review-evidence'/('ce-runtime-'+args.mode+'.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    if args.report and output.exists():
        raise FileExistsError('Refusing to overwrite an acceptance checkpoint')
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if rc or diagnostic:raise RuntimeError('CE runtime probe failed')


if __name__=='__main__':main()

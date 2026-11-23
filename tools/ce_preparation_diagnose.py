"""Replay a known intent's read/validation stages, never submit cloud work.

Registered TorrServer metadata recovery may reactivate that existing torrent.
No Session, Intake, Ledger, metadata store or cloud mutation is instantiated.
Only public media identity, stage names and traceback locations are returned.
"""
import argparse
from pathlib import Path
import re
import probe_ce_candidate as transport

transport.REMOTE = r'''
import json,pathlib,sqlite3,sys,time,traceback,urllib.request
sys.dont_write_bytecode=True
sys.path[:0]=['/storage/.kodi/addons/script.module.bobbi.core/lib',
 '/storage/.kodi/addons/script.module.bobbi.platform/lib',
 '/storage/.kodi/addons/script.module.requests/lib',
 '/storage/.kodi/addons/script.module.urllib3/lib',
 '/storage/.kodi/addons/script.module.certifi/lib',
 '/storage/.kodi/addons/script.module.idna/lib',
 '/storage/.kodi/addons/script.module.chardet/lib',
 '/storage/.kodi/addons/script.module.charset_normalizer/lib']
root=pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform')
runtime=json.loads((root/'runtime.json').read_text())
def host(action,body):
 q=urllib.request.Request('http://127.0.0.1:%d/control'%runtime['port'],json.dumps(dict(action=action,body=body)).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+runtime['token']})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(q,timeout=3) as f:r=json.load(f)
 if r.get('ok') is not True:raise RuntimeError('HOST_UNAVAILABLE')
 return r['result']
out=dict(timestamp=time.time(),request=RID,cloud_mutations=False,stages=[])
stage='account_context'
sessions=[]
try:
 account=host('account_status',{})
 if account.get('authenticated') is not True:raise RuntimeError('ACCOUNT_REQUIRED')
 state=root.parent/'plugin.video.bobbi'/'preparation'/(account['account_id'][4:]+'-'+str(account['epoch']))
 from bobbi_core.preparation_host import configuration,_private
 config=configuration(root/'preparation.json')
 out['stages'].append(dict(stage=stage,ok=True,epoch=account['epoch']))
 stage='intent_read'
 with sqlite3.connect((state/'resources.sqlite').as_uri()+'?mode=ro',uri=True) as db:
  row=db.execute('SELECT payload,state,result FROM preparation_intents WHERE id=?',(RID,)).fetchone()
 if row is None:raise ValueError('INTENT_ABSENT')
 body=json.loads(row[0])
 from bobbi_core.source_intent import checked_body,verified_intents
 media,selected,source_hash=checked_body(body)
 with sqlite3.connect((state/'resources.sqlite').as_uri()+'?mode=ro',uri=True) as db:
  out['ledger_tasks']=[dict(id=r[0],state=r[1],targets=r[2]) for r in db.execute('SELECT t.id,t.state,COUNT(p.media_id) FROM tasks t LEFT JOIN preparation_targets p ON p.task=t.id WHERE t.source_hash=? GROUP BY t.id,t.state',(source_hash,)).fetchall()]
 out['intent']=dict(state=row[1],media=media,selected=selected)
 out['stages'].append(dict(stage=stage,ok=True))
 stage='provider_identity'
 from bobbi_core.cd2 import CD2
 provider=CD2(_private(config['cd2_token_file']),config['cd2_endpoint']+'/clouddrive.CloudDriveFileSrv/')
 sessions.append(provider.session)
 identity=provider.provider_identity()
 if identity['account_id']!=account['account_id'] or identity['legacy_scope']!=config['account']:raise ValueError('ACCOUNT_MISMATCH')
 out['stages'].append(dict(stage=stage,ok=True))
 stage='metadata'
 import requests
 from bobbi_core.metadata_cache import MetadataCache
 from bobbi_core.torrent_metadata import registered_metadata
 # Bypass __init__: even directory creation is unnecessary for this diagnostic.
 cache=object.__new__(MetadataCache);cache.root=state/'torrent-file-metadata'
 metadata=cache.load(source_hash)
 cached=metadata is not None
 out['metadata_cached']=cached
 session=requests.Session();session.trust_env=False;sessions.append(session)
 out['torrent_responses']=[]
 def torrent_response(response,*args,**kwargs):
  out['torrent_responses'].append(dict(method=response.request.method,status=response.status_code))
 session.hooks['response'].append(torrent_response)
 if config.get('torrserver_pairing_file'):
  from bobbi_platform.pairing import load
  pairing=load(pathlib.Path(config['torrserver_pairing_file']))
  if pairing is None or pairing.endpoint!=config['torrserver_endpoint']:raise ValueError('PAIRING_MISMATCH')
  session.auth=(pairing.username,pairing.password)
 if metadata is None:metadata=registered_metadata(session,config['torrserver_endpoint'],source_hash)
 out['stages'].append(dict(stage=stage,ok=True,cached=cached,file_count=len(metadata['file_stats'])))
 stage='catalog'
 from bobbi_core.catalog_identity import Catalog
 from bobbi_core.project_metadata import tmdb_key
 cat_session=requests.Session();cat_session.trust_env=False;sessions.append(cat_session)
 if config.get('tmdb_proxy'):cat_session.proxies={'https':config['tmdb_proxy']}
 catalog=Catalog(cat_session,tmdb_key() or (_private(config['tmdb_api_key_file']) if config.get('tmdb_api_key_file') else '')).lookup(media)
 out['catalog']={key:catalog[key] for key in ('id','kind','aliases','year','ambiguous','release_seasons') if key in catalog}
 out['stages'].append(dict(stage=stage,ok=True))
 stage='verified_intents'
 from bobbi_core.torrent_selection import select_exact_file
 result=verified_intents(body,metadata,config['account'],config['destination'],select_exact_file,catalog)
 out['stages'].append(dict(stage=stage,ok=True,media_ids=[item[0]['media_id'] for item in result]))
 out['ok']=True
except Exception as error:
 out['ok']=False
 out['stages'].append(dict(stage=stage,ok=False,error=type(error).__name__,frames=[dict(file=pathlib.Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)[-8:]]))
finally:
 for session in sessions:session.close()
print(json.dumps(out))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{32}', args.request) or args.output.exists():
        parser.error('Known request and new output required')
    transport.REMOTE = 'RID=' + repr(args.request) + '\n' + transport.REMOTE
    transport.run(args.transport_source, args.output)

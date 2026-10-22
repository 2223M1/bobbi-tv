"""Read bounded playback diagnostics without exporting URLs or credentials."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def diagnostic_scope(path, request):
    """Accept a full runner artifact, never a launch stub or a product receipt."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2*1024*1024:
        raise ValueError('DIAGNOSTIC_RECEIPT_INVALID')
    with path.open('rb') as source:
        raw = source.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:
        raise ValueError('DIAGNOSTIC_RECEIPT_INVALID')
    value = json.loads(raw)
    rid = lambda item: isinstance(item,str) and re.fullmatch('[0-9a-f]{32}',item) is not None
    sha = lambda item: isinstance(item,str) and re.fullmatch('[0-9a-f]{64}',item) is not None
    native = value.get('native_instance') if isinstance(value,dict) else None
    owner = value.get('owner_context') or {} if isinstance(value,dict) else {}
    identity = value.get('file_identity') if isinstance(value,dict) else None
    binding = re.fullmatch(r'transport:([0-9a-f]{64})\|diagnostic:([0-9a-f]{64})\|transport:([0-9a-f]{64})',
                          identity or '') if isinstance(identity,str) else None
    if not (isinstance(value,dict) and type(value.get('schema')) is int and value['schema']==1
            and value.get('operation')=='start' and rid(value.get('run_id'))
            and rid(request) and value.get('request_id')==request
            and isinstance(native,str) and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',native)
            and type(value.get('tool_revision')) is int and value['tool_revision'] in (4,5,6,7,8)
            and value.get('route') in ('direct','sharestream','sharestream-open-range','sharestream-open-range-microbatch',
                                      'sharestream-open-range-bound-guard','sharestream-block-startup-1m')
            and (value['route']!='sharestream-open-range' or value['tool_revision']>=5)
            and (value['route']!='sharestream-open-range-microbatch' or value['tool_revision']>=6)
            and (value['route']!='sharestream-open-range-bound-guard' or value['tool_revision']>=7)
            and (value['route']!='sharestream-block-startup-1m' or value['tool_revision']>=8)
            and value.get('state') in ('observing','completed','stop_unconfirmed','unconfirmed')
            and value.get('diagnostic_only') is True and value.get('product_proof') is False
            and value.get('retry_allowed') is False and value.get('open_call_returned') is True
            and isinstance(owner,dict) and owner.get('request_id')==request and rid(owner.get('boot_id'))
            and type(owner.get('epoch')) is int and owner['epoch']>=0
            and sha(value.get('url_sha256')) and binding and binding[3]==value['url_sha256']
            and isinstance(value.get('samples'),list) and 1<=len(value['samples'])<=1000):
        raise ValueError('DIAGNOSTIC_RECEIPT_INVALID')
    matched = False
    for sample in value['samples']:
        if not isinstance(sample,dict):
            raise ValueError('DIAGNOSTIC_RECEIPT_INVALID')
        seen = sample.get('native')
        if seen is not None:
            if not (isinstance(seen,dict) and seen.get('request_id')==request
                    and seen.get('native_instance')==native):
                raise ValueError('DIAGNOSTIC_RECEIPT_INVALID')
            matched = True
    if not matched:
        raise ValueError('DIAGNOSTIC_RECEIPT_INVALID')
    modes={'sharestream-open-range':'open_range','sharestream-open-range-microbatch':'open_range_microbatch',
           'sharestream-open-range-bound-guard':'open_range_bound_guard',
           'sharestream-block-startup-1m':'block_startup_1m'}
    expected_mode=modes.get(value['route'])
    if expected_mode is not None and value.get('transport_diagnostic')!={'mode':expected_mode,'seconds':60}:
        raise ValueError('DIAGNOSTIC_RECEIPT_INVALID')
    return dict(run_id=value['run_id'],request_id=request,native_instance=native,
        route=value['route'],tool_revision=value['tool_revision'],transport_sha256=value['url_sha256'],
        request_sha256=hashlib.sha256(request.encode('ascii')).hexdigest()[:16],
        file_identity_sha256=hashlib.sha256(identity.encode('utf-8')).hexdigest(),
        receipt_sha256=hashlib.sha256(raw).hexdigest(),diagnostic_only=True,product_proof=False)


REMOTE = r'''
import hashlib,json,pathlib,re,subprocess,time,sys
sys.dont_write_bytecode=True
sys.path.insert(0,'/storage/.kodi/addons/script.module.bobbi.core/lib')
from bobbi_core.share_stream import observation_fields
root=pathlib.Path('/storage/.kodi')
lines=(root/'temp'/LOG_NAME).read_text(errors='replace').splitlines()
if DIAGNOSTIC is None:
    starts=[i for i,line in enumerate(lines) if REQUEST in line and 'SESSION_ACTIVATED' in line]
    assert starts, 'REQUEST_NOT_IN_CURRENT_LOG'
    lines=lines[max(0,starts[-1]-5):]
markers=('CINEMA-', 'BOBBI-', '[bobbi]', 'VideoPlayer', 'CVideoPlayer',
         'CDVDAudio', 'CDVDClock', 'CAML', 'Font', 'font', 'SUBTITLE', 'subtitle',
         'libass', 'Curl', 'curl', 'ERROR', 'WARNING')
out=[]
observations=[]
def exact_token(line,value):
    return re.search(r'(?<![0-9a-f])'+re.escape(value)+r'(?![0-9a-f])',line) is not None
def selected_observation(value):
    if not isinstance(value,dict):return None
    if value.get('event')!='share_read':return None
    safe=observation_fields(value)
    if DIAGNOSTIC is not None:
        transport=safe.get('transport')
        if transport:
            if transport!=DIAGNOSTIC['transport_sha256']:return None
        elif safe.get('request')!=DIAGNOSTIC['request_sha256']:return None
    return dict(event='share_read',**safe)
def diagnostic_line(line):
    matched=[key for key,value in (('request',REQUEST),('native_instance',DIAGNOSTIC['native_instance']),
                ('transport',DIAGNOSTIC['transport_sha256'])) if exact_token(line,value)]
    if not matched:return None
    # Free text may contain filenames/accounts even after URL substitution.
    # Emit only fixed marker names and scoped IDs, never the raw diagnostic line.
    allowed=('SESSION_ACTIVATED','AV_STARTED','TERMINAL','STOP','NATURAL_EOF','READ_ERROR',
             'VideoPlayer','CVideoPlayer','CAML','ERROR','WARNING')
    return dict(event='scoped_log_marker',request=REQUEST,matched_by=matched,
                markers=[marker for marker in allowed if marker in line])
for line in lines:
    if '[bobbi] {' in line:
        try:
            value=json.loads(line.split('[bobbi] ',1)[1])
            selected=selected_observation(value)
            if selected is not None:observations.append(selected)
        except ValueError:pass
    if DIAGNOSTIC is not None:
        selected=diagnostic_line(line)
        if selected is not None:out.append(selected)
        continue
    if not any(m in line for m in markers): continue
    if any(m in line.lower() for m in ('cookie','token','password','authorization','bearer','api_key','apikey')): continue
    line=re.sub(r'(?:https?://|plugin://|magnet:\?)\S+', '<transport>', line)
    out.append(line[:1000])
journal=subprocess.check_output(['journalctl','-u','kodi.service','--since','-60 minutes','-o','cat','--no-pager'],timeout=8).decode(errors='replace')
for line in journal.splitlines():
    start=line.find('{"event": "share_read"')
    if start<0: start=line.find('{"at":')
    if start<0: continue
    try: value=json.loads(line[start:])
    except ValueError: continue
    selected=selected_observation(value)
    if selected is not None:observations.append(selected)
if DIAGNOSTIC is not None:
    assert out or observations, 'REQUEST_NOT_IN_DIAGNOSTIC_LOG'
def bounded_evidence(value,limit=120*1024):
    # The transport caps UTF-8 stdout at 128 KiB. Preserve early startup and
    # final state instead of retaining only the tail and losing the first stall.
    groups=('lines','share_observations')
    counts={key:len(value[key]) for key in groups}
    value['truncation']={'original_counts':counts,'dropped':{key:0 for key in groups}}
    while True:
        raw=json.dumps(value,ensure_ascii=False)
        if len(raw.encode('utf-8'))<=limit:return raw
        populated=[key for key in groups if value[key]]
        if not populated:raise ValueError('LOG_METADATA_EXCEEDS_BOUND')
        key=max(populated,key=lambda name:len(json.dumps(value[name],ensure_ascii=False).encode('utf-8')))
        value[key].pop(len(value[key])//2)
        value['truncation']['dropped'][key]+=1
crashes=[p.name for p in (root/'temp').glob('kodi_crashlog*')][-8:]
if DIAGNOSTIC is not None:crashes=[hashlib.sha256(name.encode()).hexdigest() for name in crashes]
print(bounded_evidence({'timestamp':time.time(),'request':REQUEST,'source_log':LOG_NAME,'lines':out,
                  'diagnostic_scope':DIAGNOSTIC,
                  'share_observations':observations,
                  'crashes':crashes}))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--brief',action='store_true')
    parser.add_argument('--log',choices=('kodi.log','kodi.old.log'),default='kodi.log')
    parser.add_argument('--retain-raw',type=Path,help='External private evidence directory, never staged to Git')
    parser.add_argument('--diagnostic-receipt',type=Path,
                        help='Explicit full runner receipt; never substitutes a product session marker')
    args=parser.parse_args()
    if len(args.request)!=32 or any(c not in '0123456789abcdef' for c in args.request):
        raise ValueError('request must be a request ID')
    scope=diagnostic_scope(args.diagnostic_receipt,args.request) if args.diagnostic_receipt else None
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('ce_log_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client,wire=transport.connect()
    try:
        if args.retain_raw:
            directory=args.retain_raw.resolve()
            if directory == ROOT or ROOT in directory.parents:
                raise ValueError('Raw logs must stay outside the source repository')
            directory.mkdir(parents=True,exist_ok=True)
            with client.open_sftp() as sftp:
                for name in ('kodi.log','kodi.old.log'):
                    remote='/storage/.kodi/temp/'+name
                    if sftp.stat(remote).st_size>64*1024*1024:
                        raise ValueError('Raw log exceeds acquisition bound')
                    with sftp.open(remote,'rb') as source, (directory/name).open('xb') as target:
                        while True:
                            block=source.read(1024*1024)
                            if not block:break
                            target.write(block)
        rc,result,diagnostic=wire.readonly(client,('REQUEST='+repr(args.request)+'\nLOG_NAME='+repr(args.log)
            +'\nDIAGNOSTIC='+repr(scope)+'\n'+REMOTE).encode(),deadline_seconds=20)
    finally: client.close()
    output=ROOT/'review-evidence'/('ce-playback-log-'+('diagnostic-' if scope else '')+str(time.time_ns())+'.json')
    with output.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    shown = result
    if args.brief:
        shown = dict(request=args.request, lines=len(result.get('lines',[])),
                     share_observations=len(result.get('share_observations',[])),crashes=result.get('crashes'))
    print(json.dumps(dict(evidence=str(output),result=shown),ensure_ascii=False))
    if rc or diagnostic: raise RuntimeError('log probe failed')


if __name__=='__main__': main()

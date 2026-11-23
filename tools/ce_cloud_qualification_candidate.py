"""Read-only exact-task candidate qualification, injected in memory, not deployed.

Existing account/task/map guards are reused. Media keeps ONE 16 MiB/20 s/32-read
RangeBudget and lane, including any ffprobe fallback. The outer 35-second limit
also bounds mapping and postchecks; it is not a second media budget.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import signal
import time

import ce_cloud_ebml_directory as binding

OUTER_SECONDS=35.0


def safe_result(value):
    from bobbi_core.media_probe import BYTE_BUDGET
    method=value.get('method','ffprobe')
    coverage=value.get('coverage','bounded_demux')
    if (method,coverage) not in {('ffprobe','bounded_demux'),('matroska_container_header','prefix_to_first_cluster')}:
        raise ValueError('CANDIDATE_RESULT')
    duration=value.get('duration')
    if (type(duration) not in (int,float) or duration<=0
            or (type(duration) is int and duration.bit_length()>53) or not math.isfinite(duration)):
        raise ValueError('CANDIDATE_RESULT')
    videos=[]
    streams=value.get('streams')
    if type(streams) is not list or not 1<=len(streams)<=128:
        raise ValueError('CANDIDATE_RESULT')
    for row in streams:
        if row.get('codec_type')!='video' or row.get('disposition',{}).get('attached_pic'):continue
        codec=row.get('codec_name')
        if type(codec) is not str or not re.fullmatch('[a-z0-9_]{1,64}',codec):
            raise ValueError('CANDIDATE_RESULT')
        width,height=row.get('width'),row.get('height')
        if type(width) is not int or type(height) is not int or not 1<=width<=16384 or not 1<=height<=16384:
            raise ValueError('CANDIDATE_RESULT')
        videos.append(dict(codec=codec,width=width,height=height))
    if not videos:raise ValueError('CANDIDATE_RESULT')
    for key,maximum in (('read_bytes',BYTE_BUDGET),('requests',32)):
        if type(value.get(key)) is not int or not 0<value[key]<=maximum:raise ValueError('CANDIDATE_RESULT')
    if (type(value.get('seconds')) not in (int,float) or not 0<=value['seconds']<=20.5
            or not math.isfinite(value['seconds']) or type(value.get('probe_sha256')) is not str
            or not re.fullmatch('[0-9a-f]{64}',value['probe_sha256'])):
        raise ValueError('CANDIDATE_RESULT')
    result=dict(method=method,coverage=coverage,duration=duration,videos=videos,
        read_bytes=value['read_bytes'],requests=value['requests'],seconds=value['seconds'],
        probe_sha256=value['probe_sha256'],ordinary_candidate=duration>=300,
        state='READONLY_NOT_PUBLISHED',media_profile=False)
    if method=='matroska_container_header':
        if type(value.get('attachments_bytes')) is not int or value['attachments_bytes']<=0 or type(value.get('chapters_checked')) is not bool:
            raise ValueError('CANDIDATE_RESULT')
        result.update(attachments_bytes=value['attachments_bytes'],chapters_checked=value['chapters_checked'])
    return result


def safe_unsupported(error):
    stages={'prefix','ebml','info','tracks','chapters','seekhead','seek_coverage','required_headers'}
    reasons={'LAYOUT_UNSUPPORTED','PREFIX_SCAN_LIMIT','TRACK_FIELD_UNSUPPORTED','TRACK_FIELD_DUPLICATE',
        'TRACK_FIELD_REQUIRED','BLOCK_ADDITION_UNSUPPORTED','CODEC_UNSUPPORTED','VIDEO_FIELD_UNSUPPORTED','VIDEO_FIELD_DUPLICATE'}
    stage,reason,element=getattr(error,'stage',None),getattr(error,'reason',None),getattr(error,'element_id',None)
    if (type(stage) is not str or type(reason) is not str or stage not in stages or reason not in reasons
            or (element is not None and (type(element) is not int or not 0<element<2**32))):
        return {}
    result=dict(stage=stage,reason=reason,element_id=element)
    encoding=getattr(error,'encoding',None)
    if encoding is not None:
        result['encoding']=safe_encoding(encoding)
    return result


def safe_encoding(value):
    def ids(items):
        return type(items) is list and len(items)<=32 and all(type(n) is int and 0<n<2**32 for n in items)
    if (type(value) is not dict or set(value)!={'complete','track_type','container_ids','encodings'}
            or type(value['complete']) is not bool
            or (value['track_type'] is not None and (type(value['track_type']) is not int or not 1<=value['track_type']<=254))
            or not ids(value['container_ids']) or type(value['encodings']) is not list or len(value['encodings'])>4):
        return {'complete':False}
    for row in value['encodings']:
        if (type(row) is not dict or set(row)!={'order','scope','type','algorithm','settings_bytes',
                'encryption_present','defaulted','child_ids'}
                or any(type(row[key]) is not int or not 0<=row[key]<=255 for key in ('order','scope','type'))
                or (row['algorithm'] is not None and (type(row['algorithm']) is not int or not 0<=row['algorithm']<=255))
                or type(row['settings_bytes']) is not int or not 0<=row['settings_bytes']<=65536
                or type(row['encryption_present']) is not bool or not ids(row['child_ids'])
                or type(row['defaulted']) is not list or len(row['defaulted'])>4
                or any(type(key) is not str or key not in {'order','scope','type','algorithm'} for key in row['defaulted'])
                or len(set(row['defaulted']))!=len(row['defaulted'])):
            return {'complete':False}
    return value


def header_diagnose(binary,size,read,cancelled):
    """Explicit read-only diagnosis: never fallback after unsupported grammar."""
    from bobbi_core import media_probe as media
    from bobbi_core.matroska_qualification import inspect_headers
    if not media._LANE.acquire(blocking=False):raise media.ProbeError('PROBE_ALREADY_RUNNING')
    budget=None
    try:
        budget=media.RangeBudget(size,read,cancelled)
        value=inspect_headers(budget,media.BYTE_BUDGET-media.ANALYSIS_BYTES)
        return dict(value,read_bytes=budget.count,requests=budget.requests,probe_sha256=budget.digest.hexdigest(),
                    seconds=round(time.monotonic()-budget.started,3))
    except Exception as error:
        if budget is not None:
            error.metrics=dict(read_bytes=budget.count,requests=budget.requests,seconds=round(time.monotonic()-budget.started,3))
        raise
    finally:media._LANE.release()


def diagnose(root,expected,account_read=None,provider_factory=None,probe=None,clock=time.monotonic):
    from bobbi_platform.account_manager import validate_snapshot
    from bobbi_core.preparation_host import configuration,_private
    from bobbi_core.cd2 import CD2
    from bobbi_core.cloud_qualifier import CloudQualifier
    from bobbi_core.media_probe import qualification_probe,http_range_reader,ProbeError
    from bobbi_core.matroska_qualification import UnsupportedLayout
    started,deadline=clock(),clock()+OUTER_SECONDS
    out=dict(schema=1,mode='readonly_exact_qualification_candidate',task=expected['task'],
        source_hash=expected['source_hash'],media_id=expected['media_id'],selection_request=expected['selection_request'],
        cloud_mutations=False,ledger_mutations=False,player_commands=False,
        budget=dict(media_bytes=16*1024*1024,media_requests=32,media_seconds=20,outer_seconds=OUTER_SECONDS))
    counters=dict(requests=0,bytes=0,ranges=[])
    provider,stage=None,'account_before'
    def guard():
        if clock()>=deadline:raise binding.DiagnosticError('TIME_BUDGET')
        return True
    def account():
        guard()
        value=account_read() if account_read else binding.runtime_account(root,min(.3,deadline-clock()))
        guard()
        return validate_snapshot(value,authenticated=True)
    try:
        scope=account()
        out['account_before']=True
        root=Path(root)
        config=configuration(root/'preparation.json')
        database=root.parent/'plugin.video.bobbi'/'preparation'/(scope['account_id'][4:]+'-'+str(scope['epoch']))/'resources.sqlite'
        stage='task_before'
        request=binding.load_bound_task(database,expected,config['account'],config['destination'],guard)
        before=binding.digest(request)
        out['selection_tuple_sha256']=binding.digest(request['targets'][0]['_selection']['file'])
        provider=provider_factory() if provider_factory else CD2(_private(config['cd2_token_file']),config['cd2_endpoint']+'/clouddrive.CloudDriveFileSrv/')
        def current_provider():
            guard()
            actual=provider.provider_identity()
            guard()
            if actual!=dict(account_id=scope['account_id'],legacy_scope=config['account']):
                raise binding.DiagnosticError('PROVIDER_ACCOUNT_CHANGED')
        stage='provider_before';current_provider()
        out['provider_before']=True
        stage='exact_mapping_before'
        item=binding.mapped(provider,request,guard)
        qualifier=CloudQualifier(config['ffprobe'],config['cd2_endpoint'],config['download_capability'])
        url=qualifier.download_url(provider,item)
        if account()!=scope:raise binding.DiagnosticError('ACCOUNT_CHANGED')
        out['file_bytes']=item['bytes']
        underlying=http_range_reader(provider.session,url,item['bytes'])
        def read(start,end):
            guard()
            record=dict(start=start,end=end,received=0)
            counters['requests']+=1
            counters['ranges'].append(record)
            for chunk in underlying(start,end):
                counters['bytes']+=len(chunk);record['received']+=len(chunk)
                yield chunk
        stage='qualification_probe'
        result=safe_result((probe or qualification_probe)(config['ffprobe'],item['bytes'],read,lambda:clock()>=deadline))
        guard()
        stage='task_after'
        after=binding.load_bound_task(database,expected,config['account'],config['destination'],guard)
        if binding.digest(after)!=before:raise binding.DiagnosticError('TASK_CHANGED')
        stage='exact_mapping_after'
        mapped=binding.mapped(provider,after,guard)
        if any(mapped[key]!=item[key] for key in ('file_id','path','bytes','task_root_id','torrent_file_id','torrent_path')):
            raise binding.DiagnosticError('EXACT_MAPPING_CHANGED')
        stage='provider_after';current_provider()
        stage='account_after'
        if account()!=scope:raise binding.DiagnosticError('ACCOUNT_CHANGED')
        out.update(ok=True,account_after=True,provider_after=True,task_unchanged=True,exact_mapping_unchanged=True,qualification=result)
    except binding._HardDeadline:
        out.update(ok=False,stage=stage,error='TIME_BUDGET')
    except Exception as error:
        code='READONLY_DIAGNOSTIC_FAILED'
        if isinstance(error,binding.DiagnosticError) and str(error) in binding.SAFE_ERRORS:code=str(error)
        elif isinstance(error,ProbeError) and re.fullmatch('[A-Z][A-Z0-9_]{0,63}',str(error)):code=str(error)
        elif isinstance(error,UnsupportedLayout):
            code='MATROSKA_HEADER_UNSUPPORTED'
            out['header_unsupported']=safe_unsupported(error)
        out.update(ok=False,stage=stage,error=code)
        if isinstance(error,(ProbeError,UnsupportedLayout)):
            metrics=getattr(error,'metrics',{})
            out['probe_metrics']={key:metrics[key] for key in ('read_bytes','requests','seconds')
                                  if type(metrics.get(key)) in (int,float) and 0<=metrics[key]<=16*1024*1024 and math.isfinite(metrics[key])}
    finally:
        if provider is not None:provider.session.close()
        out['media_reads']=counters
        out['elapsed_ms']=max(0,int((clock()-started)*1000))
    return out


def remote_main(expected,source_hashes=None,header_only=False):
    from bobbi_core.media_probe import qualification_probe
    started=time.monotonic()
    def expired(*unused):raise binding._HardDeadline()
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,OUTER_SECONDS)
    def bounded_probe(*args):
        remaining=OUTER_SECONDS-(time.monotonic()-started)
        if remaining<=0:raise binding._HardDeadline()
        signal.setitimer(signal.ITIMER_REAL,min(20,remaining))
        try:return (header_diagnose if header_only else qualification_probe)(*args)
        finally:
            left=OUTER_SECONDS-(time.monotonic()-started)
            signal.setitimer(signal.ITIMER_REAL,max(.001,left))
    try:result=diagnose('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform',expected,probe=bounded_probe)
    except binding._HardDeadline:result=dict(schema=1,ok=False,error='TIME_BUDGET')
    except Exception:result=dict(schema=1,ok=False,error='READONLY_DIAGNOSTIC_FAILED')
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result['total_elapsed_ms']=max(0,int((time.monotonic()-started)*1000))
    result['header_only_diagnose']=header_only
    if source_hashes is not None:result['injected_source_sha256']=source_hashes
    print(json.dumps(result,ensure_ascii=True,allow_nan=False))


def remote_source(expected,header_only=False):
    root=Path(__file__).resolve().parents[1]
    tools=root/'tools'
    core=root/'addons/script.module.bobbi.core/lib/bobbi_core'
    source="import sys,types,hashlib\nsys.dont_write_bytecode=True\n"
    source+="sys.path[:0]="+repr(['/storage/.kodi/addons/'+addon+'/lib' for addon in
        ('script.module.bobbi.core','script.module.bobbi.platform','script.module.requests','script.module.urllib3',
         'script.module.certifi','script.module.idna','script.module.chardet','script.module.charset_normalizer')])+"\nimport bobbi_core\n"
    hashes={}
    for name,path in [('ce_ebml_directory',tools/'ce_ebml_directory.py'),
                      ('ce_cloud_ebml_directory',tools/'ce_cloud_ebml_directory.py'),
                      ('bobbi_core.matroska_qualification',core/'matroska_qualification.py'),
                      ('bobbi_core.media_probe',core/'media_probe.py')]:
        raw=path.read_text(encoding='utf-8')
        hashes[name]=hashlib.sha256(raw.encode('utf-8')).hexdigest()
        source+="m=types.ModuleType("+repr(name)+")\nsys.modules["+repr(name)+"]=m\n"
        source+="exec(compile("+repr(raw)+",'<candidate>','exec'),m.__dict__)\n"
        if name.startswith('bobbi_core.'):
            source+="setattr(bobbi_core,"+repr(name.split('.')[-1])+",m)\n"
    source+="namespace={'__name__':'ce_cloud_qualification_remote'}\n"
    raw=Path(__file__).read_text(encoding='utf-8')
    hashes['ce_cloud_qualification_candidate']=hashlib.sha256(raw.encode('utf-8')).hexdigest()
    source+="exec(compile("+repr(raw)+",'<candidate-runner>','exec'),namespace)\n"
    return source+"namespace['remote_main']("+repr(expected)+","+repr(hashes)+","+repr(header_only)+")\n"


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('task','source-hash','media-id','selection-request'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--header-only-diagnose',action='store_true')
    args=parser.parse_args()
    if args.output.exists():parser.error('Keep prior evidence; select a new output path')
    expected=binding.expectation(args.task,args.source_hash,args.media_id,args.selection_request)
    import probe_ce_candidate as transport
    transport.REMOTE=remote_source(expected,args.header_only_diagnose)
    transport.run(args.transport_source,args.output)

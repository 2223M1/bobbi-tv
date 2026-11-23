"""One exact cloud-task EBML directory diagnostic; no preparation/player writes.

The remote entry point has one 20-second process alarm, including identity checks.
Only a read-only SQLite connection and existing CD2 mapping/download APIs are used.
No URL, account value, cloud path, filename, token, payload, or exception text is
returned. A partial directory never establishes absence of attachments.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import signal
import sqlite3
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from ce_ebml_directory import inspect_directory

SECONDS = 20.0
MEDIA_BYTES = 128 * 1024
MEDIA_REQUESTS = 32
SAFE_ERRORS = frozenset(('TIME_BUDGET', 'ACCOUNT_CHANGED', 'ACCOUNT_REQUIRED',
    'PROVIDER_ACCOUNT_CHANGED', 'TASK_BINDING_INVALID', 'TASK_CHANGED',
    'TARGET_CHANGED', 'EXACT_MAPPING_CHANGED', 'FINISHED_TASK_UNCONFIRMED',
    'MEDIA_REQUEST_BUDGET', 'MEDIA_BYTE_BUDGET', 'EXACT_RANGE_UNAVAILABLE',
    'TRUNCATED_RANGE', 'OVERSIZED_RANGE', 'RUNTIME_ACCOUNT_UNAVAILABLE', 'READONLY_DIAGNOSTIC_FAILED'))


class DiagnosticError(RuntimeError):
    pass


class _HardDeadline(BaseException):
    """Must bypass the parser's intentionally broad callback-error handling."""
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *unused):
        raise DiagnosticError('RUNTIME_ACCOUNT_UNAVAILABLE')


def runtime_account(root, timeout):
    """Existing authenticated runtime contract, without Kodi profile discovery."""
    path=Path(root)/'runtime.json'
    try:
        if (not path.is_file() or any(part.is_symlink() for part in (path,*path.parents))
                or path.stat().st_size>4096 or not 0<timeout<=.3):
            raise ValueError()
        with path.open('rb') as stream:
            raw=stream.read(4097)
        if len(raw)>4096:
            raise ValueError()
        descriptor=json.loads(raw)
        if (type(descriptor) is not dict or set(descriptor)!={'port','token'}
                or type(descriptor['port']) is not int or not 1024<=descriptor['port']<=65535
                or type(descriptor['token']) is not str or not re.fullmatch('[0-9a-f]{64}',descriptor['token'])):
            raise ValueError()
        request=Request('http://127.0.0.1:{}/control'.format(descriptor['port']),
            data=b'{"action":"account_status","body":{}}',
            headers={'Content-Type':'application/json','Authorization':'Bearer '+descriptor['token']})
        with build_opener(ProxyHandler({}),_NoRedirect()).open(request,timeout=timeout) as response:
            if response.status!=200:
                raise ValueError()
            raw=response.read(16385)
        if len(raw)>16384:
            raise ValueError()
        value=json.loads(raw)
        if type(value) is not dict or set(value)!={'ok','result'} or value['ok'] is not True:
            raise ValueError()
        return value['result']
    except (OSError,ValueError,TypeError,KeyError):
        raise DiagnosticError('RUNTIME_ACCOUNT_UNAVAILABLE') from None


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()


def expectation(task, source_hash, media_id, selection_request):
    if (not re.fullmatch('[0-9a-f]{32}', task) or not re.fullmatch('[0-9a-f]{40}', source_hash)
            or not re.fullmatch(r'tmdb:(?:movie:[1-9]\d*|tv:[1-9]\d*:s\d+:e[1-9]\d*)', media_id)
            or not re.fullmatch('[0-9a-f]{32}', selection_request)):
        raise ValueError('Exact task/source/media/selection required')
    return dict(task=task, source_hash=source_hash, media_id=media_id, selection_request=selection_request)


def load_bound_task(path, expected, legacy_account, destination, guard):
    """Use the installed worker's read-only next-target policy; no Ledger init."""
    from bobbi_core.preparation import checked_request
    from bobbi_core import preparation_worker
    guard()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=0)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA busy_timeout=0')
        db.set_progress_handler(lambda: int(guard() is False), 1000)
        db.execute('BEGIN')  # Read snapshot only; no schema/recovery/write owner.
        row = db.execute('SELECT provider,account,destination,source_hash,reserved_bytes,state,payload '
                         'FROM tasks WHERE id=?', (expected['task'],)).fetchone()
        payload = json.loads(row['payload']) if row is not None else None
        choose = getattr(preparation_worker,'next_qualification_target',None)
        if callable(choose):
            selected = choose(db,expected['task'],payload) if row is not None else None
        else:
            if isinstance(payload,dict) and '_qualification_cursor' in payload:
                raise DiagnosticError('TASK_BINDING_INVALID')
            target = db.execute('''SELECT t.payload FROM preparation_targets t
                WHERE t.task=? AND NOT EXISTS(SELECT 1 FROM prepared_bindings b WHERE b.task=t.task
                    AND b.media_id=t.media_id AND b.version_key=t.version_key)
                ORDER BY t.media_id,t.version_key LIMIT 1''', (expected['task'],)).fetchone()
            selected=json.loads(target[0]) if target is not None else None
    guard()
    if (row is None or type(selected) is not dict or row['provider'] != '115' or row['state'] != 'mapping'
            or row['account'] != legacy_account or row['destination'] != destination
            or row['source_hash'] != expected['source_hash'] or selected.get('media_id') != expected['media_id']):
        raise DiagnosticError('TASK_BINDING_INVALID')
    if type(payload) is not dict or type(selected) is not dict or '_selection' not in selected:
        raise DiagnosticError('TASK_BINDING_INVALID')
    checked = checked_request({key:value for key,value in selected.items() if key != '_selection'})
    if (checked['account'] != legacy_account or checked['destination'] != destination
            or checked['source_info_hash'] != expected['source_hash']
            or checked['media_id'] != expected['media_id']
            or checked['bytes_required'] != row['reserved_bytes']):
        raise DiagnosticError('TASK_BINDING_INVALID')
    selection = selected['_selection']
    if (type(selection) is not dict or set(selection) != {'file', 'title', 'release_title', 'anime',
            'request_id', 'metadata_sha256', 'work_identity'}
            or selection['request_id'] != expected['selection_request']
            or type(selection['metadata_sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}', selection['metadata_sha256'])):
        raise DiagnosticError('TASK_BINDING_INVALID')
    observation = payload.get('provider_observation')
    if (type(observation) is not dict or set(observation) != {'account', 'destination',
            'source_info_hash', 'state', 'file_id', 'parent_id'}
            or observation['state'] != 'finished' or observation['account'] != legacy_account
            or observation['destination'] != destination or observation['source_info_hash'] != expected['source_hash']
            or any(type(observation[key]) is not str or not observation[key] for key in ('file_id', 'parent_id'))):
        raise DiagnosticError('FINISHED_TASK_UNCONFIRMED')
    return dict(account=legacy_account, destination=destination, source_hash=row['source_hash'],
                reserved_bytes=row['reserved_bytes'], observation=observation, targets=[selected],
                scheduling_cursor=payload.get('_qualification_cursor'))


def mapped(provider, request, guard):
    """Reuse CloudQualifier's exact completed-task and selected-file mapping."""
    from bobbi_core.cloud_mapping import map_torrent_file
    guard()
    observations = [item for item in provider.offline_tasks(request['destination'])
                    if item['info_hash'] == request['source_hash']]
    guard()
    if len(observations) != 1:
        raise DiagnosticError('FINISHED_TASK_UNCONFIRMED')
    current, old = observations[0], request['observation']
    if current['status'] != 2 or any(current[key] != old[key] for key in ('file_id', 'parent_id')):
        raise DiagnosticError('FINISHED_TASK_UNCONFIRMED')
    item = map_torrent_file(provider, request['destination'], current, request['targets'][0]['_selection']['file'])
    guard()
    return item


def exact_http_reader(session, url, size, deadline, guard, counters, clock=time.monotonic):
    """Closed 206 ranges only; never ask for an open-ended payload or retry."""
    def read(start, end):
        guard()
        if type(start) is not int or type(end) is not int or not 0 <= start <= end < size:
            raise DiagnosticError('EXACT_RANGE_UNAVAILABLE')
        wanted = end-start+1
        if counters['requests'] >= MEDIA_REQUESTS:
            raise DiagnosticError('MEDIA_REQUEST_BUDGET')
        # Reserve one consumer chunk of headroom to reject an overlong body
        # without exceeding this diagnostic's tighter 128 KiB body cap.
        if wanted+min(4096,wanted+1) > MEDIA_BYTES-counters['bytes']:
            raise DiagnosticError('MEDIA_BYTE_BUDGET')
        remaining = deadline-clock()
        if remaining <= 0:
            raise DiagnosticError('TIME_BUDGET')
        record = dict(start=start, end=end, received=0, status=0)
        counters['requests'] += 1
        counters['ranges'].append(record)
        result = bytearray()
        with session.get(url, headers={'Range':'bytes={}-{}'.format(start,end), 'Accept-Encoding':'identity'},
                timeout=(min(3.05,remaining),min(4.0,remaining)), stream=True, allow_redirects=False) as response:
            status = response.status_code
            record['status'] = status if type(status) is int and 100 <= status <= 599 else 0
            if (status != 206 or response.headers.get('Content-Range') != 'bytes {}-{}/{}'.format(start,end,size)
                    or response.headers.get('Content-Encoding','identity') != 'identity'
                    or response.headers.get('Content-Length',str(wanted)) != str(wanted)):
                raise DiagnosticError('EXACT_RANGE_UNAVAILABLE')
            for chunk in response.iter_content(min(4096,wanted+1)):
                guard()
                if not chunk:
                    continue
                counters['bytes'] += len(chunk)
                record['received'] += len(chunk)
                if counters['bytes'] > MEDIA_BYTES:
                    raise DiagnosticError('MEDIA_BYTE_BUDGET')
                if not isinstance(chunk,bytes) or len(result)+len(chunk) > wanted:
                    raise DiagnosticError('OVERSIZED_RANGE')
                result.extend(chunk)
        guard()
        if len(result) != wanted:
            raise DiagnosticError('TRUNCATED_RANGE')
        return bytes(result)
    return read


def diagnose(root, expected, account_read=None, provider_factory=None, clock=time.monotonic):
    from bobbi_platform.account_manager import validate_snapshot
    from bobbi_core.preparation_host import configuration, _private
    from bobbi_core.cloud_qualifier import CloudQualifier
    from bobbi_core.cd2 import CD2
    started, deadline = clock(), clock()+SECONDS
    counters = dict(requests=0,bytes=0,ranges=[])
    out = dict(schema=1, mode='readonly_exact_cloud_ebml', task=expected['task'],
        source_hash=expected['source_hash'], media_id=expected['media_id'],
        selection_request=expected['selection_request'], cloud_mutations=False, ledger_mutations=False,
        player_commands=False, budget=dict(media_bytes=MEDIA_BYTES,media_requests=MEDIA_REQUESTS,seconds=SECONDS))
    stage, provider = 'account_before', None
    def guard():
        if clock() >= deadline:
            raise DiagnosticError('TIME_BUDGET')
        return True
    def account():
        guard()
        value = (account_read() if account_read else runtime_account(root,timeout=min(.3,deadline-clock())))
        guard()
        return validate_snapshot(value, authenticated=True)
    try:
        scope = account()
        out['account_before'] = True
        root = Path(root)
        config = configuration(root/'preparation.json')
        state = root.parent/'plugin.video.bobbi'/'preparation'/(scope['account_id'][4:]+'-'+str(scope['epoch']))
        database = state/'resources.sqlite'
        stage = 'task_before'
        request = load_bound_task(database,expected,config['account'],config['destination'],guard)
        binding = digest(request)
        out['selection_tuple_sha256'] = digest(request['targets'][0]['_selection']['file'])
        stage = 'provider_before'
        provider = (provider_factory() if provider_factory else
            CD2(_private(config['cd2_token_file']),config['cd2_endpoint']+'/clouddrive.CloudDriveFileSrv/'))
        def provider_current():
            guard()
            identity = provider.provider_identity()
            guard()
            if identity != dict(account_id=scope['account_id'],legacy_scope=config['account']):
                raise DiagnosticError('PROVIDER_ACCOUNT_CHANGED')
        provider_current()
        out['provider_before'] = True
        stage = 'exact_mapping_before'
        item = mapped(provider,request,guard)
        qualifier = CloudQualifier(config['ffprobe'],config['cd2_endpoint'],config['download_capability'])
        url = qualifier.download_url(provider,item)  # In-memory existing CD2 route only; never emitted.
        guard()
        if account() != scope:
            raise DiagnosticError('ACCOUNT_CHANGED')
        out['file_bytes'] = item['bytes']
        stage = 'ebml_directory'
        read = exact_http_reader(provider.session,url,item['bytes'],deadline,guard,counters,clock)
        directory = inspect_directory(item['bytes'],read,cancelled=lambda: clock()>=deadline,clock=clock)
        guard()
        stage = 'task_after'
        after = load_bound_task(database,expected,config['account'],config['destination'],guard)
        if digest(after) != binding:
            raise DiagnosticError('TASK_CHANGED')
        stage = 'exact_mapping_after'
        current_item = mapped(provider,after,guard)
        if any(current_item[key] != item[key] for key in ('file_id','path','bytes','task_root_id','torrent_file_id','torrent_path')):
            raise DiagnosticError('EXACT_MAPPING_CHANGED')
        stage = 'provider_after'
        provider_current()
        stage = 'account_after'
        if account() != scope:
            raise DiagnosticError('ACCOUNT_CHANGED')
        out.update(ok=True,account_after=True,provider_after=True,task_unchanged=True,
                   exact_mapping_unchanged=True,directory=directory)
    except _HardDeadline:
        out.update(ok=False,stage=stage,error='TIME_BUDGET')
    except Exception as error:
        code = str(error) if isinstance(error,DiagnosticError) and str(error) in SAFE_ERRORS else 'READONLY_DIAGNOSTIC_FAILED'
        out.update(ok=False,stage=stage,error=code)
    finally:
        if provider is not None:
            provider.session.close()
        out['media_reads'] = counters
        out['elapsed_ms'] = max(0,int((clock()-started)*1000))
    return out


def remote_main(expected):
    # Linux-only maintainer process. The alarm includes mapping and postchecks,
    # and interrupts synchronous socket IO; no daemon/thread is left behind.
    def expired(*unused):
        raise _HardDeadline()
    started=time.monotonic()
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,SECONDS)
    try:
        result = diagnose('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform',expected)
    except _HardDeadline:
        result = dict(schema=1,ok=False,error='TIME_BUDGET')
    except Exception:
        result = dict(schema=1,ok=False,error='READONLY_DIAGNOSTIC_FAILED')
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    result['total_elapsed_ms']=max(0,int((time.monotonic()-started)*1000))
    print(json.dumps(result,ensure_ascii=True,allow_nan=False))


def remote_source(expected):
    here=Path(__file__).resolve().parent
    bootstrap = "import sys,types\nsys.dont_write_bytecode=True\n"
    bootstrap += "sys.path[:0]="+repr(['/storage/.kodi/addons/'+addon+'/lib' for addon in
        ('script.module.bobbi.core','script.module.bobbi.platform','script.module.requests',
         'script.module.urllib3','script.module.certifi','script.module.idna','script.module.chardet',
         'script.module.charset_normalizer')])+"\n"
    bootstrap += "parser=types.ModuleType('ce_ebml_directory')\n"
    bootstrap += "exec(compile("+repr((here/'ce_ebml_directory.py').read_text(encoding='utf-8'))+",'<ebml-directory>','exec'),parser.__dict__)\n"
    bootstrap += "sys.modules['ce_ebml_directory']=parser\nnamespace={'__name__':'ce_cloud_ebml_remote'}\n"
    bootstrap += "exec(compile("+repr(Path(__file__).read_text(encoding='utf-8'))+",'<cloud-ebml-directory>','exec'),namespace)\n"
    return bootstrap+"namespace['remote_main']("+repr(expected)+")\n"


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--task',required=True)
    parser.add_argument('--source-hash',required=True)
    parser.add_argument('--media-id',required=True)
    parser.add_argument('--selection-request',required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Keep previous evidence; select a new output path')
    expected=expectation(args.task,args.source_hash,args.media_id,args.selection_request)
    import probe_ce_candidate as transport
    transport.REMOTE=remote_source(expected)
    transport.run(args.transport_source,args.output)

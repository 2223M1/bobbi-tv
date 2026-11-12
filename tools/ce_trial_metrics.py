"""Read-only CE trial metrics and one path-independent receipt analyzer.

Promotes the former per-run r06 collector/summary logic into the existing trial
CLI. No playback controls, cache eviction, scan admission or third transport.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess

METRIC_SOURCES = (
    'script.module.bobbi.core/lib/bobbi_core/share_stream.py',
    'script.module.bobbi.core/lib/bobbi_core/catalog_query.py',
    'script.module.bobbi.core/lib/bobbi_core/media_library_index.py',
    'script.module.bobbi.platform/lib/bobbi_platform/catalog_service.py',
    'script.module.bobbi.platform/lib/bobbi_platform/scan_sources.py',
    'script.module.bobbi.platform/lib/bobbi_platform/mounted_catalog.py',
    'plugin.video.bobbi/lib/utils/views/personal_catalog.py')

REMOTE = r'''
import hashlib,json,os,pathlib,re,sqlite3,subprocess,time,urllib.request,xml.etree.ElementTree as ET

def digest(path):
    value=hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def proc_fields(raw):
    tail=raw[raw.rindex(')')+2:].split()
    return dict(cpu_ticks=int(tail[11])+int(tail[12]),start_ticks=int(tail[19]))

def process_sample(pid):
    row=proc_fields(pathlib.Path('/proc',pid,'stat').read_text())
    row.update(monotonic=time.monotonic(),utc=time.time())
    allowed={'VmRSS':'rss_kib','VmHWM':'rss_high_water_kib','Threads':'threads'}
    for line in pathlib.Path('/proc',pid,'status').read_text().splitlines():
        key,_,value=line.partition(':')
        if key in allowed:row[allowed[key]]=int(value.strip().split()[0])
    total=list(map(int,pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    row.update(host_total_ticks=sum(total),host_idle_ticks=total[3]+total[4])
    return row

def trace_line(raw):
    if b'share_read' not in raw or len(raw)>65536:return None
    text=raw.decode('utf-8',errors='replace')
    # Kodi prefixes the product JSON. Do not return or save any other log text.
    for offset in [m.start() for m in re.finditer(r'\{',text)][:8]:
        try:value=json.JSONDecoder().raw_decode(text[offset:])[0]
        except ValueError:continue
        if type(value) is dict and value.get('event')=='share_read':
            result={}
            for key in ('http','monotonic_us','len','delivered','suppressed'):
                if type(value.get(key)) is int and 0<=value[key]<2**63:result[key]=value[key]
            for key,size in (('run',16),('file',64)):
                if type(value.get(key)) is str and re.fullmatch('[0-9a-f]{%d}'%size,value[key]):result[key]=value[key]
            if value.get('phase') in ('begin','fetch_end','write_end','end','response','yield','retry','window','upstream_status','gate_wait'):
                result['phase']=value['phase']
            if value.get('method') in ('GET','HEAD'):result['method']=value['method']
            return result
    return None

class TraceTail:
    def __init__(self,path):
        self.path=pathlib.Path(path);self.offset=0;self.inode=None;self.pending=b''
        self.gaps=0;self.missing=0;self.events=[];self.seen=set()
        try:
            st=self.path.stat();self.offset=st.st_size;self.inode=st.st_ino
        except OSError:self.missing+=1
    def poll(self,began,ended,expected_file=None):
        try:
            st=self.path.stat()
            if self.inode is not None and (st.st_ino!=self.inode or st.st_size<self.offset):
                self.gaps+=1;self.offset=0;self.pending=b''
            self.inode=st.st_ino
            if st.st_size-self.offset>1024*1024:
                self.gaps+=1;self.offset=st.st_size;self.pending=b'';return
            with self.path.open('rb') as stream:
                stream.seek(self.offset);raw=stream.read(1024*1024);self.offset=stream.tell()
        except OSError:self.missing+=1;return
        lines=(self.pending+raw).split(b'\n');self.pending=lines.pop()
        if len(self.pending)>65536:self.pending=b'';self.gaps+=1
        for line in lines:
            row=trace_line(line)
            if not row or not began*1e6<=row.get('monotonic_us',-1)<=ended*1e6:continue
            if expected_file and row.get('file')!=expected_file:continue
            key=(row.get('run'),row.get('http'),row.get('phase'),row.get('monotonic_us'))
            if key in self.seen:continue
            if len(self.events)>=20000:self.gaps+=1;return
            self.seen.add(key);self.events.append(row)

def trace_summary(tail,elapsed):
    begins={ (r.get('run'),r.get('http')) for r in tail.events if r.get('phase')=='begin' and r.get('method')=='GET' }
    return dict(status='observed_events_only' if tail.events else 'unavailable',
        sink='existing_kodi_log_only',log_gaps=tail.gaps,missing_polls=tail.missing,
        event_count=len(tail.events),suppressed_events_reported=sum(r.get('suppressed',0) for r in tail.events if r.get('phase')=='end'),
        file_hashes=sorted({r['file'] for r in tail.events if 'file' in r})[:32],
        client_get_begins_observed=len(begins),client_get_begins_observed_per_minute=round(len(begins)*60/elapsed,3) if elapsed else None,
        fetch_end_bytes_observed=sum(r.get('len',0) for r in tail.events if r.get('phase')=='fetch_end'),
        completed_response_delivered_bytes_observed=sum(r.get('delivered',0) for r in tail.events if r.get('phase')=='end'),
        exact_client_range_count=None,upstream_http_requests=None,upstream_bytes=None,
        unavailable_reason='Sparse existing trace may suppress/delay events; successful upstream HTTP requests have no one-event-per-request counter. Fetch-end len is observed validated fetch bytes, not total upstream traffic. Native Pan stream observer is disabled; direct CD2 may bypass ShareStream entirely.',
        qualification='Observed counts are lower bounds in this monotonic window, never exact network/range totals. No packet capture or new telemetry was enabled.')

def binding():
    pids=subprocess.check_output(['pidof','kodi.bin'],timeout=3).decode().split()
    if len(pids)!=1:raise ValueError('KODI_PROCESS_COUNT')
    pid=pids[0];addons=pathlib.Path('/storage/.kodi/addons');components=[]
    for path in sorted(addons.glob('*/addon.xml')):
        if 'bobbi' not in path.parent.name or path.stat().st_size>262144:continue
        raw=path.read_bytes();root=ET.fromstring(raw)
        components.append(dict(id=root.get('id'),version=root.get('version'),manifest_sha256=hashlib.sha256(raw).hexdigest()))
    result=dict(pid=int(pid),native_sha256=digest('/proc/'+pid+'/exe'),components=components,
        installed_source_sha256={relative:digest(addons/relative) for relative in METRIC_SOURCES},
        boot_sha256=digest('/proc/sys/kernel/random/boot_id'),clock_ticks_per_second=os.sysconf('SC_CLK_TCK'),cpu_count=os.cpu_count())
    try:
        state=json.loads(pathlib.Path('/storage/.local/share/bobbi-private-updates/state.json').read_text())
        result['installed_sequence']=state.get('sequence') if type(state.get('sequence')) is int else None
    except (OSError,ValueError):result['installed_sequence']=None
    return pid,result

def rpc(method,params=None):
    request=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
        json.dumps(dict(jsonrpc='2.0',id=902,method=method,params=params or {})).encode(),
        {'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=.8) as stream:
        raw=stream.read(65537)
    if len(raw)>65536:raise ValueError('RPC_LIMIT')
    reply=json.loads(raw)
    if 'error' in reply:raise ValueError('RPC_UNAVAILABLE')
    return reply['result']

def activity():
    value={}
    began=time.monotonic()
    try:
        native=rpc('Player.BobiState').get('playback') or {}
        player={key:native[key] for key in ('request_id','native_instance','phase','reason') if key in native}
        # Compare opaque identities, never return a playback locator.
        players=rpc('Player.GetActivePlayers')
        video=[item['playerid'] for item in players if item.get('type')=='video']
        if len(video)==1:
            raw=rpc('Player.GetItem',dict(playerid=video[0],properties=['file']))['item'].get('file','')
            player['file_sha256']=hashlib.sha256(raw.encode()).hexdigest() if raw else None
            props=rpc('Player.GetProperties',dict(playerid=video[0],properties=['time','totaltime','speed','cachepercentage']))
            player.update({key:props.get(key) for key in ('speed','cachepercentage')})
            for key in ('time','totaltime'):
                t=props.get(key,{})
                player[key+'_seconds']=sum(t.get(part,0)*scale for part,scale in
                    (('hours',3600),('minutes',60),('seconds',1),('milliseconds',.001)))
        value['player']=player
        # A read latency is not physical input-to-photon latency.
        at=time.monotonic()
        gui=rpc('GUI.GetProperties',dict(properties=['currentwindow','currentcontrol']))
        value['gui_query_ms']=(time.monotonic()-at)*1000
        value['window_id']=gui.get('currentwindow',{}).get('id')
        value['control_id']=gui.get('currentcontrol',{}).get('id')
    except (OSError,ValueError,KeyError,TypeError):
        value['player_unavailable']=True
    path=pathlib.Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform/media-index.sqlite3')
    try:
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.05) as db:
            rows=db.execute("SELECT id,source,state FROM scans WHERE state IN ('queued','running') LIMIT 33").fetchall()
            value['scans']=[dict(task_id=row[0],source_id=row[1],state=row[2]) for row in rows[:32]]
            value['scans_truncated']=len(rows)>32
    except (OSError,sqlite3.Error):
        value['scans_unavailable']=True
    try:
        values={}
        for line in pathlib.Path('/proc/net/dev').read_text().splitlines()[2:]:
            name,sep,tail=line.partition(':')
            fields=tail.split()
            if sep and len(fields)>=16 and name.strip()!='lo':
                values[name.strip()]=dict(rx_bytes=int(fields[0]),tx_bytes=int(fields[8]))
        value['network_device_totals']=values
    except (OSError,ValueError):
        value['network_unavailable']=True
    value['activity_observation_seconds']=time.monotonic()-began
    value['activity_monotonic']=time.monotonic()
    return value

def collect():
    pid,installed=binding()  # Hashing overhead precedes the measured interval.
    tail=TraceTail('/storage/.kodi/temp/kodi.log');samples=[];errors=[]
    began=time.monotonic();utc_started=time.time();original_start=None
    for index in range(DURATION+1):
        time.sleep(max(0,began+index-time.monotonic()))
        try:
            row=process_sample(pid)
            if original_start is None:original_start=row['start_ticks']
            if row['start_ticks']!=original_start:raise ValueError('KODI_PROCESS_REPLACED')
            if samples:
                previous=samples[-1];wall=row['monotonic']-previous['monotonic']
                row['process_cpu_percent_one_core']=round(100*(row['cpu_ticks']-previous['cpu_ticks'])/installed['clock_ticks_per_second']/wall,3)
                total=row['host_total_ticks']-previous['host_total_ticks'];idle=row['host_idle_ticks']-previous['host_idle_ticks']
                row['host_cpu_busy_percent']=round(100*(total-idle)/total,3) if total>0 else None
            row.update(activity())
            samples.append(row)
        except (OSError,ValueError,IndexError) as error:
            errors.append(dict(sample=index,error=type(error).__name__,reason='PROCESS_SAMPLE_UNAVAILABLE'));break
        tail.poll(began,time.monotonic(),EXPECTED_FILE)
    ended=time.monotonic();elapsed=ended-began
    return dict(schema=1,mode='readonly',sample_name=SAMPLE_NAME,condition=CONDITION,
        cache_state=CACHE_STATE,repeat=REPEAT,requested_seconds=DURATION,sample_interval_seconds=1,utc_started=utc_started,utc_ended=time.time(),
        monotonic_started=began,monotonic_ended=ended,elapsed_seconds=elapsed,
        source_tree=SOURCE_TREE,source_tree_binding='operator-supplied label; compare installed_source_sha256 against that tree separately',
        installed=installed,samples=samples,errors=errors,trace=trace_summary(tail,elapsed),
        limitations=['Condition/cache labels are operator supplied; scans/player observations independently describe sampled activity.',
        'CPU is proc stat elapsed process time; RSS is proc status VmRSS, not tracemalloc. Sampling overhead is not subtracted.',
        'No exact first-frame, seek or physical input latency. GUI query time measures read RPC only. Network counters are device-wide, not attributed to Kodi or the selected media.'])

print(json.dumps(collect(),separators=(',',':')))
'''


def remote_code(args):
    if not re.fullmatch('[0-9a-f]{40}', args.source_tree or ''):
        raise ValueError('METRICS_SOURCE_TREE_REQUIRED')
    if not args.condition or not args.cache_state:
        raise ValueError('METRICS_CONDITION_AND_CACHE_STATE_REQUIRED')
    fields = dict(SAMPLE_NAME=args.work, CONDITION=args.condition, SOURCE_TREE=args.source_tree,
                  DURATION=args.seconds, EXPECTED_FILE=None, CACHE_STATE=args.cache_state,
                  REPEAT=args.repeat, METRIC_SOURCES=METRIC_SOURCES)
    return '\n'.join(key + '=' + repr(value) for key, value in fields.items()) + '\n' + REMOTE


def distribution(values):
    values = sorted(values)
    return dict(n=len(values), median=statistics.median(values) if values else None,
                p95_nearest_rank=values[math.ceil(.95 * len(values))-1] if values else None,
                minimum=min(values) if values else None, maximum=max(values) if values else None)


def metrics(result, running_only=False):
    rows = result['samples']
    ticks = result['installed']['clock_ticks_per_second']
    cpu, host, query, rss, intervals, tasks = [], [], [], [], [], set()
    first_running = {}
    for row in rows:
        active = {item['task_id'] for item in row.get('scans', []) if item.get('state') == 'running'}
        tasks.update(active)
        for task in active:
            first_running.setdefault(task, row.get('activity_monotonic', row['monotonic']))
        observed_running = any(row['monotonic'] >= first_running[task] for task in active)
        if not running_only or observed_running:
            if 'rss_kib' in row:
                rss.append(row['rss_kib'])
            if 'gui_query_ms' in row:
                query.append(row['gui_query_ms'])
    for left, right in zip(rows, rows[1:]):
        active_left = {item['task_id'] for item in left.get('scans', []) if item.get('state') == 'running'}
        active_right = {item['task_id'] for item in right.get('scans', []) if item.get('state') == 'running'}
        # CPU ticks precede the bounded RPC/SQLite observation. Exclude the
        # first partial interval, rather than attributing its pre-scan time.
        overlap = {task for task in active_left.intersection(active_right)
                   if left['monotonic'] >= first_running[task]
                   and right['monotonic'] <= right.get('activity_monotonic', right['monotonic'])}
        if running_only and not overlap:
            continue
        seconds = right['monotonic'] - left['monotonic']
        if left['start_ticks'] != right['start_ticks'] or seconds <= 0:
            continue
        cpu.append((right['cpu_ticks'] - left['cpu_ticks']) / ticks / seconds * 100)
        total = right['host_total_ticks'] - left['host_total_ticks']
        idle = right['host_idle_ticks'] - left['host_idle_ticks']
        if total > 0:
            host.append(100 * (total-idle) / total)
        intervals.append(seconds)
    network = {}
    if rows and not running_only:
        first, last = rows[0].get('network_device_totals', {}), rows[-1].get('network_device_totals', {})
        for interface in set(first).intersection(last):
            delta = {key: last[interface][key] - first[interface][key] for key in ('rx_bytes','tx_bytes')}
            if all(value >= 0 for value in delta.values()):
                network[interface] = delta
    return dict(sample_points=len(rows), cpu_interval_count=len(intervals), cpu_interval_seconds=sum(intervals),
                process_cpu_percent_one_core=distribution(cpu), host_cpu_busy_percent=distribution(host),
                rss_kib=distribution(rss), gui_read_rpc_ms=distribution(query),
                running_tasks_observed=sorted(tasks), network_device_bytes=network,
                first_frame_ms=None, input_to_photon_ms=None, exact_client_range_count=None,
                upstream_bytes=None)


def source_binding(result, repo):
    """Bind sampled installed bytes to the recorded tree, never today's worktree."""
    tree = result.get('source_tree')
    if not re.fullmatch('[0-9a-f]{40}', tree or ''):
        raise ValueError('METRICS_SOURCE_IDENTITY_INVALID')
    installed = result['installed']
    if set(installed['installed_source_sha256']) != set(METRIC_SOURCES):
        raise ValueError('METRICS_REQUIRED_SOURCE_MISSING')
    checked = {}
    names = dict(installed['installed_source_sha256'])
    names.update({row['id'] + '/addon.xml': row['manifest_sha256'] for row in installed['components']})
    for name, actual in names.items():
        if not re.fullmatch(r'[a-zA-Z0-9_./-]+', name) or '..' in name.split('/') or name.startswith('/'):
            raise ValueError('METRICS_SOURCE_PATH_INVALID')
        expected = subprocess.check_output(['git','-C',str(repo),'show',tree + ':addons/' + name])
        checked[name] = hashlib.sha256(expected).hexdigest() == actual
    return dict(tree=tree, files=checked, matched=bool(checked) and all(checked.values()))


def summarize(paths, repo):
    if not paths or len(paths) > 64:
        raise ValueError('EXPLICIT_RECEIPTS_REQUIRED')
    results, identities = [], set()
    for path in paths:
        raw = Path(path).read_bytes()
        if len(raw) > 4*1024*1024:
            raise ValueError('METRICS_RECEIPT_TOO_LARGE')
        envelope = json.loads(raw)
        result = envelope['result']
        exits = [envelope[key] for key in ('remote_exit_code','transport_exit_code','exit_code','trial_exit_code')
                 if key in envelope]
        if (any(type(code) is not int or code != 0 for code in exits)
                or envelope.get('diagnostic_present') or result.get('errors') or len(result.get('samples', [])) < 2):
            raise ValueError('METRICS_RECEIPT_FAILED')
        bound = source_binding(result, repo)
        if not bound['matched']:
            raise ValueError('METRICS_INSTALLED_SOURCE_MISMATCH')
        installed = result['installed']
        identity = {key: installed[key] for key in
                    ('native_sha256','components','installed_source_sha256','boot_sha256','installed_sequence')}
        identity['source_tree'] = result['source_tree']
        identities.add(json.dumps(identity, sort_keys=True))
        players = [row.get('player', {}) for row in result['samples']]
        results.append(dict(path=str(Path(path).resolve()), sha256=hashlib.sha256(raw).hexdigest(),
            sample=result['sample_name'], condition=result['condition'], cache_state=result['cache_state'],
            repeat=result['repeat'], utc_started=result['utc_started'], utc_ended=result['utc_ended'],
            pid=installed['pid'], process_start_ticks=sorted({row['start_ticks'] for row in result['samples']}),
            source_binding=bound, full_window=metrics(result), observed_running_intervals=metrics(result, True),
            files=sorted({row['file_sha256'] for row in players if row.get('file_sha256')}),
            speeds=sorted({row['speed'] for row in players if type(row.get('speed')) in (int,float)}),
            player_positions_seconds=[row.get('time_seconds') for row in players],
            observed_owner_count=len({(row['request_id'],row['native_instance']) for row in players
                if re.fullmatch('[0-9a-f]{32}', row.get('request_id') or '')
                and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', row.get('native_instance') or '')}),
            player_unavailable_points=sum(bool(row.get('player_unavailable')) for row in result['samples']),
            scans_unavailable_points=sum(bool(row.get('scans_unavailable')) for row in result['samples']),
            trace=result['trace']))
    return dict(schema=1, operation='summarize', state='measured', device_contacted=False,
        samples=results, same_build_and_boot=len(identities)==1,
        identity_scope='Seven required sampled source files plus installed Bobbi component manifests and native/boot identity; use ce_verify_installed for complete installation verification.',
        qualification='Each repeat retained separately. Matching build is necessary, not sufficient for causal comparison: file, position, rate, actual scan overlap and cache conditions must also match.',
        methodology=dict(cpu='Elapsed process ticks / clock ticks / elapsed seconds * 100; one core = 100%.',
            p95='Nearest rank, descriptive only for these short windows.',
            scan='Only consecutive sample intervals with the SAME task positively running at both ends.',
            network='Device-interface byte delta, including other processes; never Kodi/upstream bytes.',
            gui='Read-only GUI RPC latency, not remote key or physical display latency.',
            cold='Operator-declared cache condition; process cold is not disk/CDN cold. No cache eviction performed.'))

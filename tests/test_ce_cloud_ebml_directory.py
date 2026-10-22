"""Offline exact-task/CD2-route diagnostics; never invokes the device transport."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from threading import Event, Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
for addon in ('script.module.bobbi.core','script.module.bobbi.platform'):
    sys.path.insert(0,str(ROOT/'addons'/addon/'lib'))
import ce_cloud_ebml_directory as tool
from bobbi_core import preparation_host

SCOPE=dict(account_id='115:'+'a'*64,epoch=2,authenticated=True)
LEGACY='b'*64
EXPECTED=tool.expectation('c'*32,'d'*40,'tmdb:tv:1429:s1:e1','e'*32)
DATA=bytes.fromhex('1a45dfa38018538067851f43b67580')


def setup_db(path):
    path.parent.mkdir(parents=True)
    target=dict(provider='115',account=LEGACY,destination='/115open/inbox',source_info_hash='d'*40,
        media_id=EXPECTED['media_id'],version_key='f'*64,bytes_required=len(DATA),purpose='current',
        _selection=dict(file=dict(id=0,path='fixture.mkv',length=len(DATA)),title='private title',
            release_title='private release',anime=True,request_id=EXPECTED['selection_request'],
            metadata_sha256='1'*64,work_identity={'provider':'tmdb'}))
    observation=dict(account=LEGACY,destination='/115open/inbox',source_info_hash='d'*40,
        state='finished',file_id='private-file-id',parent_id='private-parent-id')
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE tasks(id TEXT,provider TEXT,account TEXT,destination TEXT,
            source_hash TEXT,reserved_bytes INTEGER,state TEXT,payload TEXT);
            CREATE TABLE preparation_targets(task TEXT,media_id TEXT,version_key TEXT,payload TEXT);
            CREATE TABLE prepared_bindings(task TEXT,media_id TEXT,version_key TEXT);''')
        db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',('c'*32,'115',LEGACY,'/115open/inbox',
            'd'*40,len(DATA),'mapping',json.dumps(dict(provider_observation=observation))))
        db.execute('INSERT INTO preparation_targets VALUES(?,?,?,?)',('c'*32,target['media_id'],target['version_key'],json.dumps(target)))
    return target,observation


class Response:
    def __init__(self,start,end,data=DATA):
        self.status_code=206
        self.headers={'Content-Range':'bytes {}-{}/{}'.format(start,end,len(data)),
                      'Content-Length':str(end-start+1)}
        self.body=data[start:end+1]
    def __enter__(self): return self
    def __exit__(self,*unused): pass
    def iter_content(self,chunk_size):
        for start in range(0,len(self.body),chunk_size):
            yield self.body[start:start+chunk_size]


class Session:
    def __init__(self): self.calls=[];self.closed=False;self.hook=lambda response:None
    def get(self,url,**kwargs):
        assert kwargs['allow_redirects'] is False and kwargs['stream'] is True
        assert kwargs['headers']['Accept-Encoding']=='identity'
        assert 0<kwargs['timeout'][0]<=3.05 and 0<kwargs['timeout'][1]<=4
        self.calls.append((url,deepcopy(kwargs)))
        start,end=map(int,kwargs['headers']['Range'][6:].split('-'))
        response=Response(start,end)
        self.hook(response)
        return response
    def close(self): self.closed=True


class Provider:
    def __init__(self): self.session=Session();self.identities=0;self.maps=0;self.after=lambda:None
    def provider_identity(self):
        self.identities+=1
        return dict(account_id=SCOPE['account_id'],legacy_scope=LEGACY)
    def offline_tasks(self,destination):
        assert destination=='/115open/inbox'
        self.maps+=1
        if self.maps==2:self.after()
        return [dict(info_hash='d'*40,status=2,file_id='private-file-id',parent_id='private-parent-id')]
    def identified_files(self,path):
        if path=='/115open':
            return [dict(path='/115open/inbox',name='inbox',file_id='private-parent-id',directory=True,bytes=0)]
        assert path=='/115open/inbox'
        return [dict(path='/115open/inbox/fixture.mkv',name='fixture.mkv',file_id='private-file-id',directory=False,bytes=len(DATA))]
    def runtime_info(self): return {'version':'0.8.20 fixture'}


@pytest.fixture
def scene(tmp_path,monkeypatch):
    root=tmp_path/'script.module.bobbi.platform'
    root.mkdir()
    path=tmp_path/'plugin.video.bobbi'/'preparation'/('a'*64+'-2')/'resources.sqlite'
    target,observation=setup_db(path)
    config=dict(account=LEGACY,destination='/115open/inbox',ffprobe='/private/binary',
                cd2_endpoint='http://127.0.0.1:19798',download_capability='observed-0.8.20')
    monkeypatch.setattr(preparation_host,'configuration',lambda path:config)
    provider=Provider()
    return SimpleNamespace(root=root,path=path,provider=provider,target=target,observation=observation,config=config)


def run(scene,**kwargs):
    return tool.diagnose(scene.root,EXPECTED,account_read=lambda:deepcopy(SCOPE),
                         provider_factory=lambda:scene.provider,**kwargs)


def test_real_mapping_and_parser_preserve_database_and_emit_no_private_values(scene):
    before=scene.path.read_bytes()
    result=run(scene)
    assert result['ok'] and result['directory']['stop_code']=='first_cluster'
    assert result['task_unchanged'] and result['exact_mapping_unchanged'] and result['account_after']
    assert 0<result['media_reads']['bytes']<=128*1024 and 0<result['media_reads']['requests']<=32
    assert scene.path.read_bytes()==before and scene.provider.session.closed
    output=json.dumps(result)
    for private in ('fixture.mkv','private','115open','http://','Bearer',SCOPE['account_id'],LEGACY):
        assert private not in output
    assert scene.provider.maps==2 and scene.provider.identities==2
    # The read connection is genuinely closed; it cannot hold a reader lock.
    with sqlite3.connect(scene.path,timeout=0) as db: db.execute('BEGIN EXCLUSIVE')


@pytest.mark.parametrize('change',['source','account','destination','state','media','request','observation','bound'])
def test_exact_task_mismatch_rejects_before_media_reads(scene,change):
    with sqlite3.connect(scene.path) as db:
        if change in ('source','account','destination','state'):
            key=dict(source='source_hash',account='account',destination='destination',state='state')[change]
            db.execute('UPDATE tasks SET '+key+'=?',('wrong',))
        elif change=='observation':
            db.execute('UPDATE tasks SET payload=?',(json.dumps(dict(provider_observation=dict(scene.observation,state='downloading'))),))
        elif change=='bound':
            db.execute('INSERT INTO prepared_bindings VALUES(?,?,?)',('c'*32,EXPECTED['media_id'],'f'*64))
        else:
            target=deepcopy(scene.target)
            if change=='media': target['media_id']='tmdb:tv:1429:s1:e2'
            else: target['_selection']['request_id']='2'*32
            db.execute('UPDATE preparation_targets SET payload=?',(json.dumps(target),))
    result=run(scene)
    assert not result['ok'] and result['media_reads']['requests']==0
    assert 'directory' not in result


@pytest.mark.parametrize('change',['account','provider','task','mapping'])
def test_post_read_changes_withhold_directory(scene,change):
    if change=='account':
        scopes=iter([SCOPE,SCOPE,dict(SCOPE,epoch=3)])
        result=tool.diagnose(scene.root,EXPECTED,account_read=lambda:next(scopes),provider_factory=lambda:scene.provider)
    else:
        if change=='provider':
            calls=[0]
            def identity():
                calls[0]+=1
                return dict(account_id=SCOPE['account_id'] if calls[0]==1 else '115:'+'9'*64,legacy_scope=LEGACY)
            scene.provider.provider_identity=identity
        elif change=='task':
            def alter(response):
                with sqlite3.connect(scene.path) as db: db.execute("UPDATE tasks SET state='ready'")
            scene.provider.session.hook=alter
        else:
            scene.provider.after=lambda:setattr(scene.provider,'identified_files',lambda path:[])
        result=run(scene)
    assert not result['ok'] and result['media_reads']['bytes']>0 and 'directory' not in result


@pytest.mark.parametrize('status,header,body,code',[(200,None,None,'EXACT_RANGE_UNAVAILABLE'),
    (302,None,None,'EXACT_RANGE_UNAVAILABLE'),(206,'bytes 0-0/99',None,'EXACT_RANGE_UNAVAILABLE'),
    (206,None,b'','TRUNCATED_RANGE'),(206,None,b'xx','OVERSIZED_RANGE')])
def test_http_closed_ranges_never_follow_or_accept_wrong_file(status,header,body,code):
    session=Session()
    def fault(response):
        response.status_code=status
        if header is not None:response.headers['Content-Range']=header
        if body is not None:response.body=body
    session.hook=fault
    counters=dict(bytes=0,requests=0,ranges=[])
    read=tool.exact_http_reader(session,'private-url',len(DATA),10,lambda:True,counters,clock=lambda:0)
    with pytest.raises(tool.DiagnosticError,match=code):read(0,0)
    assert counters['requests']==1


def test_hard_deadline_bypasses_parser_exception_catch_and_keeps_metrics(scene):
    def expired(response): raise tool._HardDeadline()
    scene.provider.session.hook=expired
    result=run(scene)
    assert not result['ok'] and result['error']=='TIME_BUDGET'
    assert result['media_reads']['requests']==1 and scene.provider.session.closed


def test_remote_bundle_is_self_contained_and_has_only_reviewed_entrypoint():
    raw=tool.remote_source(EXPECTED)
    compile(raw,'remote','exec')
    assert "namespace['remote_main']" in raw and 'sys.dont_write_bytecode=True' in raw
    assert "signal.setitimer(signal.ITIMER_REAL,SECONDS)" in raw
    for prohibited in ('registered_metadata(','.add_offline(','.complete(','.mark_ready(','.publish(','.control('):
        assert prohibited not in Path(tool.__file__).read_text(encoding='utf-8')


def test_default_account_path_real_runtime_dispatch_needs_no_xbmcvfs(scene,monkeypatch):
    from bobbi_platform.runtime import Runtime
    from bobbi_platform.host import Host
    monkeypatch.setitem(sys.modules,'xbmcvfs',None)  # A real missing Kodi module, not a substitute.
    calls=[]
    host=Host.__new__(Host)
    host.stopping=Event()
    host.accounts=SimpleNamespace(snapshot=lambda:calls.append('account_status') or deepcopy(SCOPE))
    runtime=Runtime(host.dispatch,scene.root/'runtime.json')
    runtime.start()
    try:
        before=(scene.root/'runtime.json').read_bytes()
        result=tool.diagnose(scene.root,EXPECTED,provider_factory=lambda:scene.provider)
        assert result['ok'] and result['account_before'] and result['account_after']
        assert calls==['account_status']*3
        assert (scene.root/'runtime.json').read_bytes()==before
        assert json.loads(before)['token'] not in json.dumps(result)
    finally:
        runtime.close()


def test_installed_target_policy_and_cursor_are_part_of_diagnostic_binding(scene):
    target=deepcopy(scene.target)
    target['media_id']='tmdb:tv:1429:s1:e2'
    cursor=[scene.target['media_id'],scene.target['version_key']]
    with sqlite3.connect(scene.path) as db:
        db.execute('INSERT INTO preparation_targets VALUES(?,?,?,?)',('c'*32,target['media_id'],target['version_key'],json.dumps(target)))
        db.execute('UPDATE tasks SET payload=?',(json.dumps(dict(provider_observation=scene.observation,_qualification_cursor=cursor)),))
    expected=dict(EXPECTED,media_id=target['media_id'])
    value=tool.load_bound_task(scene.path,expected,LEGACY,'/115open/inbox',lambda:True)
    assert value['targets'][0]==target and value['scheduling_cursor']==cursor
    with pytest.raises(tool.DiagnosticError):
        tool.load_bound_task(scene.path,EXPECTED,LEGACY,'/115open/inbox',lambda:True)


def test_legacy_worker_without_helper_allows_only_absent_cursor(scene,monkeypatch):
    from bobbi_core import preparation_worker
    monkeypatch.delattr(preparation_worker,'next_qualification_target',raising=False)
    assert tool.load_bound_task(scene.path,EXPECTED,LEGACY,'/115open/inbox',lambda:True)['targets']==[scene.target]
    with sqlite3.connect(scene.path) as db:
        db.execute('UPDATE tasks SET payload=?',(json.dumps(dict(provider_observation=scene.observation,_qualification_cursor=None)),))
    with pytest.raises(tool.DiagnosticError,match='TASK_BINDING_INVALID'):
        tool.load_bound_task(scene.path,EXPECTED,LEGACY,'/115open/inbox',lambda:True)


def test_cursor_rotation_during_read_rejects_even_when_single_target_wraps(scene):
    def rotate(response):
        with sqlite3.connect(scene.path) as db:
            db.execute('UPDATE tasks SET payload=?',(json.dumps(dict(provider_observation=scene.observation,
                _qualification_cursor=[scene.target['media_id'],scene.target['version_key']])),))
    scene.provider.session.hook=rotate
    result=run(scene)
    assert not result['ok'] and result['error']=='TASK_CHANGED' and 'directory' not in result


@pytest.mark.parametrize('descriptor',[
    {}, {'port':True,'token':'a'*64}, {'port':1023,'token':'a'*64},
    {'port':65536,'token':'a'*64}, {'port':12345,'token':'a'*63},
    {'port':12345,'token':'A'*64}, {'port':12345,'token':'a'*64,'url':'https://private'},
    {'port':12345,'token':'x'*5000}])
def test_bad_runtime_descriptor_stops_before_network(tmp_path,monkeypatch,descriptor):
    (tmp_path/'runtime.json').write_text(json.dumps(descriptor),encoding='utf-8')
    monkeypatch.setattr(tool,'build_opener',lambda *a:pytest.fail('invalid descriptor made a request'))
    with pytest.raises(tool.DiagnosticError,match='RUNTIME_ACCOUNT_UNAVAILABLE'):
        tool.runtime_account(tmp_path,.1)


@pytest.mark.parametrize('case',['redirect','oversized','wrong_envelope','rejected'])
def test_real_runtime_http_response_is_bounded_and_never_redirected(tmp_path,case):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*unused): pass
        def do_POST(self):
            requests.append(self.path)
            assert self.path=='/control' and self.headers.get('Authorization')=='Bearer '+'a'*64
            raw=self.rfile.read(int(self.headers['Content-Length']))
            assert json.loads(raw)==dict(action='account_status',body={})
            status=302 if case=='redirect' else 200
            self.send_response(status)
            if case=='redirect':self.send_header('Location','http://127.0.0.1:{}/other'.format(self.server.server_port))
            body=(b'x'*16385 if case=='oversized' else json.dumps(
                dict(ok=False) if case=='rejected' else dict(ok=True,result=SCOPE,extra=True)).encode())
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server=HTTPServer(('127.0.0.1',0),Handler)
    worker=Thread(target=server.serve_forever,kwargs={'poll_interval':.01})
    worker.start()
    (tmp_path/'runtime.json').write_text(json.dumps(dict(port=server.server_port,token='a'*64)),encoding='utf-8')
    try:
        with pytest.raises(tool.DiagnosticError,match='RUNTIME_ACCOUNT_UNAVAILABLE'):
            tool.runtime_account(tmp_path,.3)
        assert requests==['/control']
    finally:
        server.shutdown();server.server_close();worker.join(1)

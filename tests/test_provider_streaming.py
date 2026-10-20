"""Actual portable -> fanout -> Jackett chain, with bounded synthetic IO."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from threading import Event, Lock
import time
from types import ModuleType, SimpleNamespace
from urllib.parse import urlencode

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'addons/plugin.video.bobbi/lib'
CORE = ROOT / 'addons/script.module.bobbi.core/lib/bobbi_core'


@pytest.fixture
def chain(monkeypatch, tmp_path):
    def package(name, path):
        value = ModuleType(name)
        value.__path__ = [str(path)]
        monkeypatch.setitem(sys.modules, name, value)
        return value
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, value)
        spec.loader.exec_module(value)
        parent, _, child = name.rpartition('.')
        if parent in sys.modules:
            monkeypatch.setattr(sys.modules[parent], child, value, raising=False)
        return value
    def stub(name, **values):
        value = ModuleType(name)
        value.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, value)
        return value
    for name in ('lib', 'lib.clients', 'lib.domain', 'lib.utils', 'lib.utils.parsers',
                 'lib.utils.kodi', 'lib.utils.general', 'lib.jacktook'):
        package(name, LIB.joinpath(*name.split('.')[1:]))
    package('bobbi_core', CORE)
    logs = []
    stub('xbmc', getSkinDir=lambda: 'skin.bobbi.cinema', LOGINFO=1, LOGDEBUG=0,
         Monitor=lambda: SimpleNamespace(abortRequested=lambda: False))
    stub('lib.jacktook.utils', kodilog=logs.append)
    stub('lib.utils.kodi.utils', get_setting=lambda key: False, notification=lambda *a: None,
         translation=str)
    stub('lib.utils.kodi.settings', get_jackett_timeout=lambda: 8)
    stub('lib.utils.general.utils', USER_AGENT_HEADER={})
    stub('lib.utils.kodi.logging', summarize_locator_for_log=lambda value: '<locator>')
    for name in ('search_completion', 'child_lifetime', 'subtitle_io', 'runtime_paths', 'search_admission'):
        load('bobbi_core.' + name, CORE / (name + '.py'))
    monkeypatch.setattr(sys.modules['bobbi_core.runtime_paths'], 'ProfilePath', lambda name: tmp_path/name)
    load('lib.domain.torrent', LIB/'domain/torrent.py')
    load('lib.utils.parsers.xmltodict', LIB/'utils/parsers/xmltodict.py')
    load('lib.clients.base', LIB/'clients/base.py')
    for name in ('fanout_diagnostics', 'portable_http', 'jackett_http', 'jackett_fanout', 'jackett'):
        load('lib.clients.'+name, LIB/'clients'/ (name+'.py'))
    return SimpleNamespace(http=sys.modules['lib.clients.portable_http'],
        fanout=sys.modules['lib.clients.jackett_fanout'],
        jackett=sys.modules['lib.clients.jackett'], logs=logs, load=load, stub=stub, package=package)


class Response:
    def __init__(self, raw=b'<rss><channel/></rss>', status=200, gate=None):
        self.raw, self.status_code, self.gate = raw, status, gate
        self.headers = {'Content-Length': str(len(raw))}
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.closed = True
    def iter_content(self, size):
        if self.gate is not None:
            assert self.gate.wait(3), 'bounded fixture release missing'
        yield self.raw
    @property
    def content(self):
        return self._content


def rss(title='Fixture'):
    return ('<rss><channel><item><title>'+title+'</title><link>magnet:?xt=urn:btih:'+
            'a'*40+'</link><size>12345</size></item></channel></rss>').encode()


def client(chain, bodies, get=None):
    def request(url, **options):
        return bodies[url]
    session = SimpleNamespace(headers={}, get=get or request)
    value = chain.jackett.Jackett('http://fixture.invalid', 'fixture-key', '9117', None, session=session)
    value._configured_indexers = ['nyaasi']
    value._movie_urls = lambda *a, **k: list(bodies)
    return value


def search(value, seconds=1, **kwargs):
    return value._search_cinema('Fixture', 'movies', 1, 1, None, None, 2020, '',
                               deadline=time.monotonic()+seconds, **kwargs)


def test_real_ce_counterexample_fast_responses_survive_slowest_deadline(chain):
    # CE evidence: 9 successful HTTP responses were all discarded after the
    # slow sibling consumed the budget; parse_started_ms was null for all 9.
    slow = Event()
    bodies = {'http://fixture.invalid/fast%d'%i: Response(rss('Fast%d'%i)) for i in range(9)}
    bodies['http://fixture.invalid/slow'] = Response(rss('Late'), gate=slow)
    published = []
    try:
        result = search(client(chain, bodies), publish=lambda rows: published.extend(rows))
        assert {row.title for row in result} == {'Fast%d'%i for i in range(9)}
        assert {row.title for row in published} == {row.title for row in result}
        assert result.completion.timed_out == 1 and not result.completion.complete
        snapshot = json.loads(next(row.split('FANOUT-TERMINAL ',1)[1] for row in chain.logs if row.startswith('FANOUT-TERMINAL ')))
        accepted = [r for r in snapshot['records'] if r['transport']=='succeeded']
        assert len(accepted)==9 and all(r['parse']=='succeeded' and r['parse_started_ms'] is not None for r in accepted)
    finally:
        slow.set()


def test_fast_success_400_bad_xml_oversize_and_empty_have_distinct_outcomes(chain):
    bodies = {'http://fixture.invalid/'+name: response for name,response in (
        ('valid', Response(rss())), ('400', Response(b'',400)), ('bad',Response(b'<rss>')),
        ('large',Response(b'x'*(4*1024*1024+1))), ('empty',Response()))}
    result = search(client(chain,bodies), seconds=2)
    assert len(result)==1 and result[0].title=='Fixture'
    assert result.completion.succeeded==2 and result.completion.failed==3
    assert not result.completion.complete
    assert all(r.closed for r in bodies.values())


def test_empty_rss_is_complete_not_failed(chain):
    result = search(client(chain, {'http://fixture.invalid/empty':Response()}))
    assert not result and result.completion.complete


def test_cancellation_does_not_publish_late_response(chain):
    cancelled, released, entered = Event(), Event(), Event()
    def request(url, **options):
        entered.set()
        cancelled.set()
        return Response(rss('Late'),gate=released)
    published=[]
    try:
        result=search(client(chain, {'http://fixture.invalid/late':None},request),
                      cancelled=cancelled.is_set,publish=lambda rows:published.extend(rows))
        assert entered.is_set() and not result and not published and not result.completion.complete
    finally:released.set()


def test_stalled_workers_retain_global_slots_and_bounded_join(chain):
    blocked, all_started = Event(), Event()
    mutex, running = Lock(), [0]
    def request(url, **options):
        with mutex:
            running[0]+=1
            if running[0]==4:all_started.set()
        return Response(b'{}',gate=blocked)
    session=SimpleNamespace(get=request)
    urls=['http://fixture.invalid/'+str(i) for i in range(20)]
    began=time.monotonic()
    try:
        list(chain.http.iter_events(session,urls,began+.15,lambda:False,'json',1024))
        assert all_started.is_set() and time.monotonic()-began < .65
        # A separately loaded interpreter module uses the same OS-held slots.
        other=chain.load('portable_other_fixture',LIB/'clients/portable_http.py')
        events=list(other.iter_events(session,urls,time.monotonic()+.2,lambda:False,'json',1024))
        assert all(row[2]=='global_io_busy' for row in events)
        assert running[0]==4
    finally:
        blocked.set()
        end=time.monotonic()+1
        while any(t.name=='BobiHTTP' and t.is_alive() for t in __import__('threading').enumerate()) and time.monotonic()<end:
            time.sleep(.01)


def test_independent_sessions_preserve_tls_proxy_auth_without_shared_cookies(chain):
    original=requests.Session()
    original.headers['X-Fixture']='yes'
    original.proxies={'https':'http://127.0.0.1:9'}
    original.cookies.set('fixture','value')
    cloned,owned=chain.http._session(original)
    try:
        assert owned and cloned is not original and cloned.cookies is not original.cookies
        assert cloned.headers==original.headers and cloned.proxies==original.proxies
        assert cloned.verify is True and cloned.trust_env==original.trust_env
        cloned.cookies.set('fixture','changed')
        assert original.cookies.get('fixture')=='value'
    finally:cloned.close();original.close()


def test_out_of_order_parse_diagnostics_use_source_ordinal(chain):
    release=Event()
    bodies={'http://fixture.invalid/slow':Response(rss('Slow'),gate=release),
            'http://fixture.invalid/fast':Response(rss('Fast'))}
    def publish(rows):
        if rows[0].title=='Fast':release.set()
    result=search(client(chain,bodies),publish=publish)
    records=json.loads(next(row.split('FANOUT-TERMINAL ',1)[1] for row in chain.logs if row.startswith('FANOUT-TERMINAL ')))['records']
    assert len(result)==2 and all(row['parsed_count']==1 for row in records)
    assert records[1]['parse_started_ms']<records[0]['parse_started_ms']


def test_entity_xml_is_rejected_before_expansion(chain):
    response=Response(b'<!DOCTYPE rss [<!ENTITY x "secret">]><rss><channel><item>&x;</item></channel></rss>')
    result=search(client(chain,{'http://fixture.invalid/xml':response}))
    assert not result and result.completion.failed==1


def test_generator_close_is_bounded_and_workers_release_slots(chain):
    released = Event()
    response = Response(b'{}', gate=released)
    session = SimpleNamespace(get=lambda *a, **k: response)
    events = chain.http.iter_events(session, ['http://fixture.invalid/one'],
        time.monotonic()+2, lambda: False, 'json', 1024)
    assert next(events)[1] == 'started'
    began = time.monotonic()
    try:
        events.close()
        assert time.monotonic()-began < .6
        assert list(events) == []
    finally:
        released.set()
    # Actual OS locks must become available after the delayed response closes.
    end = time.monotonic()+1
    while not response.closed and time.monotonic()<end:
        time.sleep(.01)
    assert response.closed
    probes = []
    try:
        while len(probes)<4 and time.monotonic()<end:
            lease = chain.http._slot()
            if lease is not None:
                probes.append(lease)
            else:
                time.sleep(.01)
        assert len(probes)==4
    finally:
        for lease in probes:
            lease.release()


def test_thread_start_failure_releases_slot_without_joining_unstarted_thread(chain, monkeypatch):
    releases = []
    monkeypatch.setattr(chain.http, '_slot', lambda: SimpleNamespace(release=lambda: releases.append(1)))
    class FailedThread:
        def __init__(self, **options):
            pass
        def start(self):
            raise RuntimeError('fixture-start')
        def join(self, timeout):
            pytest.fail('unstarted thread joined')
    monkeypatch.setattr(chain.http, 'Thread', FailedThread)
    with pytest.raises(RuntimeError, match='fixture-start'):
        list(chain.http.iter_events(None, ['http://fixture.invalid/one'],
             time.monotonic()+1, lambda:False, 'json', 1024))
    assert releases == [1]


def test_session_close_failure_still_returns_response_and_releases_slot(chain, monkeypatch):
    releases = []
    def close():
        releases.append('close')
        raise OSError('untrusted cleanup exception text')
    session = SimpleNamespace(get=lambda *a, **k:Response(b'{}'), close=close)
    monkeypatch.setattr(chain.http, '_session', lambda template:(session, True))
    for _ in range(5):
        events = list(chain.http.iter_events(session, ['http://fixture.invalid/one'],
            time.monotonic()+1, lambda:False, 'json', 1024))
        assert events[-1][1]=='succeeded'
    assert len(releases)==5


def presentation(chain):
    chain.package('lib.cinema', LIB/'cinema')
    chain.load('lib.cinema.frontend_contract', LIB/'cinema/frontend_contract.py')
    return chain.load('lib.cinema.source_presentation', LIB/'cinema/source_presentation.py')


def test_terminal_provider_diagnostics_are_allowlisted_even_for_malformed_values(chain):
    diagnostics = presentation(chain).provider_diagnostics
    secret = 'https://fixture.invalid/?token=do-not-log'
    class HostileKey:
        def __str__(self):
            pytest.fail('arbitrary provider objects must not be stringified')
    actual = diagnostics({
        'Jackett:4':dict(state='PARTIAL',error='queries=2/3 failed=1 '+secret,count=2,
                         completion=dict(planned=3,succeeded=2,failed=1,url=secret)),
        'Juku:2':dict(state='FAILED',error='JukuError',count=0),
        secret:dict(state=secret,error=secret,count=True,completion=secret),
        'qqdocs:3':dict(state=[],error={},count=-1,completion={'failed':True,'planned':65537}),
        HostileKey():None,
    })
    assert actual[0]==dict(provider='jackett',ordinal=4,state='PARTIAL',error='',count=2,
                          completion=dict(planned=3,succeeded=2,failed=1))
    assert actual[1]['error']=='JukuError'
    assert actual[2]==dict(provider='other',ordinal=0,state='UNKNOWN',error='',count=0,completion={})
    assert actual[3]['completion']=={} and actual[3]['state']=='UNKNOWN'
    assert secret not in json.dumps(actual)
    assert len(diagnostics({'Jackett:'+str(i):{} for i in range(60)}))==40


def test_picker_logs_one_terminal_provider_snapshot_not_each_refresh(chain):
    presentation(chain)
    tree = ast.parse((LIB/'gui/source_select.py').read_text(encoding='utf-8'))
    assert any(isinstance(n, ast.Import) and any(v.name=='json' for v in n.names) for n in tree.body)
    method = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
                  and n.name=='_refresh_progressive_sources')
    def log(value, level):
        assert level == 1  # Visible without enabling full Kodi debug logging.
        chain.logs.append(value)
    namespace = dict(json=json,kodilog=log,xbmc=SimpleNamespace(LOGINFO=1))
    exec(compile(ast.Module(body=[method],type_ignores=[]),'source_select.py','exec'),namespace)
    snapshot = dict(revision=1,recommended_key=None,metadata={},entries=[],
                    providers={'Juku:1':dict(state='RUNNING',count=0)})
    session = SimpleNamespace(TERMINAL={'FAILED','COMPLETE','PARTIAL','TIMEOUT','CANCELLED'},
        focus_key=None,status=lambda:snapshot,snapshot=lambda **k:snapshot)
    properties = {}
    window = SimpleNamespace(source_session=session,_source_revision=-1,list_sources=[],
        filter_applied=False,_auto_select_pending=False,_source_interacted=False,last_error='',
        _refresh_frontend_metadata=lambda **k:None,populate_qualities_header=lambda:None,
        populate_sources_list=lambda **kw:None,setProperty=properties.__setitem__)
    refresh = namespace['_refresh_progressive_sources']
    refresh(window)
    assert not chain.logs
    snapshot['revision']=2
    snapshot['providers']['Juku:1'].update(state='FAILED',error='JukuError')
    refresh(window)
    refresh(window,force=True)
    assert len(chain.logs)==1
    assert json.loads(chain.logs[0].split('BOBBI-PROVIDERS ',1)[1])[0]['error']=='JukuError'


def test_streaming_wrapper_retains_same_identity_filter_before_publish():
    tree=ast.parse((LIB/'search.py').read_text(encoding='utf-8'))
    wrapper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_perform_search_with_title_fallback')
    callback=next(n for n in ast.walk(wrapper) if isinstance(n,ast.FunctionDef) and n.name=='publish_checked')
    assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_cinema_filter_catalog_candidates' for n in ast.walk(callback))
    assert '_progressive' in ast.unparse(tree)


@pytest.mark.parametrize('filename,argument,expected',[
    ('frontend_metadata.py','movie:123',{'id':123}),
    ('season_cards.py',123,{'fixture':'latest'})])
def test_real_tmdb_transport_without_close_preserves_success(chain,monkeypatch,filename,argument,expected):
    for name in ('lib.api','lib.api.tmdbv3api','lib.api.tmdbv3api.objs','lib.cinema'):
        chain.package(name,LIB.joinpath(*name.split('.')[1:]))
    chain.load('lib.api.tmdbv3api.as_obj',LIB/'api/tmdbv3api/as_obj.py')
    chain.load('lib.api.tmdbv3api.exceptions',LIB/'api/tmdbv3api/exceptions.py')
    tmdb=chain.load('lib.api.tmdbv3api.tmdb',LIB/'api/tmdbv3api/tmdb.py')
    transport=chain.load('bobbi_core.metadata_transport',CORE/'metadata_transport.py')
    chain.stub('lib.api.tmdbv3api.objs.anime',_am6b_tokyo_today=lambda:None)
    chain.stub('lib.cinema.episode_order',validate_group=lambda *a:None)
    payload={'id':123,'number_of_seasons':2}
    response=requests.Response();response.status_code=200;response._content=json.dumps(payload).encode()
    monkeypatch.setattr(transport,'request',lambda *a,**k:response)
    monkeypatch.setenv('TMDB_API_KEY','test-only-not-real')
    monkeypatch.delenv('TMDB_PROXIES',raising=False)
    assert not hasattr(transport,'close')
    tree=ast.parse((LIB/'clients/tmdb'/filename).read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_fetch')
    namespace=dict(time=time,urlencode=urlencode,_playing=lambda:False,
                   latest_season=lambda *a:{'fixture':'latest'})
    exec(compile(ast.Module(body=[fn],type_ignores=[]),filename,'exec'),namespace)
    result=namespace['_fetch'](argument,time.monotonic()+10) if filename=='season_cards.py' else namespace['_fetch'](argument)
    assert result==({'id':123,'number_of_seasons':2} if filename=='frontend_metadata.py' else expected)

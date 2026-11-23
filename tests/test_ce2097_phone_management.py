"""Real loopback HTTP fixture, never a phone/cloud/device verification claim."""
from copy import deepcopy
from http.client import HTTPConnection
from http.server import HTTPServer
import importlib.util
import json
from pathlib import Path
import sys
from threading import Thread
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addons/plugin.video.bobbi'


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, PLUGIN / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def phone(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'addons/script.module.bobbi.core/lib'))
    module = load('phone_management_fixture', 'lib/services/phone_management.py')
    expected = dict(provider='quark', account_id='quark:'+'a'*64, epoch=1, authenticated=True)
    state = SimpleNamespace(expected=expected, calls=[], result=dict(items=[], next_offset=None), now=100)
    def rpc(action, body, **kw):
        state.calls.append((action, deepcopy(body)))
        if action == 'pan_status':
            return dict(providers=[dict(provider='quark', account=deepcopy(state.expected))])
        return deepcopy(state.result)
    state.module = module
    state.manager = module.PhoneManagement(expected, 'http://127.0.0.1:8081', rpc=rpc, clock=lambda: state.now)
    state.headers = {'Host': '127.0.0.1:8081', 'Origin': 'http://127.0.0.1:8081'}
    return state


def pair(state):
    result, cookie = state.manager.handle('/manage/api/pair', state.headers,
        state.module.encode(dict(code=state.manager.pairing_url.split('#')[1])))
    state.headers.update(Cookie=cookie.split(';')[0], **{'X-Bobbi-CSRF': result['csrf']})
    return result, cookie


def invoke(state, action='catalog_items', params=None):
    return state.manager.handle('/manage/api', state.headers,
        state.module.encode(dict(action=action, params=params or {})))[0]


@pytest.mark.parametrize('mutation', ['origin', 'host', 'cross_site', 'missing_cookie', 'csrf', 'expired', 'revoked', 'account'])
def test_browser_permission_gate_precedes_any_business_call(phone, mutation):
    pair(phone)
    if mutation == 'origin': phone.headers['Origin'] = 'http://evil.invalid'
    elif mutation == 'host': phone.headers['Host'] = 'evil.invalid'
    elif mutation == 'cross_site': phone.headers['Sec-Fetch-Site'] = 'cross-site'
    elif mutation == 'missing_cookie': phone.headers.pop('Cookie')
    elif mutation == 'csrf': phone.headers['X-Bobbi-CSRF'] = 'x'*43
    elif mutation == 'expired': phone.now += 901
    elif mutation == 'revoked': phone.manager.revoke()
    elif mutation == 'account': phone.expected = dict(phone.expected, epoch=2)
    with pytest.raises(phone.module.PhoneError): invoke(phone)
    assert not [action for action, _ in phone.calls if action.startswith('catalog_')]


def test_pairing_is_one_use_cookie_not_javascript_readable_and_refresh_recovers(phone):
    code=phone.manager.pairing_url.split('#')[1]
    result, cookie = pair(phone)
    assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie and 'Path=/manage/api' in cookie
    assert 'session' not in result and code not in json.dumps(result)
    with pytest.raises(phone.module.PhoneError):
        phone.manager.handle('/manage/api/pair', phone.headers, phone.module.encode(dict(code=code)))
    headers={key: value for key,value in phone.headers.items() if key != 'X-Bobbi-CSRF'}
    assert phone.manager.handle('/manage/api/session',headers,b'{}')[0]['csrf']==result['csrf']


@pytest.mark.parametrize('action,params', [
    ('pan_open_stream', {}), ('catalog_items', {'expected': {}}),
    ('catalog_items', {'selected': {}}), ('catalog_items', {'limit': 6}),
    ('catalog_items', {'limit': True}), ('catalog_scan', {'source_id': 'http://secret.invalid'}),
    ('catalog_apply', {'commands': [], 'request_id': 'a'*32})])
def test_closed_rpc_contract_rejects_arbitrary_authority_before_domain_call(phone, action, params):
    pair(phone)
    with pytest.raises(phone.module.PhoneError): invoke(phone,action,params)
    assert not [a for a,_ in phone.calls if a.startswith('catalog_')]


def test_read_only_scope_cannot_mutate(phone):
    phone.manager.scopes=frozenset(('catalog_read',))
    pair(phone)
    with pytest.raises(phone.module.PhoneError,match='ACTION_FORBIDDEN'):
        invoke(phone,'catalog_cancel',{'task_id':'a'*32})


def test_reply_projection_excludes_all_credentials_and_private_file_authority(phone):
    pair(phone)
    phone.result=dict(items=[dict(file=dict(id='a'*64,name='<script>alert(1)</script>',parent='/目录',truncated=False,
        file_id='private-id',credentials='secret'),state='unmatched',revision=0,available=True,
        selected={'cookie':'private'},account_id='private',url='https://secret.invalid')],
        next_offset=None,token='runtime-private',headers={'Authorization':'secret'})
    result=invoke(phone)
    raw=json.dumps(result)
    assert 'secret' not in raw and 'private' not in raw and 'runtime' not in raw
    assert result['items'][0]['available'] is True
    assert result['items'][0]['file']['name']=='<script>alert(1)</script>'
    assert phone.calls[-2][1]['expected']==phone.expected


def test_preview_required_apply_keeps_idempotency_and_partial_results(phone):
    pair(phone)
    command=dict(file_id='a'*64,expected_revision=0,action='ignore',mapping=None)
    params=dict(request_id='b'*32,commands=[command])
    with pytest.raises(phone.module.PhoneError,match='PREVIEW_REQUIRED'):
        invoke(phone,'catalog_apply',params)
    phone.result=dict(items=[dict(status='ready',file=dict(id='a'*64,name='片.mkv'),revision=0,before=None,after=None)])
    invoke(phone,'catalog_preview',dict(commands=[command]))
    phone.result=dict(items=[dict(status='conflict',revision=1)])
    first=invoke(phone,'catalog_apply',params)
    assert first==invoke(phone,'catalog_apply',params)==phone.result
    calls=[body for action,body in phone.calls if action=='catalog_apply']
    assert calls[0]==calls[1] and calls[0]['request_id']=='b'*32


def test_cancel_receipt_is_not_falsified_and_browser_close_does_not_cancel(phone):
    pair(phone)
    phone.result=dict(state='running',cancel_requested=True,task_id='a'*32)
    assert invoke(phone,'catalog_cancel',dict(task_id='a'*32))==phone.result
    phone.manager.revoke()
    assert len([a for a,_ in phone.calls if a=='catalog_cancel'])==1


def test_sources_are_paged_at_browser_boundary(phone):
    pair(phone)
    phone.result=dict(items=[dict(id='%032x'%i,name=str(i)) for i in range(12)])
    result=invoke(phone,'catalog_sources',dict(offset=5,limit=5))
    assert [row['name'] for row in result['items']]==['5','6','7','8','9'] and result['next_offset']==10
    assert [body for action,body in phone.calls if action=='catalog_sources']==[dict(expected=phone.expected)]


def test_history_summary_is_read_only_scoped_and_unknown_duration_stays_unknown(phone):
    phone.manager.scopes=frozenset(('catalog_read',))
    pair(phone)
    phone.result=dict(items=[dict(id='a'*64,name='未看完.mkv',position=42.5,duration=None,updated_at=123,
        completion_reason='stopped',file_ref={'private':'locator'},url='https://signed.invalid/private')],next_offset=5)
    result=invoke(phone,'catalog_history',dict(offset=0,limit=5))
    assert result['items'][0]==dict(id='a'*64,name='未看完.mkv',position=42.5,duration=None,updated_at=123,
                                   completion_reason='stopped')
    assert result['next_offset']==5
    assert [body for action,body in phone.calls if action=='catalog_history']==[
        dict(expected=phone.expected,offset=0,limit=5)]
    with pytest.raises(phone.module.PhoneError):
        invoke(phone,'catalog_history',dict(file_id='a'*64,play=True))


@pytest.fixture
def http_server(phone, monkeypatch):
    # Preserve existing Stremio helpers, substituting only unrelated Kodi/cache
    # dependencies. Requests below execute the production HTTP handler.
    def module(name, **values):
        value=ModuleType(name)
        value.__dict__.update(values)
        monkeypatch.setitem(sys.modules,name,value)
        return value
    for name in ('lib','lib.services','lib.api','lib.api.stremio','lib.clients','lib.clients.stremio',
                 'lib.db','lib.utils','lib.utils.general','lib.utils.kodi'):
        package=module(name);package.__path__=[]
    module('lib.api.stremio.addon_manager',build_addon_instance_key=lambda value:'fixture')
    module('lib.clients.stremio.constants',STREMIO_ADDONS_CATALOGS_KEY='catalog',STREMIO_ADDONS_KEY='stream',
        STREMIO_TV_ADDONS_KEY='tv',STREMIO_USER_ADDONS='addons',decode_selected_ids=lambda value:[],encode_selected_ids=lambda value:value)
    module('lib.clients.stremio.protocol',MAX_RESOURCE_JSON_BYTES=1024,is_safe_http_url=lambda value:False,
        request_with_safe_redirects=lambda *args,**kw:None)
    module('lib.db.cached',cache=SimpleNamespace(get=lambda key:None,set=lambda *args:None))
    module('lib.utils.general.utils',USER_AGENT_HEADER={})
    module('lib.utils.kodi.utils',kodilog=lambda *args:None)
    monkeypatch.setitem(sys.modules,'lib.services.phone_management',phone.module)
    web=load('webserver_phone_fixture','lib/services/webserver.py')
    server=HTTPServer(('127.0.0.1',0),web.StremioRequestHandler)
    phone.manager.origin='http://127.0.0.1:%d'%server.server_port
    phone.manager.host='127.0.0.1:%d'%server.server_port
    server.phone_management=phone.manager
    thread=Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    def request(path,body=None,headers=None,method='POST'):
        connection=HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        try:
            connection.request(method,path,body=phone.module.encode(body or {}),headers=dict(
                {'Content-Type':'application/json','Origin':phone.manager.origin},**(headers or {})))
            reply=connection.getresponse()
            return reply.status,dict(reply.getheaders()),reply.read()
        finally: connection.close()
    yield request,phone
    phone.manager.revoke();server.shutdown();server.server_close();thread.join(1)


def test_actual_http_pair_static_api_cors_and_csrf(http_server):
    request,phone=http_server
    status,headers,html=request('/manage',method='GET')
    assert status==200 and b'innerHTML' not in html
    assert 'Access-Control-Allow-Origin' not in headers and headers['Cache-Control']=='no-store'
    code=phone.manager.pairing_url.split('#')[1]
    assert request('/manage/api/pair',dict(code=code),{'Origin':'http://evil.invalid'})[0]==403
    status,headers,raw=request('/manage/api/pair',dict(code=code))
    assert status==200
    cookie=headers['Set-Cookie'].split(';')[0];csrf=json.loads(raw)['csrf']
    assert request('/manage/api',dict(action='catalog_items',params={}),{'Cookie':cookie})[0]==403
    status,headers,raw=request('/manage/api',dict(action='catalog_items',params={}),{'Cookie':cookie,'X-Bobbi-CSRF':csrf})
    assert status==200 and json.loads(raw)==dict(items=[],next_offset=None)
    assert 'Access-Control-Allow-Origin' not in headers
    assert request('/api/addons',method='GET')[0]==404  # No unrelated legacy authority in this optional session.
    assert request('/manage/api',method='OPTIONS')[0]==403
    phone.manager.revoke()
    assert request('/manage/api',dict(action='catalog_items',params={}),{'Cookie':cookie,'X-Bobbi-CSRF':csrf})[0]==401


def test_page_has_no_html_interpolation_or_persistent_tokens():
    javascript=(PLUGIN/'resources/web/manage.js').read_text(encoding='utf-8')
    assert 'innerHTML' not in javascript and 'localStorage' not in javascript and 'sessionStorage' not in javascript
    assert 'textContent' in javascript and "history.replaceState(null,'',location.pathname)" in javascript
    assert 'request_id:requestId' in javascript and 'expected_revision:item.revision' in javascript
    assert 'pan_open_stream' not in javascript and 'PlayMedia' not in javascript

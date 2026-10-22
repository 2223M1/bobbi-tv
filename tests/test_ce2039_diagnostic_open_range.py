"""Diagnostic-only open Range: local HTTP and bounded virtual byte fixtures."""
from copy import deepcopy
from http.client import IncompleteRead
from threading import Event, Thread
from types import SimpleNamespace
import time

import pytest

from test_ce_progressive_http import pipeline, stream, wait_end, PAYLOAD
from test_ce2035_progressive_initial_range import large_payload, small_downstream_socket, wait_for

DIAGNOSTIC = {'mode': 'open_range', 'seconds': 60}


@pytest.mark.parametrize('invalid', [None, True, {}, {'mode':'progressive','seconds':60},
    {'mode':'open_range','seconds':True}, {'mode':'open_range','seconds':1.0},
    {'mode':'open_range','seconds':0}, {'mode':'open_range','seconds':61},
    {'mode':'open_range','seconds':60,'extra':True}])
def test_diagnostic_is_strict_and_never_a_general_preference(invalid):
    with pytest.raises(ValueError,match='SHARE_DIAGNOSTIC_INVALID'):stream.checked_diagnostic(invalid)


@pytest.mark.parametrize('progressive',[False,True])
def test_registration_scopes_mode_and_does_not_extend_deadline(progressive):
    with pipeline(progressive,diagnostic=DIAGNOSTIC) as (service,_,_,_,_,_):
        entry=next(iter(service.records.values()));deadline=entry.diagnostic_deadline
        first=service.register_diagnostic(entry.body,None,DIAGNOSTIC)
        second=service.register_diagnostic(entry.body,None,DIAGNOSTIC)
        assert first==second and entry.diagnostic_deadline==deadline
        assert service.progressive is progressive and service.segment_bytes==stream.MAX_SEGMENT_BYTES
        with pytest.raises(ValueError,match='SHARE_REQUEST_RETARGETED'):service.register(entry.body)
        with pytest.raises(ValueError,match='SHARE_REQUEST_RETARGETED'):
            service.register_diagnostic(entry.body,None,dict(DIAGNOSTIC,seconds=59))
        ordinary=dict(entry.body,request_id='b'*32)
        service.register(ordinary)
        peer=service.records['b'*32]
        assert peer.diagnostic is None and peer.io_lock is entry.io_lock
        with pytest.raises(ValueError,match='SHARE_REQUEST_RETARGETED'):
            service.register_diagnostic(ordinary,None,DIAGNOSTIC)
        with pytest.raises(ValueError,match='SHARE_FIELDS'):
            service.register(dict(ordinary,diagnostic=DIAGNOSTIC))


@pytest.mark.parametrize('value,expected',[(None,'bytes=0-'),('bytes=117-','bytes=117-'),
    ('bytes=117-524404','bytes=117-524404')])
def test_exact_open_or_finite_wire_range_with_default_block_unchanged(value,expected):
    headers=[]
    with pipeline(False,diagnostic=DIAGNOSTIC,range_headers=headers,
                  queue_bytes=stream.PROGRESSIVE_QUEUE_BYTES) as (service,connect,calls,events,_,peak):
        connection,response=connect(value)
        try:
            start,end,_=stream.byte_range(value,len(PAYLOAD))
            assert response.read()==PAYLOAD[start:end+1]
        finally:response.close();connection.close()
        wait_end(events)
        assert headers[0]==expected and calls[0]==(start,end)
        assert service.progressive is False and peak[0]==1
        assert events[-1]['timing_scope']=='diagnostic_cumulative'
        assert all(type(events[-1][key]) is int and events[-1][key]>=0 for key in
            ('grant_us','connect_us','read_wait_us','queue_room_us','queue_put_us','queue_get_us','socket_send_us'))


def test_over_sixty_four_mib_does_not_force_a_cap_reconnect(large_payload):
    headers=[]
    with pipeline(False,payload=large_payload,diagnostic=DIAGNOSTIC,range_headers=headers,
                  queue_bytes=stream.PROGRESSIVE_QUEUE_BYTES) as (_,connect,calls,events,_,peak):
        connection,response=connect()
        try:assert response.read()==large_payload
        finally:response.close();connection.close()
        wait_end(events)
        assert headers[0]=='bytes=0-' and calls[0]==(0,len(large_payload)-1)
        assert all(end==len(large_payload)-1 for start,end in calls)
        assert any(row['phase']=='window' and row['retry_window']==1 for row in events)
        assert events[-1]['outcome']=='complete' and peak[0]==1
        assert len(events)<=stream.OBSERVATION_LIMIT


@pytest.mark.parametrize('mode',['short_once','expired','chunked'])
def test_diagnostic_keeps_exact_suffix_and_signature_renewal(mode):
    headers=[]
    with pipeline(mode=mode,diagnostic=DIAGNOSTIC,range_headers=headers,
                  queue_bytes=stream.PROGRESSIVE_QUEUE_BYTES) as (_,connect,calls,events,resolves,_):
        connection,response=connect('bytes=117-')
        try:assert response.read()==PAYLOAD[117:]
        finally:response.close();connection.close()
        wait_end(events)
        if mode=='short_once':assert calls[1][0]==117+128*1024
        if mode=='expired':assert len(resolves)==2
        assert all(header.endswith('-') for header in headers)
        assert events[-1]['outcome']=='complete'


@pytest.mark.parametrize('mode',['wrong_range','wrong_length','encoding','overflow'])
def test_untrusted_response_never_looks_complete(mode):
    with pipeline(mode=mode,diagnostic=DIAGNOSTIC) as (_,connect,_,events,_,_):
        connection,response=connect('bytes=17-99999')
        try:
            if mode=='overflow':
                with pytest.raises(IncompleteRead):response.read()
            else:assert response.status==503
        finally:response.close();connection.close()
        wait_end(events)
        assert events[-1]['outcome']=='failed' and events[-1]['delivered']<99983


def test_queue_pressure_yields_and_resumes_only_accepted_suffix(monkeypatch):
    small_downstream_socket(monkeypatch)
    with pipeline(diagnostic=DIAGNOSTIC,queue_bytes=64*1024) as (_,connect,calls,events,_,peak):
        first,response=connect();second=other=None
        try:
            wait_for(lambda:any(row['phase']=='yield' for row in events))
            second,other=connect('bytes=3000000-3032767')
            assert other.read()==PAYLOAD[3000000:3032768]
            assert response.read()==PAYLOAD
        finally:
            response.close();first.close()
            if other:other.close()
            if second:second.close()
        wait_end(events,2)
        row=next(row for row in events if row['phase']=='yield' and row['start']==0)
        assert calls[1][0] in (row['offset']+row['bytes'],3000000)
        assert any(start==row['offset']+row['bytes'] for start,end in calls[1:])
        assert peak[0]==1 and all(row.get('queue_peak',0)<=64*1024 for row in events)


def test_expiry_is_binding_local_and_late_grant_cannot_publish(monkeypatch):
    now=[100.]
    monkeypatch.setattr(stream.time,'monotonic',lambda:now[0])
    body=dict(request_id='a'*32,locator='x',guid='g',title='f',size=1)
    def slow_grant(body):
        now[0]=102.
        return 'http://example.test/file|User-Agent=test'
    binding=stream.Binding(body,slow_grant,lambda _:True,diagnostic={'mode':'open_range','seconds':1})
    ordinary=stream.Binding(body,lambda _:None,lambda _:True)
    with pytest.raises(OSError,match='SHARE_STOPPED'):binding.grant()
    assert binding.address is None and binding.cancelled() and not ordinary.cancelled()


def reader_fixture(monkeypatch, failures_at, window=64*1024):
    """Virtual bytes with actual read_block/retry transitions; no sleeps or CDN."""
    monkeypatch.setattr(stream,'MAX_SEGMENT_BYTES',window)
    owner=SimpleNamespace(stopping=SimpleNamespace(wait=lambda _:False),report=lambda _:None)
    handler=stream.Handler.__new__(stream.Handler)
    handler.server=SimpleNamespace(owner=owner);handler.cancelled=lambda:False
    handler.observe=lambda *args,**kwargs:None;handler.diagnostic_timings=None
    entry=SimpleNamespace(body={'size':window*3},grant=lambda **kwargs:'https://safe.test/file|User-Agent=test',
        io_lock=SimpleNamespace(contended=lambda:False,recently_yielded=lambda:False,note_yield=lambda:None))
    events=list(failures_at);calls=[];accepted=[]
    class Response:
        def __init__(self,offset,end):
            self.status_code=206;self.offset=offset;self.end=end
            self.headers={'Content-Range':f'bytes {offset}-{end}/{entry.body["size"]}',
                          'Content-Length':str(end-offset+1)}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,chunk):
            offset=self.offset
            while offset<=self.end:
                if events and offset==events[0]:events.pop(0);raise OSError('temporary')
                next_stop=min([self.end+1,offset+4096]+([events[0]] if events else []))
                yield b'x'*(next_stop-offset);offset=next_stop
    class Session:
        def get(self,url,**kwargs):
            first,last=kwargs['headers']['Range'][6:].split('-')
            offset,end=int(first),int(last) if last else entry.body['size']-1
            calls.append((offset,end));return Response(offset,end)
    consume=lambda chunk:accepted.append(len(chunk)) or True
    return handler,Session(),entry,consume,calls,accepted


def test_errors_reset_only_after_accepted_sixty_four_mib_window(monkeypatch):
    width=64*1024
    handler,session,entry,consume,calls,accepted=reader_fixture(monkeypatch,
        [4096]*3+[width+4096]*3+[2*width+4096]*3)
    count,_=handler.read_block(session,entry,0,entry.body['size']-1,0,consume,
                              retry_window=stream.RetryWindow(0))
    assert count==sum(accepted)==entry.body['size'] and len(calls)==10


def test_fourth_failure_in_same_window_is_terminal_even_after_forward_progress(monkeypatch):
    handler,session,entry,consume,calls,accepted=reader_fixture(monkeypatch,[4096,8192,12288,16384])
    with pytest.raises(OSError,match='SHARE_READ_UNAVAILABLE'):
        handler.read_block(session,entry,0,entry.body['size']-1,0,consume,retry_window=stream.RetryWindow(0))
    assert len(calls)==4 and sum(accepted)==16384


def test_gate_yield_does_not_reset_error_window(monkeypatch):
    handler,session,entry,consume,calls,accepted=reader_fixture(monkeypatch,[4096]*3+[12288])
    entry.io_lock.contended=lambda:sum(accepted)>=8192
    budget=stream.RetryWindow(0)
    count,_=handler.read_block(session,entry,0,entry.body['size']-1,0,consume,retry_window=budget)
    assert count==8192 and budget.failures==3
    entry.io_lock.contended=lambda:False
    with pytest.raises(OSError,match='SHARE_READ_UNAVAILABLE'):
        handler.read_block(session,entry,count,entry.body['size']-1,0,consume,retry_window=budget)
    assert budget.failures==4 and sum(accepted)==12288


def test_expiry_cancels_partial_http_and_returns_its_producer_slot():
    with pipeline(mode='trickle',delay=.01,diagnostic={'mode':'open_range','seconds':1}) as (
            service,connect,calls,events,_,_):
        connection,response=connect('bytes=0-9999')
        try:
            assert response.read(1)==PAYLOAD[:1]
            with pytest.raises((IncompleteRead,ConnectionError,OSError)):response.read()
        finally:response.close();connection.close()
        wait_end(events)
        assert events[-1]['outcome']!='complete' and events[-1]['cancel']=='diagnostic_expired'
        assert not service.producers
        for _ in range(6):assert service.producer_slots.acquire(blocking=False)
        for _ in range(6):service.producer_slots.release()
        second,late=connect('bytes=0-1')
        try:assert late.status==404
        finally:late.close();second.close()


def test_host_separate_registration_keeps_normal_endpoint_and_account_gate(tmp_path):
    from bobbi_platform.host import Host
    from bobbi_platform.account_manager import AccountError
    from test_accounts import credential
    def factory(accounts):
        return stream.ShareStream(lambda _:None,lambda *args:None,lambda _:True,
                                  account=accounts,observer=lambda _:None)
    host=Host(tmp_path,stream_factory=factory);host.start()
    try:
        account=host.accounts.install(credential(),host.accounts.snapshot())
        body=dict(request_id='a'*32,locator='am6bqqdocs://A1/123',guid='qqdocs:test',
            title='Fixture.mkv',size=1000,media='movie:1:0:0',account=account)
        normal=host.dispatch('share_open',body)
        service=host.streams
        diagnostic=dict(body,request_id='b'*32,diagnostic=DIAGNOSTIC)
        ready=host.dispatch('share_open_diagnostic',diagnostic)
        assert ready['state']=='ready' and host.streams is service and not service.progressive
        assert service.records['a'*32].diagnostic is None
        assert service.records['a'*32].io_lock is service.records['b'*32].io_lock
        assert not (tmp_path/'share-transport.json').exists()
        with pytest.raises(ValueError):host.dispatch('share_open',diagnostic)
        with pytest.raises(ValueError):host.dispatch('share_open_diagnostic',body)
        host.accounts.logout(account)
        with pytest.raises(AccountError):host.dispatch('share_open_diagnostic',dict(diagnostic,request_id='c'*32))
    finally:host.close()


def test_expired_before_headers_closes_unanswered_http_after_producer_drains():
    entered,release,client_done,closed=Event(),Event(),Event(),Event()
    results=[]
    with pipeline(diagnostic={'mode':'open_range','seconds':1},header_pause=(entered,release)) as (
            service,connect,calls,events,_,_):
        def client():
            connection=response=None
            try:
                connection,response=connect('bytes=0-1')
                results.append(response.read())
            except (ConnectionError,OSError):
                pass
            finally:
                if response:response.close()
                if connection:connection.close()
                client_done.set()
        def close():
            service.close();closed.set()
        consumer=Thread(target=client,daemon=True);closer=Thread(target=close,daemon=True)
        consumer.start()
        try:
            assert entered.wait(2)
            wait_for(next(iter(service.records.values())).cancelled)
            assert service.producers
            closer.start()
            assert not closed.wait(.1)  # A late producer still owns the service.
            release.set()
            assert client_done.wait(2) and closed.wait(2)
            assert not results and not service.producers
            assert all(row.get('delivered',0)==0 for row in events)
            assert not any(row.get('outcome')=='complete' for row in events)
        finally:
            release.set();consumer.join(2)
            if closer.ident is not None:closer.join(2)

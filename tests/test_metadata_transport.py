import importlib.util
from pathlib import Path
import socket
import ssl
import struct
import sys
from types import ModuleType
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('metadata_transport', ROOT / 'addons/script.module.bobbi.core/lib/bobbi_core/metadata_transport.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


def test_request_budget_is_nested_cancelable_and_thread_local():
    from concurrent.futures import ThreadPoolExecutor
    cancelled = [False]
    assert not transport.request_silent()
    with transport.request_budget(time.monotonic() + 2, lambda: cancelled[0], quiet=True):
        assert 0 < transport.request_remaining(10) <= 2
        with transport.request_budget(time.monotonic() + 20):
            assert transport.request_remaining(10) <= 2 and transport.request_silent()
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(transport.request_remaining, 10).result() == 10
        cancelled[0] = True
        assert transport.request_remaining(10) == 0
    assert transport.request_remaining(10) == 10 and not transport.request_silent()


def test_verified_doh_route_reuse_avoids_repeated_system_connect_penalty(monkeypatch):
    calls=[]
    monkeypatch.setattr(transport,'_DNS_CACHE',{})
    monkeypatch.setattr(transport,'_SUCCESS_ROUTE',{})
    def connect(host,ip=None,timeout=5):
        calls.append(ip)
        if ip is None:raise OSError('system route unavailable')
        return Connection()
    # Connection construction itself is normally nonblocking; make failure
    # occur in request(), as the real HTTPS.connect does.
    class Failed(Connection):
        def request(self,*a,**k):raise OSError('system route unavailable')
    def create(host,ip=None,timeout=5):
        calls.append(ip)
        return Failed() if ip is None else Connection()
    def resolver(host,*a):
        transport._DNS_CACHE[host]=(time.monotonic()+60,('1.1.1.1',))
        return ['1.1.1.1']
    transport.fetch('https://image.tmdb.org/t/p/w342/test.jpg',time.monotonic()+2,connect=create,resolver=resolver)
    assert calls==[None,'1.1.1.1']
    calls.clear()
    transport.fetch('https://image.tmdb.org/t/p/w342/test.jpg',time.monotonic()+2,connect=create,resolver=resolver)
    assert calls==['1.1.1.1']


@pytest.mark.parametrize('failure', ['TLS', 'SHORT_READ'])
def test_failed_preferred_address_is_not_pinned_for_following_images(monkeypatch,failure):
    calls=[]
    monkeypatch.setattr(transport,'_SUCCESS_ROUTE',{'image.tmdb.org':('1.1.1.1',time.monotonic()+60)})
    class Broken(Connection):
        def request(self,*a,**k):
            if failure=='TLS':raise ssl.SSLError('invalid certificate')
            raise transport.MetadataError('SHORT_READ')
    def connect(host,ip=None,timeout=5):
        calls.append(ip)
        return Broken() if ip else Connection()
    with pytest.raises(transport.MetadataError,match=failure):
        transport.fetch('https://image.tmdb.org/t/p/w342/a.jpg',time.monotonic()+2,connect=connect)
    assert calls==['1.1.1.1']  # No TLS bypass inside the failing request.
    transport.fetch('https://image.tmdb.org/t/p/w342/b.jpg',time.monotonic()+2,connect=connect)
    assert calls==['1.1.1.1',None]


class Response:
    status = 200
    def __init__(self, raw=b'{}', declared='2'):
        self.raw, self.declared = raw, declared
    def getheader(self, name):
        return self.declared if name == 'Content-Length' else None
    def getheaders(self):
        return []
    def read1(self, amount):
        raw, self.raw = self.raw[:amount], self.raw[amount:]
        return raw


class Connection:
    sock = None
    def request(self, *args, **kwargs):
        pass
    def getresponse(self):
        return Response()
    def close(self):
        pass


def test_declared_short_valid_json_is_not_success():
    with pytest.raises(transport.MetadataError, match='SHORT_READ'):
        transport.receive(Response(b'{}', '3'), Connection(), time.monotonic()+1, lambda: False)


@pytest.mark.parametrize('length', [None, '2'])
def test_complete_known_and_unknown_length(length):
    assert transport.receive(Response(b'{}', length), Connection(), time.monotonic()+1, lambda: False) == b'{}'


def test_cancellation_and_limit():
    with pytest.raises(transport.MetadataError, match='CANCELLED'):
        transport.receive(Response(), Connection(), time.monotonic()+1, lambda: True)
    with pytest.raises(transport.MetadataError, match='LIMIT'):
        transport.receive(Response(b'123', None), Connection(), time.monotonic()+1, lambda: False, 2)


def test_dns_response_uses_question_identity_and_public_ips():
    question = transport.dns_query('api.themoviedb.org', 123)
    raw = struct.pack('!HHHHHH', 123, 0x8180, 1, 1, 0, 0) + question[12:]
    raw += b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 300, 4) + socket.inet_aton('8.8.8.8')
    assert transport.dns_answers(raw, question) == ['8.8.8.8']
    with pytest.raises(transport.MetadataError):
        transport.dns_answers(raw[:1]+b'\xff'+raw[2:], question)
    with pytest.raises(transport.MetadataError, match='DNS_EMPTY'):
        transport.dns_answers(raw[:-4]+socket.inet_aton('192.168.1.1'), question)


def test_dns_fallback_keeps_original_tls_hostname():
    seen = []
    def connect(host, ip=None, timeout=5):
        seen.append((host, ip))
        if ip is None:
            class Failure(Connection):
                def request(self, *a, **kw):
                    raise socket.gaierror('fixture')
            return Failure()
        return Connection()
    result = transport.fetch('https://api.themoviedb.org/3/movie/1', time.monotonic()+1,
        connect=connect, resolver=lambda *args: ['8.8.8.8'])
    assert result['route'] == 'doh-direct'
    assert seen == [('api.themoviedb.org', None), ('api.themoviedb.org', '8.8.8.8')]


def test_tls_failure_never_weakens_validation_or_falls_back():
    class Failure(Connection):
        def request(self, *a, **kw):
            raise ssl.SSLCertVerificationError('fixture')
    with pytest.raises(transport.MetadataError, match='TLS'):
        transport.fetch('https://image.tmdb.org/a.jpg', time.monotonic()+1,
            connect=lambda *args, **kw: Failure(), resolver=lambda *args: pytest.fail('No TLS bypass'))


@pytest.mark.parametrize('url', ['http://api.themoviedb.org/3', 'https://api.themoviedb.org.evil/3',
                               'https://user@api.themoviedb.org/3', 'https://gimg0.baidu.com/relay'])
def test_no_unknown_origin_or_image_relay(url):
    with pytest.raises(transport.MetadataError, match='ORIGIN'):
        transport.fetch(url, time.monotonic()+1)


def test_requests_wrapper_preserves_safe_failure_stage_without_key(monkeypatch):
    import requests
    monkeypatch.setattr(transport, 'fetch', lambda *a,**k:(_ for _ in ()).throw(transport.MetadataError('TLS')))
    with pytest.raises(requests.ConnectionError) as caught:
        transport.request('GET','https://api.themoviedb.org/3/movie/1?api_key=never-log-this')
    assert caught.value.metadata_stage == 'TLS'
    assert str(caught.value) == 'METADATA_TLS'
    assert 'never-log-this' not in str(caught.value)


def test_body_failure_is_not_misreported_as_dns_or_connect():
    class Broken(Response):
        def read1(self, amount):
            raise ConnectionResetError('fixture-private-url')
    class BodyFailure(Connection):
        def getresponse(self):
            return Broken()
    with pytest.raises(transport.MetadataError) as caught:
        transport.fetch('https://api.themoviedb.org/3/movie/1',time.monotonic()+1,
            connect=lambda *a,**k:BodyFailure(), resolver=lambda *a:['8.8.8.8'])
    assert caught.value.stage == 'BODY' and 'fixture' not in str(caught.value)


def test_unknown_error_stage_cannot_leak_server_or_url():
    assert str(transport.MetadataError('secret-url-and-key')) == 'METADATA_UNKNOWN'


@pytest.mark.parametrize('url',[None,{},'https://image.tmdb.org:invalid/t/p/a.jpg'])
def test_malformed_url_is_a_fixed_origin_error(url):
    with pytest.raises(transport.MetadataError,match='ORIGIN'):
        transport.fetch(url,time.monotonic()+1)


def test_doh_success_cache_obeys_bounded_dns_ttl_and_only_sends_hostname(monkeypatch):
    transport._DNS_CACHE.clear()
    calls=[]
    class Resolver(Connection):
        def request(self, method, path, body, headers):
            assert method=='POST' and path=='/dns-query'
            assert b'api_key' not in body and b'12345' not in body
            self.question=body
            calls.append(body)
        def getresponse(self):
            question=self.question
            raw=question[:2]+struct.pack('!HHHHH',0x8180,1,1,0,0)+question[12:]
            raw+=b'\xc0\x0c'+struct.pack('!HHIH',1,1,900,4)+socket.inet_aton('8.8.8.8')
            return Response(raw,str(len(raw)))
    before=time.monotonic()
    first=transport.resolve('image.tmdb.org',before+1,lambda:False,connect=lambda *a,**k:Resolver())
    second=transport.resolve('image.tmdb.org',before+1,lambda:False,connect=lambda *a,**k:pytest.fail('DNS cache hit'))
    assert first == second == ['8.8.8.8'] and len(calls)==1
    assert 0 < transport._DNS_CACHE['image.tmdb.org'][0]-before <= 301
    transport._DNS_CACHE.clear()


def test_safe_stage_survives_bundled_tmdb_boundary_without_duplicate_tls_retry(monkeypatch):
    import requests
    package=ModuleType('fixture_tmdb_transport')
    package.__path__=[str(ROOT/'addons/plugin.video.bobbi/lib/api/tmdbv3api')]
    monkeypatch.setitem(sys.modules,package.__name__,package)
    spec=importlib.util.spec_from_file_location(package.__name__+'.tmdb',Path(package.__path__[0])/'tmdb.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls=[]
    def requester(*a,**kw):
        calls.append(1)
        error=requests.ConnectionError('METADATA_TLS')
        error.metadata_stage='TLS'
        raise error
    with pytest.raises(module.TMDbException) as caught:
        module.TMDb._request_with_bounds(requester,'GET','https://api.themoviedb.org/3?api_key=secret',None,None,None)
    assert caught.value.metadata_stage=='TLS'
    assert 'METADATA_TLS' in str(caught.value) and 'secret' not in str(caught.value)
    assert calls == [1]

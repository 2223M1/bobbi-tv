"""The CE system reader is a raw-wire adapter, not a second account or HTTP policy."""
from contextlib import closing
from functools import partial
from http.client import IncompleteRead, RemoteDisconnected
import os
from pathlib import Path
import time
from threading import Event

import pytest

from test_ce_progressive_http import PAYLOAD, pipeline, wait_end
from test_online_transport import endpoint
from bobbi_core.share_origin import RangeOrigin
from bobbi_platform import ce_share_origin as ce

on_posix = pytest.mark.skipif(os.name != 'posix' or not Path(ce.SYSTEM_CURL).is_file(),
                              reason='requires the real POSIX system curl and socket pair')


@pytest.mark.parametrize(('platform','release','available','selected'), (
    ('linux','ID="CoreELEC"\n',True,True), ('linux','ID=coreelec\n',False,False),
    ('linux','NAME=CoreELEC\nID=debian\n',True,False), ('win32','ID=coreelec\n',True,False),
    ('linux','ID=android\n',True,False)))
def test_reader_is_a_ce_installation_capability(monkeypatch,platform,release,available,selected):
    monkeypatch.setattr(ce.sys,'platform',platform)
    monkeypatch.setattr(ce.os,'access',lambda path,flags: available and path==ce.SYSTEM_CURL)
    monkeypatch.setattr(ce.Path,'read_text',lambda *a,**k: release)
    factory=ce.installed_reader()
    assert (factory is not None) == selected
    if selected:
        assert factory().wire is ce.wire_socket


@pytest.mark.parametrize('value', ['line\nnext','line\rnext','null\x00','a'*8193])
def test_private_config_has_one_value_per_line(value):
    with pytest.raises(ValueError,match='SHARE_TRANSPORT_INVALID'):
        ce._quoted(value)
    assert ce._quoted('a"b\\c') == '"a\\"b\\\\c"'


@on_posix
@pytest.mark.parametrize('mode',['normal','chunked','short_once','expired','wrong_range','wrong_length','encoding','overflow'])
def test_actual_native_wire_uses_one_shared_range_and_retry_owner(mode):
    with pipeline(True,mode,real_origin=True,origin_factory=lambda:RangeOrigin(ce.wire_socket)) as (_,connect,calls,events,resolves,_):
        conn,resp=connect('bytes=117-524404')
        with closing(conn):
            if mode in ('wrong_range','wrong_length','encoding'):
                assert resp.status==503
            elif mode=='overflow':
                try: valid=resp.read()
                except (OSError,EOFError,IncompleteRead) as exc: valid=getattr(exc,'partial',b'')
                assert valid!=PAYLOAD[117:524405]
            else:
                assert resp.status==206 and resp.read()==PAYLOAD[117:524405]
        wait_end(events)
        if mode=='short_once':
            assert len(calls)>1 and calls[1][0]>117
        if mode=='expired':
            assert len(resolves)==2


@on_posix
def test_actual_native_tls_refuses_untrusted_peer_and_never_follows_redirect(endpoint,tmp_path,monkeypatch):
    origin=RangeOrigin(partial(ce.wire_socket, ca_file=tmp_path/'cert.pem'))
    headers={'User-Agent':'private fixture agent','Range':'bytes=1-','Connection':'close','Accept-Encoding':'identity'}
    request=dict(headers=headers,stream=True,allow_redirects=False,timeout=(2,2))
    endpoint.blob=bytes(range(256))*16
    children=[]
    spawn=ce.subprocess.Popen
    def start(argv,**options):
        assert not any('localhost' in arg or headers['User-Agent'] in arg for arg in argv)
        assert options['env']=={} and options['close_fds'] and argv[1]=='-q'
        child=spawn(argv,**options);children.append(child);return child
    monkeypatch.setattr(ce.subprocess,'Popen',start)
    monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:1')
    with origin.get(endpoint.url+'/resume',**request) as resp:
        assert resp.status_code==206 and b''.join(resp.iter_content(32768))==endpoint.blob[1:]
    with origin.get(endpoint.url+'/chunked',**request) as resp:
        assert b''.join(resp.iter_content(32768))==endpoint.blob
    with origin.get(endpoint.url+'/redirect',**request) as resp:
        assert resp.status_code==302
    with pytest.raises((OSError,RemoteDisconnected)), RangeOrigin(ce.wire_socket).get(endpoint.url+'/resume',**request):
        pytest.fail('untrusted endpoint')
    assert [r[0] for r in endpoint.requests]==['/resume','/chunked','/redirect']
    assert set(endpoint.sni)=={'localhost'} and all(p.poll() is not None for p in children)


@on_posix
def test_revocation_reaps_its_native_reader_while_the_origin_is_still_stalled(monkeypatch):
    wait,release=Event(),Event()
    processes=[]
    spawn=ce.subprocess.Popen
    def start(*args,**kw):
        proc=spawn(*args,**kw);processes.append(proc);return proc
    monkeypatch.setattr(ce.subprocess,'Popen',start)
    with pipeline(True,payload=PAYLOAD[:65536],body_pause=(16384,wait,release),
                  real_origin=True,origin_factory=lambda:RangeOrigin(ce.wire_socket)) as (service,connect,*_):
        conn,resp=connect()
        try:
            assert wait.wait(2) and resp.read(256)==PAYLOAD[:256]
            conn.close(); resp.close()
            # Revocation closes this instance even if no more payload is available.
            with service.lock:
                bindings=tuple(service.records.values())
            for binding in bindings: binding.revoke()
            cutoff=time.monotonic()+2
            while time.monotonic()<cutoff and processes[-1].poll() is None:
                time.sleep(.02)
            assert processes[-1].poll() is not None and not release.is_set()
        finally:
            release.set()
    assert processes and all(child.poll() is not None for child in processes)

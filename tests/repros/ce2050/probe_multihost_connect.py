#!/usr/bin/env python3
"""Real localhost IPv4+IPv6 connect stalls; no patched network behavior."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace

p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=a.repo.resolve()
for name in ('script.module.requests','script.module.urllib3','script.module.idna','script.module.certifi','script.module.charset_normalizer'):
    sys.path.insert(0,str(root/'third_party/addons'/name/'lib'))
for name in ('plugin.video.bobbi.torrent','script.module.bobbi.core'):
    sys.path.insert(0,str(root/'addons'/name/'lib'))
from bobbi_torrent.backend import Backend,BackendError
from bobbi_torrent import resolver,http_io
from urllib3.util import connection
import requests,urllib3

listeners=[];fill=[];backend=None
seen=[];tracked=[];entered=threading.Event();observations={}
original_getaddrinfo=socket.getaddrinfo
original_track=http_io.RequestIO.track
try:
    first=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    first.bind(('127.0.0.1',0));first.listen(0);listeners.append(first)
    port=first.getsockname()[1]
    records=socket.getaddrinfo('localhost',port,connection.allowed_gai_family(),socket.SOCK_STREAM)
    addresses=[]
    for family,kind,proto,canonical,address in records:
        assert ipaddress.ip_address(address[0]).is_loopback
        pair=(family,address)
        if pair not in addresses:addresses.append(pair)
    assert len(addresses)>=2, 'Fixture requires real localhost with at least two addresses'
    for family,address in addresses:
        if family==socket.AF_INET and address==('127.0.0.1',port):continue
        listener=socket.socket(family,socket.SOCK_STREAM)
        if family==socket.AF_INET6:listener.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
        listener.bind(address);listener.listen(0);listeners.append(listener)
    for family,address in addresses:
        for _ in range(8):
            sock=socket.socket(family,socket.SOCK_STREAM);sock.settimeout(.03)
            try:sock.connect(address);fill.append(sock)
            except socket.timeout:sock.close();break
        else:raise AssertionError('Failed to saturate queue')
    def lookup(*args,**kwargs):
        result=original_getaddrinfo(*args,**kwargs)
        if args[0]=='localhost' and args[1]==port:
            seen.extend([dict(family=int(r[0]),address=r[4][0]) for r in result]);entered.set()
        return result
    def track(guard,sock):
        tracked.append(time.monotonic());return original_track(guard,sock)
    socket.getaddrinfo=lookup;http_io.RequestIO.track=track
    backend=Backend(dict(schema=1,endpoint='http://localhost:'+str(port),auth=None,metadata_seconds=2,buffering_seconds=2))
    resolver.FILE_CHOICE_STATUS_SECONDS=.01
    runner=resolver.Resolver(backend,SimpleNamespace(active=lambda:None),SimpleNamespace())
    def choose(candidates):
        assert entered.wait(3)
        time.sleep(.05)
        observations['back']=time.monotonic()
        return None
    started=time.monotonic()
    result=runner.choose_with_status(choose,[dict(id=1)],'f'*40)
    returned=time.monotonic()
    assert result is None
    workers=[t.name for t in threading.enumerate() if t.name in ('bobbi-control-io','bobbi-file-choice-status')]
    assert not workers
    paths=['addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/http_io.py','addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/backend.py','addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/resolver.py','third_party/addons/script.module.urllib3/lib/urllib3/util/connection.py']
    receipt=dict(schema=1,scope='Actual vendored Requests and real localhost DNS/address enumeration plus saturated loopback accept queues',
        simulated_getaddrinfo=False,simulated_connect=False,real_device=False,requests=requests.__version__,urllib3=urllib3.__version__,
        configured_endpoint_host='localhost',lookup_results=seen,request_budget_seconds=2,
        elapsed_seconds=round(returned-started,3),seconds_after_back=round(returned-observations['back'],3),
        socket_track_calls=len(tracked),workers_at_return=workers,outcome='back',
        source=[dict(path=x,sha256=hashlib.sha256((root/x).read_bytes()).hexdigest()) for x in paths])
    a.output.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
finally:
    socket.getaddrinfo=original_getaddrinfo;http_io.RequestIO.track=original_track
    if backend is not None:backend.close()
    for sock in fill+listeners:sock.close()

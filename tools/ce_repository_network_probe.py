"""Read-only DNS/TLS check for the single author-repository hostname."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

REMOTE = r'''
import ipaddress,json,pathlib,socket,ssl,time,urllib.request,xml.etree.ElementTree as ET
host='raw.githubusercontent.com'
path='/Sam-Max/repository.jacktook/master/repo/zips/addons.xml.md5'
out={'read_only':True,'host':host,'system_dns':[],'doh':[],'https_checks':[]}
try:out['system_dns']=sorted({r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
except OSError as error:out['system_dns_error']=type(error).__name__
for url in ('https://dns.alidns.com/resolve?name='+host+'&type=A',
 'https://cloudflare-dns.com/dns-query?name='+host+'&type=A'):
 try:
  request=urllib.request.Request(url,headers={'Accept':'application/dns-json'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as response:
   data=json.loads(response.read(8192))
  answers=[r['data'] for r in data.get('Answer',[]) if r.get('type')==1 and ipaddress.ip_address(r['data']).is_global]
  out['doh'].append({'resolver':urllib.request.urlparse(url).hostname if hasattr(urllib.request,'urlparse') else url.split('/')[2], 'addresses':answers})
 except Exception as error:out['doh'].append({'resolver':url.split('/')[2],'error':type(error).__name__})
addresses=list(dict.fromkeys(out['system_dns']+[a for row in out['doh'] for a in row.get('addresses',[])]))
for address in addresses[:6]:
 start=time.monotonic()
 result={'address':address,'certificate_and_hostname_verified':False}
 try:
  if not ipaddress.ip_address(address).is_global:raise ValueError('NON_GLOBAL_DNS')
  with socket.create_connection((address,443),timeout=3) as sock:
   with ssl.create_default_context().wrap_socket(sock,server_hostname=host) as connection:
    result['certificate_and_hostname_verified']=True
    connection.sendall(('HEAD '+path+' HTTP/1.1\r\nHost: '+host+'\r\nConnection: close\r\n\r\n').encode())
    result['status_line']=connection.recv(512).split(b'\r\n',1)[0].decode('ascii',errors='replace')
 except Exception as error:result['error']=type(error).__name__
 result['seconds']=round(time.monotonic()-start,3)
 out['https_checks'].append(result)
settings=ET.parse('/storage/.kodi/userdata/guisettings.xml').getroot()
out['kodi_proxy_enabled']=next((n.text for n in settings if n.get('id')=='network.usehttpproxy'),None)
print(json.dumps(out))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError('Evidence already exists')
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('repo_network_transport', args.transport_source / 'ui-redesign/tools/device_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client, wire = module.connect()
    try:
        code, result, diagnostic = wire.readonly(client, REMOTE.encode(), deadline_seconds=45)
    finally:
        client.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False))
    if code or diagnostic:
        raise RuntimeError('Read-only network check failed')


if __name__ == '__main__':
    main()

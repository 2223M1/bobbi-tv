"""Replay the retained Twelve Angry Men selected tuple; no video body fetch."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import json,pathlib,sys,time,types,traceback,hashlib
root=pathlib.Path('/storage/.kodi')
for addon in ('script.module.bobbi.platform','script.module.bobbi.core','script.module.bobbi.catalog'):
    sys.path.insert(0,str(root/'addons'/addon/'lib'))
sys.modules['xbmcvfs']=types.SimpleNamespace(translatePath=lambda value:value.replace('special://profile/',str(root/'userdata')+'/'))
from bobbi_catalog.api import Client,ShareError,valid_cdn
from bobbi_core.juku_catalog import Cache,selected
name='12.Angry.Men.1957.2160p.UHD.BluRay.REMUX.HEVC.DV.HDR.DTS-HD.MA.2.0-HDHIVE.mkv'
cache=Cache(readonly=True)
try:
    matches=[]
    for record in cache.db.execute('SELECT key,media,payload FROM selections WHERE media LIKE ? LIMIT 100',('%389%',)):
        row=json.loads(record['payload'])
        if name in row.get('name','') and row.get('size')==58762851801:
            matches.append((record['key'],record['media'],row))
finally:
    cache.close()
assert len(matches)==1,'EXACT_RETAINED_SELECTION_NOT_UNIQUE'
key,media,old=matches[0]
row=selected('am6bjuku://'+key,'juku:'+key,old['name'],old['size'],media)
fields={}
class Capture:
    def __init__(self,opener): self.opener=opener
    def open(self,*args,**kwargs):
        response=self.opener.open(*args,**kwargs)
        class Response:
            headers=response.headers
            fp=response.fp
            raw=bytearray()
            def read(self,n): return self.read1(n)
            def read1(self,n):
                data=response.read1(n)
                if len(self.raw)+len(data)<=2*1024**2:self.raw.extend(data)
                return data
            def __enter__(self):return self
            def __exit__(self,*args):
                response.close()
                try:
                    value=json.loads(self.raw)
                    fields['api_state']=value.get('state') is True
                    for key in ('errno','code','errcode'):
                        raw=value.get(key)
                        if str(raw).isdigit() and len(str(raw))<=10:fields['api_'+key]=int(raw)
                    # Emit only a closed vocabulary, never the upstream body.
                    message=str(value.get('error') or value.get('message') or value.get('msg') or '')
                    terms={'file_missing':('不存在','已删除'), 'share_cancelled':('已取消','已失效'),
                        'login':('登录',), 'password':('访问码','提取码','密码'), 'membership':('会员',),
                        'save_required':('转存','接收'), 'file_blocked':('违规','举报'), 'file_size':('50G','50g')}
                    fields['message_categories']=[k for k,words in terms.items() if any(w in message for w in words)]
                except (ValueError,TypeError,AttributeError):pass
        return Response()
class Probe(Client):
    def get(self,*args,**kwargs):
        data=super().get(*args,**kwargs)
        fields.update(fid_present='fid' in data,name_present='fn' in data,size_present='fs' in data,
            fid_equal=str(data.get('fid'))==row['fid'],name_equal=data.get('fn')==row['name'],
            size_equal=str(data.get('fs'))==str(row['size']),url_present=bool(data.get('url')))
        return data
began=time.monotonic()
report=dict(media=media,selection_key=key,bytes=row['size'],same_cached_file=True)
try:
    client=Probe()
    client.opener=Capture(client.opener)
    address=client.resolve(row['share'],row,time.monotonic()+8)
    report.update(resolved=True,url_valid=valid_cdn(address.partition('|')[0]))
except Exception as error:
    code=getattr(error,'code',None)
    report.update(resolved=False,error_class=type(error).__name__,
        category=code if code in ShareError.CODES else 'local_exception',
        frames=[dict(module=pathlib.Path(f.filename).name,function=f.name,line=f.lineno)
                for f in traceback.extract_tb(error.__traceback__)][-8:])
report.update(milliseconds=round((time.monotonic()-began)*1000),response_shape=fields)
print(json.dumps(report,ensure_ascii=False))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport-source', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('ce_grant_transport', args.transport_source/'ui-redesign/tools/device_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client, wire = transport.connect()
    try:
        script = ('import json,traceback,pathlib\ntry:\n    exec(compile(' + repr(REMOTE)
            + ',"ce-grant-probe","exec"))\nexcept Exception as error:\n'
              '    print(json.dumps(dict(error_class=type(error).__name__, frames=['
              'dict(module=pathlib.Path(f.filename).name,function=f.name,line=f.lineno) '
              'for f in traceback.extract_tb(error.__traceback__)])))\n')
        rc, result, diagnostic = wire.readonly(client, script.encode(), deadline_seconds=25)
    finally:
        client.close()
    output = ROOT/'review-evidence'/('ce2012-same-file-grant-'+str(time.time_ns())+'.json')
    output.write_text(json.dumps(dict(exit_code=rc,result=result,diagnostic_present=bool(diagnostic)),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(evidence=str(output),result=result)))
    return 1 if rc or diagnostic or not result.get('resolved') else 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Pinned, read-only CE dependency/configuration checks; never emit credentials."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import sys
sys.dont_write_bytecode=True
import hashlib, importlib, json, os, pathlib, re, struct, subprocess, sysconfig, types, urllib.request, xml.etree.ElementTree as ET
out={'schema':1,'mode':'readonly','python':sys.version.split()[0],'pointer_bytes':struct.calcsize('P'),'addons':[],'crypto':{},'paths':{}}
def elf(path):
    with pathlib.Path(path).open('rb') as stream: raw=stream.read(20)
    return {'class':raw[4],'machine':struct.unpack('<H',raw[18:20])[0]} if raw[:4]==b'\x7fELF' else None
out['python_elf']=elf(sys.executable)
for base in ('/usr/share/kodi/addons','/storage/.kodi/addons'):
    path=pathlib.Path(base)/'script.module.pycryptodome/addon.xml'
    if path.is_file():
        meta=ET.parse(path).getroot()
        out['addons'].append(dict(root=str(path.parent),version=meta.get('version'),extensions=[n.attrib for n in meta.findall('extension')]))
try:
    request=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',data=json.dumps(dict(jsonrpc='2.0',id=1,method='Addons.GetAddonDetails',params={'addonid':'script.module.pycryptodome','properties':['version','enabled','path']})).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=4) as response: out['kodi_addon']=json.load(response)
except Exception as error: out['kodi_addon']={'error_type':type(error).__name__}
try:
    pids=subprocess.check_output(['pidof','kodi.bin']).decode().split()
    out['kodi_elf']=[elf('/proc/'+pid+'/exe') for pid in pids]
    maps=pathlib.Path('/proc/'+pids[0]+'/maps').read_text()
    out['kodi_python_libraries']=sorted(set(line.split()[-1] for line in maps.splitlines() if 'libpython' in line))
except Exception as error: out['kodi_elf_error']=type(error).__name__
for namespace in ('Cryptodome','Crypto'):
    try:
        module=importlib.import_module(namespace)
        out['crypto'][namespace]=dict(file=str(module.__file__),version=getattr(module,'__version__','unknown'))
    except Exception as error: out['crypto'][namespace]={'error_type':type(error).__name__}
try:
    crypto_stage='module'
    module=types.ModuleType('candidate_juku_api')
    module.__file__='candidate_juku_api.py'
    exec(JUKU_SOURCE,module.__dict__)
    crypto_stage='ecc_import'
    ECC=module.crypto_module('Crypto.PublicKey.ECC')
    crypto_stage='dss_import'
    DSS=module.crypto_module('Crypto.Signature.DSS')
    out['dss_expected_types']={name:getattr(value,'__module__','') for name,value in vars(DSS).items() if isinstance(value,type)}
    crypto_stage='sha256_import'
    SHA256=module.crypto_module('Crypto.Hash.SHA256')
    crypto_stage='aes_import'
    AES=module.crypto_module('Crypto.Cipher.AES')
    crypto_stage='p256_generate'
    key=ECC.generate(curve='P-256')
    digest=SHA256.new(b'bobbi-readonly-abi-probe')
    crypto_stage='p256_sign_verify'
    signature=DSS.new(key,'fips-186-3').sign(digest)
    DSS.new(key.public_key(),'fips-186-3').verify(digest,signature)
    crypto_stage='aes_encrypt'
    encrypted=AES.new(b'0'*16,AES.MODE_ECB).encrypt(b'1'*16)
    out['candidate_crypto']={'ecc_p256_sign_verify':True,'aes_encrypt':len(encrypted)==16,'namespace':ECC.__name__.split('.')[0]}
except Exception as error: out['candidate_crypto']={'error_type':type(error).__name__,'stage':crypto_stage,'code':getattr(error,'code',''),'local_fixture_error':str(error)[:200]}
try:
    from Crypto.PublicKey import ECC as old_ecc
    from Crypto.Signature import DSS as old_dss
    from Crypto.Hash import SHA256 as old_hash
    old_key=old_ecc.generate(curve='P-256')
    old_digest=old_hash.new(b'bobbi-readonly-abi-probe')
    old_signature=old_dss.new(old_key,'fips-186-3').sign(old_digest)
    old_dss.new(old_key.public_key(),'fips-186-3').verify(old_digest,old_signature)
    out['crypto_namespace_fixture']={'p256_sign_verify':True}
except Exception as error: out['crypto_namespace_fixture']={'error_type':type(error).__name__,'local_fixture_error':str(error)[:200]}
try:
    old_search=list(sys.path)
    sys.path[:]=[item for item in sys.path if 'site-packages' not in item and '/kodi/addons/' not in item]
    for name in list(sys.modules):
        if name in ('Crypto','Cryptodome') or name.startswith(('Crypto.','Cryptodome.')): del sys.modules[name]
    module._CRYPTO_NAMESPACE=None
    isolated_ecc=module.crypto_module('Crypto.PublicKey.ECC')
    isolated_key=isolated_ecc.generate(curve='P-256')
    isolated_signature=module.sign_payload(isolated_key,b'bobbi-isolated-abi-probe')
    module.crypto_module('Crypto.Signature.DSS').new(isolated_key.public_key(),'fips-186-3',encoding='binary').verify(module.crypto_module('Crypto.Hash.SHA256').new(b'bobbi-isolated-abi-probe'),isolated_signature)
    out['candidate_crypto_isolated']={'p256_sign_verify':True,'namespace':module._CRYPTO_NAMESPACE,'no_path_widening':all('site-packages' not in item and '/kodi/addons/' not in item for item in sys.path)}
except Exception as error: out['candidate_crypto_isolated']={'error_type':type(error).__name__,'local_fixture_error':str(error)[:200]}
finally: sys.path[:]=old_search
for key,path in [('legacy_assrt','/storage/.config/am6b-subtitles283/assrt-token'),('candidate_assrt','/storage/.kodi/userdata/addon_data/plugin.video.bobbi/assrt-token')]:
    value=pathlib.Path(path)
    out['paths'][key]={'exists':value.is_file(),'valid_shape':bool(re.fullmatch(r'[A-Za-z0-9]{32}',value.read_text().strip())) if value.is_file() and value.stat().st_size<4096 else False}
old=pathlib.Path('/storage/.config/am6b-subtitles283/assrt-token')
new=pathlib.Path('/storage/.kodi/userdata/addon_data/plugin.video.bobbi/assrt-token')
out['assrt_same']=old.is_file() and new.is_file() and old.read_bytes()==new.read_bytes()
for name,path in [('legacy','/storage/.local/share/bobitv/preparation-runtime/r3-20260922/config.json'),('candidate','/storage/.kodi/userdata/addon_data/script.module.bobbi.platform/preparation.json')]:
    config=pathlib.Path(path)
    result={'exists':config.is_file()}
    if config.is_file():
        value=json.loads(config.read_text())
        for key in ('ffprobe','font_tool','font_native_directory','tmdb_api_key_file','cd2_token_file','python_library_directory'):
            if key in value:
                item=pathlib.Path(value[key])
                result[key]={'path':str(item),'exists':item.exists(),'file':item.is_file(),'directory':item.is_dir(),'executable':os.access(str(item),os.X_OK)}
                if key in ('ffprobe','font_tool') and item.is_file(): result[key]['elf']=elf(item)
    out['paths'][name+'_preparation']=result
print(json.dumps(out))
'''


def run(source, output):
    sys.path.insert(0, str(source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('dependencies_transport',source/'ui-redesign/tools/device_transport.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    juku=(ROOT/'addons/script.module.bobbi.core/lib/bobbi_core/juku_api.py').read_text(encoding='utf-8')
    client,wire=module.connect()
    try:
        code,result,diagnostic=wire.readonly(client,('JUKU_SOURCE='+repr(juku)+'\n'+REMOTE).encode(),deadline_seconds=45)
        if code or diagnostic: raise RuntimeError('Read-only dependency probe failed')
    finally: client.close()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'review-evidence/ce-dependencies-preflight.json')
    args=parser.parse_args()
    run(args.transport_source,args.output)

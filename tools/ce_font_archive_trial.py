"""Run candidate listing parser in an isolated, bounded existing decoder.

Uses only the exact already-downloaded 47 MB trial font RAR. No cloud read,
program replacement, font activation, player command or service restart.
"""
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = Path('D:/AM6B-Project/AM6B-review-ui-anirss-20261018')
REMOTE = r'''
import hashlib,json,pathlib,subprocess,sys,time,urllib.request
archive=pathlib.Path('/storage/.local/share/bobbi-private-trials/20261020/font-rar-ggbas0w7/fonts.rar')
assert not archive.is_symlink() and archive.stat().st_size==47296835
sha=hashlib.sha256(archive.read_bytes()).hexdigest()
assert sha=='0cdf357b08a3e48d0664a6afe6e382ccf3bc9b54dd24209c83d7a6d872efa1be'
root=pathlib.Path('/storage/.kodi')
config=json.loads((root/'userdata/addon_data/script.module.bobbi.platform/preparation.json').read_text())
output=archive.parent/('candidate-'+str(time.time_ns()))
def idle():
 req=urllib.request.Request('http://127.0.0.1:8080/jsonrpc',json.dumps(dict(jsonrpc='2.0',id=1,method='Player.GetActivePlayers')).encode(),{'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=2) as response:return json.load(response).get('result')==[]
assert idle(),'PLAYBACK_ACTIVE'
library=str(root/'addons/script.module.bobbi.core/lib')
worker=library+'/bobbi_core/font_extract_worker.py'
code='import sys,types,runpy\nsys.path.insert(0,'+repr(library)+')\nimport bobbi_core\nm=types.ModuleType("bobbi_core.font_archive")\nexec('+repr(PARSER)+',m.__dict__)\nsys.modules[m.__name__]=m\nrunpy.run_path('+repr(worker)+',run_name="__main__")'
args=[sys.executable,'-B','-c',code,'--tool',config['font_tool'],'--archive',str(archive),'--sha256',sha,'--output',str(output)]
process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
began=time.monotonic()
try:
 while process.poll() is None:
  if time.monotonic()-began>45 or not idle():raise RuntimeError('TRIAL_CANCELLED')
  try:process.wait(timeout=.5)
  except subprocess.TimeoutExpired:pass
except BaseException:
 import os,signal
 os.killpg(process.pid,signal.SIGKILL);process.wait();raise
stdout,stderr=process.communicate()
report=json.loads((output/'result.json').read_text())
print(json.dumps(dict(exit_code=process.returncode,report=report,stderr=stderr.decode(errors='replace')[-3000:]),ensure_ascii=False))
'''

sys.path.insert(0,str(TRANSPORT/'ui-redesign/runtime/ssh-python'))
spec=importlib.util.spec_from_file_location('font_probe_transport',TRANSPORT/'ui-redesign/tools/device_transport.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
client,wire=transport.connect()
try:
    parser=(ROOT/'addons/script.module.bobbi.core/lib/bobbi_core/font_archive.py').read_text(encoding='utf-8')
    code,result,diagnostic=wire.readonly(client,('PARSER='+repr(parser)+'\n'+REMOTE).encode(),deadline_seconds=55)
finally:
    client.close()
path=ROOT/'review-evidence/ce-20261020'/('font-rar-candidate-'+str(time.time_ns())+'.json')
path.write_text(json.dumps(dict(result=result,exit_code=code,diagnostic_present=bool(diagnostic)),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report=result.get('report',{})
print(json.dumps(dict(evidence=str(path),exit_code=result.get('exit_code'),state=report.get('state'),fonts=len(report.get('fonts',[])),seconds=report.get('seconds'),error=result.get('stderr')),ensure_ascii=False))
if code or diagnostic or result.get('exit_code') or report.get('state')!='EXTRACTED_FONTS_NOT_BOUND_OR_LOADED':raise SystemExit(1)

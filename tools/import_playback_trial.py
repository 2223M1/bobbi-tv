"""Mechanical namespace import of the reviewed, SHA-pinned CE trial harness."""
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('D:/AM6B-Maintainable/20260912-133935/execution/release317/trial.py')
SHA256 = 'd92d7c33c74027b6c6ca0ceb2b4c4e5625d621c3f670f8fd00b7b0d15aa6a87f'
WORKS = {
    'wild_tales': dict(title='Wild Tales', tmdb_id=265195, kind='movie', year=2014),
    'girls_last_tour': dict(title="Girls' Last Tour", tmdb_id=74185, kind='tv', year=2017, season=1, episode=1),
}
BRIDGE = '''def call(message):
    # Real device-local host IPC; CLI probes have no xbmcvfs interpreter.
    config=json.loads(Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform/runtime.json').read_text())
    request=urllib.request.Request('http://127.0.0.1:%d/control'%config['port'],
        data=json.dumps(dict(action='playback',body=message)).encode(),
        headers={'Authorization':'Bearer '+config['token'],'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=.3) as response:
        result=json.load(response)
    if result.get('ok') is not True:raise RuntimeError('PLAYBACK_OWNER_UNAVAILABLE')
    return result['result']
'''


def main():
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA256:
        raise ValueError('Reviewed trial source changed')
    text=raw.decode('utf-8')
    lines=text.splitlines(keepends=True)
    changes=[]
    for node in ast.parse(text).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            if node.targets[0].id=='BASE':
                changes.append((node.lineno,node.end_lineno,"BASE=Path('/storage/.local/share/bobbi-private-trials/20261019')\n"))
            if node.targets[0].id=='TESTS':
                changes.append((node.lineno,node.end_lineno,'TESTS='+repr(WORKS)+'\n'))
    assert len(changes)==2
    for start,end,value in sorted(changes,reverse=True):lines[start-1:end]=[value]
    text=''.join(lines).replace('plugin.video.jacktook','plugin.video.bobbi').replace('script.module.am6b.core','script.module.bobbi.core').replace('am6b_core','bobbi_core')
    text=text.replace('BASE.mkdir(mode=0o700, exist_ok=True)', 'BASE.mkdir(mode=0o700, parents=True, exist_ok=True)')
    text=text.replace('from bobbi_core.playback_ipc import call',BRIDGE)
    compile(text,'ce_trial_remote','exec')
    (ROOT/'tools/ce_trial_remote.py').write_text(text,encoding='utf-8',newline='\n')
    print('Imported reviewed ordinary-UI trial; source SHA256='+SHA256)


if __name__=='__main__':main()
